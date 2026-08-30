# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18), and the 2026-07-27 loop-cycle-11 alpha-audit session (pruned 2026-07-29), and the 2026-08-01 three-repo-N=3 / hook-rule-correction session (pruned 2026-08-01), and the 2026-08-01 (evening) Stage-2-drain / L1 / dashboard-spine session (pruned 2026-08-01), and the 2026-08-01 (night) dashboard-spec-completion session (pruned 2026-08-01), and the 2026-08-01 (earlier) P3/P4/P5 + wiki-swap session and the 2026-08-01 (late) MCP-list/P1 session (both pruned 2026-08-02), and the 2026-08-02 all-five-recommendations/USM-flip/watchdog session (pruned 2026-08-09), and the 2026-08-10/11 intake/retry-degrades session + the 2026-08-11 detector-precision/recall session + the 2026-08-11 (evening) centre-overlay-inpaint session (all three pruned 2026-08-12), and the 2026-08-12 faint-mark REMOVAL lane session (pruned 2026-08-12), and the 2026-08-12 (later) overlay-registration-SCALE session (pruned 2026-08-12), and the 2026-08-12 QA-lane precision-census session (pruned 2026-08-12), and the 2026-08-12 veil-ring session (pruned 2026-08-13), and the 2026-08-12 clean-retry-degrades/one-engine session + the 2026-08-12 bare-pytest-wrong-tree session (both pruned 2026-08-16), and the 2026-08-23 queue-run/revert-lever session (pruned 2026-08-29), and the 2026-08-29 chord-coverage session (pruned 2026-08-29) - keep the last 3.

---

## 2026-08-30 (second session) - both framings were wrong

One commit plus this doc sync. Suite **2408 passed / 18 skipped, exit 0** on a
fresh full run (128s, nothing deselected); baseline was 2400/18 and I added 8
tests. ruff clean repo-wide, drift_guard 0 breaches. Detail:
`docs/CLEAN_CREDITLINE_EDGES_2026-08-30.md`, LEDGER 140.

- **Built the rebuild harness first and it is exact:** every one of the 39
  recorded masks reproduces from its recorded box at `reach=0`, 39 of 39. That
  is the pre-`escaped_ink` lane, so the recorded outputs are stale by one fix -
  worth knowing before reading any of them.
- **The right edge truncates on 4 of 39, not 2.** viego-the-ruined-king (52px
  short), 261f (117), aidraw-...-watercolornessie (56), 266f (152). And
  `syndra-dlsfckr`, named in the hand-off as a right-edge case, is NOT one - its
  `.COM` is fully covered.
- **The right-edge WALK is FALSIFIED. Do not retry it.** Five rule families,
  60+ configurations: the `left_extent` mirror, band-calibrated, walk-only ink at
  lower beta, a leading-row guard, a geodesic `escaped_ink` strip, an
  edge-adjacency gate. Nothing reaches 4 of 4 without moving over half the 35
  controls; nothing reaches 3 of 4 for under a control p90 of 57px of mask growth
  into artwork. `easyocr` re-run before any filtering returns NO read right of
  the box on any of the four, and `local_ink` cannot see the tails at all.
  **The ends are not mirrors:** left is the `(c)` ring, one compact object in the
  leading; right is more of the same text in several glyphs, and the hops needed
  to cross them are exactly what walks into art.
- **The mid-line holes are the REVERT, not the mask.** Inside the mark's own row
  band the shipped mask's gaps on syndra are max 3px, and `escaped_ink` reaches
  0px inside the read box on 37 of 39. The `R` and `X` come back because the
  scoped corridor hands back 1048 byte-identical pixels that sit exactly on those
  glyphs. Known 1.80-percent handback; nobody had asked WHERE it lands.
- **Shipped, moving no pixel:** `handed_back_px` per step and `handed_back` per
  plan / lane record / summary / REVIEW.md, sorted above repaint width. Not the
  same as `reverted_px` - a commit hands back whatever the filler returned
  unchanged and `reverted_px` is 0 there. Queue total 18,835 px.
