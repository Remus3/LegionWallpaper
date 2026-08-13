# Legion Wallpaper - Roadmap

_Now + Next only. Highest priority at the TOP. Full history in `docs/history_notes.md`. Aspirational in `BACKLOG.md`._

---

## Open items - High priority

- **clean-retry-degrades - the cleaning stage's later iterations make the image
  WORSE than `_cleanworking_01` - NEW 2026-08-02, two witnesses.**
  Operator review of the 12-slug cleaning queue: "the iterations after `_01` just
  degrade it further which is why the `_01`s are the best result out of them so
  far." Confirmed on both slugs that survived review -
  `nguyen-ky-phuc-reyjin-leblanc-j-f1` and
  `p08e8-shadow-hunter-vayne-by-namakx-dg9ydp9-pre` - where `_01` was the
  approved result and `_02`/`_03` were rejected. So the retry loop is not just
  unhelpful past attempt 1, it is actively harmful, and every REJECT currently
  spends a pass making things worse.
  HALF 1 ANSWERED + FIXED 2026-08-10 (`2958338`). The probe is `tools/lw_clean_retry_probe.py`
  (read-only; verdict census on stdlib, metric census under the cv venv).
  Measured over the whole cleaning stage - 21 slugs, 18 with 2+ workings, 50
  rejected workings:
    * Retries won **0** of the 3 slugs the operator has adjudicated. Two settled
      on `_01`'s content, one on `_cleaninitial` (no clean at all). Resolved by
      sha256, because each winning `_04`/`_03` is an `operator-select` COPY of
      earlier content - the approving version number overstates which attempt
      actually produced the accepted pixels.
    * `_02` (always sdxl-animagine): n=15, seam_ssim better than `_01` in 1,
      worse in 14, editing 1.66x more area, moving further from the initial in
      14/15. Strict degradation, matching the operator's read.
    * `_03` (always iopaint): n=9, seam better in 6 - but repainting 2.66x the
      area of `_01`, and all 9 rejected. Its seam "win" is bought by painting
      over more of the picture, which is the detector-precision problem below,
      not a better clean.
  Root cause of the INTRA-working loop: `_auto_inpaint` builds `mask`/`base`
  once ABOVE its attempt loop and `inpaint_lama` is pure over them, so attempt 2
  recomputed bit-identical pixels and re-derived an identical verdict - pure
  spent GPU. Fix landed: `max_attempts` defaults to 1 in `process_slug`,
  `run_batch` and `--max-attempts`, pinned by
  `tests/test_lw_clean_retry_default.py`. Do NOT raise it again without making
  something vary per attempt (growing the dilation is the obvious candidate).
  Still open: the cross-engine ladder (lama -> sdxl -> iopaint) is fired on
  REJECT by the operator/skill, not by a code default, so nothing in code yet
  stops attempt 2 being spent. Decide whether the ladder should be gated on a
  measured improvement or dropped to a single engine.
  HALF 2 (`cleaning-detector-precision`) ANSWERED 2026-08-11 - **the detector is
  precise; no rule was narrowed.** Measured by `tools/lw_clean_detector_probe.py`
  over the WHOLE gated corpus (all 21 cleaning-stage slugs, detect + gate re-run
  on each `_cleaninitial`): 14 slugs gate to `auto`, and all 14 regions were then
  looked at directly - every one is an artist credit URL, handle, signature or
  credit strip, i.e. ADR-005 REMOVE content. **0 false positives.** 4 route to
  `qa` (a human decides, not a proposal) and 3 to `clean`.
  Both cited cases are stale: `vayne3` detects NOTHING now (n=0; the bare-`@`
  narrowing already closed it, and the team logos never produced a box), and
  `p08e8`'s fire is the real `@namakxin` signature whose removal the operator
  APPROVED - its `_cleandone` differs from `_cleaninitial` by 65122 px. Same
  correction for `nguyen-ky-phuc` (9719 px). A REJECT note is a WEAK label - it
  lands on one working's pixels; the strong label is the APPROVE_CLEAN sha256.
  Of the 3 adjudicated slugs exactly one (`vayne3`) settled on uncleaned pixels,
  and the detector proposes nothing on it.
  Shipped instead of a narrowing: `tests/test_lw_clean_detector_precision.py`
  pins all 21 measured rows (real OCR strings + geometry) to their verdict, plus
  a KEEP-set test asserting no measured KEEP slug may ever become `auto`.
  Evidence: `docs/CLEAN_DETECTOR_PRECISION_2026-08-11.md`; LEDGER 85 + 90.

