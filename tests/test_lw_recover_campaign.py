"""Tests for tools/lw_recover_campaign.py - the source-recovery CAMPAIGN driver.

Spec: docs/research/SOURCE_RECOVERY.md + docs/RESTORATION_PLAN.md section 2.1
(the four-tier waterfall) + section 8 (DeviantArt download-quota urgency). The
campaign driver orchestrates the existing tools/lw_recover.py primitives across
the pending preview set; it re-implements NONE of them. Written test-first per
CLAUDE.md TDD.

CI constraint (mirrors tests/test_lw_recover.py): this module must import with
ONLY stdlib + numpy available. imagehash/PIL are reachable only via the injected
`compute` default (never imported at top). EVERY side effect - network, hash,
subprocess, clock, file walk - is dependency-INJECTED, so NO test here touches
the network, a real subprocess, or disk outside tmp_path.
"""

import csv
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lw_recover  # noqa: E402
from tools import lw_recover_campaign as campaign  # noqa: E402


# ---------------------------------------------------------------------------
# fakes (no network, no heavy deps) - the http fakes mirror test_lw_recover.py
# ---------------------------------------------------------------------------
class FakeHttp:
    """Injected http getter: get(url, *, data, headers, timeout) -> (status, text)."""

    def __init__(self, responses=None, default=(200, "{}")):
        self.responses = responses or {}
        self.default = default
        self.calls = []

    def __call__(self, url, *, data=None, headers=None, timeout=None):
        self.calls.append(url)
        for frag, resp in self.responses.items():
            if frag in url:
                return resp
        return self.default


class CountingCompute:
    """A compute(path)->{'phash','dhash'} fake that records its call count and
    can be told to raise for specific paths (an unreadable file)."""

    def __init__(self, table=None, raise_for=None):
        self.table = table or {}
        self.raise_for = set(raise_for or ())
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        if path in self.raise_for:
            raise OSError("cannot read image")
        return self.table.get(path, {"phash": 0, "dhash": 0})


class RecordingFetch:
    """A gallery_dl_fetch stand-in recording (deviation_id, kwargs) and
    returning a canned dict (ok by default)."""

    def __init__(self, result=None):
        self.result = result or {"ok": True, "status": "fetched"}
        self.calls = []

    def __call__(self, deviation_id, config, dest_dir=None, original=False, **kw):
        self.calls.append({"deviation_id": deviation_id, "dest_dir": dest_dir,
                           "original": original})
        return self.result


class RecordingAnnotate:
    """An annotate stand-in recording (slug, source_url) and returning a canned
    dict (annotated by default)."""

    def __init__(self, result=None):
        self.result = result or {"ok": True, "status": "annotated"}
        self.calls = []

    def __call__(self, slug, source_url, **kw):
        self.calls.append({"slug": slug, "source_url": source_url, "kw": kw})
        return self.result


def _sleep_recorder():
    calls = []

    def _sleep(secs):
        calls.append(secs)
    _sleep.calls = calls
    return _sleep


# ===========================================================================
# 1. enumerate_targets - build the pending target list from a fake tree
# ===========================================================================
def test_enumerate_targets_picks_pending_excludes_recovered():
    # Fake tree:
    #   originals/  (FLAT) -> two previews + a non-preview rip + .gitkeep
    #   found/aaa/  -> only a -pre (PENDING - include)
    #   found/bbb/  -> a -pre AND a <token>-<uuid> original (RECOVERED - exclude)
    #   found/ccc/  -> only a non-preview file (no preview - nothing to take)
    originals = os.path.join("root", "originals")
    found = os.path.join("root", "found")
    tree = {
        originals: ["ahri_by_x_dl1a2b3-pre.jpg", "sona_by_y_dm9z8y7-fullview.png",
                    "1341679.jpeg", ".gitkeep"],
        found: ["aaa", "bbb", "ccc"],
        os.path.join(found, "aaa"): ["janna_by_z_dl27k7h-pre.jpg", ".gitkeep"],
        os.path.join(found, "bbb"): [
            "kaisa_by_w_dl3e4dq-pre.jpg",
            "dl3e4dq-0ad4bcb2-42f6-48d5-b3ea-cb216eda20bd.jpg"],
        os.path.join(found, "ccc"): ["notes.txt"],
    }
    dirs = set(tree.keys())

    def lister(path):
        return list(tree.get(path, []))

    def isdir(path):
        return path in dirs

    out = campaign.enumerate_targets(originals, found, lister=lister, isdir=isdir)
    names = sorted(t["name"] for t in out)
    assert names == ["ahri_by_x_dl1a2b3-pre.jpg",
                     "janna_by_z_dl27k7h-pre.jpg",
                     "sona_by_y_dm9z8y7-fullview.png"]
    # the RECOVERED folder's -pre is excluded; .gitkeep + non-preview rips ignored
    assert not any(t["name"] == "kaisa_by_w_dl3e4dq-pre.jpg" for t in out)
    assert not any(t["name"] == "1341679.jpeg" for t in out)
    # every result carries an abspath and a slug
    for t in out:
        assert os.path.isabs(t["path"])
        assert t["slug"]


