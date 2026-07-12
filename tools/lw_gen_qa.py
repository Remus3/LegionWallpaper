"""Stateless QA scorer for one lw-gen candidate batch (Phase 2 of the sidecar).

Reads a batch directory produced by tools/lw_gen_run.py, scores every candidate
PNG, applies the two-stage gate, writes a per-candidate cand_<NN>.qa.json sidecar
and updates gen_manifest.json candidates[] in place (atomic write). Rank / promote
decisions are NOT made here - that is tools/lw_gen_promote.py.

Gate (HARD ordering, Stage A gates Stage B):
  Stage A (subject identity): subject_cos >= T_subj AND margin >= T_margin AND the
    subject is the argmax over the distractor set (subject_cos > off_cos).
    Fail reason: "wrong_subject" (below floor or not argmax) else "weak_margin".
  Stage B (only if A passed) (image quality): aesthetic >= T_aes AND lap_var >= T_blur.
    Fail reason: "degenerate" (low aesthetic) else "blurry" (low sharpness).
  verdict PASS iff A and B pass; else REJECT with the FIRST failing reason.

CI constraint (read before editing imports): committed tests import this module on
Python 3.12 with only numpy + Pillow available. numpy is a top-level import; PIL is
imported lazily. open_clip, torch and cv2 are NOT available in CI and must never be
imported at module top level - the real CLIP scorer lazy-imports them inside its
body, and tests inject a stub scorer so no model is ever loaded. lap_var is computed
numpy-only (no cv2). Any file this module writes uses an atomic write (tmp then
os.replace) per the project hard rules.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

import numpy as np

# --------------------------------------------------------------------------
# Fallback thresholds + distractors, used only when tools/lw_gen_config.json
# cannot be read. The live values come from config qa{} (see load_config).
# --------------------------------------------------------------------------
DEFAULT_THRESHOLDS: Dict[str, float] = {
    "T_subj": 0.26,
    "T_margin": 0.05,
    "T_aes": 0.45,
    "T_blur": 100.0,
}
DEFAULT_DISTRACTORS = [
    "Darius", "Garen", "Katarina", "Ahri", "Lux", "Jinx", "Yasuo",
    "Hecarim", "Illaoi", "blank canvas", "generic anime character",
    "generic character", "abstract art", "landscape photo",
]

# Reason codes (contract-locked, must match promote + manifest schema).
REASON_WRONG_SUBJECT = "wrong_subject"
REASON_WEAK_MARGIN = "weak_margin"
REASON_DEGENERATE = "degenerate"
REASON_BLURRY = "blurry"

VERDICT_PASS = "PASS"
VERDICT_REJECT = "REJECT"


@dataclass
class RawScore:
    """Per-candidate raw scores emitted by a scorer (real CLIP or a test stub).

    off_cos is the MAX cosine over the distractor set (subject/aliases excluded),
    so the subject is the argmax over distractors iff subject_cos > off_cos.
    """

    subject_cos: float
    off_cos: float
    aesthetic: float
    lap_var: float


@dataclass
class Grade:
    """Result of applying the two-stage gate to one RawScore."""

    verdict: str
    reason: Optional[str]
    stage_a_pass: bool
    stage_b_pass: Optional[bool]  # None means Stage B was never consulted
    margin: float


# Scorer is any callable that maps an image path to a RawScore.
Scorer = Callable[[str], RawScore]


# --------------------------------------------------------------------------
# M1 weapon-region CLIP gate (design_weapon.md sec 6). Proves an accepted
# weapon fix is CANONICAL (a wrist crossbow), not merely that the subject
# survived. Scores a ROI CROP - not the whole frame - so it is immune to the
# DoF blur confound (GEN_RETUNE.md:116-123). Positives/distractors are the
# design-of-record text sets. weapon_cos = MEAN cosine vs positives; weapon_off
# = MAX cosine vs distractors (the crossbow is the argmax iff cos > off).
# --------------------------------------------------------------------------
WEAPON_POSITIVES = [
    "a wrist-mounted mechanical repeating crossbow",
    "a crossbow mounted on an armored forearm",
    "a small mechanical crossbow",
]
WEAPON_DISTRACTORS = [
    "a longbow", "a sword blade", "a rifle", "an axe", "a spear",
    "bat wings", "an empty gloved hand", "a blurry dark shape",
]
# Placeholder floors: the live values come from config weapon{} after the M1
# calibration (good official-skin crops vs known-bad candidate crops). T_wblur
# mirrors the QA blur floor (GEN_RETUNE.md); T_weapon/T_wmargin are set at the
# good/bad separation midpoint and MUST NOT ship at these seed values.
WEAPON_DEFAULT_THRESHOLDS: Dict[str, float] = {
    "T_weapon": 0.22,
    "T_wmargin": 0.03,
    "T_wblur": 150.0,
}

# Weapon reason codes (parallel to the QA Stage-A/B codes).
REASON_WEAPON_OFFCLASS = "weapon_offclass"      # below floor OR not the argmax
REASON_WEAPON_WEAK_MARGIN = "weapon_weak_margin"
REASON_WEAPON_MUSH = "weapon_mush"              # region lap_var below T_wblur


@dataclass
class WeaponScore:
    """Per-crop weapon-gate raw scores (real CLIP or a test stub).

    weapon_cos is the MEAN cosine over WEAPON_POSITIVES; weapon_off is the MAX
    cosine over WEAPON_DISTRACTORS; lap_var is the ROI crop's local sharpness.
    """

    weapon_cos: float
    weapon_off: float
    lap_var: float


@dataclass
class WeaponGrade:
    """Result of the weapon gate on one WeaponScore."""

    verdict: str
    reason: Optional[str]
    margin: float


def weapon_grade(scores: "WeaponScore", thresholds: Dict[str, float]) -> "WeaponGrade":
    """Apply the 4-clause weapon gate (design_weapon.md sec 6) to one WeaponScore.

    PASS iff weapon_cos >= T_weapon AND weapon_cos > weapon_off AND
    (weapon_cos - weapon_off) >= T_wmargin AND lap_var >= T_wblur. The reason
    ordering is HARD (offclass -> weak_margin -> mush), mirroring the QA grade.
    """
    t_weapon = float(thresholds["T_weapon"])
    t_wmargin = float(thresholds["T_wmargin"])
    t_wblur = float(thresholds["T_wblur"])

    margin = scores.weapon_cos - scores.weapon_off
    is_argmax = scores.weapon_cos > scores.weapon_off

    if scores.weapon_cos < t_weapon or not is_argmax:
        return WeaponGrade(VERDICT_REJECT, REASON_WEAPON_OFFCLASS, margin)
    if margin < t_wmargin:
        return WeaponGrade(VERDICT_REJECT, REASON_WEAPON_WEAK_MARGIN, margin)
    if scores.lap_var < t_wblur:
        return WeaponGrade(VERDICT_REJECT, REASON_WEAPON_MUSH, margin)
    return WeaponGrade(VERDICT_PASS, None, margin)


# --------------------------------------------------------------------------
# Pure gate logic (no I/O, no model) - the unit-tested core.
# --------------------------------------------------------------------------
def grade(scores: RawScore, thresholds: Dict[str, float]) -> Grade:
    """Apply the HARD Stage-A-before-Stage-B gate to one RawScore.

    Stage B is only evaluated when Stage A passes; a candidate that fails A always
    reports an A reason (wrong_subject / weak_margin) even if it would also fail B.
    """
    t_subj = float(thresholds["T_subj"])
    t_margin = float(thresholds["T_margin"])
    t_aes = float(thresholds["T_aes"])
    t_blur = float(thresholds["T_blur"])

    margin = scores.subject_cos - scores.off_cos

    # ---- Stage A: subject identity (gates Stage B) ----
    is_argmax = scores.subject_cos > scores.off_cos
    if scores.subject_cos < t_subj or not is_argmax:
        return Grade(VERDICT_REJECT, REASON_WRONG_SUBJECT, False, None, margin)
    if margin < t_margin:
        return Grade(VERDICT_REJECT, REASON_WEAK_MARGIN, False, None, margin)

    # ---- Stage B: image quality (only reached when A passed) ----
    if scores.aesthetic < t_aes:
        return Grade(VERDICT_REJECT, REASON_DEGENERATE, True, False, margin)
    if scores.lap_var < t_blur:
        return Grade(VERDICT_REJECT, REASON_BLURRY, True, False, margin)

    return Grade(VERDICT_PASS, None, True, True, margin)


# --------------------------------------------------------------------------
# numpy-only no-reference laplacian variance (CI-safe; no cv2).
# --------------------------------------------------------------------------
_LAPLACIAN_4 = np.array([[0.0, 1.0, 0.0], [1.0, -4.0, 1.0], [0.0, 1.0, 0.0]])


def _to_gray(arr: np.ndarray) -> np.ndarray:
    a = np.asarray(arr, dtype=np.float64)
    if a.ndim == 2:
        return a
    if a.ndim == 3 and a.shape[2] >= 3:
        return 0.299 * a[:, :, 0] + 0.587 * a[:, :, 1] + 0.114 * a[:, :, 2]
    raise ValueError(f"expected 2D or HxWx3 array, got shape {a.shape}")


def _conv3(a: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    k = np.asarray(kernel, dtype=np.float64)
    p = np.pad(a, 1, mode="edge")
    out = np.zeros_like(a)
    h, w = a.shape
    for dy in range(3):
        for dx in range(3):
            coef = k[dy, dx]
            if coef == 0.0:
                continue
            out += coef * p[dy : dy + h, dx : dx + w]
    return out


def laplacian_variance(path: str) -> float:
    """No-reference blur metric: variance of the 4-neighbour Laplacian of the luma.

    Pure numpy + PIL (lazy). Mirrors cv2.Laplacian(gray, CV_64F).var() without cv2.
    """
    from PIL import Image  # lazy: CI has Pillow, but keep the import local

    with Image.open(path) as im:
        arr = np.asarray(im.convert("RGB"), dtype=np.float64)
    gray = _to_gray(arr)
    return float(np.var(_conv3(gray, _LAPLACIAN_4)))


# --------------------------------------------------------------------------
# Config + threshold resolution
# --------------------------------------------------------------------------
def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config(root: Optional[str] = None) -> Dict[str, Any]:
    """Load tools/lw_gen_config.json; return {} if it is absent or unreadable.

    Absence is tolerated so the module imports + runs before Phase-0 provisioning;
    resolve_thresholds falls back to DEFAULT_THRESHOLDS in that case.
    """
    root = root or _repo_root()
    path = os.path.join(root, "tools", "lw_gen_config.json")
    try:
        with open(path, encoding="utf-8") as fo:
            return json.load(fo)
    except (OSError, ValueError):
        return {}


def resolve_thresholds(config: Dict[str, Any], manifest: Dict[str, Any]) -> Dict[str, float]:
    """Thresholds = config qa{} defaults, then per-batch manifest 'qa_overrides'.

    manifest['qa_overrides'] (written by lw_gen_run from the brief) may override any
    of T_subj / T_margin / T_aes / T_blur. Missing keys fall back to config then to
    DEFAULT_THRESHOLDS, so the resolved dict is always fully populated.
    """
    resolved = dict(DEFAULT_THRESHOLDS)
    qa = (config or {}).get("qa", {})
    for key in DEFAULT_THRESHOLDS:
        if key in qa:
            resolved[key] = float(qa[key])
    overrides = (manifest or {}).get("qa_overrides", {}) or {}
    for key in DEFAULT_THRESHOLDS:
        if key in overrides and overrides[key] is not None:
            resolved[key] = float(overrides[key])
    return resolved


def resolve_weapon_thresholds(config: Dict[str, Any], manifest: Dict[str, Any]) -> Dict[str, float]:
    """Weapon floors = config weapon{} defaults, then per-batch weapon_overrides.

    Same shape as resolve_thresholds: missing keys fall back to config weapon{}
    then to WEAPON_DEFAULT_THRESHOLDS, so the resolved dict is always fully
    populated (T_weapon / T_wmargin / T_wblur).
    """
    resolved = dict(WEAPON_DEFAULT_THRESHOLDS)
    wcfg = (config or {}).get("weapon", {}) or {}
    for key in WEAPON_DEFAULT_THRESHOLDS:
        if key in wcfg and wcfg[key] is not None:
            resolved[key] = float(wcfg[key])
    overrides = (manifest or {}).get("weapon_overrides", {}) or {}
    for key in WEAPON_DEFAULT_THRESHOLDS:
        if key in overrides and overrides[key] is not None:
            resolved[key] = float(overrides[key])
    return resolved


# --------------------------------------------------------------------------
# Real CLIP scorer (lazy open_clip / torch). Never imported in CI (tests stub it).
# --------------------------------------------------------------------------
class ClipScorer:
    """open-clip ViT-L-14 scorer. Loads the model ONCE, scores each candidate.

    Not used by tests - the test suite injects a stub Scorer so no weights load.
    """

    def __init__(self, config: Dict[str, Any], manifest: Dict[str, Any]) -> None:
        self.clip_model = config.get("clip_model", "ViT-L-14")
        self.clip_pretrained = config.get("clip_pretrained", "openai")
        subject = manifest.get("subject", "")
        aliases = manifest.get("subject_aliases") or [subject]
        # subject target texts: the canonical wallpaper prompt plus any aliases.
        self.subject_texts = [f"a wallpaper of {subject}, a League of Legends champion"]
        self.subject_texts += [f"a wallpaper of {a}, a League of Legends champion" for a in aliases]
        cfg_distractors = config.get("distractors") or DEFAULT_DISTRACTORS
        alias_lower = {str(a).lower() for a in aliases} | {str(subject).lower()}
        self.distractor_texts = [d for d in cfg_distractors if str(d).lower() not in alias_lower]
        self._model = None
        self._tokenizer = None
        self._preprocess = None
        self._device = None
        self._subject_embed = None
        self._distractor_embed = None
        self._aes_embed = None

    def load(self) -> "ClipScorer":
        import open_clip  # lazy heavy dep
        import torch  # lazy heavy dep

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model, _, preprocess = open_clip.create_model_and_transforms(
            self.clip_model, pretrained=self.clip_pretrained
        )
        model = model.to(device).eval()
        tokenizer = open_clip.get_tokenizer(self.clip_model)
        self._model = model
        self._preprocess = preprocess
        self._tokenizer = tokenizer
        self._device = device
        self._subject_embed = self._encode_text(self.subject_texts)
        self._distractor_embed = self._encode_text(self.distractor_texts)
        self._aes_embed = self._encode_text(["a high quality image", "a low quality image"])
        return self

    def _encode_text(self, texts):
        import torch

        with torch.no_grad():
            tok = self._tokenizer(texts).to(self._device)
            emb = self._model.encode_text(tok)
            emb = emb / emb.norm(dim=-1, keepdim=True)
        return emb

    def _encode_image(self, path: str):
        import torch
        from PIL import Image

        with Image.open(path) as im:
            tensor = self._preprocess(im.convert("RGB")).unsqueeze(0).to(self._device)
        with torch.no_grad():
            emb = self._model.encode_image(tensor)
            emb = emb / emb.norm(dim=-1, keepdim=True)
        return emb

    def __call__(self, path: str) -> RawScore:
        import torch

        img = self._encode_image(path)
        subj = (img @ self._subject_embed.T).squeeze(0)
        subject_cos = float(subj.mean().item())
        dist = (img @ self._distractor_embed.T).squeeze(0)
        off_cos = float(dist.max().item()) if dist.numel() else -1.0
        aes = (img @ self._aes_embed.T).squeeze(0)
        aesthetic = float(torch.softmax(aes, dim=0)[0].item())
        lap = laplacian_variance(path)
        return RawScore(subject_cos, off_cos, aesthetic, lap)


class WeaponClipScorer:
    """open-clip weapon-region scorer for a ROI crop (design_weapon.md sec 6).

    Same lazy heavy-dep contract as ClipScorer (torch/open_clip imported only
    inside load/_encode - never in CI). Uses the SAME clip_model/clip_pretrained
    as the QA scorer (config: ViT-L-14-quickgelu / openai) so the two gates share
    one embedding space. Scores a CROP path: weapon_cos = MEAN cosine vs the
    crossbow positives, weapon_off = MAX cosine vs distractors, plus the crop's
    local laplacian variance.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.clip_model = config.get("clip_model", "ViT-L-14-quickgelu")
        self.clip_pretrained = config.get("clip_pretrained", "openai")
        wcfg = (config or {}).get("weapon", {}) or {}
        self.positive_texts = wcfg.get("positives") or list(WEAPON_POSITIVES)
        self.distractor_texts = wcfg.get("distractors") or list(WEAPON_DISTRACTORS)
        self._model = None
        self._tokenizer = None
        self._preprocess = None
        self._device = None
        self._positive_embed = None
        self._distractor_embed = None

    def load(self) -> "WeaponClipScorer":
        import open_clip  # lazy heavy dep
        import torch  # lazy heavy dep

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model, _, preprocess = open_clip.create_model_and_transforms(
            self.clip_model, pretrained=self.clip_pretrained
        )
        model = model.to(device).eval()
        tokenizer = open_clip.get_tokenizer(self.clip_model)
        self._model = model
        self._preprocess = preprocess
        self._tokenizer = tokenizer
        self._device = device
        self._positive_embed = self._encode_text(self.positive_texts)
        self._distractor_embed = self._encode_text(self.distractor_texts)
        return self

    def _encode_text(self, texts):
        import torch

        with torch.no_grad():
            tok = self._tokenizer(texts).to(self._device)
            emb = self._model.encode_text(tok)
            emb = emb / emb.norm(dim=-1, keepdim=True)
        return emb

    def _encode_image(self, path: str):
        import torch
        from PIL import Image

        with Image.open(path) as im:
            tensor = self._preprocess(im.convert("RGB")).unsqueeze(0).to(self._device)
        with torch.no_grad():
            emb = self._model.encode_image(tensor)
            emb = emb / emb.norm(dim=-1, keepdim=True)
        return emb

    def __call__(self, path: str) -> WeaponScore:
        img = self._encode_image(path)
        pos = (img @ self._positive_embed.T).squeeze(0)
        weapon_cos = float(pos.mean().item())
        dist = (img @ self._distractor_embed.T).squeeze(0)
        weapon_off = float(dist.max().item()) if dist.numel() else -1.0
        lap = laplacian_variance(path)
        return WeaponScore(weapon_cos, weapon_off, lap)


