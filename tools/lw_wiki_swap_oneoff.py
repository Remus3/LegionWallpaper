"""One-off: swap the 22 confirmed wiki upgrades in as the new `_firstinitial`.

Operator-directed 2026-08-01, on the evidence in
`docs/WIKI_VS_FIRSTINITIAL_2026-08-01.md`: of 77 corpus images confirmed to be
the same artwork as a canonical wiki splash, 22 are a clear upgrade on BOTH axes
(more native pixels AND sharper at common scale, from the original bytes).

The pipeline has no reverse transition, so this performs the proven reopen dance
(memory `project-reprocess-done-slug`, 2026-07-15):

  1. fetch + VERIFY every wiki original first, mutating nothing
  2. stage `1.First Pass Scratch/<slug>/` with the new initial + a copy of the
     Done manifest (copy before any move, so a crash loses nothing)
  3. move the stale `2.First Pass Done/<slug>/` to a dated backup
  4. `lw_first_pass.py --batch <slugs>` then `lw_pipeline.py approve <slug>`

Two things this handles that the memory does not mention:

  * `select_source` PREFERS a decodable fetched DeviantArt fullview over the
    scratch `_firstinitial`. 9 of these 22 have one, so staging alone would be
    silently ignored for those and the run would report success having changed
    nothing. Their fetched folders are moved into the same backup.
  * `_firstinitial` keeps the SOURCE's extension, so the stale one is found by
    glob rather than by assuming `.png`.

Everything removed is MOVED into one dated backup directory, never deleted.

Usage:
  python tools/lw_wiki_swap_oneoff.py --plan <swap22.json> --dry-run
  python tools/lw_wiki_swap_oneoff.py --plan <swap22.json>
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "images"
SCRATCH = IMAGES / "1.First Pass Scratch"
DONE = IMAGES / "2.First Pass Done"
FETCHED = ROOT / "data" / "recovery" / "fetched"
GG = "https://wiki.leagueoflegends.com/en-us/api.php"
UA = "lw_wiki_swap/1.0 (Legion Wallpaper canonical-source swap)"


def api(params):
    params = dict(params)
    params.setdefault("format", "json")
    req = urllib.request.Request(GG + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def fetch_original(title):
    """The file's ORIGINAL bytes plus its declared dimensions.

    No `?format=original` dance is needed on wiki.gg - that rule is Fandom's
    (docs/MCP_LIFT_P3_2026-08-01.md). The declared sha1 is deliberately NOT
    asserted against these bytes: no host serves bytes matching it, so
    provenance records the sha256 of what actually arrived.
    """
    js = api({"action": "query", "titles": title, "prop": "imageinfo",
              "iiprop": "url|size|dimensions|sha1"})
    ii = None
    for _, pg in (js.get("query", {}).get("pages", {}) or {}).items():
        for cand in pg.get("imageinfo", []) or []:
            ii = cand
    if not ii:
        raise RuntimeError(f"no imageinfo for {title}")
    req = urllib.request.Request(ii["url"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        body = r.read()
    return body, ii


def verify(body, expect_w, expect_h):
    """Decode and confirm the bytes are the image the plan was built on."""
    with Image.open(io.BytesIO(body)) as im:
        im.load()
        w, h = im.size
        fmt, mode = im.format, im.mode
    if (w, h) != (expect_w, expect_h):
        raise RuntimeError(f"dims {w}x{h} != planned {expect_w}x{expect_h}")
    return {"w": w, "h": h, "format": fmt, "mode": mode,
            "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def stale_initial(slug_dir: Path):
    hits = sorted(slug_dir.glob(f"{slug_dir.name}_firstinitial.*"))
    return hits[0] if hits else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Swap wiki upgrades into first pass")
    ap.add_argument("--plan", required=True, help="json list with slug/match/wiki_w/wiki_h")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--backup", default=None, help="override the backup dir")
    args = ap.parse_args(argv)

    rows = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    backup = Path(args.backup) if args.backup else (
        ROOT / "data" / f"wiki_swap_backup_{date.today():%Y%m%d}")
    print(f"{len(rows)} slug(s); backup dir {backup}")
    if args.dry_run:
        print("DRY RUN - nothing will be fetched or moved\n")

    # ---- preflight, before anything is touched -------------------------------
    problems = []
    for r in rows:
        slug = r["slug"]
        if not (DONE / slug).is_dir():
            problems.append(f"{slug}: Done folder missing")
        if (SCRATCH / slug).exists():
            problems.append(f"{slug}: scratch folder ALREADY exists")
        if not stale_initial(DONE / slug):
            problems.append(f"{slug}: no _firstinitial in Done")
    if problems:
        print("REFUSED - preflight found problems:")
        for p in problems:
            print("  " + p)
        return 2
    print("preflight OK: every Done folder present, no scratch collisions\n")

    if args.dry_run:
        for r in rows:
            fv = FETCHED / r["slug"]
            print(f"  {r['slug'][:52]:<54} <- {r['match'][5:]}"
                  + ("   [+move fetched fullview aside]" if fv.is_dir() else ""))
        return 0

    # ---- phase 1: fetch + verify EVERYTHING before mutating anything ---------
    staged_bytes = {}
    for n, r in enumerate(rows, 1):
        body, ii = fetch_original(r["match"])
        meta = verify(body, r["wiki_w"], r["wiki_h"])
        staged_bytes[r["slug"]] = (body, meta, ii)
        print(f"  [{n:>2}/{len(rows)}] fetched {meta['bytes']/1e6:>5.1f} MB "
              f"{meta['w']}x{meta['h']} {meta['format']} {r['match'][5:52]}")
    print("\nall originals fetched and verified - mutation begins\n")

    # ---- phase 2: stage, then move the stale state aside --------------------
    (backup / "done").mkdir(parents=True, exist_ok=True)
    (backup / "fetched").mkdir(parents=True, exist_ok=True)
    (backup / "new_initials").mkdir(parents=True, exist_ok=True)
    record = []

    for r in rows:
        slug = r["slug"]
        body, meta, ii = staged_bytes[slug]
        done_dir = DONE / slug
        scratch_dir = SCRATCH / slug
        scratch_dir.mkdir(parents=True, exist_ok=False)

        # copy the manifest FIRST - a crash here loses nothing
        shutil.copy2(done_dir / "manifest.json", scratch_dir / "manifest.json")

        ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(meta["format"], ".jpg")
        new_init = scratch_dir / f"{slug}_firstinitial{ext}"
        tmp = new_init.with_suffix(new_init.suffix + ".tmp")
        tmp.write_bytes(body)
        tmp.replace(new_init)
        shutil.copy2(new_init, backup / "new_initials" / new_init.name)

        moved_fetched = None
        fv = FETCHED / slug
        if fv.is_dir():
            # select_source prefers a fetched fullview; leaving it would make
            # the swap a silent no-op for this slug.
            dst = backup / "fetched" / slug
            shutil.move(str(fv), str(dst))
            moved_fetched = str(dst)

        old_init = stale_initial(done_dir)
        shutil.move(str(done_dir), str(backup / "done" / slug))

        record.append({
            "slug": slug, "wiki_title": r["match"],
            "new_initial": str(new_init), "new_initial_sha256": meta["sha256"],
            "new_dims": [meta["w"], meta["h"]], "new_format": meta["format"],
            "new_bytes": meta["bytes"],
            "declared_sha1_NOT_asserted": ii.get("sha1"),
            "old_initial_name": old_init.name if old_init else None,
            "old_dims": [r["src_w"], r["src_h"]],
            "px_ratio": r["px_ratio"], "lap_ratio": r["orig_lap_ratio"],
            "held_halo_pct": r["held_halo_pct"],
            "aspect_class": r["cls"], "area_loss": r["loss"],
            "moved_done_to": str(backup / "done" / slug),
            "moved_fetched_to": moved_fetched,
        })
        print(f"  staged {slug[:56]}")

    (backup / "swap_manifest.json").write_text(
        json.dumps(record, indent=1) + "\n", encoding="utf-8")
    slugs_file = backup / "slugs.txt"
    slugs_file.write_text("\n".join(r["slug"] for r in record) + "\n",
                          encoding="utf-8")
    print(f"\nstaged {len(record)} slug(s). Backup + manifest: {backup}")
    print("NEXT (explicit slugs file - never --all-scratch, it would sweep the "
          "20 pre-existing WIP scratch slugs):")
    print(f'  python tools/lw_first_pass.py --batch "{slugs_file}"')
    return 0


if __name__ == "__main__":
    sys.exit(main())
