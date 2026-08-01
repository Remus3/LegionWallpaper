# MCP lift triage - LW pass, 2026-08-01

Sources reviewed: the operator's `review prefix.txt` LW list (63 marketplace URLs,
headed `LW:`), `First-Pass.md` (an RC-scoped triage, 146 entries), and
`First-Pass-Addendum.md` (an RC competitor teardown).

IDs here are `LWM-##`, LW's own. They are NOT the same numbering as RC's `CCR-##`
and must never be cited as if they were. The CCR id is carried in a column only
so a row can be traced back to the evidence it inherited.

Fit tags use LW's ROADMAP grammar - `NEXT` / `LATER` / `OPERATOR-GATED` /
`CLOSED:<reason>` - not RC's.

---

## Evidence tiers (every row is labelled; no row is unlabelled)

- `VERIFIED-LIVE` - I fetched the listing this session and read what it actually
  does. 5 of 63.
- `INHERITED-RC` - description comes from `First-Pass.md`, written by a prior
  RC-scoped pass. The DESCRIPTION is reused; the SCORE is re-derived for LW and
  is mine. 58 of 63.
- `UNREVIEWED` - nobody has looked. 0 remaining after this pass.

Inheriting a description is not inheriting a verdict. See "The inversion" below
for why that distinction is the whole point of this document.

---

## LW scoring rubric (1-10, liftability to Legion Wallpaper)

LW is a staged, self-auditing image restoration pipeline. No web runtime, no
live model-call surface, one local listener (`lw_monitor` on 8901,
operator-launched). Solo operator. The problems-of-now that a tool can actually
touch:

1. **The pipe is stalled at Stage 2.** Nothing has ever flowed past cleaning.
   Stage 3/4/5 engines do not exist yet.
2. **Operator approval is the real queue** - 17 slugs sit at NEEDAUTH today.
   Anything that makes a batch easier to adjudicate is worth more than anything
   that makes the code prettier.
3. **Source recovery** - DeviantArt quota, `-pre` previews, Tier 2 SauceNAO.
4. **Watermark and signature detection** feeding the masked-inpaint lane.
5. **Gate calibration** - thresholds seeded at n=10/n=12 and owed recalibration.
6. **Claimed-green verification** - LW's single most documented failure class.
7. **The headless enforcement gap** - MEASURED here 2026-07-26: `claude -p
   --permission-mode bypassPermissions` does NOT load PreToolUse hooks, so
   `.githooks/` is the only backstop that survives every channel.
8. **Context and bootstrap budget.**

Scores:

- **8-10** hits one of those eight directly and is usable without a new paid
  dependency.
- **5-7** real concept or method for LATER; partial fit, or blocked behind an
  unfunded ROADMAP item.
- **2-4** generic developer tooling; would help any Python repo, helps LW no
  more than average.
- **0-1** wrong domain outright.

License gate, same as RC's: MIT/Apache/BSD/ISC = vendor-safe. AGPL/BSL =
method-only, do not vendor. None stated = reference only.

**Standing constraint, stated once:** nothing in this document has been
installed. Adding an MCP server changes the session tool surface, and several
here want an API key or burn metered credits. Installation is an operator call.

---

## The inversion - the single most important finding in this review

62 of the 63 LW links already carry a scored entry in `First-Pass.md`. It is
tempting to inherit those scores. **Do not.** RC closed an entire class of
entries with reasons of the form "RC is a 2D coaching dashboard, no image or 3D
need" - and that class is LW's whole domain.

But the correction does NOT run the way the names suggest, and this is the part
worth reading twice. I fetched the four highest-stakes rows rather than
reasoning from their slugs:

