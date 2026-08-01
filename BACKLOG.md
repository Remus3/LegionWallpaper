# Legion Wallpaper - Backlog

_Aspirational / longer-term items. When an item moves to active work, migrate it to `ROADMAP.md` "Open items"._
_Shipped items live in git log + `docs/LEDGER.md`; this file is for things NOT yet done._
_Product is defined by ADR-002/ADR-003 (staged self-auditing restoration pipeline); sections fill as aspirational items emerge._

---

## Product

- _No aspirational product items yet; active work lives in `ROADMAP.md`._

## Platform / observability

- _No items yet. Candidates once the product runs: metrics endpoint, health rollups, log retention tooling._

## Data pipeline

- _No items yet. Candidates: image manifests, provenance records, gate-metric retention._

## Developer experience

- **mcp-lift-phases - act on the 2026-08-01 MCP triage.** Full evidence and the
  per-entry rubric in `docs/MCP_LIFT_TRIAGE_2026-08-01.md`; the triage was
  filed but never queued, which is why this entry exists.
  - **L1 - DONE 2026-08-01, result in `docs/MCP_LIFT_L1_2026-08-01.md`.** Both
    halves ran and both changed the plan. skylos is NOT wire-into-CI material
    here: it flagged `lw_httpd.py:122 allow_reuse_address = False`, which IS the
    single-instance bind guard, and most other high-confidence hits are
    framework attrs or symbols with 12-55 live references. Usable only as a
    one-shot human-read hint at `uvx skylos==3.0.0 <onedir>` (latest needs MSVC
    build tools; it also takes ONE directory per run). Real yield was a finding
    skylos did not make - see `gpu-busy-fork-unification`.
  - **L2 - the `--append-subagent-system-prompt` half is CLOSED, not deferred.**
    The flag DOES NOT EXIST on the installed CLI (2.1.220 ships only
    `--append-system-prompt`, `--append-system-prompt-file`,
    `--forward-subagent-text`). Its premise had already failed separately:
    PreToolUse hooks DO reach headless `bypassPermissions` (`e436128`), so the
    gap it was going to plug is not there either. Still OPEN on its own merits:
    `red-handed`, a local deterministic MIT auditor of "tests pass" claims
    against git history - the tool form of LW's most documented failure class,
    currently answered by spending a whole verifier subagent.
  - **L3 and L4 are SUPERSEDED by the stage-4 deep dive, 2026-08-01 -
    `docs/MCP_LIFT_DIVE_2026-08-01.md`.** All 63 LW-list entries were fetched at
    source (the triage had 5 VERIFIED-LIVE and 58 INHERITED-RC), plus the 5
    off-list entries. Read the dive, not the triage, before acting on any row.
    The replacement plan, in order:
  - **P1 - DONE 2026-08-01, see LEDGER 71.** `tools/claimed_green_gate.py`, 26
    tests, wired into the `Stop` slot that had been empty since the file was
    written. Three detectors (`claim-no-run`, `claim-vs-fail`, `no-verify`), the
    `stop_hook_active` loop guard tested, and the `pytest_guard` stdout
    asymmetry fixed in the same slice. Do-not-redo: the transcript join is by
    `tool_use_id` onto a LATER entry and a Bash result has NO `code` field -
    synthetic same-entry fixtures pass while the gate is dead against real data.
    Original scope, kept for reference:
    in Python in `tools/` from the official hook contract: `Stop` hands the hook
    `last_assistant_message` (the claim) and `transcript_path` (the evidence);
    block with `{"decision":"block","reason":...}` or exit 2. MUST read
    `stop_hook_active` and exit 0 when true - the loop guard is COOPERATIVE, not
    enforced, and an always-block Stop hook loops forever. Same slice: audit
    `text_first_guard.py` + `pytest_guard.py` for the exit-0-stdout asymmetry -
    for PreToolUse/PostToolUse/Stop, exit-0 stdout goes to the DEBUG LOG only
    and never reaches the model; use `additionalContext` or exit 2.
  - **P2 - DONE 2026-08-01, commit `9d63303`.** mockd v0.7.1 installed at
    `C:\Tools\mockd` (operator-approved, sha256 verified), real oEmbed
    exchanges recorded to `tests/fixtures/deviantart/`, replayed by a headless
    `mockd engine` in `tests/test_lw_recover_replay.py` (11 tests, skip when
    mockd is absent). **The recording refuted the suite**: `_default_http`
    wrapped `urlopen`, which RAISES on 4xx/5xx, so the getter could only ever
    return 200 and every non-200 branch in `oembed_liveness` /
    `saucenao_search` was unreachable in production - live only from the
    hand-written fakes that DID return `(404, ...)`. A dead deviation was
    landing on the transport-error verdict, so tier routing branched on the
    wrong one. Fixed by consuming `HTTPError` as the response it is.
    Do-not-redo: the mockd matcher key is `queryParams`, not `query`, and the
    engine binds a control port derived from the serving port, so tests must
    use `--port 0 --print-url`. The hand-written stubs were KEPT, not deleted:
    the fix made them accurate rather than obsolete, and they cover waterfall
    routing the replay file does not. Still open from the original scope: a
    recorded quota BLOCK (could not be captured - `original=true` was not
    blocked on 2026-08-01, rc=0 and a 1.77 MB original came back) and a
    paginated gallery. Memory `reference-deviantart-recovery` was CORRECTED in
    that same session and is no longer stale on the quota point - it now records
    the 2026-08-01 re-measurement and that the 2026-07-15 exhaustion was a
    point-in-time state, not a standing block. Do not re-file it as stale. gallery-dl is a subprocess, not http, so mockd cannot
    mock it; proxying its https needs the MITM CA trusted machine-wide, which
    is an operator call. Original scope, kept for reference:
    One zero-dependency
    Go binary with prebuilt WINDOWS releases, fully offline, no account,
    Apache-2.0, stateful multi-step flows AND proxy record-and-replay. Record the
    real DeviantArt oEmbed + gallery-dl exchanges once, including a quota block,
    and replay them. Acceptance: recovery tests pass with the network unplugged
    and the hand-written stubs deleted.
  - **P3 - DONE 2026-08-01, result in `docs/MCP_LIFT_P3_2026-08-01.md`.** The
    probe answered YES on the capability and NO on the server, so the impl
    choice INVERTS a second time: **adopt the source, decline both wrappers.**
    Both wikis serve splash art anonymously (Fandom MW 1.43.9, wiki.gg MW
    1.45.3), 19 of 20 sampled champions carry `*Skin_HD.jpg` and 143 of 147 HD
    files are at or above 2560x1440 (up to 11084x6425) - so a canonical source
    could turn the AI upscale into a downscale-only passthrough for the slugs it
    covers. But the probe ran against the Action API DIRECTLY, which is what
    both candidate servers wrap, and it answers in ~40 lines of stdlib `urllib`
    - the transport `lw_recover.py` already uses. Installing either buys a Node
    or Go/Docker dependency for zero new capability.
    Prefer **wiki.gg**; Fandom is the fallback and MUST carry `?format=original`.
    NOT claimed because NOT measured: that this helps the EXISTING corpus (the
    wiki hosts official Riot splash; much of LW's corpus is DeviantArt fan art
    no wiki hosts), that a wiki HD file beats the held `_firstinitial` for any
    given slug, or anything about licensing. **The intersection is now COUNTED
    (2026-08-01, LEDGER 75, `docs/WIKI_INTERSECTION_2026-08-01.md`): 77 corpus
    images are confirmed same-artwork as a canonical wiki splash on TWO
    independent metrics, and 77 of 77 have a wiki source at or above 2560x1440,
    median 7.43x the target pixel count.** That is 23.3 percent of the 330
    attributed corpus and a LOWER bound - the 122 `CHAMPION_UNKNOWNS.md` images
    were never swept. A Tier-0.5 canonical-source step is now justified on
    evidence rather than on hope - but see the next line before sizing it.
    **The per-slug comparison against the held `_firstinitial` is now DONE
    (2026-08-01, LEDGER 76, `docs/WIKI_VS_FIRSTINITIAL_2026-08-01.md`) and it
    cuts the prize down: 46 of 77 favour the wiki, not 77.** 23 held sources
    have MORE pixels than their wiki twin (aggregator 8K files), and on raw
    sharpness the wiki file is the softer of the two in 35 of 77. What rescues
    the case is that the held file's extra sharpness is mostly RINGING - over
    those 35 rows the held `halo_pct` against the authentic original is median
    0.1032 with 26 of 35 over the 0.05 G1 line, while the wiki original comes
    back at median 0.0089. So: 22 clear upgrades, 24 where the wiki is merely
    the cleaner source, 31 keep-or-inconclusive. Do NOT carry the "median 7.43x
    the target" figure into a source decision - its denominator is the target,
    not the held file. Also settled by that sweep: 8 of 81 structural matches are
    fan-made 4K wallpapers DERIVED from the official splash (same composition,
    different pixels), so any such tier needs two metrics and must route the
    structure-agrees-content-differs band to operator review - a single-metric
    gate would have swapped all 8 out from under the operator's chosen
    treatment.
    Do-not-redo: installing either MediaWiki MCP server; fetching a Fandom file
    URL WITHOUT `?format=original` (the default is a lossy WEBP transcode served
    under a `.jpg` name at 28 percent of the declared size, with the pixel dims
    preserved so a dimensions check reads clean); asserting byte-identity to the
    API-declared sha1 (NO host serves bytes matching it - all three paths
    re-encode, so record the sha256 of what was FETCHED); reading a
    per-champion `allimages` count without following `aicontinue` (500 is the
    cap, and the full walk took Vayne from 12 HD to 19); reading a 0-result name
    guess as absence (`Velkoz_` -> 0, `Vel'Koz_` -> 8 HD all over target -
    apostrophes are load-bearing).
    Original scope, kept for reference: use
    `professionalwiki/mediawiki-mcp-server`, NOT olgasafonova: it is the only one
    of the two exposing `get-file-data` (inline image bytes) plus `get-file`
    download links, and LW's need is splash-art FILES, not article text. One
    probe decides it - does it return bytes from a Fandom wiki. olgasafonova is
    the fallback (Fandom named explicitly, Windows stated, 40+ tools). Anonymous
    read needs no account on either, so this is a network dependency, not a
    metered one.
  - **P4 - DONE 2026-08-01.** `claim` / `release` / `claims` subcommands plus
    `claim_files` / `release_files` / `get_active_claims` / `normalize_claim_path`
    in `tools/slice_orchestrator.py`, 40 tests in
    `tests/test_slice_orchestrator_claims.py`. Method lifted from depwire, code
    NOT vendored (BSL 1.1 until 2029-02-25). Closes f1-phase6 queue item 7's
    first half: disjointness is now checkable instead of asserted by a human
    reading a directive. The `claims` field is OPTIONAL by contract, exactly
    like `verdicts` - an absent key means no claims, so every manifest written
    before this stays valid and none reads as claimed.
    Design calls, all test-pinned: comparison keys are separator-normalized AND
    case-folded, deliberately over-colliding, because the two error directions
    are not symmetric (a missed conflict loses an agent's work; a false conflict
    only refuses a claim the operator can re-scope) - this is the third time
    path identity has bitten this operator, after the three `~/.claude.json`
    keys for one directory and red-handed's subdirectory drop. Containment is
    SEGMENT-wise, so `tools` holds `tools/x.py` but `tool` does not - a naive
    startswith would cry wolf and end with the table bypassed. Claims and
    releases are ALL-OR-NOTHING (a half-granted claim lets an agent start on the
    files it did get, which loses work the same way no table does). Release is
    holder-only. Non-repo-relative paths - absolute, drive-lettered, or any `..`
    that escapes root - are REFUSED, never guessed, matching the discipline
    `next-session-handoff-enforcement` asks for.
    Still open, and NOT built: nothing calls it yet. The orchestrator exposes
    the primitive; wiring it into directive dispatch so an agent cannot start
    without a granted claim is the enforcement half, and it belongs with
    f1-phase6 item 7's "executor serializes AND RECORDS the deviation".
  - **P5 - DONE 2026-08-01, DO NOT ADOPT. Result in
    `docs/MCP_LIFT_P5_2026-08-01.md`.** Ran against both pages, which was the
    adoption test, and it caught nothing the 5-phase ritual missed. Its single
    finding is a false positive that fires on the fix it recommends: it flags
    `web/monitor.html:9` as "raw colors leaking into UI code" and recommends
    moving colours into CSS variables, while quoting the `:root{}` custom-property
    block as its evidence. Its colour metric is wrong in BOTH directions
    (monitor.html has 11 unique hex, reported as 1; rundash.html has 10,
    reported as 0) and it reports 29 and 175 "Tailwind classes" in two files
    with zero Tailwind. Its scores are unbacked: rundash.html scores 38/100 with
    ZERO findings, monitor.html scores 49 despite being the less tokenized of
    the two, and the same unchanged rundash.html scores 81/100 under
    `craft audit` against 38 under `diagnose`. `enforce-design-ci` is ruled out
    specifically - wiring that into CI would be a false-green generator aimed at
    the exact failure `claimed_green_gate.py` exists to catch.
    Do-not-redo: `npx memi` is a DIFFERENT package (0.0.8, unrelated author);
    the tool is `@memi-design/cli` 2.7.4 (MIT, node>=20, verified before
    execution). Do not re-evaluate on one subcommand - they disagree by 43
    points on the same file. The dive's own reservation was the whole story.
    One idea confirmed rather than lifted: memi labels unassessed dimensions
    "unverified, not verified-good" instead of letting silence read as a pass -
    which is LW's own NOT OBSERVED chip and the `verdicts` absent-means-unobserved
    rule. LW got there first; nothing to take.
  - **P6 - CLOSED 2026-08-01 as NOT APPLICABLE, measured. LW replays no
    credentials anywhere, so there is nothing to fix.** The queued relevance
    check ran first, exactly as it was written to, and answered no on every
    axis. Evidence, all live:
    (a) `tools/lw_recover.py:398-401` builds the COMPLETE gallery-dl argv -
    `["gallery-dl", "--dest", dest]` plus an optional `-o original=true` plus
    the url. No `--cookies`, no cookie file, no browser flag.
    (b) `%APPDATA%/gallery-dl/config.json` carries exactly five keys -
    `client-id`, `client-secret`, `original`, `quality`, `intermediary`. No
    `cookies` key, no `browser` key, no refresh token; the OAuth client mints a
    public access token per run (memory `reference-deviantart-recovery`).
    (c) grep across `tools/` and `ops/` for
    `cookie|cookiejar|netscape|session_token|set-cookie` and for
    `playwright|selenium|puppeteer|remote-debugging|enable-automation|webdriver|CDP`
    returns ZERO hits. LW has no browser automation at all, so
    `navigator.webdriver` has no surface here.
    (d) `docs/research/SOURCE_RECOVERY.md` plans none either: "browser" appears
    only as a caveat that SauceNAO's own limits PAGE 403s non-browser fetches
    (a documentation-sourcing note, not an LW fetch path) and as Tier 3's
    MANUAL queue, where a HUMAN uses browser Google Lens or Yandex.
    Deliberately NOT done: verifying the `--enable-automation` claim itself on
    this box. The dive flagged it as needing verification, but with no surface
    to apply it to that is effort spent on a claim nothing consumes - if the
    rule is ever needed, verify it THEN.
    KEEP AS A FORWARD CONSTRAINT, which is the only residue worth carrying: the
    one place this could ever bite is automating Tier 3. Google Lens and Yandex
    have no official API and the spec explicitly routes them to a human, so
    that is precisely where the temptation to export a cookie jar would arise.
    If Tier 3 is ever automated, attach to a live profile and let the PAGE issue
    the request; do not export a jar, because it rots silently as its session
    token expires and the failure looks like a source going dead.
    Do-not-redo: Reddit's specific cookie names and modhash endpoint do NOT
    transfer - only the structural rules do. The source is an r/ClaudeWorkflows
    post, and the dive established all six are bot-generated summaries whose
    checkable claims were wrong two times in four.
  - **P7 - task-orchestrator's server-ENFORCED gate. LATER, method-only.**
    Dived 5 -> 7, the highest-scoring row never given a phase. The unique
    property, verbatim: "if a required design note isn't filled, `advance_item`
    returns an error" - an agent cannot skip a gate because the CALL fails,
    versus prompt-based frameworks where instructions are merely what agents
    "should follow". State is local (SQLite + Exposed ORM with FTS5, default
    `data/current-tasks.db`), loopback needs no auth, MIT.
    NARROWED by P4: its other headline feature, `claim_item` multi-agent
    ownership, is exactly the primitive LW shipped 2026-08-01 in
    `slice_orchestrator.py`, so the only thing left to want here is the enforced
    gate. That folds into the same unbuilt half P4 left open - nothing yet
    refuses to start an agent without a granted claim (f1-phase6 item 7).
    Do NOT install to get it: distribution is a Kotlin DOCKER image and Windows
    support is UNSTATED. Lift the shape into `slice_orchestrator.py`, the same
    call P4 made about depwire.
    Page anomalies recorded so nobody re-reads them as server properties: the
    marketplace title says "1 Tools" against 14 in its body, and it carries a
    Spanish-language line advertising an `/api/orchestrate` endpoint at "Fee:
    $0.20 USDC via x402" matching no listed tool.
  - **P8 - gitwand for merge-conflict auto-resolution. LATER.** Held at 6 and
    "verified better than expected", but never phased. Auto-resolution is a
    LOCAL pattern registry with no key and no LLM call - LLM involvement is
    opt-in via `gitwand_resolve_hunk_llm` only - and it "never touches complex
    or ambiguous hunks". MIT, v3.6.0, Windows first-class (.msi, .exe, winget).
    Fit: LW runs worktree-isolated agents on disjoint file sets with a sole
    merger, so conflicts are rare BY DESIGN and this earns its place only if the
    orchestrator pattern is widened past disjointness.
    One probe decides it, and it is the reason this was not simply adopted: the
    worktree support quoted on the page describes the DESKTOP GUI, and whether
    the 7 MCP tools accept a worktree path is UNKNOWN. If they do not, it cannot
    touch LW's merge path at all.
  - **CLOSED by the dive, do not reopen:** viznoir as a render backend - its
    glTF is an EXPORT format on a list with PNG/MP4, so it is the wrong
    direction for `glb-render-fetch`, and there is zero skinned-mesh evidence
    (the question L4 was gated on: answered NO). picdefenseio in any role - all
    its image tools take a public http/https URL and cannot read a local file,
    so the corpus would have to be published first, against ADR-005's
    private-use boundary. uniprof and neurostack - neither runs on a Windows
    host. red-handed - lift the detector design, do NOT install: the repo is
    four days old with 3 stars, has no Windows CI, and carries two confirmed
    path-separator bugs that silently drop subdirectory sessions.
  Do-not-redo: do NOT inherit the sibling project's scores - it closed an entire
  class as "no image need", which is LW's whole domain. Do NOT triage by slug:
  measured, three of four name-based guesses were wrong in both directions.
  **Queue hygiene (2026-08-01):** P1-P5 are done, P6 is CLOSED as not
  applicable (measured, not assumed), P7 and P8 are queued above and unstarted. P6 existed in the dive but was missing from this list for the
  whole run; P7 and P8 were dived and scored (7 and 6) but never given a phase
  at all. Before calling this entry finished, diff the dive's replacement plan
  and its promotions section against the P-numbers here - a row that lives only
  in a doc's prose does not get worked.
  Still open from L2, and NOT discharged by P1: the RETROSPECTIVE half. P1
  shipped the live gate (`claimed_green_gate.py` reads a Stop-hook payload from
  stdin, no CLI, no history mode), but the question the triage actually posed -
  retroactively, how often was a green claim in this repo unbacked - is
  untouched. Lift the detector design, do NOT install red-handed (two confirmed
  path-separator bugs, no Windows CI).