- **cleaning-detector-recall - the detector MISSES marks: 14 confirmed false
  negatives, ~12 percent of the `clean` verdicts - NEW 2026-08-11, measured.**
  The mirror of the precision census, and the reason precision alone was not an
  answer. Population: all 302 `_firstdone` images in `2.First Pass Done` (the
  21-slug cleaning queue CANNOT answer recall - it is this detector's own 2026-
  07-16 `auto` output, so scoring it there is circular). Gate verdicts: 27
  `auto` / 46 `qa` / 229 `clean`. The 229 `clean` were split into 4 strata; S1-S3
  (17 images) were censused in full and S4 (212, no box at any conf) sampled at
  n=14. Confirmed by eye: **14 false negatives** (13 of them in S1-S3),
  extrapolating to ~28 of 229 (~12 percent), wide interval.
  ROOT CAUSE, measured: **11 of the 14 are ONE object** - the semi-transparent
  DeviantArt centre overlay. It fails on three axes at once: YOLO scores it
  0.11-0.25 against a 0.35 detect floor (2 carry no box even at 0.10), OCR reads
  it as garble so `is_watermark_text` never sees "deviantart", and its centroid
  is mid-frame so even a boxed one lands on `qa/not_border`. The other 3 are a
  thin painted signature (2; YOLO gives one of them NO box at any conf) and an
  artist wordmark placed away from the bottom band (1).
  DO NOT "fix" this by weakening `is_lol_logo`: the wordmark KEEP rule fired on
  all 4 S1 misses and looks guilty, but in every one the missed mark ALSO had no
  box above the floor, so removing the rule catches nothing and re-opens the
  false positives that are currently zero. DO NOT simply drop the conf floor
  either - the low-conf box is a good FLAG signal (13 of 17 low-conf clean
  images are real misses, ~76 percent) but a bad AUTO signal.
  DETECTION HALF SHIPPED 2026-08-11 - **gate v3, `clean` 229 -> 214 over the
  live 302-image corpus.** `tools/lw_clean_overlay.py` median-stacks the
  high-pass of frames that carry the overlay into a template (the mark is the
  same pixels in the same place, so the art cancels and the logo + URL come out
  legible) and scores a frame by masked normalized correlation with a tight
  shift search. Three measured decisions, not guesses: clip the high-pass at
  +-8 levels (positive median 0.112 -> 0.220 leave-one-ARTIST-out), search
  +-3.0% h / +-1.6% w (weakest positive -0.02 -> 0.100), and keep that window
  TIGHT (a +-90/+-200px search lifts CLEAN frames to 0.095 faster than it lifts
  positives). `OVERLAY_SCORE_MIN = 0.15` is calibrated: 15 clean images flip to
  `qa`, all 15 verified real marks, ZERO false; at 0.12 three carry no mark.
  Live re-gate: 38 rows changed - 15 `clean` -> `qa/centre_overlay` (including
  the two `lol_logo` cases), 22 `qa` -> a better reason, and 1 `auto` -> `qa`
  (`239f` carries a banner AND an overlay, so auto would have left the overlay).
  Invariants: the flag can only produce `qa`, never `auto` (an unattended edit
  driven by a correlation score would spend the 0-false-positive precision), and
  it sits above the `n == 0` and `lol_logo` rules but below `watermark_ocr`.
  The template is a derivative of a third party's watermark: it lives in
  `ops/runtime/clean/` (gitignored), is rebuilt from the 19 verified slugs
  listed in the doc, and a MISSING template means the flag is simply off (v2
  behaviour exactly), which is how CI runs.
  REMOVAL HALF LANDED 2026-08-11, PARTIAL AND HONEST ABOUT IT: `estimate_matte`
  + `remove_overlay` recover a continuous alpha from the collection and INVERT
  the matting equation (`J = (I - aW)/(1-a)`), so the reconstruction is faithful
  - no fill, no hallucination, outside-region identity by construction. Measured
  over the 19 confirmed frames: detector score **median 0.565 -> 0.112, 17 of 19
  under the flag**. Method: register -> interpolate a background seed DOWN
  COLUMNS (rows biased alpha 20 percent low; a median seed is R&D method 4's
  recorded failure) -> alpha shape = median of `(I-J)/(W-J)` -> ONE global gain
  fitted against the detector's own post-removal score (grid optimum 2.0,
  interior: 1.0 -> 0.258, 2.0 -> 0.120, 3.0 -> 0.166).
  TWO DEAD ENDS, MEASURED, do not redo: a per-pixel least-squares fit of the
  matting equation reaches only **R^2 0.10** on this corpus (the background-seed
  error exceeds the mark, so an R^2 gate either drops 93 percent of the mark or
  lets art through, and spatial pooling made it worse); and re-estimating W PER
  PIXEL **diverges** (mean post-removal score 0.149 -> 0.174 -> 0.254, W drifting
  154 -> 87) because alpha and W trade off without a prior.
  **The mark is REDUCED, NOT ERASED** - at 1:1 a faint ghost survives on every
  frame. So it ships as a QA-lane candidate generator
  (`--build-overlay-matte` / `--remove-overlay`, writing a candidate plus a
  before/after JSON and PRINTING the save-working/submit commands), never auto,
  never auto-approved.
  **CORRECTION (same session, before wrap): matting-Laplacian + IRLS ALREADY EXIST and were measured to CAP.** `tools/lw_clean_dekel.py` (LEDGER 29, commit `bad25c8`) is a full Dekel - Levin closed-form matte, IRLS alternating minimisation, sub-pixel phase-correlation alignment, filled alpha init - and it leaves a legible dark-stroke ghost for a structural reason: the mark is stylised white-fill PLUS dark-outline text, which a single achromatic W cannot invert, and the residual is mark stroke entangled with real art. The shipped answer to that ghost is LEDGER 30, `tools/lw_clean_iopaint.py`: masked LaMa with a COMPLETE mask that covers the dark OUTLINE, not just the bright fill, seeded by a cross-image filled matte. So the next step for the centre overlay is to feed THIS matte into that mask builder - not to rebuild the algebra.
  INPAINT HALF LANDED 2026-08-11 (LEDGER 95): the matte now SEEDS the LaMa mask.
  `lw_clean_iopaint.py --overlay` registers the frame, runs the algebraic
  pre-pass, thresholds the matte into a mask (open -> density speck filter ->
  dilate -> bbox ROI), completes it with THIS frame's own residual inside a gate
  (7px across the strokes, 40px ALONG the credit line, bright-only sideways
  because the nearest art is a dark lip line), and runs ONE LaMa pass. Removal
  needs a WIDER band than detection - the logo's top edge sits at y/h 0.506 vs
  the detector band's 0.55 - so `REMOVAL_BAND = (0.45, 0.85)` and a separate
  `*_wide.npz` pair exist; the detector's calibrated `BAND` was NOT moved.
  Measured over all 32 flagged slugs: detector score median **0.310 -> 0.069**,
  worst 0.696 -> 0.115, **32 of 32 under the 0.15 flag** (was 0 of 32). By eye the
  CREDIT LINE clears completely on busy art; the logo's flat veil survives on
  smooth art. Evidence `docs/CLEAN_OVERLAY_INPAINT_2026-08-11.md`, candidates in
  `ops/runtime/clean/overlay_lane/`.
  VEIL HALF LANDED 2026-08-11 (LEDGER 96): `estimate_veil` recovers the logo's
  FLAT interior, which the high-pass template cannot see (matte alpha there was
  exactly 0.0). Whitening against a background window wider than the veil, a
  CONSENSUS low quartile across the collection instead of the median, a support
  that is opened + closed and deliberately stops ~10px inside the true edge, and
  the amplitude CALIBRATED against the veil's own boundary step: recovered
  **alpha 0.133** (an interior optimum), matching the ~0.14 read directly off the
  step. The veil rides in the matte beside the stroke alpha, is applied by the
  INVERSION, and only a 9px ring at its boundary is handed to LaMa - never the
  310x240px interior. Re-run over the 32: median 0.310 -> 0.068, 32/32 under the
  flag, and by eye `245f` / `miss-fortune` come back clean where part 1 left a
  polygon.
  FAINT-MARK HALF LANDED 2026-08-11 (LEDGER 97) - **gate v4 closes (b) and (c)
  together, and it needed no new model.** The census's "no box at any conf"
  claim was measured at ITS OWN 0.10 sweep floor, not at any confidence: swept
  to 0.02 all four remaining misses carry a YOLO box ON THE MARK -
  `110-cleanup` 0.1366, `p2402-kda-evelynn` 0.1228, `karthasbasefinal` 0.1135,
  `dragon-slayer-pantheon` **0.0522**. The production floor is 0.35, so every
  one was discarded before `gate_decision` ran. `detect_image` now runs YOLO
  ONCE at `FAINT_CONF_MIN` and splits at `DETECT_CONF` into `yolo` + `faint`
  (free, not a second inference - NMS never suppresses a box with a weaker one,
  measured identical on 39 of 39 firstdones), and `gate_decision` applies the
  flag as a POST-PASS over the v3 ladder.
  **The post-pass placement is the safety argument, not a style choice.** Two of
  the misses have no confident box, so an ORDERED rule would sit above `n == 0`
  - which is above `bottom_banner` / `corner_mark` too - and 7 currently-`auto`
  live images carry a qualifying faint box. Those 7 would have silently
  demoted. The post-pass is provably incapable of it: it only rewrites `clean`
  -> `qa`, and leaves an existing `qa` reason alone (21 live rows) because the
  ladder's reason is more specific than `faint_mark`.
  Two calibrated constants. `FAINT_CONF_MIN = 0.05`, swept over the live 302:
  floor 0.10 -> 3 flips 3 real 0 false; 0.07 -> 4 flips 3 real 1 false; 0.05 ->
  5 flips 4 real 1 false. 0.05 ships because it is the ONLY setting reaching the
  0.0522 signature; 0.10 is the zero-false alternative, one constant away.
  `FAINT_MIN_W_FRAC = 0.05` narrows the noisy tier on one prior - a credit line
  is WIDE - and the widths separate with nothing in the gap (real 0.076 / 0.100
  / 0.157 / 0.176 vs art 0.009 / 0.021 / 0.033). The prior is NOT universal and
  is not claimed to be: it would reject 4 of 28 live `auto` boxes and 2 of 65
  `qa` boxes (small square-ish marks), and the one false flag it admits is 0.154
  wide.
  LIVE RESULT: 26 auto / 62 qa / 214 clean -> **26 auto / 67 qa / 209 clean**.
  Exactly 5 rows change, all `clean` -> `qa/faint_mark`, NO auto lost, and each
  was cropped and looked at - 4 real (`SMALLTAVERNX.DEVIANTART.COM`, `NAMAKXI N
  P&M 2402`, and the "Alex Flores" signature on both alexflores frames), 1 false
  (`dbwtlkx-eeb94ce2`, blurred stonework). On the KEEP side `--corpus cleaning`
  produces ZERO `faint_mark` rows and all 14 `auto` proposals stand.
  DEAD ENDS, MEASURED, do not redo: **tiled / SAHI inference is WORSE, not
  better** (karthas's signature scored 0.1135 full-frame and VANISHED in the
  tiles; p2402 lost its wordmark box and gained a 0.4613 box on unrelated art) -
  the weights were trained on whole frames and the context is load-bearing;
  **EasyOCR on a brush signature** returns nothing or garble at confidence 0.00
  at 1x, 2x AND 4x; and a **per-artist signature template** was deliberately NOT
  built - the corpus holds exactly 2 alexflores images and both are known, so a
  1-frame template is a lookup table for a set of size 2, not a detector.
  Pinned by `tests/test_lw_clean_faint_mark.py` (25 tests), including the one
  false flag, pinned as a row so it stays visible rather than folded into a rate.
  FAINT REMOVAL LANDED 2026-08-12 (LEDGER 98) - closes (e). `lw_clean_iopaint.py
  --faint`. **The first thing measured is that the family is NOT one object**,
  unlike the 32-slug overlay: 2 brush signatures the lane CLEANS, 1 wordmark on
  busy art it REFUSES to the manual lane, 1 DA overlay it DEFERS to `--overlay`,
  and the known false flag, which costs a 0.8 percent mask - a near no-op.
  Three new things over the existing masked-LaMa path (everything else reused
  whole - same mask builder, paste-back, outside-ROI tripwire, never auto):
  (1) the ROI is DERIVED from the detector's own sub-floor boxes, extended by
  any OCR box that OVERLAPS one (p2402's YOLO box stops at x=2348 while OCR
  reads the wordmark to x=2482); overlap is required, not proximity, because
  both alexflores frames carry the KEPT LoL wordmark in the opposite corner.
  (2) `FAINT_BRIGHT_THR` 42 vs the banner default 10 - painted art reads above
  +10 from its own local median, so at the default the signature mask swallows
  the picture (karthas 32.6 percent coverage at 10 -> 14.3 at 42; by eye one
  cloud streak still survives at 34 and none at 42). (3) two refusals plus an
  outcome check: `FAINT_COVERAGE_MAX` 25 (p2402 masks 33.4 percent - refused
  BEFORE the GPU, mask left on disk, manual launch line printed),
  `FAINT_OVERLAY_DEFER` 0.10 - a MEASUREMENT, not a fit: over the 209 clean
  firstdones the overlay score runs p50 0.0596 / p90 0.0770 / p99 0.1042 / max
  0.1213, the four non-overlay flags score 0.048-0.064 and `110-cleanup` scores
  0.109 - and a post-pass RE-DETECT on the candidate that reports a surviving
  box as `status: residual` (coverage is a proxy; the detector is the
  measurement).
  VERIFIED: karthas CLEANED 14.1 percent / 4570 px changed, dragon-slayer
  CLEANED 22.1 / 6774, dbwtlkx CLEANED 0.8 / 936, p2402 MANUAL, 110-cleanup
  DEFER - and **0 changed pixels outside the ROI on all three**, re-measured
  from the files on disk rather than taken from the in-process tripwire. Both
  signatures cropped and looked at: gone, background continuous, the only cost a
  soft patch where a bright art fleck fell inside dragon-slayer's mask.
  DEAD ENDS, MEASURED: the dark-outline adjacency gate does NOT separate p2402
  (the art's own crevices satisfy it at every reach - r4/r7/r11 -> 30.9/32.8/
  34.4 percent, blob intact); the faint lane on a LOW-alpha DA overlay is
  structurally wrong, not untuned (110's credit line stays legible at 19.0
  percent, chroma adds nothing at 19.9, and its overlay score goes UP 0.1090 ->
  0.1203); and a `--pad 260` overlay run on 110 fixes the ROI clipping but still
  leaves the line legible at 0.109 -> 0.1031, because the binding constraint
  there is REGISTRATION (this frame correlates at 0.109 against the flagged
  family's 0.310 median), which belongs to the overlay item.
  Pinned by `tests/test_lw_clean_faint_lane.py` (25 tests).
  REGISTRATION FIXED 2026-08-12 (LEDGER 99) - **`110-cleanup` now CLEARS, and it
  was never a one-image fix.** `best_shift` registers TRANSLATION only; the
  overlay is composited at a fixed size on the DA-served image and a firstdone is
  that image resampled to 2560x1440, so a frame from a different source
  resolution carries the mark at a different PIXEL size that no shift can align.
  Swept a template scale over every flagged slug under 0.25 plus the case: EXACTLY
  TWO are mismatched and both at the SAME 1.12 - `110-cleanup` 0.1090 -> 0.5052
  and `122` 0.1696 -> 0.6542 - both landing in the range the well-registered
  frames occupy (mecha-ahri 0.696, 123f 0.635). Everything else peaks at 1.00.
  TWO BOUNDARIES, both measured. (1) **The scale search is for REMOVAL, never for
  the gate:** a max-over-scales lifts the clean frame
  `wallpapersden-...-sejuani` 0.1213 -> 0.1537, OVER the 0.15 flag - a false
  positive manufactured by the search, the same lesson the shift window learned.
  `overlay_score` is untouched and a test asserts it never grows a scale
  parameter. (2) **A non-native scale must be DECISIVE:** correctly-registered
  frames wobble up to 1.22x under a scale search (270f), the two real ones come
  in at 3.86x and 4.63x, so `SCALE_ACCEPT_RATIO = 2.0` sits far from both and a
  refusal keeps scale 1.0 - a wrong scale is a wrong edit, a refused one is only
  today's behaviour.
  BLAST RADIUS: over all 32 `centre_overlay` slugs plus 110-cleanup, **2
  re-register and 31 register EXACTLY as before** (same shift, scale 1.0), and
  `scale2d_centered` returns its input untouched at 1.0 so those 31 take a
  bit-identical pixel path - the LEDGER 95/96 candidates stand. Spot-checked live:
  mecha-ahri 0.6958 -> 0.0737, 245f 0.5858 -> 0.0903.
  RESULT: 110-cleanup 0.1090 -> **0.0868** and 122 0.1696 -> **0.0941**, both
  registered at shift (24,-1) scale 1.12, and by eye the credit line is GONE on
  both. Every changed pixel on all four verified frames falls inside one of the
  lane's two editors (the inversion's band or LaMa's ROI) - unexplained 0.
  Note 122 already had a candidate from the LEDGER 95/96 pass produced at the
  WRONG scale; a correct-scale one was written to
  `ops/runtime/clean/overlay_scale/122/` during this verification, so take that
  one - the stale candidate is still in `overlay_lane/`. 110-cleanup's gate verdict is unchanged
  and still `qa/faint_mark` (detection score 0.109, under the 0.15 flag, and
  detection did not gain the search) - `FAINT_OVERLAY_DEFER` is what routes it,
  so the chain completes without moving a gate threshold.
  (d) CLOSED 2026-08-12 - **the QA lane is 94 percent real work, and no threshold
  moves.** All 67 `qa` rows of the live gate-v4 corpus were labelled BY EYE from
  crops of what each row actually flagged (`tools/lw_clean_qa_crops.py`, contact
  sheets in `ops/runtime/clean/qa_precision/`, ambiguous cells re-cut at 1:1/2x).
  Region precision (is the BOXED thing a mark) **62/67 = 92.5 percent**; frame
  precision (does the frame carry a mark anywhere, i.e. was the routing right)
  **63/67 = 94.0 percent**. Per reason, region: `centre_overlay` **32/32**,
  `not_border` 25/28, `faint_mark` 4/5, `low_conf` 1/1, `area_too_large` 0/1.
  The one row where the two disagree is the finding: `258-cleanup` boxes its
  letterbox bars (junk) but DOES carry a `TYSIUUUL.DEVIANTART.COM` credit line at
  `overlay_score` 0.1254, just under the 0.15 flag - right for the wrong reason.
  The 4 genuinely mark-free frames are `177-cleanup` (jersey logo + "FAKER"
  nameplate), `186-cleanup` (the poster's own "unto DARKNESS/LIGHT" typography),
  `193-cleanup` (a painted snowflake) and `dbwtlkx-eeb94ce2` (brick texture at
  conf 0.0765). DO NOT tighten on them: their `conf_max` 0.72-0.79, `n_boxes`,
  `area_pct` and `ocr_hit` all sit inside the true-positive range, so every cut
  that drops them drops real marks too. Detail `docs/CLEAN_QA_PRECISION_2026-08-12.md`.
  (a) CLOSED 2026-08-12 - **the mask WAS too wide, and the excess was a ring the
  lane added to hide a cliff it had created itself.** The item recorded "a blur,
  not a legible mark"; at 1:1 (the ROI is 666x442 at deliverable scale, so the
  side-files ARE 1:1) it is structural damage - nostril edge gone, upper lip a
  wash, mask blocks visible. Decomposed, the mask was strokes 17778 px + **veil
  ring 21205 px** + completion 24838 px. Over six frames the ORIGINAL carries no
  level step at the veil support boundary (|step| <= 0.9, 6 of 6 - the support is
  eroded to stop inside the veil) while the inversion leaves 12.7-27.4, so the
  hard-edged correction MANUFACTURED the step the ring was blending.
  `veil_alpha_map` now ramps the correction to zero over `VEIL_FEATHER = 16` px
  outside the support (swept knee: introduced discontinuity 23.30 -> 2.12 -> 1.28
  asymptote) and the ring is retired. Re-run over the whole flagged family (33
  slugs): median mask 63821 -> 41349 px (35% less), median score 0.0680 ->
  0.0664, 33 of 33 still under the flag. Suite 1957 passed / 18 skipped. DO NOT re-add the ring (test-pinned)
  and DO NOT read `hf_keep` as the damage signal (mecha-ahri is mid-pack at
  0.452). Detail `docs/CLEAN_VEIL_FEATHER_2026-08-12.md`.
  STILL OPEN: (f) `p2402-kda-evelynn` is queued for the MANUAL IOPaint lane and
  nothing automates it - a stylised wordmark on busy art that no threshold
  separates; **`mecha-ahri` now joins it** (the logo strokes and credit line lie
  across the nose and upper lip, so any automatic fill invents facial structure).
  MEASURED LEAD, not shipped: the algebraic pre-pass alone already clears the
  0.15 flag on 5 of 6 frames (0.084-0.156), so "skip LaMa when the pre-pass
  clears" is worth measuring over all 32.
  Evidence: `docs/CLEAN_QA_PRECISION_2026-08-12.md` +
  `docs/CLEAN_OVERLAY_SCALE_2026-08-12.md` +
  `docs/CLEAN_FAINT_LANE_2026-08-12.md` +
  `docs/CLEAN_FAINT_MARK_2026-08-11.md` +
  `docs/CLEAN_OVERLAY_DETECTOR_2026-08-11.md` +
  `docs/CLEAN_DETECTOR_RECALL_2026-08-11.md`; census tool
  `tools/lw_clean_detector_probe.py --corpus firstdone`.

- **manifest-hash-provenance - CLOSED 2026-08-01 (LEDGER 83 + 84). Nothing open.**
  `scan --verify` reports 0 mismatches and 0 milestone files go unchecked; all
  726 have a recorded hash that matches disk. A source replaced outside a
  transition is now recorded with an appended REPLACE_SOURCE (the INTAKE hash is
  never rewritten), `verify` resolves a file's expected hash from its LATEST
  transition by timestamp, and a milestone is identified by slug + stage + phase
  + version rather than by filename - so a replacement that changes container
  format stays checked instead of going silent.
  Kept here because two things must not be un-learned: (1) the ordering bug and
  the extension blind spot were both found only by investigating a single noisy
  row (vayne3) rather than clearing it - 9 of the original 32 mismatches were the
  ordering bug and 9 more files were unverifiable entirely; (2) the backfill tool
  REFUSES to run unscoped, which is what stopped an unexplained anomaly being
  laundered into recorded history.
  Do-not-redo: do NOT reintroduce filename keying anywhere that compares against
  a manifest, and do NOT record a REPLACE_SOURCE for a drift nobody has explained
  - that converts a finding into history.
  Evidence: LEDGER 83 + 84; `docs/WIKI_SWAP_22_2026-08-01.md`.

_Shipped/closed entries move to `docs/LEDGER.md` (append-only). Only open/in-flight work stays below, highest priority first. Sequencing for the next 2-4 weeks: `docs/ATTACK_PLAN.md`. Item grammar: id - title - state - next action - evidence link._

- **gemini-removal - REVERSIBLE HALF LANDED 2026-08-02. The loop is Claude-only
  and self-adjudicating by default; the vendor is two config keys away.**
  LW had no adjudicator key to flip, so the removal had to BUILD the seam RC
  already had. Landed: `oracle_backend()` / `claude_oracle()` / `oracle()` in
  `loop_controller.py`; `director()` and `auditor()` dispatch through it; and
  `director_backend` + `auditor_backend` ship as `claude`. The Claude oracle is
  READ-ONLY on purpose (`--permission-mode plan`, NOT the executor's
  `bypassPermissions`) - an adjudicator that can write is not an adjudicator.
  An unknown backend value resolves to `claude`: never a crash, and never
  silently back to the vendor being removed.
  **ROLLBACK IS TWO KEYS.** Nothing was deleted - `gemini()`, `_gemini_call()`,
  `gemini_model`, `gemini_cmd`, `gemini_price_per_mtok`, `ceiling_usd`,
  `tools/gemini_audit.ps1` and both prompt templates all stay, the same posture
  the `channel` flip took (LEDGER 40). `ceiling_usd` remains a real rail and
  simply reads $0 while the Claude backend is in play.
  Next (the SWEEP, deliberately not bundled): physically delete the Gemini call
  path, the vendor references in the prompt templates, `gemini_price_per_mtok`
  and the `GEMINI_USD` accounting - but only after the Claude oracle has
  authored directives on a live multi-cycle run. Until then the rollback must
  stay reachable. `LW-GeminiAudit` is DROPPED from the scheduled-task roster
  (`docs/OPERATIONS.md`); it was never registered, so nothing was disabled.
  Why the shape was different here: LW has no adjudicator
  key at all - Gemini was structurally the DIRECTOR and AUDITOR via
  `gemini_model`, `gemini_cmd`, `director_prompt.md`, `auditor_prompt.md`,
  `tools/gemini_audit.ps1`, the `ceiling_usd` accounting, and the mutex hold at
  the mutex hold. Removing it meant replacing what AUTHORS each cycle's
  directive, not switching a backend behind a flag that already existed.
  Supporting evidence from LW's own runs: a read-only Claude verifier refuted a
  Claude slice on a false behavior-identical claim, and a second refuted another
  on a cache-eviction regression a 530-line test file missed - same vendor, both
  caught, because the grader was adversarial and independent rather than
  differently-branded. Vendor diversity was not what was catching errors.
  Do-not-redo: do NOT delete `GEMINI_MUTEX` from `winmutex.py` - it is
  byte-identical-by-contract with RC, deleting it needs a three-way re-pin, and
  the gemini rollback path still consumes it. Do NOT rename the `gemini.ready`
  IPC sentinel - that is the AHK bridge's byte-level handshake filename and has
  nothing to do with the vendor.
  Evidence: `moon_sync_inbox/2026-08-01-0820-from-RC-*` section 7;
  `tests/test_oracle_backend.py` (16 tests);
  `docs/OPERATOR_ANSWERS_2026-08-02.md`.

- **rundash-instrumentation - DONE 2026-08-01; the spec has no open items.**
  DONE 2026-08-01 (`0ee1c9e`): chips render VERIFIED / REFUTED / NOT OBSERVED
  from an append-only per-slice verdict history written only through
  `slice_orchestrator.py`. A REFUTE with no later CONFIRM renders REFUTED even
  when the slice is `committed`; earlier refutations survive as `prior_refutes`.
  ALSO DONE 2026-08-01 (LEDGER 65): the directive-history spine - `run_id`,
  `cost_usd` and `session_id` now reach the file, the reader segments runs on a
  real id with the cycle heuristic kept as the legacy fallback, and
  `read_cycle_history` is wired into `/api/run`, which it never was.
  ALSO DONE 2026-08-01 (LEDGER 66): the P1b Cycle History panel renders it, and
  the cost boundary is enforced - `cost_usd` stays in the file for forensics and
  is projected OUT of `/api/run`, because LEDGER 40 settles that Claude dollar
  figures are notional and the spec rejects a cost panel outright.
  ALSO DONE 2026-08-01 (LEDGER 69-70): the last four spec items plus one that
  was not in the spec. `3e8ce6a` truth_gate persists a per-slice observation
  with the OBSERVED counts; `1d3c2c5` joins the three run-id namespaces on
  evidence only; `621e8d1` mirrors the fleet before Claude Code reaps it (136
  agents / 35 sessions / back to 2026-07-03 on first run); `27b22c3` P4
  Operator Queue + P5 Suite Trajectory; `71baedd` P6 Fleet History, which reads
  the mirror nothing was reading.
  Do-not-build without a real producer: P4's HELD column (no HELD substate
  exists in `pipeline_state.json`) and its run-attributed "this run added N"
  line (nothing attributes an image to a run). Both were scoped OUT
  deliberately - inventing a source is worse than the gap.
  Next: nothing in the spec. `truth_gate_blocking` stays false until a live run
  has been observed, and `joined_sessions` on P6 stays 0 until a controller
  cycle writes a `session_id` - the field is wired, it just has not run.
  truth_gate DONE 2026-08-01 (LEDGER 68) - wired into the run flow, ADVISORY
  until observed on a live run (`truth_gate_blocking` false); its first real
  invocation found the gate's own suite command swept the whole tree and
  manufactured a REFUSE on a green tree.
  Do-not-redo: do NOT collapse `lw_httpd.parse_ts` and
  `lw_rundash_state.parse_iso` - naive UTC vs naive LOCAL, 5h apart here, and
  `loop_controller.py:303` writes naive LOCAL so `parse_iso` is correct.
  Evidence: `docs/RUNDASH_SPEC_2026-08-01.md`; dashboard 127.0.0.1:8900.

