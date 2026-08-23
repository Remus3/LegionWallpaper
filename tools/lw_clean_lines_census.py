"""Does the comparison layer agree with the operator about which fills broke lines?

The layer is only worth carrying through the schedule if its verdicts match the
ones already known. Four captures have labels that were not produced by any
measure:

  operator   the frame they hand-cleaned and accepted            -> must be intact
  lama       our fill given their masks; they passed the replay  -> must be intact
  heal       the track E healing brush, which smeared 105 and
             mangled 107 at 1:1                                  -> must be worse
  behind     the membrane estimate, which is a blur inside
             the mark by construction                            -> must be broken

The layer is built ONCE per capture from the marked frame - readable art only,
so the mark contributes nothing - and every variant is scored against those same
chords. Anything else would be scoring each fill against its own opinion.

  python tools/lw_clean_lines_census.py
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
import lw_clean_lines as L  # noqa: E402
import lw_clean_replay as R  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDEDITS = os.path.join(ROOT, "ops", "runtime", "clean", "handedits")
SCRATCH = os.path.join(ROOT, "images", "3.Cleaning Scratch")
HEALDIR = os.path.join(ROOT, "ops", "runtime", "clean", "heal")
BEHIND = os.path.join(ROOT, "ops", "runtime", "clean", "behind")
DGK = "dgk8f92-bc10d7a7-f520-4b4f-ad86-ac70f6d50293"

CAPTURES = [("105", "105-cleanup", "105-cleanup"),
            ("107", "107-cleanup", "107-cleanup"),
            ("209", "209-cleanup", "209-cleanup"),
            ("dgk", DGK, "dgk8f92")]

# The operator's brush stops at the mark's visible edge; its soft skirt is still
# mark and must not be mistaken for art meeting the boundary.
HALO = 3


def union_mask(capture, name_contains):
    masks, outs = R.collect(capture, name_contains)
    acc = None
    for i in sorted(masks):
        m = np.asarray(Image.open(masks[i]).convert("L")) > 127
        acc = m if acc is None else (acc | m)
    return acc, outs[max(outs)]


def variants(tag, slug, op_path):
    out = [("original", os.path.join(SCRATCH, slug, f"{slug}_cleaninitial.png")),
           ("operator", op_path),
           ("lama", os.path.join(HEALDIR, f"{tag}_oneshot_lama.png")),
           ("heal", os.path.join(HEALDIR, f"{tag}_oneshot_heal.png")),
           ("behind", os.path.join(BEHIND, f"{tag}_behind.png"))]
    return [(n, p) for n, p in out if os.path.exists(p)]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lw_clean_lines_census")
    ap.add_argument("--out", default=BEHIND)
    ap.add_argument("--grad-min", type=float, default=L.GRAD_MIN)
    args = ap.parse_args(argv)

    rows = []
    for tag, folder, name_contains in CAPTURES:
        mark, op_path = union_mask(os.path.join(HANDEDITS, folder),
                                   name_contains)
        marked = R.load_rgb(os.path.join(SCRATCH, folder,
                                         f"{folder}_cleaninitial.png"))
        layer_mask = HEAL._dilate(mark, HALO)
        chords = L.build_layer(marked, layer_mask, grad_min=args.grad_min)
        rec = {"tag": tag, "mask_px": int(mark.sum()), "chords": len(chords),
               "variants": {}}
        for name, path in variants(tag, folder, op_path):
            rec["variants"][name] = {
                k: v for k, v in L.score(R.load_rgb(path), layer_mask,
                                         chords).items() if k != "chords"}
        rows.append(rec)

    names = ["original", "operator", "lama", "heal", "behind"]
    print(f"{'slug':5s} {'chords':>6s} | " +
          " | ".join(f"{n:>9s}" for n in names))
    print("-" * 76)
    for r in rows:
        cells = []
        for n in names:
            v = r["variants"].get(n)
            cells.append("        -" if not v or v["median_ratio"] is None
                         else f"{v['median_ratio']:9.3f}")
        print(f"{r['tag']:5s} {r['chords']:6d} | " + " | ".join(cells))
    print("\nintact fraction")
    for r in rows:
        cells = []
        for n in names:
            v = r["variants"].get(n)
            cells.append("        -" if not v or v["intact_fraction"] is None
                         else f"{v['intact_fraction']:9.2f}")
        print(f"{r['tag']:5s} {r['chords']:6d} | " + " | ".join(cells))

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "lines_census.json")
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"captures": rows, "grad_min": args.grad_min}, fh, indent=2)
    os.replace(tmp, path)
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
