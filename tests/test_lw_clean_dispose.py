"""Tests for tools/lw_clean_dispose.py - gate-driven cleaning disposition.

CI constraint: this module imports lw_clean_pass, which is import-clean on
numpy + PIL + stdlib (see the header of tests/test_lw_clean_pass.py), so every
test here runs everywhere. NOTHING below executes a pipeline command or touches
images/** - the subprocess boundary is monkeypatched or run in --dry-run.

The load-bearing properties: a `qa` verdict NEVER produces a pipeline
transition, a non-zero rc short-circuits the remaining steps (a refusal is
recorded, never forced), and approval is attributed to a non-operator actor so
the ADR-008 rail can see it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_dispose as disp  # noqa: E402


def _argvs(rec):
    return [step["argv"] for step in rec["steps"]]


def test_approve_is_attributed_to_a_non_operator_actor():
    argv = disp.approve_cmd("some-slug")
    assert argv[2:] == ["approve", "some-slug", "--actor", "tool:auto-approve"]


def test_qa_verdict_never_touches_the_pipeline(monkeypatch):
    called = []
    monkeypatch.setattr(disp, "run_cmd", lambda *a, **k: called.append(a))
    rec = disp.drive("slug-a", "qa", "img.png", dry_run=True)
    assert rec["status"] == "queued-qa"
    assert rec["steps"] == []
    assert called == []


def test_clean_verdict_plans_save_working_then_submit_then_approve():
    rec = disp.drive("slug-b", "clean", "C:/img.png", dry_run=True)
    assert rec["status"] == "would-approve"
    verbs = [argv[2] for argv in _argvs(rec)]
    assert verbs == ["save-working", "submit", "approve"]
    save = _argvs(rec)[0]
    assert "--tool" in save and save[save.index("--tool") + 1] == "clean-scan"


def test_auto_verdict_does_not_inpaint_under_dry_run():
    rec = disp.drive("slug-c", "auto", "C:/img.png", dry_run=True)
    assert rec["status"] == "would-inpaint"
    assert rec["steps"] == []


def test_a_refusal_short_circuits_and_is_recorded(monkeypatch):
    def fake(argv, dry_run=False):
        rc = 3 if argv[2] == "submit" else 0
        return {"argv": argv, "rc": rc, "out": "", "err": "refused"}

    monkeypatch.setattr(disp, "run_cmd", fake)
    rec = disp.drive("slug-d", "clean", "C:/img.png")
    assert rec["status"] == "refused"
    assert [argv[2] for argv in _argvs(rec)] == ["save-working", "submit"]


def test_a_failure_short_circuits_before_approve(monkeypatch):
    monkeypatch.setattr(disp, "run_cmd", lambda argv, dry_run=False: {
        "argv": argv, "rc": 1, "out": "", "err": "boom"})
    rec = disp.drive("slug-e", "clean", "C:/img.png")
    assert rec["status"] == "failed"
    assert len(rec["steps"]) == 1


def test_main_honours_only_filter_and_writes_one_row_per_slug(tmp_path):
    triage = tmp_path / "triage.jsonl"
    rows = [{"slug": "s1", "verdict": "clean", "image": "a.png"},
            {"slug": "s2", "verdict": "qa", "image": "b.png"},
            {"slug": "s3", "verdict": "clean", "image": "c.png"}]
    triage.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out = tmp_path / "res.jsonl"
    rc = disp.main(["--triage", str(triage), "--out", str(out),
                    "--only", "clean", "--dry-run"])
    assert rc == 0
    got = [json.loads(ln) for ln in out.read_text(encoding="utf-8").splitlines()]
    assert [r["slug"] for r in got] == ["s1", "s3"]
    assert {r["status"] for r in got} == {"would-approve"}
