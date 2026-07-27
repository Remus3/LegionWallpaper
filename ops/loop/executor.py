#!/usr/bin/env python
"""Pluggable EXECUTOR channel for the headless loop (the thing that does the work).

Companion seam to the adjudicator (the read-only BRAIN). The loop needs exactly
one thing from an executor: hand it a directive, get back what happened. That
was hard-wired to the AutoHotkey GUI bridge - a machine-wide singleton keyed on
a window title, which is why two loops could never run at once.

This module is the seam: one contract, `run(cycle, body, src) -> DoneRecord`,
with the AHK bridge lifted verbatim as today's default. The SDK backend
(headless `claude -p`) lands in P2; see
docs/specs/2026-07-26-f1-sdk-executor-channel.md.

P1 is a REFACTOR ONLY. Every string the AHK path writes, every deadline, every
log line and every stop() reason is byte-preserved from loop_controller.py - the
acceptance test is that a hermetic 2-cycle dry run produces byte-identical
control/ artifacts before and after. Nothing here is new behavior.

The controller owns the artifacts both channels share (directive.md, cycle.txt,
budget.json, the metering); the executor owns only what is channel-specific -
for AHK that is the gemini.ready typing handshake and the claude.done sentinel.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# ---- child-process teardown (platform seam) ---------------------------------
#
# The sdk timeout path was `taskkill /F /T` and nothing else. On POSIX taskkill
# is a missing executable, so the OSError was swallowed by a bare `pass`, the
# child outlived the "kill", and the proc.wait() that followed re-raised
# TimeoutExpired straight out of the handler instead of recording a failed
# cycle. The Windows case was not safe either: any taskkill failure took the
# same swallowed path. Found by RC 8333cbd3 on its nightly ubuntu run.

_REAP_TIMEOUT_SEC = 30

# Resolved at import, not inside the POSIX branch: SIGKILL does not exist on
# Windows, so naming it in there would make that branch unimportable - and so
# untestable - from the one machine this loop actually runs on.
_KILL_SIG = getattr(signal, "SIGKILL", signal.SIGTERM)


def _spawn_group_kwargs() -> dict:
    """POSIX-only Popen kwargs the teardown depends on. See the Popen call."""
    return {} if os.name == "nt" else {"start_new_session": True}


def _kill_child_tree(proc) -> str:
    """Kill a hung child and its descendants. Returns what actually happened.

    Returns a string rather than logging directly because the old code logged
    its INTENT ("taskkill /F /T") before trying, so the log read identically
    whether the kill worked, failed, or was not even possible on the platform.
    """
    if proc.poll() is not None:
        return "child already exited before the kill"
    if os.name == "nt":
        # NEVER Stop-Process (CLAUDE.md hard rule); /T so the whole tree dies -
        # a wedged `claude -p` has child tool processes of its own.
        try:
            r = subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                               capture_output=True, timeout=_REAP_TIMEOUT_SEC,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return (f"taskkill /F /T pid={proc.pid} rc={r.returncode}"
                    if r.returncode == 0 else
                    f"taskkill FAILED pid={proc.pid} rc={r.returncode} - "
                    f"falling back to proc.kill()")
        except (OSError, subprocess.SubprocessError) as e:
            proc.kill()
            return f"taskkill unavailable ({type(e).__name__}) - proc.kill() instead"
    try:
        os.killpg(os.getpgid(proc.pid), _KILL_SIG)
        return f"killpg pgid={os.getpgid(proc.pid)} sig={_KILL_SIG}"
    except (OSError, ProcessLookupError) as e:
        proc.kill()
        return f"killpg failed ({type(e).__name__}) - proc.kill() instead"


@dataclass
class DoneRecord:
    """What one executed cycle produced.

    `raw` is the parsed claude.done payload, carried through untouched because
    the director prompt is built from it - reshaping it would change directive
    text and make this refactor a behavior change.

    cost_usd / session_id are 0.0 / None on the AHK channel: that channel returns
    no receipt, which is why the controller still scrapes transcripts for cost.
    The SDK channel fills both from the `claude -p` result JSON (verified: it
    returns total_cost_usd and session_id), which is what retires the scraper.
    """

    cycle: int
    sha: str = ""
    tests_pass: str = "?"
    regressions: bool = False
    cost_usd: float = 0.0
    session_id: str | None = None
    error: str | None = None
    raw: dict = field(default_factory=dict)


def failure_raw(cycle: int, error: str, session_id) -> dict:
    """The payload a FAILED cycle hands the next director call.

    loop_controller does `done = rec.raw` and feeds exactly that forward as
    `=== LAST claude.done ===`. Every failure path used to leave `raw` at its
    default {}, so a cycle that timed out, died, or produced no structured
    output told the director LITERALLY NOTHING - `{}` - and the recorded error
    string never left this module. The cycle the director most needs to know
    about is the one that failed, and that was the one branch it could not see.
    Found by RC hitting the same hole in its own reporting seam, 2026-07-27.

    Deliberately NOT shaped like a success payload: no sha, no tests_pass, no
    regressions. Inventing a sha would defeat the controller's same-sha
    no-progress guard, and inventing the other two would report a test result
    nobody measured. A reader gets the failure and nothing that looks like a
    result.
    """
    rec = {"cycle": cycle, "error": error}
    if session_id:
        rec["session_id"] = session_id
    return rec


def directive_payload(cycle: int, body: str, src: str, clear_each_cycle: bool = True) -> str:
    """The exact text the bridge types. Lifted verbatim from loop_controller.

    Byte-exactness matters more than it looks: line 1 is the CYCLE header the AHK
    bridge skips, and the leading `/clear` is what gives each cycle a fresh
    context. Change the shape and the bridge silently types a slash command as
    prose (the `/clear` -> `clear/` race this channel already has a scar from).
    """
    clear_line = "/clear\n" if clear_each_cycle else ""
    if src in ("cycle_command", "fixed"):
        # a literal single-line task, typed as-is after /clear
        return f"CYCLE={cycle}\n{clear_line}{body}"
    return (
        f"CYCLE={cycle}\n{clear_line}"
        "/gemini-headless-upgrade and Read the file ops/loop/control/directive.md and fully execute it now. "
        "No questions; auto-pick the recommended option and proceed."
    )


class AhkExecutor:
    """The legacy GUI channel: write gemini.ready, wait for AHK to type it, wait
    for the done sentinel. Verbatim lift - see the module docstring.

    Machine-wide singleton by construction (it targets a window title), so this
    channel can never satisfy the concurrent-run requirement. That is the whole
    reason the SDK channel exists.
    """

    name = "ahk"

    def __init__(self, cfg, ctl, *, log, stop, awrite, wait_for, wait_gone, rjson,
                 stall_action, stall_recovery_directive):
        self.cfg = cfg
        self.ctl = ctl
        self.log = log
        self.stop = stop
        self.awrite = awrite
        self.wait_for = wait_for
        self.wait_gone = wait_gone
        self.rjson = rjson
        self.stall_action = stall_action
        self.stall_recovery_directive = stall_recovery_directive

    def run(self, cycle: int, body: str, src: str) -> DoneRecord:
        ctl = self.ctl
        self.awrite(ctl / "gemini.ready",
                    directive_payload(cycle, body, src,
                                      self.cfg.get("clear_each_cycle", True)))
        self.log(f"cycle {cycle}: directive written ({len(body)} chars), gemini.ready set")

        # AHK/stub deletes gemini.ready after typing; its disappearance IS the typed signal
        if not self.wait_gone(ctl / "gemini.ready", time.time() + 120):
            self.stop(f"cycle {cycle}: AHK never typed (gemini.ready not consumed in 120s)")
        deadline = time.time() + self.cfg["cycle_deadline_sec"]
        self.log(f"cycle {cycle}: typed (ready consumed); deadline in {self.cfg['cycle_deadline_sec']}s")

        # WP-I3: one-shot stall recovery before a hard STOP. On the FIRST cycle-deadline
        # breach, inject a /diagnose recovery directive into the existing (stalled) session
        # and extend the deadline ONCE (decision = stall_action, pure + tested); hard-STOP
        # only on a SECOND breach. The no-progress and AHK-never-typed guards remain the
        # runaway backstops so a truly wedged run still stops cleanly after exactly one
        # recovery attempt.
        breach = 0
        while not self.wait_for(ctl / "claude.done", deadline):
            breach += 1
            if self.stall_action(breach) == "stop":
                self.stop(f"cycle {cycle}: claude.done not seen after stall recovery (hard hang)")
            self.log(f"cycle {cycle}: deadline breach {breach} - injecting stall recovery, extending once")
            self.awrite(ctl / "gemini.ready", self.stall_recovery_directive(cycle))
            if not self.wait_gone(ctl / "gemini.ready", time.time() + 120):
                self.stop(f"cycle {cycle}: AHK never typed the stall-recovery directive")
            deadline = time.time() + self.cfg["cycle_deadline_sec"]

        done = self.rjson(ctl / "claude.done", {})
        (ctl / "claude.done").unlink(missing_ok=True)
        return DoneRecord(
            cycle=cycle,
            sha=done.get("sha") or "",
            tests_pass=done.get("tests_pass", "?"),
            regressions=bool(done.get("regressions")),
            raw=done,
        )


DONE_SCHEMA = {
    "type": "object",
    "properties": {
        "sha": {"type": "string"},
        "tests_pass": {"type": "string"},
        "regressions": {"type": "boolean"},
        "summary": {"type": "string"},
    },
    "required": ["sha", "tests_pass", "regressions", "summary"],
}

FINAL_STEP = (
    "FINAL STEP: do NOT run ops/loop/done_sentinel.py. Instead return the JSON object "
    "required by the output schema: sha (the live git HEAD after your commit), "
    "tests_pass (the count you observed THIS run, as a string), regressions (true only "
    "if you could not reach green), summary (one line)."
)

_AHK_FINAL_STEP = (
    "FINAL STEP: run  \"C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python"
    "\\Python314\\python.exe\" ops/loop/done_sentinel.py --tests <PASS_COUNT> "
    "--regressions <0_or_1>\n"
    "  where Claude substitutes the real passing-test count and 1 only if it could not "
    "get green."
)


def final_step_instruction(channel: str | None) -> str:
    """THE single source of truth for how a cycle reports completion.

    It has to be one function because the two channels need OPPOSITE
    instructions, and for a while both were hardcoded in prompt text that the
    executor then contradicted at runtime:

      ahk - done_sentinel.py writing control/claude.done IS the completion
            signal; the controller blocks on that file.
      sdk - the process returns a schema-validated JSON object, so running the
            sentinel is wrong (it writes a file nobody reads and costs a turn).

    `director_prompt.md` used to hardcode the AHK line and `config.json`'s
    `directive_suffix` repeated it, while `sdk_prompt()` appended the opposite.
    FINAL_STEP was appended last so it probably won, but "probably" is not a
    contract - and with sdk as the default the next director-authored cycle is
    the first to actually exercise it. Both prompt sources now defer here.
    """
    ch = (channel or "ahk").strip().lower()
    if ch == "ahk":
        return _AHK_FINAL_STEP
    if ch == "sdk":
        return FINAL_STEP
    raise ValueError(f"unknown executor channel {ch!r} (known: 'ahk', 'sdk')")


def sdk_prompt(cycle: int, body: str, src: str) -> str:
    """The prompt piped to `claude -p` on stdin.

    Deliberately NOT directive_payload(): that one carries a CYCLE header the AHK
    bridge skips and a leading `/clear`, both of which are artifacts of typing
    into a live window. A `-p` call is already a fresh process, so `/clear` is
    meaningless and the header would just be prose in the prompt.

    Slash commands still resolve under `-p` (confirmed against the CLI's own
    `--bare` help text), so the existing directive opener works unchanged.
    """
    head = body if src in ("cycle_command", "fixed") else (
        "/gemini-headless-upgrade and Read the file ops/loop/control/directive.md and "
        "fully execute it now. No questions; auto-pick the recommended option and proceed."
    )
    return f"{head}\n\n{FINAL_STEP}\n"


class SdkExecutor:
    """Headless `claude -p` channel. No window, no window title, no typing.

    This is the channel that makes concurrent LW+RC runs possible: it holds no
    machine-wide resource, so two loops collide only on things the slot governor
    and the named mutexes already bound.

    It also returns a receipt the AHK channel never could - total_cost_usd and a
    schema-validated structured_output - which is what retires the transcript
    meter and done_sentinel.py once this channel is the default.
    """

    name = "sdk"

    def __init__(self, cfg, ctl, *, log, stop, awrite, **_ignored):
        self.cfg = cfg
        self.ctl = ctl
        self.log = log
        self.stop = stop
        self.awrite = awrite
        self.session_id: str | None = None
        self.session_in_play: str | None = None

    def _argv_prefix(self) -> list:
        """`claude_cmd` may be a string or an argv list (tests inject a shim)."""
        cmd = self.cfg.get("claude_cmd")
        if isinstance(cmd, list):
            return list(cmd)
        if isinstance(cmd, str) and cmd:
            return [cmd]
        import shutil
        return [shutil.which("claude.cmd") or shutil.which("claude") or "claude"]

    def build_argv(self, cycle: int) -> list:
        import json as _json
        argv = self._argv_prefix() + [
            "-p",
            "--output-format", "json",
            "--input-format", "text",
            "--permission-mode", self.cfg.get("permission_mode", "bypassPermissions"),
            "--json-schema", _json.dumps(DONE_SCHEMA),
            "--add-dir", str(self.cfg.get("repo_root", ".")),
        ]
        model = self.cfg.get("executor_model")
        if model:
            argv += ["--model", str(model)]
        # OFF BY DEFAULT (operator 2026-07-26). On a Claude Code Max subscription
        # the CLI's total_cost_usd is NOTIONAL API-equivalent pricing, not what
        # the plan is billed - so capping on it throttles real work against a
        # number that does not correspond to spend. Set cycle_budget_usd only on
        # a metered API key, where the figure is real. The gemini ceiling is
        # unaffected: that vendor IS metered per token.
        budget = self.cfg.get("cycle_budget_usd")
        if budget:
            argv += ["--max-budget-usd", str(budget)]
        # clear_each_cycle True reproduces the AHK channel's /clear exactly: a
        # brand new session per cycle. False keeps continuity via --resume, which
        # is cheaper (no cold re-read of CLAUDE.md + living docs each cycle).
        if self.cfg.get("clear_each_cycle", True) or not self.session_id:
            import uuid
            sid = str(uuid.uuid4())
            argv += ["--session-id", sid]
        else:
            sid = self.session_id
            argv += ["--resume", sid]
        # Retain the id in play (minted OR resumed). On a timeout or an
        # unparseable-stdout cycle no result payload ever exists, so this is the
        # only handle on that cycle's transcript JSONL - and those are precisely
        # the cycles an operator has to go read.
        self.session_in_play = sid
        return argv

    def run(self, cycle: int, body: str, src: str) -> DoneRecord:
        import json as _json
        import subprocess as _sp

        argv = self.build_argv(cycle)
        prompt = sdk_prompt(cycle, body, src)
        timeout = float(self.cfg.get("cycle_deadline_sec", 5400))
        self.log(f"cycle {cycle}: sdk executor starting ({len(body)} chars, timeout {timeout:.0f}s)")

        # start_new_session is POSIX-only and load-bearing, not tidiness: it
        # gives the child its OWN process group, and without it os.getpgid()
        # answers with THIS controller's group - so the killpg below would kill
        # the loop trying to do the reaping. Windows takes it as
        # `unused_start_new_session`, so passing it there is a silent no-op.
        # creationflags stays written out LITERALLY rather than folded into the
        # same **dict: tests/test_no_console_flash.py resolves that argument by
        # AST at every spawn site, and a **dict is opaque to it - hiding the
        # flag would make this site unprovable while the guard kept reporting a
        # protection it could no longer see. Convention from RC 8333cbd3.
        proc = _sp.Popen(argv, stdin=_sp.PIPE, stdout=_sp.PIPE, stderr=_sp.PIPE,
                         text=True, encoding="utf-8", errors="replace",
                         cwd=str(self.cfg.get("repo_root", ".")),
                         creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0),
                         **_spawn_group_kwargs())
        try:
            out, err = proc.communicate(prompt, timeout=timeout)
        except _sp.TimeoutExpired:
            self.log(f"cycle {cycle}: sdk timeout after {timeout:.0f}s "
                     f"(sid={self.session_in_play}) - killing the child tree")
            self.log(f"cycle {cycle}: {_kill_child_tree(proc)}")
            # Bounded, and its expiry is deliberately NOT fatal. By the time it
            # runs the cycle's verdict is already decided, and letting it raise
            # is what turned one wedged child into a dead unattended run: the
            # contract is that a cycle without a usable result degrades to a
            # RECORDED FAILED CYCLE, never an exception out of run().
            try:
                proc.wait(timeout=_REAP_TIMEOUT_SEC)
            except _sp.TimeoutExpired:
                self.log(f"cycle {cycle}: child survived the reap - recording "
                         f"the failed cycle anyway")
            err = f"timeout after {timeout:.0f}s"
            return DoneRecord(cycle=cycle, session_id=self.session_in_play,
                              error=err,
                              raw=failure_raw(cycle, err, self.session_in_play))

        try:
            res = _json.loads(out.strip() or "{}")
        except ValueError:
            head = (out or err or "").strip().replace("\n", " ")[:200]
            self.log(f"cycle {cycle}: sdk returned unparseable stdout "
                     f"(sid={self.session_in_play}): {head}")
            err = f"unparseable result: {head}"
            return DoneRecord(cycle=cycle, session_id=self.session_in_play,
                              error=err,
                              raw=failure_raw(cycle, err, self.session_in_play))

        cost = float(res.get("total_cost_usd") or 0.0)
        # A payload sid supersedes the retained one, but never leaves us blind:
        # the log line is the operator's only route to the transcript file.
        sid = res.get("session_id") or self.session_in_play
        if sid:
            self.session_id = sid

        if res.get("is_error") or proc.returncode != 0:
            detail = str(res.get("result") or err or "").strip().replace("\n", " ")[:200]
            self.log(f"cycle {cycle}: sdk reported error "
                     f"(rc={proc.returncode} sid={sid}): {detail}")
            err = detail or f"exit {proc.returncode}"
            return DoneRecord(cycle=cycle, cost_usd=cost, session_id=sid,
                              error=err, raw=failure_raw(cycle, err, sid))

        so = res.get("structured_output")
        if not isinstance(so, dict) or not all(k in so for k in DONE_SCHEMA["required"]):
            # The CLI validates against --json-schema, so this means the run ended
            # without producing one (hit a limit, refused, wandered off). Treat it
            # as a failed cycle rather than inventing fields - a fabricated sha
            # would defeat the controller's same-sha no-progress guard.
            self.log(f"cycle {cycle}: sdk returned no valid structured_output (sid={sid})")
            err = "missing or incomplete structured_output"
            return DoneRecord(cycle=cycle, cost_usd=cost, session_id=sid,
                              error=err, raw=failure_raw(cycle, err, sid))

        self.log(f"cycle {cycle}: sdk done cost=${round(cost, 4)} sid={sid} "
                 f"sha={str(so.get('sha'))[:8]} tests={so.get('tests_pass')}")
        return DoneRecord(
            cycle=cycle,
            sha=str(so.get("sha") or ""),
            tests_pass=str(so.get("tests_pass", "?")),
            regressions=bool(so.get("regressions")),
            cost_usd=cost,
            session_id=sid,
            raw=dict(so),
        )


def gate_inactive_reason(repo_root) -> str | None:
    """Why the commit gate is not active, or None if it is.

    `core.hooksPath` is LOCAL config and is NOT cloned. A fresh clone therefore
    has the tracked `.githooks/` on disk and NO hooks running - the tracked dir
    buys nothing until someone sets the config. An unattended headless run in
    that state commits and pushes with no glyph / ruff / trailer gate at all,
    and nobody is watching a session-start report. So the loop refuses to start
    rather than run ungated: this is the one place where failing loud beats
    degrading quietly.
    """
    import subprocess as _sp
    installer = Path(repo_root) / "tools" / "install_git_hooks.py"
    if not installer.is_file():
        return None  # not this repo's concern - do not invent a blocker
    try:
        r = _sp.run([sys.executable, str(installer), "--check", "--repo", str(repo_root)],
                    capture_output=True, text=True, timeout=30,
                    creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0))
    except (OSError, _sp.SubprocessError) as e:
        return f"could not verify the commit gate: {e}"
    if r.returncode != 0:
        detail = (r.stderr or r.stdout).strip().replace("\n", " ")[:200]
        return detail or "commit gate not active"
    return None


def build(cfg, ctl, **deps):
    """Return the executor the config selects. `channel` defaults to ahk.

    Unknown values fail LOUD rather than silently falling back: a typo in
    `channel` must not quietly run the legacy singleton channel during a
    concurrent run, which is exactly the failure this seam exists to prevent.
    """
    channel = str(cfg.get("channel", "ahk")).strip().lower()
    if channel == "ahk":
        return AhkExecutor(cfg, ctl, **deps)
    if channel == "sdk":
        return SdkExecutor(cfg, ctl, **deps)
    raise ValueError(
        f"unknown executor channel {channel!r} (known: 'ahk', 'sdk')")
