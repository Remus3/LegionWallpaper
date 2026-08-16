# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18), and the 2026-07-27 loop-cycle-11 alpha-audit session (pruned 2026-07-29), and the 2026-08-01 three-repo-N=3 / hook-rule-correction session (pruned 2026-08-01), and the 2026-08-01 (evening) Stage-2-drain / L1 / dashboard-spine session (pruned 2026-08-01), and the 2026-08-01 (night) dashboard-spec-completion session (pruned 2026-08-01), and the 2026-08-01 (earlier) P3/P4/P5 + wiki-swap session and the 2026-08-01 (late) MCP-list/P1 session (both pruned 2026-08-02), and the 2026-08-02 all-five-recommendations/USM-flip/watchdog session (pruned 2026-08-09), and the 2026-08-10/11 intake/retry-degrades session + the 2026-08-11 detector-precision/recall session + the 2026-08-11 (evening) centre-overlay-inpaint session (all three pruned 2026-08-12), and the 2026-08-12 faint-mark REMOVAL lane session (pruned 2026-08-12), and the 2026-08-12 (later) overlay-registration-SCALE session (pruned 2026-08-12), and the 2026-08-12 QA-lane precision-census session (pruned 2026-08-12), and the 2026-08-12 veil-ring session (pruned 2026-08-13) - keep the last 3.

---

## 2026-08-16 (latest) - IP-Adapter WINS where the LoRA lost

One commit. The untested lane flagged at the end of the 2026-08-15 session turned
out to be the answer. LEDGER 108.

- **A reference image carries identity; a trained per-champion LoRA did not.**
  Best scale **0.3**. Every adapter arm beats the no-adapter control on
  subject_cos, margin, CLIP-vs-real and luminance-vs-real.
- **The mechanism is the INVERSE of the LoRA's failure**, which is why this is
  believable rather than a lucky arm: the LoRA left subject_cos flat while
  off_cos climbed (drift toward generic anime); the adapter lifts subject_cos and
  pins off_cos. The margin gain is identity, not distractor collapse.
- **The control reproduced byte-identical** to yesterday's run at matched seeds -
  so the recipe has not drifted, and the adapter-off code path is provably inert.
- **Costs are real and are in the ledger:** sharpness falls hard and
  monotonically, and at scale >= 0.5 a second fox familiar hallucinates in. Best
  arm 0.3 is also the sharpest arm. Do not reach for a higher scale to chase
  identity without re-checking lap_var.
- **What it does NOT do:** facial structure and the red whisker markings are not
  transferred. That is expected of the GENERAL adapter (one global CLIP
  embedding) and is the specific thing plus-face should fix.
- **Provenance gap found and closed:** the general adapter + CLIP image encoder
  had been on disk since 2026-07-16, load-bearing and completely unrecorded in
  `docs/GEN_MODELS.md`. Both now recorded with real hashes, license verified live.
- **NEXT, operator-gated:** the plus-face fetch. Row is written, command is in
  `docs/GEN_MODELS.md`, sha256 + date filled after. `--ip-adapter-weight-name`
  exists so that run needs NO code change. Then re-run on animagine-xl-4.0 - this
  eval is RealVisXL-only by design and says nothing about the shipped base.
- **Still open, untouched across both sessions:** `m1-gate-fund-or-close`
  (FUND/CLOSE), the two `g1-source-adequacy` policy questions, and the
  `legacy-audit-backfill` data call.

## 2026-08-15 - gen recon triple: render capture proven, LoRA path dead

One commit, one new tracked tool. Three background agents ran in parallel while
the main window stayed free (operator restated the subagent-first directive).
LEDGER 107.

- **The operator's question was: capture 360 views of every skin from the 3D
  models as trainer data for matching aesthetics + designs per champion.** The
  answer is that capture WORKS and is cheap, and the training premise is DEAD.
  Both halves are measured, not argued.
