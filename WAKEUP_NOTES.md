# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18), and the 2026-07-27 loop-cycle-11 alpha-audit session (pruned 2026-07-29), and the 2026-08-01 three-repo-N=3 / hook-rule-correction session (pruned 2026-08-01), and the 2026-08-01 (evening) Stage-2-drain / L1 / dashboard-spine session (pruned 2026-08-01), and the 2026-08-01 (night) dashboard-spec-completion session (pruned 2026-08-01), and the 2026-08-01 (earlier) P3/P4/P5 + wiki-swap session and the 2026-08-01 (late) MCP-list/P1 session (both pruned 2026-08-02), and the 2026-08-02 all-five-recommendations/USM-flip/watchdog session (pruned 2026-08-09), and the 2026-08-10/11 intake/retry-degrades session + the 2026-08-11 detector-precision/recall session + the 2026-08-11 (evening) centre-overlay-inpaint session (all three pruned 2026-08-12), and the 2026-08-12 faint-mark REMOVAL lane session (pruned 2026-08-12), and the 2026-08-12 (later) overlay-registration-SCALE session (pruned 2026-08-12), and the 2026-08-12 QA-lane precision-census session (pruned 2026-08-12), and the 2026-08-12 veil-ring session (pruned 2026-08-13), and the 2026-08-12 clean-retry-degrades/one-engine session + the 2026-08-12 bare-pytest-wrong-tree session (both pruned 2026-08-16), and the 2026-08-23 queue-run/revert-lever session (pruned 2026-08-29) - keep the last 3.

---

## 2026-08-29 (latest) - a verdict per lane, and the control that was missing

Commits: f49102f + this one. Suite 2331 passed / 18 skipped, ruff clean.

- **The pair was measured against the wrong control.** `--scoped-revert` ALONE
  had never been run over the queue - the 2x2 had three cells - so the pair was
  being credited with everything scoped does by itself. Ran the fourth cell:
  `ops/runtime/clean/creditline/run_scoped/`.
- **Measure that decides a default: the mark HANDED BACK** (mask px ending
  byte-identical to untouched, which is what a revert restores). Whole revert
  272,893 px (28.13 percent) / stubs 285,870 (29.47) / **scoped 17,508 (1.80)**
  / both 29,474 (3.04). Held blobs 21 / 37 / **1** / 2. Still reading 13 / 13 /
  **2** / 2.
- **OPERATOR VERDICT: `--scoped-revert` DEFAULTS ON, `--stubs` STAYS OPT-IN.**
  Scoped is no worse than the whole revert on any of the 39 and cannot be.
  Stubs improves none and regresses four; `107-cleanup` goes clean -> legible
  `(c) SMALL`.
- **The akali blocker is dead.** All 17 blobs commit, 0 held / 0 partial, output
  byte-identical across all four configurations. The strap smear is the FILL's
  and ships in today's default; the objection came from the p40/p80 sweep cells.
- **105-cleanup 11.562 against 15.454 untouched under all four** - one sha,
  re-measured live off the 82-mask capture.
- Shipped `scoped=True`, `--no-scoped-revert` (with `--scoped-revert` still
  accepted), and `tools/lw_clean_lane_compare.py` - every configuration in one
  column at 1:1, cropped to what differs. Strips:
  `ops/runtime/clean/creditline/lanes/REVIEW.md`.
- **NEXT: nothing is queued on this lane.** Every code lever on coverage is
  shipped or falsified and both defaults are now settled. The ~35 genuinely
  blind steps need a measurement the probe cannot take.
- **C: HIT 100 PERCENT MID-SESSION and truncated `tools/lw_clean_spot.py` to 0
  bytes** (restored from git, nothing lost). 118 of the 119 GB under
  `%LOCALAPPDATA%\Temp\claude` is `C--Clockspeed`, not LW. This is now a
  correctness risk, not just housekeeping.

---

## 2026-08-29 (second session) - the blind remainder, split and spent

Five commits: dac7872, cb1475f, 827e688, d37be63, d61e382. Suite 2323/18, ruff
clean, drift_guard 0 breaches, CI green.

