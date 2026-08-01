"""Three-way concurrency, measured with REAL PROCESSES.

Why this file exists. `WAKEUP`/hand-off carried "three-way concurrency of any
kind" and "a contended acquire reaping a stale lock in a live run" as STILL
UNMEASURED, while N=3 was already live in `ops/loop/config.json`. The existing
coverage in `tests/test_loop_concurrency.py` drives `slots.hold` with THREADS -
eight of them against two slots - which proves the bucket arithmetic but cannot
prove the two things N=3 actually rests on:

  1. `try_acquire` uses `O_CREAT|O_EXCL`. Threads in one interpreter share a
     process and can interleave inside the GIL in ways separate processes do
     not; only real processes exercise the filesystem exclusivity that the
     cross-repo protocol is built on.
  2. `reap` decides on `pid_alive`. Every thread reports the SAME live pid, so
     a thread test can never exercise a dead-holder reap under live contention -
     the exact case that must not deadlock the other two repos.

What this measures, stated honestly: the SHARED PRIMITIVES under genuine
three-way contention from three separate OS processes. It does NOT run three
repositories' real loops - LW cannot drive Riot Commander or Red Moon, and
nothing here reads or writes a sibling tree. Every test injects its own slots
root under tmp_path, so the machine-wide bucket at
`C:\\ProgramData\\lw-loop\\slots` is never touched.

The GPU serialization test deliberately uses a TEST-ONLY mutex name rather than
`winmutex.GPU_MUTEX`. Taking the real `Global\\LW_GPU` here would either block on
a live sibling run or starve one, which is a side effect a test has no business
having.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLOTS = ROOT / "ops" / "loop" / "slots.py"
WINMUTEX = ROOT / "ops" / "loop" / "winmutex.py"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Long enough that three real process spawns overlap inside it, short enough
# that the suite does not crawl. Measured spawn cost on this box is ~0.2s.
HOLD_S = 1.5


SLOT_WORKER = r"""
import importlib.util, json, os, sys, time
spec = importlib.util.spec_from_file_location("lw_slots", sys.argv[1])
slots = importlib.util.module_from_spec(spec); spec.loader.exec_module(slots)
root, max_slots, tag, hold_s, out = sys.argv[2], int(sys.argv[3]), sys.argv[4], \
    float(sys.argv[5]), sys.argv[6]
rec = {"tag": tag, "pid": os.getpid()}
try:
    with slots.hold(max_slots, repo=tag, root=root, timeout=60.0,
                    backoff=0.05, jitter=0.05) as slot:
        rec["slot"] = os.path.basename(str(slot))
        rec["enter"] = time.time()
        time.sleep(hold_s)
        rec["exit"] = time.time()
except Exception as exc:
    rec["error"] = "%s: %s" % (type(exc).__name__, exc)
open(out, "w", encoding="ascii").write(json.dumps(rec))
"""

MUTEX_WORKER = r"""
import importlib.util, json, os, sys, time
spec = importlib.util.spec_from_file_location("lw_wm", sys.argv[1])
wm = importlib.util.module_from_spec(spec); spec.loader.exec_module(wm)
name, hold_s, out = sys.argv[2], float(sys.argv[3]), sys.argv[4]
rec = {"pid": os.getpid()}
try:
    with wm.hold(name, timeout=60.0):
        rec["enter"] = time.time()
        time.sleep(hold_s)
        rec["exit"] = time.time()
except Exception as exc:
    rec["error"] = "%s: %s" % (type(exc).__name__, exc)