| entry | what the name suggests | what it ACTUALLY is | LW verdict |
|---|---|---|---|
| viznoir | an image tool (operator listed it first) | VTK scientific visualization over simulation meshes - OpenFOAM, CGNS, Exodus | not an image tool at all, but see LWM-05 |
| rendex-mcp | a renderer LW could use | hosted API that screenshots HTML and URLs to PNG/PDF | wrong direction, cloud, keyed |
| picdefenseio | RC closed it as duplicate OCR | ships **watermark detection with source + confidence** and **"find pages where an image appears"** | maps onto TWO live LW surfaces |
| skylos | dead-code linter | dead code **plus** secret detection and AI-hallucinated-API checks, local, Apache-2.0, no key | better fit for LW than for RC |

Name-based triage gets three of those four wrong, in both directions. The
inversion is real for exactly one entry (picdefenseio) and the two that LOOK
like image tools are not. That is the measurement, not the intuition.

---

## LWM-05 - the find, and it comes from the one entry nobody had reviewed

`kimimgo/viznoir` is the only LW-listed URL absent from `First-Pass.md`. On its
face it is irrelevant: scientific visualization for simulation data. LW has no
simulation data.

It also renders **glTF**, headlessly, locally, via EGL/OSMesa, MIT, no API key,
with `render` / `batch_render` / `preview_3d` / `compose_assets`.

ROADMAP item `glb-render-fetch` is OPEN and its owed half is stated as: "fetch
the URL, parse the GLB container, skin the mesh against the surviving joints,
and render the crop that `load_assets` consumes. That half needs a network
dependency and a render backend, so it is a separate slice by design."

viznoir is a candidate for the **render backend** half, and it arrives without
the cloud dependency that made every other render entry a non-starter.

**This is a hypothesis, not a finding.** The unresolved question is whether its
glTF path carries SKINNED meshes - joint weights applied against a skeleton -
or only static geometry. LW's need is specifically to skin against surviving
joints, and VTK/meshio glTF import is not obviously skeletal. Verify that before
any further work; if it is static-geometry-only, this entry drops to a 2 and the
item stays owed. Do not fund a slice on the strength of a matching file
extension.

---

## Ranked table (all 63, LW score desc)

