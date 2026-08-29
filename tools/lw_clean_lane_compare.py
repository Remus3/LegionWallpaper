"""Stack one slug's output across LANE CONFIGURATIONS, cropped to what differs.

`lw_clean_creditline_run.py` writes one review sheet per slug per run - untouched
above, cleaned below - which answers "is this frame clean" for ONE configuration.
It cannot answer the question a default flip actually turns on, which is whether
`--stubs` or `--scoped-revert` made a frame BETTER OR WORSE than the run without
it. Answering that from two sheets means flipping between two files of the same
crop and holding the difference in your head.

So this puts every configuration in one column at native pixels, and crops to the
union of the pixels that differ between them. Everything outside that box is
byte-identical across the runs by construction, and including it only shrinks
what the eye can see of the part that moved.

The output is a strip and an index, worst-first by changed pixels. There is no
score and no verdict: the acceptance bar is the operator's eye at 1:1, ghost /
banding / faint all FAIL.

  python tools/lw_clean_lane_compare.py --out <dir> \
      neither=ops/runtime/clean/creditline/run \
      stubs=ops/runtime/clean/creditline/run_stubs4 \
      "stubs+scoped=ops/runtime/clean/creditline/run_stubs_scoped"
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_clean_heal_compare as SHEET  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

# Wider than the run sheet's own pad. A revert that puts a band of the mark back
# is judged against the art beside it, not against the band.
PAD = 60
SUFFIX = "_creditline.png"


def changed_box(arrays, pad=PAD):
    """Padded bbox of every pixel where the variants disagree, or None.

    One variant can never disagree with itself, so a single array is None too -
    a slug present in only one run has nothing to compare and is not a row.
    """
    if len(arrays) < 2:
        return None
    base = arrays[0]
    diff = np.zeros(base.shape[:2], dtype=bool)
    for other in arrays[1:]:
        diff |= np.any(base != other, axis=2)
    ys, xs = np.nonzero(diff)
    if ys.size == 0:
        return None
    h, w = base.shape[:2]
    return (max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad),
            min(w, int(xs.max()) + 1 + pad), min(h, int(ys.max()) + 1 + pad))


def slug_of(path):
    return os.path.basename(path)[:-len(SUFFIX)]


def common_slugs(dirs):
    """Slugs every run produced an output for, so no row compares a hole."""
    sets = [{slug_of(p) for p in glob.glob(os.path.join(d, "*" + SUFFIX))}
            for d in dirs]
    return sorted(set.intersection(*sets)) if sets else []


def untouched_source(dirs, slug):
    """The input frame, taken from whichever plan recorded it. Never a run's."""
    for d in dirs:
        plan = os.path.join(d, f"{slug}_plan.json")
        if not os.path.exists(plan):
            continue
        with open(plan, encoding="utf-8") as fh:
            src = json.load(fh).get("source")
        if src and os.path.exists(src):
            return src
    return None


def _load(path):
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB"))


def write_index(rows, out_path, labels):
    """Worst-first by changed pixels, and no verdict anywhere."""
    head = " | ".join(f"{lab} held/partial" for lab in labels)
    lines = ["# Lane comparison - one strip per slug, configurations stacked",
             "",
             f"{len(rows)} slugs compared, {sum(1 for r in rows if r['changed_px'])}"
             " differ between configurations.",
             "",
             "Acceptance is the eye at 1:1: ghost, banding and faint all FAIL.",
             "A partial revert puts a band of the ORIGINAL back, mark included,",
             "so it is the row most likely to fail the bar.",
             "",
             f"| # | slug | changed px | {head} | strip |",
             "|---|------|-----------:|" + "---|" * len(labels) + "---|"]
    for i, r in enumerate(rows, 1):
        cells = " | ".join(f"{r['plans'][lab][0]}/{r['plans'][lab][1]}"
                           if lab in r["plans"] else "-" for lab in labels)
        strip = os.path.basename(r["strip"]) if r["strip"] else ""
        link = f"[{strip}]({strip})" if strip else "(identical)"
        lines.append(f"| {i} | {r['slug']} | {r['changed_px']} | {cells} | {link} |")
    tmp = out_path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, out_path)
    return out_path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lw_clean_lane_compare")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pad", type=int, default=PAD)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("runs", nargs="+", help="label=run-dir, in display order")
    args = ap.parse_args(argv)

    labels, dirs = [], []
    for spec in args.runs:
        label, _, d = spec.partition("=")
        if not d or not os.path.isdir(d):
            raise SystemExit(f"missing run dir: {spec}")
        labels.append(label)
        dirs.append(d)

    os.makedirs(args.out, exist_ok=True)
    rows = []
    for slug in common_slugs(dirs):
        outs = [os.path.join(d, slug + SUFFIX) for d in dirs]
        box = changed_box([_load(p) for p in outs], pad=args.pad)
        plans = {}
        for label, d in zip(labels, dirs, strict=True):
            plan = os.path.join(d, f"{slug}_plan.json")
            if os.path.exists(plan):
                with open(plan, encoding="utf-8") as fh:
                    rec = json.load(fh)
                plans[label] = (rec.get("held", 0), rec.get("partial", 0))
        if box is None:
            rows.append({"slug": slug, "changed_px": 0, "strip": None,
                         "plans": plans})
            continue
        variants = []
        src = untouched_source(dirs, slug)
        if src:
            variants.append(("untouched", src))
        variants += list(zip(labels, outs, strict=True))
        strip = os.path.join(args.out, f"{slug}_lanes.png")
        SHEET.build(variants, box, strip)
        changed = int(np.count_nonzero(np.any(
            _load(outs[0]) != _load(outs[-1]), axis=2)))
        rows.append({"slug": slug, "changed_px": changed, "strip": strip,
                     "plans": plans, "box": list(box)})
        print(f"{slug}: changed={changed}px box={box}")
        if args.limit and sum(1 for r in rows if r["strip"]) >= args.limit:
            break

    rows.sort(key=lambda r: -r["changed_px"])
    print("wrote " + write_index(rows, os.path.join(args.out, "REVIEW.md"),
                                 labels))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
