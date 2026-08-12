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

    import lw_clean_overlay as ov
    tpl = ov.load_template()

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
        # gate v3: the centre-overlay FLAG. 0.0 when no template is built, which
        # reproduces the v2 verdicts exactly.
        ov_score = ov.overlay_score(ov.load_image(path), tpl) if tpl else 0.0
        verdict, reason = cp.gate_decision(
            len(boxes), conf_max, ocr_hit, area_pct, centroid, w, h, ocr_texts,
            overlay_score=ov_score)
        out.append({
            "slug": r["slug"],
            "label": r["label"],
            "overlay_score": round(ov_score, 4),
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


def build_overlay_template(slugs, out_path=None, stages=None, wide=False):
    """Median-stack the named slugs' images into a centre-overlay template.

    The slugs must be images CONFIRMED by eye to carry the DeviantArt centre
    overlay - the estimator has no way to tell a marked frame from a clean one,
    and a clean frame in the stack only blurs the template. The verified list
    lives in `docs/CLEAN_OVERLAY_DETECTOR_2026-08-11.md`; re-run this whenever
    it grows.

    The template is a derivative of a third party's watermark, so it is written
    under `ops/runtime/` (gitignored) and never tracked in this public repo.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import lw_clean_overlay as ov

    known = {r["slug"]: r for r in label_census()}
    known.update({r["slug"]: r for r in firstdone_rows()})
    imgs, used = [], []
    for s in slugs:
        row = known.get(s)
        if row is None:
            hits = [k for k in known if k.startswith(s)]
            row = known[hits[0]] if hits else None
        if row is None or not row.get("initial"):
            print(f"  SKIP (no image on disk): {s}")
            continue
        imgs.append(ov.load_image(row["initial"]))
        used.append(row["slug"])
    if not imgs:
        raise SystemExit("no images resolved - nothing to stack")
    band = ov.REMOVAL_BAND if wide else ov.BAND
    tpl = ov.estimate_template(imgs, band=band)
    path = ov.save_template(
        out_path or (ov.WIDE_TEMPLATE_PATH if wide else ov.TEMPLATE_PATH), tpl)
    print(f"band={band}")
    print(f"template from {len(used)} images -> {path}")
    for s in used:
        print(f"  {s}")
    return path


def _resolve_slug(name, known):
    row = known.get(name)
    if row is None:
        hits = [k for k in known if k.startswith(name)]
        row = known[hits[0]] if hits else None
    return row


def build_overlay_matte(slugs, out_path=None, wide=False):
    """Estimate {alpha, W} for the centre overlay from CONFIRMED-marked slugs.

    Same input list as the template build - these must be frames verified by eye
    to carry the overlay. Writes under `ops/runtime/` (gitignored): the matte is
    a derivative of a third party's watermark, exactly like the template.
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import lw_clean_overlay as ov

    known = {r["slug"]: r for r in label_census()}
    known.update({r["slug"]: r for r in firstdone_rows()})
    tpl = ov.load_template(ov.WIDE_TEMPLATE_PATH if wide else ov.TEMPLATE_PATH)
    if tpl is None:
        raise SystemExit("no template - run --build-overlay-template first")
    imgs, used = [], []
    for s in slugs:
        row = _resolve_slug(s, known)
        if row is None or not row.get("initial"):
            print(f"  SKIP (no image on disk): {s}")
            continue
        imgs.append(ov.load_image(row["initial"]))
        used.append(row["slug"])
    if not imgs:
        raise SystemExit("no images resolved - nothing to solve")
    matte = ov.estimate_matte(imgs, tpl)
    # The FLAT VEIL is a second, independent measurement over the same frames -
    # the high-pass template cannot see a region with no high-pass, so the logo's
    # interior needs the whitening estimator plus its boundary-step calibration.
    veil = ov.estimate_veil(imgs, tpl)
    matte["veil"] = veil
    if float(veil.get("alpha", 0.0)):
        print(f"  veil alpha={veil['alpha']:.3f} (raw {veil['raw']:.3f} x gain "
              f"{veil['gain']}), support {int(veil['support'].sum())} px, "
              f"residual step {veil['step']:.2f} levels")
    else:
        print("  veil: none found (no solid flat region above threshold)")
    path = ov.save_matte(
        out_path or (ov.WIDE_MATTE_PATH if wide else ov.MATTE_PATH), matte)
    a = matte["alpha"]
    print(f"matte from {len(used)} images -> {path}")
    print(f"  gain={matte['gain']} mean post-removal score={matte['score']:.3f}")
    print(f"  alpha>0 on {int((a > 0).sum())} px ({100.0 * (a > 0).mean():.3f}%"
          f" of the band), max={a.max():.3f}")
    return path


def remove_overlay_for(slugs, out_dir=None):
    """Write a de-watermarked CANDIDATE per slug, and report before/after.

    Produces pixels into the runtime dir and PRINTS the lw_pipeline commands -
    it never mutates pipeline state, matching `lw_clean_pass`'s single-writer
    discipline. The candidate is a QA proposal: the overlay is reduced, not
    provably erased (see docs/CLEAN_OVERLAY_DETECTOR_2026-08-11.md).
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import lw_clean_overlay as ov
    import lw_clean_pass as cp

    tpl = ov.load_template()
    matte = ov.load_matte()
    if tpl is None or matte is None:
        raise SystemExit("need both a template and a matte - build them first")
    known = {r["slug"]: r for r in label_census()}
    known.update({r["slug"]: r for r in firstdone_rows()})
    rows = []
    for s in slugs:
        row = _resolve_slug(s, known)
        if row is None or not row.get("initial"):
            print(f"  SKIP (no image on disk): {s}")
            continue
        slug = row["slug"]
        img = ov.load_image(row["initial"])
        before, dy, dx = ov.best_shift(img, tpl)
        cleaned, changed = ov.remove_overlay(img, matte, shift=(dy, dx))
        after = ov.overlay_score(cleaned.astype(float), tpl)
        target = out_dir or os.path.join(cp.RUNTIME_CLEAN, slug)
        os.makedirs(target, exist_ok=True)
        png = os.path.join(target, f"{slug}_overlay_cand.png")
        cp.atomic_write_png(png, cleaned)
        cp.atomic_write_json(
            os.path.join(target, f"{slug}_overlay.json"),
            {"slug": slug, "score_before": round(before, 4),
             "score_after": round(after, 4), "shift": [dy, dx],
             "changed_px": int(changed.sum()), "gain": matte.get("gain"),
             "flag_threshold": cp.OVERLAY_SCORE_MIN, "candidate": png})
        still = "STILL FLAGGED" if after >= cp.OVERLAY_SCORE_MIN else "under flag"
        print(f"  {slug}: {before:.3f} -> {after:.3f} ({still}) -> {png}")
        # Built here rather than via build_save_working_cmd, which hard-codes
        # --tool lama: the provenance of these pixels is the matting solve, and
        # a manifest that says "lama" would be a lie in the permanent record.
        save = [cp.SYS_PY, cp.PIPELINE, "save-working", slug, "--from", png,
                "--tool", "overlay-dekel", "--params",
                json.dumps({"gain": matte.get("gain"),
                            "score_before": round(before, 4),
                            "score_after": round(after, 4)})]
        cp._print_cmds([save, cp.build_submit_cmd(slug)])
        rows.append((slug, before, after))
    return rows


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
    ap.add_argument("--build-overlay-template", nargs="+", metavar="SLUG",
                    default=None,
                    help="median-stack these CONFIRMED-marked slugs into the "
                         "centre-overlay template and exit")
    ap.add_argument("--build-overlay-matte", nargs="+", metavar="SLUG",
                    default=None,
                    help="solve {alpha, W} for the overlay from these "
                         "CONFIRMED-marked slugs and exit")
    ap.add_argument("--wide", action="store_true",
                    help="build the REMOVAL pair on lw_clean_overlay.REMOVAL_BAND "
                         "(the wider band that keeps the logo's clipped top) and "
                         "cache it under the *_wide paths")
    ap.add_argument("--remove-overlay", nargs="+", metavar="SLUG", default=None,
                    help="write a de-watermarked CANDIDATE per slug into the "
                         "runtime dir and print the pipeline commands")
    args = ap.parse_args(argv)

    if args.build_overlay_template:
        build_overlay_template(args.build_overlay_template, out_path=args.out,
                               wide=args.wide)
        return 0
    if args.build_overlay_matte:
        build_overlay_matte(args.build_overlay_matte, out_path=args.out,
                            wide=args.wide)
        return 0
    if args.remove_overlay:
        remove_overlay_for(args.remove_overlay)
        return 0

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
