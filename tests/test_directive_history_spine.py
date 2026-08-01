"""The directive_history.jsonl data spine - run id, cost and session id.

Backlog items 4 and 5 of `docs/RUNDASH_SPEC_2026-08-01.md`:

  4. cost_usd and session_id are LIVE in the `DoneRecord` and dropped when the
     history record is built. The controller does `done = rec.raw` and passes
     only that dict, so the two fields never reach the file - they exist only as
     prose in controller.log.
  5. Three id spaces exist with no mapping (`slice_manifest.run_id`, the
     controller's own `run_id`, Claude's `sessionId`) and directive_history.jsonl
     carries NO run id at all, so cycle numbers COLLIDE across runs - two
     `cycle 1` records exist in the live file today.

The reader compensates today with a heuristic: a cycle number that fails to
advance starts a new segment. That heuristic is not wrong, it is unbacked - it
cannot tell a genuine new run from a controller that restarted mid-run and
resumed at a lower cycle. It stays as the fallback for the records already on
disk, which can never gain a run id retroactively, and a real run_id wins where
one is present.

Loading note: importing loop_controller RUNS a controller, so the function under
test is extracted from source the same way tests/test_director_prompt_budget.py
does it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CONTROLLER = ROOT / "ops" / "loop" / "loop_controller.py"

sys.path.insert(0, str(ROOT / "tools"))
from lw_rundash_state import read_cycle_history  # noqa: E402


def _record_directive_outcome(tmp_ctl):
    """Extract record_directive_outcome + directive_title with a stub namespace."""
    import time as _time

    src = CONTROLLER.read_text(encoding="utf-8")
    start = src.index("def directive_title(")
    end = src.index("\ndef read_directive_history(", start)
    ns = {"json": json, "time": _time, "Path": Path, "CTL": tmp_ctl,
          "log": lambda *a, **k: None}
    exec(compile(src[start:end], "rdo", "exec"), ns)  # noqa: S102 - own source
    return ns["record_directive_outcome"]


class _Done:
    """Stand-in for executor.DoneRecord - only the two dropped fields matter."""

    def __init__(self, cost_usd=0.0, session_id=None):
        self.cost_usd = cost_usd
        self.session_id = session_id


# ---------------------------------------------------------------------------
# writer - item 4 and item 5
# ---------------------------------------------------------------------------
def test_cost_and_session_id_reach_the_file(tmp_path):
    rdo = _record_directive_outcome(tmp_path)
    rec = rdo(3, "# a directive", "aaaaaaaa", "bbbbbbbb", {"tests_pass": "1400"},
              "VERDICT: CLEAN", ctl=tmp_path,
              done_record=_Done(cost_usd=1.25, session_id="sess-abc"))
    assert rec["cost_usd"] == 1.25
    assert rec["session_id"] == "sess-abc"
    on_disk = json.loads((tmp_path / "directive_history.jsonl").read_text().strip())
    assert on_disk["cost_usd"] == 1.25
    assert on_disk["session_id"] == "sess-abc"


def test_run_id_reaches_the_file(tmp_path):
    rdo = _record_directive_outcome(tmp_path)
    rec = rdo(1, "# d", "a", "b", {}, "", ctl=tmp_path, run_id="7dd1dc02")
    assert rec["run_id"] == "7dd1dc02"
    assert json.loads(
        (tmp_path / "directive_history.jsonl").read_text().strip())["run_id"] == "7dd1dc02"


def test_the_ahk_channel_shape_still_records(tmp_path):
    """cost 0.0 / session None is the documented AHK-channel receipt. Not an error."""
    rdo = _record_directive_outcome(tmp_path)
    rec = rdo(1, "# d", "a", "b", {}, "", ctl=tmp_path, done_record=_Done())
    assert rec["cost_usd"] == 0.0
    assert rec["session_id"] is None


def test_a_legacy_call_with_no_done_record_still_writes(tmp_path):
    """The controller is the single writer, but nothing may crash the loop."""
    rdo = _record_directive_outcome(tmp_path)
    rec = rdo(1, "# d", "a", "b", {"tests_pass": "1"}, "V", ctl=tmp_path)
    assert rec["cost_usd"] == 0.0
    assert rec["session_id"] is None
    assert rec["run_id"] is None
    assert rec["cycle"] == 1


def test_the_existing_fields_are_untouched(tmp_path):
    """Additive only - the director prompt is built from this chain."""
    rdo = _record_directive_outcome(tmp_path)
    rec = rdo(9, "# the title line", "aaaaaaaaaaaa", "bbbbbbbbbbbb",
              {"tests_pass": "1416", "regressions": True}, "VERDICT: REGRESS x",
              ctl=tmp_path)
    assert rec["cycle"] == 9
    assert rec["title"] == "the title line"
    assert rec["sha_before"] == "aaaaaaaa"
    assert rec["sha_after"] == "bbbbbbbb"
    assert rec["tests"] == "1416"
    assert rec["regress"] is True
    assert rec["verdict"] == "VERDICT: REGRESS x"


# ---------------------------------------------------------------------------
# reader - a real run id beats the heuristic, the heuristic survives for legacy
# ---------------------------------------------------------------------------
def _write(p, records):
    p.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def test_run_id_segments_runs_the_heuristic_would_merge(tmp_path):
    """Two runs whose cycle numbers ASCEND across the boundary.

    The cycle heuristic sees 1,2,3,4 and reports one run. This is the case it
    cannot see, and the reason the id was added.
    """
    p = tmp_path / "directive_history.jsonl"
    _write(p, [
        {"cycle": 1, "ts": "2026-08-01T01:00:00", "run_id": "aaaa1111"},
        {"cycle": 2, "ts": "2026-08-01T02:00:00", "run_id": "aaaa1111"},
        {"cycle": 3, "ts": "2026-08-01T03:00:00", "run_id": "bbbb2222"},
        {"cycle": 4, "ts": "2026-08-01T04:00:00", "run_id": "bbbb2222"},
    ])
    out = read_cycle_history(p)
    assert out["run_count"] == 2
    assert [r["run_index"] for r in out["records"]] == [1, 1, 2, 2]
    assert [r["run_id"] for r in out["records"]] == [
        "aaaa1111", "aaaa1111", "bbbb2222", "bbbb2222"]
    assert out["run_id_backed"] is True


def test_a_restart_that_resumes_lower_is_ONE_run_when_the_id_says_so(tmp_path):
    """The heuristic's false positive: same run, cycle drops after a restart."""
    p = tmp_path / "directive_history.jsonl"
    _write(p, [
        {"cycle": 5, "ts": "2026-08-01T01:00:00", "run_id": "aaaa1111"},
        {"cycle": 1, "ts": "2026-08-01T02:00:00", "run_id": "aaaa1111"},
    ])
    out = read_cycle_history(p)
    assert out["run_count"] == 1
    assert [r["run_index"] for r in out["records"]] == [1, 1]


