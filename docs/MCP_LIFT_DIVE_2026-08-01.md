# MCP lift - stage 4 DEEP DIVE, 2026-08-01

Companion to `docs/MCP_LIFT_TRIAGE_2026-08-01.md`. That document scored 63
entries with **5 VERIFIED-LIVE and 58 INHERITED-RC** - every score but five was
derived from a one-line summary written by a prior RC-scoped pass. This document
closes that gap: **all 63 LW-list entries were fetched at source in this pass**,
plus the 5 off-list entries the triage ranked above the whole list.

Method: 7 parallel research agents, facts-only briefs (no scoring in the brief),
scores re-derived here against the LW rubric in the triage. Every field a page
did not state is recorded UNKNOWN rather than inferred. IDs remain `LWM-##`.

Source of the list: `C:\Users\Administrator\Desktop\review prefix.txt`, 63 urls
headed `LW:`. Its operator-note block (`**!=` / `=!**`) is EMPTY - there are no
operator notes on the LW list, unlike the RC corpus.

---

## 0. The three findings that change the implementation plan

**1. Half the list cannot run on this box at all, and that is now measured.**
31 of 63 (49%) require an API key, an account, a hosted service or metered
credits - 21 hard-require, 10 more default to a hosted endpoint or meter a free
tier. Only **13 of 63 state Windows support anywhere on the page**, and two
state the opposite outright (neurostack: Linux/macOS only; uniprof: "Running on
a Windows host is currenly not supported" [sic], WSL2 only). LW is Windows-only
and no-cloud. This is not a judgement about quality - it is a platform census,
and it disqualifies more of the list than any rubric did.

**2. The triage's own top two rows do not survive their dive.** Both were
`VERIFIED-LIVE`, so this is not an inheritance failure - it is that the triage
asked the right questions and filed them as OPEN rather than answering them.
- `LWM-01 viznoir` (6, blocked on "does its glTF path carry SKINNED meshes"):
  **answered NO, and the premise was wrong twice over.** glTF is an OUTPUT
  format on a list with PNG/WebP/MP4/LaTeX - viznoir EXPORTS glTF, it does not
  consume it, which is the wrong direction for `glb-render-fetch`. There is no
  mention of skinning, skeletons, bones, armature or rigging anywhere; the mesh
  support is scientific mesh via meshio. **6 -> 3.**
- `LWM-02 picdefenseio` (6, filed as a Tier-2 COMPLEMENT to SauceNAO):
  **hard-blocked on input.** Verbatim: "All image tools take a single `url` (a
  public http/https image URL)". It cannot read a local file, so every corpus
  image would have to be published publicly first - which cuts directly against
  the private-use boundary ADR-005 rests on. Keyed AND credit-metered per call.
  The watermark tool does return source plus confidence as claimed; it is
  unreachable for LW's corpus regardless. **6 -> 2.**

**3. The best row on the list was scored 5 and its decisive features were in
nobody's summary.** See `LWM-07 mockd` below. Two more entries rose the same
way, on capabilities no one-line description carried: `depwire`'s file-claim
protocol and `memi` being static-over-source rather than screenshot-driven.

---

## 1. Promotions - the rows the dive raised

### LWM-07 mockd - 5 -> 8. The highest-scoring row on the LW list.

Every property LW needs was confirmed and none of them was in the inherited
summary:

- **One zero-dependency Go binary**, prebuilt for Windows on the Releases page.
- **Fully offline, no account.** Verbatim: "mockd works fully offline with no
  account required." Cloud features are "Coming soon" and not required.
- **Apache License 2.0** - vendor-safe under the third-party gate.
- **Stateful multi-step flows**, not static fixtures.
- **Proxy recording: record real traffic, replay as mocks.**
- 18 MCP tools plus a standalone server; 7 protocols.

