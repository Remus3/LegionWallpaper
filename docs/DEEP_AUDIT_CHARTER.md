# DEEP AUDIT CHARTER - LW full-project audit/refactor program

> **DORMANT TEMPLATE - NOT ARMED.** This charter arms ONLY by explicit operator
> directive. The code-worth-auditing precondition is now met (product defined
> per ADR-002/ADR-003; tools/ holds 40 modules incl. lw_pipeline.py) - the
> operator directive is the sole remaining gate. Until it is given, no audit
> loop runs, no authorization below is granted, and nothing in this file
> overrides `CLAUDE.md` defaults. Ported as a template from the Riot
> Commander charter (authored there 2026-06-11) so the eventual program starts
> from a proven shape.

This is the STANDING charter for the autonomous audit loop, once armed. Each
cycle: read this file, read the synopsis for current phase state, execute the
next bounded slice, log, hand off.

## Mission

An extremely professional, exacting, complete audit + refactor + optimization +
cleanup of EVERY file in the LW tree (code, ops, tools, docs - the whole tree),
from three lenses simultaneously: as a programmer (correctness, structure,
efficiency, security, hardening), as a user (UX, latency, clarity), and as an
outside reviewer (readability, documentation, professionalism). Run to
COMPLETION across as many sessions as needed.

## Model / harness

- Fable 5, MAX effort (effortLevel xhigh set in .claude/settings.json), 1M
  context: the probe-and-set step is DONE ahead of arming - .claude/settings.json
  already sets "model": "claude-fable-5[1m]" and headless cycles run on it; no
  first-cycle probe needed.
- Adjust claude mode usage as required (caveman stays default; drop to normal
  only where the charter demands readable reporting).

## Authorizations (ALL UNSET - operator grant required per slot at arm time)

Each slot below must be explicitly granted (or struck) by the operator when
this charter is armed. None are granted today.

1. [UNSET] FROZEN-FILE edits directly authorized - the CLAUDE.md frozen list
   OPEN for this audit.
2. [UNSET] Git HISTORY may be modified; GitHub remotes may be modified;
   everything stays recoverable via GitHub version history as the explicit
   safety net.
3. [UNSET] .md REWRITES expressly allowed (full-context rewrites; make every
   .md human readable + properly commented; no-history-rewrite rule SUSPENDED
   for the program).
4. [UNSET] Relocate files (largest to smallest), alter folder structure,
   archive/remove redundant files, remove scrap files.
5. [UNSET] PRUNE ENTIRELY: (slot for product-specific stale-caveat sweeps -
   product now defined per ADR-002/ADR-003; name the LW caveat classes at arm
   time; the origin charter used this slot to purge retired-hardware and
   stale-warning classes).
6. [UNSET] BOM/encoding retro-sweep the ENTIRE project (smart-quote sweep
   folds in).
7. [UNSET] No spend limit. Many session loops expected (not 1, not 10). Do not
   stop for frivolous things. Do not gate on operator approval unless VERY
   explicitly dangerous. Questions of scope/direction go to GEMINI (cli
   back-and-forth), never wait on the operator; take the best-recommended,
   future-proof answer for the design of LW.

## Program tracks (phases; a live synopsis carries todo/done state once armed)

- P0 BASELINE: full-tree inventory (file count/sizes/runtime-use vs repo
  bloat), test+CI baseline, health probes, reference captures. Build the audit
  work-map.
- P1 STRUCTURE: folder-structure redesign where warranted; relocations;
  dead/scrap/redundant file archival or deletion; file-size + runtime-use
  evaluation; claude-context optimization (CLAUDE.md/docs bloat reduction).
- P2 CODE AUDIT: every source/doc file - correctness, security hardening,
  efficiency, integrity tests; simplify processes that cause tool-usage/CI
  friction (BOM encoding class, PS5.1 quirks, stale-pipe class). Verifiable
  findings + concrete sourcing ONLY - never rely on past memory or
  assumptions; re-probe everything live.
- P3 PRUNE SWEEPS: stale-caveat classes out; BOM/smart-quote/encoding
  retro-sweep; em-dash drift check.
- P4 [TBD - define at arm time (product now defined per ADR-002/ADR-003)] (the
  origin charter used this phase to retire live LLM call sites to
  precomputed/deterministic paths; define the LW analogue when the product has
  LLM surfaces, else strike).
- P5 [TBD - define at arm time (product now defined per ADR-002/ADR-003)]
  (origin: complete a product surface to end-of-need).
- P6 ROADMAP/BACKLOG + NEW LIFTS: drain remaining viable items; research new
  lifts; implement.
- P7 UI/UX END-TO-END: full UI & UX audit agents end to end against the real
  running product (tooling: MCP clicks - Windows-MCP / computer-use /
  chrome-devtools; research+install what is needed).
- P8 DOCS: every .md rewritten human-readable, current, properly commented;
  memory files reconciled to post-audit reality.

## Loop mechanics (variant of gemini-headless-upgrade - NOT the stock skill)

- Driver: ops/loop (controller + AHK) clears the Claude window each cycle and
  feeds the directive; repoint config directive_suffix HERE at arm time (today
  it carries the operator's current run focus, not this charter). Gemini =
  director/auditor/consultant for scope+direction questions; avoid stale
  handoffs (timestamp + sha-stamp every handoff; a handoff older than the
  current HEAD's committed state is STALE - re-derive, don't trust).
- Multi-agent fanout per cycle: orchestrator-merge pattern (disjoint worktree
  slices, verifier gate + truth-gate PROCEED before merge/commit). Validated
  fanout only.
- Scheduled tasks + AHK are authorized tools to keep the back-and-forth
  autonomous ONLY once the charter is armed.
- Per cycle: commit + push + CI green + /done + /clear within viable context
  bounds.
- LIVE SYNOPSIS on the Desktop
  (C:/Users/Administrator/Desktop/LW_DEEP_AUDIT_SYNOPSIS.md, atomic writes):
  stages/phases todo/done, gemini<->claude handoff log (append, terse), no
  repeated findings. This is the operator's morning review artifact - keep it
  current.
- Stale/fail states (claude OR gemini): reorient and continue unless genuinely
  done. Never end the program on a transient failure.

## Hard floors that SURVIVE this charter (everything else above overrides defaults)

- ASCII-only authored content (no em/en dashes, no smart quotes) stays.
- Atomic writes stay. py_compile-before-restart stays. taskkill-not-Stop-Process
  stays.
- TDD + truth-gate verification discipline stays (gate every multi-slice round).
- Do not break the live product for the operator; restart + verify health after
  runtime changes.
