# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.

---

# 2026-07-03 (session 2 - PRODUCT DEFINED: restoration pipeline v1 shipped)

Commit `1d3631b` (44 files, +7946): the staged self-auditing image restoration
pipeline. Operator's 10-folder / 4-phase scheme adopted VERBATIM (ADR-003)
plus 13 additive safety fixes; product recorded in ADR-002; operational plan
is `docs/RESTORATION_PLAN.md` (v2 - v1 archived as RESTORATION_PLAN_v1.md).

**Shipped:** `tools/lw_pipeline.py` (state machine, SAFE-MOVE, slug grammar,
manifests, 49 tests) - `tools/lw_monitor.py` + `web/monitor.html` (:8901,
Desktop "LW Monitor" shortcut, UI fixture audit PASSED, 26 tests) - 7 stage
commands (/intake /first-pass /cleaning-pass /final-pass /last-pass
/end-review /pipeline-status) - 5 research docs + state-machine spec +
monitor spec - migration: 76 intake sources + 302 reference PNGs copied+
SHA256-verified into `images/` (Desktop `need up` untouched, MIGRATED.md
marker left; operator deletes at leisure). First real scan green:
pending_intake=76, anomalies=0. Suite 147/0; verifier CONFIRM.

**Do NOT redo:** migration (done, verified); the design research (docs/
research/ is the source of truth); the DeviantArt token base36 decode is
VERIFIED working. **Next:** QA Session 1 - install .venv-upscale + lw-clean
venvs per RESTORATION_PLAN.md install checklist, run ONE image end-to-end
through /intake + /first-pass, calibrate G1 thresholds. **Queued operator
decisions:** artist-signature keep/remove policy; LongPathsEnabled (deferred).

---

# 2026-07-03 (GENESIS - operating system inherited from Riot Commander; docs-only, no product code)

Legion Wallpaper bootstrapped by cloning HOW the Riot Commander (RC) project
operates - 1:1 process port, ZERO product content. The product (some kind of
wallpaper app for the Legion machine) is deliberately NOT defined yet; the
first real work item is the scope decision (ROADMAP.md, top item).

**What was ported (process, not product):**
- `CLAUDE.md` operating rules + `.claude/` (settings, hooks, agents, commands)
  - the tier system, gates, TDD/RED-first discipline, subagent-first
  delegation, verification rituals, ASCII-only hard rule, CLAUDE.md size
  budget (under 60KB, never append ledger entries to it).
- Living-doc skeletons: `ROADMAP.md` (highest priority at TOP), `BACKLOG.md`
  (aspirational lanes), this file (newest-first hand-off), `docs/LEDGER.md`
  (append-only newest-first per-item ledger, numbering starts at 1),
  `docs/history_notes.md` (deep archive), `docs/adr/` (TEMPLATE + ADR-001).
- Runtime conventions (documented, not yet running): supervisor pattern,
  `restart_trigger.txt`, `ops/runtime/health.json`, `logs/YYYY-MM-DD.log`,
  atomic writes, py_compile-before-restart, taskkill-not-Stop-Process.
- `docs/OPERATIONS.md`: restart workflow + the LW-* scheduled-task convention
  with the standard roster (LW-Supervisor / LW-GeminiAudit / LW-WeeklyHygiene /
  LW-CIWatchdog) - example commands only, NOT YET REGISTERED.
- `docs/AGENTS.md`: the two-supervisor + 8-agent-roster PATTERN as a role
  template (gatekeeper/scheduler/ingest/testing/analyzer/ui-fallback/auditor/
  nl-parser), gate policy pattern, `agents/state/` file conventions - wiring TBD.
- `docs/DEEP_AUDIT_CHARTER.md`: RC's three-lens audit charter as a DORMANT
  template, authorization slots UNSET.

**Where things live:** repo root `C:\LegionWallpaper\`; rules in `CLAUDE.md`;
docs in `docs/`; harness in `.claude/`; canonical Python
`C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe`
(`pythonw.exe` for hooks/daemons; bare `py` is BANNED - pytest-less launcher
runtime). Do NOT touch `C:\LegionWallpaper\Claude\` - that is Claude Desktop
app data, not project content.

**What is TBD (do not invent):** the product itself (engine, rendering,
architecture, endpoints, ports); the module map; the test suite; every
scheduled task (none registered); the agent-framework wiring; the deep-audit
program (arms only by explicit operator directive once code exists).

**Decision record:** `docs/adr/ADR-001-inherit-rc-operating-system.md`
(Accepted, 2026-07-03).

**Process notes:** (1) RC product references (Daemon Slayer, dashboards,
Riot API, match DB, tailnet topology, etc.) were dropped or replaced with
explicit "TBD - product not yet defined" placeholders - if a ported rule reads
oddly abstract, that is why; the rule itself is intact. (2) The frozen-file
list starts EMPTY; files earn freeze status as the product stabilizes.
