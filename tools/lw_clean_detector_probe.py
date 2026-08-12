"""lw_clean_detector_probe.py - measure cleaning-detector PRECISION.

ROADMAP item `clean-retry-degrades`, half 2 (`cleaning-detector-precision`):
"the cleaner FINDS work on images that need none". Half 1 measured the retry
ladder; this measures the DETECTOR, i.e. how often detect -> gate proposes an
edit on content the operator ruled clean.

Two halves, both reported as measured counts:

  LABEL census (stdlib only) - derives each cleaning-stage slug's operator
  label from ground truth already on disk:
    * `needs_none`  - a REJECT note saying no watermark / defect was present,
      OR an APPROVE_CLEAN whose sha256 equals the slug's `_cleaninitial`
      (the operator selected the UNCLEANED pixels, so no edit was wanted).
    * `wrong_edit`  - a REJECT note saying the corrections are contextually
      incorrect for the image content (the edit was wrong; that can be a
      detector fault or a fill fault, so it is counted separately).
    * `engine_swap` - a REJECT that only re-routes the fill engine (LaMa ->
      SDXL -> Dekel/IOPaint). Says nothing about the detector.
    * `unlabelled` - no operator adjudication yet.

  DETECT census (needs the cleaning venv: torch + ultralytics + easyocr) -
  re-runs `detect_image` + the SAME `gate_decision` the pipeline uses, on each
  slug's `_cleaninitial`, and records verdict, reason, per-box geometry and the
  raw OCR strings. The initial is used deliberately: it is the image the
  detector actually faced, before any inpaint changed the pixels.

A FALSE POSITIVE is then a slug labelled `needs_none` on which the gate returns
`auto` (it would have inpainted without asking). `qa` is not counted as a false
positive - routing an ambiguous image to a human is the gate working.

Read-only: this probe never writes into a pipeline stage folder. Detect results
are cached in the report JSON so the analysis can be re-run without a GPU.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = r"C:\LegionWallpaper"
STAGES = (
    os.path.join(ROOT, "images", "3.Cleaning Scratch"),
    os.path.join(ROOT, "images", "4.Cleaning Done"),
)
PIPELINE_LOG = os.path.join(ROOT, "PIPELINE_LOG.md")
FIRSTDONE_STAGE = os.path.join(ROOT, "images", "2.First Pass Done")

# Operator REJECT note -> label. Substring match on the lowercased note.
_NEEDS_NONE_NOTES = (
    "no watermark or defect present",
    "did not need cleaning",
)
_WRONG_EDIT_NOTES = (
    "contextually incorrect",
)
_ENGINE_SWAP_NOTES = (
    "swap lama erase",
    "block-sdxl rejected",
    "redo via dekel",
)


def _sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifests(stages=STAGES):
    """Yield (slug, stage_dir, manifest_dict) for every cleaning-stage slug."""
    for stage in stages:
        if not os.path.isdir(stage):
            continue
        for slug in sorted(os.listdir(stage)):
            d = os.path.join(stage, slug)
            mpath = os.path.join(d, "manifest.json")
            if not os.path.isfile(mpath):
                continue
            try:
                with open(mpath, encoding="utf-8") as f:
                    yield slug, d, json.load(f)
            except (OSError, ValueError):
                continue


def classify_note(note) -> str:
    """Map one REJECT note to a label key ('needs_none'/'wrong_edit'/...)."""
    t = str(note or "").lower()
    if any(s in t for s in _NEEDS_NONE_NOTES):
        return "needs_none"
    if any(s in t for s in _WRONG_EDIT_NOTES):
        return "wrong_edit"
    if any(s in t for s in _ENGINE_SWAP_NOTES):
        return "engine_swap"
    return "other"


def label_census(stages=STAGES):
    """Per-slug operator label from manifest transitions + the initial's sha.

    A slug can carry several REJECT notes over its life; `needs_none` wins over
    `wrong_edit` wins over `engine_swap`, because the strongest statement the
    operator made about the DETECTOR is the one that matters here.
    """
    order = {"needs_none": 3, "wrong_edit": 2, "engine_swap": 1, "other": 0}
    rows = []
    for slug, d, man in load_manifests(stages):
        notes, best = [], None
        approved_sha = None
        for t in man.get("transitions") or []:
            op = t.get("op")
            if op == "REJECT":
                note = t.get("note") or ""
                notes.append(note)
                key = classify_note(note)
                if best is None or order[key] > order[best]:
                    best = key
            elif op == "APPROVE_CLEAN":
                approved_sha = t.get("sha256_out") or approved_sha

        initial = os.path.join(d, f"{slug}_cleaninitial.png")
        initial_sha = _sha256_file(initial) if os.path.isfile(initial) else None
        approved_is_initial = bool(
            approved_sha and initial_sha and approved_sha == initial_sha)
        if approved_is_initial:
            best = "needs_none"

        rows.append({
            "slug": slug,
            "dir": d,
            "initial": initial if os.path.isfile(initial) else None,
            "label": best or "unlabelled",
            "approved_is_initial": approved_is_initial,
            "reject_notes": notes,
        })
    return rows


def firstdone_rows(stage=FIRSTDONE_STAGE):
    """Rows for the UNROUTED population: every `_firstdone` in 2.First Pass Done.

    This is the population a RECALL census must sample. The 21-slug cleaning
    queue cannot answer recall: it IS the `auto` output of this detector's own
    2026-07-16 triage of 228 firstdones (LEDGER 27), so scoring the detector on
    it is circular. A false negative can only live where the gate said `clean`
    and nothing was routed - i.e. here.
    """
    rows = []
    if not os.path.isdir(stage):
        return rows
    for slug in sorted(os.listdir(stage)):
        d = os.path.join(stage, slug)
        p = os.path.join(d, f"{slug}_firstdone.png")
        if os.path.isfile(p):
            rows.append({"slug": slug, "dir": d, "initial": p,
                         "label": "unrouted", "approved_is_initial": False,
                         "reject_notes": []})
    return rows


# --------------------------------------------------------------------------
# DETECT census (cleaning venv only)
# --------------------------------------------------------------------------
def load_models_once(langs=("en", "ch_sim")):
    """Load YOLO + EasyOCR ONCE. A 302-image census reloads them otherwise."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import lw_clean_pass as cp
    return cp.load_models(langs)


