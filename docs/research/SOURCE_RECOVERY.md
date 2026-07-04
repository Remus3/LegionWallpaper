# Source Recovery Research - Finding the Real Full-Res Original

Status: research complete 2026-07-03. Web claims verified where marked VERIFIED;
anything not independently confirmed is marked UNVERIFIED. ASCII only.

Scope: topic 1 of the LW pipeline research wave - how the intake stage recovers
the original full-resolution source for each corpus image before any upscale or
inpaint work happens. Supersedes the old plan's bare "gallery-dl + SauceNAO"
note by verifying it and adding a cheaper, deterministic first tier that needs
no reverse image search at all for most of the corpus.

## Executive summary

1. The single most valuable finding: **the DeviantArt filename token IS the
   deviation ID**. Strip the leading "d", base36-decode the rest, and
   `https://www.deviantart.com/deviation/<id>` redirects to the artwork page.
   VERIFIED LIVE against the local corpus (see 2.2). Most of the corpus can be
   re-sourced deterministically with zero reverse-image-search quota spent.
2. Reverse image search is the fallback, not the primary. SauceNAO API is the
   right automatable engine for this corpus (it indexes DeviantArt and Pixiv);
   free tier is ~4 searches/30s and ~100/day, so it is a queue, not a loop.
   Bing Visual Search API is DEAD (retired 2025-08-11). TinEye is paid and
   weak for fan art. IQDB does not index DeviantArt. Google Lens has no
   official API - unofficial scrapers or paid SERP proxies only.
3. DeviantArt clamped downloads on 2026-03-09: the "Free Download" button is
   now 10/week (free) / 150/week (Core). gallery-dl `"original": true` rides
   that same quota. Plan around it: fullview/API quality-100 files (which is
   what the corpus `-fullview.jpg` saves already are) do not use the download
   quota; reserve `original` pulls for the images that truly need them.
4. Wallpaper-site rips (uhdpaper etc.): the watermarked download is the
   product; there is no clean original on the site. For OFFICIAL Riot splash
   art the clean version exists elsewhere (CommunityDragon, League wiki HD
   category, Data Dragon at 1215x717) - recover, do not inpaint. For non-official
   art ripped by wallpaper sites, find the artist post via SauceNAO; only
   inpaint when no clean source exists anywhere.
5. Local pair-matching (302 processed PNGs -> 77 local source JPGs) needs no
   internet and no ML: 64-bit pHash + dHash consensus, brute force 302x77,
   accept Hamming <= 8, review 9-14. imagehash's dependency chain has cp314
   wheels (PyWavelets 1.9.0 added them 2025-08-04), so it should run on the
   box's Python 3.14 - verify at install; Python 3.12 side-venv is the
   fallback. CLIP embeddings are optional polish, not required.

## 0. Corpus ground truth (checked on this machine, 2026-07-03)

- Processed corpus: `C:\Users\Administrator\Pictures\` - 303 entries,
  `NNN.png` / `NNN_cleanup.png`, 2560x1440.
- Originals: `C:\Users\Administrator\Desktop\need up\` staging tree
  (`0.Originals` has 19 files; more `-fullview.jpg` files sit inside
  `2.First Pass Done` and other stage folders - the ~77 total is scattered,
  intake must sweep the whole tree).
- Three source filename shapes observed:
  - `<title>_by_<artist>_<token>-pre.jpg` (DeviantArt preview save, smaller)
  - `<title>_by_<artist>_<token>-fullview.jpg` (DeviantArt fullview save)
  - `<token>-<uuid>.jpg` (raw wixmp CDN save, e.g.
    `dl3e4dq-0ad4bcb2-42f6-48d5-b3ea-cb216eda20bd.jpg`) - no artist in the
    name, but the leading token still resolves (see 2.2).

## 1. Automatable reverse image search - 2026 landscape

### 1.1 SauceNAO API - the primary engine for this corpus

- Official JSON API at `https://saucenao.com/search.php` with
  `output_type=2&api_key=...&db=999` (or a dbmask); POST the image file or
  pass a URL. Free registered API key required.
- Coverage: indexes Pixiv, DeviantArt (index 34), danbooru/gelbooru boorus,
  Twitter/X, ArtStation coverage is weak-to-absent (UNVERIFIED - test on a
  known ArtStation piece before relying on it). For a corpus of DeviantArt AI
  fan art plus official splash rips, SauceNAO is the best-fit engine.
