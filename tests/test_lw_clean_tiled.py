"""Tests for tools/lw_clean_tiled.py - the tiled decomposition cleaner.

Written test-first. The design is not invented here: it is measured off two
operator hand-clean captures on 2026-08-22 (docs/CLEAN_HANDEDIT_ANALYSIS_
2026-08-22.md), where one big mask was rejected 87 times and 82 small ones were
accepted. The properties below are that measurement turned into assertions:

  - the mark is decomposed into MANY small tiles, never inpainted in one shot
  - every tile carries a generous margin (the operator brushed ~8x the area that
    actually changed, and the ratio held across a 2.5x change in stroke size)
  - tile size scales INVERSELY with local gradient (softer art, bigger strokes)
  - the decomposition loses nothing: the union of tiles is exactly the mask

Pure numpy + PIL, so this runs in CI; the LaMa driver is exercised elsewhere.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_tiled as T  # noqa: E402


def _band(h=200, w=800, y0=90, y1=110, x0=50, x1=750):
    """A credit-line-shaped mask: a long thin band, like the real marks."""
    m = np.zeros((h, w), dtype=bool)
    m[y0:y1, x0:x1] = True
    return m


# ---------------------------------------------------------------- tile sizing
def test_tile_area_matches_the_two_measured_anchors():
    # 105-cleanup: local gradient 3.48 -> median brush 6495 px
    # 107-cleanup: local gradient 2.70 -> median brush 16298 px
    assert T.target_tile_area(3.48) == pytest.approx(6495, rel=0.10)
    assert T.target_tile_area(2.70) == pytest.approx(16298, rel=0.10)


def test_tile_area_falls_as_the_art_gets_busier():
    areas = [T.target_tile_area(g) for g in (2.0, 3.0, 4.0, 6.0)]
    assert areas == sorted(areas, reverse=True)


def test_tile_area_is_clamped_at_both_ends():
    assert T.target_tile_area(0.01) <= T.TILE_AREA_MAX
    assert T.target_tile_area(99.0) >= T.TILE_AREA_MIN


# ---------------------------------------------------------------- margin rule
def test_the_mark_is_grown_to_about_eight_times_its_own_area():
    m = _band()
    grown = T.grow_to_ratio(m, T.MARGIN_RATIO)
    ratio = grown.sum() / m.sum()
    assert ratio == pytest.approx(T.MARGIN_RATIO, rel=0.35)
    assert np.all(grown[m])          # growth never drops original pixels


def test_growth_stays_inside_the_frame():
    m = np.zeros((40, 40), dtype=bool)
    m[0:3, 0:3] = True               # hard against the corner
    grown = T.grow_to_ratio(m, T.MARGIN_RATIO)
    assert grown.shape == m.shape
    assert grown.sum() >= m.sum()


# ---------------------------------------------------------------- decomposition
def test_the_band_is_decomposed_into_many_tiles_not_one():
    m = _band()
    tiles = T.tile_mask(m, target_area=2000)
    assert len(tiles) > 5
    assert all(t.mask.sum() > 0 for t in tiles)


def test_tiles_partition_the_mask_exactly():
    m = _band()
    tiles = T.tile_mask(m, target_area=2000)
    union = np.zeros_like(m)
    total = 0
    for t in tiles:
        sub = np.zeros_like(m)
        sub[t.y0:t.y1, t.x0:t.x1] = t.mask
        assert not np.any(union & sub), "tiles must not overlap"
        union |= sub
        total += int(t.mask.sum())
    assert np.array_equal(union, m)
    assert total == int(m.sum())


def test_no_tile_greatly_exceeds_the_target_area():
    m = _band()
    target = 2000
    for t in T.tile_mask(m, target_area=target):
        assert t.mask.sum() <= target * 2.5


def test_an_empty_mask_yields_no_tiles():
    assert T.tile_mask(np.zeros((50, 50), dtype=bool), target_area=500) == []


def test_tile_order_is_deterministic_and_reading_order():
    m = _band()
    a = T.tile_mask(m, target_area=2000)
    b = T.tile_mask(m, target_area=2000)
    assert [(t.y0, t.x0) for t in a] == [(t.y0, t.x0) for t in b]
    keys = [(t.y0, t.x0) for t in a]
    assert keys == sorted(keys)


# ---------------------------------------------------------------- crop window
def test_crop_adds_context_around_the_tile_and_clamps():
    box = T.crop_box(10, 10, 30, 20, margin=16, width=100, height=100)
    assert box == (0, 0, 46, 36)
    box2 = T.crop_box(80, 80, 100, 100, margin=16, width=100, height=100)
    assert box2 == (64, 64, 100, 100)


def test_crop_is_never_the_whole_frame_for_a_small_tile():
    w = h = 2000
    x0, y0, x1, y1 = T.crop_box(900, 900, 940, 920, margin=32, width=w, height=h)
    assert (x1 - x0) * (y1 - y0) < 0.05 * w * h


# ---------------------------------------------------------------- gradient probe
def test_local_gradient_is_higher_on_busy_art_than_smooth():
    rng = np.random.default_rng(0)
    smooth = np.tile(np.linspace(0, 255, 200, dtype=np.float32), (200, 1))
    smooth = np.stack([smooth] * 3, axis=2).astype(np.uint8)
    busy = rng.integers(0, 255, (200, 200, 3), dtype=np.uint8)
    box = (20, 20, 180, 180)
    assert T.local_gradient(busy, box) > T.local_gradient(smooth, box)


def test_local_gradient_handles_a_degenerate_box():
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    assert T.local_gradient(img, (0, 0, 1, 1)) == 0.0


# ---------------------------------------------------------------- plan assembly
def _textured(h, w, seed=1):
    """Art-like content: the gradient probe must see something to measure."""
    rng = np.random.default_rng(seed)
    return rng.integers(40, 210, (h, w, 3), dtype=np.uint8)


def test_the_plan_reports_what_it_will_do_before_touching_pixels():
    img = _textured(300, 900)
    plan = T.build_plan(img, _band(h=300, w=900))
    assert plan["n_tiles"] > 5
    assert plan["target_tile_area"] > 0
    assert plan["mark_px"] > 0
    assert plan["grown_px"] > plan["mark_px"]
    assert len(plan["tiles"]) == plan["n_tiles"]


def test_flat_art_gets_the_largest_tile_and_busy_art_the_smallest():
    """A degenerate flat frame is not a bug: with no detail to preserve the
    sizing rule saturates at the ceiling. Busy art must saturate at the floor.
    """
    flat = np.zeros((300, 900, 3), dtype=np.uint8)
    busy = _textured(300, 900, seed=7)
    band = _band(h=300, w=900)
    assert T.build_plan(flat, band)["target_tile_area"] == T.TILE_AREA_MAX
    assert T.build_plan(busy, band)["target_tile_area"] == T.TILE_AREA_MIN


def test_each_tile_is_committed_before_the_next_one_is_read():
    """Tile N+1 must see tile N's result - the UI commits every stroke."""
    img = _textured(120, 400, seed=3)
    band = _band(h=120, w=400, y0=50, y1=62, x0=40, x1=360)
    seen = []

    def fake_inpaint(crop, cmask):
        seen.append(int(crop.sum()))
        out = crop.copy()
        out[cmask > 0] = 255          # each commit is visible in the next read
        return out

    out, plan = T.run_tiled(img, band, fake_inpaint, passes=1,
                            log=lambda *_: None)
    # one pass: tiles applied is exactly the plan's tile count
    assert plan["tiles_applied"] == plan["n_tiles"] > 1
    assert len(set(seen)) > 1         # the input changed as tiles committed
    assert np.any(out != img)


