"""Tests for align_rois in tools/lw_clean_dekel.py - sub-pixel ROI alignment.

CI constraint (read before editing imports): lw_clean_dekel imports cv2 AND
skimage at module scope, and NEITHER is present on the CI interpreter (CI runs
numpy + PIL + stdlib only - see the header of tests/test_lw_clean_iopaint.py).
So this whole module importorskips at collection and SKIPS in CI by design. It
runs under the lw-clean venv:

    C:\\Tools\\lw-clean\\venv\\Scripts\\python.exe -m pytest tests/test_lw_clean_dekel_align.py

That is a deliberate trade, not an oversight: align_rois is the alignment stage
of the Dekel multi-image watermark solve, it cannot execute without those deps,
and shipping it with ZERO tests (its state before this file) was worse than
shipping tests that only a venv can run. Do not "fix" the skip by stubbing cv2
or skimage - a stubbed phase-correlation proves nothing about registration.

All fixtures are synthetic numpy arrays. NEVER touch images/**.

The load-bearing property asserted here is the one the function exists for:
alignment must REDUCE cross-frame disagreement of the mark signal, and the
recovered shifts must track the applied offsets up to a global constant (the
reference is the median of the mark signals, so an absolute origin is not
defined - only the differences between frames are).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# cv2 + skimage are module-scope imports inside lw_clean_dekel; skip the whole
# file where either is missing rather than exploding at collection.
pytest.importorskip("cv2")
pytest.importorskip("skimage")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
dekel = pytest.importorskip("lw_clean_dekel")


H = W = 72

# (dy, dx) applied to the shared glyph, per frame. Deliberately includes a
# zero-offset frame, both signs, and a repeat magnitude.
OFFSETS = [(0, 0), (1, -3), (-2, 2), (3, 4), (0, -1)]


def _glyph():
    """High-gradient shared mark: box outline plus a diagonal.

    Gradient structure is what mark_signal keys on, so the fixture is edges,
    not a filled blob - a filled blob has interior gradient ~0 and registers
    poorly for reasons that have nothing to do with align_rois.
    """
    g = np.zeros((H, W), np.float32)
    g[20:52, 20:24] = 1.0
    g[20:52, 48:52] = 1.0
    g[20:24, 20:52] = 1.0
    g[48:52, 20:52] = 1.0
    for i in range(28):
        g[24 + i, 24 + i] = 1.0
    return g


def _frames(offsets=OFFSETS, seed=0):
    """One ROI per offset: shared glyph shifted by (dy, dx) over per-frame art.

    The art differs every frame (that is the point - it must cancel under the
    median while the glyph survives).
    """
    rng = np.random.default_rng(seed)
    glyph = _glyph()
    out = []
    for dy, dx in offsets:
        art = rng.random((H, W, 3)).astype(np.float32) * 0.35
        moved = np.roll(np.roll(glyph, dy, axis=0), dx, axis=1)
        out.append(np.clip(art + moved[:, :, None] * 0.6, 0, 1))
    return out


def _mark_spread(rois):
    """Cross-frame disagreement of the mark signal (mean per-pixel stdev)."""
    sigs = np.array([dekel.mark_signal(r) for r in rois])
    return float(np.mean(np.std(sigs, axis=0)))


# ---------------------------------------------------------------------------
# 1. output contract
# ---------------------------------------------------------------------------
def test_align_rois_returns_four_parallel_sequences_of_the_input_length():
    rois = _frames()
    aligned, fwd, inv, shifts = dekel.align_rois(rois)
    assert len(aligned) == len(fwd) == len(inv) == len(shifts) == len(rois)


def test_aligned_rois_keep_the_input_shape_and_the_affines_are_2x3():
    rois = _frames()
    aligned, fwd, inv, _shifts = dekel.align_rois(rois)
    for a, r in zip(aligned, rois, strict=True):
        assert a.shape == r.shape
    for m, mi in zip(fwd, inv, strict=True):
        assert m.shape == (2, 3)
        assert mi.shape == (2, 3)


def test_a_single_roi_is_handled_without_a_degenerate_median():
    """n=1 is a real call shape - the median reference is just that frame."""
    aligned, fwd, inv, shifts = dekel.align_rois(_frames(offsets=[(0, 0)]))
    assert len(aligned) == 1
    assert shifts[0] == (0.0, 0.0)
    assert fwd[0].shape == (2, 3) and inv[0].shape == (2, 3)


# ---------------------------------------------------------------------------
# 2. registration correctness - the reason the function exists
# ---------------------------------------------------------------------------
def test_alignment_reduces_cross_frame_mark_disagreement():
    rois = _frames()
    aligned, _fwd, _inv, _shifts = dekel.align_rois(rois)
    before = _mark_spread(rois)
    after = _mark_spread(aligned)
    assert after < before
    # measured 0.63 reduction on this fixture; assert well clear of noise but
    # far enough below the measurement to survive cv2/skimage version drift.
    assert (1.0 - after / before) > 0.40


def test_recovered_shifts_track_the_applied_offsets_up_to_a_constant():
    """Only DIFFERENCES are defined: the reference is a median, not a frame.

    Recovered shift is the inverse of the applied offset (it is the correction
    that undoes it), so differences carry a negative sign.
    """
    rois = _frames()
    _aligned, _fwd, _inv, shifts = dekel.align_rois(rois)
    rec_dy = np.array([s[0] for s in shifts])
    rec_dx = np.array([s[1] for s in shifts])
    app_dy = np.array([o[0] for o in OFFSETS], dtype=float)
    app_dx = np.array([o[1] for o in OFFSETS], dtype=float)
    # centre both, which removes the undefined global constant
    assert rec_dy - rec_dy.mean() == pytest.approx(-(app_dy - app_dy.mean()), abs=0.15)
    assert rec_dx - rec_dx.mean() == pytest.approx(-(app_dx - app_dx.mean()), abs=0.15)


def test_identical_rois_produce_no_shift():
    same = [_frames(offsets=[(0, 0)])[0].copy() for _ in range(4)]
    _aligned, _fwd, _inv, shifts = dekel.align_rois(same)
    for dy, dx in shifts:
        assert abs(dy) < 0.05
        assert abs(dx) < 0.05


# ---------------------------------------------------------------------------
# 3. affine bookkeeping
# ---------------------------------------------------------------------------
def test_inverse_affine_undoes_the_forward_affine():
    _aligned, fwd, inv, _shifts = dekel.align_rois(_frames())
    for m, mi in zip(fwd, inv, strict=True):
        comp = np.vstack([m, [0, 0, 1]]) @ np.vstack([mi, [0, 0, 1]])
        assert comp == pytest.approx(np.eye(3), abs=1e-9)


def test_the_translation_affine_carries_the_reported_shift():
    """fwd is [[1,0,dx],[0,1,dy]] in the default translation-only mode."""
    _aligned, fwd, _inv, shifts = dekel.align_rois(_frames())
    for m, (dy, dx) in zip(fwd, shifts, strict=True):
        assert m[0, 2] == pytest.approx(dx)
        assert m[1, 2] == pytest.approx(dy)
        assert m[0, 0] == pytest.approx(1.0)
        assert m[1, 1] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 4. the opt-in ECC branch
# ---------------------------------------------------------------------------
def test_ecc_refinement_keeps_the_output_contract():
    rois = _frames()
    aligned, fwd, inv, shifts = dekel.align_rois(rois, use_ecc=True)
    assert len(aligned) == len(fwd) == len(inv) == len(shifts) == len(rois)
    for a, r, m, mi in zip(aligned, rois, fwd, inv, strict=True):
        assert a.shape == r.shape
        assert m.shape == (2, 3) and mi.shape == (2, 3)
        assert np.isfinite(m).all()


def test_ecc_does_not_rewrite_the_reported_shifts():
    """`shifts` records the phase-correlation estimate, taken BEFORE ECC runs.

    ECC refines the affine in `fwd` only. A caller reading `shifts` after
    use_ecc=True is reading the translation estimate, not the refinement -
    pinned here because the difference is invisible at the call site.
    """
    rois = _frames()
    _a1, _f1, _i1, plain = dekel.align_rois(rois)
    _a2, _f2, _i2, ecc = dekel.align_rois(rois, use_ecc=True)
    assert plain == ecc
