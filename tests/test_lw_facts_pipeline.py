# arch: tests for the lw_facts.py pipeline digest section | section=tests | frozen=no
"""Tests for the pipeline section of tools/lw_facts.py.

The session-start digest gains a "## Pipeline" section: per-stage counts
under images/, loose files in 0.Originals awaiting intake, needs-attention
count from ops/runtime/pipeline_state.json, and the PIPELINE_LOG.md last
line. Everything is probed against an injectable root so these tests run
entirely inside tmp_path - the real images/ tree is NEVER touched.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from tools import lw_facts  # noqa: E402

STAGES = (
    "0.Originals",
    "1.First Pass Scratch",
    "2.First Pass Done",
    "3.Cleaning Scratch",
    "4.Cleaning Done",
    "5.Final Scratch",
    "6.Final Done",
    "7.Last Scratch",
    "8.End Review",
    "9.Image Backup",
)


def _make_tree(root: Path) -> Path:
    """Empty stage skeleton (mirrors the .gitkeep layout of the real tree)."""
    images = root / "images"
    for stage in STAGES:
        d = images / stage
        d.mkdir(parents=True)
        (d / ".gitkeep").write_text("", encoding="ascii")
    ref = images / "reference_pictures"
    ref.mkdir()
    (ref / ".gitkeep").write_text("", encoding="ascii")
    return images


def _text(lines: list[str]) -> str:
    return "\n".join(lines)


# -- idle / degraded paths -------------------------------------------------

def test_idle_when_images_missing(tmp_path):
    lines = lw_facts._pipeline_lines([], root=tmp_path)
    assert "pipeline idle" in _text(lines)


def test_idle_when_tree_empty(tmp_path):
    _make_tree(tmp_path)
    lines = lw_facts._pipeline_lines([], root=tmp_path)
    assert "pipeline idle" in _text(lines)


def test_never_raises_when_images_is_a_file(tmp_path):
    (tmp_path / "images").write_text("not a dir", encoding="ascii")
    anomalies: list[str] = []
    lines = lw_facts._pipeline_lines(anomalies, root=tmp_path)
    assert lines  # degraded, but produced output without raising


# -- counts ------------------------------------------------------------------

def test_awaiting_intake_counts_loose_files_not_gitkeep(tmp_path):
    images = _make_tree(tmp_path)
    for name in ("a.jpg", "b.png", "c.webp"):
        (images / "0.Originals" / name).write_bytes(b"x")
    lines = lw_facts._pipeline_lines([], root=tmp_path)
    text = _text(lines)
    assert "3" in text
    assert "awaiting intake" in text


def test_stage_folder_counts_are_per_image_subfolders(tmp_path):
    images = _make_tree(tmp_path)
    (images / "1.First Pass Scratch" / "ahri-star").mkdir()
    (images / "1.First Pass Scratch" / "jinx-arcane").mkdir()
    (images / "4.Cleaning Done" / "ahri-star").mkdir()
    lines = lw_facts._pipeline_lines([], root=tmp_path)
    text = _text(lines)
    assert "1.First Pass Scratch=2" in text
    assert "4.Cleaning Done=1" in text
    assert "pipeline idle" not in text


def test_reference_pictures_file_count(tmp_path):
    images = _make_tree(tmp_path)
    for i in range(4):
        (images / "reference_pictures" / f"ref{i}.png").write_bytes(b"x")
    lines = lw_facts._pipeline_lines([], root=tmp_path)
    assert "reference_pictures" in _text(lines)
    assert "4" in _text(lines)


# -- pipeline_state.json -----------------------------------------------------

def test_needs_attention_from_state_counts(tmp_path):
    _make_tree(tmp_path)
    state_dir = tmp_path / "ops" / "runtime"
    state_dir.mkdir(parents=True)
    (state_dir / "pipeline_state.json").write_text(
        json.dumps({"schema": 1, "counts": {"anomalies": 2}, "anomalies": [{}, {}]}),
        encoding="ascii",
    )
    anomalies: list[str] = []
    lines = lw_facts._pipeline_lines(anomalies, root=tmp_path)
    assert "needs_attention=2" in _text(lines)
    assert any("pipeline" in a for a in anomalies)


def test_state_zero_anomalies_is_quiet(tmp_path):
    _make_tree(tmp_path)
    state_dir = tmp_path / "ops" / "runtime"
    state_dir.mkdir(parents=True)
    (state_dir / "pipeline_state.json").write_text(
        json.dumps({"schema": 1, "counts": {"anomalies": 0}, "anomalies": []}),
        encoding="ascii",
    )
    anomalies: list[str] = []
    lines = lw_facts._pipeline_lines(anomalies, root=tmp_path)
    assert "needs_attention=0" in _text(lines)
    assert anomalies == []


def test_state_absent_is_tolerated(tmp_path):
    _make_tree(tmp_path)
    anomalies: list[str] = []
    lines = lw_facts._pipeline_lines(anomalies, root=tmp_path)
    assert lines
    assert anomalies == []


def test_state_malformed_degrades_without_raising(tmp_path):
    _make_tree(tmp_path)
    state_dir = tmp_path / "ops" / "runtime"
    state_dir.mkdir(parents=True)
    (state_dir / "pipeline_state.json").write_text("{not json", encoding="ascii")
    anomalies: list[str] = []
    lines = lw_facts._pipeline_lines(anomalies, root=tmp_path)
    assert lines  # no exception escaped
    assert any("pipeline_state" in a for a in anomalies)


# -- PIPELINE_LOG.md ----------------------------------------------------------

def test_log_last_line_reported(tmp_path):
    _make_tree(tmp_path)
    (tmp_path / "PIPELINE_LOG.md").write_text(
        "# header\n\nfirst | INTAKE | ok\nlast | APPROVE_FIRST | ok\n\n",
        encoding="ascii",
    )
    lines = lw_facts._pipeline_lines([], root=tmp_path)
    assert "last | APPROVE_FIRST | ok" in _text(lines)


def test_log_absent_is_tolerated(tmp_path):
    _make_tree(tmp_path)
    anomalies: list[str] = []
    lines = lw_facts._pipeline_lines(anomalies, root=tmp_path)
    assert lines
    assert anomalies == []


# -- main() wiring -------------------------------------------------------------

def test_main_emits_pipeline_section(tmp_path, monkeypatch, capsys):
    _make_tree(tmp_path)
    monkeypatch.setattr(lw_facts, "_ROOT", tmp_path)
    monkeypatch.setattr(lw_facts, "_HEALTH", tmp_path / "ops" / "runtime" / "health.json")
    monkeypatch.setattr(lw_facts, "_WAKEUP", tmp_path / "WAKEUP_NOTES.md")
    rc = lw_facts.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "## Pipeline" in out
