"""The canonical backup name must hold the CURRENT generation.

Origin (2026-09-01): after the academy-ahri reopen, `verify` reported a
HASH_MISMATCH on 9.Image Backup/<slug>/<slug>_cleaninitial.png. No bytes were
lost - Ops.backup_put refuses to overwrite and had parked the rebuilt copy
alongside as `_cleaninitial.2.png` - but that leaves the CANONICAL name holding
the superseded generation while the manifest's latest transition describes the
new one.

backup_put numbers by arrival: first write wins the canonical slot, later ones
get `.N`. That is right for a genuine collision and wrong for a supersede,
which is what a reopen produces. `verify` resolves one expected hash per
milestone key (_expected_hashes, latest by timestamp), so it can only ever
agree with a backup whose canonical name is the newest generation.

The fix is NOT to make the stale file unverifiable - `_milestone_key` settles
that: "the mismatch is noise, the silence reads as a pass". It is to rotate the
superseded generation into a `.N` archival slot at reopen time so the rebuild
lands canonical, and to backfill the row that already exists.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_backfill_backup_generation as bf  # noqa: E402
import lw_pipeline as lw  # noqa: E402

STAGE_FOLDERS = [
    "0.Originals", "1.First Pass Scratch", "2.First Pass Done",
    "3.Cleaning Scratch", "4.Cleaning Done", "5.Final Scratch",
    "6.Final Done", "7.Last Scratch", "8.End Review", "9.Image Backup",
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


def _seed_cleaned(root: Path) -> Path:
    d = root / "4.Cleaning Done" / SLUG
    d.mkdir(parents=True)
    (d / f"{SLUG}_firstinitial.jpg").write_bytes(b"old-source")
    (d / f"{SLUG}_cleaninitial.png").write_bytes(b"old-upscale")
    (d / f"{SLUG}_cleandone.png").write_bytes(b"old-upscale")
    man = lw.new_manifest(SLUG, "orig.jpg",
                          lw.sha256_file(d / f"{SLUG}_firstinitial.jpg"))
    (d / "manifest.json").write_text(json.dumps(man), encoding="ascii")

    b = root / "9.Image Backup" / SLUG
    b.mkdir(parents=True)
    (b / "orig.jpg").write_bytes(b"old-source")
    (b / f"{SLUG}_cleaninitial.png").write_bytes(b"old-upscale")
    (b / "manifest.json").write_text(json.dumps(man), encoding="ascii")
    return d


# ---------------------------------------------------------------------------
# reopen rotates the superseded generation out of the canonical slot
# ---------------------------------------------------------------------------

def test_reopen_frees_the_canonical_backup_slot(root):
    _seed_cleaned(root)
    b = root / "9.Image Backup" / SLUG

    assert run(root, "reopen", SLUG, "--to", "first", "--yes") == 0

    # canonical is free for the rebuild; the superseded bytes are still archived
    assert not (b / f"{SLUG}_cleaninitial.png").exists()
    archived = list(b.glob(f"{SLUG}_cleaninitial.*.png"))
    assert len(archived) == 1
    assert archived[0].read_bytes() == b"old-upscale"


def test_rotation_only_touches_the_superseded_generation(root):
    """A backup copy that is NOT the dropped content is left alone."""
    _seed_cleaned(root)
    b = root / "9.Image Backup" / SLUG
    (b / f"{SLUG}_cleaninitial.png").write_bytes(b"something-else-entirely")
    # the guard must now refuse: the dropped milestone is no longer preserved
    assert run(root, "reopen", SLUG, "--to", "first", "--yes") == 3
    assert (b / f"{SLUG}_cleaninitial.png").read_bytes() == b"something-else-entirely"


def test_rotation_picks_the_next_free_slot(root):
    _seed_cleaned(root)
    b = root / "9.Image Backup" / SLUG
    (b / f"{SLUG}_cleaninitial.2.png").write_bytes(b"an-earlier-archive")

    assert run(root, "reopen", SLUG, "--to", "first", "--yes") == 0
    assert (b / f"{SLUG}_cleaninitial.2.png").read_bytes() == b"an-earlier-archive"
    assert (b / f"{SLUG}_cleaninitial.3.png").read_bytes() == b"old-upscale"


def test_reopen_dry_run_does_not_rotate(root):
    _seed_cleaned(root)
    b = root / "9.Image Backup" / SLUG
    assert run(root, "reopen", SLUG, "--to", "first", "--yes", "--dry-run") == 0
    assert (b / f"{SLUG}_cleaninitial.png").read_bytes() == b"old-upscale"


def test_verify_is_clean_after_a_full_reopen_and_rebuild(root, capsys):
    """End to end: the whole point of the rotation."""
    _seed_cleaned(root)
    assert run(root, "reopen", SLUG, "--to", "first", "--yes") == 0

    # the rebuild writes its own generation into the canonical slot
    scratch = root / "1.First Pass Scratch" / SLUG
    rebuilt = scratch / f"{SLUG}_cleaninitial.png"
    rebuilt.write_bytes(b"new-upscale")
    b = root / "9.Image Backup" / SLUG
    lw.Ops(dry=False).backup_put(rebuilt, b, rebuilt.name)
    man = lw.load_manifest(scratch)
    lw.add_transition(man, "APPROVE_CLEAN",
                      dst=f"4.Cleaning Done/{SLUG}/{rebuilt.name}",
                      sha_out=lw.sha256_file(rebuilt))
    lw.Ops(dry=False).write_json(scratch / "manifest.json", man)

    assert (b / f"{SLUG}_cleaninitial.png").read_bytes() == b"new-upscale"
    capsys.readouterr()
    run(root, "verify")
    assert "HASH_MISMATCH" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# the backfill for rows that already went through the old path
# ---------------------------------------------------------------------------

def _seed_inverted(root: Path) -> Path:
    """The exact shape on disk after the academy-ahri reopen: canonical holds
    the OLD generation, `.2` holds the current one."""
    d = root / "4.Cleaning Done" / SLUG
    d.mkdir(parents=True)
    (d / f"{SLUG}_cleaninitial.png").write_bytes(b"new-upscale")
    man = lw.new_manifest(SLUG, "orig.jpg", "0" * 64)
    lw.add_transition(man, "APPROVE_CLEAN",
                      dst=f"4.Cleaning Done/{SLUG}/{SLUG}_cleaninitial.png",
                      sha_out=lw.sha256_file(d / f"{SLUG}_cleaninitial.png"))
    (d / "manifest.json").write_text(json.dumps(man), encoding="ascii")

    b = root / "9.Image Backup" / SLUG
    b.mkdir(parents=True)
    (b / f"{SLUG}_cleaninitial.png").write_bytes(b"old-upscale")
    (b / f"{SLUG}_cleaninitial.2.png").write_bytes(b"new-upscale")
    (b / "manifest.json").write_text(json.dumps(man), encoding="ascii")
    return b


def test_backfill_reports_the_swap_without_writing(root, capsys):
    b = _seed_inverted(root)
    assert bf.main(["--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert SLUG in out and "would promote" in out
    assert (b / f"{SLUG}_cleaninitial.png").read_bytes() == b"old-upscale"


def test_backfill_apply_promotes_the_current_generation(root):
    b = _seed_inverted(root)
    assert bf.main(["--root", str(root), "--apply"]) == 0
    assert (b / f"{SLUG}_cleaninitial.png").read_bytes() == b"new-upscale"
    # the superseded bytes are archived, never deleted
    archived = [p for p in b.glob(f"{SLUG}_cleaninitial.*.png")]
    assert any(p.read_bytes() == b"old-upscale" for p in archived)


def test_backfill_is_idempotent(root):
    b = _seed_inverted(root)
    assert bf.main(["--root", str(root), "--apply"]) == 0
    before = sorted(p.name for p in b.iterdir())
    assert bf.main(["--root", str(root), "--apply"]) == 0
    assert sorted(p.name for p in b.iterdir()) == before


def test_backfill_leaves_an_unexplained_mismatch_alone(root, capsys):
    """No `.N` sibling carries the expected hash - report, never guess."""
    b = _seed_inverted(root)
    (b / f"{SLUG}_cleaninitial.2.png").unlink()
    assert bf.main(["--root", str(root), "--apply"]) == 0
    out = capsys.readouterr().out
    assert "unexplained" in out
    assert (b / f"{SLUG}_cleaninitial.png").read_bytes() == b"old-upscale"


def test_backfill_ignores_a_folder_that_is_already_correct(root, capsys):
    b = _seed_inverted(root)
    assert bf.main(["--root", str(root), "--apply"]) == 0
    capsys.readouterr()
    assert bf.main(["--root", str(root)]) == 0
    assert "would promote" not in capsys.readouterr().out