def weapon_crop_report(crop_path: str, scorer: "Callable[[str], WeaponScore]") -> Dict[str, float]:
    """Score one ROI crop and return a flat JSON-able dict.

    The body of the `--weapon-crop` helper mode: the weapon pass (in .venv-gen)
    shells this in .venv-metrics so torch/open_clip stay in the metrics venv.
    scorer is injectable (a WeaponClipScorer live, a stub in CI).
    """
    s = scorer(crop_path)
    return {"weapon_cos": s.weapon_cos, "weapon_off": s.weapon_off, "lap_var": s.lap_var}


# --------------------------------------------------------------------------
# Atomic JSON write (project hard rule)
# --------------------------------------------------------------------------
def _atomic_write_json(path: str, data: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fo:
        fo.write(json.dumps(data, indent=2) + "\n")
        fo.flush()
        os.fsync(fo.fileno())
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# Batch driver
# --------------------------------------------------------------------------
def _qa_sidecar_path(batch_dir: str, cand_file: str) -> str:
    stem = cand_file[:-4] if cand_file.lower().endswith(".png") else cand_file
    return os.path.join(batch_dir, stem + ".qa.json")


def score_batch(batch_dir: str, scorer: Optional[Scorer] = None,
                config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Score every candidate in batch_dir, write sidecars, update the manifest.

    scorer is injectable: pass a stub in tests to avoid any model load. When None,
    a ClipScorer is built + loaded from config/manifest.
    Returns the updated manifest dict.
    """
    manifest_path = os.path.join(batch_dir, "gen_manifest.json")
    with open(manifest_path, encoding="utf-8") as fo:
        manifest = json.load(fo)

    if config is None:
        config = load_config()
    thresholds = resolve_thresholds(config, manifest)

    if scorer is None:
        scorer = ClipScorer(config, manifest).load()

    candidates = manifest.get("candidates", [])
    for cand in candidates:
        cand_file = cand.get("file")
        if not cand_file:
            continue
        img_path = os.path.join(batch_dir, cand_file)
        scores = scorer(img_path)
        g = grade(scores, thresholds)

        cand["subject_cos"] = scores.subject_cos
        cand["off_cos"] = scores.off_cos
        cand["margin"] = g.margin
        cand["aesthetic"] = scores.aesthetic
        cand["lap_var"] = scores.lap_var
        cand["stage_a_pass"] = g.stage_a_pass
        cand["stage_b_pass"] = g.stage_b_pass
        cand["verdict"] = g.verdict
        cand["reason"] = g.reason

        sidecar = {
            "file": cand_file,
            "round": cand.get("round"),
            "seed": cand.get("seed"),
            "model": manifest.get("model"),
            "clip_model": manifest.get("clip_model"),
            "prompt": manifest.get("prompt"),
            "negative": manifest.get("negative"),
            "subject_cos": scores.subject_cos,
            "off_cos": scores.off_cos,
            "margin": g.margin,
            "aesthetic": scores.aesthetic,
            "lap_var": scores.lap_var,
            "stage_a_pass": g.stage_a_pass,
            "stage_b_pass": g.stage_b_pass,
            "verdict": g.verdict,
            "reason": g.reason,
            "thresholds": thresholds,
        }
        _atomic_write_json(_qa_sidecar_path(batch_dir, cand_file), sidecar)

    _atomic_write_json(manifest_path, manifest)
    return manifest


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Score one lw-gen candidate batch (stateless QA).")
    parser.add_argument("batch_dir", nargs="?", default=None,
                        help="path to images/_gen_scratch/<batch-id>/")
    parser.add_argument("--weapon-crop", dest="weapon_crop", default=None,
                        help="score ONE weapon ROI crop; print {weapon_cos, weapon_off, "
                             "lap_var} as JSON and exit (design_weapon.md sec 6/7.1)")
    args = parser.parse_args(argv)

    # Helper mode: score a single weapon ROI crop (the weapon pass shells this in
    # .venv-metrics so torch/open_clip never load in .venv-gen).
    if args.weapon_crop:
        try:
            scorer = WeaponClipScorer(load_config()).load()
            report = weapon_crop_report(os.path.abspath(args.weapon_crop), scorer)
        except Exception as exc:  # noqa: BLE001 - never surface a raw torch/clip trace
            print("qa: weapon-crop scoring failed - metrics venv not provisioned or a "
                  "scorer error (see logs).", file=sys.stderr)
            _log_error(exc)
            return 1
        print(json.dumps(report))
        return 0

    if not args.batch_dir:
        print("qa: batch_dir required (or use --weapon-crop <png>)", file=sys.stderr)
        return 2
    batch_dir = os.path.abspath(args.batch_dir)
    manifest_path = os.path.join(batch_dir, "gen_manifest.json")
    if not os.path.isfile(manifest_path):
        print(f"qa: no gen_manifest.json in {batch_dir}", file=sys.stderr)
        return 2
    try:
        manifest = score_batch(batch_dir)
    except Exception as exc:  # noqa: BLE001 - never surface a raw torch/clip trace
        print("qa: scoring failed - generator not provisioned or a scorer error "
              "(see logs). Run the Phase-0 setup (docs/GEN_MODELS.md).", file=sys.stderr)
        _log_error(exc)
        return 1

    passed = sum(1 for c in manifest.get("candidates", []) if c.get("verdict") == VERDICT_PASS)
    total = len(manifest.get("candidates", []))
    print(f"qa: scored {total} candidate(s), {passed} PASS -> {manifest_path}")
    return 0


def _log_error(exc: Exception) -> None:
    """Append the raw error to logs/ - never surface it to the user."""
    try:
        import datetime

        root = _repo_root()
        logs = os.path.join(root, "logs")
        os.makedirs(logs, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d")
        with open(os.path.join(logs, f"{stamp}.log"), "a", encoding="utf-8") as fo:
            fo.write(f"[lw_gen_qa] {type(exc).__name__}: {exc}\n")
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
