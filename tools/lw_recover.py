"""lw_recover.py - source-recovery campaign waterfall for Legion Wallpaper.

Spec: docs/research/SOURCE_RECOVERY.md (the complete recovery spec: token
decode, Tier 0/1/2 mechanics, SauceNAO + gallery-dl gating, filename shapes)
and docs/RESTORATION_PLAN.md section 2.1 (the four-tier waterfall) + section 8
(DeviantArt download-quota urgency).

The waterfall (stop at the FIRST tier that succeeds; every decision logged):

  Tier 0  LOCAL PAIR MATCH   offline, free, deterministic - pHash + dHash
                             consensus over a candidate corpus. Usable NOW.
  Tier 1  DEVIANTART TOKEN   offline decode of the filename token -> deviation
                             id -> URL; a public oEmbed liveness check; a
                             gallery-dl subprocess fetch GATED on config.
  Tier 2  SAUCENAO           reverse image search GATED on API-Key-SauceNAO.txt.
  Tier 3  MANUAL QUEUE       leftovers appended to data/recovery/manual_queue.csv.

CI-safe style (copied from tools/lw_g1_gate.py + tools/lw_golden.py): ONLY the
standard library is imported at module top level. imagehash + PIL are
lazy-imported inside compute_hashes; every network call is dependency-INJECTED
(an http getter callable) so the module imports cleanly on a bare Python
3.12/3.14 and NO unit test ever touches the network. gallery-dl is a subprocess
wrapper (runner injectable) that always passes CREATE_NO_WINDOW so a headless
run never flashes a console on the Legion box.

Error Handling rule (CLAUDE.md): a tier NEVER surfaces a raw API/network error
string and NEVER crashes the waterfall - it catches, returns a friendly
degraded status, and the driver treats that tier as "skipped" and falls
through to the next. Atomic writes only (tmp then os.replace).

7-bit ASCII only in this file (repo hard rule): no em/en dashes, no smart
quotes; " - " for clause breaks.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

# CREATE_NO_WINDOW: suppress the console flash when we shell out to gallery-dl
# under a windowless parent on Windows (0 on other platforms - a harmless flag).
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# The DeviantArt filename token: an optional leading _ or start-of-string, a "d"
# then 6-8 base36 chars, immediately followed by "-" (the -pre / -fullview /
# -<uuid> boundary). Covers all three corpus shapes documented in
# SOURCE_RECOVERY section 0 / 2.2.
_TOKEN_RE = re.compile(r"(?:^|_)(d[0-9a-z]{6,8})-")

# The DeviantArt artist username in a "*_by_<artist>_<token>-*" filename. DA
# usernames are letters/digits/hyphens (no underscores), so the segment between
# "_by_" and the "_<token>-" boundary is the username. Used to rebuild the
# canonical /<artist>/art/<slug>-<id> oEmbed URL (see oembed_liveness).
_ARTIST_RE = re.compile(r"_by_([a-z0-9][a-z0-9-]*)_d[0-9a-z]{6,8}-", re.IGNORECASE)

# Public oEmbed + deviation endpoints (SOURCE_RECOVERY 2.2). oEmbed is a
# metadata / liveness source over public http, NOT the download path.
_DEVIATION_URL = "https://www.deviantart.com/deviation/{id}"
_OEMBED_URL = "https://backend.deviantart.com/oembed?url={url}"
_SAUCENAO_URL = "https://saucenao.com/search.php"

# SauceNAO similarity thresholds (SOURCE_RECOVERY 1.1, community convention).
_SAUCENAO_ACCEPT = 85.0
_SAUCENAO_REVIEW = 60.0


# ===========================================================================
# default http getter (only used when a caller does NOT inject one; unit tests
# always inject, so this real path is never exercised in CI)
# ===========================================================================
def _default_http(url: str, *, data: Optional[bytes] = None,
                  headers: Optional[Dict[str, str]] = None,
                  timeout: float = 15.0):
    """Minimal stdlib HTTP returning (status, text). Real network path only.

    GET when data is None, POST when data is bytes (urllib flips the method
    automatically the moment a Request carries data). Keeps the standing
    User-Agent and merges in any injected headers (e.g. a multipart
    Content-Type). Wrapped by every caller in try/except so a transport error
    degrades to a friendly status rather than propagating (Error Handling rule).
    """
    merged = {"User-Agent": "lw_recover/1.0"}
    if headers:
        merged.update(headers)
    req = urllib.request.Request(url, data=data, headers=merged)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.status, resp.read().decode("utf-8", errors="replace")


# ===========================================================================
# config / keys  (never crash)
# ===========================================================================
def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_api_key(name: str, root: Optional[str] = None) -> Optional[str]:
    """Read API-Key-<name>.txt from the repo root, stripped, or None if absent.

    NEVER raises - a missing or unreadable key file simply yields None, which
    gates the corresponding tier into its friendly "not configured" branch.
    """
    base = root or _repo_root()
    path = os.path.join(base, f"API-Key-{name}.txt")
    try:
        with open(path, encoding="ascii", errors="replace") as f:
            val = f.read().strip()
        return val or None
    except OSError:
        return None


# ===========================================================================
# Tier 0 - LOCAL PAIR MATCH  (offline, free, deterministic)
# ===========================================================================
def compute_hashes(path: str) -> Dict[str, int]:
    """Return {'phash': int, 'dhash': int} - 64-bit pHash + dHash of an image.

    imagehash + PIL are LAZY-imported here so the module stays importable on a
    bare stdlib+numpy environment (CI). imagehash returns an ImageHash whose
    .hash is a boolean numpy array; pack it big-endian into a 64-bit int so the
    values are plain ints (JSON-serialisable, hashable, cheap to Hamming).
    """
    import imagehash  # lazy: absent in CI / bare system python
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGB")
        ph = imagehash.phash(im, hash_size=8)
        dh = imagehash.dhash(im, hash_size=8)
    return {"phash": _pack_hash(ph), "dhash": _pack_hash(dh)}


def _pack_hash(image_hash) -> int:
    """Pack an imagehash.ImageHash (8x8 bool array) into a 64-bit int."""
    bits = image_hash.hash.flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bool(bit))
    return value


def hamming(a: int, b: int) -> int:
    """Hamming distance between two integer hashes (popcount of the XOR)."""
    return int(a ^ b).bit_count()


def consensus_match(
    target: Dict[str, int],
    corpus: List[Dict[str, Any]],
    accept: int = 8,
    review: int = 14,
) -> Dict[str, Any]:
    """Consensus pHash+dHash match of one target against a candidate corpus.

    SOURCE_RECOVERY section 4: BOTH pHash and dHash Hamming <= accept => match;
    <= review (with both agreeing) => review; otherwise no match. Consensus is
    the point - a single hash agreeing is NOT enough (guards false pairs from
    the upscale + unsharp + inpaint transform chain).

    Each corpus entry is {'path': str, 'phash': int, 'dhash': int}. Returns
    {'decision': 'match'|'review'|'no_match', 'source': path-or-None,
     'evidence': {phash_hamming, dhash_hamming} for the best candidate}. The
    best candidate is the one minimising max(phash_hamming, dhash_hamming) - the
    consensus (both-must-agree) distance.
    """
    best = None
    best_worst = None
    for cand in corpus:
        ph = hamming(target["phash"], cand["phash"])
        dh = hamming(target["dhash"], cand["dhash"])
        worst = max(ph, dh)  # consensus distance: both must be within a bound
        if best_worst is None or worst < best_worst:
            best_worst = worst
            best = {"path": cand["path"], "phash_hamming": ph, "dhash_hamming": dh}

    if best is None:
        return {"decision": "no_match", "source": None, "evidence": {}}

    evidence = {"phash_hamming": best["phash_hamming"],
                "dhash_hamming": best["dhash_hamming"]}
    if best_worst <= accept:
        decision = "match"
    elif best_worst <= review:
        decision = "review"
    else:
        return {"decision": "no_match", "source": None, "evidence": evidence}
    return {"decision": decision, "source": best["path"], "evidence": evidence}


# ===========================================================================
# Tier 1 - DEVIANTART TOKEN DECODE
# ===========================================================================
def decode_deviation_token(name: str) -> Optional[int]:
    """Decode the DeviantArt deviation id from a filename token (or bare token).

    SOURCE_RECOVERY 2.2: the token is "d" + base36 of the deviation id. Handles
    all three documented shapes plus a bare token:
      - <title>_by_<artist>_<token>-pre.jpg
      - <title>_by_<artist>_<token>-fullview.jpg
      - <token>-<uuid>.jpg
      - "dlnxav6" (bare token)
    Strip the leading "d", base36-decode -> integer id. Returns None when no
    token is present (e.g. a plain wallpaper-site rip like "1341679.jpeg").
    """
    m = _TOKEN_RE.search(name)
    token = None
    if m:
        token = m.group(1)
    elif re.fullmatch(r"d[0-9a-z]{6,8}", name):
        token = name  # a bare token with no suffix
    if not token:
        return None
    try:
        return int(token[1:], 36)  # drop the leading "d", base36 decode
    except ValueError:
        return None


def deviation_url(deviation_id: int) -> str:
    """https://www.deviantart.com/deviation/<id> (redirects to the artwork)."""
    return _DEVIATION_URL.format(id=deviation_id)


