"""Tests for tools/lw_clean_lane.py - the manual-QA lane batch driver.

Pure stdlib + a monkeypatched subprocess boundary; no worker is ever executed
and no pixels are touched, so this runs in CI.

Two load-bearing properties, both learned the hard way:
  - a CRLF slug list must not reach the worker (a CR-suffixed slug produced 44
    silent "no clean input image" errors in the 2026-08-22 lane run);
  - region mode with no detector box must SKIP, never widen to the whole frame -
    an unbounded mask is how a QA lane starts repainting art.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_lane as lane  # noqa: E402


def test_crlf_slug_list_is_read_clean(tmp_path):
    p = tmp_path / "lane.txt"
    p.write_bytes(b"alpha\r\nbravo\r\n\r\n")
    assert lane.read_slugs(str(p)) == ["alpha", "bravo"]


def test_region_is_the_padded_union_of_the_boxes():
    boxes = [[100, 200, 150, 240], [120, 190, 300, 260]]
    assert lane.region_from_boxes(boxes, 2560, 1440, pad=10) == (90, 180, 311, 271)


def test_region_clamps_to_the_frame():
    boxes = [[5, 5, 2550, 1435]]
    assert lane.region_from_boxes(boxes, 2560, 1440, pad=50) == (0, 0, 2560, 1440)


def test_no_box_means_no_region_rather_than_the_whole_frame():
    assert lane.region_from_boxes([], 2560, 1440) is None


def test_region_mode_refuses_to_build_argv_without_a_region():
    with pytest.raises(ValueError):
        lane.build_argv("s", "region", None)


@pytest.mark.parametrize("mode,flag", [("overlay", "--overlay"), ("faint", "--faint")])
def test_lane_flags(mode, flag):
    assert lane.build_argv("s", mode)[-1] == flag


def test_region_argv_is_comma_joined():
    argv = lane.build_argv("s", "region", (1, 2, 3, 4))
    assert argv[-2:] == ["--region", "1,2,3,4"]


def test_a_slug_with_no_box_is_skipped_and_recorded(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(lane.subprocess, "run", lambda *a, **k: called.append(a))
    triage = {"s1": {"slug": "s1", "image": "x.png", "boxes": []}}
    monkeypatch.setattr(lane, "_frame_size", lambda row: (2560, 1440))
    res = lane.run_lane(["s1"], "region", triage)
    assert res[0]["status"] == "skipped"
    assert called == []


def test_worker_status_is_lifted_from_its_json(monkeypatch):
    class P:
        returncode = 0
        stdout = 'noise\n{"slug": "s", "status": "cleaned"}'
        stderr = ""
    monkeypatch.setattr(lane.subprocess, "run", lambda *a, **k: P())
    res = lane.run_lane(["s"], "overlay")
    assert res[0]["status"] == "cleaned"


def test_results_are_written_atomically(tmp_path, monkeypatch):
    class P:
        returncode = 0
        stdout = '{"status": "cleaned"}'
        stderr = ""
    monkeypatch.setattr(lane.subprocess, "run", lambda *a, **k: P())
    out = tmp_path / "res.jsonl"
    lane.run_lane(["s"], "overlay", out=str(out))
    assert out.exists()
    assert not (tmp_path / "res.jsonl.part").exists()


def test_status_comes_from_the_last_json_blob_not_the_first(monkeypatch):
    class P:
        returncode = 0
        stdout = '{"status": "starting"}\nnoise\n{"slug": "s", "status": "manual"}'
        stderr = ""
    monkeypatch.setattr(lane.subprocess, "run", lambda *a, **k: P())
    assert lane.run_lane(["s"], "faint")[0]["status"] == "manual"


def test_unparseable_worker_output_falls_back_to_the_return_code(monkeypatch):
    class P:
        returncode = 0
        stdout = "no json here"
        stderr = ""
    monkeypatch.setattr(lane.subprocess, "run", lambda *a, **k: P())
    assert lane.run_lane(["s"], "faint")[0]["status"] == "ok"
