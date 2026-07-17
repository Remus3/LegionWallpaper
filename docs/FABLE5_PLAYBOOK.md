# FABLE5 PLAYBOOK - prompt pack + model ladder (2026-07-16)

Authored on Fable 5 during the ~6h access window (weekly Fable bucket at 0
percent; all-model weekly at 18 percent; Max20). Purpose: spend Fable on
judgment-heavy analysis, hand execution to Opus 4.8 sessions, and run
tonight's autonomous .md hygiene pass via the AHK loop. Operator pastes the
prompts below verbatim (P1/P2/P3), always prefixed with the shared preamble.

## 1. Budget strategy

- Fable 5 window (separate weekly bucket, currently free): burn it ONLY on
  judgment work - P1 analytical-leap audit now, then P2 headless hygiene
  tonight while the window lasts. Keep the Claude window on
  `/model claude-fable-5` so AHK cycles ride the Fable bucket.
- When the Fable window expires mid-run: switch window to Opus 4.8 and
  resume; continuity lives on disk (git + LEDGER + directive chain), so a
  model swap between cycles is safe.
- Opus 4.8 = default model for all future execution sessions (P3).
- Sonnet subagents = mechanical fan-out (batch doc edits, greps, formatting).
  Haiku subagents = polling/status only. Main thread stays on the smartest
  model; prompts must say "fan mechanical work to model: sonnet subagents".

## 2. Model + effort ladder per phase

| Phase | Model | Notes |
|---|---|---|
| Repo audit, ranking, adjudicating done-vs-stale | Fable 5 now, Opus 4.8 later | thinking high; evidence via subagents, decisions in main thread |
| Plan/spec authoring | Fable 5 now, Opus 4.8 later | high |
| Bulk .md rewrite / mechanical restructure | Sonnet subagents | low effort, batch per file |
| Code feature work (attack-plan items) | Opus 4.8 | tier rules R5-R7 apply |
| Verification / gates | session model | verifier subagent only per R7 |
| Status probes / polling | Haiku subagent | low |

Tier discipline (binding in every prompt): a .md-only session is Tier-0 BY
DEFINITION - edit + ASCII sweep + commit, NO test suite, NO restart, NO
subagent swarm per edit. Tier-1 = that module's tests. Tier-2 = full suite +
restart. Classify up only on real doubt.

## 3. Shared preamble - paste at the top of EVERY session prompt

```
GROUND TRUTH FIRST: before believing any doc claim, probe reality (git log,
docs/LEDGER.md, lw_facts pipeline counts, file existence). Every assertion of
done/stale/broken needs cited evidence: path:line, sha12, or LEDGER item.
NO GHOST-CHASING: if a probe contradicts a doc, the doc is stale - fix the
doc; never debug phantom code, and never investigate a "bug" without a
reproducing command first. RIGHT-SIZED EFFORT: classify each change
Tier-0/1/2 (CLAUDE.md R5) and verify at that tier only - a one-line doc edit
gets no suite, no restart, no swarm. ASCII only, no em/en-dashes, commit via
git commit -F <tmpfile>, push after each verified-green commit.
```

## 4. P1 - Fable analytical-leap audit (run FIRST, fresh session, ~60-90 min)

```
[shared preamble]
Mission: produce docs/ATTACK_PLAN.md - the highest-leverage 2-4 week
development plan for LW (analytical forward leap, not busywork).
Steps: (1) Evidence sweep via parallel read-only sonnet subagents over
ROADMAP.md, BACKLOG.md, docs/LEDGER.md, WAKEUP_NOTES.md,
docs/ARCHITECTURE.md, docs/RESTORATION_PLAN.md, docs/research/*.md, and live
pipeline counts. (2) Build the real state table per pipeline stage: works /
stubbed / blocking (e.g. 21 stuck in 3.Cleaning Scratch, nothing past stage
4, 16 loose in 0.Originals, aspect-ratio gap). (3) Rank candidate leaps by
throughput-unblocked-per-effort: Stage-3 final pass build, Stage-2
partial+manual lane closure, supervisor/runtime + gate automation, intake
burn, aspect conformance. (4) Write docs/ATTACK_PLAN.md: top 3-5 items, each
with goal, acceptance criteria, tier, model plan (what sonnet subagents
carry), est sessions, explicit non-goals. (5) Commit -F + push.
Decision authority yours; max ONE framed question at a genuine fork.
```