- **usm-halo-calibration - RESOLVED 2026-08-02. `USM_DEFAULT` is now
  `(1.2, 35, 3)`, down from percent 70. The halo threshold was NOT touched.**
  The missing axis got measured: fidelity per variant over all 17 gated batch20
  slugs at 70 / 50 / 35 / none, ms_ssim + lpips + dists + ssim, 17/17 ok.
  The result was not the expected trade-off curve - **every fidelity metric
  improves monotonically as the mask weakens, worst case included** (at 35 vs
  70: ms_ssim min 0.9985 vs 0.9952, lpips max 0.0137 vs 0.0437, dists max
  0.0211 vs 0.0373). The mask was COSTING fidelity, not buying it. With halo
  flags 7/17 -> 0/17 and the worst gated `lap_ratio` still 1.1399 over its 1.0
  floor, usm35 wins on every axis at once.
  The threshold stays at 0.05 deliberately: at usm35 nothing flags, so the line
  stops mattering, and moving a ruler to fit a reading was the one axis ruled
  out - it is the only change that improves the report without improving the
  image.
  Do-not-redo: dropping the mask entirely (6 of 16 gated slugs fall through the
  `lap_ratio` hard floor); re-opening ADR-004 (the upscaler contributes almost
  none of the halo - max 0.0062 with no mask); reading the synthetic step-edge
  fixture as evidence about mask strength (`halo_pct` SATURATES there and reads
  equal to no-mask at 35, which is why that test now pins the historical 70).
  Read the fidelity numbers for what they are: FR self-comparison against the
  conditioned source, so a weaker mask is closer to the source by construction.
  They say the gate's own metrics improve, not that the image looks sharper -
  `lap_ratio` is the sharpness side and is what stops the argument at 35.
  Still open, and NOT implied by this change: the 288 already-approved
  firstdones were produced at usm70 and are now on a different recipe from
  anything produced after today. Reprocessing any of them is an operator call;
  the 7 carrying a halo flag are the obvious candidates if it is taken up.
  Evidence: `docs/USM_FIDELITY_CENSUS_2026-08-02.md` (+ the 2026-07-30 halo
  census it reproduces to 4dp); `scratchpad/usm_fidelity_census.json`.