# ===========================================================================
# 2. derive_slug cross-check against the real lw_pipeline.slugify
# ===========================================================================
def test_derive_slug_matches_pipeline_slugify():
    from tools import lw_pipeline  # lazy inside test - not needed at module import
    for name in ("ionian_janna_by_niphrimit_dl27k7h-pre.jpg",
                 "dark_cosmic_ahri_by_someone_dlnxav6-fullview.png",
                 "1341679.jpeg"):
        assert campaign.derive_slug(name) == lw_pipeline.slugify(name)
    # the documented worked example spelled out explicitly
    assert campaign.derive_slug("ionian_janna_by_niphrimit_dl27k7h-pre.jpg") == (
        "ionian-janna-by-niphrimit-dl27k7h-pre")


# ===========================================================================
# 3. build_corpus_hashes - atomic + caches + skips unreadable
# ===========================================================================
def test_build_corpus_hashes_caches_and_is_atomic(tmp_path):
    imgdir = tmp_path / "pics"
    imgdir.mkdir()
    good = imgdir / "a.png"
    good.write_bytes(b"x")
    bad = imgdir / "b.png"
    bad.write_bytes(b"y")
    cache = tmp_path / "cache" / "hashes.json"

    compute = CountingCompute(
        table={str(good): {"phash": 5, "dhash": 6}},
        raise_for=[str(bad)])

    # a fake stat carrying a stable mtime/size so the cache key is deterministic
    class FakeStat:
        def __init__(self, mt, sz):
            self.st_mtime = mt
            self.st_size = sz

    stat_table = {str(good): FakeStat(111.0, 10), str(bad): FakeStat(222.0, 20)}

    def statter(path):
        return stat_table[path]

    def walker(top):
        yield (str(imgdir), [], ["a.png", "b.png"])

    rows = campaign.build_corpus_hashes(
        [str(imgdir)], str(cache), compute=compute, walker=walker, statter=statter)
    # the unreadable file is omitted; only the good one is hashed
    paths = [r["path"] for r in rows]
    assert str(good) in paths
    assert str(bad) not in paths
    first_calls = len(compute.calls)
    assert first_calls >= 2  # both attempted on the cold run
    # atomic: no .tmp left behind
    leftovers = [p.name for p in (tmp_path / "cache").iterdir()
                 if p.suffix == ".tmp"]
    assert leftovers == []
    # second run: the successfully-hashed (unchanged) file is served from cache
    # and NOT re-hashed. The unreadable file was never cached, so it is legit to
    # retry it - assert the GOOD file specifically is not recomputed.
    good_calls_before = compute.calls.count(str(good))
    rows2 = campaign.build_corpus_hashes(
        [str(imgdir)], str(cache), compute=compute, walker=walker, statter=statter)
    assert compute.calls.count(str(good)) == good_calls_before  # cache hit, no recompute
    assert any(r["path"] == str(good) and r["phash"] == 5 for r in rows2)


# ===========================================================================
# 4. run_campaign - stops at Tier 0 on a local match (no network/fetch)
# ===========================================================================
def test_run_campaign_tier0_local_match(tmp_path):
    target = {"path": str(tmp_path / "007-pre.png"), "name": "007-pre.png",
              "slug": "007-pre"}
    corpus = [{"path": "src/007_src.jpg", "phash": 0b11, "dhash": 0b1}]
    compute = CountingCompute(table={target["path"]: {"phash": 0, "dhash": 0}})
    http = FakeHttp()
    fetch = RecordingFetch()
    annotate = RecordingAnnotate()
    matches = tmp_path / "matches.json"

    rep = campaign.run_campaign(
        [target], corpus, config={}, http=http, compute=compute,
        fetch=fetch, annotate=annotate, matches_path=str(matches))
    assert rep["summary"]["matched"] == 1
    assert http.calls == []           # no network on a Tier-0 stop
    assert fetch.calls == []          # no fetch on a Tier-0 stop
    assert annotate.calls and annotate.calls[0]["source_url"] == "src/007_src.jpg"
    assert matches.is_file()


