"""Truth-gate: pre-commit reconciliation of worker claims against ground truth.

Protocol (insights 2026-06-10 fold-in; companion to .claude/agents/verifier.md):
  1. Re-run the real test suite fresh, capture actual exit code + counts.
  2. Re-read every file a worker claimed to edit; confirm claimed content present.
  3. Probe CI status for HEAD from the authoritative source (gh CLI).
  4. REFUSE (exit 2) if any claim cannot be independently reproduced;
     quarantined slices are listed for re-dispatch.

Reconciliation report written atomically to ops/runtime/truth_gate_report.json.

Claims JSON shape:
  {"run_id": "...",
   "suite_cmd": "C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe -m pytest tests/ -q",     # optional; default = what CI runs
   "check_ci": true,                           # optional; default true
   "slices": [{"id": "S1", "claim": "...",
               "files": [{"path": "rel/or/abs.py", "must_contain": ["snippet"]}],
               "claimed_passed": 42, "claimed_failed": 0}]}   # counts optional

Usage:
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/truth_gate.py --claims claims.json [--skip-suite] [--report PATH]
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = ROOT / "ops" / "runtime" / "truth_gate_report.json"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

# Only these triggers honour paths-ignore. A schedule run fires whatever the
# commit touched, so its existence says nothing about the commit's own files.
_PATH_FILTERED_EVENTS = ("push", "pull_request")

# CREATE_NO_WINDOW: 0 on non-Windows so the module still imports/tests in CI.
# Under a pythonw.exe parent a console child allocates its OWN window. Applies
# to the shell=True suite run too - there it suppresses the cmd.exe console.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# The bare "py" launcher can resolve to a pytest-less interpreter (e.g. the
# python-manager pythoncore-3.14-64 install), which zeroes the suite and turns
# every gate into a blanket REFUSE. Pin the canonical project interpreter;
# fall back to whichever interpreter is running this script.
_CANONICAL_PY = Path(r"C:\Users\Administrator\AppData\Local\Programs\Python"
                     r"\Python314\python.exe")
SUITE_PY = str(_CANONICAL_PY if _CANONICAL_PY.exists() else Path(sys.executable))
# `tests/` is NOT optional. A bare `-m pytest -q` collects from the repo root and
# sweeps in files the project suite never runs - tools/test_lw_clean_dekel.py
# (imports skimage, which lives only in the lw-clean venv) and a vendored MCP
# extension's conftest under Claude/. Collection then dies, counts come back
# zeroed, and every count claim quarantines: the gate manufactures a REFUSE on a
# green tree. Measured 2026-08-01, the first time anything actually invoked this.
# This must stay identical to what .github/workflows/ci.yml runs.
DEFAULT_SUITE_CMD = f'"{SUITE_PY}" -m pytest tests/ -q'

_SUMMARY_TOKEN = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped|"
                            r"xfailed|xpassed|deselected|warnings?)")


def parse_pytest_summary(text):
    """Parse the final pytest summary line into counts. Last matching line wins."""
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0,
              "no_tests_ran": False}
    summary_line = None
    for line in text.splitlines():
        if _SUMMARY_TOKEN.search(line) and (" in " in line or "=" in line):
            summary_line = line
        if "no tests ran" in line:
            counts["no_tests_ran"] = True
    if summary_line:
        for num, label in _SUMMARY_TOKEN.findall(summary_line):
            if label.startswith("error"):
                counts["errors"] += int(num)
            elif label in ("passed", "failed", "skipped"):
                counts[label] = int(num)
    return counts


def run_suite_fresh(cmd, out_path):
    """Run the suite, tee output to a file, read the FILE back (stale-pipe guard)."""
    out_path = Path(out_path)
    with open(out_path, "w", encoding="utf-8", errors="replace") as fh:
        proc = subprocess.run(cmd, shell=True, cwd=str(ROOT),
                              stdout=fh, stderr=subprocess.STDOUT,
                              creationflags=NO_WINDOW)
    text = out_path.read_text(encoding="utf-8", errors="replace")
    obs = parse_pytest_summary(text)
    obs["exit_code"] = proc.returncode
    obs["cmd"] = cmd
    obs["output_file"] = str(out_path)
    return obs


def check_file_claims(file_claims):
    """Re-read each claimed file; confirm existence + every must_contain snippet."""
    out = []
    for fc in file_claims:
        p = Path(fc["path"])
        if not p.is_absolute():
            p = ROOT / p
        rec = {"path": fc["path"], "exists": p.is_file(), "missing_snippets": []}
        if rec["exists"]:
            body = p.read_text(encoding="utf-8", errors="replace")
            rec["missing_snippets"] = [s for s in fc.get("must_contain", [])
                                       if s not in body]
        out.append(rec)
    return out


def check_git():
    def _git(*args):
        r = subprocess.run(["git", *args], cwd=str(ROOT),
                           capture_output=True, text=True,
                           creationflags=NO_WINDOW)
        return r.stdout.strip()
    status = _git("status", "-s")
    head = _git("log", "--oneline", "-1")
    return {"clean": status == "", "dirty_files": status.splitlines(),
            "head": head}


def parse_paths_ignore(text):
    """Map every `on:` trigger to its paths-ignore globs ([] when it has none).

    Stdlib parse rather than PyYAML: requirements.txt is the CI install list,
    and a gate whose job is to read six lines of its own workflow must not be
    able to fail on a third-party import.
    """
    events = {}
    on_indent = None
    trigger_indent = None
    event = None
    collecting = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        key = stripped.split(":", 1)[0].strip().strip("\"'")
        if on_indent is None:
            if indent == 0 and key == "on":
                on_indent = indent
            continue
        if indent <= on_indent:
            break
        if trigger_indent is None:
            trigger_indent = indent
        if indent == trigger_indent and not stripped.startswith("-"):
            event = key
            events.setdefault(event, [])
            collecting = False
        elif event is None:
            continue
        elif stripped.startswith("-"):
            if collecting:
                events[event].append(stripped[1:].strip().strip("\"'"))
        else:
            collecting = key == "paths-ignore"
    return events


def _glob_to_regex(pattern):
    """GitHub filter-pattern semantics: `**` spans separators, `*` does not.

    Measured against the live repo 2026-07-27: '**/*.md' suppressed the run for
    a commit whose only files were root-level ROADMAP.md / WAKEUP_NOTES.md, so
    a leading `**/` matches zero segments as well as many.
    """
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def workflow_ignores_commit(changed_files, workflow=WORKFLOW):
    """True only when EVERY path-filtered trigger ignores EVERY changed file.

    Each unknown resolves to False on purpose: "no run will ever exist" is the
    one answer that can turn a run still waiting to start into a green light,
    so it is only ever returned on positive evidence from the workflow itself.
    """
    if not changed_files:
        return False
    try:
        events = parse_paths_ignore(Path(workflow).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    filters = [events[e] for e in _PATH_FILTERED_EVENTS if e in events]
    if not filters or not all(filters):
        return False
    for globs in filters:
        matchers = [_glob_to_regex(g) for g in globs]
        if not all(any(m.match(f) for m in matchers) for f in changed_files):
            return False
    return True


def _changed_files(sha):
    """Files touched by <sha>, or [] when unknowable.

    A merge commit lists none under --name-only, which must not be mistaken for
    a commit that changed nothing CI cares about.
    """
    r = subprocess.run(["git", "show", "--name-only", "--pretty=format:", sha],
                       cwd=str(ROOT), capture_output=True, text=True,
                       creationflags=NO_WINDOW)
    if r.returncode != 0:
        return []
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def check_ci(sha="HEAD", workflow=WORKFLOW):
    """Authoritative CI status via gh. 'unavailable' if gh/runs absent.

    An empty run list is two different facts wearing one face: 'not-evaluated'
    (paths-ignore covers every changed file, so no run was ever coming) and
    'queued' (a run is owed but GitHub has not registered it yet). Reporting
    both as one string let a race with the API read as a settled verdict.
    """
    try:
        if sha == "HEAD":
            r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                               capture_output=True, text=True,
                               creationflags=NO_WINDOW)
            sha = r.stdout.strip()
        r = subprocess.run(
            ["gh", "run", "list", "--commit", sha, "--limit", "10",
             "--json", "status,conclusion,name"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=30,
            creationflags=NO_WINDOW)
        if r.returncode != 0:
            return {"status": "unavailable", "detail": r.stderr.strip()[:200],
                    "sha": sha}
        runs = json.loads(r.stdout or "[]")
        if not runs:
            ignored = workflow_ignores_commit(_changed_files(sha), workflow)
            return {"status": "not-evaluated" if ignored else "queued",
                    "sha": sha, "runs": []}
        if any(x["status"] != "completed" for x in runs):
            return {"status": "pending", "sha": sha, "runs": runs}
        if all(x["conclusion"] == "success" for x in runs):
            return {"status": "success", "sha": sha, "runs": runs}
        return {"status": "failure", "sha": sha, "runs": runs}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return {"status": "unavailable", "detail": str(e)[:200], "sha": sha}


def reconcile(claims, suite_obs, file_obs_by_slice, git_obs, ci_obs):
    """Cross-check every claim against observations. Any irreproducible claim
    quarantines its slice; suite red or CI failure refuses globally."""
    slices_out = []
    quarantined = []
    for sl in claims.get("slices", []):
        disc = []
        for rec in file_obs_by_slice.get(sl["id"], []):
            if not rec["exists"]:
                disc.append("claimed file missing on disk: {}".format(rec["path"]))
            elif rec["missing_snippets"]:
                disc.append("claimed change absent in {}: {}".format(rec["path"], rec["missing_snippets"]))
        cp = sl.get("claimed_passed")
        if cp is not None and suite_obs["passed"] != cp:
            disc.append("claimed_passed={} but observed {}".format(cp, suite_obs["passed"]))
        cf = sl.get("claimed_failed")
        if cf is not None and suite_obs["failed"] != cf:
            disc.append("claimed_failed={} but observed {}".format(cf, suite_obs["failed"]))
        verdict = "CONFIRM" if not disc else "QUARANTINE"
        if verdict == "QUARANTINE":
            quarantined.append(sl["id"])
        slices_out.append({"id": sl["id"], "claim": sl.get("claim", ""),
                           "verdict": verdict, "discrepancies": disc})
    global_disc = []
    if suite_obs["failed"] > 0 or suite_obs["errors"] > 0:
        global_disc.append("suite red: {} failed, {} errors".format(suite_obs["failed"], suite_obs["errors"]))
    if suite_obs.get("exit_code") not in (0, None):
        global_disc.append("suite exit_code={}".format(suite_obs["exit_code"]))
    if suite_obs.get("no_tests_ran"):
        global_disc.append("no tests ran")
    if ci_obs.get("status") == "failure":
        global_disc.append("ci failure at {}".format(ci_obs.get("sha", "?")))
    verdict = "REFUSE" if (quarantined or global_disc) else "PROCEED"
    return {"run_id": claims.get("run_id", ""), "verdict": verdict,
            "suite": suite_obs, "git": git_obs, "ci": ci_obs,
            "slices": slices_out, "quarantined": quarantined,
            "global_discrepancies": global_disc,
            "action": ("commit allowed" if verdict == "PROCEED" else
                       "COMMIT BLOCKED - re-dispatch quarantined slices "
                       "with the discrepancy list as added context")}


def load_claims(path):
    """utf-8-sig tolerates the BOM PowerShell 5.1 Out-File -Encoding utf8 emits."""
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_report_atomic(report, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    tmp.replace(target)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Truth-gate pre-commit reconciler")
    ap.add_argument("--claims", required=True)
    ap.add_argument("--report", default=str(DEFAULT_REPORT))
    ap.add_argument("--skip-suite", action="store_true",
                    help="reuse no suite run; suite counts come back zeroed "
                         "and count-claims will quarantine (debug only)")
    args = ap.parse_args(argv)

    claims = load_claims(args.claims)
    if args.skip_suite:
        suite_obs = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0,
                     "no_tests_ran": False, "exit_code": None,
                     "cmd": "(skipped)"}
    else:
        suite_obs = run_suite_fresh(claims.get("suite_cmd", DEFAULT_SUITE_CMD),
                                    ROOT / "ops" / "runtime" / "truth_gate_suite.txt")
    file_obs = {sl["id"]: check_file_claims(sl.get("files", []))
                for sl in claims.get("slices", [])}
    git_obs = check_git()
    ci_obs = (check_ci() if claims.get("check_ci", True)
              else {"status": "skipped"})

    report = reconcile(claims, suite_obs, file_obs, git_obs, ci_obs)
    write_report_atomic(report, args.report)
    print(json.dumps({k: report[k] for k in
                      ("verdict", "quarantined", "global_discrepancies")}))
    print(f"report: {args.report}")
    return 0 if report["verdict"] == "PROCEED" else 2


if __name__ == "__main__":
    sys.exit(main())
