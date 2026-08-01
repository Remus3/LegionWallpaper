"""Durable slice manifest so a crashed headless run resumes instead of redoing.

A headless run dies for reasons that have nothing to do with the work: an API
400, a dropped socket, a cascade-cancel. Without a checkpoint on disk the
relaunched run has no way to tell a slice that was already merged and pushed
from one that never started, so it redoes committed work - or worse, re-dispatches
a slice on top of its own commit. The manifest at ops/runtime/slice_manifest.json
is that checkpoint: `committed` means durable and skipped, everything else means
redo.

Status ladder (see .claude/commands/headless-upgrade.md):
  pending -> in_progress (dispatched) -> verified (verifier CONFIRMed)
          -> committed (merge + push landed)      failed (quarantined)

The ladder is a POSITION and it forgets. `verdict` is the parallel record of who
checked the work and what they found, and it is a HISTORY on purpose: slice B1 of
run 2026-08-01-01 was REFUTED by its verifier, reworked, then re-verified, and a
single-valued field would have left only the CONFIRM. The refutation that was
later fixed is exactly the thing an operator needs to still be able to see (spec
docs/RUNDASH_SPEC_2026-08-01.md, instrumentation backlog items 1 and 2).

The `verdicts` field is OPTIONAL and its ABSENCE means NOT OBSERVED. Every
manifest written before this subcommand existed therefore stays valid and none of
them silently become "verified" - `add` does not seed the key, only `verdict`
creates it.

Usage:
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/slice_orchestrator.py init --run-id 2026-07-29-01 --head <sha> [--force]
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/slice_orchestrator.py add --id S1 --title "run infra" [--files a.py,b.py]
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/slice_orchestrator.py set --id S1 --status committed [--commit <sha>] [--note text]
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/slice_orchestrator.py verdict --id S1 --state CONFIRM --observer verifier [--agent-id <id>] [--passed N --skipped N --failed N] [--discrepancy line]... [--note text] [--at <iso>] [--backfilled]
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/slice_orchestrator.py resume
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/slice_orchestrator.py status
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = ROOT / "ops" / "runtime" / "slice_manifest.json"

SCHEMA = 1
STATUSES = ("pending", "in_progress", "verified", "committed", "failed")
DONE = "committed"

# The per-slice verdict history. Optional by contract - see the module docstring.
VERDICT_FIELD = "verdicts"

# What a verdict can say. Deliberately NOT the dashboard's display vocabulary
# (VERIFIED / REFUTED / NOT OBSERVED): this is what an observer reported, and the
# third display state is the ABSENCE of any record here.
VERDICT_STATES = ("CONFIRM", "REFUTE")

# Who is allowed to have observed it. A free-text observer would let a slice
# certify itself, which is the failure mode the whole panel exists to expose.
OBSERVERS = ("verifier", "merger", "truth_gate")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_stamp(text):
    """An ISO stamp normalized to explicit UTC, or None when it is not one.

    A NAIVE stamp is REFUSED rather than guessed at. Measured 2026-08-01:
    tools/lw_httpd.parse_ts reads a naive stamp as UTC while
    tools/lw_rundash_state.parse_iso reads the same stamp as LOCAL - a 5 hour
    delta on this machine, because loop_controller writes naive local and reads
    it back local. A stamp carrying its own offset is the one form neither
    reader can misread, so that is the only form this writer emits.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    raw = text.strip()
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_manifest(path):
    """Return the manifest dict, or None when there is no manifest yet.

    utf-8-sig tolerates the BOM PowerShell 5.1 Out-File -Encoding utf8 emits,
    matching truth_gate.load_claims - a manifest hand-edited from a PS prompt
    must still parse.
    """
    path = Path(path)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_manifest_atomic(manifest, path):
    """tmp sibling then replace: a consumer polling mid-write sees old or new,
    never a truncated file (CLAUDE.md atomic-write hard rule)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest["updated"] = _now()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def unfinished(manifest):
    """Slice entries that a relaunch still owes work on."""
    return [s for s in manifest.get("slices", []) if s.get("status") != DONE]


def cmd_init(path, run_id, head, force=False):
    existing = load_manifest(path)
    if existing is not None and not force:
        pending = unfinished(existing)
        if pending:
            ids = ", ".join(s.get("id", "?") for s in pending)
            print(f"REFUSED: {path} already holds {len(pending)} "
                  f"non-committed slice(s): {ids}", file=sys.stderr)
            print("This is a RESUME, not a fresh run - use `resume` to list the "
                  "work owed, or `init --force` to discard the checkpoint.",
                  file=sys.stderr)
            return 2
    write_manifest_atomic({"schema": SCHEMA, "run_id": run_id, "head": head,
                           "created": _now(), "slices": []}, path)
    print(f"init: run_id={run_id} head={head} manifest={path}")
    return 0


def cmd_add(path, slice_id, title, files):
    manifest = load_manifest(path)
    if manifest is None:
        print(f"ERROR: no manifest at {path} - run `init` first",
              file=sys.stderr)
        return 2
    if any(s.get("id") == slice_id for s in manifest.get("slices", [])):
        print(f"ERROR: slice id {slice_id} already in the manifest",
              file=sys.stderr)
        return 2
    parsed = [f.strip() for f in (files or "").split(",") if f.strip()]
    manifest.setdefault("slices", []).append(
        {"id": slice_id, "title": title, "files": parsed, "status": "pending",
         "commit": None, "note": "", "updated": _now()})
    write_manifest_atomic(manifest, path)
    print(f"add: {slice_id} pending ({len(parsed)} file(s))")
    return 0


def cmd_set(path, slice_id, status, commit, note):
    if status not in STATUSES:
        print("ERROR: unknown status {!r} - allowed: {}"
              .format(status, ", ".join(STATUSES)), file=sys.stderr)
        return 2
    manifest = load_manifest(path)
    if manifest is None:
        print(f"ERROR: no manifest at {path} - run `init` first",
              file=sys.stderr)
        return 2
    for entry in manifest.get("slices", []):
        if entry.get("id") == slice_id:
            entry["status"] = status
            if commit is not None:
                entry["commit"] = commit
            if note is not None:
                entry["note"] = note
            entry["updated"] = _now()
            write_manifest_atomic(manifest, path)
            print(f"set: {slice_id} -> {status}")
            return 0
    print(f"ERROR: no slice with id {slice_id} in {path}",
          file=sys.stderr)
    return 2


def build_verdict_record(state, observer, *, agent_id=None, passed=None,
                         skipped=None, failed=None, discrepancies=None,
                         note=None, at=None, backfilled=False):
    """THE owner of the verdict-record shape. Raises ValueError on a bad field.

    Every writer of an observation - the CLI below, tools/truth_gate.py, and
    whatever comes next - builds its record here. A second hand-rolled dict is
    how the reader (lw_rundash_state._normalize_verdict) ends up tolerant of one
    shape and blind to another, and a verdict the board cannot read is worse
    than no verdict at all: it renders as NOT OBSERVED, which is a lie.
    """
    state_up = (state or "").strip().upper()
    if state_up not in VERDICT_STATES:
        raise ValueError("unknown verdict state {!r} - allowed: {}"
                         .format(state, ", ".join(VERDICT_STATES)))
    who = (observer or "").strip()
    if who not in OBSERVERS:
        raise ValueError("unknown observer {!r} - allowed: {}"
                         .format(observer, ", ".join(OBSERVERS)))
    stamp = _now() if at is None else normalize_stamp(at)
    if stamp is None:
        raise ValueError(
            f"--at {at!r} must carry an explicit offset or a trailing Z - a naive"
            " stamp is read as UTC by one consumer and as LOCAL by another"
            )
    counts = None
    if any(v is not None for v in (passed, skipped, failed)):
        counts = {"passed": passed, "skipped": skipped, "failed": failed}
    return {
        "state": state_up,
        "observer": who,
        "at": stamp,
        "agent_id": (agent_id or "").strip() or None,
        "counts": counts,
        "discrepancies": [d.strip() for d in (discrepancies or []) if d and d.strip()],
        "note": (note or "").strip(),
        "backfilled": bool(backfilled),
    }


def append_verdict_record(manifest, slice_id, record):
    """Append `record` to one slice in an already-loaded manifest. True if hit.

    Does NOT write. The caller batches its writes, because one atomic write per
    slice would leave a poller able to observe a half-recorded run.

    `status` and `updated` are LEFT ALONE. The ladder is where the work is; this
    is what somebody found when they looked, and a refutation that silently
    rewound the ladder is what erased the 2026-07-30 REFUTE in the first place.
    The dashboard also subtracts `updated` to show time in the current status,
    so stamping it would report a slice parked for four hours as "just now".
    """
    for entry in manifest.get("slices", []):
        if entry.get("id") != slice_id:
            continue
        history = entry.get(VERDICT_FIELD)
        if not isinstance(history, list):
            history = []
        history.append(record)
        entry[VERDICT_FIELD] = history
        return True
    return False


def cmd_verdict(path, slice_id, state, observer, *, agent_id=None, passed=None,
                skipped=None, failed=None, discrepancies=None, note=None,
                at=None, backfilled=False):
    """Append one observation to a slice's verdict history.

    Deliberately does NOT touch `status`. The ladder is where the work is; this
    is what somebody found when they looked, and a refutation that silently
    rewound the ladder is what erased the 2026-07-30 REFUTE in the first place.
    Move the ladder with `set` when you mean to move it.

    Counts stay None when nothing was observed. A REFUTE that never got a suite
    number must not read as "0 passed" - a confident wrong number here is worse
    than an empty one, because the entire point is that a claim without evidence
    is visible as such.
    """
    try:
        record = build_verdict_record(
            state, observer, agent_id=agent_id, passed=passed, skipped=skipped,
            failed=failed, discrepancies=discrepancies, note=note, at=at,
            backfilled=backfilled)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    manifest = load_manifest(path)
    if manifest is None:
        print(f"ERROR: no manifest at {path} - run `init` first", file=sys.stderr)
        return 2
    if not append_verdict_record(manifest, slice_id, record):
        print(f"ERROR: no slice with id {slice_id} in {path}", file=sys.stderr)
        return 2
    write_manifest_atomic(manifest, path)
    count = len(next(e[VERDICT_FIELD] for e in manifest["slices"]
                     if e.get("id") == slice_id))
    print(f"verdict: {slice_id} {record['state']} by {record['observer']} "
          f"({count} record(s) on this slice)")
    return 0


def latest_verdict(entry):
    """The last record appended to a slice, or None.

    LAST, not newest-by-timestamp: the list is append-only and file order is the
    order things actually happened, while a stamp can be absent or hand-edited.
    """
    history = entry.get(VERDICT_FIELD) if isinstance(entry, dict) else None
    if not isinstance(history, list):
        return None
    records = [r for r in history if isinstance(r, dict)]
    return records[-1] if records else None


def cmd_resume(path):
    """Print only the slices still owed, one per line, tab-separated.

    Always exit 0: the wrapper calls this unconditionally on relaunch, and a
    first-ever run legitimately has no manifest at all.
    """
    manifest = load_manifest(path)
    if manifest is None:
        return 0
    for entry in unfinished(manifest):
        print("{}\t{}\t{}\t{}".format(entry.get("id", "?"),
                                      entry.get("status", "?"),
                                      entry.get("title", ""),
                                      ",".join(entry.get("files", []))))
    return 0


def cmd_status(path):
    manifest = load_manifest(path)
    if manifest is None:
        print(f"no manifest at {path}")
        return 0
    print("run_id={} head={} schema={} updated={}"
          .format(manifest.get("run_id", "?"), manifest.get("head", "?"),
                  manifest.get("schema", "?"), manifest.get("updated", "?")))
    slices = manifest.get("slices", [])
    print("{:<8} {:<12} {:<10} {:<18} {:<30} {}"
          .format("ID", "STATUS", "COMMIT", "EVIDENCE", "TITLE", "FILES"))
    for entry in slices:
        latest = latest_verdict(entry)
        # "-" and not a blank: no record is the NOT OBSERVED state, and a blank
        # column reads as "fine" exactly the way the dashboard chip must not.
        evidence = "-"
        if latest:
            evidence = "{} {}".format(latest.get("state", "?"),
                                      latest.get("observer", "?"))[:18]
        print("{:<8} {:<12} {:<10} {:<18} {:<30} {}"
              .format(entry.get("id", "?"), entry.get("status", "?"),
                      (entry.get("commit") or "-")[:10], evidence,
                      entry.get("title", "")[:30],
                      ",".join(entry.get("files", []))))
    print(f"{len(slices)} slice(s), {len(unfinished(manifest))} not committed")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(description="Durable headless-run slice manifest")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", parents=[common], help="create a fresh manifest")
    p.add_argument("--run-id", required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--force", action="store_true",
                   help="discard an existing checkpoint with owed slices")

    p = sub.add_parser("add", parents=[common], help="append a pending slice")
    p.add_argument("--id", required=True, dest="slice_id")
    p.add_argument("--title", required=True)
    p.add_argument("--files", default="", help="comma-separated paths")

    p = sub.add_parser("set", parents=[common], help="advance a slice's status")
    p.add_argument("--id", required=True, dest="slice_id")
    p.add_argument("--status", required=True)
    p.add_argument("--commit", default=None)
    p.add_argument("--note", default=None)

    p = sub.add_parser("verdict", parents=[common],
                       help="append an observation to a slice's verdict history")
    p.add_argument("--id", required=True, dest="slice_id")
    p.add_argument("--state", required=True,
                   help="CONFIRM or REFUTE - what the observer found")
    p.add_argument("--observer", required=True,
                   help="who observed it: " + ", ".join(OBSERVERS))
    p.add_argument("--agent-id", default=None, dest="agent_id",
                   help="the observing agent id, when there is one")
    p.add_argument("--passed", type=int, default=None, help="suite count OBSERVED")
    p.add_argument("--skipped", type=int, default=None, help="suite count OBSERVED")
    p.add_argument("--failed", type=int, default=None, help="suite count OBSERVED")
    p.add_argument("--discrepancy", action="append", default=None,
                   dest="discrepancies", help="one discrepancy line; repeatable")
    p.add_argument("--note", default=None)
    p.add_argument("--at", default=None,
                   help="observation time; MUST carry a Z or an explicit offset")
    p.add_argument("--backfilled", action="store_true",
                   help="recorded after the fact from evidence, not live")

    sub.add_parser("resume", parents=[common],
                   help="print only the non-committed slices")
    sub.add_parser("status", parents=[common], help="print the whole manifest")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    path = Path(args.manifest)
    if args.cmd == "init":
        return cmd_init(path, args.run_id, args.head, args.force)
    if args.cmd == "add":
        return cmd_add(path, args.slice_id, args.title, args.files)
    if args.cmd == "set":
        return cmd_set(path, args.slice_id, args.status, args.commit, args.note)
    if args.cmd == "verdict":
        return cmd_verdict(path, args.slice_id, args.state, args.observer,
                           agent_id=args.agent_id, passed=args.passed,
                           skipped=args.skipped, failed=args.failed,
                           discrepancies=args.discrepancies, note=args.note,
                           at=args.at, backfilled=args.backfilled)
    if args.cmd == "resume":
        return cmd_resume(path)
    return cmd_status(path)


if __name__ == "__main__":
    sys.exit(main())
