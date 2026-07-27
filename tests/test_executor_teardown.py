"""A hung sdk child must die, and the log must say what actually happened.

The sdk timeout path was `taskkill /F /T` and nothing else. On POSIX taskkill is
a missing executable, so the OSError went into a bare `pass`, the child outlived
the "kill", and the proc.wait() after it re-raised TimeoutExpired out of the
handler - turning one wedged child into a dead unattended run. The Windows path
was not safe either: any taskkill failure took the same swallowed route.

The contract these pin: a cycle without a usable result degrades into a RECORDED
FAILED CYCLE, never an exception escaping run(). Found by RC on its nightly
ubuntu run (RC 8333cbd3); LW carried the identical code.

The POSIX branch is exercised on Windows by monkeypatching os.name. That is
deliberate - the branch that cannot run on the machine the loop lives on is
exactly the one that rots unnoticed.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "lw_executor_teardown_under_test", ROOT / "ops" / "loop" / "executor.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ex = _load()


class _FakeProc:
    def __init__(self, pid=4242, alive=True):
        self.pid = pid
        self._alive = alive
        self.killed = False

    def poll(self):
        return None if self._alive else 0

    def kill(self):
        self.killed = True
        self._alive = False


def test_spawn_group_kwargs_is_posix_only(monkeypatch):
    """On Windows start_new_session is silently ignored, so passing it there
    would be a no-op that reads as protection."""
    monkeypatch.setattr(os, "name", "nt")
    assert ex._spawn_group_kwargs() == {}
    monkeypatch.setattr(os, "name", "posix")
    assert ex._spawn_group_kwargs() == {"start_new_session": True}


def test_kill_sig_exists_on_every_platform():
    """SIGKILL is absent on Windows; resolving it at import inside the POSIX
    branch would make that branch unimportable from the machine that runs."""
    assert ex._KILL_SIG is not None


def test_an_already_dead_child_is_not_killed_again():
    proc = _FakeProc(alive=False)
    assert "already exited" in ex._kill_child_tree(proc)
    assert proc.killed is False


def test_posix_uses_the_process_group_not_the_bare_pid(monkeypatch):
    """killpg on the child's OWN group. Without start_new_session the child
    shares the CONTROLLER's group, so this call would kill the reaper."""
    monkeypatch.setattr(os, "name", "posix")
    seen = {}
    monkeypatch.setattr(os, "getpgid", lambda pid: 9999, raising=False)
    monkeypatch.setattr(os, "killpg",
                        lambda pgid, sig: seen.update(pgid=pgid, sig=sig),
                        raising=False)
    proc = _FakeProc()
    out = ex._kill_child_tree(proc)
    assert seen["pgid"] == 9999, "must kill the group, not the pid"
    assert "killpg" in out


def test_posix_falls_back_to_kill_when_the_group_is_gone(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(os, "getpgid", lambda pid: 9999, raising=False)

    def boom(pgid, sig):
        raise ProcessLookupError("gone")

    monkeypatch.setattr(os, "killpg", boom, raising=False)
    proc = _FakeProc()
    out = ex._kill_child_tree(proc)
    assert proc.killed is True, "a failed killpg must still reap the child"
    assert "proc.kill()" in out


def test_windows_reports_the_taskkill_outcome_not_the_intent(monkeypatch):
    """The old code logged 'taskkill /F /T' BEFORE trying, so the log read the
    same whether the kill worked, failed, or was impossible."""
    monkeypatch.setattr(os, "name", "nt")

    class _R:
        returncode = 1

    monkeypatch.setattr(ex.subprocess, "run", lambda *a, **k: _R())
    out = ex._kill_child_tree(_FakeProc())
    assert "FAILED" in out and "rc=1" in out


def test_windows_falls_back_when_taskkill_is_not_there(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")

    def boom(*a, **k):
        raise FileNotFoundError("taskkill")

    monkeypatch.setattr(ex.subprocess, "run", boom)
    proc = _FakeProc()
    out = ex._kill_child_tree(proc)
    assert proc.killed is True
    assert "proc.kill()" in out


def test_the_reap_timeout_is_bounded():
    """Unbounded, a wedged child parks the loop forever; the old code hardcoded
    30 in one place and the guard needs a name to assert against."""
    assert 0 < ex._REAP_TIMEOUT_SEC <= 120


def test_the_popen_site_still_states_creationflags_literally():
    """RC's constraint, and it protects LW's own guard: tests/
    test_no_console_flash.py resolves creationflags by AST, and a **dict is
    opaque to it. Folding the flag in would leave the spawn unprovable while
    the guard kept reporting a protection it could no longer see."""
    src = (ROOT / "ops" / "loop" / "executor.py").read_text(encoding="utf-8")
    i = src.index("_sp.Popen(")
    call = src[i:i + 600]
    assert "creationflags=getattr(_sp" in call, \
        "creationflags must stay literal at the Popen site, not hidden in a **dict"
    assert "_spawn_group_kwargs()" in call


@pytest.mark.parametrize("survives", [False, True])
def test_a_timeout_never_raises_out_of_the_run(monkeypatch, survives):
    """THE contract. Even when the child outlives the reap, the cycle must be
    RECORDED as failed rather than blowing up an unattended run."""
    calls = {"waited": False}

    class _P:
        pid = 1234
        returncode = None

        def poll(self):
            return None

        def kill(self):
            pass

        def communicate(self, *a, **k):
            raise subprocess.TimeoutExpired("claude", 1)

        def wait(self, timeout=None):
            calls["waited"] = True
            if survives:
                raise subprocess.TimeoutExpired("claude", timeout or 0)
            return 0

    logged: list[str] = []
    monkeypatch.setattr(ex, "_kill_child_tree", lambda p: "stubbed kill")
    # run() does `import subprocess as _sp` at CALL time, so the real module is
    # what has to be patched - patching a name on ex would miss it entirely.
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _P())

    ex_obj = ex.SdkExecutor({"cycle_deadline_sec": 1, "repo_root": str(ROOT)},
                            ROOT / "ops" / "loop" / "control",
                            log=logged.append, stop=lambda *a, **k: None,
                            awrite=lambda *a, **k: None)
    rec = ex_obj.run(1, "body", "src")

    assert calls["waited"], "the reap must be attempted"
    assert rec.error and "timeout" in rec.error
    assert not rec.sha, (
        "a failed cycle must carry NO sha - a fabricated one defeats the "
        "controller's same-sha no-progress guard")
    if survives:
        assert any("survived the reap" in ln for ln in logged), \
            "a child that outlives the reap must be said out loud, not swallowed"