def test_legacy_records_keep_the_cycle_heuristic(tmp_path):
    """Records already on disk can never gain a run id. Do not regress them."""
    p = tmp_path / "directive_history.jsonl"
    _write(p, [
        {"cycle": 1, "ts": "2026-07-30T01:00:00"},
        {"cycle": 2, "ts": "2026-07-30T02:00:00"},
        {"cycle": 1, "ts": "2026-07-30T03:00:00"},
    ])
    out = read_cycle_history(p)
    assert out["run_count"] == 2
    assert [r["run_index"] for r in out["records"]] == [1, 1, 2]
    assert [r["run_id"] for r in out["records"]] == [None, None, None]
    assert out["run_id_backed"] is False


def test_a_mixed_file_is_backed_only_when_every_record_has_an_id(tmp_path):
    """Half-instrumented must not read as authoritative."""
    p = tmp_path / "directive_history.jsonl"
    _write(p, [
        {"cycle": 1, "ts": "2026-07-30T01:00:00"},
        {"cycle": 1, "ts": "2026-08-01T01:00:00", "run_id": "bbbb2222"},
    ])
    out = read_cycle_history(p)
    assert out["run_id_backed"] is False
    assert out["run_count"] == 2


def test_cost_and_session_id_are_read_back(tmp_path):
    p = tmp_path / "directive_history.jsonl"
    _write(p, [{"cycle": 1, "ts": "2026-08-01T01:00:00", "run_id": "a",
                "cost_usd": 2.5, "session_id": "sess-x"}])
    r = read_cycle_history(p)["records"][0]
    assert r["cost_usd"] == 2.5
    assert r["session_id"] == "sess-x"


