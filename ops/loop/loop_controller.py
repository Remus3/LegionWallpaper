#!/usr/bin/env python
"""gemini-headless-upgrade loop controller (the BRAIN).

Headless. Never touches the GUI. Drives the cycle:
  gemini-director -> directive.md + gemini.ready -> (AHK types) -> claude.done
  -> meter budget -> gemini-auditor -> clean:advance | regress:FIX-first -> repeat

IPC = files in control_dir, atomic (tmp + os.replace), plain-text where AHK reads.
Both gemini and claude are stateless per cycle; continuity lives on disk
(git history + docs/LEDGER.md + the directive chain). Ported 1:1 from the RC
ancestor loop - process mechanics unchanged, product references TBD.
"""
import importlib.util
import json
import os
import re
import uuid
import subprocess
import sys
import time
from pathlib import Path

# Legion focus-steal rule: the controller runs under pythonw, so any console
# child would allocate its own window and flash on the operator's desktop.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ops/loop is never on sys.path (the controller is launched by absolute path);
# bind the sibling executor module explicitly, same pattern as the adjudicator.
def _bind(modname, filename):
    if modname in sys.modules:
        return sys.modules[modname]
    spec = importlib.util.spec_from_file_location(
        modname, Path(__file__).resolve().parent / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


executor = _bind("lw_loop_executor", "executor.py")
# slots.py + winmutex.py are BYTE-IDENTICAL across LW and RC by contract - they
# coordinate the two repos' runs with each other through ProgramData and the OS
# mutex namespace, so a divergence is a silent concurrency bug, not a conflict.
slots = _bind("lw_loop_slots", "slots.py")
winmutex = _bind("lw_loop_winmutex", "winmutex.py")

# Module-RELATIVE, not an absolute path only this machine has. The previous
# fallback hardcoded C:\LegionWallpaper\...\config.json, and the comment below
# justified the empty-CFG branch with "a clean checkout has no config.json" -
# which is false: all four ops/loop/config*.json are tracked. The file was
# always there; it was addressed by a path that only resolves on Legion. So a
# Linux runner silently took the CFG = {} branch and every import-time consumer
# of CFG tested a configuration that never runs in production, while the same
# tests passed here against the real one. Same environment-dependent-truth
# family as f1 item 12. Resolves identically on Legion, so this is not a
# behaviour change where the loop actually runs. Found by RC 261aeb30.
_CFG_ARG = (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith(".json")
            else str(Path(__file__).resolve().parent / "config.json"))
try:
    CFG = json.loads(Path(_CFG_ARG).read_text(encoding="utf-8"))
except (FileNotFoundError, OSError, json.JSONDecodeError):
    # Genuinely absent or unreadable config: the pure helpers under unit test
    # never read CFG, and a live launch always passes a real config path.
    CFG = {}
def _cfg_path(key, default):
    """Adopt a config-supplied path ONLY when it is absolute on THIS platform.

    A drive-letter string is absolute on Windows and a RELATIVE single-component
    name on POSIX: Path("C:\\LegionWallpaper").is_absolute() is False there, and
    the name keeps its backslashes. Adopting one would make the mkdir below mint
    a literal `C:\\LegionWallpaper\\ops\\loop\\control` directory inside whatever
    CWD imported this module.

    That became reachable only when the config started loading off Legion. While
    _CFG_ARG was a hardcoded absolute, the read failed everywhere else and
    CFG = {} meant these defaults always applied - so fixing that path exposed
    this one. Second-order effect of my own fix, caught by RC flagging the same
    is_absolute() rule on their side before it reached a runner here.
    """
    raw = CFG.get(key)
    if raw and Path(raw).is_absolute():
        return Path(raw)
    return Path(default)


ROOT = _cfg_path("repo_root", Path(__file__).resolve().parents[2])
CTL = _cfg_path("control_dir", Path(__file__).resolve().parent / "control")
CTL.mkdir(parents=True, exist_ok=True)
DRY = bool(CFG.get("dry_run", False))
GEMINI_USD = 0.0  # cumulative estimated Gemini spend - THIS is the capped budget (not Claude)
RUN_ID = ""  # minted in main(); namespaces logs + slot payloads across concurrent runs

def log(m):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {m}"
    print(line, flush=True)
    with open(CTL / "controller.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")

def awrite(path, text):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)

def consume_directive_override(ctl=None):
    """One-shot operator directive override (written by the operator; the RC
    ancestor exposed a POST /api/loop-control channel for this - the LW
    equivalent is TBD, product not yet defined).

    Returns the override text and removes the file so it applies to exactly one
    cycle, or None when absent / empty. Default-absent => byte-identical loop.
    """
    base = Path(ctl) if ctl is not None else CTL
    p = base / "directive_override.md"
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:  # noqa: BLE001
        text = ""
    p.unlink(missing_ok=True)
    return text or None

def cycle_source(cfg, override):
    """Pure: which directive source feeds this cycle. Precedence:
    operator override > cycle_command > fixed_directive > gemini director.

    cycle_command (e.g. a self-directing slash command like /LW-Continue) is
    typed VERBATIM after /clear and SKIPS the gemini director - the command
    self-directs from its own living plan - but KEEPS the gemini auditor each
    cycle. fixed_directive skips BOTH director and auditor. Default-absent both
    => 'director' (byte-identical to the historical loop)."""
    if override:
        return "override"
    if cfg.get("cycle_command"):
        return "cycle_command"
    if cfg.get("fixed_directive"):
        return "fixed"
    return "director"