def parse_artist(name: str) -> Optional[str]:
    """Extract the DeviantArt artist username from a *_by_<artist>_<token>-* name.

    Returns the lowercased username, or None when the name has no "_by_<artist>_"
    segment (e.g. a raw <token>-<uuid>.jpg CDN save). The username lets
    oembed_liveness rebuild the canonical /<artist>/art/<slug>-<id> URL that the
    public oEmbed endpoint now requires - the /deviation/<id> redirect form 404s
    after the 2026 DeviantArt clampdown.
    """
    m = _ARTIST_RE.search(name)
    return m.group(1).lower() if m else None


def oembed_liveness(
    deviation_id: int,
    http: Optional[Callable] = None,
    artist: Optional[str] = None,
) -> Dict[str, Any]:
    """Public-oEmbed liveness + metadata check for a deviation (no API key).

    SOURCE_RECOVERY 2.2: the public oEmbed endpoint returns title / author /
    dimensions for a live deviation. Used as a cheap "does this still exist /
    who made it" probe BEFORE spending a gallery-dl fetch. The http getter is
    injected (get(url) -> (status, text)); unit tests pass a fake so no real
    request is made. A dead deviation (non-200) or any transport error returns
    {'alive': False, ...} - never raises, never leaks a raw error string.
    """
    getter = http or _default_http
    dev_url = deviation_url(deviation_id)  # /deviation/<id> - resolvable provenance
    # DeviantArt's public oEmbed now 404s on the /deviation/<id> redirect form
    # (2026 clampdown) but resolves the canonical /<artist>/art/<slug>-<id> URL
    # (the title slug is ignored - it keys on artist + id). Build the canonical
    # form when the artist is known; without one, fall back to the legacy form
    # (which reads dead, so the waterfall falls through to SauceNAO).
    if artist:
        query_target = f"https://www.deviantart.com/{artist}/art/x-{deviation_id}"
    else:
        query_target = dev_url
    url = _OEMBED_URL.format(url=urllib.parse.quote(query_target, safe=""))
    try:
        status, text = getter(url, timeout=15.0)
    except Exception as exc:  # noqa: BLE001 - degrade, never surface raw error
        return {"alive": False, "error": f"oembed request failed ({type(exc).__name__})"}

    if status != 200:
        return {"alive": False, "status_code": status}
    try:
        meta = json.loads(text)
    except (ValueError, TypeError):
        return {"alive": False, "error": "oembed returned non-JSON"}
    return {
        "alive": True,
        "title": meta.get("title"),
        "author_name": meta.get("author_name"),
        "width": meta.get("width"),
        "height": meta.get("height"),
        "deviation_url": dev_url,
    }


