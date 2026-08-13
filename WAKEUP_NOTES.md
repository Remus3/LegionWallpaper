# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18), and the 2026-07-27 loop-cycle-11 alpha-audit session (pruned 2026-07-29), and the 2026-08-01 three-repo-N=3 / hook-rule-correction session (pruned 2026-08-01), and the 2026-08-01 (evening) Stage-2-drain / L1 / dashboard-spine session (pruned 2026-08-01), and the 2026-08-01 (night) dashboard-spec-completion session (pruned 2026-08-01), and the 2026-08-01 (earlier) P3/P4/P5 + wiki-swap session and the 2026-08-01 (late) MCP-list/P1 session (both pruned 2026-08-02), and the 2026-08-02 all-five-recommendations/USM-flip/watchdog session (pruned 2026-08-09), and the 2026-08-10/11 intake/retry-degrades session + the 2026-08-11 detector-precision/recall session + the 2026-08-11 (evening) centre-overlay-inpaint session (all three pruned 2026-08-12) - keep the last 3.

---

## 2026-08-12 (latest) - the veil ring was hiding a cliff the lane made

One commit. Suite **1957 passed / 18 skipped** (3.14). LEDGER 101. ROADMAP
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
  **The matte is deliberately NOT rebuilt** - 0.03 of alpha on a flat objective
  is not worth invalidating 33 candidates again.

**NEXT:** if a candidate ship gate is wanted, build it on a legibility measure
(mean |gray - median21| over the mask's credit-line band: original 14.32 /
pre-pass 15.97 / +LaMa 7.00 medians), not the detector score. When the matte is
next rebuilt for any reason, the wider grid applies automatically and the
warning will say whether the new fit is interior.

---

## 2026-08-12 - QA-lane precision census, 67 rows labelled by eye

One commit. Doc + one new probe tool. LEDGER 100. ROADMAP
`cleaning-detector-recall` item **(d) CLOSED** - the item's last open
measurement.

- **The human queue is 94 percent real work.** All 67 `qa` rows of the live
  gate-v4 302-image corpus labelled from crops that were actually viewed.
  Region precision (is the BOXED thing a mark) **62/67 = 92.5 percent**; frame
  precision (does the frame carry a mark anywhere) **63/67 = 94.0 percent**.
  Per reason, region: `centre_overlay` **32/32**, `not_border` 25/28,
  `faint_mark` 4/5, `low_conf` 1/1, `area_too_large` 0/1.
- **The two precisions disagree on exactly one row, and that is the finding.**
  `258-cleanup` boxes its letterbox bars (junk) but DOES carry a
  `TYSIUUUL.DEVIANTART.COM` credit line at `overlay_score` 0.1254 - just under
  the 0.15 flag. Right for the wrong reason; a second signal saved it.
- **No threshold moved, deliberately.** The 4 mark-free frames (`177-cleanup`
  jersey logo + "FAKER", `186-cleanup` "unto DARKNESS/LIGHT" art typography,
  `193-cleanup` a painted snowflake, `dbwtlkx-eeb94ce2` brick texture) sit
  INSIDE the true-positive range on `conf_max`, `n_boxes`, `area_pct` and
  `ocr_hit`. Any cut that drops them drops real marks.
- **New tool `tools/lw_clean_qa_crops.py`** - crops what a row actually flagged
  (template support bbox for `centre_overlay`, box union elsewhere), tiles
  labelled sheets, adds an amplified high-pass tile for the low-amplitude DA
  overlay. `--reason` / `--slug` / `--per-sheet`. Sheets land in
  `ops/runtime/clean/qa_precision/` (gitignored).
- Verified: ruff clean, doc/roadmap/ledger subset **43 passed / 2 skipped**.
  Full suite NOT re-run - Tier-0/1 change, no production path touched.
- Evidence: `docs/CLEAN_QA_PRECISION_2026-08-12.md`.

STILL OPEN on the item: (a) LaMa softening on pale flat art (`mecha-ahri`), and
(f) `p2402-kda-evelynn` in the MANUAL IOPaint lane.

---

## 2026-08-12 (later) - overlay registration searches SCALE

One commit. Suite **1956 passed / 18 skipped** (3.14). LEDGER 99.

- **`110-cleanup` clears, and it was never a one-image fix.** `best_shift`
  registers translation only; the overlay is composited at a fixed size on the
  DA-served image, so a frame from a different source resolution carries the
  mark at a different PIXEL size. Swept every flagged slug under 0.25: EXACTLY
  TWO are mismatched, both at the SAME 1.12 - `110-cleanup` 0.1090 -> 0.5052 and
  `122` 0.1696 -> 0.6542, both landing in the well-registered range.