# ===========================================================================
# 5. run_campaign - Tier 1: fetch the fullview + annotate the deviation URL
# ===========================================================================
def test_run_campaign_tier1_fetch_and_annotate(tmp_path):
    # name carries the live xayah token dm44iab -> 1337184659
    target = {"path": str(tmp_path / "xayah_by_pebano1_dm44iab-fullview.jpg"),
              "name": "xayah_by_pebano1_dm44iab-fullview.jpg",
              "slug": "xayah-by-pebano1-dm44iab-fullview"}
    compute = CountingCompute(table={target["path"]: {"phash": 0, "dhash": 0}})
    http = FakeHttp(responses={"oembed": (200, '{"title":"X","author_name":"Y"}')})
    fetch = RecordingFetch()
    annotate = RecordingAnnotate()
    sleep = _sleep_recorder()

    rep = campaign.run_campaign(
        [target], corpus=[], config={"deviantart": {"client-id": "x"}},
        http=http, compute=compute, fetch=fetch, annotate=annotate,
        sleep=sleep, fetch_dir=str(tmp_path / "fetched"),
        matches_path=str(tmp_path / "matches.json"))
    assert rep["summary"]["fetched"] == 1
    # fetch called with the DECODED deviation id and original=False (quota-free)
    assert fetch.calls[0]["deviation_id"] == 1337184659
    assert fetch.calls[0]["original"] is False
    # annotate called with the deviation URL as the source
    assert annotate.calls[0]["source_url"].endswith("deviation/1337184659")
    assert rep["summary"]["annotated"] == 1


# ===========================================================================
# 6. run_campaign - Tier 1 loose-file case: annotate returns no_manifest
# ===========================================================================
def test_run_campaign_tier1_annotate_skipped_loose_file(tmp_path):
    target = {"path": str(tmp_path / "xayah_by_pebano1_dm44iab-fullview.jpg"),
              "name": "xayah_by_pebano1_dm44iab-fullview.jpg",
              "slug": "xayah-by-pebano1-dm44iab-fullview"}
    compute = CountingCompute(table={target["path"]: {"phash": 0, "dhash": 0}})
    http = FakeHttp(responses={"oembed": (200, '{"title":"X"}')})
    fetch = RecordingFetch()
    annotate = RecordingAnnotate(result={"ok": False, "status": "no_manifest"})
    matches = tmp_path / "matches.json"

    rep = campaign.run_campaign(
        [target], corpus=[], config={"deviantart": {"client-id": "x"}},
        http=http, compute=compute, fetch=fetch, annotate=annotate,
        fetch_dir=str(tmp_path / "fetched"), matches_path=str(matches))
    assert rep["summary"]["annotate_skipped"] == 1
    # the loose file's source is STILL persisted to matches.json (provenance)
    data = json.loads(matches.read_text(encoding="ascii"))
    assert any(r["slug"] == target["slug"] and r["source"] for r in data)


# ===========================================================================
# 7. run_campaign - all tiers miss -> manual queue + both files written
# ===========================================================================
def test_run_campaign_all_tiers_miss_manual_queue(tmp_path):
    target = {"path": str(tmp_path / "1341679.jpeg"), "name": "1341679.jpeg",
              "slug": "1341679"}
    compute = CountingCompute(table={target["path"]: {"phash": 0, "dhash": 0}})
    http = FakeHttp(default=(200, "{}"))  # saucenao yields fail (no results)
    fetch = RecordingFetch()
    annotate = RecordingAnnotate()
    matches = tmp_path / "matches.json"
    manual = tmp_path / "manual_queue.csv"

    rep = campaign.run_campaign(
        [target], corpus=[], config={}, http=http, compute=compute,
        fetch=fetch, annotate=annotate,
        matches_path=str(matches), manual_queue_path=str(manual))
    assert rep["summary"]["manual_queued"] == 1
    assert matches.is_file()
    assert manual.is_file()
    with open(manual, newline="", encoding="ascii") as f:
        rows = list(csv.DictReader(f))
    assert rows and rows[0]["target"] == "1341679.jpeg"


