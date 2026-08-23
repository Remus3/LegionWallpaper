"""Tests for tools/lw_clean_heal.py - the healing-brush fill (track E).

Written test-first. The design is the operator's own words on 2026-08-22 - "like
photoshops healing brush" - turned into properties. A healing brush is exemplar
texture plus GRADIENT-DOMAIN (Poisson) reconciliation, not learned inpainting,
and that choice is only worth making if these hold:

  - the seam vanishes BY CONSTRUCTION: the solve is Dirichlet on the hole
    boundary, so the filled region meets its surroundings exactly
  - LINES continue: given content that repeats under some translation, the
    exemplar search finds that translation and the structure carries through
    the hole. This is the exact defect that got 45 candidates rejected.
  - it is DETERMINISTIC: no learned prior, so "phantom context" cannot appear
  - nothing outside the mask moves, ever (the standing cleaning-lane assertion)
  - on smooth art there is no texture worth importing and the solver degrades to
    a membrane fill - which is what 209-cleanup (one stroke, smooth panel) is

Pure numpy + Pillow, no scipy/cv2/torch, so this runs in the fast CI lane.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_heal as H  # noqa: E402


# ------------------------------------------------------------------- fixtures
def _ramp(h=120, w=160):
    """A smooth two-axis ramp: no texture at all, the 209-cleanup shape."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    v = 40.0 + 0.6 * yy + 0.5 * xx
    return np.clip(np.dstack([v, v * 0.9, v * 0.8]), 0, 255).astype(np.uint8)


