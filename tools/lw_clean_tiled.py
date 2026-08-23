"""Tiled decomposition cleaner - the operator's hand method, in code.

WHY THIS EXISTS. On 2026-08-22 every automated cleaning candidate produced for
the 87-slug QA queue was rejected by the operator - 4 review rounds, 3 different
mask sources, both fill decisions, zero accepted. The operator then hand-cleaned
two slugs in the IOPaint UI and saved all 128 iterations, and the measurement
(docs/CLEAN_HANDEDIT_ANALYSIS_2026-08-22.md) said the failure was never the mask
quality:

  operator, 105-cleanup : 82 strokes, median 6,495 px each (0.18% of frame)
  automated lane, same slug: ONE mask of ~36,800 px, larger than the operator's
                             entire 82-step cumulative edit, applied at once

IOPaint logs `Run crop strategy` on every call: it crops tight around the brush
mask, so the model only ever sees local context and returns local texture. A mask
covering a big region throws that away, and the result is the blur, the smudging
and the misaligned lines the operator rejected 87 times.

So this module does not try to build a better mask. It decomposes the mark into
many small tiles and inpaints them one at a time with a tight crop, committing as
it goes - the loop the operator performs by hand.

THREE MEASURED CONSTANTS, not guesses (n=2 captures - a direction to re-measure
as more land, not a law):

  MARGIN_RATIO 8.0   - LaMa changed ~12% of what the operator brushed in BOTH
                       captures (0.118 and 0.122) across a 2.5x change in stroke
                       size. A mask that hugs the glyph is not the method.
  tile area          - inverse in local gradient, fitted through the two anchors
                       (gradient 3.48 -> 6,495 px; 2.70 -> 16,298 px). Softer art
                       tolerates bigger strokes, which is what the operator said
                       and what the frames show.
  crop margin        - context around each tile, so LaMa fills a hole it can see
                       around rather than inventing a region.

IMPORT DISCIPLINE mirrors lw_clean_iopaint: stdlib + numpy + PIL at module level
(all CI-safe); torch / simple_lama arrive lazily inside the driver, so the pure
geometry above is tested everywhere.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

Image.MAX_IMAGE_PIXELS = None

# Fitted through the two measured anchors: area = A * exp(-K * gradient).
TILE_FIT_A = 394000.0
TILE_FIT_K = 1.1799
TILE_AREA_MIN = 2000.0
TILE_AREA_MAX = 40000.0

# The operator brushed ~8x the area that actually changed, in both captures.
MARGIN_RATIO = 8.0

# Context ring around each tile handed to the model. Kept well under the tile
# size so the crop stays local - the whole point of the decomposition.
CROP_MARGIN = 32

DEFAULT_PASSES = 6
# Overlapping windows by default: an abutting grid signs its own boundaries
# into the result (measured - regular tick marks across the cleaned band).
STRIDE_FRAC = 0.5
MIN_PASS_CHANGE = 0.002      # fraction of the brushed area; below this, stop


@dataclass
class Tile:
    """One brush-sized piece of the mark, with its own submask."""
    y0: int
    x0: int
    y1: int
    x1: int
    mask: np.ndarray = field(repr=False)


def target_tile_area(gradient):
    """Tile area in pixels for art of this local gradient (inverse, clamped)."""
    g = max(0.0, float(gradient))
    area = TILE_FIT_A * math.exp(-TILE_FIT_K * g)
    return float(min(TILE_AREA_MAX, max(TILE_AREA_MIN, area)))


def _dilate1(mask):
    """One 3x3 binary dilation, pure numpy (no cv2 in the CI-safe layer)."""
    out = mask.copy()
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out


def grow_to_ratio(mask, ratio=MARGIN_RATIO, max_iter=64):
    """Grow the mark until it covers ~`ratio` times its own area.

    The margin is the measured part of the operator's method, not padding for
    its own sake: it is what lets the model see the mark's soft edge and the
    art on both sides of it.
    """
    mask = np.asarray(mask, dtype=bool)
    base = int(mask.sum())
    if base == 0:
        return mask.copy()
    target = base * float(ratio)
    cur = mask.copy()
    for _ in range(max_iter):
        if cur.sum() >= target:
            break
        nxt = _dilate1(cur)
        if int(nxt.sum()) == int(cur.sum()):   # saturated against the frame
            break
        cur = nxt
    return cur


def tile_mask(mask, target_area, offset=0, stride_frac=1.0):
    """Split a mask into reading-order tiles of roughly `target_area` pixels.

    Grid partition: deterministic, non-overlapping, and lossless (the union of
    the tiles is exactly the input mask). A grid is the honest shape here - the
    marks are text bands, and the operator's strokes walk along them.

    `stride_frac` < 1 makes consecutive windows OVERLAP by that fraction
    instead of abutting; `offset` shifts the grid origin. Successive passes MUST use different
    offsets: re-running an identical mask is a no-op (lama is a pure function of
    image and mask, and the unmasked context has not moved), so a re-pass only
    does work when the tile boundaries - and therefore each pixel's context -
    have moved.
    """
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        return []
    step = max(1, int(round(math.sqrt(max(1.0, float(target_area))))))
    h, w = mask.shape
    frac = min(1.0, max(0.05, float(stride_frac)))
    if frac >= 1.0:
        # Abutting grid: a strict partition, offset by `offset`.
        off = int(offset) % step
        starts_y = ([0] if off else []) + list(range(off, h, step))
        starts_x = ([0] if off else []) + list(range(off, w, step))
        spans_y = [(y0, off if (y0 == 0 and off) else min(h, y0 + step))
                   for y0 in starts_y]
        spans_x = [(x0, off if (x0 == 0 and off) else min(w, x0 + step))
                   for x0 in starts_x]
    else:
        # Overlapping windows: consecutive tiles share area, so no boundary
        # survives - a later tile always spans the seam an earlier one left.
        stride = max(1, int(round(step * frac)))
        off = int(offset) % stride
        spans_y = [(y0, min(h, y0 + step)) for y0 in range(off - stride, h, stride)
                   if min(h, y0 + step) > max(0, y0)]
        spans_x = [(x0, min(w, x0 + step)) for x0 in range(off - stride, w, stride)
                   if min(w, x0 + step) > max(0, x0)]
        spans_y = [(max(0, a), b) for a, b in spans_y if b > max(0, a)]
        spans_x = [(max(0, a), b) for a, b in spans_x if b > max(0, a)]
    tiles = []
    for y0, y1 in spans_y:
        for x0, x1 in spans_x:
            if y1 <= y0 or x1 <= x0:
                continue
            sub = mask[y0:y1, x0:x1]
            if sub.any():
                tiles.append(Tile(y0=y0, x0=x0, y1=y1, x1=x1, mask=sub.copy()))
    return tiles


def _box_mean(g, k):
    """Mean over a (2k+1) box, via an integral image. Pure numpy, O(n)."""
    pad = np.pad(g, k + 1, mode="edge")
    ii = pad.cumsum(axis=0).cumsum(axis=1)
    h, w = g.shape
    y0 = np.arange(h)
    x0 = np.arange(w)
    yy0, xx0 = np.meshgrid(y0, x0, indexing="ij")
    a = ii[yy0, xx0]
    b = ii[yy0, xx0 + 2 * k + 1]
    c = ii[yy0 + 2 * k + 1, xx0]
    d = ii[yy0 + 2 * k + 1, xx0 + 2 * k + 1]
    area = float((2 * k + 1) ** 2)
    return (d - b - c + a) / area


def residue_mask(img, footprint, thr=10.0, k=9):
    """Where the mark USED to be and still has not blended out.

    The operator's definition of the bad areas: "where the text used to be and
    hasnt been blended out completely while keeping the affected area crisp".
    Two consequences, both load-bearing:

      - the search is confined to the ORIGINAL footprint, so a later pass can
        never wander into clean art (a blanket dilation did exactly that and
        destroyed the frame);
      - it looks for surviving local STRUCTURE, not for a colour: leftover
        glyph fragments stand off their surroundings, blended fill does not.
    """
    foot = np.asarray(footprint, dtype=bool)
    if not foot.any():
        return np.zeros(foot.shape, dtype=bool)
    g = np.asarray(img, dtype=np.float32)
    if g.ndim == 3:
        g = g.mean(axis=2)
    dev = np.abs(g - _box_mean(g, k))
    return foot & (dev > float(thr))


def tiles_from_labels(labels, mark):
    """One tile per labelled region the mark touches - boundaries ON contours.

    The operator's rule, in their words: fit the mask "alongside LIGHT/DARK
    borders, and also across them". A lattice ignores image structure, so every
    pass re-imprints its own periodic boundary - measured as tick marks and a
    dashed strip on 105-cleanup. A tile that stops at a contour puts its seam
    where the picture already has one.
    """
    labels = np.asarray(labels)
    mark = np.asarray(mark, dtype=bool)
    if not mark.any():
        return []
    tiles = []
    for lab in np.unique(labels[mark]):
        sel = mark & (labels == lab)
        bb = mask_bbox(sel)
        if bb is None:
            continue
        x0, y0, x1, y1 = bb
        tiles.append(Tile(y0=y0, x0=x0, y1=y1, x1=x1,
                          mask=sel[y0:y1, x0:x1].copy()))
    return tiles


def _neighbour_labels(labels, region):
    """Labels adjacent to the REGIONS the mark sits in, excluding those regions.

    Adjacency is taken from the containing segments, not from the mark blob: a
    credit line sits well inside one contour region, so dilating the glyphs
    themselves finds only their own label and the reach finds nothing. The
    operator reaches out of the region the text is on, into the next one along.
    """
    labels = np.asarray(labels)
    own = set(np.unique(labels[region]).tolist())
    own_region = np.isin(labels, list(own))
    ring = _dilate1(own_region) & ~own_region
    return [int(v) for v in np.unique(labels[ring]) if int(v) not in own]


def extend_into_similar(img, labels, mark, max_labels=2, max_delta=18.0):
    """Reach into neighbouring regions of MATCHING luminance, never across.

    The operator: they go "beyond the text into similar-like areas that needs
    used as the context to pull down into the area to be altered". The reach is
    what supplies the fill its texture; crossing a contrast border instead drags
    the wrong material in, which is the smearing this whole lane failed on.
    """
    labels = np.asarray(labels)
    mark = np.asarray(mark, dtype=bool)
    if not mark.any():
        return mark.copy()
    g = np.asarray(img, dtype=np.float32)
    if g.ndim == 3:
        g = g.mean(axis=2)
    base = float(g[mark].mean())
    out = mark.copy()
    cands = []
    for lab in _neighbour_labels(labels, mark):
        sel = labels == lab
        if not sel.any():
            continue
        delta = abs(float(g[sel].mean()) - base)
        if delta <= max_delta:
            cands.append((delta, lab, sel))
    for _delta, _lab, sel in sorted(cands, key=lambda c: c[0])[:max(0, int(max_labels))]:
        out |= sel
    return out


def subdivide_labels(img, labels, max_area, segmenter=None,
                     min_gradient=None, exclude=None):
    """Re-segment any region larger than `max_area`, hierarchically.

    A single large low-gradient region hands the model a fill area with the mark
    still sitting inside its own context, and the text survives - measured as
    residue over the tan half of 105-cleanup after the first contour run. The
    split is done by re-segmenting INSIDE the region, so the new boundaries keep
    following edge flow instead of falling back to a lattice.

    `min_gradient` gates it: a region flatter than this is left WHOLE. SLIC on
    smooth content degenerates to regular cells, so subdividing a smooth region
    rebuilds the lattice the contour mode exists to avoid - measured, it put the
    hatching back across the whole band. It also contradicts the operator's own
    rule that soft gradients take BROADER strokes, not finer ones.

    `segmenter(crop_rgb, target_area) -> label array` is injectable, so the
    bookkeeping here is testable without skimage.
    """
    labels = np.asarray(labels)
    img = np.asarray(img)
    seg = segmenter or segment_contours
    out = np.zeros_like(labels)
    nxt = 0
    for lab in np.unique(labels):
        region = labels == lab
        area = int(region.sum())
        if area <= max_area:
            out[region] = nxt
            nxt += 1
            continue
        bb = mask_bbox(region)
        x0, y0, x1, y1 = bb
        crop = img[y0:y1, x0:x1]
        # `exclude` is the mark: this gate reads a region OF the footprint, so
        # without it the measure is taken almost entirely on the mark and the
        # gate subdivides flat art it was written to leave whole (track A).
        if (min_gradient is not None
                and local_gradient(img, bb, pad=0, exclude=exclude) < min_gradient):
            out[region] = nxt
            nxt += 1
            continue
        sub = np.asarray(seg(crop, max_area))
        local = region[y0:y1, x0:x1]
        for s in np.unique(sub[local]):
            piece = local & (sub == s)
            if not piece.any():
                continue
            target = out[y0:y1, x0:x1]
            target[piece] = nxt
            out[y0:y1, x0:x1] = target
            nxt += 1
    return out


def segment_contours(img, target_area, compactness=8.0):
    """Label map whose boundaries follow edge flow (SLIC, lazily imported).

    skimage lives only in the lw-clean venv, so the import stays inside the
    function and every pure consumer above is testable in CI.
    """
    from skimage.segmentation import slic
    arr = np.asarray(img)
    n = max(2, int(round(arr.shape[0] * arr.shape[1] / max(1.0, float(target_area)))))
    return slic(arr, n_segments=n, compactness=compactness, start_label=0,
                channel_axis=2)


def crop_box(x0, y0, x1, y1, margin, width, height):
    """Context window around one tile, clamped to the frame."""
    return (max(0, int(x0) - margin), max(0, int(y0) - margin),
            min(int(width), int(x1) + margin), min(int(height), int(y1) + margin))


def local_gradient(img, box, pad=24, exclude=None):
    """Mean absolute first difference around `box` - the busyness measure.

    Same estimator used to fit the tile-size anchors, so the calibration and the
    runtime probe cannot drift apart: with `exclude` unset this is bit-identical
    to the version those anchors were fitted with.

    `exclude` drops a mask's pixels from the statistic. A difference is counted
    only when BOTH its endpoints are readable, so no excluded value reaches the
    result through either end of a gradient. This matters because the caller is
    usually asking "how busy is the art I am about to fill", holding a frame
    that still carries the mark: measured on the four hand-clean captures the
    unexcluded answer is wrong by 221% on average and 603% at worst, and it
    slams the two SMOOTHEST images into the minimum tile size because their
    marks are the loudest thing in frame. Policy (halo dilation, widening a
    window the mark fills) lives in `lw_clean_behind`.
    """
    x0, y0, x1, y1 = box
    h, w = img.shape[:2]
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(w, x1 + pad)
    y1 = min(h, y1 + pad)
    g = np.asarray(img[y0:y1, x0:x1], dtype=np.float32)
    if g.ndim == 3:
        g = g.mean(axis=2)
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0
    dx = np.abs(np.diff(g, axis=1))
    dy = np.abs(np.diff(g, axis=0))
    if exclude is None or not np.any(exclude):
        return (float(dx.mean()) + float(dy.mean())) / 2.0
    valid = ~np.asarray(exclude, dtype=bool)[y0:y1, x0:x1]
    okx = valid[:, :-1] & valid[:, 1:]
    oky = valid[:-1, :] & valid[1:, :]
    gx = float(dx[okx].mean()) if okx.any() else 0.0
    gy = float(dy[oky].mean()) if oky.any() else 0.0
    return (gx + gy) / 2.0


def mask_bbox(mask):
    """Bounding box of a boolean mask, or None when it is empty."""
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def build_plan(img, mark_mask, margin_ratio=MARGIN_RATIO,
               stride_frac=STRIDE_FRAC, gradient=None):
    """Decide the whole decomposition BEFORE any pixel is written.

    Returned as data so a dry run can be reviewed, logged and diffed against the
    operator's own captures without spending the GPU.

    The busyness that sets the tile size EXCLUDES the mark by default (track A).
    Pass `gradient` to override it with a policy-computed value - see
    `lw_clean_behind.local_gradient_behind`, which also dilates for the mark's
    halo and widens a window the mark fills.
    """
    mark = np.asarray(mark_mask, dtype=bool)
    bbox = mask_bbox(mark)
    if gradient is not None:
        grad = float(gradient)
    else:
        grad = local_gradient(img, bbox, exclude=mark) if bbox else 0.0
    area = target_tile_area(grad)
    grown = grow_to_ratio(mark, margin_ratio)
    tiles = tile_mask(grown, area, stride_frac=stride_frac)
    return {
        "mark_px": int(mark.sum()),
        "grown_px": int(grown.sum()),
        "mark_bbox": list(bbox) if bbox else None,
        "local_gradient": round(grad, 4),
        "target_tile_area": round(area, 1),
        "n_tiles": len(tiles),
        "tiles": [[t.x0, t.y0, t.x1, t.y1, int(t.mask.sum())] for t in tiles],
        "grown": grown,
    }


def run_tiled(img, mark_mask, inpaint, margin_ratio=MARGIN_RATIO,
              crop_margin=CROP_MARGIN, passes=DEFAULT_PASSES,
              min_pass_change=MIN_PASS_CHANGE, stride_frac=STRIDE_FRAC,
              labels=None, escalate_px=0, target_residue=False,
              log=print):
    """Inpaint tile by tile over REPEATED staggered passes, committing as it goes.

    `inpaint(crop_rgb, crop_mask_u8) -> filled_rgb` is injected, so ordering,
    commit discipline and convergence are testable without a GPU.

    Two properties, both measured off the operator's capture rather than chosen:

    COMMIT PER TILE - tile N+1 must see tile N's result, as the UI does.

    REPEATED PASSES - the operator's 82 strokes summed to 636,135 px over a union
    of 21,184 (30x overlap; median pixel brushed 19 times; each changed pixel
    re-written ~4 times). A single pass over each area leaves the mark as a
    visible ghost - measured: the first single-pass build differed from the
    operator's result by as much as the untouched original did. Each pass shifts
    the grid, because an identical mask over unchanged context is a no-op.
    """
    plan = build_plan(img, mark_mask, margin_ratio, stride_frac)
    grown = plan.pop("grown")
    footprint = np.asarray(mark_mask, dtype=bool)
    # The reach a residue pass may ever use: the footprint plus the same margin
    # the first pass had. Nothing outside this is ever touched again.
    footprint_grown = grow_to_ratio(footprint, margin_ratio * 2.0)
    cur = np.array(img, dtype=np.uint8, copy=True)
    base = np.asarray(img, dtype=np.uint8)
    h, w = cur.shape[:2]
    step = max(1, int(round(math.sqrt(plan["target_tile_area"]))))
    total_tiles = 0
    passes_run = 0
    mask_px_per_pass = []
    stopped_early = False
    per_pass = []
    for p in range(max(1, int(passes))):
        before = cur.copy()
        offset = (p * step) // max(1, int(passes))
        if p and (escalate_px or target_residue):
            # The operator, on what a pass leaves behind: "as the text smudges
            # into small pieces, i increase the masking area to pull more
            # context into the bad areas. and it continues to blend/iterate
            # out". A fixed mask re-fills the same hole from the same
            # surroundings and converges on whatever it converged on first.
            if target_residue:
                # ...and the bad areas are "where the text used to be and hasnt
                # been blended out completely". Later passes work ONLY there,
                # so clean art stays crisp - a blanket dilation repainted 30px
                # beyond the mark and destroyed the frame.
                res = residue_mask(cur, footprint)
                if not res.any():
                    stopped_early = True
                    log("LW TILED: no residue left inside the footprint - done")
                    break
                for _ in range(int(escalate_px)):
                    res = _dilate1(res)
                grown = res & footprint_grown
            else:
                for _ in range(int(escalate_px)):
                    grown = _dilate1(grown)
        mask_px_per_pass.append(int(grown.sum()))
        if labels is not None:
            # Contour mode: boundaries follow edge flow, so a pass leaves its
            # seams on edges the picture already has. Re-segmenting per pass
            # would be wasted work - the label map is geometry, not content.
            pass_tiles = tiles_from_labels(labels, grown)
        else:
            pass_tiles = tile_mask(grown, plan["target_tile_area"], offset=offset,
                                   stride_frac=stride_frac)
        for t in pass_tiles:
            cx0, cy0, cx1, cy1 = crop_box(t.x0, t.y0, t.x1, t.y1, crop_margin,
                                          w, h)
            crop = cur[cy0:cy1, cx0:cx1]
            cmask = np.zeros(crop.shape[:2], dtype=np.uint8)
            cmask[t.y0 - cy0:t.y1 - cy0, t.x0 - cx0:t.x1 - cx0] = (
                t.mask.astype(np.uint8) * 255)
            filled = inpaint(crop, cmask)
            sel = cmask > 0
            crop_out = np.asarray(filled, dtype=np.uint8)
            # Commit ONLY the masked pixels: the model may touch its whole crop,
            # and letting that through would repaint context the mark never
            # covered.
            region = cur[cy0:cy1, cx0:cx1]
            region[sel] = crop_out[sel]
            cur[cy0:cy1, cx0:cx1] = region
            total_tiles += 1
        passes_run += 1
        moved = int(np.any(cur != before, axis=2).sum())
        per_pass.append(moved)
        log(f"LW TILED: pass {passes_run} (offset {offset}) moved {moved} px")
        if plan["grown_px"] and moved < min_pass_change * plan["grown_px"]:
            stopped_early = True
            break
    plan["tiles_applied"] = total_tiles
    plan["passes_run"] = passes_run
    plan["stopped_early"] = stopped_early
    plan["px_moved_per_pass"] = per_pass
    plan["mask_px_per_pass"] = mask_px_per_pass
    changed = int(np.any(cur != base, axis=2).sum())
    plan["changed_px"] = changed
    plan["changed_over_mask"] = (round(changed / plan["grown_px"], 4)
                                 if plan["grown_px"] else None)
    log(f"LW TILED: {passes_run} passes, {total_tiles} tiles, {changed} px changed")
    return cur, plan


CONTROL_INNER = 6
CONTROL_OUTER = 48
CONTROL_QUANTILE = 0.95
EXCESS_STOP = 1.6


def control_band(footprint, inner=CONTROL_INNER, outer=CONTROL_OUTER):
    """A ring of UNTOUCHED art just outside the footprint.

    This is the reference the whole measure hangs on: the same picture, the same
    local style, none of the mark. `inner` keeps the ring clear of the mark's
    soft edge, which would otherwise pollute the reference with the very thing
    being measured.
    """
    foot = np.asarray(footprint, dtype=bool)
    if not foot.any():
        return np.zeros(foot.shape, dtype=bool)
    near = foot.copy()
    for _ in range(int(inner)):
        near = _dilate1(near)
    far = near.copy()
    for _ in range(max(0, int(outer) - int(inner))):
        far = _dilate1(far)
    return far & ~near


def _deviation(img, k=9):
    """Local structure: distance from the surrounding box mean."""
    g = np.asarray(img, dtype=np.float32)
    if g.ndim == 3:
        g = g.mean(axis=2)
    return np.abs(g - _box_mean(g, k))


def calibrate_threshold(img, control, quantile=CONTROL_QUANTILE, k=9):
    """The deviation level that ordinary art in THIS image already reaches.

    A fixed threshold cannot work: the operator's own accepted frames still read
    thousands of pixels as residue under one, and chasing that damaged 107 where
    the footprint covers real art. Calibrating on the control makes the measure
    say what it should - "busier than this picture's own detail".
    """
    ctrl = np.asarray(control, dtype=bool)
    if not ctrl.any():
        return float("inf")
    dev = _deviation(img, k)
    return float(np.quantile(dev[ctrl], float(quantile)))


def relative_residue(img, footprint, inner=CONTROL_INNER, outer=CONTROL_OUTER,
                     quantile=CONTROL_QUANTILE, k=9):
    """Residue measured against the picture's own art, not an absolute cut.

    MEASURED LIMIT, 2026-08-22 - do not use this alone to decide a frame is
    dirty. On the two ground-truth slugs it reports NO excess even while the
    watermark is plainly present:

      105-cleanup untouched (mark present) excess 1.01 | accepted 0.64
      107-cleanup untouched (mark present) excess 0.36 | accepted 0.17

    The measure is not broken - it is answering "is this region busier than the
    art beside it", and a semi-transparent credit line honestly is NOT. These
    marks are low-amplitude COHERENT STRUCTURE, and local contrast fires on
    brush detail while missing text. It works as a STOP rule shape (an accepted
    frame does score lower than an untouched one, both times) but it cannot
    START the work. Detection needs a feature that sees coherence - template
    correlation for the known overlay, or a legibility measure.

    Returns (mask, stats). `excess_ratio` is how much more of the footprint
    exceeds the calibrated level than the control does; by construction the
    control sits at 1 - quantile, so a ratio near 1.0 means the footprint is
    indistinguishable from the art beside it - which is what "blended out"
    means and what the operator's accepted frames look like.
    """
    foot = np.asarray(footprint, dtype=bool)
    ctrl = control_band(foot, inner, outer)
    if not foot.any() or not ctrl.any():
        return np.zeros(foot.shape, dtype=bool), {
            "threshold": None, "foot_density": 0.0, "control_density": 0.0,
            "excess_ratio": 0.0}
    thr = calibrate_threshold(img, ctrl, quantile, k)
    dev = _deviation(img, k)
    hot = dev > thr
    foot_density = float(hot[foot].mean())
    control_density = float(hot[ctrl].mean())
    ratio = (foot_density / control_density) if control_density > 0 else (
        float("inf") if foot_density > 0 else 0.0)
    return (foot & hot), {"threshold": round(thr, 3),
                          "foot_density": round(foot_density, 5),
                          "control_density": round(control_density, 5),
                          "excess_ratio": round(ratio, 3)}


def coverage_at(step, steps, start=0.05):
    """Fraction of the detected residue to treat at `step` of `steps`.

    Measured off the operator's 82 masks: the share of residue they brush ramps
    from ~2% at the first stroke to ~96% at the last. Early strokes barely move
    the frame (after 40 of 82 steps it is still at 12.97 of 15.06 distance from
    the final); the convergence is back-loaded, so the ramp is too.
    """
    n = max(1, int(steps))
    k = min(max(0, int(step)), n - 1) if n > 1 else 0
    if n == 1:
        return 1.0
    frac = start + (1.0 - start) * (k / float(n - 1))
    return float(min(1.0, max(0.0, frac)))


def select_residue(residue, fraction):
    """Take a contiguous run of the residue along its own long axis.

    The operator works a spot at a time and returns to it - they do not treat
    every fragment in the frame at once. Selecting a CONTIGUOUS run reproduces
    that; scattering the same pixel budget over the whole band would hand the
    model many tiny disconnected holes instead of one workable area.
    """
    res = np.asarray(residue, dtype=bool)
    if not res.any() or fraction >= 1.0:
        return res.copy()
    if fraction <= 0.0:
        return np.zeros_like(res)
    cols = np.nonzero(res.any(axis=0))[0]
    rows = np.nonzero(res.any(axis=1))[0]
    horizontal = (cols.max() - cols.min()) >= (rows.max() - rows.min())
    axis_idx = cols if horizontal else rows
    span = int(axis_idx.max() - axis_idx.min() + 1)
    width = max(1, int(round(span * float(fraction))))
    counts = res.sum(axis=0 if horizontal else 1)
    # Densest window of that width: where the mark is most present.
    csum = np.concatenate([[0], np.cumsum(counts)])
    best, best_v = int(axis_idx.min()), -1
    for s in range(int(axis_idx.min()), int(axis_idx.max()) - width + 2):
        v = int(csum[s + width] - csum[s])
        if v > best_v:
            best_v, best = v, s
    out = np.zeros_like(res)
    if horizontal:
        out[:, best:best + width] = res[:, best:best + width]
    else:
        out[best:best + width, :] = res[best:best + width, :]
    return out


# CAUTION, corrected 2026-08-22 on the third and fourth captures: this was
# derived from "only ~20% of each operator brush is residue", which held on two
# captures with similar step counts and FAILS on four - changed/mask runs 0.118,
# 0.122, 0.235, 1.027 and tracks the ITERATION COUNT (re-work), not the margin.
# At 82 steps with 30x overlap nearly every brushed pixel is already clean; at
# one step everything under the brush changes. Measured against MARK area the
# margin is about 1.6x on 209-cleanup, nothing like 5x. Derive this per image
# rather than trusting the constant.
CONTEXT_RATIO = 5.0


def run_schedule(img, mark_mask, inpaint, steps=12, context_ratio=CONTEXT_RATIO,
                 crop_margin=CROP_MARGIN, min_residue_px=64, relative=False,
                 excess_stop=EXCESS_STOP, lines=False, log=print):
    """Generate the operator's mask SCHEDULE and fill along it.

    Each step: find what is left inside the original footprint, take a
    contiguous run of it sized by the ramp, pad it to `context_ratio` times its
    area, fill that with a tight crop, commit. Stop when nothing is left.

    This is the piece the replay proved was missing: given the operator's own
    masks our fill produces an accepted frame, so the whole remaining problem is
    producing masks like theirs.

    `lines` carries the track-B comparison layer through the steps: the chords
    are predicted ONCE, from the art around the mark before anything is filled,
    and every step is scored against those same chords. It RECORDS, it does not
    gate - acting on the verdict is track C, and no candidate is approved on a
    scalar here.
    """
    cur = np.array(img, dtype=np.uint8, copy=True)
    footprint = np.asarray(mark_mask, dtype=bool)
    reach = grow_to_ratio(footprint, MARGIN_RATIO * 2.0)
    h, w = cur.shape[:2]
    mask_px, residue_px = [], []
    chords, line_layer, line_steps = None, None, []
    if lines:
        import lw_clean_lines as LINES
        line_layer = _dilate1(_dilate1(_dilate1(footprint)))
        chords = LINES.build_layer(cur, line_layer)
        log(f"LW SCHEDULE: comparison layer has {len(chords)} chords")
    stopped_early = False
    run = 0
    excess = []
    for k in range(max(1, int(steps))):
        if relative:
            # Stop when the footprint is no busier than the art beside it: that
            # is what "blended out" means, and an absolute pixel count says the
            # operator's own accepted frames are still dirty.
            res, stats = relative_residue(cur, footprint)
            excess.append(stats["excess_ratio"])
            residue_px.append(int(res.sum()))
            if stats["excess_ratio"] <= float(excess_stop):
                stopped_early = True
                log(f"LW SCHEDULE: excess {stats['excess_ratio']} <= "
                    f"{excess_stop} - the footprint matches its control, done")
                break
        else:
            res = residue_mask(cur, footprint)
            residue_px.append(int(res.sum()))
            if int(res.sum()) < int(min_residue_px):
                stopped_early = True
                log(f"LW SCHEDULE: residue down to {int(res.sum())} px - done")
                break
        sel = select_residue(res, coverage_at(k, steps))
        mask = grow_to_ratio(sel, context_ratio) & reach
        mask_px.append(int(mask.sum()))
        bb = mask_bbox(mask)
        if bb is None:
            stopped_early = True
            break
        x0, y0, x1, y1 = crop_box(bb[0], bb[1], bb[2], bb[3], crop_margin, w, h)
        crop = cur[y0:y1, x0:x1]
        cmask = (mask[y0:y1, x0:x1].astype(np.uint8) * 255)
        filled = np.asarray(inpaint(crop, cmask), dtype=np.uint8)
        sel_px = cmask > 0
        region = cur[y0:y1, x0:x1]
        region[sel_px] = filled[sel_px]
        cur[y0:y1, x0:x1] = region
        run += 1
        note = ""
        if chords:
            import lw_clean_lines as LINES
            sc = LINES.score(cur, line_layer, chords)
            line_steps.append({k: v for k, v in sc.items() if k != "chords"})
            note = (f" lines={sc['verdict']} "
                    f"median_ratio={sc['median_ratio']}")
        log(f"LW SCHEDULE: step {run}/{steps} residue={int(res.sum())} "
            f"selected={int(sel.sum())} mask={int(mask.sum())}{note}")
    plan = {"steps_run": run, "stopped_early": stopped_early,
            "excess_per_step": excess,
            "n_chords": 0 if chords is None else len(chords),
            "lines_per_step": line_steps,
            "mask_px_per_step": mask_px, "residue_px_per_step": residue_px,
            "changed_px": int(np.any(cur != np.asarray(img, dtype=np.uint8),
                                     axis=2).sum())}
    return cur, plan


def _lama_inpainter():
    """Lazily build the simple-lama callable (torch lands here, not at import)."""
    from simple_lama_inpainting import SimpleLama
    lama = SimpleLama()

    def _fn(crop_rgb, crop_mask_u8):
        out = lama(Image.fromarray(crop_rgb), Image.fromarray(crop_mask_u8))
        return np.asarray(out.convert("RGB"), dtype=np.uint8)[
            :crop_rgb.shape[0], :crop_rgb.shape[1]]
    return _fn


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lw_clean_tiled")
    ap.add_argument("--image", required=True)
    ap.add_argument("--mask", required=True, help="mark mask PNG (white = mark)")
    ap.add_argument("--out", required=True, help="output PNG")
    ap.add_argument("--plan-out", help="write the plan JSON here")
    ap.add_argument("--margin-ratio", type=float, default=MARGIN_RATIO)
    ap.add_argument("--crop-margin", type=int, default=CROP_MARGIN)
    ap.add_argument("--contours", action="store_true",
                    help="tile on edge-following segments instead of a lattice")
    ap.add_argument("--subdivide", type=float, default=0,
                    help="re-segment any region larger than N x the tile area "
                         "(0 = off)")
    ap.add_argument("--schedule", type=int, default=0,
                    help="run the operator's measured mask SCHEDULE for N steps "
                         "(residue -> contiguous run -> context pad -> fill)")
    ap.add_argument("--context-ratio", type=float, default=CONTEXT_RATIO)
    ap.add_argument("--relative", action="store_true",
                    help="measure residue against a control band of the same "
                         "art and stop when the footprint matches it")
    ap.add_argument("--excess-stop", type=float, default=EXCESS_STOP)
    ap.add_argument("--target-residue", action="store_true",
                    help="later passes work only where the mark has not blended "
                         "out yet, instead of dilating everywhere")
    ap.add_argument("--escalate-px", type=int, default=0,
                    help="dilate the mask by N px before each later pass, to "
                         "pull more context into whatever the last pass left")
    ap.add_argument("--subdivide-min-gradient", type=float, default=None,
                    help="only subdivide regions busier than this (smooth ones "
                         "stay whole - splitting them rebuilds a lattice)")
    ap.add_argument("--extend-labels", type=int, default=0,
                    help="reach into N neighbouring regions of matching "
                         "luminance to source the fill texture")
    ap.add_argument("--stride-frac", type=float, default=STRIDE_FRAC,
                    help="window overlap; 1.0 = abutting grid (leaves seams)")
    ap.add_argument("--passes", type=int, default=DEFAULT_PASSES,
                    help="staggered repeat passes over the mark (measured: the "
                         "operator re-brushes every pixel many times)")
    ap.add_argument("--lines", action="store_true",
                    help="carry the track-B comparison layer through the "
                         "schedule and record a per-step line verdict")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan only: no GPU, no pixels")
    args = ap.parse_args(argv)

    with Image.open(args.image) as im:
        img = np.asarray(im.convert("RGB"), dtype=np.uint8)
    with Image.open(args.mask) as im:
        mark = np.asarray(im.convert("L")) > 127

    if args.dry_run:
        plan = build_plan(img, mark, args.margin_ratio, args.stride_frac)
        plan.pop("grown")
        print(json.dumps(plan, indent=2)[:4000])
        if args.plan_out:
            _write_json(args.plan_out, plan)
        return 0

    if args.schedule:
        out, plan = run_schedule(img, mark, _lama_inpainter(), steps=args.schedule,
                                 context_ratio=args.context_ratio,
                                 crop_margin=args.crop_margin,
                                 relative=args.relative,
                                 excess_stop=args.excess_stop,
                                 lines=args.lines)
        tmp = args.out + ".part"
        Image.fromarray(out).save(tmp, format="PNG")
        os.replace(tmp, args.out)
        print(json.dumps(plan, indent=2))
        if args.plan_out:
            _write_json(args.plan_out, plan)
        return 0

    labels = None
    if args.contours:
        bb = mask_bbox(mark)
        grad = local_gradient(img, bb, exclude=mark) if bb else 0.0
        area = target_tile_area(grad)
        labels = segment_contours(img, area)
        if args.subdivide:
            # A region bigger than one brush-sized tile still hides the mark in
            # its own context; split it before any fill happens.
            labels = subdivide_labels(img, labels, max_area=area * args.subdivide,
                                      min_gradient=args.subdivide_min_gradient,
                                      exclude=mark)
        if args.extend_labels:
            mark = extend_into_similar(img, labels, mark,
                                       max_labels=args.extend_labels)
    out, plan = run_tiled(img, mark, _lama_inpainter(), args.margin_ratio,
                          args.crop_margin, passes=args.passes,
                          stride_frac=args.stride_frac, labels=labels,
                          escalate_px=args.escalate_px,
                          target_residue=args.target_residue)
    tmp = args.out + ".part"
    # format is explicit: PIL infers it from the extension, and the atomic
    # temp name ends in .part, which it cannot resolve.
    Image.fromarray(out).save(tmp, format="PNG")
    os.replace(tmp, args.out)
    print(json.dumps({k: v for k, v in plan.items() if k != "tiles"}, indent=2))
    if args.plan_out:
        _write_json(args.plan_out, plan)
    return 0


def _write_json(path, obj):
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, path)


if __name__ == "__main__":
    raise SystemExit(main())