- **Two boundaries, both measured, both pinned.** (1) The search is for REMOVAL,
  never the GATE - a max-over-scales lifts clean `wallpapersden-sejuani` 0.1213
  -> 0.1537, over the 0.15 flag; `overlay_score` is untouched and a test asserts
  it never grows a scale parameter. (2) `SCALE_ACCEPT_RATIO = 2.0` - registered
  frames wobble up to 1.22x, the two real ones are 3.86x and 4.63x; a refusal
  keeps scale 1.0, which is the safe direction.
- **Blast radius measured BEFORE trusting it:** 2 re-register, **31 register
  exactly as before**, and `scale2d_centered` short-circuits at 1.0 so those 31
  take a bit-identical pixel path - LEDGER 95/96 candidates stand. Live
  spot-check: mecha-ahri 0.6958 -> 0.0737, 245f 0.5858 -> 0.0903.
- **Result: 110 -> 0.0868, 122 -> 0.0941, credit line GONE on both by eye.**
  Every changed pixel on all four verified frames sits inside one of the lane's
  two editors (inversion band / LaMa ROI) - unexplained 0.
- **Do not chase the outside-ROI count.** It reads 6-11k pixels and is not a
  defect: the inversion legitimately edits sub-threshold alpha across the band,
  which is why the tripwire compares post-LaMa against the PRE-PASS frame.
- Fixture trap repeated and caught: the first synthetic test built its template
  from the same noise realization as the test image, so the art correlated with
  itself at scale 1.0 and drowned the mark - the same "frames must be unrelated"
  lesson as the veil work (LEDGER 96).

**NEXT:** `p2402-kda-evelynn` is the only faint-family slug still owed to the
manual IOPaint lane. Note `122`'s candidate WAS regenerated at the correct scale
into `ops/runtime/clean/overlay_scale/122/` during verification - the stale
wrong-scale one from the LEDGER 95/96 pass is still sitting in
`ops/runtime/clean/overlay_lane/`, so take the candidate from the new dir.

---

## 2026-08-12 - faint-mark REMOVAL lane

One commit. Suite **1939 passed / 18 skipped** (3.14). LEDGER 98.

- **The family is NOT one object, and measuring that first shaped the lane.**
  Five flagged slugs, four dispositions: 2 brush signatures CLEANED, 1 wordmark
  on busy art REFUSED to manual, 1 low-alpha DA overlay DEFERRED to `--overlay`,
  and the known false flag costs a 0.8% mask (a near no-op - the useful
  negative control).
- **`lw_clean_iopaint.py --faint`** reuses the masked-LaMa path whole. New:
  the ROI is DERIVED from the detector's sub-floor boxes (+ any OCR box that
  OVERLAPS one - p2402's YOLO box stops 134px short of what OCR reads; overlap
  not proximity, or the KEPT LoL wordmark in the far corner joins in), and
  `FAINT_BRIGHT_THR` 42 vs the banner default 10 (painted art reads above +10
  from its own median, so at 10 the mask swallows the picture).
- **Two refusals + an outcome check.** `FAINT_COVERAGE_MAX` 25 fires before the
  GPU. `FAINT_OVERLAY_DEFER` 0.10 is a MEASUREMENT - clean-population overlay
  score p50 0.0596 / p99 0.1042, the non-overlay flags 0.048-0.064, 110-cleanup
  0.109. Post-pass RE-DETECT on the candidate reports a survivor as `residual`.
- **Verified: 0 changed pixels outside the ROI on all three cleaned frames,
  re-measured off disk, not from the in-process tripwire.** Signatures cropped
  before/after: gone, background continuous.
- **Three dead ends, measured:** the dark-outline adjacency gate does NOT
  separate p2402 (art crevices satisfy it at every reach); the faint lane on a
  low-alpha overlay is structurally wrong (110's line stays legible, its overlay
  score goes UP 0.1090 -> 0.1203); and `--pad 260` on the overlay lane fixes
  110's ROI clipping but not the mark - the constraint there is REGISTRATION
  (0.109 vs the family's 0.310 median).
- Two traps fixed in passing: the lane tests are autouse-pinned to overlay score
  0.0 because CI has no template and Legion does (a synthetic fixture was
  passing/failing BY MACHINE); and argparse %-formats help text, so `--faint`'s
  literal `%` took two existing CLI tests red until doubled.

**NEXT:** p2402 + 110-cleanup are queued for the MANUAL IOPaint lane - nothing
automates them. 110's real fix is the overlay lane's registration on
weakly-correlating frames.
