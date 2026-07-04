"""Tests for the `annotate` subcommand of tools/lw_pipeline.py.

The annotate verb closes the manifest provenance/metrics writer gap: it is the
only verb that records source-recovery provenance (top-level source_url) or G1
metrics into a slug's manifest.json.

Behavior choice under test (matches cmd_annotate docstring): an ANNOTATE
transition is ALWAYS appended when the command mutates - source_url-only still
records an ANNOTATE transition, and that transition's `audit` field is None
(metrics ride in `audit` only when --metrics is given). Written test-first per
CLAUDE.md TDD.
"""
from __future__ import annotations

import json
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
    for name in STAGE_FOLDERS:
        d = r / name
        d.mkdir(parents=True)
        (d / ".gitkeep").write_text("")
    return r


def run(root: Path, *args: str) -> int:
    return lw.main(["--root", str(root), *args])


def _seed(root: Path, stage_dir: str, slug: str) -> Path:
    """Create a slug folder with a fresh INTAKE-style manifest; return folder."""
    folder = root / stage_dir / slug
    folder.mkdir(parents=True)
    man = lw.new_manifest(slug, f"{slug}.png", "0" * 64)
    lw.add_transition(man, "INTAKE", src=f"0.Originals/{slug}.png",
                      dst=f"{stage_dir}/{slug}/{slug}_firstinitial.png",
                      sha_in="0" * 64, sha_out="0" * 64)
    (folder / "manifest.json").write_text(
        json.dumps(man, indent=2) + "\n", encoding="utf-8")
    return folder


def _manifest(folder: Path) -> dict:
    return json.loads((folder / "manifest.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- source_url

def test_annotate_source_url_sets_top_level_and_records_transition(root: Path):
    folder = _seed(root, "1.First Pass Scratch", "ahri")
    before = _manifest(folder)
    assert before["source_url"] is None
    n_before = len(before["transitions"])

    url = "https://www.deviantart.com/artist/art/ahri-123"
    assert run(root, "annotate", "ahri", "--source-url", url) == 0

    man = _manifest(folder)
    assert man["source_url"] == url
    # prior INTAKE transition left intact
    assert man["transitions"][0]["op"] == "INTAKE"
    # source_url-only STILL records one ANNOTATE transition, audit=None
    assert len(man["transitions"]) == n_before + 1
    last = man["transitions"][-1]
    assert last["op"] == "ANNOTATE"
    assert last["audit"] is None
    assert last["actor"] == "operator"


# ---------------------------------------------------------------- metrics

def test_annotate_metrics_inline_appends_audit_transition(root: Path):
    folder = _seed(root, "1.First Pass Scratch", "ahri")
    metrics = {"msssim": 0.98, "lpips": 0.1}
    assert run(
        root, "annotate", "ahri",
        "--metrics", json.dumps(metrics),
        "--tool", "g1gate",
    ) == 0
    man = _manifest(folder)
    last = man["transitions"][-1]
    assert last["op"] == "ANNOTATE"
    assert last["audit"] == metrics
    assert last["actor"] == "tool:g1gate"
    assert last["tool"] == "g1gate"
    # source_url untouched when only --metrics given
    assert man["source_url"] is None


def test_annotate_metrics_from_file(root: Path, tmp_path: Path):
    folder = _seed(root, "1.First Pass Scratch", "ahri")
    metrics = {"msssim": 0.991, "halo": 0.02, "sharpness": 1.4}
    mfile = tmp_path / "g1.json"
    mfile.write_text(json.dumps(metrics), encoding="utf-8")
    assert run(root, "annotate", "ahri", "--metrics", f"@{mfile}") == 0
    man = _manifest(folder)
    assert man["transitions"][-1]["audit"] == metrics


def test_annotate_both_source_and_metrics(root: Path):
    folder = _seed(root, "1.First Pass Scratch", "ahri")
    metrics = {"msssim": 0.95}
    url = "https://example.com/src.png"
    assert run(
        root, "annotate", "ahri",
        "--source-url", url, "--metrics", json.dumps(metrics),
    ) == 0
    man = _manifest(folder)
    assert man["source_url"] == url
    assert man["transitions"][-1]["audit"] == metrics


# ---------------------------------------------------------------- done folder

def test_annotate_works_on_slug_in_done_folder(root: Path):
    folder = _seed(root, "8.End Review", "jinx")
    assert run(root, "annotate", "jinx", "--source-url", "https://x/y") == 0
    assert _manifest(folder)["source_url"] == "https://x/y"


def test_annotate_works_on_slug_in_backup_only(root: Path):
    folder = _seed(root, "9.Image Backup", "vi")
    metrics = {"msssim": 0.9}
    assert run(root, "annotate", "vi", "--metrics", json.dumps(metrics)) == 0
    assert _manifest(folder)["transitions"][-1]["audit"] == metrics


# ---------------------------------------------------------------- errors

def test_annotate_unknown_slug_exit_2(root: Path):
    assert run(root, "annotate", "ghost", "--source-url", "https://x/y") == 2


def test_annotate_neither_flag_exit_2(root: Path):
    _seed(root, "1.First Pass Scratch", "ahri")
    assert run(root, "annotate", "ahri") == 2


def test_annotate_bad_json_exit_2(root: Path):
    _seed(root, "1.First Pass Scratch", "ahri")
    assert run(root, "annotate", "ahri", "--metrics", "{not valid json") == 2


def test_annotate_metrics_missing_file_exit_2(root: Path, tmp_path: Path):
    _seed(root, "1.First Pass Scratch", "ahri")
    missing = tmp_path / "nope.json"
    assert run(root, "annotate", "ahri", "--metrics", f"@{missing}") == 2


def test_annotate_no_manifest_exit_2(root: Path):
    # folder exists but has no manifest.json
    (root / "1.First Pass Scratch" / "orphan").mkdir(parents=True)
    assert run(root, "annotate", "orphan", "--source-url", "https://x/y") == 2


# ---------------------------------------------------------------- dry-run

def test_annotate_dry_run_does_not_modify_manifest(root: Path, capsys):
    folder = _seed(root, "1.First Pass Scratch", "ahri")
    before = (folder / "manifest.json").read_text(encoding="utf-8")
    assert run(
        root, "annotate", "ahri",
        "--source-url", "https://x/y",
        "--metrics", '{"msssim": 0.9}',
        "--dry-run",
    ) == 0
    after = (folder / "manifest.json").read_text(encoding="utf-8")
    assert after == before
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