| LWM | LW | fit | CCR | name | evidence | LW reasoning |
|---|---|---|---|---|---|---|
| 01 | 6 | NEXT | 81 | skylos | VERIFIED-LIVE | Local, Apache-2.0, no key, Python-first. LW carries four `_*_oneoff.py` scripts and 47 tools accreted over a month; dead-code and secret scanning is a real condition here, not a hypothetical. Runs as a one-shot without being installed as a server. |
| 02 | 6 | LATER | 25 | picdefenseio | VERIFIED-LIVE | Watermark detection returning **source + confidence** is a shape LW's own detector lacks, and "find pages where an image appears" is adjacent to Tier-2 recovery. LW already pays for a metered image API (SauceNAO), so the keyed-service objection that closed this for RC does not transfer. NOT a SauceNAO replacement - its own listing says it does backlink discovery, not true reverse-image search. Complement at best. |
| 03 | 6 | LATER | 39/84 | mediawiki (two impls) | INHERITED-RC | The LoL wiki is a Fandom MediaWiki and carries canonical splash art plus skin metadata. LW's hardest unautomated judgement is best-source selection; a canonical-source probe ahead of Tier 1 is the only entry here that touches it. Two competing impls - pick one, do not wire both. |
| 04 | 6 | LATER | 111 | gitwand | INHERITED-RC | Merge-conflict auto-resolution over the orchestrator pattern. LW ran 4 worktree agents on disjoint file sets this week with a sole merger; disjointness is enforced by hand today. |
| 05 | 6 | LATER | n/a | viznoir | VERIFIED-LIVE | See LWM-05 above. Blocked on the skinned-mesh question and on `glb-render-fetch` being funded at all. |
| 06 | 5 | LATER | 109 | task-orchestrator | INHERITED-RC | Server-enforced workflow gates. LW's slice manifest (`tools/slice_orchestrator.py`) already does the durable half; the enforced-gate half is the gap. |
| 07 | 5 | LATER | 110 | mockd | INHERITED-RC | LW's recovery tests stub oEmbed and gallery-dl by hand. A stateful mock is a genuine fit for the waterfall's multi-tier flow, which is exactly where hand-rolled stubs get thin. |
| 08 | 4 | LATER | 115 | memi | INHERITED-RC | RC's top-scored entry, and it drops here: LW has ONE page (`web/monitor.html`) and the UI-audit ritual fires rarely. Same tool, different denominator. |
| 09 | 4 | LATER | 105 | Uniprof | INHERITED-RC | LW's wall-clock is GPU inference, not Python. A CPU profiler measures the wrong half of a 4x upscale. |
| 10 | 4 | LATER | 82 | token-optimizer-mcp | INHERITED-RC | Context budget is a named LW concern (skill section 10b), but LW's fix is disk-over-thread, already ruled. |
| 11 | 4 | LATER | 68 | neurostack | INHERITED-RC | STALE detection over markdown notes is the interesting half - LW's memories carry a documented staleness risk. Recall itself is not an LW gap. |
| 12 | 4 | LATER | 101 | Local Model Suitability | INHERITED-RC | Thematically closest of the batch to LW's all-local posture, but it classifies LLM calls; LW's local models are diffusion and pose, which it does not cover. |
| 13 | 4 | LATER | 58 | Claude Flow | INHERITED-RC | Trajectory self-learning over past runs is the only novel angle; LW's LEDGER is the manual version. |
| 14 | 3 | LATER | 102 | Pharaoh | INHERITED-RC | Code graph. LW already wires KARP Inspector Lite - same surface. |
| 15 | 3 | LATER | 88 | codebase-memory | INHERITED-RC | As above. |
| 16 | 3 | LATER | 113 | better-code-review-graph | INHERITED-RC | As above. |
| 17 | 3 | LATER | 114 | depwire | INHERITED-RC | As above, plus BSL-1.1 - method only until it converts. |
| 18 | 3 | LATER | 95 | Atomadic Forge | INHERITED-RC | Python AST refactor scoring; ruff plus `tools/drift_guard.py` cover LW's actual enforcement. |
| 19 | 3 | LATER | 74 | goldencheck | INHERITED-RC | LW's tabular surface is `pipeline_state.json` and census tables, all schema-stable and already asserted by tests. |
| 20 | 3 | LATER | 116 | pindoc | INHERITED-RC | Line-pinned decisions. LEDGER plus `docs/adr/` cover it. |
| 21 | 3 | LATER | 108 | neural-memory | INHERITED-RC | Typed-edge graph memory. No LW gap. |
| 22 | 3 | LATER | 77 | klavis / Strata | INHERITED-RC | Tool-surface curation; real concern, but LW's deferred-tool loading already does it at the harness level. |
| 23 | 3 | LATER | 55 | Kagan | INHERITED-RC | Board over worktree agents. LW has the manifest; a board is UX, not a need. |
| 24 | 3 | CLOSED:no-video | 26 | reka | INHERITED-RC | LW has no video surface. End-review 2AFC is stills. |
| 25 | 3 | CLOSED:covered | 100 | Frenchie | INHERITED-RC | Generic OCR. LW runs easyocr in-process in the cleaning venv, closer to the pixels. |
| 26 | 3 | LATER | 71 | octocode | INHERITED-RC | Evidence-first code research; marginal over existing greps. |
| 27 | 3 | LATER | 98 | DepScope | INHERITED-RC | Pre-install package verification. LW's dependency churn is near zero and pinned in venvs. AGPL client. |
| 28 | 3 | LATER | 104 | Spec-Driven Development | INHERITED-RC | LW already mandates spec-first via the subagent protocol. |
| 29 | 3 | LATER | 44 | helmdeck | INHERITED-RC | Capability packs for small local models; LW's local models are image models. |
| 30 | 3 | LATER | 117 | driflyte | INHERITED-RC | Topic RAG over crawled pages; hosted, rate-limited. |
| 31 | 3 | LATER | 66 | autots | INHERITED-RC | Changepoint detection could in principle watch gate-metric drift across batches. Thin, and LW's census approach is stronger. |
| 32 | 3 | LATER | 50 | AnomalyArmor | INHERITED-RC | Schema drift and freshness over SQL warehouses; LW writes local JSON. |
| 33 | 2 | CLOSED:dupe | 63 | praisonai | INHERITED-RC | Duplicates LW's orchestrator pattern. |
| 34 | 2 | CLOSED:dupe | 85 | claudex | INHERITED-RC | Cross-session memory; LW has WAKEUP/LEDGER/memory. |
| 35 | 2 | CLOSED:dupe | 90 | synapse-layer | INHERITED-RC | As above, plus a Postgres dependency LW will not take. |
| 36 | 2 | CLOSED:dupe | 91 | Cathedral | INHERITED-RC | Crypto agent identity; not an LW need. |
| 37 | 2 | CLOSED:dupe | 92 | Ejentum | INHERITED-RC | Reasoning scaffolds; LW has skills. |
| 38 | 2 | CLOSED:dupe | 118 | midos | INHERITED-RC | Generic knowledge base. |
| 39 | 2 | CLOSED:dupe | 112 | skillsmith | INHERITED-RC | LW has a rich local skill set. Elastic-2.0. |
| 40 | 2 | CLOSED:dupe | 78 | idea-reality | INHERITED-RC | Idea validation; LW's product is defined. |
| 41 | 2 | CLOSED:dupe | 76 | temporal-mcp | INHERITED-RC | Time awareness between turns. |
| 42 | 2 | CLOSED:dupe | 119 | kansei | INHERITED-RC | MCP discovery catalogue. |
| 43 | 2 | CLOSED:dupe | 65 | context-awesome | INHERITED-RC | Awesome-list search. |
| 44 | 2 | CLOSED:dupe | 93 | Agent Interviews | INHERITED-RC | SaaS integration hub. |
| 45 | 2 | CLOSED:dupe | 83 | computer-use-mcp | INHERITED-RC | LW already wires computer-use and Windows-MCP, and LW's R1-R3 rules push AWAY from visual tools for text tasks. |
| 46 | 2 | CLOSED:dupe | 42 | shaft_mcp | INHERITED-RC | Selenium; LW has the browser pane. |
| 47 | 2 | CLOSED:dupe | 107 | code-runner | INHERITED-RC | LW runs Python natively on Legion. |
| 48 | 2 | CLOSED:wrong-eco | 73 | npm-sentinel | INHERITED-RC | LW is Python. |
| 49 | 2 | CLOSED:no-need | 87 | webembedding | INHERITED-RC | Site cloning. |
| 50 | 2 | CLOSED:no-need | 97 | Data Compliance | INHERITED-RC | LW is private-use, single operator. |
| 51 | 2 | CLOSED:no-need | 57 | arifOS | INHERITED-RC | Governance kernel; AGPL. |
| 52 | 2 | CLOSED:no-need | 89 | x64dbg | INHERITED-RC | Binary RE. |
| 53 | 2 | CLOSED:wrong-dir | 94 | VULK | INHERITED-RC | Generates 3D websites. Wrong direction for `glb-render-fetch`, which needs to CONSUME a GLB, not author one. |
| 54 | 2 | CLOSED:wrong-dir | 31 | threews-3d-studio | INHERITED-RC | Text/image-to-3D generation. Same wrong direction, and hosted. |
| 55 | 2 | CLOSED:cloud | 75 | rendex | VERIFIED-LIVE | Renders HTML/URLs to images. LW renders pixels from pixels. Hosted, keyed, quota'd. |
| 56 | 2 | CLOSED:cloud | 53 | Transloadit | INHERITED-RC | Cloud media pipelines. LW's transforms are local, deliberate, and audited per step; routing corpus images through a third party also cuts against the private-use boundary that ADR-005 rests on. |
| 57 | 2 | CLOSED:no-need | 67 | typeui | INHERITED-RC | Design-system server for UI generation; LW has one page. |
| 58 | 2 | CLOSED:no-need | 106 | youtube-transcript | INHERITED-RC | No video research surface. |
| 59 | 1 | CLOSED:wrong-domain | 96 | CrawlConsole | INHERITED-RC | SEO. |
| 60 | 1 | CLOSED:wrong-domain | 86 | rootly | INHERITED-RC | Incident management. |
| 61 | 1 | CLOSED:wrong-domain | 52 | TaScan | INHERITED-RC | Physical-world task protocol. |
| 62 | 1 | CLOSED:wrong-domain | 103 | Synapse-GEO | INHERITED-RC | Agent-discoverability SEO. LW is a private repo and explicitly does not want to be discovered. |
| 63 | 1 | CLOSED:no-need | 49/54/etc | remainder | INHERITED-RC | Link sharing, markdown publishing, and similar - no LW surface. |

