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

TEMPLATE_PATH = os.path.join(
    r"C:\LegionWallpaper", "ops", "runtime", "clean", "overlay_template.npz")


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
    if not tpl:
        return 0.0
    b = band_of(highpass(image), tpl["band"])
    t = np.asarray(tpl["template"], dtype=np.float64)
    s = np.asarray(tpl["support"], dtype=bool)
    if t.shape != b.shape:
        t = _resize2d(t, b.shape)
        s = _resize2d(s, b.shape, nearest=True)
    m = s.astype(np.float64)
    n = float(m.sum())
    if n <= 0:
        return 0.0
    x = np.clip(b, -CLIP_LEVELS, CLIP_LEVELS)
    t = np.clip(t, -CLIP_LEVELS, CLIP_LEVELS)
    if float(np.abs(x).max()) <= 1e-9:
        return 0.0

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
    win = ncc[np.ix_(np.abs(dy) <= max(1, int(fy * frame_h)),
                     np.abs(dx) <= max(1, int(fx * w)))]
    if win.size == 0:
        return 0.0
    return float(win.max())


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