- Rate limits, free registered key: **4 searches per 30 seconds, 100 per
  24 hours** - observed consistently in wrapper docs (saucenao-api on PyPI
  shows "4 remaining / 30s, 99 remaining / day" responses). The official
  limits page blocks non-browser fetches (HTTP 403), so treat the exact
  numbers as wrapper-observed rather than page-quoted; paid upgrades raise
  both limits (exact paid numbers UNVERIFIED).
- ToS (saucenao.com/legal.html, fetched 2026-07-03): automation with one key
  is not prohibited; what gets you banned is using multiple accounts/IPs to
  bypass limits, or account sharing. One key, throttled client, overnight
  queue = compliant.
- Practical client: `pysaucenao` (async) or `saucenao_api` (sync) on PyPI.
  Response gives per-result `similarity` plus source URLs and author fields.
  Working thresholds (community convention, tune on our data): accept >= 85,
  human-review 60-85, discard < 60.

### 1.2 The rest of the field

- **Bing Visual Search API: RETIRED.** All Bing Search APIs were decommissioned
  2025-08-11 (endpoints return HTTP 410). Microsoft's replacement (Grounding
  with Bing Search inside Azure AI Agents) does not expose visual search for
  this use case. Remove from any plan. VERIFIED (Microsoft Lifecycle notice).
- **TinEye API**: commercial only - $200/yr for 5,000 searches is the smallest
  bundle (help.tineye.com pricing, fetched 2026-07-03). Crawl-based and
  exact-match oriented: good at "where else does this file appear", mediocre
  at fan-art source attribution, and it historically indexes wallpaper mirror
  sites better than DeviantArt. Not worth paying for here.
- **IQDB**: no official API; scraping the simple form is technically easy but
  its index is boorus + zerochan/anime-pictures - **it does not index
  DeviantArt** (high confidence; confirm the index list at iqdb.org before
  citing). Low value for this corpus; skip.
- **Google Lens**: no official API. Options: (a) unofficial scrapers -
  `chrome-lens-py` (protobuf endpoint; OCR-oriented, reverse-match support
  varies by version), `krishna2206/google-lens-python` (fragile, breaks when
  Google changes markup); (b) paid SERP proxies - SerpApi and Apify both sell
  Google Lens endpoints (pricing varies, roughly cents/search, UNVERIFIED).
  ToS risk on the scrapers. Verdict: manual browser Lens for the final
  stragglers, not an automated tier.
- **Yandex reverse image**: often surprisingly good at wallpapers and art
  mirrors, but no official API for image search; automation means scraping or
  paid SERP proxies. Same verdict as Lens: manual fallback tool only.
- **Google Cloud Vision Web Detection**: official, paid, automatable, but
  optimized for entity/web matches, not art attribution; typically returns
  the wallpaper mirrors rather than the artist post. Not recommended as a
  primary. (Assessment, not measured - UNVERIFIED.)

Bottom line: SauceNAO is the only engine that is simultaneously automatable,
cheap, ToS-clean, and strong on DeviantArt/Pixiv. Everything else is either
dead, paid-and-wrong-shaped, or a manual fallback.

## 2. DeviantArt recovery specifics

### 2.1 gallery-dl (v1.32.5, 2026-06-30; supports Python 3.8-3.14 - runs on the box's 3.14)

Setup for original-quality access:
1. Register an OAuth app at DeviantArt -> Developers -> Applications & Keys.
   Redirect URI whitelist must contain
   `https://mikf.github.io/gallery-dl/oauth-redirect.html`.
2. Put `client-id` / `client-secret` in gallery-dl config, run
   `gallery-dl oauth:deviantart`, store the resulting `refresh-token`.
   Refresh tokens go stale after ~3 months or cache deletion - expect
   re-auth as a maintenance chore.
3. Key config options (gdl-org.github.io/docs/configuration.html, fetched
   2026-07-03):
   - `extractor.deviantart.original` (default false): download the artist's
     original file when the deviation is downloadable. **Now consumes the
     site-wide weekly download quota** - see 2.3.
   - `extractor.deviantart.quality` (default 100): JPEG quality for
     API-served content; set to `"png"` to prefer PNG re-encodes.
   - `extractor.deviantart.intermediary` (default true): pulls larger
     intermediary versions of older non-downloadable images.
   - The old `jwt` full-res trick (rewriting wixmp URL tokens) is no longer
     documented and DeviantArt signs CDN URLs with path-restricted JWTs now -
     treat it as dead.

