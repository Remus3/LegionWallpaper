"""The P5 judge must not report green on the cases that matter.

Regression tests for a defect RC found on review 2026-07-26: winmutex logged
ACQUIRED unconditionally but RELEASED only when it actually held the lock, so
the fail-open path opened a window that never closed. A pairing parser drops
that window silently - making the ONE case where the mutex did not serialize
the one case invisible to condition 4. An unserialized concurrent gemini call
would have passed green.

These tests pin the judge's side of that fix. The emitter's side is pinned by
the ACQUIRED-is-gated assertion in test_loop_concurrency.py.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "lw_p5_probe_under_test", ROOT / "ops" / "loop" / "p5_probe.py")
p5 = importlib.util.module_from_spec(_spec)
sys.modules["lw_p5_probe_under_test"] = p5
_spec.loader.exec_module(p5)

G = "Global\\LWRC_GEMINI"


def _log(*rows: str) -> str:
    return "\n".join(rows) + "\n"


def _cycle(t: str, n: int = 1) -> str:
    return f"2026-07-26T{t} cycle {n}: claude.done sha=abc regress=False"


def _acq(t: str) -> str:
    return f"2026-07-26T{t} winmutex: ACQUIRED {G}"


def _rel(t: str) -> str:
    return f"2026-07-26T{t} winmutex: RELEASED {G}"


def _samples(path: Path, peak: int, both: bool = True) -> Path:
    rows = []
    owners = [{"slot": f"{i}.lock", "repo": ("LW" if i == 0 else "RC") if both else "LW"}
              for i in range(peak)]
    rows.append(json.dumps({"t": 1.0, "n": peak, "owners": owners}))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def _run(tmp_path: Path, lw_rows, rc_rows, peak=2, both=True):
    lw = tmp_path / "lw.log"
    rc = tmp_path / "rc.log"
    lw.write_text(_log(*lw_rows), encoding="utf-8")
    rc.write_text(_log(*rc_rows), encoding="utf-8")
    s = _samples(tmp_path / "s.jsonl", peak, both)
    return p5.judge(lw, rc, s, max_slots=2, deadline=900)


# ---- the shape that should pass --------------------------------------------

def test_clean_disjoint_run_passes(tmp_path: Path):
    rc_code = _run(
        tmp_path,
        [_cycle("20:00:00"), _acq("20:00:01"), _rel("20:00:02"),
         "2026-07-26T20:00:03 STOP written: max_cycles 2 reached"],
        [_cycle("20:00:05"), _acq("20:00:06"), _rel("20:00:07"),
         "2026-07-26T20:00:08 STOP written: max_cycles 2 reached"])
    assert rc_code == 0


# ---- the traps -------------------------------------------------------------

def test_overlapping_gemini_windows_fail(tmp_path: Path):
    assert _run(
        tmp_path,
        [_cycle("20:00:00"), _acq("20:00:01"), _rel("20:00:10")],
        [_cycle("20:00:00"), _acq("20:00:05"), _rel("20:00:12")]) == 1


def test_unserialized_marker_is_a_hard_fail_even_with_no_overlap(tmp_path: Path):
    """The mutex did not serialize that call - the resource was shared with no
    lock at all. Windows looking disjoint is irrelevant."""
    assert _run(
        tmp_path,
        [_cycle("20:00:00"),
         f"2026-07-26T20:00:01 winmutex: UNSERIALIZED {G} - CreateMutexW failed; "
         f"proceeding WITHOUT the lock"],
        [_cycle("20:00:20"), _acq("20:00:21"), _rel("20:00:22")]) == 1


def test_unpaired_acquired_is_a_hard_fail(tmp_path: Path):
    """THE regression. An ACQUIRED with no RELEASED is a window the pairing
    parser drops; without this check the run reports zero windows and green."""
    assert _run(
        tmp_path,
        [_cycle("20:00:00"), _acq("20:00:01")],  # never released
        [_cycle("20:00:20"), _acq("20:00:21"), _rel("20:00:22")]) == 1


def test_dropped_window_would_otherwise_look_clean(tmp_path: Path):
    """Proves the trap is real: the pairing parser genuinely returns nothing for
    an unclosed hold, which is why the count check has to exist."""
    assert p5.gemini_windows([_acq("20:00:01")]) == []
    assert len(p5.gemini_windows([_acq("20:00:01"), _rel("20:00:02")])) == 1


def test_occupancy_above_max_slots_fails(tmp_path: Path):
    assert _run(
        tmp_path,
        [_cycle("20:00:00"), _acq("20:00:01"), _rel("20:00:02")],
        [_cycle("20:00:05"), _acq("20:00:06"), _rel("20:00:07")],
        peak=3) == 1


def test_unexpected_stop_fails(tmp_path: Path):
    assert _run(
        tmp_path,
        [_cycle("20:00:00"), _acq("20:00:01"), _rel("20:00:02"),
         "2026-07-26T20:00:03 STOP written: no progress: same sha 2 cycles"],
        [_cycle("20:00:05"), _acq("20:00:06"), _rel("20:00:07")]) == 1


def test_slot_wait_longer_than_deadline_fails(tmp_path: Path):
    lw = [_cycle("20:00:00"),
          "2026-07-26T20:00:00 slots: all 2 busy - waiting",
          "2026-07-26T20:30:00 slots: acquired 0.lock (run_id=x cycle=1)",
          _acq("20:30:01"), _rel("20:30:02")]
    assert _run(tmp_path, lw, [_cycle("20:00:05"), _acq("20:00:06"),
                               _rel("20:00:07")]) == 1