def rjson(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default

def stop(reason):
    awrite(CTL / "STOP", reason)
    log(f"STOP written: {reason}")
    sys.exit(0)

# ---- git helpers -------------------------------------------------------
def git(*args):
    # Bound every git call: the headless loop has NO deadline around these
    # synchronous reads (wait_for/wait_gone only cover the AHK handshake), so a
    # wedged git (stale index.lock, hung hook) would strand the unattended run.
    # Degrade a timeout / failure to "" - callers already tolerate empty
    # (prev_sha[:8] of "" is "", auditor guards `if not new_sha`).
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args],
                              capture_output=True, text=True, timeout=30,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    except (subprocess.SubprocessError, OSError) as e:
        log(f"git {args[0] if args else ''} failed: {e}")
        return ""

def head():
    return git("rev-parse", "HEAD")

def _rev_parse(ref):
    """Resolve a git ref to a sha, or '' when it does not exist (e.g. HEAD~2 in a
    young repo). git() already degrades a bad ref / failure to '' (rev-parse
    --verify -q prints nothing + exits non-zero), so this never raises."""
    return git("rev-parse", "--verify", "-q", ref)

def _is_ancestor(a, b):
    """True iff commit a is an ancestor of (or identical to) commit b. Uses a
    direct call because the answer is the EXIT CODE, not stdout, and the
    stdout-only git() helper cannot express it."""
    if not a or not b:
        return False
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", a, b],
            capture_output=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False

def audit_range(clean_sha, new_sha):
    """base..new_sha the gemini auditor scores each cycle (RC-ancestor lesson R61).

    ROOT CAUSE (false-positive REGRESS recursion): the old window was the single
    cycle's commits (prev_sha..new_sha). A /done docs-sync commit that lands in
    its OWN cycle was audited in isolation - the auditor saw docs asserting an
    engine/logic change whose code was committed a cycle earlier and lay OUTSIDE
    the window, so the lone docs commit read as a regression. That fed a
    FIX-FIRST directive with nothing to fix, which shipped another docs commit,
    audited alone again: an infinite REGRESS loop.

    Fix: never audit a lone commit. base = the OLDER of the last-CLEAN anchor and
    new_sha~2, so (a) a docs commit always carries the commit(s) it documents,
    and (b) an unresolved REGRESS chain keeps its full context back to the last
    known-good state. Fallbacks for a young repo: new_sha~2 -> new_sha~1 ->
    new_sha (a bare sha = a valid whole-tree diff)."""
    floor = _rev_parse(f"{new_sha}~2")
    if clean_sha and floor:
        # keep the clean anchor only while it is OLDER than the 2-commit floor;
        # otherwise widen to the floor so the window is never a single commit.
        base = clean_sha if _is_ancestor(clean_sha, floor) else floor
    else:
        base = clean_sha or floor
    base = base or _rev_parse(f"{new_sha}~1")
    return f"{base}..{new_sha}" if base else new_sha

def tail(rel, n, root=None):
    base = Path(root) if root is not None else ROOT
    p = base / rel
    if not p.exists():
        return ""
    return "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[-n:])

def head_lines(rel, n, root=None):
    # The HEAD n lines. For a newest-first append-at-top ledger (docs/LEDGER.md)
    # this is the NEWEST n entries. Using tail() here was the continuity bug:
    # it fed the director the OLDEST ledger items, so just-completed work was
    # invisible and the director re-proposed already-shipped items.
    base = Path(root) if root is not None else ROOT
    p = base / rel
    if not p.exists():
        return ""
    return "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[:n])

def cap_bytes(text, limit, label):
    # 2026-07-01 NO_WORK-starvation fix (RC ancestor): the director prompt went
    # out at 572KB (the plan grew a 289KB findings log; modern LEDGER items are
    # multi-KB single lines, so head-60 was 93KB) and gemini completed with an
    # EMPTY body -> misread as NO_WORK -> STOP with 5 OPEN queue rows. Doc
    # growth must never starve the director again: keep the HEAD (queue tables
    # / newest entries live at the top of both docs) and stamp a visible cut.
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[{label} truncated at {limit} bytes - full text in the repo file]"

# Hard byte budgets for the unbounded director-context components.
# 2026-07-02 re-tighten (RC ancestor): gemini CLI silently returns EMPTY stdout
# above ~80KB stdin (80KB delivered fine, 160KB empty, no stderr error -
# measured live; the 01:56 outage killed cycles 9-100 of the prior run). The
# 2026-07-01 caps (140K plan alone) still allowed a >160KB total, so every
# component cap now fits the WHOLE prompt inside GEMINI_STDIN_CAP with headroom.
# 2026-07-03 re-tighten AGAIN: the threshold DRIFTS - a 79,911-byte director
# payload (cap_stdin-trimmed to the old 80,000 ceiling) returned silent EMPTY
# every try (both pro + flash), burning cycles 10-32 directive-less; the SAME
# payload truncated to 70,000 and 60,000 bytes both delivered (measured live).
# Treat the ceiling as weather, not physics: sit well under the worst
# measurement. Component caps compose to ~56KB with the ~16KB template/digest/
# chain overhead, so a normal prompt never even hits the cap_stdin backstop.
PLAN_CTX_CAP = 24_000
LEDGER_CTX_CAP = 8_000
ROADMAP_CTX_CAP = 8_000

