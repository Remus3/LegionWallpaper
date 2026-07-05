"""lw_recover_campaign.py - source-recovery CAMPAIGN DRIVER for Legion Wallpaper.

Spec: docs/research/SOURCE_RECOVERY.md (Tier 0/1/2 mechanics) and
docs/RESTORATION_PLAN.md section 2.1 (the four-tier waterfall) + section 8
(DeviantArt download-quota urgency). This module ORCHESTRATES the existing
tools/lw_recover.py primitives across the pending preview set - it re-implements
NONE of them. The waterfall math, token decode, oEmbed, gallery-dl wrapper,
SauceNAO client, and manual-queue append all live in lw_recover; here we only:

  1. enumerate the pending targets (0.Originals flat + Found subfolders that do
     NOT yet hold a recovered original),
  2. build a cached corpus of pHash/dHash over the candidate source dirs,
  3. drive lw_recover.run_waterfall per target,
  4. act on the winning tier (fetch the fullview for a live deviation; record
     the source URL as manifest provenance via the real pipeline annotate),
  5. persist every per-target result to a resumable matches.json.

CI-safe style (copied 1:1 from tools/lw_recover.py): ONLY the standard library
is imported at module top level. imagehash + PIL are reachable ONLY through the
injected `compute` default (lw_recover.compute_hashes, which lazy-imports them);
NOTHING heavy is imported here. EVERY side effect - network (http getter),
hashing (compute), subprocess (runner / fetch), clock (sleep) - is
dependency-INJECTED so NO unit test touches the network, a real subprocess, or
disk outside a tmp dir. Atomic writes only (tmp then os.replace, mirroring
lw_recover.append_manual_queue).

Error Handling rule (CLAUDE.md): a target NEVER surfaces a raw error string and
NEVER crashes the campaign - a per-target failure is caught, recorded as a
friendly status, and the driver moves to the next target.

7-bit ASCII only (repo hard rule): no em/en dashes, no smart quotes; " - " for
clause breaks.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
import unicodedata
from typing import Any, Callable, Dict, List, Optional

# Bootstrap: launched as a script (python tools/lw_recover_campaign.py) the
# script's own dir - not the repo root - lands on sys.path, so the sibling
# "from tools import ..." below would fail. Put the repo root on sys.path FIRST
# (the __main__ guard repeats this; doing it here also covers direct script use,
# the project convention e.g. python tools/lw_pipeline.py annotate ...).
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import lw_recover  # noqa: E402

# CREATE_NO_WINDOW: suppress the console flash when we shell out to the pipeline
# annotate under a windowless parent on Windows (0 elsewhere - a harmless flag).
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# A pending preview file: <stuff>-pre.<ext> or <stuff>-fullview.<ext>.
_PREVIEW_RE = re.compile(r"-(?:pre|fullview)\.[^.]+$", re.IGNORECASE)

# A recovered original already dropped into a Found subfolder: the wixmp shape
# <token>-<uuid>-... i.e. "d" + 6-8 base36, then a "-", then an 8-hex block.
_RECOVERED_RE = re.compile(r"^d[0-9a-z]{6,8}-[0-9a-f]{8}-")

# Image extensions we hash when building the candidate corpus.
_IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")

# CLI defaults (Legion box layout). Overridable on the command line.
_DEFAULT_ORIGINALS = os.path.join("images", "0.Originals")
_DEFAULT_FOUND = r"C:\Users\Administrator\Desktop\Found"
_DEFAULT_CORPUS = [r"C:\Users\Administrator\Pictures",
                   r"C:\Users\Administrator\Desktop\Found"]
_DEFAULT_FETCH_DIR = os.path.join("data", "recovery", "fetched")


# ===========================================================================
# 1. derive_slug - reproduce lw_pipeline.slugify EXACTLY (minus RESERVED_NAMES)
# ===========================================================================
def derive_slug(name: str) -> str:
    """Slug a basename identically to lw_pipeline.slugify (steps 1-6).

    stem = splitext[0]; NFKD-normalize; ascii-ignore-encode -> lower; collapse
    every non [a-z0-9] run to "-"; strip leading/trailing "-"; cap at 64 and
    rstrip("-"); empty -> "img". The RESERVED_NAMES ".-x" suffix rule is
    intentionally OMITTED (a d-token filename can never collide with con/prn/
    lpt1/...); test_derive_slug_matches_pipeline_slugify cross-checks real
    corpus names against the live slugify to prove parity on the inputs we see.
    """
    stem = os.path.splitext(name)[0]
    stem = unicodedata.normalize("NFKD", stem)
    stem = stem.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem)
    slug = slug.strip("-")
    slug = slug[:64].rstrip("-")
    if not slug:
        slug = "img"
    return slug


# ===========================================================================
# 2. enumerate_targets - the pending preview set
# ===========================================================================
def enumerate_targets(
    originals_dir: str,
    found_root: str,
    *,
    lister: Callable[[str], List[str]] = os.listdir,
    isdir: Callable[[str], bool] = os.path.isdir,
) -> List[Dict[str, Any]]:
    """Build the pending target list from 0.Originals + the Found tree.

    Rule (verified ground truth):
      (a) In originals_dir FLAT, take every file matching *-pre.* / *-fullview.*.
      (b) For each SUBFOLDER of found_root, take its -pre / -fullview file ONLY
          IF that folder does NOT already contain a recovered original (a file
          matching _RECOVERED_RE, i.e. <token>-<uuid>-...). A folder that has
          already been recovered is skipped entirely.
    .gitkeep and any non-preview file are ignored; pipeline stage dirs are never
    descended (we only look one level into found_root's immediate subfolders).

    lister / isdir are injected so a test drives a fake tree with no real disk.
    Each result = {"path": abspath, "name": basename, "slug": derive_slug(name)}.
    """
    targets: List[Dict[str, Any]] = []

    # (a) flat previews directly under originals_dir
    if isdir(originals_dir):
        for entry in sorted(_safe_list(lister, originals_dir)):
            if _is_preview(entry):
                targets.append(_make_target(originals_dir, entry))

    # (b) one level into found_root: each immediate subfolder
    if isdir(found_root):
        for sub in sorted(_safe_list(lister, found_root)):
            subpath = os.path.join(found_root, sub)
            if not isdir(subpath):
                continue
            entries = _safe_list(lister, subpath)
            if any(_RECOVERED_RE.match(e) for e in entries):
                continue  # already recovered - nothing pending here
            for entry in sorted(entries):
                if _is_preview(entry):
                    targets.append(_make_target(subpath, entry))

    return targets


def _safe_list(lister: Callable[[str], List[str]], path: str) -> List[str]:
    try:
        return list(lister(path))
    except OSError:
        return []


def _is_preview(entry: str) -> bool:
    if entry == ".gitkeep":
        return False
    return bool(_PREVIEW_RE.search(entry))


def _make_target(folder: str, entry: str) -> Dict[str, Any]:
    return {
        "path": os.path.abspath(os.path.join(folder, entry)),
        "name": entry,
        "slug": derive_slug(entry),
    }


# ===========================================================================
# 3. build_corpus_hashes - cached pHash/dHash over the candidate source dirs
# ===========================================================================
def build_corpus_hashes(
    dirs: List[str],
    cache_path: str,
    *,
    compute: Callable[[str], Dict[str, int]] = lw_recover.compute_hashes,
    walker: Callable = os.walk,
    statter: Callable = os.stat,
    now: Optional[Callable[[], float]] = None,
) -> List[Dict[str, Any]]:
    """Hash every image under each dir in `dirs`, caching by (mtime, size).

    Returns [{"path","phash","dhash"}, ...]. The cache is a JSON map
    abspath -> {mtime, size, phash, dhash}; on a second run, a file whose
    (mtime, size) is unchanged is served from cache and NOT re-hashed (compute
    is not called for it). An unreadable file (compute raises) is skipped and
    omitted, mirroring the Tier-0 CLI at lw_recover.py:635-638. Atomic write
    (tmp then os.replace). compute / walker / statter are injected for tests.
    """
    cache = _load_cache(cache_path)
    new_cache: Dict[str, Dict[str, Any]] = {}
    rows: List[Dict[str, Any]] = []

    for root in dirs:
        for dirpath, _dirs, files in walker(root):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                if ext not in _IMG_EXTS:
                    continue
                fp = os.path.abspath(os.path.join(dirpath, fn))
                try:
                    st = statter(fp)
                    mtime = float(st.st_mtime)
                    size = int(st.st_size)
                except OSError:
                    continue  # vanished / unreadable - skip
                cached = cache.get(fp)
                if cached and cached.get("mtime") == mtime and \
                        cached.get("size") == size:
                    entry = {"mtime": mtime, "size": size,
                             "phash": cached["phash"], "dhash": cached["dhash"]}
                else:
                    try:
                        h = compute(fp)
                    except Exception:  # noqa: BLE001 - skip unreadable, like the CLI
                        continue
                    entry = {"mtime": mtime, "size": size,
                             "phash": h["phash"], "dhash": h["dhash"]}
                new_cache[fp] = entry
                rows.append({"path": fp, "phash": entry["phash"],
                             "dhash": entry["dhash"]})

    _atomic_write_json(cache_path, new_cache)
    return rows


def _load_cache(cache_path: str) -> Dict[str, Any]:
    try:
        with open(cache_path, encoding="ascii", errors="replace") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


# ===========================================================================
# 4. annotate_via_pipeline - real provenance annotate (shells the pipeline)
# ===========================================================================
def annotate_via_pipeline(
    slug: str,
    source_url: str,
    *,
    tool: str = "lw_recover_campaign",
    runner: Callable = subprocess.run,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Record source_url as manifest provenance via the REAL pipeline annotate.

    Shells `python tools/lw_pipeline.py annotate <slug> --source-url <url>
    --tool <tool>` with creationflags=CREATE_NO_WINDOW (no console flash on
    Legion). Return-code mapping:
      0            -> {"ok": True,  "status": "annotated"}
      non-zero     -> {"ok": False, "status": "no_manifest"}   (incl code 2 =
                      slug not in scratch/done/backup, or no manifest.json - the
                      loose-file case for a raw Found/Desktop file)
      FileNotFoundError / other -> {"ok": False, "status": "error", ...}
    NEVER raises. dry_run short-circuits to {"ok": True, "status": "dry_run"}
    without shelling. runner is injected so tests never spawn a real process.
    """
    if dry_run:
        return {"ok": True, "status": "dry_run"}

    import sys
    cmd = [sys.executable, os.path.join("tools", "lw_pipeline.py"), "annotate",
           slug, "--source-url", source_url, "--tool", tool]
    try:
        proc = runner(cmd, capture_output=True, text=True,
                      creationflags=_NO_WINDOW)
    except FileNotFoundError:
        return {"ok": False, "status": "error",
                "message": "python or lw_pipeline.py not found"}
    except Exception as exc:  # noqa: BLE001 - degrade, never surface raw error
        return {"ok": False, "status": "error",
                "message": f"annotate invocation failed ({type(exc).__name__})"}

    if getattr(proc, "returncode", 1) == 0:
        return {"ok": True, "status": "annotated"}
    # code 2 (no manifest / slug not found) and any other non-zero: the slug has
    # no manifest to annotate (a loose Found/Desktop file). Degrade, do not fail.
    return {"ok": False, "status": "no_manifest"}


# ===========================================================================
# 5. run_campaign - the orchestrator
# ===========================================================================
def run_campaign(
    targets: List[Dict[str, Any]],
    corpus: List[Dict[str, Any]],
    config: Dict[str, Any],
    *,
    http: Optional[Callable] = None,
    compute: Callable[[str], Dict[str, int]] = lw_recover.compute_hashes,
    fetch: Callable = lw_recover.gallery_dl_fetch,
    annotate: Callable = annotate_via_pipeline,
    sleep: Callable[[float], None] = time.sleep,
    saucenao_throttle: float = 8.0,
    matches_path: Optional[str] = None,
    saucenao_cache_path: Optional[str] = None,
    manual_queue_path: Optional[str] = None,
    fetch_dir: Optional[str] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Drive the recovery waterfall across the pending target set.

    Per target (capped at `limit`): compute its hashes, run
    lw_recover.run_waterfall, then act on the winning tier -
      T0 local match  -> annotate the LOCAL source path (manifest provenance)
      T1 live devart  -> gallery-dl fetch the fullview (original=False, quota
                         free) then annotate the deviation URL
      T2 saucenao     -> annotate the saucenao URL and cache the response so it
                         is never re-searched
      T3 manual queue -> the waterfall already wrote manual_queue.csv
    Every per-target result is persisted to matches_path (atomic JSON list) so
    the campaign is resumable and is the provenance-of-record for loose files.
    A network-tier hit (T1 oembed / T2 saucenao) is followed by a
    sleep(saucenao_throttle); a Tier-0 local match is NOT throttled. dry_run
    performs no fetch, no real annotate, and no file writes - it still returns
    the planned summary. A per-target error is caught and recorded, never
    crashing the campaign (Error Handling rule).
    """
    subset = targets if limit is None else targets[:limit]
    results: List[Dict[str, Any]] = []
    summary = {"total": 0, "matched": 0, "fetched": 0, "saucenao": 0,
               "review": 0, "manual_queued": 0, "annotated": 0,
               "annotate_skipped": 0, "errors": 0}
    sauce_cache = {} if dry_run else _load_cache(saucenao_cache_path) \
        if saucenao_cache_path else {}

    for target in subset:
        summary["total"] += 1
        slug = target.get("slug") or derive_slug(target.get("name", ""))
        try:
            record = _process_one(
                target, slug, corpus, config, http=http, compute=compute,
                fetch=fetch, annotate=annotate, sleep=sleep,
                saucenao_throttle=saucenao_throttle,
                manual_queue_path=manual_queue_path, fetch_dir=fetch_dir,
                sauce_cache=sauce_cache, saucenao_cache_path=saucenao_cache_path,
                dry_run=dry_run)
        except Exception as exc:  # noqa: BLE001 - one bad target never kills the run
            summary["errors"] += 1
            results.append({"slug": slug, "name": target.get("name"),
                            "tier": None, "source": None,
                            "status": "error",
                            "message": f"target failed ({type(exc).__name__})"})
            continue

        results.append(record)
        _tally(summary, record)

    if not dry_run and matches_path:
        _atomic_write_json(matches_path, results)

    return {"results": results, "summary": summary}


def _process_one(
    target: Dict[str, Any],
    slug: str,
    corpus: List[Dict[str, Any]],
    config: Dict[str, Any],
    *,
    http,
    compute,
    fetch,
    annotate,
    sleep,
    saucenao_throttle,
    manual_queue_path,
    fetch_dir,
    sauce_cache,
    saucenao_cache_path,
    dry_run,
) -> Dict[str, Any]:
    """Run one target through the waterfall and act on the winning tier.

    Returns the per-target record dict. Raises only on a truly unexpected error
    (caught by run_campaign) - the recovery primitives themselves never raise.
    """
    # Compute this target's hashes; a hash failure degrades to a zero hash so
    # the waterfall can still try the token / saucenao tiers (Error Handling).
    hash_status = "ok"
    try:
        h = compute(target["path"])
    except Exception as exc:  # noqa: BLE001 - friendly per-target degrade
        h = {"phash": 0, "dhash": 0}
        hash_status = f"hash_failed ({type(exc).__name__})"
    wf_target = dict(target)
    wf_target["phash"] = h["phash"]
    wf_target["dhash"] = h["dhash"]

    rep = lw_recover.run_waterfall(
        wf_target, corpus, config, http=http,
        manual_queue_path=manual_queue_path)
    tier = rep.get("tier")
    decisions = rep.get("decisions", [])
    is_review = any(d.get("decision") == "review" for d in decisions)

    record: Dict[str, Any] = {
        "slug": slug,
        "name": target.get("name"),
        "path": target.get("path"),
        "tier": tier,
        "source": rep.get("source"),
        "hash_status": hash_status,
        "review": is_review,
        "fetch_status": None,
        "annotate_status": None,
        "evidence": rep.get("evidence", {}),
    }

    hit_network = False

    if tier == 0:
        # local consensus match - source is a local path; annotate provenance.
        record["annotate_status"] = _do_annotate(
            annotate, slug, rep.get("source"), dry_run)

    elif tier == 1:
        # live deviation - pull the quota-free fullview, then annotate the URL.
        hit_network = True
        deviation_id = lw_recover.decode_deviation_token(target.get("name", ""))
        if not dry_run and fetch is not None and deviation_id is not None:
            dest = os.path.join(fetch_dir or _DEFAULT_FETCH_DIR, slug)
            fres = fetch(deviation_id, config, dest_dir=dest, original=False)
            record["fetch_status"] = fres.get("status") if isinstance(
                fres, dict) else "unknown"
            record["fetched"] = bool(isinstance(fres, dict) and fres.get("ok"))
        else:
            record["fetch_status"] = "dry_run" if dry_run else "skipped"
            record["fetched"] = False
        # annotate the deviation URL regardless of whether the fetch degraded.
        record["annotate_status"] = _do_annotate(
            annotate, slug, rep.get("source"), dry_run)

    elif tier == 2:
        # saucenao accept - annotate the source URL, cache the hit so it is
        # never re-searched (keyed by the target path).
        hit_network = True
        if not dry_run:
            sauce_cache[target["path"]] = {
                "slug": slug, "source": rep.get("source"),
                "evidence": rep.get("evidence", {})}
        record["annotate_status"] = _do_annotate(
            annotate, slug, rep.get("source"), dry_run)

    elif tier == 3:
        # the waterfall already parked this in manual_queue.csv; nothing to do.
        record["annotate_status"] = "manual"

    # self-throttle only after a network-tier target (T1 oembed / T2 saucenao),
    # never after a Tier-0 local match. Skipped entirely in dry-run.
    if hit_network and not dry_run:
        sleep(saucenao_throttle)

    if not dry_run and saucenao_cache_path and tier == 2:
        _atomic_write_json(saucenao_cache_path, sauce_cache)

    return record


def _do_annotate(annotate, slug, source_url, dry_run) -> str:
    """Call annotate and normalise its result into a short status string.

    In dry_run we still call annotate(dry_run=True) so the injected stub records
    the intent, but it performs no real work. Returns "annotated" |
    "annotate_skipped" (mapped from a no_manifest / non-ok result) | "dry_run".
    """
    if source_url is None:
        return "no_source"
    res = annotate(slug, source_url=source_url, dry_run=dry_run)
    if not isinstance(res, dict):
        return "annotate_skipped"
    if res.get("status") == "dry_run":
        return "dry_run"
    if res.get("ok"):
        return "annotated"
    return "annotate_skipped"


def _tally(summary: Dict[str, int], record: Dict[str, Any]) -> None:
    """Fold one per-target record into the running summary counters."""
    tier = record.get("tier")
    if tier == 0:
        summary["matched"] += 1
    elif tier == 1:
        if record.get("fetched"):
            summary["fetched"] += 1
    elif tier == 2:
        summary["saucenao"] += 1
    elif tier == 3:
        summary["manual_queued"] += 1
    if record.get("review"):
        summary["review"] += 1
    astatus = record.get("annotate_status")
    if astatus == "annotated":
        summary["annotated"] += 1
    elif astatus == "annotate_skipped":
        summary["annotate_skipped"] += 1


# ===========================================================================
# atomic JSON write (mirrors lw_recover.append_manual_queue)
# ===========================================================================
def _atomic_write_json(path: str, obj: Any) -> str:
    """Write obj as JSON to path via tmp-then-os.replace (never a torn file)."""
    target = os.path.abspath(path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="ascii") as f:
        json.dump(obj, f, indent=2)
    os.replace(tmp, target)
    return target


# ===========================================================================
# config assembly for the REAL run (gallery-dl config presence + api keys)
# ===========================================================================
def _assemble_config() -> Dict[str, Any]:
    """Build the waterfall config from the gallery-dl config + local API keys.

    Reads %APPDATA%/gallery-dl/config.json if present and lifts its
    extractor.deviantart block (client-id / client-secret / refresh-token) into
    a top-level {"deviantart": {...}} so gallery_dl_fetch's gate sees it. Never
    raises - a missing / malformed config yields an empty config (Tier 1 fetch
    then degrades to not_configured, which the campaign handles). The SauceNAO
    key is read live by run_waterfall itself; nothing to wire here.
    """
    cfg: Dict[str, Any] = {}
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return cfg
    gdl_path = os.path.join(appdata, "gallery-dl", "config.json")
    try:
        with open(gdl_path, encoding="utf-8", errors="replace") as f:
            gdl = json.load(f)
    except (OSError, ValueError):
        return cfg
    da = (((gdl.get("extractor") or {}).get("deviantart")) or {}) \
        if isinstance(gdl, dict) else {}
    if da.get("client-id"):
        cfg["deviantart"] = {
            "client-id": da.get("client-id"),
            "client-secret": da.get("client-secret"),
            "refresh-token": da.get("refresh-token"),
        }
    return cfg


# ===========================================================================
# thin argparse CLI
# ===========================================================================
def _default_matches_path() -> str:
    return os.path.join("data", "recovery", "matches.json")


def _default_hashes_path() -> str:
    return os.path.join("data", "recovery", "hashes.json")


def _default_saucenao_cache_path() -> str:
    return os.path.join("data", "recovery", "saucenao_cache.json")


def main(argv=None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="lw_recover_campaign",
        description="source-recovery campaign driver - orchestrate the "
                    "lw_recover waterfall across the pending preview set")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="run the recovery campaign")
    pr.add_argument("--originals", default=_DEFAULT_ORIGINALS,
                    help="flat 0.Originals dir of dropped previews")
    pr.add_argument("--found", default=_DEFAULT_FOUND,
                    help="root of the per-artwork Found subfolders")
    pr.add_argument("--corpus", nargs="+", default=list(_DEFAULT_CORPUS),
                    help="candidate source dirs to hash for Tier-0 matching")
    pr.add_argument("--limit", type=int, default=None,
                    help="process at most N targets")
    pr.add_argument("--dry-run", action="store_true",
                    help="plan only - no fetch, no annotate, no writes")
    pr.add_argument("--fetch-dir", default=_DEFAULT_FETCH_DIR,
                    help="where gallery-dl drops fetched fullviews")
    pr.add_argument("--throttle", type=float, default=8.0,
                    help="seconds to sleep after each network-tier target - "
                         "SauceNAO is rare here (tokens resolve at Tier-1 "
                         "oEmbed) so 2.0 suits an oEmbed-dominated full run")

    pp = sub.add_parser("report", help="dump data/recovery/matches.json")
    pp.add_argument("--matches", default=_default_matches_path())

    a = p.parse_args(argv)

    if a.cmd == "report":
        try:
            with open(a.matches, encoding="ascii", errors="replace") as f:
                data = json.load(f)
        except (OSError, ValueError):
            print("[]")
            return 1
        print(json.dumps(data, indent=2))
        return 0

    if a.cmd == "run":
        targets = enumerate_targets(a.originals, a.found)
        corpus = build_corpus_hashes(a.corpus, _default_hashes_path())
        config = _assemble_config()
        report = run_campaign(
            targets, corpus, config,
            http=lw_recover._default_http,
            fetch=lw_recover.gallery_dl_fetch,
            annotate=annotate_via_pipeline,
            matches_path=_default_matches_path(),
            saucenao_cache_path=_default_saucenao_cache_path(),
            fetch_dir=a.fetch_dir,
            saucenao_throttle=a.throttle,
            limit=a.limit,
            dry_run=a.dry_run)
        print(json.dumps(report["summary"], indent=2))
        return 0

    return 1


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.exit(main())
