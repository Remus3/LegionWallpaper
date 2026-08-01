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
  - **P2 - mockd for the recovery waterfall. NEXT after P1.** One zero-dependency
    Go binary with prebuilt WINDOWS releases, fully offline, no account,
    Apache-2.0, stateful multi-step flows AND proxy record-and-replay. Record the
    real DeviantArt oEmbed + gallery-dl exchanges once, including a quota block,
    and replay them. Acceptance: recovery tests pass with the network unplugged
    and the hand-written stubs deleted.
  - **P3 - MediaWiki canonical-source probe. OPERATOR-GATED.** Use
    `professionalwiki/mediawiki-mcp-server`, NOT olgasafonova: it is the only one
    of the two exposing `get-file-data` (inline image bytes) plus `get-file`
    download links, and LW's need is splash-art FILES, not article text. One
    probe decides it - does it return bytes from a Fandom wiki. olgasafonova is
    the fallback (Fandom named explicitly, Windows stated, 40+ tools). Anonymous
    read needs no account on either, so this is a network dependency, not a
    metered one.
  - **P4 - file-claim table. LATER, METHOD ONLY.** Implement depwire's
    `claim_files` / `release_files` / `get_active_claims` shape inside
    `slice_orchestrator.py`, which is the primitive LW enforces by hand today.
    Do NOT vendor depwire - BSL 1.1 until it converts to Apache 2.0 on
    2029-02-25.
  - **P5 - memi as a one-shot UI audit. LATER.** `npx`, no install, no key,
    Windows explicitly supported, MIT, and the audit is STATIC over source - no
    running page or screenshot needed. Run it against both pages and adopt only
    if it catches something the 5-phase ritual missed.
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
