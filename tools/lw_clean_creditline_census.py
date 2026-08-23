"""Census for the credit-line reader: gold accuracy, coverage, false positives.

Three questions, and the third is the one the repo has been burned by before:

  GOLD      on the two captures whose brush masks are known, how much of the
            operator's own mask does the read cover, and what does the frame
            look like when the proven fill is handed that mask?
  COVERAGE  how many of the queued slugs does it find a line on?
  PRECISION does it fire on frames the operator APPROVED AS CLEAN? The claim
            "false positives are zero" was overturned once already, on 7 slugs
            that turned out to carry no mark at all, so the negative set is
            sampled rather than assumed.

Needs the lw-clean venv - easyocr, and simple-lama for the --fill half.

  C:\\Tools\\lw-clean\\venv\\Scripts\\python.exe tools/lw_clean_creditline_census.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_clean_creditline as CL  # noqa: E402
import lw_clean_replay as R  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = os.path.join(ROOT, "images", "3.Cleaning Scratch")
DONE = os.path.join(ROOT, "images", "4.Cleaning Done")
HANDEDITS = os.path.join(ROOT, "ops", "runtime", "clean", "handedits")
DGK = "dgk8f92-bc10d7a7-f520-4b4f-ad86-ac70f6d50293"
GOLD = [("105", "105-cleanup", "105-cleanup"),
        ("107", "107-cleanup", "107-cleanup"),
        ("209", "209-cleanup", "209-cleanup"),
        ("dgk", DGK, "dgk8f92")]


def initial_of(root, slug):
    for name in (f"{slug}_cleaninitial.png", f"{slug}_firstinitial.png"):
        p = os.path.join(root, slug, name)
        if os.path.exists(p):
            return p
    return None


def brush_of(folder, nc):
    masks, outs = R.collect(os.path.join(HANDEDITS, folder), nc)
    b = None
    for i in sorted(masks):
        a = np.asarray(Image.open(masks[i]).convert("L")) > 127
        b = a if b is None else (b | a)
    return b, outs[max(outs)]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lw_clean_creditline_census")
    ap.add_argument("--out", default=os.path.join(ROOT, "ops", "runtime",
                                                  "clean", "creditline"))
    ap.add_argument("--negatives", type=int, default=120,
                    help="how many approved-clean slugs to sample")
    ap.add_argument("--fill", action="store_true",
                    help="also run the proven fill on the gold masks")
    ap.add_argument("--cpu", action="store_true")
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)

    reader = CL._reader(gpu=not args.cpu)
    rec = {"gold": [], "scratch": [], "negatives": []}

    fill = None
    if args.fill:
        import lw_clean_spot as SPOT
        fill = SPOT._lama()

    print("=== gold ===")
    for tag, folder, nc in GOLD:
        brush, op_path = brush_of(folder, nc)
        img = R.load_rgb(initial_of(SCRATCH, folder))
        hits = CL.detect(img, reader)
        row = {"tag": tag, "hits": hits, "brush_px": int(brush.sum())}
        if hits:
            m = CL.mask_from_hits(img.shape, hits)
            inter = int((m & brush).sum())
            row.update(mask_px=int(m.sum()),
                       precision=round(inter / max(1, int(m.sum())), 4),
                       covers=round(inter / max(1, int(brush.sum())), 4))
            if fill is not None:
                import lw_clean_spot as SPOT
                truth = R.load_rgb(op_path).astype(np.int16)
                out, plan = SPOT.run_spot_heal(img, m, fill)
                d = np.abs(out.astype(np.int16) - truth).max(axis=2)
                d0 = np.abs(img.astype(np.int16) - truth).max(axis=2)
                row["frame"] = round(float(d[brush].mean()), 3)
                row["frame_untouched"] = round(float(d0[brush].mean()), 3)
                row["held"] = plan["held"]
                Image.fromarray(out).save(
                    os.path.join(args.out, f"{tag}_creditline_fill.png"))
        rec["gold"].append(row)
        print(f"  {tag:5s} hits={len(hits)} " +
              (f"px={row.get('mask_px')} prec={row.get('precision')} "
               f"covers={row.get('covers')} frame={row.get('frame')} "
               f"(untouched {row.get('frame_untouched')}) held={row.get('held')}"
               if hits else "(no credit line read)"))

    print("\n=== scratch coverage ===")
    for slug in sorted(os.listdir(SCRATCH)):
        p = initial_of(SCRATCH, slug)
        if not p:
            continue
        hits = CL.detect(R.load_rgb(p), reader)
        rec["scratch"].append({"slug": slug, "n": len(hits),
                               "text": hits[0]["text"] if hits else None,
                               "conf": hits[0]["conf"] if hits else None})
    found = [r for r in rec["scratch"] if r["n"]]
    print(f"  {len(found)} of {len(rec['scratch'])} queued slugs carry a "
          f"readable credit line")

    print("\n=== negatives (operator-approved clean) ===")
    slugs = sorted(os.listdir(DONE))[:args.negatives]
    for slug in slugs:
        p = initial_of(DONE, slug)
        if not p:
            continue
        hits = CL.detect(R.load_rgb(p), reader)
        rec["negatives"].append({"slug": slug, "n": len(hits),
                                 "text": hits[0]["text"] if hits else None})
    fp = [r for r in rec["negatives"] if r["n"]]
    print(f"  {len(fp)} of {len(rec['negatives'])} approved-clean slugs fired")
    for r in fp[:10]:
        print(f"    {r['slug']}: {r['text']}")

    path = os.path.join(args.out, "creditline_census.json")
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(rec, fh, indent=2)
    os.replace(tmp, path)
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
