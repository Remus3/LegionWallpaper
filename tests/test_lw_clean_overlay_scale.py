"""Scale-aware REGISTRATION for the overlay removal lane.

`best_shift` registers translation only. Two frames in the flagged family carry
the overlay at a different PIXEL SIZE, and no shift can align those - measured
over every flagged slug scoring under 0.25 plus `110-cleanup`:

    110-cleanup   0.1090 -> 0.5052  at scale 1.12
    122           0.1696 -> 0.6542  at scale 1.12
    everything else peaks at 1.00, wobbling at most +0.034

Both land on the SAME 1.12 and both jump into the range the well-registered
frames already occupy (mecha-ahri 0.696, 123f 0.635), which is what a correct
registration looks like rather than a lucky correlation.

Two boundaries this file exists to hold.

**The scale search is for REMOVAL, never for the gate.** Measured on the top of
the clean population, a max-over-scales lifts `wallpapersden-...-sejuani` from
0.1213 to 0.1537 - over the 0.15 flag, i.e. a false positive manufactured by the
search. That is the same lesson the shift window already learned: a wider search
buys the negatives more chances than it buys the positives.

**A non-native scale must be DECISIVE to be accepted.** Frames that are
correctly registered at 1.00 still wobble by up to +0.034 (270f, 0.1548 ->
0.1889 at 0.94). Accepting an argmax would misregister a frame that was fine.
The measured separation is wide - noise peaks at 1.22x the native score, the two
real ones at 3.86x and 4.63x - so the ratio gate sits at 2.0, and it errs toward
keeping scale 1.0, which is the safe direction (a wrong scale means a wrong
edit; a rejected scale means today's behaviour).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))
import lw_clean_overlay as OV  # noqa: E402


# ===========================================================================
# 1. the centred rescale primitive
# ===========================================================================
def test_scale_of_one_is_identity():
    a = np.arange(48, dtype=np.float64).reshape(6, 8)
    assert np.array_equal(OV.scale2d_centered(a, 1.0), a)


def test_scale_keeps_the_array_shape():
    a = np.zeros((10, 20))
    for s in (0.8, 1.0, 1.3):
        assert OV.scale2d_centered(a, s).shape == (10, 20)


def test_scaling_up_magnifies_about_the_centre():
    """A centred block must stay centred and get wider."""
    a = np.zeros((20, 20))
    a[8:12, 8:12] = 1.0
    up = OV.scale2d_centered(a, 2.0)
    ys, xs = np.nonzero(up > 0.5)
    assert xs.max() - xs.min() > 4, "the block must widen"
    assert abs((xs.min() + xs.max()) / 2 - 9.5) <= 1.0, "and stay centred"


def test_scaling_down_pads_with_zero():
    a = np.ones((20, 20))
    down = OV.scale2d_centered(a, 0.5)
    assert down[0, 0] == 0.0 and down[-1, -1] == 0.0
    assert down[10, 10] == pytest.approx(1.0)


def test_bool_arrays_stay_bool():
    a = np.zeros((16, 16), dtype=bool)
    a[6:10, 6:10] = True
    out = OV.scale2d_centered(a, 1.4)
    assert out.dtype == bool and out.any()


# ===========================================================================
# 2. best_registration - scale x shift, with the decisiveness gate
# ===========================================================================
def _tpl_from(arr, band=(0.0, 1.0)):
    sup = np.abs(arr) > 1e-9
    return {"template": arr, "support": sup, "band": band, "n": 1}


def _mark(size=(160, 240)):
    m = np.zeros(size)
    m[70:76, 60:180] = 40.0
    m[80:86, 60:180] = -40.0
    return m


def _planted(scale=1.0, shift=(0, 0), size=(160, 240), seed=11):
    """A frame carrying a known mark at a known scale and offset.

    The seed varies per frame on purpose: with one shared noise realization the
    art correlates perfectly with itself at scale 1.0 and drowns the mark, which
    is the fixture trap the veil work already recorded once (a fixture whose
    frames are related makes the method under test unmeasurable).
    """
    rng = np.random.default_rng(seed)
    img = rng.normal(120, 12, (size[0], size[1], 3))
    mark = np.roll(OV.scale2d_centered(_mark(size), scale), shift, axis=(0, 1))
    return img + mark[:, :, None]


def _mark_tpl(size=(160, 240)):
    """A template of the mark alone - what a median over many unrelated frames
    converges to, without the single-frame noise a one-image stack carries."""
    return _tpl_from(OV.highpass(np.repeat(_mark(size)[:, :, None], 3, axis=2)))


def test_registration_finds_the_planted_scale():
    score, _dy, _dx, s = OV.best_registration(_planted(1.3, seed=3), _mark_tpl(),
                                              scales=[1.0, 1.15, 1.3, 1.45])
    assert s == pytest.approx(1.3)
    assert score > 0.3


def test_registration_defaults_to_native_scale_on_a_matching_frame():
    _score, _dy, _dx, s = OV.best_registration(_planted(1.0, seed=4), _mark_tpl(),
                                               scales=[0.9, 1.0, 1.1])
    assert s == pytest.approx(1.0)


def test_a_marginal_gain_is_refused_and_keeps_scale_one():
    """270f: 0.1548 native, 0.1889 at 0.94. A 1.22x wobble is not a mismatch,
    and accepting it would misregister a frame that was already right."""
    assert OV.accept_scale(0.1889, 0.1548) is False
    assert OV.accept_scale(0.5052, 0.1090) is True     # 110-cleanup, 4.63x
    assert OV.accept_scale(0.6542, 0.1696) is True     # 122, 3.86x


def test_acceptance_ratio_is_the_calibrated_constant():
    assert OV.SCALE_ACCEPT_RATIO == pytest.approx(2.0)
    assert OV.accept_scale(0.2, 0.1) is True
    assert OV.accept_scale(0.199, 0.1) is False


def test_a_non_positive_native_score_never_accepts_a_scale():
    """With nothing to compare against, the ratio is meaningless - keep 1.0."""
    assert OV.accept_scale(0.9, 0.0) is False
    assert OV.accept_scale(0.9, -0.05) is False


def test_registration_is_a_no_op_without_a_template():
    assert OV.best_registration(_planted(), None) == (0.0, 0, 0, 1.0)


def test_registration_reduces_to_best_shift_at_scale_one():
    """The scale-1.0 arm must be the SAME computation the removal lane used
    before, or this change silently re-registers all 32 flagged frames."""
    tpl = _tpl_from(OV.band_of(OV.highpass(_planted(1.0)), (0.0, 1.0)))
    img = _planted(1.0, shift=(3, -5))
    score, dy, dx = OV.best_shift(img, tpl)
    rscore, rdy, rdx, s = OV.best_registration(img, tpl, scales=[1.0])
    assert (rscore, rdy, rdx, s) == (score, dy, dx, 1.0)


# ===========================================================================
# 3. the gate boundary - detection must NOT gain the scale search
# ===========================================================================
def test_overlay_score_takes_no_scale_argument():
    """A scale search in the gate manufactures false positives (measured:
    wallpapersden-sejuani 0.1213 -> 0.1537, over the 0.15 flag). The detection
    entry point must not grow one."""
    import inspect
    params = set(inspect.signature(OV.overlay_score).parameters)
    assert "scale" not in params and "scales" not in params


def test_scale_grid_is_centred_on_native_and_modest():
    assert 1.0 in OV.SCALE_GRID
    assert min(OV.SCALE_GRID) >= 0.85 and max(OV.SCALE_GRID) <= 1.25
    assert 1.12 in OV.SCALE_GRID, "the measured mismatch must be reachable"


# ===========================================================================
# 4. remove_overlay honours the registered scale
# ===========================================================================
def _matte(size=(160, 240), alpha=0.5):
    a = np.zeros(size)
    a[70:86, 60:180] = alpha
    w = np.full(size + (3,), 255.0)
    return {"alpha": a, "W": w, "band": (0.0, 1.0)}


def test_removal_at_scale_one_is_unchanged():
    img = np.full((160, 240, 3), 100.0)
    base, _ = OV.remove_overlay(img, _matte())
    scaled, _ = OV.remove_overlay(img, _matte(), scale=1.0)
    assert np.array_equal(base, scaled)


def test_removal_at_a_larger_scale_edits_a_larger_region():
    img = np.full((160, 240, 3), 100.0)
    _o1, c1 = OV.remove_overlay(img, _matte())
    _o2, c2 = OV.remove_overlay(img, _matte(), scale=1.3)
    assert c2.sum() > c1.sum() * 1.2


def test_removal_outside_the_scaled_matte_is_byte_identical():
    """The alpha-0 copy-through must survive scaling - it is how AG 1.3 holds
    by construction rather than by measurement."""
    rng = np.random.default_rng(5)
    img = rng.integers(0, 255, (160, 240, 3)).astype(np.float64)
    out, changed = OV.remove_overlay(img, _matte(), scale=1.15)
    src = np.clip(np.rint(img), 0, 255).astype(np.uint8)
    assert np.array_equal(out[~changed], src[~changed])
