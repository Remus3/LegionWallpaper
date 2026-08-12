"""Centre-overlay REMOVAL - recover (W, alpha) from a collection, then invert.

`docs/research/WATERMARK_REMOVAL_RND.md` section 0 states the problem: the mark
is SEMI-TRANSPARENT, `I = (1-a)J + aW`, and the halo is an ALPHA-ESTIMATION
problem, not an inpainting one. A binary mask either keeps the 1-2px partial-
alpha ramp (halo survives) or eats it (a filler must invent it). Section 3 says
the only artifact-free fix is to recover a CONTINUOUS alpha plus W and invert
the equation, which reconstructs the ramp exactly - no halo, no hallucination.

That paper method needs a collection carrying the same mark. The centre-overlay
detector already built one: 19 verified frames plus a template that registers
them. So removal here is a per-pixel solve, NOT a generative fill:

    for each pixel, across the collection:  I_i - J_i = a*W - a*J_i
    which is linear in (a*W, a) once J_i - the clean background - is estimated

J_i starts as a median-filtered copy (the strokes are thin, so a 15px median
erases them) and is then RE-ESTIMATED from the current (a, W) each iteration.
That alternation is what fixes the recorded failure of method 4 in the R&D
table, "alpha underestimated (median bg contaminated by dense text)", and W is
SOLVED FOR rather than pinned at 255, per section 3 item 1.

The tests below plant a known (W, alpha) over synthetic art, so the truth is
available and the assertions are about recovery error, not about looks.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))
import lw_clean_overlay as ov  # noqa: E402

H, W_PX = 240, 400
W_TRUE = np.array([250.0, 245.0, 240.0])       # the mark's colour, near-white


def _art(seed):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W_PX]
    base = 96 + 55 * np.sin(xx / 21.0 + seed) + 38 * np.cos(yy / 15.0 - seed)
    base = base + rng.normal(0, 10, size=(H, W_PX))
    rgb = np.stack([base, base * 0.93, base * 1.07], axis=2)
    return np.clip(rgb, 5, 250)


def _alpha_truth():
    """A glyph-ish matte with SOFT edges - the whole point of the exercise.

    Geometry mirrors the real overlay: a COMPACT band of marks (logo, glyph row,
    underline) with clear art above and below it, sitting near the middle of the
    detector band. That matters for more than realism - a seed that interpolates
    the background has to bridge the mark, and how far it must bridge depends on
    this shape.
    """
    a = np.zeros((H, W_PX), dtype=np.float64)
    y0 = int(H * 0.72)
    a[y0:y0 + 3, int(W_PX * 0.22):int(W_PX * 0.78)] = 0.75
    for i in range(14):
        a[y0 - 20 + i, int(W_PX * 0.46) + i:int(W_PX * 0.46) + i + 3] = 0.7
    for x in range(int(W_PX * 0.24), int(W_PX * 0.76), 8):
        a[y0 - 10:y0 - 3, x:x + 3] = 0.65
    # soften the edges so partial-alpha pixels exist, like a real glyph
    k = np.array([0.25, 0.5, 0.25])
    a = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 0, a)
    a = np.apply_along_axis(lambda m: np.convolve(m, k, mode="same"), 1, a)
    return a


def _composite(seed):
    """One observed frame: art with the mark alpha-composited over it."""
    art = _art(seed)
    a = _alpha_truth()[:, :, None]
    return np.clip(art * (1 - a) + W_TRUE[None, None, :] * a, 0, 255)


@pytest.fixture(scope="module")
def collection():
    return [_composite(s) for s in range(40, 58)]


@pytest.fixture(scope="module")
def tpl(collection):
    return ov.estimate_template(collection)


@pytest.fixture(scope="module")
def matte(collection, tpl):
    return ov.estimate_matte(collection, tpl)


def _band(arr):
    return ov.band_of(arr, ov.BAND)


# ===========================================================================
# 1. recovery of (alpha, W)
# ===========================================================================
def test_estimate_matte_recovers_alpha_where_the_mark_is(matte):
    truth = _band(_alpha_truth())
    got = matte["alpha"]
    assert got.shape == truth.shape
    core = truth > 0.5
    assert core.sum() > 50
    err = np.abs(got[core] - truth[core])
    assert float(err.mean()) < 0.10


def test_estimate_matte_barely_touches_unmarked_pixels(matte):
    """Art must not be dragged into the matte.

    Not a claim of exactly zero: the median-ratio estimator does leak a little
    onto unmarked pixels - measured on this fixture, 56 of 26416 (0.2 percent)
    pick up an alpha at all, the largest 0.076, i.e. a ~7 percent blend on a
    handful of pixels. The contract is that the leak stays rare AND small; if
    the matte ever starts bleeding onto the painting, both bounds move at once.
    """
    truth = _band(_alpha_truth())
    off = truth <= 0.01
    leaked = matte["alpha"][off]
    assert float(leaked.max()) < 0.10
    assert float((leaked > 0.05).mean()) < 0.005


def test_matte_holds_w_constant_and_fits_a_gain_instead(matte):
    """W is a fixed reference colour, and the amplitude is a FITTED gain.

    R&D section 3 item 1 says do not pin W at 255 but estimate it. Estimating
    it PER PIXEL was implemented and measured to diverge on the real corpus:
    alpha and W trade off (only their product is identifiable without a prior),
    so three rounds of re-solving W drove the mean post-removal detector score
    0.149 -> 0.174 -> 0.254 while W drifted from ~154 to ~87. Until the
    matting-Laplacian priors exist to pin alpha independently, the stable half
    of the model is one reference colour plus a gain fitted against the
    detector - which is what this asserts, so nobody re-derives the divergence.
    """
    got = matte["W"]
    assert got.shape[-1] == 3
    for ch in range(3):
        assert abs(float(np.median(got[..., ch])) - ov.W_REF[ch]) < 1e-9
    assert matte["gain"] in ov.GAIN_GRID
    # the fixture's true colour is near the reference, which is why removal
    # works at all - a wildly different mark colour would need a new W_REF.
    assert abs(float(np.median(W_TRUE)) - ov.W_REF[0]) < 15.0


# ===========================================================================
# 2. removal by inverting the matting equation
# ===========================================================================
def test_remove_overlay_restores_the_underlying_art(matte):
    """The reconstruction must be FAITHFUL, not plausible."""
    seed = 300
    observed = _composite(seed)
    truth = _art(seed)
    cleaned, changed = ov.remove_overlay(observed, matte)
    a = _band(_alpha_truth())
    band_c = _band(cleaned.astype(np.float64))
    band_t = _band(truth)
    marked = a > 0.05
    before = np.abs(_band(observed) - band_t)[marked].mean()
    after = np.abs(band_c - band_t)[marked].mean()
    assert after < before / 3.0
    assert after < 12.0
    assert changed.sum() > 0


def test_remove_overlay_reconstructs_the_soft_edge_not_just_the_core(matte):
    """The halo lives in the 0 < a < 0.5 ramp - that is what must improve."""
    seed = 301
    observed = _composite(seed)
    truth = _art(seed)
    cleaned, _ = ov.remove_overlay(observed, matte)
    a = _band(_alpha_truth())
    ramp = (a > 0.05) & (a < 0.5)
    assert ramp.sum() > 50
    before = np.abs(_band(observed) - _band(truth))[ramp].mean()
    after = np.abs(_band(cleaned.astype(np.float64)) - _band(truth))[ramp].mean()
    assert after < before / 2.0


def test_remove_overlay_never_touches_a_pixel_outside_the_matte(matte):
    """AG 1.3: outside the edited region the output is byte-identical."""
    observed = _composite(302)
    cleaned, changed = ov.remove_overlay(observed, matte)
    obs_u8 = np.clip(np.rint(observed), 0, 255).astype(np.uint8)
    outside = ~changed
    assert np.array_equal(cleaned[outside], obs_u8[outside])


def test_remove_overlay_collapses_the_detector_score(matte, tpl):
    """The detector is its own verifier: after removal it must stop firing."""
    observed = _composite(303)
    before = ov.overlay_score(observed, tpl)
    cleaned, _ = ov.remove_overlay(observed, matte)
    after = ov.overlay_score(cleaned.astype(np.float64), tpl)
    assert before > 0.25
    assert after < before / 2.0


def test_remove_overlay_is_a_noop_without_a_matte():
    observed = _composite(304)
    cleaned, changed = ov.remove_overlay(observed, None)
    assert changed.sum() == 0
    assert np.array_equal(
        cleaned, np.clip(np.rint(observed), 0, 255).astype(np.uint8))


def test_remove_overlay_survives_an_opaque_alpha(matte):
    """a -> 1 makes the inversion singular; it must clamp, not divide by zero."""
    hot = {"alpha": np.ones_like(matte["alpha"]),
           "W": matte["W"], "band": matte["band"], "n": matte["n"]}
    cleaned, _ = ov.remove_overlay(_composite(305), hot)
    assert np.isfinite(cleaned).all()
    assert cleaned.dtype == np.uint8


# ===========================================================================
# 3. round-trip
# ===========================================================================
def test_matte_round_trips_through_disk(tmp_path, matte):
    p = os.path.join(str(tmp_path), "m.npz")
    ov.save_matte(p, matte)
    back = ov.load_matte(p)
    assert np.allclose(back["alpha"], matte["alpha"])
    assert np.allclose(back["W"], matte["W"])
    assert back["band"] == matte["band"]
    # the fitted gain has to survive the round trip: it is the provenance of
    # every pixel this matte changes, and it lands in the slug's manifest.
    assert back["gain"] == matte["gain"]


def test_load_matte_missing_file_returns_none():
    assert ov.load_matte(os.path.join("C:", os.sep, "no", "such", "m.npz")) is None
