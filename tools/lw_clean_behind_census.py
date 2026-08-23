"""Census: does the behind-the-mark measure track the truth the marked one misses?

Ground truth exists for exactly four images and it is not a proxy: the operator
hand-cleaned them and accepted the result, so their final frame IS the art
behind the mark. Measuring busyness on that final is the number every estimator
in this census is trying to predict without being allowed to see it.

Three estimators are compared, all on the same window:

  marked     the incumbent - `lw_clean_tiled.local_gradient` on the frame that
             still carries the mark
  excluded   the mark's pixels dropped from the statistic (track A's answer)
  membrane   the statistic taken on the behind-the-mark IMAGE estimate, which
             is in the census to show why the image estimate must not be used
             for the statistic: a harmonic fill is smooth by construction and
             biases the measure down as surely as the mark biases it up

  python tools/lw_clean_behind_census.py --out ops/runtime/clean/behind
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_clean_behind as B  # noqa: E402
import lw_clean_replay as R  # noqa: E402
import lw_clean_tiled as T  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDEDITS = os.path.join(ROOT, "ops", "runtime", "clean", "handedits")
SCRATCH = os.path.join(ROOT, "images", "3.Cleaning Scratch")
DGK = "dgk8f92-bc10d7a7-f520-4b4f-ad86-ac70f6d50293"

CAPTURES = [
    ("105", "105-cleanup", "105-cleanup", "credit line, folded fabric"),
    ("107", "107-cleanup", "107-cleanup", "area, soft gradients"),
    ("209", "209-cleanup", "209-cleanup", "signature, smooth panel"),
    ("dgk", DGK, "dgk8f92", "block, soft snow"),
]


def union_mask(capture, name_contains):
    masks, outs = R.collect(capture, name_contains)
    acc = None
    for i in sorted(masks):
        m = np.asarray(Image.open(masks[i]).convert("L")) > 127
        acc = m if acc is None else (acc | m)
    return acc, outs[max(outs)], len(masks)


def row(tag, folder, name_contains, art, save_estimate=None):
    cap = os.path.join(HANDEDITS, folder)
    slug = folder if folder.startswith(DGK) else folder
    init = os.path.join(SCRATCH, slug, f"{slug}_cleaninitial.png")
    mark, op_path, steps = union_mask(cap, name_contains)
    marked = R.load_rgb(init)
    truth = R.load_rgb(op_path)
    box = T.mask_bbox(mark)

    est = B.behind_image(marked, mark)
    if save_estimate:
        os.makedirs(save_estimate, exist_ok=True)
        path = os.path.join(save_estimate, f"{tag}_behind.png")
        tmp = path + ".part"
        Image.fromarray(est).save(tmp, format="PNG")
        os.replace(tmp, path)

    g = {"truth": B.busyness(truth, box),
         "marked": B.busyness(marked, box),
         "excluded": B.local_gradient_behind(marked, mark, box),
         "membrane": B.busyness(est, box)}
    # How much the ESTIMATE knows about what is actually under there, against
    # the operator's own final. This is the number that decides whether the
    # estimate is worth looking at for stroke PLACEMENT.
    def _err(a):
        return round(float(np.abs(a.astype(np.int16) - truth.astype(np.int16))
                           .max(axis=2)[mark].mean()), 3)

    rec = {"tag": tag, "art": art, "steps": steps, "mask_px": int(mark.sum()),
           "box": list(box), "gradient": {k: round(v, 4) for k, v in g.items()},
           "in_mask_error": {"marked": _err(marked), "behind": _err(est)},
           "error_pct": {k: round(100.0 * (v - g["truth"]) / g["truth"], 1)
                         for k, v in g.items() if k != "truth"},
           "tile_area": {k: round(T.target_tile_area(v)) for k, v in g.items()}}
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lw_clean_behind_census")
    ap.add_argument("--out", default=os.path.join(ROOT, "ops", "runtime",
                                                  "clean", "behind"))
    ap.add_argument("--no-estimates", action="store_true")
    args = ap.parse_args(argv)

    rows = [row(t, f, n, a, None if args.no_estimates else args.out)
            for t, f, n, a in CAPTURES]

    hdr = (f"{'slug':5s} {'steps':>5s} {'truth':>7s} {'marked':>8s} "
           f"{'excluded':>9s} {'membrane':>9s} | tile area: "
           f"{'true':>6s} {'marked':>7s} {'excluded':>9s}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        g, e, a = r["gradient"], r["error_pct"], r["tile_area"]
        print(f"{r['tag']:5s} {r['steps']:5d} {g['truth']:7.3f} "
              f"{g['marked']:8.3f} {g['excluded']:9.3f} {g['membrane']:9.3f} | "
              f"{'':11s}{a['truth']:6d} {a['marked']:7d} {a['excluded']:9d}")
    print()
    print("in-mask distance to the operator's final (lower = the estimate "
          "knows more about what is under the mark):")
    for r in rows:
        e = r["in_mask_error"]
        print(f"  {r['tag']:5s} marked {e['marked']:7.2f} -> behind "
              f"{e['behind']:7.2f}")
    print()
    for name in ("marked", "excluded", "membrane"):
        errs = [abs(r["error_pct"][name]) for r in rows]
        print(f"{name:9s} mean |error| {sum(errs) / len(errs):7.1f}%   "
              f"worst {max(errs):7.1f}%")

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "behind_census.json")
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"captures": rows}, fh, indent=2)
    os.replace(tmp, path)
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
