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

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path


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
    raise ValueError(
        f"unknown executor channel {channel!r} (P1 ships 'ahk'; 'sdk' lands in P2)")
