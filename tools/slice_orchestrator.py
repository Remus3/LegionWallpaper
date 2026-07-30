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

Usage:
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/slice_orchestrator.py init --run-id 2026-07-29-01 --head <sha> [--force]
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/slice_orchestrator.py add --id S1 --title "run infra" [--files a.py,b.py]
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe tools/slice_orchestrator.py set --id S1 --status committed [--commit <sha>] [--note text]
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


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    print("{:<8} {:<12} {:<10} {:<34} {}"
          .format("ID", "STATUS", "COMMIT", "TITLE", "FILES"))
    for entry in slices:
        print("{:<8} {:<12} {:<10} {:<34} {}"
              .format(entry.get("id", "?"), entry.get("status", "?"),
                      (entry.get("commit") or "-")[:10],
                      entry.get("title", "")[:34],
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
    if args.cmd == "resume":
        return cmd_resume(path)
    return cmd_status(path)


if __name__ == "__main__":
    sys.exit(main())
