"""Every subprocess spawn in tools/ and ops/ must resolve CREATE_NO_WINDOW.

Under a pythonw.exe parent a console child allocates its OWN window, so a spawn
without the flag flashes a console on the operator's desktop. `tools/
lw_window_guard.py` has checked this since the guard was written, but two ways:

  DISCOVERY - it rglobs tools/ + ops/, so no file can hide from it. Kept.
  VALUE     - `if "creationflags" in call or "CREATE_NO_WINDOW" in call`. That
              is a SUBSTRING test standing in for a value check, and it passes
              on `creationflags=0`, on a comment mentioning the word, and on
              `getattr(subprocess, "CREATE_NO_WINDW", 0)` - a typo that returns
              0, spawns fine, and flashes anyway. Silent fail-open. Replaced
              here by an AST resolver that follows the argument to a value.

Second reason this file exists at all: the guard is a SESSION-START HOOK, so it
only ever runs on the machine that would show the flash. In CI it does not run.
A check that only executes in the environment that created the state cannot
catch a regression pushed from anywhere else. Riot Commander found the same two
shapes in its own copy (RC 2026-07-27); this is LW's half.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load_guard():
    """Import the HOOK's own resolver rather than reimplementing it here.

    Two copies would drift, and a drifted guard-checker that agrees with
    nothing is worse than none: CI would go green on a resolver the session
    hook does not use. The hook is the shipping artifact; this file tests it.
    """
    spec = importlib.util.spec_from_file_location(
        "lw_window_guard_under_test", ROOT / "tools" / "lw_window_guard.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


guard = _load_guard()
SCAN_DIRS = guard.SCAN_DIRS
SPAWN_FUNCS = guard.SPAWN_FUNCS
FLAG_NAME = guard.FLAG_NAME
FLAG_VALUE = guard.FLAG_VALUE
_module_consts = guard._module_consts
resolves_to_flag = guard.resolves_to_flag


def _spawn_sites():
    """(path, lineno, creationflags-node-or-None) for every subprocess spawn."""
    sites = []
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for py in sorted(base.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:  # a syntax error is py_compile's job, not ours
                continue
            consts = _module_consts(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                is_spawn = (isinstance(f, ast.Attribute) and f.attr in SPAWN_FUNCS
                            and isinstance(f.value, ast.Name)
                            and f.value.id == "subprocess")
                if not is_spawn:
                    continue
                flags = next((k.value for k in node.keywords
                              if k.arg == "creationflags"), None)
                sites.append((py.relative_to(ROOT).as_posix(),
                              node.lineno, flags, consts))
    return sites


def test_there_are_spawn_sites_to_check():
    """Guard the guard: an empty sweep must not read as a pass."""
    assert len(_spawn_sites()) >= 5


@pytest.mark.parametrize("path,lineno,flags,consts",
                         _spawn_sites(),
                         ids=lambda v: str(v) if isinstance(v, (str, int)) else "")
def test_spawn_site_sets_create_no_window(path, lineno, flags, consts):
    assert flags is not None, (
        f"{path}:{lineno} spawns a subprocess with no creationflags - under "
        f"pythonw.exe this flashes a console window on the operator's desktop")
    assert resolves_to_flag(flags, consts), (
        f"{path}:{lineno} passes creationflags but it does not resolve to "
        f"{FLAG_NAME}. A typo'd getattr returns 0, spawns fine, and flashes "
        f"anyway - which is why the substring check could not see this.")


# ---- teeth, proved by mutation rather than asserted -------------------------

@pytest.mark.parametrize("src,expected", [
    ('subprocess.run(["x"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))', True),
    ('subprocess.run(["x"], creationflags=subprocess.CREATE_NO_WINDOW)', True),
    ('subprocess.run(["x"], creationflags=0x08000000)', True),
    # the motivating silent fail-open: returns 0, spawns, flashes
    ('subprocess.run(["x"], creationflags=getattr(subprocess, "CREATE_NO_WINDW", 0))', False),
    ('subprocess.run(["x"], creationflags=0)', False),
    ('subprocess.run(["x"], creationflags=subprocess.CREATE_NEW_CONSOLE)', False),
])
def test_resolver_rejects_what_the_substring_check_accepted(src, expected):
    tree = ast.parse(src)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == "run")
    flags = next(k.value for k in call.keywords if k.arg == "creationflags")
    assert resolves_to_flag(flags, {}) is expected


@pytest.mark.parametrize("src,expected", [
    ('NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)', True),
    ('NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0', True),
    ('NO_WINDOW = 0 if sys.platform == "win32" else 0', False),
])
def test_resolver_follows_module_level_constants(src, expected):
    tree = ast.parse(src + '\nsubprocess.run(["x"], creationflags=NO_WINDOW)\n')
    consts = _module_consts(tree)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == "run")
    flags = next(k.value for k in call.keywords if k.arg == "creationflags")
    assert resolves_to_flag(flags, consts) is expected
