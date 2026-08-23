"""Stack 1:1 crops of one mark across variants, for the operator's eye.

The acceptance bar set on 2026-08-22 is ZERO watermark residue judged at 1:1 by
the operator, and no scalar is a verdict. So the deliverable of a fill experiment
is not a number, it is a strip the operator can look at: the same crop, at native
resolution with no resampling, once per variant, labelled.

The crop window is the union of the capture's own masks - the region the operator
themselves decided needed work - padded a little so the surrounding art is in
frame and a seam would be obvious.

  python tools/lw_clean_heal_compare.py --capture <dir> --name-contains 105 \
      --out sheet.png original=a.png operator=b.png lama=c.png heal=d.png
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_clean_replay as R  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

PAD = 40
LABEL_H = 22
GAP = 6
BG = (24, 24, 24)
FG = (235, 235, 235)


def mask_union_box(capture, name_contains, pad=PAD, size=None):
    """Bounding box of every mask in the capture, padded and clipped."""
    masks, _outs = R.collect(capture, name_contains)
    if not masks:
        return None
    x0 = y0 = 10 ** 9
    x1 = y1 = -1
    for path in masks.values():
        with Image.open(path) as im:
            m = np.asarray(im.convert("L")) > 127
        ys, xs = np.nonzero(m)
        if ys.size == 0:
            continue
        y0, y1 = min(y0, int(ys.min())), max(y1, int(ys.max()) + 1)
        x0, x1 = min(x0, int(xs.min())), max(x1, int(xs.max()) + 1)
    if x1 < 0:
        return None
    w, h = size if size else (10 ** 9, 10 ** 9)
    return (max(0, x0 - pad), max(0, y0 - pad),
            min(w, x1 + pad), min(h, y1 + pad))


def build(variants, box, out_path):
    """One column, one row per variant, native pixels, labelled."""
    x0, y0, x1, y1 = box
    cw, ch = x1 - x0, y1 - y0
    rows = []
    for name, path in variants:
        with Image.open(path) as im:
            rows.append((name, im.convert("RGB").crop((x0, y0, x1, y1))))
    total = len(rows) * (ch + LABEL_H + GAP) + GAP
    sheet = Image.new("RGB", (cw + 2 * GAP, total), BG)
    draw = ImageDraw.Draw(sheet)
    y = GAP
    for name, crop in rows:
        draw.text((GAP + 4, y + 5), f"{name}   [{cw}x{ch} @ 1:1  x{x0} y{y0}]",
                  fill=FG)
        sheet.paste(crop, (GAP, y + LABEL_H))
        y += LABEL_H + ch + GAP
    tmp = out_path + ".part"
    sheet.save(tmp, format="PNG")
    os.replace(tmp, out_path)
    return sheet.size


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lw_clean_heal_compare")
    ap.add_argument("--capture", required=True)
    ap.add_argument("--name-contains")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pad", type=int, default=PAD)
    ap.add_argument("variants", nargs="+", help="label=path, in display order")
    args = ap.parse_args(argv)

    variants = []
    for spec in args.variants:
        name, _, path = spec.partition("=")
        if not path or not os.path.exists(path):
            raise SystemExit(f"missing variant image: {spec}")
        variants.append((name, path))

    with Image.open(variants[0][1]) as im:
        size = im.size
    box = mask_union_box(args.capture, args.name_contains, args.pad, size)
    if box is None:
        raise SystemExit("no masks found in the capture")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    print(f"box={box} -> {build(variants, box, args.out)}  {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
