#!/usr/bin/env python3
"""Backfill a REPLACE_SOURCE transition for sources that were swapped in place.

The 22 canonical-source swaps (LEDGER 77 + 78) replaced `_firstinitial` files
without recording that they had been replaced, so `scan --verify` reports
HASH_MISMATCH against the INTAKE hash. The outputs are correct; the provenance
record is incomplete. A guard that only fixed future swaps would leave those
rows wrong forever (CLAUDE.md "Data Fixes"), so this is the recovery pass.

It APPENDS - never edits a recorded transition - and is idempotent by hash, so a
second run writes nothing.

REFUSES TO RUN UNSCOPED, and that is the whole safety property. `scan --verify`
reports 32 mismatches, but only the swapped slugs are EXPLAINED; the rest
pre-date the operation and are on slugs it never touched. Blanket-recording
those would convert unexplained anomalies into recorded history and silence the
check that found them. So the slug set must come from the swap manifest (which
carries the wiki title per slug, recorded as the new source) or from explicit
--slug arguments.

DRY-RUN BY DEFAULT. Pass --apply to write.

  python tools/lw_backfill_replace_source.py --from-swap-manifest data/wiki_swap_backup_20260801/swap_manifest.json
  python tools/lw_backfill_replace_source.py --from-swap-manifest <path> --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lw_pipeline as lp  # noqa: E402

WIKI_BASE = "https://leagueoflegends.fandom.com/wiki/"


def load_scope(path):
    """slug -> source url, from the swap manifest the operation wrote."""
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    scope = {}
    for rec in records:
        slug = rec.get("slug")
        if not slug:
            continue
        title = rec.get("wiki_title")
        scope[slug] = (WIKI_BASE + title.replace(" ", "_")) if title else None
    return scope


def drifted(root: Path, slugs):
    """(folder, file, recorded, on_disk) per drifted hash, scoped to `slugs`."""
    out = []
    for stage in sorted(Path(root).iterdir()):
        if not stage.is_dir():
            continue
        for folder in sorted(stage.iterdir()):
            if folder.name not in slugs:
                continue
            if not folder.is_dir() or not (folder / "manifest.json").is_file():
                continue
            expected = lp._expected_hashes([folder])
            for path in sorted(folder.iterdir()):
                if not path.is_file() or not lp.parse_milestone(path.name):
                    continue
                want = expected.get(lp._milestone_key(path.name))
                if not want:
                    continue
                have = lp.sha256_file(path)
                if want != have:
                    out.append((folder, path, want, have))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent
                                          / "images"))
    ap.add_argument("--from-swap-manifest", default=None,
                    help="the swap manifest the operation wrote; supplies both "
                         "the slug scope and the per-slug source url")
    ap.add_argument("--slug", action="append", default=None,
                    help="explicit slug; repeatable. Use when there is no manifest")
    ap.add_argument("--apply", action="store_true", help="write; default is dry-run")
    ap.add_argument("--note", default="source replaced in place; hash recorded "
                                      "retroactively (ROADMAP wiki-swap-manifest-"
                                      "hash-residue)")
    args = ap.parse_args(argv)

    if not args.from_swap_manifest and not args.slug:
        ap.error("refusing to run unscoped - pass --from-swap-manifest or --slug."
                 " Recording every mismatch would silence anomalies nothing"
                 " explains.")

    scope = load_scope(args.from_swap_manifest) if args.from_swap_manifest else {}
    for slug in args.slug or []:
        scope.setdefault(slug, None)

    rows = drifted(Path(args.root), set(scope))
    for _folder, path, want, have in rows:
        print("{:<10} {}\n  recorded {}  on disk {}".format(
            "ADD" if args.apply else "WOULD ADD", path, want[:16], have[:16]))

    slugs_hit = {folder.name for folder, _p, _w, _h in rows}
    print(f"\nscope: {len(scope)} slug(s); drifted files: {len(rows)} across "
          f"{len(slugs_hit)} slug(s)")
    if not args.apply:
        print("dry-run. Re-run with --apply to write.")
        return 0

    written = 0
    for folder, path, _want, _have in rows:
        if lp.record_replace_source(folder, path, note=args.note,
                                    source_url=scope.get(folder.name)):
            written += 1
    print(f"wrote {written} REPLACE_SOURCE transition(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
