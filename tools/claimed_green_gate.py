#!/usr/bin/env python3
"""Stop-hook gate: refuse a claimed-green handoff that no run backs (P1).

LW's single most documented failure class is a "tests pass" claim that was never
backed by a run this session. The manual answer has been a whole `verifier`
subagent per claim. This is the mechanical one, and it fires at exactly the
right moment: `Stop` is the event where Claude asserts it is done, and its
payload carries BOTH halves of the question - `last_assistant_message` is the
claim and `transcript_path` is the evidence.

Contract (official hook docs, see docs/MCP_LIFT_DIVE_2026-08-01.md section 3):
  - a block is exit 0 with top-level {"decision": "block", "reason": ...}, and
    the reason IS fed back to the model, which is what makes this a gate rather
    than a log line
  - `stop_hook_active` is COOPERATIVE. The harness does NOT cap the loop; a hook
    that always blocks wedges the session forever. Reading it first is the
    single most important line in this file.

Detectors, ported in design (not code) from `red-handed` - MIT, dived
2026-08-01, NOT installed: it is four days old, has no Windows CI, and carries
two path-separator bugs that silently drop subdirectory sessions.

  claim-no-run    a green claim, and no test-shaped command ran at all
  claim-vs-fail   a green claim, and the LAST run was red
  no-verify       a commit bypassing hooks right after a hook rejected one

Design rule taken from red-handed's own false-positive regressions: when the
evidence is ambiguous, ALLOW. A gate that cries wolf gets disabled, and a
disabled gate catches nothing. Every ambiguous case here is a test.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path

# A run that was killed is not a run that failed. red-handed learned this the
# same way: 124 timeout, 137 SIGKILL, 143 SIGTERM.
INTERRUPTED_CODES = {124, 137, 143}

GREEN_CLAIM = re.compile(
    r"""(
      tests?\s+(all\s+)?pass(es|ed|ing)?
    | (full\s+)?suite\s+(is\s+)?(green|passes|passing)
    | \d+\s+passed
    | all\s+green
    | ci\s+(is\s+)?green
    | green\s+on\s+[0-9a-f]{7,}
    )""",
    re.I | re.X,
)

# The operator can always waive it. Silence beats an accusation the operator
# already answered.
WAIVER = re.compile(
    r"(skip|don'?t\s+run|no\s+need\s+to\s+run|without\s+running)\s+"
    r"(the\s+)?(tests?|suite)",
    re.I,
)

TEST_COMMAND = re.compile(r"(^|[\s;&|])(py\.?test|python\s+-m\s+pytest)\b", re.I)

HOOK_REJECTION = re.compile(
    r"(precommit_gate\s+BLOCKED|pre-commit|pre-push|commit-msg|husky|lint-staged"
    r"|hook\s+(failed|rejected|blocked))",
    re.I,
)

BYPASS_ENV = re.compile(r"\b(HUSKY=0|HUSKY_SKIP_HOOKS=1|NO_VERIFY=1|SKIP=)", re.I)


def _read_payload() -> dict:
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except (ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _tokens(command: str) -> list:
    """Split a command line into tokens, tolerating Windows backslash paths.

    shlex on posix=True eats backslashes, which turns C:\\LegionWallpaper into
    C:LegionWallpaper and can drop a flag. posix=False keeps them.
    """
    try:
        return shlex.split(command, posix=False)
    except ValueError:
        return command.split()


def _is_commit_bypass(command: str) -> bool:
    """True for `git commit` with hooks off - and NOT for `git push -n`.

    `git push -n` is a dry run and is harmless; a substring match on "-n" reads
    it as a bypass. Segment the command instead. This exact false positive is
    one red-handed had to fix.
    """
    if BYPASS_ENV.search(command):
        return True
    tokens = _tokens(command)
    lowered = [t.lower() for t in tokens]
    if "git" not in lowered:
        return False
    try:
        verb = lowered[lowered.index("git") + 1]
    except IndexError:
        return False
    if verb != "commit":
        return False
    return any(t in ("--no-verify", "-n") for t in lowered)


def _is_interrupted(value) -> bool:
    """`interrupted` arrives as the STRING "False" in real transcripts.

    Plain truthiness on that is always True, which would classify every run as
    interrupted and silently disable the gate.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def _classify_run(action: dict) -> str:
    """pass / fail / unknown / no-evidence for one test-shaped command.

    Measured against a live transcript: a Bash result carries NO `code` field at
    all - only stdout, stderr and interrupted. So the pytest COUNT LINE is the
    primary evidence and the exit code is the fallback, not the other way round.
    """
    code = action.get("code")
    output = action.get("output") or ""
    if _is_interrupted(action.get("interrupted")):
        return "unknown"
    if isinstance(code, int) and code in INTERRUPTED_CODES:
        return "unknown"
    if re.search(r"\b\d+\s+failed\b", output, re.I):
        return "fail"
    if re.search(r"\b\d+\s+(passed|deselected)\b", output, re.I):
        return "pass"
    if isinstance(code, int):
        return "pass" if code == 0 else "fail"
    return "no-evidence"


