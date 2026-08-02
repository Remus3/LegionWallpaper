#!/usr/bin/env python
"""LW-CIWatchdog - unattended red-main CI auto-fixer.

One pass per invocation, then exit. The scheduled task (`LW-CIWatchdog`, at
startup + every 2 minutes) is the loop; this file deliberately is not, so a
wedged pass dies with its process instead of living forever.

Shape of a pass:

    HALT? -> lock -> check_ci(main) -> settled failure? -> isolated worktree
    -> headless `claude -p` fixes it there -> push branch -> open PR
    -> the PR's OWN CI must go green on its OWN head sha -> merge -> clean up

This tool can push and merge. Three rails, all tested in
`tests/test_ci_watchdog.py`:

  1. HALT is checked FIRST and answers everything. A kill switch that only works
     when the tool is otherwise healthy is not a kill switch.
     Kill: create `ops\\runtime\\ci_watchdog\\HALT`, or
     `Disable-ScheduledTask LW-CIWatchdog`.
  2. Ambiguity NEVER means act. `queued` / `pending` / `unavailable` /
     `not-evaluated` all WAIT; only a settled `failure` triggers a fix. That
     distinction is exactly what f1 item 12 built into `truth_gate.check_ci`,
     and this tool reuses that function rather than re-deriving it - an
     abbreviated sha reaching `gh run list` returns [] and would otherwise read
     as "nothing owed".
  3. The merge self-gates on the FIX BRANCH's own green CI AT ITS OWN HEAD SHA.
     A stale success from an earlier push to the same branch is the trap that
     turns one red main into two.

Per-sha attempt budget (default 2). A transient Anthropic condition (credit /
rate limit / overloaded) does NOT burn an attempt - same class the weekly-hygiene
wrapper already handles, and one bad afternoon must not exhaust the budget on a
repo that was never broken.

Every subprocess sets CREATE_NO_WINDOW: a console flashing on the operator's
desktop is a recurring real defect here, and this thing runs every 2 minutes.

Exit codes: 0 pass completed (including "nothing to do"), 1 pass failed, 2 usage.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "ops" / "runtime" / "ci_watchdog"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

HALT_FILE = "HALT"
LOCK_FILE = "lock.json"
STATE_FILE = "state.json"
# A fix pass (worktree + model + suite) runs far longer than the 2-minute
# trigger, so overlapping invocations are the DEFAULT, not an edge case. The
# stale window is generous enough that a slow-but-live pass is never stolen.
LOCK_STALE_S = 3600.0
MAX_ATTEMPTS = 2
BASE_BRANCH = "main"
# Poll budget for the fix branch's own CI. 40 * 30s = 20 minutes, comfortably
# past a normal run, and a timeout leaves the PR OPEN for the operator rather
# than merging it unverified.
PR_CI_POLLS = 40
PR_CI_INTERVAL_S = 30.0

_TRANSIENT = re.compile(
    r"credit balance is too low|rate[ _-]?limit|overloaded|too many requests"
    r"|status(?: code)? (?:429|529)|insufficient (?:credit|quota)",
    re.IGNORECASE)


def _bind_truth_gate():
    """Bind tools/truth_gate.py BY PATH - tools/ is not importable as a package."""
    spec = importlib.util.spec_from_file_location(
        "lw_ci_watchdog_truth_gate", ROOT / "tools" / "truth_gate.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ==========================================================================
# Pure decision logic - no network, no worktree, no model
# ==========================================================================
def halted(state_dir):
    """The HALT file's contents, or a generic reason if it is empty.

    An empty file still halts: `type nul > HALT` is the likeliest way an
    operator creates one under stress, and reading that as "no halt" would
    disarm the kill switch at exactly the moment it is being used.
    """
    p = Path(state_dir) / HALT_FILE
    if not p.is_file():
        return None
    try:
        body = p.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        body = ""
    return body or "HALT file present"


def decide(ci, state, *, max_attempts=MAX_ATTEMPTS, halt=None):
    """What this pass should do. Returns {"action", "reason", "sha"}.

    Actions: halt | idle | wait | fix | give-up. Anything not understood WAITS -
    acting on an unrecognised status is how an auto-fixer starts inventing work.
    """
    if halt:
        return {"action": "halt", "reason": halt, "sha": None}
    status = (ci or {}).get("status")
    sha = (ci or {}).get("sha")
    if status in ("success", "not-evaluated"):
        return {"action": "idle", "reason": f"CI {status}", "sha": sha}
    if status != "failure":
        return {"action": "wait",
                "reason": f"CI {status!r} is not settled - not acting", "sha": sha}
    # The budget is PER SHA: a different failure deserves its own attempts, or
    # one exhausted sha wedges the watchdog forever.
    attempts = int(state.get("attempts", 0)) if state.get("sha") == sha else 0
    if attempts >= max_attempts:
        return {"action": "give-up",
                "reason": f"{attempts} attempts already spent on {sha[:8] if sha else '?'} "
                          f"(max {max_attempts}) - leaving it for the operator",
                "sha": sha}
    return {"action": "fix", "reason": f"CI failure on {sha[:8] if sha else '?'}",
            "sha": sha}


def bump_attempt(state, sha):
    """Attempt counter for `sha`. Pure - returns a new dict."""
    if state.get("sha") == sha:
        return {"sha": sha, "attempts": int(state.get("attempts", 0)) + 1}
    return {"sha": sha, "attempts": 1}


def branch_name(sha, attempt):
    return f"ci-fix/{(sha or 'unknown')[:8]}-{attempt}"


def merge_allowed(pr_ci, head_sha):
    """Merge only on the fix branch's OWN success at the head being merged.

    The sha equality is the load-bearing half. A success left over from an
    earlier push to the same branch is a real green for a commit nobody is
    merging, and taking it would put an unverified fix on main.
    """
    if not isinstance(pr_ci, dict):
        return False
    return pr_ci.get("status") == "success" and pr_ci.get("sha") == head_sha


def is_transient(text):
    """A vendor-side condition that is not a repo fault, so it must not burn an
    attempt. Same class the weekly-hygiene wrapper already detects."""
    return bool(_TRANSIENT.search(text or ""))


# ==========================================================================
# Single instance
# ==========================================================================
def acquire(state_dir, pid=None, now=None):
    """Take the pass lock. False when a live pass already holds it.

    A corrupt or unreadable lock file is treated as FREE: a wedged watchdog that
    cannot be restarted is worse than a rare double pass, and the worktree
    branch names carry the attempt number so a collision is visible.
    """
    d = Path(state_dir)
    d.mkdir(parents=True, exist_ok=True)
    pid = os.getpid() if pid is None else pid
    now = time.time() if now is None else now
    lock = d / LOCK_FILE
    if lock.is_file():
        try:
            rec = json.loads(lock.read_text(encoding="utf-8"))
            if now - float(rec.get("ts", 0)) < LOCK_STALE_S:
                return False
        except (OSError, ValueError, TypeError):
            pass
    _awrite(lock, json.dumps({"pid": pid, "ts": now}))
    return True


def release(state_dir):
    (Path(state_dir) / LOCK_FILE).unlink(missing_ok=True)


def _awrite(path, text):
    """Atomic write, per the project hard rule - consumers may poll mid-write."""
    path = Path(path)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def read_state(state_dir):
    try:
        return json.loads((Path(state_dir) / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_state(state_dir, state):
    _awrite(Path(state_dir) / STATE_FILE, json.dumps(state, indent=2))


# ==========================================================================
# IO
# ==========================================================================
def log(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} [ci_watchdog] {msg}"
    print(line, flush=True)
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(STATE_DIR / "watchdog.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def run(argv, cwd=None, timeout=600, stdin=None):
    return subprocess.run(argv, cwd=str(cwd or ROOT), input=stdin,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout,
                          creationflags=NO_WINDOW)


FIX_PROMPT = """\
This is an UNATTENDED scheduled run. No operator is watching the chat.

