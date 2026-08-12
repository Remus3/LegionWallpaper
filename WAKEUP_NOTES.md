# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18), and the 2026-07-27 loop-cycle-11 alpha-audit session (pruned 2026-07-29), and the 2026-08-01 three-repo-N=3 / hook-rule-correction session (pruned 2026-08-01), and the 2026-08-01 (evening) Stage-2-drain / L1 / dashboard-spine session (pruned 2026-08-01), and the 2026-08-01 (night) dashboard-spec-completion session (pruned 2026-08-01), and the 2026-08-01 (earlier) P3/P4/P5 + wiki-swap session and the 2026-08-01 (late) MCP-list/P1 session (both pruned 2026-08-02), and the 2026-08-02 all-five-recommendations/USM-flip/watchdog session (pruned 2026-08-09) - keep the last 3.

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

---

## 2026-08-11 (late) - faint-mark FLAG (gate v4): the last 4 recall misses

One commit. Suite **1914 passed / 18 skipped** (3.14). LEDGER 97.

- **It needed a FLOOR, not a model.** The census's "no box at any conf" was
  measured at ITS OWN 0.10 sweep floor. Swept to 0.02, all four remaining misses
  carry a YOLO box on the mark: `110-cleanup` 0.1366, `p2402` 0.1228,
  `karthasbasefinal` 0.1135, `dragon-slayer-pantheon` **0.0522**. Production
  detects at 0.35, so every one was thrown away before the gate ran.
- **`detect_image` sweeps once at `FAINT_CONF_MIN` and splits at
  `DETECT_CONF`.** Free, not a second inference - NMS never suppresses a box
  with a weaker one, measured identical on 39/39. `boxes`/`confs` exclude the
  faint tier, so mask geometry and `area_pct` are untouched.
- **The flag is a POST-PASS over the v3 ladder, and that is the safety
  argument.** An ordered rule would have to sit above `n == 0` (two misses have
  no confident box), which is above the auto rules too - and 7 live `auto`
  images carry a qualifying faint box. The post-pass can only rewrite
  `clean` -> `qa`, and leaves an existing `qa` reason alone.
- **Live: 26/62/214 -> 26/67/209.** Exactly 5 rows flip, all to
  `qa/faint_mark`, no auto lost, each cropped and looked at: 4 real, 1 false
  (`dbwtlkx-eeb94ce2`, blurred stonework). KEEP set: ZERO faint_mark rows, 14
  autos stand.
- **Constants are swept, not guessed.** `FAINT_CONF_MIN = 0.05` (0.10 -> 3 flips
  0 false; 0.05 -> 5 flips 1 false, and is the ONLY floor reaching 0.0522; 0.10
  is the zero-false alternative, one constant away). `FAINT_MIN_W_FRAC = 0.05`
  sits inside a clean width gap (real 0.076-0.176 vs art 0.009-0.033) and is
  explicitly NOT claimed universal.
- **Three dead ends, measured - do not redo:** tiled/SAHI inference is WORSE
  (karthas's signature vanishes; p2402 loses its box and gains a 0.4613 false
  one on unrelated art) because the weights need whole-frame context; EasyOCR
  reads a brush signature as garble at 0.00 at 1x/2x/4x; and a per-artist
  signature template was deliberately not built - 2 known frames is a lookup
  table, not a detector.

**NEXT:** REMOVAL for this family. The flag routes to the human queue and
nothing automates the edit; the two brush signatures are thin strokes over busy
art, which is the manual IOPaint lane's shape rather than LaMa's.

---

## 2026-08-11 (evening) - centre-overlay INPAINT: 32/32 under the flag

One commit `109124d`. Suite **1881 passed / 18 skipped** (3.14). LEDGER 95.

- **The matte now SEEDS the LaMa mask, and the whole flagged family clears the
  score bar.** `lw_clean_iopaint.py --overlay`: register -> algebraic pre-pass ->
  matte-seeded mask -> one LaMa pass -> the existing outside-ROI tripwire.
  Detector score over all 32 `centre_overlay` slugs: median **0.310 -> 0.069**,
  worst **0.696 -> 0.115**, **32/32 under 0.15** (was 0/32).