- **No GUI / OBS / OCR / machine-control needed.** CommunityDragon serves every
  skin's own `.skn` + `_tx_cm.png` script-only, unblocked. The operator-assist
  lane stays in reserve for chromas and anything CDragon does not serve.
- **The `.skl` 404 only ever blocked WEAPON ISOLATION.** For whole-mesh renders
  it is irrelevant. Proven by the aristocrat control, recorded in the POC as an
  outright failure, which renders clean first try.
- **PRESERVED: `tools/lw_render_skn.py` + 13 tests.** The original POC code was
  LOST with an ephemeral scratchpad (`LEDGER.md:2861`); the rebuild was sitting
  in scratchpad about to be lost the same way. GPU imports are deferred so the
  camera math tests in the main env; `.venv-poc` is still required to render.
- **Ahri LoRA scored: FAILS, worse than no LoRA.** `subject_cos` flat across all
  arms, `off_cos` rising - it drifts toward generic anime, it does not learn
  Ahri. Trained on RealVisXL, not the current Animagine base. Never sampled from
  before this run.
- **Root cause, found independently by two agents:** one generic caption
  averaged over mutually contradictory skins. The proposal to capture EVERY skin
  scales exactly that failure mode.
- **NEXT (nothing is blocked on it):** base model + ControlNet + IP-Adapter is
  the stronger lane and IP-Adapter is still untested. A retried champion LoRA is
  one skin / clean captions / ~400 steps. Render capture is parked and cheap for
  the DISCRIMINATIVE consumer only - `m1-gate-fund-or-close`, still operator-gated.
- **Operator decision still open:** the FUND/CLOSE call on m1. Also unanswered -
  the two `g1-source-adequacy` policy questions and the `legacy-audit-backfill`
  data call, both untouched this session.

## 2026-08-13 - /sync-all-md pass: four stale structural facts

One commit (`b80e7cb`), docs only. Suite **1975 passed / 18 skipped** run fresh
this turn, ruff clean, hygiene trio green, drift_guard 0 breaches / 4 notes.
LEDGER 106. No ROADMAP item moved - nothing shipped but doc congruence.

- **Canonical facts established live, not read off a doc:** 1992 collected /
  1975 passed / 18 skipped; no product VERSION constant exists yet; 3 `LW-*`
  scheduled tasks Ready (matches the OPERATIONS roster of 3 registered + 2
  unregistered rows); stages 2.First Pass Done=302, 3.Cleaning Scratch=18.
- **Fixed:** README ADR list stopped at ADR-008 (ADR-009 shipped in `74a6b09`);
  ARCHITECTURE named lw_ports allocations "(monitor=8901)" while
  `tools/lw_ports.py:33-34` also pins `RUNDASH = 8900`; ARCHITECTURE's component
  map had NO `tools/lw_rundash.py` entry; OPERATIONS claimed "HTTP health
  endpoints: TBD (no ports exist)" while both read-only servers serve
  `/api/health` today.
- **Cross-reference sweep: 0 genuinely broken refs** across the 7 living docs.
  The only non-existent targets are the documented-TBD set
  (`ops/lw_supervisor.py`, `ops/runtime/health.json`, `agents/**`,
  `tests/test_bare_py_ban.py`) - all four are named as absent by the doc citing
  them. Do NOT "fix" these; they are intentional placeholders.
- **Two calls left OPEN for the operator, deliberately not applied:** (1) the
  gemini-vendor docs (`GEMINI.md`, `docs/GEMINI_AUDIT_CONFIG.md`,
  `docs/GEMINI_REVIEW_CONSUMPTION.md`, `tools/gemini_audit_prompt.md`,
  `ops/loop/{director,auditor}_prompt.md`) are still tracked as live though the
  vendor retired 2026-08-02 - CLAUDE.md keeps `gemini_audit.ps1` as the rollback
  path, so quarantining them is an operator decision, not a sync decision;
  (2) 13 `MEMORY.md` index lines exceed the 150-char cap (longest 248) - that is
  `/consolidate-memory`'s job, flagged only.