# Proven-safe gemini stdin ceiling (see above). cap_stdin() backstops EVERY
# gemini() call (director / auditor / stall) at this size.
GEMINI_STDIN_CAP = 60_000

def cap_stdin(body, limit=None):
    """Backstop: keep the HEAD (prompt template + instructions) and the TAIL
    (directive_suffix / escalation / final rules); cut the expendable middle."""
    lim = GEMINI_STDIN_CAP if limit is None else limit
    if len(body) <= lim:
        return body
    marker = "\n...[STDIN CAP: middle truncated to fit the gemini CLI stdin limit - head + tail preserved]...\n"
    keep = lim - len(marker)
    head = int(keep * 0.6)
    return body[:head] + marker + body[len(body) - (keep - head):]

# ---- directive-chain continuity (persisted; survives controller restarts) ---
def directive_title(body):
    """A compact one-line label for an issued directive (for the chain digest)."""
    if not body:
        return "(empty)"
    theme = scope = ""
    for line in body.splitlines():
        s = line.strip()
        u = s.upper()
        if u.startswith("THEME:") and not theme:
            theme = s.split(":", 1)[1].strip()
        elif u.startswith("SCOPE:") and not scope:
            scope = s.split(":", 1)[1].strip()
    if theme or scope:
        return (f"{theme} - {scope}".strip(" -"))[:160]
    for line in body.splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            return s[:160]
    return "(empty)"

def parse_claimed_count(text):
    """The executor's claimed pass count, or None when it did not claim one.

    `DoneRecord.tests_pass` is free text and defaults to "?". Coercing that to 0
    would INVENT a claim the executor never made and then quarantine the cycle
    for failing it, which is worse than not checking.
    """
    if not isinstance(text, str):
        return None
    m = re.search(r"\d+", text)
    return int(m.group(0)) if m else None


def build_truth_gate_claims(run_id, cycle, done, manifest):
    """PURE: the claims doc tools/truth_gate.py reconciles against ground truth.

    Every manifest slice contributes a FILE-EXISTENCE claim. The suite-count
    claim goes on ONE synthetic `cycle-<n>` slice instead of being copied onto
    each real slice: `tests_pass` is a run-level number, and hanging it on every
    slice would quarantine all of them over one wrong count and hide which claim
    actually failed.

    `must_contain` stays empty deliberately. We do not have the per-slice diff
    here, and asserting content we cannot source is how a gate starts REFUSING
    on its own invention.
    """
    slices = []
    for sl in ((manifest or {}).get("slices") or []):
        slices.append({
            "id": sl.get("id", "?"),
            "claim": sl.get("title", ""),
            "files": [{"path": p, "must_contain": []} for p in (sl.get("files") or [])],
        })
    claimed = parse_claimed_count((done or {}).get("tests_pass"))
    if claimed is not None:
        slices.append({"id": f"cycle-{cycle}",
                       "claim": f"cycle {cycle} reported {claimed} passing",
                       "files": [], "claimed_passed": claimed})
    return {"run_id": run_id, "check_ci": True, "slices": slices}


def run_truth_gate(claims, *, claims_path, report_path, runner=None,
                   skip_suite=False):
    """Invoke tools/truth_gate.py and return (verdict, report).

    Exit 2 is a REAL REFUSE, not a broken tool - a wrapper that read nonzero as
    failure would silently downgrade a refusal into a shrug, so the VERDICT is
    read from the report the gate wrote, never inferred from the exit code.

    Fail-CLOSED on the verdict, fail-OPEN on the loop: if the report cannot be
    read the answer is ERROR, which is never permission to proceed - but it is
    also not an exception, because a reconciliation tool must not be able to
    wedge the run it is only observing.
    """
    run = runner if runner is not None else subprocess.run
    claims_path, report_path = Path(claims_path), Path(report_path)
    claims_path.parent.mkdir(parents=True, exist_ok=True)
    claims_path.write_text(json.dumps(claims, indent=2), encoding="utf-8")
    argv = [sys.executable, str(ROOT / "tools" / "truth_gate.py"),
            "--claims", str(claims_path), "--report", str(report_path)]
    if skip_suite:
        argv.append("--skip-suite")
    try:
        run(argv, capture_output=True, text=True, creationflags=NO_WINDOW)
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - an observer may never wedge the run
        log(f"truth_gate: could not complete ({type(exc).__name__}: {exc})")
        return "ERROR", {"verdict": "ERROR", "error": str(exc)}
    return report.get("verdict", "ERROR"), report


def run_agent_mirror(runner=None):
    """Snapshot the agent fleet into ops/runtime/ before Claude Code reaps it.

    Called once per cycle because the reaping window is exactly the window in
    which nobody is watching - a mirror that only ran when the dashboard was
    open would miss the runs it exists to preserve.

    Fail-OPEN and silent on success: this is bookkeeping about the run, and
    bookkeeping that can wedge the run is worse than no bookkeeping.
    """
    run = runner if runner is not None else subprocess.run
    try:
        run([sys.executable, str(ROOT / "tools" / "lw_agent_mirror.py"), "--quiet"],
            capture_output=True, text=True, creationflags=NO_WINDOW, timeout=60)
    except Exception as exc:  # noqa: BLE001 - an observer may never wedge the run
        log(f"agent_mirror: could not complete ({type(exc).__name__}: {exc})")
        return False
    return True


