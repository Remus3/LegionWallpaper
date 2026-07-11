# LW session history archive

Deep archive for content pruned from the living docs. Nothing here is ever
rewritten - relocations are verbatim, newest batch first.

**Archival contract:**

- `WAKEUP_NOTES.md` keeps only the last 2-3 sessions at full fidelity. When it
  is pruned, the older session blocks move HERE verbatim under a
  `## Relocated YYYY-MM-DD (reason - keep last N sessions: ...)` header, and the
  WAKEUP_NOTES banner gains a pointer line naming what was archived.
- `docs/LEDGER.md` stays append-only; if it is ever pruned for size, the oldest
  item range relocates here verbatim (e.g. "items 1-N") and the LEDGER pointer
  line is updated to say so.
- `ROADMAP.md` shipped/closed entries do not accumulate - they live in the
  ledger; anything roadmap-shaped that must be preserved verbatim on prune
  lands here.

---

## Relocated 2026-07-05 (keep last 3 sessions: WAKEUP added the 2026-07-05 V3-promotion session)

# 2026-07-04 (QA Session 1 - first-pass stack live + G1 calibrated n=10)

First real pipeline runs. Installed the first-pass ML stack (py3.12,
`.venv-upscale` = torch 2.11+cu128 + spandrel on RTX 5070, `.venv-metrics` =
pyiqa 99 metrics); gallery-dl + imagehash on 3.14. Ran 10 images intake ->
first-pass -> operator-approved into `2.First Pass Done` (fiora2 + a 9-image
Found-original batch), full manifest audit trails. G1 calibrated n=10
(realesrgan-x4plus-anime fallback, USM70): MS-SSIM 0.984-0.993, LPIPS
0.047-0.144, GT LPIPS <= 0.097; tighter seeds in `AUDIT_GATES.md` 1.4 (pass
msssim >= 0.98, lpips <= 0.12).

Key: `reference_pictures` is a FR ground-truth goldmine (pHash dP=0 matches).
Found corpus (`Desktop\Found`, 121 folders) = 21 real originals + 97 still
`-pre`. Laplacian ratio is source-dependent, NOT an over-sharpen ceiling - need
a real overshoot detector.

**Do NOT redo:** the ML venv installs (done + gitignored `.venv-*/`); the 10
approved first-pass images. **Gaps:** no manifest verb for provenance/metrics
(ROADMAP NOW + spawned task); IllustrationJaNai primary weights still TODO (this
run used the ncnn fallback). **Next:** QA Session 2 - IJN primary path +
recalibrate; then the recovery campaign (149 pending, 75 `niphrimit` `-pre`).
**Queued:** artist-signature policy (watermarks on all Found originals);
LongPathsEnabled (deferred).

---

# 2026-07-04 (golden set - first-pass drift-regression harness shipped)

Commits 8e8b9a0 + 936d99b + e0a1250. Built `tools/lw_golden.py` (freeze +
regress) - the drift-detection harness, adapted for no-ground-truth (operator
ruling: no finished refs; reference of record = the current blessed IJN
first-pass output, not perfection). Flow: brainstorm -> spec
(`docs/research/GOLDEN_SET.md`) -> plan
(`docs/superpowers/plans/2026-07-04-golden-set.md`) -> TDD build; heavy deps
INJECTED so the tool is CI-testable. Operator blessed all 10, froze
`data/golden/golden_set.json` (TRACKED, pv d9ec8125, 10 cases; image bytes
gitignored + sha-pinned). Regress self-check PASSED 10/10 within epsilon (also
proves IJN upscale determinism). Suite 190 passed / 3 skipped; CI green.

Do NOT redo: the golden freeze (done); the 10 baselines. Two process scars in
LEDGER item 4: a stray `&` spawned a duplicate torch job -> pagefile OOM
(WinError 1455); nearly taskkill'd dwm/explorer/claude by trusting `nvidia-smi`
compute-apps blindly - ALWAYS verify a PID name before taskkill. Next: widen n
past 10; trial V3 DAT2 via `lw_golden regress`; add banding/JPEG-artifact
defect-class cases to the golden set.

---

# 2026-07-04 (QA Session 2 - IJN primary path live + G1 gate frozen n=10)

Commit dca6071. IllustrationJaNai V1 DAT2 (spandrel/torch) is now the PRIMARY
first-pass upscaler and the G1 gate is frozen on it. Downloaded + extracted the
V1 DAT2 weights to `tools/models/` (gitignored; OpenModelDB -> Google-Drive zip
bundle, confirm-token dance), spandrel loads DAT/4x on the RTX 5070. Built 3
committed modules (TDD, subagent slices, CI-safe via importorskip):
`lw_upscale.py` (spandrel + ncnn backends, seam-exact tiling), `lw_g1_gate.py`
(the REAL overshoot detector replacing the crude edge-diff proxy, plus
laplacian/banding/common-scale-FR/verdict), and a `lw_pipeline annotate` verb
(provenance + G1 metrics into manifests; closes task_fb503c0a). Ran the 10
approved images through IJN and G1-scored IJN vs the realesrgan-anime fallback
with identical code: **IJN wins 10/10 on MS-SSIM, LPIPS, AND halo_pct.** Froze
AUDIT_GATES 1.4; fixed a band_delta hard-fail bug (was fail>0 - it wrongly
hard-failed the BETTER upscaler 8/10 on ~0.004 noise; demoted to advisory
flag). Suite 183 passed / 2 skipped, ruff clean, pushed.

**Premise CORRECTED (operator ruling):** `reference_pictures/*_cleanup.png` are
"original-not-found" MARKERS, NOT finished ground-truth. The Session 1 "GT vs
finished ref" band is VOID - G1 scores self-metrics only; every image still
needs work. Saved to memory (`project-no-finished-ground-truth`).

**Do NOT redo:** venvs + V1 DAT2 weights (downloaded, gitignored under
`tools/models/` + `.venv-*/`); the 10 first-pass images. **Next:** golden set of
approved (input, output) pairs - the prereq for any GT-vs-approved regression,
since none exists yet; widen n past 10; trial V3detail DAT2 (its OpenModelDB
gdrive link was unresolved this session). **Queued (unchanged):** recovery
campaign (149 pending, 75 `niphrimit` `-pre`); artist-signature policy; API
keys (SauceNAO + DeviantArt).

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
