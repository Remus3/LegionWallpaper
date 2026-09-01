"""Tests for tools/lw_overlay_from_pair.py - matte extraction from a hand-clean.

CI constraint (read before editing imports): these run on system python 3.14 and
CI 3.12 with ONLY PIL + numpy + stdlib available. No torch, no cv2, no GPU. The
module under test is pure numpy by design, so everything here is exercised on
synthetic composites with a KNOWN alpha and a KNOWN mark colour - which is the
only way to assert the estimator is correct rather than merely plausible.

Written test-first per CLAUDE.md TDD.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import lw_overlay_from_pair as OP  # noqa: E402


def _synth(h=64, w=96, seed=0):
    """A deterministic 'artwork' plus a known alpha matte and mark colour."""
    rng = np.random.default_rng(seed)
    orig = rng.integers(20, 230, size=(h, w, 3)).astype(np.float64)
    alpha = np.zeros((h, w), dtype=np.float64)
    alpha[10:30, 12:60] = 0.35          # solid glyph core
    alpha[34:40, 12:60] = 0.12          # a fainter second line
    # a soft horizontal ramp, the antialiased edge case
    alpha[44:50, 12:60] = np.linspace(0.0, 0.4, 48)[None, :]
    mark = 250.0
    obs = orig * (1.0 - alpha[..., None]) + mark * alpha[..., None]
    return orig, alpha, mark, obs


def test_composite_roundtrips_the_forward_model():
    """The helper must implement exactly the model the estimator inverts."""
    orig, alpha, mark, obs = _synth()
    again = OP.composite(orig, alpha, mark)
    assert np.allclose(again, obs)


def test_alpha_from_pair_recovers_a_known_matte():
    """before + after + known mark colour -> the alpha that produced them."""
    orig, alpha, mark, obs = _synth()
    got = OP.alpha_from_pair(obs, orig, mark)
    assert got.shape == alpha.shape
    # every region matters, including the faint line and the ramp
    assert np.abs(got - alpha).max() < 0.02
    # and it must not invent alpha where there was none
    assert got[alpha == 0].max() < 0.02


def test_alpha_is_clamped_and_finite_when_art_meets_the_mark_colour():
    """orig == mark makes the closed form singular; it must not emit NaN/inf.

    A real frame has near-white pixels under a white mark, so this is the
    ordinary case, not a contrived one.
    """
    orig = np.full((8, 8, 3), 250.0)
    alpha = np.full((8, 8), 0.5)
    obs = OP.composite(orig, alpha, 250.0)
    got = OP.alpha_from_pair(obs, orig, 250.0)
    assert np.isfinite(got).all()
    assert ((got >= 0.0) & (got <= 1.0)).all()


def test_fit_mark_colour_recovers_the_mark():
    """The mark colour is measurable from the pair, not an assumption."""
    orig, alpha, mark, obs = _synth()
    got = OP.fit_mark_colour(obs, orig)
    assert abs(got - mark) <= 2.0


def test_fit_mark_colour_ignores_untouched_pixels():
    """Pixels the mark never touched carry no information and must not bias it."""
    orig, alpha, mark, obs = _synth()
    # widen the frame with a large untouched margin
    pad = np.pad(orig, ((40, 40), (40, 40), (0, 0)), mode="edge")
    obs_pad = np.pad(obs, ((40, 40), (40, 40), (0, 0)), mode="edge")
    got = OP.fit_mark_colour(obs_pad, pad)
    assert abs(got - mark) <= 3.0


def test_extract_reports_residual_and_support():
    """extract() returns the matte plus the numbers that say whether to trust it."""
    orig, alpha, mark, obs = _synth()
    out = OP.extract(obs, orig)
    assert abs(out["mark_colour"] - mark) <= 2.0
    assert out["support_px"] == int((alpha > OP.ALPHA_FLOOR).sum())
    assert out["residual_mae"] < 1.0
    assert np.abs(out["alpha"] - alpha).max() < 0.02


def test_extract_on_an_identical_pair_finds_no_overlay():
    """A hand-clean that changed nothing must not manufacture a matte."""
    orig, _alpha, _mark, _obs = _synth()
    out = OP.extract(orig.copy(), orig.copy())
    assert out["support_px"] == 0
    assert out["alpha"].max() < OP.ALPHA_FLOOR


def test_shape_mismatch_is_refused():
    """A mismatched pair is an operator error and must fail loudly."""
    orig, _a, _m, obs = _synth()
    with pytest.raises(ValueError):
        OP.extract(obs, orig[:, :-1])