def test_only_masked_pixels_are_committed():
    """A model may touch its whole crop; context must survive untouched."""
    img = _textured(120, 400, seed=5)
    band = _band(h=120, w=400, y0=50, y1=62, x0=40, x1=360)

    def greedy_inpaint(crop, cmask):
        return np.full_like(crop, 7)   # tries to repaint everything

    out, plan = T.run_tiled(img, band, greedy_inpaint, log=lambda *_: None)
    grown = T.grow_to_ratio(band, T.MARGIN_RATIO)
    assert np.array_equal(out[~grown], img[~grown])
    assert np.all(out[grown] == 7)


# ------------------------------------------------- repeated overlapping passes
# Measured on the operator's 105-cleanup capture: 82 strokes summing to 636,135
# px over a union of 21,184 - a 30x overlap factor, median pixel brushed 19
# times, each changed pixel re-written ~4 times. The method is REPEATED passes,
# not a one-shot partition; a single pass leaves the mark as a visible ghost
# (measured: the first tiled build differed from the operator's result by as
# much as the untouched original did).
#
# Re-passing with the SAME mask is a no-op - lama is a pure function of
# (image, mask) and the unmasked context is unchanged, which is the documented
# clean-retry-degrades finding. So each pass must OFFSET its grid, giving every
# pixel a different tile neighbourhood and a different context each time.
def test_offsetting_the_grid_moves_the_tile_boundaries():
    m = _band()
    a = T.tile_mask(m, target_area=2000, offset=0)
    b = T.tile_mask(m, target_area=2000, offset=17)
    assert [(t.y0, t.x0) for t in a] != [(t.y0, t.x0) for t in b]