- **next-session-handoff-enforcement - the file exists, the guard does not.**
  `C:\Users\Administrator\Desktop\LW-NEXT-SESSION.txt` is now written each
  `/done` (adopted from the sibling convention so three concurrent sessions
  cannot overwrite each other's hand-off). What is NOT built is the half that
  makes it safe: the consumer enforcing the `LW-` prefix, with the write target
  read from an on-disk intent document and ANY non-conforming value falling back
  to the default - absolute paths, drive letters, `..` segments, empty,
  non-string, or a filename not prefixed `LW-`. Without it a doctored or stale
  intent document could redirect an LW session's write over a sibling's
  hand-off. Cross-repo writes must be a deliberate act, never a fallback.

- _Also candidates: pre-commit hooks hardening, suite speed, local tooling._

## Reliability / hardening

- _No items yet. Candidates: supervisor edge cases, crash-loop backoff, watchdog coverage._

## Speculative

- _No items yet. Ideas with no committed path land here first._

## Research / inspiration

### 2026-07-26 - 3DSkinViewer / modelviewer.lol - canonical 3D geometry source - UNEXPLORED

Source: `https://github.com/Ventoba/3DSkinViewer` (operator-supplied, not yet
evaluated hands-on). Probed 2026-07-26: MIT, 6 commits, 2 stars, 0 forks, 1 open
issue - a small personal project. README: "A pengu plugin that lets you see any
Skin in Collection tab as a 3D model, based on modelviewer.lol".

**Why it may matter (NOT yet verified):** the plugin is a thin client; the
interesting artifact is whatever `modelviewer.lol` serves - LoL champion 3D
models. The M1 weapon work is blocked precisely because there is no way to render
Vayne's canonical wrist crossbow from arbitrary angles: the CLIP region gate is
dead (LEDGER 21 / `docs/research/GEN_RETUNE.md` sec "WEAPON-GATE CALIBRATION"),
the weapon LoRA is data-starved (9-19 crops), and DreamUp text-gen cannot render a
wrist-mounted device at all (it produces hand-held tactical crossbows). A real 3D
mesh would supply unlimited canonical views for LoRA training, W3 IP-Adapter
reference images, and gate positives - the exact gap every prior approach hit.

**RESOLVED 2026-07-26 - operator rulings + prior work on disk.** Q1-Q4 as first
drafted are answered; do NOT re-ask them.
1. **Programmatic access to modelviewer.lol: NO, already measured.**
   `docs/research/crossbow_render_poc.md` (2026-07-16) records modelviewer.lol
   (Khada) as Cloudflare-protected + loading via in-app blobs, explicitly NOT
   scrapeable. Do not retry the website-scrape route.
2. **Asset-distribution concern: CLOSED by operator ruling.** Assets are already
   public and widely used across public sites. LW is private-use regardless
   (RESTORATION_PLAN sec 10), so nothing ships either way.
3. **`.skn` path: PROVEN AND ALREADY BUILT, but it is NOT a reason to skip the
   GUI.** The CommunityDragon acquire -> pyritofile parse -> bone-set isolate ->
   headless moderngl render chain works (`.venv-poc`, 16 crops produced). Its ONE
   recorded hard limit is per-skin weapon isolation: the skeleton is shared across
   skins, themed skins bind capes/wings/a wine bottle to the same bone indices, and
   CDragon 404s the `.skl` so bone NAMES are unavailable. Clean isolation was
   achieved on BASE ONLY. Operator's point: a local interactive viewer is a
   curation surface for exactly that gap - choose angle + variant by eye per
   champion / skin / chroma instead of guessing bone sets. The GUI and the headless
   renderer are complementary, not either/or.
4. **rc_live conflict: EXCEPTION GRANTED (operator).** The hard gate targets VRAM
   contention from a concurrently-running game or another GPU project on this box -
   not League-client mods as a category. Asset capture while nothing else contends
   for the GPU is fine.

**The one genuinely open question:** does 3DSkinViewer render LOCALLY in-client in
a way that permits capture - sidestepping the Cloudflare/blob wall that killed the
website scrape - and can a GUI-made selection (champion / skin / chroma / angle) be
exported back to drive the already-working `.skn` render pipeline? If it is just a
local view of the same unreachable blobs, it adds nothing over the headless path.

**Consumer matters - read this before citing the POC's negative verdict.** The POC
verdict is negative for the WEAPON LORA specifically: 4 clean base renders took
training 6 -> 10 crops, v2 == v1, same plateau, concluded to be a CEILING of the
masked-inpaint + thin-LoRA method on stylized splash art rather than a data-quantity
problem. That finding does NOT transfer to the GATE. A canonicity classifier
(the 2026-07-26 DreamUp corpus work) is a different consumer with a different
failure mode - its blocker is a provenance confound in the training corpus, and
unlimited canonical multi-angle renders are an untested candidate fix for it.
Do not cite "renders did not help" as a reason to skip gate-positive experiments.

**Do-not-redo context:** SDPose-Wholebody (mmcv wall) and the ViT-L-14 region gate
are both settled dead ends - see CLAUDE.md "Settled". This item does not reopen
either; it attacks the upstream data problem instead.
