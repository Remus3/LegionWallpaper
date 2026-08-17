"""The CI watchdog must not flash a console every time it ticks.

Measured 2026-08-17: LW-CIWatchdog was registered against `python.exe` with
`<Hidden>false</Hidden>` and an InteractiveToken principal, repeating every two
minutes, so a console window appeared and stole focus on the operator's desktop.
The module's own docstring promises the opposite ("Every subprocess sets
CREATE_NO_WINDOW: a console flashing on the operator's screen ..."), but that
care covered the CHILD processes only - the PARENT was launched with a console
by `install()`, which passes `sys.executable` straight through.

`RC-CIWatchdog` does the same job from `pythonw.exe` and never flashed, which
is what identified the difference.

Written test-first per CLAUDE.md TDD.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import ci_watchdog as cw  # noqa: E402


def test_windowless_maps_the_live_interpreter_to_pythonw():
    """The case that actually matters: this box's own python.exe.

    Asserted against sys.executable rather than a fabricated path, because the
    mapping is guarded on the sibling EXISTING - a made-up path would exercise
    the fallback and prove nothing about a real install.
    """
    live = Path(sys.executable)
    if live.name.lower() != "python.exe":
        return  # already windowless (or an embedded host); nothing to map
    if not live.with_name("pythonw.exe").is_file():
        return  # no sibling on this machine; the fallback tests cover it
    assert cw.windowless_python(sys.executable) == str(
        live.with_name("pythonw.exe"))


def test_windowless_leaves_pythonw_alone():
    exe = r"C:\Py\Python314\pythonw.exe"
    assert cw.windowless_python(exe) == exe


def test_windowless_is_a_noop_when_the_sibling_is_absent(tmp_path: Path):
    """Never point the task at an executable that does not exist."""
    exe = tmp_path / "python.exe"
    exe.write_text("")
    assert cw.windowless_python(str(exe)) == str(exe)


def test_windowless_uses_the_sibling_when_it_exists(tmp_path: Path):
    exe = tmp_path / "python.exe"
    exe.write_text("")
    (tmp_path / "pythonw.exe").write_text("")
    assert cw.windowless_python(str(exe)) == str(tmp_path / "pythonw.exe")


def test_task_xml_is_hidden():
    xml = cw.task_xml(r"C:\Py\pythonw.exe", r"C:\LW\tools\ci_watchdog.py")
    assert "<Hidden>true</Hidden>" in xml
    assert "<Hidden>false</Hidden>" not in xml


def test_task_xml_still_carries_the_repeat_and_the_script():
    xml = cw.task_xml(r"C:\Py\pythonw.exe", r"C:\LW\tools\ci_watchdog.py",
                      every_minutes=2)
    assert "PT2M" in xml
    assert "ci_watchdog.py" in xml
