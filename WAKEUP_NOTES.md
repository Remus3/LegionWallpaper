# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18), and the 2026-07-27 loop-cycle-11 alpha-audit session (pruned 2026-07-29), and the 2026-08-01 three-repo-N=3 / hook-rule-correction session (pruned 2026-08-01), and the 2026-08-01 (evening) Stage-2-drain / L1 / dashboard-spine session (pruned 2026-08-01), and the 2026-08-01 (night) dashboard-spec-completion session (pruned 2026-08-01), and the 2026-08-01 (earlier) P3/P4/P5 + wiki-swap session and the 2026-08-01 (late) MCP-list/P1 session (both pruned 2026-08-02), and the 2026-08-02 all-five-recommendations/USM-flip/watchdog session (pruned 2026-08-09), and the 2026-08-10/11 intake/retry-degrades session + the 2026-08-11 detector-precision/recall session + the 2026-08-11 (evening) centre-overlay-inpaint session (all three pruned 2026-08-12), and the 2026-08-12 faint-mark REMOVAL lane session (pruned 2026-08-12), and the 2026-08-12 (later) overlay-registration-SCALE session (pruned 2026-08-12), and the 2026-08-12 QA-lane precision-census session (pruned 2026-08-12), and the 2026-08-12 veil-ring session (pruned 2026-08-13), and the 2026-08-12 clean-retry-degrades/one-engine session + the 2026-08-12 bare-pytest-wrong-tree session (both pruned 2026-08-16) - keep the last 3.

---

## 2026-08-22 (latest) - track A DONE: the mark stops voting on its own treatment

Second half of the same session, after track E was closed.

- **The bug, re-measured live** (not carried from the doc): `local_gradient`
  reads the MARKED frame, and `target_tile_area` is inverse, so a loud mark buys
  itself the smallest strokes. Against the operator's four finals as truth:
  105 3.684 vs 2.878 (+28%), 107 3.179 vs 2.907 (+9%), 209 7.754 vs 2.247
  (**+245%**), dgk 5.467 vs 0.778 (**+603%**). The two SMOOTHEST captures both
  hit the 2000px tile floor - and 209 is the one the operator cleaned in ONE
  stroke, where the truth asks for 27805.
- **Shipped `tools/lw_clean_behind.py`** plus the primitive inside
  `lw_clean_tiled.local_gradient(..., exclude=)`: a first difference counts only
  when BOTH endpoints are readable, so no masked value reaches the statistic
  through either end of a gradient. With `exclude` unset it is bit-identical to
  the estimator the tile-size anchors were fitted with, asserted in the suite.
- **Census vs ground truth** (`tools/lw_clean_behind_census.py`): mean abs error
  marked **221.3%** (worst 603%) -> excluded **14.6%** (worst 27.8%). 15x. The
  membrane-on-the-estimate column scores 13.8% but is systematically LOW on all
  four (a harmonic fill has no texture), which is why the estimate is NOT what
  the statistic is taken on - predicted in the module before it was measured.
- **Wired:** `build_plan` excludes the mark by default (it was already holding
  the mask and simply not using it) and takes a `gradient=` override; the
  SIBLING case `subdivide_labels` was found by grepping the same root cause and
  fixed the same way - that gate reads a region OF the footprint, so it was
  measuring the mark almost exclusively and subdividing flat art it exists to
  leave whole. Both CLI paths pass the mark through.
- **Unlooked-for second result:** the membrane estimate of the picture behind
  the mark is EXCELLENT on smooth art and harmful on structured art - in-mask
  distance to the operator's final: dgk 49.89 -> **5.09** (LaMa gets 2.38),
  209 27.26 -> **1.95**, but 105 15.45 -> 14.67 and 107 23.50 -> **35.71**. The
  new busyness measure orders all four correctly, so the statistic gates the
  estimate. NO threshold fitted - four captures cannot calibrate one.
- **Verified:** 14 new tests (RED confirmed first), full suite **2196 passed /
  18 skipped**, ruff clean. Doc:
  `docs/CLEAN_BEHIND_THE_MARK_2026-08-22.md`.
- **Do NOT redo:** busyness on the marked frame anywhere in the stack; busyness
  on the behind-the-mark estimate; fitting a trust threshold on these four.

---

## 2026-08-22 - track E built and FALSIFIED: the fill stays LaMa

Single-track session on the operator's named PRIMARY track, the healing brush.
Built it properly, measured it against ground truth, and it loses.

- **Shipped `tools/lw_clean_heal.py`** - pure numpy + Pillow (no torch / cv2 /
  scipy, runs in the fast CI lane): run-length union-find blob labelling, a
  lossless grid tiling near the operator's measured median stroke area, an
  exemplar search scored on the VALID annulus only (the mark never votes on its
  own replacement, and no offset may read a still-marked pixel), a Poisson solve
  by conjugate gradients with Dirichlet boundary, and TWO-SIDED guidance that
  crossfades a source from each side of a thin mark in the gradient domain.
  18 tests, `tests/test_lw_clean_heal.py`, including outside-mask identity,
  determinism, seam-vs-paste, and a line-continuity test that encodes the exact
  defect that got 45 candidates rejected. Mutation-checked: disabling the
  exemplar path breaks the line test, so the suite is load-bearing.