def _yolo_low(path, models, conf):
    """YOLO boxes at a LOWERED conf floor - what the CONF_AUTO gate never saw.

    detect_yolo runs at conf=0.35 by default, so a faint mark scoring 0.2 never
    reaches the gate at all. Recording the low-conf sweep separates "the
    detector cannot see it" from "the gate threw it away".
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import lw_clean_pass as cp
    import numpy as np
    from PIL import Image
    with Image.open(path) as im:
        arr = np.asarray(im.convert("RGB"))
    with cp.gpu_lock(models["device"]):
        return cp.detect_yolo(arr, models["yolo"], conf=conf)


def detect_census(rows, limit=None, models=None, low_conf=None):
    """Re-run detect + gate on each row's image. Returns row dicts."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import lw_clean_pass as cp
    from PIL import Image

    out = []
    todo = [r for r in rows if r["initial"]]
    if limit:
        todo = todo[:limit]
    for r in todo:
        path = r["initial"]
        with Image.open(path) as im:
            w, h = im.size
        det = cp.detect_image(path, models=models)
        boxes = cp.union_boxes(det["boxes"])
        confs = det.get("confs") or []
        conf_max = max(confs) if confs else 0.0
        ocr_texts = det.get("ocr_texts", [])
        ocr_hit = bool(det.get("ocr_hit")) or any(
            cp.classify_ocr_string(t) for t in ocr_texts)
        area_pct = cp.dilated_union_area_pct(boxes, w, h, cp.DILATE_PX)
        centroid = cp.centroid_of(boxes)
        verdict, reason = cp.gate_decision(
            len(boxes), conf_max, ocr_hit, area_pct, centroid, w, h, ocr_texts)
        out.append({
            "slug": r["slug"],
            "label": r["label"],
            "w": w, "h": h,
            "n_boxes": len(boxes),
            "conf_max": round(conf_max, 4),
            "area_pct": round(area_pct, 4),
            "centroid": [round(c, 1) for c in centroid] if centroid else None,
            "centroid_rel": ([round(centroid[0] / w, 4),
                              round(centroid[1] / h, 4)] if centroid else None),
            "ocr_hit": ocr_hit,
            "is_lol_logo": cp.is_lol_logo(ocr_texts),
            "is_watermark_text": cp.is_watermark_text(ocr_texts),
            "verdict": verdict,
            "reason": reason,
            "boxes": [[round(v, 1) for v in b] for b in boxes],
            "yolo": [{"box": [round(v, 1) for v in d["box"]],
                      "conf": round(d["conf"], 4)} for d in det.get("yolo", [])],
            "ocr": [{"box": [round(v, 1) for v in d["box"]],
                     "text": d["text"], "conf": round(d["conf"], 4)}
                    for d in det.get("ocr", [])],
        })
        if low_conf is not None and models is not None:
            out[-1]["yolo_low"] = [
                {"box": [round(v, 1) for v in d["box"]],
                 "conf": round(d["conf"], 4)}
                for d in _yolo_low(path, models, low_conf)]
        print(f"  {r['slug']}: {verdict}/{reason} "
              f"n={len(boxes)} area={area_pct:.2f}% label={r['label']}",
              flush=True)
    return out


