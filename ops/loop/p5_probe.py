#!/usr/bin/env python
r"""P5 instrumentation: sample slot occupancy, then judge the four conditions.

P5 is the acceptance test for the whole F1 spec (a live CONCURRENT LW+RC run).
Its conditions are only meaningful if they are MEASURED, so this file does the
measuring rather than leaving it to a post-hoc reading of two logs.

  sample  - poll the shared slot bucket every N seconds and record occupancy.
            Runs for the duration of the concurrent run; writes JSONL.
  judge   - read both controller logs + the occupancy samples and rule on all
            four conditions, printing PASS/FAIL per condition with evidence.

Usage:
  python ops/loop/p5_probe.py sample --out samples.jsonl [--interval 5] [--seconds 3600]
  python ops/loop/p5_probe.py judge --lw <lw controller.log> --rc <rc controller.log>
                                    --samples samples.jsonl --max-slots 2
                                    [--deadline 900]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

SLOT_ROOT = Path(r"C:\ProgramData\lw-loop\slots")
TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")


def sample(out: Path, interval: float, seconds: float, root: Path) -> int:
    end = time.time() + seconds
    with open(out, "w", encoding="utf-8") as fh:
        while time.time() < end:
            try:
                held = sorted(p.name for p in root.glob("*.lock"))
            except OSError:
                held = []
            owners = []
            for name in held:
                try:
                    rec = json.loads((root / name).read_text(encoding="utf-8"))
                    owners.append({"slot": name, "repo": rec.get("repo"),
                                   "run_id": rec.get("run_id"), "cycle": rec.get("cycle")})
                except (OSError, ValueError):
                    owners.append({"slot": name, "repo": "?"})
            fh.write(json.dumps({"t": time.time(), "n": len(held),
                                 "owners": owners}) + "\n")
            fh.flush()
            time.sleep(interval)
    return 0


def _epoch(line: str) -> float | None:
    m = TS.match(line)
    if not m:
        return None
    return time.mktime(time.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S"))


def gemini_windows(log_lines: list[str]) -> list[tuple[float, float]]:
    """ACQUIRED/RELEASED pairs for the gemini mutex, as epoch windows."""
    out, open_at = [], None
    for ln in log_lines:
        if "winmutex: ACQUIRED" in ln and "GEMINI" in ln:
            open_at = _epoch(ln)
        elif "winmutex: RELEASED" in ln and "GEMINI" in ln and open_at is not None:
            end = _epoch(ln)
            if end is not None:
                out.append((open_at, end))
            open_at = None
    return out


def overlaps(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> list:
    hits = []
    for s1, e1 in a:
        for s2, e2 in b:
            lo, hi = max(s1, s2), min(e1, e2)
            if hi > lo:
                hits.append((lo, hi))
    return hits


def max_slot_wait(log_lines: list[str]) -> float:
    """Longest gap between 'all busy - waiting' and the next 'acquired'."""
    worst, waiting_at = 0.0, None
    for ln in log_lines:
        if "slots:" in ln and "busy - waiting" in ln:
            waiting_at = _epoch(ln)
        elif "slots: acquired" in ln and waiting_at is not None:
            got = _epoch(ln)
            if got is not None:
                worst = max(worst, got - waiting_at)
            waiting_at = None
    return worst


def judge(lw: Path, rc: Path, samples: Path, max_slots: int, deadline: float) -> int:
    lwl = lw.read_text(encoding="utf-8", errors="replace").splitlines()
    rcl = rc.read_text(encoding="utf-8", errors="replace").splitlines()
    fails = []

    # 1. both runs reach their last cycle and exit clean (no stop() other than
    #    the benign max_cycles terminator)
    def clean(lines, who):
        stops = [x for x in lines if "STOP written:" in x]
        bad = [s for s in stops if "max_cycles" not in s]
        reached = [x for x in lines if re.search(r"cycle \d+: .*(done|claude\.done)", x)]
        ok = bool(reached) and not bad
        return ok, f"{who}: {len(reached)} completed-cycle lines, unexpected stops={bad}"

    ok1a, d1a = clean(lwl, "LW")
    ok1b, d1b = clean(rcl, "RC")
    print(f"[{'PASS' if ok1a and ok1b else 'FAIL'}] 1. both runs complete, no unexpected stop")
    print(f"        {d1a}\n        {d1b}")
    if not (ok1a and ok1b):
        fails.append(1)

    # 2. no slot wait longer than a cycle deadline
    w_lw, w_rc = max_slot_wait(lwl), max_slot_wait(rcl)
    ok2 = w_lw <= deadline and w_rc <= deadline
    print(f"[{'PASS' if ok2 else 'FAIL'}] 2. no slot wait exceeds cycle_deadline_sec ({deadline}s)")
    print(f"        LW worst wait {w_lw:.0f}s | RC worst wait {w_rc:.0f}s")
    if not ok2:
        fails.append(2)

    # 3. sampled slot occupancy never exceeds max_slots
    peak, n, both = 0, 0, 0
    for ln in samples.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        n += 1
        peak = max(peak, rec.get("n", 0))
        repos = {o.get("repo") for o in rec.get("owners", [])}
        if len([r for r in repos if r]) > 1:
            both += 1
    ok3 = peak <= max_slots
    print(f"[{'PASS' if ok3 else 'FAIL'}] 3. sampled occupancy never exceeds max_slots={max_slots}")
    print(f"        {n} samples, peak={peak}, samples with BOTH repos holding={both}")
    if not ok3:
        fails.append(3)
    if both == 0:
        print("        NOTE: never observed both repos holding at once - the run may not "
              "have actually overlapped, which makes conditions 3 and 4 weak evidence")

    # 4. gemini call windows never overlap across repos
    gw_lw, gw_rc = gemini_windows(lwl), gemini_windows(rcl)
    bad = overlaps(gw_lw, gw_rc)
    ok4 = not bad
    print(f"[{'PASS' if ok4 else 'FAIL'}] 4. gemini windows never overlap across repos")
    print(f"        LW windows={len(gw_lw)} RC windows={len(gw_rc)} overlaps={len(bad)}")
    if not gw_lw or not gw_rc:
        print("        NOTE: one side logged NO gemini windows - condition 4 is vacuous. "
              "A run with fixed_directive skips director AND auditor, so no gemini call "
              "happens; use cycle_command (auditor kept) or a real director run.")
    if not ok4:
        fails.append(4)

    print(f"\nP5 verdict: {'PASS' if not fails else 'FAIL on conditions ' + str(fails)}")
    return 0 if not fails else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--out", required=True)
    s.add_argument("--interval", type=float, default=5.0)
    s.add_argument("--seconds", type=float, default=3600.0)
    s.add_argument("--root", default=str(SLOT_ROOT))
    j = sub.add_parser("judge")
    j.add_argument("--lw", required=True)
    j.add_argument("--rc", required=True)
    j.add_argument("--samples", required=True)
    j.add_argument("--max-slots", type=int, default=2)
    j.add_argument("--deadline", type=float, default=900.0)
    a = ap.parse_args()
    if a.cmd == "sample":
        return sample(Path(a.out), a.interval, a.seconds, Path(a.root))
    return judge(Path(a.lw), Path(a.rc), Path(a.samples), a.max_slots, a.deadline)


if __name__ == "__main__":
    sys.exit(main())