def _iter_actions(transcript: Path):
    """Yield {command, output, code, interrupted} per tool call, in order.

    The result does NOT sit on the assistant entry that made the call - it
    arrives on a LATER user entry joined by `tool_use_id`, with the payload at
    entry-level `toolUseResult`. Measured on a live 1.4 MB transcript: 115
    tool_use, 115 results, 115 paired. Reading only the same entry finds every
    command and no outcome, which classifies a real green run as unknown.

    The same-entry shape is still accepted, so a hand-built fixture works too.

    Sidechain (subagent) lines are NOT filtered out: a suite run by a subagent
    is still a run, and accusing on that is a false positive.
    """
    try:
        raw_lines = transcript.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return

    entries = []
    for line in raw_lines:
        try:
            entry = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(entry, dict):
            entries.append(entry)

    # Pass 1: join every tool_result back to the id of the call it answers.
    results = {}
    for entry in entries:
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        payload = entry.get("toolUseResult")
        if not isinstance(payload, dict):
            continue
        for part in content:
            if isinstance(part, dict) and part.get("type") == "tool_result":
                results[part.get("tool_use_id")] = payload

    def _shape(payload: dict, command: str) -> dict:
        return {
            "command": command,
            "output": str(payload.get("stdout") or "")
            + str(payload.get("stderr") or ""),
            "code": payload.get("code"),
            "interrupted": payload.get("interrupted"),
        }

    # Pass 2: walk the calls in order, pairing each with its result.
    for entry in entries:
        message = entry.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        same_entry = entry.get("toolUseResult")
        same_entry = same_entry if isinstance(same_entry, dict) else {}
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "tool_use":
                continue
            tool_input = part.get("input")
            if not isinstance(tool_input, dict):
                continue
            command = tool_input.get("command")
            if not isinstance(command, str) or not command.strip():
                continue
            payload = results.get(part.get("id"), same_entry)
            yield _shape(payload, command)


def _user_text(transcript: Path) -> str:
    chunks = []
    try:
        handle = transcript.open(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    with handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(entry, dict) or entry.get("type") != "user":
                continue
            message = entry.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str):
                chunks.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        chunks.append(part["text"])
    return "\n".join(chunks)


def _block(reason: str) -> int:
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    sys.stdout.write("\n")
    return 0


def evaluate(payload: dict) -> str | None:
    """Return a block reason, or None to allow. Pure - the tests drive this."""
    # THE LOOP GUARD. Nothing above this line.
    if payload.get("stop_hook_active"):
        return None

    raw_path = payload.get("transcript_path")
    if not isinstance(raw_path, str) or not raw_path:
        return None
    transcript = Path(raw_path)
    if not transcript.is_file():
        return None

    actions = list(_iter_actions(transcript))

    # no-verify runs regardless of whether a green claim was made - bypassing a
    # hook rejection is its own finding.
    for index, action in enumerate(actions):
        if not _is_commit_bypass(action["command"]):
            continue
        earlier = actions[:index]
        # A real Bash result carries NO exit code, so requiring a non-zero one
        # here disabled this detector entirely against live transcripts. Only a
        # PROVEN success (code == 0) rules a rejection out.
        rejected = any(
            HOOK_REJECTION.search(prior["output"] or "") and prior.get("code") != 0
            for prior in earlier
        )
        if rejected:
            return (
                "no-verify: a hook rejected a commit and the next commit turned "
                "hooks off. The gate is the authority - fix what it flagged, do "
                "not bypass it. Re-run the commit without --no-verify."
            )

    claim = payload.get("last_assistant_message")
    if not isinstance(claim, str) or not GREEN_CLAIM.search(claim):
        return None

    if WAIVER.search(_user_text(transcript)):
        return None

    runs = [a for a in actions if TEST_COMMAND.search(a["command"])]
    if not runs:
        return (
            "claim-no-run: this turn claims tests pass, but no pytest run "
            "happened in this session - not in the main thread and not in a "
            "subagent. Run `python -m pytest -q` and report the counts you "
            "actually observed, or drop the claim."
        )

    verdicts = [_classify_run(run) for run in runs]
    decided = [v for v in verdicts if v in ("pass", "fail")]
    if decided and decided[-1] == "fail":
        return (
            "claim-vs-fail: this turn claims tests pass, but the last pytest run "
            "in this session was RED. Re-run it and report the counts from that "
            "run, not from an earlier one."
        )
    if not decided:
        # The one place ambiguity does NOT allow: the missing evidence IS the
        # thing the claim asserts. Cheap to satisfy - re-run and show counts.
        return (
            "no-counts: a pytest command ran but left no machine-readable "
            "result - no pass/fail counts and no exit code. That is not "
            "evidence of green. Re-run `python -m pytest -q` and report the "
            "counts you actually observed."
        )
    return None


def main() -> int:
    reason = evaluate(_read_payload())
    if reason:
        return _block(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
