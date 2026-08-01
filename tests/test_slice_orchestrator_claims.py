"""The file-claim table: disjointness enforced by the manifest, not by hand.

LW dispatches N parallel worktree agents on "disjoint file sets" and today that
disjointness is asserted by a human reading a directive (f1-phase6 queue item 7).
Nothing checks it, so two agents can be handed the same file and the sole merger
finds out at merge time, after both have spent their run.

These tests pin the primitive that closes that: an agent CLAIMS its files before
it starts, a claim that overlaps a live one is REFUSED, and the refusal is
all-or-nothing so a partially-conflicting agent never half-starts.

The conflict cases are where the bugs live, so they carry the weight here:

  1. `tools/x.py` and `tools\\x.py` and `./tools/x.py` are ONE file. LW has been
     bitten twice by path-separator identity (three ~/.claude.json keys for one
     directory; red-handed's subdirectory drop), and a missed conflict silently
     loses an agent's edits while a false conflict merely refuses. The safe
     direction is to over-collide, so comparison is case-insensitive too.
  2. A directory claim contains the files under it: `tools` conflicts with
     `tools/x.py`. Segment-wise, so `tool` does NOT conflict with `tools/x.py`.
  3. Releasing is holder-only. An agent that could release another's claim
     rebuilds the exact hole the table exists to close.

Every test routes writes through an explicit --manifest under tmp_path; nothing
here may touch the live ops/runtime/slice_manifest.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import slice_orchestrator as so  # noqa: E402


def _target(tmp_path):
    return tmp_path / "ops" / "runtime" / "slice_manifest.json"


def _run(manifest, *argv):
    return so.main([*argv, "--manifest", str(manifest)])


def _load(manifest):
    return json.loads(Path(manifest).read_text(encoding="utf-8"))


def _init(manifest, run_id="2026-08-01-01", head="deadbee"):
    return _run(manifest, "init", "--run-id", run_id, "--head", head)


# ---------------------------------------------------------------- normalization
@pytest.mark.parametrize("variant", [
    "tools/x.py",
    "tools\\x.py",
    "./tools/x.py",
    ".\\tools\\x.py",
    "tools//x.py",
    "TOOLS/X.PY",
    "  tools/x.py  ",
])
def test_separator_case_and_prefix_variants_are_one_key(variant):
    assert so.normalize_claim_path(variant) == so.normalize_claim_path("tools/x.py")


@pytest.mark.parametrize("bad", [
    "", "   ", None, 42,
    "C:/LegionWallpaper/tools/x.py",     # absolute, drive letter
    "/etc/passwd",                        # absolute, posix
    "../sibling/x.py",                    # escapes the repo
    "tools/../../x.py",                   # escapes after collapsing
])
def test_paths_that_are_not_repo_relative_are_refused_not_guessed(bad):
    assert so.normalize_claim_path(bad) is None


def test_interior_dot_segments_collapse_without_escaping():
    assert so.normalize_claim_path("tools/./sub/../x.py") == so.normalize_claim_path("tools/x.py")


# ---------------------------------------------------------------- absent field
def test_a_manifest_with_no_claims_key_reports_none(tmp_path):
    # Optional-by-contract, exactly like `verdicts`: every manifest written
    # before this existed must stay valid and must NOT read as "claimed".
    target = _target(tmp_path)
    _init(target)
    assert so.get_active_claims(_load(target)) == {}
    assert so.CLAIM_FIELD not in _load(target)


def test_add_does_not_seed_the_claims_key(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _run(target, "add", "--id", "S1", "--title", "t", "--files", "tools/x.py")
    assert so.CLAIM_FIELD not in _load(target)


# ---------------------------------------------------------------- claiming
def test_disjoint_claims_from_two_agents_both_succeed(tmp_path):
    target = _target(tmp_path)
    _init(target)
    assert _run(target, "claim", "--agent", "A1", "--files", "tools/a.py,tools/b.py") == 0
    assert _run(target, "claim", "--agent", "A2", "--files", "tools/c.py") == 0
    active = so.get_active_claims(_load(target))
    assert {k: v["agent"] for k, v in active.items()} == {
        "tools/a.py": "A1", "tools/b.py": "A1", "tools/c.py": "A2"}


def test_overlapping_claim_is_refused(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py")
    assert _run(target, "claim", "--agent", "A2", "--files", "tools/a.py") == 2
    active = so.get_active_claims(_load(target))
    assert active["tools/a.py"]["agent"] == "A1"


def test_overlap_detected_across_separator_and_case_variants(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py")
    assert _run(target, "claim", "--agent", "A2", "--files", "TOOLS\\A.PY") == 2


def test_a_partially_conflicting_claim_takes_NOTHING(tmp_path):
    # All-or-nothing: a half-granted claim would let an agent start on the files
    # it did get, which is the same lost-work failure as no table at all.
    target = _target(tmp_path)
    _init(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py")
    assert _run(target, "claim", "--agent", "A2",
                "--files", "tools/b.py,tools/a.py,tools/c.py") == 2
    active = so.get_active_claims(_load(target))
    assert set(active) == {"tools/a.py"}
    assert "tools/b.py" not in active and "tools/c.py" not in active


def test_reclaiming_your_own_file_is_idempotent(tmp_path):
    target = _target(tmp_path)
    _init(target)
    assert _run(target, "claim", "--agent", "A1", "--files", "tools/a.py") == 0
    assert _run(target, "claim", "--agent", "A1", "--files", "tools/a.py,tools/b.py") == 0
    active = so.get_active_claims(_load(target))
    assert set(active) == {"tools/a.py", "tools/b.py"}
    assert len(_load(target)[so.CLAIM_FIELD]) == 2


def test_a_directory_claim_conflicts_with_a_file_under_it(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools")
    assert _run(target, "claim", "--agent", "A2", "--files", "tools/a.py") == 2


def test_a_file_claim_conflicts_with_a_directory_claim_over_it(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py")
    assert _run(target, "claim", "--agent", "A2", "--files", "tools") == 2


def test_containment_is_segment_wise_not_string_prefix(tmp_path):
    # "tool" is not a parent of "tools/a.py" - a naive startswith would refuse a
    # legitimate claim and teach the operator to bypass the table.
    target = _target(tmp_path)
    _init(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py")
    assert _run(target, "claim", "--agent", "A2", "--files", "tool") == 0
    assert _run(target, "claim", "--agent", "A3", "--files", "tools/a.python") == 0


def test_claim_with_an_unusable_path_refuses_the_whole_claim(tmp_path):
    target = _target(tmp_path)
    _init(target)
    assert _run(target, "claim", "--agent", "A1",
                "--files", "tools/a.py,../escape.py") == 2
    assert so.get_active_claims(_load(target)) == {}


def test_claim_with_no_usable_files_is_an_error_not_a_silent_noop(tmp_path):
    target = _target(tmp_path)
    _init(target)
    assert _run(target, "claim", "--agent", "A1", "--files", "  ,  ") == 2


def test_claim_requires_a_manifest(tmp_path):
    assert _run(_target(tmp_path), "claim", "--agent", "A1", "--files", "a.py") == 2


# ---------------------------------------------------------------- releasing
def test_release_frees_the_file_for_another_agent(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py")
    assert _run(target, "release", "--agent", "A1", "--files", "tools/a.py") == 0
    assert so.get_active_claims(_load(target)) == {}
    assert _run(target, "claim", "--agent", "A2", "--files", "tools/a.py") == 0


def test_release_by_a_non_holder_is_refused_and_changes_nothing(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py")
    assert _run(target, "release", "--agent", "A2", "--files", "tools/a.py") == 2
    active = so.get_active_claims(_load(target))
    assert active["tools/a.py"]["agent"] == "A1"


def test_release_without_files_frees_only_that_agents_claims(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py,tools/b.py")
    _run(target, "claim", "--agent", "A2", "--files", "tools/c.py")
    assert _run(target, "release", "--agent", "A1") == 0
    active = so.get_active_claims(_load(target))
    assert set(active) == {"tools/c.py"}


def test_release_of_an_unheld_file_is_refused(tmp_path):
    target = _target(tmp_path)
    _init(target)
    assert _run(target, "release", "--agent", "A1", "--files", "tools/a.py") == 2


def test_release_is_all_or_nothing(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py")
    _run(target, "claim", "--agent", "A2", "--files", "tools/b.py")
    assert _run(target, "release", "--agent", "A1",
                "--files", "tools/a.py,tools/b.py") == 2
    active = so.get_active_claims(_load(target))
    assert set(active) == {"tools/a.py", "tools/b.py"}


# ---------------------------------------------------------------- record shape
def test_a_claim_records_who_when_and_the_path_as_written(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools\\Sub\\X.py",
         "--slice", "S1", "--note", "worktree wt-a")
    rec = _load(target)[so.CLAIM_FIELD][0]
    assert rec["agent"] == "A1"
    assert rec["path"] == "tools/Sub/X.py"      # normalized for storage
    assert rec["key"] == "tools/sub/x.py"       # folded only for comparison
    assert rec["slice"] == "S1"
    assert rec["note"] == "worktree wt-a"
    assert so.normalize_stamp(rec["at"]) == rec["at"]


def test_claims_survive_a_status_change_on_an_unrelated_slice(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _run(target, "add", "--id", "S1", "--title", "t")
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py")
    _run(target, "set", "--id", "S1", "--status", "committed")
    assert set(so.get_active_claims(_load(target))) == {"tools/a.py"}


def test_claims_are_written_atomically(tmp_path, monkeypatch):
    # Same guard the manifest's other writers carry: a consumer polling mid-write
    # must see old or new, never a truncation.
    target = _target(tmp_path)
    _init(target)
    opened = []
    real_open = Path.open

    def spy(self, *a, **kw):
        # mode arrives positionally from open() and by keyword from write_text;
        # checking only the positional form would make this test pass vacuously.
        mode = str(a[0]) if a else str(kw.get("mode", ""))
        if "w" in mode or "a" in mode:
            opened.append(Path(self))
        return real_open(self, *a, **kw)

    monkeypatch.setattr(Path, "open", spy)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py")
    assert target not in opened


# ---------------------------------------------------------------- listing
def test_claims_subcommand_prints_holders(tmp_path, capsys):
    target = _target(tmp_path)
    _init(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py")
    _run(target, "claim", "--agent", "A2", "--files", "tools/b.py")
    capsys.readouterr()
    assert _run(target, "claims") == 0
    out = capsys.readouterr().out
    assert "tools/a.py" in out and "A1" in out
    assert "tools/b.py" in out and "A2" in out


def test_claims_on_a_manifest_without_the_key_says_none(tmp_path, capsys):
    target = _target(tmp_path)
    _init(target)
    capsys.readouterr()
    assert _run(target, "claims") == 0
    assert "no active claims" in capsys.readouterr().out.lower()


def test_conflict_message_names_the_holder_and_the_file(tmp_path, capsys):
    # The operator's next action is "go look at what A1 is doing", so the refusal
    # has to say who, not just that something clashed.
    target = _target(tmp_path)
    _init(target)
    _run(target, "claim", "--agent", "A1", "--files", "tools/a.py")
    capsys.readouterr()
    _run(target, "claim", "--agent", "A2", "--files", "tools/a.py")
    err = capsys.readouterr().err
    assert "tools/a.py" in err and "A1" in err
