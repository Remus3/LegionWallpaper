"""Legion Wallpaper - W4 Vayne weapon-concept LoRA dataset curation.

Builds the captioned 1024x1024 training set for the wrist-mounted repeating
crossbow concept from two sources:
  1. The 19 official Vayne skin splashes (full character images): DWPose locates
     the right wrist, lw_gen_weaponfix derives the weapon ROI, the padded ROI is
     cropped and letterboxed to 1024. A per-splash DWPose overlay is written for
     the operator to eyeball (including for the splashes that get SKIPPED, so the
     operator can see WHY a localize failed).
  2. The 5 hand-made asset crops (feathered RGBA crossbow cutouts): each is
     composited onto a neutral field, then letterboxed to 1024.

Every raw crop gets a paired <name>.txt caption. The captions are OBJECT-ONLY
by design (a single crossbow concept token, deliberately NO character / identity
/ skin tokens) so the LoRA learns the weapon, not whole-character Vayne.

This is a DATASET tool, not the pipeline: it reads the splash + asset dirs and
writes crops. It does NOT augment (augmentation is a later pass over the
operator-culled keep-set).

CI constraint (torch-free): this module imports ONLY stdlib + the three torch-
free project modules (the localizer harness, the weaponfix geometry, the asset
loader) at top level. torch / onnxruntime / cv2 are imported LAZILY inside the
real DWPose backend, which the test suite never reaches (it injects a stub
backend). The pure helpers (letterbox_to_square / build_caption) are unit-tested
without any heavy dep. PIL is imported lazily inside functions, mirroring the
rest of the gen sidecar.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

# Allow both `python tools/lw_gen_curate_weapon_crops.py` (script mode puts
# tools/ on sys.path, not the repo root) and `from tools import ...`. Mirror the
# lw_gen_weaponpass shim.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import lw_gen_localizer_eval as loc  # noqa: E402
from tools.lw_gen_weaponfix import (  # noqa: E402
    forearm_frame, pad_bbox, weapon_roi_from_keypoints,
)
from tools.lw_gen_weapon_assets import load_assets  # noqa: E402

# --- defaults ---------------------------------------------------------------
DEFAULT_SPLASH_DIR = os.path.join(ROOT, "tools", "models", "lora_datasets", "vayne")
DEFAULT_ASSET_DIR = os.path.join(ROOT, "tools", "models", "weapon_assets", "vayne")
DEFAULT_OUT_DIR = os.path.join(ROOT, "tools", "models", "lora_datasets", "vayne_weapon_crops")

CROP_SIZE = 1024
# Neutral mid-gray letterbox pad. Chosen to MATCH the flat (128,128,128) field
# the RGBA asset crops are composited onto (mirrors lw_gen_weaponpass
# _asset_ip_image), so the whole training set shares one neutral pad field and
# no crop carries a distracting solid-color border the LoRA could key on.
PAD_FILL = (128, 128, 128)

# Splash discovery extensions (the corpus is .jpg; accept siblings defensively).
_SPLASH_EXTS = ("*.jpg", "*.jpeg", "*.png", "*.webp")

# Object-only caption for the crossbow concept (design intent: NO character /
# identity / skin tokens, to avoid whole-character dilution). Based on the
# lw_gen_weaponpass WEAPON_PROMPT, stripped of the "vayne, league of legends"
# identity head. Same string for every crop - a single object concept.
CROSSBOW_CAPTION = (
    "vaynecrossbow, wrist-mounted repeating crossbow, mechanical crossbow "
    "gauntlet on forearm, bat-wing crossbow limbs, silver metal, loaded bolt, "
    "intricate mechanical detail"
)

# The wrist we curate. Vayne's rig is the right-hand crossbow (the asset crops
# are all *_right; the weapon pass localizes the right wrist by default).
_WRIST = "right"


# --------------------------------------------------------------------------
# Pure helpers (torch-free; unit-tested directly).
# --------------------------------------------------------------------------
def letterbox_to_square(img, size=CROP_SIZE, fill=PAD_FILL):
    """Resize `img` to fit a size x size square, preserving aspect, pad `fill`.

    The content is scaled by min(size/w, size/h) (never upscaled past fitting the
    box on its long side), centered, and the remaining margin is filled with the
    neutral pad color. Returns a new RGB PIL image of exactly (size, size). A hard
    rectangular paste (no blending) keeps the pad byte-exactly `fill`.
    """
    from PIL import Image

    rgb = img.convert("RGB")
    w, h = rgb.size
    if w <= 0 or h <= 0:
        return Image.new("RGB", (size, size), fill)
    scale = min(size / float(w), size / float(h))
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    resized = rgb.resize((new_w, new_h), resample=Image.LANCZOS)
    canvas = Image.new("RGB", (size, size), fill)
    canvas.paste(resized, ((size - new_w) // 2, (size - new_h) // 2))
    return canvas


def build_caption(name):
    """Return the OBJECT-ONLY caption for a crossbow crop.

    Deliberately identical for every crop: this is a single object concept, so
    the caption carries the concept token + material/shape descriptors and NO
    character / identity / skin tokens (whole-character dilution is the failure
    mode a weapon-concept LoRA must avoid). `name` is accepted for a possible
    future per-skin color hint but is intentionally NOT embedded, which
    guarantees no skin or character name can leak into the caption.
    """
    return CROSSBOW_CAPTION


def _composite_on_neutral(png_path, bg=PAD_FILL):
    """Composite a feathered RGBA crop onto a flat neutral RGB field.

    Mirrors lw_gen_weaponpass._asset_ip_image: the crop's own alpha is the
    matte, so the feathered edge blends into the neutral field. Returns RGB.
    """
    from PIL import Image

    crop = Image.open(png_path).convert("RGBA")
    base = Image.new("RGB", crop.size, bg)
    base.paste(crop, (0, 0), crop)
    return base


# --------------------------------------------------------------------------
# I/O helpers (atomic writes per project hard rule: write tmp, then os.replace).
# --------------------------------------------------------------------------
def _atomic_save_png(img, path):
    tmp = path + ".tmp"
    img.save(tmp, format="PNG")
    os.replace(tmp, path)


def _atomic_write_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="ascii") as fo:
        fo.write(text)
        fo.flush()
        os.fsync(fo.fileno())
    os.replace(tmp, path)


def _splash_paths(splash_dir):
    """Sorted, de-duplicated list of splash image paths in `splash_dir`."""
    paths = []
    for ext in _SPLASH_EXTS:
        paths.extend(glob.glob(os.path.join(splash_dir, ext)))
    return sorted(set(paths))


def _save_crop(out_dir, name, square):
    """Write raw/<name>.png + its paired raw/<name>.txt caption (atomic)."""
    raw_dir = os.path.join(out_dir, "raw")
    _atomic_save_png(square, os.path.join(raw_dir, name + ".png"))
    _atomic_write_text(os.path.join(raw_dir, name + ".txt"), build_caption(name) + "\n")


# --------------------------------------------------------------------------
# Curation driver.
# --------------------------------------------------------------------------
def curate(splash_dir, asset_dir, out_dir, backend=None, min_conf=0.3,
           pad=0.1, size=CROP_SIZE):
    """Build the captioned 1024 crop set from the splashes + the asset crops.

    Returns a summary dict:
      {"localized": int, "skipped": [(name, reason), ...], "assets": int,
       "total": int, "out_dir": str, "splash_dir": str, "asset_dir": str}

    For each splash: run the (injectable) pose backend, render a DWPose overlay
    (ALWAYS, so a skip is still eyeball-able), then localize the right wrist. A
    None forearm_frame -> skip "no_forearm"; a not-ok ROI -> skip roi.fallback;
    else crop the padded ROI, letterbox to `size`, and save raw + caption. For
    each asset crop: composite onto the neutral field, letterbox, save raw +
    caption. Atomic writes throughout. No augmentation.
    """
    from PIL import Image

    if backend is None:
        backend = loc.dwpose_backend

    raw_dir = os.path.join(out_dir, "raw")
    overlays_dir = os.path.join(out_dir, "overlays")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(overlays_dir, exist_ok=True)

    localized = 0
    skipped = []

    for src in _splash_paths(splash_dir):
        name = os.path.splitext(os.path.basename(src))[0]
        out = backend(src, min_conf=min_conf)
        kp_map = out.kp_map
        width, height = Image.open(src).size
        wh = (width, height)

        # Overlay for BOTH wrists (mirror lw_gen_weaponpass propose mode) so the
        # operator can see the localize - even on a skip - then write it first.
        roi_r = weapon_roi_from_keypoints(kp_map, "right", wh, out.right_hand)
        roi_l = weapon_roi_from_keypoints(kp_map, "left", wh, out.left_hand)
        overlay = loc.render_overlay(src, kp_map, roi_r, roi_l, name)
        _atomic_save_png(overlay, os.path.join(overlays_dir, name + ".png"))

        # Localize the right wrist: forearm geometry first, then the ROI.
        if forearm_frame(kp_map, _WRIST, wh) is None:
            skipped.append((name, "no_forearm"))
            continue
        if not roi_r.ok:
            skipped.append((name, roi_r.fallback))
            continue

        box = pad_bbox(roi_r.bbox, pad, wh)
        crop = Image.open(src).convert("RGB").crop(box)
        _save_crop(out_dir, name, letterbox_to_square(crop, size))
        localized += 1

    # ---- The 5 hand-made asset crops (composite RGBA -> neutral -> letterbox). ----
    assets = load_assets(asset_dir)
    for asset in assets:
        stem = os.path.splitext(asset.file)[0]
        name = "asset_" + stem
        composited = _composite_on_neutral(asset.png_path)
        _save_crop(out_dir, name, letterbox_to_square(composited, size))

    return {
        "localized": localized,
        "skipped": skipped,
        "assets": len(assets),
        "total": localized + len(assets),
        "out_dir": out_dir,
        "splash_dir": splash_dir,
        "asset_dir": asset_dir,
    }


def _print_summary(summary):
    for name, reason in summary["skipped"]:
        print(f"  skip {name}: {reason}")
    print(
        f"{summary['localized']} localized / {len(summary['skipped'])} skipped "
        f"/ {summary['assets']} asset crops = {summary['total']} base pool"
    )
    print(f"out dir: {summary['out_dir']}")


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="lw_gen_curate_weapon_crops.py",
        description="Curate the W4 Vayne weapon-concept LoRA crop set "
                    "(auto-crop 19 splashes + composite 5 asset crops -> 1024 + captions).",
    )
    p.add_argument("--min-conf", dest="min_conf", type=float, default=0.3,
                   help="DWPose keypoint confidence floor (default 0.3)")
    p.add_argument("--pad", type=float, default=0.1,
                   help="ROI bbox padding fraction before crop (default 0.1)")
    p.add_argument("--out", dest="out", default=None,
                   help="output dir (default tools/models/lora_datasets/vayne_weapon_crops)")
    return p


def _log_error(exc):
    """Append the raw error to logs/ - never surface it to the user."""
    try:
        import datetime

        logs = os.path.join(ROOT, "logs")
        os.makedirs(logs, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d")
        with open(os.path.join(logs, f"{stamp}.log"), "a", encoding="utf-8") as fo:
            fo.write(f"[lw_gen_curate_weapon_crops] {type(exc).__name__}: {exc}\n")
    except OSError:
        pass


def main(argv=None):
    args = build_parser().parse_args(argv)
    out_dir = args.out or DEFAULT_OUT_DIR
    try:
        summary = curate(
            DEFAULT_SPLASH_DIR, DEFAULT_ASSET_DIR, out_dir,
            min_conf=args.min_conf, pad=args.pad,
        )
    except Exception as exc:  # noqa: BLE001 - never surface a raw torch/onnx trace
        print("weapon-crop curation failed - generator not provisioned or a "
              "DWPose/backend error (see logs). Run the Phase-0 setup "
              "(docs/GEN_MODELS.md).", file=sys.stderr)
        _log_error(exc)
        return 1

    _print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
