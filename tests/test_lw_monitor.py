"""Tests for tools/lw_monitor.py - the LW pipeline monitor server.

Mirrors the 13-case plan in docs/research/LW_MONITOR_SPEC.md section 9:
pure build_pipeline_view calls against tmp_path fixtures, plus real HTTP
round-trips on an ephemeral port (bind port 0). Never touches the real
images/ tree or the Desktop.
"""

import base64
import http.client
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import lw_monitor  # noqa: E402

T = 1800000000.0  # fixed injected "now" epoch for deterministic age math

# 1x1 transparent PNG - valid file for thumb tests without requiring Pillow
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def iso(epoch):
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def write_state(tmp_path, payload):
    p = tmp_path / "pipeline_state.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def view(state_path, now_ts=T, cache=None):
    return lw_monitor.build_pipeline_view(state_path, now_ts=now_ts, cache=cache if cache is not None else {})


# ---------------------------------------------------------------- case 1


def test_list_images_grouped_by_stage_with_counts(tmp_path):
    p = write_state(tmp_path, {
        "schema": 1,
        "run_id": "r1",
        "updated_at": iso(T),
        "stage_names": {"1": "First Pass Scratch", "4": "Cleaning Done"},
        "images": [
            {"id": "ahri-star", "file": "images/1.First Pass Scratch/ahri-star/a.png",
             "stage": 1, "phase": "_firstworking_02", "ts": iso(T - 60), "actor": "op"},
            {"id": "jinx-arcane", "stage": 1, "phase": "_firstinitial", "ts": iso(T - 120)},
            {"id": "lux-final", "stage": 4, "phase": "_cleandone", "ts": iso(T - 500)},
        ],
    })
    v = view(p)
    assert v["ok"] is True
    assert v["state_present"] is True
    assert v["stale"] is False
    assert v["run_id"] == "r1"
    assert v["counts"]["1"] == 2
    assert v["counts"]["4"] == 1
    assert v["counts"]["?"] == 0
    assert v["phase_counts"]["_working"] == 1
    assert v["phase_counts"]["_initial"] == 1
    assert v["phase_counts"]["_done"] == 1
    stages = v["stages"]
    assert [s["stage"] for s in stages] == [1, 4]
    assert stages[0]["name"] == "First Pass Scratch"
    assert stages[0]["count"] == 2
    # active-first ordering: _working before _initial
    assert [i["id"] for i in stages[0]["items"]] == ["ahri-star", "jinx-arcane"]
    assert stages[0]["items"][0]["age_s"] == pytest.approx(60.0)


# ---------------------------------------------------------------- case 2


def test_dict_form_images_id_from_key(tmp_path):
    p = write_state(tmp_path, {
        "images": {
            "ahri-star": {"stage": 3, "phase": "_cleanworking_04", "ts": iso(T - 10)},
        },
    })
    v = view(p)
    assert v["counts"]["3"] == 1
    assert v["stages"][0]["items"][0]["id"] == "ahri-star"


# ---------------------------------------------------------------- case 3


def test_unknown_fields_ignored(tmp_path):
    p = write_state(tmp_path, {
        "run_id": "r2",
        "totally_new_top_level": {"a": [1, 2, 3]},
        "images": [
            {"id": "x", "stage": 2, "phase": "_firstdone", "ts": iso(T - 5),
             "brand_new_field": ["ignored"], "another": 42},
        ],
    })
    v = view(p)
    assert v["ok"] is True
    assert v["counts"]["2"] == 1
    assert v["stages"][0]["items"][0]["id"] == "x"


# ---------------------------------------------------------------- case 4


def test_missing_stage_and_phase_defaults(tmp_path):
    p = write_state(tmp_path, {
        "images": [
            {"file": "images/somewhere/bar-baz.png"},
            {},
            {"id": "float-stage", "stage": "not-an-int"},
        ],
    })
    v = view(p)
    assert v["counts"]["?"] == 3
    q = [s for s in v["stages"] if s["stage"] == "?"][0]
    ids = {i["id"] for i in q["items"]}
    assert "bar-baz" in ids       # id derived from file basename
    assert "item-1" in ids        # id derived from list index
    assert "float-stage" in ids   # non-int stage -> "?" bucket
    for item in q["items"]:
        assert item["phase"] == "_initial"


# ---------------------------------------------------------------- case 5


def test_unknown_phase_string_preserved_verbatim(tmp_path):
    p = write_state(tmp_path, {
        "images": [{"id": "x", "stage": 2, "phase": "_weird", "ts": iso(T)}],
    })
    v = view(p)
    item = v["stages"][0]["items"][0]
    assert item["phase"] == "_weird"
    assert item["phase_class"] is None
    assert v["phase_counts"]["_weird"] == 1


