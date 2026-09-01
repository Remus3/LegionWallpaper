"""Send a slug back to an earlier scratch stage (tools/lw_pipeline.py reopen).

Origin (2026-09-01): a better 1280x756 source turned up for a slug already
sitting in 4.Cleaning Done, and there was no reverse move - the documented
workaround was a hand "reopen dance" that moved folders outside lw_pipeline,
which is exactly the single-writer rule it is not allowed to break.

The load-bearing guard is that a reopen DROPS the stale downstream milestones
(they were derived from the old source and are now lies), so it refuses unless
each of those is already hash-preserved in 9.Image Backup. A stale directory is
cheap; a lost milestone is not - the same trade _prune_prior_done makes.
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

SLUG = "twin-slug"


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


def _seed_cleaned(root: Path, *, preserve: bool = True) -> Path:
    """A slug parked in 4.Cleaning Done with its full carried-forward chain."""
    d = root / "4.Cleaning Done" / SLUG
    d.mkdir(parents=True)
    (d / f"{SLUG}_firstinitial.jpg").write_bytes(b"old-source")
    (d / f"{SLUG}_cleaninitial.png").write_bytes(b"upscaled-2560")
    (d / f"{SLUG}_cleandone.png").write_bytes(b"upscaled-2560")
    man = lw.new_manifest(SLUG, "orig.jpg", lw.sha256_file(d / f"{SLUG}_firstinitial.jpg"))
    lw.add_transition(man, "APPROVE_CLEAN", note="seeded")
    (d / "manifest.json").write_text(json.dumps(man), encoding="ascii")

    b = root / "9.Image Backup" / SLUG
    b.mkdir(parents=True)
    (b / "orig.jpg").write_bytes(b"old-source")
    if preserve:
        (b / f"{SLUG}_cleaninitial.png").write_bytes(b"upscaled-2560")
        (b / f"{SLUG}_cleandone.png").write_bytes(b"upscaled-2560")
    (b / "manifest.json").write_text(json.dumps(man), encoding="ascii")
    return d


def test_reopen_moves_the_folder_back_and_drops_stale_milestones(root):
    _seed_cleaned(root)
    assert run(root, "reopen", SLUG, "--to", "first", "--yes") == 0

    scratch = root / "1.First Pass Scratch" / SLUG
    assert scratch.is_dir()
    assert not (root / "4.Cleaning Done" / SLUG).exists()
    # the source survives; everything derived from it does not
    assert (scratch / f"{SLUG}_firstinitial.jpg").is_file()
    assert not (scratch / f"{SLUG}_cleaninitial.png").exists()
    assert not (scratch / f"{SLUG}_cleandone.png").exists()

    log = (root.parent / "PIPELINE_LOG.md").read_text(encoding="ascii")
    assert f"| {SLUG} | REOPEN |" in log


def test_reopen_preserves_the_manifest_history(root):
    _seed_cleaned(root)
    before = len(json.loads(
        (root / "4.Cleaning Done" / SLUG / "manifest.json").read_text())["transitions"])
    assert run(root, "reopen", SLUG, "--to", "first", "--yes") == 0

    man = json.loads((root / "1.First Pass Scratch" / SLUG
                      / "manifest.json").read_text(encoding="utf-8"))
    assert len(man["transitions"]) == before + 1
    assert man["transitions"][-1]["op"] == "REOPEN"
    # the earlier chain is still readable, not rewritten
    assert any(t["op"] == "APPROVE_CLEAN" for t in man["transitions"])


def test_reopen_refuses_when_a_milestone_is_not_backed_up(root, capsys):
    """Dropping the only copy of a milestone is the one thing it must not do."""
    _seed_cleaned(root, preserve=False)
    assert run(root, "reopen", SLUG, "--to", "first", "--yes") == 3
    out = capsys.readouterr().out
    assert "not preserved" in out
    assert (root / "4.Cleaning Done" / SLUG).is_dir()
    assert not (root / "1.First Pass Scratch" / SLUG).exists()


def test_preservation_is_by_content_not_by_filename(root):
    """A pass-through stage leaves _cleandone byte-identical to _cleaninitial.

    The backup legitimately holds one copy under one name, and the bytes are
    what must not be lost - so a name-only check would refuse a reopen that is
    provably safe. This is the real shape of the academy-ahri twin.
    """
    d = _seed_cleaned(root, preserve=False)
    b = root / "9.Image Backup" / SLUG
    # only the _cleaninitial name is backed up, but _cleandone has those bytes
    (b / f"{SLUG}_cleaninitial.png").write_bytes(b"upscaled-2560")
    assert (d / f"{SLUG}_cleandone.png").read_bytes() == b"upscaled-2560"

    assert run(root, "reopen", SLUG, "--to", "first", "--yes") == 0
    assert (root / "1.First Pass Scratch" / SLUG).is_dir()


def test_reopen_with_source_swaps_and_records_replace_source(root, tmp_path):
    _seed_cleaned(root)
    newsrc = tmp_path / "better.jpg"
    newsrc.write_bytes(b"new-1280-source")

    assert run(root, "reopen", SLUG, "--to", "first", "--yes",
               "--source", str(newsrc),
               "--source-url", "https://example.invalid/deviation/1") == 0

    scratch = root / "1.First Pass Scratch" / SLUG
    assert (scratch / f"{SLUG}_firstinitial.jpg").read_bytes() == b"new-1280-source"
    man = json.loads((scratch / "manifest.json").read_text(encoding="utf-8"))
    ops = [t["op"] for t in man["transitions"]]
    assert "REPLACE_SOURCE" in ops
    swap = next(t for t in man["transitions"] if t["op"] == "REPLACE_SOURCE")
    assert swap["sha256_out"] == lw.sha256_file(scratch / f"{SLUG}_firstinitial.jpg")
    assert swap["sha256_in"] != swap["sha256_out"]


def test_reopen_source_extension_change_leaves_no_stale_initial(root, tmp_path):
    """A .png replacement must not leave the old .jpg _firstinitial behind."""
    _seed_cleaned(root)
    newsrc = tmp_path / "better.png"
    newsrc.write_bytes(b"new-png-source")
    assert run(root, "reopen", SLUG, "--to", "first", "--yes",
               "--source", str(newsrc)) == 0
    scratch = root / "1.First Pass Scratch" / SLUG
    assert (scratch / f"{SLUG}_firstinitial.png").is_file()
    assert not (scratch / f"{SLUG}_firstinitial.jpg").exists()


def test_reopen_refuses_without_yes(root, capsys):
    _seed_cleaned(root)
    assert run(root, "reopen", SLUG, "--to", "first") == 2
    assert "--yes" in capsys.readouterr().out
    assert (root / "4.Cleaning Done" / SLUG).is_dir()


def test_reopen_dry_run_mutates_nothing(root, capsys):
    _seed_cleaned(root)
    assert run(root, "reopen", SLUG, "--to", "first", "--yes", "--dry-run") == 0
    assert "DRY-RUN" in capsys.readouterr().out
    assert (root / "4.Cleaning Done" / SLUG).is_dir()
    assert not (root / "1.First Pass Scratch" / SLUG).exists()


def test_dry_run_plan_shows_the_source_swap(root, tmp_path, capsys):
    """A plan that hides half the operation is worse than no plan."""
    _seed_cleaned(root)
    newsrc = tmp_path / "better.jpg"
    newsrc.write_bytes(b"new-1280-source")
    assert run(root, "reopen", SLUG, "--to", "first", "--yes", "--dry-run",
               "--source", str(newsrc)) == 0
    out = capsys.readouterr().out
    assert "better.jpg" in out
    assert f"{SLUG}_firstinitial.jpg" in out
    assert (root / "4.Cleaning Done" / SLUG).is_dir()
    # the plan must not claim to delete a stale milestone out of the DESTINATION -
    # _cleaninitial never gets there, it is dropped at the source folder
    assert f"1.First Pass Scratch\\{SLUG}\\{SLUG}_cleaninitial.png" not in out


def test_reopen_unknown_slug_is_a_precondition_error(root, capsys):
    assert run(root, "reopen", "nope", "--to", "first", "--yes") == 2
    assert "not found" in capsys.readouterr().out


def test_reopen_refuses_a_target_that_is_not_earlier(root, capsys):
    _seed_cleaned(root)
    assert run(root, "reopen", SLUG, "--to", "final", "--yes") == 2
    assert "earlier" in capsys.readouterr().out
    assert (root / "4.Cleaning Done" / SLUG).is_dir()


def test_reopen_refuses_while_a_lock_is_held(root, capsys):
    d = _seed_cleaned(root)
    (d / ".lw.lock").write_text("held")
    assert run(root, "reopen", SLUG, "--to", "first", "--yes") == 2
    assert "lock" in capsys.readouterr().out.lower()
    assert (root / "4.Cleaning Done" / SLUG).is_dir()