open(out, "w", encoding="ascii").write(json.dumps(rec))
"""


def _spawn(tmp_path, script_src, args, n, name):
    """Launch n workers as REAL processes, as simultaneously as we can, join all."""
    script = tmp_path / f"{name}_worker.py"
    script.write_text(script_src, encoding="ascii")
    outs, procs = [], []
    for i in range(n):
        out = tmp_path / f"{name}_{i}.json"
        outs.append(out)
        procs.append(subprocess.Popen(
            [sys.executable, str(script), *args(i), str(out)],
            creationflags=NO_WINDOW, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True))
    for p in procs:
        p.wait(timeout=180)
    recs = []
    for out in outs:
        assert out.exists(), "a worker produced no record at all"
        recs.append(json.loads(out.read_text(encoding="ascii")))
    return recs


def _max_overlap(recs):
    """Peak simultaneous holders, by sweep line over the measured intervals."""
    events = []
    for r in recs:
        events.append((r["enter"], 1))
        events.append((r["exit"], -1))
    events.sort(key=lambda e: (e[0], -e[1]))  # an enter at t ties as concurrent
    cur = peak = 0
    for _, delta in events:
        cur += delta
        peak = max(peak, cur)
    return peak


def _no_errors(recs):
    bad = [r for r in recs if "error" in r]
    assert not bad, f"workers failed: {bad}"


# ---------------------------------------------------------------------------
# slots, three real processes
# ---------------------------------------------------------------------------
def test_three_processes_actually_run_concurrently_at_n3(tmp_path):
    """The measurement the hand-off asked for: N=3 really is three at once.

    Asserting <= 3 alone would pass on a bucket that serialized everything, so
    the load-bearing assertion is the peak EQUALS 3 - genuine overlap observed.
    """
    root = tmp_path / "slots"
    recs = _spawn(tmp_path, SLOT_WORKER,
                  lambda i: [str(SLOTS), str(root), "3", f"repo{i}", str(HOLD_S)],
                  3, "slot3")
    _no_errors(recs)
    assert _max_overlap(recs) == 3
    assert len({r["slot"] for r in recs}) == 3, "two processes took the same slot"
    assert len({r["pid"] for r in recs}) == 3, "workers were not separate processes"


def test_a_fourth_process_is_held_out_at_n3(tmp_path):
    """The governor's whole job. Four contenders, never more than three inside."""
    root = tmp_path / "slots"
    recs = _spawn(tmp_path, SLOT_WORKER,
                  lambda i: [str(SLOTS), str(root), "3", f"repo{i}", str(HOLD_S)],
                  4, "slot4")
    _no_errors(recs)
    assert _max_overlap(recs) == 3, "the cap did not hold across processes"
    span = max(r["exit"] for r in recs) - min(r["enter"] for r in recs)
    assert span > HOLD_S, "the fourth never waited - it was not actually contended"


def test_a_stale_lock_is_reaped_under_live_contention(tmp_path):
    """Item two of the unmeasured list, and the fail-open promise in slots.py.

    A dead holder's lock is planted in every slot before any contender starts,
    so the ONLY way through is a reap decided by pid_alive during a contended
    acquire. If reap were respectful rather than fail-open this deadlocks.
    """
    root = tmp_path / "slots"
    root.mkdir(parents=True)
    dead_pid = 999_999_999  # never alive; slots.pid_alive is the decider
    for i in range(3):
        (root / f"{i}.lock").write_text(
            json.dumps({"pid": dead_pid, "repo": "ghost", "run_id": "x",
                        "cycle": 0, "ts": time.time()}), encoding="ascii")
    recs = _spawn(tmp_path, SLOT_WORKER,
                  lambda i: [str(SLOTS), str(root), "3", f"repo{i}", "0.3"],
                  3, "reap")
    _no_errors(recs)
    assert _max_overlap(recs) == 3, "a reaped bucket did not readmit three"


# ---------------------------------------------------------------------------
# the GPU mutex, three real processes - the OPPOSITE guarantee
# ---------------------------------------------------------------------------
def test_the_gpu_mutex_serializes_three_processes_to_one(tmp_path):
    """Slots admit three; the GPU mutex must admit exactly one.

    Test-only mutex name on purpose - taking the real Global\\LW_GPU would block
    on, or starve, a live sibling run.
    """
    name = "Global\\LW_TEST_3WAY_" + str(int(time.time() * 1000) % 10_000_000)
    recs = _spawn(tmp_path, MUTEX_WORKER,
                  lambda i: [str(WINMUTEX), name, "0.4"], 3, "gpu")
    _no_errors(recs)
    assert _max_overlap(recs) == 1, "two processes were inside the GPU mutex at once"
    total = sum(r["exit"] - r["enter"] for r in recs)
    span = max(r["exit"] for r in recs) - min(r["enter"] for r in recs)
    assert span >= total * 0.9, "holds overlapped - the mutex did not serialize"
