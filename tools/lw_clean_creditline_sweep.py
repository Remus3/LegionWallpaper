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
    part = f", {rec['partial']} partial" if rec.get("partial") else ""
    return (f"p{pct:g}  mask={rec['mask_px']}  "
            f"{rec['committed']} healed, {rec['held']} held{part}  "
            f"{'reads' if rec['still_reads'] else 'quiet'}")


def sweep_one(slug, path, pcts, reader, fill, out_dir, pad=CL.PAD,
              scoped=False):
    """Every percentile on one slug, off the untouched frame, stacked at 1:1."""
    import lw_clean_replay as R
    img = R.load_rgb(path)
    hits = CL.detect(img, reader)
    if not hits:
        print(f"{slug}: no credit line read - skipped")
        return None
    os.makedirs(out_dir, exist_ok=True)
    rows, variants = [], [("untouched", path)]
    for pct in pcts:
        out, rec = RUN.run_one(img, hits, fill, pad=pad, glyph_pct=pct,
                               scoped=scoped)
        rec["still_reads"] = [{"text": a["text"], "conf": a["conf"]}
                              for a in CL.detect(out, reader)]
        rec["pct"] = pct
        rec["out"] = RUN._write_png(out, os.path.join(out_dir, f"p{pct:g}.png"))
        rows.append({k: v for k, v in rec.items() if k != "steps"})
        variants.append((label_for(pct, rec), rec["out"]))
        print(f"  {label_for(pct, rec)}")
    window = RUN.crop_box_from_hits([{"box": rows[0]["box"]}], img.shape)
    sheet = os.path.join(out_dir, f"{slug}_glyphpct_sweep.png")
    SHEET.build(variants, window, sheet)
    rec = {"slug": slug, "source": path, "sheet": sheet, "rows": rows}
    RUN._write_json(rec, os.path.join(out_dir, "sweep.json"))
    return rec


def first_quiet(rows):
    """The thinnest mask whose output the reader no longer reads.

    A floor, not a verdict. 259f goes quiet at p70 with the line still plainly
    legible on the sheet, so this marks where to START looking, never where to
    stop.
    """
    for r in rows:
        if not r["still_reads"]:
            return r["pct"]
    return None


def build_parser():
    ap = argparse.ArgumentParser(prog="lw_clean_creditline_sweep")
    ap.add_argument("--slug", action="append",
                    help="repeatable; defaults to 259f")
    ap.add_argument("--scratch", default=SCRATCH)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--pcts", default=PCTS)
    ap.add_argument("--pad", type=int, default=CL.PAD)
    ap.add_argument("--cpu", action="store_true")
    ap.add_argument("--scoped-revert", action="store_true",
                    help="accepted and ignored - scoped is the default since "
                         "the 2026-08-29 verdict; use --no-scoped-revert to "
                         "hand back the whole blob")
    ap.add_argument("--no-scoped-revert", action="store_true",
                    help="hand back the WHOLE blob when a fill breaks a line, "
                         "the pre-2026-08-29 behaviour")
    return ap


def main(argv=None):
    from PIL import Image
    from lw_clean_creditline_census import initial_of
    Image.MAX_IMAGE_PIXELS = None

    args = build_parser().parse_args(argv)
    pcts = parse_pcts(args.pcts)
    slugs = args.slug or ["259f"]
    reader = CL._reader(gpu=not args.cpu)
    fill = SPOT._lama()

    done = []
    for slug in slugs:
        path = initial_of(args.scratch, slug)
        if not path:
            print(f"{slug}: no cleaning initial - skipped")
            continue
        print(f"=== {slug}")
        rec = sweep_one(slug, path, pcts, reader, fill,
                        os.path.join(args.out, slug), pad=args.pad,
                        scoped=not args.no_scoped_revert)
        if rec:
            done.append(rec)
            print(f"  first quiet at p{first_quiet(rec['rows'])}")

    summary = {"pcts": pcts,
               "slugs": [{"slug": r["slug"], "sheet": r["sheet"],
                          "first_quiet": first_quiet(r["rows"]),
                          "rows": r["rows"]} for r in done]}
    print("\nwrote " + RUN._write_json(summary,
                                       os.path.join(args.out, "sweep.json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