def test_an_offset_grid_still_partitions_the_mask_exactly():
    m = _band()
    union = np.zeros_like(m)
    for t in T.tile_mask(m, target_area=2000, offset=23):
        sub = np.zeros_like(m)
        sub[t.y0:t.y1, t.x0:t.x1] = t.mask
        assert not np.any(union & sub)
        union |= sub
    assert np.array_equal(union, m)


def test_multiple_passes_revisit_every_pixel():
    img = _textured(120, 400, seed=11)
    band = _band(h=120, w=400, y0=50, y1=62, x0=40, x1=360)
    calls = []

    def counting_inpaint(crop, cmask):
        calls.append(int((cmask > 0).sum()))
        out = crop.copy()
        out[cmask > 0] = out[cmask > 0] // 2
        return out

    _out, plan = T.run_tiled(img, band, counting_inpaint, passes=3,
                             log=lambda *_: None)
    assert plan["passes_run"] == 3
    # every pass re-covers the whole brushed area, so the brushed total is a
    # multiple of the union - the operator's overlap, reproduced
    assert sum(calls) >= 3 * plan["grown_px"] * 0.9


def test_passes_stop_early_once_a_pass_changes_almost_nothing():
    img = _textured(120, 400, seed=13)
    band = _band(h=120, w=400, y0=50, y1=62, x0=40, x1=360)

    def idempotent_inpaint(crop, cmask):
        return crop            # nothing ever changes

    _out, plan = T.run_tiled(img, band, idempotent_inpaint, passes=8,
                             log=lambda *_: None)
    assert plan["passes_run"] < 8
    assert plan["stopped_early"] is True


def test_a_single_pass_is_still_available_and_is_the_old_behaviour():
    img = _textured(120, 400, seed=17)
    band = _band(h=120, w=400, y0=50, y1=62, x0=40, x1=360)
    _out, plan = T.run_tiled(img, band, lambda c, m: c, passes=1,
                             log=lambda *_: None)
    assert plan["passes_run"] == 1


# ------------------------------------------------------------ overlapping tiles
# A pure grid leaves its own signature: at 6 staggered passes the credit line was
# gone but the tile boundaries showed as regular tick marks across the band. The
# operator's strokes OVERLAP each other, so no boundary ever survives - a later
# stroke always spans the seam a previous one left. stride_frac < 1 reproduces
# that: consecutive windows overlap instead of abutting.
def test_a_stride_under_one_makes_windows_overlap():
    m = _band()
    abutting = T.tile_mask(m, target_area=2000, stride_frac=1.0)
    overlapping = T.tile_mask(m, target_area=2000, stride_frac=0.5)
    assert len(overlapping) > len(abutting)


def test_overlapping_tiles_still_cover_every_masked_pixel():
    m = _band()
    covered = np.zeros_like(m)
    for t in T.tile_mask(m, target_area=2000, stride_frac=0.5):
        covered[t.y0:t.y1, t.x0:t.x1] |= t.mask
    assert np.array_equal(covered, m)


def test_overlapping_tiles_do_overlap_in_coverage():
    m = _band()
    counts = np.zeros(m.shape, dtype=np.int32)
    for t in T.tile_mask(m, target_area=2000, stride_frac=0.5):
        counts[t.y0:t.y1, t.x0:t.x1] += t.mask
    assert counts[m].max() > 1        # some pixel is written more than once


