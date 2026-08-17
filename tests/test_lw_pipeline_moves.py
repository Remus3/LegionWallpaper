"""Transition + safety tests for tools/lw_pipeline.py.

Spec: docs/research/PIPELINE_STATE_MACHINE.md sections 2.3-2.7 and 3, with
the operator rulings: End Review reject ENABLED, Done-N GC after verified
arrival ENABLED, End Review PASS deletes 8.End Review\\<slug> after the
hash-verified copy to 9.Image Backup. Written test-first per CLAUDE.md TDD.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
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


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _tree_digest(base: Path) -> dict:
    out = {}
    for p in sorted(base.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(base))] = _sha(p)
    return out


def _milestones(folder: Path) -> set:
    return {p.name for p in folder.iterdir() if lw.parse_milestone(p.name)}


def _edit(root: Path, slug: str, stage: str, tag: bytes, tmp: Path) -> None:
    """Simulate an operator edit round: save-working, submit."""
    src = tmp / f"edit-{slug}-{stage}-{tag.decode()}.png"
    src.write_bytes(b"edited-" + tag)
    assert run(root, "save-working", slug, "--from", str(src)) == 0
    assert run(root, "submit", slug) == 0


def _walk_to_end_review(root: Path, tmp: Path, slug: str = "ahri") -> None:
    _drop(root, f"{slug}.png", b"orig-" + slug.encode())
    assert run(root, "intake", "--all") == 0
    for stage in ("first", "clean", "final", "last"):
        if stage != "first":
            assert run(root, "start-stage", slug) == 0
        _edit(root, slug, stage, stage.encode(), tmp)
        assert run(root, "approve", slug) == 0


# ---------------------------------------------------------------- intake

def test_intake_happy_path(root: Path):
    _drop(root, "Ahri Star.png", b"orig-bytes")
    assert run(root, "intake", "--all") == 0
    backup = root / "9.Image Backup" / "ahri-star"
    scratch = root / "1.First Pass Scratch" / "ahri-star"
    assert (backup / "Ahri Star.png").read_bytes() == b"orig-bytes"
    assert (scratch / "ahri-star_firstinitial.png").read_bytes() == b"orig-bytes"
    assert not (root / "0.Originals" / "Ahri Star.png").exists()
    man = json.loads((scratch / "manifest.json").read_text())
    assert man["slug"] == "ahri-star"
    assert man["original_filename"] == "Ahri Star.png"
    assert man["transitions"][0]["op"] == "INTAKE"
    # log + state written next to the pipeline root's parent
    log = root.parent / "PIPELINE_LOG.md"
    assert log.is_file() and "| INTAKE |" in log.read_text()
    state = json.loads(
        (root.parent / "ops" / "runtime" / "pipeline_state.json").read_text()
    )
    assert state["images"]["ahri-star"]["state"] == "FIRST_SCRATCH"


def test_intake_skips_zero_byte_and_fresh_files(root: Path, capsys):
    p0 = root / "0.Originals" / "empty.png"
    p0.write_bytes(b"")
    old = p0.stat().st_mtime - 120
    os.utime(p0, (old, old))
    fresh = root / "0.Originals" / "fresh.png"
    fresh.write_bytes(b"still-downloading")  # mtime = now -> not stable yet
    assert run(root, "intake", "--all") == 0
    assert p0.is_file() and fresh.is_file()
    assert not (root / "1.First Pass Scratch" / "empty").exists()
    assert not (root / "1.First Pass Scratch" / "fresh").exists()


def test_intake_skips_partial_extensions(root: Path):
    for name in ("a.crdownload", "b.part", "c.tmp", "d.download"):
        _drop(root, name, b"partial")
    assert run(root, "intake", "--all") == 0
    for sub in (root / "1.First Pass Scratch").iterdir():
        assert not sub.is_dir()


# ---------------------------------------------------------------- full walk

def test_full_stage_walk_milestone_sets(root: Path, tmp_path: Path):
    _drop(root, "ahri.png", b"orig-ahri")
    assert run(root, "intake", "--all") == 0

    _edit(root, "ahri", "first", b"f1", tmp_path)
    assert run(root, "approve", "ahri") == 0
    done2 = root / "2.First Pass Done" / "ahri"
    assert _milestones(done2) == {"ahri_firstinitial.png", "ahri_firstdone.png"}
    assert not (root / "1.First Pass Scratch" / "ahri").exists()

    assert run(root, "start-stage", "ahri") == 0
    scratch3 = root / "3.Cleaning Scratch" / "ahri"
    assert _milestones(scratch3) == {"ahri_firstinitial.png", "ahri_cleaninitial.png"}
    # _cleaninitial content = _firstdone content; backed up at stage start
    assert (root / "9.Image Backup" / "ahri" / "ahri_cleaninitial.png").is_file()
    # Operator ruling 2026-08-17: Done N is pruned AT the transition, its
    # content having been carried into Scratch N+1 above. The hash-verified
    # FM-02 GC still governs the later Done N -> Done N+1 hop.
    assert not done2.exists()

    _edit(root, "ahri", "clean", b"c1", tmp_path)
    assert run(root, "approve", "ahri") == 0
    done4 = root / "4.Cleaning Done" / "ahri"
    assert _milestones(done4) == {
        "ahri_firstinitial.png", "ahri_cleaninitial.png", "ahri_cleandone.png",
    }
    assert not done2.exists()  # FM-02 GC after verified arrival
    assert not scratch3.exists()

    assert run(root, "start-stage", "ahri") == 0
    _edit(root, "ahri", "final", b"n1", tmp_path)
    assert run(root, "approve", "ahri") == 0
    done6 = root / "6.Final Done" / "ahri"
    assert _milestones(done6) == {
        "ahri_firstinitial.png", "ahri_cleaninitial.png",
        "ahri_finalinitial.png", "ahri_finaldone.png",
    }
    assert not done4.exists()

    assert run(root, "start-stage", "ahri") == 0
    _edit(root, "ahri", "last", b"l1", tmp_path)
    assert run(root, "approve", "ahri") == 0
    review = root / "8.End Review" / "ahri"
    assert _milestones(review) == {
        "ahri_firstinitial.png", "ahri_cleaninitial.png",
        "ahri_finalinitial.png", "ahri_lastinitial.png", "ahri_lastdone.png",
    }
    assert not done6.exists()

    lastdone_hash = _sha(review / "ahri_lastdone.png")
    assert run(root, "finalize", "ahri") == 0
    backup = root / "9.Image Backup" / "ahri"
    assert _sha(backup / "ahri_lastdone.png") == lastdone_hash
    assert not review.exists()  # operator correction: 8\<slug> deleted on pass
    # full milestone chain lives in backup
    names = {p.name for p in backup.iterdir()}
    assert {"ahri.png", "ahri_cleaninitial.png", "ahri_finalinitial.png",
            "ahri_lastinitial.png", "ahri_lastdone.png"} <= names
    state = json.loads(
        (root.parent / "ops" / "runtime" / "pipeline_state.json").read_text()
    )
    assert state["images"]["ahri"]["state"] == "PASSED"


def test_approve_discards_working_files(root: Path, tmp_path: Path):
    _drop(root, "ahri.png", b"orig")
    assert run(root, "intake", "--all") == 0
    _edit(root, "ahri", "first", b"w1", tmp_path)
    assert run(root, "approve", "ahri") == 0
    done2 = root / "2.First Pass Done" / "ahri"
    assert not any("working" in p.name for p in done2.iterdir())


def test_start_stage_refuses_if_already_in_scratch(root: Path, tmp_path: Path):
    _drop(root, "ahri.png", b"orig")
    assert run(root, "intake", "--all") == 0
    _edit(root, "ahri", "first", b"w1", tmp_path)
    assert run(root, "approve", "ahri") == 0
    assert run(root, "start-stage", "ahri") == 0
    assert run(root, "start-stage", "ahri") == 2  # precondition error


# ---------------------------------------------------------------- submit/reject

def test_submit_requires_working_and_no_double_submit(root: Path, tmp_path: Path):
    _drop(root, "ahri.png", b"orig")
    assert run(root, "intake", "--all") == 0
    assert run(root, "submit", "ahri") == 2  # no working file yet
    _edit(root, "ahri", "first", b"w1", tmp_path)
    assert run(root, "submit", "ahri") == 2  # already submitted


def test_reject_renumbers_max_plus_one(root: Path, tmp_path: Path):
    _drop(root, "ahri.png", b"orig")
    assert run(root, "intake", "--all") == 0
    _edit(root, "ahri", "first", b"w1", tmp_path)
    scratch = root / "1.First Pass Scratch" / "ahri"
    # operator manually drops a higher working while needauth pending
    (scratch / "ahri_firstworking_05.png").write_bytes(b"manual")
    assert run(root, "reject", "ahri", "--note", "too soft") == 0
    assert (scratch / "ahri_firstworking_06.png").is_file()
    assert not (scratch / "ahri_firstneedauth.png").exists()
    man = json.loads((scratch / "manifest.json").read_text())
    assert man["transitions"][-1]["op"] == "REJECT"
    assert "too soft" in (man["transitions"][-1].get("note") or "")


def test_reject_without_needauth_errors(root: Path):
    _drop(root, "ahri.png", b"orig")
    assert run(root, "intake", "--all") == 0
    assert run(root, "reject", "ahri") == 2


# ---------------------------------------------------------------- save-working

def test_save_working_adopt(root: Path):
    _drop(root, "ahri.png", b"orig")
    assert run(root, "intake", "--all") == 0
    scratch = root / "1.First Pass Scratch" / "ahri"
    (scratch / "export from editor.png").write_bytes(b"edited-bytes")
    assert run(root, "save-working", "ahri", "--adopt") == 0
    assert (scratch / "ahri_firstworking_01.png").read_bytes() == b"edited-bytes"
    assert not (scratch / "export from editor.png").exists()


def test_save_working_records_tool_params(root: Path, tmp_path: Path):
    _drop(root, "ahri.png", b"orig")
    assert run(root, "intake", "--all") == 0
    src = tmp_path / "up.png"
    src.write_bytes(b"upscaled")
    assert run(
        root, "save-working", "ahri", "--from", str(src),
        "--tool", "realesrgan", "--params", '{"scale": 4}',
    ) == 0
    man = json.loads(
        (root / "1.First Pass Scratch" / "ahri" / "manifest.json").read_text()
    )
    t = man["transitions"][-1]
    assert t["tool"] == "realesrgan" and t["params"] == {"scale": 4}
    assert t["sha256_out"] == hashlib.sha256(b"upscaled").hexdigest()


# ---------------------------------------------------------------- dry-run

def test_dry_run_mutates_nothing(root: Path, tmp_path: Path, capsys):
    _drop(root, "ahri.png", b"orig")
    before = _tree_digest(root.parent)
    assert run(root, "intake", "--all", "--dry-run") == 0
    assert _tree_digest(root.parent) == before
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    # now a real intake, then dry-run the rest of the surface
    assert run(root, "intake", "--all") == 0
    src = tmp_path / "e.png"
    src.write_bytes(b"e")
    assert run(root, "save-working", "ahri", "--from", str(src)) == 0
    assert run(root, "submit", "ahri") == 0
    before = _tree_digest(root.parent)
    for args in (
        ["approve", "ahri", "--dry-run"],
        ["reject", "ahri", "--dry-run"],
    ):
        assert run(root, *args) == 0
        assert _tree_digest(root.parent) == before


# ---------------------------------------------------------------- recovery

def test_crash_recovery_resumes_approved_pending_move(root: Path, tmp_path: Path):
    _drop(root, "ahri.png", b"orig")
    assert run(root, "intake", "--all") == 0
    _edit(root, "ahri", "first", b"w1", tmp_path)
    scratch = root / "1.First Pass Scratch" / "ahri"
    # simulate crash right after approve step 1 (needauth renamed to done)
    (scratch / "ahri_firstneedauth.png").rename(scratch / "ahri_firstdone.png")
    rc = lw.main(["--root", str(root), "scan"])
    assert rc == 1  # anomaly / resumable state reported
    assert run(root, "scan", "--fix-resumable") == 0
    done2 = root / "2.First Pass Done" / "ahri"
    assert _milestones(done2) == {"ahri_firstinitial.png", "ahri_firstdone.png"}
    assert not scratch.exists()


def test_scan_gc_stale_part_files(root: Path):
    _drop(root, "ahri.png", b"orig")
    assert run(root, "intake", "--all") == 0
    scratch = root / "1.First Pass Scratch" / "ahri"
    part = scratch / "ahri_firstworking_01.png.part"
    part.write_bytes(b"truncated")
    old = time.time() - 90000  # > 1 day
    os.utime(part, (old, old))
    assert lw.main(["--root", str(root), "scan"]) == 1
    assert run(root, "scan", "--fix-resumable") == 0
    assert not part.exists()


def test_gc_only_after_hash_verify(root: Path):
    # STALE_DONE where Done2 holds content NOT present in Done4: GC must refuse
    done2 = root / "2.First Pass Done" / "ahri"
    done4 = root / "4.Cleaning Done" / "ahri"
    done2.mkdir()
    done4.mkdir()
    (done2 / "ahri_firstinitial.png").write_bytes(b"AAA")
    (done2 / "ahri_firstdone.png").write_bytes(b"DIVERGED")
    (done4 / "ahri_firstinitial.png").write_bytes(b"AAA")
    (done4 / "ahri_cleaninitial.png").write_bytes(b"BBB")
    (done4 / "ahri_cleandone.png").write_bytes(b"CCC")
    assert lw.main(["--root", str(root), "scan", "--fix-resumable"]) == 1
    assert done2.exists()  # refused: ahri_firstdone content missing downstream
    # now make it verifiable
    (done2 / "ahri_firstdone.png").write_bytes(b"BBB")
    assert run(root, "scan", "--fix-resumable") == 0
    assert not done2.exists()


# ---------------------------------------------------------------- residue + locks

def test_scratch_residue_defers_gc(root: Path, tmp_path: Path):
    _drop(root, "ahri.png", b"orig")
    assert run(root, "intake", "--all") == 0
    _edit(root, "ahri", "first", b"w1", tmp_path)
    scratch = root / "1.First Pass Scratch" / "ahri"
    (scratch / "ahri-edit.psd").write_bytes(b"photoshop-sidecar")
    assert run(root, "approve", "ahri") == 0  # approval completes
    assert (root / "2.First Pass Done" / "ahri" / "ahri_firstdone.png").is_file()
    assert scratch.exists()  # folder kept, residue preserved
    assert (scratch / "ahri-edit.psd").is_file()


def test_lock_blocks_second_writer(root: Path, tmp_path: Path):
    _drop(root, "ahri.png", b"orig")
    assert run(root, "intake", "--all") == 0
    scratch = root / "1.First Pass Scratch" / "ahri"
    (scratch / ".lw.lock").write_text(
        json.dumps({"pid": os.getpid(), "ts": time.time()})
    )
    src = tmp_path / "e.png"
    src.write_bytes(b"e")
    assert run(root, "save-working", "ahri", "--from", str(src)) == 2


# ---------------------------------------------------------------- end review

def test_end_review_reject_demotes_to_last_scratch(root: Path, tmp_path: Path):
    _walk_to_end_review(root, tmp_path)
    assert run(root, "reject", "ahri", "--stage", "last") == 0
    scratch7 = root / "7.Last Scratch" / "ahri"
    assert (scratch7 / "ahri_lastworking_01.png").is_file()
    assert not (scratch7 / "ahri_lastdone.png").exists()
    assert not (root / "8.End Review" / "ahri").exists()
    assert _milestones(scratch7) >= {
        "ahri_firstinitial.png", "ahri_cleaninitial.png",
        "ahri_finalinitial.png", "ahri_lastinitial.png",
    }


def test_finalize_without_deliver_touches_nothing_outside(root: Path, tmp_path: Path):
    _walk_to_end_review(root, tmp_path)
    deliver_dir = tmp_path / "pictures"
    deliver_dir.mkdir()
    assert run(root, "finalize", "ahri") == 0
    assert list(deliver_dir.iterdir()) == []


def test_finalize_deliver_sequential(root: Path, tmp_path: Path):
    _walk_to_end_review(root, tmp_path)
    deliver_dir = tmp_path / "pictures"
    deliver_dir.mkdir()
    (deliver_dir / "001.png").write_bytes(b"x")
    (deliver_dir / "003.png").write_bytes(b"y")
    review_hash = _sha(root / "8.End Review" / "ahri" / "ahri_lastdone.png")
    assert run(
        root, "finalize", "ahri", "--deliver", str(deliver_dir),
        "--rename-sequential",
    ) == 0
    assert _sha(deliver_dir / "002.png") == review_hash
    assert not list(deliver_dir.glob("*.part"))
    man = json.loads(
        (root / "9.Image Backup" / "ahri" / "manifest.json").read_text()
    )
    assert man["delivered_as"] == "002.png"


def test_finalize_deliver_named(root: Path, tmp_path: Path):
    _walk_to_end_review(root, tmp_path, slug="jinx")
    deliver_dir = tmp_path / "pictures"
    deliver_dir.mkdir()
    assert run(root, "finalize", "jinx", "--deliver", str(deliver_dir)) == 0
    assert (deliver_dir / "jinx.png").is_file()


# ---------------------------------------------------------------- verify

def test_verify_detects_corruption(root: Path, tmp_path: Path):
    _drop(root, "ahri.png", b"orig")
    assert run(root, "intake", "--all") == 0
    _edit(root, "ahri", "first", b"w1", tmp_path)
    assert run(root, "approve", "ahri") == 0
    target = root / "2.First Pass Done" / "ahri" / "ahri_firstdone.png"
    target.write_bytes(b"BITFLIP")
    assert run(root, "verify", "ahri") == 3
    # verify never mutates
    assert target.read_bytes() == b"BITFLIP"


def test_verify_clean_tree_passes(root: Path, tmp_path: Path):
    _drop(root, "ahri.png", b"orig")
    assert run(root, "intake", "--all") == 0
    assert run(root, "verify", "--all") == 0