## 5. P2 - tonight's headless .md hygiene run (AHK, Fable window)

Vehicle: `/gemini-headless-upgrade` with the objective override below
(fallback if Gemini is down: `/LW-Continue` loop with the same override).
Caps and model live in `ops/loop/config.json`.

```
[shared preamble]
RUN OBJECTIVE (overrides the section 4/4b TBD slots for this run): repo .md
hygiene - remove finished content, prune redundant/expired notations,
restructure surviving item lines. NO CODE CHANGES this run.
Scope IN: ROADMAP.md, BACKLOG.md, WAKEUP_NOTES.md, README.md, GEMINI.md,
docs/ARCHITECTURE.md, docs/OPERATIONS.md, docs/RESTORATION_PLAN.md,
docs/RESTORATION_PLAN_v1.md (superseded-dupe candidate: verify, then archive
to docs/_archive/), docs/AGENTS.md, docs/DEEP_AUDIT_CHARTER.md,
docs/GEMINI_AUDIT_CONFIG.md, docs/GEMINI_REVIEW_CONSUMPTION.md,
docs/GENERATOR_SIDECAR_PLAN.md, docs/GEN_MODELS.md, docs/research/*.md.
Scope OUT (never rewrite): docs/LEDGER.md + PIPELINE_LOG.md (append-only),
docs/adr/** (immutable), docs/_archive/**, docs/history_notes.md (append-only
archive target), CLAUDE.md (operator approval only), .claude/**, logs.
Per cycle = one file (or one coherent pair):
(a) evidence pass - for every open/todo item, grep LEDGER + git log for
completion evidence; (b) DONE: delete from doc; LEDGER already holds the
record; (c) EXPIRED (superseded by ADR/LEDGER): remove, cite the superseder
in the commit message; (d) REDUNDANT across docs: keep one canonical home,
one-line pointer elsewhere; (e) restructure surviving items into consistent
grammar: id - title - state - next action - evidence link, grouped by
stage/theme; (f) history-worthy prose relocates VERBATIM to
docs/history_notes.md, never destroyed; (g) Tier-0 verify: diff re-read,
ASCII sweep, commit -F, push.
Deletion rule: NO evidence = NOT done - tag `[stale? 2026-07-16]` instead of
deleting. Cycle cap 12; stop early when a full sweep changes nothing; on a
hook/gate failure fix once, else skip the file and log it. Final cycle: run
/sync-all-md reconciliation, append ONE LEDGER entry for the whole hygiene
pass, update WAKEUP_NOTES, push.
```

## 6. P3 - future Opus 4.8 execution session template (per attack-plan item)

```
[shared preamble]
Mission: ATTACK_PLAN item N: <title>. Re-verify the item's cited evidence
still holds (probe first). Then TDD per CLAUDE.md: failing test ->
implement -> tier-appropriate verify. Subagent-first for substantive build
(worktree agents on disjoint files, verifier gate before merge); inline only
trivial edits (R9). Fan mechanical work to model: sonnet subagents.
Acceptance = the item's criteria demonstrated live, not asserted. Commit -F
+ push, LEDGER entry, WAKEUP_NOTES. Stop at the scope edge - adjacent
discoveries go to BACKLOG.md, not into this session.
```

## 7. Prompting rules that make or break these sessions

1. One mission per session; scope fence as explicit file lists.
2. Acceptance criteria AND non-goals stated in the prompt, never implied.
3. Evidence standard named (sha12 / LEDGER / path:line) - kills ghost-chasing.
4. Tier declared up front - kills over-verification of one-line edits.
5. Stop conditions + cycle caps on anything headless.
6. Smartest model in the main thread; grunt work to sonnet subagents.
7. /clear between missions; WAKEUP_NOTES carries the baton.
