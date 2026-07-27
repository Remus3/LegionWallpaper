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
import ast
import csv
import io
import json
import os
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

# Tasks that MUST stay in the operator's interactive session because they touch
# per-session Win32 surfaces that do not exist in session 0. Reported as
# "expected" rather than as drift - a guard that flags the same 3 rows forever
# is a guard people learn to ignore. Source: RC's own S4U sweep 2026-07-26
# (13 tasks flipped, these 3 deliberately held).
#   RC-HotkeyListener  - RegisterHotKey + overlay, needs a window station
#   RC-LiveFlipWatcher - toast notifications, per-session
#   RC-Supervisor      - Win32 + overlay ownership
# Add a row here ONLY with the reason; an entry without one is drift wearing a
# costume.
EXPECTED_INTERACTIVE = {
    "RC-HotkeyListener": "RegisterHotKey + overlay (per-session window station)",
    "RC-LiveFlipWatcher": "toast notifications (per-session)",
    "RC-Supervisor": "Win32 + overlay ownership",
}
SCAN_DIRS = ("tools", "ops")


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
        return None, [], []
    try:
        rows = list(csv.DictReader(io.StringIO(out)))
    except csv.Error:
        return None, [], []
    seen, risky, expected, total = set(), [], [], 0
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
        short = name.lstrip("\\")
        if short in EXPECTED_INTERACTIVE:
            expected.append(short)
            continue
        risky.append((short, cmd[:110]))
    return total, risky, expected


SPAWN_FUNCS = {"run", "Popen", "call", "check_call", "check_output"}
FLAG_NAME = "CREATE_NO_WINDOW"
FLAG_VALUE = 0x08000000


def _module_consts(tree):
    """Module-level NAME -> value-node bindings, so a spawn may pass a constant."""
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    out[t.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                out[node.target.id] = node.value
    return out


def resolves_to_flag(node, consts, depth=0):
    """True only when `node` provably carries CREATE_NO_WINDOW.

    This replaced a substring test (`"creationflags" in call`) that stood in for
    a value check. That form passed on `creationflags=0`, on the word appearing
    in a comment inside the call, and on `getattr(subprocess, "CREATE_NO_WINDW",
    0)` - a typo that returns the 0 default, spawns fine, and flashes anyway.
    Fails CLOSED: an expression this cannot follow is not the flag, because a
    guard that guesses yes is the fail-open it was written to remove.
    Riot Commander hit the identical shape in its own copy, 2026-07-27.
    """
    if node is None or depth > 6:
        return False
    if isinstance(node, ast.Attribute):
        return node.attr == FLAG_NAME
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id == "getattr":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                return node.args[1].value == FLAG_NAME
        return False
    if isinstance(node, ast.Constant):
        return node.value == FLAG_VALUE
    if isinstance(node, ast.Name):
        return resolves_to_flag(consts.get(node.id), consts, depth + 1)
    if isinstance(node, ast.IfExp):
        return (resolves_to_flag(node.body, consts, depth + 1)
                or resolves_to_flag(node.orelse, consts, depth + 1))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return (resolves_to_flag(node.left, consts, depth + 1)
                or resolves_to_flag(node.right, consts, depth + 1))
    return False


def check_spawns():
    """B - subprocess call sites whose creationflags do not resolve to the flag."""
    misses = []
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for py in sorted(base.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
            except (OSError, SyntaxError):
                continue
            consts = _module_consts(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                if not (isinstance(f, ast.Attribute) and f.attr in SPAWN_FUNCS
                        and isinstance(f.value, ast.Name)
                        and f.value.id == "subprocess"):
                    continue
                flags = next((k.value for k in node.keywords
                              if k.arg == "creationflags"), None)
                if flags is not None and resolves_to_flag(flags, consts):
                    continue
                misses.append(f"{py.relative_to(ROOT).as_posix()}:{node.lineno}")
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
    total, risky, expected = check_tasks()
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
        note = f", {len(expected)} expected-interactive" if expected else ""
        print(f"- tasks: clean ({total} non-Microsoft, no unexpected window-capable{note})")

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