The fit is exact and specific. LW's recovery tests hand-stub oEmbed and
gallery-dl, and the triage already named that as where hand-rolled stubs get
thin. Record the real DeviantArt responses ONCE - including the weekly-quota
block and a paginated gallery - and replay them deterministically forever.
That is a test-infrastructure win on the one waterfall LW cannot exercise live
without burning quota (memory `reference-deviantart-recovery`).

### LWM-06 task-orchestrator - 5 -> 7, with a Windows question and a page anomaly.

- **Gates are genuinely server-enforced**, verbatim: "if a required design note
  isn't filled, `advance_item` returns an error", contrasted with
  "Prompt-based frameworks: Instructions that agents should follow". An agent
  cannot skip a gate because the call itself fails.
- **State is local**: SQLite + Exposed ORM with FTS5, default
  `data/current-tasks.db`. No cloud. Loopback mode needs no auth.
- `claim_item` gives multi-agent ownership - LW enforces disjoint files by hand.
- MIT.

Capped at 7, not higher: distribution is a **Kotlin Docker image**, Windows
support is UNSTATED, and LW's `slice_orchestrator.py` already owns the durable
half. **Anomaly worth recording:** the marketplace page's title reads "1 Tools"
against 14 in its body, and it carries a Spanish-language line advertising a
`/api/orchestrate` endpoint at "Fee: $0.20 USDC via x402" that matches no listed
tool. Treat both as marketplace page defects, not verified server properties.

### LWM-17 depwire - 3 -> 6 CONCEPT-ONLY, on a feature no summary mentioned.

`claim_files`, `release_files`, `get_active_claims` - a **file-claim protocol**.
LW runs worktree-isolated agents on disjoint file sets with a sole merger, and
disjointness is enforced by hand today. That is the exact primitive, and it was
invisible in the "code graph, same surface" summary the triage inherited.

**License gate: BSL 1.1, converting to Apache 2.0 on 2029-02-25.** Source
available, NOT open source. **Method only - do NOT vendor.** LW can implement a
claim table in `slice_orchestrator.py` in an afternoon; that is the lift.

### LWM-08 memi - 4 -> 6. The triage's denominator argument held; its cost model did not.

Corrected on three points the summary got wrong:
- The audit is **STATIC over source** - it does not need a running page, a
  screenshot, or a browser.
- **No account or API key for the first audit**, run as one `npx` invocation.
- **Windows is explicitly stated**: "Node 20, 22, and 24 on macOS, Linux, and
  Windows". Version 2.7.4, MIT.
- It covers exactly LW's ritual axes: "Missing labels, reduced-motion
  fallbacks, focus and contrast risks" and "Weak hierarchy, spacing drift", plus
  an `enforce-design-ci` gate mode.

LW has two pages, not one (`web/monitor.html` plus the run dashboard), and the
5-phase UI-audit ritual currently costs a subagent every time it fires. A
deterministic one-shot that needs no install is cheaper than the ritual it
partly replaces. Still not NEXT - it does not cover the ASCII phase, and the
ritual's judgement half is not automatable.

### LWM-03 mediawiki - 6 held, but the impl choice INVERTS.

The triage said "two competing impls - pick one, do not wire both" and did not
say which. Both were fetched:

| | professionalwiki | olgasafonova |
|---|---|---|
| **inline image BYTES** | **YES - `get-file-data`** | no |
| file info + download links | `get-file` | metadata + upload |
| Fandom named on page | no (says "any MediaWiki") | **YES, named** |
| Windows stated | implied only | **YES** |
| tools | ~7 headline, more in README | 40+ |
| runtime | Node/npm | Go binary or Docker |
| license | MIT | MIT |
| anonymous read | yes | yes |

**Pick professionalwiki.** LW's need is best-source selection - splash-art FILES
and skin metadata, not prose - and `get-file-data` returning image bytes for
visual analysis is the only tool in either server that touches it. Fandom is a
MediaWiki instance and "any MediaWiki instance" covers it; that is one probe to
falsify, not a reason to pick the server that cannot return bytes. olgasafonova
is the fallback if the Fandom probe fails, and it wins on breadth and stated
Windows support if the need ever turns out to be article text.