- **"116 blind" was a forecast. The run leaves 125, and they are TWO facts.**
  54 steps (25,618 px) have no ring pixel clearing GRAD_MIN - flat art, agreed
  by `gradient_behind` 0.59 vs 2.11, a measure that never reads the ring. No
  line to lose, so the rollback there is unemployed, not blind. `hot_band()` +
  a `surround` flat/lines field name it; no verdict moves.
- **`STUB_REACH` 6 -> 10 shipped.** Self-check survival identical (91.6
  percent), no-evidence 125 -> 119, held/committed unchanged, still_reads 13
  with no slug moving, 105-cleanup 11.562 byte-identical.
- **`STUB_LEN` swept and CLOSED - 12px WINS.** Longer rays break their own
  straight-line assumption and the self-check drops them. Do not redo.
- **The 65 remaining decomposed:** 36 no expectation obtainable, 15 mixed, 11
  where the line enters the letter next door, 3 with no cluster. MAX_CROSSINGS
  and the structure tensor drop NOTHING (measured, was asserted).
- **Two levers killed:** a derived expectation from crossing strength (within
  25 percent only 46.8 percent of the time) and reach 20 (its whole effect is
  531 px of line put back, 334 on the frame the operator called nearly
  perfect). Both refused on evidence.
- **BIGGEST RESULT, unlooked-at: `--stubs --scoped-revert` together** (never run
  as a pair before): held 37 -> 2, partial 0 -> 33, pixels given back 283,190 ->
  25,553, reads 13 -> 2, 105 unchanged. NOT proof - ahri was reader-silent with
  the mark standing and READS once the fill landed. Sheets:
  `ops/runtime/clean/creditline/run_stubs_scoped/REVIEW.md`.
- **NEXT: the operator's eye on that pair**, then whether `stubs` + `scoped`
  default ON. No code lever remains on the ~35 real holes.
- Also: `lw_ports.FORBIDDEN` + `owner_of()` carry the six-project registry.
- **OPEN, carried forward: C: is FULL.** 185.6 GB in `%LOCALAPPDATA%\Temp\claude`,
  and this session's file alone is 41 MB.

---

## 2026-08-29 - chord coverage, and two verdict bugs it exposed

Three commits: d9861e9, 0184089, 30e98cd. Suite 2311/18, ruff clean,
drift_guard 0 breaches.

- **Measured the blind spot before touching anything.** 269 of 357 steps (75.4
  percent) and 47.6 percent of repainted pixels commit on `no-evidence`. akali
  carries 4 chords over 17 blobs.
- **Both obvious levers falsified.** Perfect pairing recovers only 34 of 269.
  **Lowering GRAD_MIN makes coverage WORSE** (239 at 3.0, 252 at 2.0 vs 235) -
  the clustering merges crossings. DO NOT redo that sweep.
- **Shipped `build_stubs()`.** A lone crossing predicts a RAY: 153 of 269 blind
  steps reached, 4.5x the pairing ceiling. Self-proven against its own untouched
  frame (stubs 1,024/1,103 at median 1.019; chords 95/102 at 1.082). 825 ship.
- **Bug 1, found by the run:** `_verdict` pooled all evidence into one median,
  so 825 stubs silenced NINE chord reverts including both of 259f's. Fixed:
  pools judged separately, revert from either stands.
- **Bug 2, found by the GOLD:** the broken-line ANY-rule let ONE stub revert
  105-cleanup step 0, taking it from 11.562 back to 15.329 against 15.454
  untouched - it blocked a fill measurably moving TOWARD the operator's result.
  Fixed: stub pool keeps only the strength median (a consensus). No new knob.
- **End state:** no-evidence 269 -> 125, held 21 -> 37, still_reads 13 -> 13
  with NO slug moving either way, 105 back to 11.562 byte-identical to
  stubs-off. 146 steps decided by a stub, 16 reverts.
- **STILL OPT-IN.** The eye has not seen this lane. Sheets:
  `ops/runtime/clean/creditline/run_stubs3/`.
- **NEXT: the 116 steps carrying neither chord nor stub** - no line enters them
  that the layer can see, so no pairing or threshold reaches them. Needs a
  different mechanism; none proposed on this evidence.
- **OPEN, carried forward: C: is FULL.** 185.6 GB in `%LOCALAPPDATA%\Temp\claude`.
  Commands handed to the operator 2026-08-23, still not run.
