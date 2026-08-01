"""Tests for tools/lw_rundash.py - the LW run dashboard server (P1 + P3).

Same posture as tests/test_lw_monitor.py: the view builders are pure and every
path is injected from tmp_path, and the HTTP cases bind port 0 so a live
instance on the real port cannot be collided with. Nothing here reads the real
ops/loop/control, the real images tree, or the operator's transcript dir - a
test that read those would pass or fail on whatever the machine happened to be
doing at the time.

The two assertions that exist because of measured incidents, not tidiness:

  RECYCLED PID. 2026-08-01, RUNNING.lock named a pid the OS had reissued to an
  unrelated conhost and the loop refused to start for five days. A dashboard
  that reads LIVE off the lock reproduces that failure as a display bug, so the
  corroboration is pinned here rather than trusted.

  NOT OBSERVED. The evidence chip must render amber on every row, never blank
  and never hidden. Blank reads as "fine"; the panel indicting itself is the
  point of P2 before its instrumentation lands.
"""

import http.client
import json
import re
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import lw_rundash  # noqa: E402

PAGE = Path(__file__).resolve().parent.parent / "web" / "rundash.html"
MODULE = Path(__file__).resolve().parent.parent / "tools" / "lw_rundash.py"


# ------------------------------------------------------------------ fixtures


def iso(epoch):
    return lw_rundash.rundash_state.iso_from_epoch(epoch)


def write_manifest(tmp_path, payload):
    p = tmp_path / "slice_manifest.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def control(tmp_path, *, lock=None, stop=None, cycle=None, log=None):
    ctl = tmp_path / "control"
    ctl.mkdir(exist_ok=True)
    if lock is not None:
        (ctl / "RUNNING.lock").write_text(json.dumps(lock), encoding="utf-8")
    if stop is not None:
        (ctl / "STOP").write_text(stop, encoding="utf-8")
    if cycle is not None:
        (ctl / "cycle.txt").write_text(str(cycle), encoding="utf-8")
    if log is not None:
        (ctl / "controller.log").write_text(log, encoding="utf-8")
    return ctl