def test_contract_phase_tokens_classified(tmp_path):
    # the producer's stage-prefixed tokens classify into the four canonicals
    p = write_state(tmp_path, {
        "images": [
            {"id": "a", "stage": 1, "phase": "_firstinitial"},
            {"id": "b", "stage": 1, "phase": "_firstworking_12"},
            {"id": "c", "stage": 3, "phase": "_cleanneedauth"},
            {"id": "d", "stage": 7, "phase": "_lastdone"},
        ],
    })
    v = view(p)
    assert v["phase_counts"]["_initial"] == 1
    assert v["phase_counts"]["_working"] == 1
    assert v["phase_counts"]["_needauth"] == 1
    assert v["phase_counts"]["_done"] == 1
    # the _cleanneedauth item feeds the attention lane
    assert any(a["id"] == "c" and a["kind"] == "needauth" for a in v["attention"])


def test_producer_state_shape_mapped(tmp_path):
    # PIPELINE_STATE_MACHINE.md section 4.2 shape: images dict keyed by slug
    # with state/substate/working_max/last_op_ts and no stage/phase fields.
    p = write_state(tmp_path, {
        "schema": 1,
        "generated_ts": iso(T),
        "images": {
            "ahri-star-guardian": {
                "state": "CLEAN_SCRATCH", "substate": "EDITING",
                "stage_folder": "3.Cleaning Scratch",
                "working_max": 4, "last_op_ts": iso(T - 30),
            },
            "jinx-arcane": {
                "state": "FIRST_SCRATCH", "substate": "NEEDAUTH",
                "last_op_ts": iso(T - 40),
            },
        },
    })
    v = view(p)
    assert v["counts"]["3"] == 1
    assert v["counts"]["1"] == 1
    stage3 = [s for s in v["stages"] if s["stage"] == 3][0]
    assert stage3["items"][0]["phase_class"] == "_working"
    assert any(a["id"] == "jinx-arcane" and a["kind"] == "needauth" for a in v["attention"])


# ---------------------------------------------------------------- case 6


def test_missing_state_file(tmp_path):
    v = view(tmp_path / "nope.json")
    assert v["ok"] is True
    assert v["state_present"] is False
    assert v["stale"] is False
    assert v["stages"] == []
    assert v["attention"] == []


def test_garbage_json_without_prior_good(tmp_path):
    p = tmp_path / "pipeline_state.json"
    p.write_text("{ this is not json", encoding="utf-8")
    v = view(p)
    assert v["ok"] is True
    assert v["state_present"] is False
    assert v["stale"] is False


# ---------------------------------------------------------------- case 7


def test_garbage_json_after_good_read_serves_stale(tmp_path):
    cache = {}
    p = write_state(tmp_path, {
        "run_id": "r-good",
        "images": [{"id": "x", "stage": 1, "phase": "_firstinitial", "ts": iso(T - 5)}],
    })
    v1 = view(p, now_ts=T, cache=cache)
    assert v1["stale"] is False and v1["run_id"] == "r-good"
    p.write_text("{ mid-write garbage", encoding="utf-8")
    v2 = view(p, now_ts=T + 10, cache=cache)
    assert v2["ok"] is True
    assert v2["stale"] is True
    assert v2["state_present"] is True
    assert v2["run_id"] == "r-good"
    assert v2["counts"]["1"] == 1
    assert v2.get("stale_since")


# ---------------------------------------------------------------- case 8


def test_attention_ordering_and_stuck_threshold(tmp_path):
    p = write_state(tmp_path, {
        "images": [
            {"id": "stuck-old", "stage": 3, "phase": "_cleanworking_02", "ts": iso(T - 1000)},
            {"id": "fresh-work", "stage": 3, "phase": "_cleanworking_01", "ts": iso(T - 100)},
            {"id": "edge-900", "stage": 3, "phase": "_cleanworking_03", "ts": iso(T - 900)},
            {"id": "boom", "stage": 5, "phase": "_finalworking_01", "ts": iso(T - 50),
             "error": "inpaint crashed"},
            {"id": "auth-me", "stage": 1, "phase": "_firstneedauth", "ts": iso(T - 200),
             "needauth": "operator must approve mask"},
        ],
    })
    v = view(p, now_ts=T)
    kinds = [a["kind"] for a in v["attention"]]
    ids = [a["id"] for a in v["attention"]]
    assert kinds == ["needauth", "error", "stuck"]
    assert ids == ["auth-me", "boom", "stuck-old"]
    auth = v["attention"][0]
    assert auth["reason"] == "operator must approve mask"
    err = v["attention"][1]
    assert "inpaint crashed" in err["reason"]
    stuck = v["attention"][2]
    assert stuck["age_s"] == pytest.approx(1000.0)
    # age exactly 900 is NOT stuck (threshold is strictly greater-than)
    assert "edge-900" not in ids
    assert "fresh-work" not in ids


