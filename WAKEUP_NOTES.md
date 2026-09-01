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

## 2026-09-01 (later) - twenty through first pass, and the watermark under the queue

One commit (`ad99249`), pushed. Suite **2450 passed / 18 skipped** on a fresh
full run (120s) - baseline 2449, +1 for the new regression test. ruff clean,
`verify: ok (604 images checked)` zero mismatches, scan anomalies 0.
Ran `/first-pass` then `/cleaning-pass` over the 24 slugs in scratch.

- **15 slugs reached `4.Cleaning Done` at exactly 2560x1440.** All 20 that
  entered the upscale scored G1 PASS - no FLAG, no FAIL. `clean_done` 492 ->
  507, `clean_scratch` 100 -> 85 (5 new QA + the 80 pre-existing),
  `first_scratch` 24 -> 4.
- **One slug was lost to a quoting bug, not to quality.**
  `deviantart_1375265414_Kai'Sa.jpg` - the apostrophe closed the `r'...'`
  literal in the generated `python -c` snippet and the upscale subprocess died
  on a SyntaxError. Both snippet sites now go through `_pylit()`
  (`json.dumps`); `run_fr_metrics` had the identical pattern and would have
  failed on the same file at the gate step, so it was fixed in the same slice.
  RED-first test `ast.parse`s the snippet and asserts the paths round-trip.
  kai-sa reran to PASS.
- **The QA-queued slugs all carry the DeviantArt preview watermark.** A
  semi-transparent `(c) ARTIST.DEVIANTART.COM` band at y=971..1013 of 1440,
  across three different artists. I cropped the detected boxes and looked - this
  is confirmed, not inferred. It is an artifact of the quota-free
  `intermediary=true` fetch route, so it will recur on every slug recovered that
  way. The gate was RIGHT to refuse (`centre_overlay` x4, `not_border` x1): the
  strip crosses the subject. Doctrine says recover, do not inpaint, when a clean
  source exists - so these want a re-fetch at `original=true` (weekly quota),
  NOT a 660px LaMa repaint through a face. Annotated into all 5 manifests.
- **Checked the 15 shipped rather than trusting the zero-detection verdict.**
  Cropped the same y-band from all 15 plus a full-frame contact sheet: clean.
  The split is by artist - all 15 came from fudoyuseivn.
- **Operator granted the sona crop; it landed in the same watermark queue.**
  `sona-feathers-void` (1920x1280) center-cropped top+bottom to 1920x1080 and
  scored G1 **PASS** (lap_ratio 1.3576, halo 0.0239, msssim 0.9990, lpips
  0.0059), then the cleaning scan routed it to QA on `faint_mark` - and the crop
  shows the SAME `(c) ARTIST.DEVIANTART.COM` band, caught by the faint-mark lane
  at conf 0.12 instead of by a yolo box. So the recovery bucket is **6**, not 5.
  `cozy-fall-with-seraphine` (910px wide after crop) and `leona-and-diana`
  (900px) stay held: both sit under the 1280px G0 floor, so they queue for
  source recovery rather than a thin ~2.8x upscale.

- **Re-fetched the 6 at `original=true` as asked; DeviantArt refuses at source.**
  A control fetch on `akali` came back **byte-identical** to the intermediary we
  already had (same sha256, same 717037 bytes, same 1280x718). The reason is not
  quota and not the missing refresh-token: `gallery-dl -j` reports
  **`is_downloadable: false` on all 6**, across all 4 artists - the artists
  disabled downloads, so DA serves only the watermarked intermediary and no
  OAuth would change it. Worth noting `content.filesize` runs to 28 MB behind a
  1280px served frame, so the clean original exists, it is just withheld. All 6
  manifests carry the finding; the memory now says check
  `gallery-dl -j <url>` for `is_downloadable` BEFORE spending anything, since
  the check is free. **Do not retry this route.**

- **Dropped 3, attempted the hand-clean on 3 - and the hand-clean is a PARTIAL,
  so nothing shipped.** `akali`, `kai-sa` and `xayah` were GC'd via
  `lw_pipeline remove --yes` (full GC, both the scratch folder and the
  `9.Image Backup` entry, matching the `note=full GC` precedent);
  `clean_scratch` 86 -> 83.
- **The DA mark is TWO objects, and only one of them came off.** The credit
  line `(c) ARTIST.DEVIANTART.COM` removes cleanly: a strip mask over the
  measured glyph rows (45px / 39px / 62px bands, 0.9-1.2 percent of frame) plus
  one simple-lama pass, outside-mask MAD exactly 0.000000. Verified at 2x on the
  busiest crossings - the first attempt used the full 58-62px strip and smeared
  neon-jinx's braid, so the band was tightened to the measured glyph rows and
  the braid, zipper and hair now survive.
- **The second object is a big faint LOGO veil mid-frame, and it defeats the
  existing assets.** `overlay_prepass` made all three WORSE: the cached
  `overlay_matte_wide` encodes a DIFFERENT render's credit line
  (`(c) SMALLTAVERNX.DEVIANTART.COM`), so it mis-registers (sona shift
  [43,-35]), leaves the veil and paints red streaks across sona's face. Those
  candidates were deleted. A clean-frame control (two fudoyuseivn `_cleandone`
  frames at the same coordinates, 2.4x contrast) shows no such block edge, so
  the veil is real and not a measurement artifact.
- **Held, not shipped.** Zero-residue is the bar and the veil fails it. The
  partial candidates stay at `ops/runtime/clean/<slug>/<slug>_handclean_cand.png`
  and all 3 manifests carry the attempt. **Unblock:** re-estimate template+matte
  for THIS render via `lw_clean_overlay.estimate_template` / `estimate_veil` once
  a larger same-render frame set exists - deliberately NOT fitted on these 3,
  because the settled ruling puts the veil estimator at SNR ~1 and 40 percent
  movement when the frame set changes. Every future DA-intermediary intake adds
  frames to that set.

- **Still open, all operator-owned:** 3 slugs HELD over the 0.08 aspect-loss cap
  needing a `--crop-overrides` side grant (`cozy-fall-with-seraphine` 1024x512
  too wide; `sona-feathers-void` 1920x1280 and `leona-and-diana` 900x600 too
  tall - and leona also fails G0 at 900px). `1000040081-...-375w-2x` stays
  excluded: a 750x436 source under the 1280x720 G0 floor.

---

## 2026-09-01 (earlier) - intake grew a perceptual gate, and the pipeline grew a reverse

Four commits, all pushed, CI green on each. Suite **2449 passed / 18 skipped**
on a fresh full run (118s); baseline was 2408 and I added 41 tests. ruff clean
repo-wide, drift_guard 0 breaches, `verify: ok (604 images checked)` with ZERO
mismatches. Started as `/intake`, became four fixes the intake exposed.

- **/intake ran: 24 intaken, 2 refused as byte-identical.** Tier-1 token decode
  hit 24/24 and fetched 24/24. Read the gain honestly: 20 gained ~x1.2, 4 were
  already at cap, and the ceiling is **1280px wide** - the quota-free
  `intermediary` cap, NOT true originals. First pass upscales from ~1280, not
  from an artist file.
- **The byte-hash dedup had a hole and it is closed (`2fe8087`).** `unique_slug`
  compared bytes, and only against the ONE colliding candidate slug - a
  re-download under an unrelated filename was compared to NOTHING. Now every
  incoming file is compared against all 605 backup originals, bands delegated to
  `lw_recover.consensus_match` so intake and Tier-0 recovery cannot drift.
  `--allow-near-dup` overrides; imagehash absent degrades to a noted no-op.
- **Swept all 605 for rows the gap let through: exactly ONE** (academy-ahri).
  The 4 review-band pairs sit at Hamming 12-14 between different champions -
  noise floor, not pollution. Do not re-sweep.
- **`remove` and `reopen` exist now (`3d81298`, `b2c932f`).** There was no
  delete path and no reverse move, and the documented workaround moved folders
  by hand - the one thing the single-writer rule forbids. Memory
  `project-reprocess-done-slug` said "the pipeline has NO reverse command";
  that is FALSE now and the memory is rewritten.
- **academy-ahri twin rebuilt from the 1280x756.** Verified the source carried
  REAL detail first (Lap variance 919.4 native vs 645.4 for the preview upscaled
  to the same grid) rather than assuming a bigger render is a better one. G1
  improved on every axis that moved: lap_ratio 1.1263 -> 1.3491, lpips 0.01981
  -> 0.003643, msssim 0.99693 -> 0.999494. Cleaning re-triaged `no_detections`,
  so the original pass-through was correct behavior, not a silent failure.
- **The verify residue is fixed, not documented away (`fa56adc`).** Root cause:
  `backup_put` numbers by ARRIVAL, so a supersede left the CANONICAL name
  holding the old generation. Rejected the tempting fix (rename it so it stops
  parsing and goes quiet) - `_milestone_key` already settled that: "the mismatch
  is noise, the silence reads as a pass". Rotation now happens at reopen time;
  `tools/lw_backfill_backup_generation.py` recovered the row already on disk.
  This also cleared the LEDGER 77/78 residue - hence 604/604 clean.
- **Do NOT redo:** the 605-slug near-dup sweep, the academy-ahri rebuild, the
  backup-generation backfill (idempotent, 0 unexplained). All shipped.
- **Still open, deliberately:** the 2 byte-identical dupes sit in `0.Originals`
  and will report `pending_intake=2` on every scan until GC'd - operator call.
  `data/recovery/fetched/...-pre-2/` staging kept after use.

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