def test_a_torn_tail_is_still_discarded_with_the_new_fields(tmp_path):
    """The non-atomic-writer guarantee must survive the schema change."""
    p = tmp_path / "directive_history.jsonl"
    p.write_text(
        json.dumps({"cycle": 1, "ts": "2026-08-01T01:00:00", "run_id": "a"}) + "\n"
        + '{"cycle": 2, "ts": "2026-08-01T02:00:00", "run_i',
        encoding="utf-8")
    out = read_cycle_history(p)
    assert out["torn_tail"] is True
    assert out["corrupt_lines"] == 0
    assert out["parsed"] == 1


# ---------------------------------------------------------------------------
# the spine reaches /api/run - read_cycle_history had NO production consumer
# ---------------------------------------------------------------------------
def _rundash():
    import lw_rundash
    return lw_rundash


def test_the_api_payload_carries_the_cycle_history(tmp_path):
    """It was built, tested and never wired. A reader nothing calls is not a spine."""
    import time as _time

    lw_rundash = _rundash()
    ctl = tmp_path / "control"
    ctl.mkdir()
    _write(ctl / "directive_history.jsonl", [
        {"cycle": 1, "ts": "2026-08-01T01:00:00", "run_id": "aaaa1111",
         "cost_usd": 1.5, "session_id": "sess-a"},
        {"cycle": 2, "ts": "2026-08-01T02:00:00", "run_id": "bbbb2222"},
    ])
    view = lw_rundash.build_run_view(
        control_dir=ctl, manifest_path=tmp_path / "none.json", repo_root=tmp_path,
        now_ts=_time.time(), cache={}, runner=None, pid_alive=lambda pid: False)
    cycles = view["cycles"]
    assert cycles["present"] is True
    assert cycles["run_count"] == 2
    assert cycles["run_id_backed"] is True
    # cost_usd is deliberately projected OUT at this boundary - see
    # test_cost_never_crosses_into_the_api_payload.
    assert "cost_usd" not in cycles["records"][0]
    assert cycles["records"][0]["session_id"] == "sess-a"


def test_a_missing_history_file_is_absent_not_an_error(tmp_path):
    """Fail-soft: the dashboard must render before the first cycle ever resolves."""
    import time as _time

    lw_rundash = _rundash()
    ctl = tmp_path / "control"
    ctl.mkdir()
    view = _rundash().build_run_view(
        control_dir=ctl, manifest_path=tmp_path / "none.json", repo_root=tmp_path,
        now_ts=_time.time(), cache={}, runner=None, pid_alive=lambda pid: False)
    assert view["ok"] is True
    assert view["cycles"]["present"] is False
    assert view["cycles"]["records"] == []


# ---------------------------------------------------------------------------
# the dashboard boundary: the FILE keeps cost, the PAYLOAD must not carry it
# ---------------------------------------------------------------------------
def test_cost_never_crosses_into_the_api_payload(tmp_path):
    """LEDGER 40 and the spec's rejected cost panel: tokens, never dollars.

    Recording cost_usd in directive_history.jsonl is legitimate - it is the
    executor's raw receipt and belongs in runtime forensics. Serving it to a
    panel is the settled-against thing. The existing page-level guard only
    exercised an EMPTY history, so it could not have caught this.
    """
    import time as _time

    lw_rundash = _rundash()
    ctl = tmp_path / "control"
    ctl.mkdir()
    _write(ctl / "directive_history.jsonl", [
        {"cycle": 1, "ts": "2026-08-01T01:00:00", "run_id": "aaaa1111",
         "cost_usd": 4.25, "session_id": "sess-a", "title": "t"},
    ])
    view = lw_rundash.build_run_view(
        control_dir=ctl, manifest_path=tmp_path / "none.json", repo_root=tmp_path,
        now_ts=_time.time(), cache={}, runner=None, pid_alive=lambda pid: False)
    blob = json.dumps(view).lower().replace(
        json.dumps(str(tmp_path))[1:-1].lower(), "<tmp>")
    for word in ("usd", "dollar", "cost"):
        assert word not in blob, f"'{word}' reached the payload"
    # the useful half still arrives
    rec = view["cycles"]["records"][0]
    assert rec["session_id"] == "sess-a"
    assert rec["run_id"] == "aaaa1111"