Example `%APPDATA%\gallery-dl\config.json` fragment:

```json
{
  "extractor": {
    "deviantart": {
      "client-id": "<from API-Key-DeviantArt.txt>",
      "client-secret": "<from API-Key-DeviantArt.txt>",
      "refresh-token": "cache",
      "original": false,
      "quality": 100,
      "intermediary": true,
      "sleep-request": 2.0
    }
  }
}
```

Run per-deviation: `gallery-dl "https://www.deviantart.com/deviation/<id>"`.
Flip `original` to true (or pass `-o original=true`) only for the shortlist
that needs the artist's uploaded file, to conserve the weekly quota.

### 2.2 Filename token -> deviation URL (VERIFIED LIVE - this is the crown jewel)

DeviantArt image filenames embed the deviation ID as base36 with a leading
"d":

```
token "dm44iab"  ->  strip "d"  ->  int("m44iab", 36) = 1337184659
https://www.deviantart.com/deviation/1337184659
  -> 302 -> https://www.deviantart.com/pebano1/art/Xayah-1337184659
```

Verified 2026-07-03 against the corpus file
`xayah_by_pebano1_dm44iab-fullview.jpg` - the redirect landed on the correct
deviation (title "Xayah", author "PeBaNO1"). The `<token>-<uuid>.jpg` raw CDN
saves carry the same token as their prefix (`dl3e4dq-...` -> id 1275487406),
so ALL three observed filename shapes are resolvable offline to a URL.

Metadata without OAuth: the public oEmbed endpoint
`https://backend.deviantart.com/oembed?url=<deviation-url>` returns JSON with
`title`, `author_name`, dimensions, and a (JWT-tokenized, size-capped) wixmp
URL. Verified live 2026-07-03 on the same deviation. Good for cheap
"does this still exist / who made it" checks before invoking gallery-dl;
note the oEmbed `url` field itself is capped (w_1192 observed), so it is a
metadata source, not the download path - gallery-dl with OAuth is the
download path.

Token extraction rules (from observed corpus names):
- `*_by_<artist>_<token>-pre.jpg` / `*_by_<artist>_<token>-fullview.jpg`:
  token = last `_`-separated segment before the `-pre`/`-fullview` suffix.
- `<token>-<uuid>.jpg`: token = text before the first `-`.
- Regex that covers both: `(?:^|_)(d[0-9a-z]{6,8})(?=-)` - validate by
  base36-decoding and range-checking (current IDs are ~10 digits decimal).

### 2.3 The 2026-03-09 download clampdown

