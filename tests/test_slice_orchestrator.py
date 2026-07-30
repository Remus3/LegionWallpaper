"""A crashed headless run must be able to tell committed work from work to redo.

The manifest is the only thing that survives an API 400, a socket drop, or a
cascade-cancel, so the two failure modes it exists to prevent are both tested
here as guards rather than as happy paths:

  1. `init` over a manifest that still holds non-committed slices would erase
     the record of what was already committed - the exact data loss the file
     exists to stop. It must refuse.
  2. A consumer polling mid-write must never see a half-written manifest, so
     the target file is never opened for writing in place; a sibling tmp is
     written and then replaced (CLAUDE.md atomic-write hard rule).

Every test routes writes through an explicit --manifest under tmp_path. Nothing
in this file may touch the live ops/runtime/slice_manifest.json - a test that
clobbered the real manifest would destroy a running headless run's checkpoint.
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
    """Two levels deep on purpose: proves the ops/runtime mkdir actually runs."""
    return tmp_path / "ops" / "runtime" / "slice_manifest.json"


def _run(manifest, *argv):
    return so.main([*argv, "--manifest", str(manifest)])


def _load(manifest):
    return json.loads(Path(manifest).read_text(encoding="utf-8"))


def _init(manifest, run_id="2026-07-29-01", head="deadbee"):
    return _run(manifest, "init", "--run-id", run_id, "--head", head)


def test_default_manifest_is_the_documented_live_path():
    # The skill's documented invocations omit --manifest, so the default has to
    # be the path the orchestrator and the wrapper both agree on.
    assert so.DEFAULT_MANIFEST == ROOT / "ops" / "runtime" / "slice_manifest.json"


def test_init_creates_a_schema_versioned_manifest(tmp_path):
    target = _target(tmp_path)
    assert _init(target, run_id="2026-07-29-07", head="abc1234") == 0
    data = _load(target)
    assert data["schema"] == so.SCHEMA
    assert data["run_id"] == "2026-07-29-07"
    assert data["head"] == "abc1234"
    assert data["slices"] == []


def test_add_appends_pending_slices_with_parsed_file_lists(tmp_path):
    target = _target(tmp_path)
    _init(target)
    assert _run(target, "add", "--id", "S1", "--title", "run infra",
                "--files", "tools/a.py,tests/test_a.py") == 0
    assert _run(target, "add", "--id", "S2", "--title", "no files") == 0
    slices = _load(target)["slices"]
    assert [s["id"] for s in slices] == ["S1", "S2"]
    assert slices[0]["status"] == "pending"
    assert slices[0]["title"] == "run infra"
    assert slices[0]["files"] == ["tools/a.py", "tests/test_a.py"]
    assert slices[1]["files"] == []


def test_add_refuses_a_duplicate_slice_id(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _run(target, "add", "--id", "S1", "--title", "first")
    assert _run(target, "add", "--id", "S1", "--title", "second") != 0
    slices = _load(target)["slices"]
    assert len(slices) == 1
    assert slices[0]["title"] == "first"


def test_add_without_a_manifest_fails_rather_than_inventing_one(tmp_path):
    target = _target(tmp_path)
    assert _run(target, "add", "--id", "S1", "--title", "orphan") != 0
    assert not target.exists()


@pytest.mark.parametrize("status", so.STATUSES)
def test_every_status_round_trips_through_set(tmp_path, status):
    target = _target(tmp_path)
    _init(target)
    _run(target, "add", "--id", "S1", "--title", "t")
    assert _run(target, "set", "--id", "S1", "--status", status,
                "--commit", "cafe123", "--note", "why it moved") == 0
    entry = _load(target)["slices"][0]
    assert entry["status"] == status
    assert entry["commit"] == "cafe123"
    assert entry["note"] == "why it moved"


@pytest.mark.parametrize("bogus", ["done", "COMMITTED", "", "pending ", "in-progress"])
def test_set_rejects_an_unknown_status_without_storing_it(tmp_path, bogus):
    target = _target(tmp_path)
    _init(target)
    _run(target, "add", "--id", "S1", "--title", "t")
    assert _run(target, "set", "--id", "S1", "--status", bogus) != 0
    assert _load(target)["slices"][0]["status"] == "pending"


def test_set_rejects_an_unknown_slice_id(tmp_path):
    target = _target(tmp_path)
    _init(target)
    _run(target, "add", "--id", "S1", "--title", "t")
    assert _run(target, "set", "--id", "S9", "--status", "verified") != 0


@pytest.mark.parametrize("status", [s for s in so.STATUSES if s != "committed"])
def test_resume_lists_every_non_committed_status_and_hides_committed(
        tmp_path, status, capsys):
    target = _target(tmp_path)
    _init(target)
    _run(target, "add", "--id", "KEEP", "--title", "already durable")
    _run(target, "add", "--id", "REDO", "--title", "needs redoing")
    _run(target, "set", "--id", "KEEP", "--status", "committed", "--commit", "f00")
    _run(target, "set", "--id", "REDO", "--status", status)
    capsys.readouterr()
    assert _run(target, "resume") == 0
    out = capsys.readouterr().out
    assert "REDO" in out
    assert "KEEP" not in out


def test_resume_is_silent_and_exits_zero_when_nothing_remains(tmp_path, capsys):
    target = _target(tmp_path)
    _init(target)
    _run(target, "add", "--id", "S1", "--title", "t")
    _run(target, "set", "--id", "S1", "--status", "committed", "--commit", "f00")
    capsys.readouterr()
    assert _run(target, "resume") == 0
    assert "S1" not in capsys.readouterr().out


def test_resume_exits_zero_with_no_manifest_at_all(tmp_path, capsys):
    # A first-ever run has no manifest; resume is the wrapper's unconditional
    # first call, so a missing file is a normal state, not an error.
    assert _run(_target(tmp_path), "resume") == 0
    assert capsys.readouterr().out.strip() == ""


def test_init_refuses_over_a_manifest_with_non_committed_slices(tmp_path, capsys):
    target = _target(tmp_path)
    _init(target, run_id="first-run", head="aaa")
    _run(target, "add", "--id", "S1", "--title", "in flight")
    _run(target, "set", "--id", "S1", "--status", "committed", "--commit", "f00")
    _run(target, "add", "--id", "S2", "--title", "not yet committed")
    before = _load(target)
    capsys.readouterr()
    assert _init(target, run_id="second-run", head="bbb") != 0
    combined = capsys.readouterr()
    assert "S2" in (combined.out + combined.err)
    assert _load(target) == before


def test_init_force_overrides_the_refusal(tmp_path):
    target = _target(tmp_path)
    _init(target, run_id="first-run", head="aaa")
    _run(target, "add", "--id", "S1", "--title", "in flight")
    assert _run(target, "init", "--run-id", "second-run", "--head", "bbb",
                "--force") == 0
    data = _load(target)
    assert data["run_id"] == "second-run"
    assert data["slices"] == []


def test_init_proceeds_when_every_prior_slice_committed(tmp_path):
    target = _target(tmp_path)
    _init(target, run_id="first-run", head="aaa")
    _run(target, "add", "--id", "S1", "--title", "done")
    _run(target, "set", "--id", "S1", "--status", "committed", "--commit", "f00")
    assert _init(target, run_id="second-run", head="bbb") == 0
    assert _load(target)["run_id"] == "second-run"


def test_status_renders_every_slice(tmp_path, capsys):
    target = _target(tmp_path)
    _init(target, run_id="2026-07-29-09", head="abc1234")
    _run(target, "add", "--id", "S1", "--title", "alpha")
    _run(target, "add", "--id", "S2", "--title", "beta")
    _run(target, "set", "--id", "S1", "--status", "committed", "--commit", "f00d")
    capsys.readouterr()
    assert _run(target, "status") == 0
    out = capsys.readouterr().out
    for token in ("2026-07-29-09", "S1", "alpha", "S2", "beta", "committed", "f00d"):
        assert token in out


@pytest.mark.parametrize("argv", [
    ("init", "--run-id", "r", "--head", "h"),
    ("add", "--id", "S1", "--title", "t"),
    ("set", "--id", "S1", "--status", "verified"),
])
def test_no_subcommand_ever_writes_the_target_in_place(tmp_path, monkeypatch, argv):
    """The atomic contract: write a tmp sibling, then replace. Never the target.

    Asserted by spying on Path.write_text / Path.replace rather than by racing a
    reader, because a race that happens to pass proves nothing.
    """
    target = _target(tmp_path)
    if argv[0] != "init":
        _init(target)
        if argv[0] == "set":
            _run(target, "add", "--id", "S1", "--title", "t")

    written = []
    replaced = []
    real_write = Path.write_text
    real_replace = Path.replace

    def spy_write(self, *a, **kw):
        written.append(Path(self))
        return real_write(self, *a, **kw)

    def spy_replace(self, dst):
        replaced.append((Path(self), Path(dst)))
        return real_replace(self, dst)

    monkeypatch.setattr(Path, "write_text", spy_write)
    monkeypatch.setattr(Path, "replace", spy_replace)
    assert _run(target, *argv) == 0
    monkeypatch.undo()

    assert target not in written, "manifest target was written in place"
    assert replaced, "no tmp -> target replace happened"
    assert replaced[-1][1] == target
    assert written[-1] == replaced[-1][0]
    assert list(target.parent.glob("*.tmp")) == [], "tmp file left behind"
    assert _load(target)["schema"] == so.SCHEMA
