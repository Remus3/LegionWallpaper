"""Gate-driven disposition of the cleaning-scratch corpus (operator call 2026-08-22).

Reads a triage JSONL produced by `lw_clean_pass --all-scratch --dry-run
--triage-out`, then per verdict:

  clean -> register the initial as a clean-scan working, submit, approve
  auto  -> live inpaint via lw_clean_pass.process_slug, then submit + approve
  qa    -> live pass ONLY (writes the mask + detect side-files); the slug STAYS
           in 3.Cleaning Scratch for the manual IOPaint lane. No pipeline
           mutation, ever.

Nothing here re-decides a verdict: the gate already did. Every pipeline
transition goes through `lw_pipeline` so the ledger + rails stay authoritative
(ADR-008 approval rail, ADR-009 one-engine rule); a refusal is RECORDED and the
slug is skipped, never forced.

Run under the lw-clean venv (process_slug needs cv2 + torch):
  C:\\Tools\\lw-clean\\venv\\Scripts\\python.exe tools/lw_clean_dispose.py \
      --triage <path> --out <results.jsonl> [--only clean,auto,qa] [--limit N]
      [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lw_clean_pass as lcp  # noqa: E402

# Resolved HERE rather than reused from lw_clean_pass: the console-flash guard
# (tests/test_no_console_flash.py) follows creationflags to a value within the
# spawning module, and a cross-module attribute is exactly the shape it cannot
# prove. Same value, provable in place.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
ACTOR = "tool:auto-approve"


def run_cmd(argv, dry_run=False):
    """Run one pipeline argv with no console window. Returns a result dict."""
    if dry_run:
        return {"argv": argv, "rc": 0, "out": "", "err": "", "skipped": True}
    proc = subprocess.run(argv, capture_output=True, text=True,
                          creationflags=NO_WINDOW)
    return {"argv": argv, "rc": proc.returncode,
            "out": (proc.stdout or "").strip()[-400:],
            "err": (proc.stderr or "").strip()[-400:]}


def approve_cmd(slug):
    return [lcp.SYS_PY, lcp.PIPELINE, "approve", slug, "--actor", ACTOR]


def drive(slug, verdict, image, dry_run=False):
    """Take one slug from its verdict to its resting place. Never raises."""
    rec = {"slug": slug, "verdict": verdict, "steps": [], "status": "pending"}
    if verdict == "qa":
        if not dry_run:
            try:
                res = lcp.process_slug(slug, image=image, dry_run=False)
                rec["pass_status"] = res.get("status")
                rec["reason"] = res.get("reason")
            except Exception as exc:  # noqa: BLE001 - one bad slug must not halt
                rec["status"] = "error"
                rec["error"] = f"{type(exc).__name__}: {exc}"
                return rec
        rec["status"] = "queued-qa"
        return rec

    if verdict == "clean":
        cmds = lcp.build_cleanscan_cmds(slug, image)
    else:  # auto
        if dry_run:
            rec["status"] = "would-inpaint"
            return rec
        try:
            res = lcp.process_slug(slug, image=image, dry_run=False)
        except Exception as exc:  # noqa: BLE001
            rec["status"] = "error"
            rec["error"] = f"{type(exc).__name__}: {exc}"
            return rec
        rec["pass_status"] = res.get("status")
        cmds = res.get("commands")
        if not cmds:
            # gate-fail or discard: the harness sent it to the QA queue.
            rec["status"] = "queued-qa"
            rec["reason"] = res.get("reason") or "inpaint gate-fail"
            return rec

    for argv in list(cmds) + [approve_cmd(slug)]:
        step = run_cmd(argv, dry_run=dry_run)
        rec["steps"].append(step)
        if step["rc"] != 0:
            rec["status"] = "refused" if step["rc"] == 3 else "failed"
            return rec
    rec["status"] = "done" if not dry_run else "would-approve"
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lw_clean_dispose")
    ap.add_argument("--triage", required=True, help="triage JSONL from --dry-run")
    ap.add_argument("--out", required=True, help="results JSONL")
    ap.add_argument("--only", default="clean,auto,qa",
                    help="comma list of verdicts to act on")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true",
                    help="plan only: no inpaint, no pipeline transition")
    args = ap.parse_args(argv)

    wanted = {v.strip() for v in args.only.split(",") if v.strip()}
    rows = []
    with open(args.triage, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    rows = [r for r in rows if r.get("verdict") in wanted]
    if args.limit:
        rows = rows[:args.limit]

    counts = {}
    with open(args.out, "w", encoding="utf-8") as out:
        for i, row in enumerate(rows, 1):
            rec = drive(row["slug"], row["verdict"], row.get("image"),
                        dry_run=args.dry_run)
            out.write(json.dumps(rec) + "\n")
            out.flush()
            counts[rec["status"]] = counts.get(rec["status"], 0) + 1
            print(f"[{i}/{len(rows)}] {row['slug']:<52} "
                  f"{row['verdict']:<5} -> {rec['status']}", flush=True)

    print("LW DISPOSE " + " | ".join(f"{k}={v}" for k, v in sorted(counts.items())),
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
