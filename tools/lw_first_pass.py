"""Legion Wallpaper - committed first-pass driver (Stage 1 orchestrator).

Reproduces the validated 2026-07-05 recipe (slug
p08e8-shadow-hunter-vayne-by-namakx-dg9ydp9-pre -> G1 PASS) as a resumable,
single- and batch-mode CLI. Per slug, end to end:

  1. Best-source selection: prefer the fetched Tier-1 fullview at
     data\\recovery\\fetched\\<slug>\\deviantart\\*\\deviantart_* (any
     FETCHED_EXTS extension) if it exists and decodes; else the scratch
     <slug>_firstinitial.*. Never
     re-intake a fullview (re-slugging diverges the slug).
  2. Aspect conditioning (NEW policy, pure + unit-tested): if the source ratio
     is within ASPECT_TOL of 16:9 pass it straight through; else center-crop to
     exact 16:9 when the area loss is <= 0.08, otherwise HOLD (annotate the
     manifest and leave the slug in scratch). The crop MUST happen before
     first_pass even for over-2560 sources, because _covers_target's
     downscale-only path still calls _finish which raises on non-16:9.
  3. Upscale: lw_upscale.first_pass via the .venv-upscale python (torch/spandrel
     live only there), IllustrationJaNai V3 detail DAT2, CREATE_NO_WINDOW.
  4. save-working through lw_pipeline (single-writer rule).
  5. G1 gate: FR metrics via the .venv-metrics python (pyiqa), numpy metrics in
     system python at common scale, verdict() against DEFAULT_G1_THRESHOLDS.
     GOTCHA: fr_metrics returns 'ms_ssim' but verdict wants 'msssim' - remapped.
  6. annotate the manifest with metrics + verdict + crop-box + source choice.
  7. submit iff verdict in {PASS, FLAG}. Hard FAIL -> leave in scratch, record
     the reasons in the manifest.

CI constraint: this module imports only PIL + numpy + stdlib at top level. torch
and pyiqa are NEVER imported here - the GPU/FR work is shelled to their venvs.
The image reads for aspect conditioning and numpy G1 use PIL only. All pure
logic (aspect_class, center_crop_box, select_source, remap_fr, assemble_metrics,
_run_json, load_source_urls) is unit-tested without torch/pyiqa/GPU.

GPU is one device - the batch runner is strictly sequential; NEVER parallelize
upscales. Every subprocess passes creationflags=CREATE_NO_WINDOW (Legion
focus-steal rule).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# lw_g1_gate is stdlib+numpy at import time (pyiqa/torch are lazy inside it), so
# importing verdict/DEFAULT_G1_THRESHOLDS here is CI-safe.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lw_g1_gate import DEFAULT_G1_THRESHOLDS, verdict  # noqa: E402

# --------------------------------------------------------------------------
# Paths (Legion machine, mirrored from the validated seed scripts).
# --------------------------------------------------------------------------
ROOT = r"C:\LegionWallpaper"
TOOLS = ROOT + r"\tools"
IMAGES = ROOT + r"\images"
FIRST_SCRATCH = IMAGES + r"\1.First Pass Scratch"
FETCHED_ROOT = ROOT + r"\data\recovery\fetched"
MATCHES_JSON = ROOT + r"\data\recovery\matches.json"

SYS_PY = r"C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe"
UP_PY = ROOT + r"\.venv-upscale\Scripts\python.exe"
MET_PY = ROOT + r"\.venv-metrics\Scripts\python.exe"
PIPELINE = TOOLS + r"\lw_pipeline.py"
MODEL_PATH = TOOLS + r"\models\4x_IllustrationJaNai_V3detail_DAT2_28k_bf16.safetensors"

# 16:9 target + tolerance. ASPECT_TOL matches lw_upscale.ASPECT_TOL (the ratio
# window _finish enforces); AREA_LOSS_MAX is the crop_ok/crop_heavy split.
TARGET = (2560, 1440)
TARGET_ASPECT = TARGET[0] / TARGET[1]  # 1.7777...
ASPECT_TOL = 0.02
AREA_LOSS_MAX = 0.08

# CREATE_NO_WINDOW: 0 on non-Windows so the module still imports/tests in CI.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ==========================================================================
# Pure logic: aspect conditioning
# ==========================================================================
def center_crop_box(w, h):
    """Center-crop box (left, top, right, bottom) making an exact-16:9 window.

    If the source is too WIDE (ratio > 16/9), crop width: new_w =
    round(h*16/9), centered horizontally, full height. If too TALL, crop
    height: new_h = round(w*9/16), centered vertically, full width. Integer
    pixels. Returns the box for a source that is NOT already ~16:9 (callers
    gate on aspect_class first); for an exactly-16:9 source it returns the full
    frame.
    """
    ratio = w / h
    if ratio > TARGET_ASPECT:
        new_w = round(h * 16 / 9)
        new_w = min(new_w, w)
        left = (w - new_w) // 2
        return (left, 0, left + new_w, h)
    if ratio < TARGET_ASPECT:
        new_h = round(w * 9 / 16)
        new_h = min(new_h, h)
        top = (h - new_h) // 2
        return (0, top, w, top + new_h)
    return (0, 0, w, h)


CROP_SIDES = ("left", "right", "top", "bottom")


def anchored_crop_box(w, h, sides):
    """Exact-16:9 crop box taking its loss only from operator-permitted sides.

    `sides` is the set of edges the operator has allowed the crop to eat into.
    They are a PERMISSION, not a demand: only the axis that actually needs
    cropping is touched, so a horizontal grant on a too-TALL frame is unused
    (narrowing it would move the ratio further from 16:9 and cost extra area).

    Both sides of the needed axis permitted -> the center crop. Exactly one ->
    the whole loss comes off that edge. Neither -> ValueError, because the
    instruction cannot be honoured and silently center-cropping would ignore
    the operator. A frame already within ASPECT_TOL of 16:9 is returned whole.
    """
    bad = [s for s in sides if s not in CROP_SIDES]
    if bad:
        raise ValueError(f"unknown crop side(s): {bad}; want {CROP_SIDES}")
    if not sides:
        raise ValueError("no crop side given")

    ratio = w / h
    if abs(ratio - TARGET_ASPECT) <= ASPECT_TOL:
        return (0, 0, w, h)

    if ratio > TARGET_ASPECT:  # too wide - the width shrinks
        allowed = [s for s in ("left", "right") if s in sides]
        if not allowed:
            raise ValueError(
                "frame is too wide but no left/right crop side permitted")
        new_w = min(round(h * 16 / 9), w)
        remove = w - new_w
        if len(allowed) == 2:
            left = remove // 2
        else:
            left = remove if allowed[0] == "left" else 0
        return (left, 0, left + new_w, h)

    allowed = [s for s in ("top", "bottom") if s in sides]  # too tall
    if not allowed:
        raise ValueError(
            "frame is too tall but no top/bottom crop side permitted")
    new_h = min(round(w * 9 / 16), h)
    remove = h - new_h
    if len(allowed) == 2:
        top = remove // 2
    else:
        top = remove if allowed[0] == "top" else 0
    return (0, top, w, top + new_h)


def parse_crop_overrides(path):
    """Read a {slug: sides} operator override file. Returns {slug: [sides]}.

    Values may be a comma-separated string ("left,top") or a list. Every side
    is validated here so a typo fails at parse time, not mid-batch after the
    GPU has already burned minutes on earlier slugs.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for slug, val in raw.items():
        sides = ([s.strip() for s in val.split(",")]
                 if isinstance(val, str) else list(val))
        sides = [s for s in sides if s]
        bad = [s for s in sides if s not in CROP_SIDES]
        if bad or not sides:
            raise ValueError(f"{slug}: bad crop sides {val!r}")
        out[slug] = sides
    return out


