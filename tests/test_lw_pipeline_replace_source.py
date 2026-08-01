"""A replaced source must be RECORDED, not have its INTAKE hash rewritten.

The 22 canonical-source swaps (LEDGER 77 + 78) left `scan --verify` reporting
HASH_MISMATCH on 21 of them: each manifest's INTAKE transition still records the
hash of the file that was intaken, while the `_firstinitial` on disk has
legitimately been replaced by the wiki source. The `_firstdone` outputs are
correct; only the bookkeeping is wrong.

Two ways to fix it, and this file pins the one chosen (ROADMAP
wiki-swap-manifest-hash-residue):

  REJECTED - rewrite the INTAKE hash in place. It makes verify green by editing
  history, and every other ledger in this repo is append-only for the same
  reason: the manifest is the provenance record, and a record that silently
  restates what was intaken cannot answer "what did we actually start from".

  CHOSEN - append a REPLACE_SOURCE transition carrying sha256_in (what was
  there) and sha256_out (what replaced it). History grows, verify has a newer
  truth to compare against, and the swap becomes visible instead of invisible.

Which makes the ORDER of transitions load-bearing, so it is tested rather than
inherited from dict-insertion luck: the expected hash for a file is the one from
its LATEST transition by timestamp.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import lw_pipeline as lp  # noqa: E402


def _slug_dir(tmp_path, slug="a-slug"):
    folder = tmp_path / "2.First Pass Done" / slug
    folder.mkdir(parents=True)
    return folder


def _write(folder, name, body: bytes):
    target = folder / name
    target.write_bytes(body)
    return target


def _manifest(folder, slug, transitions):
    man = {"schema": 1, "slug": slug, "original_filename": f"{slug}.jpg",
           "original_sha256": None, "source_url": None,
           "created_ts": "2026-07-05T08:00:00Z", "delivered_as": None,
           "transitions": transitions}
    (folder / "manifest.json").write_text(json.dumps(man, indent=2), encoding="utf-8")
    return man


def _transition(op, ts, dst, sha_out, sha_in=None):
    return {"ts": ts, "op": op, "actor": "operator", "tool": None, "params": None,
            "src": None, "dst": dst, "sha256_in": sha_in, "sha256_out": sha_out,
            "note": None, "audit": None}


# ---------------------------------------------------------------- the residue
def test_a_swapped_source_reports_a_mismatch_against_the_intake_hash(tmp_path):
    # The state the 21 slugs are in today: file replaced, only INTAKE recorded.
    folder = _slug_dir(tmp_path)
    target = _write(folder, "a-slug_firstinitial.jpg", b"the wiki source")
    _manifest(folder, "a-slug", [
        _transition("INTAKE", "2026-07-05T08:04:58Z",
                    "1.First Pass Scratch/a-slug/a-slug_firstinitial.jpg",
                    "0" * 64)])
    anomalies = []
    lp._verify_folders("a-slug", [folder], anomalies)
    assert [a["class"] for a in anomalies] == ["HASH_MISMATCH"]
    assert anomalies[0]["detail"] == str(target)


def test_a_recorded_replace_source_clears_it(tmp_path):
    folder = _slug_dir(tmp_path)
    target = _write(folder, "a-slug_firstinitial.jpg", b"the wiki source")
    current = lp.sha256_file(target)
    _manifest(folder, "a-slug", [
        _transition("INTAKE", "2026-07-05T08:04:58Z",
                    "1.First Pass Scratch/a-slug/a-slug_firstinitial.jpg", "0" * 64),
        _transition("REPLACE_SOURCE", "2026-08-01T22:00:00Z",
                    "2.First Pass Done/a-slug/a-slug_firstinitial.jpg",
                    current, sha_in="0" * 64)])
    anomalies = []
    lp._verify_folders("a-slug", [folder], anomalies)
    assert anomalies == []


def test_the_expected_hash_comes_from_the_LATEST_transition_by_timestamp(tmp_path):
    # Not from file order. A manifest whose entries are out of order would
    # otherwise verify against a superseded hash and report a false mismatch -
    # or worse, accept a stale file as current.
    folder = _slug_dir(tmp_path)
    target = _write(folder, "a-slug_firstinitial.jpg", b"the wiki source")
    current = lp.sha256_file(target)
    _manifest(folder, "a-slug", [
        _transition("REPLACE_SOURCE", "2026-08-01T22:00:00Z",
                    "2.First Pass Done/a-slug/a-slug_firstinitial.jpg", current),
        _transition("INTAKE", "2026-07-05T08:04:58Z",
                    "1.First Pass Scratch/a-slug/a-slug_firstinitial.jpg", "0" * 64)])
    anomalies = []
    lp._verify_folders("a-slug", [folder], anomalies)
    assert anomalies == []


def test_a_genuinely_corrupt_file_is_still_caught_after_a_replace(tmp_path):
    # The fix must not become a way to silence verify: a REPLACE_SOURCE whose
    # recorded hash does not match what is on disk is still a mismatch.
    folder = _slug_dir(tmp_path)
    _write(folder, "a-slug_firstinitial.jpg", b"something else entirely")
    _manifest(folder, "a-slug", [
        _transition("INTAKE", "2026-07-05T08:04:58Z",
                    "1.First Pass Scratch/a-slug/a-slug_firstinitial.jpg", "0" * 64),
        _transition("REPLACE_SOURCE", "2026-08-01T22:00:00Z",
                    "2.First Pass Done/a-slug/a-slug_firstinitial.jpg", "f" * 64)])
    anomalies = []
    lp._verify_folders("a-slug", [folder], anomalies)
    assert [a["class"] for a in anomalies] == ["HASH_MISMATCH"]


# ---------------------------------------------------------------- the recorder
def test_record_replace_source_appends_and_never_edits_history(tmp_path):
    folder = _slug_dir(tmp_path)
    target = _write(folder, "a-slug_firstinitial.jpg", b"the wiki source")
    before = _manifest(folder, "a-slug", [
        _transition("INTAKE", "2026-07-05T08:04:58Z",
                    "1.First Pass Scratch/a-slug/a-slug_firstinitial.jpg", "0" * 64)])

    recorded = lp.record_replace_source(folder, target, note="wiki swap",
                                        source_url="https://example.invalid/x.jpg")
    assert recorded is True
    man = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))

    assert len(man["transitions"]) == 2
    assert man["transitions"][0] == before["transitions"][0]   # untouched
    new = man["transitions"][1]
    assert new["op"] == "REPLACE_SOURCE"
    assert new["sha256_in"] == "0" * 64                        # what was there
    assert new["sha256_out"] == lp.sha256_file(target)         # what replaced it
    assert new["dst"].endswith("a-slug_firstinitial.jpg")
    assert new["note"] == "wiki swap"
    assert new["params"]["source_url"] == "https://example.invalid/x.jpg"


def test_record_replace_source_is_a_no_op_when_the_hash_already_agrees(tmp_path):
    # Re-running the backfill must not append a second identical record.
    folder = _slug_dir(tmp_path)
    target = _write(folder, "a-slug_firstinitial.jpg", b"the wiki source")
    _manifest(folder, "a-slug", [
        _transition("INTAKE", "2026-07-05T08:04:58Z",
                    "1.First Pass Scratch/a-slug/a-slug_firstinitial.jpg",
                    lp.sha256_file(target))])
    assert lp.record_replace_source(folder, target, note="wiki swap") is False
    man = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert len(man["transitions"]) == 1


def test_record_replace_source_refuses_a_slug_with_no_manifest(tmp_path):
    folder = _slug_dir(tmp_path)
    target = _write(folder, "a-slug_firstinitial.jpg", b"x")
    assert lp.record_replace_source(folder, target, note="wiki swap") is False