### LWM-04 gitwand - 6 held, and it verified better than expected.

Auto-resolution is a **local pattern registry, no key and no LLM call**; LLM
involvement is opt-in via `gitwand_resolve_hunk_llm` only. It "never touches
complex or ambiguous hunks". MIT, v3.6.0, **Windows first-class** (.msi, .exe,
winget). Caveat: the worktree support quoted on the page describes the desktop
GUI; whether the 7 MCP tools accept a worktree path is UNKNOWN.

---

## 2. Demotions and confirmations

| LWM | was | now | what the dive found |
|---|---|---|---|
| 01 viznoir | 6 | **3** | glTF is export-only; zero skinned-mesh evidence. `compose_assets` grid/N-by-M comparison is the only residue - LW builds contact sheets by hand. |
| 02 picdefenseio | 6 | **2** | Public-URL input only; cannot read a local file. Keyed and metered. |
| 05 viznoir dup / glb-render-fetch backend | 6 | **CLOSED** | Same finding as 01. `glb-render-fetch` still has no render backend from this corpus. |
| 09 uniprof | 4 | **2** | Explicitly no native Windows host (WSL2 only), and zero mentions of GPU anywhere. LW's wall-clock is GPU inference - it measures the wrong half AND cannot run here. |
| 11 neurostack | 4 | **2** | Documentation states Linux or macOS only. |
| 19 goldencheck | 3 | **4** | Corrected: it DOES validate local CSV/Parquet/Excel, not warehouse-only, and stores its own baseline via `goldencheck baseline`. Still needs LW's JSON exported to a supported format first. |
| 25 Frenchie | 3 | **2** | OCR is HOSTED on getfrenchie.dev with metered credits; local paths are accepted but the artwork is uploaded off-box. LW runs easyocr in-process. Confirms the triage's ruling with a stronger reason. |
| 27 DepScope | 3 | **3** | Covers PyPI and Conda, not npm-only - correcting the inherited read. Hosted but keyless. Client is AGPL-3.0-or-later, backend proprietary. Package names would leave the box. |
| 32 AnomalyArmor | 2 | **1** | Confirmed hosted SaaS, account plus `ARMOR_API_KEY` required. |
| 52 x64dbg | 2 | **2** | Confirmed NOT read-only - memory write, patching, PE dump, anti-debug bypass. No LW surface. Held. |
| 12 Local Model Suitability | 4 | **1** | Classifies TEXT LLM calls only (llama3.2, mistral, phi3). LW's local models are diffusion, upscale and pose. It also requires a cloud key to answer, inverting its own premise. |
| 22 klavis / 30 driflyte / 43 context-awesome | 3 | held | All confirmed hosted-first. |

Rows the dive confirmed at their inherited score, with no new evidence either
way, are not re-listed - the ranked table in the triage stands for them.

---

## 3. The off-list entries - and the one that outranks the whole list

The triage asserted the highest-value items for LW were NOT on the list it was
handed. All four were dived. **Their only recorded url is a Reddit post, and
every Reddit fetch failed** - `Claude Code is unable to fetch from
www.reddit.com`, five for five. Nothing below is inferred from a post title;
each was traced to upstream source instead.

### Item B - Claude Code hooks. SCORE 9, and it is the only NEXT with zero dependencies.

Researched against the official docs (`code.claude.com/docs/en/hooks`), not the
Reddit post. This is the highest-value finding in the entire review because it
needs no install, no license, no key and no network.

- **30 hook events exist today**, including `Stop`, `SubagentStop`,
  `PostToolUseFailure`, `TaskCompleted` and `SessionEnd`.
- **Stop input carries `last_assistant_message` and `transcript_path`** - the
  claim text and the evidence, handed to the hook at exactly the moment Claude
  asserts it is done.
