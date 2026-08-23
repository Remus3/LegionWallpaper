"""Sweep the glyph percentile on one slug and stack the results at 1:1.

`GLYPH_PCT = 88` was chosen by one slug picking one of nine cells, on 105, whose
credit line sits over flat mid-tone art. On 259f - a light overlay over bright,
busy art - it lands on a fraction of the strokes and the line is still fully
legible after nine committed blobs, twice over. That is a mask that is too thin,
and no number of further rounds fixes a mask that is too thin.

A LOWER percentile is a THICKER mask: p88 keeps the top 12 percent of the
high-pass inside the verified box, p50 keeps half of it. Down at the bottom the
mask stops being stroke-shaped and becomes the slab that was already measured to
break lines, so the rollback firing is a result and not a failure of the run.

There is no ground truth here - 259f is not one of the four hand-clean captures -
so this produces no score and picks no winner. It produces one sheet: the same
crop at native resolution, once per percentile, labelled with what the run did.
The operator's eye picks.

  C:\\Tools\\lw-clean\\venv\\Scripts\\python.exe tools/lw_clean_creditline_sweep.py --slug 259f
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_clean_creditline as CL  # noqa: E402
import lw_clean_creditline_run as RUN  # noqa: E402
import lw_clean_heal_compare as SHEET  # noqa: E402
import lw_clean_spot as SPOT  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = os.path.join(ROOT, "images", "3.Cleaning Scratch")
OUT = os.path.join(ROOT, "ops", "runtime", "clean", "creditline", "sweep")

# Thin to thick. 88 is the incumbent and stays first so the sheet opens on what
# the lane does today; the rest halve the survivor fraction step by step.
PCTS = "88,80,70,60,50,40,25"


def parse_pcts(text):
    """Percentiles, thickest LAST, so the sheet reads as more and more paint."""
    vals = []
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            raise ValueError(f"empty percentile in {text!r}")
        v = float(part)
        if not 0.0 <= v <= 100.0:
            raise ValueError(f"percentile out of range: {v}")
        vals.append(v)
    if not vals:
        raise ValueError("no percentiles given")
    return sorted(set(vals), reverse=True)


def label_for(pct, rec):
    """What the row is, in the three numbers that explain it."""
    return (f"p{pct:g}  mask={rec['mask_px']}  "
            f"{rec['committed']} healed, {rec['held']} held  "
            f"{'reads' if rec['still_reads'] else 'quiet'}")


def main(argv=None):
    from PIL import Image
    import lw_clean_replay as R
    from lw_clean_creditline_census import initial_of
    Image.MAX_IMAGE_PIXELS = None

    ap = argparse.ArgumentParser(prog="lw_clean_creditline_sweep")
    ap.add_argument("--slug", default="259f")
    ap.add_argument("--scratch", default=SCRATCH)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--pcts", default=PCTS)
    ap.add_argument("--pad", type=int, default=CL.PAD)
    ap.add_argument("--cpu", action="store_true")
    args = ap.parse_args(argv)

    pcts = parse_pcts(args.pcts)
    path = initial_of(args.scratch, args.slug)
    if not path:
        raise SystemExit(f"no cleaning initial for {args.slug}")
    out_dir = os.path.join(args.out, args.slug)
    os.makedirs(out_dir, exist_ok=True)

    reader = CL._reader(gpu=not args.cpu)
    fill = SPOT._lama()
    img = R.load_rgb(path)
    hits = CL.detect(img, reader)
    if not hits:
        raise SystemExit(f"no credit line read on {args.slug}")

    rows, variants = [], [("untouched", path)]
    for pct in pcts:
        out, rec = RUN.run_one(img, hits, fill, pad=args.pad, glyph_pct=pct)
        rec["still_reads"] = [{"text": a["text"], "conf": a["conf"]}
                              for a in CL.detect(out, reader)]
        rec["pct"] = pct
        rec["out"] = RUN._write_png(out, os.path.join(out_dir, f"p{pct:g}.png"))
        rows.append({k: v for k, v in rec.items() if k != "steps"})
        variants.append((label_for(pct, rec), rec["out"]))
        print(label_for(pct, rec))

    window = RUN.crop_box_from_hits([{"box": rows[0]["box"]}], img.shape)
    sheet = os.path.join(out_dir, f"{args.slug}_glyphpct_sweep.png")
    SHEET.build(variants, window, sheet)
    RUN._write_json({"slug": args.slug, "source": path, "rows": rows},
                    os.path.join(out_dir, "sweep.json"))
    print(f"\nwrote {sheet}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
