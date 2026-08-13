# Cleaning ladder decision - measured census, 2026-08-12

Closes the remaining half of the ROADMAP item `clean-retry-degrades`: should the
cross-engine cleaning ladder (lama -> sdxl-animagine -> iopaint) be gated on a
measured improvement, or dropped to a single engine?

**Answer: dropped to a single engine per submission.** The ladder is no longer
fired on a REJECT; a second engine costs an explicit `--allow-ladder`. Recorded
as ADR-009, enforced in `lw_pipeline.assert_ladder_allowed`, pinned by
`tests/test_lw_clean_ladder_gate.py` (14 tests).

## Population

Whole cleaning stage, not a sample: **21 slugs** (18 in `3.Cleaning Scratch`, 3
resolved), **18 with 2+ workings**, **50 rejected workings**, **24 retries
scored** against their slug's `_01` on the cleaning gate's own metric functions.
Re-run 2026-08-12 with `tools/lw_clean_retry_probe.py --metrics` under
`C:\Tools\lw-clean\venv`; it reproduces the 2026-08-10 numbers exactly.

## Finding 1 - the ladder has never produced a winner

Strong labels only (the APPROVE_CLEAN sha256, traced to the LOWEST working
version carrying those bytes, because the approving version is routinely an
`operator-select` copy):

| adjudicated slug | won by |
|---|---|
| `nguyen-ky-phuc-reyjin-leblanc-j-f1` | `_01` (lama) |
| `p08e8-shadow-hunter-vayne-by-namakx-dg9ydp9-pre` | `_01` (lama) |
| `vayne3` | `_cleaninitial` (no clean at all) |

Retries: **0 of 3**. The other 15 multi-working slugs are undecided - every one
of them sits in the queue carrying 2 or 3 rejected workings.

## Finding 2 - the rungs, measured

    _02  n=15 (always sdxl-animagine)  seam better= 1 worse=14 | 1.66x edit area | moved further from initial 14/15
    _03  n= 9 (always iopaint)         seam better= 6 worse= 3 | 2.66x edit area | moved further from initial  3/9

`_02` is a strict degradation. `_03` is the interesting case: it wins seam_ssim
two thirds of the time, and all 9 were rejected anyway.

## Finding 3 - why no measured-improvement gate is available

The only metric on which a later rung ever wins is bought with area. Over the 24
scored retries:

* Pearson r(edit-area ratio, seam_ssim gain) = **+0.46**
* mean edit-area ratio **3.06x** when a retry gains seam, **1.61x** when it does
  not
* 4 of the 7 seam-gaining retries repaint more than 1.5x `_01`'s area, and every
  seam-gaining retry was rejected

A ladder gated on seam_ssim would therefore select for the biggest repaint. That
is the same failure mode as the settled ruling that `overlay_score` is a
DETECTION flag and never a removal-QUALITY gate (LEDGER 101-103): a number
calibrated for one job does not become a ship gate by being available.

The stronger labels cannot rescue a gate either, for two reasons:

1. **The workings of the 3 adjudicated slugs are GC'd off disk.** The metric
   census can only score UNDECIDED slugs, so any threshold would be fitted on
   unlabeled data and validated against nothing.
2. **The 50 rejects are three blanket ENGINE verdicts, not per-image ones.** The
   manifests carry identical timestamps and identical notes across the whole
   queue:

   | when | note | rung |
   |---|---|---|
   | 2026-07-16T20:37 | `swap LaMa erase -> SDXL Animagine reconstruction` | rejects `_01` |
   | 2026-07-16T22:15 | `block-SDXL rejected; redo via Dekel` | rejects `_02` |
   | 2026-08-02T00:11 | `operator reject: corrections are contextually incorrect for the image` | rejects `_03` |

   Per-slug ladder spend buys a decision that is being taken per ENGINE. That is
   the actual shape of the cost: 3 batch runs over 21 slugs, ~50 GPU inpaints,
   3 judgements.

## What was NOT decided

* **The engines stay.** `lw_clean_sdxl.py` remains the content-bearing-mark
  worker and `lw_clean_iopaint.py` remains the proven QA-lane candidate
  generator (it never mutates pipeline state; it prints the save-working and
  submit commands for the operator). Neither is chained automatically any more.
* **The gate is cleaning-stage-only.** No ladder problem has been measured on
  first / final / last, so they are untouched.
* **Repeating the SAME engine is out of scope here** - that is the intra-working
  retry, already fixed by `max_attempts=1` (`2958338`,
  `tests/test_lw_clean_retry_default.py`).

## Re-open conditions

Raise the ladder again only with (a) a measure that predicts the operator's
verdict on held-out slugs - not seam_ssim, and not any metric that rises with
edit area - or (b) an engine that beats `_01` on slugs where `_01` was approved.
