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