- **Also falsified, recorded:** a `.COM` suffix predicate on the read text; glyph
  pitch from the read length; and stroke contrast at the handed-back pixels as a
  legibility gate (259f keeps 84.6 percent with a CLEAN output - the corridor
  restored an art streak, not a mark).
- **Still an operator call:** refusing a corridor that hands a legible letter
  back falls through to a WHOLE revert today (28.13 percent against 1.80);
  making refusal mean COMMIT is one line plus a lane re-run.
- **THEN RE-RAN THE QUEUE UNDER THE SHIPPING DEFAULT** (LEDGER 141):
  `ops/runtime/clean/creditline/run_shipdefault/`, 39 slugs, exit 0, ~6 min,
  plain defaults. First run ever under `88e1ac7`. `box_px` identical to
  `run_ringfix` (2,057,596) so it is like for like: **mask 1,092,590 -> 948,500
  (-13.2 percent, reproducing LEDGER 139 live)**, blobs 403 -> 430, committed
  383 -> 415, partial 20 -> **15**, held 0, still_reads 0, handed back
  **17,171 px**.
- **The mid-line holes were ALREADY FIXED - there was no lever to build.**
  `syndra-dlsfckr` hands back **1048 -> 46 px** and at 1:1 the whole line, `R`
  and `X` included, is gone. The escape changed the blob structure so the
  corridor no longer crosses the glyphs.
- **`handed_back` is the ONLY field ordering this review** - `held` and
  `still_reads` are 0 on all 39. Top two checked at 1:1, both zero-residue FAILS
  that every older field called clean: `soraka` (2641px) reads `(c) .VE?ENINE`
  and a legible `.COM`; `105-cleanup` (2037px) carries a faint `L ... WALL`
  ghost. Correct first try. n=2 by eye - useful ordering, still not a gate.
- **NEXT is NOT a code task:** the operator's eye over
  `run_shipdefault/REVIEW.md`, worst first. Approve zero-residue frames into
  `4.Cleaning Done`, route the rest to manual IOPaint. ADR-008: a vision pass may
  FLAG, never approve. The right-edge four are unaffected and stay falsified.

---

## 2026-08-30 (first session) - the ring, then the damage under it

Five commits: 3c4e704, a469624, 47903a2, c8eb152, 88e1ac7, plus this doc sync.
Suite 2400 passed / 18 skipped, exit 0, nothing deselected. ruff clean,
drift_guard 0 breaches.

- **Paid the ledger the interrupted session owed** (LEDGER 134-136 for 6fffd74 /
  78a0521 / d13cdfc). `tools/lw_clean_fr.py` is NOT unwired despite nothing
  importing it - it is a PRODUCER, `--out` writes the audit and `lw_pipeline
  annotate --metrics @path` eats it. Do not "fix" the missing import.
- **Looked at all 39 credit-line sheets, flag-only (LEDGER 137).** The reader is
  near-blind: `still_reads` fired on 2, the eye read a line on 28. That
  direction was already known; the magnitude was not.
- **Fixed the (c) ring (LEDGER 138, 47903a2).** Root cause was NOT "OCR skips
  the symbol" - the mask's left edge was `box_x0 - PAD` and the mark's true left
  extent is not a constant (20-21px small type, 35 large, 43-44 at scale 1.2,
  76-96 where OCR drops leading letters). `left_extent()` measures it.
  Second separable cause fixed too: `glyph_mask`'s box-global p88 was set by the
  brightest thing in the box. Ring ink outside the mask 6923 -> 1871 px.
- **Re-ran the lane (run_ringfix) and re-triaged all 39.** Ring GONE on 28,
  residue LEGIBLE 28 -> 19, NONE 4 -> 8, held and still_reads both to 0. Only
  `107-cleanup` is unflagged outright.
- **Then fixed the damage (LEDGER 139, 88e1ac7).** Three of my framings died to
  measurement: lines are NOT cut at the seam (82.6 percent of damage is 5+ px
  deep), the rollback has NO no-chord blind spot (it fired on the worst blobs
  and bought 1.2-7.3 percent), and nothing leaks outside the mask (0 px on all
  39). Real cause: `glyph_mask` takes the top 12 percent of high-pass inside the
  box and on busy art that IS the art. `escaped_ink()` follows ink back in from
  outside and subtracts it - mask -13.2 percent, strong edges -17.0, ridges
  -16.7, ZERO registered logo ink lost.