# ===========================================================================
# 8. run_campaign - honors limit and throttles between network-tier targets
# ===========================================================================
def test_run_campaign_limit_and_throttle(tmp_path):
    # three token targets, but limit=2 -> only two processed, one sleep between.
    def mk(tok, dev):
        nm = f"art_by_a_{tok}-pre.jpg"
        return {"path": str(tmp_path / nm), "name": nm,
                "slug": campaign.derive_slug(nm), "_dev": dev}

    targets = [mk("dm44iab", 1337184659), mk("dlnxav6", 1309974594),
               mk("dl27k7h", 0)]
    compute = CountingCompute(table={t["path"]: {"phash": 0, "dhash": 0}
                                     for t in targets})
    http = FakeHttp(responses={"oembed": (200, '{"title":"X"}')})
    fetch = RecordingFetch()
    annotate = RecordingAnnotate()
    sleep = _sleep_recorder()

    rep = campaign.run_campaign(
        targets, corpus=[], config={"deviantart": {"client-id": "x"}},
        http=http, compute=compute, fetch=fetch, annotate=annotate,
        sleep=sleep, limit=2, fetch_dir=str(tmp_path / "f"),
        matches_path=str(tmp_path / "m.json"))
    assert rep["summary"]["total"] == 2          # limit honored
    assert len(rep["results"]) == 2
    # both hit the network tier -> at least one throttle sleep happened
    assert len(sleep.calls) >= 1


# ===========================================================================
# 9. run_campaign(dry_run=True) writes nothing and calls no real side effects
# ===========================================================================
def test_run_campaign_dry_run_no_side_effects(tmp_path):
    target = {"path": str(tmp_path / "xayah_by_pebano1_dm44iab-fullview.jpg"),
              "name": "xayah_by_pebano1_dm44iab-fullview.jpg",
              "slug": "xayah-by-pebano1-dm44iab-fullview"}
    compute = CountingCompute(table={target["path"]: {"phash": 0, "dhash": 0}})
    http = FakeHttp(responses={"oembed": (200, '{"title":"X"}')})
    fetch = RecordingFetch()
    annotate = RecordingAnnotate()
    matches = tmp_path / "matches.json"

    rep = campaign.run_campaign(
        [target], corpus=[], config={"deviantart": {"client-id": "x"}},
        http=http, compute=compute, fetch=fetch, annotate=annotate,
        matches_path=str(matches), fetch_dir=str(tmp_path / "f"), dry_run=True)
    assert not matches.exists()      # no file writes in dry-run
    assert fetch.calls == []         # real fetch never invoked
    # annotate not invoked for real (dry_run threads through / short-circuits)
    assert all(c["kw"].get("dry_run") for c in annotate.calls) or annotate.calls == []
    assert rep["summary"]["total"] == 1


# ===========================================================================
# 10. annotate_via_pipeline - maps returncode without a real subprocess
# ===========================================================================
def test_annotate_via_pipeline_maps_returncodes():
    class R:
        def __init__(self, rc):
            self.returncode = rc
            self.stdout = ""
            self.stderr = ""

    seen = {}

    def runner_ok(cmd, **kw):
        seen["cmd"] = cmd
        seen["kw"] = kw
        return R(0)

    ok = campaign.annotate_via_pipeline("slug-a", "http://src", runner=runner_ok)
    assert ok == {"ok": True, "status": "annotated"}
    # the shelled command targets the pipeline annotate verb with the source URL
    assert "annotate" in seen["cmd"] and "slug-a" in seen["cmd"]
    assert "--source-url" in seen["cmd"] and "http://src" in seen["cmd"]
    import subprocess as _sp
    assert seen["kw"].get("creationflags") == getattr(_sp, "CREATE_NO_WINDOW", 0)

    # returncode 2 (no manifest / not found) -> friendly no_manifest, never raises
    no_man = campaign.annotate_via_pipeline(
        "slug-b", "http://src", runner=lambda c, **k: R(2))
    assert no_man == {"ok": False, "status": "no_manifest"}

    # a missing python/tool degrades to a friendly error, never raises
    def boom(cmd, **kw):
        raise FileNotFoundError("python not found")
    err = campaign.annotate_via_pipeline("slug-c", "http://src", runner=boom)
    assert err["ok"] is False and err["status"] == "error"

    # dry_run never shells out
    dry = campaign.annotate_via_pipeline("slug-d", "http://src", dry_run=True,
                                         runner=lambda c, **k: R(99))
    assert dry == {"ok": True, "status": "dry_run"}


# ===========================================================================
# 11. module import safety (CI: stdlib + numpy only)
# ===========================================================================
def test_module_imports_without_heavy_deps():
    # If this file imported at the top, the module already imported clean on a
    # bare stdlib+numpy env (imagehash/PIL reachable only via injected compute).
    assert hasattr(campaign, "run_campaign")
    assert hasattr(campaign, "enumerate_targets")
    assert hasattr(campaign, "derive_slug")
