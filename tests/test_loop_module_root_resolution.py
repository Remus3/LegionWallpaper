r"""Config-supplied paths are adopted only when absolute ON THIS PLATFORM.

`Path("C:\LegionWallpaper").is_absolute()` is True on Windows and False on
POSIX, where the whole thing is one relative component whose NAME contains
backslashes. loop_controller does `CTL.mkdir(parents=True, exist_ok=True)` at
IMPORT time, so adopting such a value on Linux mints a literal
`C:\LegionWallpaper\ops\loop\control` directory inside whatever CWD imported it.

This was not reachable while the config path itself was a hardcoded absolute:
the read failed off Legion, CFG was {}, and the module-relative defaults always
applied. Making the config load everywhere (da598c1) is what exposed it - a
second-order effect of that fix, which is the kind a fix is least likely to be
tested for. RC flagged the same is_absolute() rule from their side.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CONTROLLER = ROOT / "ops" / "loop" / "loop_controller.py"
LOOP_MODULES = ("loop_controller.py", "done_sentinel.py", "claude_stub.py")


def _cfg_path_impl():
    """Load just the helper - importing the module runs an mkdir and a controller."""
    src = CONTROLLER.read_text(encoding="utf-8")
    start = src.index("def _cfg_path(")
    end = src.index("\nROOT = ", start)
    ns = {"Path": Path, "CFG": {}}
    exec(compile(src[start:end], "_cfg_path", "exec"), ns)  # noqa: S102 - own source
    return ns


def test_a_windows_style_path_is_rejected_when_it_is_not_absolute_here():
    ns = _cfg_path_impl()
    ns["CFG"] = {"control_dir": r"C:\LegionWallpaper\ops\loop\control"}
    got = ns["_cfg_path"]("control_dir", Path("fallback"))
    if Path(r"C:\LegionWallpaper").is_absolute():      # Windows
        assert got == Path(r"C:\LegionWallpaper\ops\loop\control")
    else:                                              # POSIX
        assert got == Path("fallback"), (
            "a drive-letter string is RELATIVE here - adopting it would mkdir a "
            "directory literally named C:\\LegionWallpaper\\...")


def test_a_relative_value_is_rejected_on_every_platform():
    """The rejection branch, provable from Windows. The test above can only
    exercise whichever side of is_absolute() the host platform gives it, so on
    Legion it proves the ADOPT path and nothing else - and the branch that
    matters off Legion would go unexercised on the only machine anyone runs."""
    ns = _cfg_path_impl()
    for rel in ("ops/loop/control", "control", "./control", ""):
        ns["CFG"] = {"control_dir": rel}
        assert ns["_cfg_path"]("control_dir", Path("fallback")) == Path("fallback"), \
            f"{rel!r} is not absolute and must not be adopted"


def test_an_absent_or_empty_value_falls_back():
    ns = _cfg_path_impl()
    for cfg in ({}, {"control_dir": ""}, {"control_dir": None}):
        ns["CFG"] = cfg
        assert ns["_cfg_path"]("control_dir", Path("fallback")) == Path("fallback")


def test_a_genuinely_absolute_value_is_honoured():
    """The override has to keep working - config.json points the loop at a real
    control dir and a launch must be able to redirect it."""
    ns = _cfg_path_impl()
    here = ROOT / "ops" / "loop" / "control"
    ns["CFG"] = {"control_dir": str(here)}
    assert ns["_cfg_path"]("control_dir", Path("fallback")) == here


@pytest.mark.parametrize("mod", LOOP_MODULES)
def test_every_loop_module_derives_its_root_rather_than_naming_one(mod):
    """The hardcoded root was a CLASS. This is the machine-checked version of
    the sweep, so the next one cannot be a one-line fix that misses siblings."""
    src = (ROOT / "ops" / "loop" / mod).read_text(encoding="utf-8")
    assert re.search(r"^ROOT\s*=\s*(Path\(__file__\)|_cfg_path\()", src, re.M), (
        f"{mod} must derive ROOT from __file__ (optionally via _cfg_path), "
        f"not name an absolute path only one machine has")
