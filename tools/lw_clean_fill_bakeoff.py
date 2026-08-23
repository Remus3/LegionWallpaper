"""One-shot fill bake-off across the operator's hand-clean captures.

The 82-step replay answers "does our fill land where theirs did when the mask is
theirs". It does NOT compare fill engines fairly, because a healing brush is a
one-shot instrument: re-solving the same region 82 times compounds its own
output, while a learned inpainter re-imagines the region from a cleaner context
each pass and improves. Measured on 105-cleanup, the heal scores 14.0 through
the 82-step replay and far better in one shot.

So this asks the fair question instead: given the UNION of every mask the
operator brushed - their own decision about what had to go - fill it ONCE with
each engine and compare against the frame they accepted.

Distance to the operator's final is a sanity check, never a verdict, and it is
biased: their finals came out of IOPaint, which serves LaMa, so a LaMa fill is
being scored against its own family. The sheets are the deliverable.

  python tools/lw_clean_fill_bakeoff.py --capture <dir> --name-contains 105 \
      --initial <png> --outdir ops/runtime/clean/heal
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_clean_heal as HEAL  # noqa: E402
import lw_clean_replay as R  # noqa: E402

Image.MAX_IMAGE_PIXELS = None


def union_mask(capture, name_contains):
    masks, outs = R.collect(capture, name_contains)
    if not masks:
        return None, None, None
    acc = None
    for i in sorted(masks):
        m = np.asarray(Image.open(masks[i]).convert("L")) > 127
        acc = m if acc is None else (acc | m)
    return acc, outs[max(outs)], len(masks)


def score(out, operator, mask):
    d = np.abs(out.astype(np.int16) - operator.astype(np.int16)).max(axis=2)
    return {"mean_in_mask": round(float(d[mask].mean()), 3),
            "p95_in_mask": int(np.percentile(d[mask], 95)),
            "diverged_px": int((d[mask] > 8).sum())}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lw_clean_fill_bakeoff")
    ap.add_argument("--capture", required=True)
    ap.add_argument("--name-contains")
    ap.add_argument("--initial", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--engines", default="heal,heal1,lama")
    args = ap.parse_args(argv)

    mask, op_path, n = union_mask(args.capture, args.name_contains)
    if mask is None:
        raise SystemExit("no masks in capture")
    img = R.load_rgb(args.initial).copy()
    operator = R.load_rgb(op_path)
    box = R.crop_around(mask, img.shape[1], img.shape[0])
    x0, y0, x1, y1 = box
    crop, cmask = img[y0:y1, x0:x1], mask[y0:y1, x0:x1]

    os.makedirs(args.outdir, exist_ok=True)
    rec = {"tag": args.tag, "steps_captured": n, "mask_px": int(mask.sum()),
           "crop": [x0, y0, x1, y1], "engines": {}}
    rec["engines"]["untouched"] = score(img, operator, mask)

    for name in args.engines.split(","):
        cur = img.copy()
        if name == "lama":
            fn = R._lama()
            filled = fn(crop, (cmask.astype(np.uint8) * 255))
            cur[y0:y1, x0:x1][cmask] = filled[cmask]
        else:
            out, info = HEAL.heal(crop, cmask, two_sided=(name == "heal"))
            cur[y0:y1, x0:x1] = out
            rec.setdefault("heal_info", {})[name] = {
                "tiles": info["tiles"],
                "modes": sorted({s["mode"] for s in info["steps"]})}
        # `oneshot` in the name on purpose: the replay writes <tag>_<engine>
        # finals into the same directory and the two are not comparable.
        path = os.path.join(args.outdir, f"{args.tag}_oneshot_{name}.png")
        tmp = path + ".part"
        Image.fromarray(cur).save(tmp, format="PNG")
        os.replace(tmp, path)
        rec["engines"][name] = score(cur, operator, mask)
        rec["engines"][name]["png"] = path

    out_json = os.path.join(args.outdir, f"{args.tag}_bakeoff.json")
    tmp = out_json + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rec, fh, indent=2)
    os.replace(tmp, out_json)
    print(json.dumps(rec, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