def aspect_class(w, h):
    """Classify a source's aspect and return (cls, box, area_loss).

    cls is one of:
      'ok'         - within ASPECT_TOL of 16:9; box is None, area_loss 0.0.
      'crop_ok'    - outside tol but a center-crop to exact 16:9 loses
                     <= AREA_LOSS_MAX of the area; box is the crop box.
      'crop_heavy' - the crop would lose > AREA_LOSS_MAX; box is the crop box
                     (for provenance) but the caller must HOLD, not upscale.

    area_loss = 1 - (cropped_area / original_area).
    """
    ratio = w / h
    if abs(ratio - TARGET_ASPECT) <= ASPECT_TOL:
        return "ok", None, 0.0
    box = center_crop_box(w, h)
    left, top, right, bottom = box
    cropped = (right - left) * (bottom - top)
    area_loss = 1.0 - (cropped / (w * h))
    if area_loss <= AREA_LOSS_MAX:
        return "crop_ok", box, area_loss
    return "crop_heavy", box, area_loss


# ==========================================================================
# Pure logic: best-source selection
# ==========================================================================
def _pil_decodes(path):
    """True iff PIL can open+load the file (a real decode, not just a header)."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.load()
        return True
    except Exception:  # noqa: BLE001 - any decode failure means "unusable"
        return False


# Extensions a fetched fullview may carry, in SELECTION-PREFERENCE order.
# WHY this exact set: it is a subset of lw_pipeline.IMAGE_EXTS
# (tools/lw_pipeline.py:62), so a fullview chosen here is one the rest of the
# pipeline can also ingest - picking anything wider would only move the failure
# further from its cause.
# WHY this order is the tie-break: DeviantArt serves the same deviation under
# more than one encode, and the upscaler amplifies JPEG ringing that a lossless
# encode of the same art does not carry - so lossless is preferred over lossy
# when a fetch dir holds both.
FETCHED_EXTS = (".png", ".webp", ".jpeg", ".jpg")


def _fullview_sort_key(path):
    """Total order over fullview candidates: FETCHED_EXTS rank, then path.

    WHY the case fold before the raw path: the same fetch replayed on a
    case-insensitive filesystem can differ only in casing, and a raw-bytes sort
    would then hand back a different winner for what is the same corpus. The
    raw path stays as the final component so the key is never ambiguous.
    """
    ext = os.path.splitext(path)[1].lower()
    return (FETCHED_EXTS.index(ext), path.lower(), path)


def find_fetched_fullview(slug, fetched_root=FETCHED_ROOT):
    """Best DeviantArt fullview for a slug, or None.

    Globs <fetched_root>\\<slug>\\deviantart\\*\\deviantart_* (the artist
    subfolder is the single wildcard) and keeps the files whose extension is in
    FETCHED_EXTS; ties break by _fullview_sort_key, so a mixed-extension fetch
    directory resolves to the same file on every run.

    WHY the extension is filtered in python instead of inside the glob: glob
    folds case on Windows but not on Linux and the suite runs on both, so a
    .PNG fetch would be visible on one and invisible on the other.
    """
    pattern = os.path.join(str(fetched_root), slug, "deviantart", "*",
                           "deviantart_*")
    hits = [p for p in glob.glob(pattern)
            if os.path.splitext(p)[1].lower() in FETCHED_EXTS
            and os.path.isfile(p)]
    hits.sort(key=_fullview_sort_key)
    return hits[0] if hits else None


def find_firstinitial(slug, scratch_dir):
    """The <slug>_firstinitial.<ext> file in the scratch folder, or None."""
    d = Path(scratch_dir)
    if not d.is_dir():
        return None
    for p in sorted(d.iterdir()):
        if p.is_file() and p.name.startswith(f"{slug}_firstinitial."):
            return str(p)
    return None


def select_source(slug, scratch_dir, fetched_root=FETCHED_ROOT,
                  decode_check=_pil_decodes):
    """Pick the upscale input for a slug: (path, kind).

    Prefers a decodable fetched fullview; else the scratch _firstinitial. kind
    is 'fullview', 'firstinitial', or 'none'. decode_check is injected so tests
    can stub the PIL decode.
    """
    full = find_fetched_fullview(slug, fetched_root)
    if full and decode_check(full):
        return full, "fullview"
    init = find_firstinitial(slug, scratch_dir)
    if init and decode_check(init):
        return init, "firstinitial"
    # Last resort: an undecodable initial still beats nothing to report on, but
    # if neither decodes we return none.
    if init:
        return init, "firstinitial"
    return None, "none"


# ==========================================================================
# Pure logic: FR remap + metric assembly + source-url map
# ==========================================================================
def remap_fr(fr):
    """Copy an fr_metrics dict remapping 'ms_ssim' -> 'msssim'.

    verdict() keys on 'msssim'; fr_metrics emits 'ms_ssim'. Other keys pass
    through unchanged; 'common_scale' is retained for provenance.
    """
    out = dict(fr)
    if "ms_ssim" in out:
        out["msssim"] = out.pop("ms_ssim")
    return out


def assemble_metrics(fr, lap_ratio, halo_pct, band_delta):
    """Build the verdict() input dict from FR results + numpy metrics.

    fr may carry 'ms_ssim' (remapped) or 'msssim'. Non-numeric FR values (the
    'ERR ...' strings fr_metrics records on a bad metric) are dropped so a
    single failed metric does not crash verdict; a dropped key is simply not
    gated (verdict skips missing keys).
    """
    remapped = remap_fr(fr)
    metrics = {"lap_ratio": lap_ratio, "halo_pct": halo_pct,
               "band_delta": band_delta}
    for key in ("msssim", "lpips"):
        val = remapped.get(key)
        if isinstance(val, (int, float)):
            metrics[key] = val
    return metrics


def gate_metrics(metrics, backend):
    """Return the metric subset to feed verdict(), conditioned on the backend.

    ADR-006: a downscale-only path (source already covered 2560x1440; one Lanczos
    down, no AI upscale) has no upscale to sharpen, so the lap_ratio softness
    FLOOR is invalid there - it reads as arbitrary pass/fail by source content.
    Drop lap_ratio from the GATED set for backend "downscale-only"; keep msssim,
    lpips (structure preservation) and halo_pct, band_delta (added artifacts).
    The lap_ratio VALUE is still recorded in the manifest for provenance - it is
    just not gated on. Every other backend gates on the full set unchanged.
    """
    if backend == "downscale-only":
        return {k: v for k, v in metrics.items() if k != "lap_ratio"}
    return dict(metrics)


def load_source_urls(matches_path=MATCHES_JSON):
    """Map slug -> source url from matches.json (top-level JSON array).

    Missing/unreadable file -> {}. Each entry's 'source' is the deviation URL
    (or a local path for Tier-0). Entries without a slug are skipped.
    """
    p = Path(matches_path)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for entry in data:
        slug = entry.get("slug")
        if slug:
            out[slug] = entry.get("source")
    return out


# ==========================================================================
# Subprocess orchestration (monkeypatched in tests; never runs torch/pyiqa)
# ==========================================================================
def _last_json_line(text):
    """Return the last stdout line that parses as a JSON object.

    pyiqa/torch print load banners to stdout; the payload is the final
    '{...}' line. Raises ValueError if no JSON object line is present.
    """
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("no JSON object line in subprocess stdout:\n"
                     + text[-500:])


def _run_json(python_exe, snippet, tag):
    """Run `python_exe -c snippet`, return the parsed last-json-line dict.

    Always passes creationflags=CREATE_NO_WINDOW (Legion focus-steal rule) and
    capture_output/text. A non-zero return raises RuntimeError carrying the tag
    + stderr tail; missing JSON raises ValueError.
    """
    proc = subprocess.run(
        [python_exe, "-c", snippet],
        capture_output=True, text=True, creationflags=NO_WINDOW,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"[{tag}] subprocess rc={proc.returncode}: "
            f"{(proc.stderr or '')[-500:]}"
        )
    return _last_json_line(proc.stdout)


def _pylit(value):
    """Embed a path in a generated `python -c` snippet as a safe literal.

    json.dumps escapes backslashes, both quote characters and non-ASCII, and
    its output is a valid Python string literal - so a fetched filename
    carrying an apostrophe (deviantart_1375265414_Kai'Sa.jpg) can no longer
    terminate the literal early and kill the subprocess on a SyntaxError
    (2026-09-01 batch). Never interpolate a path into a snippet by hand.
    """
    return json.dumps(str(value))


def run_upscale(src_path, out_path, model_path=MODEL_PATH):
    """Shell to .venv-upscale python: lw_upscale.first_pass -> audit dict."""
    snippet = (
        f"import sys,json;sys.path.insert(0,{_pylit(TOOLS)});"
        "from lw_upscale import first_pass;"
        f"a=first_pass(src_path={_pylit(src_path)},"
        f"out_path={_pylit(out_path)},"
        f"backend='spandrel',model_path={_pylit(model_path)});"
        "print(json.dumps(a))"
    )
    return _run_json(UP_PY, snippet, "upscale")


def run_fr_metrics(out_path, source_path):
    """Shell to .venv-metrics python: lw_g1_gate.fr_metrics -> FR dict.

    ref == source == the conditioned source (self-comparison at common scale).
    """
    snippet = (
        f"import sys,json;sys.path.insert(0,{_pylit(TOOLS)});"
        "from lw_g1_gate import fr_metrics;"
        f"print(json.dumps(fr_metrics({_pylit(out_path)},"
        f"{_pylit(source_path)},{_pylit(source_path)},"
        f"names=('ssim','ms_ssim','lpips','dists'))))"
    )
    return _run_json(MET_PY, snippet, "fr_metrics")


def compute_numpy_metrics(source_path, out_path):
    """Numpy G1 metrics at common scale, in-process (system python only).

    Downscales the output to the source resolution (Image.LANCZOS) so both are
    at common scale, then laplacian_ratio, overshoot_halo(...)['halo_pct'],
    banding_delta. Returns (lap_ratio, halo_pct, band_delta).
    """
    import numpy as np
    from PIL import Image

    from lw_g1_gate import banding_delta, laplacian_ratio, overshoot_halo

    with Image.open(source_path) as s:
        src = s.convert("RGB")
        src_size = src.size
        src_a = np.asarray(src)
    with Image.open(out_path) as o:
        out_common = o.convert("RGB").resize(src_size, Image.LANCZOS)
        out_a = np.asarray(out_common)
    lap = laplacian_ratio(src_a, out_a)
    halo = overshoot_halo(src_a, out_a)["halo_pct"]
    band = banding_delta(src_a, out_a)
    return lap, halo, band


# ==========================================================================
# Pipeline (single-writer) helpers
# ==========================================================================
def _pipeline(*args):
    """Run lw_pipeline.py under system python; return CompletedProcess."""
    return subprocess.run(
        [SYS_PY, PIPELINE, *args],
        capture_output=True, text=True, creationflags=NO_WINDOW,
    )


def pipeline_save_working(slug, from_png, params):
    proc = _pipeline("save-working", slug, "--from", from_png,
                     "--tool", "lw_first_pass", "--params", json.dumps(params))
    if proc.returncode != 0:
        raise RuntimeError(f"save-working rc={proc.returncode}: "
                           f"{(proc.stderr or proc.stdout)[-400:]}")
    return proc.stdout.strip()


def pipeline_annotate(slug, source_url, metrics_obj):
    """annotate <slug> --source-url <url|omit> --metrics @<tmpfile>."""
    fd, tmp = tempfile.mkstemp(suffix=".json", prefix="lw_fp_metrics_")
    os.close(fd)
    try:
        Path(tmp).write_text(json.dumps(metrics_obj, indent=2), encoding="utf-8")
        args = ["annotate", slug, "--metrics", "@" + tmp,
                "--tool", "lw_first_pass"]
        if source_url:
            args += ["--source-url", source_url]
        proc = _pipeline(*args)
        if proc.returncode != 0:
            raise RuntimeError(f"annotate rc={proc.returncode}: "
                               f"{(proc.stderr or proc.stdout)[-400:]}")
        return proc.stdout.strip()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def pipeline_submit(slug):
    proc = _pipeline("submit", slug)
    if proc.returncode != 0:
        raise RuntimeError(f"submit rc={proc.returncode}: "
                           f"{(proc.stderr or proc.stdout)[-400:]}")
    return proc.stdout.strip()


# ==========================================================================
# Aspect conditioning: write a cropped temp source when needed
# ==========================================================================
def condition_source(src_path, tmp_dir, crop_sides=None):
    """Prepare the upscale input: return (path, plan_dict).

    plan_dict = {aspect_class, src_dims:[w,h], area_loss, crop_box, cropped}.
    - 'ok'         -> returns src_path unchanged, cropped False.
    - 'crop_ok'    -> writes a center-cropped exact-16:9 temp PNG, cropped True.
    - 'crop_heavy' -> returns (None, plan) so the caller HOLDs.

    `crop_sides` is the operator override: it anchors the crop to the permitted
    edges AND authorises an area loss past AREA_LOSS_MAX, turning what would be
    a HOLD into a real crop classed 'crop_override'. An already-16:9 source
    stays a passthrough whatever sides are named.
    """
    from PIL import Image

    with Image.open(src_path) as im:
        w, h = im.size
        cls, box, area_loss = aspect_class(w, h)
        if crop_sides and cls != "ok":
            box = anchored_crop_box(w, h, crop_sides)
            left, top, right, bottom = box
            area_loss = 1.0 - ((right - left) * (bottom - top)) / (w * h)
            cls = "crop_override"
        plan = {"aspect_class": cls, "src_dims": [w, h],
                "area_loss": round(area_loss, 6), "crop_box": box,
                "cropped": False}
        if crop_sides:
            plan["crop_sides"] = list(crop_sides)
        if cls == "ok":
            return src_path, plan
        if cls == "crop_heavy":
            return None, plan
        cropped_img = im.convert("RGB").crop(box)
    stem = Path(src_path).stem
    out = os.path.join(str(tmp_dir), stem + "_crop16x9.png")
    cropped_img.save(out, format="PNG")
    plan["cropped"] = True
    return out, plan


# ==========================================================================
# Per-slug driver
# ==========================================================================
def scratch_dir_for(slug):
    return os.path.join(FIRST_SCRATCH, slug)


def slug_state(slug):
    """Cheap resumable-state probe from the scratch folder contents.

    Returns 'needauth' (already submitted), 'held' (manifest carries an aspect
    hold), 'editing' (a _firstinitial present, ready to process), or 'absent'.
    """
    d = Path(scratch_dir_for(slug))
    if not d.is_dir():
        return "absent"
    for p in d.iterdir():
        if p.is_file() and p.name == f"{slug}_firstneedauth.png":
            return "needauth"
    man = d / "manifest.json"
    if man.is_file():
        try:
            data = json.loads(man.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if data:
            for t in reversed(data.get("transitions", [])):
                audit = t.get("audit")
                if isinstance(audit, dict) and audit.get("hold"):
                    return "held"
    if find_firstinitial(slug, d):
        return "editing"
    return "absent"


def process_slug(slug, source_urls, tmp_dir, dry_run=False, crop_sides=None):
    """Run the full first-pass chain for one slug. Returns a result dict.

    result = {slug, status, ...}. status is one of:
      'pass' / 'flag' / 'fail' - the G1 verdict path (submit on pass|flag).
      'held'                   - aspect crop too heavy; annotated, not upscaled.
      'skipped'                - already NEEDAUTH or previously HELD.
      'error'                  - a source-selection or subprocess failure.
    """
    state = slug_state(slug)
    # An operator crop override is the whole point of revisiting a HELD slug,
    # so it - and only it - reopens one. NEEDAUTH still never reprocesses.
    if state == "needauth" or (state == "held" and not crop_sides):
        return {"slug": slug, "status": "skipped", "reason": state}

    scratch = scratch_dir_for(slug)
    src, kind = select_source(slug, scratch)
    if src is None:
        return {"slug": slug, "status": "error",
                "reason": "no decodable source (fullview or _firstinitial)"}
    source_url = source_urls.get(slug)

    # Aspect conditioning (needs a real image read; skip the write on dry-run).
    from PIL import Image
    with Image.open(src) as im:
        w, h = im.size
    cls, box, area_loss = aspect_class(w, h)
    if crop_sides and cls != "ok":
        box = anchored_crop_box(w, h, crop_sides)
        left, top, right, bottom = box
        area_loss = 1.0 - ((right - left) * (bottom - top)) / (w * h)
        cls = "crop_override"
    plan = {"slug": slug, "source_choice": kind, "source_path": src,
            "aspect_class": cls, "src_dims": [w, h],
            "area_loss": round(area_loss, 6), "crop_box": box}
    if crop_sides:
        plan["crop_sides"] = list(crop_sides)

    if cls == "crop_heavy":
        hold_metrics = {"hold": "aspect_crop_heavy", "src_dims": [w, h],
                        "area_loss": round(area_loss, 6),
                        "source_choice": kind, "crop_box": box}
        if not dry_run:
            pipeline_annotate(slug, source_url, hold_metrics)
        return {"slug": slug, "status": "held", **plan}

    if dry_run:
        plan["upscale_mode"] = ("downscale-only"
                                if (w >= TARGET[0] and h >= TARGET[1]
                                    and cls == "ok")
                                else "upscale-4x")
        plan["status"] = "dry-run"
        return plan

    # Condition (write cropped temp if crop_ok), then upscale.
    conditioned, cplan = condition_source(src, tmp_dir, crop_sides=crop_sides)
    up_out = os.path.join(str(tmp_dir), slug + "_firstpass_up.png")
    audit = run_upscale(conditioned, up_out)

    # usm_applied: False means first_pass resampled nothing (source was already
    # exactly 2560x1440) and so ran no unsharp mask - a reviewer needs that to
    # read halo_pct correctly.
    params = {"backend": audit.get("backend"), "model": audit.get("model"),
              "scale": audit.get("scale"), "source_choice": kind,
              "aspect_class": cls, "crop_box": box,
              "usm_applied": audit.get("usm_applied")}
    pipeline_save_working(slug, up_out, params)

    # G1 gate against the conditioned source (the real upscale input).
    fr = run_fr_metrics(up_out, conditioned)
    lap, halo, band = compute_numpy_metrics(conditioned, up_out)
    metrics = assemble_metrics(fr, lap, halo, band)
    backend = audit.get("backend")
    # ADR-006: downscale-only drops the (invalid) lap_ratio floor from the gate.
    v = verdict(gate_metrics(metrics, backend), DEFAULT_G1_THRESHOLDS)

    annotate_payload = {
        "gate": "G1", "metrics": metrics, "fr_all": fr,
        "backend": backend, "lap_ratio_gated": backend != "downscale-only",
        "verdict": v["verdict"], "reasons": v["reasons"],
        "source_choice": kind, "aspect_class": cls, "crop_box": box,
        "area_loss": round(area_loss, 6), "cropped": cplan.get("cropped"),
        # crop_sides is the operator's directed-crop instruction; recording it
        # is what makes a >AREA_LOSS_MAX crop auditable rather than silent.
        "crop_sides": list(crop_sides) if crop_sides else None,
        # usm_applied tells a reviewer whether halo_pct measured a real
        # sharpening pass or a no-resample passthrough (see params above).
        # source_mode + alpha_flattened make the always-RGB output's alpha drop
        # visible per slug - it was previously silent corpus-wide.
        "upscale_audit": {k: audit.get(k) for k in
                          ("backend", "model", "scale", "src_dims",
                           "up_dims", "out_dims", "usm_applied",
                           "source_mode", "alpha_flattened")},
    }
    pipeline_annotate(slug, source_url, annotate_payload)

    status = v["verdict"].lower()  # pass|flag|fail
    if v["verdict"] in ("PASS", "FLAG"):
        pipeline_submit(slug)
    return {"slug": slug, "status": status, "verdict": v["verdict"],
            "reasons": v["reasons"], "metrics": metrics, **plan}


# ==========================================================================
# Batch runner + CLI
# ==========================================================================
def _all_scratch_slugs():
    """Slugs in 1.First Pass Scratch that are in the EDITING state."""
    base = Path(FIRST_SCRATCH)
    if not base.is_dir():
        return []
    out = []
    for child in sorted(base.iterdir()):
        if child.is_dir() and slug_state(child.name) == "editing":
            out.append(child.name)
    return out


def _print_slug_line(res):
    st = res.get("status", "?")
    if st in ("pass", "flag", "fail"):
        reasons = "; ".join(res.get("reasons", [])) or "-"
        print(f"  {res['slug']:<58} {st.upper():<7} {reasons}")
    elif st == "held":
        print(f"  {res['slug']:<58} HELD    aspect_crop_heavy "
              f"loss={res.get('area_loss')}")
    elif st == "skipped":
        print(f"  {res['slug']:<58} SKIP    ({res.get('reason')})")
    elif st == "dry-run":
        print(f"  {res['slug']:<58} DRY     src={res.get('source_choice')} "
              f"aspect={res.get('aspect_class')} "
              f"mode={res.get('upscale_mode')} box={res.get('crop_box')}")
    else:
        print(f"  {res['slug']:<58} ERROR   {res.get('reason')}")


def run_batch(slugs, limit=None, dry_run=False, crop_overrides=None):
    """Sequentially process slugs (GPU is one device). Prints a summary banner."""
    if limit is not None:
        slugs = slugs[:limit]
    crop_overrides = crop_overrides or {}
    source_urls = load_source_urls()
    counts = {"processed": 0, "pass": 0, "flag": 0, "fail": 0,
              "held": 0, "skipped": 0, "error": 0}
    print(f"LW FIRST PASS BATCH START | slugs={len(slugs)} "
          f"dry_run={dry_run}")
    with tempfile.TemporaryDirectory(prefix="lw_first_pass_") as tmp_dir:
        for slug in slugs:
            try:
                res = process_slug(slug, source_urls, tmp_dir, dry_run=dry_run,
                                   crop_sides=crop_overrides.get(slug))
            except Exception as exc:  # noqa: BLE001 - one slug != batch death
                res = {"slug": slug, "status": "error", "reason": str(exc)}
            _print_slug_line(res)
            st = res.get("status")
            if st == "dry-run":
                counts["processed"] += 1
            elif st in counts:
                counts[st] += 1
                if st in ("pass", "flag", "fail"):
                    counts["processed"] += 1
    print(
        "LW FIRST PASS BATCH | processed={processed} pass={pass} flag={flag} "
        "fail={fail} held={held} skipped={skipped}".format(**counts)
        + (f" error={counts['error']}" if counts["error"] else "")
    )
    return counts


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="lw_first_pass",
        description="Legion Wallpaper Stage-1 first-pass driver")
    p.add_argument("slug", nargs="?", help="single slug to process")
    p.add_argument("--batch", metavar="SLUGS",
                   help="path to a slugs.txt (one slug per line) or "
                        "--all-scratch")
    p.add_argument("--all-scratch", action="store_true",
                   help="batch every EDITING slug in 1.First Pass Scratch")
    p.add_argument("--limit", type=int, help="cap the number of slugs")
    p.add_argument("--dry-run", action="store_true",
                   help="print the plan without mutating")
    p.add_argument("--crop-overrides", metavar="JSON",
                   help="operator directed-crop file {slug: 'top,left'}; "
                        "anchors the crop and reopens a HELD slug")
    args = p.parse_args(argv)

    overrides = (parse_crop_overrides(args.crop_overrides)
                 if args.crop_overrides else {})

    if args.batch or args.all_scratch:
        if args.all_scratch or args.batch == "--all-scratch":
            slugs = _all_scratch_slugs()
            # a held slug is invisible to _all_scratch_slugs; an override is
            # the operator explicitly reopening it, so pull it back in.
            slugs += [s for s in overrides
                      if s not in slugs and slug_state(s) == "held"]
        else:
            text = Path(args.batch).read_text(encoding="utf-8")
            slugs = [ln.strip() for ln in text.splitlines()
                     if ln.strip() and not ln.strip().startswith("#")]
        run_batch(slugs, limit=args.limit, dry_run=args.dry_run,
                  crop_overrides=overrides)
        return 0

    if not args.slug:
        p.error("give a slug, or --batch <file>/--all-scratch")

    source_urls = load_source_urls()
    with tempfile.TemporaryDirectory(prefix="lw_first_pass_") as tmp_dir:
        res = process_slug(args.slug, source_urls, tmp_dir,
                           dry_run=args.dry_run,
                           crop_sides=overrides.get(args.slug))
    print(json.dumps(res, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