def fleet_dir(tmp_path, agents):
    """agents: list of (id, meta dict, list of jsonl event dicts)."""
    base = tmp_path / "session" / "subagents"
    base.mkdir(parents=True, exist_ok=True)
    for agent_id, meta, events in agents:
        (base / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
        if events is not None:
            lines = "\n".join(json.dumps(e) for e in events) + "\n"
            (base / f"agent-{agent_id}.jsonl").write_text(lines, encoding="utf-8")
    return tmp_path / "session"


def fake_git(*, worktrees=(), status=None, branch_head="main", oid="abc123def456",
             ahead=0, behind=0, rc=0, stderr=""):
    """A git runner that answers the two commands the views actually issue."""
    def run(argv):
        if rc != 0:
            return rc, "", stderr
        if "worktree" in argv:
            out = []
            for wt in worktrees:
                out.append(f"worktree {wt['path']}")
                out.append(f"HEAD {wt.get('head', oid)}")
                if wt.get("branch"):
                    out.append(f"branch refs/heads/{wt['branch']}")
                out.append("")
            return 0, "\n".join(out), ""
        lines = [f"# branch.oid {oid}", f"# branch.head {branch_head}",
                 "# branch.upstream origin/main", f"# branch.ab +{ahead} -{behind}"]
        target = argv[2]
        for entry in (status or {}).get(target, []):
            lines.append(entry)
        return 0, "\n".join(lines) + "\n", ""
    return run


# ------------------------------------------------------- P1: the run ledger


def test_empty_tree_renders_a_dead_run_rather_than_raising(tmp_path):
    view = lw_rundash.build_run_view(
        control_dir=tmp_path / "control", manifest_path=tmp_path / "none.json",
        repo_root=tmp_path, now_ts=time.time(), cache={},
        runner=fake_git(), pid_alive=lambda pid: False)
    assert view["ok"] is True
    assert view["run"]["state"] == "DEAD"
    assert view["slices"] == []
    assert view["manifest"]["present"] is False


def test_live_needs_a_live_pid_a_fresh_lock_and_a_moving_disk(tmp_path):
    now = time.time()
    ctl = control(tmp_path, lock={"pid": 4242, "run_id": "7dd1dc02", "ts": now - 10},
                  cycle=3, log="cycle 3 start\n")
    manifest = write_manifest(tmp_path, {"run_id": "2026-08-01-01", "head": "55b9e95",
                                         "updated": iso(now - 5), "slices": []})
    view = lw_rundash.build_run_view(
        control_dir=ctl, manifest_path=manifest, repo_root=tmp_path, now_ts=now,
        cache={}, runner=fake_git(), pid_alive=lambda pid: True)
    assert view["run"]["state"] == "LIVE"
    assert view["run"]["corroborated"] is True
    assert view["run"]["pid"] == 4242
    assert view["run"]["cycle"] == 3


def test_a_recycled_pid_is_dead_however_alive_the_pid_table_says_it_is(tmp_path):
    # The 2026-08-01 defect: pid 8532 was alive and belonged to a conhost. A
    # lock older than the stale window is not a run, whatever the OS says.
    now = time.time()
    ctl = control(tmp_path, lock={"pid": 8532, "ts": now - 5 * 86400},
                  log="cycle 12 done\n")
    Path(ctl / "controller.log").touch()
    manifest = write_manifest(tmp_path, {"slices": []})
    view = lw_rundash.build_run_view(
        control_dir=ctl, manifest_path=manifest, repo_root=tmp_path, now_ts=now,
        cache={}, runner=fake_git(), pid_alive=lambda pid: True)
    assert view["run"]["state"] == "DEAD"
    assert view["run"]["corroborated"] is False
    assert "recycled" in view["run"]["reason"]


def test_the_board_carries_one_row_per_slice_with_time_in_status(tmp_path):
    now = time.time()
    manifest = write_manifest(tmp_path, {
        "run_id": "r1", "head": "55b9e95", "updated": iso(now),
        "slices": [
            {"id": "B1", "title": "scaffold", "files": ["tools/lw_httpd.py"],
             "status": "committed", "commit": "db168ff", "updated": iso(now - 60)},
            {"id": "B3", "title": "rundash server", "files": ["tools/lw_rundash.py"],
             "status": "in_progress", "commit": None, "updated": iso(now - 3600)},
        ]})
    view = lw_rundash.build_run_view(
        control_dir=tmp_path / "control", manifest_path=manifest, repo_root=tmp_path,
        now_ts=now, cache={}, runner=fake_git(), pid_alive=lambda pid: False)
    ids = [s["id"] for s in view["slices"]]
    assert ids == ["B1", "B3"]
    b3 = view["slices"][1]
    assert b3["status"] == "in_progress"
    # An hour in status, asserted as a range: the ISO round-trip truncates at
    # the microsecond, so pinning the exact minute makes this flap.
    assert 3540 < b3["status_age_s"] <= 3600
    assert b3["status_age_human"] in ("59m", "60m")
    assert view["counts"]["committed"] == 1
    assert view["open_count"] == 1


def test_a_slice_parked_in_progress_raises_the_stuck_signal(tmp_path):
    now = time.time()
    manifest = write_manifest(tmp_path, {"slices": [
        {"id": "B3", "title": "rundash", "status": "in_progress", "updated": iso(now - 7200)}]})
    view = lw_rundash.build_run_view(
        control_dir=tmp_path / "control", manifest_path=manifest, repo_root=tmp_path,
        now_ts=now, cache={}, runner=fake_git(), pid_alive=lambda pid: False,
        stuck_after_s=900.0)
    assert view["slices"][0]["stuck"] is True
    assert view["stuck_count"] == 1
    assert any(a["kind"] == "stuck_slice" for a in view["alerts"])


def test_two_open_slices_naming_one_path_raise_a_disjointness_warning(tmp_path):
    now = time.time()
    manifest = write_manifest(tmp_path, {"slices": [
        {"id": "B3", "status": "in_progress", "files": ["tools/lw_ports.py"], "updated": iso(now)},
        {"id": "B4", "status": "pending", "files": ["tools/lw_ports.py"], "updated": iso(now)},
    ]})
    view = lw_rundash.build_run_view(
        control_dir=tmp_path / "control", manifest_path=manifest, repo_root=tmp_path,
        now_ts=now, cache={}, runner=fake_git(), pid_alive=lambda pid: False)
    assert view["disjointness"] == [{"file": "tools/lw_ports.py", "slices": ["B3", "B4"]}]
    assert any(a["kind"] == "disjointness" for a in view["alerts"])


# --------------------------------------------------------- P1: the fleet


def test_the_fleet_is_attributed_to_slices_by_branch_and_reports_tokens(tmp_path):
    now = time.time()
    session = fleet_dir(tmp_path, [
        ("aaa", {"agentType": "general-purpose", "worktreePath": "C:/wt/b3",
                 "worktreeBranch": "worktree-agent-B3", "description": "slice B3"},
         [{"timestamp": iso(now - 300), "message": {"usage": {"output_tokens": 120}}},
          {"timestamp": iso(now - 10), "message": {"usage": {"output_tokens": 80}}}]),
        ("bbb", {"agentType": "verifier", "description": "verify"},
         [{"timestamp": iso(now - 20)}]),
    ])
    manifest = write_manifest(tmp_path, {"slices": [
        {"id": "B3", "status": "in_progress", "updated": iso(now)}]})
    view = lw_rundash.build_run_view(
        control_dir=tmp_path / "control", manifest_path=manifest, session_dir=session,
        repo_root=tmp_path, now_ts=now, cache={}, runner=fake_git(),
        pid_alive=lambda pid: False)
    assert view["fleet"]["counts"]["total"] == 2
    assert view["fleet"]["counts"]["worktree"] == 1
    assert view["fleet"]["output_tokens"] == 200
    agent = view["slices"][0]["agent"]
    assert agent is not None
    assert agent["id"] == "aaa"
    assert agent["output_tokens"] == 200
    # Ownership is inferred from a branch name, not recorded by the producer,
    # so it ships labelled as a hint rather than as fact.
    assert agent["hint"] is True


def test_a_silent_worktree_agent_is_only_stalled_while_the_run_is_live(tmp_path):
    now = time.time()
    session = fleet_dir(tmp_path, [
        ("aaa", {"agentType": "general-purpose", "worktreePath": "C:/wt/b3",
                 "worktreeBranch": "worktree-agent-B3"},
         [{"timestamp": iso(now - 9000)}]),
    ])
    # Backdate the transcript so idle age, not content, is what decides.
    old = now - 9000
    for p in (session / "subagents").glob("agent-*.jsonl"):
        import os
        os.utime(p, (old, old))
    manifest = write_manifest(tmp_path, {"slices": []})
    dead = lw_rundash.build_run_view(
        control_dir=tmp_path / "control", manifest_path=manifest, session_dir=session,
        repo_root=tmp_path, now_ts=now, cache={}, runner=fake_git(),
        pid_alive=lambda pid: False)
    assert dead["run"]["state"] == "DEAD"
    assert not [a for a in dead["alerts"] if a["kind"] == "stalled_agent"]

    ctl = control(tmp_path, lock={"pid": 99, "ts": now - 5}, log="x\n")
    live = lw_rundash.build_run_view(
        control_dir=ctl, manifest_path=manifest, session_dir=session,
        repo_root=tmp_path, now_ts=now, cache={}, runner=fake_git(),
        pid_alive=lambda pid: True)
    assert live["run"]["state"] == "LIVE"
    assert [a for a in live["alerts"] if a["kind"] == "stalled_agent"]


# ------------------------------------------------------ P2: the evidence chip


def test_every_slice_ships_an_amber_not_observed_chip(tmp_path):
    now = time.time()
    manifest = write_manifest(tmp_path, {"slices": [
        {"id": "B1", "status": "committed", "commit": "db168ff", "updated": iso(now)},
        {"id": "B3", "status": "in_progress", "updated": iso(now)},
    ]})
    view = lw_rundash.build_run_view(
        control_dir=tmp_path / "control", manifest_path=manifest, repo_root=tmp_path,
        now_ts=now, cache={}, runner=fake_git(), pid_alive=lambda pid: False)
    for row in view["slices"]:
        chip = row["evidence"]
        assert chip["state"] == "NOT OBSERVED"
        assert chip["class"] == "amber"
        assert chip["why"]  # blank is a lie - the chip says why it cannot see


def test_the_three_evidence_states_all_exist_even_though_one_is_reachable():
    assert lw_rundash.EVIDENCE_STATES == ("VERIFIED", "REFUTED", "NOT OBSERVED")


# ----------------------------------------------------------------- git facts


def test_head_summary_reads_sha_branch_and_ahead_behind(tmp_path):
    got = lw_rundash.head_summary(tmp_path, runner=fake_git(oid="55b9e95aaaa", ahead=2, behind=1))
    assert got["ok"] is True
    assert got["head"].startswith("55b9e95")
    assert got["branch"] == "main"
    assert got["ahead"] == 2
    assert got["behind"] == 1


def test_head_moved_since_the_run_started_is_computed_not_guessed(tmp_path):
    now = time.time()
    manifest = write_manifest(tmp_path, {"head": "55b9e95", "slices": []})
    same = lw_rundash.build_run_view(
        control_dir=tmp_path / "control", manifest_path=manifest, repo_root=tmp_path,
        now_ts=now, cache={}, runner=fake_git(oid="55b9e95ffff"), pid_alive=lambda pid: False)
    assert same["run"]["head_moved"] is False
    moved = lw_rundash.build_run_view(
        control_dir=tmp_path / "control", manifest_path=manifest, repo_root=tmp_path,
        now_ts=now, cache={}, runner=fake_git(oid="deadbeef0000"), pid_alive=lambda pid: False)
    assert moved["run"]["head_moved"] is True


def test_a_git_failure_never_reaches_the_payload_as_a_raw_error(tmp_path):
    manifest = write_manifest(tmp_path, {"slices": []})
    secret = "fatal: not a git repository (or any of the parent directories)"
    view = lw_rundash.build_run_view(
        control_dir=tmp_path / "control", manifest_path=manifest, repo_root=tmp_path,
        now_ts=time.time(), cache={}, runner=fake_git(rc=128, stderr=secret),
        pid_alive=lambda pid: False)
    assert view["run"]["git_ok"] is False
    assert "fatal" not in json.dumps(view)


# ------------------------------------------------------ P3: resume decision


def test_a_dirty_agent_worktree_makes_the_verdict_salvage_first(tmp_path):
    now = time.time()
    manifest = write_manifest(tmp_path, {"slices": [
        {"id": "B3", "status": "in_progress", "updated": iso(now)}]})
    runner = fake_git(
        worktrees=[{"path": str(tmp_path), "branch": "main"},
                   {"path": "C:/wt/b3", "branch": "worktree-agent-B3"}],
        status={"C:/wt/b3": ["? tools/lw_rundash.py"]})
    view = lw_rundash.build_resume_view(
        control_dir=tmp_path / "control", manifest_path=manifest, repo_root=tmp_path,
        now_ts=now, cache={}, runner=runner, pid_alive=lambda pid: False)
    assert view["verdict"] == "SALVAGE FIRST"
    assert view["stranded"][0]["files"] == ["tools/lw_rundash.py"]
    assert view["open_count"] == 1


def test_a_clean_fleet_is_resume_safe(tmp_path):
    manifest = write_manifest(tmp_path, {"slices": []})
    runner = fake_git(worktrees=[{"path": str(tmp_path), "branch": "main"}])
    view = lw_rundash.build_resume_view(
        control_dir=tmp_path / "control", manifest_path=manifest, repo_root=tmp_path,
        now_ts=time.time(), cache={}, runner=runner, pid_alive=lambda pid: False)
    assert view["verdict"] == "RESUME SAFE"


def test_the_controller_log_tail_is_pinned_only_when_the_run_is_dead(tmp_path):
    now = time.time()
    ctl = control(tmp_path, log="cycle 11 ok\ncycle 12 ok\nNO_WORK\n")
    manifest = write_manifest(tmp_path, {"slices": []})
    runner = fake_git(worktrees=[{"path": str(tmp_path), "branch": "main"}])
    dead = lw_rundash.build_resume_view(
        control_dir=ctl, manifest_path=manifest, repo_root=tmp_path, now_ts=now,
        cache={}, runner=runner, pid_alive=lambda pid: False)
    assert dead["run_state"] == "DEAD"
    assert dead["log_tail"][-1] == "NO_WORK"

    control(tmp_path, lock={"pid": 7, "ts": now - 5})
    live = lw_rundash.build_resume_view(
        control_dir=ctl, manifest_path=manifest, repo_root=tmp_path, now_ts=now,
        cache={}, runner=runner, pid_alive=lambda pid: True)
    assert live["run_state"] == "LIVE"
    assert live["log_tail"] == []


def test_a_git_failure_degrades_the_resume_panel_without_leaking_stderr(tmp_path):
    manifest = write_manifest(tmp_path, {"slices": []})
    secret = "fatal: could not read Username for 'https://example.invalid'"
    view = lw_rundash.build_resume_view(
        control_dir=tmp_path / "control", manifest_path=manifest, repo_root=tmp_path,
        now_ts=time.time(), cache={}, runner=fake_git(rc=1, stderr=secret),
        pid_alive=lambda pid: False)
    assert view["inventory_ok"] is False
    assert view["git_message"]
    assert "fatal" not in json.dumps(view)


# ----------------------------------------------------------------- plumbing


def test_the_session_dir_is_discovered_by_newest_subagents_dir(tmp_path):
    old = tmp_path / "old-session" / "subagents"
    old.mkdir(parents=True)
    new = tmp_path / "new-session" / "subagents"
    new.mkdir(parents=True)
    import os
    os.utime(old, (time.time() - 9000, time.time() - 9000))
    assert lw_rundash.newest_session_dir(tmp_path) == new.parent
    assert lw_rundash.newest_session_dir(tmp_path / "nope") is None


def test_the_cycle_cap_comes_from_the_loop_config(tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"max_cycles": 12}), encoding="utf-8")
    assert lw_rundash.read_cycle_cap(cfg) == 12
    assert lw_rundash.read_cycle_cap(tmp_path / "absent.json") is None
    cfg.write_text("{not json", encoding="utf-8")
    assert lw_rundash.read_cycle_cap(cfg) is None


