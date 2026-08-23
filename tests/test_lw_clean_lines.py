"""Tests for tools/lw_clean_lines.py - the overlap-muxed comparison layer.

Track B. The operator rejected 45 of 45 automated candidates for one stated
reason: lines from outside the matte do not re-align. Nothing in the stack could
SEE that, so every gate passed frames the eye rejected instantly.

The layer is built from the content around the mark, before any fill: where a
strong edge meets the mark's boundary it is going somewhere, and the crossing on
the far side that agrees with it in direction and position is where it comes
out. Each such pair is a CHORD - a prediction, made from readable art only,
about a line that must exist inside the filled region.

Scoring a fill is then a measurement, not a judgement: probe across the
predicted path and ask whether the line is there. Three failures are told apart
and that distinction is the whole point:

  intact      the line is on the predicted path with the expected contrast
  erased      the fill smoothed it away (a membrane fill does this)
  misaligned  a line exists but not where the art says it goes - the exact
              defect that got the candidates rejected

Pure numpy + Pillow, so this runs in the fast CI lane.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_lines as L  # noqa: E402
import lw_clean_tiled as T  # noqa: E402


# ------------------------------------------------------------------- fixtures
def _line_img(h=160, w=240, c=10, width=1.5, shift=0.0, only_outside=None):
    """A light field with a dark diagonal stroke at y = x + c."""
    img = np.full((h, w, 3), 210, dtype=np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]
    on = np.abs((yy - c) - xx - shift) <= width
    if only_outside is not None:
        on = on & ~only_outside
    img[on] = 30
    return img


def _two_lines(h=160, w=240):
    img = np.full((h, w, 3), 210, dtype=np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]
    img[np.abs((yy - 10) - xx) <= 1.5] = 30
    img[np.abs((yy + 30) - xx) <= 1.5] = 30
    return img


def _band(h=160, w=240, y0=54, y1=66, x0=20, x1=200):
    m = np.zeros((h, w), dtype=bool)
    m[y0:y1, x0:x1] = True
    return m


def _flat(h=160, w=240):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    v = 90.0 + 0.15 * yy + 0.1 * xx
    return np.clip(np.dstack([v, v, v]), 0, 255).astype(np.uint8)


def _erased(img, mask):
    """What a membrane fill does: the region flattened to its own mean."""
    out = img.copy()
    out[mask] = img[~mask].mean(axis=0).astype(np.uint8)
    return out


def _misaligned(img, mask, shift=7.0):
    """A line IS there, just not where the art says it goes."""
    out = img.copy()
    out[mask] = 210
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    wrong = (np.abs((yy - 10) - xx - shift) <= 1.5) & mask
    out[wrong] = 30
    return out


# ------------------------------------------------------- building the layer
def test_a_line_crossing_the_mark_produces_exactly_one_chord():
    img = _line_img()
    mask = _band()
    chords = L.build_layer(img, mask)
    assert len(chords) == 1
    c = chords[0]
    ys = sorted([c.p0[0], c.p1[0]])
    assert ys[0] < 54 and ys[1] >= 65, "the chord must span the mark"


def test_flat_art_produces_no_chords_at_all():
    chords = L.build_layer(_flat(), _band())
    assert chords == []


def test_a_verdict_on_no_chords_is_no_evidence_not_a_pass():
    img, mask = _flat(), _band()
    rec = L.score(img, mask, L.build_layer(img, mask))
    assert rec["n_chords"] == 0
    assert rec["verdict"] == "no-evidence"


def test_two_lines_pair_with_themselves_not_with_each_other():
    img = _two_lines()
    mask = _band()
    chords = L.build_layer(img, mask)
    assert len(chords) == 2
    for c in chords:
        # each chord's ends belong to the same line: y - x is the line's own
        # constant, and it must agree at both ends.
        k0 = c.p0[0] - c.p0[1]
        k1 = c.p1[0] - c.p1[1]
        assert abs(k0 - k1) <= 6.0


def test_the_layer_is_deterministic():
    img, mask = _line_img(), _band()
    a = L.build_layer(img, mask)
    b = L.build_layer(img, mask)
    assert [(c.p0, c.p1) for c in a] == [(c.p0, c.p1) for c in b]


def test_the_layer_is_built_from_readable_art_only():
    """The prediction may not read a single pixel inside the mark.

    Otherwise it would learn the mark and then congratulate a fill for
    reproducing it - the same trap track A found in the busyness measure.
    """
    img, mask = _line_img(), _band()
    before = L.build_layer(img, mask)
    wrecked = img.copy()
    rng = (np.indices(mask.shape)[1] % 2).astype(bool)
    wrecked[mask & rng] = 0
    wrecked[mask & ~rng] = 255
    after = L.build_layer(wrecked, mask)
    assert [(c.p0, c.p1, round(c.expected, 6)) for c in before] == \
           [(c.p0, c.p1, round(c.expected, 6)) for c in after]


# ------------------------------------------------------------ scoring a fill
def test_the_true_art_scores_intact():
    img, mask = _line_img(), _band()
    rec = L.score(img, mask, L.build_layer(img, mask))
    assert rec["verdict"] == "intact"
    assert rec["median_ratio"] >= 0.7


def test_an_erased_line_scores_broken():
    img, mask = _line_img(), _band()
    chords = L.build_layer(img, mask)
    rec = L.score(_erased(img, mask), mask, chords)
    assert rec["median_ratio"] <= 0.3
    assert rec["verdict"] == "broken"


def test_a_misaligned_line_scores_broken_even_though_a_line_is_there():
    """The defect the operator named. Contrast alone would call this a pass."""
    img, mask = _line_img(), _band()
    chords = L.build_layer(img, mask)
    wrong = _misaligned(img, mask)
    rec = L.score(wrong, mask, chords)
    assert rec["median_ratio"] <= 0.4
    assert rec["verdict"] == "broken"
    # and it is NOT that the frame went flat: there is real contrast in there,
    # unlike the erased case, so a contrast measure would have passed it.
    assert wrong[mask].std() > 5 * _erased(img, mask)[mask].std() + 10


def test_scoring_reads_only_the_filled_region_it_was_asked_about():
    img, mask = _line_img(), _band()
    chords = L.build_layer(img, mask)
    a = L.score(img, mask, chords)
    far = img.copy()
    far[0:20, :] = 0
    b = L.score(far, mask, chords)
    assert a["median_ratio"] == pytest.approx(b["median_ratio"], abs=1e-9)


def test_a_partly_broken_fill_lands_between_the_two():
    img = _two_lines()
    mask = _band()
    chords = L.build_layer(img, mask)
    half = img.copy()
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    kill = (np.abs((yy + 30) - xx) <= 4.0) & mask
    half[kill] = 210
    rec = L.score(half, mask, chords)
    assert 0 < rec["intact_fraction"] < 1


def test_the_per_chord_detail_is_reported_for_a_human():
    img, mask = _line_img(), _band()
    rec = L.score(img, mask, L.build_layer(img, mask))
    assert len(rec["chords"]) == rec["n_chords"]
    c = rec["chords"][0]
    assert {"p0", "p1", "expected", "measured", "ratio"} <= set(c)


# ------------------------------------- carried through the stepped processing
def _marked(truth, mask):
    """The art with a watermark-like bar laid over the band."""
    out = truth.copy()
    out[mask] = (0.45 * out[mask].astype(np.float64) + 0.55 * 235).astype(np.uint8)
    return out


def test_the_schedule_records_a_line_verdict_for_every_step():
    truth = _line_img()
    mask = _band()
    marked = _marked(truth, mask)

    def _restore(crop_rgb, crop_mask_u8):
        return crop_rgb          # stand-in: the caller only writes the masked px

    out, plan = T.run_schedule(marked, mask, _restore, steps=3, lines=True)
    assert plan["n_chords"] >= 1
    assert len(plan["lines_per_step"]) == plan["steps_run"]
    for step in plan["lines_per_step"]:
        assert step["verdict"] in ("intact", "broken", "no-evidence")


def test_the_schedule_sees_a_fill_that_erases_the_art():
    """An inpainter that flattens the region must be visible in the record."""
    truth = _line_img()
    mask = _band()
    marked = _marked(truth, mask)

    def _erase(crop_rgb, crop_mask_u8):
        return np.full_like(crop_rgb, 210)

    def _keep(crop_rgb, crop_mask_u8):
        return crop_rgb

    _o1, wrecked = T.run_schedule(marked, mask, _erase, steps=3, lines=True)
    _o2, kept = T.run_schedule(marked, mask, _keep, steps=3, lines=True)
    assert wrecked["lines_per_step"] and kept["lines_per_step"]
    assert (wrecked["lines_per_step"][-1]["median_ratio"]
            < kept["lines_per_step"][-1]["median_ratio"])


def test_the_layer_is_off_unless_asked_for():
    truth = _line_img()
    mask = _band()

    def _keep(crop_rgb, crop_mask_u8):
        return crop_rgb

    _out, plan = T.run_schedule(_marked(truth, mask), mask, _keep, steps=2)
    assert plan["n_chords"] == 0
    assert plan["lines_per_step"] == []
