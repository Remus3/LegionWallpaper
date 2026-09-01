#!/usr/bin/env python3
"""Promote the CURRENT generation into the canonical backup milestone name.

`Ops.backup_put` numbers by arrival: the first write wins the canonical name
and later ones land as `<stem>.<n><ext>`. That is right for a genuine collision
and wrong for a SUPERSEDE, which is what a reopen produces - the rebuilt
milestone gets parked beside a canonical name that still holds the generation
it replaced, and `verify` (one expected hash per milestone key, latest by
timestamp) reports HASH_MISMATCH on it forever.

`lw_pipeline reopen` now rotates the superseded copy out of the way before the
rebuild, so this cannot recur. A guard that only fixed future reopens would
leave the existing rows wrong (CLAUDE.md "Data Fixes"), so this is the recovery
pass for the ones already on disk.

It only ever RENAMES, never deletes, and only when the evidence is unambiguous:
the canonical copy disagrees with the manifest AND a `.N` sibling in the same
folder carries exactly the hash the manifest expects. A mismatch with no such
sibling is UNEXPLAINED and is reported, not guessed at - silencing it would
convert an anomaly into recorded history and kill the check that found it.

Idempotent: a second run finds nothing to do.

DRY-RUN BY DEFAULT. Pass --apply to write.

  python tools/lw_backfill_backup_generation.py
  python tools/lw_backfill_backup_generation.py --apply
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lw_pipeline as lp  # noqa: E402


def _siblings(folder, name):
    """Archived `<stem>.<n><ext>` copies beside a canonical milestone name."""
    stem, ext = os.path.splitext(name)
    out = []
    for p in sorted(folder.iterdir()):
        if not p.is_file() or p.name == name:
            continue
        s, e = os.path.splitext(p.name)
        head, _, tail = s.rpartition(".")
        if e == ext and head == stem and tail.isdigit():
            out.append(p)
    return out


def plan(ctx):
    """Per backup folder, the canonical files whose generation is superseded."""
    rows = []
    base = ctx.root / lp.BACKUP
    if not base.is_dir():
        return rows
    for folder in sorted(base.iterdir()):
        if not folder.is_dir():
            continue
        # the slug's live manifest is the authority; the backup copy is a stale
        # intake-time snapshot, so look the slug up in its stage folder first.
        slug = folder.name
        srcs = []
        for finder in (lp.find_scratch, lp.find_done):
            _stage, f = finder(ctx, slug)
            if f is not None:
                srcs.append(f)
        srcs.append(folder)
        expected = lp._expected_hashes(srcs)
        for p in sorted(folder.iterdir()):
            if not p.is_file():
                continue
            key = lp._milestone_key(p.name)
            if key is None:
                continue
            want = expected.get(key)
            if want is None or lp.sha256_file(p) == want:
                continue
            promote = next((s for s in _siblings(folder, p.name)
                            if lp.sha256_file(s) == want), None)
            rows.append({"folder": folder, "canonical": p,
                         "promote": promote, "want": want})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(lp.DEFAULT_ROOT),
                    help="pipeline root (default C:\\LegionWallpaper\\images)")
    ap.add_argument("--apply", action="store_true",
                    help="write; default is dry-run")
    args = ap.parse_args(argv)

    ctx = lp.Ctx(Path(args.root), dry=not args.apply)
    rows = plan(ctx)
    if not rows:
        print("backup generations: nothing to do")
        return 0

    ops = lp.Ops(dry=not args.apply)
    fixed = unexplained = 0
    for row in rows:
        folder, canonical, promote = row["folder"], row["canonical"], row["promote"]
        if promote is None:
            unexplained += 1
            print(f"unexplained mismatch (no archived sibling carries the "
                  f"expected hash): {ctx.rel(canonical)}")
            continue
        fixed += 1
        verb = "promote" if args.apply else "would promote"
        print(f"{verb} {promote.name} -> {canonical.name} in "
              f"{ctx.rel(folder)}")
        if args.apply:
            # park the superseded generation first so the slot is free
            ops.rename(canonical,
                       lp.next_archive_slot(folder, canonical.name))
            ops.rename(promote, canonical)
    print(f"backup generations: {fixed} promoted, {unexplained} unexplained"
          f"{'' if args.apply else ' (dry-run)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