# ------------------------------------------------------------- HTTP surface


@pytest.fixture
def server(tmp_path):
    now = time.time()
    manifest = write_manifest(tmp_path, {"run_id": "http-run", "head": "55b9e95",
                                         "updated": iso(now), "slices": [
        {"id": "B3", "title": "rundash", "status": "in_progress", "updated": iso(now)}]})
    ctl = control(tmp_path, cycle=4, log="cycle 4 start\n")
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"max_cycles": 12}), encoding="utf-8")
    page = tmp_path / "rundash.html"
    page.write_text("<h1>LW RUNDASH TEST PAGE</h1>", encoding="utf-8")
    srv = lw_rundash.RunDashServer(
        ("127.0.0.1", 0), lw_rundash.Handler, control_dir=ctl, manifest_path=manifest,
        config_path=cfg, page_path=page, repo_root=tmp_path, session_dir=None,
        runner=fake_git(worktrees=[{"path": str(tmp_path), "branch": "main"}]),
        pid_alive=lambda pid: False, cache={})
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


def _get(port, path, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path, headers={"Host": host} if host else {})
    resp = conn.getresponse()
    body = resp.read()
    out = (resp.status, resp.getheader("Content-Type") or "",
           resp.getheader("Cache-Control") or "", body)
    conn.close()
    return out