**LW score distribution (n=63):** 6:5 5:2 4:6 3:19 2:26 1:5

Compare RC's distribution over its own corpus. LW's is flatter and lower, and
that is the correct outcome: LW is a narrower project with a smaller tool
surface to improve, and most of this catalogue is developer-workflow tooling
aimed at a large codebase with many contributors.

---

## What is NOT in the LW list, and outranks everything that is

The operator's LW list is 63 marketplace URLs. `First-Pass.md` carries 146
entries, and the last 27 are not marketplace links at all - they are technique
and practice entries. **Four of them score higher for LW than anything on the
LW list**, and one addresses a gap LW measured and documented itself.

| rank | source | LW score | why it outranks the list |
|---|---|---|---|
| 1 | CCR-146 subagent system-prompt inheritance | **9** | `--append-subagent-system-prompt` injects rules into EVERY nested subagent and works headless. LW's CLAUDE.md records the measured fact that headless `claude -p` does NOT load PreToolUse hooks - this is the missing enforcement reach for exactly that hole. It also corrects a live assumption: LW's `.claude/agents/*.md` subagents never inherited CLAUDE.md framing, so any rule believed to reach them by inheritance does not. Verify both flags against the installed CLI before relying on either. |
| 2 | CCR-143 red-handed | **8** | A local, deterministic, MIT auditor of "tests pass" claims against git history. LW's Verification Discipline section exists because of this failure class, and the manual answer is the `verifier` subagent - which cost four full agents in one run this week. Its "commit after a hook rejection" check is one LW specifically needs. |
| 3 | CCR-136 browser automation findings | **7** | Three measured protocol facts about `navigator.webdriver`, transient interstitials, and cookie rot. LW's recovery waterfall drives DeviantArt and has already been shaped around fetch behaviour. Facts, not code - re-implement freely. |
| 4 | CCR-127 hooks (PreToolUse + Stop) | **6** | LW has hooks wired; the Stop-gate slot is the one that would block a handoff until the suite is green. |
| 5 | CCR-142 rigorous engineering prompt | **6** | "Provenance on every number with the tier LABELLED" and "pin the convention before comparing numbers" are LW rules in all but name - the halo census had to pin common-scale before any number meant anything. |