- **ci-watchdog - `tools/ci_watchdog.py` WRITTEN and `LW-CIWatchdog` ARMED
  2026-08-02. Unproven on a real red main.**
  One pass per invocation (the scheduled task is the loop, so a wedged pass dies
  with its process). Rails: HALT is checked FIRST and an empty HALT file counts;
  only a settled `failure` triggers a fix (queued / pending / unavailable /
  not-evaluated all WAIT); 2 attempts per failing sha, and a transient Anthropic
  condition refunds the attempt; the merge self-gates on the fix branch's OWN
  green CI at its OWN head sha, and a stale success for a different sha is
  refused. Reuses `truth_gate.check_ci` rather than re-deriving the status
  distinction f1 item 12 already built.
  Registration is by the tool's own `--install` (XML): `schtasks` REJECTS
  `/RI` for `/SC ONSTART` outright, the same wall `lw_wallpaper_rotate` hit.
  Next: it has never seen a real red main. Watch its first genuine fire, and
  read `ops/runtime/ci_watchdog/watchdog.log` after any red push.
  Kill switch: create `ops\runtime\ci_watchdog\HALT` or
  `Disable-ScheduledTask LW-CIWatchdog`.
  Evidence: `tests/test_ci_watchdog.py` (26 tests); `docs/OPERATIONS.md` roster.

