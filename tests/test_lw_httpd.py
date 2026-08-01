"""Tests for tools/lw_httpd.py - the shared LW dashboard HTTP scaffold.

These cover the plumbing DIRECTLY rather than through a consumer. Every guard
in this module is one line away from being wrong and invisible when wrong: the
Host check, the 500 wrapper that must not leak a traceback, the log override
that keeps stdout empty under pythonw, and the deliberate allow_reuse_address
= False that makes a bind failure mean "already running".

Every server here binds port 0 and every path is injected - a fixed port would
collide with the operator's live monitor on this machine.
"""

import http.client
import json
import logging
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import lw_httpd  # noqa: E402

T = 1800000000.0  # fixed injected "now" epoch


# ------------------------------------------------------------- test handlers


class EchoHandler(lw_httpd.BaseLWHandler):
    """Minimal consumer: one route that succeeds, one that blows up."""

    logger_name = "lw_httpd_test"

    def _route(self, method):
        if self.path == "/boom":
            raise ValueError("bear-1234-secret exploded at line 42")
        self._send_json(200, {"ok": True, "method": method, "path": self.path})


@pytest.fixture
def server():
    srv = lw_httpd.LWServer(("127.0.0.1", 0), EchoHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


def _get(port, path, host=None, method="GET"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": host} if host else {}
    conn.request(method, path, headers=headers)
    resp = conn.getresponse()
    body = resp.read()
    status = resp.status
    conn.close()
    return status, body


# ----------------------------------------------------------------- time bits


def test_iso_from_epoch_round_trip_and_junk():
    assert lw_httpd.iso_from_epoch(T).endswith("Z")
    assert lw_httpd.parse_ts(lw_httpd.iso_from_epoch(T)) == pytest.approx(T)
    for junk in (None, "", "   ", "not-a-date", [], object()):
        assert lw_httpd.iso_from_epoch(junk) is None
        assert lw_httpd.parse_ts(junk) is None


def test_parse_ts_naive_string_is_treated_as_utc():
    assert lw_httpd.parse_ts("2027-01-15T00:00:00") == lw_httpd.parse_ts("2027-01-15T00:00:00Z")


def test_age_text_buckets():
    assert lw_httpd.age_text(None) == ""
    assert lw_httpd.age_text(30) == "30s"
    assert lw_httpd.age_text(600) == "10m"
    assert lw_httpd.age_text(7200) == "2.0h"


# --------------------------------------------------------- read_json_tolerant


def test_read_json_tolerant_absent_file(tmp_path):
    cache = {}
    got = lw_httpd.read_json_tolerant(tmp_path / "nope.json", cache)
    assert got["present"] is False
    assert got["data"] is None
    assert got["stale"] is False
    assert cache == {}  # an absent file must not poison the cache


def test_read_json_tolerant_valid_file_populates_cache(tmp_path):
    cache = {}
    p = tmp_path / "run.json"
    p.write_text(json.dumps({"run_id": "r1"}), encoding="utf-8")
    got = lw_httpd.read_json_tolerant(p, cache, now_ts=T)
    assert got["present"] is True
    assert got["data"] == {"run_id": "r1"}
    assert got["stale"] is False
    assert got["stale_since"] is None
    assert got["mtime"] is not None
    assert cache[str(p)]["good_iso"] == lw_httpd.iso_from_epoch(T)


def test_read_json_tolerant_corrupt_without_prior_good_is_absent(tmp_path):
    p = tmp_path / "run.json"
    p.write_text("{ half a wri", encoding="utf-8")
    got = lw_httpd.read_json_tolerant(p, {})
    assert got["present"] is False
    assert got["data"] is None
    assert got["stale"] is False


def test_read_json_tolerant_corrupt_after_good_serves_stale(tmp_path):
    cache = {}
    p = tmp_path / "run.json"
    p.write_text(json.dumps({"run_id": "r-good"}), encoding="utf-8")
    first = lw_httpd.read_json_tolerant(p, cache, now_ts=T)
    assert first["stale"] is False
    p.write_text("{ mid-write garbage", encoding="utf-8")
    second = lw_httpd.read_json_tolerant(p, cache, now_ts=T + 10)
    assert second["present"] is True
    assert second["data"] == {"run_id": "r-good"}
    assert second["stale"] is True
    assert second["stale_since"] == lw_httpd.iso_from_epoch(T)  # when it was good, not now
    # a torn read must not overwrite the last-good entry
    assert cache[str(p)]["data"] == {"run_id": "r-good"}


def test_read_json_tolerant_recovers_when_the_writer_finishes(tmp_path):
    cache = {}
    p = tmp_path / "run.json"
    p.write_text(json.dumps({"n": 1}), encoding="utf-8")
    lw_httpd.read_json_tolerant(p, cache, now_ts=T)
    p.write_text("{ torn", encoding="utf-8")
    assert lw_httpd.read_json_tolerant(p, cache, now_ts=T + 1)["stale"] is True
    p.write_text(json.dumps({"n": 2}), encoding="utf-8")
    back = lw_httpd.read_json_tolerant(p, cache, now_ts=T + 2)
    assert back["stale"] is False
    assert back["data"] == {"n": 2}


def test_json_null_reads_as_absent(tmp_path):
    # `data is None` is this API's absent sentinel, so a file whose entire
    # content is `null` cannot mean anything else.
    p = tmp_path / "run.json"
    p.write_text("null", encoding="utf-8")
    got = lw_httpd.read_json_tolerant(p, {}, now_ts=T)
    assert got["present"] is False
    assert got["data"] is None
    assert got["stale"] is False


def test_json_null_does_not_evict_last_good(tmp_path):
    """good -> null -> corrupt must still serve the good board.

    The regression this pins: a `null` parses successfully, so a naive cache
    write treats it as the new last-good and throws the real payload away. The
    next torn read then has nothing to fall back on and the board goes blank -
    the exact failure the last-good cache exists to prevent.
    """
    cache = {}
    p = tmp_path / "run.json"
    p.write_text(json.dumps({"run_id": "r1", "images": [{"id": "x"}]}), encoding="utf-8")
    assert lw_httpd.read_json_tolerant(p, cache, now_ts=T)["stale"] is False
    p.write_text("null", encoding="utf-8")
    mid = lw_httpd.read_json_tolerant(p, cache, now_ts=T + 5)
    assert mid["present"] is False
    assert cache[str(p)]["data"] == {"run_id": "r1", "images": [{"id": "x"}]}
    p.write_text("{ torn mid-write", encoding="utf-8")
    got = lw_httpd.read_json_tolerant(p, cache, now_ts=T + 10)
    assert got["present"] is True
    assert got["stale"] is True
    assert got["data"] == {"run_id": "r1", "images": [{"id": "x"}]}
    # and it is dated from when the payload was good, not from the null read
    assert got["stale_since"] == lw_httpd.iso_from_epoch(T)


def test_json_null_alone_never_becomes_a_stale_payload(tmp_path):
    # null -> corrupt, with no good read ever: nothing to fall back on, and
    # the null must not have installed itself as a fallback either.
    cache = {}
    p = tmp_path / "run.json"
    p.write_text("null", encoding="utf-8")
    lw_httpd.read_json_tolerant(p, cache, now_ts=T)
    assert cache == {}
    p.write_text("{ torn", encoding="utf-8")
    got = lw_httpd.read_json_tolerant(p, cache, now_ts=T + 1)
    assert got["present"] is False
    assert got["stale"] is False


@pytest.mark.parametrize("payload", ["0", '""', "[]", "false", "{}"])
def test_other_falsy_payloads_are_real_and_do_replace_last_good(tmp_path, payload):
    """Only `null` is special - every other falsy JSON is content.

    A producer that legitimately writes `[]` or `0` has said something, and a
    reader that kept serving the previous payload would be lying about the
    current state. This asymmetry is deliberate, so it gets pinned.
    """
    cache = {}
    p = tmp_path / "run.json"
    p.write_text(json.dumps({"run_id": "r1"}), encoding="utf-8")
    lw_httpd.read_json_tolerant(p, cache, now_ts=T)
    p.write_text(payload, encoding="utf-8")
    mid = lw_httpd.read_json_tolerant(p, cache, now_ts=T + 5)
    assert mid["present"] is True
    assert mid["data"] == json.loads(payload)
    assert mid["stale"] is False
    p.write_text("{ torn", encoding="utf-8")
    got = lw_httpd.read_json_tolerant(p, cache, now_ts=T + 10)
    assert got["stale"] is True
    assert got["data"] == json.loads(payload)  # the falsy value, not {"run_id": "r1"}
    assert got["stale_since"] == lw_httpd.iso_from_epoch(T + 5)


def test_monitor_view_survives_good_then_null_then_corrupt(tmp_path):
    """The same defect measured where an operator would see it: a blank board.

    lw_monitor is the first consumer of read_json_tolerant, and its own suite
    never writes a bare `null`, so this end-to-end shape is pinned here.
    """
    from tools import lw_monitor

    cache = {}
    p = tmp_path / "pipeline_state.json"
    p.write_text(json.dumps({
        "run_id": "r1",
        "images": [{"id": "x", "stage": 1, "phase": "_firstworking_01"}],
    }), encoding="utf-8")
    first = lw_monitor.build_pipeline_view(p, now_ts=T, cache=cache)
    assert first["state_present"] is True and first["run_id"] == "r1"
    p.write_text("null", encoding="utf-8")
    lw_monitor.build_pipeline_view(p, now_ts=T + 5, cache=cache)
    p.write_text("{ torn mid-write", encoding="utf-8")
    v = lw_monitor.build_pipeline_view(p, now_ts=T + 10, cache=cache)
    assert v["state_present"] is True
    assert v["stale"] is True
    assert v["run_id"] == "r1"
    assert v["counts"]["1"] == 1
    assert len(v["stages"]) == 1
    assert v["stale_since"] == lw_httpd.iso_from_epoch(T)


def test_read_json_tolerant_caches_are_per_path(tmp_path):
    cache = {}
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps({"which": "a"}), encoding="utf-8")
    b.write_text(json.dumps({"which": "b"}), encoding="utf-8")
    lw_httpd.read_json_tolerant(a, cache, now_ts=T)
    lw_httpd.read_json_tolerant(b, cache, now_ts=T)
    b.write_text("{ torn", encoding="utf-8")
    assert lw_httpd.read_json_tolerant(b, cache, now_ts=T + 1)["data"] == {"which": "b"}
    assert lw_httpd.read_json_tolerant(a, cache, now_ts=T + 1)["stale"] is False


# --------------------------------------------------------------- host guard


def test_host_header_foreign_name_rejected(server):
    port = server.server_address[1]
    for evil in ("evil.example.com", "attacker.test:8901", "0.0.0.0"):
        status, body = _get(port, "/anything", host=evil)
        assert status == 403, evil
        assert json.loads(body) == {"ok": False, "error": "forbidden"}


def test_host_header_loopback_names_accepted(server):
    port = server.server_address[1]
    for good in (f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1", "LocalHost"):
        status, body = _get(port, "/ok", host=good)
        assert status == 200, good
        assert json.loads(body)["ok"] is True


def test_host_guard_runs_before_the_route(server):
    # /boom raises; a foreign Host must be turned away before it ever gets there
    port = server.server_address[1]
    status, body = _get(port, "/boom", host="evil.example.com")
    assert status == 403
    assert json.loads(body)["error"] == "forbidden"


# ------------------------------------------------------------- guarded 500


def test_route_exception_becomes_a_500_with_no_traceback(server, caplog):
    port = server.server_address[1]
    with caplog.at_level(logging.ERROR):
        status, body = _get(port, "/boom")
    assert status == 500
    assert json.loads(body) == {"ok": False, "error": "internal error"}
    text = body.decode("utf-8")
    assert "Traceback" not in text
    assert "bear-1234-secret" not in text  # the exception message never reaches the wire
    assert "lw_httpd.py" not in text
    # it is swallowed on the wire, not swallowed entirely - the log still has it
    assert any("bear-1234-secret" in r.getMessage() or (r.exc_info and "unhandled" in r.getMessage())
               for r in caplog.records)


def test_server_survives_a_failing_route(server):
    port = server.server_address[1]
    assert _get(port, "/boom")[0] == 500
    status, body = _get(port, "/still-here")
    assert status == 200
    assert json.loads(body)["path"] == "/still-here"


def test_unimplemented_route_does_not_crash_the_server():
    class Bare(lw_httpd.BaseLWHandler):
        logger_name = "lw_httpd_test"

    srv = lw_httpd.LWServer(("127.0.0.1", 0), Bare)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        status, body = _get(srv.server_address[1], "/")
        assert status == 500
        assert json.loads(body)["ok"] is False
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


def test_post_is_dispatched_too(server):
    port = server.server_address[1]
    status, body = _get(port, "/ok", method="POST")
    assert status == 200
    assert json.loads(body)["method"] == "POST"


def test_request_logging_never_reaches_the_console(server, capsys):
    # BaseHTTPRequestHandler logs to stderr by default; under pythonw there is
    # no console to log to, so the override must keep both streams empty.
    port = server.server_address[1]
    assert _get(port, "/ok")[0] == 200
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_started_iso_is_set(server):
    assert server.started_iso and server.started_iso.endswith("Z")


# --------------------------------------------------------------- setup_logging


def test_setup_logging_creates_the_parent_directory(tmp_path):
    target = tmp_path / "logs" / "svc.log"
    lw_httpd.setup_logging(target)
    assert target.parent.is_dir()


def test_setup_logging_never_raises_on_an_unusable_path(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory", encoding="utf-8")
    lw_httpd.setup_logging(blocker / "nested" / "svc.log")  # must not raise


# ---------------------------------------------------- bind-first instance guard


def test_reuse_address_is_off_so_a_second_bind_really_fails():
    # This attribute IS the single-instance guard. With SO_REUSEADDR on, the
    # second launch would bind happily and two servers would fight for the port.
    assert lw_httpd.LWServer.allow_reuse_address is False


def test_serve_or_defer_defers_when_the_port_is_taken(tmp_path):
    holder = lw_httpd.LWServer(("127.0.0.1", 0), EchoHandler)
    port = holder.server_address[1]
    opened = []
    url = f"http://127.0.0.1:{port}/"

    def factory():
        return lw_httpd.LWServer(("127.0.0.1", port), EchoHandler)

    try:
        rc = lw_httpd.serve_or_defer(factory, url, name="test-svc",
                                     log=logging.getLogger("lw_httpd_test"),
                                     open_url=opened.append)
    finally:
        holder.server_close()
    assert rc == 0            # a double launch is not an error
    assert opened == [url]    # and it points the operator at the live instance


def test_serve_or_defer_does_not_open_a_browser_unasked():
    holder = lw_httpd.LWServer(("127.0.0.1", 0), EchoHandler)
    port = holder.server_address[1]

    def factory():
        return lw_httpd.LWServer(("127.0.0.1", port), EchoHandler)

    try:
        rc = lw_httpd.serve_or_defer(factory, f"http://127.0.0.1:{port}/", name="test-svc",
                                     log=logging.getLogger("lw_httpd_test"), open_url=None)
    finally:
        holder.server_close()
    assert rc == 0


def test_serve_or_defer_serves_then_closes_cleanly():
    made = []
    opened = []
    rcs = []

    def factory():
        srv = lw_httpd.LWServer(("127.0.0.1", 0), EchoHandler)
        made.append(srv)
        return srv

    def run():
        rcs.append(lw_httpd.serve_or_defer(factory, "http://127.0.0.1:0/", name="test-svc",
                                           log=logging.getLogger("lw_httpd_test"),
                                           open_url=opened.append))

    t = threading.Thread(target=run, daemon=True)
    t.start()
    deadline = time.time() + 5
    while not made and time.time() < deadline:
        time.sleep(0.01)
    assert made, "factory never ran"
    port = made[0].server_address[1]
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            assert _get(port, "/ok")[0] == 200
            break
        except OSError:
            time.sleep(0.01)
    else:
        pytest.fail("server never accepted a connection")
    made[0].shutdown()
    t.join(timeout=5)
    assert rcs == [0]
    assert opened == ["http://127.0.0.1:0/"]
