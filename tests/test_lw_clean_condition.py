"""Tests for tools/lw_clean_condition.py - opacity / hue / tone conditioning.

Track D. The idea is that a mark is a semi-transparent layer over the art,

    observed = alpha * colour + (1 - alpha) * content

so estimating alpha and colour from the readable ring around the mark lets the
region be pushed back toward the content before any filler is asked for
anything: the mark's amplitude drops and the region's tone matches its
surroundings.

These tests hold the ESTIMATOR to that model on art where the model is true by
construction. That separation matters: the census on the real captures shows the
model does not describe three of the four marks, and this file is what proves
the difference is the corpus rather than a broken estimator.

Pure numpy + Pillow, so this runs in the fast CI lane.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_condition as C  # noqa: E402


# ------------------------------------------------------------------- fixtures
def _art(h=180, w=260):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    v = 120.0 + 45.0 * np.sin(yy / 7.0) * np.cos(xx / 9.0) + 0.2 * xx
    return np.clip(np.dstack([v, v * 0.92, v * 0.85]), 0, 255).astype(np.uint8)


def _band(shape, y0=70, y1=100, x0=40, x1=220):
    m = np.zeros(shape[:2], dtype=bool)
    m[y0:y1, x0:x1] = True
    return m


def _veil(img, mask, alpha, colour):
    """The model, applied: what a true semi-transparent layer would produce."""
    out = img.astype(np.float64).copy()
    a = np.asarray(alpha, dtype=np.float64)
    c = np.asarray(colour, dtype=np.float64)
    out[mask] = a * c + (1.0 - a) * out[mask]
    return np.clip(out, 0, 255).astype(np.uint8)


# --------------------------------------------------------- the estimator
def test_a_uniform_veil_is_recovered_from_the_ring_alone():
    art = _art()
    mask = _band(art.shape)
    seen = _veil(art, mask, [0.5, 0.5, 0.5], [240, 240, 240])
    rec = C.estimate_veil(seen, mask)
    assert rec["applies"]
    assert np.allclose(rec["alpha"], 0.5, atol=0.08)
    assert np.allclose(rec["colour"], 240, atol=12)


def test_a_tinted_veil_is_recovered_per_channel():
    """The hue half of the track: the layer need not be grey."""
    art = _art()
    mask = _band(art.shape)
    seen = _veil(art, mask, [0.45, 0.45, 0.45], [255, 200, 150])
    rec = C.estimate_veil(seen, mask)
    assert rec["applies"]
    assert rec["colour"][0] > rec["colour"][1] > rec["colour"][2]


def test_inverting_the_veil_puts_the_art_back():
    art = _art()
    mask = _band(art.shape)
    seen = _veil(art, mask, [0.5, 0.5, 0.5], [240, 240, 240])
    out, _rec = C.auto_condition(seen, mask)
    before = np.abs(seen[mask].astype(int) - art[mask].astype(int)).mean()
    after = np.abs(out[mask].astype(int) - art[mask].astype(int)).mean()
    assert after < 0.4 * before


def test_nothing_outside_the_mark_ever_moves():
    art = _art()
    mask = _band(art.shape)
    seen = _veil(art, mask, [0.5, 0.5, 0.5], [240, 240, 240])
    out, _rec = C.auto_condition(seen, mask)
    assert out.dtype == seen.dtype and out.shape == seen.shape
    assert np.array_equal(out[~mask], seen[~mask])


def test_an_unveiled_region_is_left_alone():
    """No veil means no correction - not a small one applied anyway."""
    art = _art()
    mask = _band(art.shape)
    out, rec = C.auto_condition(art, mask)
    assert not rec["steps"][0]["applies"]
    assert np.array_equal(out, art)


def test_a_contrast_loss_inside_the_arts_own_variation_is_not_a_veil():
    """The null: two annuli of the same art already differ, so a difference
    that size is no evidence of anything."""
    art = _art()
    mask = _band(art.shape)
    seen = _veil(art, mask, [0.02, 0.02, 0.02], [240, 240, 240])
    rec = C.estimate_veil(seen, mask)
    assert not rec["applies"]
    assert "variation" in rec["reason"] or "not a veil" in rec["reason"]


def test_a_region_busier_than_its_ring_is_not_treated_as_veiled():
    """A veil can only REDUCE contrast. More contrast means it is not a veil."""
    art = _art()
    mask = _band(art.shape)
    loud = art.copy()
    yy, xx = np.mgrid[0:art.shape[0], 0:art.shape[1]]
    loud[mask & ((xx % 4) < 2)] = 255
    loud[mask & ((xx % 4) >= 2)] = 0
    rec = C.estimate_veil(loud, mask)
    assert not rec["applies"]


def test_the_gain_is_clamped_so_a_strong_veil_cannot_explode():
    art = _art()
    mask = _band(art.shape)
    seen = _veil(art, mask, [0.97, 0.97, 0.97], [250, 250, 250])
    out, rec = C.auto_condition(seen, mask)
    assert rec["steps"][0]["alpha"] <= C.MAX_ALPHA + 1e-9
    assert np.isfinite(out[mask].astype(float)).all()


def test_conditioning_is_deterministic():
    art = _art()
    mask = _band(art.shape)
    seen = _veil(art, mask, [0.4, 0.4, 0.4], [230, 220, 210])
    a, _ = C.auto_condition(seen, mask)
    b, _ = C.auto_condition(seen, mask)
    assert np.array_equal(a, b)


def test_an_empty_mark_is_a_no_op():
    art = _art()
    out, rec = C.auto_condition(art, np.zeros(art.shape[:2], dtype=bool))
    assert np.array_equal(out, art)
    assert rec["steps"] == []


# ------------------------------------------------- the validator, validated
def test_the_ground_truth_fit_recovers_a_veil_it_is_shown():
    """fit_veil is what the census judges the model by, so it is checked too."""
    art = _art()
    mask = _band(art.shape)
    seen = _veil(art, mask, [0.5, 0.5, 0.5], [240, 240, 240])
    fit = C.fit_veil(seen, art, mask)
    assert np.allclose(fit["alpha"], 0.5, atol=0.03)
    assert np.allclose(fit["colour"], 240, atol=6)
    assert min(fit["r2"]) > 0.98


def test_the_ground_truth_fit_reports_a_bad_model_as_a_bad_fit():
    """An opaque mark carries no information about what is under it, and the
    fit has to say so rather than return a confident number."""
    art = _art()
    mask = _band(art.shape)
    opaque = art.copy()
    rng = (np.indices(mask.shape)[1] * 37 % 251).astype(np.uint8)
    opaque[mask] = np.stack([rng[mask]] * 3, axis=1)
    fit = C.fit_veil(opaque, art, mask)
    assert max(fit["r2"]) < 0.5


# ------------------------------------------------------------ per blob
def test_each_blob_is_conditioned_from_its_own_ring():
    art = _art()
    a = _band(art.shape, 20, 40, 20, 90)
    b = _band(art.shape, 120, 150, 150, 240)
    seen = _veil(_veil(art, a, [0.5] * 3, [250] * 3), b, [0.2] * 3, [40] * 3)
    _out, rec = C.auto_condition(seen, a | b)
    assert len(rec["steps"]) == 2
    alphas = sorted(np.mean(s["alpha"]) for s in rec["steps"])
    assert alphas[0] < alphas[1], "one veil is much lighter than the other"


def test_conditioning_the_whole_region_at_once_is_still_available():
    art = _art()
    a = _band(art.shape, 20, 40, 20, 90)
    b = _band(art.shape, 120, 150, 150, 240)
    seen = _veil(art, a | b, [0.4] * 3, [240] * 3)
    _out, rec = C.auto_condition(seen, a | b, per_blob=False)
    assert len(rec["steps"]) == 1


def test_a_blob_with_no_readable_ring_is_skipped_not_guessed():
    art = _art()
    mask = np.ones(art.shape[:2], dtype=bool)
    out, rec = C.auto_condition(art, mask)
    assert np.array_equal(out, art)
    assert rec["steps"][0]["reason"] == "no readable ring"


def test_the_record_carries_what_a_human_needs_to_check_it():
    art = _art()
    mask = _band(art.shape)
    seen = _veil(art, mask, [0.5] * 3, [240] * 3)
    _out, rec = C.auto_condition(seen, mask)
    step = rec["steps"][0]
    assert {"alpha", "colour", "applies", "reason", "px"} <= set(step)
    assert step["px"] == int(mask.sum())
    assert rec["conditioned_px"] == pytest.approx(int(mask.sum()))