DeviantArt now limits "Free Download" button use to **10/week for free
accounts, 150/week for Core** (announced via team status update; tracked in
gallery-dl issue #9217). Consequences for LW:
- Bulk `original: true` runs are dead for free accounts. Budget original
  pulls: ~10/week free, or one month of Core (~$4-8, UNVERIFIED current
  price) to burst 150/week during the initial recovery campaign.
- API-served fullview/intermediary content (what gallery-dl fetches with
  `original: false`) is NOT the download button and is not documented as
  metered beyond normal API rate limits. For AI-generated 4K wallpapers the
  fullview at quality=100 is frequently the full uploaded resolution anyway;
  measure per-image (compare oEmbed/API dimensions against the fullview
  fetch) before spending a download-quota slot. (The exact fullview size cap
  policy varies by deviation age and artist settings - UNVERIFIED in
  general; verify empirically on our own corpus.)

## 3. Wallpaper-site sources (uhdpaper and friends)

- Confirmed conceptually: sites like uhdpaper watermark their exports and do
  not offer a clean original - the watermarked file IS the product. (Corpus
  observation; the site itself does not advertise clean versions.) Recovery
  from the site is impossible by construction; the choice is find-the-art-
  elsewhere or inpaint the watermark.
- For OFFICIAL Riot splash art in the corpus, clean full-res versions exist:
  - **League wiki** (wiki.leagueoflegends.com), category
    "High definition champion skins" - hosts HD splashes, some up to 4K.
    VERIFIED the category exists; per-image resolution varies.
  - **CommunityDragon**: directory listing VERIFIED at
    `https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champion-splashes/`
    (per-champion-ID folders, per-skin JPGs; there is also an `uncentered/`
    variant tree). These are the game-client assets; resolution is typically
    1280x720-class for in-client splashes (UNVERIFIED per file - check
    before preferring it over the wiki).
  - **Data Dragon** (official Riot CDN):
    `https://ddragon.leagueoflegends.com/cdn/img/champion/splash/<Champ>_<skinNum>.jpg`
    - long-documented endpoint, 1215x717 (too small to be the recovery
    target; useful as a reference/identification image).
- Recipe: when intake flags an image as official splash art (SauceNAO hit on
  official art, or obvious filename), route it to "official CDN recovery"
  (wiki first, CommunityDragon second) instead of the inpaint queue. The
  wiki + CDragon assets are watermark-free, so this converts an inpainting
  problem into a download.
- Non-official art ripped by wallpaper sites: SauceNAO -> artist post ->
  gallery-dl. Only if the artist post is gone (deleted deviation, dead
  account) does the watermarked rip go to the inpaint queue.

## 4. Local pair-matching (302 processed PNGs -> 77 local sources, offline)

Goal: auto-link each processed `NNN.png` to its local source `.jpg` so intake
never re-searches something we already own.

- **Method: 64-bit perceptual hashes, brute force.** 302 x 77 = 23,254
  comparisons - trivial; no BK-tree/FAISS needed at this scale.
  - `imagehash.phash(img)` (DCT-based, robust to rescale/recompress - exactly
    our transform chain) plus `imagehash.dhash(img)` as a second opinion.
  - Thresholds on 64-bit hashes (community-standard starting points, tune on
    the first labeled batch): Hamming <= 8 = same image (auto-accept when
    both pHash and dHash agree), 9-14 = review queue, >= 15 = no match.
    Public write-ups commonly use <= 4-5 for strict dupes; our processed
    images went through upscale + unsharp + inpaint, so start looser (8) and
    tighten if false pairs appear.
  - Known weakness: cropping/extending to 16:9 shifts pHash. If a processed
    image was reframed, hash both the full frame and a center crop of the
    source at the target aspect ratio before comparing.
- **CLIP embeddings: optional tier 2**, only for pairs pHash misses.
  open_clip ViT-B/32, cosine >= 0.95 = near-dup, 0.90-0.95 = review.
  302 + 77 images embed fine on CPU in minutes; GPU not required, which
  sidesteps the whole Blackwell/CUDA wheel question for this task.
- **Python 3.14 compatibility on this box** (Python at
  `C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe`):
  - Pillow, numpy: cp314 wheels available (mid-2026). VERIFIED at the
    ecosystem level, verify exact pins at install.
  - PyWavelets (imagehash dependency): 1.9.0 added cp314 wheels 2025-08-04.
    VERIFIED (PyWavelets release notes).
  - imagehash itself is pure Python - expected to work; verify at install
    (its scipy usage is optional/legacy; if scipy drags, pin
    `imagehash` latest and test import).
  - torch (only if CLIP tier is built): torch 2.12.1 ships cp314 wheels, but
    there are reports of CPU-only resolution on 3.14 (pytorch issue
    #169929) and the RTX 5070 (sm_120) needs cu128+ builds. Pragmatic call:
    run CLIP on CPU, or make a Python 3.12 venv for anything torch+CUDA.
    Do NOT block the pipeline on this - pHash is the workhorse.

## 5. Concrete LW intake/recovery recipe

Waterfall - stop at the first tier that succeeds; every decision logged so the
audit stage can replay it:

```
Tier 0  LOCAL PAIR MATCH (offline, free, deterministic)
        pHash+dHash all of Pictures/ and the "need up" tree ->
        link processed PNG to local source JPG. Cache hashes in
        data/recovery/hashes.json (atomic writes per CLAUDE.md).

Tier 1  TOKEN PARSE (offline -> 2 cheap HTTP calls, deterministic)
        Extract d-token from the linked source filename ->
        int(token[1:], 36) -> https://www.deviantart.com/deviation/<id>
        -> oEmbed for liveness/metadata -> gallery-dl (quality=100,
        intermediary=true) for the best non-quota file. Escalate to
        original=true only if fetched dimensions < corpus target and the
        deviation is downloadable (respect 10/week free budget).

Tier 2  SAUCENAO API (quota: ~4/30s, ~100/day free)
        For processed PNGs with no local source or dead deviation.
        db mask = DeviantArt + Pixiv + boorus. similarity >= 85 auto,
        60-85 review, < 60 fail. Throttle 1 req / 8s; overnight queue;
        persist results so an image is never searched twice.

Tier 2b OFFICIAL-ART ROUTE
        If any tier identifies the image as official Riot splash art:
        fetch clean from League wiki HD category / CommunityDragon
        champion-splashes instead of inpainting the watermark.

Tier 3  MANUAL QUEUE (data/recovery/manual_queue.csv)
        Leftovers get a row with thumbnail path + suggested manual tools
        (browser Google Lens, Yandex). Human resolves or marks
        "no source exists - inpaint path".
```

Config knobs (project conventions):
- `API-Key-SauceNAO.txt`, `API-Key-DeviantArt.txt` (client-id + client-secret
  + refresh-token) in project root - matches the existing gitignored
  `API-Key-*.txt` convention in CLAUDE.md.
- Recovery state: `data/recovery/` - `hashes.json`, `matches.json`,
  `saucenao_cache.json`, `manual_queue.csv`. Atomic tmp-then-replace writes.
- Politeness defaults: gallery-dl `sleep-request: 2.0`; SauceNAO 8s spacing
  + hard daily stop at 95 (leave headroom); one API key, one IP, per ToS.
- Budget reality check: with Tier 0/1 doing the heavy lifting, the SauceNAO
  tier probably only sees the wallpaper-site rips and orphan PNGs - likely
  well under the 100/day cap within a 2-3 day campaign.

## Risks and open items

- DeviantArt could extend the download clampdown to API fullview content -
  the March 2026 change shows appetite for anti-scraping moves. Mitigation:
  run the recovery campaign soon, cache everything.
- gallery-dl refresh tokens expire (~3 months) - build a friendly re-auth
  error message into intake rather than a silent failure.
- SauceNAO exact free-tier numbers are wrapper-observed (limits page blocks
  bots) - the client must read the `short_remaining` / `long_remaining`
  fields from each API response and self-throttle from live data, not from
  hardcoded constants.
- ArtStation coverage in SauceNAO is doubtful - if corpus items trace to
  ArtStation, expect Tier 3 manual work.
- Deleted deviations: token parse will resolve to a 404/oEmbed error - route
  to SauceNAO (mirrors may exist) then manual queue.
- The `-pre.jpg` saves are downscaled previews - never treat them as the
  recovery target, only as match keys for finding the real source.

## Sources (fetched/verified 2026-07-03)

- SauceNAO legal: https://saucenao.com/legal.html
- SauceNAO wrapper limit observations: https://pypi.org/project/saucenao-api/ ,
  https://pypi.org/project/pysaucenao/
- Bing Search APIs retirement (2025-08-11):
  https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement
- TinEye API pricing: https://services.tineye.com/TinEyeAPI ,
  https://help.tineye.com/article/275-signing-up
- gallery-dl: https://pypi.org/project/gallery-dl/ (1.32.5, 2026-06-30);
  config reference: https://gdl-org.github.io/docs/configuration.html ;
  OAuth app setup: https://github.com/mikf/gallery-dl/discussions/5376
- DeviantArt download limits: https://github.com/mikf/gallery-dl/issues/9217 ;
  https://www.deviantart.com/team/status-update/An-adjustments-being-made-to-1307747979
- Deviation URL redirect + oEmbed: verified live against
  https://www.deviantart.com/deviation/1337184659 and
  https://backend.deviantart.com/oembed?url=... (2026-07-03)
- CommunityDragon splashes:
  https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champion-splashes/
- League wiki HD splash category:
  https://wiki.leagueoflegends.com/en-us/Category:High_definition_champion_skins
- pHash thresholds background: https://benhoyt.com/writings/duplicate-image-detection/ ,
  https://github.com/knjcode/imgdupes
- PyWavelets cp314 wheels (1.9.0, 2025-08-04):
  https://pywavelets.readthedocs.io/en/latest/release.1.9.0.html
- torch cp314 status: https://github.com/pytorch/pytorch/issues/169929
- Google Lens unofficial: https://pypi.org/project/chrome-lens-py/ ,
  https://github.com/krishna2206/google-lens-python
