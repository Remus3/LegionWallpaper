"""Tests for tools/lw_clean_behind.py - measuring the art BEHIND the mark.

Track A. The schedule decides how to treat a mark by measuring busyness on the
frame that still carries it, so a loud mark inflates its own score and the
tile-size rule keyed on that score prescribes the SMALLEST strokes for the
smoothest art. Measured live on the four hand-clean captures, against the
operator's own accepted finals as ground truth:

  slug   marked   true    error
  105     3.684   2.878    +28%
  107     3.178   2.907     +9%
  209     7.754   2.247   +245%     one stroke, on a smooth panel
  dgk     5.467   0.778   +603%     eighteen strokes, on soft snow

209 and dgk both fall to the 2000px tile floor on the marked measure when the
truth asks for 27805 and 40000. That is the bug this module exists to fix.

Two things are needed and they are different:

  busyness()      the STATISTIC, with the mark's pixels excluded from it, so
                  stroke SIZE is chosen on the art rather than on the mark
  behind_image()  an ESTIMATE of the picture under the mark, so stroke
                  PLACEMENT has something to look at

Pure numpy + Pillow, so this runs in the fast CI lane.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_behind as B  # noqa: E402
import lw_clean_tiled as T  # noqa: E402


# ------------------------------------------------------------------- fixtures
def _panel(h=160, w=240):
    """A smooth panel - 209-cleanup's art: nothing busy anywhere."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    v = 60.0 + 0.25 * yy + 0.20 * xx
    return np.clip(np.dstack([v, v * 0.95, v * 0.9]), 0, 255).astype(np.uint8)


def _busy(h=160, w=240):
    """Genuinely busy art: fine structure everywhere, no mark."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    v = 128.0 + 60.0 * np.sin(yy / 2.0) * np.cos(xx / 3.0)
    return np.clip(np.dstack([v, v, v]), 0, 255).astype(np.uint8)


def _mark_on(img, y0=70, y1=95, x0=40, x1=200, stride=6):
    """A loud text-like mark: thin high-contrast strokes over a band."""
    out = img.copy()
    m = np.zeros(img.shape[:2], dtype=bool)
    m[y0:y1, x0:x1] = True
    strokes = np.zeros_like(m)
    strokes[y0:y1, x0:x1:stride] = True
    strokes[y0:y1, x0 + 1:x1:stride] = True
    out[strokes] = 255
    out[y0 + 8:y0 + 10, x0:x1] = 0
    return out, m


def _box_of(mask):
    ys, xs = np.nonzero(mask)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


# ------------------------------------------- the calibration must not drift
def test_busyness_is_the_existing_estimator_when_nothing_is_excluded():
    """The tile-size fit was calibrated with lw_clean_tiled.local_gradient.

    If this module measured busyness even slightly differently, every tile-size
    anchor in the repo would silently mean something else.
    """
    img = _busy()
    box = (30, 20, 200, 140)
    assert B.busyness(img, box) == pytest.approx(T.local_gradient(img, box),
                                                 rel=0, abs=1e-6)


def test_an_empty_exclusion_changes_nothing():
    img = _busy()
    box = (30, 20, 200, 140)
    empty = np.zeros(img.shape[:2], dtype=bool)
    assert B.busyness(img, box, exclude=empty) == pytest.approx(
        B.busyness(img, box), rel=0, abs=1e-6)


# ------------------------------------------------------------- the actual bug
def test_a_loud_mark_inflates_the_measure_taken_on_the_marked_frame():
    truth = _panel()
    marked, mask = _mark_on(truth)
    box = _box_of(mask)
    assert B.busyness(marked, box) > 3.0 * B.busyness(truth, box)


def test_excluding_the_mark_recovers_the_true_busyness():
    truth = _panel()
    marked, mask = _mark_on(truth)
    box = _box_of(mask)
    got = B.busyness(marked, box, exclude=mask, dilate=B.DEFAULT_DILATE)
    want = B.busyness(truth, box)
    assert abs(got - want) <= 0.25 * want


def test_it_recovers_the_true_busyness_on_busy_art_too():
    """Excluding must not turn every image into a smooth one."""
    truth = _busy()
    marked, mask = _mark_on(truth)
    box = _box_of(mask)
    got = B.busyness(marked, box, exclude=mask, dilate=B.DEFAULT_DILATE)
    want = B.busyness(truth, box)
    assert abs(got - want) <= 0.25 * want


def test_the_excluded_measure_cannot_read_a_masked_pixel():
    """The strongest form of the property: change what is under the mark to
    something absurd and the measure must not move at all."""
    truth = _panel()
    marked, mask = _mark_on(truth)
    box = _box_of(mask)
    before = B.busyness(marked, box, exclude=mask, dilate=0)
    wrecked = marked.copy()
    noise = np.indices(mask.shape)[1] % 2
    wrecked[mask] = np.where(noise[mask][:, None] > 0, 255, 0)
    after = B.busyness(wrecked, box, exclude=mask, dilate=0)
    assert after == pytest.approx(before, rel=0, abs=1e-9)


def test_dilating_the_exclusion_covers_the_marks_halo():
    """A brush mask stops short of the mark's soft edge; the halo is still mark."""
    truth = _panel()
    marked, mask = _mark_on(truth)
    halo = B._dilate(mask, 2) & ~mask
    marked[halo] = np.clip(marked[halo].astype(np.int16) + 60, 0, 255)
    box = _box_of(mask)
    want = B.busyness(truth, box)
    tight = abs(B.busyness(marked, box, exclude=mask, dilate=0) - want)
    wide = abs(B.busyness(marked, box, exclude=mask, dilate=3) - want)
    assert wide < tight


