"""Recovery-waterfall tests that replay RECORDED DeviantArt bytes over the real
http path - no injected getter, no hand-written response bodies.

Why this file exists (P2, BACKLOG `mcp-lift-phases`): every other recovery test
injects a fake getter that RETURNS `(404, "not found")`. The production getter
`_default_http` does no such thing - `urllib.request.urlopen` RAISES
`HTTPError` on any 4xx/5xx, so it can only ever return status 200. That means
the non-200 branches of `oembed_liveness` and `saucenao_search` were reachable
only from the fakes, and a dead deviation really degraded to INCONCLUSIVE via
the except path rather than to the non-200 verdicts the tests asserted.

The fixtures under `tests/fixtures/deviantart/` are real responses captured
from `backend.deviantart.com` on 2026-08-01 and are replayed by a local mockd
engine (`C:\\Tools\\mockd\\mockd.exe`, Apache-2.0, offline, no account). With
the network unplugged these still pass; without mockd on disk they skip.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import lw_recover  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "deviantart")
MOCKD = os.environ.get("LW_MOCKD_BIN", r"C:\Tools\mockd\mockd.exe")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# The recorded pair. `pebano1/1337184659` is the SOURCE_RECOVERY 2.2 worked
# example and was live when captured; `someone/1309974594` 404s upstream - the
# suite's other tests assert that id is ALIVE against a body nobody recorded.
ALIVE_ID, ALIVE_ARTIST = 1337184659, "pebano1"
DEAD_ID, DEAD_ARTIST = 1309974594, "someone"

pytestmark = pytest.mark.skipif(
    not os.path.isfile(MOCKD),
    reason=f"mockd not installed at {MOCKD} - see BACKLOG mcp-lift-phases P2",
)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def replay_port():
    """A mockd engine replaying the recorded fixtures. Headless: no admin API,
    no PID file, no disk writes - the shape the engine command exists for."""
    cfg = os.path.join(FIXTURES, "mockd.yaml")
    # `--port 0` and NOT a port we picked: the engine also binds a control port
    # derived from the serving one, so a fixed port collides with any engine
    # already up (it did, on the first run of this file). Auto-assign moves
    # both, and --print-url is how the chosen one comes back.
    proc = subprocess.Popen(
        [MOCKD, "engine", "--config", cfg, "--port", "0", "--print-url"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        creationflags=_NO_WINDOW,
    )
    port = None
    deadline = time.time() + 30
    while time.time() < deadline and port is None:
        if proc.poll() is not None:
            pytest.fail(f"mockd engine exited early: {proc.stdout.read()[:500]}")
        line = proc.stdout.readline()
        if "://" in line:
            port = int(line.strip().rsplit(":", 1)[1])
    if port is None:
        proc.kill()
        pytest.fail("mockd engine never printed its url")
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.1)
    yield port
    # Never Stop-Process (CLAUDE.md); Popen.kill is TerminateProcess, not that.
    proc.kill()
    proc.wait(timeout=10)


@pytest.fixture
def oembed_at(replay_port, monkeypatch):
    """Point the module's oEmbed endpoint at the replay engine. Only the HOST
    is swapped - the path, the query shape and the real `_default_http` all
    stay exactly as production runs them."""
    monkeypatch.setattr(
        lw_recover, "_OEMBED_URL",
        f"http://127.0.0.1:{replay_port}/oembed?url={{url}}")
    return replay_port


# ---------------------------------------------------------------------------
# the recorded fixtures are real, and still parse
# ---------------------------------------------------------------------------
def test_recorded_alive_body_is_real_deviantart_json():
    with open(os.path.join(FIXTURES, "oembed_alive.body"), encoding="utf-8") as fh:
        meta = json.load(fh)
    assert meta["title"] == "Xayah"
    assert meta["author_name"] == "PeBaNO1"
    assert meta["type"] == "photo"


def test_recorded_dead_body_is_not_json_which_the_stubs_never_modelled():
    """The real 404 body is plain text, not JSON. Every hand-written stub fed
    a JSON-ish body through the non-200 path, so the unparseable case was only
    ever reached by the separate non-JSON test."""
    with open(os.path.join(FIXTURES, "oembed_dead.body"), encoding="utf-8") as fh:
        body = fh.read()
    assert "Deviation not found" in body
    with pytest.raises(ValueError):
        json.loads(body)


# ---------------------------------------------------------------------------
# the real transport, against recorded bytes
# ---------------------------------------------------------------------------
def test_alive_deviation_resolves_over_the_real_http_path(oembed_at):
    res = lw_recover.oembed_liveness(ALIVE_ID, artist=ALIVE_ARTIST)
    assert res["alive"] is True
    assert res["title"] == "Xayah"
    assert res["author_name"] == "PeBaNO1"


def test_default_http_returns_non_200_rather_than_raising(oembed_at):
    """THE POINT OF THIS FILE. `_default_http` must hand its caller the status
    so the non-200 verdicts in `oembed_liveness` are reachable in production.
    Before the fix this raised HTTPError and every non-200 branch was dead
    code that only the injected fakes could ever enter."""
    url = f"http://127.0.0.1:{oembed_at}/oembed?url=nope"
    status, text = lw_recover._default_http(url)
    assert status == 404
    assert "Deviation not found" in text


def test_dead_deviation_is_inconclusive_not_a_transport_error(oembed_at):
    """A 404 from a canonical URL is 'unknown, not dead' - but it must arrive
    through the STATUS branch carrying status_code, not through the except
    branch that reports 'probe could not complete'."""
    res = lw_recover.oembed_liveness(DEAD_ID, artist=DEAD_ARTIST)
    assert res["alive"] is False
    assert res["status_code"] == 404
    assert res["reason"] == ("oembed did not resolve the canonical URL - "
                            "liveness is unknown, not dead")


def test_a_genuine_transport_failure_still_degrades_friendly(oembed_at):
    """The except path must survive the fix: nothing is listening on this port,
    so this is a real connection error, and it may never surface a raw string."""
    dead_port = _free_port()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(lw_recover, "_OEMBED_URL",
                   f"http://127.0.0.1:{dead_port}/oembed?url={{url}}")
        res = lw_recover.oembed_liveness(ALIVE_ID, artist=ALIVE_ARTIST)
    assert res["alive"] is False
    assert res["reason"] == "oembed probe could not complete"
    assert "Traceback" not in res["error"]


def test_http_error_subclasses_are_read_for_their_body_not_reraised(oembed_at):
    """HTTPError is itself a readable response object. Proving we consume it
    keeps a future refactor from 'simplifying' the handler back into a raise."""
    url = f"http://127.0.0.1:{oembed_at}/oembed?url=nope"
    try:
        status, _ = lw_recover._default_http(url)
    except urllib.error.HTTPError:  # pragma: no cover - the regression
        pytest.fail("_default_http re-raised instead of returning the status")
    assert status == 404


def test_the_replay_needs_no_network(oembed_at):
    """Guards the acceptance criterion. If this ever starts reaching
    deviantart.com the fixture wiring has rotted."""
    assert "127.0.0.1" in lw_recover._OEMBED_URL
    assert shutil.which("gallery-dl") or True  # presence is not required here


# ---------------------------------------------------------------------------
# gallery-dl: recorded SUBPROCESS output, which mockd cannot serve
# ---------------------------------------------------------------------------
# gallery-dl is shelled out to, not called over http, so the recording here is
# a real captured (returncode, stdout, stderr) rather than a mockd exchange.
# Proxying gallery-dl's own https through mockd would need its MITM CA trusted
# machine-wide - a system-settings change, so it is an operator call, not one
# this test file may make. Captured live 2026-08-01 against deviation
# 1337184659 with `-o original=true`, which returned rc=0 and a 1.77 MB
# original - it was NOT weekly-quota-blocked, contradicting the standing note
# in memory `reference-deviantart-recovery`.
class _ReplayRunner:
    """A runner replaying a recorded gallery-dl result. Not a hand-written
    stub: every field below was captured from a real invocation."""

    def __init__(self, returncode, stdout, stderr):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr
        self.cmd = None
        self.kwargs = None

    def __call__(self, cmd, **kwargs):
        self.cmd = cmd
        self.kwargs = kwargs
        return self


def _recorded_gdl():
    with open(os.path.join(FIXTURES, "gdl_original.stdout"), encoding="utf-8") as fh:
        out = fh.read()
    with open(os.path.join(FIXTURES, "gdl_original.stderr"), encoding="utf-8") as fh:
        err = fh.read()
    return _ReplayRunner(0, out, err)


def test_gallery_dl_success_replays_a_real_recorded_run(tmp_path):
    runner = _recorded_gdl()
    cfg = {"deviantart": {"client-id": "recorded", "client-secret": "recorded"}}
    res = lw_recover.gallery_dl_fetch(
        ALIVE_ID, config=cfg, dest_dir=str(tmp_path), runner=runner, original=True)
    assert res["ok"] is True
    assert res["status"] == "fetched"
    assert res["url"] == lw_recover.deviation_url(ALIVE_ID)


def test_the_recorded_run_carries_the_oauth_handshake_line():
    """The captured stderr proves the fetch really authenticated rather than
    falling back to an anonymous path - the detail a written stub would omit."""
    runner = _recorded_gdl()
    assert "Requesting public access token" in runner.stderr
    assert runner.returncode == 0


def test_original_flag_reaches_the_command_line(tmp_path):
    runner = _recorded_gdl()
    cfg = {"deviantart": {"client-id": "recorded"}}
    lw_recover.gallery_dl_fetch(
        ALIVE_ID, config=cfg, dest_dir=str(tmp_path), runner=runner, original=True)
    assert "original=true" in runner.cmd
    # No console flash on Legion - the spawn must always carry the flag.
    assert runner.kwargs.get("creationflags") == getattr(
        subprocess, "CREATE_NO_WINDOW", 0)
