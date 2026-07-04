"""CLI surface + scan/status/log/state contract tests for tools/lw_pipeline.py.

Spec: docs/research/PIPELINE_STATE_MACHINE.md sections 3 and 4.
Grammar edge cases live in test_lw_pipeline_grammar.py; transition and
safety behavior in test_lw_pipeline_moves.py.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_pipeline as lw  # noqa: E402

STAGE_FOLDERS = [
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
]


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "images"
    for name in STAGE_FOLDERS + ["reference_pictures"]:
        d = r / name
        d.mkdir(parents=True)
        (d / ".gitkeep").write_text("")
    return r


@pytest.fixture(autouse=True)
def _fast_gate(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(lw, "PROBE_SECONDS", 0.0)


def _drop(root: Path, name: str, content: bytes = b"fake-image-bytes") -> Path:
    p = root / "0.Originals" / name
    p.write_bytes(content)
    old = p.stat().st_mtime - 120
    os.utime(p, (old, old))
    return p


def run(root: Path, *args: str) -> int:
    return lw.main(["--root", str(root), *args])


def test_source_is_ascii():
    src = Path(__file__).resolve().parent.parent / "tools" / "lw_pipeline.py"
    raw = src.read_bytes()
    assert all(b <= 127 for b in raw), "lw_pipeline.py must be 7-bit ASCII"


def test_scan_empty_tree(root: Path):
    assert run(root, "scan") == 0
    state = json.loads(
        (root.parent / "ops" / "runtime" / "pipeline_state.json").read_text()
    )
    assert state["schema"] == 1
    assert state["counts"]["pending_intake"] == 0
    assert state["images"] == {}
    assert state["root"] == str(root)


def test_scan_tolerates_gitkeep_and_reference_pictures(root: Path):
    (root / "reference_pictures" / "42_cleanup.png").write_bytes(b"ref")
    assert run(root, "scan") == 0  # no anomalies from .gitkeep or references


def test_scan_counts_pending_intake(root: Path):
    _drop(root, "a.png")
    _drop(root, "b.jpg", b"other")
    assert run(root, "scan") == 0
    state = json.loads(
        (root.parent / "ops" / "runtime" / "pipeline_state.json").read_text()
    )
    assert state["counts"]["pending_intake"] == 2


def test_scan_flags_unparsed_file(root: Path):
    sub = root / "2.First Pass Done" / "ahri"
    sub.mkdir()
    (sub / "ahri_firstinitial.png").write_bytes(b"a")
    (sub / "ahri_firstdone.png").write_bytes(b"b")
    (sub / "WeirdFile.xyz").write_bytes(b"junk")
    assert run(root, "scan") == 1
    state = json.loads(
        (root.parent / "ops" / "runtime" / "pipeline_state.json").read_text()
    )
    classes = {a["class"] for a in state["anomalies"]}
    assert "UNPARSED_FILE" in classes


def test_scan_flags_duplicate_key(root: Path):
    sub = root / "2.First Pass Done" / "ahri"
    sub.mkdir()
    (sub / "ahri_firstinitial.png").write_bytes(b"a")
    (sub / "ahri_firstdone.png").write_bytes(b"b")
    (sub / "ahri_firstdone.jpg").write_bytes(b"twin")  # FM-06 ambiguous twin
    assert run(root, "scan") == 1
    state = json.loads(
        (root.parent / "ops" / "runtime" / "pipeline_state.json").read_text()
    )
    classes = {a["class"] for a in state["anomalies"]}
    assert "DUPLICATE_KEY" in classes


def test_pipeline_log_line_format(root: Path):
    _drop(root, "ahri.png")
    assert run(root, "intake", "--all") == 0
    lines = [
        ln for ln in (root.parent / "PIPELINE_LOG.md").read_text().splitlines()
        if " | " in ln
    ]
    assert lines
    parts = lines[-1].split(" | ")
    assert len(parts) == 8
    ts, slug, op, fromto, actor, sha12, status, note = parts
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", ts)
    assert slug == "ahri"
    assert op == "INTAKE"
    assert " -> " in fromto
    assert actor.startswith("actor=")
    assert re.match(r"^sha12=[0-9a-f]{12}$", sha12)
    assert status in ("ok",) or status.startswith("fail:")
    assert note.startswith("note=")


def test_status_lists_images(root: Path, capsys: pytest.CaptureFixture):
    _drop(root, "ahri.png")
    assert run(root, "intake", "--all") == 0
    capsys.readouterr()
    assert run(root, "status") == 0
    out = capsys.readouterr().out
    assert "ahri" in out and "FIRST_SCRATCH" in out


def test_status_single_slug_detail(root: Path, capsys: pytest.CaptureFixture):
    _drop(root, "ahri.png")
    assert run(root, "intake", "--all") == 0
    capsys.readouterr()
    assert run(root, "status", "ahri") == 0
    out = capsys.readouterr().out
    assert "FIRST_SCRATCH" in out and "INTAKE" in out


def test_unknown_slug_is_precondition_error(root: Path):
    assert run(root, "submit", "nope") == 2
    assert run(root, "approve", "nope") == 2
    assert run(root, "start-stage", "nope") == 2


def test_state_json_written_atomically_no_leftover_tmp(root: Path):
    _drop(root, "ahri.png")
    assert run(root, "intake", "--all") == 0
    runtime = root.parent / "ops" / "runtime"
    leftovers = [p for p in runtime.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []
