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
