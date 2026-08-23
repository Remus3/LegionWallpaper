"""Run the credit-line lane over the queue and put 1:1 crops in front of an eye.

The chain the 2026-08-22 investigation left behind is read the line -> narrow the
verified box to its glyphs -> heal each blob with rollback. Every piece was
measured on its own; none of it has been LOOKED at on more than two frames, and
the acceptance bar is the operator's eye on a 1:1 crop with zero residue - ghost,
banding and faint all fail. So this runner's deliverable is not a score. It is
one sheet per slug: the same crop, native pixels, untouched above and cleaned
below, cropped to the region the reader itself claimed.

What it records per slug is diagnostic, never a verdict:

  held        blobs the rollback undid, which means the slug stays in the queue
  still_reads whether the reader still finds a credit line in the OUTPUT. A
              clear read afterwards is proof of failure; silence is NOT proof of
              success - the reader needs contrast, and a faint ghost that fails
              the operator's bar can easily fall under it. On 105 the lane
              reaches 11.56 against 15.45 untouched and the operator's own 8.08,
              so expect reduced, not finished.

Needs the lw-clean venv - easyocr, and simple-lama for the fill.

  C:\\Tools\\lw-clean\\venv\\Scripts\\python.exe tools/lw_clean_creditline_run.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_clean_creditline as CL  # noqa: E402
import lw_clean_heal_compare as SHEET  # noqa: E402
import lw_clean_spot as SPOT  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = os.path.join(ROOT, "images", "3.Cleaning Scratch")
OUT = os.path.join(ROOT, "ops", "runtime", "clean", "creditline", "run")

# Context around the read box in the review sheet. Wider than the fill's own pad
# on purpose: a seam or a banding edge shows up against the art beside it, not
# against the mark it replaced.
CROP_PAD = 80


def crop_box_from_hits(hits, shape, pad=CROP_PAD):
    """The review window: every hit box, unioned, padded, clipped to the frame."""
    if not hits:
        return None
    h, w = int(shape[0]), int(shape[1])
    xs0 = min(r["box"][0] for r in hits)
    ys0 = min(r["box"][1] for r in hits)
    xs1 = max(r["box"][2] for r in hits)
    ys1 = max(r["box"][3] for r in hits)
    return (max(0, xs0 - pad), max(0, ys0 - pad),
            min(w, xs1 + pad), min(h, ys1 + pad))


def run_one(img, hits, inpaint, pad=CL.PAD, box_shape=False, rollback=True,
            log=None):
    """Read box -> glyph mask -> per-blob heal. Returns the frame and a record."""
    img = np.asarray(img, dtype=np.uint8)
    rec = {"box": None, "box_px": 0, "mask_px": 0, "blobs": 0,
           "committed": 0, "held": 0, "n_chords": 0, "status": "no-hit",
           "steps": []}
    if not hits:
        return img.copy(), rec
    rec["box"] = [min(r["box"][0] for r in hits),
                  min(r["box"][1] for r in hits),
                  max(r["box"][2] for r in hits),
                  max(r["box"][3] for r in hits)]
    box = CL.mask_from_hits(img.shape, hits, pad=pad)
    mask = box if box_shape else CL.glyph_mask(img, box)
    rec["box_px"] = int(box.sum())
    rec["mask_px"] = int(mask.sum())
    out, plan = SPOT.run_spot_heal(img, mask, inpaint, rollback=rollback,
                                   log=log)
    for key in ("blobs", "committed", "held", "n_chords", "status", "steps"):
        rec[key] = plan[key]
    return out, rec


def review_order(rows):
    """Worst first: still reading, then held blobs, then the widest repaint.

    The operator looks at sheets in the order most likely to find a failure,
    because the bar is zero residue and a single bad frame settles the lane.
    """
    return sorted(rows, key=lambda r: (-len(r.get("still_reads") or []),
                                       -int(r.get("held") or 0),
                                       -int(r.get("mask_px") or 0),
                                       str(r.get("slug"))))


def write_index(summary, path):
    """A review sheet index - links, worst first, and no verdict anywhere."""
    rows = review_order(summary.get("rows") or [])
    out = ["# Credit-line lane - review queue", "",
           f"{summary.get('n', 0)} slugs cleaned - "
           f"{summary.get('held', 0)} with a held blob - "
           f"{summary.get('still_reads', 0)} still reading a credit line.", "",
           "Acceptance is the eye on the 1:1 crop: ghost, banding and faint all",
           "FAIL. `still_reads` is diagnostic - a read afterwards proves failure,",
           "silence proves nothing.", "",
           "| # | slug | held | reads again | mask px | sheet |",
           "|---|------|------|-------------|---------|-------|"]
    for i, r in enumerate(rows, 1):
        sheet = os.path.basename(str(r.get("sheet") or ""))
        out.append(f"| {i} | {r.get('slug')} | {r.get('held')} | "
                   f"{len(r.get('still_reads') or [])} | {r.get('mask_px')} | "
                   f"[{sheet}]({sheet}) |")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    os.replace(tmp, path)
    return path


def _write_png(arr, path):
    from PIL import Image
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".part"
    Image.fromarray(arr).save(tmp, format="PNG")
    os.replace(tmp, path)
    return path


def _write_json(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, indent=2)
    os.replace(tmp, path)
    return path


def main(argv=None):
    from PIL import Image
    import lw_clean_replay as R
    Image.MAX_IMAGE_PIXELS = None

    ap = argparse.ArgumentParser(prog="lw_clean_creditline_run")
    ap.add_argument("--scratch", default=SCRATCH)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--slug", action="append",
                    help="run only these slugs (repeatable)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-rollback", action="store_true")
    ap.add_argument("--box", action="store_true",
                    help="fill the solid read box (measured worse)")
    ap.add_argument("--cpu", action="store_true")
    args = ap.parse_args(argv)

    from lw_clean_creditline_census import initial_of
    slugs = args.slug or sorted(os.listdir(args.scratch))
    reader = CL._reader(gpu=not args.cpu)
    fill = SPOT._lama()
    os.makedirs(args.out, exist_ok=True)

    rows = []
    for slug in slugs:
        path = initial_of(args.scratch, slug)
        if not path:
            continue
        t0 = time.time()
        img = R.load_rgb(path)
        hits = CL.detect(img, reader)
        if not hits:
            continue
        out, rec = run_one(img, hits, fill, box_shape=args.box,
                           rollback=not args.no_rollback)
        rec.update(slug=slug, source=path, n_hits=len(hits),
                   text=hits[0]["text"], conf=hits[0]["conf"])
        rec["out"] = _write_png(out, os.path.join(args.out,
                                                  f"{slug}_creditline.png"))
        after = CL.detect(out, reader)
        rec["still_reads"] = [{"text": a["text"], "conf": a["conf"]}
                              for a in after]
        window = crop_box_from_hits(hits, img.shape)
        rec["sheet"] = os.path.join(args.out, f"{slug}_sheet.png")
        SHEET.build([("untouched", path), ("cleaned", rec["out"])], window,
                    rec["sheet"])
        rec["seconds"] = round(time.time() - t0, 1)
        _write_json(rec, os.path.join(args.out, f"{slug}_plan.json"))
        rows.append({k: v for k, v in rec.items() if k != "steps"})
        print(f"{slug}: blobs={rec['blobs']} held={rec['held']} "
              f"mask={rec['mask_px']}px still_reads={len(after)} "
              f"{rec['seconds']}s")
        if args.limit and len(rows) >= args.limit:
            break

    summary = {"scratch": args.scratch, "n": len(rows),
               "held": sum(1 for r in rows if r["held"]),
               "still_reads": sum(1 for r in rows if r["still_reads"]),
               "rows": rows}
    print("\nwrote " + _write_json(summary, os.path.join(args.out,
                                                        "run_summary.json")))
    print("wrote " + write_index(summary, os.path.join(args.out, "REVIEW.md")))
    print(f"{summary['n']} slugs cleaned, {summary['held']} with a held blob, "
          f"{summary['still_reads']} still reading a credit line")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
