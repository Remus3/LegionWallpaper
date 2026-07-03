---
description: Reconcile every Markdown doc in the repo against a single source of canonical facts, fix cross-doc drift, refresh the README in its locked style, flag broken cross-references and orphaned/stale/deprecated .md files. Use when docs have drifted (test counts, versions, coverage) or after a run of sessions, before a doc audit, or when the operator asks to "sync all md".
---

> **SUBAGENT-FIRST (standing protocol, operator 2026-06-20).** Always use subagents for substantive work; do not build solo in the main thread.
> 1. **Spec first:** a Plan/design subagent (or the Gemini director) emits the spec/plan BEFORE any code; verify it vs ground truth (grep cited file:line, `ops/runtime/health.json` when it exists, git) - never scaffold on assumptions.
> 2. **New session:** interview the Gemini director (or the operator if Gemini is down) for intent + acceptance criteria, re-probe live state, THEN build.
> 3. **Act via subagents:** worktree-isolated build agents on disjoint files (sole merger) + a read-only `verifier` subagent gate before any merge or "done".
> 4. Trivial one-line cosmetic edits may inline (refines R9). See `CLAUDE.md` "Subagent-First Protocol" + memory `feedback_subagent_first_protocol`.

The operator wants every `.md` in the repo to tell the **same story with the same numbers**. Docs drift: README says one test count, the product doc another, WAKEUP a third. This skill establishes canonical facts ONCE from authoritative sources, propagates them everywhere, refreshes the README in its locked style, and surfaces broken/orphaned docs - without rewriting history.

This is a **documentation-only** skill. It makes NO code changes, does NOT restart any LW service, does NOT touch `data/`.

**Args:**
- _(none)_ -> full reconcile, apply surgical edits, print report. **No commit.**
- `--dry-run` (or `preview`) -> report only, zero writes. Use first if unsure.
- `commit` -> after edits, stage ONLY the doc files touched + one Conventional Commit. Never `git add -A`.
- `readme` -> fast path: sections 1 + 4 + 6 + 10 only (just reconcile + rewrite the README).

Run sections in order. Surgical edits only - never full rewrites of anything except the README body (which has an explicit style contract in section 4).

---

### 1. Establish canonical facts (the whole point - do this first)

Read these authoritative sources and write the values down. Every doc must match THESE, not each other:

| Fact | Canonical source (read at runtime - never trust a doc) |
|---|---|
| Repo test count | `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" -m pytest tests/ -q --co 2>$null` -> count collected; **collect, don't trust the doc** |
| Product VERSION | TBD - product not yet defined. When LW gains an authoritative VERSION constant, read the assignment in source; cross-check the live health endpoint if a service is up |
| Product data facts (counts, coverage, registries) | TBD - product not yet defined. Recompute from the authoritative data/registries at runtime, never from a doc; **drop any `_meta` key before counting** |
| Latest session + commits | `git -C "C:/LegionWallpaper" log --oneline -15` + the top block of `WAKEUP_NOTES.md` + the highest-numbered item in `docs/LEDGER.md` |

Produce a **Canonical Facts table** in your working notes. This is the contract for sections 3-5. If a live service is down, derive values from source files and note "service offline - values from source, not /health" in the report.

### 2. Inventory the .md ecosystem

`Glob **/*.md`. Classify every hit into one bucket (exclude `python-embed/`, `node_modules/`, `.pytest_cache/`, site-packages - third-party):

- **LIVING - sync targets (surgical edits OK):** `README.md`, `CLAUDE.md` (only the one-line product reference + the `### Settled` summary - the "Active priorities" block is a static pointer, do NOT add items), `ROADMAP.md`, `BACKLOG.md`, `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`, `docs/AGENTS.md`. Extend this list as LW grows living docs (product docs TBD); a doc added here must be named in this section.
- **APPEND-ONLY - never rewrite, never reflow:** `WAKEUP_NOTES.md` (append + prune via `scripts/wakeup_prune.py` only), `docs/history_notes.md`, everything under `docs/_archive/**`, `docs/adr/**` (ADRs are immutable - add a new ADR, never edit an old one), any dated artifact (`AUDIT_*`, `PHASE_*`, `*_2026-*`), `agents/**/charter.md`, `agents/**/reports/**`. Per memory `feedback_no_history_rewrite` + `reference_archive_dir`: **only sync the living docs; never rewrite a ledger.**
- **FROZEN - do not edit (CLAUDE.md hard rule):** whatever is on the CLAUDE.md frozen list - read that list at runtime; do not assume. Read-only here.
- **INDEX:** `MEMORY.md` (index of memory files - one line per entry, <=150 chars, never write memory bodies into it) and the memory `*.md` under `C:/Users/Administrator/.claude/projects/C--LegionWallpaper/memory/`.
- **SKILL/COMMAND specs:** `.claude/commands/*.md` (tracked - LW tracks `.claude/` in git) and the `tools/*.md` helper specs (the diagnose/caveman family) - including **this skill's own file** (see section 9 self-congruence).
- **CANDIDATE - unclassified:** anything else -> section 7 disposition.