- **g1-source-adequacy - G1 is blind to an inadequate SOURCE; 105 of 276 approved
  images came from one - OPERATOR-GATED on policy.**
  Next: operator answers two questions, then it is a small deterministic slice -
  (1) is a 2.5x upscale from 1024x576 acceptable? (2) inadequate source = FLAG or
  FAIL? Deliberately NOT guessed; guessing repeats the mistake `anat-vision-review`
  caught the same day. Cheap once decided - `src_dims` is already in every
  manifest, so no model and no pixels needed.
  Do-not-redo: do NOT retune the G1 fidelity metrics - they are correct at their
  job; the gap is a MISSING ABSOLUTE precondition, not a miscalibrated relative one.
  Evidence: LEDGER 60; `docs/SOURCE_ADEQUACY_CENSUS_2026-07-29.md`.

- **legacy-audit-backfill - 12 approved images carry no G1 audit; 10 of them were
  built with the FALLBACK upscaler - NEXT (backfill, not a code fix).**
  Next: backfill or mark the 12 as pre-audit legacy, then decide the 10 reprocesses.
  Verified NOT a live bug (all 12 predate ADR-004; the current code path always
  writes the audit). NOT reprocessed unattended - `APPROVE_FIRST` is an operator
  judgement by design, so regenerating would park 10 images in your approval queue.
  The CODE half is DONE 2026-07-30 (`94bea85`): approve and finalize now record
  `gate_check` as `pass` / `override` / `no_audit`, so an override is greppable
  and a legacy no-audit approval is its own outcome rather than passing for a
  clean one. Only the DATA decision is still owed.
  Evidence: LEDGER 60 + 61; `docs/SOURCE_ADEQUACY_CENSUS_2026-07-29.md` (slugs listed).

- **anat-vision-review - AUTHORITY RULED 2026-08-02 (ADR-008) and the rails are
  SHIPPED. The reviewer itself is the remaining slice.**
  Ruling: a vision reviewer may FLAG, never REJECT, and an unresolved flag
  BLOCKS approval by any actor that is not the operator. Reasons, all measured:
  a REJECT demotes, and `clean-retry-degrades` shows a further pass makes the
  image WORSE, so a false REJECT degrades what it was protecting; a vision 2AFC
  is not reproducible, so the operator cannot re-derive a verdict they dispute;
  and splash art is deliberately non-anatomical with no ground truth to check.
  SHIPPED in `tools/lw_pipeline.py`: `clamp_vision_audit()` coerces a vision
  audit's REJECT/FAIL to FLAG at the ANNOTATE WRITE boundary (not in a prompt -
  a rule in a prompt is a request), `_approval_record` reports `blocking_flags`,
  and `assert_approval_allowed()` refuses a non-operator approval with exit 3
  BEFORE the needauth rename. `approve --actor` defaults to `operator`.
  The rail deliberately lands BEFORE auto-approval exists: a gate written after
  the thing it gates is a gate that was once open.
  Next: build the reviewer on the Claude-vision 2AFC path `end-review` already
  uses. It must arrive already unable to exceed these rails.
  Do-not-redo: keypoint head-spine offset as a gate metric - built, measured
  over all 288 approved firstdones, rejected on the evidence; ships as a
  diagnostic only (`tools/lw_anat_metrics.py` + `tools/lw_anat_probe.py`).
  Revisit REJECT only when the Phase A shadow window has >= 50 operator-reviewed
  images and flag precision is a NUMBER (`autonomy-phases-bc`).
  Watch: `BLOCKING_FLAG_PREFIXES` is a prefix match - a future reason starting
  with `anat_` becomes blocking silently.
  Do-not-redo: keypoint head-spine offset as a gate metric; swapping the localizer
  to rescue it (splash art is cropped at the waist, so most images have no confident
  hips - a better pose model cannot find hips outside the crop); reading a DWPose
  figure count as a detection count (35 percent yield zero person boxes and
  `tools/dwpose_onnx/onnxpose.py:26` silently substitutes the whole frame).
  Evidence: LEDGER 60; `docs/ANATOMY_CENSUS_2026-07-29.md`.

- **m1-gate-fund-or-close - decide attempt #4 on the weapon-canonicity gate - OPERATOR-GATED.**
  Next: operator decides FUND or CLOSE. Three measured negatives landed
  2026-07-26 (LEDGER 37) and the binding constraint is now known and cheap to
  fix: canonical n=5 gives AUC granularity 1/65, so no result can be
  significant. FUND = hand-crop wrists from the 19 official Vayne splashes
  already local at `tools/models/lora_datasets/vayne/` (the existing 5
  `weapon_assets` crops came from that same pool) to reach n~19 canonical vs
  ~13 non-canonical, all real Riot art, matched on pixel count AND provenance.
  CLOSE = accept `gate_mode="operator"` permanently, which is already the
  shipped default and works.
  THIRD OPTION opened 2026-08-02 by operator re-measurement of modelviewer.lol:
  seed each champion + skin ONCE and capture many perspectives / rotations,
  giving a render library where BOTH classes come from the same renderer. That
  matches provenance BY CONSTRUCTION and removes the n=5 ceiling, so the
  provenance objection - correct against mixing renders with real art - does not
  apply to an all-render design. Residual risk becomes train-on-renders /
  infer-on-paintings domain shift. See BACKLOG "3DSkinViewer / modelviewer.lol"
  point 1 and `glb-render-fetch`.
  Evidence: LEDGER 37; `scratchpad/probe_results.md` +
  `scratchpad/render_exemplar_results.md`.
  Do-not-redo: img2img weapon-swap (structure-locked, 0/12); any probe trained
  across a provenance boundary (AUC 1.0 = generator fingerprint); the 36 staged
  DreamUp step4 prompts (superseded by the render path). Match on EVERY axis -
  provenance and resolution both slipped in while palette was being tuned.