def test_http_serves_the_page(server):
    status, ctype, cache, body = _get(server.server_address[1], "/")
    assert status == 200
    assert ctype.startswith("text/html")
    assert b"LW RUNDASH TEST PAGE" in body


def test_http_run_route_is_enveloped_and_uncached(server):
    status, ctype, cache, body = _get(server.server_address[1], "/api/run")
    assert status == 200
    assert ctype.startswith("application/json")
    assert cache == "no-store"
    payload = json.loads(body)
    assert payload["ok"] is True
    assert payload["run"]["run_id"] == "http-run"
    assert payload["run"]["cycle_cap"] == 12
    assert payload["slices"][0]["evidence"]["state"] == "NOT OBSERVED"


def test_http_resume_route_returns_a_verdict(server):
    status, _ctype, cache, body = _get(server.server_address[1], "/api/resume")
    assert status == 200
    assert cache == "no-store"
    assert json.loads(body)["verdict"] in ("RESUME SAFE", "SALVAGE FIRST")


def test_http_health_route(server):
    status, _c, _cc, body = _get(server.server_address[1], "/api/health")
    payload = json.loads(body)
    assert status == 200
    assert payload["ok"] is True
    assert payload["port"] == server.server_address[1]


def test_http_foreign_host_is_refused(server):
    status, _c, _cc, body = _get(server.server_address[1], "/api/run", host="evil.example.com")
    assert status == 403
    assert json.loads(body)["ok"] is False