### 3. Reconcile cross-cutting facts across LIVING docs

For every fact in the section 1 table, grep all LIVING docs for stale instances and replace with the canonical value. The usual offenders:

- **Test counts** - README ("N tests"), the core product doc's status line **and** its module-map row (they drift independently), the CLAUDE.md product reference line.
- **Product VERSION** - product doc status line, CLAUDE.md product reference line. (WAKEUP carries it too but is append-only - leave it.)
- **Product data facts (counts, coverage)** - wherever cited (TBD - product not yet defined).

Rule: pick the phrasing already in the doc and swap only the number/version. Do not restructure sentences. If a doc rounds ("~3,000", "about two-thirds") keep the rounding unless it's now wrong.

### 4. README pass - locked style

The README is maintained in a deliberately locked plain-English style (RC precedent: a one-time rewrite locked the style; every later pass enforces it). **Style contract - enforce, do not "improve":**

- Audience: a smart reader who is NOT this codebase's engineer. Prose paragraphs, not bullet dumps.
- Keep the section skeleton stable once established: title+tagline -> What it does -> How it works -> <core-engine section, TBD - product not yet defined> -> Where it runs -> Project status -> More -> License. Don't add sections. (Until the first deliberate LW README rewrite locks the skeleton, treat the current README's structure as the skeleton.)
- **No session changelog, no session ids, no commit SHAs, no enumerated "then we added X" history.** README describes the *current* system, not how it got here.
- At most **one** table allowed (which one: TBD - product not yet defined). Don't add tables.
- No deep cross-machine/topology specifics, no install steps - those live in CLAUDE.md / docs.
- Only the hard numbers update (tests / versions / product facts), pulled from section 1. Prose stays prose.
- "More" links must all resolve (section 6 verifies).

If the README's structural claims still match reality, only the numbers change. If something structural genuinely changed (a capability retired, a new top-level capability), update the one relevant sentence - minimally.

### 5. Per-doc congruence pass (LIVING only)

- **CLAUDE.md** - touch ONLY: (a) the one product reference line if VERSION/facts moved; (b) the `### Settled` summary if a decision changed. The "Active priorities" block is a STATIC POINTER - per-item completion entries go to `docs/LEDGER.md` (newest-first), NEVER into CLAUDE.md (CI size-budgeted < 60KB). Leave Topology / Paths / Hard rules / everything else alone.
- **ROADMAP.md** - Now+Next ledger, highest priority at TOP. Mark shipped items DONE + SHA; ensure the top reflects the latest session from section 1. Do not delete completed items (history lives elsewhere); do not rewrite older entries.
- **BACKLOG.md** - strike (`~~...~~`) anything that shipped this period with the SHA; don't reorder. BACKLOG stays aspirational.
- **docs/ARCHITECTURE.md / OPERATIONS.md / AGENTS.md** - **structural sync only.** Verify module map / endpoints / ports / task names against the actual code & CLAUDE.md. Update a line only if code changed it. These are not changelogs - don't add session notes.
- **The core product doc** (TBD - product not yet defined) - expect it to be the highest-drift doc once it exists: reconcile its status line (VERSION + N tests + data facts), its module-map row, and its coverage numbers on every pass.
- **MEMORY.md** - verify every linked memory file exists and each line is <=150 chars; if a LIVING doc fact contradicts a memory, the memory is stale -> note it in the report (do NOT auto-edit memory bodies here; that's `/consolidate-memory`'s job - just flag).
- **Lessons** - there is no `LESSONS.md`. The lesson surface is memory `feedback_*` entries plus any future dated lesson artifacts (append-only - do NOT rewrite). If a lesson schema doc ever diverges from the code that consumes it, report it - don't edit the dated artifact.

### 6. Cross-reference integrity

For every LIVING doc, extract every relative link `](path)` and every backticked file path, and verify the target exists.

- **Referenced-but-missing** -> report each (path, the doc(s) citing it). A missing ref that lives inside a session-ledger entry or other dated prose is history: rewriting it is a `feedback_no_history_rewrite` violation for zero benefit - report, don't repoint. For missing refs in genuinely living prose: **do not silently rewrite** - surface the decision with options; only apply if the operator has a standing preference in memory/CLAUDE.md.
- **Orphaned** -> a LIVING-looking doc that nothing links to and that isn't in the section 2 living set -> section 7.
- Broken anchors / renamed files -> list them.

