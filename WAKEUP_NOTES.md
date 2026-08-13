# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18), and the 2026-07-27 loop-cycle-11 alpha-audit session (pruned 2026-07-29), and the 2026-08-01 three-repo-N=3 / hook-rule-correction session (pruned 2026-08-01), and the 2026-08-01 (evening) Stage-2-drain / L1 / dashboard-spine session (pruned 2026-08-01), and the 2026-08-01 (night) dashboard-spec-completion session (pruned 2026-08-01), and the 2026-08-01 (earlier) P3/P4/P5 + wiki-swap session and the 2026-08-01 (late) MCP-list/P1 session (both pruned 2026-08-02), and the 2026-08-02 all-five-recommendations/USM-flip/watchdog session (pruned 2026-08-09), and the 2026-08-10/11 intake/retry-degrades session + the 2026-08-11 detector-precision/recall session + the 2026-08-11 (evening) centre-overlay-inpaint session (all three pruned 2026-08-12), and the 2026-08-12 faint-mark REMOVAL lane session (pruned 2026-08-12), and the 2026-08-12 (later) overlay-registration-SCALE session (pruned 2026-08-12), and the 2026-08-12 QA-lane precision-census session (pruned 2026-08-12) - keep the last 3.

---

## 2026-08-12 (latest) - clean-retry-degrades CLOSED: one engine per submission

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

---

## 2026-08-12 - the veil ring was hiding a cliff the lane made

Four commits (`71bf503`, `d74888b`, `8766adf`, `5527059`). Suite **1958 passed /
18 skipped** (3.14), CI green. LEDGER 101-103. ROADMAP
`cleaning-detector-recall` item **(a) CLOSED**.

- **The premise was wrong, and looking at 1:1 is what caught it.** The item said
  "a blur, not a legible mark". The lane's ROI is 666x442 at deliverable scale,
  so the side-files ARE 1:1 - viewed, `mecha-ahri` has lost the nostril edge, the
  upper lip is a wash, and the mask's stair-stepped boundary shows as blocks.
- **A third of the mask was a ring, and the ring was blending a step the
  pipeline itself created.** Decomposed: strokes 17778 px + **veil ring 21205
  px** + completion 24838 px = 63821 (21.68% of ROI). Signed-distance profiles
  over six frames: the ORIGINAL has NO level step at the veil support boundary
  (|step| <= 0.9, 6 of 6 - the support is eroded to stop INSIDE the veil, so both
  sides are veiled alike), the inversion leaves **12.7-27.4**.
- **Fix at the cause, TDD RED first (24.7 levels on the fixture).**
  `veil_alpha_map` ramps the correction out over `VEIL_FEATHER = 16` px (swept:
  23.30 -> 3.37 -> **2.12** -> 1.72 -> 1.28 asymptote; smallest that clears it is
  safest, a longer ramp darkens art). `VEIL_EDGE_R` retired, ring gone.
- **Measured over the WHOLE flagged family, 33 slugs:** median mask 63821 ->
  41349 px (**35% less**), median score 0.0680 -> 0.0664, worst 0.0941 -> 0.0955,
  **33 of 33 still under the 0.15 flag**. Outside-ROI changed pixels re-measured
  OFF DISK unchanged at 6383/6679/6696. Read mask PIXELS, not coverage percent -
  the ROI shrinks with the mask, so a few slugs look flat in percent.
- **`mecha-ahri` still goes to MANUAL IOPaint** - the strokes and credit line lie
  across the nose and lip, so any auto fill invents facial structure.
- Evidence: `docs/CLEAN_VEIL_FEATHER_2026-08-12.md`. Feathered candidates in
  `ops/runtime/clean/overlay_feather/`; the `overlay_lane/` set is STALE.

- **"Skip LaMa when the pre-pass clears" was measured over all 33 in the same
  session and REJECTED.** A six-frame sample said 5 of 6; the population says
  **21 of 33** (median 0.1331, max 0.2009, and the inversion RAISES the score on
  `110-cleanup`, `270f`, `dark-cosmic-ahri`). Worse, the score lies: credit-line
  strips cut at 1:1 from the three LOWEST-scoring frames (0.076-0.084) still READ
  ("STELLASTRIA.D" plainly legible on `ahri-dmbclo0`), and the reason is
  measured - the pre-pass keeps **103 percent** of the credit line's local stroke
  contrast (median over 33; LaMa keeps 48 percent). It kills the whole-band
  CORRELATION, not the text.
- **Standing rule from that: `overlay_score` is a DETECTION flag, never a
  removal-QUALITY gate.** A frame can sit at 0.076, deep inside the clean
  distribution, and still show its artist credit line at 1:1.

- **The veil AMPLITUDE was settled in the same session (LEDGER 102).** The
  ring-pair confound is REFUTED by a control: the same objective over 31 frames
  carrying NO overlay minimises at the smallest gain (alpha 0.0133) and rises
  monotonically. But the shipped `alpha 0.1332 = raw 0.0266 x gain 5.0` sat
  EXACTLY on the old grid's last point - a boundary solution written up as an
  interior optimum; on a grid to 19.75 the objective turns at gain 3.75 ->
  **alpha 0.0999**. It barely matters: the clean-frame run is also an
  11.48-level noise floor against a ~14-level signal, so 0.09-0.13 all fit, and
  by eye on `dark-cosmic-ahri` the current value leaves neither residue nor dark
  blob. `VEIL_GAIN_GRID` -> 10.0 and `_fit_veil_gain` WARNS on a ceiling hit.
- **MATTE REBUILT on operator call (LEDGER 103) - and it went UP, not down.**
  Rebuilt from the same 19 slugs: gain **5.25** (interior, no warning), **alpha
  0.1332 -> 0.1398 (+5.0%)** - one step past the old ceiling, the OPPOSITE
  direction from the 31-frame curve. That is the SNR-1 finding made concrete:
  swap the frame set and this estimator moves 40 percent. Only the veil alpha
  changed - stroke alpha, `W` and the support are bit-identical. All 33
  candidates re-cut into `ops/runtime/clean/overlay_rebuilt/`: median score
  0.0664 -> 0.0645, worst 0.0955 -> 0.0942, 33/33 under the flag, pre-pass moves
  1-2 levels over 13-16% of the ROI, no dark blob by eye on `dark-cosmic-ahri`.
  Old matte kept in `ops/runtime/clean/_backup_2026-08-12/`; `overlay_lane/` and
  `overlay_feather/` are superseded.

**NEXT:** if a candidate ship gate is wanted, build it on a legibility measure
(mean |gray - median21| over the mask's credit-line band: original 14.32 /
pre-pass 15.97 / +LaMa 7.00 medians), not the detector score. When the matte is
next rebuilt for any reason, the wider grid applies automatically and the
warning will say whether the new fit is interior.

---