def test_http_unknown_route_is_a_clean_404(server):
    status, _c, _cc, body = _get(server.server_address[1], "/api/nope")
    assert status == 404
    assert json.loads(body)["ok"] is False


def test_a_second_bind_defers_instead_of_crashing(tmp_path, monkeypatch):
    holder = lw_rundash.RunDashServer(
        ("127.0.0.1", 0), lw_rundash.Handler, control_dir=tmp_path,
        manifest_path=tmp_path / "m.json", config_path=tmp_path / "c.json",
        page_path=tmp_path / "p.html", repo_root=tmp_path, cache={})
    port = holder.server_address[1]
    opened = []
    monkeypatch.setattr(lw_rundash.webbrowser, "open", lambda url: opened.append(url))
    try:
        rc = lw_rundash.main(["--port", str(port), "--open", "--log-file", str(tmp_path / "rd.log")])
    finally:
        holder.server_close()
    assert rc == 0
    assert opened and str(port) in opened[0]


# ------------------------------------------------------- authored-text rules


def test_the_page_and_the_module_are_7_bit_ascii():
    # By byte scan, not by eye. A stray en-dash in a double-quoted PowerShell
    # string is what started this rule; the HTML is the easiest place to slip.
    for path in (PAGE, MODULE, Path(__file__)):
        raw = path.read_bytes()
        bad = [(i, b) for i, b in enumerate(raw) if b > 127]
        assert not bad, f"{path.name} has non-ASCII bytes at {bad[:5]}"


