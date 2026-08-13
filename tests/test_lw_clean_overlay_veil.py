"""The centre overlay's FLAT VEIL - the half the high-pass matte cannot see.

LEDGER 95 pinned why the DA logo survives the inpaint lane on smooth art: the
template's support is the top 2 percent of the median HIGH-PASS, and a flat
region has no high-pass, so `estimate_matte` returns alpha exactly 0.0 inside the
logo. The strokes get removed, the veil stays.

This is the successor estimator, and it is a different measurement, not a looser
threshold:

    whiten_i = (gray_i - bg_i) / (255 - bg_i)      bg over a window WIDER than
                                                   the veil, so it reads the art
                                                   OUTSIDE rather than the veil
    veil     = median over the registered collection      (art cancels)

That recovers the SHAPE with the right sign but damped - measured on the corpus,
the logo interior reads 0.060 against ~0.14 from its own boundary step - so the
amplitude is CALIBRATED against that step: pick the gain whose removal leaves no
level difference across the veil's boundary. Same shape of decision as the stroke
matte's `_fit_gain`, against a different, more direct observable.

The veil is deliberately kept SEPARATE from the stroke alpha in the matte: the
inversion must apply to both, but the LaMa mask must cover only the strokes -
handing a filler 310x240px of face is worse than the veil it would replace.

Pure numpy + PIL (the coarse-median trick is also what keeps this CI-safe:
cv2.medianBlur asserts k < 16 at that width).
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

H, W_PX = 240, 400
BAND = (0.0, 1.0)
# The estimator only works when its background window is WIDER than the veil, so
# the fixture keeps that ratio: an 80px-wide veil read against a ~102px window
# (a median of 51 on a half-scale copy). At corpus scale that is 310px vs ~408px.
VEIL_BOX = (np.s_[90:150], np.s_[160:240])
ALPHA_TRUE = 0.15
SMALL = {"veil_scale": 2, "veil_k": 51}


def _art(seed):
    """UNRELATED artworks - not one picture shifted.

    This matters for more than realism. The calibration reads a level difference
    across the veil's boundary, and any given painting has its own gradient
    there; only a collection of unrelated frames averages that away. A fixture
    built from one sinusoid at shifted phases keeps the bias correlated across
    frames and no boundary method can work on it - which is exactly the trap this
    fixture was rewritten to avoid.
    """
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W_PX]
    level = rng.uniform(60, 170)
    base = (level
            + rng.uniform(-35, 35) * np.sin(xx / rng.uniform(15, 60)
                                            + rng.uniform(0, 6.3))
            + rng.uniform(-35, 35) * np.cos(yy / rng.uniform(12, 50)
                                            + rng.uniform(0, 6.3)))
    base = base + rng.normal(0, 3, size=(H, W_PX))
    return np.clip(np.stack([base, base * 0.96, base * 1.04], axis=2), 5, 245)


def _marked(seed, alpha=ALPHA_TRUE):
    art = _art(seed)
    out = art.copy()
    sl = (VEIL_BOX[0], VEIL_BOX[1], slice(None))
    out[sl] = (1 - alpha) * art[sl] + alpha * np.asarray(ov.W_REF)
    return art, out


def _frames(n=16):
    return [_marked(i)[1] for i in range(n)]


def test_veil_estimator_finds_the_flat_region_the_high_pass_misses():
    """The planted square is recovered as a FILLED support, art is not."""
    veil = ov.estimate_veil(_frames(), band=BAND, **SMALL)
    sup = veil["support"]
    planted = np.zeros((H, W_PX), dtype=bool)
    planted[VEIL_BOX] = True
    inside = float(sup[planted].mean())
    outside = float(sup[~planted].mean())
    # Not 1.0 by design: the support stops ~10px inside the veil's true edge
    # rather than risk darkening real art, and that rim is the strip the stroke
    # mask hands to LaMa anyway.
    assert inside > 0.65, f"the veil must be filled, got {inside:.2f}"
    assert outside < 0.05, f"art must not be veil, got {outside:.2f}"


def test_veil_alpha_is_calibrated_to_the_boundary_step():
    """The recovered alpha must match the truth, not just its shape.

    The raw whitening reads LOW (the background window still partly follows the
    veil). The gain is fitted so that removal leaves no step across the veil's own
    boundary, which is the one observable that pins the amplitude.
    """
    veil = ov.estimate_veil(_frames(), band=BAND, **SMALL)
    assert abs(veil["alpha"] - ALPHA_TRUE) < 0.04, veil["alpha"]
    assert veil["raw"] < veil["alpha"], "the raw whitening is expected to underread"


def test_a_gain_on_the_grid_ceiling_is_reported_as_a_boundary_solution():
    """A fit that stops where the search stops is not a measurement.

    The 2026-08-11 matte recorded gain 5.0 against a 0.5..5.0 grid and the value
    was written up as an interior optimum. Measured 2026-08-12 over 31 flagged
    frames, the objective actually minimises at gain 3.75 (alpha 0.0999) and 5.0
    is already worse - so the shipped amplitude is 33 percent above its own
    estimator's optimum, and nothing in the pipeline said so. It does now.
    """
    bands = [np.asarray(f, dtype=np.float64) for f in _frames(4)]
    sup = np.zeros((H, W_PX), dtype=bool)
    sup[VEIL_BOX] = True
    short = (0.5, 1.0)          # a grid far too short for a 0.15 veil
    with pytest.warns(RuntimeWarning, match="grid ceiling"):
        gain, _ = ov._fit_veil_gain(bands, sup, 0.02, np.asarray(ov.W_REF),
                                    gains=short)
    assert gain == short[-1]
    # and the shipped grid must reach well past where the corpus optimum sits
    assert ov.VEIL_GAIN_GRID[-1] >= 10.0, ov.VEIL_GAIN_GRID[-1]


def test_removal_with_the_veil_erases_the_step():
    """End to end: the corrected frame has no level difference at the boundary."""
    veil = ov.estimate_veil(_frames(), band=BAND, **SMALL)
    art, marked = _marked(3)
    matte = {"alpha": np.zeros((H, W_PX)), "W": ov._w_map(np.zeros((H, W_PX)),
                                                         np.asarray(ov.W_REF)),
             "band": BAND, "veil": veil}
    out, changed = ov.remove_overlay(marked, matte)
    assert int(changed.sum()) > 0, "the veil must be removed even with no strokes"
    err_before = np.abs(marked - art)[VEIL_BOX].mean()
    err_after = np.abs(out.astype(float) - art)[VEIL_BOX].mean()
    assert err_after < err_before / 3.0, (err_before, err_after)


def test_the_veil_correction_does_not_cliff_at_its_own_support_edge():
    """The support edge is NOT an edge of the original, so removal must not make one.

    Measured on the corpus 2026-08-12: across six frames the ORIGINAL carries no
    level step at the recorded support boundary (|step| <= 0.9 levels, 6 of 6) -
    the support stops inside the veil, so both sides of that line are veiled
    alike. A hard-edged correction therefore MANUFACTURES a 12.7-27.4 level cliff
    that was never in the art, which is what the old ring handed to LaMa. The
    ramp is the fix at the cause: correct the interior in full, then fade out.
    """
    veil = ov.estimate_veil(_frames(), band=BAND, **SMALL)
    art, marked = _marked(3)
    matte = {"alpha": np.zeros((H, W_PX)), "W": ov._w_map(np.zeros((H, W_PX)),
                                                         np.asarray(ov.W_REF)),
             "band": BAND, "veil": veil}
    sup = veil["support"]
    rim = ov._dilate_bool(sup, 5) & ~ov._erode_bool(sup, 5)
    deep = ov._erode_bool(sup, 11)

    def rim_jump(feather):
        amap = ov.veil_alpha_map(veil, (H, W_PX), feather=feather)
        a = np.clip(amap, 0.0, ov.ALPHA_MAX)[:, :, None]
        w = ov._w_map(np.zeros((H, W_PX)), np.asarray(ov.W_REF))
        fixed = np.clip((marked - a * w) / np.maximum(1.0 - a, 1e-3), 0, 255)
        gy, gx = np.gradient(fixed.mean(axis=2) - np.asarray(marked).mean(axis=2))
        g = np.hypot(gy, gx)
        return float(np.percentile(g[rim], 99)), float(np.percentile(g[deep], 99))

    hard, _ = rim_jump(0)
    soft, art_only = rim_jump(ov.VEIL_FEATHER)
    # `deep` is the control: inside the support the correction is uniform, so its
    # gradient is the ART's, not the correction's. The rim must approach that.
    assert hard > 6 * art_only, f"fixture is not exercising the cliff ({hard:.1f})"
    assert soft < hard / 3.0, f"the ramp barely helped: {hard:.1f} -> {soft:.1f}"
    assert soft < 8.0, f"the correction still cliffs {soft:.1f} levels"


def test_the_veil_is_never_handed_to_the_inpainter_at_all():
    """Interior AND boundary are the inversion's job - the filler gets neither.

    The ring existed only to blend the cliff the hard-edged correction made. With
    the correction feathered there is nothing to blend, and the ring was never
    free: at corpus scale it is ~25px wide, it sits mid-frame wherever the logo
    sits, and on pale flat art (mecha-ahri) it crossed the nose and upper lip -
    LaMa deformed both.
    """
    veil = ov.estimate_veil(_frames(), band=BAND, **SMALL)
    matte = {"alpha": np.zeros((H, W_PX)), "W": ov._w_map(np.zeros((H, W_PX)),
                                                         np.asarray(ov.W_REF)),
             "band": BAND, "veil": veil}
    mask, region = IO.overlay_mask((H, W_PX), matte)
    # No strokes and no ring means there is nothing left to inpaint at all.
    assert region is None, "a veil-only matte must produce no inpaint region"
    assert not (mask > 127).any(), "the veil must never reach the filler"


def test_a_matte_without_a_veil_still_removes_exactly_as_before():
    """Back-compat: every cached matte predates this field."""
    art, marked = _marked(5)
    a = np.zeros((H, W_PX))
    a[100:104, 150:250] = 0.5
    matte = {"alpha": a, "W": ov._w_map(a, np.asarray(ov.W_REF)), "band": BAND}
    out, changed = ov.remove_overlay(marked, matte)
    assert int(changed.sum()) == int((a > 0).sum())


def test_veil_round_trips_through_disk(tmp_path):
    veil = ov.estimate_veil(_frames(), band=BAND, **SMALL)
    a = np.zeros((H, W_PX))
    matte = {"alpha": a, "W": ov._w_map(a, np.asarray(ov.W_REF)), "band": BAND,
             "n": 16, "gain": 2.0, "score": 0.11, "veil": veil}
    p = ov.save_matte(str(tmp_path / "m.npz"), matte)
    back = ov.load_matte(p)
    assert back["veil"] is not None
    assert abs(back["veil"]["alpha"] - veil["alpha"]) < 1e-9
    assert np.array_equal(back["veil"]["support"], veil["support"])


def test_no_veil_when_the_frames_carry_none():
    """A clean collection must not invent a veil out of art."""
    veil = ov.estimate_veil([_art(i) for i in range(16)], band=BAND, **SMALL)
    assert float(veil["support"].mean()) < 0.05