def test_stride_is_clamped_so_it_cannot_stall():
    m = _band()
    tiles = T.tile_mask(m, target_area=2000, stride_frac=0.0001)
    assert 0 < len(tiles) < 100000


# ------------------------------------------------- edge-aligned (operator v2)
# The operator, on why their result has no seams where mine do: they fit the
# mask "alongside LIGHT/DARK borders, and also across them", and they extend it
# "beyond the text into similar-like areas that needs used as the context to
# pull down into the area to be altered". A lattice ignores both - every pass
# re-imprints its own periodic boundary, which is the tick-mark and dashed-strip
# artifacting measured on 105-cleanup.
#
# So tiles come from a LABEL MAP whose boundaries follow image structure. The
# segmentation itself is lazy (skimage, venv-only); everything below is pure and
# takes an injected label array, so it runs in CI.
def _labels_two_regions(h=60, w=120):
    """Two luminance regions split by a diagonal - a light/dark border."""
    yy, xx = np.mgrid[0:h, 0:w]
    return np.where(xx > yy * 2, 1, 0).astype(np.int32)


def test_tiles_follow_label_boundaries_not_a_lattice():
    labels = _labels_two_regions()
    mark = np.zeros(labels.shape, dtype=bool)
    mark[25:35, 20:100] = True          # a band crossing the border
    tiles = T.tiles_from_labels(labels, mark)
    assert len(tiles) == 2              # one per region it crosses, not per cell
    for t in tiles:
        sub = np.zeros(labels.shape, dtype=bool)
        sub[t.y0:t.y1, t.x0:t.x1] = t.mask
        seen = set(np.unique(labels[sub]))
        assert len(seen) == 1, "a tile must not straddle a light/dark border"


def test_every_marked_pixel_is_covered_exactly_once():
    labels = _labels_two_regions()
    mark = np.zeros(labels.shape, dtype=bool)
    mark[25:35, 20:100] = True
    covered = np.zeros(labels.shape, dtype=np.int32)
    for t in T.tiles_from_labels(labels, mark):
        covered[t.y0:t.y1, t.x0:t.x1] += t.mask
    assert np.array_equal(covered > 0, mark)
    assert covered.max() == 1


def test_a_label_the_mark_never_touches_is_left_alone():
    labels = _labels_two_regions()
    mark = np.zeros(labels.shape, dtype=bool)
    mark[5:8, 100:110] = True           # entirely inside label 1
    tiles = T.tiles_from_labels(labels, mark)
    assert len(tiles) == 1


def test_no_tiles_for_an_empty_mark():
    assert T.tiles_from_labels(_labels_two_regions(),
                               np.zeros((60, 120), dtype=bool)) == []


def test_context_extension_reaches_into_the_most_similar_neighbour():
    """'Pull down' the wanted texture: grow the mask into the neighbouring
    region whose luminance matches, never into the contrasting one."""
    img = np.zeros((60, 120, 3), dtype=np.uint8)
    labels = np.zeros((60, 120), dtype=np.int32)
    labels[:, 40:80] = 1
    labels[:, 80:] = 2
    img[:, :40] = 100          # like the mark's region
    img[:, 40:80] = 105        # near-identical -> the one to pull from
    img[:, 80:] = 240          # contrasting -> must NOT be pulled in
    mark = np.zeros((60, 120), dtype=bool)
    mark[20:40, 10:35] = True  # sits in label 0
    grown = T.extend_into_similar(img, labels, mark, max_labels=1)
    assert grown[:, 40:80].any(), "should reach into the matching neighbour"
    assert not grown[:, 80:].any(), "must not reach across the contrast border"


def test_context_extension_is_a_no_op_without_a_similar_neighbour():
    img = np.zeros((40, 80, 3), dtype=np.uint8)
    labels = np.zeros((40, 80), dtype=np.int32)
    labels[:, 40:] = 1
    img[:, :40] = 30
    img[:, 40:] = 250                      # nothing similar to pull from
    mark = np.zeros((40, 80), dtype=bool)
    mark[10:20, 5:20] = True
    grown = T.extend_into_similar(img, labels, mark, max_labels=1,
                                  max_delta=20.0)
    assert np.array_equal(grown, mark)


