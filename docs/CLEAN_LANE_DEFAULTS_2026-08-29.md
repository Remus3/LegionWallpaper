# The two cleaning lanes: `--scoped-revert` defaults ON, `--stubs` stays opt-in

_2026-08-29. Settles the "NEXT" left by `docs/CLEAN_CHORD_COVERAGE_2026-08-29.md`:
the operator's eye on the two opt-in lanes, and a verdict per lane._

## Verdict

| lane | verdict |
|---|---|
| `scoped_revert` (`--scoped-revert`) | **DEFAULT ON** |
| `build_stubs` (`--stubs`) | **stays OPT-IN** |

## The run that had never been done

Every recorded run carried at most one of the two flags, and the pair run
(`run_stubs_scoped`) was read as the strongest configuration measured. It was
being compared against the wrong control: **`--scoped-revert` ALONE had never
been run over the queue.** The 2x2 was missing its fourth cell, so the pair was
being credited with everything scoped does on its own.

That cell is now run (`ops/runtime/clean/creditline/run_scoped/`, 39 slugs).

## The measure

`still_reads` is not a verdict (reader silence proves nothing) and no distance
score is one either. What a default flip actually decides is how much MARK is
handed back, so the number here is the one thing that is not a matter of
opinion: **mask pixels that end byte-identical to the untouched frame.** A
revert - whole or scoped - restores the original, mark included, so those
pixels are the mark left standing. 39 slugs, 970,042 mask px.

| configuration | mark handed back | held blobs | partial | slugs the reader still finds a line in |
|---|---|---|---|---|
| whole revert (the old default) | 272,893 (28.13 percent) | 21 | 0 | 13 |
| `--stubs` | 285,870 (29.47 percent) | 37 | 0 | 13 |
| **`--scoped-revert`** | **17,508 (1.80 percent)** | **1** | 19 | **2** |
| `--stubs --scoped-revert` | 29,474 (3.04 percent) | 2 | 33 | 2 |

## Why scoped goes ON

**It is not worse than the whole revert on any of the 39 slugs, and it cannot
be.** The band is a subset of the blob it replaces, and `scoped_revert()` only
takes a band that the ORDINARY verdict passes on
(`tools/lw_clean_spot.py:232-241`) - the radius grows until it does, and if it
takes the whole region the step was a whole revert all along. So the art check
that the whole revert was buying is still the gate; the only thing that changes
is that the stretch of mark with no line near it stops being handed back with
it.

Measured: 28.13 percent -> 1.80 percent handed back, 21 held blobs -> 1, 13
slugs still reading -> 2.

**The stated blocker does not exist at the shipped settings.** `--scoped-revert`
was opt-in because "on akali a blocky smear stands where the bodysuit strap
was". `akali-godly-deer` commits all 17 blobs with 0 held and 0 partial in
EVERY configuration, and its output PNG is byte-identical across all four. The
smear is the FILL's, it is in today's default output, and neither flag moves it
in either direction. The objection came from the p40/p80 cells of the
percentile sweep, where a thicker mask merged the strokes into one blob; it
does not reproduce at the incumbent glyph percentile.

## Why stubs stays opt-in

**Alone it is strictly worse than the incumbent** - 29.47 percent handed back
against 28.13, held blobs 37 against 21 - and the extra holds are visible
damage to the deliverable, not to the art. `107-cleanup` goes from CLEAN to
`(c) SMALL` plainly legible at 1:1.

**On top of scoped it still costs and buys nothing measurable.** 3.04 percent
against 1.80, 33 partials against 19, and it improves not one of the 39 slugs.
The four frames where the pair is worse than the incumbent are all its doing:

| slug | whole revert | `--stubs` | `--scoped-revert` | both |
|---|---|---|---|---|
| 107-cleanup | 3 | 2,202 | 3 | 275 |
| aidraw-2662100118 | 24 | 219 | 24 | 104 |
| inkshadow-kai-sa | 244 | 617 | 244 | 337 |
| viego-the-king | 31 | 128 | 31 | 103 |

The case FOR stubs is protection, not removal: 144 steps that were filled
unwatched become watched. But that benefit has never been shown to protect
anything. On `105-cleanup`, the one slug with a hand-clean capture, stubs make
no difference at all (the output is one sha under all four configurations), and
the last time a stub did act there it was measured BLOCKING a good fill. The
cost, by contrast, is measured on four frames. Kept and reachable, not default.

## The gold, re-measured live

Metric is the lane's own: mean per-pixel max-channel distance to the operator's
accepted final, over the operator's own 82-mask brush (21,184 px).

| | over the brush |
|---|---|
| untouched | 15.454 |
| whole revert | 11.562 |
| `--stubs` | 11.562 |
| `--scoped-revert` | 11.562 |
| both | 11.562 |

Identical because the output PNG is one sha (`ec11b139aec7dc85`) under all four
- 105 carries no held blob in any configuration, so there is nothing for either
flag to change. The acceptance bar for this session is met on what ships.

## What the eye saw

Strips: `ops/runtime/clean/creditline/lanes/REVIEW.md`, one per slug, every
configuration in one column at 1:1, cropped to the pixels that differ between
them (`tools/lw_clean_lane_compare.py`). 19 of 39 slugs differ at all.

- `seraphine`, `259f`, `evelynn`, `queen-of-the-saltwind`: the whole credit line
  is plainly legible under the whole revert AND under stubs, and gone under
  scoped.
- `aatrox`: cleanest at scoped alone. Adding stubs puts visible pale fragments
  back.
- `107-cleanup`: clean under the whole revert, `(c) SMALL` legible under stubs.
- `akali` and `dark-cosmic-ahri` still fail the zero-residue bar under every
  configuration, akali identically so. Neither lane reaches them.

**No configuration passes the zero-residue bar on every frame.** Scoped moves
several frames from "the whole line is legible" to clean and leaves faint
fragments on others. This is a default flip on the best measured configuration,
not a claim that the lane is finished.

## Shipped

- `lw_clean_spot.run_spot_heal(..., scoped=True)` by default. `scoped=False` is
  the old whole-blob revert, one argument away, and it is what the pool-verdict
  tests now pin so they keep testing which POOL decided rather than how much a
  revert hands back.
- `--no-scoped-revert` on `lw_clean_creditline_run.py`,
  `lw_clean_creditline_sweep.py` and `lw_clean_spot.py`, following the existing
  `--no-rollback` convention. `--scoped-revert` is still ACCEPTED and ignored,
  so every command recorded in `docs/LEDGER.md` and the queue docs still runs.
- `tools/lw_clean_lane_compare.py` + `tests/test_lw_clean_lane_compare.py`.
- `stubs` untouched: still `False`, still `--stubs`.

Two census tools call `run_spot_heal` with no `scoped` argument
(`lw_clean_condition_census.py:94-95`, `lw_clean_creditline_census.py:114`) and
therefore inherit the new default. That is intended - a census should measure
what the lane actually does - but any figure recorded from either of them BEFORE
2026-08-29 was measured under the whole revert and does not compare directly
against a fresh run.

## Do not redo

- Do not re-open `--scoped-revert` on the akali smear. It is byte-identical with
  and without the flag; the frame is the fill's problem.
- Do not read the pair run as the strongest configuration. It was measured
  against a missing control and scoped alone beats it on all 39 slugs.
- Do not default `--stubs` ON on the coverage argument alone. Coverage is real
  (144 steps) and its only measured effect on the deliverable is negative.