def _stripes(h=120, w=160, period=12):
    """Vertical stripes: content that repeats under a known translation."""
    xx = np.mgrid[0:h, 0:w][1]
    v = np.where((xx % period) < period // 2, 60.0, 200.0)
    return np.dstack([v, v, v]).astype(np.uint8)


def _diagonal_line(h=120, w=160):
    """A dark diagonal stroke on a light field - an art LINE to be preserved."""
    img = np.full((h, w, 3), 210, dtype=np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]
    on = np.abs((yy - 10) - xx) <= 1.5
    img[on] = 30
    return img


def _band(h=120, w=160, y0=54, y1=66, x0=20, x1=140):
    m = np.zeros((h, w), dtype=bool)
    m[y0:y1, x0:x1] = True
    return m


# --------------------------------------------------- the hard identity contract
def test_nothing_outside_the_mask_ever_moves():
    img = _stripes()
    mask = _band()
    out, _ = H.heal(img, mask)
    assert out.shape == img.shape and out.dtype == img.dtype
    assert np.array_equal(out[~mask], img[~mask])


def test_empty_mask_is_a_no_op():
    img = _stripes()
    out, info = H.heal(img, np.zeros(img.shape[:2], dtype=bool))
    assert np.array_equal(out, img)
    assert info["tiles"] == 0


def test_the_fill_is_deterministic():
    img = _diagonal_line()
    mask = _band()
    a, _ = H.heal(img, mask)
    b, _ = H.heal(img, mask)
    assert np.array_equal(a, b)


# ---------------------------------------------------------- the Poisson solver
def test_membrane_fill_reconstructs_a_smooth_ramp():
    """No guidance field: the harmonic solution IS the ramp, to within a level."""
    img = _ramp()
    mask = _band()
    out = H.poisson_fill(img, mask, offset=None)
    err = np.abs(out[mask].astype(int) - img[mask].astype(int))
    assert err.max() <= 1


def test_exemplar_fill_reconstructs_a_repeating_texture():
    """Guidance from the true period puts the stripes back where they were."""
    img = _stripes(period=12)
    mask = _band()
    out = H.poisson_fill(img, mask, offset=(0, 12))
    err = np.abs(out[mask].astype(int) - img[mask].astype(int))
    assert err.mean() <= 2.0


def test_the_solve_leaves_no_seam_at_the_hole_boundary():
    """A wrong-tone exemplar must still meet the boundary exactly.

    This is the property that distinguishes a heal from a paste: the source is
    120 levels darker than the destination and the result may not show a step.
    """
    img = _stripes()
    mask = _band()
    dark = img.astype(np.int16) - 120
    src = np.clip(dark, 0, 255).astype(np.uint8)
    out = H.poisson_fill(img, mask, offset=(0, 12), source=src)
    pasted = img.copy()
    pasted[mask] = np.roll(src, -12, axis=1)[mask]

    def _step(a):
        return float(np.abs(a[54, 20:140].astype(int)
                            - a[53, 20:140].astype(int)).mean())

    assert _step(pasted) > 40.0, "the paste must actually show a step"
    assert _step(out) <= 0.25 * _step(pasted)


def test_a_hole_touching_the_image_border_still_solves():
    img = _ramp()
    mask = np.zeros(img.shape[:2], dtype=bool)
    mask[0:8, 0:20] = True
    out, _ = H.heal(img, mask)
    assert np.array_equal(out[~mask], img[~mask])
    assert np.isfinite(out[mask].astype(float)).all()


# ------------------------------------------------------------ exemplar search
def test_the_search_finds_the_translation_that_repeats_the_content():
    img = _stripes(period=12)
    mask = _band()
    off, rec = H.search_source(img, mask, mask, radius=40)
    assert off is not None
    dy, dx = off
    # the stripes are invariant in y, so any dy is right and dx must land on
    # the period; a full-width band cannot be sourced from its own row.
    assert dx % 12 == 0
    assert abs(dy) >= 12
    assert rec["ring_rmse"] < 5.0


def test_the_search_never_sources_from_inside_the_mark():
    """A source patch overlapping the mark would paint the mark back in."""
    img = _stripes(period=12)
    mask = _band()
    off, _ = H.search_source(img, mask, mask, radius=40)
    dy, dx = off
    shifted = np.zeros_like(mask)
    ys, xs = np.nonzero(mask)
    yy, xx = ys + dy, xs + dx
    ok = (yy >= 0) & (yy < mask.shape[0]) & (xx >= 0) & (xx < mask.shape[1])
    shifted[yy[ok], xx[ok]] = True
    assert not (shifted & mask).any()


def test_smooth_art_takes_the_membrane_mode_not_an_exemplar():
    """209-cleanup: a signature on a smooth panel. There is no texture to pull."""
    img = _ramp()
    mask = _band()
    _out, info = H.heal(img, mask)
    assert {t["mode"] for t in info["steps"]} == {"membrane"}


def test_textured_art_never_takes_the_membrane_mode():
    """Measured on 105-cleanup: on textured art a membrane fill is a smear.

    The first version rejected any exemplar whose ring match was not good, and
    real painted art does not repeat exactly, so every tile fell back to
    membrane and the fabric was lost. An imperfect exemplar is the better of
    the two available answers here, and there is no third one.
    """
    img = _stripes(period=12)
    mask = _band()
    _out, info = H.heal(img, mask)
    assert all(t["mode"] != "membrane" for t in info["steps"])


def test_the_fill_keeps_the_detail_of_the_art_it_replaces():
    """The smear test. A blur would drop the variance; a heal must not."""
    img = _stripes(period=12)
    mask = _band()
    out, _ = H.heal(img, mask)
    inside = out[mask].astype(np.float64).std()
    outside = img[~mask].astype(np.float64).std()
    assert inside >= 0.5 * outside


def test_a_thin_mark_pulls_from_both_of_its_sides():
    """A credit line is explained by what is above AND below it, not one side."""
    img = _stripes(period=12)
    mask = _band()
    _out, info = H.heal(img, mask)
    step = info["steps"][0]
    assert step["mode"] == "two-sided"
    a, b = step["offset"], step["offset2"]
    axis = H.tile_axis(mask)
    assert axis is not None
    pa = a[0] * axis[0] + a[1] * axis[1]
    pb = b[0] * axis[0] + b[1] * axis[1]
    assert pa * pb < 0, "both sources came from the same side of the mark"


def test_a_round_blob_has_no_preferred_axis():
    mask = np.zeros((120, 160), dtype=bool)
    mask[50:70, 60:80] = True
    assert H.tile_axis(mask) is None


# ------------------------------------------------------- the line-continuity bar
def test_a_line_crossing_the_mark_is_carried_through_it():
    """The rejection reason, made into an assertion.

    A diagonal stroke crosses a credit-line-shaped mark. After healing, the
    pixels the line WOULD have occupied must be dark, and the ones beside it
    must not be - i.e. the line continues, and it continues in the right place.
    """
    img = _diagonal_line()
    mask = _band()
    out, _ = H.heal(img, mask)
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    on_line = (np.abs((yy - 10) - xx) <= 1.0) & mask
    off_line = (np.abs((yy - 10) - xx) >= 4.0) & mask
    assert on_line.sum() > 5
    assert out[on_line].mean() < 110
    assert out[off_line].mean() > 170


# -------------------------------------------------------------------- tiling
def test_tiles_partition_the_mask_exactly():
    mask = _band(x0=5, x1=155)
    tiles = H.plan_tiles(mask, target_area=400)
    union = np.zeros_like(mask)
    for t in tiles:
        assert not (union & t).any(), "tiles overlap"
        union |= t
    assert np.array_equal(union, mask)


def test_a_long_band_is_decomposed_not_filled_in_one_shot():
    mask = _band(x0=5, x1=155)
    tiles = H.plan_tiles(mask, target_area=400)
    assert len(tiles) >= 3
    assert max(int(t.sum()) for t in tiles) <= 400 * 2


def test_separate_blobs_never_share_a_tile():
    mask = np.zeros((120, 160), dtype=bool)
    mask[20:30, 20:30] = True
    mask[80:90, 120:130] = True
    tiles = H.plan_tiles(mask, target_area=10000)
    assert len(tiles) == 2