- WAKEUP already at the keep-3 limit before this entry; prune re-run at wrap.

---

## 2026-08-12 - clean-retry-degrades CLOSED: one engine per submission

One commit (`74a6b09`). Suite **1975 passed / 18 skipped** (baseline 1961 + 14
new), CI run 31659578807 green (`check` + `cv-lane`). LEDGER 105, ADR-009. The
`clean-retry-degrades` ROADMAP item is REMOVED - both halves answered, closed
entries live in the ledger per the archival contract.

- **The question was: gate the cross-engine ladder on a measured improvement, or
  drop it? Answer: DROP it.** No improvement gate is available, and that IS the
  finding. Over the 24 scored retries, seam_ssim gain tracks edit area (Pearson
  r=+0.46; mean area ratio 3.06x when a retry gains seam vs 1.61x when it does
  not) and every seam-gaining retry was rejected. Gating on seam would select
  for the biggest repaint - the `overlay_score` failure mode (LEDGER 101-103).
- **Two further blocks on any label-fitted threshold**, both read off the
  manifests this turn: the 3 adjudicated slugs' workings are GC'd off disk (the
  metric census can only score UNDECIDED slugs), and the 50 rejects are three
  BLANKET engine verdicts - identical timestamps and identical notes across the
  whole queue. Per-slug ladder spend buys a per-ENGINE decision.
- **Shipped:** `lw_pipeline.assert_ladder_allowed` + `cleaning_engines_used`.
  `save-working --tool X` exits 3 when the slug already carries cleaning
  workings from another engine, unless `--allow-ladder`. Fails closed (an
  unclassified tool counts as an engine); `operator-select` / `clean-scan` /
  `manual` / `qa` / untagged operator saves exempt; cleaning stage ONLY.
- **The engines are KEPT** - `lw_clean_sdxl` for content-bearing marks,
  `lw_clean_iopaint` as the QA-lane candidate generator. Only the automatic
  chain is gone. `.claude/commands/cleaning-pass.md` step 6 says so.
- Do NOT re-open on a seam_ssim argument, and do NOT fit a threshold on the
  undecided queue - it carries no strong labels.

---

## 2026-08-12 - bare pytest swept the wrong tree; 8 tests ran nowhere

Two commits (`eee55d6`, `26c5ae3`) plus this doc sync. Suite **1961 passed / 18
skipped** (3.14, up 3 from the new guard file), CI run 31658420160 green
(`check` + `cv-lane`). LEDGER 104. No ROADMAP item moved - this is test-infra,
not product work.

- **Triggered by the Stop hook, correctly.** The session-open banner said "CI
  green"; that was hook-reported state, not a run. `claimed_green_gate.py`
  refused the turn. Ran it, and the bare `python -m pytest -q` died at
  collection with 2 errors while `pytest tests/ -q` was green at 1958/18.
- **Cause: no pytest config at all**, so a bare invocation walked the repo root
  and swept in `tools/test_lw_clean_dekel.py` (skimage, CV venv only) and a
  vendored MCP extension's tests. `pytest.ini` pins `testpaths = tests`.
  testpaths applies only when NO path arg is given, so `pytest tests/ -q` and
  the cv-lane's explicit file arg are unaffected.
- **The real find:** with testpaths pinned, `tools/test_lw_clean_dekel.py` was
  reachable by nothing - and no CI lane named it either. 8 Dekel-solver tests
  had been executing nowhere. Added to the cv-lane, floor raised 10 -> 18.
- **Raise the cv-lane floor whenever you add a suite there.** A floor below the
  real count is how an uncollected suite hides behind a green lane;
  `tests/test_cv_lane_coverage.py` fails you if you forget.
- Do NOT hunt a regression behind that original 2-error collection - the suite
  was always green, only the invocation was wrong.