def test_no_dollar_figure_appears_anywhere_on_the_page_or_in_the_payload(tmp_path):
    # LEDGER 40: Claude cost accounting is notional on a Max plan. Tokens only.
    html = PAGE.read_text(encoding="ascii")
    assert not re.search(r"\$\s*[0-9]", html)
    for word in ("usd", "dollar", "cost_usd", "ceiling"):
        assert word not in html.lower()
    now = time.time()
    manifest = write_manifest(tmp_path, {"slices": [
        {"id": "B3", "status": "in_progress", "updated": iso(now)}]})
    view = lw_rundash.build_run_view(
        control_dir=tmp_path / "control", manifest_path=manifest, repo_root=tmp_path,
        now_ts=now, cache={}, runner=fake_git(), pid_alive=lambda pid: False)
    # Scrub the tmp dir first - pytest names it after this test, so the word
    # under test is in every absolute path the payload legitimately carries.
    blob = json.dumps(view).lower().replace(json.dumps(str(tmp_path))[1:-1].lower(), "<tmp>")
    for word in ("usd", "dollar", "cost"):
        assert word not in blob


def test_the_page_carries_the_p1_and_p3_panels_and_the_amber_chip():
    html = PAGE.read_text(encoding="ascii")
    assert "Run Ledger" in html
    assert "Resume Decision" in html
    assert "NOT OBSERVED" in html
    assert "esc(" in html  # every insertion goes through the escaper


def test_the_page_never_writes_with_fetch():
    # Read-only service: the page must not POST anything but the shutdown the
    # operator explicitly clicks, and it does not have that button.
    html = PAGE.read_text(encoding="ascii")
    assert "method:" not in html.replace(" ", "")
    assert "POST" not in html


def test_the_module_never_prints(tmp_path):
    # pythonw has no stdout; a print here is a silent hang risk, not a log line.
    src = MODULE.read_text(encoding="ascii")
    assert not re.search(r"(?<![.\w])print\s*\(", src)