- **A block is signalled two ways**: exit 2 with the reason on stderr, or exit 0
  with top-level `{"decision":"block","reason":"..."}`. Stop uses the TOP-LEVEL
  `decision` field, not PreToolUse's `hookSpecificOutput.permissionDecision`.
- **`stop_hook_active` is COOPERATIVE, not enforced.** The harness does not cap
  the loop; a hook that always blocks loops forever. It must read the flag and
  exit 0 when true. This is the trap the entry's own caution named, confirmed.
- **The reason DOES reach the model.** Three channels: `decision: block` +
  `reason`, `hookSpecificOutput.additionalContext`, or exit-2 stderr.
- **Asymmetry that matters for LW's existing hooks:** plain exit-0 stdout
  reaches the model ONLY for SessionStart, Setup, SubagentStart,
  UserPromptSubmit and UserPromptExpansion. For **PreToolUse, PostToolUse and
  Stop it goes to the debug log only**. LW's `text_first_guard.py` and
  `pytest_guard.py` are PreToolUse/PostToolUse - if either prints an explanation
  to stdout expecting the model to read it, the model never sees it.

### Item A - red-handed. 8 -> 7, and Windows is the decisive caveat.

Real repo: `github.com/sjh9714/red-handed` (found by GitHub search; the Reddit
post was unreachable). MIT, TypeScript, node >= 20, one runtime dependency
(`picocolors`). Run with `npx @jinhyuk9714/red-handed@latest`.