**Assertion:** the highest-value items for LW were outside the list I was handed.
A triage that only scores what it is given cannot report that, which is why this
section exists.

---

## Defect in the source document, reported because it hides the good rows

`First-Pass.md` says "119 links" (line 3) and its score distribution reads
`(n=119)` (line 34), topping out at score 7. The file actually carries **146
scored entries**, and the true distribution is:

```
1:19  2:33  3:28  4:14  5:22  6:18  7:7  8:4  9:1   (n=146)
```

There are four 8s and a 9. The header, the stated distribution, and the index
labelled "all 119, desc" are stale by 27 entries, and the practical effect is
that **the five highest-scoring entries in the document are invisible to anyone
who reads the top of it** - including the one that addresses LW's measured
headless enforcement gap.

This is the counted-claim class `tools/drift_guard.py` checks for in LW's own
docs. Recomputing the distribution is a one-line fix on the RC side.

---

## What is liftable from First-Pass-Addendum.md

The Addendum is an RC competitor teardown of a League build calculator. The
CONTENT is irrelevant to LW. Three methods are not, and one of them is a
warning LW just proved on its own corpus.

**1. "Use the export, not DOM capture" - CONVERGENT, already LW practice.**
Their breakthrough was finding the machine-readable surface instead of building
a scraper. LW independently converged: the recovery waterfall decodes a
DeviantArt token and drives gallery-dl rather than scraping the site, and the
ROADMAP records site-scraping as measured-and-ruled-out. No lift; record as
independent confirmation that the instinct generalizes.