def read_manifest_run_id(path=None):
    """The slice manifest's OWN run id, or None. Never raises.

    This is the join key for spec item 5. The manifest names a run
    `2026-08-01-01` and the controller names the same run `7dd1dc02`; nothing on
    disk paired them, so the dashboard header showed two ids and could not say
    they were one run. Recording the manifest id on each cycle record makes the
    pairing OBSERVED rather than inferred from adjacency.

    Read at record time rather than threaded down from the cycle: the manifest
    can be re-inited mid-run, and what belongs on the record is what the ladder
    said at the moment the cycle resolved.
    """
    p = Path(path) if path is not None else ROOT / "ops" / "runtime" / "slice_manifest.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    rid = data.get("run_id") if isinstance(data, dict) else None
    return rid.strip() or None if isinstance(rid, str) else None


def record_directive_outcome(cycle, body, sha_before, sha_after, done, verdict,
                             ctl=None, done_record=None, run_id=None,
                             manifest_run_id=None):
    """Append one resolved-cycle record to control/directive_history.jsonl.

    The controller is the single writer; the file is gitignored runtime state and
    is NEVER cleared (newest-first read via read_directive_history), so the
    directive chain persists across the frequent mid-run controller restarts.

    `done` is `DoneRecord.raw` - the claude.done payload - and cost_usd and
    session_id are NOT in it: they are fields on the DoneRecord itself, which is
    why they used to be dropped here and survive only as prose in controller.log.
    `done_record` is that DoneRecord, taken separately so the raw payload keeps
    being carried through untouched (the director prompt is built from it).

    `run_id` is the controller's own run id. Without it cycle numbers COLLIDE
    across runs and a reader can only guess at run boundaries from a cycle number
    that fails to advance - which cannot distinguish a new run from a restart
    that resumed lower. Both stay optional: nothing here may crash the loop, and
    a missing value must degrade to the old behaviour rather than raise."""
    base = Path(ctl) if ctl is not None else CTL
    d = done or {}
    rec = {"cycle": cycle, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "run_id": run_id,
           "manifest_run_id": manifest_run_id,
           "title": directive_title(body),
           "sha_before": (sha_before or "")[:8], "sha_after": (sha_after or "")[:8],
           "tests": d.get("tests_pass"), "regress": bool(d.get("regressions")),
           "cost_usd": float(getattr(done_record, "cost_usd", 0.0) or 0.0),
           "session_id": getattr(done_record, "session_id", None),
           "verdict": ((verdict or "").strip().splitlines() or [""])[0]}
    try:
        with open(base / "directive_history.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError as e:
        log(f"directive_history append failed: {e}")
    return rec

def read_directive_history(n, ctl=None):
    base = Path(ctl) if ctl is not None else CTL
    p = base / "directive_history.jsonl"
    if not p.exists():
        return []
    recs = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            recs.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return recs[-n:]

def _format_directive_chain(recs):
    if not recs:
        return "(none issued yet this run)"
    out = []
    for r in reversed(recs):  # newest first
        out.append(f"- cycle {r.get('cycle')}: {r.get('title', '')} "
                   f"-> {r.get('sha_after', '')} [{r.get('verdict', '')}]")
    return "\n".join(out)

# ---- gemini (read-only, STDIN pipe; mirrors tools/gemini_audit.ps1) ----
def _read_err(errfile):
    # PS 5.1 `2>'file'` writes the error stream UTF-16 LE (Out-File default);
    # the old utf-8 read mojibake'd it, which masked the real API error behind
    # NUL-interleaved node warnings for a whole half-day outage in the RC
    # ancestor (2026-07-02 01:56-11:17).
    try:
        raw = errfile.read_bytes()
    except OSError:
        return ""
    enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
    return raw.decode(enc, errors="replace").strip()

def _err_summary(txt, cap=400):
    # Surface the ERROR lines (503 overload / 429 quota) - the node/terminal
    # warnings that open the stream otherwise crowd them out of a head read.
    hits = [ln.strip() for ln in txt.splitlines()
            if any(k in ln.lower() for k in ("error", "unavailable", "exhausted", "quota", "429", "503"))]
    return (" | ".join(hits) if hits else txt)[:cap]

def gemini(prompt_body, instruction):
    """Serialized machine-wide: Gemini is ONE metered account. Two concurrent
    director calls burn quota in parallel and can trip RESOURCE_EXHAUSTED, which
    the failover logic would misread as real credit exhaustion and stickily swap
    the backend for the rest of the run. Director calls are seconds, so the
    serialization costs nothing."""
    with winmutex.hold(winmutex.GEMINI_MUTEX, log=log):
        return _gemini_call(prompt_body, instruction)


def _gemini_call(prompt_body, instruction):
    global GEMINI_USD
    prompt_body = cap_stdin(prompt_body)
    infile = CTL / "_gemini_in.txt"
    errfile = CTL / "_gemini_err.txt"
    awrite(infile, prompt_body)
    model = CFG.get("gemini_model", "gemini-3-pro-preview")
    # 2026-07-02 outage fix (RC ancestor): gemini-3-pro-preview 503-overloads
    # for hours at a time (big prompts rejected, small ones admitted); 3 empty
    # tries then advancing burned 92 directive-less cycles. After the primary
    # tries exhaust, retry on the cheaper fallback model - a flash directive
    # beats an empty cycle.
    fallback = CFG.get("gemini_fallback_model", "gemini-2.5-flash")
    attempts = [model] * 3 + ([fallback] * 2 if fallback and fallback != model else [])
    inst = instruction.replace("'", "''")
    out = ""
    for tryn, m in enumerate(attempts, start=1):
        ps = ("$ErrorActionPreference='Continue';"
              "$env:GEMINI_API_KEY=[Environment]::GetEnvironmentVariable('GEMINI_API_KEY','User');"
              f"Get-Content -Raw '{infile}' | "
              f"{CFG.get('gemini_cmd', 'gemini')} -p '{inst}' -m '{m}' --approval-mode plan --skip-trust 2>'{errfile}' | Out-String")
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                               capture_output=True, text=True, timeout=300,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            out = (r.stdout or "").strip()
        except Exception as e:  # noqa: BLE001
            out = ""
            log(f"gemini try {tryn} ({m}) error: {e}")
        if out:
            break
        # Empty stdout: surface WHY (decoded + error-line filtered stderr).
        err = _err_summary(_read_err(errfile))
        if err:
            log(f"gemini try {tryn} ({m}) empty stdout; stderr: {err}")
        time.sleep(8 * tryn)
    gp = CFG.get("gemini_price_per_mtok", {"input": 2.0, "output": 12.0})
    GEMINI_USD += (len(prompt_body) / 4 * gp["input"] + len(out) / 4 * gp["output"]) / 1_000_000
    # N3 (revised 2026-07-01): EMPTY output is NEVER a usable answer - the director
    # prompt mandates a directive or the literal NO_WORK token, the auditor a VERDICT
    # line - so a completed-but-empty call is a swallowed CLI/API error, exactly like
    # a timeout. Return the None sentinel for BOTH, so the director path advances the
    # cycle instead of mis-reading "" as NO_WORK and falsely terminating a run with
    # OPEN queue rows (the RC ancestor's 2026-07-01 17:57 false-stop; the same-sha
    # no-progress guard still ends a persistent outage cleanly).
    if not out:
        return None
    return out

# ---- gemini roles ------------------------------------------------------
def build_director_context(last_done, last_audit, *, root=None, ctl=None):
    """Pure: assemble the context appended after the director prompt template.

    Carries an explicit ALREADY-COMPLETED DIGEST (recent commits newest-first +
    the NEWEST docs/LEDGER.md items via head_lines, NOT the stale tail + the
    directive chain already issued this run) plus a BUILD-ON / de-dup rule, so
    the director cannot re-issue just-shipped work. root/ctl are injectable for
    tests; production calls use the module ROOT/CTL."""
    base = Path(root) if root is not None else ROOT
    plan = base / "docs/ORCHESTRATION_PLAN.md"
    plan_txt = plan.read_text(encoding="utf-8", errors="replace") if plan.exists() else "(no plan file)"
    plan_txt = cap_bytes(plan_txt, PLAN_CTX_CAP, "ORCHESTRATION_PLAN")
    chain = _format_directive_chain(read_directive_history(12, ctl=ctl))
    ctx = (
        f"\n\n=== ORCHESTRATION PLAN (PRIMARY work source; pick next OPEN session, skip EXCLUDED) ===\n{plan_txt}"
        "\n\n=== ALREADY-COMPLETED DIGEST - every item below is DONE. BUILD ON it; NEVER re-issue it ==="
        f"\n\n--- RECENT COMMITS (newest first) ---\n{git('log', '--oneline', '-n', '25')}"
        "\n\n--- docs/LEDGER.md NEWEST items (newest-first; each line is a COMPLETED item) ---\n"
        f"{cap_bytes(head_lines('docs/LEDGER.md', 60, root=root), LEDGER_CTX_CAP, 'LEDGER head')}"
        "\n\n--- DIRECTIVES ALREADY ISSUED THIS RUN (do NOT re-issue any unit below) ---\n"
        f"{chain}"
        "\n\nDE-DUP RULE: before emitting the directive, cross-check your chosen unit against the "
        "ALREADY-COMPLETED DIGEST above (recent commits + newest LEDGER items + issued directives). "
        "If it duplicates a DONE ledger item, a recent commit, or a directive already issued, DISCARD "
        "it and synthesize the next NON-duplicate unit. BUILD ON completed work; never re-narrate or "
        "re-do it."
        f"\n\n=== ROADMAP.md (open items - high priority at TOP; head read) ===\n"
        f"{cap_bytes(head_lines('ROADMAP.md', 120, root=root), ROADMAP_CTX_CAP, 'ROADMAP head')}"
        f"\n\n=== LAST claude.done ===\n{json.dumps(last_done)}"
        f"\n\n=== LAST AUDIT (if REGRESS, the directive MUST fix it first) ===\n{last_audit or '(none)'}")
    ask = (Path(ctl) if ctl is not None else CTL) / "gemini_ask.txt"
    if ask.exists():
        try:
            q = ask.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:  # noqa: BLE001
            q = ""
        if q:
            ctx += ("\n\n=== EXECUTOR ESCALATION (resolve FIRST; the directive MUST encode this "
                    "decision + instruct the scaffolding + any ROADMAP/BACKLOG reshape) ===\n" + q)
        ask.unlink(missing_ok=True)
    # Its OWN section header, not a bare blank line after the audit body.
    # Unlabelled prose adjacent to a live section gets attributed to that
    # section: RC caught its director quoting a months-old static suffix back
    # as the current work order in its own PREMISE-CHECK (RC 2026-07-27). The
    # header says both what this is and that live sections outrank it.
    suffix = CFG.get("directive_suffix", "")
    if suffix:
        ctx += ("\n\n=== OPERATOR STANDING ORDERS (STATIC config text, not a live "
                "signal - every === section above reflects the CURRENT tree and "
                "outranks anything here that disagrees) ===\n" + suffix)
    return ctx

def director(last_done, last_audit):
    tmpl = (ROOT / "ops/loop/director_prompt.md").read_text(encoding="utf-8")
    # The FINAL STEP is channel-specific and the two channels want OPPOSITE
    # instructions, so it is injected from the live config rather than hardcoded
    # in the template (which used to name done_sentinel.py unconditionally and
    # contradict the sdk executor's own appended instruction).
    tmpl = tmpl.replace("{{FINAL_STEP}}",
                        executor.final_step_instruction(CFG.get("channel")))
    ctx = build_director_context(last_done, last_audit)
    return gemini(tmpl + ctx, "Output ONLY the directive markdown for the next cycle. No preamble.")

def auditor(prev_sha, new_sha, clean_sha=None):
    if not new_sha or prev_sha == new_sha:
        return "VERDICT: CLEAN\n(no new commit this cycle)"
    rng = audit_range(clean_sha, new_sha)
    diff = git("diff", rng)
    if len(diff) > 55000:
        diff = diff[:55000] + "\n...[truncated]"
    tmpl = (ROOT / "ops/loop/auditor_prompt.md").read_text(encoding="utf-8")
    body = f"{tmpl}\n\n=== RANGE {rng} ===\n{git('log','--oneline',rng)}\n\n=== DIFF ===\n{diff}"
    verdict = gemini(body, "Audit. First line MUST be 'VERDICT: CLEAN' or 'VERDICT: REGRESS', then the reason.")
    if verdict is None:
        # N3: gemini errored (timeout / CLI) - an un-auditable cycle is NOT a regression.
        # Return a safe CLEAN so the controller's string ops never hit the None sentinel
        # and a flaky auditor never falsely blocks a clean cycle.
        return "VERDICT: CLEAN\n(auditor gemini error - could not audit this cycle; treated as non-regress)"
    return verdict

# ---- budget meter: sum active-session JSONL usage since start_ts -------
def _price(model, usage):
    t = CFG["price_per_mtok"]
    key = next((k for k in ("opus", "sonnet", "haiku") if k in (model or "").lower()), "default")
    p = t[key]
    return (usage.get("input_tokens", 0) * p["input"]
            + usage.get("output_tokens", 0) * p["output"]
            + usage.get("cache_creation_input_tokens", 0) * p["cache_write"]
            + usage.get("cache_read_input_tokens", 0) * p["cache_read"]) / 1_000_000

def _iso(ts):
    try:
        return time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:  # noqa: BLE001
        return 0.0

def session_files():
    d = Path(CFG["transcript_dir"])
    pin = CFG.get("session_jsonl")
    if pin:
        p = Path(pin)
        return [p, *list((d / p.stem / "subagents").glob("*.jsonl"))]
    tops = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not tops:
        return []
    active = tops[0]
    return [active, *list((d / active.stem / "subagents").glob("*.jsonl"))]

def meter(start_ts):
    spent = 0.0
    for f in session_files():
        try:
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    o = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                msg = o.get("message", {})
                usage = msg.get("usage")
                if not usage:
                    continue
                ts = _iso(o.get("timestamp", ""))
                if ts and ts < start_ts:
                    continue
                spent += _price(msg.get("model", ""), usage)
        except Exception:  # noqa: BLE001
            continue
    return round(spent, 4)

# ---- main loop ---------------------------------------------------------
def wait_for(path, deadline_ts):
    while time.time() < deadline_ts:
        if (CTL / "STOP").exists():
            log("external STOP seen"); sys.exit(0)
        if Path(path).exists():
            return True
        time.sleep(CFG["poll_sec"])
    return False

def wait_gone(path, deadline_ts):
    while time.time() < deadline_ts:
        if (CTL / "STOP").exists():
            log("external STOP seen"); sys.exit(0)
        if not Path(path).exists():
            return True
        time.sleep(CFG["poll_sec"])
    return False

def stall_action(breach_n):
    """WP-I3 pure decision: how to answer the Nth consecutive cycle-deadline breach.
    The FIRST breach earns a one-shot recovery (inject /diagnose + extend the deadline
    once); a SECOND breach is a genuine hang -> hard STOP. Pure + unit-testable headless
    (no CFG / IO). main() wires this to the actual recover/stop side effects."""
    return "recover" if breach_n <= 1 else "stop"

def stall_recovery_directive(cycle):
    """WP-I3: the one-shot recovery typed into the EXISTING (stalled) executor on the
    FIRST cycle-deadline breach, before any hard STOP. NO /clear - the wedged session's
    context is exactly what /diagnose must inspect. The instruction self-terminates by
    running the done_sentinel final step, so the controller gets its claude.done either
    way (recovered or blocked). Line 1 is the CYCLE header the AHK bridge skips. Pure +
    unit-testable; the main() wiring extends the deadline once around it."""
    # sys.executable, not a hardcoded interpreter path: the recovery directive
    # must name the SAME python that is running this controller. A pinned path
    # is wrong the moment the interpreter moves or a venv is in play, and it
    # would send the stall-recovery step - the one that runs when things are
    # already broken - at an interpreter that may not exist.
    py = sys.executable
    return (
        f"CYCLE={cycle}\n"
        "/diagnose the loop stall: run git status, read the newest pytest result file, read "
        "ops/runtime/health.json, and read the tail of ops/loop/control/controller.log; then "
        "either recover THIS cycle (finish the work package, commit + push + /done) OR write a "
        "one-line blocker to ops/loop/control/blocker.txt. Either way FINISH by running: "
        f"\"{py}\" ops/loop/done_sentinel.py --tests <pass_count> --regressions <0|1>"
    )

def claim_single_controller():
    """One controller per repo. A second one would interleave two runs through
    the SAME control_dir - the handshake files are not namespaced, so both would
    consume each other's gemini.ready and claude.done. Concurrency ACROSS repos
    is the goal; concurrency within one repo is corruption.

    Returns the run_id. Exits nonzero if another live controller holds the repo.
    """
    lock = CTL / "RUNNING.lock"
    if lock.exists():
        rec = rjson(lock, {})
        holder = int(rec.get("pid", 0) or 0)
        # A live pid does not prove the ORIGINAL holder lives: Windows reissues
        # pids, and on 2026-08-01 this lock named a pid from a run that ended
        # five days earlier which the OS had since handed to an unrelated
        # conhost. Bare liveness wedged the repo. A holder owns it for at most a
        # cycle, so a lock older than the stale window cannot be a live run.
        age = time.time() - float(rec.get("ts", 0) or 0)
        fresh = age < slots.DEFAULT_STALE_AFTER
        alive = bool(holder) and holder != os.getpid() and slots.pid_alive(holder)
        if alive and fresh:
            sys.stderr.write(
                f"another controller is already running in this repo "
                f"(pid={holder} run_id={rec.get('run_id')} since {rec.get('ts')}). "
                f"Stop it first, or delete {lock} if it is a stale leftover.\n")
            sys.exit(2)
        why = "not alive" if not alive else f"expired ({age:.0f}s old)"
        log(f"reclaiming stale RUNNING.lock (pid={holder} {why})")
    run_id = uuid.uuid4().hex[:8]
    awrite(lock, json.dumps({"pid": os.getpid(), "run_id": run_id,
                             "ts": time.time(), "repo": str(ROOT)}))
    awrite(CTL / "run_id.txt", run_id)
    return run_id


def main():
    global RUN_ID
    for f in ("STOP", "gemini.ready", "typed.flag", "claude.done", "cycle.txt"):
        (CTL / f).unlink(missing_ok=True)
    RUN_ID = claim_single_controller()
    log(f"run_id={RUN_ID}")
    start_ts = time.time()
    # persistent-session model: pin the session active at launch (the executor being
    # driven via /clear) so the meter bills it for the whole run, not whatever is newest.
    if not CFG.get("session_jsonl"):
        d = Path(CFG["transcript_dir"])
        tops = sorted(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if tops:
            CFG["session_jsonl"] = str(tops[0])
            log(f"pinned executor session jsonl: {tops[0].name}")
    prev_sha = head()
    last_clean_sha = prev_sha  # R61: auditor diff base = last known-good sha (loop start is clean)
    last_done, last_audit = {}, ""
    same_sha_streak = 0
    log(f"loop start dry_run={DRY} ceiling={CFG['ceiling_usd']} head={prev_sha[:8]}")
    # core.hooksPath is LOCAL config and is not cloned, so a fresh clone runs with
    # NO commit gate while the tracked .githooks sits there looking installed. An
    # unattended run in that state pushes ungated and no one reads a session
    # report, so refuse to start instead.
    gate_gap = executor.gate_inactive_reason(ROOT)
    if gate_gap:
        stop(f"commit gate not active - refusing to run ungated: {gate_gap} "
             f"(fix: python tools/install_git_hooks.py)")
    EXEC = executor.build(
        CFG, CTL, log=log, stop=stop, awrite=awrite, wait_for=wait_for,
        wait_gone=wait_gone, rjson=rjson, stall_action=stall_action,
        stall_recovery_directive=stall_recovery_directive)

    FIXED = CFG.get("fixed_directive")  # fixed-message mode: skip gemini director+auditor entirely
    CYCLE_CMD = CFG.get("cycle_command")  # self-directing slash command typed verbatim; director SKIPPED, auditor KEPT
    for cycle in range(1, CFG["max_cycles"] + 1):
        # STOP is otherwise only polled inside wait_for/wait_gone, which never
        # run while the director is erroring - a 2026-07-03 outage in the RC
        # ancestor spun 20+ directive-less cycles where an operator STOP would
        # have been ignored.
        if (CTL / "STOP").exists():
            log("external STOP seen (cycle top)")
            sys.exit(0)
        override = consume_directive_override()
        src = cycle_source(CFG, override)
        if src == "override":
            body = override
            log(f"cycle {cycle}: operator directive override applied ({len(body)} chars)")
        elif src == "cycle_command":
            body = CYCLE_CMD
        elif src == "fixed":
            body = FIXED
        else:
            body = director(last_done, last_audit)
            if body is None:
                # N3: gemini retries exhausted (timeout / CLI error) - NOT a real NO_WORK
                # signal. Advance to the next cycle instead of terminating the whole run;
                # the no-progress (same-sha) guard still stops a persistent outage cleanly.
                log(f"cycle {cycle}: director gemini error (retries exhausted) - advancing, NOT terminating")
                continue
            if body[:40].upper().find("NO_WORK") >= 0:
                stop("director returned NO_WORK")
        awrite(CTL / "directive.md", body)
        awrite(CTL / "cycle.txt", str(cycle))
        # The channel-specific half of a cycle (typing handshake + done sentinel for
        # AHK; one `claude -p` call for sdk in P2) lives behind the executor seam.
        # Artifacts both channels share stay here: directive.md, cycle.txt,
        # budget.json and the metering below.
        # Slot held ONLY around the executor call - never around git or the
        # adjudicator, so a long merge in this repo cannot starve the other one.
        with slots.hold(int(CFG.get("max_concurrent_lanes", 3)),
                        repo=str(ROOT), run_id=RUN_ID, cycle=cycle, log=log):
            rec = EXEC.run(cycle, body, src)
        done = rec.raw
        last_done = done
        new_sha = rec.sha or head()

        # Independent reconciliation of what the executor CLAIMED against ground
        # truth. Until now truth_gate.py existed, was tested, and was invoked by
        # nothing - its report had never been written on this machine, so the
        # loop's most documented failure class (an unbacked green claim) was
        # answered only by whatever the cycle said about itself.
        # ADVISORY by default: the verdict is logged, reported and carried into
        # the audit, but `truth_gate_blocking` (default False) decides whether a
        # REFUSE actually stops the cycle. Landing a new control-flow branch as
        # blocking, on a loop that is not currently running, would be shipping
        # an unmeasured change to the one thing that must not wedge.
        tg_verdict = None
        if CFG.get("truth_gate", True):
            manifest = rjson(ROOT / "ops" / "runtime" / "slice_manifest.json", None)
            tg_verdict, tg_report = run_truth_gate(
                build_truth_gate_claims(RUN_ID, cycle, done, manifest),
                claims_path=CTL / "truth_gate_claims.json",
                report_path=ROOT / "ops" / "runtime" / "truth_gate_report.json",
                skip_suite=bool(CFG.get("truth_gate_skip_suite", False)))
            log(f"cycle {cycle}: truth_gate -> {tg_verdict} "
                f"quarantined={tg_report.get('quarantined') or []}")
            if tg_verdict == "REFUSE" and CFG.get("truth_gate_blocking", False):
                log(f"cycle {cycle}: truth_gate REFUSE is blocking - "
                    f"{tg_report.get('action', 'commit blocked')}")
        log(f"cycle {cycle}: claude.done sha={new_sha[:8]} tests={done.get('tests_pass')} regress={done.get('regressions')}")

        # NO Claude dollar accounting (operator 2026-07-26). Two reasons, both
        # measured today rather than assumed:
        #   1. On a Claude Code Max subscription the figures are NOTIONAL
        #      API-equivalent pricing, not what the plan is billed. Recording
        #      them as a budget invites capping on a number unrelated to spend.
        #   2. meter() was wrong anyway. It auto-pins the newest transcript in
        #      the project dir, which is normally the operator's INTERACTIVE
        #      session, so it billed this loop $329 for a conversation it never
        #      ran. Reproduced independently in RC ($43.69, flat across cycles).
        # gemini accounting STAYS: that vendor is genuinely metered per token,
        # so its ceiling is a real rail rather than an accounting artifact.
        # meter() itself is left defined - it is on the phase-6 held-deletion
        # list and the ahk path still has no other cost signal.
        awrite(CTL / "budget.json", json.dumps(
            {"gemini_usd": round(GEMINI_USD, 4), "gemini_ceiling": CFG["ceiling_usd"],
             "cycle": cycle}))
        log(f"cycle {cycle}: gemini=${round(GEMINI_USD, 4)}/{CFG['ceiling_usd']}")
        if GEMINI_USD >= CFG["ceiling_usd"]:
            stop(f"gemini budget ceiling hit: ${round(GEMINI_USD, 4)} >= ${CFG['ceiling_usd']}")

        if not CFG.get("ignore_no_progress"):
            same_sha_streak = same_sha_streak + 1 if new_sha == prev_sha else 0
            if same_sha_streak >= 2:
                stop("no progress: same sha 2 cycles")

        verdict = "VERDICT: CLEAN\n(fixed-directive mode: gemini auditor disabled)" if src == "fixed" else auditor(prev_sha, new_sha, last_clean_sha)
        if done.get("regressions"):
            verdict = ("VERDICT: REGRESS\nClaude self-reported it could NOT reach green this "
                       "cycle (regressions flag). Fix this before any new work.\n\n" + verdict)
        last_audit = verdict
        regress = verdict.strip().upper().startswith("VERDICT: REGRESS")
        # R61: advance the clean anchor only on a CLEAN verdict; a REGRESS keeps
        # the window open back to the last known-good sha so the eventual fix is
        # audited WITH the commits it repairs (never a lone docs-sync commit).
        if not regress:
            last_clean_sha = new_sha
        log(f"cycle {cycle}: audit -> {'REGRESS' if regress else 'CLEAN'}")
        # Persist the resolved directive to the chain so the NEXT director cycle
        # sees what was already issued + shipped and builds on it (continuity fix).
        record_directive_outcome(cycle, body, prev_sha, new_sha, done, verdict,
                                 done_record=rec, run_id=RUN_ID,
                                 manifest_run_id=read_manifest_run_id())
        run_agent_mirror()
        prev_sha = new_sha

    stop(f"max_cycles {CFG['max_cycles']} reached")

if __name__ == "__main__":
    main()
