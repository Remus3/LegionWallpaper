"""Contract tests for the per-stage pipeline commands (.claude/commands/*.md).

Build-wave deliverable (2026-07-03): one command per pipeline stage so the
operator can quickly express which stage to start with. Each command must:
  - exist and be 7-bit ASCII (CLAUDE.md hard rule),
  - carry YAML frontmatter with a description,
  - carry the SUBAGENT-FIRST standing-protocol blockquote,
  - open with a preflight that runs `tools/lw_pipeline.py status` and reads
    the PIPELINE_LOG.md tail,
  - degrade gracefully when ML tooling is absent by pointing at the
    docs/RESTORATION_PLAN.md install checklist,
  - end with a log/state update plus a tight banner.

These are authored-markdown contract locks, not behavior tests - the
commands are operator playbooks, so the testable surface is the presence
of the binding sections.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CMD_DIR = _REPO_ROOT / ".claude" / "commands"

STAGE_COMMANDS = [
    "intake",
    "first-pass",
    "cleaning-pass",
    "final-pass",
    "last-pass",
    "end-review",
    "pipeline-status",
]


def _path(name: str) -> Path:
    return _CMD_DIR / f"{name}.md"


@pytest.mark.parametrize("name", STAGE_COMMANDS)
def test_command_exists(name: str) -> None:
    p = _path(name)
    assert p.is_file(), f"missing stage command: {p}"


@pytest.mark.parametrize("name", STAGE_COMMANDS)
def test_command_is_ascii(name: str) -> None:
    p = _path(name)
    if not p.is_file():
        pytest.skip("existence covered by test_command_exists")
    raw = p.read_bytes()
    non_ascii = [(i, b) for i, b in enumerate(raw) if b > 127]
    assert not non_ascii, (
        f"{p.name} has {len(non_ascii)} non-ASCII bytes; "
        f"first at offset {non_ascii[0][0]}"
    )


@pytest.mark.parametrize("name", STAGE_COMMANDS)
def test_command_frontmatter(name: str) -> None:
    p = _path(name)
    if not p.is_file():
        pytest.skip("existence covered by test_command_exists")
    text = p.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{p.name}: missing YAML frontmatter"
    assert "description:" in text.split("---", 2)[1], (
        f"{p.name}: frontmatter has no description"
    )


@pytest.mark.parametrize("name", STAGE_COMMANDS)
def test_command_subagent_first_block(name: str) -> None:
    p = _path(name)
    if not p.is_file():
        pytest.skip("existence covered by test_command_exists")
    text = p.read_text(encoding="utf-8")
    assert "SUBAGENT-FIRST" in text, (
        f"{p.name}: missing the SUBAGENT-FIRST standing-protocol block"
    )


@pytest.mark.parametrize("name", STAGE_COMMANDS)
def test_command_preflight(name: str) -> None:
    p = _path(name)
    if not p.is_file():
        pytest.skip("existence covered by test_command_exists")
    text = p.read_text(encoding="utf-8")
    assert "tools/lw_pipeline.py status" in text, (
        f"{p.name}: preflight must run tools/lw_pipeline.py status"
    )
    assert "PIPELINE_LOG.md" in text, (
        f"{p.name}: preflight must read the PIPELINE_LOG.md tail"
    )


@pytest.mark.parametrize("name", STAGE_COMMANDS)
def test_command_graceful_degrade_pointer(name: str) -> None:
    p = _path(name)
    if not p.is_file():
        pytest.skip("existence covered by test_command_exists")
    text = p.read_text(encoding="utf-8")
    assert "RESTORATION_PLAN.md" in text, (
        f"{p.name}: must point missing-tool degradation at the "
        f"docs/RESTORATION_PLAN.md install checklist"
    )


@pytest.mark.parametrize("name", STAGE_COMMANDS)
def test_command_ends_with_banner_section(name: str) -> None:
    p = _path(name)
    if not p.is_file():
        pytest.skip("existence covered by test_command_exists")
    text = p.read_text(encoding="utf-8").lower()
    assert "banner" in text, f"{p.name}: missing the closing banner section"