def summarize(det_rows):
    """Cross-tab verdict against the operator label. Returns a summary dict."""
    by_label = {}
    for r in det_rows:
        cell = by_label.setdefault(r["label"], {})
        cell[r["verdict"]] = cell.get(r["verdict"], 0) + 1
    fps = [r for r in det_rows
           if r["label"] == "needs_none" and r["verdict"] == "auto"]
    return {
        "n_slugs": len(det_rows),
        "by_label_verdict": by_label,
        "false_positive_slugs": [r["slug"] for r in fps],
        "false_positives": len(fps),
        "needs_none_total": sum(1 for r in det_rows
                                if r["label"] == "needs_none"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels-only", action="store_true",
                    help="stdlib label census only (no ML, no GPU)")
    ap.add_argument("--corpus", choices=("cleaning", "firstdone"),
                    default="cleaning",
                    help="cleaning = the 21 gated slugs (PRECISION); firstdone "
                         "= every _firstdone in 2.First Pass Done (RECALL)")
    ap.add_argument("--low-conf", type=float, default=None,
                    help="also sweep YOLO at this conf floor (firstdone census)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=None, help="write the full report JSON here")
    args = ap.parse_args(argv)

    if args.corpus == "firstdone":
        rows = firstdone_rows()
        print(f"FIRSTDONE census: {len(rows)} unrouted slugs")
    else:
        rows = label_census()
        counts = {}
        for r in rows:
            counts[r["label"]] = counts.get(r["label"], 0) + 1
        print(f"LABEL census: {len(rows)} cleaning-stage slugs")
        for k in sorted(counts):
            print(f"  {k}: {counts[k]}")
        for r in rows:
            if r["label"] == "needs_none":
                print(f"  needs_none -> {r['slug']} "
                      f"(approved_is_initial={r['approved_is_initial']})")

    report = {"labels": rows}
    if not args.labels_only:
        print("DETECT census (this loads YOLO + EasyOCR):")
        models = load_models_once() if (
            args.low_conf is not None or len(rows) > 40) else None
        det = detect_census(rows, limit=args.limit, models=models,
                            low_conf=args.low_conf)
        report["detect"] = det
        report["summary"] = summarize(det)
        print(json.dumps(report["summary"], indent=2))

    if args.out:
        tmp = args.out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        os.replace(tmp, args.out)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
