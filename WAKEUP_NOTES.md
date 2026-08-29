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

## 2026-08-29 (latest) - chord coverage, and two verdict bugs it exposed

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

---

## 2026-08-23 - the queue run, and the revert was the lever

Five commits: 363d9e5, 4a7c047, c993009, 4dbe017, 89f55ae. Suite 2293/18, ruff
clean.

- **Ran the chain on the whole queue and looked at it.** 39 of 80 slugs carry a
  readable line; 16 held a blob, 13 still read one in their own output. The lane
  REDUCES and does not finish. Sheets: `ops/runtime/clean/creditline/run/`.
- **266f: the lane erased artwork** (the poster's gold tagline shares a row with
  the credit). Two narrower masking rules were built for it and BOTH measured
  worse; both reverted, record in `_credit_span`.
- **Second round (operator asked):** 13 reading -> 10, but at 1:1 it trades text
  for smear and degrades frames already done. No blanket second round.
- **GLYPH_PCT sweep (operator asked):** no cell clears all ten, three clear at
  none, because thickening merges strokes into one blob the rollback reverts
  whole. Knob closed.
- **`scoped_revert()` is the lever.** Band around the damaged lines, grown until
  the ordinary verdict passes. 259f clean at the INCUMBENT p88; miss-fortune
  clears at last; held 0 in all 28 cells. OPT-IN: on akali it smears the strap,
  because the layer has no chord there. **Next: chord COVERAGE.**
- **Reader-quiet overstates removal by one step** - caught twice. `still_reads`
  silence is never evidence.
- **OPEN, not fixed: C: is FULL.** `%LOCALAPPDATA%\Temp\claude` = 185.6 GB of
  never-cleaned session scratchpads (Clockspeed 133.1, one LW session 34.0,
  RC 16.4). That is the black desktop - Windows wrote a 0-byte
  TranscodedWallpaper while SPI reported success - and it turned one suite run
  RED on temp exhaustion. Deletion commands handed to the operator; not run.

---

## 2026-08-22 - mask generation: the question was MIS-POSED

Went after the standing open problem. The finding is not a tuning result.

- **The template was never failing at what it does.** It scored recall 0.405 /
  0.086 against the two gold brush masks, and every fix made things worse -
  four alpha thresholds x three dilations all landed at or below "do nothing",
  and a coherence pass was worse still, with BIGGER masks scoring worse. That is
  impossible for a mask that is merely too small, so it had to be misplaced.
  Rendering it over the frame settled it in one look: **the template finds the
  DA LOGO, the operator cleans the CREDIT LINE.** Different marks, different
  places. Every recall number was scoring a logo detector against a credit-line
  gold standard, and the hand-clean captures are PARTIAL gold - 105's capture
  leaves a real, correctly-detected logo untouched.
- **Why the template cannot find the line:** it is a median over 19 frames from
  mixed uploaders and the line carries the uploader's name, so the text averages
  out of the stack while the logo survives. Frames DO group by uploader (top
  correlation pairs are same-uploader; 37 of 81 slugs carry `-by-<uploader>-`)
  but leave-one-out neighbour templates at group sizes 3-7 do NOT beat the
  global one - too few frames to cancel the art.
- **Shipped `tools/lw_clean_creditline.py`.** The line is text, so read it.
  easyocr was already in the stack and found nothing at full-frame scale; shown
  the layout BAND, enhanced two ways and unioned, with reads joined into LINES
  before verification and approximate substring matching, it reads both:
  `SLMSHADYWAALPAPERDEVIANTAR` 0.725 and `SMALLTAVERNWALLPAPERDEVIAN`+`ARTGOM`
  0.745, and correctly nothing on the painted signature. **The hit verifies
  itself** - the string contains DEVIANTART - which is what makes it different
  in kind from the falsified residue detectors.
- **Measured:** covers **0.9995** of the operator's brush on 105; **39 of 80**
  queued slugs carry a readable line; **1 of 119** approved-clean frames fired
  (`230-cleanup`, reading `SMALLTANERNXDEVIANTART CAM` twice - looks like a real
  credit line on a frame approved as clean, so it is a question for the eye).
- **The box is the right PLACE and the wrong SHAPE:** handed the solid box the
  fill broke a line and track C's rollback reverted the step (15.45 = untouched).
  Narrowed to the GLYPHS inside the verified box - which is not the falsified
  global residue, because that measure had to decide IF a mark was there and
  this one already knows - it lands at **11.56 against 15.45 untouched and the
  operator's own 8.08**, committed, 0 of 7 spots held. The two glyph constants
  are ONE slug picking one of nine cells and are labelled as such.
- **Corrected anchor worth more than the tool:** the operator's brush is only
  **1.05 to 1.65x** the pixels their clean actually changed, on all four
  captures. Replaces the falsified 8x margin and `CONTEXT_RATIO = 5.0`.
- **Still open:** 107-class AREA marks (best 22.3 vs 23.5 untouched), the logo
  itself, and the 41 slugs with no readable line.
- **Verified:** 22 new tests, full suite **2265 passed / 18 skipped**, ruff
  clean. Doc: `docs/CLEAN_MASKGEN_2026-08-22.md`.