def test_top_level_anomalies_feed_attention(tmp_path):
    p = write_state(tmp_path, {
        "images": [],
        "anomalies": [
            {"slug": "jinx-arcane", "class": "STALE_DONE",
             "detail": "2.First Pass Done superseded", "resumable": True},
        ],
    })
    v = view(p)
    assert len(v["attention"]) == 1
    a = v["attention"][0]
    assert a["kind"] == "error"
    assert a["id"] == "jinx-arcane"
    assert "STALE_DONE" in a["reason"]


# ---------------------------------------------------------------- case 9


def test_done_cap_limits_listed_items_not_counts(tmp_path):
    images = [
        {"id": f"img-{i:03d}", "stage": 8, "phase": "_lastdone", "ts": iso(T - i)}
        for i in range(300)
    ]
    p = write_state(tmp_path, {"images": images})
    v = view(p)
    stage8 = [s for s in v["stages"] if s["stage"] == 8][0]
    assert stage8["count"] == 300
    assert v["counts"]["8"] == 300
    assert len(stage8["items"]) == 5
    # newest five listed
    assert [i["id"] for i in stage8["items"]] == [
        "img-000", "img-001", "img-002", "img-003", "img-004"]


# ---------------------------------------------------------------- case 10


def test_tail_log(tmp_path):
    missing = lw_monitor.tail_log(tmp_path / "nope.md", 60)
    assert missing == {"ok": True, "present": False, "lines": []}
    logp = tmp_path / "PIPELINE_LOG.md"
    logp.write_text("".join(f"line-{i}\n" for i in range(300)), encoding="utf-8")
    got = lw_monitor.tail_log(logp, 5)
    assert got["present"] is True
    assert got["lines"] == ["line-295", "line-296", "line-297", "line-298", "line-299"]
    capped = lw_monitor.tail_log(logp, 100000)
    assert len(capped["lines"]) == 200  # hard cap


# ---------------------------------------------------------------- case 11


def test_validate_thumb_path(tmp_path):
    root = tmp_path / "imgroot"
    root.mkdir()
    good = root / "a.png"
    good.write_bytes(PNG_1X1)
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG_1X1)
    txt = root / "notes.txt"
    txt.write_text("x", encoding="utf-8")
    roots = [root]
    assert lw_monitor._validate_thumb_path(str(good), roots) == good.resolve()
    # traversal, relative and absolute
    assert lw_monitor._validate_thumb_path("..\\..\\Windows\\win.ini", roots) is None
    assert lw_monitor._validate_thumb_path(str(root / ".." / "outside.png"), roots) is None
    assert lw_monitor._validate_thumb_path(str(outside), roots) is None
    # suffix allowlist
    assert lw_monitor._validate_thumb_path(str(txt), roots) is None
    # nonexistent file under the root
    assert lw_monitor._validate_thumb_path(str(root / "missing.png"), roots) is None
    # empty / junk input
    assert lw_monitor._validate_thumb_path("", roots) is None


# ---------------------------------------------------------------- case 12
# HTTP round-trips on an ephemeral port


@pytest.fixture
def server(tmp_path):
    state = write_state(tmp_path, {
        "run_id": "http-run",
        "images": [{"id": "x", "stage": 1, "phase": "_firstworking_01", "ts": iso(time.time())}],
    })
    logp = tmp_path / "PIPELINE_LOG.md"
    logp.write_text("2026-07-03T00:00:00Z | x | INTAKE | a -> b | actor=op | sha12=0 | ok | note=-\n",
                    encoding="utf-8")
    page = tmp_path / "monitor.html"
    page.write_text("<h1>LW TEST PAGE</h1>", encoding="utf-8")
    imgroot = tmp_path / "imgroot"
    imgroot.mkdir()
    (imgroot / "a.png").write_bytes(PNG_1X1)
    srv = lw_monitor.MonitorServer(
        ("127.0.0.1", 0), lw_monitor.Handler,
        state_path=state, log_path=logp, page_path=page,
        image_roots=[imgroot], cache={})
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv, imgroot
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


