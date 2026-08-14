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

## 2026-08-13 (latest) - /sync-all-md pass: four stale structural facts

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
