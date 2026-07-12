"""Legion Wallpaper - M1 weapon pass stage (detect -> mask -> inpaint), W1 rung.

The 4th gen-sidecar stage script. Wires the adopted DWPose localizer
(tools/lw_gen_localizer_eval.dwpose_backend) into a real, masked SDXL inpaint
re-roll of the wrist-mounted weapon region, honoring the interlock contract
(lw_gen_run.py:7-10): this stage shares ONLY the batch dir + gen_manifest.json,
it is never imported by run/qa/promote. Design of record:
docs/research/golden_designs/design_weapon.md (sec 3 W1, sec 4 mask, sec 5 API,
sec 6 identity assert, sec 7 integration).

Two modes:
  PROPOSE (wrist is None): render both-wrist ROI overlays into weapon_review/
    for the operator to pick the rig side. Mutates no candidate, inpaints
    nothing.
  FIX (wrist in {"left","right"}): per candidate, DWPose -> select side ->
    weapon_roi_from_keypoints. A fallback (no mask) routes to review with a
    sidecar + note, never inpaints. An ok ROI drives one masked inpaint roll,
    a HARD paste-back composite (out-of-mask pixels stay byte-identical), the
    outside-identity assertion, a cand_XX_wfix.png write, cand[file] advance,
    a cand_XX.weapon.json sidecar, and an atomic manifest write.

CI constraint (torch-free): this module imports ONLY stdlib + numpy + the two
torch-free project modules (lw_gen_run stage helpers, lw_gen_weaponfix geometry)
at top level. torch / diffusers / cv2 / onnxruntime are imported LAZILY inside
the real backend + real inpainter builders, which the test suite never reaches
(it injects stub backend + stub inpainter). The pure helpers
(select_wrist_inputs / paste_back / assert_outside_identity) are unit-tested
without any heavy dep.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

# Allow both `python tools/lw_gen_weaponpass.py <batch>` (script mode puts tools/
# on sys.path, not the repo root) and `from tools import lw_gen_weaponpass` to
# resolve the `tools` namespace package. Mirror lw_gen_localizer_eval's shim.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import lw_gen_localizer_eval as loc  # noqa: E402
from tools import lw_gen_run as gr  # noqa: E402
from tools.lw_gen_weaponfix import weapon_roi_from_keypoints  # noqa: E402

# --- W1 defaults (design_weapon.md sec 5) -----------------------------------
WEAPON_PROMPT = (
    "vayne, league of legends, wrist-mounted repeating crossbow, mechanical "
    "crossbow gauntlet on forearm, bat wing crossbow limbs, silver metal, "
    "loaded silver bolt, intricate mechanical detail, masterpiece, absurdres"
)
WEAPON_NEG = (
    "sword, blade, longbow, rifle, gun, axe, spear, staff, empty hand, "
    "extra fingers, deformed weapon, worst quality"
)
WEAPON_STEPS = 32
WEAPON_GUIDANCE = 6.0

_STAGE = "wfix"


# --------------------------------------------------------------------------
# Pure helpers (torch-free; unit-tested directly).
# --------------------------------------------------------------------------
def select_wrist_inputs(out, wrist):
    """Return (kp_map, side_hand) for the chosen wrist from a BackendOutput.

    The kp_map is passed through whole (the geometry reads the side keys); the
    hand list is the right_hand for wrist=="right" else the left_hand.
    """
    hand = out.right_hand if wrist == "right" else out.left_hand
    return out.kp_map, hand


def paste_back(cand_arr, inpainted_arr, mask_binary):
    """Hard paste-back: where mask_binary is True -> inpainted, else candidate.

    Outside-mask pixels are byte-identical to the candidate (np.where copies the
    candidate value verbatim). Result carries the candidate's dtype.
    """
    cand = np.asarray(cand_arr)
    inpainted = np.asarray(inpainted_arr)
    mask = np.asarray(mask_binary, dtype=bool)
    if cand.ndim == 3 and mask.ndim == 2:
        mask = mask[:, :, None]
    return np.where(mask, inpainted, cand).astype(cand.dtype)


def assert_outside_identity(orig_arr, final_arr, mask_binary):
    """Raise AssertionError unless final == orig on every pixel OUTSIDE the mask.

    The cleaning-pass-style non-regression guard (design_weapon.md sec 6): a
    weapon fix must never touch a pixel the mask did not cover.
    """
    orig = np.asarray(orig_arr)
    final = np.asarray(final_arr)
    mask = np.asarray(mask_binary, dtype=bool)
    if not np.array_equal(final[~mask], orig[~mask]):
        raise AssertionError(
            "weapon pass mutated pixels OUTSIDE the weapon mask "
            "(paste-back identity violated)"
        )


# --------------------------------------------------------------------------
# I/O helpers (atomic writes per project hard rule).
# --------------------------------------------------------------------------
def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fo:
        fo.write(json.dumps(data, indent=2) + "\n")
        fo.flush()
        os.fsync(fo.fileno())
    os.replace(tmp, path)


def _atomic_write_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="ascii") as fo:
        fo.write(text)
        fo.flush()
        os.fsync(fo.fileno())
    os.replace(tmp, path)


def _raw_stem(cand_file):
    """The RAW candidate stem (stage suffix + .png stripped): cand_00."""
    stem = cand_file[:-4] if cand_file.lower().endswith(".png") else cand_file
    for suf in ("_wfix", "_repair", "_finish"):
        if stem.endswith(suf):
            return stem[: -len(suf)]
    return stem


def _weapon_sidecar_path(batch_dir, cand_file):
    return os.path.join(batch_dir, _raw_stem(cand_file) + ".weapon.json")


def _load_config_safe():
    """Load tools/lw_gen_config.json; {} when absent (pre-provisioning safe)."""
    path = os.path.join(ROOT, "tools", "lw_gen_config.json")
    try:
        with open(path, encoding="utf-8") as fo:
            return json.load(fo)
    except (OSError, ValueError):
        return {}


# --------------------------------------------------------------------------
# Real SDXL inpainter builder (LAZY torch/diffusers - never reached in CI).
# --------------------------------------------------------------------------
def _build_real_inpainter(config):
    """Construct the SDXL inpaint closure by reusing lw_gen_run's base loader.

    AutoPipelineForInpainting.from_pipe(base, controlnet=None) yields a plain
    StableDiffusionXLInpaintPipeline sharing the base weights (zero extra VRAM;
    design_weapon.md sec 5). The returned closure matches the injectable
    inpainter contract: (image, mask_image, prompt, negative_prompt, strength,
    seed) -> PIL.Image.
    """
    from diffusers import AutoPipelineForInpainting

    model_abs = os.path.join(ROOT, config["model_path"])
    base = gr._load_pipeline(config, model_abs, fast=False)
    inpipe = AutoPipelineForInpainting.from_pipe(base, controlnet=None)

    def _inpaint(image, mask_image, prompt, negative_prompt, strength, seed):
        import torch

        generator = torch.Generator("cuda").manual_seed(int(seed))
        return inpipe(
            prompt=prompt, negative_prompt=negative_prompt,
            image=image, mask_image=mask_image, strength=float(strength),
            num_inference_steps=WEAPON_STEPS, guidance_scale=WEAPON_GUIDANCE,
            width=image.width, height=image.height, generator=generator,
        ).images[0]

    return _inpaint


# --------------------------------------------------------------------------
# Review routing (a fallback never inpaints; it records why + a note).
# --------------------------------------------------------------------------
def _route_to_review(batch_dir, cand_file, wrist, rung, fallback, min_conf):
    review_dir = os.path.join(batch_dir, "weapon_review")
    os.makedirs(review_dir, exist_ok=True)
    note = os.path.join(review_dir, _raw_stem(cand_file) + ".note.txt")
    _atomic_write_text(
        note,
        f"weapon pass routed to review: fallback={fallback} "
        f"wrist={wrist} rung={rung} file={cand_file}\n",
    )
    sidecar = {
        "wrist": wrist, "rung": rung, "roi_bbox": None,
        "fallback": fallback, "outside_mask_identical": None,
        "min_conf": min_conf, "strength": None, "seed": None,
        "inpainted": False,
    }
    _atomic_write_json(_weapon_sidecar_path(batch_dir, cand_file), sidecar)


# --------------------------------------------------------------------------
# Batch driver.
# --------------------------------------------------------------------------
def weapon_pass(batch_dir, wrist=None, rung="w1", rolls=4, strength=0.92,
                min_conf=0.3, only=None, config=None, backend=None,
                inpainter=None):
    """Run the M1 W1 weapon pass over a batch dir; return the manifest dict.

    wrist is None -> PROPOSE (both-wrist overlays, no mutation). wrist set ->
    FIX (detect -> mask -> inpaint -> paste-back -> advance). backend defaults
    to dwpose_backend and inpainter to a real-SDXL closure; both are injectable
    so pure tests never load onnx/torch. `only` (a cand file name), when set,
    restricts the pass to that candidate. Atomic writes throughout.
    """
    from PIL import Image  # lazy; CI has Pillow

    if config is None:
        config = _load_config_safe()
    weapon_cfg = (config or {}).get("weapon") or {}
    prompt = weapon_cfg.get("prompt") or WEAPON_PROMPT
    negative = weapon_cfg.get("negative") or WEAPON_NEG

    if backend is None:
        backend = loc.dwpose_backend

    manifest_path = os.path.join(batch_dir, "gen_manifest.json")
    with open(manifest_path, encoding="utf-8") as fo:
        manifest = json.load(fo)
    candidates = manifest.get("candidates", [])

    # ---- PROPOSE: emit both-wrist overlays, mutate nothing. ----
    if wrist is None:
        review_dir = os.path.join(batch_dir, "weapon_review")
        os.makedirs(review_dir, exist_ok=True)
        for cand in candidates:
            cand_file = cand.get("file")
            if not cand_file or (only is not None and cand_file != only):
                continue
            src = os.path.join(batch_dir, cand_file)
            if not os.path.exists(src):
                continue
            out = backend(src, min_conf=min_conf)
            width, height = Image.open(src).size
            roi_r = weapon_roi_from_keypoints(out.kp_map, "right", (width, height), out.right_hand)
            roi_l = weapon_roi_from_keypoints(out.kp_map, "left", (width, height), out.left_hand)
            overlay = loc.render_overlay(src, out.kp_map, roi_r, roi_l, _raw_stem(cand_file))
            overlay.save(os.path.join(review_dir, _raw_stem(cand_file) + "_overlay.png"))
        return manifest

    # ---- FIX: detect -> mask -> inpaint -> paste-back -> advance. ----
    active_inpainter = inpainter
    for cand in candidates:
        cand_file = cand.get("file")
        if not cand_file or (only is not None and cand_file != only):
            continue
        src = os.path.join(batch_dir, cand_file)
        if not os.path.exists(src):
            continue

        out = backend(src, min_conf=min_conf)
        kp_map, hand = select_wrist_inputs(out, wrist)
        cand_img = Image.open(src).convert("RGB")
        width, height = cand_img.size
        roi = weapon_roi_from_keypoints(kp_map, wrist, (width, height), hand)
        if not roi.ok:
            _route_to_review(batch_dir, cand_file, wrist, rung, roi.fallback, min_conf)
            continue

        if active_inpainter is None:
            active_inpainter = _build_real_inpainter(config)

        seed = int(cand.get("seed") or 0)
        feathered = (np.clip(roi.mask_feathered, 0.0, 1.0) * 255.0).astype(np.uint8)
        mask_pil = Image.fromarray(feathered, mode="L")
        inpainted = active_inpainter(cand_img, mask_pil, prompt, negative, strength, seed)
        if inpainted.size != cand_img.size:
            inpainted = inpainted.resize(cand_img.size)
        inpainted = inpainted.convert("RGB")

        cand_arr = np.asarray(cand_img)
        final_arr = paste_back(cand_arr, np.asarray(inpainted), roi.mask_binary)
        assert_outside_identity(cand_arr, final_arr, roi.mask_binary)

        new_file = gr.stage_filename(cand_file, _STAGE)
        Image.fromarray(final_arr).save(os.path.join(batch_dir, new_file))
        gr.advance_cand_file(cand, new_file, _STAGE)

        sidecar = {
            "wrist": wrist, "rung": rung,
            "roi_bbox": list(roi.bbox) if roi.bbox else None,
            "fallback": None, "outside_mask_identical": True,
            "min_conf": min_conf, "strength": strength, "seed": seed,
            "rolls": rolls, "meta": getattr(out, "meta", {}) or {},
        }
        _atomic_write_json(_weapon_sidecar_path(batch_dir, new_file), sidecar)
        _atomic_write_json(manifest_path, manifest)

    return manifest


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="lw_gen_weaponpass.py",
        description="Legion Wallpaper weapon pass (M1 W1): detect -> mask -> inpaint.",
    )
    p.add_argument("batch_dir", help="path to images/_gen_scratch/<batch-id>/")
    p.add_argument("--wrist", choices=["left", "right"], default=None,
                   help="rig side to fix; absent (or --propose) => propose mode")
    p.add_argument("--propose", action="store_true",
                   help="emit both-wrist overlays into weapon_review/, inpaint nothing")
    p.add_argument("--weapon-rung", dest="weapon_rung", default="w1")
    p.add_argument("--rolls", type=int, default=4)
    p.add_argument("--strength", type=float, default=0.92)
    p.add_argument("--weapon-min-conf", dest="weapon_min_conf", type=float, default=0.3)
    p.add_argument("--only", default=None, help="restrict to one cand file (cand_XX.png)")
    return p


def _log_error(exc):
    """Append the raw error to logs/ - never surface it to the user."""
    try:
        import datetime

        logs = os.path.join(ROOT, "logs")
        os.makedirs(logs, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d")
        with open(os.path.join(logs, f"{stamp}.log"), "a", encoding="utf-8") as fo:
            fo.write(f"[lw_gen_weaponpass] {type(exc).__name__}: {exc}\n")
    except OSError:
        pass


def main(argv=None):
    args = build_parser().parse_args(argv)
    wrist = None if args.propose else args.wrist
    try:
        manifest = weapon_pass(
            args.batch_dir, wrist=wrist, rung=args.weapon_rung, rolls=args.rolls,
            strength=args.strength, min_conf=args.weapon_min_conf, only=args.only,
        )
    except Exception as exc:  # noqa: BLE001 - never surface a raw torch/onnx trace
        print("weapon pass failed - generator not provisioned or a backend/inpaint "
              "error (see logs). Run the Phase-0 setup (docs/GEN_MODELS.md).",
              file=sys.stderr)
        _log_error(exc)
        return 1

    n = len(manifest.get("candidates", []))
    mode = "propose" if wrist is None else f"fix({wrist})"
    print(f"weapon pass [{mode}] over {n} candidate(s) -> {args.batch_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
