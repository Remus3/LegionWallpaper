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


def crop_box(x0, y0, x1, y1, margin, width, height):
    """Context window around one tile, clamped to the frame."""
    return (max(0, int(x0) - margin), max(0, int(y0) - margin),
            min(int(width), int(x1) + margin), min(int(height), int(y1) + margin))


def local_gradient(img, box, pad=24):
    """Mean absolute first difference around `box` - the busyness measure.

    Same estimator used to fit the tile-size anchors, so the calibration and the
    runtime probe cannot drift apart.
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
    gx = float(np.abs(np.diff(g, axis=1)).mean())
    gy = float(np.abs(np.diff(g, axis=0)).mean())
    return (gx + gy) / 2.0


def mask_bbox(mask):
    """Bounding box of a boolean mask, or None when it is empty."""
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return None
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def build_plan(img, mark_mask, margin_ratio=MARGIN_RATIO,
               stride_frac=STRIDE_FRAC):
    """Decide the whole decomposition BEFORE any pixel is written.

    Returned as data so a dry run can be reviewed, logged and diffed against the
    operator's own captures without spending the GPU.
    """
    mark = np.asarray(mark_mask, dtype=bool)
    bbox = mask_bbox(mark)
    grad = local_gradient(img, bbox) if bbox else 0.0
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
    cur = np.array(img, dtype=np.uint8, copy=True)
    base = np.asarray(img, dtype=np.uint8)
    h, w = cur.shape[:2]
    step = max(1, int(round(math.sqrt(plan["target_tile_area"]))))
    total_tiles = 0
    passes_run = 0
    stopped_early = False
    per_pass = []
    for p in range(max(1, int(passes))):
        before = cur.copy()
        offset = (p * step) // max(1, int(passes))
        for t in tile_mask(grown, plan["target_tile_area"], offset=offset,
                           stride_frac=stride_frac):
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
    changed = int(np.any(cur != base, axis=2).sum())
    plan["changed_px"] = changed
    plan["changed_over_mask"] = (round(changed / plan["grown_px"], 4)
                                 if plan["grown_px"] else None)
    log(f"LW TILED: {passes_run} passes, {total_tiles} tiles, {changed} px changed")
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
    ap.add_argument("--stride-frac", type=float, default=STRIDE_FRAC,
                    help="window overlap; 1.0 = abutting grid (leaves seams)")
    ap.add_argument("--passes", type=int, default=DEFAULT_PASSES,
                    help="staggered repeat passes over the mark (measured: the "
                         "operator re-brushes every pixel many times)")
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

    out, plan = run_tiled(img, mark, _lama_inpainter(), args.margin_ratio,
                          args.crop_margin, passes=args.passes,
                          stride_frac=args.stride_frac)
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