### 7. Other .md - update / deprecate / complete

For each CANDIDATE (and any orphan from section 6), decide and report a disposition (apply only the safe ones; surface the rest):

- **Stale but live** -> reconcile facts (section 3) if it's effectively a living doc that escaped the section 2 list; recommend adding it to this skill's section 2 list.
- **Superseded / dead** -> recommend moving to `docs/_archive/YYYY-MM-DD-<reason>/` (the quarantine pattern from memory `reference_archive_dir` - **move, never delete; reversible**). Do not move without operator confirmation unless it's already obviously dated and unreferenced.
- **Incomplete** (TODO/TBD/`<placeholder>`/empty sections) -> list the file + the gap; don't fabricate content to fill it. (An intentional "TBD - product not yet defined" placeholder is NOT a gap - leave it until the product is defined.)
- **Duplicate** (two docs claiming to be the source of truth for the same thing) -> name both, recommend which is canonical.

Never delete a `.md`. Quarantine is the only removal.

### 8. Append-only / history protection (hard invariant)

Before any write, re-confirm the target is in the LIVING set. If a fact is wrong in `WAKEUP_NOTES.md`, `docs/history_notes.md`, `docs/_archive/**`, an ADR, or any dated artifact: **do not fix it there.** History records what was true *then*. Note the discrepancy in the report and fix only the LIVING doc. The only sanctioned WAKEUP mutation is `"C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" "C:/LegionWallpaper/scripts/wakeup_prune.py" --keep 3` (idempotent; run only if WAKEUP has >3 sessions and the operator asked for a prune - otherwise just report the count).

### 9. Self-congruence

This skill ships as ONE tracked file: `.claude/commands/sync-all-md.md` - the tracked canonical IS the operative slash command. LW tracks `.claude/` in git (only machine-local pieces are gitignored); the RC-inherited scheme of a tracked `tools/` canonical plus a gitignored `.claude/` runtime mirror was collapsed to this single tracked file at port time (ADR-001), so there is no second copy to diff.

Verify the command file is committed instead: `git status --porcelain -- .claude/commands/sync-all-md.md` must print nothing. If it is dirty, the change is either this pass's own deliberate edit (stage it via the `commit` arg like any other doc) or unexplained drift (diff it against HEAD and surface the decision - do not silently keep or revert). Before reporting clean, also confirm the file satisfies the no-em-dash / no-smart-quote hard rule. Report the state. (A doc-sync skill whose own spec sits silently uncommitted, or that re-injects banned glyphs into the repo, is self-refuting.)

### 10. Final report banner

Print exactly this shape:

```
==================================================================
  /sync-all-md - md congruence pass
==================================================================
  canonical facts    : tests=<n> version=<v|TBD> product_facts=<...|TBD>
  living docs edited : <list of files + one-line what-changed each>
  facts reconciled   : <N stale numbers/versions fixed across M docs>
  readme             : <numbers-only | +1 structural line | unchanged>
  broken refs        : <N>  (genuinely-missing only)
  orphans / stale    : <N flagged>  deprecation moves proposed: <N>
  history protected  : <N stale-in-ledger noted, not edited>
  self-congruence    : <committed clean | staged this pass | drift surfaced>
  commit             : <none | docs: sync living docs - <topic> (SHA)>
==================================================================
  Decisions needing operator: <broken-ref resolutions, deprecation moves, ...>
==================================================================
```

List anything needing a human call (broken-ref resolution, deprecation moves, history discrepancies) under the bottom rule. If `--dry-run`, every "edited"/"commit" line says `(preview)` and nothing was written.

### Safety rails

- Documentation only. NO code edits, NO `data/` writes, NO service restarts.
- Never rewrite history (WAKEUP / history_notes / _archive / ADRs / dated artifacts) - section 8 is non-negotiable.
- Never touch a CLAUDE.md frozen file. Never edit a memory body (only flag stale; defer to `/consolidate-memory`).
- README: enforce the locked style contract; resist the urge to "polish" beyond fact reconciliation.
- `commit` arg: stage only the explicit doc files you edited (list them by path), never `git add -A`/`.`. Conventional Commit subject (`docs: sync living docs - <topic>`) with the standard `Co-Authored-By: Claude <model name> <noreply@anthropic.com>` trailer. Never `--amend`, never force-push, never `--no-verify`.
- Broken-ref and deprecation decisions are surfaced, not silently applied, unless the operator has a standing preference recorded in memory/CLAUDE.md.
- Preserve file encodings and line endings. Surgical edits - minimal diff.