CI is RED on {base} at {sha}. Failing runs: {runs}

Your job is ONLY to make CI green again. Specifically:

1. Read the failing run's logs (`gh run view <id> --log-failed`) and find the
   ACTUAL cause. Do not guess from the test name.
2. Fix the cause, not the symptom. If the fix belongs to a family of similar
   cases, grep for the siblings and fix them too.
3. Run the full suite locally and confirm it passes before committing.
4. Commit on the CURRENT branch (you are already on a fix branch in an isolated
   worktree - do NOT switch branches, do NOT touch main).

HARD BOUNDARIES:
- Do NOT push, do NOT open a PR, do NOT merge. The watchdog does all three, and
  it self-gates the merge on this branch's own green CI.
- Do NOT change test expectations to make a test pass unless the expectation is
  provably the bug. Say so explicitly in the commit message if you do.
- Do NOT widen scope. A CI fix is not a refactor.
- Follow CLAUDE.md: 7-bit ASCII only, no em-dashes, no Co-Authored-By trailer.
- If you cannot find a real cause, make NO commit and say why. An empty pass is
  a fine outcome; a speculative commit on main is not.
"""


def _fix_in_worktree(wt, sha, runs, model, timeout):
    """Run headless claude inside the worktree. Returns (ok, transient, output)."""
    prompt = FIX_PROMPT.format(base=BASE_BRANCH, sha=sha, runs=runs)
    argv = ["claude", "-p", prompt, "--model", model,
            "--permission-mode", "bypassPermissions",
            "--add-dir", str(wt)]
    try:
        r = run(argv, cwd=wt, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, False, "timeout"
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0 and is_transient(out):
        return False, True, out[-2000:]
    return r.returncode == 0, False, out[-2000:]


def _head_of(wt):
    r = run(["git", "rev-parse", "HEAD"], cwd=wt, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else ""


def _cleanup_worktree(wt, branch, *, keep):
    if keep:
        log(f"worktree kept for inspection: {wt} ({branch})")
        return
    run(["git", "worktree", "remove", "--force", str(wt)], timeout=120)
    run(["git", "branch", "-D", branch], timeout=60)


def do_fix_pass(sha, runs, attempt, tg, *, model, dry_run, fix_timeout):
    """One fix attempt: worktree -> model -> push -> PR -> self-gate -> merge."""
    branch = branch_name(sha, attempt)
    wt = ROOT / "worktrees" / branch.replace("/", "_")
    if dry_run:
        log(f"DRY RUN: would create {wt} on {branch} and attempt a fix")
        return True

    r = run(["git", "worktree", "add", "-b", branch, str(wt), BASE_BRANCH],
            timeout=300)
    if r.returncode != 0:
        log(f"worktree add failed: {r.stderr.strip()[:300]}")
        return False
    keep = False
    try:
        before = _head_of(wt)
        ok, transient, out = _fix_in_worktree(wt, sha, runs, model, fix_timeout)
        if transient:
            # Vendor-side, not a repo fault. Reported by the caller as a
            # non-attempt so one bad afternoon cannot exhaust the budget.
            log("transient API condition - not burning an attempt")
            return "transient"
        after = _head_of(wt)
        if after == before:
            log(f"no commit made (claude ok={ok}) - nothing to push. tail: {out[-300:]}")
            return False
        r = run(["git", "push", "-u", "origin", branch], cwd=wt, timeout=300)
        if r.returncode != 0:
            log(f"push failed: {r.stderr.strip()[:300]}")
            return False
        r = run(["gh", "pr", "create", "--base", BASE_BRANCH, "--head", branch,
                 "--title", f"ci: auto-fix red {BASE_BRANCH} at {sha[:8]}",
                 "--body", f"Automated by LW-CIWatchdog for the CI failure on "
                           f"{sha}.\n\nMerge is self-gated on this branch's own "
                           f"green CI at its own head sha."],
                cwd=wt, timeout=180)
        if r.returncode != 0:
            log(f"pr create failed: {r.stderr.strip()[:300]}")
            keep = True
            return False
        log(f"PR opened for {branch} @ {after[:8]}; waiting on its own CI")
        for _ in range(PR_CI_POLLS):
            pr_ci = tg.check_ci(after)
            if merge_allowed(pr_ci, after):
                m = run(["gh", "pr", "merge", branch, "--squash", "--delete-branch"],
                        cwd=wt, timeout=300)
                if m.returncode == 0:
                    log(f"merged {branch} - {BASE_BRANCH} should be green")
                    return True
                log(f"merge failed: {m.stderr.strip()[:300]}")
                keep = True
                return False
            if pr_ci.get("status") == "failure":
                log(f"fix branch's OWN CI is red - refusing to merge {branch}")
                keep = True
                return False
            time.sleep(PR_CI_INTERVAL_S)
        log(f"fix branch CI never settled - PR left OPEN for the operator ({branch})")
        keep = True
        return False
    finally:
        _cleanup_worktree(wt, branch, keep=keep)


def one_pass(*, model, dry_run, max_attempts, fix_timeout, state_dir=STATE_DIR):
    reason = halted(state_dir)
    if reason:
        log(f"HALT: {reason}")
        return 0
    if not acquire(state_dir):
        log("another pass holds the lock - exiting")
        return 0
    try:
        tg = _bind_truth_gate()
        ci = tg.check_ci("HEAD")
        state = read_state(state_dir)
        d = decide(ci, state, max_attempts=max_attempts)
        log(f"{d['action']}: {d['reason']}")
        if d["action"] != "fix":
            return 0
        state = bump_attempt(state, d["sha"])
        write_state(state_dir, state)
        runs = ", ".join(x.get("name", "?") for x in (ci.get("runs") or []))
        result = do_fix_pass(d["sha"], runs, state["attempts"], tg,
                             model=model, dry_run=dry_run, fix_timeout=fix_timeout)
        if result == "transient":
            # Refund: the repo was never the problem.
            write_state(state_dir, {"sha": d["sha"],
                                    "attempts": max(0, state["attempts"] - 1)})
            return 0
        return 0 if result else 1
    finally:
        release(state_dir)


# ==========================================================================
# Self-registration (the LW convention: a task is installed by its own tool)
# ==========================================================================
TASK_NAME = "LW-CIWatchdog"
TASK_XML = ROOT / "ops" / "runtime" / "lw_ci_watchdog_task.xml"


def task_xml(python_exe, script, *, every_minutes=2):
    """Task Scheduler XML for a boot trigger that REPEATS.

    `schtasks /Create` cannot express this: `/RI` is rejected outright for
    `/SC ONSTART` (and for ONLOGON - the same wall `lw_wallpaper_rotate` hit).
    So the trigger goes through XML, exactly as that tool does.

    A BootTrigger's Repetition only starts when the trigger FIRES, so a
    boot-only task registers Ready and sits idle until the next reboot. The
    TimeTrigger below arms the repeat from install time, which is the same
    correction `docs/OPERATIONS.md` records for any LW-* task wanting a repeat.
    """
    start = time.strftime("%Y-%m-%dT%H:%M:%S")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>LW CI watchdog - red-main auto-fixer. Kill switch: create
ops\\runtime\\ci_watchdog\\HALT or Disable-ScheduledTask {TASK_NAME}.</Description>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
      <Repetition>
        <Interval>PT{every_minutes}M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </BootTrigger>
    <TimeTrigger>
      <StartBoundary>{start}</StartBoundary>
      <Enabled>true</Enabled>
      <Repetition>
        <Interval>PT{every_minutes}M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>Administrator</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>"{python_exe}"</Command>
      <Arguments>"{script}"</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def install():
    TASK_XML.parent.mkdir(parents=True, exist_ok=True)
    xml = task_xml(sys.executable, str(Path(__file__).resolve()))
    # UTF-16 with a BOM: schtasks /XML rejects anything else for this schema.
    tmp = Path(str(TASK_XML) + ".tmp")
    tmp.write_bytes(xml.encode("utf-16"))
    tmp.replace(TASK_XML)
    r = run(["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(TASK_XML), "/F"],
            timeout=120)
    print((r.stdout or r.stderr).strip())
    return r.returncode


def uninstall():
    r = run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], timeout=120)
    print((r.stdout or r.stderr).strip())
    return r.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", default="claude-sonnet-5",
                    help="model for the fix pass (a CI fix is diagnosis, not design)")
    ap.add_argument("--dry-run", action="store_true",
                    help="decide and log, but never create a worktree or push")
    ap.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS,
                    help="fix attempts per failing sha before giving up")
    ap.add_argument("--fix-timeout", type=float, default=3600.0,
                    help="seconds the headless fix pass may run")
    ap.add_argument("--status", action="store_true",
                    help="print the decision and exit without acting")
    ap.add_argument("--install", action="store_true",
                    help=f"register the {TASK_NAME} scheduled task")
    ap.add_argument("--uninstall", action="store_true",
                    help=f"remove the {TASK_NAME} scheduled task")
    args = ap.parse_args(argv)
    if args.install:
        return install()
    if args.uninstall:
        return uninstall()
    if args.status:
        tg = _bind_truth_gate()
        ci = tg.check_ci("HEAD")
        print(json.dumps({"ci": ci, "state": read_state(STATE_DIR),
                          "halt": halted(STATE_DIR),
                          "decision": decide(ci, read_state(STATE_DIR),
                                             max_attempts=args.max_attempts,
                                             halt=halted(STATE_DIR))}, indent=2))
        return 0
    return one_pass(model=args.model, dry_run=args.dry_run,
                    max_attempts=args.max_attempts, fix_timeout=args.fix_timeout)


if __name__ == "__main__":
    raise SystemExit(main())