- **Removal needs a WIDER band than detection** - the logo's top edge is at y/h
  0.506 vs the detector band's 0.55, so `REMOVAL_BAND = (0.45, 0.85)` plus a
  separate `*_wide.npz` pair (`--wide` on the probe's two build commands). The
  calibrated detector `BAND` + 0.15 threshold were NOT touched.
- **Mask recipe, all three parts measured:** threshold 0.08 (0.03 stretches the
  ROI from 550x290 to 1229x624 on speckle), a DENSITY speck filter (25 px in a
  31x31 box - erosion cannot separate a 3x3 blob from a 4px stroke), and
  completion from the frame's OWN residual inside a gate that is 7px across the
  strokes but 40px ALONG the credit line, bright-only sideways because the
  nearest art is a dark lip line.
- **By eye: the credit line clears, the logo's flat veil does not** on smooth art
  (`miss-fortune`, `mecha-ahri`); on busy art (`bayonetta-dm7iirw`, `239f`)
  nothing is visible at all. Candidates stay QA proposals, never auto.
- **Root cause of the veil, pinned:** the template support is the top 2 percent of
  the median HIGH-PASS, so a flat region contributes NOTHING - matte alpha inside
  the logo is exactly 0.0. Probed the successor estimator (whitening against a
  background window wider than the veil, median over the collection): it renders
  the silhouette FILLED, but underreads (interior 0.060 vs ~0.14 from the boundary
  step) and its support sprawls. Numbers in
  `docs/CLEAN_OVERLAY_INPAINT_2026-08-11.md`.
- Latent bug fixed in passing: `_binary_dilate`/`_binary_erode` padded both axes
  with the SE's row radius, so any non-square element raised a broadcast error.

### Then the VEIL, same session (LEDGER 96)

- **`estimate_veil` closes the by-eye gap.** Whitening against a background window
  WIDER than the veil, combined by the collection's **25th percentile** (not the
  median - art residue is high in a few frames, the veil in all), support opened +
  closed and stopping ~10px inside the true edge, amplitude **calibrated against
  the veil's own boundary step**: recovered **alpha 0.133**, matching the ~0.14
  measured directly off the step.
- **Two traps, both measured:** a fixture built from one sinusoid at shifted
  phases makes the boundary bias correlated across frames and NO boundary method
  can work on it (the frames must be unrelated artworks); and rings flush against
  the support straddle the veil edge (inner ring only 56 percent veil), which
  halves the step and halves the alpha. Both rings now stand off by 2-3 widths.
- **The veil is inverted, never inpainted** - it rides beside the stroke alpha in
  the matte, `remove_overlay` maxes them, and only a 9px ring at its boundary
  joins the LaMa mask.
- Re-run over the 32: median **0.310 -> 0.068**, 32/32 under the flag. The score
  barely moves (the detector is a high-pass correlator - it never saw the veil);
  the PICTURE is what changed. `245f` + `miss-fortune` clean, `mecha-ahri` down to
  a soft blur. Suite 1889/18.

**NEXT:** the remaining defect on pale flat art is LaMa's own softening along the
masked strokes - a blur, not a legible mark. Everything else open on the item is
the OTHER 3 recall misses (thin painted signatures, an off-band wordmark), which
need their own detector.

---

## 2026-08-11 - clean-retry-degrades HALF 2: detector precision measured, 0 FP

One commit. Suite **1837 passed / 18 skipped** (3.14, full run). LEDGER 91.

- **Answer: the detector is precise. 14 unattended (`auto`) proposals over the
  whole 21-slug gated corpus, ZERO false positives.** New read-only probe
  `tools/lw_clean_detector_probe.py` re-runs detect + the same `gate_decision`
  on each `_cleaninitial`; every `auto` region was then cropped and looked at.
  All 14 are a credit URL, handle, signature or credit strip (ADR-005 REMOVE).
  4 route to `qa` (not a proposal), 3 to `clean`.
- **Both cited cases were stale.** `vayne3` detects nothing at all now (n=0);
  `p08e8`'s fire is the real `@namakxin` signature the operator APPROVED
  removing (65122 changed px in `_cleandone`), same for `nguyen-ky-phuc` (9719).
- **Method lesson worth keeping:** a REJECT note is a WEAK label - it lands on
  one working's pixels, not on the detector's box. The strong label is the
  `APPROVE_CLEAN` sha256 vs `_cleaninitial`. Reading the notes alone would have
  "found" 2 false positives that are not false positives.
- **No rule narrowed** (acceptance branch 2). Shipped the regression net
  instead: `tests/test_lw_clean_detector_precision.py`, 29 tests pinning all 21
  measured rows + a KEEP-set test that no KEEP slug may become `auto`.
- Still open on the parent item: the cross-engine ladder is fired by the
  operator/skill, not by code.

### Then RECALL, same session (LEDGER 92)

