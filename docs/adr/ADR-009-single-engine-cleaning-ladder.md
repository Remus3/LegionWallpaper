# ADR-009: The cleaning stage runs ONE engine per submission - the cross-engine ladder is not automatic

**Date:** 2026-08-12
**Status:** Accepted

## Context

Stage-2 cleaning grew a cross-engine ladder in practice: LaMa erase
(`lw_clean_pass`) on attempt 1, SDXL reconstruction (`lw_clean_sdxl`) on attempt
2, IOPaint-emulation masked LaMa (`lw_clean_iopaint`) on attempt 3. Nothing in
code chained them - the ladder was fired on a REJECT by the operator or the
cleaning-pass skill - so the first half of `clean-retry-degrades` (defaulting
`max_attempts` to 1, commit `2958338`) left the cross-engine spend untouched.

The open question was whether the ladder should be gated on a measured
improvement or dropped. It was answered with a full-stage census, not a sample -
21 slugs, 18 with 2+ workings, 50 rejected workings, 24 retries scored against
their own `_01` with the cleaning gate's metric functions
(`tools/lw_clean_retry_probe.py --metrics`, re-run 2026-08-12; full writeup in
`docs/CLEAN_LADDER_DECISION_2026-08-12.md`):

1. **The ladder has never produced a winner.** Of the 3 slugs the operator has
   adjudicated, retries won 0 - two settled on `_01`'s content and one on
   `_cleaninitial`. Resolution is by APPROVE_CLEAN sha256, because the approving
   `_03`/`_04` are `operator-select` COPIES of earlier content.
2. **`_02` (sdxl-animagine) strictly degrades:** n=15, seam_ssim better than
   `_01` in 1 and worse in 14, editing 1.66x more area and moving further from
   the initial in 14/15.
3. **`_03` (iopaint) wins seam and loses anyway:** n=9, seam better in 6 - while
   repainting 2.66x the area, and all 9 were rejected.
4. **No metric can serve as the gate.** Across the 24 scored retries the seam
   gain tracks the edit area (Pearson r = +0.46; mean area ratio 3.06x when a
   retry gains seam versus 1.61x when it does not). Gating the ladder on seam
   would select for the biggest repaint - the same failure mode as the settled
   ruling that `overlay_score` is a DETECTION flag and never a removal-QUALITY
   gate (LEDGER 101-103).
5. **The reject labels are per-ENGINE, not per-image.** The 50 rejects are three
   blanket verdicts with identical timestamps and notes across the whole queue
   ("swap LaMa erase -> SDXL Animagine reconstruction", "block-SDXL rejected;
   redo via Dekel", "operator reject: corrections are contextually incorrect for
   the image"). Per-slug ladder spend buys a decision taken once per engine.

## Decision

The cleaning stage runs ONE inpaint engine per submission. `lw_pipeline
save-working` refuses (exit 3) a `--tool` that introduces a second engine for a
slug already carrying cleaning workings from another engine, unless the caller
passes `--allow-ladder`. The engines themselves are kept and stay
operator-invocable; what is removed is the automatic chain on REJECT.

## Consequences

**Good:** a REJECT no longer spends a second and third GPU pass whose measured
base rate of winning is 0. The queue's real question - which ENGINE fits this
mark - is asked once, by the operator, instead of being re-litigated per slug.
The gate fails closed: an unclassified new worker counts as a second engine, so
a future engine inherits the rule rather than slipping past it.

**Trade-off:** a slug that genuinely needs a different engine now costs one
explicit flag. Bookkeeping tools (`operator-select`, `clean-scan`, `manual`,
`qa`) and an untagged operator save are exempt, so resolving a rejected queue by
hand is never blocked - the operator is never refused, mirroring ADR-008.

**Watch for:** the gate is cleaning-stage-only; if a ladder appears on final or
last, it needs its own measurement, not an extension of this one by analogy.
Re-open the ladder only with a measure that predicts the operator's verdict on
held-out slugs (not seam_ssim, and not any metric that rises with edit area), or
with an engine that beats `_01` on slugs where `_01` was approved.
