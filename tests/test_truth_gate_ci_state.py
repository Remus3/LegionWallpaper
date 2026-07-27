"""check_ci must not report a not-yet-registered run as a run that will never exist.

`gh run list --commit <sha>` returns an empty list for two completely different
commits: one whose changed files are all covered by the workflow's paths-ignore
(no run was ever going to exist), and one that touches code but was pushed
seconds ago (the run is coming, GitHub just has not registered it). Collapsing
both into one status is a false-green - an assertion of "CI is settled" that is
only true in the first case.

Live ground truth this file encodes (probed 2026-07-27 against the real repo):
  d7db23e ROADMAP.md + WAKEUP_NOTES.md + docs/*.md -> gh run list == []
  549f52c ops/loop/executor.py + tests/*.py        -> one completed run
Root-level .md is therefore matched by the workflow's '**/*.md', which pins the
glob semantics: '**' matches ZERO or more leading path segments.

Every subprocess boundary is stubbed - no network, no real `gh`, and no
dependency on the repo's live git history for any asserted value.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import truth_gate  # noqa: E402

REAL_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


class _Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _stub(changed=(), runs=(), gh_rc=0, gh_stderr="", changed_rc=0):
    """One stub for every subprocess check_ci makes, dispatched on argv.

    The leading blank line on the git side is deliberate: `git show
    --pretty=format:` emits one, so the parser has to tolerate it.
    """
    def run(cmd, *args, **kwargs):
        if cmd[0] == "git" and "rev-parse" in cmd:
            return _Result(0, "resolvedheadsha\n")
        if cmd[0] == "git":
            return _Result(changed_rc, "\n" + "\n".join(changed) + "\n")
        if cmd[0] == "gh":
            return _Result(gh_rc, json.dumps(list(runs)), gh_stderr)
        raise AssertionError(f"unexpected command: {cmd}")
    return run


@pytest.fixture()
def stub(monkeypatch):
    def install(**kwargs):
        monkeypatch.setattr(truth_gate.subprocess, "run", _stub(**kwargs))
    return install


# --- the ambiguity itself ------------------------------------------------
#
# These drive a STUBBED filtered workflow rather than the repo's live ci.yml.
# They used to read the real file, which meant they were asserting LW's current
# CI configuration and not the logic - so when ci.yml dropped its paths-ignore
# on 2026-07-27 they went red without anything being wrong with check_ci. A test
# that breaks when a config it does not own changes was testing the wrong thing.
# The not-evaluated branch is unreachable in this repo today and still has to be
# correct, because a filter re-added anywhere revives it.

def _filtered(tmp_path, glob="**/*.md"):
    wf = tmp_path / "ci.yml"
    wf.write_text(
        "name: ci\n"
        "on:\n"
        "  push:\n"
        "    branches: [main]\n"
        "    paths-ignore:\n"
        f"      - '{glob}'\n"
        "  pull_request:\n"
        "    branches: [main]\n"
        "    paths-ignore:\n"
        f"      - '{glob}'\n"
        "jobs: {}\n", encoding="utf-8")
    return wf


def test_docs_only_and_code_commits_are_distinguishable(stub, tmp_path):
    """The regression: two commits with opposite meanings must not read alike."""
    wf = _filtered(tmp_path)
    stub(changed=["ROADMAP.md", "docs/LEDGER.md"], runs=[])
    docs = truth_gate.check_ci("aaaa111", workflow=wf)
    stub(changed=["tools/truth_gate.py"], runs=[])
    code = truth_gate.check_ci("bbbb222", workflow=wf)
    assert docs["status"] != code["status"], (
        "a docs-only commit (no run will EVER exist) and a code commit whose "
        "run has not registered yet both report {!r}".format(docs["status"]))


def test_docs_only_commit_is_not_evaluated(stub, tmp_path):
    stub(changed=["ROADMAP.md", "docs/LEDGER.md"], runs=[])
    assert truth_gate.check_ci(
        "aaaa111", workflow=_filtered(tmp_path))["status"] == "not-evaluated"


def test_code_commit_without_a_run_yet_is_queued(stub):
    stub(changed=["tools/truth_gate.py"], runs=[])
    assert truth_gate.check_ci("bbbb222")["status"] == "queued"


def test_mixed_docs_and_code_commit_is_queued(stub):
    """One non-ignored file re-arms the whole workflow."""
    stub(changed=["ROADMAP.md", "ops/loop/executor.py"], runs=[])
    assert truth_gate.check_ci("cccc333")["status"] == "queued"


def test_root_level_markdown_is_covered_by_the_double_star_glob(stub, tmp_path):
    """'**/*.md' matches ROADMAP.md - measured against GitHub, not assumed."""
    stub(changed=["WAKEUP_NOTES.md"], runs=[])
    assert truth_gate.check_ci(
        "dddd444", workflow=_filtered(tmp_path))["status"] == "not-evaluated"


# --- conservative fallbacks: the pessimistic answer is always "queued" ----

def test_unknowable_file_list_is_queued(stub):
    """A merge commit lists no files under --name-only."""
    stub(changed=[], runs=[])
    assert truth_gate.check_ci("eeee555")["status"] == "queued"


def test_failed_git_show_is_queued(stub):
    stub(changed=["ROADMAP.md"], runs=[], changed_rc=128)
    assert truth_gate.check_ci("ffff666")["status"] == "queued"


def test_missing_workflow_is_queued(stub, tmp_path):
    stub(changed=["ROADMAP.md"], runs=[])
    got = truth_gate.check_ci("aaaa777", workflow=tmp_path / "absent.yml")
    assert got["status"] == "queued"


def test_unparseable_workflow_is_queued(stub, tmp_path):
    wf = tmp_path / "ci.yml"
    wf.write_text("this file is not a workflow at all\n", encoding="utf-8")
    stub(changed=["ROADMAP.md"], runs=[])
    assert truth_gate.check_ci("bbbb888", workflow=wf)["status"] == "queued"


def test_trigger_without_paths_ignore_is_queued(stub, tmp_path):
    """An unfiltered pull_request trigger means the run happens regardless."""
    wf = tmp_path / "ci.yml"
    wf.write_text(
        "name: ci\n"
        "on:\n"
        "  push:\n"
        "    branches: [main]\n"
        "    paths-ignore:\n"
        "      - '**/*.md'\n"
        "  pull_request:\n"
        "    branches: [main]\n"
        "jobs: {}\n", encoding="utf-8")
    stub(changed=["ROADMAP.md"], runs=[])
    assert truth_gate.check_ci("cccc999", workflow=wf)["status"] == "queued"


def test_workflow_paths_ignore_is_read_not_hardcoded(stub, tmp_path):
    """Change the glob in the workflow and the verdict must follow it."""
    wf = tmp_path / "ci.yml"
    wf.write_text(
        "name: ci\n"
        "on:\n"
        "  push:\n"
        "    paths-ignore:\n"
        "      - 'docs/**'\n"
        "  pull_request:\n"
        "    paths-ignore:\n"
        "      - 'docs/**'\n"
        "jobs: {}\n", encoding="utf-8")
    stub(changed=["docs/LEDGER.md"], runs=[])
    assert truth_gate.check_ci("dddd000", workflow=wf)["status"] == "not-evaluated"
    stub(changed=["ROADMAP.md"], runs=[])
    assert truth_gate.check_ci("dddd001", workflow=wf)["status"] == "queued"


def test_real_workflow_declares_no_path_filter():
    """Inverted 2026-07-27: ci.yml no longer skips docs-only pushes.

    The old assertion pinned `paths-ignore: ['**/*.md']` and its docstring said
    that if ci.yml ever dropped the filter, the skip logic must go too. The
    filter is gone - guards that read tracked .md off disk were being skipped by
    the exact commits most likely to break them, which RC demonstrated twice in
    one day.

    The skip LOGIC deliberately stays. It is not dead weight: `check_ci` models
    GitHub's behaviour correctly, is exercised by the 20-odd tests above with a
    stubbed workflow, and with no globs declared it simply never returns
    `not-evaluated` - every unknown falls to `queued`, which is the safe
    direction it was built to fail in. Deleting it would mean a filter re-added
    later silently reproduces the exact ambiguity f1 item 12 existed to remove.
    This test is now the tripwire for that: re-adding a filter turns it red and
    forces the decision to be explicit.
    """
    events = truth_gate.parse_paths_ignore(
        REAL_WORKFLOW.read_text(encoding="utf-8"))
    for ev in ("push", "pull_request"):
        assert events.get(ev) == [], (
            f"ci.yml declares paths-ignore on {ev} again. Docs-only pushes "
            f"would stop running the guards that read docs off disk. If this "
            f"is intended, say so here and re-justify check_ci's "
            f"not-evaluated branch, which this repo currently cannot reach.")
    assert events.get("schedule") == []


# --- pre-existing behaviour must survive ---------------------------------

def test_pending_run(stub):
    stub(changed=["tools/truth_gate.py"],
         runs=[{"status": "in_progress", "conclusion": None, "name": "ci"}])
    assert truth_gate.check_ci("aaab111")["status"] == "pending"


def test_success_run(stub):
    stub(changed=["tools/truth_gate.py"],
         runs=[{"status": "completed", "conclusion": "success", "name": "ci"}])
    assert truth_gate.check_ci("aaab222")["status"] == "success"


def test_failure_run(stub):
    stub(changed=["tools/truth_gate.py"],
         runs=[{"status": "completed", "conclusion": "failure", "name": "ci"}])
    assert truth_gate.check_ci("aaab333")["status"] == "failure"


def test_gh_missing_is_unavailable(stub):
    stub(changed=["tools/truth_gate.py"], runs=[], gh_rc=1, gh_stderr="no gh")
    got = truth_gate.check_ci("aaab444")
    assert got["status"] == "unavailable"
    assert got["detail"] == "no gh"


def test_head_is_resolved_to_a_sha(stub):
    stub(changed=["tools/truth_gate.py"],
         runs=[{"status": "completed", "conclusion": "success", "name": "ci"}])
    assert truth_gate.check_ci("HEAD")["sha"] == "resolvedheadsha"


# --- reconcile: the new statuses inform, they never block ----------------

_GREEN_SUITE = {"passed": 7, "failed": 0, "errors": 0, "skipped": 0,
                "no_tests_ran": False, "exit_code": 0}


def _reconcile_with(ci_status):
    return truth_gate.reconcile({"run_id": "r"}, dict(_GREEN_SUITE), {},
                                {"clean": True, "dirty_files": [], "head": "x"},
                                {"status": ci_status, "sha": "s", "runs": []})


@pytest.mark.parametrize("status", ["queued", "not-evaluated", "pending",
                                    "success", "unavailable", "skipped"])
def test_reconcile_proceeds_on_every_non_failure_status(status):
    """Blocking on GitHub API lag would wedge an unattended headless run."""
    report = _reconcile_with(status)
    assert report["verdict"] == "PROCEED"
    assert report["global_discrepancies"] == []


def test_reconcile_still_refuses_on_ci_failure():
    report = _reconcile_with("failure")
    assert report["verdict"] == "REFUSE"


def test_reconcile_reports_the_ci_status_verbatim():
    assert _reconcile_with("not-evaluated")["ci"]["status"] == "not-evaluated"
