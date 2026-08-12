"""Centre-overlay -> IOPaint mask: the cross-image matte SEEDS the LaMa mask.

Why this file exists. LEDGER 94 measured the algebraic removal
(`lw_clean_overlay.remove_overlay`) down to a detector score of 0.112 and then
CAPPED: at 1:1 a dark ghost of the credit line survives, because the mark is a
white fill PLUS a dark outline and no single achromatic W inverts both. LEDGER 29
already tried the textbook next step (Levin matting-Laplacian + IRLS,
`lw_clean_dekel.py`) and hit the same wall. The shipped answer for that family of
marks is LEDGER 30: masked LaMa over a COMPLETE mask - one that covers the dark
OUTLINE as well as the bright FILL.

So the residual is an INPAINTING problem, and the matte is the best mask seed
available: it is a cross-image estimate of exactly which pixels carry the mark,
with the art cancelled out. These tests pin the seam between the two - the matte
becomes a binary mask plus an ROI, registered to the frame the detector matched.

Pure numpy + PIL only (no cv2, no torch, no GPU): the mask builder is the part
that has to stay CI-safe.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))
import lw_clean_iopaint as IO  # noqa: E402
import lw_clean_overlay as ov  # noqa: E402

FRAME = (1440, 2560)
BAND = (0.55, 0.85)


def _matte(band=BAND, frame=FRAME, alpha=0.5):
    """A matte with one compact glyph block, in band coordinates."""
    h, w = frame
    y0, y1 = int(h * band[0]), int(h * band[1])
    a = np.zeros((y1 - y0, w), dtype=np.float64)
    a[100:130, 1100:1500] = alpha
    return {"alpha": a, "W": ov._w_map(a, np.asarray(ov.W_REF)),
            "band": tuple(band), "n": 19, "gain": 2.0, "score": 0.11}


def test_mask_covers_the_matte_and_its_ramp():
    """Every alpha pixel is masked, and the mask GROWS - it must eat the ramp.

    The glyph15 lesson from LEDGER 30: a mask tight to the bright fill leaves a
    dark edge ghost, so the dilation is load-bearing, not cosmetic.
    """
    m = _matte()
    mask, region = IO.overlay_mask(FRAME, m)
    assert mask.shape == FRAME
    h = FRAME[0]
    y0 = int(h * BAND[0])
    seed = np.zeros(FRAME, dtype=bool)
    seed[y0 + 100:y0 + 130, 1100:1500] = True
    assert np.all(mask[seed] > 127), "the matte's own pixels must be masked"
    assert int((mask > 127).sum()) > int(seed.sum()), "the ramp must be swallowed"
    x0, ry0, x1, ry1 = region
    assert x0 < 1100 and x1 > 1500 and ry0 < y0 + 100 and ry1 > y0 + 130


def test_region_is_the_mark_bbox_not_the_whole_band():
    """The ROI follows the mark. A band-wide ROI would hand LaMa 2560x432 of art."""
    _mask, region = IO.overlay_mask(FRAME, _matte())
    x0, y0, x1, y1 = region
    assert (x1 - x0) < 700 and (y1 - y0) < 250
    assert 0 <= x0 < x1 <= FRAME[1] and 0 <= y0 < y1 <= FRAME[0]


def test_speckle_below_the_stroke_size_is_dropped():
    """An isolated pixel between two glyphs is estimator noise, not a mark.

    Measured on the real matte: thresholding alone keeps ~1300 stray pixels
    scattered over the whole band, which would drag the ROI from 460x215 out to
    1967x432 and mask art nowhere near the overlay.
    """
    m = _matte()
    h = FRAME[0]
    y0 = int(h * BAND[0])
    m["alpha"][5, 40] = 0.9        # a lone speck far from the glyph block
    _mask, region = IO.overlay_mask(FRAME, m)
    assert region[0] > 200, "one speck must not stretch the ROI to the frame edge"
    mask, _r = IO.overlay_mask(FRAME, m)
    assert mask[y0 + 5, 40] == 0


def test_alpha_below_the_threshold_is_not_masked():
    """The threshold is a knob with a measured default, not a hard-coded 0."""
    faint = _matte(alpha=0.03)
    mask, region = IO.overlay_mask(FRAME, faint)
    assert int((mask > 127).sum()) == 0 and region is None
    mask2, region2 = IO.overlay_mask(FRAME, faint, alpha_thr=0.01)
    assert int((mask2 > 127).sum()) > 0 and region2 is not None


def test_mask_follows_the_registration_shift():
    """The mark moves between frames; the mask has to move with it.

    Same convention as `remove_overlay`: the shift comes from `best_shift` and is
    applied by rolling the matte, so mask and algebraic removal cannot disagree
    about where the mark is.
    """
    m = _matte()
    _mask, base = IO.overlay_mask(FRAME, m)
    _mask2, moved = IO.overlay_mask(FRAME, m, shift=(17, -23))
    assert moved[1] - base[1] == 17
    assert moved[0] - base[0] == -23


def test_matte_from_a_different_frame_size_is_resized():
    """A 1920x1080 frame must reuse a matte estimated at 2560x1440."""
    small = (1080, 1920)
    mask, region = IO.overlay_mask(small, _matte())
    assert mask.shape == small
    assert region is not None and region[2] <= 1920


def test_no_matte_is_a_no_op():
    mask, region = IO.overlay_mask(FRAME, None)
    assert region is None and int((mask > 127).sum()) == 0


def test_roi_mask_matches_the_region():
    """`overlay_roi_mask` is what the cleaner feeds LaMa - ROI-shaped, 0/255."""
    mask, region = IO.overlay_mask(FRAME, _matte())
    roi_mask = IO.overlay_roi_mask(mask, region)
    x0, y0, x1, y1 = region
    assert roi_mask.shape == (y1 - y0, x1 - x0)
    assert set(np.unique(roi_mask)).issubset({0, 255})
    assert int((roi_mask > 127).sum()) == int((mask > 127).sum())


def test_pre_removal_runs_before_the_mask_is_applied():
    """The lane is ALGEBRAIC-then-INPAINT, and the order is the whole design.

    `remove_overlay` reconstructs the partial-alpha ramp exactly over the big flat
    logo (300x240px over a face on the real corpus - far too much area to hand a
    filler), so LaMa only ever sees the thin residual the matting equation could
    not invert. Inpainting first would throw that away.
    """
    rng = np.random.default_rng(7)
    art = rng.uniform(40, 200, size=FRAME + (3,))
    m = _matte(alpha=0.4)
    h = FRAME[0]
    y0 = int(h * BAND[0])
    band = art[y0:int(h * BAND[1])]
    a = m["alpha"][:, :, None]
    marked = art.copy()
    marked[y0:int(h * BAND[1])] = (1 - a) * band + a * np.asarray(ov.W_REF)

    pre, changed = ov.remove_overlay(marked, m)
    assert int(changed.sum()) > 0
    inside = np.zeros(FRAME, dtype=bool)
    inside[y0 + 100:y0 + 130, 1100:1500] = True
    err_before = np.abs(marked - art)[inside].mean()
    err_after = np.abs(pre.astype(float) - art)[inside].mean()
    assert err_after < err_before / 4.0, "the pre-pass must do the heavy lifting"


def test_region_pad_is_clamped_to_the_frame():
    """A mark near the frame edge must not produce an ROI outside it."""
    m = _matte()
    m["alpha"][:] = 0.0
    m["alpha"][0:6, 0:6] = 0.5
    m["alpha"][0:6, 2554:2560] = 0.5
    mask, region = IO.overlay_mask(FRAME, m, pad=200)
    x0, y0, x1, y1 = region
    assert x0 == 0 and x1 == 2560 and y0 >= 0 and y1 <= 1440
    assert mask.shape == FRAME


def test_isolated_blobs_are_dropped_but_strokes_survive():
    """A 3x3 estimator blob is not a glyph; a 4px stroke is.

    Measured on the wide matte: the opening leaves ~8 round specks scattered over
    the band, and each one is a hole LaMa would repaint in art nowhere near the
    mark - and they stretched the ROI from the mark's own 550x290 to 1006x445.
    Erosion cannot separate them (a real stroke is only 4-6px wide either), so the
    filter is local DENSITY: a stroke has hundreds of neighbours in a 31x31
    window, a speck has nine.
    """
    m = _matte()
    m["alpha"][:] = 0.0
    m["alpha"][100:104, 1100:1500] = 0.5      # a stroke
    m["alpha"][300:303, 300:303] = 0.9        # a speck, far away
    mask, region = IO.overlay_mask(FRAME, m)
    h = FRAME[0]
    y0 = int(h * BAND[0])
    assert mask[y0 + 301, 301] == 0
    assert mask[y0 + 102, 1300] > 127
    assert region[0] > 900, "the speck must not stretch the ROI"


def _roi_with_residual(shape=(120, 300)):
    """Flat art plus a dark residual stroke - what the pre-pass leaves behind."""
    rng = np.random.default_rng(3)
    roi = rng.normal(140, 2.0, size=shape + (3,))
    roi[40:44, 60:240] -= 45.0          # residual dark glyph line (in the gate)
    roi[10:14, 10:40] -= 45.0           # a real art edge far from any mark
    return np.clip(roi, 0, 255)


def test_completion_closes_the_gaps_the_matte_missed():
    """The matte is a SHAPE estimate; the frame in hand is the ground truth.

    Measured on mecha-ahri: thresholding the matte alone leaves the credit line
    patchy - glyph cores masked, the strokes between them not - so the ghost only
    partly clears. The diff term reads THIS frame's residual and fills that in.
    Lowering the threshold instead was measured to be the wrong lever: 0.08 ->
    0.03 stretches the ROI from 464x215 to 1229x624 by dragging in speckle.
    """
    roi = _roi_with_residual()
    seed = np.zeros(roi.shape[:2], dtype=np.uint8)
    seed[40:44, 60:100] = 255           # two glyph cores...
    seed[40:44, 110:240] = 255          # ...with the stroke between them missing
    out = IO.complete_overlay_mask(roi, seed)
    assert np.all(out[seed > 127] > 127), "completion must keep the seed"
    assert int((out > 127).sum()) > int((seed > 127).sum())
    assert out[41, 105] > 127, "the gap inside the glyph row must be bridged"


def test_completion_stays_inside_the_gate():
    """Art edges away from the mark are NOT the mark - LaMa must never see them."""
    roi = _roi_with_residual()
    seed = np.zeros(roi.shape[:2], dtype=np.uint8)
    seed[40:44, 60:240] = 255
    out = IO.complete_overlay_mask(roi, seed)
    assert out[12, 25] == 0, "an art edge outside the gate must stay unmasked"
    assert int(out[:30].sum()) == 0


def test_completion_reaches_along_the_text_line_for_bright_marks():
    """The credit line runs off the end of the seed, and only sideways.

    Measured on mecha-ahri: the matte's seed stops ~40px short of the leading
    "(C)", which therefore survived the inpaint while every glyph the seed did
    reach cleared. A round gate cannot reach that far without also reaching the
    lips directly below the line, so the extension is HORIZONTAL and accepts only
    BRIGHT residual - the mark's fill is white, while the art edge it is most
    likely to bump into (a lip line) is dark.
    """
    rng = np.random.default_rng(11)
    roi = np.clip(rng.normal(120, 2.0, size=(80, 300, 3)), 0, 255)
    roi[30:36, 70:95] += 60.0        # a bright glyph BEYOND the seed, same row
    roi[55:60, 70:95] -= 60.0        # a dark art edge below, equally far out
    seed = np.zeros(roi.shape[:2], dtype=np.uint8)
    seed[30:36, 100:240] = 255
    out = IO.complete_overlay_mask(roi, seed)
    assert out[33, 80] > 127, "the bright glyph along the line must be reached"
    assert out[57, 80] == 0, "a dark edge off the line must NOT be"


def test_completion_gate_width_is_a_knob():
    roi = _roi_with_residual()
    seed = np.zeros(roi.shape[:2], dtype=np.uint8)
    seed[40:44, 60:240] = 255
    narrow = IO.complete_overlay_mask(roi, seed, gate_k=3)
    wide = IO.complete_overlay_mask(roi, seed, gate_k=101)
    assert int((narrow > 127).sum()) < int((wide > 127).sum())


@pytest.mark.parametrize("thr", [0.02, 0.08, 0.2])
def test_threshold_monotonically_shrinks_the_mask(thr):
    """Higher threshold -> never more mask. Guards a sign slip in the compare."""
    m = _matte(alpha=0.5)
    m["alpha"][100:130, 1100:1300] = 0.1
    mask, _r = IO.overlay_mask(FRAME, m, alpha_thr=thr)
    loose, _r2 = IO.overlay_mask(FRAME, m, alpha_thr=0.005)
    assert int((mask > 127).sum()) <= int((loose > 127).sum())