def gallery_dl_fetch(
    deviation_id: int,
    config: Dict[str, Any],
    dest_dir: str,
    runner: Optional[Callable] = None,
    original: bool = False,
) -> Dict[str, Any]:
    """Fetch a deviation with gallery-dl (subprocess) - GATED on DeviantArt config.

    SOURCE_RECOVERY 2.1 + RESTORATION_PLAN section 8: gallery-dl with OAuth is
    the download path; quality=100 / intermediary=true fetches do NOT consume
    the weekly download quota, so `original` defaults to False (flip only for
    the shortlist that truly needs the artist's uploaded file).

    Gating: without a DeviantArt config block (client-id / secret / refresh
    token) this returns a friendly {'ok': False, 'status': 'not_configured'} -
    it never shells out and never crashes. The subprocess ALWAYS passes
    creationflags=CREATE_NO_WINDOW (no console flash on Legion). `runner` is
    injectable so unit tests never spawn a real process; if gallery-dl itself
    is missing the FileNotFoundError degrades to a friendly status.
    """
    da_cfg = config.get("deviantart") if isinstance(config, dict) else None
    if not da_cfg or not da_cfg.get("client-id"):
        return {"ok": False, "status": "not_configured",
                "message": "DeviantArt not configured - drop client-id / "
                           "client-secret / refresh-token to enable Tier 1 fetch"}

    run = runner or subprocess.run
    url = deviation_url(deviation_id)
    cmd = ["gallery-dl", "--dest", dest_dir]
    if original:
        cmd += ["-o", "original=true"]
    cmd.append(url)
    try:
        proc = run(
            cmd,
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW,
        )
    except FileNotFoundError:
        return {"ok": False, "status": "gallery_dl_missing",
                "message": "gallery-dl not installed - pip install gallery-dl"}
    except Exception as exc:  # noqa: BLE001 - degrade, never surface raw error
        return {"ok": False, "status": "error",
                "message": f"gallery-dl invocation failed ({type(exc).__name__})"}

    if getattr(proc, "returncode", 1) == 0:
        return {"ok": True, "status": "fetched", "dest_dir": dest_dir, "url": url}
    return {"ok": False, "status": "fetch_failed",
            "message": "gallery-dl returned a non-zero exit - see logs",
            "returncode": getattr(proc, "returncode", None)}