- **f1-phase6-queue - 12 follow-ups from the sdk-channel migration - RC-SIDE REMAINDER (LW's share is DONE).**
  Phase 6 DELETIONS remain HELD by operator call (flip yes, delete no); both repos
  default to `channel: sdk` and rollback is one config key. The gate for revisiting
  deletion is satisfied on both sides (LW 24-min / RC 71-min full-length cycles).
  Queue, agreed with RC and unstarted: (1) `chmod +x .githooks/*` - DONE on LW,
  open on RC. (2) `gate_inactive_reason` must check the exec bit on POSIX, not just
  presence. (3) log `sid` on EVERY `SdkExecutor` path incl. success - a cycle's
  transcript is currently unfindable once the process exits. (4) `ENGINE-IMPACT:
  BUMP` must require a numbered step naming every anchor site (RC found a FIFTH
  anchor: two changelogs, `agents/daemon_slayer/CHANGELOG.md` != `Share/CHANGELOG.md`).
  (5) `skipif` audit - skip when the CAPABILITY is absent, never when the thing under
  test is. (5a) pin the shared-file sha256s as constants so each repo's CI enforces
  parity alone. (6) CI arms the gate then asserts it - DONE on LW. (7) directives
  naming N parallel agents must assert disjoint files; executor serializes AND
  RECORDS the deviation. (9) POSIX `winmutex` branch must emit `UNSERIALIZED` -
  today it is unserialized AND untraced, so every guard we built passes vacuously
  off-Windows; joint edit + re-sync. (10) enumerate every instance of a defect class
  IN THE FILE before committing the fix, then across the codebase - CLAUDE.md:171
  says this but points outward, and it was missed twice in one function. (11) a
  claim heavy enough to justify a schema change ships as a TEST, not a transcript.
  (12) when asserting CI state, distinguish `not evaluated` (docs-only path filter)
  from `queued` - they are indistinguishable in `gh run list`.
  (5a) and (9) are DONE and VERIFIED IN SYNC on both sides: LW `3bd9a8b`, RC
  `fbf744f5`, both trees re-hashed clean to `slots.py 95077a62...` and
  `winmutex.py f1b4b011...` (the latter supersedes `c21bfe4f...`). (1) is done
  on both sides too - RC's exec bits landed as `19b680cc`.
  (3) is DONE on LW (`549f52c`): `build_argv` now retains the session id it
  mints or resumes, so all five `SdkExecutor` paths log it - including timeout
  and unparseable stdout, which never parse a payload and so previously had no
  id to log at all. Same commit repairs the CI red that `202cef3` introduced
  (the `directive_suffix` guard keyworded `done_sentinel`, which the phase-6
  DO-NOT-REDO line legitimately names).
  (12) is DONE on LW (`07ed5bc`): `check_ci` split the single `no-runs` outcome
  into `not-evaluated` and `queued`. The `paths-ignore` globs are PARSED from
  `.github/workflows/ci.yml` rather than hardcoded, so the check cannot drift
  from the workflow, and every unknown - unreadable workflow, no `paths-ignore`
  key, failed `git show`, merge commit - falls to `queued`. `not-evaluated`
  requires positive evidence. `reconcile()` still REFUSEs only on `failure`:
  making `queued` refuse would wedge an unattended run on GitHub API lag.
  Residual, adjacent and NOT item 12: `check_ci` only rev-parses when
  `sha == "HEAD"`, so an abbreviated sha reaches `gh run list --commit` and
  returns `[]`. The conservative fallback answers `queued`, so it is not a false
  green, but the abbreviation gap is real - `check_ci("549f52c")` -> `queued`
  while the full sha -> `success`.
  (7) is DONE on LW (`b7814b3`, LEDGER 80) in the only form LW can enforce it:
  `slice_orchestrator.start_gate()` REFUSES `set --status in_progress` unless the
  named agent holds a claim on every file the slice declares, and a slice with no
  declared files cannot start. So a directive that names N parallel agents no
  longer merely ASSERTS disjointness - an overlap is refused at dispatch and the
  refusal names the holder. The executor-serializes-AND-RECORDS-the-deviation
  half stays RC-side.
  LW's share of the queue is now empty; RC keeps (2), (4), (5), (10), (11).
  Cross-repo channel is the gitignored `moon_sync_inbox/` in each repo.
  Evidence: LEDGER 41 + 40; `docs/specs/2026-07-26-f1-sdk-executor-channel.md`.

- **glb-render-fetch - acquire the .glb bytes the ported resolver now addresses - NEXT.**
  Next: the addressing + filtering half shipped 2026-07-26 (LEDGER 38, 1dbfc2d) -
  `glb_model_url` / `glb_skin_id` / `is_weapon_joint` / `weapon_joint_indices` /
  `mesh_primitives` live in `tools/lw_gen_weapon_assets.py` and are pure, so the
  module stays torch-free AND network-free. What is still OWED is the I/O half:
  fetch the URL, parse the GLB container, skin the mesh against the surviving
  joints, and render the crop that `load_assets` consumes. That half needs a
  network dependency and a render backend, so it is a separate slice by design.
  Evidence: LEDGER 38 (1dbfc2d); LEDGER 37 for the live CDN verification.
  Do-not-redo: ASSET-SCRAPING the modelviewer.lol website (Cloudflare + in-app
  blobs, POC-measured 2026-07-16) - but note that ruling is scoped to fetching
  asset blobs and NOTHING else. Operator re-measurement 2026-08-02: Cloudflare is
  no longer the blocker and a CAPTURE route is viable - seed each champion + skin
  ONCE and capture many perspectives / rotations of the output window, building a
  render library in a single pass. That is a live option for this item and for
  `m1-gate-fund-or-close`; see BACKLOG "3DSkinViewer / modelviewer.lol" point 1.
  Also do-not-redo: any fixed bone-INDEX set (two rig conventions exist, so indices
  cannot port); reading `primitives[0]` alone (newer skins split mesh 0 into
  9-10 primitives sharing one POSITION accessor - drops most triangles); the
  `.skl` skeleton from CDragon (404) - the named-joint path replaces it.

- **refs-46-first-pass - process the 46 intaken reference_pictures - DONE
  2026-07-27. 46 of 46 APPROVED by the operator; `1.First Pass Scratch` is
  empty and `2.First Pass Done` holds 288 slugs (242 prior + these 46).**
  **A PROCESS MISS ON APPROVAL, recorded because the ruling it skipped is still
  open:** this entry said `first-pass-alpha-letterbox` should be ruled on BEFORE
  approval, and the session did not surface that to the operator - it raised the
  pixel-identity caveat instead. The pixel-identity evidence was itself blind to
  the issue: identity was measured as sha256 over decoded RGB buffers, which
  cannot see an alpha plane being dropped. NOTHING IS LOST - `approve`
  safe-copies `_firstinitial` next to `_firstdone`, verified on `258-cleanup`
  (`_firstinitial` RGBA, `_firstdone` RGB), and `9.Image Backup` holds a third
  copy - so the 15 affected slugs remain reprocessable via the reopen dance once
  the policy call lands. What was actually spent is the operator's chance to
  decide before staging, not the data.
  Next: stage-2 cleaning on the 46 (operator direction 2026-07-27).
  Cycle 10 (LEDGER 55, plan row R25) ran the last 5,
  `280f` `281-cleanup` `286f` `32-cleanup` `84f`,
  cycle 9 (LEDGER 54, plan row R24) ran
  `270f` `272-cleanup` `274f` `276f` `277f`,
  cycle 8 (LEDGER 53, plan row R23) ran
  `261f` `262f` `264-cleanup` `266f` `269f`,
  cycle 7 (LEDGER 52, plan row R22) ran
  `239f` `245f` `254f` `258-cleanup` `259f`,
  cycle 6 (LEDGER 51, plan row R21) ran
  `219-cleanup` `221-cleanup` `225f` `229f` `230-cleanup`,
  cycle 5 (LEDGER 50, plan row R20) ran
  `186-cleanup` `190-cleanup` `193-cleanup` `196f` `209-cleanup`,
  cycle 4 (LEDGER 49, plan row R19) ran
  `150-cleanup` `153-cleanup` `170-cleanup` `177-cleanup` `180-cleanup`,
  cycle 3 (LEDGER 48, plan row R18) ran
  `123f` `124f` `127-cleanup` `134-cleanup` `14-cleanup`, cycle 2 (LEDGER 47,
  plan row R17) ran `105-cleanup` `106-cleanup` `107-cleanup` `110-cleanup`
  `122`, and all five took 5/5 G1 PASS with an empty reasons list. That is the
  R16 fix measured in production over 45 consecutive slugs: cycle 1 FLAGGED on
  halo, cycles 2-10 flag nothing. Cycles 3-10 also MEASURED the pixel-identity
  claim (sha256 over the decoded RGB buffers per pair) instead of inferring it
  from equal dimensions; the PNG bytes otherwise differ only because SUBMIT
  re-encodes, and cycle 5's `186-cleanup` is the only RGB output so far to
  SHRINK on that re-encode rather than grow. Cycle 7's two big shrinks are a
  different mechanism entirely - see `first-pass-alpha-letterbox` below.
  Probe notes for the next cycle: the audit block
  is NOT at manifest top level - it is `transitions[i].audit` for the
  `ANNOTATE` transition, and a top-level read silently returns empty for every
  field. `manifest.json` carries no `state` key at all; state/substate is
  derived from the filesystem by `scan_tree`, and `lw_pipeline.Ctx()` takes the
  IMAGES dir, not the project root - passing the project root scans 0 images
  and returns a silent all-zero result rather than an error.
  All 46 processed slugs sit at
  `FIRST_SCRATCH/NEEDAUTH` - approval is operator-only and is the real queue.
  Cycle 1 proved the chain on slug `0`
  (`_firstneedauth`, G1 FLAG on halo only, LEDGER 45) and corrected the premise:
  all 46 `_firstinitial` files are EXACTLY 2560x1440, so every slug takes the
  `downscale-only` branch at scale=1, no resample happens, and the unsharp mask
  was the ONLY operation first pass applied to this batch. The AI upscaler is
  not exercised by these 46 at all (model load verified separately: spandrel DAT
  scale 4, torch 2.11.0+cu128, RTX 5070). Director decision B (LEDGER 46, plan
  row R16) fixed it at the cause: no resample, no unsharp mask. First pass is now
  a provenance-only passthrough for an already-at-target source - measured live
  on slugs `0` and `105-cleanup`, halo_pct 0.0711 -> 0.0 and lap_ratio 1.965 ->
  1.0, output pixel-identical to the source. A genuine over-target downscale
  (e.g. 4K -> 1440p) still gets its USM; the skip is keyed on the exact-target
  size, NOT on `scale == 1`. The 47/61 downscale-only halo flags in
  `project-first-pass-recipe-validated` stay an open watch - those DID resample.
  Then route them to stage-2 cleaning - 35 were
  gate-flagged (13 auto / 22 qa) and 11 were held on manual OCR review, so
  the watermark work happens at `3.Cleaning Scratch`, NOT before first pass.
  Recovery waterfall is still OWED for this set: every manifest carries
  `source_url: null` (Tier 0/1/2 deliberately skipped at operator direction),
  and 112 of the novel refs are still source-recoverable.
  Evidence: LEDGER 35 + 36 (63cc35b, 3b8e0f1); per-file verdict + reason
  table in `docs/refs_cleaning_queue.md`.
  Do-not-redo: the 226 clean refs are already delivered to Pictures as
  `ref_*.png` (sha-verified) - do not re-triage or re-copy them. If any of
  the 112 recoverable ones later gets restored, REMOVE its raw `ref_*` copy
  from Pictures or rotation gains a near-duplicate.

- **batch20-first-pass - FIRST PASS DONE 2026-07-30; 17 slugs sit at NEEDAUTH
  awaiting operator approval, 3 are HELD.**
  Next: operator approves or rejects the 17 (`lw_pipeline.py approve|reject`);
  approval is operator-only by design. Result: 10 PASS, 7 FLAG, 0 FAIL, 3 HELD.
  All 7 flags are the SAME reason - `halo_pct` over the 0.05 line, 0.0567 to
  0.1196 - and that is now measured and explained, see `usm-halo-calibration`
  at the top of this file. This batch DID exercise the AI upscaler (16 of 17
  took `upscale-4x`), unlike the 46 refs which were all exactly 2560x1440 and
  took the passthrough branch - which is exactly why this batch flags and that
  one did not.
  The 3 HELD are `puppet-master-syndra` and both `spirit-blossom-vayne` slugs,
  all on `aspect_crop_heavy` (area loss ~0.156 vs the 0.08 `AREA_LOSS_MAX`
  cap). They are annotated, never upscaled, and still EDITING. Crop policy is
  product direction and was NOT decided unattended - that ruling is owed.
  Intake + recovery ran 2026-07-29: Tier 0 `no_match` for all 20 (every one
  novel), Tier 1 decoded a DeviantArt token for all 20 and gallery-dl fetched
  all 20 at the quota-free setting. 8 of 20 gained real pixels, best
  `blood-moon-priestess-mel` 1159x689 -> 1920x1142 (2.75x); the other 12 held
  pixel count but shed 6-7x of JPEG compression.
  Do-not-redo: `original: true` on DeviantArt (weekly quota; the intermediary
  path already measured a gain and costs none); re-intaking a fetched fullview
  through `0.Originals` (re-slugging diverges the slug - `lw_first_pass`
  selects by convention path instead).
  Evidence: `PIPELINE_LOG.md` 2026-07-30T12:0x-12:17Z block; per-slug audit at
  `transitions[i].audit` for the ANNOTATE transition; LEDGER 61.

- **first-pass-alpha-letterbox - first pass silently drops the alpha channel,
  and G1 is blind to it - OPEN (found cycle 7, LEDGER 52, plan row R22;
  widened by cycle 8, LEDGER 53, plan row R23; sub-shape B identified by
  cycle 9, LEDGER 54, plan row R24; CENSUS CLOSED by cycle 10, LEDGER 55, plan
  row R25; audit hygiene SHIPPED by cycle 11, LEDGER 56, plan row R26;
  SUB-SHAPE B RULED by the operator 2026-07-29 - ACCEPT AND RECORD, change no
  pixels; SUB-SHAPE A's policy call is still open).**
  **STILL OPEN AND NOW POST-APPROVAL.** All 46 were approved on 2026-07-27
  without this ruling - see the miss recorded under `refs-46-first-pass`. That
  does not close it and does not lose anything: every `_firstinitial` is
  preserved RGBA beside its RGB `_firstdone` in `2.First Pass Done` and again in
  `9.Image Backup`. It does change the shape of acting on it - a ruling that
  says "keep the alpha" now needs the reopen dance for the affected slugs
  instead of a re-run before staging. Rule on it BEFORE stage-2 cleaning, since
  cleaning writes on top of `_firstdone`.
  The census is now complete over all 46 refs, so the numbers below are final
  rather than a running tally: FIFTEEN of the 46 are RGBA with a genuinely
  non-opaque alpha, 31 are RGB, none is any other mode. Cycles 8 and 9 both
  came back 5-for-5 RGBA, which read as "most of the corpus"; cycle 10 came
  back 3 of 5 and the full sweep settles it at 15 of 46, so this is a common
  shape but a minority one. Final shape histogram over the 15: sub-shape B 1px
  rim x8, sub-shape A hairline letterbox x4, the B left/right-column variant
  x2, and `258-cleanup`'s 160-row letterbox alone x1. The alpha PLANES collapse
  to only five distinct bitmaps (sha256-16 `2d01a0afce742e26` x8,
  `4be64a25a2e1d11c` x4, `f47a60870653b036` x1, `8d42f440f08f26d0` x1,
  `03a55dd42770d45d` x1), so three of them account for 14 of the 15 files -
  export-toolchain provenance, not per-image chance. That matters for the
  policy call: ONE ruling on sub-shape B disposes of 10 of the 15 files, and a
  second on sub-shape A disposes of 4 more. Two DISTINCT sub-shapes:
  Sub-shape A - a fully transparent (alpha=0) full-width top/bottom letterbox
  whose underlying RGB is already pure black: `258-cleanup` rows 0-79 +
  1360-1439 (160 rows, 11.11 percent of the frame - the actual artwork is
  2560x1280, an exact 2:1 plate letterboxed into a 16:9 canvas), and a 3px
  hairline `[0-2]` + `[1437-1439]` (6 rows, 0.4167 percent) on `259f`, `261f`,
  `262f` and `264-cleanup` - four slugs with byte-identical bar geometry, so
  the hairline is a shared authoring or export artifact, not per-image chance.
  Sub-shape B (found cycle 8, IDENTIFIED cycle 9) - PARTIAL translucency with
  no transparent row at all, and it is a 1-PIXEL OUTER BORDER RIM, not the
  scattered anti-aliased band cycle 8 read it as. Cycle 9's five slugs plus
  cycle 8's `269f` each measure alpha min=220 max=255, ZERO fully transparent
  pixels, and exactly 7996 non-opaque pixels = `2*2560 + 2*1440 - 4`, the frame
  perimeter, with a 100 percent opaque interior. Cycle 8's `266f` measures
  2880 = `2*1440`, the same rim with only the left/right columns. Cycle 9's
  five alpha planes are `np.array_equal` BIT-IDENTICAL to one another (plane
  sha256-16 `2d01a0afce742e26`), so this is one export-toolchain artifact
  stamped across many files rather than per-image chance - cycle 10's `280f`
  and `286f` carry that same plane hash, making it 8 files on one bitmap.
  One dent in the taxonomy, from cycle 10: `281-cleanup` is a 2880
  left/right-column rim like `266f`, but its alpha min is 218, not the 220
  every other rim carries, and its plane hash (`03a55dd42770d45d`) matches
  nothing else. Its plane's value histogram is exactly `{218: 1440, 222: 1440}`
  - one column at 218, the other at 222, no 220 anywhere in the file, so its
  two columns are not even equal to each other. "alpha min 220" is a strong
  regularity, NOT an invariant - any detector written for this must not
  hard-code it. Nothing is
  letterboxed here; the alpha is simply discarded. The item name understates it
  - the general defect is an unannounced RGBA -> RGB flatten.
  First pass writes RGB, so sub-shape A bars bake to pure black (verified max
  AND min channel value 0) and the file shrinks ~40 percent on the alpha drop -
  the only reason this was noticed at all. Every cycle-8 output shrank
  (-39.7 to -42.1 percent) and every cycle-9 output shrank (-40.6 to -43.3
  percent) for exactly this reason, which is a different mechanism from cycle
  5's `186-cleanup` RGB re-encode shrink.
  The gap: G1 compares RGB only, so black-vs-black under alpha=0 scores a
  perfect 1.0 and a letterboxed source is structurally invisible to the gate.
  `aspect_class=ok` on `258-cleanup` is satisfied by the transparent bars, not
  by the artwork, so it would approve as a 2560x1440 wallpaper with an 80px
  black bar top and bottom. Sub-shape B is invisible to the gate for the same
  reason and has no aspect consequence at all - the composite over an opaque
  background is unchanged, so it may well be acceptable as-is.
  Decide the POLICY before writing any detector, and decide it PER SUB-SHAPE.
  **SUB-SHAPE B IS RULED (operator, 2026-07-29): ACCEPT AND RECORD.** The
  flatten is recorded in the audit and NO pixels change - a 1px perimeter rim
  (or a left/right-column variant) has no consequence composited over any
  background, which is what the cycle-9 rim measurement established. That
  disposes of TEN of the fifteen files (the 8 full-perimeter rims on plane hash
  `2d01a0afce742e26` plus the 2 left/right-column variants, `266f` and
  `281-cleanup`), and it needs no reopen dance: their already-approved
  `_firstdone` files stand as-is and go straight to stage-2 cleaning. Recording
  for the ten is the `alpha_flattened` + `source_mode` field shipped in cycle 11
  (`ef67c49`), which those ten predate - so their record lives in this ROADMAP
  entry and the LEDGER, not in their own manifests, and that is the accepted
  cost of ruling post-approval rather than a reason to re-run them.
  **SUB-SHAPE A IS STILL OPEN** and still blocks its five slugs: for A, crop to
  the content box and re-run the aspect logic against that, re-source a
  full-bleed original, or accept the bars as authored intent. A wrong automatic
  answer is worse than the current queue, so those five (`258-cleanup` with the
  160-row letterbox, plus the 3px-hairline four `259f` / `261f` / `262f` /
  `264-cleanup`) stay held ahead of cleaning. Nothing downstream is blocked for
  the other ten; this is a correctness hole in the audit, not a gate.
  Cheapest first step, and it needs no policy call: DONE cycle 11 (LEDGER 56,
  plan row R26, commit `ef67c49`). `first_pass` now reads the source PIL mode
  off the existing probe BEFORE any `convert("RGB")` and records `source_mode`
  + `alpha_flattened` in `upscale_audit`, so every future run self-reports the
  drop instead of leaving a file-size anomaly as the only tell.
  `alpha_flattened` is True for palette-with-transparency sources too, not
  just mode RGBA - a `P` + `tRNS` source flattens identically and would
  otherwise read clean. NOTE the 15 already-processed refs predate the field
  and carry no such key; their flatten is documented here, not in their
  audits. The "scan the remaining unprocessed refs" step is DONE (cycle 10
  swept all 46); what is still owed is the POLICY call itself (per sub-shape),
  and the note that the same blindness applies to any future letterbox in a
  solid non-black colour, where the RGB metrics would ALSO score clean.

- **iopaint-batch-drain - Stage-2 watermark batch reprocess - IN PROGRESS, and
  the NEXT SESSION'S focus (operator direction 2026-07-27).** The 46 refs
  approved this session join this queue. `first-pass-alpha-letterbox` is now
  PARTLY ruled: sub-shape B (10 slugs) is ACCEPT-AND-RECORD as of 2026-07-29 and
  is CLEARED for cleaning; sub-shape A (5 slugs - `258-cleanup` `259f` `261f`
  `262f` `264-cleanup`) is STILL HELD, because cleaning writes on top of
  `_firstdone` and a later "crop to the content box" ruling would mean redoing
  cleaning as well as first pass for those five. Clean the other 41 freely.
  Next: land the 3 pass-improvements from the triage (full-width banner band;
  chroma-thr ~12 default; namakx template-mask / adaptive dark_thr) -> re-run
  the worker over the 9 CLEAN-AUTO + cleared PARTIALs -> `save-working --tool
  iopaint` + submit needauth -> route fantasy-design + prestige-coven-xayah
  (+ fury-sona if fidelity demands) to the manual IOPaint lane -> clean-scan
  the 190 clean firstdones + dark-cosmic-ahri + the 14 uhdpaper firstdones
  landed 2026-07-18 (LEDGER 32 session) (G3 Haiku 2AFC + V3denoise
  halftone alt stay gated on the vision stage).
  Evidence: LEDGER 30 (bc5fc19) + `docs/research/IOPAINT_TRIAGE.md` (9 auto /
  7 partial / 2 manual); manual-lane launch cmd in
  `docs/research/CLEANING_INPAINT.md` + `.claude/commands/cleaning-pass.md`.
  Do-not-redo: Dekel / pure algebraic (LEDGER 29 measured cap); white-only
  masks (mask MUST cover the dark edge).

- **g1-dists-cap-ratify - CLOSED 2026-08-02. `MAX_COMMON_PIXELS` = 3840x2160 is
  ratified as ADR-007. Nothing open.**
  The value was shipped unratified (LEDGER 32, `b14b688`) because DISTS was
  otherwise uncomputable for 8K-class sources - 63 of 230 first-pass images had
  lost it silently. Ratified as-is on three grounds: it sits BELOW the proven
  ceiling 4096x2306 rather than at it, it lands on the scale 26 corpus images
  already use natively (so the cap is a no-op for them), and the mechanism only
  ever DOWNSCALES the reference, so AUDIT_GATES 1.2 caveat 2 still holds.
  The premise that had to be corrected to answer it: the cap sets the
  SOURCE-vs-OUTPUT COMPARISON scale, not the deliverable. Output stays exactly
  2560x1440; sources run to 6500x3660, and FR metrics compare at source scale
  because upscaling the reference manufactures a blurry reference.
  Do-not-redo: native-8K DISTS (measured impossible on this box, both devices);
  editing `MAX_COMMON_PIXELS` without a new ADR - `tests/test_g1_common_scale_budget.py`
  now fails CI if it moves. Watch: any future `DEFAULT_G1_THRESHOLDS`
  recalibration must SEGMENT on the `capped` flag, never pool capped and native
  measurements - that is one threshold fitted to two measurement bases.
  Evidence: `docs/adr/ADR-007-fr-common-scale-pixel-budget.md`;
  `docs/research/AUDIT_GATES.md` 1.2 point 6; LEDGER 32.

- **golden-sec6-ratify - GOLDEN_DEFINITION sec 6 Q1-Q4 - OPERATOR-BLOCKED.**
  Next: operator ratifies glasses shape / style-band steer / dodge lane /
  scorecard. Champion labels already DONE.
  Evidence: LEDGER 17 (open questions) + LEDGER 18 (labels done).

- **resource-4-messups - re-source 4 ingest messups - MANUAL (NOW).**
  Next: drop clean 1920x1080+ Battle Academia splashes for `xayah1` /
  `camille1` / `kaisa1` / `fiora1` into `0.Originals` + re-intake (originals
  are 1920x1173 with a ~210px foreign strip pasted on top). Fallback only if
  the manual grab is skipped: bottom-anchored crop -> ~1712x960 -> ~1.5x
  upscale (lossy; not preferred).
  Evidence: operator ruling 2026-07-07 (LEDGER 13); Tier-0 pHash found no
  local twin (423-file corpus), no source token for auto-fetch.

- **corpus-crop-redo - 3 slugs crop + reprocess - LATER.**
  Next: #115 Hwei / #247 Shyvana / #253 Soraka - champion label correct,
  crop the leftover top artifact, then reprocess.
  Evidence: `docs/research/corpus/CROP_REDO_QUEUE.md`.

- **g1-lpips-downscale-watch - downscale-only lpips threshold - LATER (watch).**
  Next: only if more synthetic-8K downscales trip a spurious `lpips > 0.2`
  FAIL, calibrate a downscale-only lpips threshold (ADR-006-style ruling).
  One datapoint so far - not actionable.
  Evidence: `elise-8k` operator force-submit + approve 2026-07-07 (LEDGER 12
  session).

## Open items - Medium priority

- **autonomy-phases-bc - promote autonomy per calibration ladder - LATER.**
  Next: after the Phase A shadow window accumulates >= 50 operator-reviewed
  images, promote per the ladder. Never skip the ladder.
  Evidence: `docs/RESTORATION_PLAN.md` section 5.

- **shareability-packaging - package the process as the deliverable - LATER.**
  Next: package pipeline code, gate ladder, rubric, golden-set protocol,
  manifests - never the cleaned third-party images. Prereq: licensing
  re-check on detector/LaMa weights.
  Evidence: `docs/RESTORATION_PLAN.md` section 9.

- **arm-scheduled-tasks - roster REVIEWED + acted on 2026-08-02. Every remaining
  row is blocked on a MISSING SCRIPT, not on approval.**
  `LW-WeeklyHygiene` is REGISTERED (Sunday 04:17, verified `Ready`). Its
  `-Model` default was `claude-sonnet-4-6`, not a current model id - fixed to
  `claude-sonnet-5` in the same change, since a weekly unattended task with a
  stale id fails silently every week.
  `LW-GeminiAudit` is RETIRED by `gemini-removal` - never registered, so nothing
  was disabled; it is off the roster for good.
  `LW-CIWatchdog` was blocked on a missing script, so the script was WRITTEN and
  the task is now REGISTERED (verified `Ready`). See `ci-watchdog` below.
  `LW-Supervisor` is the only unarmed row left: `ops/lw_supervisor.py` does not
  exist, and it stays blocked until the product has a long-running process to
  supervise. Arming it now would fail on every logon.
  Deep-audit program stays DORMANT - separate gate, untouched by this review.
  Evidence: `docs/OPERATIONS.md` roster + `docs/OPERATOR_ANSWERS_2026-08-02.md`
  section 4; `docs/DEEP_AUDIT_CHARTER.md`.

## Status at a glance

Live status is intentionally NOT duplicated here - a static table goes stale.
Sources of truth:

- Pipeline state: `ops/runtime/pipeline_state.json` (written by
  `tools/lw_pipeline.py`; viewed via lw_monitor at `127.0.0.1:8901`)
- Transition history: `PIPELINE_LOG.md` (project root, append-only, gitignored)
- Process, pid, alive flag: `ops/runtime/health.json` (producer still TBD)
- Daily log: `logs/YYYY-MM-DD.log`
- Scheduled tasks: `Get-ScheduledTask -TaskName "LW-*" | Select TaskName, State`
  (expected result today: none - nothing is registered yet)

---

## Cross-cutting principles (never violate)

- **Frozen files** - see CLAUDE.md. Explicit operator sign-off required for any
  change. (The frozen list is currently EMPTY - files earn freeze status as the
  product stabilizes.)
- **Atomic writes only** - `tmp.write_text(...); tmp.replace(target)`.
- **`py_compile` before restart** - syntax errors crash silently under `pythonw.exe`.
- **Restart via `restart_trigger.txt`** - never `Stop-Process`; `taskkill /F /PID`
  for hard kills.
- **7-bit ASCII only** in authored content - no em/en dashes, no smart quotes.
- **Do not build blind** - product-shaping choices need an ADR or an explicit
  operator directive first.
- **Never double-resample** - one AI upscale, one Lanczos down, one light USM
  (the v1 softness bug, structurally banned by ADR-002).
- **Never touch `images/` content in tests or git** - tests use tmp_path;
  `images/**` gitignored except the .gitkeep skeleton.
