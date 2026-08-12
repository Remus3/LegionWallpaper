"""Build labelled contact sheets for the `qa` rows of a cleaning-detector census.

The recall census (`tools/lw_clean_detector_probe.py --corpus firstdone`) counts a
`qa` verdict as "caught" without ever asking whether the flagged region carries a
real mark, so the human queue's PRECISION is unmeasured. This tool crops what each
`qa` row actually flagged and tiles the crops into sheets an operator (or a vision
pass) can label by eye - the same way the precision and recall censuses were settled.

What gets cropped depends on the reason:
  centre_overlay -> the overlay template's own support bbox (that is the evidence
                    the flag fired on), padded, plus a high-pass boost tile because
                    the DA overlay is deliberately low-amplitude.
  everything else -> the union of the YOLO boxes the gate saw (`faint_marks` for a
                    `faint_mark` row), padded to a legible minimum.

Usage:
  python tools/lw_clean_qa_crops.py                 # all qa rows, all reasons
  python tools/lw_clean_qa_crops.py --reason not_border --per-sheet 6
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CENSUS = os.path.join(ROOT, "ops", "runtime", "clean_recall_census_gatev4.json")
TEMPLATE = os.path.join(ROOT, "ops", "runtime", "clean", "overlay_template.npz")
CORPUS = os.path.join(ROOT, "images", "2.First Pass Done")
OUTDIR = os.path.join(ROOT, "ops", "runtime", "clean", "qa_precision")

CELL_W = 760
PAD_BOX = 48
PAD_OVERLAY = 40
LABEL_H = 26


def _support_bbox_rel():
    """Relative (x0, y0, x1, y1) of the overlay template's support, frame coords."""
    z = np.load(TEMPLATE)
    sup = z["support"]
    band = tuple(float(v) for v in z["band"])
    rows = np.where(sup.any(axis=1))[0]
    cols = np.where(sup.any(axis=0))[0]
    bh = sup.shape[0]
    y0 = band[0] + (band[1] - band[0]) * (rows[0] / bh)
    y1 = band[0] + (band[1] - band[0]) * (rows[-1] / bh)
    return cols[0] / sup.shape[1], y0, cols[-1] / sup.shape[1], y1


def _boost(crop: Image.Image) -> Image.Image:
    """Amplified high-pass view - a viewing aid for a low-amplitude mark."""
    a = np.asarray(crop.convert("L"), dtype=np.float64)
    lo = np.asarray(
        crop.convert("L").resize((max(1, a.shape[1] // 9), max(1, a.shape[0] // 9)),
                                 Image.BOX).resize(crop.size, Image.BILINEAR),
        dtype=np.float64,
    )
    hp = np.clip((a - lo) * 6.0 + 128.0, 0, 255).astype(np.uint8)
    return Image.fromarray(hp)


def _firstdone(slug: str) -> str | None:
    p = os.path.join(CORPUS, slug, slug + "_firstdone.png")
    return p if os.path.exists(p) else None


def _region(row: dict, sup_rel) -> tuple[int, int, int, int]:
    w, h = int(row["w"]), int(row["h"])
    if row["reason"] == "centre_overlay":
        x0, y0, x1, y1 = sup_rel
        return (
            max(0, int(x0 * w) - PAD_OVERLAY),
            max(0, int(y0 * h) - PAD_OVERLAY * 3),
            min(w, int(x1 * w) + PAD_OVERLAY),
            min(h, int(y1 * h) + PAD_OVERLAY),
        )
    boxes = row.get("boxes") or []
    if row["reason"] == "faint_mark" or not boxes:
        boxes = [m["box"] for m in (row.get("faint_marks") or [])] or boxes
    if not boxes:
        return (0, 0, w, h)
    xs0 = min(b[0] for b in boxes)
    ys0 = min(b[1] for b in boxes)
    xs1 = max(b[2] for b in boxes)
    ys1 = max(b[3] for b in boxes)
    cx, cy = (xs0 + xs1) / 2, (ys0 + ys1) / 2
    half_w = max((xs1 - xs0) / 2 + PAD_BOX, 260)
    half_h = max((ys1 - ys0) / 2 + PAD_BOX, 150)
    return (
        max(0, int(cx - half_w)), max(0, int(cy - half_h)),
        min(w, int(cx + half_w)), min(h, int(cy + half_h)),
    )


def _cell(row: dict, sup_rel, boost: bool):
    path = _firstdone(row["slug"])
    if not path:
        return None
    im = Image.open(path).convert("RGB")
    reg = _region(row, sup_rel)
    crop = im.crop(reg)
    if row["reason"] != "centre_overlay":
        d = ImageDraw.Draw(crop)
        boxes = row.get("boxes") or []
        if row["reason"] == "faint_mark" or not boxes:
            boxes = [m["box"] for m in (row.get("faint_marks") or [])] or boxes
        for b in boxes:
            d.rectangle(
                [b[0] - reg[0], b[1] - reg[1], b[2] - reg[0], b[3] - reg[1]],
                outline=(255, 0, 0), width=3,
            )
    scale = CELL_W / crop.width
    crop = crop.resize((CELL_W, max(1, int(crop.height * scale))), Image.LANCZOS)
    tiles = [crop]
    if boost and row["reason"] == "centre_overlay":
        tiles.append(_boost(crop).convert("RGB"))
    height = sum(t.height for t in tiles) + LABEL_H
    cell = Image.new("RGB", (CELL_W, height), (20, 20, 20))
    y = LABEL_H
    for t in tiles:
        cell.paste(t, (0, y))
        y += t.height
    lab = "{} | ov={:.3f} nb={} cmax={:.2f}".format(
        row["slug"][:52], row["overlay_score"], row["n_boxes"], row["conf_max"])
    ImageDraw.Draw(cell).text((6, 7), lab, fill=(255, 255, 0))
    return cell


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default=CENSUS)
    ap.add_argument("--reason", default=None)
    ap.add_argument("--slug", default=None)
    ap.add_argument("--per-sheet", type=int, default=4)
    ap.add_argument("--no-boost", action="store_true")
    ap.add_argument("--outdir", default=OUTDIR)
    args = ap.parse_args()

    rows = [r for r in json.load(open(args.census))["detect"] if r["verdict"] == "qa"]
    if args.reason:
        rows = [r for r in rows if r["reason"] == args.reason]
    if args.slug:
        rows = [r for r in rows if r["slug"] == args.slug]
    rows.sort(key=lambda r: (r["reason"], r["slug"]))
    sup_rel = _support_bbox_rel()
    os.makedirs(args.outdir, exist_ok=True)

    sheet, n = [], 0
    for row in rows:
        cell = _cell(row, sup_rel, not args.no_boost)
        if cell is None:
            print("MISSING firstdone:", row["slug"])
            continue
        sheet.append((row, cell))
        if len(sheet) == args.per_sheet:
            n += 1
            _write(sheet, args.outdir, n)
            sheet = []
    if sheet:
        n += 1
        _write(sheet, args.outdir, n)
    return 0


def _write(sheet, outdir, n):
    w = max(c.width for _, c in sheet)
    h = sum(c.height + 8 for _, c in sheet)
    im = Image.new("RGB", (w, h), (0, 0, 0))
    y = 0
    for _, c in sheet:
        im.paste(c, (0, y))
        y += c.height + 8
    tag = sheet[0][0]["reason"]
    out = os.path.join(outdir, f"sheet_{tag}_{n:02d}.png")
    im.save(out)
    print(out, "|", ", ".join(r["slug"] for r, _ in sheet))


if __name__ == "__main__":
    sys.exit(main())
