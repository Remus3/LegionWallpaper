# arch: desktop wallpaper deck rotator | section=tools | frozen=no
"""lw_wallpaper_rotate.py - show every wallpaper exactly once before any repeat.

Design contract: docs/superpowers/specs/2026-07-18-wallpaper-deck-rotator-design.md

The Windows 10 built-in slideshow keeps no deck and no cursor (LastTickLow /
LastTickHigh pinned at 0), so "Shuffle" is memoryless sampling with
replacement and it re-seeds on wake, logon and Explorer restart. This tool
replaces it with a deck: shuffle the corpus into one permutation, walk it to
the end, then reshuffle. The permutation and the cursor are persisted, so the
once-per-cycle guarantee survives the exact events that reset the built-in
shuffle.

Four boundaries, only one of which touches Windows:
  - deck logic   pure functions over plain lists (new_cycle_deck /
                 reconcile_deck / advance). No filesystem, no ctypes - which
                 is what makes the guarantee provable in a test.
  - state io     load_state / save_state, atomic per the CLAUDE.md hard rule.
  - win32 shim   set_wallpaper, SPI_SETDESKWALLPAPER via ctypes. Mocked in
                 tests; the one unit a test cannot cover.
  - cli          argument parsing and command dispatch.

Usage:
  lw_wallpaper_rotate.py tick [--dry-run]   advance one image
  lw_wallpaper_rotate.py status             cycle, position, remaining, next few
  lw_wallpaper_rotate.py reshuffle          force a new cycle now
  lw_wallpaper_rotate.py install            register the LW-Wallpaper task
  lw_wallpaper_rotate.py uninstall          remove the LW-Wallpaper task
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import random
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "tools" / "lw_wallpaper_config.json"
LOG_DIR = ROOT / "logs"  # module-level so tests can redirect it
TASK_NAME = "LW-Wallpaper"
STATE_VERSION = 1

# Legion focus-steal rule: every subprocess authored in this repo passes
# creationflags=CREATE_NO_WINDOW, or a console flashes every interval.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

SPI_SETDESKWALLPAPER = 0x0014
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDWININICHANGE = 0x02

DEFAULT_CONFIG = {
    "source_dir": "C:\\Users\\Administrator\\Pictures",
    "interval_minutes": 3,
    "state_path": "ops/runtime/wallpaper_deck.json",
    "extensions": [".jpg", ".jpeg", ".png", ".bmp"],
}


def _log(msg: str) -> None:
    """Append one line to logs/YYYY-MM-DD.log. Never raises.

    Raw API error strings live here and nowhere else (CLAUDE.md error-handling
    rule); user-facing output stays friendly.
    """
    try:
        stamp = datetime.now()
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_DIR / f"{stamp:%Y-%m-%d}.log", "a", encoding="utf-8") as fo:
            fo.write(f"{stamp:%H:%M:%S} [lw_wallpaper_rotate] {msg}\n")
    except OSError:
        pass


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _rng(rng):
    """Default to the module-level random; tests inject a seeded Random."""
    return rng if rng is not None else random


# --------------------------------------------------------------- deck logic
# Pure: plain lists in, plain lists out. No filesystem, no ctypes, no clock.

def new_cycle_deck(present, last_shown=None, rng=None) -> list:
    """Shuffle `present` into a fresh cycle, avoiding a back-to-back repeat.

    Step 3 of the tick algorithm. Without the seam swap the last image of
    cycle N can be the first image of cycle N+1 - a visible repeat, which is
    exactly the complaint this tool exists to fix. A single-image corpus skips
    the swap entirely (there is no other index to swap with), so the seam
    never loops.
    """
    rng = _rng(rng)
    deck = list(present)
    rng.shuffle(deck)
    if last_shown is not None and len(deck) > 1 and deck[0] == last_shown:
        other = rng.randrange(1, len(deck))
        deck[0], deck[other] = deck[other], deck[0]
    return deck


def reconcile_deck(deck, cursor, present, rng=None) -> list:
    """Fold filesystem changes into the current cycle (step 2).

    Deleted files vanish from the owed tail; new files are spliced into the
    owed tail at random positions so pipeline output joins the current cycle
    instead of waiting for the next one. deck[:cursor] is never touched -
    history is history, and keeping it means the cursor stays valid.
    """
    rng = _rng(rng)
    cursor = max(0, min(int(cursor), len(deck)))
    present_set = set(present)
    shown = list(deck[:cursor])
    owed = [name for name in deck[cursor:] if name in present_set]
    known = set(deck)
    for name in present:
        if name not in known:
            owed.insert(rng.randrange(0, len(owed) + 1), name)
    return shown + owed


def advance(deck, cursor, present, last_shown=None, rng=None):
    """Steps 2-4: reconcile, roll the cycle if exhausted, take one pick.

    Returns (deck, cursor, pick, started_new_cycle). The cursor comes back
    already advanced past the pick, so the caller only has to persist it.
    """
    rng = _rng(rng)
    if not present:
        return list(deck), cursor, None, False
    # Reconcile only an in-progress cycle. A fresh or exhausted deck falls
    # through to the reshuffle below, so the first-ever tick opens cycle 1
    # instead of being silently built by the splice.
    if deck and cursor < len(deck):
        deck = reconcile_deck(deck, cursor, present, rng=rng)
    started_new = False
    if not deck or cursor >= len(deck):
        deck = new_cycle_deck(present, last_shown=last_shown, rng=rng)
        cursor = 0
        started_new = True
    return deck, cursor + 1, deck[cursor], started_new


# ----------------------------------------------------------------- state io

def default_state(source_dir: str) -> dict:
    return {
        "version": STATE_VERSION,
        "source_dir": str(source_dir),
        "deck": [],
        "cursor": 0,
        "cycle": 0,
        "last_shown": None,
        "cycle_started_utc": None,
        "last_tick_utc": None,
    }


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def load_state(path, source_dir: str = "") -> dict:
    """Read the deck state. Missing or corrupt state rebuilds - never raises.

    A rotator must not wedge the desktop over a bad JSON file, so every
    failure mode here degrades to a fresh deck and a log line.
    """
    fresh = default_state(source_dir)
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return fresh
    try:
        data = json.loads(raw)
    except ValueError:
        _log(f"state file unreadable ({path}) - rebuilding a fresh deck")
        return fresh
    if not isinstance(data, dict) or data.get("version") != STATE_VERSION:
        _log(f"state file shape or version unusable ({path}) - rebuilding a fresh deck")
        return fresh
    deck = data.get("deck")
    cursor = data.get("cursor")
    if not isinstance(deck, list) or not all(isinstance(name, str) for name in deck):
        _log(f"state deck is not a list of names ({path}) - rebuilding a fresh deck")
        return fresh
    if not _is_int(cursor) or not 0 <= cursor <= len(deck):
        _log(f"state cursor out of range ({path}) - rebuilding a fresh deck")
        return fresh

    state = dict(fresh)
    state["source_dir"] = data.get("source_dir") or str(source_dir)
    state["deck"] = list(deck)
    state["cursor"] = cursor
    cycle = data.get("cycle")
    state["cycle"] = cycle if _is_int(cycle) and cycle >= 0 else 0
    last_shown = data.get("last_shown")
    state["last_shown"] = last_shown if isinstance(last_shown, str) else None
    for key in ("cycle_started_utc", "last_tick_utc"):
        value = data.get(key)
        state[key] = value if isinstance(value, str) else None
    return state


def save_state(path, state) -> None:
    """Atomic write (CLAUDE.md hard rule): serialize, write tmp, replace.

    A tick can land while another reader is mid-read, so the target is only
    ever swapped in whole. Serializing first means a bad state object never
    creates a tmp file at all, and a failed replace cleans its tmp up.
    """
    path = Path(path)
    payload = json.dumps(state, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ------------------------------------------------------------------- config

def load_config(path=None) -> dict:
    """Config with defaults filled in and state_path resolved to absolute."""
    path = Path(path) if path else CONFIG_PATH
    cfg = dict(DEFAULT_CONFIG)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _log(f"config unreadable ({path}) - using defaults: {type(exc).__name__}")
        data = {}
    if isinstance(data, dict):
        for key in DEFAULT_CONFIG:
            if data.get(key) is not None:
                cfg[key] = data[key]
    state_path = Path(str(cfg["state_path"]))
    if not state_path.is_absolute():
        state_path = ROOT / state_path
    cfg["state_path"] = str(state_path)
    try:
        cfg["interval_minutes"] = max(1, int(cfg["interval_minutes"]))
    except (TypeError, ValueError):
        cfg["interval_minutes"] = DEFAULT_CONFIG["interval_minutes"]
    return cfg


def scan_source(source_dir, extensions) -> list:
    """Image filenames directly under source_dir, sorted. Never raises."""
    wanted = {str(e).lower() if str(e).startswith(".") else "." + str(e).lower()
              for e in extensions}
    try:
        entries = list(Path(source_dir).iterdir())
    except OSError:
        return []
    return sorted(p.name for p in entries if p.is_file() and p.suffix.lower() in wanted)


# ---------------------------------------------------------------- win32 shim

def set_wallpaper(path) -> bool:
    """Set the desktop wallpaper. True on success.

    Setting a concrete file drops Windows out of slideshow mode into
    single-image mode, which is what stops the built-in slideshow from
    fighting the rotator. This is the only unit that talks to Windows;
    tests inject a stand-in. Documented escalation if Windows ever reasserts
    slideshow mode: IDesktopWallpaper::SetWallpaper (CLSID_DesktopWallpaper).
    """
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SystemParametersInfoW.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint,
        ]
        user32.SystemParametersInfoW.restype = ctypes.c_int
        ok = user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER, 0, str(path),
            SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE,
        )
        if not ok:
            _log(f"SystemParametersInfoW failed for {path}: "
                 f"GetLastError={ctypes.get_last_error()}")
            return False
        return True
    except Exception as exc:  # noqa: BLE001 - a tick must never crash the scheduled task
        _log(f"set_wallpaper crashed for {path}: {type(exc).__name__}: {exc}")
        return False


# --------------------------------------------------------------- commands

def tick(config, dry_run: bool = False, rng=None, set_wallpaper_fn=None):
    """Advance one image. Returns (exit_code, pick_or_None)."""
    source_dir = Path(str(config.get("source_dir") or DEFAULT_CONFIG["source_dir"]))
    state_path = Path(str(config.get("state_path") or DEFAULT_CONFIG["state_path"]))
    extensions = config.get("extensions") or DEFAULT_CONFIG["extensions"]

    if not source_dir.is_dir():
        _log(f"source directory missing: {source_dir}")
        print(f"tick: source directory not found - {source_dir}", file=sys.stderr)
        return 2, None

    present = scan_source(source_dir, extensions)
    if not present:
        _log(f"source directory empty: {source_dir} - nothing to show")
        return 0, None

    state = load_state(state_path, source_dir=str(source_dir))
    # Deck entries are relative to source_dir, so a moved corpus keeps its deck.
    state["source_dir"] = str(source_dir)
    deck, cursor, pick, started_new = advance(
        state["deck"], state["cursor"], present,
        last_shown=state.get("last_shown"), rng=rng,
    )
    if pick is None:
        return 0, None
    if dry_run:
        return 0, pick

    show = set_wallpaper_fn or set_wallpaper
    if not show(str(source_dir / pick)):
        # Not shown, so still owed: the cursor does not move and nothing is written.
        _log(f"wallpaper not applied - {pick} stays owed")
        print("tick: could not apply the wallpaper (see logs) - image stays owed",
              file=sys.stderr)
        return 1, pick

    now = _utc_now()
    state["deck"] = deck
    state["cursor"] = cursor
    state["last_shown"] = pick
    state["last_tick_utc"] = now
    if started_new:
        state["cycle"] = int(state.get("cycle") or 0) + 1
        state["cycle_started_utc"] = now
    try:
        save_state(state_path, state)
    except OSError as exc:
        _log(f"state save failed ({state_path}): {type(exc).__name__}: {exc}")
        print("tick: image set, but the deck state could not be saved (see logs)",
              file=sys.stderr)
        return 1, pick
    return 0, pick


def status(config) -> list:
    """Human-readable deck status lines."""
    source_dir = Path(str(config.get("source_dir") or DEFAULT_CONFIG["source_dir"]))
    state_path = Path(str(config.get("state_path") or DEFAULT_CONFIG["state_path"]))
    extensions = config.get("extensions") or DEFAULT_CONFIG["extensions"]
    state = load_state(state_path, source_dir=str(source_dir))
    deck = state["deck"]
    cursor = state["cursor"]
    remaining = max(0, len(deck) - cursor)
    upcoming = deck[cursor:cursor + 5]
    return [
        f"{TASK_NAME}: cycle={state['cycle']} position={cursor}/{len(deck)} "
        f"remaining={remaining}",
        f"source_dir={source_dir} present={len(scan_source(source_dir, extensions))}",
        f"last_shown={state['last_shown']} last_tick_utc={state['last_tick_utc']}",
        "next: " + (", ".join(upcoming) if upcoming else "(new cycle on the next tick)"),
    ]


def reshuffle(config, rng=None) -> int:
    """Force a new cycle now. Does not set a wallpaper - the next tick does."""
    source_dir = Path(str(config.get("source_dir") or DEFAULT_CONFIG["source_dir"]))
    state_path = Path(str(config.get("state_path") or DEFAULT_CONFIG["state_path"]))
    extensions = config.get("extensions") or DEFAULT_CONFIG["extensions"]
    if not source_dir.is_dir():
        _log(f"source directory missing: {source_dir}")
        print(f"reshuffle: source directory not found - {source_dir}", file=sys.stderr)
        return 2
    present = scan_source(source_dir, extensions)
    if not present:
        _log(f"source directory empty: {source_dir} - nothing to reshuffle")
        print("reshuffle: no images found - nothing to do")
        return 0
    state = load_state(state_path, source_dir=str(source_dir))
    state["source_dir"] = str(source_dir)
    state["deck"] = new_cycle_deck(present, last_shown=state.get("last_shown"), rng=rng)
    state["cursor"] = 0
    state["cycle"] = int(state.get("cycle") or 0) + 1
    state["cycle_started_utc"] = _utc_now()
    try:
        save_state(state_path, state)
    except OSError as exc:
        _log(f"state save failed ({state_path}): {type(exc).__name__}: {exc}")
        print("reshuffle: could not save the deck state (see logs)", file=sys.stderr)
        return 1
    print(f"reshuffle: cycle {state['cycle']} over {len(state['deck'])} images")
    return 0


# -------------------------------------------------------------- scheduling

def _pythonw() -> str:
    """pythonw.exe next to the running interpreter - no console flash per tick."""
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")
    return str(windowless if windowless.exists() else exe)


def _task_user_id() -> str:
    user = os.environ.get("USERNAME") or ""
    domain = os.environ.get("USERDOMAIN") or ""
    if domain and user:
        return domain + "\\" + user
    return user


def task_xml(interval_minutes: int, start_boundary: str = "") -> str:
    """Task Scheduler XML: at logon, repeating every interval_minutes forever.

    XML rather than plain schtasks flags because schtasks rejects /RI for an
    ONLOGON schedule, and the Task Scheduler UI only offers preset repetition
    intervals - an arbitrary 3 minute repeat has to be set programmatically.
    """
    # A LogonTrigger's Repetition only starts when that trigger fires, so a
    # logon-only task sits idle until the next logon. The TimeTrigger below
    # starts the repeat at install time; the LogonTrigger keeps it alive
    # across reboots. Local time, not UTC - schtasks reads it as local.
    boundary = start_boundary or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    script = str(Path(__file__).resolve())
    command = _xml_escape(_pythonw())
    arguments = _xml_escape(f'"{script}" tick')
    workdir = _xml_escape(str(ROOT))
    user_id = _task_user_id()
    principals = ""
    if user_id:
        principals = (
            "  <Principals>\n"
            '    <Principal id="Author">\n'
            f"      <UserId>{_xml_escape(user_id)}</UserId>\n"
            "      <LogonType>InteractiveToken</LogonType>\n"
            "      <RunLevel>LeastPrivilege</RunLevel>\n"
            "    </Principal>\n"
            "  </Principals>\n"
        )
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.2" '
        'xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        "  <RegistrationInfo>\n"
        f"    <Description>Legion Wallpaper deck rotator - one image per tick, "
        f"every image once per cycle.</Description>\n"
        "  </RegistrationInfo>\n"
        "  <Triggers>\n"
        "    <LogonTrigger>\n"
        "      <Enabled>true</Enabled>\n"
        "      <Repetition>\n"
        f"        <Interval>PT{int(interval_minutes)}M</Interval>\n"
        "        <StopAtDurationEnd>false</StopAtDurationEnd>\n"
        "      </Repetition>\n"
        "    </LogonTrigger>\n"
        "    <TimeTrigger>\n"
        "      <Enabled>true</Enabled>\n"
        f"      <StartBoundary>{_xml_escape(boundary)}</StartBoundary>\n"
        "      <Repetition>\n"
        f"        <Interval>PT{int(interval_minutes)}M</Interval>\n"
        "        <StopAtDurationEnd>false</StopAtDurationEnd>\n"
        "      </Repetition>\n"
        "    </TimeTrigger>\n"
        "  </Triggers>\n"
        + principals +
        "  <Settings>\n"
        "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
        "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n"
        "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n"
        "    <AllowHardTerminate>true</AllowHardTerminate>\n"
        "    <StartWhenAvailable>true</StartWhenAvailable>\n"
        "    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>\n"
        "    <IdleSettings>\n"
        "      <StopOnIdleEnd>false</StopOnIdleEnd>\n"
        "      <RestartOnIdle>false</RestartOnIdle>\n"
        "    </IdleSettings>\n"
        "    <AllowStartOnDemand>true</AllowStartOnDemand>\n"
        "    <Enabled>true</Enabled>\n"
        "    <Hidden>false</Hidden>\n"
        "    <RunOnlyIfIdle>false</RunOnlyIfIdle>\n"
        "    <WakeToRun>false</WakeToRun>\n"
        "    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>\n"
        "    <Priority>7</Priority>\n"
        "  </Settings>\n"
        '  <Actions Context="Author">\n'
        "    <Exec>\n"
        f"      <Command>{command}</Command>\n"
        f"      <Arguments>{arguments}</Arguments>\n"
        f"      <WorkingDirectory>{workdir}</WorkingDirectory>\n"
        "    </Exec>\n"
        "  </Actions>\n"
        "</Task>\n"
    )


def _schtasks(args, runner=None):
    run = runner or subprocess.run
    return run(
        ["schtasks"] + list(args),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=NO_WINDOW,
    )


def _apply_slideshow_registry(interval_minutes: int) -> None:
    """Clear the built-in slideshow so a stale theme cannot reassert it.

    WallpaperStyle is deliberately left alone: the rotator has no business
    changing how images are fitted.
    """
    import winreg  # Windows-only, imported lazily so the module loads anywhere

    key_path = "Control Panel\\Personalization\\Desktop Slideshow"
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_SET_VALUE) as handle:
        winreg.SetValueEx(handle, "Interval", 0, winreg.REG_DWORD,
                          int(interval_minutes) * 60000)
        winreg.SetValueEx(handle, "Shuffle", 0, winreg.REG_DWORD, 0)


def install(config, runner=None, registry_fn=None, xml_path=None) -> int:
    """Register the LW-Wallpaper scheduled task from a reviewable XML file."""
    interval = int(config.get("interval_minutes")
                   or DEFAULT_CONFIG["interval_minutes"])
    xml_path = Path(xml_path) if xml_path else ROOT / "ops" / "runtime" / "lw_wallpaper_task.xml"
    try:
        xml_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = xml_path.with_name(xml_path.name + ".tmp")
        # UTF-16 with a BOM: schtasks /XML rejects other encodings.
        tmp.write_text(task_xml(interval), encoding="utf-16")
        tmp.replace(xml_path)
    except OSError as exc:
        _log(f"task xml write failed ({xml_path}): {type(exc).__name__}: {exc}")
        print("install: could not write the task definition (see logs)", file=sys.stderr)
        return 1

    proc = _schtasks(["/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"],
                     runner=runner)
    if getattr(proc, "returncode", 1) != 0:
        _log(f"schtasks /Create failed rc={getattr(proc, 'returncode', '?')} "
             f"stdout={getattr(proc, 'stdout', '')!r} stderr={getattr(proc, 'stderr', '')!r}")
        print(f"install: could not register {TASK_NAME} (see logs)", file=sys.stderr)
        return 1

    apply_registry = registry_fn or _apply_slideshow_registry
    try:
        apply_registry(interval)
    except OSError as exc:
        # The task is registered and will run; the registry tidy-up is best effort.
        _log(f"slideshow registry tidy-up failed: {type(exc).__name__}: {exc}")
    print(f"install: registered {TASK_NAME} - every {interval} min, starting now "
          f"and again at every logon ({xml_path})")
    return 0


def uninstall(runner=None) -> int:
    """Remove the LW-Wallpaper scheduled task."""
    proc = _schtasks(["/Delete", "/TN", TASK_NAME, "/F"], runner=runner)
    if getattr(proc, "returncode", 1) != 0:
        _log(f"schtasks /Delete failed rc={getattr(proc, 'returncode', '?')} "
             f"stdout={getattr(proc, 'stdout', '')!r} stderr={getattr(proc, 'stderr', '')!r}")
        print(f"uninstall: could not remove {TASK_NAME} (see logs)", file=sys.stderr)
        return 1
    print(f"uninstall: removed {TASK_NAME}")
    return 0


# ----------------------------------------------------------------------- cli

def _add_config_arg(parser, default) -> None:
    parser.add_argument("--config", default=default,
                        help="path to lw_wallpaper_config.json")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="lw_wallpaper_rotate",
        description="wallpaper deck rotator - every image once before any repeat",
    )
    _add_config_arg(parser, str(CONFIG_PATH))
    sub = parser.add_subparsers(dest="cmd", required=True)
    tick_p = sub.add_parser("tick", help="advance one image")
    tick_p.add_argument("--dry-run", action="store_true",
                        help="report the pick and write nothing")
    status_p = sub.add_parser("status", help="cycle, position, remaining, next few")
    reshuffle_p = sub.add_parser("reshuffle", help="force a new cycle now")
    install_p = sub.add_parser("install", help=f"register the {TASK_NAME} scheduled task")
    uninstall_p = sub.add_parser("uninstall", help=f"remove the {TASK_NAME} scheduled task")
    # SUPPRESS on the subcommand copies so a --config given BEFORE the
    # subcommand is not overwritten by the subparser's own default.
    for subcommand in (tick_p, status_p, reshuffle_p, install_p, uninstall_p):
        _add_config_arg(subcommand, argparse.SUPPRESS)
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    if args.cmd == "tick":
        code, pick = tick(cfg, dry_run=args.dry_run)
        if pick is None:
            print("tick: no images to show" if code == 0
                  else "tick: no image was set (see logs)")
        else:
            print(f"tick: {'would set' if args.dry_run else 'set'} {pick}")
        return code
    if args.cmd == "status":
        for line in status(cfg):
            print(line)
        return 0
    if args.cmd == "reshuffle":
        return reshuffle(cfg)
    if args.cmd == "install":
        return install(cfg)
    return uninstall()


if __name__ == "__main__":
    sys.exit(main())