- **NEXT: the RIGHT edge and the mid-line holes.** The re-run exposed that
  `left_extent` fixed one end of a three-ended problem - `viego-the-ruined-king`
  stops at x577 leaving `COM` intact, `261f` stops at x499, `syndra-dlsfckr`
  leaves holes mid-span. The machinery exists; mirror it.
- **Do NOT redo** (all measured, all in ROADMAP + LEDGER): the achromatic gate,
  median+k*MAD thresholding, unbounded leftward walk, whole-structure
  containment ratio, morphological separation, and "revert more" - the revert
  trade curve has no knee at any slug.
- **One operator call waiting:** `LIMB_REACH` 24 removes 17 percent of the art
  damage; 32 reaches 24 percent with still no measured mark loss; first loss at
  36. One number, pinned by a test.

---

## 2026-08-29 - the interrupted session's ledger, paid

Session was cut mid-wrap when the operator switched Claude accounts. The CODE
had all landed: `git status` clean, `origin/main` level with `main`, three
commits pushed (6fffd74, 78a0521, d13cdfc). What was missing was the /done
ritual - no LEDGER entries, no wakeup block. Both now written.

- **Suite re-verified fresh THIS session, not carried forward: 2379 passed / 18
  skipped, exit 0** (107s). Matches what d13cdfc claimed, independently
  measured.
- **LEDGER 134 / 135 / 136 appended** for the three orphaned commits: the repo
  junk audit, the global-filter flag at `save-working`, and the mask-excluded
  G1 FR with its tautology guard.
- **`tools/lw_clean_fr.py` is NOT unwired, despite nothing importing it.** It is
  a PRODUCER: it writes its audit with `--out` and `lw_pipeline annotate
  --metrics @path` consumes it. Two commands by contract, one JSON shape between
  them. Do not "fix" the missing import.
- **The disk alarm from the previous session has cleared: C: has 182.8 GB free**
  (770.5 used). The 118-of-119-GB reading that truncated `lw_clean_spot.py` to 0
  bytes does not reproduce. Nothing to clean up.
- **NEXT is unchanged and is NOT a code task: the operator's eye over the queue
  as it now ships.** Every lever is shipped or falsified and both lane defaults
  are settled, so the move is a per-slug disposition, not another sweep. The run
  under the shipping default already exists - `ops/runtime/clean/creditline/
  run_scoped/REVIEW.md`, 39 slugs, 37 clean by the plan, 1 held
  (`inkshadow-kai-sa`), 2 still reading (`akali`, `ahri`) - and nobody has looked
  at those 39 sheets. Approve what clears zero-residue into `4.Cleaning Done`;
  send the rest to the manual IOPaint lane. Per ADR-008 a vision pass may FLAG
  and shortlist but can never approve, so this genuinely waits on the operator.

---

## 2026-08-29 (third session) - a verdict per lane, and the control that was missing

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
- **NEXT: the operator's eye over the queue AS IT NOW SHIPS.** No code lever
  is left - every one is shipped or falsified and both defaults are settled -
  so the next move is a per-slug disposition, not another sweep. The run under
  the shipping default already exists: `run_scoped/REVIEW.md`, 37 clean by the
  plan, 1 held (`inkshadow-kai-sa`), 2 still reading (`akali`, `ahri`), and
  nobody has looked at those 39 sheets. Approve what clears zero-residue into
  `4.Cleaning Done`; send the rest to the manual IOPaint lane. The ~35
  genuinely blind steps need a measurement the probe cannot take.
- **C: HIT 100 PERCENT MID-SESSION and truncated `tools/lw_clean_spot.py` to 0
  bytes** (restored from git, nothing lost). 118 of the 119 GB under
  `%LOCALAPPDATA%\Temp\claude` is `C--Clockspeed`, not LW. This is now a
  correctness risk, not just housekeeping.
