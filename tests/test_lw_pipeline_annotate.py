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
import os
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


@pytest.fixture(autouse=True)
def _fast_gate(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(lw, "PROBE_SECONDS", 0.0)


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


# ------------------------------------------------- approval over a gate verdict
#
# ROADMAP legacy-audit-backfill (code half): an approval over a FAIL verdict was
# byte-identical in the manifest to an approval over a clean PASS, so the audit
# trail could not answer "was this approved despite its own gate saying no?".
# Approve is still ALLOWED to override - it is an operator judgement - but the
# record must name the override. Three outcomes must stay distinguishable:
# clean pass, override, and no-audit-recorded (the legacy pre-audit case).

PASS_AUDIT = {"gate": "G1", "verdict": "PASS", "reasons": []}
FAIL_AUDIT = {"gate": "G1", "verdict": "FAIL",
              "reasons": ["msssim 0.81 < fail 0.90"]}
FLAG_AUDIT = {"gate": "G1", "verdict": "FLAG",
              "reasons": ["halo_pct 0.0711 > flag 0.05"]}


def _drop(root: Path, name: str, content: bytes = b"fake-image-bytes") -> Path:
    p = root / "0.Originals" / name
    p.write_bytes(content)
    old = p.stat().st_mtime - 120
    os.utime(p, (old, old))
    return p


def _submit_stage(root: Path, tmp_path: Path, slug: str, stage: str) -> None:
    src = tmp_path / f"{slug}-{stage}.png"
    src.write_bytes(b"edited-" + stage.encode())
    assert run(root, "save-working", slug, "--from", str(src)) == 0
    assert run(root, "submit", slug) == 0


def _needauth_in_first(root: Path, tmp_path: Path, slug: str = "ahri") -> Path:
    _drop(root, f"{slug}.png", b"orig-" + slug.encode())
    assert run(root, "intake", "--all") == 0
    _submit_stage(root, tmp_path, slug, "first")
    return root / "1.First Pass Scratch" / slug


def _gate(root: Path, slug: str, audit: dict) -> None:
    """Record a gate verdict the way tools/lw_first_pass.py does."""
    assert run(root, "annotate", slug, "--metrics", json.dumps(audit),
               "--tool", "g1gate") == 0


def _approval(folder: Path, op: str) -> dict:
    """The `approval` record on the newest transition named `op`."""
    for t in reversed(_manifest(folder)["transitions"]):
        if t["op"] == op:
            return (t.get("audit") or {}).get("approval")
    raise AssertionError(f"no {op} transition under {folder}")


def test_approve_over_clean_pass_records_a_clean_pass(root: Path, tmp_path: Path):
    _needauth_in_first(root, tmp_path)
    _gate(root, "ahri", PASS_AUDIT)
    assert run(root, "approve", "ahri") == 0
    assert _approval(root / "2.First Pass Done" / "ahri", "APPROVE_FIRST") == {
        "gate_check": "pass", "override": False, "gate": "G1",
        "verdict": "PASS", "reasons": [], "blocking_flags": [],
    }


def test_approve_over_fail_records_the_override(root: Path, tmp_path: Path):
    _needauth_in_first(root, tmp_path)
    _gate(root, "ahri", FAIL_AUDIT)
    assert run(root, "approve", "ahri") == 0  # still allowed, by design
    assert _approval(root / "2.First Pass Done" / "ahri", "APPROVE_FIRST") == {
        "gate_check": "override", "override": True, "gate": "G1",
        "verdict": "FAIL", "reasons": ["msssim 0.81 < fail 0.90"],
        "blocking_flags": [],
    }


def test_approve_over_flag_with_reasons_records_the_override(
        root: Path, tmp_path: Path):
    _needauth_in_first(root, tmp_path)
    _gate(root, "ahri", FLAG_AUDIT)
    assert run(root, "approve", "ahri") == 0
    rec = _approval(root / "2.First Pass Done" / "ahri", "APPROVE_FIRST")
    assert rec["gate_check"] == "override"
    assert rec["override"] is True
    assert rec["verdict"] == "FLAG"
    assert rec["reasons"] == ["halo_pct 0.0711 > flag 0.05"]


def test_approve_with_no_audit_is_its_own_outcome(root: Path, tmp_path: Path):
    """Legacy pre-audit approvals must not read as 'passed the gate'."""
    _needauth_in_first(root, tmp_path)
    assert run(root, "approve", "ahri") == 0
    assert _approval(root / "2.First Pass Done" / "ahri", "APPROVE_FIRST") == {
        "gate_check": "no_audit", "override": False, "gate": None,
        "verdict": None, "reasons": [], "blocking_flags": [],
    }


# ---- ADR-008: a vision flag blocks a NON-OPERATOR approval -----------------

VISION_FLAG_AUDIT = {"gate": "vision-anat", "verdict": "FLAG",
                     "reasons": ["anat_head_spine"]}


def test_a_tool_actor_cannot_approve_over_a_vision_flag(root: Path, tmp_path: Path):
    _needauth_in_first(root, tmp_path)
    _gate(root, "ahri", VISION_FLAG_AUDIT)
    assert run(root, "approve", "ahri", "--actor", "tool:auto-approve") == 3
    # and NOTHING moved - the refusal happens before the needauth rename, so the
    # slug is not left in the APPROVED_PENDING_MOVE shape for a denied promotion
    assert not (root / "2.First Pass Done" / "ahri").exists()
    assert (root / "1.First Pass Scratch" / "ahri" /
            "ahri_firstneedauth.png").exists()


def test_the_operator_may_still_approve_over_a_vision_flag(root: Path, tmp_path: Path):
    """Operator judgement is never refused; it records as an override."""
    _needauth_in_first(root, tmp_path)
    _gate(root, "ahri", VISION_FLAG_AUDIT)
    assert run(root, "approve", "ahri") == 0
    rec = _approval(root / "2.First Pass Done" / "ahri", "APPROVE_FIRST")
    assert rec["blocking_flags"] == ["anat_head_spine"]
    assert rec["gate_check"] == "override"


def test_a_tool_actor_may_approve_when_no_vision_flag_is_open(
        root: Path, tmp_path: Path):
    _needauth_in_first(root, tmp_path)
    _gate(root, "ahri", PASS_AUDIT)
    assert run(root, "approve", "ahri", "--actor", "tool:auto-approve") == 0


def test_a_vision_reject_is_clamped_to_flag_on_the_way_into_the_manifest(
        root: Path, tmp_path: Path):
    """The reviewer may FLAG, never REJECT - enforced where the audit is
    WRITTEN, so no future reviewer can demote an image by emitting a verdict."""
    _needauth_in_first(root, tmp_path)
    _gate(root, "ahri", {"gate": "vision-anat", "verdict": "REJECT",
                         "reasons": ["anat_head_spine"]})
    folder = root / "1.First Pass Scratch" / "ahri"
    audit = _manifest(folder)["transitions"][-1]["audit"]
    assert audit["verdict"] == "FLAG"
    assert audit["clamped_from"] == "REJECT"


def test_approve_uses_the_most_recent_verdict(root: Path, tmp_path: Path):
    _needauth_in_first(root, tmp_path)
    _gate(root, "ahri", PASS_AUDIT)
    _gate(root, "ahri", FAIL_AUDIT)  # a re-run downgraded it
    assert run(root, "approve", "ahri") == 0
    rec = _approval(root / "2.First Pass Done" / "ahri", "APPROVE_FIRST")
    assert rec["gate_check"] == "override"
    assert rec["verdict"] == "FAIL"


def test_approve_ignores_a_verdict_from_an_earlier_milestone(
        root: Path, tmp_path: Path):
    """A first-pass FAIL must not be re-reported against the cleaning approval."""
    _needauth_in_first(root, tmp_path)
    _gate(root, "ahri", FAIL_AUDIT)
    assert run(root, "approve", "ahri") == 0
    assert run(root, "start-stage", "ahri") == 0
    _submit_stage(root, tmp_path, "ahri", "clean")
    assert run(root, "approve", "ahri") == 0
    rec = _approval(root / "4.Cleaning Done" / "ahri", "APPROVE_CLEAN")
    assert rec["gate_check"] == "no_audit"
    assert rec["verdict"] is None


def test_resumed_approval_records_the_override_too(root: Path, tmp_path: Path):
    """APPROVED_PENDING_MOVE recovery is an approval completing - same record."""
    scratch = _needauth_in_first(root, tmp_path)
    _gate(root, "ahri", FAIL_AUDIT)
    # crash right after approve step 1 (needauth renamed to done, no move yet)
    (scratch / "ahri_firstneedauth.png").rename(scratch / "ahri_firstdone.png")
    assert run(root, "scan", "--fix-resumable") == 0
    rec = _approval(root / "2.First Pass Done" / "ahri", "RECOVER")
    assert rec["gate_check"] == "override"
    assert rec["verdict"] == "FAIL"


def _walk_to_end_review(root: Path, tmp_path: Path, last_audit=None,
                        slug: str = "ahri") -> None:
    _drop(root, f"{slug}.png", b"orig-" + slug.encode())
    assert run(root, "intake", "--all") == 0
    for stage in ("first", "clean", "final", "last"):
        if stage != "first":
            assert run(root, "start-stage", slug) == 0
        _submit_stage(root, tmp_path, slug, stage)
        if stage == "last" and last_audit is not None:
            _gate(root, slug, last_audit)
        assert run(root, "approve", slug) == 0


def test_finalize_over_fail_records_the_override(root: Path, tmp_path: Path):
    _walk_to_end_review(root, tmp_path, last_audit=FAIL_AUDIT)
    assert run(root, "finalize", "ahri") == 0
    rec = _approval(root / "9.Image Backup" / "ahri", "FINALIZE")
    assert rec["gate_check"] == "override"
    assert rec["verdict"] == "FAIL"


def test_finalize_keeps_the_supplied_audit_json_alongside_the_record(
        root: Path, tmp_path: Path):
    _walk_to_end_review(root, tmp_path, last_audit=PASS_AUDIT)
    ajson = tmp_path / "end_review.json"
    ajson.write_text(json.dumps({"vision_2afc": "win"}), encoding="utf-8")
    assert run(root, "finalize", "ahri", "--audit-json", str(ajson)) == 0
    backup = root / "9.Image Backup" / "ahri"
    audit = [t for t in _manifest(backup)["transitions"]
             if t["op"] == "FINALIZE"][-1]["audit"]
    assert audit["vision_2afc"] == "win"
    assert audit["approval"]["gate_check"] == "pass"


def test_finalize_does_not_clobber_a_supplied_approval_key(
        root: Path, tmp_path: Path):
    _walk_to_end_review(root, tmp_path, last_audit=PASS_AUDIT)
    ajson = tmp_path / "end_review.json"
    ajson.write_text(json.dumps({"approval": "operator says ship it"}),
                     encoding="utf-8")
    assert run(root, "finalize", "ahri", "--audit-json", str(ajson)) == 0
    backup = root / "9.Image Backup" / "ahri"
    audit = [t for t in _manifest(backup)["transitions"]
             if t["op"] == "FINALIZE"][-1]["audit"]
    assert audit["approval"]["gate_check"] == "pass"
    assert audit["supplied_approval"] == "operator says ship it"


def test_finalize_nests_a_non_dict_audit_payload(root: Path, tmp_path: Path):
    _walk_to_end_review(root, tmp_path, last_audit=PASS_AUDIT)
    ajson = tmp_path / "end_review.json"
    ajson.write_text(json.dumps(["2afc-a", "2afc-b"]), encoding="utf-8")
    assert run(root, "finalize", "ahri", "--audit-json", str(ajson)) == 0
    backup = root / "9.Image Backup" / "ahri"
    audit = [t for t in _manifest(backup)["transitions"]
             if t["op"] == "FINALIZE"][-1]["audit"]
    assert audit["end_review"] == ["2afc-a", "2afc-b"]
    assert audit["approval"]["gate_check"] == "pass"