- **14 confirmed false negatives, ~12 percent of the 229 `clean` verdicts.**
  Measured over all 302 unrouted `_firstdone` images (the gated corpus CANNOT
  answer recall - it is the detector's own `auto` output). 27 auto / 46 qa /
  229 clean; strata S1-S3 (17 images) censused in full, S4 (212) sampled n=14.
- **11 of the 14 are ONE object: the semi-transparent DeviantArt centre
  overlay.** Under the 0.35 YOLO floor (scores 0.11-0.25), illegible to OCR, and
  mid-frame so the geometry rules would only ever say `qa`.
- Two traps: `is_lol_logo` looks guilty (fired on all 4 S1 misses) but is NOT
  the binding cause - those marks had no box above the floor either; and the
  conf floor is a good FLAG signal, not an AUTO one (13/17 low-conf clean images
  are real misses).
- No rule changed there. The fix followed in the same session.

### Then BUILT the centre-overlay detector (LEDGER 93)

- **Gate v3: `clean` 229 -> 214 over the live 302-image corpus.**
  `tools/lw_clean_overlay.py` median-stacks the high-pass of marked frames into
  a template (the mark is the same pixels in the same place, so the art cancels)
  and scores by masked normalized correlation with a tight shift search. Pure
  numpy, no GPU, CI-safe.
- **Everything is measured, leave-one-ARTIST-out** (not leave-one-image - the
  template is partly artist-specific): clip at +-8 levels (0.112 -> 0.220),
  shift search +-3.0%h/+-1.6%w (-0.02 -> 0.100), window kept TIGHT (a wide
  search lifts CLEAN frames faster than positives). Threshold 0.15 = 15 clean
  images flip to qa, all 15 real, zero false; 0.12 costs 3 false.
- **The detector found 8 misses the census had not** - it is now 19 verified
  positives, and those 8 went into the template.
- Invariants pinned by tests: FLAG only (`qa`, NEVER `auto`), above the `n==0`
  and `lol_logo` rules, below `watermark_ocr`. One auto was lost on purpose
  (`239f` has a banner AND an overlay).
- Template is a derivative of DA's watermark -> `ops/runtime/` (gitignored),
  rebuilt via `--build-overlay-template`; missing template = flag off = v2.
- Suite 1853/18. Still open then: REMOVAL, thin signatures, `110-cleanup`.

### Then BUILT the REMOVAL (LEDGER 94) - reduced, NOT erased

- **Detector score median 0.565 -> 0.112 over the 19 confirmed frames; 17 of 19
  drop under the flag.** `estimate_matte` + `remove_overlay` invert the matting
  equation `J = (I - aW)/(1-a)` - faithful, no fill, outside-identity by
  construction.
- Method: register -> background seed by interpolating DOWN COLUMNS (row-wise
  biased alpha 20% low; a median seed is R&D method 4's recorded failure) ->
  alpha shape = median of `(I-J)/(W-J)` -> ONE gain fitted against the
  detector's own post-removal score (optimum 2.0, interior).
- **Two dead ends, measured, do not redo:** per-pixel least squares reaches only
  R^2 0.10 here (seed error > mark; pooling made it worse), and per-pixel W
  DIVERGES (0.149 -> 0.174 -> 0.254) because alpha and W trade off.
- **At 1:1 a faint ghost survives.** Not operator-grade. Ships as a QA-lane
  candidate generator (`--build-overlay-matte` / `--remove-overlay`), never
  auto. The rest needs R&D section 3 items 3-4 (matting-Laplacian + IRLS).
- A synthetic fixture caught a latent DETECTOR bug: clipping the TEMPLATE (not
  just the image) can saturate it to a constant and collapse the score to 0.0.
- Suite 1864/18.

**NEXT - and NOT what it first looked like.** "Matting-Laplacian + IRLS" is
ALREADY BUILT: `tools/lw_clean_dekel.py` (LEDGER 29, `bad25c8`) has Levin's
closed-form matte, IRLS and sub-pixel alignment, and it was measured to CAP with
the same dark-stroke ghost - the mark is white-fill PLUS dark-outline text, which
no single achromatic W can invert. The shipped answer is LEDGER 30,
`tools/lw_clean_iopaint.py`: masked LaMa with a COMPLETE mask covering the dark
OUTLINE, seeded by a cross-image filled matte. **So the real next task is to feed
THIS session's overlay matte into that mask builder for the centre-overlay
family** - `build_watermark_mask` + `MATTE_ALPHA_THR` in `lw_clean_iopaint.py`
already take a filled matte. **Do NOT redo:** pure algebraic Dekel (measured cap,
LEDGER 29), the per-pixel least-squares fit (R^2 0.10) or per-pixel W (diverges).

---

## 2026-08-10/11 - intake x4, clean-retry-degrades half 1, venv-destroying test bug

Three commits, all CI green: `2958338` (retry default), `1ea9144` (suite venv
guard), `ee73136` (production venv guard). Suite 1808/18 on 3.14; lw-clean venv
1822/10 with 3 pre-existing failures. LEDGER 90 has the full record.

- **Intake:** 4 DeviantArt previews in, Tier 0 found no local match (hamming
  18-22), Tier 1 decoded + fetched all 4 quota-free. Two real gains (sona,
  orianna -> 1920px); kaisa + amazingeudora are still preview-grade.
- **clean-retry-degrades half 1 is ANSWERED with measured numbers:** retries won
  0 of 3 adjudicated slugs; `_02` lost on seam 14/15; `_03` "wins" only by
  repainting 2.66x the area and was rejected 9/9. `max_attempts` 2 -> 1, because
  `_auto_inpaint` recomputed a bit-identical inpaint on attempt 2.
- **The test suite was deleting Pillow from the lw-clean venv on every full
  run** (ultralytics autoinstall via a patched `PIL.Image.open`). Fixed in both
  the suite and the production tool. Venv then rebuilt clean, 54/54 packages,
  CUDA live.

**Do NOT redo:** the retry default + both autoinstall guards are shipped; the
venv is rebuilt and verified (old backup deleted, pip cache deliberately kept).
**Still open + unexplained:** the 3 venv-only concurrency failures
(`test_loop_concurrency` x2, `test_three_way_concurrency`) - verified
pre-existing at `78d0ad1`, 3.12-only, invisible to CI (3.14). Next up is the
`cleaning-detector-precision` half of the ROADMAP item.
