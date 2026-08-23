"""The art BEHIND the mark - measuring it, and estimating it.

Track A. Every decision the cleaning schedule makes about a mark is currently
taken by measuring the frame that still carries it, so the mark votes on how it
should be treated. Measured live on the four operator hand-clean captures,
against their own accepted finals as ground truth:

  slug   marked   true    error   tile area asked for (marked -> true)
  105     3.684   2.878    +28%     5102 ->  13211
  107     3.178   2.907     +9%     9263 ->  12764
  209     7.754   2.247   +245%     2000 ->  27805    one stroke, smooth panel
  dgk     5.467   0.778   +603%     2000 ->  40000    soft snow

The two smoothest images in the set are the two that get slammed into the 2000px
tile floor, because their marks are the loudest thing in frame. The rule is not
mis-tuned, it is reading the wrong picture.

Two different things are needed and conflating them is what went wrong before:

  `busyness()`      the STATISTIC. The mark's own pixels are excluded from it,
                    so stroke SIZE is chosen on the art. Excluding is unbiased
                    and invents nothing; it assumes only that the art under the
                    mark resembles the art beside it.
  `behind_image()`  an ESTIMATE of the picture under the mark, so stroke
                    PLACEMENT has something to look at. This one does invent -
                    it is a membrane (harmonic) solve - so it is deliberately
                    NOT what the statistic is taken on: a smooth estimate would
                    bias busyness down exactly as the mark biases it up.

Pure numpy + Pillow. `busyness` with nothing excluded is bit-identical to
`lw_clean_tiled.local_gradient`, which is the estimator the tile-size anchors
were fitted with; if it were not, every anchor in the repo would quietly change
meaning.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_clean_heal as HEAL  # noqa: E402
import lw_clean_tiled as T  # noqa: E402

# Context ring around the mark bbox. Matches lw_clean_tiled.local_gradient's
# default so the two agree pixel for pixel when nothing is excluded.
DEFAULT_PAD = 24

# A brush mask stops at the mark's visible edge, and a semi-transparent mark has
# a soft skirt beyond that which is still mark. Three pixels of dilation covers
# it without eating meaningful art.
DEFAULT_DILATE = 3

# Below this fraction of readable pixels the window says nothing about the art,
# so widen it rather than report a confident zero.
MIN_VALID_FRACTION = 0.15
WIDEN_STEPS = 5

# One dilation implementation for the whole cleaning stack.
_dilate = HEAL._dilate


def _window(shape, box, pad):
    h, w = shape[:2]
    if box is None:
        return 0, 0, w, h
    x0, y0, x1, y1 = box
    return (max(0, int(x0) - pad), max(0, int(y0) - pad),
            min(w, int(x1) + pad), min(h, int(y1) + pad))


def busyness(img, box=None, exclude=None, pad=DEFAULT_PAD, dilate=0):
    """Mean absolute first difference, over readable pixel PAIRS only.

    A difference is counted only when both of its endpoints are outside
    `exclude`, so no masked value can reach the result - not even through one
    end of a gradient. Returns 0.0 when the window has nothing readable in it.
    """
    ex = exclude
    if ex is not None and dilate and np.any(ex):
        ex = _dilate(ex, dilate)
    if box is None:
        box = (0, 0, img.shape[1], img.shape[0])
        pad = 0
    return T.local_gradient(img, box, pad=pad, exclude=ex)


def readable_fraction(shape, box, exclude, pad, dilate):
    """How much of the window survives the exclusion."""
    x0, y0, x1, y1 = _window(shape, box, pad)
    area = max(1, (y1 - y0) * (x1 - x0))
    if exclude is None or not np.any(exclude):
        return 1.0
    ex = _dilate(exclude, dilate) if dilate else exclude
    return float((~ex[y0:y1, x0:x1]).sum()) / area


def local_gradient_behind(img, mark, box, pad=DEFAULT_PAD,
                          dilate=DEFAULT_DILATE):
    """Drop-in replacement for `lw_clean_tiled.local_gradient`, mark-aware.

    Widens the window when the mark fills it: a mark that covers everything the
    probe can see leaves no evidence about the art, and reporting a confident
    0.0 there would hand it the maximum tile - the same failure in the other
    direction.
    """
    if mark is None or not np.any(mark):
        return busyness(img, box, pad=pad)
    p = int(pad)
    for _ in range(WIDEN_STEPS):
        if readable_fraction(img.shape, box, mark, p, dilate) >= MIN_VALID_FRACTION:
            return busyness(img, box, exclude=mark, pad=p, dilate=dilate)
        p *= 2
    return busyness(img, box, exclude=mark, pad=p, dilate=dilate)


def behind_image(img, mark):
    """Estimate the picture under the mark; nothing outside it is touched.

    A membrane (harmonic) solve: the smoothest field that meets the surrounding
    art exactly. It recovers tone and low-frequency structure faithfully and
    invents no texture, which is what makes it safe to LOOK at for placement and
    unsafe to MEASURE busyness on.
    """
    mark = np.asarray(mark, dtype=bool)
    if not mark.any():
        return np.asarray(img).copy()
    return HEAL.poisson_fill(img, mark, offset=None)


# ----------------------------------------------------------------------- CLI
def main(argv=None):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None

    ap = argparse.ArgumentParser(prog="lw_clean_behind")
    ap.add_argument("--image", required=True)
    ap.add_argument("--mask", required=True, help="white = the mark")
    ap.add_argument("--out", help="write the behind-the-mark estimate here")
    ap.add_argument("--pad", type=int, default=DEFAULT_PAD)
    ap.add_argument("--dilate", type=int, default=DEFAULT_DILATE)
    args = ap.parse_args(argv)

    with Image.open(args.image) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.uint8)
    with Image.open(args.mask) as im:
        mark = np.asarray(im.convert("L")) > 127
    box = T.mask_bbox(mark)
    if box is None:
        raise SystemExit("empty mask")

    rec = {"image": args.image, "mask_px": int(mark.sum()), "box": list(box),
           "marked": round(busyness(rgb, box, pad=args.pad), 4),
           "behind": round(local_gradient_behind(rgb, mark, box, pad=args.pad,
                                                 dilate=args.dilate), 4)}
    rec["tile_area_marked"] = round(T.target_tile_area(rec["marked"]))
    rec["tile_area_behind"] = round(T.target_tile_area(rec["behind"]))
    if args.out:
        est = behind_image(rgb, mark)
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        tmp = args.out + ".part"
        Image.fromarray(est).save(tmp, format="PNG")
        os.replace(tmp, args.out)
        rec["estimate"] = args.out
    print(json.dumps(rec, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
