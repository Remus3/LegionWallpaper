"""Does the veil model describe these marks, and does conditioning help the fill?

Track D rests on a premise - that a mark is a semi-transparent layer over the
art - and the four captures can test it directly, because the operator's
accepted final IS the content behind the mark. With the content known,

    observed = (1 - alpha) * content + alpha * colour

is a straight line per channel, and its R-squared says whether the mark is a
veil at all. That is `fit_veil`, and it needs ground truth, so it lives here and
never in a lane.

Then the second half, which does not depend on the first: whatever the model
says, does conditioning the region before the fill leave the fill better off?
Both are reported, against the operator's own frames.

Run it under the lw-clean venv - the fill needs simple-lama.

  C:\\Tools\\lw-clean\\venv\\Scripts\\python.exe tools/lw_clean_condition_census.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_clean_condition as C  # noqa: E402
import lw_clean_replay as R  # noqa: E402
import lw_clean_spot as SPOT  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDEDITS = os.path.join(ROOT, "ops", "runtime", "clean", "handedits")
SCRATCH = os.path.join(ROOT, "images", "3.Cleaning Scratch")
DGK = "dgk8f92-bc10d7a7-f520-4b4f-ad86-ac70f6d50293"

CAPTURES = [("105", "105-cleanup", "105-cleanup", "credit line"),
            ("107", "107-cleanup", "107-cleanup", "area"),
            ("209", "209-cleanup", "209-cleanup", "painted signature"),
            ("dgk", DGK, "dgk8f92", "block logo")]


def union_mask(capture, name_contains):
    masks, outs = R.collect(capture, name_contains)
    acc = None
    for i in sorted(masks):
        m = np.asarray(Image.open(masks[i]).convert("L")) > 127
        acc = m if acc is None else (acc | m)
    return acc, outs[max(outs)]


def in_mask_distance(a, truth, mask):
    d = np.abs(a.astype(np.int16) - truth.astype(np.int16)).max(axis=2)
    return round(float(d[mask].mean()), 3)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lw_clean_condition_census")
    ap.add_argument("--out", default=os.path.join(ROOT, "ops", "runtime",
                                                  "clean", "condition"))
    ap.add_argument("--no-fill", action="store_true",
                    help="model fit only; skips the GPU half")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)

    fill = None if args.no_fill else SPOT._lama()
    rows = []
    for tag, folder, name_contains, art in CAPTURES:
        mark, op_path = union_mask(os.path.join(HANDEDITS, folder),
                                   name_contains)
        marked = R.load_rgb(os.path.join(SCRATCH, folder,
                                         f"{folder}_cleaninitial.png"))
        truth = R.load_rgb(op_path)

        rec = {"tag": tag, "art": art, "mask_px": int(mark.sum()),
               "fit": C.fit_veil(marked, truth, mark),
               "estimate": C.estimate_veil(marked, mark)}
        cond, crec = C.auto_condition(marked, mark)
        rec["conditioned_px"] = crec["conditioned_px"]
        rec["blobs_conditioned"] = sum(1 for s in crec["steps"] if s["applies"])
        rec["blobs"] = len(crec["steps"])
        rec["distance"] = {"untouched": in_mask_distance(marked, truth, mark),
                           "conditioned": in_mask_distance(cond, truth, mark)}
        Image.fromarray(cond).save(os.path.join(args.out, f"{tag}_cond.png"))

        if fill is not None:
            plain, pplan = SPOT.run_spot_heal(marked, mark, fill)
            after, aplan = SPOT.run_spot_heal(cond, mark, fill)
            rec["distance"]["fill"] = in_mask_distance(plain, truth, mark)
            rec["distance"]["condition_then_fill"] = in_mask_distance(
                after, truth, mark)
            rec["held"] = {"fill": pplan["held"],
                           "condition_then_fill": aplan["held"]}
            Image.fromarray(after).save(
                os.path.join(args.out, f"{tag}_cond_fill.png"))
        rows.append(rec)

    print(f"{'slug':5s} {'art':18s} {'fit r2 (R/G/B)':>22s} {'fit alpha':>10s} "
          f"{'ring alpha':>10s}  model?")
    for r in rows:
        f = r["fit"]
        r2 = "/".join(f"{v:.2f}" for v in f["r2"])
        al = "/".join(f"{v:.2f}" for v in f["alpha"])
        ok = "yes" if min(f["r2"]) > 0.8 else "NO"
        e = r["estimate"]
        print(f"{r['tag']:5s} {r['art']:18s} {r2:>22s} {al:>10s} "
              f"{e['alpha']:10.3f}  {ok}")

    print()
    keys = ["untouched", "conditioned", "fill", "condition_then_fill"]
    print(f"{'slug':5s} " + " ".join(f"{k:>19s}" for k in keys))
    for r in rows:
        cells = []
        for k in keys:
            v = r["distance"].get(k)
            cells.append("                  -" if v is None else f"{v:19.2f}")
        print(f"{r['tag']:5s} " + " ".join(cells))

    path = os.path.join(args.out, "condition_census.json")
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"captures": rows}, fh, indent=2)
    os.replace(tmp, path)
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
