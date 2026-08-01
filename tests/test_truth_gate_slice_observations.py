"""truth_gate persists what it OBSERVED onto each slice it reconciled.

Spec item 3 (docs/RUNDASH_SPEC_2026-08-01.md): "per-slice suite observations as
append-only events - the datum the whole evidence ledger is made of". Before
this, truth_gate ran the suite, reconciled every slice against it, and then
wrote the numbers to ONE report file that the next run overwrites. The slice
ladder kept no trace, so P2's evidence chips could only ever render what a human
had typed in by hand after the fact.

The contract under test is deliberately conservative: an observation NEVER
touches `status` or `updated` (that is the 2026-07-30 erased-REFUTE defect), and
a suite that did not actually run records counts=None rather than zeros.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import slice_orchestrator as so  # noqa: E402
import truth_gate as tg  # noqa: E402


SUITE_GREEN = {"passed": 1458, "failed": 0, "errors": 0, "skipped": 16,
               "no_tests_ran": False, "exit_code": 0, "cmd": "pytest tests/ -q"}


def _manifest(tmp_path, slices=("S1", "S2")):
    path = tmp_path / "slice_manifest.json"
    payload = {"schema": so.SCHEMA, "run_id": "2026-08-01-01", "head": "abc1234",
               "created": "2026-08-01T12:00:00Z",
               "slices": [{"id": sid, "title": "t " + sid, "files": [],
                           "status": "in_progress", "commit": None, "note": "",
                           "updated": "2026-08-01T12:30:00Z"} for sid in slices]}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _report(slices, *, suite=None, global_disc=()):
    return {"run_id": "7dd1dc02", "verdict": "PROCEED",
            "suite": dict(suite if suite is not None else SUITE_GREEN),
            "git": {}, "ci": {}, "slices": list(slices), "quarantined": [],
            "global_discrepancies": list(global_disc), "action": ""}


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _verdicts(path, slice_id):
    for entry in _read(path)["slices"]:
        if entry["id"] == slice_id:
            return entry.get(so.VERDICT_FIELD, [])
    raise AssertionError("no slice " + slice_id)


# ---------------------------------------------------------------- the record


def test_confirmed_slice_lands_as_confirm_with_observed_counts(tmp_path):
    path = _manifest(tmp_path)
    out = tg.persist_slice_observations(
        _report([{"id": "S1", "claim": "extract the scaffold",
                  "verdict": "CONFIRM", "discrepancies": []}]), path)

    assert out["appended"] == ["S1"]
    rec, = _verdicts(path, "S1")
    assert rec["state"] == "CONFIRM"
    assert rec["observer"] == "truth_gate"
    assert rec["counts"] == {"passed": 1458, "skipped": 16, "failed": 0}
    assert "extract the scaffold" in rec["note"]
    assert rec["at"].endswith("Z")


def test_quarantined_slice_lands_as_refute_carrying_its_discrepancies(tmp_path):
    path = _manifest(tmp_path)
    tg.persist_slice_observations(
        _report([{"id": "S1", "claim": "c", "verdict": "QUARANTINE",
                  "discrepancies": ["claimed file missing on disk: tools/x.py"]}]),
        path)

    rec, = _verdicts(path, "S1")
    assert rec["state"] == "REFUTE"
    assert rec["discrepancies"] == ["claimed file missing on disk: tools/x.py"]


def test_a_red_suite_is_carried_onto_every_slice_it_reconciled(tmp_path):
    # reconcile() refuses GLOBALLY on a red suite without quarantining any
    # individual slice. A per-slice CONFIRM with no sign of the red suite would
    # read on the board as "this slice was checked and it was fine".
    path = _manifest(tmp_path)
    tg.persist_slice_observations(
        _report([{"id": "S1", "claim": "c", "verdict": "CONFIRM",
                  "discrepancies": []},
                 {"id": "S2", "claim": "c", "verdict": "CONFIRM",
                  "discrepancies": []}],
                suite={**SUITE_GREEN, "passed": 1400, "failed": 3},
                global_disc=["suite red: 3 failed, 0 errors"]),
        path)

    for sid in ("S1", "S2"):
        rec, = _verdicts(path, sid)
        assert rec["discrepancies"] == ["global: suite red: 3 failed, 0 errors"]
        assert rec["counts"]["failed"] == 3


def test_a_suite_that_did_not_run_records_no_counts_at_all(tmp_path):
    # --skip-suite zeroes the counts. Persisting 0/0/0 would put "0 failed" on
    # the board, which reads as a pass, for a suite nobody ran.
    path = _manifest(tmp_path)
    tg.persist_slice_observations(
        _report([{"id": "S1", "claim": "c", "verdict": "CONFIRM",
                  "discrepancies": []}],
                suite={"passed": 0, "failed": 0, "errors": 0, "skipped": 0,
                       "no_tests_ran": False, "exit_code": None,
                       "cmd": "(skipped)"}),
        path, suite_observed=False)

    rec, = _verdicts(path, "S1")
    assert rec["counts"] is None


# ------------------------------------------------------- what it must not do


def test_it_never_moves_the_ladder_or_the_status_clock(tmp_path):
    path = _manifest(tmp_path)
    before = _read(path)["slices"][0]
    tg.persist_slice_observations(
        _report([{"id": "S1", "claim": "c", "verdict": "QUARANTINE",
                  "discrepancies": ["nope"]}]), path)
    after = next(s for s in _read(path)["slices"] if s["id"] == "S1")

    assert after["status"] == before["status"] == "in_progress"
    assert after["updated"] == before["updated"]
    assert after["commit"] == before["commit"]


def test_history_is_append_only_across_runs(tmp_path):
    path = _manifest(tmp_path)
    rep = _report([{"id": "S1", "claim": "c", "verdict": "QUARANTINE",
                    "discrepancies": ["first look"]}])
    tg.persist_slice_observations(rep, path)
    rep["slices"][0].update(verdict="CONFIRM", discrepancies=[])
    tg.persist_slice_observations(rep, path)

    states = [r["state"] for r in _verdicts(path, "S1")]
    assert states == ["REFUTE", "CONFIRM"]


def test_a_slice_the_manifest_never_heard_of_is_reported_not_invented(tmp_path):
    path = _manifest(tmp_path, slices=("S1",))
    out = tg.persist_slice_observations(
        _report([{"id": "S1", "claim": "c", "verdict": "CONFIRM",
                  "discrepancies": []},
                 {"id": "GHOST", "claim": "c", "verdict": "CONFIRM",
                  "discrepancies": []}]), path)

    assert out["appended"] == ["S1"]
    assert out["unknown"] == ["GHOST"]
    assert [s["id"] for s in _read(path)["slices"]] == ["S1"]


@pytest.mark.parametrize("write", [
    lambda p: None,
    lambda p: p.write_text("{not json", encoding="utf-8"),
])
def test_an_unusable_manifest_degrades_the_gate_it_never_fails_it(tmp_path, write):
    path = tmp_path / "slice_manifest.json"
    write(path)
    out = tg.persist_slice_observations(
        _report([{"id": "S1", "claim": "c", "verdict": "CONFIRM",
                  "discrepancies": []}]), path)

    assert out["appended"] == []
    assert out["reason"]


def test_the_write_is_atomic_and_leaves_no_tmp_behind(tmp_path):
    path = _manifest(tmp_path)
    tg.persist_slice_observations(
        _report([{"id": "S1", "claim": "c", "verdict": "CONFIRM",
                  "discrepancies": []},
                 {"id": "S2", "claim": "c", "verdict": "CONFIRM",
                  "discrepancies": []}]), path)

    assert _read(path)["slices"]
    assert not list(tmp_path.glob("*.tmp"))


# ------------------------------------------------- the shared record builder


def test_the_record_schema_has_exactly_one_owner(tmp_path):
    # truth_gate must not hand-roll the record: slice_orchestrator owns the
    # shape, and a second writer is how the two drift apart silently.
    path = _manifest(tmp_path)
    so.cmd_verdict(path, "S1", "CONFIRM", "verifier", passed=1, skipped=2,
                   failed=0, at="2026-08-01T13:00:00Z")
    tg.persist_slice_observations(
        _report([{"id": "S2", "claim": "c", "verdict": "CONFIRM",
                  "discrepancies": []}]), path)

    hand, gate = _verdicts(path, "S1")[0], _verdicts(path, "S2")[0]
    assert set(hand) == set(gate)


def test_build_verdict_record_refuses_an_unknown_observer():
    with pytest.raises(ValueError):
        so.build_verdict_record("CONFIRM", "some_agent")


def test_build_verdict_record_refuses_a_naive_timestamp():
    with pytest.raises(ValueError):
        so.build_verdict_record("CONFIRM", "truth_gate", at="2026-08-01T13:00:00")