# ===========================================================================
# Tier 2 - SAUCENAO  (gated on API-Key-SauceNAO.txt; injected http)
# ===========================================================================
# A FIXED ASCII multipart boundary - deterministic on purpose so tests can
# assert on the body byte-for-byte (no random / time). It is vanishingly
# unlikely to collide with real image bytes; the RFC only requires it not
# appear in the content, which holds for the file parts we send.
_MULTIPART_BOUNDARY = "lwRecoverBoundaryVC2Fd41Ac9E7b0000"


def _build_multipart(
    file_field: str,
    filename: str,
    file_bytes: bytes,
    content_type: str = "application/octet-stream",
) -> tuple:
    """Build a single-part RFC-2388 multipart/form-data body for a file upload.

    Returns (body_bytes, content_type_header) where content_type_header is
    "multipart/form-data; boundary=<fixed>". The boundary is a FIXED ASCII
    constant (deterministic - no random / time) so unit tests can assert on the
    exact bytes. CRLF line endings per the RFC.
    """
    boundary = _MULTIPART_BOUNDARY
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("ascii")
    tail = f"\r\n--{boundary}--\r\n".encode("ascii")
    body = head + file_bytes + tail
    return body, f"multipart/form-data; boundary={boundary}"


def saucenao_search(
    image_path: str,
    api_key: Optional[str],
    http: Optional[Callable] = None,
    reader: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Reverse image search via the SauceNAO API - GATED on an API key.

    SOURCE_RECOVERY 1.1: free key ~4/30s, ~100/day - a QUEUE not a loop; the
    caller is responsible for throttling. Thresholds: similarity >= 85 accept,
    60-85 review, < 60 fail. Without a key returns a friendly
    {'ok': False, 'status': 'no_key'} - the tier is skipped, never crashed.

    The image is POSTed as a multipart/form-data "file" part; the SauceNAO
    params (output_type / api_key / db / numres) ride in the query string. On a
    successful parse the returned dict also carries short_remaining /
    long_remaining (default None) from payload["header"] so the caller can
    self-throttle from live quota data, not hardcoded constants.

    http and reader are injected for tests (http(url, data=, headers=,
    timeout=) -> (status, text); reader reads the image bytes). Any transport /
    parse error degrades to {'ok': False, 'status': 'error'} with a friendly
    message - a raw API error string is never surfaced (Error Handling rule).
    """
    if not api_key:
        return {"ok": False, "status": "no_key",
                "message": "SauceNAO not configured - add API-Key-SauceNAO.txt "
                           "to enable Tier 2 reverse image search"}

    getter = http or _default_http
    read = reader or _read_bytes
    # The real API keeps the query params (output_type / api_key / db / numres)
    # in the URL and POSTs the image as a multipart/form-data "file" part - this
    # matches the saucenao_api wrapper convention. Read the bytes first so a
    # missing file degrades to a friendly status before any network attempt.
    try:
        file_bytes = read(image_path)
    except OSError as exc:
        return {"ok": False, "status": "error",
                "message": f"could not read image ({type(exc).__name__})"}

    params = urllib.parse.urlencode(
        {"output_type": "2", "api_key": api_key, "db": "999", "numres": "16"})
    url = f"{_SAUCENAO_URL}?{params}"
    filename = os.path.basename(image_path) or "upload"
    body, ctype = _build_multipart("file", filename, file_bytes)
    try:
        status, text = getter(
            url, data=body, headers={"Content-Type": ctype}, timeout=30.0)
    except Exception as exc:  # noqa: BLE001 - degrade, never surface raw error
        return {"ok": False, "status": "error",
                "message": f"saucenao request failed ({type(exc).__name__})"}

    if status != 200:
        return {"ok": False, "status": "error", "status_code": status,
                "message": "saucenao returned a non-200 status"}
    try:
        payload = json.loads(text)
    except (ValueError, TypeError):
        return {"ok": False, "status": "error",
                "message": "saucenao returned non-JSON"}

    # Live quota fields from the response header - the caller self-throttles
    # from these, not from hardcoded constants (SOURCE_RECOVERY 1.1). Default
    # None when absent so a missing field never breaks the caller.
    header = payload.get("header") or {}
    short_remaining = header.get("short_remaining")
    long_remaining = header.get("long_remaining")

    results = payload.get("results") or []
    if not results:
        return {"ok": True, "decision": "fail", "similarity": None,
                "source": None, "results": [],
                "short_remaining": short_remaining,
                "long_remaining": long_remaining}

    top = results[0]
    try:
        similarity = float(top.get("header", {}).get("similarity"))
    except (TypeError, ValueError):
        similarity = 0.0
    ext_urls = top.get("data", {}).get("ext_urls") or []
    source = ext_urls[0] if ext_urls else None

    if similarity >= _SAUCENAO_ACCEPT:
        decision = "accept"
    elif similarity >= _SAUCENAO_REVIEW:
        decision = "review"
    else:
        decision = "fail"
    return {"ok": True, "decision": decision, "similarity": similarity,
            "source": source, "results": results,
            "short_remaining": short_remaining,
            "long_remaining": long_remaining}


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


# ===========================================================================
# Tier 3 - MANUAL QUEUE  (atomic CSV append)
# ===========================================================================
_MANUAL_FIELDS = ("target", "reason", "suggested_tools")


def append_manual_queue(row: Dict[str, Any], csv_path: str) -> str:
    """Append one row to the manual-recovery queue CSV (atomic write).

    Reads the existing rows, appends the new one, and rewrites the whole file
    via tmp-then-os.replace so a mid-write reader never sees a torn file (CLAUDE
    atomic-write rule). Creates the parent directory and a header on first use.
    Only the _MANUAL_FIELDS columns are persisted (extra keys ignored, missing
    keys blank). Returns the csv_path.
    """
    import csv

    path = os.path.abspath(csv_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    existing: List[Dict[str, str]] = []
    if os.path.isfile(path):
        with open(path, newline="", encoding="ascii", errors="replace") as f:
            existing = list(csv.DictReader(f))

    existing.append({k: str(row.get(k, "")) for k in _MANUAL_FIELDS})

    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="ascii") as f:
        writer = csv.DictWriter(f, fieldnames=list(_MANUAL_FIELDS))
        writer.writeheader()
        for r in existing:
            writer.writerow({k: r.get(k, "") for k in _MANUAL_FIELDS})
    os.replace(tmp, path)
    return path


def _default_manual_queue_path() -> str:
    return os.path.join(_repo_root(), "data", "recovery", "manual_queue.csv")


# ===========================================================================
# Driver - run_waterfall (stop at first success; log every tier decision)
# ===========================================================================
def run_waterfall(
    target: Dict[str, Any],
    corpus: List[Dict[str, Any]],
    config: Dict[str, Any],
    http: Optional[Callable] = None,
    manual_queue_path: Optional[str] = None,
    accept: int = 8,
    review: int = 14,
) -> Dict[str, Any]:
    """Run the recovery waterfall for one target; stop at the first tier that
    succeeds. Every tier attempt is appended to decisions[] so the audit stage
    can replay the reasoning.

    target: {'phash': int, 'dhash': int, 'name': filename}. Returns
    {'tier': int, 'source': str-or-None, 'evidence': {...}, 'decisions': [...]}.

    Tier success rules:
      0  a consensus local pHash+dHash match (decision 'match').
      1  the filename token decodes AND oEmbed reports the deviation alive.
      2  SauceNAO returns an 'accept'-band hit (requires a configured key).
      3  always "succeeds" by parking the target in the manual queue.
    A 'review'-band result does not stop the waterfall - it is logged and the
    driver falls through, because review means "not confident enough to auto
    accept". Any degraded tier (not configured / network error) is logged and
    skipped.
    """
    decisions: List[Dict[str, Any]] = []

    # --- Tier 0: local pair match -----------------------------------------
    t0 = consensus_match(target, corpus, accept=accept, review=review)
    decisions.append({"tier": 0, "decision": t0["decision"],
                      "source": t0["source"], "evidence": t0.get("evidence", {})})
    if t0["decision"] == "match":
        return {"tier": 0, "source": t0["source"],
                "evidence": t0.get("evidence", {}), "decisions": decisions}

    # --- Tier 1: DeviantArt token decode + oEmbed liveness ----------------
    name = target.get("name", "")
    deviation_id = decode_deviation_token(name)
    if deviation_id is not None:
        live = oembed_liveness(deviation_id, http=http, artist=parse_artist(name))
        decisions.append({"tier": 1, "decision": "alive" if live.get("alive")
                          else "dead", "deviation_id": deviation_id,
                          "source": deviation_url(deviation_id), "evidence": live})
        if live.get("alive"):
            return {"tier": 1, "source": deviation_url(deviation_id),
                    "evidence": live, "decisions": decisions}
    else:
        decisions.append({"tier": 1, "decision": "no_token", "source": None,
                          "evidence": {}})

    # --- Tier 2: SauceNAO (gated on key) ----------------------------------
    api_key = load_api_key("SauceNAO")
    image_path = target.get("path") or target.get("name")
    sauce = saucenao_search(image_path, api_key=api_key, http=http)
    decisions.append({"tier": 2,
                      "decision": sauce.get("decision", sauce.get("status")),
                      "source": sauce.get("source"), "evidence":
                      {k: sauce.get(k) for k in ("similarity", "status")}})
    if sauce.get("ok") and sauce.get("decision") == "accept":
        return {"tier": 2, "source": sauce.get("source"),
                "evidence": {"similarity": sauce.get("similarity")},
                "decisions": decisions}

    # --- Tier 3: manual queue (always parks the target) -------------------
    queue_path = manual_queue_path or _default_manual_queue_path()
    reason = _manual_reason(decisions)
    append_manual_queue(
        {"target": name, "reason": reason,
         "suggested_tools": "google-lens; yandex"}, queue_path)
    decisions.append({"tier": 3, "decision": "queued", "source": None,
                      "evidence": {"queue_path": queue_path, "reason": reason}})
    return {"tier": 3, "source": None,
            "evidence": {"queue_path": queue_path}, "decisions": decisions}


def _manual_reason(decisions: List[Dict[str, Any]]) -> str:
    """A short human-readable reason for the manual queue, from prior tiers."""
    parts = []
    for d in decisions:
        parts.append(f"T{d['tier']}:{d['decision']}")
    return " ".join(parts) if parts else "no automated match"


# ===========================================================================
# thin argparse CLI
# ===========================================================================
def _cli_scan(root: str) -> List[str]:
    """List slugs still pending recovery: names in root/ that carry a d-token
    but have no decoded id logged. Thin helper - the real pending-set lives in
    the pipeline manifests; this is a convenience lister over a directory.
    """
    out = []
    if not os.path.isdir(root):
        return out
    for entry in sorted(os.listdir(root)):
        did = decode_deviation_token(entry)
        tag = f"deviation={did}" if did is not None else "no-token"
        out.append(f"{entry}\t{tag}")
    return out


def main(argv=None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="lw_recover",
        description="source-recovery waterfall (Tier 0 local match / Tier 1 "
                    "DeviantArt token / Tier 2 SauceNAO / Tier 3 manual queue)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pt = sub.add_parser("token", help="decode a DeviantArt filename token")
    pt.add_argument("--name", required=True, help="filename or bare d-token")

    p0 = sub.add_parser("tier0", help="Tier 0 local pHash+dHash match")
    p0.add_argument("--target", required=True, help="path to the target image")
    p0.add_argument("--corpus", required=True, help="dir of candidate source images")
    p0.add_argument("--accept", type=int, default=8)
    p0.add_argument("--review", type=int, default=14)

    ps = sub.add_parser("scan", help="list pending-recovery slugs in a dir")
    ps.add_argument("--root", required=True, help="dir to scan for d-tokens")

    a = p.parse_args(argv)

    if a.cmd == "token":
        did = decode_deviation_token(a.name)
        if did is None:
            print(f"no deviation token found in {a.name!r}")
            return 1
        print(f"{a.name} -> deviation {did} -> {deviation_url(did)}")
        return 0

    if a.cmd == "tier0":
        target = compute_hashes(a.target)
        target["name"] = os.path.basename(a.target)
        corpus = []
        for entry in sorted(os.listdir(a.corpus)):
            fp = os.path.join(a.corpus, entry)
            if not os.path.isfile(fp):
                continue
            try:
                h = compute_hashes(fp)
            except Exception:  # noqa: BLE001 - skip unreadable candidates
                continue
            h["path"] = fp
            corpus.append(h)
        res = consensus_match(target, corpus, accept=a.accept, review=a.review)
        print(json.dumps(res, indent=2))
        return 0 if res["decision"] != "no_match" else 1

    if a.cmd == "scan":
        for line in _cli_scan(a.root):
            print(line)
        return 0

    return 1


if __name__ == "__main__":
    import sys
    sys.path.insert(0, _repo_root())
    sys.exit(main())
