"""Batch-run one manual-QA cleaning lane over a list of slugs.

Replaces the ad-hoc shell loop that drove `lw_clean_iopaint.py` per slug. Three
modes, matching the gate reasons that put a slug in the QA queue:

  overlay - centre-overlay lane (algebraic pre-pass + LaMa residual)
  faint   - gate-v4 faint-mark lane (refuses to LaMa a mask over 25% of the ROI)
  region  - derive the ROI from the detector's OWN boxes in the triage row and
            pass it as --region; for marks the border rules cannot own
            (`not_border` and friends), where there is a real box but no lane.

It shells out to the worker rather than importing it, so the worker stays the
single place that produces pixels, and it NEVER mutates pipeline state: the
candidates land in the runtime dir and wait for the operator's eye.

Slug lists are read with universal newlines - a CRLF list silently produced a
run of 44 "no clean input image" errors before this existed.

  python tools/lw_clean_lane.py --slugs lane.txt --mode overlay
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

VENV_PY = r"C:\Tools\lw-clean\venv\Scripts\python.exe"
WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "lw_clean_iopaint.py")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
REGION_PAD = 24


def read_slugs(path):
    """One slug per line, CR-stripped, blanks dropped."""
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


def load_triage(path):
    """slug -> triage row, from the JSONL the dry-run gate writes."""
    rows = {}
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                r = json.loads(ln)
                rows[r["slug"]] = r
    return rows


def region_from_boxes(boxes, width, height, pad=REGION_PAD):
    """Union envelope of the detector boxes, padded and clamped to the frame.

    Returns None when there is no box - a region lane with no region must SKIP
    the slug, never fall back to a whole-frame mask.
    """
    if not boxes:
        return None
    xs0 = min(b[0] for b in boxes)
    ys0 = min(b[1] for b in boxes)
    xs1 = max(b[2] for b in boxes)
    ys1 = max(b[3] for b in boxes)
    x0 = max(0, int(xs0) - pad)
    y0 = max(0, int(ys0) - pad)
    x1 = min(int(width), int(xs1) + pad + 1)
    y1 = min(int(height), int(ys1) + pad + 1)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def build_argv(slug, mode, region=None, venv_py=VENV_PY, worker=WORKER):
    """argv for one worker invocation."""
    argv = [venv_py, worker, slug]
    if mode == "overlay":
        argv.append("--overlay")
    elif mode == "faint":
        argv.append("--faint")
    elif mode == "region":
        if region is None:
            raise ValueError(f"{slug}: region mode with no region")
        argv += ["--region", ",".join(str(v) for v in region)]
    else:
        raise ValueError(f"unknown mode {mode}")
    return argv


def _frame_size(row):
    """Frame size for a triage row, read from the image it names."""
    from PIL import Image
    with Image.open(row["image"]) as im:
        return im.size


def run_lane(slugs, mode, triage=None, dry_run=False, out=None):
    """Drive every slug through the worker. Returns the per-slug result list."""
    results = []
    for i, slug in enumerate(slugs, 1):
        rec = {"slug": slug, "mode": mode}
        region = None
        if mode == "region":
            row = (triage or {}).get(slug)
            if row is None:
                rec.update(status="skipped", reason="no triage row")
                results.append(rec)
                print(f"[{i}/{len(slugs)}] {slug} -> skipped (no triage row)", flush=True)
                continue
            w, h = _frame_size(row)
            region = region_from_boxes(row.get("boxes") or [], w, h)
            if region is None:
                rec.update(status="skipped", reason="no detector box to bound the ROI")
                results.append(rec)
                print(f"[{i}/{len(slugs)}] {slug} -> skipped (no box)", flush=True)
                continue
            rec["region"] = list(region)
        argv = build_argv(slug, mode, region)
        rec["argv"] = argv
        if dry_run:
            rec["status"] = "planned"
        else:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  creationflags=NO_WINDOW)
            rec["rc"] = proc.returncode
            rec["status"] = _worker_status(proc.stdout) or (
                "ok" if proc.returncode == 0 else "failed")
            rec["tail"] = (proc.stdout or proc.stderr or "").strip()[-300:]
        results.append(rec)
        print(f"[{i}/{len(slugs)}] {slug} -> {rec['status']}", flush=True)

    if out:
        tmp = out + ".part"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            for r in results:
                f.write(json.dumps(r) + "\n")
        os.replace(tmp, out)
    return results


def _worker_status(stdout):
    """Lift the status from the LAST JSON object the worker printed.

    Some lanes print a progress blob before the final one, and parsing from the
    first brace to the end then fails outright - which silently degraded every
    real status to a bare "ok" in the 2026-08-22 lane run.
    """
    if not stdout:
        return None
    dec = json.JSONDecoder()
    txt = stdout.strip()
    status, i = None, 0
    while True:
        start = txt.find("{", i)
        if start < 0:
            return status
        try:
            obj, end = dec.raw_decode(txt, start)
        except ValueError:
            i = start + 1
            continue
        if isinstance(obj, dict) and "status" in obj:
            status = obj["status"]
        i = end


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lw_clean_lane")
    ap.add_argument("--slugs", required=True)
    ap.add_argument("--mode", required=True, choices=["overlay", "faint", "region"])
    ap.add_argument("--triage", help="triage JSONL (required for --mode region)")
    ap.add_argument("--out", help="per-slug results JSONL")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if args.mode == "region" and not args.triage:
        ap.error("--mode region needs --triage")
    slugs = read_slugs(args.slugs)
    triage = load_triage(args.triage) if args.triage else None
    results = run_lane(slugs, args.mode, triage, args.dry_run, args.out)
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("LW LANE " + " | ".join(f"{k}={v}" for k, v in sorted(counts.items())),
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
