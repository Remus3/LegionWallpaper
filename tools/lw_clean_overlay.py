"""Centre-overlay detector - the DeviantArt semi-transparent watermark.

ROADMAP `cleaning-detector-recall`. The recall census (2026-08-11,
`docs/CLEAN_DETECTOR_RECALL_2026-08-11.md`) measured 14 false negatives over the
302 unrouted firstdones and found **11 of them are one object**: the DA centre
overlay - the site's logo plus `(C) NAME.DEVIANTART.COM`, alpha-composited over
the middle of the frame.

WHY A NEW DETECTOR RATHER THAN A LOWER THRESHOLD. That census also measured why
the existing stack cannot see it:
  * YOLO scores it 0.11-0.25 against a 0.35 detect floor, and TWO of the misses
    carry no box at any confidence - so it is partly a model limitation, not a
    threshold one;
  * EasyOCR returns garble for low-alpha text over busy art, so
    `is_watermark_text` never sees "deviantart";
  * its centroid is mid-frame, so every geometry rule in the gate would answer
    `qa` even if it were boxed.
Dropping the conf floor was measured to be the wrong lever: a low-conf box is a
good FLAG (13 of 17 low-conf `clean` images are real misses) but a bad AUTO
signal, and precision over the gated corpus is currently 0 false positives in 14
proposals (`docs/CLEAN_DETECTOR_PRECISION_2026-08-11.md`).

WHAT IT EXPLOITS INSTEAD. The overlay is the SAME pixels at the SAME place on
every image the site serves. Median-stacking the high-pass of images that carry
it cancels the art and leaves the mark: measured on the corpus, the stack of the
11 positives renders the logo and the URL legibly, while the stack of 8
negatives renders nothing. So:

    template = median over marked frames of (luma - local mean), in the band
    score    = zero-mean normalized correlation of one frame's high-pass
               against that template, over the template's own support

Correlation is amplitude-normalised, which is the property that matters here:
the mark's alpha varies with the background it sits on, but its SHAPE does not.

The score FLAGS to `qa` and never routes to `auto` - see `gate_decision` in
`lw_clean_pass.py` and the invariants pinned in `tests/test_lw_clean_overlay.py`.

Pure numpy + PIL. No cv2, no torch, no GPU, so the whole thing runs in CI. The
estimated template is a derivative of a third party's watermark, so it is
CACHED UNDER `ops/runtime/` (gitignored) and rebuilt from the local corpus - it
is never tracked in this public repo.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lw_clean_pass import _box_mean, _to_gray  # noqa: E402

# The overlay sits at a fixed relative height. Measured over the corpus: every
# detected DA mark centroid lands at y/h ~ 0.69 (precision census) and the
# stacked template's structure spans roughly 0.60-0.72. The band is deliberately
# wider than that so a site tweak does not silently fall out of frame.
BAND = (0.55, 0.85)
# Keep the strongest 2 percent of template pixels as its support. The mark is a
# thin, sparse glyph set: correlating over the whole band would drown it in the
# residual art the median did not fully cancel.
SUPPORT_PCT = 98.0
HP_WIN = 9
# The mark is low-amplitude; clip so one hard art edge cannot dominate.
CLIP_LEVELS = 8.0
# Shift-search half-window, as a fraction of the FRAME (not the band): +-43px
# vertically and +-41px horizontally at 2560x1440. Both are measured - see
# overlay_score. They are separate constants because the band is only 30 percent
# of the frame's height, so one shared fraction would make the vertical window
# 6px and drop a real positive whose mark sits 33px off.
SHIFT_FRAC_Y = 0.030
SHIFT_FRAC_X = 0.016
# REMOVAL-ONLY scale registration (2026-08-12). The overlay is composited at a
# fixed size on the DA-served image, and a firstdone is that image resampled to
# 2560x1440 - so a frame whose source was a different resolution carries the
# mark at a different PIXEL size, which no shift can align. Measured over every
# flagged slug under 0.25 plus 110-cleanup: exactly two are mismatched, both at
# the SAME 1.12 (110-cleanup 0.1090 -> 0.5052, 122 0.1696 -> 0.6542), and both
# land in the range the well-registered frames occupy. Everything else peaks at
# 1.00. The grid is modest and centred on native; 1.12 must stay in it.
SCALE_GRID = (0.88, 0.92, 0.96, 1.00, 1.04, 1.08, 1.12, 1.16, 1.20)
# A non-native scale is accepted only when it is DECISIVE - see accept_scale.
SCALE_ACCEPT_RATIO = 2.0

# Removal knobs. MEDIAN_SIZE must exceed the mark's stroke width (~5px at
# 2560x1440) so the seed background loses the text but keeps the painting.
MEDIAN_SIZE = 15
MATTE_ITERS = 3              # regression <-> background re-estimate rounds
ALPHA_MAX = 0.95             # 1/(1-a) is singular at a = 1
ALPHA_FLOOR = 0.02           # below this, leave the pixel alone entirely
SUPPORT_DILATE = 9           # grow the template support to cover the alpha ramp
# Model-fit gates on the per-pixel regression. A pixel only gets an alpha if its
# cross-frame variation is real (VAR_FLOOR), is actually explained by the
# matting model (R2_FLOOR), and yields one alpha all three channels agree on.
VAR_FLOOR = 4.0              # levels^2 of background variation across frames
R2_FLOOR = 0.5
CHANNEL_SPREAD_MAX = 0.25
OPEN_SIZE = 3                # speck-removal opening on the recovered matte
# The mark's colour. Held CONSTANT on purpose - see _w_map for the measurement
# that killed the per-pixel version. The corpus overlay is near-white.
W_REF = (250.0, 250.0, 250.0)
# Gains searched by _fit_gain. The measured optimum on the corpus is 2.0, well
# inside the grid, so the fit is choosing rather than saturating.
GAIN_GRID = (0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0)

TEMPLATE_PATH = os.path.join(
    r"C:\LegionWallpaper", "ops", "runtime", "clean", "overlay_template.npz")
MATTE_PATH = os.path.join(
    r"C:\LegionWallpaper", "ops", "runtime", "clean", "overlay_matte.npz")

# REMOVAL needs a WIDER band than DETECTION does, and the difference is measured:
# BAND starts at 0.55h, but the DA logo's top edge sits at y/h ~ 0.506 on
# mecha-ahri (2560x1440: row 728 vs the band's row 792). Detection does not care -
# the credit line alone separates positives from art - but removal does: the
# clipped 64 rows are a flat semi-transparent veil the matting inversion never
# touches, and it stays legible after the pre-pass. The detector's BAND is
# CALIBRATED and pinned by tests (threshold 0.15 was measured on it), so removal
# gets its own band + its own cached pair rather than moving that constant.
REMOVAL_BAND = (0.45, 0.85)
WIDE_TEMPLATE_PATH = os.path.join(
    r"C:\LegionWallpaper", "ops", "runtime", "clean",
    "overlay_template_wide.npz")
WIDE_MATTE_PATH = os.path.join(
    r"C:\LegionWallpaper", "ops", "runtime", "clean", "overlay_matte_wide.npz")


def highpass(image, win: int = HP_WIN):
    """Luma minus its local mean - the same primitive the gate already uses."""
    arr = np.asarray(image, dtype=np.float64)
    g = _to_gray(arr)
    return g - _box_mean(g, win)


def band_of(arr2d, band=BAND):
    """The horizontal slice of a 2D array the overlay lives in."""
    h = arr2d.shape[0]
    return arr2d[int(h * band[0]):int(h * band[1]), :]


def _resize2d(arr2d, shape, nearest=False):
    """Resize a 2D float/bool array to `shape` (h, w) via PIL."""
    mode = Image.NEAREST if nearest else Image.BILINEAR
    src = np.asarray(arr2d)
    im = Image.fromarray(src.astype(np.float32), mode="F")
    out = im.resize((int(shape[1]), int(shape[0])), mode)
    res = np.asarray(out, dtype=np.float64)
    return res > 0.5 if nearest else res


def scale2d_centered(arr2d, s: float):
    """PURE: rescale a 2D array by `s` about its centre, keeping its shape.

    Scaling UP crops the overflow, scaling DOWN pads with zero. Bool arrays stay
    bool (nearest), so a support or a mask survives the trip. s == 1.0 returns
    the input untouched, which is what keeps the scale-1.0 arm of
    `best_registration` bit-identical to the old translation-only path.
    """
    src = np.asarray(arr2d)
    if float(s) == 1.0:
        return src
    is_bool = src.dtype == bool
    h, w = src.shape
    nh, nw = max(int(round(h * s)), 1), max(int(round(w * s)), 1)
    res = _resize2d(src, (nh, nw), nearest=is_bool)
    out = np.zeros((h, w), dtype=bool if is_bool else np.float64)
    if nh >= h and nw >= w:
        oy, ox = (nh - h) // 2, (nw - w) // 2
        out[:, :] = res[oy:oy + h, ox:ox + w]
        return out
    ch, cw = min(nh, h), min(nw, w)
    sy, sx = max((nh - h) // 2, 0), max((nw - w) // 2, 0)
    dy, dx = max((h - nh) // 2, 0), max((w - nw) // 2, 0)
    out[dy:dy + ch, dx:dx + cw] = res[sy:sy + ch, sx:sx + cw]
    return out


def _scale_tpl(tpl, s):
    """A template rescaled about the band centre (template + support together)."""
    if float(s) == 1.0:
        return tpl
    return {"template": scale2d_centered(np.asarray(tpl["template"],
                                                    dtype=np.float64), s),
            "support": scale2d_centered(np.asarray(tpl["support"], dtype=bool), s),
            "band": tpl["band"], "n": tpl.get("n", 0)}


def accept_scale(scaled_score, native_score,
                 ratio: float = None) -> bool:
    """Is a non-native scale DECISIVE enough to register at?

    Frames that are correctly registered at 1.00 still wobble under a scale
    search - measured, at most 1.22x the native score (270f, 0.1548 -> 0.1889 at
    0.94) - while the two genuinely mismatched frames come in at 3.86x and 4.63x.
    So the gate sits at 2.0, far from both, and a refusal keeps scale 1.0: a
    wrong scale is a wrong edit, a refused one is only today's behaviour.

    A non-positive native score makes the ratio meaningless, so it never accepts.
    """
    ratio = SCALE_ACCEPT_RATIO if ratio is None else ratio
    if float(native_score) <= 0.0:
        return False
    return float(scaled_score) >= float(native_score) * float(ratio)


def best_registration(image, tpl, scales=None, max_shift=None, ratio=None):
    """(score, dy, dx, scale) - registration for REMOVAL, not for the gate.

    `best_shift` aligns translation only. Two frames in the flagged family carry
    the overlay at a different PIXEL SIZE and no shift can align them:
    `110-cleanup` 0.1090 -> 0.5052 and `122` 0.1696 -> 0.6542, both at 1.12,
    both landing in the range the well-registered frames already occupy. Every
    other flagged frame under 0.25 peaks at 1.00.

    THIS IS DELIBERATELY NOT WIRED INTO `overlay_score`. Measured on the top of
    the clean population, a max-over-scales lifts `wallpapersden-...-sejuani`
    from 0.1213 to 0.1537, over the 0.15 flag - a false positive manufactured by
    the search, the same lesson the shift window learned. Detection keeps the
    tight window; only removal, which runs on frames already judged to carry the
    mark, gets to look for the scale.
    """
    if not tpl:
        return (0.0, 0, 0, 1.0)
    scales = SCALE_GRID if scales is None else scales
    native = _correlate(image, tpl, max_shift)
    best, best_s = native, 1.0
    for s in scales:
        if float(s) == 1.0:
            continue
        cand = _correlate(image, _scale_tpl(tpl, s), max_shift)
        if cand[0] > best[0]:
            best, best_s = cand, float(s)
    if best_s != 1.0 and not accept_scale(best[0], native[0], ratio):
        return (native[0], native[1], native[2], 1.0)
    return (best[0], best[1], best[2], best_s)


def estimate_template(images, band=BAND, support_pct: float = SUPPORT_PCT):
    """Median high-pass of frames that carry the mark -> {template, support, band}.

    Every frame is reduced to its band, resized to the FIRST frame's band shape
    so a mixed-resolution corpus still stacks, then median-combined. The median
    (not the mean) is what makes one bright artwork unable to invent structure.
    """
    stack = []
    ref = None
    for im in images:
        b = band_of(highpass(im), band)
        if ref is None:
            ref = b.shape
        elif b.shape != ref:
            b = _resize2d(b, ref)
        stack.append(b)
    if not stack:
        raise ValueError("estimate_template needs at least one image")
    med = np.median(np.stack(stack), axis=0)
    thr = float(np.percentile(np.abs(med), support_pct))
    support = np.abs(med) >= max(thr, 1e-9)
    return {"template": med, "support": support, "band": tuple(band),
            "n": len(stack)}


def _cross_correlate(a, b):
    """Circular cross-correlation of two same-shape arrays (FFT, numpy only)."""
    return np.fft.irfft2(np.fft.rfft2(a) * np.conj(np.fft.rfft2(b)), s=a.shape)


def best_shift(image, tpl, max_shift=None):
    """(score, dy, dx) - the correlation peak and where it sat.

    Removal needs the WHERE as much as the whether: the matte is estimated in
    template coordinates, so each frame's mark has to be registered before the
    matting equation is inverted, or the reconstruction subtracts the mark from
    the wrong pixels. Integer pixels only for now; the R&D plan's sub-pixel
    alignment (section 3 item 2) is not implemented.
    """
    return _correlate(image, tpl, max_shift)


def overlay_score(image, tpl, max_shift=None) -> float:
    """Best masked normalized correlation of an image against the template.

    Returns a value in [-1, 1]; 0.0 for a flat frame, a missing template, or an
    empty support. The template is resized to the image's band when the frame
    size differs, so nothing here hard-codes 2560x1440.

    WHY A SHIFT SEARCH. The overlay's ABSOLUTE position moves between images
    even though its relative geometry is fixed: a firstdone is a crop plus a
    downscale of a source whose aspect ratio varies, so the mark lands a few
    dozen pixels off. Measured leave-one-ARTIST-out over the corpus positives:
    with no search the weakest positive scored -0.02 (indistinguishable from
    clean art); with the search it scores 0.100 while the strongest of 15
    reviewed clean frames reaches 0.071.

    The window is deliberately TIGHT (`SHIFT_FRAC` of the frame). Widening it to
    +-90px/+-200px was measured to lift the clean frames to 0.095 - a wider
    search buys the negatives more chances to find a lucky alignment than it
    buys the positives.

    Values are clipped to +-`CLIP_LEVELS` first. The mark is a LOW-amplitude
    structure; without the clip a single hard art edge inside the support
    dominates the correlation (measured: clipping lifts the positive median
    from 0.112 to 0.220 leave-one-artist-out).
    """
    return _correlate(image, tpl, max_shift)[0]


def _correlate(image, tpl, max_shift=None):
    """Shared core of overlay_score / best_shift -> (score, dy, dx)."""
    if not tpl:
        return (0.0, 0, 0)
    b = band_of(highpass(image), tpl["band"])
    t = np.asarray(tpl["template"], dtype=np.float64)
    s = np.asarray(tpl["support"], dtype=bool)
    if t.shape != b.shape:
        t = _resize2d(t, b.shape)
        s = _resize2d(s, b.shape, nearest=True)
    m = s.astype(np.float64)
    n = float(m.sum())
    if n <= 0:
        return (0.0, 0, 0)
    # Clip the IMAGE only. Clipping the template too looks symmetric and is a
    # bug: a strong template saturates to a constant on its own support, its
    # variance goes to zero and the correlation collapses to exactly 0.0. Found
    # by a synthetic fixture whose planted mark is far stronger than the real
    # overlay - on the corpus the template's values are a few levels, so the
    # clip never bit and the bug stayed invisible.
    x = np.clip(b, -CLIP_LEVELS, CLIP_LEVELS)
    if float(np.abs(x).max()) <= 1e-9:
        return (0.0, 0, 0)

    tm = t * m
    sum_t = float(tm.sum())
    den_t = max(float((t * t * m).sum()) - sum_t * sum_t / n, 1e-9)
    s1 = _cross_correlate(x, m)
    s2 = _cross_correlate(x * x, m)
    sxt = _cross_correlate(x, tm)
    num = sxt - s1 * (sum_t / n)
    den_x = np.maximum(s2 - s1 * s1 / n, 1e-9)
    ncc = num / np.sqrt(den_x * den_t)

    h, w = x.shape
    band = tpl["band"]
    frame_h = h / max(float(band[1]) - float(band[0]), 1e-6)
    fy, fx = (SHIFT_FRAC_Y, SHIFT_FRAC_X) if max_shift is None else (
        max_shift, max_shift)
    dy = np.fft.fftfreq(h, 1.0 / h).astype(int)
    dx = np.fft.fftfreq(w, 1.0 / w).astype(int)
    ky = np.abs(dy) <= max(1, int(fy * frame_h))
    kx = np.abs(dx) <= max(1, int(fx * w))
    win = ncc[np.ix_(ky, kx)]
    if win.size == 0:
        return (0.0, 0, 0)
    iy, ix = np.unravel_index(int(np.argmax(win)), win.shape)
    return (float(win[iy, ix]), int(dy[ky][iy]), int(dx[kx][ix]))


# ==========================================================================
# REMOVAL: recover (W, alpha) from the collection, then invert I = (1-a)J + aW
# ==========================================================================
def _fill_masked_columns(band_rgb, mask):
    """Background seed: erase the masked pixels and interpolate ACROSS COLUMNS.

    A median filter was the obvious seed and is the recorded failure of R&D
    method 4 - "alpha underestimated (median bg contaminated by dense text)".
    Inside a dense text line every pixel in the window is mark, so the median IS
    the mark and the regression sees no signal to fit. Interpolating from the
    nearest UNMASKED pixels cannot be contaminated that way - the seed never
    contains a mark pixel by construction.

    Down the COLUMNS, not along the rows: this mark is a text line, ~30px tall
    and ~1000px wide, so a row-wise fill has to bridge a thousand pixels of
    unknown art while a column-wise fill bridges thirty. Measured on the
    synthetic fixture, the row-wise seed biased alpha ~20 percent LOW.
    """
    out = np.array(band_rgb, dtype=np.float64, copy=True)
    h, w = mask.shape
    ys = np.arange(h)
    for x in range(w):
        m = mask[:, x]
        if not m.any():
            continue
        good = ~m
        if not good.any():
            continue
        for c in range(out.shape[-1]):
            out[m, x, c] = np.interp(ys[m], ys[good], band_rgb[good, x, c])
    return out


def _median_filter(band_rgb, size: int = MEDIAN_SIZE):
    """Median-filtered copy of a float RGB band - a first guess at the art.

    The mark's strokes are a few pixels wide, so a median wider than a stroke
    erases them while keeping the painting's structure. This is only the SEED:
    the R&D table records that a median background alone underestimates alpha
    where the text is dense (method 4), which is why estimate_matte iterates.
    """
    from PIL import ImageFilter
    u8 = np.clip(np.rint(band_rgb), 0, 255).astype(np.uint8)
    im = Image.fromarray(u8, mode="RGB").filter(ImageFilter.MedianFilter(size))
    return np.asarray(im, dtype=np.float64)


def _dilate_bool(mask, size: int = SUPPORT_DILATE):
    """Grow a boolean mask by `size` pixels (PIL MaxFilter, no cv2 needed)."""
    u8 = (np.asarray(mask, dtype=bool) * 255).astype(np.uint8)
    im = Image.fromarray(u8, mode="L").filter(
        __import__("PIL.ImageFilter", fromlist=["ImageFilter"]).MaxFilter(size))
    return np.asarray(im) > 127


def _open_bool(mask, size: int = OPEN_SIZE):
    """Morphological opening (erode then dilate) of a boolean mask, PIL only."""
    from PIL import ImageFilter
    u8 = (np.asarray(mask, dtype=bool) * 255).astype(np.uint8)
    im = Image.fromarray(u8, mode="L")
    im = im.filter(ImageFilter.MinFilter(size)).filter(
        ImageFilter.MaxFilter(size))
    return np.asarray(im) > 127


def _alpha_shape(stack_i, stack_j, w_ref):
    """Median over the collection of (I - J) / (W - J) - the matte's SHAPE.

    Per frame this ratio IS alpha wherever the model holds; the median over the
    collection is what kills each frame's seed error, which is the noise that
    defeated a per-pixel least-squares fit on the real corpus (its R^2 came out
    at 0.10 - the model explained a tenth of the cross-frame variation, so any
    R^2 gate either dropped 93 percent of the mark or let art through).

    The result is a SHAPE, not a calibrated alpha: this estimator is known to
    read low (R&D method 4, "alpha underestimated"), which `_fit_gain` corrects
    with one measured global factor.
    """
    num = stack_i - stack_j
    den = np.maximum(w_ref[None, None, None, :] - stack_j, 1.0)
    per_channel = np.median(np.clip(num / den, -0.2, 0.98), axis=0)
    return np.clip(per_channel.mean(axis=-1), 0.0, 1.0)


def _fit_gain(shape, region, frames, tpl, w_ref, gains=GAIN_GRID):
    """Pick the global alpha gain that best silences the DETECTOR.

    The estimator recovers the mark's shape reliably and its amplitude only up
    to a constant, so one scalar is fitted rather than assumed - and it is
    fitted against the thing that defines success: how loudly the overlay
    detector still fires after removal. Measured on the 15-frame corpus
    collection, mean post-removal score by gain: 1.0 -> 0.258, 1.5 -> 0.133,
    2.0 -> 0.120, 2.5 -> 0.141, 3.0 -> 0.166. A clear interior optimum, which is
    itself evidence the shape is right and only its scale was off.
    """
    best = (float("inf"), 1.0)
    for g in gains:
        alpha = np.where(region, np.clip(shape * g, 0.0, ALPHA_MAX), 0.0)
        matte = {"alpha": alpha, "W": _w_map(alpha, w_ref),
                 "band": tuple(tpl["band"]), "n": len(frames)}
        scores = []
        for arr, dy, dx in frames:
            cleaned, _ = remove_overlay(arr, matte, shift=(dy, dx))
            scores.append(overlay_score(cleaned.astype(np.float64), tpl))
        mean = float(np.mean(scores)) if scores else float("inf")
        if mean < best[0]:
            best = (mean, float(g))
    return best[1], best[0]


def _w_map(alpha, w_ref):
    """The mark's colour as a full map - constant, and deliberately so.

    Estimating W PER PIXEL is the textbook next step and was measured to
    DIVERGE on this corpus: alpha and W trade off (only their product is
    identifiable without a prior), so re-solving W per pixel and re-fitting drove
    the mean post-removal score 0.149 -> 0.174 -> 0.254 over three rounds while W
    drifted from ~154 to ~87. Dekel's answer is the matting-Laplacian plus IRLS
    priors that pin alpha independently; until that exists, one reference colour
    plus a fitted gain is the stable half of the model. Removing more than the
    detector can still see is not something this data supports.
    """
    return np.broadcast_to(np.asarray(w_ref, dtype=np.float64),
                           alpha.shape + (3,)).copy()


def estimate_matte(images, tpl=None, w_ref=W_REF, alpha_floor=ALPHA_FLOOR):
    """Recover {alpha, W} for the shared overlay from a collection of frames.

    Four steps, each one measured rather than assumed:

      1. REGISTER every frame to the template (`best_shift`). Pooling an
         unregistered collection is the plateau the R&D plan calls its "biggest
         missing piece".
      2. SEED the background by interpolating across the mark's own region, so
         no seed pixel can contain the mark (see `_fill_masked_columns`).
      3. SHAPE the matte as the median of (I-J)/(W-J) over the collection - the
         median is what survives per-frame seed error.
      4. FIT one global gain against the detector's own score (`_fit_gain`),
         because this estimator recovers the shape well and the amplitude only
         up to a constant.

    Outside the template's (dilated) support alpha is forced to zero, so removal
    can only ever touch pixels the detector says carry the mark. The returned
    dict carries `gain` and `score` so a later run can see what was fitted and
    how loud the detector still was.
    """
    band = tuple(tpl["band"]) if tpl else BAND
    frames, bands = [], []
    for im in images:
        arr = np.asarray(im, dtype=np.float64)
        dy = dx = 0
        if tpl is not None:
            _sc, dy, dx = best_shift(arr, tpl)
        frames.append((arr, dy, dx))
        b = band_of(arr, band)
        if dy or dx:
            b = np.roll(b, (-dy, -dx), axis=(0, 1))
        bands.append(b)
    if not bands:
        raise ValueError("estimate_matte needs at least one image")

    stack_i = np.stack(bands)
    if tpl is not None:
        support = np.asarray(tpl["support"], dtype=bool)
        if support.shape != stack_i.shape[1:3]:
            support = _resize2d(support, stack_i.shape[1:3], nearest=True)
        region = _dilate_bool(support)
    else:
        region = np.ones(stack_i.shape[1:3], dtype=bool)
    # A matte is SPATIALLY COHERENT - it is the shape of a glyph - so an
    # isolated pixel in the gap between two glyphs is noise, not a mark. The
    # opening drops 1-2px specks; every real stroke (4-6px wide at 2560x1440)
    # survives.
    region = _open_bool(region)

    seed = np.stack([_fill_masked_columns(b, region) for b in bands])
    w_ref = np.asarray(w_ref, dtype=np.float64)
    shape = np.where(region, _alpha_shape(stack_i, seed, w_ref), 0.0)

    gain, score = (1.0, float("nan"))
    if tpl is not None:
        gain, score = _fit_gain(shape, region, frames, tpl, w_ref)
    alpha = np.where(region, np.clip(shape * gain, 0.0, ALPHA_MAX), 0.0)
    alpha = np.where(alpha >= alpha_floor, alpha, 0.0)
    return {"alpha": alpha, "W": _w_map(alpha, w_ref), "band": band,
            "n": len(bands), "gain": gain, "score": score}


# ==========================================================================
# THE FLAT VEIL: the half of the mark a high-pass template cannot see
# ==========================================================================
# Background window for the whitening. It must be WIDER THAN THE VEIL (the logo
# is ~310px across at 2560x1440) or the median follows the veil and the interior
# reads as background: measured, a 201px window recovers interior alpha 0.028
# where a ~408px one recovers 0.060. cv2.medianBlur cannot go there at all (it
# asserts k < 16 above 8-bit ksize 5), so the window is built by downscaling,
# taking a small median, and scaling back - which is also what keeps this on
# numpy + PIL for CI.
VEIL_SCALE = 8
VEIL_MEDIAN_K = 51           # ~408px at VEIL_SCALE 8
VEIL_THR = 0.015             # consensus whitening -> candidate veil
# CONSENSUS, not median: art structure the median cannot cancel is high in a FEW
# frames, the veil is high in ALL of them, so the low quartile across the
# collection separates them where the median does not. Measured on the fixture:
# median leaves 19 percent of the art above threshold, the 25th percentile
# leaves 0.4 percent while keeping the veil.
VEIL_Q = 25.0
VEIL_SMOOTH_WIN = 15         # the veil is low-frequency; smooth before thresholding
VEIL_CLOSE = 51              # fill the holes a threshold leaves in a solid region
# The veil is a SOLID shape; the art residue 19 frames do not fully cancel is
# scratchy and thin. A big opening separates them where a threshold cannot: at
# 0.05 the raw support sprawls across x 643-2290 of the band.
VEIL_OPEN_R = 5
VEIL_RING = 8                # ring width used to read the boundary step
VEIL_GAIN_GRID = tuple(round(0.5 + 0.25 * i, 2) for i in range(19))  # 0.5 .. 5.0
VEIL_MIN_PX = 400            # below this the support is noise, not a veil
# The support ends INSIDE the veil's true edge (see `_veil_support`), so its
# boundary is not an edge of the ORIGINAL: measured over six corpus frames on
# 2026-08-12, the raw level step across it is |0.0-0.9| levels, while a
# hard-edged correction leaves 12.7-27.4. The correction is therefore ramped out
# instead of cut off. 16px is the knee of the sweep (introduced discontinuity
# mean 23.3 -> 3.4 at 8px -> 2.1 at 16px -> 1.7 at 24px -> 1.3 asymptote; the
# per-pixel p99 jump goes 11.8-16.1 -> 2.2-3.4), and the SMALLEST extension that
# clears it is the safest, because a ramp reaching past the veil darkens real art.
VEIL_FEATHER = 16


def _coarse_median(gray, scale: int = VEIL_SCALE, k: int = VEIL_MEDIAN_K):
    """Median over a window ~`scale * k` wide, via downscale -> median -> upscale.

    An exact median at that width is neither affordable in numpy nor available in
    cv2 (`k < 16`), and it is not needed: the quantity wanted is the level of the
    art AROUND the veil, which survives the downscale.
    """
    from PIL import ImageFilter
    h, w = gray.shape
    sc = max(int(scale), 1)
    small = Image.fromarray(np.clip(gray, 0, 255).astype(np.uint8), mode="L")
    small = small.resize((max(w // sc, 1), max(h // sc, 1)), Image.BILINEAR)
    small = small.filter(ImageFilter.MedianFilter(max(int(k) | 1, 3)))
    return np.asarray(small.resize((w, h), Image.BILINEAR), dtype=np.float64)


def _whiten(band_rgb, scale: int = VEIL_SCALE, k: int = VEIL_MEDIAN_K):
    """`(gray - bg) / (255 - bg)` - alpha for a near-white mark over `bg`."""
    g = np.asarray(band_rgb, dtype=np.float64).mean(axis=2)
    bg = _coarse_median(g, scale, k)
    return np.clip((g - bg) / np.clip(255.0 - bg, 1.0, None), 0.0, 1.0)


def _close_bool(mask, size: int):
    """Morphological closing (dilate then erode) - fills holes in a solid region."""
    from PIL import ImageFilter
    u8 = (np.asarray(mask, dtype=bool) * 255).astype(np.uint8)
    im = Image.fromarray(u8, mode="L")
    im = im.filter(ImageFilter.MaxFilter(max(int(size) | 1, 3)))
    im = im.filter(ImageFilter.MinFilter(max(int(size) | 1, 3)))
    return np.asarray(im) > 127


def _veil_support(raw, thr: float = VEIL_THR, open_r: int = VEIL_OPEN_R,
                  close_k: int = VEIL_CLOSE):
    """Threshold a SMOOTHED map, drop thin residue, then fill the solid region.

    Three steps because the failure modes are three: art residue is thin (the
    opening), a solid veil still thresholds ragged (the closing), and both are
    noisy at pixel scale (the smoothing, done by the caller).

    The support ends ~10px INSIDE the veil's true edge, and that is deliberate:
    over-reaching would darken real art by the full veil alpha, while the missing
    rim is exactly the strip the stroke mask hands to LaMa anyway.
    """
    sup = raw >= float(thr)
    if open_r and open_r >= 1:
        sup = _open_bool(sup, 2 * int(open_r) + 1)
    if close_k and close_k >= 3:
        sup = _close_bool(sup, close_k)
    return sup


def _fit_veil_gain(bands, support, raw_alpha, w_ref, ring: int = VEIL_RING,
                   gains=VEIL_GAIN_GRID):
    """Pick the gain whose removal leaves NO level step across the boundary.

    The whitening recovers the veil's shape and underreads its amplitude, so one
    scalar is fitted - against the most direct observable there is. Inside the
    veil `J = (I - aW)/(1-a)`; just outside, the art is untouched. The art itself
    is continuous across that line, so the right alpha is the one that makes the
    two ring means agree, averaged over the collection.
    """
    # Both rings stand OFF the support boundary by the same 2-3 ring widths, and
    # that symmetry is load-bearing. A ring flush against the support straddles
    # the veil's real edge - measured, a flush inner ring was only 56 percent
    # veil, which halved the step and so halved the recovered alpha.
    inner = (_erode_bool(support, 4 * int(ring) + 1)
             & ~_erode_bool(support, 6 * int(ring) + 1))
    outer = (_dilate_bool(support, 6 * int(ring) + 1)
             & ~_dilate_bool(support, 4 * int(ring) + 1))
    if not inner.any() or not outer.any():
        return 1.0, float("nan")
    best = (float("inf"), 1.0)
    for g in gains:
        a = float(np.clip(raw_alpha * g, 0.0, ALPHA_MAX))
        errs = []
        for b in bands:
            fixed = (b[inner] - a * w_ref[None, :]) / max(1.0 - a, 1e-3)
            errs.append(abs(float(fixed.mean()) - float(b[outer].mean())))
        mean = float(np.mean(errs))
        if mean < best[0]:
            best = (mean, float(g))
    return best[1], best[0]


def _erode_bool(mask, size: int):
    """Morphological erosion of a boolean mask (PIL MinFilter, no cv2)."""
    from PIL import ImageFilter
    u8 = (np.asarray(mask, dtype=bool) * 255).astype(np.uint8)
    im = Image.fromarray(u8, mode="L").filter(
        ImageFilter.MinFilter(max(int(size) | 1, 3)))
    return np.asarray(im) > 127


def estimate_veil(images, tpl=None, band=BAND, w_ref=W_REF, thr=VEIL_THR,
                  open_r: int = VEIL_OPEN_R, ring: int = VEIL_RING,
                  veil_scale: int = VEIL_SCALE, veil_k: int = VEIL_MEDIAN_K):
    """Recover the mark's FLAT region from a collection -> {alpha, support, raw}.

    `alpha` is a single number, not a map, and deliberately so: the veil IS one
    constant alpha over a solid shape, and a per-pixel map would only carry the
    art residue the median could not cancel INTO the correction. Registration
    uses the template when one is given, exactly as `estimate_matte` does.

    Returns support all-False (and alpha 0.0) when the collection carries no
    solid flat region - a clean corpus must not manufacture a veil.
    """
    band = tuple(tpl["band"]) if tpl is not None else tuple(band)
    bands = []
    for im in images:
        arr = np.asarray(im, dtype=np.float64)
        b = band_of(arr, band)
        if tpl is not None:
            _sc, dy, dx = best_shift(arr, tpl)
            if dy or dx:
                b = np.roll(b, (-dy, -dx), axis=(0, 1))
        bands.append(b)
    if not bands:
        raise ValueError("estimate_veil needs at least one image")

    stack = np.stack([_whiten(b, veil_scale, veil_k) for b in bands])
    raw_map = _box_mean(np.percentile(stack, VEIL_Q, axis=0), VEIL_SMOOTH_WIN)
    support = _veil_support(raw_map, thr, open_r)
    empty = {"alpha": 0.0, "raw": 0.0, "gain": 1.0, "step": float("nan"),
             "support": np.zeros(raw_map.shape, dtype=bool), "band": band}
    if int(support.sum()) < VEIL_MIN_PX:
        return empty
    raw = float(np.median(raw_map[support]))
    w_ref = np.asarray(w_ref, dtype=np.float64)
    gain, step = _fit_veil_gain(bands, support, raw, w_ref, ring)
    return {"alpha": float(np.clip(raw * gain, 0.0, ALPHA_MAX)), "raw": raw,
            "gain": gain, "step": step, "support": support, "band": band}


def _feather_out(sup, reach: int = VEIL_FEATHER):
    """Linear ramp 1.0 -> 0.0 over `reach` px OUTSIDE a boolean support.

    Successive 3x3 dilations, so this stays on PIL like the rest of the module
    (no scipy) and the ramp is in FRAME pixels - the caller resizes first.
    """
    out = sup.astype(np.float64)
    if not reach or reach < 1:
        return out
    cur = sup
    for i in range(1, int(reach) + 1):
        nxt = _dilate_bool(cur, 3)
        out[nxt & ~cur] = 1.0 - i / float(int(reach) + 1)
        cur = nxt
    return out


def veil_alpha_map(veil, shape=None, feather: int = VEIL_FEATHER):
    """The veil as an alpha map, full on its support and FEATHERED outward.

    The ramp is not cosmetic. The support deliberately stops inside the veil's
    true edge, so cutting the correction off at that line manufactures a level
    cliff the original never had - and the old answer to that cliff was to hand a
    ~25px ring of real art to LaMa, which is what deformed a face on the corpus's
    palest frame. Fading the correction out costs at most `alpha` on a strip that
    was already partly veiled, and it costs the filler nothing.
    """
    if not veil or not float(veil.get("alpha", 0.0)):
        return None
    sup = np.asarray(veil["support"], dtype=bool)
    if shape is not None and sup.shape != tuple(shape):
        sup = _resize2d(sup, shape, nearest=True)
    return float(veil["alpha"]) * _feather_out(sup, feather)


def remove_overlay(image, matte, shift=(0, 0), alpha_max=ALPHA_MAX, scale=1.0):
    """Invert the matting equation -> (uint8 RGB, changed-pixel mask).

    `J = (I - a*W) / (1 - a)` reconstructs the partial-alpha ramp EXACTLY
    instead of asking a filler to invent it, which is the whole reason this path
    exists rather than another mask-and-inpaint (R&D section 0).

    Pixels with alpha 0 - everything outside the matte - are copied through
    byte-for-byte, so AG 1.3's outside-region identity holds by construction
    rather than by measurement. A missing matte is a no-op.
    """
    arr = np.asarray(image, dtype=np.float64)
    out = np.clip(np.rint(arr), 0, 255).astype(np.uint8)
    changed = np.zeros(arr.shape[:2], dtype=bool)
    if not matte:
        return out, changed

    band = tuple(matte["band"])
    h = arr.shape[0]
    y0, y1 = int(h * band[0]), int(h * band[1])
    b = arr[y0:y1, :, :]
    alpha = np.asarray(matte["alpha"], dtype=np.float64)
    w = np.asarray(matte["W"], dtype=np.float64)
    if alpha.shape != b.shape[:2]:
        alpha = _resize2d(alpha, b.shape[:2])
        w = np.stack([_resize2d(w[..., c], b.shape[:2])
                      for c in range(w.shape[-1])], axis=-1)
    # The FLAT VEIL rides along here and NOWHERE else: the inversion must fix it
    # (a filler cannot invent 310x240px of face), while the LaMa mask must never
    # see it. Combining by max keeps a stroke that crosses the veil at its own,
    # higher alpha rather than averaging the two.
    veil_map = veil_alpha_map(matte.get("veil"), b.shape[:2])
    if veil_map is not None:
        alpha = np.maximum(alpha, veil_map)
    # The registered SCALE is applied after the veil joins the alpha and before
    # the shift, because both were measured in template coordinates: rescale
    # first, then translate the rescaled mark into place. W rides along
    # per-channel so the inversion still subtracts the right colour.
    if float(scale) != 1.0:
        alpha = scale2d_centered(alpha, scale)
        w = np.stack([scale2d_centered(w[..., c], scale)
                      for c in range(w.shape[-1])], axis=-1)
    dy, dx = (int(shift[0]), int(shift[1])) if shift else (0, 0)
    if dy or dx:
        alpha = np.roll(alpha, (dy, dx), axis=(0, 1))
        w = np.roll(w, (dy, dx), axis=(0, 1))

    a = np.clip(alpha, 0.0, alpha_max)[:, :, None]
    clean = np.clip((b - a * w) / np.maximum(1.0 - a, 1e-3), 0.0, 255.0)
    hit = alpha > 0.0
    band_out = out[y0:y1, :, :]
    band_out[hit] = np.clip(np.rint(clean), 0, 255).astype(np.uint8)[hit]
    out[y0:y1, :, :] = band_out
    changed[y0:y1, :][hit] = True
    return out, changed


def save_matte(path, matte):
    """Atomic write of an estimated {alpha, W} matte."""
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = str(path) + ".tmp.npz"
    veil = matte.get("veil") or {}
    extra = {}
    if veil.get("support") is not None and float(veil.get("alpha", 0.0)):
        extra = {"veil_support": np.asarray(veil["support"], dtype=bool),
                 "veil_alpha": np.asarray([float(veil["alpha"])]),
                 "veil_raw": np.asarray([float(veil.get("raw", 0.0))]),
                 "veil_gain": np.asarray([float(veil.get("gain", 1.0))]),
                 "veil_step": np.asarray([float(veil.get("step", float("nan")))])}
    np.savez_compressed(tmp, alpha=matte["alpha"], W=matte["W"],
                        band=np.asarray(matte["band"]),
                        n=np.asarray([matte.get("n", 0)]),
                        gain=np.asarray([matte.get("gain", 1.0)]),
                        score=np.asarray([matte.get("score", float("nan"))]),
                        **extra)
    os.replace(tmp, path)
    return path


def load_matte(path=MATTE_PATH):
    """Load a cached matte, or None when there is none (removal is a no-op)."""
    if not path or not os.path.isfile(path):
        return None
    with np.load(path) as z:
        veil = None
        if "veil_support" in z:
            veil = {"support": z["veil_support"].astype(bool),
                    "alpha": float(z["veil_alpha"][0]),
                    "raw": float(z["veil_raw"][0]),
                    "gain": float(z["veil_gain"][0]),
                    "step": float(z["veil_step"][0]),
                    "band": tuple(float(v) for v in z["band"])}
        return {"alpha": z["alpha"], "W": z["W"],
                "band": tuple(float(v) for v in z["band"]),
                "n": int(z["n"][0]) if "n" in z else 0,
                "gain": float(z["gain"][0]) if "gain" in z else 1.0,
                "score": float(z["score"][0]) if "score" in z else float("nan"),
                "veil": veil}


def save_template(path, tpl):
    """Atomic write (the pipeline may be reading an older template)."""
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    # np.savez appends ".npz" unless the name already ends in it, so the temp
    # name must too - otherwise os.replace looks for a file that was never made.
    tmp = str(path) + ".tmp.npz"
    np.savez_compressed(tmp, template=tpl["template"],
                        support=tpl["support"], band=np.asarray(tpl["band"]),
                        n=np.asarray([tpl.get("n", 0)]))
    os.replace(tmp, path)
    return path


def load_template(path=TEMPLATE_PATH):
    """Load a cached template, or None when there is none (score then 0.0)."""
    if not path or not os.path.isfile(path):
        return None
    with np.load(path) as z:
        return {"template": z["template"], "support": z["support"].astype(bool),
                "band": tuple(float(v) for v in z["band"]),
                "n": int(z["n"][0]) if "n" in z else 0}


def load_image(path):
    """RGB float array for a path - the one place the detector touches disk."""
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.float64)