- **Also shipped:** `tools/lw_clean_fill_bakeoff.py` (the fair one-shot engine
  comparison on the union of every captured mask), `tools/lw_clean_heal_compare.py`
  (1:1 no-resample variant sheets for the operator's eye), and
  `lw_clean_replay.py --engine {lama,heal}`.
- **Result, one-shot mean in-mask distance to the operator's accepted final:**
  105 untouched 15.45 / heal 16.45 / **lama 7.87**; 107 23.50 / 26.68 /
  **12.45**; 209 27.26 / 5.90 / **1.28**; dgk 49.89 / 5.61 / **2.38**. LaMa wins
  on all four, and the 1:1 sheets agree - the heal smears 105/107 and invents
  streaks. On 105 and 107 it scores WORSE than leaving the watermark in.
- **Why, and this is the keeper:** the corpus is PAINTED, not textured, so
  nothing repeats under translation. Best source in a 96px radius scores ring
  RMSE 26-38 against ring detail 6-38 on 105 - it explains nothing. Then both
  fallbacks fail: membrane is a blur, a forced exemplar imports foreign
  structure. The premise ("gradient blending preserves lines") is true and
  useless here: it preserves the SOURCE's lines and the source is wrong.
- **One real bug of mine, found and fixed mid-session:** the first decision rule
  fell back to membrane whenever the exemplar looked poor, which on real art is
  always - all 8 tiles on 105 took it and the fabric was lost. The rule is gone
  and the measurement is recorded in the module so it is not re-added.
- **Do NOT redo:** the healing brush as a fill. The code stays as a measured
  negative result and as a working Poisson solver; the bake-off harness stays as
  the honest way to compare any future fill.
- **Where this leaves the item:** the FILL is settled (LaMa, and now on an
  engine comparison rather than a single-engine replay). Mask generation is
  still the entire open problem, and tracks A-D are all mask-side and untouched
  by this. Decision doc: `docs/CLEAN_HEAL_DECISION_2026-08-22.md`.

---

## 2026-08-22 - cleaning: fill solved, detection open, bar set to ZERO

Long operator-driven session. Two halves of the cleaning problem separated by
measurement, and the acceptance bar raised.

- **Disposed the 566-slug cleaning corpus gate-driven** (LEDGER 122): 460 clean
  approved, 19 of 20 auto inpainted, 87 held. `4.Cleaning Done` 6 -> 485.
- **Then the operator rejected ALL 87 automated candidates** over 4 review
  rounds (45 overlay filled, the same 45 un-filled, 40 region/faint/singleton,
  7 guard survivors). Zero accepted. Two real bugs of ours fell out: the 25%
  mask-coverage guard was gated on `faint` so the region lane repainted a median
  47.6% of its ROI, and 7 slugs were DETECTOR FALSE POSITIVES flagging in-art
  text (approved unedited; the "false positives are zero" claim is overturned).
- **The operator then hand-cleaned two slugs in IOPaint and captured all 128
  steps.** That is the ground truth everything below rests on.
  - per stroke: ~0.18% of frame (105) / 0.44% (107); LaMa changes ~12% of what
    is brushed in BOTH captures; stroke size scales INVERSELY with local
    gradient, exactly as the operator said.
  - the strokes are not a sweep: 30x overlap, median pixel brushed 19 times,
    median NEW area per stroke 3.0%, and 86% of convergence lands in the last 30
    of 82 steps as the mask grows 55x.
- **REPLAY of their masks through our fill: the operator PASSED it.** So the
  FILL was never the problem - every rejection was a mask failure.
- **Built the mask SCHEDULE** (residue -> contiguous run -> pad 5x -> tight crop
  -> commit): cleaned 105 from a derived footprint, DAMAGED 107 (worse than
  doing nothing) because its footprint covers real art.
- **Detection is the open problem and contrast is dead both ways:** absolute
  residue fires on art detail; relative residue (control-band calibrated) misses
  the mark entirely - it reports NO excess on frames that still carry the
  watermark, because a semi-transparent line is not busier than the art.
- **Template + schedule** (`tools/lw_clean_overlay_schedule.py`) is the best
  result: logo gone, art intact, credit line down to a faint ghost. Still FAILS
  the new bar.
- **NEW STANDARD:** zero watermark; ghost / banding / faint all fail. Next
  session runs five tracks in parallel, PRIMARY being a **healing-brush fill**
  (exemplar + gradient-domain Poisson blending, "like photoshops healing
  brush") - deterministic, no hallucination, preserves lines by construction.
  Plan: `docs/CLEAN_NEXT_SESSION_PLAN_2026-08-22.md`.
- **Do NOT redo:** lattice tiling of any kind (it signs its own boundaries into
  the result), blanket mask escalation (destroys art), absolute or relative
  contrast residue as a starting detector, and more LaMa fill variants before
  the healing brush is tried.

- **LATE ADDITION - two more captures, and a constant of mine falsified.** The
  operator hand-cleaned both `not_border` slugs (the bucket with no ground truth
  at all): `dgk8f92-...` (583x112 block on busy art, 18 steps) and `209-cleanup`
  (painted signature on a smooth panel, ONE stroke). changed/mask across the four
  captures is 0.118 / 0.122 / 0.235 / 1.027 - it tracks the ITERATION COUNT, not
  a margin, so the "8x margin invariant" reported earlier is WRONG and
  `CONTEXT_RATIO = 5.0` is flagged in place to be derived per image. Second flaw:
  `local_gradient` is measured on the MARKED frame, so a high-contrast mark
  inflates its own busyness score (209 reads highest of the four on a smooth
  panel) - track A fixes this. Step count is a property of the MARK, not a
  parameter: 1 stroke vs 82.

---

## 2026-08-22 - clean-566 disposed gate-driven, cleaning scratch 566 -> 87

Operator answered the standing block with shape (1) (gate-driven).

- **Shipped:** `tools/lw_clean_dispose.py` + `tests/test_lw_clean_dispose.py`
  (7 tests, TDD RED-first). The driver re-decides no verdict and moves no slug
  itself - every transition is an `lw_pipeline` subprocess, so ADR-008 / ADR-009
  refusals are RECORDED and skipped, never forced; approvals carry
  `--actor tool:auto-approve`.
- **Disposition:** triage regenerated read-only first and reproduced the
  2026-08-17 split EXACTLY (460 clean / 86 qa / 20 auto over 566). Then 460
  `clean` approved, 19 of 20 `auto` inpainted (simple-lama) + approved, 87 held.
  `4.Cleaning Done` 6 -> 485, `3.Cleaning Scratch` 566 -> 87, needs_attention 0.
- **`259f`** is the 20th auto: inpainted, FAILED the G2 verify gate, fell to the
  QA queue. That is the gate working - do not "fix" it by relaxing verify.
- **Held set** with per-slug reason: `docs/cleaning_qa_queue_2026-08-22.md`
  (45 centre_overlay / 27 not_border / 12 faint_mark / 3 singletons).
- **OPEN:** the operator's 13 named `ref_*` slugs are recorded NOWHERE in the
  repo; the gate held 9 as `qa`, the other 4 were approved with the clean bucket.
  Reopen route if named: `save-working --tool operator-select` -> submit ->
  approve (no reverse stage transition exists).
- **Do NOT redo:** the disposition is not idempotent - an already-moved slug
  fails `save-working` with `not in any scratch`, which is the intended refusal.

---

## 2026-08-17 - corpus drained to cleaning, Pictures 1:1, two console-flash fixes

Operator-driven session, mostly pipeline throughput plus three shipped fixes.

- **Shipped:** `2028026` first-pass directed-crop override (`--crop-overrides`,
  `anchored_crop_box`, named sides are a PERMISSION not a demand - horizontal
  grants on a too-tall frame are dropped); `6db5443` Done-N folder is now pruned
  AT the transition (supersedes the FM-02 retention half; verified per-slug
  before delete, `PRUNE_SKIPPED` on anything unproven); `d916f9a` +
  `690ffb7` two console-flash fixes - LW-CIWatchdog ran `python.exe` every 2 min
  (now `pythonw.exe` + Hidden), LW-WeeklyHygiene had no `-WindowStyle Hidden`.
  Suite 2058 passed / 18 skipped, ruff clean, CI green.
- **Pipeline:** intaked 243 (225 `ref_*` restaged from `reference_pictures` +
  18 new operator drops), first pass 242 PASS / 1 FAIL / 0 held, approved, all
  staged to cleaning. `3.Cleaning Scratch` = **566**, `first_done` = 0,
  `2.First Pass Done` fully drained by the new prune, 0 stale folders anywhere.
- **Pictures = 555**, deduped to 0 duplicate-content pairs and 0 slugs with two
  entries; every file is in the rotator deck, 0 orphans in the owed half.
- **BLOCKED ON OPERATOR:** cleaning triage is DONE (566 rows: 460 clean / 86 qa
  / 20 auto) but the destructive half was NOT run - awaiting the gate-driven vs
  blanket-approve call, and whether `qa` stops at scratch with the named 13.
- **Do NOT redo:** the 750px thumbnail `1000040081-...-375w-2x` FAIL is
  unfixable - DeviantArt's authoritative fetch returns the same 750x437 bytes.
