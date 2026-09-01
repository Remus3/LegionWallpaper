"""GC one slug out of the pipeline (tools/lw_pipeline.py remove).

Origin (2026-09-01): the near-dup sweep found a redundant slug that had to
come out, and there was no sanctioned writer for it - every other mutation
goes through lw_pipeline, so a hand `rm -rf` would have been the first crack
in the single-writer rule. ADR-003 makes GC an operator ruling, so this
command is deliberately hard to fire by accident: it refuses without --yes,
refuses while a stage lock is held, and appends a REMOVE line to the
append-only log rather than editing the slug's history out of it.
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
    for name in STAGE_FOLDERS + ["reference_pictures"]:
        d = r / name
        d.mkdir(parents=True)
        (d / ".gitkeep").write_text("")
    return r


def run(root: Path, *args: str) -> int:
    return lw.main(["--root", str(root), *args])


def _seed(root: Path, slug: str, *, stage_dir: str = "1.First Pass Scratch",
          backup: bool = True) -> None:
    d = root / stage_dir / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}_firstinitial.jpg").write_bytes(b"pixels")
    man = lw.new_manifest(slug, "orig.jpg", "0" * 64)
    (d / "manifest.json").write_text(json.dumps(man), encoding="ascii")
    if backup:
        b = root / "9.Image Backup" / slug
        b.mkdir(parents=True, exist_ok=True)
        (b / "orig.jpg").write_bytes(b"pixels")
        (b / "manifest.json").write_text(json.dumps(man), encoding="ascii")


def test_remove_clears_scratch_and_backup_and_logs(root, capsys):
    _seed(root, "doomed-slug")
    assert run(root, "remove", "doomed-slug", "--yes") == 0

    assert not (root / "1.First Pass Scratch" / "doomed-slug").exists()
    assert not (root / "9.Image Backup" / "doomed-slug").exists()
    # the slug frees up: a later re-intake gets the clean name back
    assert not lw.slug_in_use(lw.Ctx(root), "doomed-slug")

    log = (root.parent / "PIPELINE_LOG.md").read_text(encoding="ascii")
    assert "| doomed-slug | REMOVE |" in log


def test_remove_refuses_without_yes(root, capsys):
    _seed(root, "doomed-slug")
    assert run(root, "remove", "doomed-slug") == 2
    assert "--yes" in capsys.readouterr().out
    assert (root / "1.First Pass Scratch" / "doomed-slug").is_dir()
    assert (root / "9.Image Backup" / "doomed-slug").is_dir()


def test_remove_dry_run_plans_and_mutates_nothing(root, capsys):
    _seed(root, "doomed-slug")
    assert run(root, "remove", "doomed-slug", "--yes", "--dry-run") == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "doomed-slug" in out
    assert (root / "1.First Pass Scratch" / "doomed-slug").is_dir()
    assert (root / "9.Image Backup" / "doomed-slug").is_dir()
    assert not (root.parent / "PIPELINE_LOG.md").exists()


def test_keep_backup_retains_the_safety_net(root):
    _seed(root, "doomed-slug")
    assert run(root, "remove", "doomed-slug", "--yes", "--keep-backup") == 0
    assert not (root / "1.First Pass Scratch" / "doomed-slug").exists()
    assert (root / "9.Image Backup" / "doomed-slug").is_dir()
    # the backup still pins the name, so re-intake would still collide
    assert lw.slug_in_use(lw.Ctx(root), "doomed-slug")


def test_remove_works_on_a_done_stage(root):
    _seed(root, "done-slug", stage_dir="4.Cleaning Done")
    assert run(root, "remove", "done-slug", "--yes") == 0
    assert not (root / "4.Cleaning Done" / "done-slug").exists()
    assert not (root / "9.Image Backup" / "done-slug").exists()


def test_remove_unknown_slug_is_a_precondition_error(root, capsys):
    assert run(root, "remove", "no-such-slug", "--yes") == 2
    assert "not found" in capsys.readouterr().out


def test_remove_refuses_while_a_lock_is_held(root, capsys):
    _seed(root, "doomed-slug")
    (root / "1.First Pass Scratch" / "doomed-slug" / ".lw.lock").write_text("held")
    assert run(root, "remove", "doomed-slug", "--yes") == 2
    out = capsys.readouterr().out
    assert "lock" in out.lower()
    assert (root / "1.First Pass Scratch" / "doomed-slug").is_dir()


def test_remove_spanning_scratch_and_done(root):
    """A slug present in two places is cleared from both in one call."""
    _seed(root, "spread-slug", stage_dir="1.First Pass Scratch")
    _seed(root, "spread-slug", stage_dir="4.Cleaning Done", backup=False)
    assert run(root, "remove", "spread-slug", "--yes") == 0
    assert not (root / "1.First Pass Scratch" / "spread-slug").exists()
    assert not (root / "4.Cleaning Done" / "spread-slug").exists()
    assert not (root / "9.Image Backup" / "spread-slug").exists()


def test_remove_leaves_other_slugs_alone(root):
    """The prefix twin must survive - `-pre` is not `-pre-2`."""
    _seed(root, "artwork-pre")
    _seed(root, "artwork-pre-2")
    assert run(root, "remove", "artwork-pre-2", "--yes") == 0
    assert not (root / "1.First Pass Scratch" / "artwork-pre-2").exists()
    assert (root / "1.First Pass Scratch" / "artwork-pre").is_dir()
    assert (root / "9.Image Backup" / "artwork-pre").is_dir()
