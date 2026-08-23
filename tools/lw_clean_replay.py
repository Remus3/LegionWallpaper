"""Replay the operator's captured masks, in order, and diff against their output.

This is a DIAGNOSTIC, not a lane. It answers the one question the tiled worker
cannot answer about itself: when the mask is exactly right, does our fill land
where the operator's did?

The operator captured every step of a hand clean - the brush mask and the output
it produced - so replaying mask 1..N sequentially, each on the committed result
of the last, isolates the two halves of the problem:

  divergence stays near zero -> our FILL matches theirs; the whole remaining gap
                                is mask generation, which is a tractable problem
  divergence grows           -> the fill engines differ (IOPaint's LaMa serving,
                                its crop strategy, its blending), and no mask
                                derivation will close it

IOPaint logs `Run crop strategy` on every call, so the replay crops around each
mask the same way rather than handing the model the whole frame.

  python tools/lw_clean_replay.py --capture <dir> --initial <png> --out <jsonl>
"""
from __future__ import annotations

import argparse
import json
import os
import re

import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

Image.MAX_IMAGE_PIXELS = None

# IOPaint's crop strategy pads the mask bbox before handing it to the model.
CROP_MARGIN = 128


def idx_of(name):
    m = re.search(r"\(?(\d+)\)?\.(?:jpg|jpeg|png)$", name, re.I)
    return int(m.group(1)) if m else None


def collect(root, name_contains=None):
    """Map iteration -> (mask path, output path), keyed off FILENAMES.

    One capture has its mask and output folders swapped relative to the other,
    so folder position is not a reliable signal; the basename is.

    `name_contains` is not optional in practice: captures for different slugs
    live under one tree and their iteration numbers COLLIDE, so an unfiltered
    walk silently compares one slug's replay against another slug's output.
    That produced a bogus 136-level divergence on the first run.
    """
    masks, outs = {}, {}
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            i = idx_of(f)
            if i is None:
                continue
            if name_contains and name_contains.lower() not in f.lower():
                continue
            low = f.lower()
            if "mask" in low:
                masks[i] = os.path.join(dirpath, f)
            elif "cleanup" in low:
                outs[i] = os.path.join(dirpath, f)
    return masks, outs


def load_rgb(path):
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"), dtype=np.uint8)


def crop_around(mask, width, height, margin=CROP_MARGIN):
    """The window IOPaint's crop strategy would use for this mask."""
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return None
    return (max(0, int(xs.min()) - margin), max(0, int(ys.min()) - margin),
            min(width, int(xs.max()) + 1 + margin),
            min(height, int(ys.max()) + 1 + margin))


def _lama():
    from simple_lama_inpainting import SimpleLama
    lama = SimpleLama()

    def _fn(crop_rgb, crop_mask_u8):
        out = lama(Image.fromarray(crop_rgb), Image.fromarray(crop_mask_u8))
        return np.asarray(out.convert("RGB"), dtype=np.uint8)[
            :crop_rgb.shape[0], :crop_rgb.shape[1]]
    return _fn


def _heal():
    """The healing-brush fill (track E) behind the same crop-in/crop-out API."""
    import lw_clean_heal as HEAL

    def _fn(crop_rgb, crop_mask_u8):
        out, _info = HEAL.heal(crop_rgb, crop_mask_u8 > 127)
        return out
    return _fn


ENGINES = {"lama": _lama, "heal": _heal}


def replay(initial, masks, outs, inpaint, out_jsonl, log=print):
    """Apply each captured mask in order; diff our result against theirs."""
    # .copy(): PIL's asarray view is read-only, and the replay writes in place.
    cur = load_rgb(initial).copy()
    h, w = cur.shape[:2]
    rows = []
    with open(out_jsonl, "w", encoding="utf-8", newline="\n") as fh:
        for i in sorted(masks):
            if i not in outs:
                continue
            m = np.asarray(Image.open(masks[i]).convert("L")) > 127
            box = crop_around(m, w, h)
            if box is None:
                continue
            x0, y0, x1, y1 = box
            crop = cur[y0:y1, x0:x1]
            cmask = (m[y0:y1, x0:x1].astype(np.uint8) * 255)
            filled = np.asarray(inpaint(crop, cmask), dtype=np.uint8)
            sel = cmask > 0
            region = cur[y0:y1, x0:x1]
            region[sel] = filled[sel]
            cur[y0:y1, x0:x1] = region

            theirs = load_rgb(outs[i]).astype(np.int16)
            d_all = np.abs(cur.astype(np.int16) - theirs).max(axis=2)
            d_in = d_all[m]
            row = {"i": i, "mask_px": int(m.sum()),
                   "mean_in_mask": round(float(d_in.mean()), 3),
                   "p95_in_mask": int(np.percentile(d_in, 95)),
                   "mean_frame": round(float(d_all.mean()), 4),
                   "diverged_px": int((d_all > 8).sum())}
            rows.append(row)
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            log(f"[{i}] mask={row['mask_px']} mean_in_mask={row['mean_in_mask']} "
                f"diverged={row['diverged_px']}")
    return cur, rows


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lw_clean_replay")
    ap.add_argument("--capture", required=True, help="capture dir (walked)")
    ap.add_argument("--initial", required=True)
    ap.add_argument("--out", required=True, help="per-step JSONL")
    ap.add_argument("--final-png", help="write the replayed final frame here")
    ap.add_argument("--name-contains",
                    help="only files whose name contains this (captures for "
                         "different slugs share iteration numbers)")
    ap.add_argument("--engine", choices=sorted(ENGINES), default="lama",
                    help="fill engine under test (default: lama)")
    args = ap.parse_args(argv)

    masks, outs = collect(args.capture, args.name_contains)
    print(f"masks={len(masks)} outputs={len(outs)} engine={args.engine}")
    cur, rows = replay(args.initial, masks, outs, ENGINES[args.engine](),
                       args.out)
    if args.final_png:
        tmp = args.final_png + ".part"
        Image.fromarray(cur).save(tmp, format="PNG")
        os.replace(tmp, args.final_png)
    if rows:
        print(f"steps={len(rows)}  first mean_in_mask={rows[0]['mean_in_mask']}  "
              f"last mean_in_mask={rows[-1]['mean_in_mask']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
