"""Tests for tools/lw_clean_spot.py - per-blob spot healing, with rollback.

Track C, and it is where A and B become useful rather than interesting.

The schedule this replaces commits every step unconditionally: it fills, and
whatever came out is what you get. Four captures say the operator does not work
that way - they treat one spot at a time, look at it, and undo what made things
worse.

So each blob of the mark is its own heal:

  context   sized from the art BEHIND the mark (track A), per blob, so a
            signature on a smooth panel gets a broad stroke and the same blob on
            busy art gets a tight one. This is what retires the fixed
            CONTEXT_RATIO = 5.0 that four captures falsified.
  judgement the comparison layer (track B), scoped to the chords this blob's
            context actually touches - a fill in one corner is not judged by
            lines on the other side of the frame.
  rollback  a step that turns an intact chord into a broken one is UNDONE. The
            mark surviving is recoverable; art destroyed under it is not.

Deliberately no residue detector anywhere: contrast residue is on the standing
do-not-redo list as a starting detector, and the footprint is what the detector
already decided.

Pure numpy + Pillow, so this runs in the fast CI lane.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_spot as S  # noqa: E402
import lw_clean_tiled as T  # noqa: E402


# ------------------------------------------------------------------- fixtures
def _art(h=200, w=300, line=True):
    img = np.full((h, w, 3), 210, dtype=np.uint8)
    if line:
        yy, xx = np.mgrid[0:h, 0:w]
        img[np.abs((yy - 10) - xx) <= 1.5] = 30
    return img


def _busy_art(h=200, w=300):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    v = 150.0 + 55.0 * np.sin(yy / 2.2) * np.cos(xx / 2.6)
    return np.clip(np.dstack([v, v, v]), 0, 255).astype(np.uint8)


def _blob(shape, y0, y1, x0, x1):
    m = np.zeros(shape[:2], dtype=bool)
    m[y0:y1, x0:x1] = True
    return m


def _marked(truth, mark):
    out = truth.copy()
    out[mark] = (0.4 * out[mark].astype(np.float64) + 0.6 * 240).astype(np.uint8)
    return out


def _keep(crop_rgb, crop_mask_u8):
    """A fill that changes nothing - stands in for a perfect one."""
    return crop_rgb


def _erase(crop_rgb, crop_mask_u8):
    """A fill that flattens the region, which is what a blur does."""
    return np.full_like(crop_rgb, 210)


def _truth_filler(truth, marked, mark):
    """A fill that restores the true art - the best any engine could do.

    The crop coordinates are not handed to the callback, so they are recomputed
    here exactly as the runner does. The order is deterministic, so they line up.
    """
    h, w = mark.shape
    boxes = []
    for _blob, ctx in S.plan_spots(marked, mark):
        bb = T.mask_bbox(ctx)
        boxes.append(T.crop_box(bb[0], bb[1], bb[2], bb[3], S.CROP_MARGIN, w, h))
    it = iter(boxes)

    def _fn(crop_rgb, crop_mask_u8):
        x0, y0, x1, y1 = next(it)
        return truth[y0:y1, x0:x1]
    return _fn


# ---------------------------------------------------------------- per blob
def test_every_blob_of_the_mark_gets_its_own_step():
    truth = _art()
    mark = _blob(truth.shape, 40, 52, 30, 90) | _blob(truth.shape, 150, 162, 200, 260)
    out, plan = S.run_spot_heal(_marked(truth, mark), mark, _keep)
    assert plan["blobs"] == 2
    assert len(plan["steps"]) == 2
    assert out.shape == truth.shape


def test_a_steps_context_never_reaches_another_blob():
    truth = _art()
    a = _blob(truth.shape, 40, 52, 30, 90)
    b = _blob(truth.shape, 150, 162, 200, 260)
    masks = S.plan_spots(_marked(truth, a | b), a | b, margin=3.0)
    assert len(masks) == 2
    for blob, ctx in masks:
        other = b if (blob & a).any() else a
        assert not (ctx & other).any()


def test_nothing_outside_the_context_of_any_step_moves():
    truth = _art()
    mark = _blob(truth.shape, 40, 52, 30, 90)
    marked = _marked(truth, mark)
    out, plan = S.run_spot_heal(marked, mark, _erase, rollback=False)
    touched = np.zeros(mark.shape, dtype=bool)
    for _blob_m, ctx in S.plan_spots(marked, mark):
        touched |= ctx
    assert np.array_equal(out[~touched], marked[~touched])


# ------------------------------------------------- context sized by track A
def test_smooth_art_is_worked_in_fewer_larger_strokes_than_busy_art():
    """The composition with track A, in the unit the measurement governs.

    Same blob, same size, different art behind it. The measured busyness of the
    ART - not of the mark - decides how the mark is cut into strokes. It does
    NOT decide the margin: growing a blob to the stroke target was the first
    version's mistake and it repainted 24x the mark on soft snow.
    """
    blob = _blob((200, 300), 60, 120, 40, 260)
    smooth = S.plan_spots(_marked(_art(line=False), blob), blob, split=True)
    busy = S.plan_spots(_marked(_busy_art(), blob), blob, split=True)
    assert len(smooth) < len(busy)
    assert max(int(p.sum()) for p, _c in smooth) >         max(int(p.sum()) for p, _c in busy)


def test_splitting_is_off_by_default():
    """Measured on the captures: disjoint stroke-sized pieces starve the filler
    of context and score worse than one spot per blob on large-area marks."""
    blob = _blob((200, 300), 60, 120, 40, 260)
    assert len(S.plan_spots(_marked(_busy_art(), blob), blob)) == 1


def test_by_default_a_spot_repaints_the_mark_and_nothing_else():
    """The regression measurement caught twice.

    First the context was grown to the stroke target and dgk repainted 24x its
    mark. Then a 1.6x margin still lost to the one-shot fill on all four
    captures. A brush mask is already the answer to "what has to change".
    """
    blob = _blob((200, 300), 90, 102, 120, 180)
    for art in (_art(line=False), _busy_art()):
        _piece, ctx = S.plan_spots(_marked(art, blob), blob)[0]
        assert np.array_equal(ctx, blob)


def test_a_margin_can_still_be_asked_for():
    blob = _blob((200, 300), 90, 102, 120, 180)
    _piece, ctx = S.plan_spots(_marked(_art(line=False), blob), blob,
                               margin=3.0)[0]
    assert int(ctx.sum()) > int(blob.sum())


def test_the_context_is_recorded_per_step_with_the_gradient_it_came_from():
    truth = _art()
    mark = _blob(truth.shape, 40, 52, 30, 90)
    _out, plan = S.run_spot_heal(_marked(truth, mark), mark, _keep)
    step = plan["steps"][0]
    assert step["mask_px"] >= step["blob_px"]
    assert step["gradient_behind"] > 0
    assert step["target_area"] > 0


# --------------------------------------------------------------- rollback
def test_a_step_that_breaks_a_line_is_undone():
    truth = _art()
    mark = _blob(truth.shape, 40, 52, 10, 120)     # the diagonal crosses this
    marked = _marked(truth, mark)
    out, plan = S.run_spot_heal(marked, mark, _erase)
    assert plan["steps"][0]["action"] == "revert"
    assert plan["held"] == 1
    assert plan["status"] == "held"
    assert np.array_equal(out, marked), "a reverted step must leave no trace"


def test_a_step_that_keeps_the_line_is_committed():
    truth = _art()
    mark = _blob(truth.shape, 40, 52, 10, 120)
    marked = _marked(truth, mark)
    out, plan = S.run_spot_heal(marked, mark,
                                _truth_filler(truth, marked, mark))
    assert plan["steps"][0]["action"] == "commit"
    assert plan["held"] == 0
    assert plan["status"] == "clean"
    assert not np.array_equal(out, marked)


def test_rollback_can_be_switched_off():
    truth = _art()
    mark = _blob(truth.shape, 40, 52, 10, 120)
    marked = _marked(truth, mark)
    out, plan = S.run_spot_heal(marked, mark, _erase, rollback=False)
    assert plan["steps"][0]["action"] == "commit"
    assert not np.array_equal(out, marked)


def test_a_blob_with_no_line_across_it_is_committed_on_no_evidence():
    """Abstaining is not failing: with nothing to break, the fill stands."""
    truth = _art(line=False)
    mark = _blob(truth.shape, 40, 52, 30, 90)
    marked = _marked(truth, mark)
    _out, plan = S.run_spot_heal(marked, mark, _erase)
    step = plan["steps"][0]
    assert step["chords"] == 0
    assert step["action"] == "commit"
    assert step["reason"] == "no-evidence"


def test_the_verdict_is_a_comparison_not_a_threshold():
    """Before and after are both recorded, and the decision uses both."""
    truth = _art()
    mark = _blob(truth.shape, 40, 52, 10, 120)
    _out, plan = S.run_spot_heal(_marked(truth, mark), mark, _erase)
    step = plan["steps"][0]
    assert step["median_before"] is not None
    assert step["median_after"] is not None
    assert step["median_after"] < step["median_before"]


def test_one_bad_blob_does_not_roll_back_a_good_one():
    truth = _art()
    good = _blob(truth.shape, 150, 162, 200, 260)      # no line crosses this
    bad = _blob(truth.shape, 40, 52, 10, 120)          # the diagonal does
    marked = _marked(truth, good | bad)
    _out, plan = S.run_spot_heal(marked, good | bad, _erase)
    actions = {tuple(s["blob_bbox"]): s["action"] for s in plan["steps"]}
    assert set(actions.values()) == {"commit", "revert"}


def test_the_run_is_deterministic():
    truth = _art()
    mark = _blob(truth.shape, 40, 52, 10, 120) | _blob(truth.shape, 150, 162, 200, 260)
    marked = _marked(truth, mark)
    a, pa = S.run_spot_heal(marked, mark, _erase)
    b, pb = S.run_spot_heal(marked, mark, _erase)
    assert np.array_equal(a, b)
    assert [s["action"] for s in pa["steps"]] == [s["action"] for s in pb["steps"]]


def test_an_empty_mark_is_a_no_op():
    truth = _art()
    out, plan = S.run_spot_heal(truth, np.zeros(truth.shape[:2], dtype=bool),
                                _erase)
    assert np.array_equal(out, truth)
    assert plan["blobs"] == 0
    assert plan["status"] == "clean"


# ------------------------------------------------------- scoped revert (opt-in)
def test_a_scoped_revert_keeps_the_part_of_the_fill_that_broke_nothing():
    """The blob is wide; the diagonal only crosses its left end.

    A whole-blob revert throws away the fill everywhere, including the stretch
    of mark that had no line near it, which is how a thicker mask ends up
    cleaning LESS: merge the strokes into one blob and one broken chord kills
    the lot. Scoping the revert to the neighbourhood of the lines that actually
    broke keeps the rest.
    """
    truth = _art()
    mark = _blob(truth.shape, 40, 52, 10, 120)
    marked = _marked(truth, mark)
    out, plan = S.run_spot_heal(marked, mark, _erase, scoped=True)
    step = plan["steps"][0]
    assert step["action"] == "partial"
    assert plan["partial"] == 1
    assert plan["held"] == 0
    assert 0 < step["reverted_px"] < step["mask_px"]
    assert not np.array_equal(out, marked), "the far end of the fill stands"
    on_line = [(y, y - 10) for y in range(42, 50)]
    assert all(np.array_equal(out[y, x], marked[y, x]) for y, x in on_line),         "the line's own band is put back"
    assert np.array_equal(out[44, 100], np.array([210, 210, 210], np.uint8)),         "the far end, with no line near it, keeps the fill"


def test_a_partial_still_stops_the_slug_leaving_the_queue():
    truth = _art()
    mark = _blob(truth.shape, 40, 52, 10, 120)
    _out, plan = S.run_spot_heal(_marked(truth, mark), mark, _erase, scoped=True)
    assert plan["status"] == "held", "mark left on the frame is not clean"


def test_scoping_declines_when_the_step_damaged_no_line():
    """The fallback contract: no damaged chord, nothing to scope to.

    A revert on the strength rule with no chord that measurably lost anything
    has no neighbourhood to give back, and the caller must revert whole rather
    than invent one.
    """
    truth = _art()
    mark = _blob(truth.shape, 40, 52, 10, 120)
    marked = _marked(truth, mark)
    layer = S.HEAL._dilate(mark, S.HALO)
    chords = S.LINES.build_layer(marked, layer)
    frame, band, why = S.scoped_revert(marked, marked, chords, layer, mark)
    assert (frame, band, why) == (None, None, None)


def test_scoping_is_off_by_default():
    """The measured behaviour does not change until it is asked for."""
    truth = _art()
    mark = _blob(truth.shape, 40, 52, 10, 120)
    marked = _marked(truth, mark)
    out, plan = S.run_spot_heal(marked, mark, _erase)
    assert plan["steps"][0]["action"] == "revert"
    assert plan["partial"] == 0
    assert np.array_equal(out, marked)


def test_the_band_follows_the_chord_and_not_the_blob():
    class _C:
        path = np.array([[50.0, float(x)] for x in range(50, 61)])
    band = S.band_around([_C()], (100, 100), radius=3)
    assert band[50, 50] and band[50, 60]
    assert band[47, 55] and not band[46, 55]
    assert not band[50, 70]