def _get(port, path, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": host} if host else {}
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    body = resp.read()
    ctype = resp.getheader("Content-Type") or ""
    conn.close()
    return resp.status, ctype, body


def test_http_pipeline_route(server):
    srv, _ = server
    port = srv.server_address[1]
    status, ctype, body = _get(port, "/api/pipeline")
    assert status == 200
    assert ctype.startswith("application/json")
    payload = json.loads(body)
    assert payload["ok"] is True
    assert payload["state_present"] is True
    assert payload["run_id"] == "http-run"


def test_http_serves_page(server):
    srv, _ = server
    port = srv.server_address[1]
    status, ctype, body = _get(port, "/")
    assert status == 200
    assert ctype.startswith("text/html")
    assert b"LW TEST PAGE" in body


def test_http_bad_host_rejected(server):
    srv, _ = server
    port = srv.server_address[1]
    status, _, body = _get(port, "/api/pipeline", host="evil.example.com")
    assert status == 403
    assert json.loads(body)["ok"] is False


def test_http_unknown_path_404(server):
    srv, _ = server
    port = srv.server_address[1]
    status, _, body = _get(port, "/nope")
    assert status == 404
    assert json.loads(body)["ok"] is False


def test_http_health(server):
    srv, _ = server
    port = srv.server_address[1]
    status, _, body = _get(port, "/api/health")
    assert status == 200
    payload = json.loads(body)
    assert payload["ok"] is True
    assert payload["pid"] == os.getpid()
    assert payload["port"] == port
    assert payload["state_present"] is True


def test_http_log_tail(server):
    srv, _ = server
    port = srv.server_address[1]
    status, _, body = _get(port, "/api/log?n=10")
    assert status == 200
    payload = json.loads(body)
    assert payload["present"] is True
    assert len(payload["lines"]) == 1


def test_http_thumb_traversal_403(server):
    srv, _ = server
    port = srv.server_address[1]
    for evil in ("..\\..\\Windows\\win.ini",
                 "C:\\Windows\\win.ini",
                 "....//....//etc//passwd"):
        status, _, body = _get(port, "/api/thumb?path=" + quote(evil, safe=""))
        assert status == 403, evil
        assert json.loads(body)["ok"] is False
    # missing param
    status, _, _ = _get(port, "/api/thumb")
    assert status == 403


def test_http_thumb_valid_file(server):
    srv, imgroot = server
    port = srv.server_address[1]
    status, ctype, body = _get(port, "/api/thumb?path=" + quote(str(imgroot / "a.png"), safe=""))
    assert status == 200
    assert ctype.startswith("image/")
    assert len(body) > 0


# ---------------------------------------------------------------- case 13


def test_single_instance_second_bind_exits_zero(tmp_path, monkeypatch):
    holder = lw_monitor.MonitorServer(
        ("127.0.0.1", 0), lw_monitor.Handler,
        state_path=tmp_path / "s.json", log_path=tmp_path / "l.md",
        page_path=tmp_path / "p.html", image_roots=[tmp_path], cache={})
    port = holder.server_address[1]
    opened = []
    monkeypatch.setattr(lw_monitor.webbrowser, "open", lambda url: opened.append(url))
    try:
        rc = lw_monitor.main(["--port", str(port), "--open"])
    finally:
        holder.server_close()
    assert rc == 0
    assert opened and str(port) in opened[0]


# ------------------------------------------- producer counts top-up (audit)


def test_count_only_state_surfaces_pending_intake(tmp_path):
    """scan_tree reports pre-intake originals only in counts - no per-image
    entries - so the view must still show stage-0 pressure (audit MUST-FIX)."""
    p = write_state(tmp_path, {
        "schema": 1, "generated_ts": iso(T), "scan_verify": False,
        "counts": {"pending_intake": 76, "first_scratch": 0, "passed": 0,
                   "anomalies": 0},
        "images": {}, "anomalies": [],
    })
    v = view(p)
    assert v["state_present"] is True
    assert v["counts"]["0"] == 76
    assert v["phase_counts"]["_initial"] == 76
    s0 = [s for s in v["stages"] if s["stage"] == 0]
    assert s0 and s0[0]["count"] == 76 and s0[0]["items"] == []
    assert s0[0]["name"] == "Originals"


def test_producer_counts_never_double_count_tracked_images(tmp_path):
    p = write_state(tmp_path, {
        "schema": 1,
        "counts": {"pending_intake": 2, "first_scratch": 1, "anomalies": 5},
        "images": {
            "a": {"state": "FIRST_SCRATCH", "substate": "EDITING",
                  "working_max": 1, "last_op_ts": iso(T - 10)},
        },
    })
    v = view(p)
    # tracked first_scratch image is not counted twice
    assert v["counts"]["1"] == 1
    s1 = [s for s in v["stages"] if s["stage"] == 1]
    assert s1 and s1[0]["count"] == 1 and len(s1[0]["items"]) == 1
    # pending intake still topped up; 'anomalies' key ignored (not a stage)
    assert v["counts"]["0"] == 2
    assert v["phase_counts"]["_initial"] == 2
    assert all(s["stage"] in (0, 1) or s["stage"] == "?" for s in v["stages"])