**Nine detectors**, and the LW-relevant ones are real: `claim-no-run` ("said
tests pass - none ran, not even in a subagent"), `claim-vs-fail`, `test-census`
(the suite got smaller), `assertion-weakening`, `skip-only`, `config-disable`,
and **`no-verify`** - which matches `--no-verify`, `git commit -n` and bypass
env vars, then checks whether a hook-shaped failure preceded the bypass and only
then rates it CAUGHT. That is precisely the `.githooks` bypass LW's whole gate
design rests on.

**Four facts that set the score, all measured rather than claimed:**
1. **The repo is FOUR DAYS OLD.** Created 2026-07-30, last push 2026-08-01,
   **3 stars**, 3 open issues filed by the author himself.
2. **No Windows CI.** `.github/workflows/ci.yml` is `runs-on: ubuntu-latest`
   with no matrix. Zero Windows coverage.
3. **Two confirmed Windows path bugs.** `isInside()` in `src/session/discover.ts`
   compares with a hardcoded `/` separator, so on Windows only the exact repo
   root matches and **every session started in a subdirectory is silently
   dropped**. And `path.split("/").pop()` for the session id is a no-op on
   backslash paths, so `--session <uuid>` can never match a bare uuid prefix.
4. **It would still find LW's sessions today**, measured on this machine:
   `flattenPath` turns `C:\LegionWallpaper` into `C--LegionWallpaper`, which is
   the directory that exists, and every LW transcript records
   `"cwd":"C:\\LegionWallpaper"` - the exact root. Root-level sessions match;
   subdirectory sessions do not.

**It is not read-only as advertised.** `audit` is; `hook install` writes
`~/.claude/settings.json` (plus a backup and a temp file) to install ITSELF as a
Stop hook. Also: only vitest, jest, mocha and pytest output is parsed - ruff and
`py_compile`, which LW leans on, are not. There is no transcript schema check at
all; the `version` field is read and never validated (LW's transcripts currently
carry `2.1.219`).

**Ruling: do not install. Lift the design.** Item B is the mechanism, this is
the check list, and LW can implement the two detectors it actually needs
(`claim-no-run`, `no-verify` after a hook rejection) against its own transcripts
in Python with no Windows bugs and no four-day-old dependency. Revisit the tool
itself if it grows a Windows CI matrix.

### Item C - browser automation findings. 7 -> 4. Two thirds of it is unverifiable.

Only **`navigator.webdriver` is documentation-verified** (W3C WebDriver Level 2
webdriver-active flag; MDN confirms Chrome sets it under `--headless` and
`--remote-debugging-port`). **"Transient interstitials" does not appear in the
WebDriver specification at all**, and no first-party ChromeDriver documentation
defining the behaviour could be found. Cookie-expiry semantics could not be
retrieved (the spec page truncated before section 14 on three attempts) and are
recorded UNKNOWN rather than filled in. An entry scored 7 for carrying "three
measured protocol facts" carries one.

### Item D - the two prose entries. UNSCORABLE, recorded as a gap.

Both Reddit urls unreachable; no mirror, crosspost, archive or upstream artifact
exists. Nothing was reconstructed from the titles. If this material is wanted,
the post bodies have to be pasted in from a browser session that can reach
Reddit. **This is a stage-4 GAP, not a completed dive** - same disposition RC
gave its own unreachable Reddit row.

---

## 4. Revised phase plan - what the implementation passes should actually do

The triage's L1-L4 were written before any of the above was known. L1 has run.
This supersedes L2-L4.

**P1 - the Stop-hook claimed-green gate. NEXT. No dependency, no license, no
network.** Build it from Item B's contract and red-handed's detector design, in
Python, in `tools/`. Minimum viable: on `Stop`, read `last_assistant_message`
for a green claim and `transcript_path` for whether a suite actually ran this
session; block with a `reason` when a claim has no run behind it. **Must** read
`stop_hook_active` and exit 0 when true - an always-block Stop hook loops
forever. While in there, audit `text_first_guard.py` and `pytest_guard.py` for
the exit-0-stdout asymmetry: if either explains itself on stdout, the model
never sees it, and the fix is `additionalContext` or exit 2.

**P2 - mockd for the recovery waterfall. NEXT after P1.** One Windows binary,
offline, Apache-2.0. Record the real DeviantArt oEmbed and gallery-dl exchanges
once, including a quota-block, and replay them in tests. Acceptance: the
recovery test suite passes with the network unplugged and the hand-written stubs
deleted.

**P3 - the MediaWiki canonical-source probe. OPERATOR-GATED, unchanged in
substance, decided in impl.** professionalwiki, for `get-file-data`. One probe
first: does it return image bytes from a Fandom wiki. If no, olgasafonova. Still
gated because it adds a network dependency to intake, though NOT a metered one -
anonymous read needs no account on either.

**P4 - the file-claim table. LATER, method-only.** Implement depwire's
claim/release/active-claims shape inside `slice_orchestrator.py`. Do not vendor
depwire - BSL 1.1 until 2029.

**P5 - memi as a one-shot UI audit. LATER.** `npx`, no install, no key, Windows
supported. Run it against both pages and compare its findings to the ritual's;
adopt only if it catches something the ritual missed.

**CLOSED, do not reopen:** viznoir as a render backend (glTF is export-only, no
skinned meshes); picdefenseio in any role (public-URL input only); the whole
keyed/hosted half of the list; uniprof and neurostack (cannot run on Windows).

---

## 5. Do-not-redo

- Do NOT re-dive the 63 from the marketplace pages. They were all fetched
  2026-08-01 and the facts are above; go to the upstream repo instead.
- Do NOT try Reddit for the off-list entries. Five for five unreachable this
  session. Item D needs a paste from a browser, not another fetch.
- Do NOT install red-handed on this box before checking for a Windows CI
  matrix. Two separator bugs are confirmed in the version dived here.
- Do NOT read the marketplace page's tool COUNT as authoritative:
  task-orchestrator's title says "1 Tools" against 14 in its body, octocode says
  "12 core tools" and names 13, and Frenchie states 6 and names 7.
- Do NOT trust a marketplace page's sidebar as a tool list. On kagan and klavis
  the rendered rail is a sponsor strip (CodeRabbit, Granola, Mailtrap, 1inch),
  not the server's tools. Two of the seven agents flagged this independently.