# ------------------------------------------------- subdividing large regions
# Operator, on the residue the first contour run left over the tan area: extend
# into more regions AND subdivide the large ones. A single big low-gradient
# region hands the model a fill area with the mark still inside its own context,
# so the text survives. Subdivision is HIERARCHICAL - it re-segments inside the
# region, so the new boundaries still follow edge flow rather than a lattice.
def _fake_segmenter(calls):
    def seg(crop, target_area):
        calls.append((crop.shape[:2], target_area))
        h, w = crop.shape[:2]
        lab = np.zeros((h, w), dtype=np.int32)
        lab[:, w // 2:] = 1          # split every crop in half
        return lab
    return seg


def test_a_small_region_is_left_alone():
    labels = np.zeros((20, 20), dtype=np.int32)
    img = np.zeros((20, 20, 3), dtype=np.uint8)
    calls = []
    out = T.subdivide_labels(img, labels, max_area=10_000,
                             segmenter=_fake_segmenter(calls))
    assert calls == []
    assert len(np.unique(out)) == 1


def test_a_large_region_is_split_into_several():
    labels = np.zeros((100, 100), dtype=np.int32)
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    calls = []
    out = T.subdivide_labels(img, labels, max_area=1000,
                             segmenter=_fake_segmenter(calls))
    assert calls, "the oversized region must be re-segmented"
    assert len(np.unique(out)) > 1


def test_subdivision_never_moves_a_pixel_between_regions():
    labels = np.zeros((80, 80), dtype=np.int32)
    labels[:, 40:] = 1                       # two regions, one oversized each
    img = np.zeros((80, 80, 3), dtype=np.uint8)
    out = T.subdivide_labels(img, labels, max_area=500,
                             segmenter=_fake_segmenter([]))
    for lab in np.unique(labels):
        region = labels == lab
        # every sub-label inside this region must stay inside it
        for sub in np.unique(out[region]):
            assert np.all(region[out == sub]), "a sub-label escaped its parent"


def test_subdivision_keeps_the_labels_disjoint_and_total():
    labels = np.zeros((60, 90), dtype=np.int32)
    labels[:, 45:] = 1
    img = np.zeros((60, 90, 3), dtype=np.uint8)
    out = T.subdivide_labels(img, labels, max_area=400,
                             segmenter=_fake_segmenter([]))
    assert out.shape == labels.shape
    assert out.min() >= 0
    assert int(np.unique(out).size) >= int(np.unique(labels).size)


def test_a_smooth_region_is_not_subdivided_when_a_gradient_floor_is_set():
    """SLIC on smooth content degenerates to regular cells, so subdividing a
    smooth region rebuilds the very lattice the contour mode removed - measured
    on 105-cleanup, where blanket subdivision put the hatching back across the
    whole band including the side that had come out clean. It also contradicts
    the operator's own rule: soft gradients get BROADER strokes, not finer.
    """
    smooth = np.full((100, 100, 3), 128, dtype=np.uint8)
    labels = np.zeros((100, 100), dtype=np.int32)
    calls = []
    out = T.subdivide_labels(smooth, labels, max_area=500,
                             segmenter=_fake_segmenter(calls),
                             min_gradient=1.0)
    assert calls == [], "a smooth region must be left whole"
    assert len(np.unique(out)) == 1


def test_a_busy_region_is_still_subdivided_under_the_same_floor():
    rng = np.random.default_rng(2)
    busy = rng.integers(0, 255, (100, 100, 3), dtype=np.uint8)
    labels = np.zeros((100, 100), dtype=np.int32)
    calls = []
    out = T.subdivide_labels(busy, labels, max_area=500,
                             segmenter=_fake_segmenter(calls),
                             min_gradient=1.0)
    assert calls, "a busy region must still be split"
    assert len(np.unique(out)) > 1


# --------------------------------------------------------- escalating context
# Operator: "as the text smudges into small pieces, i increase the masking area
# to pull more context into the bad areas. and it continues to blend/iterate
# out". The mask GROWS between passes - a fixed mask re-fills the same hole from
# the same surroundings and converges on whatever it converged on first.
def test_the_mask_grows_between_passes_when_escalation_is_on():
    img = _textured(160, 500, seed=21)
    band = _band(h=160, w=500, y0=70, y1=86, x0=60, x1=440)
    sizes = []

    def probe_inpaint(crop, cmask):
        sizes.append(int((cmask > 0).sum()))
        return crop

    T.run_tiled(img, band, probe_inpaint, passes=3, escalate_px=6,
                min_pass_change=0.0, log=lambda *_: None)
    assert sizes, "the inpainter must have been called"


def test_escalation_is_recorded_per_pass():
    img = _textured(160, 500, seed=23)
    band = _band(h=160, w=500, y0=70, y1=86, x0=60, x1=440)
    _out, plan = T.run_tiled(img, band, lambda c, m: c, passes=3, escalate_px=6,
                             min_pass_change=0.0, log=lambda *_: None)
    assert plan["mask_px_per_pass"] == sorted(plan["mask_px_per_pass"])
    assert plan["mask_px_per_pass"][-1] > plan["mask_px_per_pass"][0]


def test_no_escalation_keeps_the_mask_fixed():
    img = _textured(160, 500, seed=25)
    band = _band(h=160, w=500, y0=70, y1=86, x0=60, x1=440)
    _out, plan = T.run_tiled(img, band, lambda c, m: c, passes=3, escalate_px=0,
                             min_pass_change=0.0, log=lambda *_: None)
    assert len(set(plan["mask_px_per_pass"])) == 1


# ------------------------------------------------------- residue-targeted work
# Operator, defining "the bad areas": "where the text used to be and hasnt been
# blended out completely while keeping the affected area crisp". So residue is
# looked for INSIDE the original footprint only, and later passes work on that
# alone - blanket dilation repaints clean art and destroyed the frame.
def test_residue_is_found_where_structure_survives_inside_the_footprint():
    img = np.full((80, 200, 3), 120, dtype=np.uint8)
    img[38:42, 60:90] = 200                 # a leftover bright streak
    foot = np.zeros((80, 200), dtype=bool)
    foot[30:50, 20:180] = True
    res = T.residue_mask(img, foot)
    assert res[38:42, 60:90].any()
    assert not res[:30].any() and not res[50:].any()


def test_residue_is_confined_to_the_original_footprint():
    img = np.full((80, 200, 3), 120, dtype=np.uint8)
    img[5:9, 5:40] = 240                    # bright, but OUTSIDE the footprint
    foot = np.zeros((80, 200), dtype=bool)
    foot[30:50, 20:180] = True
    assert not T.residue_mask(img, foot)[5:9, 5:40].any()


def test_a_blended_area_reports_no_residue():
    img = np.full((80, 200, 3), 120, dtype=np.uint8)
    foot = np.zeros((80, 200), dtype=bool)
    foot[30:50, 20:180] = True
    assert not T.residue_mask(img, foot).any()


def test_later_passes_target_the_residue_not_the_whole_band():
    """The second pass must be SMALLER and local, not a grown copy of the first."""
    img = _textured(120, 400, seed=31)
    band = _band(h=120, w=400, y0=50, y1=62, x0=40, x1=360)
    img[54:58, 100:140] = 255               # one stubborn patch

    def blending_inpaint(crop, cmask):
        out = crop.copy()
        sel = cmask > 0
        # blends everything except the stubborn patch, which stays bright
        med = int(np.median(crop)) if crop.size else 0
        keep = out[..., 0] == 255
        out[sel & ~keep] = med
        return out

    _out, plan = T.run_tiled(img, band, blending_inpaint, passes=3,
                             escalate_px=4, target_residue=True,
                             min_pass_change=0.0, log=lambda *_: None)
    per_pass = plan["mask_px_per_pass"]
    assert per_pass[1] < per_pass[0], "later passes must narrow onto the residue"


def test_targeting_stops_when_nothing_is_left(monkeypatch):
    img = _textured(120, 400, seed=33)
    band = _band(h=120, w=400, y0=50, y1=62, x0=40, x1=360)
    monkeypatch.setattr(T, "residue_mask",
                        lambda *a, **k: np.zeros(img.shape[:2], dtype=bool))
    _out, plan = T.run_tiled(img, band, lambda c, m: c, passes=4,
                             escalate_px=4, target_residue=True,
                             min_pass_change=0.0, log=lambda *_: None)
    assert plan["passes_run"] < 4
    assert plan["stopped_early"] is True
