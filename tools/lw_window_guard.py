# arch: window-popup drift guard | section=tools | frozen=no
"""lw_window_guard.py - report any config that would POP A VISIBLE WINDOW.

SessionStart hook. Stdout (markdown) is injected as session context, so a
regression is visible at session start instead of being discovered by a
console flashing over the operator's desktop at 03:00.

Standing rule this enforces (memory feedback-no-console-flash-legion):
no LW/RC automation may create a visible console window. The three ways
that rule regresses, and the three checks here:

  A. SCHEDULED TASKS - a task re-registered without the hidden treatment.
     Risk = "Logon Mode: Interactive only" (runs in the operator's session,
     so a window is possible) AND a console-host binary AND no hidden flag.
     Calibrated against live schtasks output 2026-07-26: S4U and
     ServiceAccount tasks report "Interactive/Background" and run in
     session 0, where no window can appear at all.
  B. SUBPROCESS CALL SITES - a spawn in tools/ or ops/ without
     creationflags=CREATE_NO_WINDOW.
  C. GUI-BRIDGE DRIFT - an AutoHotkey process alive while the loop is
     configured for the headless sdk channel (see
     docs/specs/2026-07-26-f1-sdk-executor-channel.md); under channel=sdk
     no AHK bridge should exist at all.

Read-only. Never registers, edits or kills anything - it reports, the
operator (or a directed session) decides. Exit is always 0: a guard that
can block a session start is worse than the drift it watches for.
"""
import csv
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Binaries that allocate a console when started in an interactive session.
# Deliberately an allowlist, not a denylist: an unknown .exe is assumed to be
# a GUI app (MSIAfterburner, StartIsBack) so the guard does not cry wolf.
CONSOLE_BINS = {
    "python.exe", "python", "powershell.exe", "powershell", "pwsh.exe", "pwsh",
    "cmd.exe", "cmd", "cscript.exe", "cscript", "node.exe", "node",
    "ruby.exe", "perl.exe", "git.exe", "claude.cmd", "claude.ps1", "npm.cmd",
}
HIDDEN_MARKERS = ("-windowstyle hidden", "-w hidden", "-windowstyle=hidden", "//b")
SCAN_DIRS = ("tools", "ops")
SPAWN_RE = re.compile(r"subprocess\.(?:run|Popen|call|check_output|check_call)\s*\(")


def _run(args, timeout=6):
    try:
        return subprocess.run(args, capture_output=True, text=True, errors="replace",
                              timeout=timeout, creationflags=NO_WINDOW).stdout
    except (subprocess.SubprocessError, OSError):
        return ""


def _exe_of(cmd):
    """First token of a 'Task To Run' string, honoring a quoted path."""
    cmd = (cmd or "").strip()
    if not cmd:
        return ""
    if cmd.startswith('"'):
        end = cmd.find('"', 1)
        head = cmd[1:end] if end > 0 else cmd[1:]
    else:
        head = cmd.split(" ", 1)[0]
    return os.path.basename(head).lower()


def check_tasks():
    """A - scheduled tasks that could pop a console in the operator's session."""
    out = _run(["schtasks", "/query", "/fo", "csv", "/v"], timeout=20)
    if not out:
        return None, []
    try:
        rows = list(csv.DictReader(io.StringIO(out)))
    except csv.Error:
        return None, []
    seen, risky, total = set(), [], 0
    for r in rows:
        name = (r.get("TaskName") or "").strip()
        if not name or name.startswith("\\Microsoft") or name in seen:
            continue
        seen.add(name)
        total += 1
        # "Interactive only" = the operator's session. "Interactive/Background"
        # = S4U / ServiceAccount = session 0 = no window is possible.
        if (r.get("Logon Mode") or "").strip().lower() != "interactive only":
            continue
        cmd = (r.get("Task To Run") or "").strip()
        if _exe_of(cmd) not in CONSOLE_BINS:
            continue
        low = cmd.lower()
        if any(m in low for m in HIDDEN_MARKERS):
            continue
        risky.append((name.lstrip("\\"), cmd[:110]))
    return total, risky


def check_spawns():
    """B - subprocess call sites with no CREATE_NO_WINDOW."""
    misses = []
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for py in base.rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            try:
                text = py.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in SPAWN_RE.finditer(text):
                # The call text: from the open paren to its match, capped so a
                # runaway paren scan cannot stall the hook.
                depth, end = 0, m.end()
                for i in range(m.end() - 1, min(len(text), m.end() + 1200)):
                    if text[i] == "(":
                        depth += 1
                    elif text[i] == ")":
                        depth -= 1
                        if depth == 0:
                            end = i
                            break
                call = text[m.start():end]
                if "creationflags" in call or "CREATE_NO_WINDOW" in call:
                    continue
                line = text.count("\n", 0, m.start()) + 1
                misses.append(f"{py.relative_to(ROOT).as_posix()}:{line}")
    return misses


def check_bridge():
    """C - AHK bridge alive while the loop is configured headless."""
    channel = ""
    try:
        cfg = json.loads((ROOT / "ops" / "loop" / "config.json").read_text(encoding="utf-8"))
        channel = str(cfg.get("channel", "")).strip().lower()
    except (OSError, ValueError):
        return None
    if channel != "sdk":
        return None  # ahk channel (or pre-F1 config): a live bridge is expected
    out = _run(["tasklist", "/fi", "IMAGENAME eq AutoHotkey*.exe", "/fo", "csv"], timeout=8)
    return "AutoHotkey" in out


def main():
    total, risky = check_tasks()
    misses = check_spawns()
    bridge = check_bridge()

    print("# Window-popup guard")
    print()
    if total is None:
        print("- tasks: PROBE FAILED (schtasks unavailable) - not a clean result")
    elif risky:
        print(f"- tasks: **{len(risky)} of {total} would pop a console window**")
        for name, cmd in risky:
            print(f"  - `{name}` -> `{cmd}`")
        print("  - fix: add `-WindowStyle Hidden`, use `pythonw.exe`, or set the")
        print("    principal to S4U (session 0, no window possible)")
    else:
        print(f"- tasks: clean ({total} non-Microsoft tasks, none window-capable)")

    if misses:
        print(f"- subprocess sites missing CREATE_NO_WINDOW: **{len(misses)}**")
        for m in misses[:12]:
            print(f"  - {m}")
        if len(misses) > 12:
            print(f"  - ... and {len(misses) - 12} more")
    else:
        print("- subprocess sites: clean (every spawn in tools/ + ops/ sets creationflags)")

    if bridge is True:
        print("- **AHK bridge ALIVE while channel=sdk** - the headless channel must")
        print("  have no GUI bridge; stop it with `taskkill /F /IM AutoHotkey*.exe`")
    elif bridge is False:
        print("- gui bridge: clean (channel=sdk, no AutoHotkey process)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
