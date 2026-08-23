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

## 2026-08-22 (latest) - mask generation: the question was MIS-POSED

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

---

## 2026-08-22 - track D CLOSED: the veil model does not fit these marks

Fifth and last slice. All five tracks now resolved: A, B, C shipped; E and D
falsified with evidence.

- **Premise tested BEFORE building**, which is the whole story. The veil model
  `observed = alpha*colour + (1-alpha)*content` was regressed against the
  operator's finals inside each mask - with the content known that is a straight
  line per channel, so R-squared answers "is this mark a veil at all". It fits
  NONE of the four: 105 0.49/0.59/0.52, 107 0.61/0.32/0.81 (and self-
  contradicting, three alphas 0.26/0.58/0.03 for one opacity), 209 **0.00** with
  a fitted alpha of **2.23** which is not a physical opacity, dgk 0.04.
- **209 is the clarifying case:** a painted signature is OPAQUE, so its pixels
  carry no information about what is under them. There is nothing to weaken.
- **Built it anyway** so the negative is proved rather than asserted, and
  measured: where conditioning fires it makes the frame WORSE (105 15.45 ->
  22.46, 107 23.50 -> 39.65); with a fill after it, 105 goes 8.08 -> 20.01 and
  107 is simply overwritten (12.22 either way). Where the estimator is honest
  (209, dgk) it abstains and does nothing. No cell helps.
- **Design lesson that outlives the track:** on 105 the conditioned run held 1
  of 2 blobs where the plain fill held none - the rollback worked, but the
  conditioned damage STAYED, because the pre-pass wrote into the region outside
  the rollback envelope. Any future pre-pass that writes into the mark must sit
  INSIDE the snapshot.
- **Two things worth keeping from it:** `fit_veil`, the ground-truth model test,
  and the null measured from the ring's own two annuli - without that null the
  estimator fired on ordinary unmarked art, the same failure already logged for
  absolute contrast residue. Opacity is also estimated as ONE number now, since
  it is one.
- **Not wired into any lane** and should not be. The genuine veil case - the DA
  centre overlay, 45 of 80 slugs - is already handled by the TEMPLATE pre-pass
  in `lw_clean_iopaint`, and this census supports keeping it that way.
- **Verified:** 16 new tests (RED confirmed first), full suite **2243 passed /
  18 skipped**, ruff clean. Doc:
  `docs/CLEAN_CONDITIONING_DECISION_2026-08-22.md`.

---

## 2026-08-22 - track C DONE: one spot at a time, and undo what breaks

Fourth slice of the same session. E closed, A + B + C shipped.

- **Shipped `tools/lw_clean_spot.py`**: each blob of the mark is its own heal,
  judged by the track-B chords its context touches, and a step that breaks a
  line is UNDONE. Two triggers: a chord going intact -> broken, or the median
  ratio retaining less than 0.75 of its pre-step value.
- **The second trigger exists for a physical reason** found while building: a
  semi-transparent mark ATTENUATES the lines under it, so the pre-step frame is
  often already below the intact bar and no intact -> broken transition can ever
  occur. Retention measured: operator 0.947/0.937 and lama 0.922/0.921 (both
  accepted) against heal 0.543/0.496 and membrane 0.301/0.133 (both rejected).
  0.75 is mid-gap and calibrated on EIGHT observations - stated, not hidden, and
  tolerable only because a rollback is recoverable and an approval is not.
- **Two mistakes of mine, both caught by running it on the captures:**
  (1) the first version grew each blob to the track-A stroke target - that
  target is stroke SIZE, not margin - and dgk repainted 24x its mark, scoring
  22.59 where a one-shot fill scores 2.38; (2) even a 1.6x margin lost on all
  four, because the mask handed in is ALREADY a brush mask, so the 209 anchor
  (brush vs DETECTOR BOX) does not apply. Swept: m=1.0 beats m=1.6 and m=3.0 on
  every capture. Default is now no margin.
- **Splitting a blob into disjoint stroke-sized pieces is OFF** for the same
  reason - it starves the filler of context (107 produced 34 spots, all
  committed, and moved 23.50 -> 23.08, barely cleaning at all). Consistent with
  the captures: the operator's strokes OVERLAP 30x and re-cover 97% of ground
  already brushed. A partition is a different process wearing the same clothes.
- **Result:** spot-lama 8.08 / 12.22 / 1.31 / 2.23 against the one-shot's
  7.87 / 12.45 / 1.28 / 2.38 - per-blob costs nothing and buys rollback. The
  rollback held 1 of 2 blobs on 105 and 1 of 1 on 107 for the healing-brush
  engine, and never fired on lama.
- **Honest limits:** rollback protects LINES only - on 209 and dgk there are no
  chords so it abstains and commits whatever the engine gives; and with one
  chord it protects very little (at margin 1.6 on 107 the frame went to 36.04,
  worse than untouched, and the single chord held).
- **Verified:** 16 new tests (RED confirmed first), full suite **2227 passed /
  18 skipped**, ruff clean. Doc: `docs/CLEAN_SPOT_ROLLBACK_2026-08-22.md`.
