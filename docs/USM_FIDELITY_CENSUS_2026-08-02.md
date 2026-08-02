# USM fidelity census - 2026-08-02

The axis the 2026-07-30 halo census deliberately skipped, measured. Operator
direction 2026-08-02: measure fidelity per variant BEFORE proposing a USM number.

**Corpus:** all 17 gated slugs of batch20, named individually (no `--batch`
resolution, so the set is reproducible from this file alone). They now live in
`2.First Pass Done` - the probe's `--scratch-root` was made injectable for that.
**Variants:** `usm 1.2,70,3` (the shipped recipe until today), `1.2,50,3`,
`1.2,35,3`, and no mask at all.
**Command:** `tools/lw_usm_halo_probe.py --slug <x17> --usm 1.2,70,3 --usm
1.2,50,3 --usm 1.2,35,3 --usm none --fidelity --scratch-root "images/2.First
Pass Done"`. 17 of 17 rows `ok`, 0 errors, 0 failed fidelity measurements.
**Raw report:** `scratchpad/usm_fidelity_census.json`.

## Halo - reproduces the 2026-07-30 census exactly

| variant | halo_pct over 0.05 | max | min |
|---|---|---|---|
| `usm 1.2,70,3` (was shipped) | **7 / 17** | 0.1196 | 0.0041 |
| `usm 1.2,50,3` | 2 / 17 | 0.0747 | 0.0017 |
| `usm 1.2,35,3` | **0 / 17** | 0.0427 | 0.0005 |
| no mask | 0 / 17 | 0.0062 | 0.0000 |

Identical to the earlier run to 4dp. That is the control: the probe is measuring
the same pipeline it measured before, so the NEW column below can be trusted for
the same reason.

## Sharpness floor - the reason "no mask" is not the answer

`lap_ratio` has a 1.0 HARD FAIL floor. ADR-006 drops that floor for the
`downscale-only` backend, so the gated population is the 16 `spandrel` slugs.

| variant | worst gated `lap_ratio` (n=16) | gated slugs under the 1.0 floor |
|---|---|---|
| `usm 1.2,70,3` | 1.5489 | 0 |
| `usm 1.2,50,3` | 1.3259 | 0 |
| `usm 1.2,35,3` | **1.1399** | **0** |
| no mask | 0.8175 | **6** |

Dropping the mask entirely trades 7 soft flags for 6 HARD FAILS. It was never a
candidate; it is in the table because it bounds the range.

## Fidelity - the new measurement, and it is not a trade

Worst case per variant across all 17 slugs (`min` where higher is better, `max`
where lower is better):

| variant | ms_ssim min | lpips max | dists max | ssim min |
|---|---|---|---|---|
| `usm 1.2,70,3` | 0.995207 | 0.043743 | 0.037271 | 0.978031 |
| `usm 1.2,50,3` | 0.997324 | 0.024233 | 0.027568 | 0.986739 |
| `usm 1.2,35,3` | **0.998474** | **0.013666** | **0.021092** | **0.989652** |
| no mask | 0.998896 | 0.010271 | 0.020137 | 0.990994 |

**Every metric improves monotonically as the mask weakens, in the worst case and
in the mean.** There is no fidelity cost to usm35 to weigh against its halo
benefit - the mask was COSTING fidelity, not buying it. The expected shape was a
trade-off curve with an optimum somewhere in the middle; the measurement says
there is no trade on this axis at all, and the only thing pulling the other way
is `lap_ratio`.

**Read these numbers for what they are.** `fr_metrics` here is a
self-comparison against the conditioned SOURCE, so a weaker mask is closer to the
source BY CONSTRUCTION. This says the gate's own fidelity metrics improve. It
does not say the picture looks sharper - `lap_ratio` is the sharpness side of the
question, and it is what stops the argument at 35 rather than at 0.

## Decision

**`USM_DEFAULT` moves from `(1.2, 70, 3)` to `(1.2, 35, 3)`.**

At 35: zero halo flags, worst gated `lap_ratio` 1.1399 with margin over the
floor, and strictly better fidelity than the recipe it replaces on all four
scalars. The halo threshold is NOT touched - at 35 nothing flags, so the 0.05
line stops mattering, and we avoid moving a ruler to fit a reading. That was the
one axis explicitly ruled out in the operator answer, on the grounds that it is
the only change that improves the report without improving the image.

`halo_pct` remains monotone in USM percent on every slug, so it stays a strength
dial rather than a defect detector - do not re-read it as one.

## Do not redo

- Proposing a USM number on halo evidence alone. That is what made this census
  necessary.
- Dropping the mask entirely: 6 of 16 gated slugs fall through the `lap_ratio`
  hard floor.
- Re-opening ADR-004. The upscaler contributes almost none of the halo
  (max 0.0062 with no mask); this was never an upscaler problem.
- Reading the synthetic step-edge fixture in `tests/test_lw_usm_halo_probe.py`
  as evidence about mask strength. `halo_pct` SATURATES there - at 35 it reads
  exactly equal to the no-mask variant - which is why that test now pins the
  historical 70 rather than tracking `USM_DEFAULT`. Mask strength is a corpus
  question and is settled here, over 17 real slugs.

## Still open

The 288 already-approved firstdones were produced at usm70. Nothing is lost -
every `_firstinitial` is preserved beside its `_firstdone` and again in
`9.Image Backup` - but they are now on a different recipe from anything produced
after today. Whether to reprocess any of them is an operator call and is NOT
implied by this change; the 7 that carry a halo flag are the obvious candidates
if it is ever taken up.