# ------------------------------------------------------ the picture behind it
def test_behind_image_never_touches_an_unmarked_pixel():
    truth = _panel()
    marked, mask = _mark_on(truth)
    out = B.behind_image(marked, mask)
    assert out.shape == marked.shape and out.dtype == marked.dtype
    assert np.array_equal(out[~mask], marked[~mask])


def test_behind_image_recovers_a_smooth_panel_under_the_mark():
    truth = _panel()
    marked, mask = _mark_on(truth)
    out = B.behind_image(marked, mask)
    err = np.abs(out[mask].astype(int) - truth[mask].astype(int))
    assert err.mean() <= 3.0


def test_behind_image_is_a_no_op_without_a_mark():
    img = _busy()
    out = B.behind_image(img, np.zeros(img.shape[:2], dtype=bool))
    assert np.array_equal(out, img)


# ------------------------------------------------- what it is all actually for
def test_the_tile_size_stops_being_decided_by_the_mark():
    """The consequence, in the unit that matters.

    On a smooth panel the marked frame drives the tile area to the floor. The
    behind-the-mark measure has to put it back up near where the true art does.
    """
    truth = _panel()
    marked, mask = _mark_on(truth)
    box = _box_of(mask)
    marked_area = T.target_tile_area(B.busyness(marked, box))
    true_area = T.target_tile_area(B.busyness(truth, box))
    fixed_area = T.target_tile_area(B.local_gradient_behind(marked, mask, box))
    assert marked_area < 0.5 * true_area
    assert fixed_area >= 0.6 * true_area


def test_build_plan_sizes_its_tiles_from_the_art_not_from_the_mark():
    """The consumer, end to end: build_plan holds the mark and must exclude it."""
    truth = _panel()
    marked, mask = _mark_on(truth)
    plan = T.build_plan(marked, mask)
    true_grad = B.busyness(truth, _box_of(mask))
    assert plan["local_gradient"] == pytest.approx(true_grad, rel=0.35)


def test_build_plan_still_takes_an_explicit_gradient_override():
    truth = _panel()
    marked, mask = _mark_on(truth)
    plan = T.build_plan(marked, mask, gradient=1.25)
    assert plan["local_gradient"] == pytest.approx(1.25, abs=1e-6)
    assert plan["target_tile_area"] == pytest.approx(
        T.target_tile_area(1.25), rel=1e-6)


def test_the_subdivide_gate_also_stops_measuring_the_mark():
    """Sibling case, same root cause: the gate reads a region OF the footprint."""
    truth = _panel()
    marked, mask = _mark_on(truth)
    labels = np.zeros(marked.shape[:2], dtype=np.int32)
    labels[mask] = 1
    calls = []

    def _seg(crop, area):
        calls.append(area)
        return np.zeros(crop.shape[:2], dtype=np.int32)

    T.subdivide_labels(marked, labels, max_area=100, segmenter=_seg,
                       min_gradient=2.0, exclude=mask)
    without = []

    def _seg2(crop, area):
        without.append(area)
        return np.zeros(crop.shape[:2], dtype=np.int32)

    T.subdivide_labels(marked, labels, max_area=100, segmenter=_seg2,
                       min_gradient=2.0)
    assert len(without) > len(calls), "the mark drove the gate before the fix"


def test_local_gradient_behind_falls_back_cleanly_with_no_mark():
    img = _busy()
    box = (30, 20, 200, 140)
    empty = np.zeros(img.shape[:2], dtype=bool)
    assert B.local_gradient_behind(img, empty, box) == pytest.approx(
        T.local_gradient(img, box), rel=0, abs=1e-6)


def test_it_widens_the_window_when_the_mark_fills_it():
    """A mark covering everything the probe can see is not evidence of smooth
    art; reporting 0.0 there would hand it the maximum tile."""
    img = _busy()
    mask = np.ones(img.shape[:2], dtype=bool)
    mask[:20, :] = False
    mask[-20:, :] = False
    assert B.local_gradient_behind(img, mask, (60, 60, 180, 100), pad=4) > 0.0


def test_a_fully_masked_window_reports_no_busyness_rather_than_crashing():
    img = _busy()
    mask = np.ones(img.shape[:2], dtype=bool)
    assert B.busyness(img, (30, 20, 60, 50), exclude=mask) == 0.0
