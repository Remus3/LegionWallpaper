"""F1 P3 concurrency governor: slots, named mutexes, single-controller lock.

These are the tests that have to be right BEFORE any live concurrent LW+RC run,
because the failure they guard against is not a crash - it is two loops quietly
double-booking a shared resource and blaming the result on something else.

slots.py and winmutex.py are byte-identical across both repos by contract, so
nothing here may assume LW paths; every test injects its own root.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"lw_loop_{name}_under_test", ROOT / "ops" / "loop" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


slots = _load("slots")
winmutex = _load("winmutex")


# ---- the core invariant: never more than max_slots holders -----------------

def test_eight_threads_never_exceed_two_concurrent_holders(tmp_path: Path):
    """THE acceptance invariant. 8 contenders, 2 slots, sampled continuously."""
    live = 0
    peak = 0
    lock = threading.Lock()
    errors: list = []

    def worker(i: int):
        nonlocal live, peak
        try:
            with slots.hold(2, root=tmp_path, run_id=f"r{i}", cycle=i,
                            backoff=0.02, jitter=0.02, timeout=30):
                with lock:
                    live += 1
                    peak = max(peak, live)
                time.sleep(0.05)
                with lock:
                    live -= 1
        except Exception as e:  # noqa: BLE001 - surface, do not swallow
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert not errors, errors
    assert peak <= 2, f"slot governor breached: {peak} concurrent holders"
    assert peak == 2, "with 8 contenders both slots should have been used"


def test_all_slots_are_released_after_use(tmp_path: Path):
    with slots.hold(2, root=tmp_path, backoff=0.01, jitter=0.01):
        assert len(list(tmp_path.glob("*.lock"))) == 1
    assert list(tmp_path.glob("*.lock")) == [], "a slot leaked"


def test_slot_is_released_even_when_the_body_raises(tmp_path: Path):
    with pytest.raises(ValueError):
        with slots.hold(1, root=tmp_path, backoff=0.01, jitter=0.01):
            raise ValueError("boom")
    assert list(tmp_path.glob("*.lock")) == [], "an exception leaked a slot"


def test_timeout_raises_rather_than_proceeding_unslotted(tmp_path: Path):
    """A caller that cannot get a slot must fail, never run anyway."""
    with slots.hold(1, root=tmp_path, backoff=0.01, jitter=0.01):
        with pytest.raises(slots.SlotTimeout):
            with slots.hold(1, root=tmp_path, backoff=0.01, jitter=0.01, timeout=0.2):
                pytest.fail("acquired a slot that was already held")


# ---- reaping: a crashed holder must not deadlock the other repo ------------

def test_lock_held_by_a_dead_pid_is_reaped(tmp_path: Path):
    """FAIL-OPEN by design: a stale lock is reclaimed, never respected forever."""
    dead = tmp_path / "0.lock"
    dead.write_text(json.dumps({"pid": 999999999, "repo": "ghost",
                                "run_id": "x", "cycle": 1, "ts": time.time()}),
                    encoding="utf-8")
    assert slots.is_stale(dead, slots.DEFAULT_STALE_AFTER) is True
    with slots.hold(1, root=tmp_path, backoff=0.01, jitter=0.01, timeout=5) as s:
        assert s.name == "0.lock", "the dead holder's slot should be reused"


def test_lock_older_than_stale_after_is_reaped(tmp_path: Path):
    old = tmp_path / "0.lock"
    old.write_text(json.dumps({"pid": os.getpid(), "ts": time.time() - 10_000}),
                   encoding="utf-8")
    assert slots.is_stale(old, stale_after=100.0) is True


def test_live_holder_is_not_reaped(tmp_path: Path):
    """The reaper must not steal a slot from a running process."""
    mine = tmp_path / "0.lock"
    mine.write_text(json.dumps({"pid": os.getpid(), "ts": time.time()}),
                    encoding="utf-8")
    assert slots.is_stale(mine, slots.DEFAULT_STALE_AFTER) is False
    assert slots.reap(tmp_path, 1, slots.DEFAULT_STALE_AFTER) == 0


def test_corrupt_lock_cannot_wedge_the_bucket_forever(tmp_path: Path):
    bad = tmp_path / "0.lock"
    bad.write_text("{ not json", encoding="utf-8")
    os.utime(bad, (time.time() - 10_000, time.time() - 10_000))
    assert slots.is_stale(bad, stale_after=100.0) is True


def test_pid_alive_is_true_for_this_process():
    assert slots.pid_alive(os.getpid()) is True


def test_pid_alive_is_false_for_an_impossible_pid():
    assert slots.pid_alive(999999999) is False
    assert slots.pid_alive(0) is False


# ---- the payload the other repo reads --------------------------------------

def test_lock_payload_identifies_the_holder(tmp_path: Path):
    """Cross-repo debugging depends on this: which repo, which run, which cycle."""
    with slots.hold(1, root=tmp_path, repo="LW", run_id="abc123", cycle=7,
                    backoff=0.01, jitter=0.01) as s:
        rec = json.loads(s.read_text(encoding="utf-8"))
    assert rec["repo"] == "LW"
    assert rec["run_id"] == "abc123"
    assert rec["cycle"] == 7
    assert rec["pid"] == os.getpid()


# ---- one controller per repo ------------------------------------------------

def test_second_controller_in_the_same_repo_exits_nonzero(tmp_path: Path):
    """Concurrency ACROSS repos is the goal; within one repo it is corruption.

    The control_dir handshake files are not namespaced, so two controllers in
    one repo would consume each other's gemini.ready and claude.done.
    """
    import subprocess
    ctl = tmp_path / "control"
    ctl.mkdir()
    cfg = json.loads((ROOT / "ops" / "loop" / "config.dry.json").read_text(encoding="utf-8"))
    cfg.update({"control_dir": str(ctl), "max_cycles": 1, "cycle_deadline_sec": 5,
                "poll_sec": 1, "fixed_directive": "noop", "session_jsonl": ""})
    cfgp = tmp_path / "cfg.json"
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")

    # A lock held by THIS process: a live pid that is not the controller's.
    (ctl / "RUNNING.lock").write_text(
        json.dumps({"pid": os.getpid(), "run_id": "held", "ts": time.time()}),
        encoding="utf-8")

    r = subprocess.run([sys.executable, str(ROOT / "ops" / "loop" / "loop_controller.py"),
                        str(cfgp)], capture_output=True, text=True, timeout=120)
    assert r.returncode != 0, "a second controller must refuse to start"
    assert "already running" in (r.stderr + r.stdout)


def test_controller_reclaims_a_lock_whose_pid_was_recycled(tmp_path: Path):
    """A live pid does not prove the ORIGINAL holder is still alive.

    Measured on the real tree 2026-08-01: control/RUNNING.lock named pid 8532
    from a run that ended 2026-07-27, and pid 8532 had since been reissued to a
    conhost.exe started that morning. Bare pid liveness said "alive", so a fresh
    launch refused to start and the loop was wedged for five days behind a lock
    whose owner had exited cleanly (STOP was present the whole time).

    The corroboration is lock AGE: the holder claims a repo for at most a cycle
    deadline, so a lock far older than the stale window cannot belong to a live
    run no matter what the pid table says.
    """
    import subprocess
    ctl = tmp_path / "control"
    ctl.mkdir()
    cfg = json.loads((ROOT / "ops" / "loop" / "config.dry.json").read_text(encoding="utf-8"))
    cfg.update({"control_dir": str(ctl), "max_cycles": 1, "cycle_deadline_sec": 3,
                "poll_sec": 1, "fixed_directive": "noop", "session_jsonl": ""})
    cfgp = tmp_path / "cfg.json"
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")

    # os.getpid() is unambiguously alive - the point is that aliveness alone
    # must not be enough when the lock predates any plausible run.
    stale = _load("slots").DEFAULT_STALE_AFTER
    (ctl / "RUNNING.lock").write_text(
        json.dumps({"pid": os.getpid(), "run_id": "recycled",
                    "ts": time.time() - (stale * 4)}),
        encoding="utf-8")

    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "ops" / "loop" / "loop_controller.py"), str(cfgp)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        claimed = False
        for _ in range(150):
            if (ctl / "run_id.txt").is_file():
                claimed = True
                break
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        assert claimed, "an expired lock must not wedge the repo behind a recycled pid"
        rec = json.loads((ctl / "RUNNING.lock").read_text(encoding="utf-8"))
        assert rec["pid"] == proc.pid
    finally:
        proc.kill()
        proc.wait(timeout=30)


def test_controller_still_refuses_a_live_holder_inside_the_stale_window(tmp_path: Path):
    """The sibling of the case above: age must not become a way to steal a repo.

    A genuinely running controller mid-cycle has a fresh lock, and the age
    corroboration must not weaken that refusal.
    """
    import subprocess
    ctl = tmp_path / "control"
    ctl.mkdir()
    cfg = json.loads((ROOT / "ops" / "loop" / "config.dry.json").read_text(encoding="utf-8"))
    cfg.update({"control_dir": str(ctl), "max_cycles": 1, "cycle_deadline_sec": 5,
                "poll_sec": 1, "fixed_directive": "noop", "session_jsonl": ""})
    cfgp = tmp_path / "cfg.json"
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")

    stale = _load("slots").DEFAULT_STALE_AFTER
    (ctl / "RUNNING.lock").write_text(
        json.dumps({"pid": os.getpid(), "run_id": "held",
                    "ts": time.time() - (stale * 0.5)}),
        encoding="utf-8")

    r = subprocess.run([sys.executable, str(ROOT / "ops" / "loop" / "loop_controller.py"),
                        str(cfgp)], capture_output=True, text=True, timeout=120)
    assert r.returncode != 0, "a live holder inside the window still owns the repo"
    assert "already running" in (r.stderr + r.stdout)


def test_controller_reclaims_a_lock_held_by_a_dead_pid(tmp_path: Path):
    """Fail-open: a crashed controller must not lock the repo out forever."""
    import subprocess
    ctl = tmp_path / "control"
    ctl.mkdir()
    cfg = json.loads((ROOT / "ops" / "loop" / "config.dry.json").read_text(encoding="utf-8"))
    cfg.update({"control_dir": str(ctl), "max_cycles": 1, "cycle_deadline_sec": 3,
                "poll_sec": 1, "fixed_directive": "noop", "session_jsonl": ""})
    cfgp = tmp_path / "cfg.json"
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")
    (ctl / "RUNNING.lock").write_text(
        json.dumps({"pid": 999999999, "run_id": "ghost", "ts": time.time()}),
        encoding="utf-8")

    # Only the CLAIM is under test, so poll for it and kill - letting the cycle
    # run to completion would add two minutes of AHK-handshake timeout per run.
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "ops" / "loop" / "loop_controller.py"), str(cfgp)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        claimed = False
        for _ in range(150):
            if (ctl / "run_id.txt").is_file():
                claimed = True
                break
            if proc.poll() is not None:
                break
            time.sleep(0.1)
        assert claimed, "a dead holder must not block a new run from claiming the repo"
        rec = json.loads((ctl / "RUNNING.lock").read_text(encoding="utf-8"))
        assert rec["pid"] == proc.pid, "the live controller should own the lock now"
    finally:
        proc.kill()
        proc.wait(timeout=30)


# ---- named mutexes ---------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="windows mutex semantics")
def test_mutex_is_reentrant_for_the_same_thread():
    """Windows mutexes are owned per-thread; nesting must not self-deadlock."""
    with winmutex.hold("Global\\LWRC_TEST_NEST", timeout=5):
        with winmutex.hold("Global\\LWRC_TEST_NEST", timeout=5):
            pass


# winmutex.hold is a DELIBERATE no-op off Windows (winmutex.py:55-58 - "the
# loops are Windows-only"), so these two assert a primitive that does not exist
# on Linux: serialization there is vacuous, not broken. Same guard the timeout
# test already carried. The string-contract tests below stay unskipped - they
# are platform-independent and must keep running everywhere.
@pytest.mark.skipif(sys.platform != "win32", reason="windows mutex semantics")
def test_mutex_serializes_two_threads():
    live = 0
    peak = 0
    lock = threading.Lock()

    def worker():
        nonlocal live, peak
        with winmutex.hold("Global\\LWRC_TEST_SERIAL", timeout=30):
            with lock:
                live += 1
                peak = max(peak, live)
            time.sleep(0.05)
            with lock:
                live -= 1

    ts = [threading.Thread(target=worker) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=60)
    assert peak == 1, f"mutex allowed {peak} concurrent holders"


# ---- f1-phase6 item 5a: pinned parity constants -----------------------------
#
# slots.py and winmutex.py are BYTE-IDENTICAL between this repo and Riot
# Commander by contract. RC's mirror test compares its copy against the LW tree
# directly, which is the stronger check - but it SKIPS when the sibling tree is
# absent, so on a CI runner (one repo checked out, no sibling) parity is
# enforced by NOBODY. These pins close that hole: each repo's CI can prove
# parity alone, against a value both sides agreed to.
#
# RE-PINNING IS A JOINT ACT. Never regenerate these from whatever the file
# happens to be locally - that turns the guard into a rubber stamp and would
# launder a unilateral drift into "agreed". Change the shared file on one side,
# hand the other side the exact bytes, re-hash BOTH trees, confirm they match,
# and only then write the new digest here and in RC's copy in the same round.
SHARED_SHA256 = {
    # unchanged since the 2026-07-26 sync
    # Re-pinned 2026-08-01 for the three-repo docstring (two repos -> three, and
    # "either repo" -> "ANY of them"). Docstring only: no code, no protocol, no
    # behaviour. Bytes authored by RC, applied here VERBATIM and re-hashed from
    # this disk rather than trusted from the note. Provisional until all three
    # trees hash equal. Previous: 95077a62527c9764e896e3bd1da9027e5efd2b15631feb725fe6138cee5054f9
    "slots.py": "5297f2d041030398a9ba240aad527b2b01a86d6e7f57a196719af8f0a91cb0a6",
    # re-pinned 2026-07-26 for f1-phase6 item 9 (POSIX branch now emits
    # UNSERIALIZED); previous c21bfe4f309c9ed27e68f7cdf0458d001a9942e6a35c61869e6dedd16cc23b79
    "winmutex.py": "f1b4b011112685efb88616c52752657cf896fbb0993b2d2d264e7b3edde8b4f4",
}


@pytest.mark.parametrize("name", sorted(SHARED_SHA256))
def test_shared_module_matches_the_pinned_cross_repo_digest(name: str):
    """A drift here is not a merge conflict anyone notices - it is a silent
    concurrency bug where both loops believe they hold the only slot."""
    digest = hashlib.sha256((ROOT / "ops" / "loop" / name).read_bytes()).hexdigest()
    assert digest == SHARED_SHA256[name], (
        f"{name} no longer matches the digest agreed with Riot Commander. "
        f"If this change is intended, re-sync BOTH trees and re-pin on BOTH "
        f"sides in the same round - do not just update this constant.")


# ---- the shared surface no digest can pin: a VALUE, not a file --------------
#
# One slot root (C:\ProgramData\lw-loop\slots) serves both repos, but each repo
# reads its OWN config for max_concurrent_lanes. If the two disagree the
# effective machine-wide ceiling silently becomes max(lw, rc) - the governor
# stops governing and nothing fails. SHARED_SHA256 cannot cover this: the
# contract is a number living in six mutually-diverged config files across two
# trees, not a byte-identical file. Raised by RC 2026-07-27.
#
# The INTERNAL half below is the one that matters for CI, because CI checks out
# ONE tree: a cross-repo comparison can only ever skip there.

def _declared_lane_counts():
    """{config name: value} for every ops/loop config that declares the key."""
    out = {}
    for cfg in sorted((ROOT / "ops" / "loop").glob("config*.json")):
        data = json.loads(cfg.read_text(encoding="utf-8"))
        if "max_concurrent_lanes" in data:
            out[cfg.name] = data["max_concurrent_lanes"]
    return out


def test_every_config_declaring_lanes_agrees_with_the_others():
    declared = _declared_lane_counts()
    assert declared, "no config declares max_concurrent_lanes - the key was renamed or lost"
    assert len(set(declared.values())) == 1, (
        f"LW configs disagree on the machine-wide lane ceiling: {declared}. "
        f"They share one slot root, so the loosest value wins and the tighter "
        f"ones are decoration.")


def test_the_code_default_matches_what_the_configs_declare():
    """config.dry.json omits the key, so the in-code default IS the ceiling for
    any config that does not declare one. A default that drifts from the
    declared value means the omitting configs silently run a different ceiling."""
    declared = set(_declared_lane_counts().values())
    src = (ROOT / "ops" / "loop" / "loop_controller.py").read_text(encoding="utf-8")
    m = re.search(r'CFG\.get\(\s*["\']max_concurrent_lanes["\']\s*,\s*(\d+)\s*\)', src)
    assert m, "could not find the max_concurrent_lanes default in loop_controller.py"
    assert int(m.group(1)) in declared, (
        f"loop_controller defaults to {m.group(1)} but the configs declare "
        f"{declared} - any config omitting the key runs the wrong ceiling")


def test_riot_commander_agrees_on_the_lane_ceiling():
    """Cross-repo half. SKIPS on a CI runner by design - that is exactly why the
    internal half above exists and is not redundant with this one."""
    rc_root = Path(r"C:\Riot Commander") / "ops" / "loop"
    if not rc_root.is_dir():
        pytest.skip("Riot Commander tree not present on this machine")
    rc = {}
    for cfg in sorted(rc_root.glob("config*.json")):
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if "max_concurrent_lanes" in data:
            rc[cfg.name] = data["max_concurrent_lanes"]
    if not rc:
        pytest.skip("no RC config declares max_concurrent_lanes")
    assert set(rc.values()) | set(_declared_lane_counts().values()) == \
        set(_declared_lane_counts().values()), (
        f"RC declares {rc}, LW declares {_declared_lane_counts()} - one slot "
        f"root, so the higher number is the real ceiling in BOTH repos. "
        f"Change them in the same round or re-sync now.")


def test_acquired_is_logged_only_when_actually_held():
    """Emitter side of the defect RC found 2026-07-26: ACQUIRED must be gated on
    a real acquisition, and the fail-open path must emit a DISTINCT marker.
    An unconditional ACQUIRED opens a window that the gated RELEASED never
    closes, so the one case where the mutex did NOT serialize becomes the one
    case invisible to the overlap check."""
    src = (ROOT / "ops" / "loop" / "winmutex.py").read_text(encoding="utf-8")
    body = src[src.index("acquired = rc in"):src.index("yield handle")]
    assert "if acquired:" in body, "ACQUIRED must be gated on acquired"
    assert "UNSERIALIZED" in body, "the fail-open branch needs a distinct marker"
    # and the only ACQUIRED log sits inside that gate
    gated = body[body.index("if acquired:"):]
    assert "ACQUIRED" in gated


def test_unserialized_marker_wording_is_the_judge_contract():
    """p5_probe greps for this exact token; every emit site must use it."""
    src = (ROOT / "ops" / "loop" / "winmutex.py").read_text(encoding="utf-8")
    assert src.count("winmutex: UNSERIALIZED") == 3, (
        "all three unserialized paths (CreateMutexW failure, unexpected wait "
        "result, and the non-Windows no-op) must emit the same marker the "
        "judge hard-fails on")


def test_posix_no_op_branch_is_traced_not_silent(monkeypatch):
    """f1-phase6 item 9. Off Windows there is no named-mutex primitive, so hold
    degrades to a no-op - which is defensible. Yielding SILENTLY is not: every
    overlap guard in this file then passes VACUOUSLY on a POSIX runner, and the
    controller.log the judge reads carries no trace that nothing was serialized.
    Rejected alternative: an fcntl fallback. POSIX record locks are per-PROCESS,
    so test_mutex_serializes_two_threads (threads in ONE process) would stay red
    without a second RLock layer - the wrong size of change for a file that is
    byte-identical across two repos."""
    lines: list[str] = []
    monkeypatch.setattr(sys, "platform", "linux")
    with winmutex.hold("Global\\LWRC_TEST_POSIX", timeout=5, log=lines.append) as h:
        assert h is None, "the POSIX branch holds no handle"
    assert any(ln.startswith("winmutex: UNSERIALIZED Global\\LWRC_TEST_POSIX")
               for ln in lines), \
        f"the no-op branch must emit the judge's marker, got {lines!r}"
    assert not any("ACQUIRED" in ln for ln in lines), \
        "a no-op must never claim ACQUIRED - it would open a window RELEASED never closes"


def test_posix_no_op_lets_a_second_caller_in_while_the_first_holds(monkeypatch):
    """The POSIX mirror of test_mutex_timeout_raises_when_held_elsewhere, and
    the half that test_mutex_serializes_two_threads stops covering off Windows.

    Ported from RC 2c89e2a2 - both repos converged on this shape after RC found
    its own copy of the serialization test unguarded and failing on its nightly
    ubuntu run. The marker assertions above prove the no-op ANNOUNCES itself;
    only an actual second entry into a held name proves what it is announcing,
    and it must be proven rather than assumed - a future fcntl or RLock fallback
    would keep emitting the marker while quietly changing this behaviour, and
    the guard that noticed would be the one deleted as redundant.

    Overlap is established by events, not by timing: the first caller is parked
    inside its block until the second has been and gone. The marker is counted
    PER ENTRY because a log-reading judge sizes the breach by line count - one
    line per name would render N unprotected calls as a single incident.
    """
    monkeypatch.setattr(sys, "platform", "linux")
    name = "Global\\LWRC_TEST_POSIX_OVERLAP"
    lines: list[str] = []
    inside = threading.Event()
    release = threading.Event()

    def holder():
        with winmutex.hold(name, timeout=5, log=lines.append):
            inside.set()
            release.wait(timeout=10)

    t = threading.Thread(target=holder)
    t.start()
    try:
        assert inside.wait(timeout=10), "the first caller never entered its block"
        with winmutex.hold(name, timeout=0.2, log=lines.append) as h:
            assert h is None, "the POSIX branch holds no handle"
            assert not release.is_set(), \
                "the first caller must still be inside or this proves no overlap"
    finally:
        release.set()
        t.join(timeout=10)

    marker = "winmutex: UNSERIALIZED " + name
    assert sum(ln.startswith(marker) for ln in lines) == 2, \
        f"one marker per unprotected entry, not one per name, got {lines!r}"
    assert not any("ACQUIRED" in ln for ln in lines), \
        "a no-op must never claim ACQUIRED - it opens a window RELEASED never closes"


def test_posix_no_op_branch_survives_a_caller_that_passes_no_log(monkeypatch):
    """log= is optional on the two Windows fail-open branches; the new one must
    stay optional too or an unlogged caller crashes off-Windows."""
    monkeypatch.setattr(sys, "platform", "linux")
    with winmutex.hold("Global\\LWRC_TEST_POSIX_NOLOG") as h:
        assert h is None


def test_mutex_names_are_the_shared_contract():
    """Both repos must use the SAME names or they serialize against nothing."""
    assert winmutex.GEMINI_MUTEX == "Global\\LWRC_GEMINI"
    assert winmutex.GPU_MUTEX == "Global\\LW_GPU"


@pytest.mark.skipif(sys.platform != "win32", reason="windows mutex semantics")
def test_mutex_timeout_raises_when_held_elsewhere():
    got = threading.Event()
    release = threading.Event()

    def holder():
        with winmutex.hold("Global\\LWRC_TEST_TIMEOUT", timeout=10):
            got.set()
            release.wait(timeout=10)

    t = threading.Thread(target=holder)
    t.start()
    assert got.wait(timeout=10)
    try:
        with pytest.raises(winmutex.MutexTimeout):
            with winmutex.hold("Global\\LWRC_TEST_TIMEOUT", timeout=0.2):
                pytest.fail("acquired a mutex held by another thread")
    finally:
        release.set()
        t.join(timeout=10)