def test_the_reader_still_exposes_cost_for_forensics(tmp_path):
    """Only the API projection drops it - read_cycle_history stays complete."""
    p = tmp_path / "directive_history.jsonl"
    _write(p, [{"cycle": 1, "ts": "2026-08-01T01:00:00", "cost_usd": 4.25}])
    assert read_cycle_history(p)["records"][0]["cost_usd"] == 4.25


# ---------------------------------------------------------------------------
# UI fixture ritual, as assertions - STRUCTURE / TYPOGRAPHY / ASCII / HIERARCHY
# ---------------------------------------------------------------------------
PAGE = ROOT / "web" / "rundash.html"


def test_page_ascii_and_the_new_rules_use_the_token_scale():
    """ASCII phase + TYPOGRAPHY phase, by byte scan and by rule scan."""
    import re

    raw = PAGE.read_bytes()
    assert not [(i, b) for i, b in enumerate(raw) if b > 127]
    html = PAGE.read_text(encoding="ascii")
    for value in re.findall(r"font-size:\s*([^;}]+)", html):
        assert value.strip().startswith("var(--fs-")
    assert "style=" not in html


def test_the_cycle_panel_exists_and_is_wired():
    """STRUCTURE phase: a panel nothing calls is the bug this slice just fixed."""
    html = PAGE.read_text(encoding="ascii")
    assert "Cycle History" in html
    assert 'id="cycleboard"' in html
    assert "function rCycles(" in html
    assert "rCycles(p)" in html.split("function rCycles(")[0] \
        or "rCycles(p);" in html


def test_the_run_boundary_does_not_rely_on_hue_alone():
    """HIERARCHY phase - the same rule the REFUTED / NOT OBSERVED chips follow."""
    import re

    html = PAGE.read_text(encoding="ascii")
    rule = re.search(r"\.crow\.newrun\{([^}]*)\}", html).group(1)
    assert "border-top" in rule
    assert "RUN " in html


def test_an_unbacked_run_count_is_labelled_as_a_guess():
    """The whole point of run_id_backed. A guess rendered as a fact is the
    unbacked-green failure this project keeps getting burned by."""
    html = PAGE.read_text(encoding="ascii")
    assert "CYCLE-NUMBER GUESS" in html
    assert "run_id_backed" in html


def test_every_cycle_field_goes_through_the_escaper():
    """No raw interpolation into innerHTML."""
    import re

    body = PAGE.read_text(encoding="ascii").split("function rCycles(")[1]
    body = body.split("\nfunction ")[0]
    raw = re.findall(r"\+\s*(r\.\w+)", body)
    assert raw == [], f"concatenated without esc(): {raw}"


def test_the_newest_run_block_is_tagged_too_not_just_the_older_one():
    """Caught by the fixture audit against live data, not by a fixture.

    Rows render newest-first. Tagging only on a CHANGE of run_index left the
    top block - the newest run, the one the operator actually reads - with no
    label at all, while the older block below it got one. The tag fires on the
    first row as well; the divider RULE still only fires on a real change, so
    no stray line appears under the header.
    """
    html = PAGE.read_text(encoding="ascii")
    body = html.split("function rCycles(")[1].split("\nfunction ")[0]
    assert "prevRun === null || r.run_index !== prevRun" in body, "tag never fires on row 0"
    assert "prevRun !== null && r.run_index !== prevRun" in body, "divider lost its guard"
    assert 'divider ? " newrun" : ""' in body, "the rule must follow divider, not boundary"
