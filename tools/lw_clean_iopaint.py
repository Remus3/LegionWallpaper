"""Legion Wallpaper - Stage-2 IOPaint-emulation watermark cleaner.

Automates the operator's PROVEN manual IOPaint (model=lama) piece-by-piece
watermark removal: hand-masking the mark in small pieces gave a faithful clean,
and we reproduce that with simple-lama (the SAME LaMa model, already in the
lw-clean venv) driven by an ACCURATE, COMPLETE auto-mask. This is masked
inpainting - NOT the parked Dekel matting-inversion R&D worker; it REPLACES that
approach for actually cleaning the slugs.

VALIDATED recipe (proven this session on namakx dfz5w2g, see the scratchpad
progressive probe): the COMPLETE mask is a diff-from-median-background that
covers the bright glyph FILL *and* the dark glyph OUTLINE - a white-only mask
leaves a dark edge ghost, so the mask must catch both:

    gray = roi.mean(2); bg = medianBlur(gray, 21)
    diff = gray - bg
    mark = (diff > +10) | (diff < -14)      # bright FILL or dark OUTLINE
    mark = close(mark, 3x3); mask = dilate(mark, 7x7, 1)   # ~3px, swallows ramp

then ONE LaMa pass (near-clean). A --progressive peel-and-commit-ring mode is
kept for stubborn dense small-text lines (each pass fills the FULL remaining mask
so context is never watermark, but commits only the outer 1px ring, then erodes
inward and repeats).

MASK GENERALIZATION: namakx is white; other artists' marks may be coloured (e.g.
a blue DeviantArt credit). An optional CHROMA term (opponent-colour distance from
the local-median chroma) is OR-ed into the luma mark to catch coloured marks that
barely differ in luma. When a same-artist CLUSTER of >= 3 frames is available the
cross-image FILLED matte (lw_clean_dekel.estimate_filled_alpha over the aligned
ROI stack) is the more accurate mask - the mark is common to every frame while the
art cancels; single one-off slugs fall back to the single-image diff+chroma mask.

TWO-LAYER IMPORT DISCIPLINE (mirrors lw_clean_pass): module top-level imports are
stdlib + numpy + PIL + lw_clean_pass ONLY (all CI-safe). torch, simple_lama,
cv2 and lw_clean_dekel are LAZY-imported inside the functions that need them, so
the committed pure test suite imports this module and exercises the mask builder,
the argv builders and the region-identity check with NO GPU and NO cv2. cv2 is an
optional accelerator for the median blur (fast path on the real ROI); a pure-numpy
fallback keeps the mask builder correct wherever cv2 is absent.

This worker PRODUCES pixels (a candidate PNG in a non-pipeline runtime dir) plus
the exact save-working (--tool iopaint) + submit commands for the caller to run;
it NEVER mutates pipeline state (the operator approves via needauth). ASCII-only;
atomic writes; any subprocess would pass CREATE_NO_WINDOW.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image

# lw_clean_pass is stdlib + numpy + PIL at import time (its ML deps are lazy), so
# reusing its inpaint_lama / atomic writers / working-image selection / submit
# builder / paths here is CI-safe. Do NOT add cv2/torch imports at module top.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lw_clean_pass as C  # noqa: E402

# --------------------------------------------------------------------------
# Paths + cluster presets (Legion machine).
# --------------------------------------------------------------------------
ROOT = C.ROOT
CLEAN_SCRATCH = C.CLEAN_SCRATCH
RUNTIME_CLEAN = C.RUNTIME_CLEAN
SYS_PY = C.SYS_PY
PIPELINE = C.PIPELINE

# namakx repeated-watermark region on the 2560x1440 frame (x0,y0,x1,y1; x1/y1
# exclusive) - matches lw_clean_dekel.DEFAULT_REGION. The pebano region is the
# best-effort DeviantArt logo+credit box located by inspection this session.
NAMAKX_REGION = (848, 1122, 1712, 1430)
PEBANO_REGION = (930, 620, 1600, 1060)
DEFAULT_PAD = 20

# Same-artist sibling slugs for the cross-image FILLED matte (>= 3 -> matte path).
NAMAKX_SLUGS = [
    "dfz5w2g-8ba7345b-5776-4d83-b939-4ca7d045f545",
    "dfzlox4-7e2bdc64-36ce-41fa-80b0-c83f97fdf5f5",
    "dfzypoo-482973ff-dfb0-44e4-a90c-386714d27faf",
    "dfzypou-30bef263-c754-4a26-9797-484757b1c4cf",
    "dfzypp1-251c5c37-e25f-496e-a9a6-4900304e6fa5",
]

# cluster -> (region, chroma_thr, sibling slugs). chroma_thr None = luma-only
# (namakx validated). A coloured-mark cluster sets a chroma threshold so the
# CHROMA term is OR-ed in. vexxsoul is a placeholder until its region is known.
CLUSTER_PRESETS = {
    "namakx": {"region": NAMAKX_REGION, "chroma_thr": None, "slugs": NAMAKX_SLUGS},
    "pebano": {"region": PEBANO_REGION, "chroma_thr": 12.0, "slugs": []},
    "vexxsoul": {"region": None, "chroma_thr": 12.0, "slugs": []},
}

# Per-slug overrides for one-off marks the cluster/default region under-covers.
# Sourced from the 2026-07-16 batch triage (docs/research/IOPAINT_TRIAGE.md):
# improvement 3 (bottom-centre banner class needs a FULL-WIDTH band with x-pad,
# because YOLO+OCR under-covers long low-contrast credit strings) and
# improvement 4 (low-contrast COLOURED marks need the chroma term OR-ed in).
# region None = keep the default/cluster region, only override chroma_thr.
SLUG_PRESETS = {
    # 1 blue speck survived luma-only; chroma at 12 clears it (confirmed).
    "spirit-blossom-ahri-mono-01-by-hriful-dk79ceq-pre": {
        "region": None, "chroma_thr": 12.0,
    },
    # flank "(c)SLI/.DEVIANTART" sat outside the default box; the full-width
    # band + chroma clears it (confirmed).
    "viego-the-king-by-slimshadywallpaper-dhawigh-pre": {
        "region": (860, 958, 1720, 1035), "chroma_thr": 12.0,
    },
    # right-flank ".COM" sat outside the ROI -> widen the band to the right edge.
    "aidraw-2662100118-by-watercolornessie-dma7o8j-fullview": {
        "region": (848, 1122, 2560, 1430), "chroma_thr": 12.0,
    },
}


def resolve_preset(slug, region=None, cluster=None, chroma_thr=None):
    """PURE: settle (region, chroma_thr) for a slug. Returns (region, chroma, source).

    Precedence: explicit args > named cluster > per-slug preset > namakx default.
    source is one of explicit / cluster / slug / default and is logged so a run
    is reproducible from its own output.
    """
    if region is not None or chroma_thr is not None:
        cpre = CLUSTER_PRESETS.get(cluster, {}) if cluster else {}
        spre = SLUG_PRESETS.get(slug, {})
        r = region if region is not None else (
            cpre.get("region") or spre.get("region") or NAMAKX_REGION)
        c = chroma_thr if chroma_thr is not None else (
            cpre.get("chroma_thr") if cluster else spre.get("chroma_thr"))
        return r, c, "explicit"
    if cluster:
        cpre = CLUSTER_PRESETS.get(cluster, {})
        return cpre.get("region") or NAMAKX_REGION, cpre.get("chroma_thr"), "cluster"
    spre = SLUG_PRESETS.get(slug)
    if spre:
        return spre.get("region") or NAMAKX_REGION, spre.get("chroma_thr"), "slug"
    return NAMAKX_REGION, None, "default"

# Validated single-image mask defaults (namakx dfz5w2g).
BRIGHT_THR = 10.0            # gray-bg > +10 -> bright FILL
DARK_THR = -14.0            # gray-bg < -14 -> dark OUTLINE
MEDIAN_K = 21              # background median-blur kernel (odd)
CLOSE_K = 3               # morphological close kernel (odd)
DILATE_K = 7               # dilate kernel (odd) - ~3px, swallows the edge ramp
DILATE_ITER = 1
MATTE_ALPHA_THR = 0.12      # cross-image filled-matte threshold -> mask


# ==========================================================================
# PURE numpy morphology + median (cv2-free; cv2 is an optional median accel)
# ==========================================================================
def _disk_se(radius: int) -> np.ndarray:
    """Boolean elliptical (disk) structuring element of size (2r+1, 2r+1).

    Approximates cv2.getStructuringElement(MORPH_ELLIPSE, (2r+1, 2r+1)); for
    r <= 3 (the recipe's 3x3 close + 7x7 dilate) it is the same footprint.
    """
    if radius < 1:
        return np.ones((1, 1), dtype=bool)
    d = 2 * radius + 1
    yy, xx = np.ogrid[:d, :d]
    return ((yy - radius) ** 2 + (xx - radius) ** 2) <= (radius + 0.5) ** 2


def _binary_dilate(mask_bool: np.ndarray, se: np.ndarray) -> np.ndarray:
    """Binary dilation by structuring element `se` (OR of shifted copies)."""
    mask_bool = np.asarray(mask_bool, dtype=bool)
    r = se.shape[0] // 2
    h, w = mask_bool.shape
    padded = np.pad(mask_bool, r, mode="constant", constant_values=False)
    out = np.zeros_like(mask_bool)
    for di in range(se.shape[0]):
        for dj in range(se.shape[1]):
            if se[di, dj]:
                out |= padded[di:di + h, dj:dj + w]
    return out


def _binary_erode(mask_bool: np.ndarray, se: np.ndarray) -> np.ndarray:
    """Binary erosion by `se` (AND of shifted copies; frame edge does not erode)."""
    mask_bool = np.asarray(mask_bool, dtype=bool)
    r = se.shape[0] // 2
    h, w = mask_bool.shape
    padded = np.pad(mask_bool, r, mode="constant", constant_values=True)
    out = np.ones_like(mask_bool)
    for di in range(se.shape[0]):
        for dj in range(se.shape[1]):
            if se[di, dj]:
                out &= padded[di:di + h, dj:dj + w]
    return out


def _binary_close(mask_bool: np.ndarray, se: np.ndarray) -> np.ndarray:
    """Morphological close = dilate then erode (fills small gaps in the mark)."""
    return _binary_erode(_binary_dilate(mask_bool, se), se)


def _np_median_blur(gray: np.ndarray, k: int) -> np.ndarray:
    """Pure-numpy k x k median blur (edge-padded). CI / no-cv2 fallback.

    Memory scales with k*k per pixel, so this is used only on the small synthetic
    ROIs of the pure tests; the real ROI takes the cv2 fast path in _median_blur.
    """
    r = k // 2
    p = np.pad(np.asarray(gray, dtype=np.float64), r, mode="edge")
    win = sliding_window_view(p, (k, k))
    return np.median(win, axis=(-1, -2))


def _median_blur(gray_u8: np.ndarray, k: int) -> np.ndarray:
    """k x k median background estimate as float. cv2 fast path, numpy fallback."""
    try:
        import cv2
        return cv2.medianBlur(np.asarray(gray_u8, dtype=np.uint8), k).astype(np.float64)
    except Exception:   # noqa: BLE001 - cv2 absent (CI) -> exact numpy fallback
        return _np_median_blur(gray_u8, k)


# ==========================================================================
# PURE numpy chroma term (opponent-colour distance from the local median)
# ==========================================================================
def _chroma_diff(roi_bgr: np.ndarray, median_k: int = MEDIAN_K) -> np.ndarray:
    """Per-pixel chroma distance from the LOCAL median chroma (catches colour).

    cv2 fast path: CIELAB a/b distance from their median-blurred selves - the
    faithful reading of "LAB a/b chroma". numpy fallback: an opponent-colour
    approximation (a ~ R-G, b ~ (R+G)/2 - B) with the same "distance from local
    median" construction, so a coloured mark that barely differs in luma still
    scores high. Both are zero on a neutral local background.
    """
    roi = np.asarray(roi_bgr, dtype=np.float64)
    try:
        import cv2
        lab = cv2.cvtColor(roi.astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float64)
        a, b = lab[:, :, 1], lab[:, :, 2]
        med_a = cv2.medianBlur(lab[:, :, 1].astype(np.uint8), median_k).astype(np.float64)
        med_b = cv2.medianBlur(lab[:, :, 2].astype(np.uint8), median_k).astype(np.float64)
        return np.sqrt((a - med_a) ** 2 + (b - med_b) ** 2)
    except Exception:   # noqa: BLE001 - cv2 absent (CI) -> opponent-colour fallback
        bch, gch, rch = roi[:, :, 0], roi[:, :, 1], roi[:, :, 2]
        a = rch - gch
        b = 0.5 * (rch + gch) - bch
        med_a = _np_median_blur(a, median_k)
        med_b = _np_median_blur(b, median_k)
        return np.sqrt((a - med_a) ** 2 + (b - med_b) ** 2)


# ==========================================================================
# PURE: the COMPLETE watermark mask builder (the validated recipe)
# ==========================================================================
def build_watermark_mask(roi_bgr, bright_thr: float = BRIGHT_THR,
                         dark_thr: float = DARK_THR, chroma_thr=None,
                         median_k: int = MEDIAN_K, close_k: int = CLOSE_K,
                         dilate_k: int = DILATE_K, dilate_iter: int = DILATE_ITER):
    """COMPLETE diff-from-median mask covering the bright FILL and dark OUTLINE.

    roi_bgr: HxWx3 uint8/float (BGR). Returns a uint8 mask (0 / 255), WHITE =
    inpaint, same HxW as the ROI. chroma_thr (if not None) OR-s in the CHROMA
    term so a coloured mark is caught even where it barely differs in luma. The
    close + dilate swallow the 1-2px semi-transparent ramp (the glyph15 lesson:
    a tight white-only mask leaves a dark edge ghost).
    """
    roi = np.asarray(roi_bgr, dtype=np.float64)
    gray = roi.mean(axis=2)
    g8 = np.clip(gray, 0, 255).astype(np.uint8)
    bg = _median_blur(g8, median_k)
    diff = gray - bg
    mark = (diff > bright_thr) | (diff < dark_thr)
    if chroma_thr is not None:
        mark = mark | (_chroma_diff(roi, median_k) > chroma_thr)
    mark = mark.astype(bool)
    if close_k and close_k >= 3:
        mark = _binary_close(mark, _disk_se(close_k // 2))
    if dilate_k and dilate_k >= 3:
        se = _disk_se(dilate_k // 2)
        for _ in range(max(1, dilate_iter)):
            mark = _binary_dilate(mark, se)
    return (mark.astype(np.uint8) * 255)


def mask_coverage_pct(mask_u8) -> float:
    """Percent of the ROI the mask marks for inpainting."""
    m = np.asarray(mask_u8)
    if m.size == 0:
        return 0.0
    return float(np.count_nonzero(m > 127)) / float(m.size) * 100.0


# ==========================================================================
# PURE: ROI geometry, paste-back + full-frame region-identity tripwire
# ==========================================================================
def resolve_roi(full_shape, region, pad: int = DEFAULT_PAD):
    """Clamp (region, pad) to (rx0, ry0, rx1, ry1) inside a full frame."""
    h, w = full_shape[:2]
    x0, y0, x1, y1 = region
    rx0, ry0 = max(int(x0) - pad, 0), max(int(y0) - pad, 0)
    rx1, ry1 = min(int(x1) + pad, w), min(int(y1) + pad, h)
    return rx0, ry0, rx1, ry1


def paste_region_back(full_bgr, roi_after_bgr, roi_box):
    """Return a copy of the full frame with the ROI box replaced by roi_after."""
    rx0, ry0, rx1, ry1 = roi_box
    out = np.array(full_bgr).copy()
    out[ry0:ry1, rx0:rx1, :] = np.asarray(roi_after_bgr)
    return out


def assert_region_identity(full_before, full_after, roi_box):
    """Raise unless every pixel OUTSIDE the ROI box is byte-identical.

    The ROI-scoped tripwire: inpaint_lama keeps outside-MASK pixels identical
    within the ROI, and only the ROI box is pasted back, so the whole frame
    outside the box must be unchanged. A violation is a paste-back bug - halt.
    """
    before = np.asarray(full_before)
    after = np.asarray(full_after)
    rx0, ry0, rx1, ry1 = roi_box
    mask = np.zeros(before.shape[:2], dtype=bool)
    mask[ry0:ry1, rx0:rx1] = True
    outside = ~mask
    if before.ndim == 3:
        outside = np.broadcast_to(outside[:, :, None], before.shape)
    if not np.array_equal(after[outside], before[outside]):
        raise AssertionError(
            "lw_clean_iopaint mutated pixels OUTSIDE the ROI box "
            "(region paste-back identity violated)")


# ==========================================================================
# PURE: pipeline command builders (PRINTED, never executed here)
# ==========================================================================
def build_save_working_cmd(slug, from_path, params, tool="iopaint",
                           sys_py=SYS_PY, pipeline=PIPELINE):
    """argv for `save-working <slug> --from <path> --tool iopaint --params <json>`.

    Distinct from lw_clean_pass.build_save_working_cmd (which hard-codes lama);
    the IOPaint-emulation clean records --tool iopaint so provenance reflects the
    piece-by-piece LaMa lane the operator approves.
    """
    return [sys_py, pipeline, "save-working", slug, "--from", str(from_path),
            "--tool", tool, "--params", json.dumps(params)]


def build_submit_cmd(slug, sys_py=SYS_PY, pipeline=PIPELINE):
    """argv for `submit <slug>` (reuses the lw_clean_pass builder)."""
    return C.build_submit_cmd(slug, sys_py, pipeline)


def _quote(tok):
    tok = str(tok)
    return f'"{tok}"' if (" " in tok or "\t" in tok) else tok


def _print_cmds(cmds):
    for argv in cmds:
        print("  " + " ".join(_quote(t) for t in argv))


def _file_link(path):
    return "file:///" + os.path.abspath(path).replace("\\", "/")


# ==========================================================================
# ML layer (LAZY imports - never touched by the pure TDD suite / CI)
# ==========================================================================
def _load_lama(device=None):
    """Construct a SimpleLama on cuda if available (lazy heavy import).

    `device` is accepted so the caller can probe it BEFORE deciding whether to
    take the GPU mutex, and then load on the same device it locked for. Without
    that the lock decision and the placement could disagree.
    """
    import torch
    from simple_lama_inpainting import SimpleLama
    dev = device or ("cuda" if torch.cuda.is_available() else "cpu")
    return SimpleLama(device=torch.device(dev)), dev


def _bgr_to_rgb_pil(bgr):
    return Image.fromarray(np.asarray(bgr)[:, :, ::-1].astype(np.uint8))


def inpaint_once(roi_bgr, mask_u8, lama):
    """One LaMa pass over the masked ROI; outside-mask stays byte-identical.

    Reuses lw_clean_pass.inpaint_lama (the composite identity rule). Returns a
    BGR uint8 ROI the same size as the input.
    """
    out_pil = C.inpaint_lama(_bgr_to_rgb_pil(roi_bgr),
                             Image.fromarray(np.asarray(mask_u8, dtype=np.uint8)),
                             lama)
    return np.asarray(out_pil.convert("RGB"))[:, :, ::-1].copy()


def inpaint_progressive(roi_bgr, mask_u8, lama, max_iter: int = 25, log=print):
    """Peel-and-commit-ring inpaint for stubborn dense small-text.

    Each pass LaMa fills the FULL remaining mask (so context is only real art,
    never watermark), but commits ONLY the outer 1px ring, then erodes inward and
    repeats. Emulates covering the mark from its clean edge toward the stroke core.
    """
    cur = np.asarray(roi_bgr).copy()
    work = np.asarray(mask_u8) > 0
    se = _disk_se(1)   # 3x3
    for it in range(max_iter):
        if int(work.sum()) == 0:
            break
        filled = inpaint_once(cur, (work * 255).astype(np.uint8), lama)
        eroded = _binary_erode(work, se)
        ring = work & (~eroded)
        if int(ring.sum()) == 0:
            ring = work   # commit the last core
        cur[ring] = filled[ring]
        work = eroded
        log(f"  progressive pass {it}: committed {int(ring.sum())} px, "
            f"remaining {int(work.sum())}")
    return cur


def cluster_matte_mask(target_full, siblings_full, region, pad,
                       alpha_thr: float = MATTE_ALPHA_THR, dilate_k: int = DILATE_K,
                       log=print):
    """Cross-image FILLED-matte mask for the target ROI (>= 3 aligned frames).

    Aligns the target + sibling ROIs on the shared mark, estimates the filled
    continuous matte (mark common, art cancels), inverse-warps it to the target
    geometry, thresholds + dilates. Lazy-imports lw_clean_dekel (cv2/scipy/skimage).
    Returns a uint8 ROI mask (0 / 255) or None if the matte is empty.
    """
    import cv2
    import lw_clean_dekel as D
    rx0, ry0, rx1, ry1 = resolve_roi(target_full.shape, region, pad)
    frames = [target_full] + list(siblings_full)
    rois = [f[ry0:ry1, rx0:rx1, :].astype(np.float64) for f in frames]
    aligned, _fwd, inv, shifts = D.align_rois(rois)
    log(f"  matte: aligned {len(rois)} frames, target shift "
        f"(dy,dx)=({shifts[0][0]:+.2f},{shifts[0][1]:+.2f})")
    alpha = D.estimate_filled_alpha(np.array(aligned))      # [0,1] in aligned frame
    hroi, wroi = rois[0].shape[:2]
    alpha_target = cv2.warpAffine(alpha.astype(np.float64), inv[0], (wroi, hroi),
                                  flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    mark = alpha_target > alpha_thr
    if int(mark.sum()) == 0:
        return None
    if dilate_k and dilate_k >= 3:
        mark = _binary_dilate(mark, _disk_se(dilate_k // 2))
    return (mark.astype(np.uint8) * 255)


# ==========================================================================
# ORCHESTRATION
# ==========================================================================
def _load_full_bgr(path):
    """Read an image as BGR uint8 (cv2 fast path, PIL fallback)."""
    try:
        import cv2
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is not None:
            return img
    except Exception:   # noqa: BLE001 - cv2 absent -> PIL fallback
        pass
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))[:, :, ::-1].copy()


def _sibling_fulls(cluster, target_slug):
    """Load the same-artist sibling full frames for the cross-image matte."""
    preset = CLUSTER_PRESETS.get(cluster, {})
    out = []
    for slug in preset.get("slugs", []):
        if slug == target_slug:
            continue
        img = C.select_working_image(os.path.join(CLEAN_SCRATCH, slug), slug)
        if img:
            out.append(_load_full_bgr(img))
    return out


def clean_slug(slug, image=None, region=None, cluster=None, chroma_thr=None,
               pad=DEFAULT_PAD, progressive=False, use_matte=None, out_dir=None,
               dry_run=False, max_iter=25, log=print):
    """IOPaint-emulation clean for one slug. Returns a result dict.

    Never mutates pipeline state: writes the candidate full PNG + before/after
    ROI + mask to out_dir and PRINTS the save-working (--tool iopaint) + submit
    commands. dry_run builds + writes the mask/before ROI only (no GPU, no clean).
    """
    region, chroma_thr, preset_src = resolve_preset(slug, region, cluster, chroma_thr)
    log(f"LW IOPAINT {slug}: region={region} chroma_thr={chroma_thr} "
        f"(source={preset_src})")

    if image is None:
        image = C.select_working_image(os.path.join(CLEAN_SCRATCH, slug), slug)
    if image is None or not os.path.isfile(image):
        return {"slug": slug, "status": "error", "reason": "no clean input image"}

    full = _load_full_bgr(image)
    roi_box = resolve_roi(full.shape, region, pad)
    rx0, ry0, rx1, ry1 = roi_box
    roi = full[ry0:ry1, rx0:rx1, :].copy()

    siblings = _sibling_fulls(cluster, slug) if cluster else []
    matte = use_matte if use_matte is not None else (len(siblings) >= 2)
    mask_kind = "diff"
    mask = None
    if matte and siblings:
        try:
            mask = cluster_matte_mask(full, siblings, region, pad, log=log)
            mask_kind = "matte"
        except Exception as exc:   # noqa: BLE001 - matte is optional; degrade to diff
            log(f"LW IOPAINT {slug}: matte failed ({exc}); using single-image diff")
            mask = None
    if mask is None:
        mask = build_watermark_mask(roi, chroma_thr=chroma_thr)
        mask_kind = "diff"
    cov = mask_coverage_pct(mask)

    target = out_dir or os.path.join(RUNTIME_CLEAN, slug)
    os.makedirs(target, exist_ok=True)
    before_path = os.path.join(target, f"{slug}_iopaint_before.png")
    mask_path = os.path.join(target, f"{slug}_iopaint_mask.png")
    C.atomic_write_png(before_path, roi[:, :, ::-1])       # BGR->RGB for PIL
    C.atomic_write_png(mask_path, mask)
    log(f"LW IOPAINT {slug}: region={region} pad={pad} mask={mask_kind} "
        f"chroma_thr={chroma_thr} coverage={cov:.1f}% mode="
        f"{'progressive' if progressive else 'one-pass'}")

    rec = {"slug": slug, "region": list(region), "pad": pad, "mask": mask_kind,
           "chroma_thr": chroma_thr, "mask_coverage_pct": round(cov, 3),
           "mode": "progressive" if progressive else "one-pass",
           "before": before_path, "mask_png": mask_path}

    if dry_run:
        rec["status"] = "dry-run"
        log(f"  before {_file_link(before_path)}")
        log(f"  mask   {_file_link(mask_path)}")
        return rec

    # The hold spans the LaMa load AND the inpaint: loading puts weights on the
    # card, and a half-resident model racing another process's allocation is the
    # OOM this prevents. The device is probed first so a CPU-only box never
    # takes the machine-wide mutex - serializing CPU inpainting across three
    # repos would be pure loss. The dry-run branch returned above without ever
    # reaching here, so a mask-only run never blocks on the GPU.
    # gpu_lock comes from lw_clean_pass (already imported as C) rather than a
    # sixth copy of the helper - same venv, one timeout constant.
    # A contended acquire is the EXPECTED case at N=3, not an anomaly, so it
    # returns a status the caller can read rather than a raw winmutex traceback
    # (CLAUDE.md "Error Handling"). gpu_lock has already written the TIMEOUT
    # line to logs/YYYY-MM-DD.log, so the raw reason is never lost. Nothing has
    # been written at this point - the candidate PNGs are saved further down.
    dev = C._cuda_device()
    try:
        with C.gpu_lock(dev, log=log):
            lama, dev = _load_lama(dev)
            log(f"  simple-lama on {dev}")
            if progressive:
                roi_after = inpaint_progressive(roi, mask, lama,
                                                max_iter=max_iter, log=log)
            else:
                roi_after = inpaint_once(roi, mask, lama)
    except C.GpuBusy as exc:
        log(f"LW IOPAINT {slug}: GPU held by another run - skipped, nothing "
            f"written. Re-run this slug once the holder finishes.")
        return {"slug": slug, "status": "gpu_busy",
                "reason": "the GPU is held by another run and did not free in "
                          "time; this slug was skipped and nothing was written",
                "detail": str(exc)}

    full_after = paste_region_back(full, roi_after, roi_box)
    assert_region_identity(full, full_after, roi_box)      # tripwire

    after_path = os.path.join(target, f"{slug}_iopaint_after.png")
    cand_path = os.path.join(target, f"{slug}_clean_cand.png")
    C.atomic_write_png(after_path, roi_after[:, :, ::-1])
    C.atomic_write_png(cand_path, full_after[:, :, ::-1])

    params = {"engine": "simple-lama-iopaint", "region": list(region), "pad": pad,
              "mask": mask_kind, "chroma_thr": chroma_thr,
              "mask_coverage_pct": round(cov, 3),
              "mode": rec["mode"], "device": dev}
    save = build_save_working_cmd(slug, cand_path, params)
    sub = build_submit_cmd(slug)
    C.atomic_write_json(os.path.join(target, f"{slug}_iopaint.json"),
                        {**rec, "after": after_path, "cand": cand_path,
                         "params": params})
    rec["status"] = "cleaned"
    rec["after"] = after_path
    rec["cand"] = cand_path
    rec["commands"] = [save, sub]
    log(f"LW IOPAINT {slug}: CLEAN candidate written (mask={mask_kind}, "
        f"coverage={cov:.1f}%)")
    log(f"  before {_file_link(before_path)}")
    log(f"  after  {_file_link(after_path)}")
    log(f"  cand   {_file_link(cand_path)}")
    print("  next (operator approves via needauth):")
    _print_cmds([save, sub])
    return rec


# ==========================================================================
# CLI
# ==========================================================================
def _parse_region(text):
    parts = [int(v) for v in text.split(",")]
    if len(parts) != 4:
        raise ValueError("region must be x0,y0,x1,y1")
    return tuple(parts)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="lw_clean_iopaint",
        description="Legion Wallpaper Stage-2 IOPaint-emulation watermark cleaner")
    p.add_argument("slug", nargs="?", help="single slug to clean")
    p.add_argument("--image", help="explicit input image override")
    p.add_argument("--region", type=_parse_region, default=None,
                   help="watermark region x0,y0,x1,y1 (overrides --cluster)")
    p.add_argument("--cluster", choices=sorted(CLUSTER_PRESETS),
                   help="named cluster: sets region + chroma + sibling frames")
    p.add_argument("--chroma-thr", type=float, default=None,
                   help="OR-in the chroma term at this threshold (colour marks)")
    p.add_argument("--pad", type=int, default=DEFAULT_PAD)
    p.add_argument("--progressive", action="store_true",
                   help="peel-and-commit-ring mode for stubborn dense small-text")
    p.add_argument("--matte", dest="matte", action="store_true", default=None,
                   help="force the cross-image filled-matte mask (needs siblings)")
    p.add_argument("--no-matte", dest="matte", action="store_false",
                   help="force the single-image diff mask even with a cluster")
    p.add_argument("--out-dir", help="candidate/side-file dir (default runtime)")
    p.add_argument("--max-iter", type=int, default=25,
                   help="progressive-mode iteration cap")
    p.add_argument("--dry-run", action="store_true",
                   help="build + write the mask/before ROI only (no GPU)")
    args = p.parse_args(argv)

    if not args.slug:
        p.error("give a slug (with optional --region / --cluster)")

    res = clean_slug(args.slug, image=args.image, region=args.region,
                     cluster=args.cluster, chroma_thr=args.chroma_thr, pad=args.pad,
                     progressive=args.progressive, use_matte=args.matte,
                     out_dir=args.out_dir, dry_run=args.dry_run,
                     max_iter=args.max_iter)
    print(json.dumps({k: v for k, v in res.items() if k != "commands"},
                     indent=2, default=str))
    # gpu_busy is a non-zero exit like error: nothing was produced, and a batch
    # driver must not read the slug as cleaned.
    return 0 if res.get("status") not in ("error", "gpu_busy") else 1


if __name__ == "__main__":
    sys.exit(main())
