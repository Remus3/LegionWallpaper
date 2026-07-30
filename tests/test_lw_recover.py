"""Tests for tools/lw_recover.py - the source-recovery campaign waterfall.

Spec: docs/research/SOURCE_RECOVERY.md (token decode, Tier 0/1/2 mechanics,
SauceNAO thresholds, gallery-dl gating) and docs/RESTORATION_PLAN.md section
2.1 (the four-tier waterfall). Written test-first per CLAUDE.md TDD.

CI constraint (mirrors tools/lw_g1_gate.py + tools/lw_golden.py): this module
must import with ONLY stdlib + numpy available. imagehash/PIL are lazy-imported
inside functions; the Tier 0 hash tests therefore start with
pytest.importorskip("imagehash") and SKIP cleanly wherever it is absent (CI and
system python both lack it). Every network path is dependency-INJECTED (an http
getter callable), so NO test ever hits the network.
"""

import csv
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lw_recover  # noqa: E402


# ---------------------------------------------------------------------------
# fakes (no network, no heavy deps)
# ---------------------------------------------------------------------------
class FakeHttp:
    """A dependency-injected http getter recording calls and replaying canned
    responses. Signature matches the real getter: get(url) -> (status, text)."""

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


class BoomHttp:
    """An http getter that always raises - proves the friendly-degrade path
    (Error Handling rule: never surface a raw network error; skip the tier)."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, *, data=None, headers=None, timeout=None):
        self.calls.append(url)
        raise OSError("simulated connection reset by peer")


class RecordingHttp:
    """An http getter that records the full POST call - (url, data, headers) -
    so a test can assert the image bytes and multipart headers really go out."""

    def __init__(self, response=(200, "{}")):
        self.response = response
        self.url = None
        self.data = None
        self.headers = None

    def __call__(self, url, *, data=None, headers=None, timeout=None):
        self.url = url
        self.data = data
        self.headers = headers
        return self.response


# ===========================================================================
# Tier 1 - DeviantArt token decode  (the crown jewel; offline, deterministic)
# ===========================================================================
def test_decode_token_mustpass_vector_bare_token():
    # SOURCE_RECOVERY 2.2: strip leading "d" -> base36. The real dark-cosmic-ahri
    # deviation. This exact vector is the hard-requirement acceptance test.
    assert lw_recover.decode_deviation_token("dlnxav6") == 1309974594


def test_decode_token_mustpass_vector_pre_filename():
    assert lw_recover.decode_deviation_token(
        "dark_cosmic_ahri_by_someone_dlnxav6-pre.jpg") == 1309974594


def test_decode_token_documented_xayah_fullview():
    # SOURCE_RECOVERY 2.2 worked example (verified live in the research doc).
    assert lw_recover.decode_deviation_token(
        "xayah_by_pebano1_dm44iab-fullview.jpg") == 1337184659


def test_decode_token_raw_wixmp_uuid_shape():
    # <token>-<uuid>.jpg : token = text before the first "-".
    assert lw_recover.decode_deviation_token(
        "dl3e4dq-0ad4bcb2-42f6-48d5-b3ea-cb216eda20bd.jpg") == 1275487406


def test_decode_token_real_corpus_uuid_shape():
    # A real file from data/golden/inputs (dgk8f8n-<uuid>_firstinitial.jpg).
    assert lw_recover.decode_deviation_token(
        "dgk8f8n-398197d0-65d6-4299-8f0b-afdd9021c395.jpg") == int("gk8f8n", 36)


def test_decode_token_returns_none_on_no_token():
    # A non-DeviantArt name (e.g. a plain wallpaper-site rip) has no d-token.
    assert lw_recover.decode_deviation_token("1341679.jpeg") is None
    assert lw_recover.decode_deviation_token("just_a_title.png") is None


def test_deviation_url_shape():
    assert lw_recover.deviation_url(1309974594) == (
        "https://www.deviantart.com/deviation/1309974594")


# ---- oEmbed liveness (injected http, never real network) ------------------
def test_oembed_liveness_alive_returns_metadata():
    body = ('{"title": "Dark Cosmic Ahri", "author_name": "someone", '
            '"width": 3840, "height": 2160}')
    http = FakeHttp(responses={"oembed": (200, body)})
    res = lw_recover.oembed_liveness(1309974594, http=http)
    assert res["alive"] is True
    assert res["title"] == "Dark Cosmic Ahri"
    assert res["author_name"] == "someone"
    # the oEmbed endpoint must be queried with the deviation URL encoded in.
    assert any("oembed" in c for c in http.calls)


def test_oembed_liveness_dead_deviation_404():
    http = FakeHttp(default=(404, "not found"))
    res = lw_recover.oembed_liveness(999, http=http)
    assert res["alive"] is False


def test_oembed_liveness_network_error_is_friendly_not_raised():
    # Error Handling rule: a raw network error must never propagate.
    res = lw_recover.oembed_liveness(1, http=BoomHttp())
    assert res["alive"] is False
    assert "error" in res  # a friendly status string, not a traceback


# ---- artist parse + canonical oEmbed URL (2026 DeviantArt clampdown fix) ---
def test_parse_artist_from_by_token_names():
    assert lw_recover.parse_artist(
        "dark_cosmic_ahri_by_pebano1_dlnxav6-pre.jpg") == "pebano1"
    assert lw_recover.parse_artist(
        "aatrox_the_darkin_blade_by_vexxsoul_dm6j4xi-pre.jpg") == "vexxsoul"
    # a raw <token>-<uuid>.jpg CDN save carries no _by_<artist>_ segment.
    assert lw_recover.parse_artist(
        "dl3e4dq-0ad4bcb2-42f6-48d5-b3ea-cb216eda20bd.jpg") is None


def test_oembed_uses_canonical_artist_url_when_artist_given():
    # After the 2026 clampdown the backend 404s on /deviation/<id> and needs the
    # canonical /<artist>/art/<slug>-<id> form. With an artist, the query must
    # target that form (username present, no "deviation" redirect segment).
    http = FakeHttp(responses={"oembed":
                    (200, '{"title": "X", "author_name": "pebano1"}')})
    res = lw_recover.oembed_liveness(1309974594, http=http, artist="pebano1")
    assert res["alive"] is True
    assert any("pebano1" in c and "deviation" not in c for c in http.calls)
    # the provenance URL stays the resolvable /deviation/<id> form.
    assert res["deviation_url"] == (
        "https://www.deviantart.com/deviation/1309974594")


def test_oembed_without_artist_falls_back_to_legacy_deviation_form():
    # the deviation URL is percent-encoded into the oembed query, so the slash
    # reads as %2F - assert on the "deviation" segment + id, encoding-robust.
    http = FakeHttp(responses={"oembed": (200, '{"title": "X"}')})
    lw_recover.oembed_liveness(1309974594, http=http)
    assert any("deviation" in c and "1309974594" in c for c in http.calls)


# ---- regression: a DA username whose hyphens render as underscores ---------
# ROADMAP recover-parse-artist-underscore. DA exports render a hyphenated
# username with underscores, so "DaDa-WallpaperArt" arrives as
# "dada_wallpaperart" and cannot be un-rendered from the filename alone. The
# rule is: never guess a permutation, and never call the deviation dead on that
# evidence.
_VIEGO = "viego__the_ruined_king_by_dada_wallpaperart_dmhz060-pre"
_UUID_SHAPE = "di0tao3-964d7366-1b19-4d2e-9d1f-0b4c6a2f8e11.jpg"
_PLAIN = "xayah_by_pebano1_dm44iab-fullview.jpg"


def test_artist_segment_ambiguous_when_username_carries_an_underscore():
    seg = lw_recover.artist_segment(_VIEGO)
    assert seg["status"] == "ambiguous"
    assert seg["raw"] == "dada_wallpaperart"
    # no guessing: the recovered username stays None rather than a permutation.
    assert seg["artist"] is None
    assert lw_recover.parse_artist(_VIEGO) is None


def test_artist_segment_absent_on_token_uuid_shape():
    # a <token>-<uuid> CDN save has no _by_<artist>_ segment at all, so NO
    # canonical URL is buildable - the code must say that explicitly.
    seg = lw_recover.artist_segment(_UUID_SHAPE)
    assert seg["status"] == "absent"
    assert seg["raw"] is None
    assert seg["artist"] is None


def test_artist_segment_recovered_on_plain_single_word_username():
    # the well-formed case must keep working exactly as before.
    seg = lw_recover.artist_segment(_PLAIN)
    assert seg["status"] == "recovered"
    assert seg["raw"] == "pebano1"
    assert seg["artist"] == "pebano1"
    assert lw_recover.parse_artist(_PLAIN) == "pebano1"


def test_canonical_oembed_url_needs_an_artist():
    assert lw_recover.canonical_oembed_url(1309974594, None) is None
    assert lw_recover.canonical_oembed_url(1309974594, "pebano1") == (
        "https://www.deviantart.com/pebano1/art/x-1309974594")


def test_oembed_non200_with_artist_is_inconclusive_not_dead():
    # a non-200 oEmbed proves nothing: the artist segment may be a mangled
    # username, so the deviation is INCONCLUSIVE and Tier 1's fetch decides.
    http = FakeHttp(default=(404, "not found"))
    res = lw_recover.oembed_liveness(999, http=http, artist="pebano1")
    assert res["alive"] is False
    assert res["verdict"] == "inconclusive"
    assert res["verdict"] != "dead"


def test_oembed_non200_without_artist_reports_no_canonical_url():
    http = FakeHttp(default=(404, "not found"))
    res = lw_recover.oembed_liveness(999, http=http, artist=None)
    assert res["alive"] is False
    assert res["verdict"] == "no_canonical_url"
    assert "_by_" in res["reason"]  # explicit about WHY, not a bare failure


def test_oembed_non_json_is_inconclusive():
    http = FakeHttp(default=(200, "<html>nope</html>"))
    res = lw_recover.oembed_liveness(1, http=http, artist="pebano1")
    assert res["alive"] is False
    assert res["verdict"] == "inconclusive"


def test_oembed_transport_error_is_inconclusive():
    res = lw_recover.oembed_liveness(1, http=BoomHttp(), artist="pebano1")
    assert res["alive"] is False
    assert res["verdict"] == "inconclusive"


def test_oembed_alive_carries_the_alive_verdict():
    http = FakeHttp(responses={"oembed": (200, '{"title": "X"}')})
    res = lw_recover.oembed_liveness(1309974594, http=http, artist="pebano1")
    assert res["alive"] is True
    assert res["verdict"] == "alive"


# ---- gallery-dl subprocess wrapper (gated on config) ----------------------
def test_gallery_dl_fetch_not_configured_is_friendly():
    # No DeviantArt config -> friendly "not configured", never a crash.
    res = lw_recover.gallery_dl_fetch(1309974594, config={}, dest_dir="whatever")
    assert res["ok"] is False
    assert res["status"] == "not_configured"


def test_gallery_dl_fetch_uses_no_window_and_gated_runner(tmp_path):
    # When configured, it must shell out with CREATE_NO_WINDOW (no console flash
    # on Legion) and target the deviation URL. Inject the runner so no real
    # subprocess spawns.
    seen = {}

    def fake_runner(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    cfg = {"deviantart": {"client-id": "x", "client-secret": "y",
                          "refresh-token": "cache"}}
    res = lw_recover.gallery_dl_fetch(
        1309974594, config=cfg, dest_dir=str(tmp_path), runner=fake_runner)
    assert res["ok"] is True
    assert any("deviation/1309974594" in str(a) for a in seen["cmd"])
    # the CREATE_NO_WINDOW flag (0 on non-Windows) must be passed explicitly.
    import subprocess as _sp
    assert seen["kwargs"].get("creationflags") == getattr(
        _sp, "CREATE_NO_WINDOW", 0)


# ===========================================================================
# Tier 0 - LOCAL PAIR MATCH  (offline, free; imagehash lazy + skip-if-absent)
# ===========================================================================
def test_hamming_basic():
    assert lw_recover.hamming(0b0000, 0b0000) == 0
    assert lw_recover.hamming(0b1010, 0b0000) == 2
    assert lw_recover.hamming(0xFFFFFFFFFFFFFFFF, 0x0) == 64


def test_hamming_symmetric_and_self_zero():
    a, b = 0x1234ABCD, 0xFFFF0000
    assert lw_recover.hamming(a, b) == lw_recover.hamming(b, a)
    assert lw_recover.hamming(a, a) == 0


def test_consensus_match_accept_when_both_hashes_close():
    # phash + dhash BOTH within accept -> MATCH (SOURCE_RECOVERY 4).
    target = {"phash": 0x0, "dhash": 0x0}
    corpus = [
        {"path": "a.jpg", "phash": 0b111, "dhash": 0b1},       # both <= 8
        {"path": "b.jpg", "phash": 0xFFFF, "dhash": 0xFFFF},   # far
    ]
    res = lw_recover.consensus_match(target, corpus, accept=8, review=14)
    assert res["decision"] == "match"
    assert res["source"] == "a.jpg"
    assert res["evidence"]["phash_hamming"] <= 8
    assert res["evidence"]["dhash_hamming"] <= 8


def test_consensus_match_review_band():
    # In the review band (accept < d <= review) -> review, not an auto-match.
    target = {"phash": 0x0, "dhash": 0x0}
    # 11 bits differ in phash (0..8 accept, 9..14 review); dhash close.
    corpus = [{"path": "c.jpg", "phash": 0b11111111111, "dhash": 0b1}]
    res = lw_recover.consensus_match(target, corpus, accept=8, review=14)
    assert res["decision"] == "review"
    assert res["source"] == "c.jpg"


def test_consensus_match_no_match_when_only_one_hash_agrees():
    # phash close but dhash far -> NOT a match (consensus requires BOTH).
    target = {"phash": 0x0, "dhash": 0x0}
    corpus = [{"path": "d.jpg", "phash": 0b1, "dhash": 0xFFFFFFFFFFFFFFFF}]
    res = lw_recover.consensus_match(target, corpus, accept=8, review=14)
    assert res["decision"] == "no_match"
    assert res["source"] is None


def test_consensus_match_empty_corpus():
    res = lw_recover.consensus_match({"phash": 0, "dhash": 0}, [])
    assert res["decision"] == "no_match"
    assert res["source"] is None


def test_compute_hashes_needs_imagehash(tmp_path):
    pytest.importorskip("imagehash")  # skips in CI and on bare system python
    from PIL import Image
    p = tmp_path / "x.png"
    Image.new("RGB", (64, 64), (10, 20, 30)).save(p)
    h = lw_recover.compute_hashes(str(p))
    assert isinstance(h["phash"], int) and isinstance(h["dhash"], int)
    assert 0 <= h["phash"] < (1 << 64)
    assert 0 <= h["dhash"] < (1 << 64)


# ===========================================================================
# Tier 2 - SauceNAO  (gated on API key; injected http; friendly when absent)
# ===========================================================================
def test_saucenao_no_key_is_friendly_degraded():
    res = lw_recover.saucenao_search("img.png", api_key=None, http=FakeHttp())
    assert res["ok"] is False
    assert res["status"] == "no_key"


def test_saucenao_accept_threshold(tmp_path):
    img = tmp_path / "x.png"
    img.write_bytes(b"not-a-real-image-but-not-read-in-this-path")
    body = ('{"results": [{"header": {"similarity": "92.5"}, '
            '"data": {"ext_urls": ["https://www.deviantart.com/art/x-1"]}}]}')
    http = FakeHttp(responses={"saucenao": (200, body)})
    res = lw_recover.saucenao_search(
        str(img), api_key="KEY", http=http, reader=lambda p: b"bytes")
    assert res["ok"] is True
    assert res["decision"] == "accept"
    assert res["similarity"] == pytest.approx(92.5)


def test_saucenao_review_band(tmp_path):
    img = tmp_path / "x.png"
    body = ('{"results": [{"header": {"similarity": "70"}, '
            '"data": {"ext_urls": ["https://danbooru.donmai.us/post/1"]}}]}')
    http = FakeHttp(responses={"saucenao": (200, body)})
    res = lw_recover.saucenao_search(
        str(img), api_key="KEY", http=http, reader=lambda p: b"bytes")
    assert res["decision"] == "review"


def test_saucenao_fail_below_60(tmp_path):
    img = tmp_path / "x.png"
    body = '{"results": [{"header": {"similarity": "40"}, "data": {}}]}'
    http = FakeHttp(responses={"saucenao": (200, body)})
    res = lw_recover.saucenao_search(
        str(img), api_key="KEY", http=http, reader=lambda p: b"bytes")
    assert res["decision"] == "fail"


def test_saucenao_network_error_is_friendly(tmp_path):
    img = tmp_path / "x.png"
    res = lw_recover.saucenao_search(
        str(img), api_key="KEY", http=BoomHttp(), reader=lambda p: b"bytes")
    assert res["ok"] is False
    assert res["status"] == "error"  # degraded, tier skipped, not crashed


def test_build_multipart_content_type_and_body():
    # RFC-2388 single-part form-data with a FIXED ASCII boundary (deterministic
    # for tests - no random / time). The body must carry the boundary, the
    # filename, and the raw file bytes verbatim.
    body, ctype = lw_recover._build_multipart(
        "file", "x.png", b"RAWIMAGEBYTES", content_type="image/png")
    assert ctype.startswith("multipart/form-data; boundary=")
    assert isinstance(body, bytes)
    boundary = ctype.split("boundary=", 1)[1].encode("ascii")
    assert boundary in body
    assert b"x.png" in body
    assert b"RAWIMAGEBYTES" in body


def test_saucenao_posts_image_as_multipart(tmp_path):
    # The image bytes MUST be POSTed as a multipart body; the SauceNAO params
    # (output_type / db) stay in the query string per the real API + wrapper.
    img = tmp_path / "x.png"
    http = RecordingHttp(response=(
        200,
        '{"results": [{"header": {"similarity": "92"}, '
        '"data": {"ext_urls": ["https://www.deviantart.com/art/x-1"]}}]}'))
    res = lw_recover.saucenao_search(
        str(img), api_key="KEY", http=http, reader=lambda p: b"IMGBYTES")
    # query string carries the SauceNAO params
    assert "saucenao" in http.url
    assert "output_type=2" in http.url
    assert "db=999" in http.url
    # the file goes out as a multipart POST body with the real image bytes
    assert http.headers["Content-Type"].startswith("multipart/form-data")
    assert isinstance(http.data, bytes)
    assert b"IMGBYTES" in http.data
    # and the canned similarity 92 drives an accept decision
    assert res["ok"] is True
    assert res["decision"] == "accept"


def test_saucenao_reports_quota_remaining(tmp_path):
    # The client must surface short_remaining / long_remaining from each
    # response header so the caller can self-throttle from live data.
    img = tmp_path / "x.png"
    body = ('{"header": {"short_remaining": 3, "long_remaining": 97}, '
            '"results": [{"header": {"similarity": "92"}, '
            '"data": {"ext_urls": ["https://www.deviantart.com/art/x-1"]}}]}')
    http = FakeHttp(responses={"saucenao": (200, body)})
    res = lw_recover.saucenao_search(
        str(img), api_key="KEY", http=http, reader=lambda p: b"bytes")
    assert res["short_remaining"] == 3
    assert res["long_remaining"] == 97


# ===========================================================================
# Tier 3 - MANUAL QUEUE  (atomic CSV append)
# ===========================================================================
def test_append_manual_queue_creates_and_appends(tmp_path):
    csv_path = tmp_path / "recovery" / "manual_queue.csv"
    lw_recover.append_manual_queue(
        {"target": "007.png", "reason": "no local source",
         "suggested_tools": "google-lens; yandex"}, str(csv_path))
    lw_recover.append_manual_queue(
        {"target": "008.png", "reason": "dead deviation",
         "suggested_tools": "google-lens"}, str(csv_path))
    assert csv_path.is_file()
    with open(csv_path, newline="", encoding="ascii") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["target"] == "007.png"
    assert rows[1]["reason"] == "dead deviation"


def test_append_manual_queue_is_atomic_no_tmp_left(tmp_path):
    csv_path = tmp_path / "manual_queue.csv"
    lw_recover.append_manual_queue({"target": "1.png", "reason": "x",
                                    "suggested_tools": "y"}, str(csv_path))
    leftovers = [p.name for p in tmp_path.iterdir() if p.suffix in (".tmp", ".part")]
    assert leftovers == []


# ===========================================================================
# load_api_key  (never crashes)
# ===========================================================================
def test_load_api_key_absent_returns_none(tmp_path):
    assert lw_recover.load_api_key("Nonexistent", root=str(tmp_path)) is None


def test_load_api_key_reads_and_strips(tmp_path):
    (tmp_path / "API-Key-SauceNAO.txt").write_text("  abc123\n", encoding="ascii")
    assert lw_recover.load_api_key("SauceNAO", root=str(tmp_path)) == "abc123"


# ===========================================================================
# run_waterfall  (the driver: stop at first success, log every decision)
# ===========================================================================
def test_waterfall_stops_at_tier0_on_local_match():
    target = {"phash": 0x0, "dhash": 0x0, "name": "007.png"}
    corpus = [{"path": "src/007_src.jpg", "phash": 0b11, "dhash": 0b1}]
    rep = lw_recover.run_waterfall(target, corpus, config={})
    assert rep["tier"] == 0
    assert rep["source"] == "src/007_src.jpg"
    assert rep["decisions"][0]["tier"] == 0
    assert rep["decisions"][0]["decision"] == "match"


def test_waterfall_falls_to_tier1_token_decode_when_no_local_match():
    # No corpus match; the target filename carries a live d-token.
    target = {"phash": 0x0, "dhash": 0x0,
              "name": "xayah_by_pebano1_dm44iab-fullview.jpg"}
    body = '{"title": "Xayah", "author_name": "PeBaNO1"}'
    http = FakeHttp(responses={"oembed": (200, body)})
    rep = lw_recover.run_waterfall(target, corpus=[], config={}, http=http)
    assert rep["tier"] == 1
    assert "deviation/1337184659" in rep["source"]
    tiers_tried = [d["tier"] for d in rep["decisions"]]
    assert 0 in tiers_tried and 1 in tiers_tried


def test_waterfall_reaches_manual_queue_when_all_tiers_miss(tmp_path):
    # No local match, no token, no SauceNAO key -> Tier 3 manual queue.
    target = {"phash": 0x0, "dhash": 0x0, "name": "1341679.jpeg"}
    csv_path = tmp_path / "manual_queue.csv"
    rep = lw_recover.run_waterfall(
        target, corpus=[], config={}, manual_queue_path=str(csv_path))
    assert rep["tier"] == 3
    assert rep["source"] is None
    assert csv_path.is_file()
    # every tier that was attempted must be logged.
    tiers = [d["tier"] for d in rep["decisions"]]
    assert tiers == sorted(tiers)  # decisions logged in waterfall order
    assert 3 in tiers


def test_waterfall_inconclusive_oembed_does_not_demote_to_tier2(tmp_path):
    # ROADMAP recover-parse-artist-underscore. A non-200 oEmbed is NOT proof the
    # deviation is dead, so the waterfall must hold the target at Tier 1 (whose
    # fetch decides) instead of burning SauceNAO quota on false evidence.
    target = {"phash": 0x0, "dhash": 0x0,
              "name": "gone_by_artist_dm44iab-fullview.jpg"}
    http = FakeHttp(default=(404, "gone"))
    csv_path = tmp_path / "manual_queue.csv"
    rep = lw_recover.run_waterfall(
        target, corpus=[], config={}, http=http,
        manual_queue_path=str(csv_path))
    assert rep["tier"] == 1
    assert "deviation/1337184659" in rep["source"]
    t1 = [d for d in rep["decisions"] if d["tier"] == 1][0]
    assert t1["decision"] == "inconclusive"
    # no tier below 1 was attempted: no SauceNAO call, no manual-queue row.
    assert not any("saucenao" in c for c in http.calls)
    assert not csv_path.exists()
    assert not any(d["decision"] == "dead" for d in rep["decisions"])


def test_waterfall_hyphenated_username_is_not_reported_dead(tmp_path):
    # shape (a): the real file whose username "DaDa-WallpaperArt" renders as
    # "dada_wallpaperart" - no canonical URL is buildable, so oEmbed 404s and
    # the old code called it dead. It must now hold at Tier 1.
    target = {"phash": 0x0, "dhash": 0x0, "name": _VIEGO + ".jpg"}
    http = FakeHttp(default=(404, "not found"))
    csv_path = tmp_path / "manual_queue.csv"
    rep = lw_recover.run_waterfall(
        target, corpus=[], config={}, http=http,
        manual_queue_path=str(csv_path))
    assert rep["tier"] == 1
    t1 = [d for d in rep["decisions"] if d["tier"] == 1][0]
    assert t1["decision"] == "no_canonical_url"
    assert t1["evidence"]["artist_segment"] == "ambiguous"
    assert not csv_path.exists()


def test_waterfall_token_uuid_shape_is_not_reported_dead(tmp_path):
    # shape (b): <token>-<uuid> with no _by_<artist>_ segment at all.
    target = {"phash": 0x0, "dhash": 0x0, "name": _UUID_SHAPE}
    http = FakeHttp(default=(404, "not found"))
    csv_path = tmp_path / "manual_queue.csv"
    rep = lw_recover.run_waterfall(
        target, corpus=[], config={}, http=http,
        manual_queue_path=str(csv_path))
    assert rep["tier"] == 1
    t1 = [d for d in rep["decisions"] if d["tier"] == 1][0]
    assert t1["decision"] == "no_canonical_url"
    assert t1["evidence"]["artist_segment"] == "absent"
    assert not csv_path.exists()


def test_waterfall_no_token_still_reaches_the_manual_queue(tmp_path):
    # the INCONCLUSIVE hold is scoped to a decoded token - a name with no token
    # at all must still fall all the way through to Tier 3.
    target = {"phash": 0x0, "dhash": 0x0, "name": "1341679.jpeg"}
    csv_path = tmp_path / "manual_queue.csv"
    rep = lw_recover.run_waterfall(
        target, corpus=[], config={}, http=FakeHttp(default=(404, "x")),
        manual_queue_path=str(csv_path))
    assert rep["tier"] == 3
    assert csv_path.is_file()


# ===========================================================================
# module import safety  (CI: stdlib + numpy only)
# ===========================================================================
def test_module_imports_without_heavy_deps():
    # If this test file imported at the top, the module already imported clean.
    assert hasattr(lw_recover, "decode_deviation_token")
    assert hasattr(lw_recover, "run_waterfall")
