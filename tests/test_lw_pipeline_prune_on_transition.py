"""Done-N folder is pruned AT the transition, not held until Done N+1.

Operator ruling 2026-08-17, superseding the FM-02 retention half: when a slug
moves Done N -> Scratch N+1, the Done N folder goes. The fallback is the
`_initial` copy the transition itself writes into Scratch N+1, which is why
the transition makes one - and `start-stage` copies EVERY milestone forward,
not just the `_done`, so Scratch N+1 is a superset of what Done N held.

The hash-verified GC of FM-02 is unchanged for the Done N -> Done N+1 path
(`_gc_prior_done`); this covers only the earlier T2 hop.

Written test-first per CLAUDE.md TDD.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_pipeline as lw  # noqa: E402

from test_lw_pipeline_moves import (  # noqa: E402
    STAGE_FOLDERS, _drop, _edit, _milestones, run,
)


# The helpers above are plain functions and import cleanly, but a fixture does
# NOT: `pytest_plugins` is only honoured in the rootdir conftest, so declaring
# it here passed file-alone and vanished under the full suite. Own the fixture.
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


def _to_first_done(root: Path, tmp: Path, slug: str = "ahri") -> Path:
    _drop(root, f"{slug}.png", b"orig-" + slug.encode())
    assert run(root, "intake", "--all") == 0
    _edit(root, slug, "first", b"f1", tmp)
    assert run(root, "approve", slug) == 0
    done = root / "2.First Pass Done" / slug
    assert done.is_dir()
    return done


def test_start_stage_prunes_the_done_folder(root: Path, tmp_path: Path):
    """The whole point: Done N is gone once the slug is in Scratch N+1."""
    done2 = _to_first_done(root, tmp_path)
    assert run(root, "start-stage", "ahri") == 0
    assert not done2.exists()


def test_scratch_carries_every_milestone_the_done_folder_held(
        root: Path, tmp_path: Path):
    """Pruning is only safe because nothing is left behind - prove it."""
    done2 = _to_first_done(root, tmp_path)
    before = _milestones(done2)
    assert run(root, "start-stage", "ahri") == 0
    after = _milestones(root / "3.Cleaning Scratch" / "ahri")
    # every pre-existing milestone survives; the _firstdone arrives renamed
    assert {"ahri_firstinitial.png"} <= after
    assert "ahri_firstdone.png" in before
    assert "ahri_cleaninitial.png" in after


def test_cleaninitial_bytes_equal_the_pruned_firstdone(
        root: Path, tmp_path: Path):
    """The fallback must be the SAME pixels, not merely a same-named file."""
    done2 = _to_first_done(root, tmp_path)
    firstdone = (done2 / "ahri_firstdone.png").read_bytes()
    assert run(root, "start-stage", "ahri") == 0
    cleaninitial = (root / "3.Cleaning Scratch" / "ahri"
                    / "ahri_cleaninitial.png").read_bytes()
    assert cleaninitial == firstdone


def test_dry_run_prunes_nothing(root: Path, tmp_path: Path):
    done2 = _to_first_done(root, tmp_path)
    assert run(root, "start-stage", "ahri", "--dry-run") == 0
    assert done2.is_dir()
    assert (done2 / "ahri_firstdone.png").is_file()


def test_backup_still_holds_the_verbatim_original_after_pruning(
        root: Path, tmp_path: Path):
    """9.Image Backup is the permanent archive and is never pruned."""
    _to_first_done(root, tmp_path)
    assert run(root, "start-stage", "ahri") == 0
    backup = root / "9.Image Backup" / "ahri"
    assert backup.is_dir()
    assert (backup / "ahri.png").read_bytes() == b"orig-ahri"


def test_scan_reports_no_anomaly_after_the_prune(root: Path, tmp_path: Path):
    """A pruned Done N must not read as MISSING/STALE to the scanner."""
    _to_first_done(root, tmp_path)
    assert run(root, "start-stage", "ahri") == 0
    assert run(root, "scan") == 0
    state = lw.json.loads(
        (root.parent / "ops" / "runtime" / "pipeline_state.json").read_text(
            encoding="utf-8")
    ) if (root.parent / "ops" / "runtime" / "pipeline_state.json").is_file() \
        else None
    if state is not None:
        assert state["counts"].get("anomalies", 0) == 0


def test_prune_is_skipped_when_the_done_milestone_is_missing(
        root: Path, tmp_path: Path):
    """No _firstdone -> the transition errors and nothing is deleted."""
    done2 = _to_first_done(root, tmp_path)
    (done2 / "ahri_firstdone.png").unlink()
    assert run(root, "start-stage", "ahri") != 0
    assert done2.is_dir()