**2. The measured do-not-retry block - CONVERGENT, same grammar.**
"Bulk JSON ingest is RULED OUT - measured, do not retry", with the measurement
inline, is the same construct as LW's `Do-not-redo:` lines. Their version states
the byte count and the null field that killed it. LW's are usually prose. Worth
copying the habit of pasting the actual measurement into the do-not-redo line.

**3. The structural-default-bias warning - THE REAL LIFT, and LW just hit it.**
The Addendum flags that a user complaint about builds skewing lethality is
STRUCTURAL rather than perception, because the default ally team is fixed and
unrepresentative. Restated generally: **a default or seed that is
unrepresentative of the corpus produces bias that looks like a quality problem.**

That is precisely the `usm-halo-calibration` finding from 2026-07-30. LW's halo
threshold is a seed measured at n=10 on a DIFFERENT upscaler with a DIFFERENT
mask setting, and it flagged 7 of 17 images on a corpus it was never calibrated
for. The flags were structural, not a quality collapse.

The transferable rule, in LW's own words: **before treating a gate's output as a
finding about the images, check whether the gate's seed was drawn from the same
population as the images.** That belongs alongside the existing corpus-matching
rule, and it is stronger than the Addendum's version because LW has a measured
instance.

**4. The parity table shape** - `their control | their default | LW equivalent
(file:line) | AHEAD / PARITY / BEHIND / N-A` - is a good format for LW's next
gate comparison against any published upscaler-QA metric set. Adopt the shape,
not the content.

---

## Phases

**Phase L1 - free, local, no install, no key.** One-shot `skylos` scan over
`tools/` and `ops/` for dead code and any secret-shaped literal; LW carries four
`_*_oneoff.py` scripts and a month of accreted tooling. Verify the two CLI flags
from CCR-146 against the installed Claude version. Both are cheap and neither
adds a dependency.

**Phase L2 - close the enforcement gap.** This is the highest-value work in the
whole review and none of it comes from the LW list. Wire
`--append-subagent-system-prompt` to carry the ASCII rule, the verification
mandate and the frozen-file list into every nested subagent, covering the
surface the PreToolUse hooks were MEASURED not to reach. Then evaluate
`red-handed` against LW's own transcript history - it would answer,
retroactively, how often a green claim in this repo was unbacked. Consider the
Stop-hook gate last, since it is the most intrusive.

**Phase L3 - pipeline-adjacent, operator-gated.** A MediaWiki canonical-source
probe ahead of Tier 1 in the recovery waterfall, and an evaluation of
picdefenseio as a Tier-2 COMPLEMENT to SauceNAO (not a replacement - it does
backlink discovery, not reverse-image search). Both touch the recovery waterfall,
so both need the operator's call on whether another metered service is wanted.

**Phase L4 - blocked.** viznoir as the render backend for `glb-render-fetch`,
gated on two things in order: (a) does its glTF path carry skinned meshes, and
(b) is `glb-render-fetch` funded at all. It is currently neither NEXT nor owed.

---

## Do-not-redo

- Do NOT inherit RC's scores. The descriptions are reusable; the verdicts were
  derived against a coaching dashboard.
- Do NOT triage by slug. Measured this pass: three of four name-based guesses
  were wrong, in both directions.
- Do NOT treat viznoir as a solved render backend. The skinned-mesh question is
  open and a matching file extension is not evidence.
- Do NOT position picdefenseio as a SauceNAO replacement. Its own listing says
  backlink discovery, not reverse-image search.
- Do NOT install anything from this document without the operator's call. Several
  entries want a key or burn credits.
