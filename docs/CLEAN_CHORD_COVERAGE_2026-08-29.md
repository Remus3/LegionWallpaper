# Chord coverage: the rollback is blind on three quarters of what it fills

_2026-08-29. Follows `docs/CLEAN_CREDITLINE_QUEUE_2026-08-22.md`, which ended
"NEXT: chord COVERAGE, not revert granularity."_

## The defect, restated in numbers

`scoped_revert()` works where a chord exists. It is opt-in because on
`akali-godly-deer` it leaves a blocky smear where the bodysuit strap was, and
the stated reason was that the comparison layer "has no chord there". That is
now measured rather than asserted.

Over the 39 plans the queue run left in
`ops/runtime/clean/creditline/run/*_plan.json`:

| step outcome | steps | masked px |
|---|---|---|
| `no-evidence` (no chord over the step - commits unconditionally) | 269 | 461,326 |
| a chord was there and held or fired | 88 | 507,406 |

**75.4 percent of steps, and 47.6 percent of the pixels the lane repaints, are
committed with the rollback unable to see anything.** Seven of the 39 slugs
carry ZERO chords for the whole mark. `akali-godly-deer` carries 4 chords over
17 blobs, and 16 of its 17 steps read `no-evidence`.

This is not a threshold on the verdict. `_verdict()` in `tools/lw_clean_spot.py`
returns `("commit", "no-evidence")` when no chord enters the step's context
(`tools/lw_clean_spot.py:248-249`), which is the correct default for a rollback
that must never invent damage - but it means coverage, not sensitivity, is what
bounds the whole mechanism.

## Where the chords are lost

Funnel over the same 39 slugs, reproducing each run's layer exactly (mask
pixel counts and per-slug chord counts match all 39 plans):

| stage | count | note |
|---|---|---|
| boundary band pixels | 178,225 | ring of readable art around the mark |
| clear `GRAD_MIN = 6.0` | 24,856 | **13.9 percent** |
| crossings after clustering | 1,566 | no slug hit `MAX_CROSSINGS` |
| pairs surviving geometry | 209 | of 39,699 considered |
| lost to greedy one-pair-per-crossing | 25 | |
| lost to `_expected_at` returning `None` | 82 | **39 percent of the survivors** |
| CHORDS | 102 | |

Two levers, and they are not equal:

1. **`_expected_at` (`tools/lw_clean_lines.py:290-296`).** 82 pairs pass every
   geometric test and are then dropped because the expectation probe cannot
   find readable art at that line within 6px of the crossing. Four of the seven
   zero-chord slugs are in this bucket - they had valid pairs and lost every one
   here. This lever cannot manufacture a chord from noise: the geometry already
   accepted the pair, and the only thing missing is a reference measurement.
2. **`GRAD_MIN = 6.0`.** 86 percent of the boundary ring is never considered.
   Much the wider lever and much the riskier one - lowering it admits crossings
   from noise, and a false chord manufactures a false revert, which is how the
   percentile sweep already failed (`ROADMAP.md`, clean-creditline-queue).

Per the standing rule (start with the tightest set, widen only on test
evidence), lever 1 goes first and lever 2 is not touched in this pass.

## Why `_expected_at` fails here specifically

The credit-line glyph mask is a FIELD OF SMALL BLOBS - 17 on akali - not one
region. `_expected_at` walks back along the line, out of the mark, and asks
`_readable()` for a swath 9px wide across the path (`PROBE_OFFSET 2.0` plus
`ALIGN_TOL 1.5`, checked at `+-(offset + 1)`). Within 6px of a crossing, that
swath usually lands in the NEXT glyph. The probe is not failing to find art; it
is being blocked by a neighbouring letter.

## How far back the probe would have to walk (measured, real frames)

For each of the 82 pairs lost at `_expected_at`, the smallest walk-back distance
`s` at which `_readable()` first succeeds, searched to 40px:

- **46 of 82 are recoverable at some distance** - min 7.5, median 13.0, max 38.5.
- **36 of 82 are never readable at any distance up to 40px.** Those are not a
  reach problem: the probe's own 9px swath does not fit anywhere along that
  line, so a longer walk cannot help them.

| reach | pairs recovered (of 82) |
|---|---|
| 6 (today) | 0 |
| 8 | 6 |
| 10 | 17 |
| 12 | 21 |
| 14 | 27 |
| 16 | 28 |
| 24 | 37 |
| 40 | 46 |

The curve flattens and the far tail is dubious on its own terms - an expectation
measured 30px away along a curving line is a weak prediction of what the line
looks like where the mark crosses it, and `expected` is the DENOMINATOR of every
ratio the verdict reads. So the honest ceiling for this lever is around the
median, not the tail.

## The pairing levers have almost no headroom - measured

Before building anything, the ceiling: if EVERY geometrically valid pair became
a chord - no greedy loss, no `_expected_at` loss, both levers above solved
perfectly - how many of the 269 blind steps would gain evidence?

| layer | blind steps (of 357) |
|---|---|
| today | 269 |
| every valid pair becomes a chord | **235** |
| ... and `GRAD_MIN` 3.0 | 239 |
| ... and `GRAD_MIN` 2.0 | 252 |

A perfect solution to both filter losses recovers **34 of 269 blind steps, 12.6
percent of the gap**. That is the whole prize for fixing `_expected_at`, and it
is not worth a constant.

**`GRAD_MIN` is not a coverage lever, and lowering it makes coverage WORSE.**
239 at 3.0 and 252 at 2.0 against 235 at the incumbent 6.0. The mechanism is the
clustering step: `boundary_crossings` dilates the hot pixels by `CLUSTER_DILATE`
and takes one weighted centroid per connected blob, so a lower floor MERGES
neighbouring crossings into fewer, bigger clusters whose structure tensor gives
a mushier direction. More hot pixels, fewer usable crossings. **Do not redo the
`GRAD_MIN` sweep** - it is falsified in the direction everyone would guess.

## What the funnel actually says

The mask is a FIELD OF LETTERS - 17 blobs on akali, 24 on 266f - and a chord
needs TWO crossings on the SAME small blob. The corpus supplies about one
crossing per blob (1,566 crossings against a comparable number of blobs), so the
pairing requirement is not filtering out chords that exist; it is asking for a
coincidence that mostly does not occur. The layer discards **93 percent of its
own evidence** (1,566 crossings -> 102 chords) by construction, not by tuning.

So chord coverage cannot be bought at any threshold in this module. The question
becomes what a SINGLE crossing is worth.

## What a single crossing is worth: the STUB

A crossing on its own predicts a RAY - the line enters here, going this way, so
it has to continue that way into the mark. It is strictly weaker than a chord:
with no far-side anchor it cannot see MISALIGNED, only ERASED. But ERASED is the
akali failure - a blocky smear where the bodysuit strap was - and erasure is
what the rollback exists to catch.

Ceiling over the same 39 slugs and the same 269 blind steps:

| | blind steps recovered |
|---|---|
| perfect pairing (both filter levers solved) | 34 |
| **a stub with an expectation reaches the step** | **153** |
| still blind after stubs | 116 |

**Stubs are 4.5x the entire ceiling of the pairing levers**, which settles the
direction: coverage comes from spending the 93 percent of evidence the layer
throws away, not from loosening what it keeps.

### The obvious objection, and the guard

A stub assumes the line runs STRAIGHT. Real art curves, and a chord only
survives curvature because it is anchored at both ends. An unguarded stub over a
curving line reads as damage on a fill that did nothing wrong, and a false
revert is not free - it leaves the mark standing and the slug in the hand queue.

So a stub must prove itself on the frame it was built from: score it against the
UNTOUCHED image, where the only correct answer is "intact". A stub that cannot
predict its own source frame is a bad predictor and is never admitted. This is
the same shape as the credit-line reader verifying itself on the string
DEVIANTART - the evidence carries its own check - and it is what separates a
stub from the residue detectors that were falsified.

### Does the straight-ray assumption hold on this corpus?

Every stub and, as a control, every chord, scored against the untouched frame it
was built from - where the only correct answer is intact:

| | proven on its own frame | median ratio |
|---|---|---|
| chords (the incumbent evidence) | 95 of 102 | 1.082 |
| **stubs** | **1,024 of 1,103** | **1.019** |

Stubs are as reliable as chords by the only check either can be given without an
eye, and there are **10.8x as many of them**. The self-check costs 79 of 1,103.

Those 1,103 are every crossing that has an expectation, including the 204 that
chords already spent. `build_stubs` excludes those - one line must not vote
twice on the same fill - and then applies the self-check, so what actually
ships over the queue is **825 stubs against 102 chords**, 8.1x.

## Shipped

- `lw_clean_lines.build_stubs()` - rays from crossings no chord claimed, each
  proven against its own source frame before use. `Chord` gains `kind`
  ("chord" / "stub"), appended at the end with a default, and `score()` rows
  carry it so a caller can tell weak evidence from strong.
- `lw_clean_spot.run_spot_heal(..., stubs=True)` - **opt-in**, off by default,
  the same discipline `scoped` shipped under: nothing already measured moves
  until an eye has seen this lane. The plan records `n_stubs`.
- `lw_clean_creditline_run.py --stubs`.
- `GRAD_MIN` untouched, `_expected_at` untouched. Both were measured and both
  are the wrong lever.
- `build_layer` is now a thin wrapper over a shared `_layer()` pairing pass, so
  stubs can see which crossings a chord already spent. Behaviour-preserving,
  checked against ground truth rather than asserted: `build_layer` reproduces
  the chord count of all 39 recorded plans, 0 mismatches.

### The limit, stated rather than hidden

The self-check is one ratio and it cannot tell a line that DRIFTED off its
tangent from a line the mark ATTENUATED. A semi-transparent mark dims what is
under it, so the ray reads weak on the source frame and a geometrically correct
stub is dropped. On the credit-line lane that costs 79 of 1,103, because those
marks are painted glyphs. A veil lane - the `centre_overlay` bucket - would pay
much more and needs a check that separates the two failures. Pinned by
`test_a_mark_that_attenuates_its_line_costs_the_stub_and_that_is_a_LIMIT`.

A stub also cannot see MISALIGNED, only ERASED. That is the akali failure and it
is the one the rollback was built for, but it means stub-covered steps are
guarded more weakly than chord-covered ones, and `kind` on every scored row is
what lets a caller act on that.
## The run, and the bug it found - which was not in the stubs

First `--stubs` pass over the queue against the recorded run, same inputs, the
flag the only difference. Coverage landed where it was forecast:

```
no-evidence      269 -> 125   (144 steps gained evidence, forecast 153)
evidence         chords 102, stubs 825
```

But 13 steps that ALREADY had chords changed verdict, and **nine of them flipped
revert -> commit**. Both of 259f's went, the slug `scoped_revert` was proven on,
along with one that had read "lines lost 73 percent of their strength".

The cause was in `_verdict`, not in the stubs. It took the median ratio over all
relevant evidence, so 825 stubs entering the same median outvoted the chords
that were reverting: a step with two chords saying "lost 73 percent" and twenty
stubs saying "fine" came out committed. The broken-line rule is an ANY-rule and
cannot be diluted; the strength rule is a MEDIAN and can be, by weaker evidence
that merely outnumbers it. Every one of the nine sat on the strength rule.

**Fix: the two pools are judged separately and a revert from either stands.** A
stub may only ADD a verdict, never soften a chord's. `_pool_verdict()` per kind,
stub reasons prefixed `a stub says ` so the plan records which evidence decided.

Re-run with that in place:

| | recorded run | with stubs |
|---|---|---|
| steps | 357 | 357 |
| `no-evidence` | 269 | **125** |
| committed | 336 | 307 |
| held | 21 | **50** |
| slugs still reading a credit line | 13 | **16** |

All nine dilution flips are gone. The five remaining changes on chord-covered
steps are ALL commit -> revert - purely additive, stubs catching damage the
chords missed, and each names the stub that decided it. 149 steps in total had
their verdict decided by a stub.

### The price, stated plainly

29 more blobs are held, and **three more slugs still read their credit line**
(`ashe`, `syndra`, `inkshadow-kai-sa`, against `soraka` going quiet). A hold
leaves the mark standing, so the lane cleans LESS than it did. That is the
rollback working as designed - "the mark surviving is recoverable; art destroyed
under it is not" - and against the zero-watermark bar none of these frames were
shippable either way. But it is a cost, not a free win.

**Flag for the eye, and it is the important one: `105-cleanup` regressed.** It
went reads 0 -> 1, held 0 -> 1, on `a stub says broke 1 of 17 lines`. 105 is the
one slug with a hand-clean capture to check against, and the lane's headline
number (11.56 against 15.45 untouched and the operator's own 8.08) was measured
there. Whether that stub is protecting art or merely blocking a good fill is
answerable against the gold, and it is the next thing to settle - a stub that
holds the reference slug for nothing would undo the whole case for the default.

Sheets for the eye: `ops/runtime/clean/creditline/run_stubs2/`.
## Checked against the gold, and the first answer was wrong

105-cleanup is the only slug with a hand-clean capture, so the flagged
regression was answerable rather than a matter of opinion. Metric is the lane's
own: mean per-pixel max-channel distance to the operator's accepted final, over
the operator's own brush. It reproduces the published figures exactly (15.454
against 15.45, 11.562 against 11.56), so the harness is faithful.

| | over the brush | over the held blob |
|---|---|---|
| untouched | 15.454 | 15.607 |
| lane, stubs off | 11.562 | 11.727 |
| lane, stubs on (any-break rule) | **15.329** | **15.609** |
| the operator's own fill | 0.000 (theirs scored 8.08) | - |

The stub reverted step 0 on `broke 1 of 17 lines`, and the fill it blocked was
moving the frame TOWARD the hand result. It was blocking cleaning, not damage,
and it gave back the entire 55 percent of the gap the lane had closed on the one
slug that can be checked. 20,487 of the 20,609 px it held came back identical to
untouched.

**Root cause, structural rather than a threshold.** The broken-line rule is an
ANY-rule: one item going intact -> broken reverts the step. That is right for
chords, which are few and anchored at both ends. It is wrong for stubs, where a
blob carries seventeen or more individually unreliable predictors and one of
them misfiring is ordinary. Four of the five chord-covered flips were
single-stub breaks (105 1 of 17, viego 1 of 17, kai-sa 1 of 11, 280f 1 of 1).
It is the same defect as the median dilution, running the other way: first weak
evidence was allowed to outvote strong, then a single weak vote was allowed to
act alone.

**Fix, and it needs no new constant:** the stub pool keeps only the strength
rule, which is a median and therefore already a consensus. A stub may speak
together with the others; it may never act alone. `KEEP_FRACTION` is reused as
is.

## Where it landed

| | recorded run | with stubs |
|---|---|---|
| steps | 357 | 357 |
| `no-evidence` | 269 | **125** |
| committed | 336 | 320 |
| held | 21 | **37** |
| slugs still reading a credit line | 13 | **13** |

105 back to **11.562**, byte-identical to the stubs-off result. No slug's
`still_reads` changed in either direction. Only two chord-covered steps changed
verdict and both are consensus reverts a stub pool found (`280f` step 4 and
`seraphine` step 3, "lines lost 32 / 31 percent of their strength"). 146 steps
had their verdict decided by a stub, 16 of them reverts.

So: **144 steps that were being filled unwatched are now watched, 16 more blobs
are protected, and it costs nothing measurable** - not on the reference slug,
not in what the reader can still find. Still opt-in: the numbers say go, but the
acceptance bar here is the operator's eye on a 1:1 crop and it has not seen this
lane. Sheets: `ops/runtime/clean/creditline/run_stubs3/`.

### What is still blind

116 steps carry neither a chord nor a stub. They are blobs with no line entering
them at all that the layer can see, and no amount of pairing or thresholding
reaches them - a different mechanism would be needed, and this document does not
propose one.

## The remainder, measured: it was two populations wearing one name

_Same 39 plans, reproduced exactly - chords, stubs, blobs and mask px match
every one, 0 mismatches. 116 was the pre-run FORECAST; the run itself leaves
**125**._

| | steps | masked px | band max grad, median | `gradient_behind`, median |
|---|---|---|---|---|
| **flat** - no ring pixel clears `GRAD_MIN` | **54** | 25,618 | 2.2 | **0.59** |
| **blind** - a line is in the band | **71** | 29,447 | 22.6 | 2.11 |
| (all 357 steps, for scale) | 357 | - | - | 2.31 |

`gradient_behind` is the corroboration that matters: it is measured by a
different module, from the picture BEHIND the mark, and it never reads the ring
the first column is computed from. Both say the same thing about the same 54
blobs. Flat art, flat surround.

**So half the remainder is not a hole.** A rollback exists to stop a fill
destroying readable art. Where no line enters the blob there is no line to
break, and reverting would only put the mark back - strictly worse than a fill
that at most left residue. Those 54 steps commit today, and committing is the
right answer; the plan simply could not say whether a step was unwatched or had
nothing to watch.

`no-evidence` was that conflation. `lw_clean_lines.hot_band()` now exposes the
pixels the crossings are already made from - the same `GRAD_MIN`, one
definition, so no second threshold can drift away from it - `boundary_crossings`
is refactored onto it against ground truth, and every step records `surround` as
`flat` or `lines`. It moves no verdict. 0 of the 232 evidenced steps read flat,
which is the consistency check the field has to pass.

### The 71 that ARE a hole

They lose their evidence in the STUB path, and to levers that were swept for
chord PAIRS and never for stubs:

| where the evidence went | crossings near the 71 |
|---|---|
| `_expected_at` returned `None` | 101 |
| a stub exists, its 12px ray missed the blob | 26 |
| the stub failed its own self-check | 13 |
| spent by a chord whose path left the step | 3 |

The reach curve in this document was measured over chord PAIRS, where both ends
must find an expectation and the doc's own caution applies twice. A stub needs
ONE. And `STUB_LEN = 12.0` is labelled in the source as never swept - "one value
that produced a measured result". Neither is the falsified `GRAD_MIN` lever.

## The stub's expectation reach: swept, shipped, and it cost nothing

The reach curve earlier in this document was measured over chord PAIRS, where
both ends must find an expectation. A STUB needs one. Swept over the same 39
slugs with the chords held fixed, scoring blind steps and the self-check
survival rate together - the incumbent cell reproduces the recorded run exactly
(825 stubs, 125 blind, 55,065 px), so the harness is faithful:

| reach | stubs kept | self-check pass | blind steps | blind px |
|---|---|---|---|---|
| 6 (incumbent) | 825 | 91.6 percent | 125 | 55,065 |
| **10 (shipped)** | **912** | **91.6 percent** | **119** | **38,544** |
| 14 | 957 | 91.6 percent | 118 | 38,217 |
| 20 | 1,004 | 91.2 percent | 113 | 36,509 |
| 30 | 1,056 | 90.9 percent | 107 | 35,126 |

10 is where the price is zero. The survival rate does not move at all, so the
87 crossings it admits are as reliable by the layer's own check as the 825
already in, and they reach the BIG blobs: 6 more steps but 16,521 px, 56 percent
of everything that was being filled with a line in the band and no evidence. The
tail is not taken - an expectation measured 30px away is a weak prediction of
the line where the mark crosses it, and `expected` is the denominator of every
ratio the verdict reads. `EXPECT_REACH = 6.0` still governs chords, whose own
ceiling was measured at 34 steps and left alone.

### `STUB_LEN` is swept too, and the incumbent WINS - do not redo it

| stub length | blind steps (at reach 6) | self-check pass |
|---|---|---|
| **12 (incumbent)** | **125** | **91.6 percent** |
| 20 | 132 | 88.6 percent |
| 30 | 135 | 84.4 percent |

A longer ray reaches further and breaks its own straight-line assumption, so the
self-check drops it, and the net is LESS coverage. Same ordering at every reach.
The one knob the last pass shipped un-swept is now swept and closed.

### The run: same inputs, one lever

| | run_stubs3 (reach 6) | run_stubs4 (reach 10) |
|---|---|---|
| steps | 357 | 357 |
| committed / held | 320 / 37 | 320 / 37 |
| stubs | 825 | **912** |
| `no-evidence` | 125 | **119** (54 of them FLAT) |
| slugs still reading a credit line | 13 | 13, and **not one slug moved either way** |
| `105-cleanup` against the operator's final | 11.562 | **11.562** |

Eight steps changed what the plan says. Six are `no-evidence` becoming "a stub
says lines held" - coverage, same action. Two are action flips and they go in
OPPOSITE directions: `bayonetta-dm7iirw` step 0 revert -> commit (the wider stub
pool's median no longer reads a 29 percent loss) and `dark-cosmic-ahri` step 0
commit -> revert (new stubs find a 25 percent one). That is what more evidence
should do, and it is why the held count is unchanged rather than monotone. The
chord pool is untouched by any of it - a stub still may not soften a chord's
verdict, and still may not fire the any-rule alone.

So after this pass the 357 steps stand as: 238 judged, 54 flat with no line to
lose, and **65 genuinely blind** - down from 269 at the start of the day, and
from 116 as forecast at the start of this pass. Sheets:
`ops/runtime/clean/creditline/run_stubs4/`, worst first in `REVIEW.md`.

## Going after the 65: where the last evidence is lost, stage by stage

Same 39 plans, the shipped reach-10 layer, every stage of the funnel
instrumented per blind step - 65 steps, 12,926 px:

| clusters near a blind step | count |
|---|---|
| no expectation, even at reach 10 | 72 |
| a stub exists, its ray entered another blob | 35 |
| `_orient_into` returned `None` - the line runs ALONGSIDE the mark | 20 |
| failed the self-check | 15 |
| spent by a chord whose path left the step | 2 |
| dropped by `MAX_CROSSINGS` | **0** |
| degenerate structure tensor | **0** |

`MAX_CROSSINGS` never binds on any of the 39 slugs. That was asserted in the
first funnel and is now measured.

By step, which is what decides whether a step is a hole at all:

| | steps | px |
|---|---|---|
| **no expectation anywhere** - a line enters, oriented into the blob, and nothing readable can be found to calibrate it | **36** | 8,157 |
| mixed / self-check | 15 | 2,098 |
| every nearby line enters a NEIGHBOUR letter or runs alongside | 11 | 2,359 |
| no cluster of any kind near | 3 | 312 |

So 14 of the 65 are the same kind of fact as the flat 54: nothing of this
blob's own to see. The hole is 36 steps, plus some of the 15.

### The crossing's own gradient cannot stand in for the probe - REFUSED

The obvious way to manufacture an expectation where the probe cannot reach is
to derive it from the crossing's own strength, which is free. Calibrated over
the 1,200 crossings that have both:

| `expected / strength` | value |
|---|---|
| median | 1.834 |
| p10 / p90 | 0.836 / 2.923 |
| IQR | 1.324 - 2.355 |

Fitting the median constant, a derived expectation lands within 25 percent of
the probe's value **46.8 percent** of the time (p10 0.627, p90 2.193). It is a
different operator on a different footprint - `_response` takes the larger of a
step and a ridge answer with an alignment search, the cluster carries one max
gradient magnitude - and they do not track. `expected` is the DENOMINATOR of
every ratio the verdict reads and the strength rule fires at `KEEP_FRACTION`
0.75, so a denominator wrong by 2x manufactures and silences reverts at will.
**Do not redo this.**

### The reach lever is not exhausted, and the rest of it is NOT taken

Of the 366 crossings still without an expectation at reach 10, **162 (44
percent) are never readable out to 40px**: the probe's own 9px swath does not
fit anywhere along that line, so no walk can help them. The other 204 recover
at median 20px - 49 by 14, 105 by 20, 166 by 30.

Reach 20 was run over the whole queue as evidence, and it passes the stated
acceptance bar:

| | run_stubs4 (reach 10, shipped) | run_reach20 (evidence only) |
|---|---|---|
| `no-evidence` | 119 | **113** |
| blind with a line | 65 | **59** |
| committed / held | 320 / 37 | 318 / **39** |
| slugs still reading | 13 | 13, none moved |
| `105-cleanup` | 11.562 | **11.562** |

**It is still not shipped.** The prize is 6 steps and about 1,200 px. What it
costs is two more held blobs - the lane cleaning LESS, each hold leaving a mark
standing - bought with an expectation measured 20px away along a curving line,
which is precisely the weak-denominator objection this document raised against
the pairing tail. The self-check does not price that risk either: it scores the
ray on a frame where the MARK still supplies the contrast, so it cannot
validate the expectation's correctness, only its plausibility before the fill.
Reach 10 was taken because its price was measurably ZERO; reach 20's is not,
and a knob that trades cleaning for coverage wants the operator's eye, not a
sweep. The run is kept at `ops/runtime/clean/creditline/run_reach20/` so the
comparison can be looked at rather than re-measured.

### What the 357 steps are, at the end of this

| | steps |
|---|---|
| judged by a chord or a stub | 238 |
| flat - no line in the ring at all | 54 |
| a line, but it belongs to the letter next door or runs alongside | 11 |
| no cluster near, or no expectation obtainable in principle (44 percent of the misses) | ~19 |
| **a line enters, could be measured, and is not** | **~35** |

That last row is the whole remaining hole, and every lever this document has
tried on it is now either shipped or falsified: `GRAD_MIN` (worse), pairing
(34-step ceiling), `STUB_LEN` (worse), the derived expectation (46.8 percent),
and the reach tail (not free). What is left is not a threshold. It would need
an expectation the probe cannot take - a different measurement of what the line
looks like where the mark covers it - and nothing in this corpus supplies one.

## The two opt-in lanes run TOGETHER, which had never been done

`scoped_revert` (2026-08-23) and `build_stubs` (this document) were built for
different halves of the same problem - one makes a revert cheaper, the other
makes reverts possible where the layer was blind - and every recorded run had
exactly one of them on. `run_stubs4` carries `partial = 0`, so the pairing was
untested. Run over the queue with both:

| | run_stubs4 (stubs only) | **stubs + scoped** |
|---|---|---|
| held - whole blobs undone | 37 | **2** |
| partial - band around the damaged line | 0 | **33** |
| pixels given back | 283,190 | **25,553** |
| committed steps | 320 | 322 |
| slugs the reader still finds a line in | 13 | **2** |
| `105-cleanup` against the operator's final | 11.562 | **11.562** |

The lane KEEPS 257,637 px of fill it was throwing away, a 91 percent cut in
what a revert costs, and every surviving revert scoped to the SMALLEST band in
the ladder (4px). 19 of 39 frames differ, 313,107 px in total.

On `dark-cosmic-ahri`, the frame the operator reported as barely changed: step
0 goes from 7,815 px undone to **835**, step 2 (a chord revert at 73 percent
strength loss, the strong kind) from 2,716 to 866, step 10 from 90 to 89.

### Two readings this run does NOT support

**Reads 13 -> 2 is not a clean sweep, and this run demonstrates the standing
rule better than any argument for it.** `dark-cosmic-ahri` was SILENT in
`run_stubs4` while carrying an almost untouched mark - the biggest blob had
been reverted whole - and it READS in the scoped run after most of that mark
came off. Reader silence is not evidence of removal, in either direction. The
two that still read are `akali-godly-deer` and `dark-cosmic-ahri`; the other
eleven need the eye at 1:1, not the reader's word.

**Four steps changed verdict for a reason that is not the rollback.** Three
reverts became plain commits (`soraka` 3, `meramora` 3, `queen-of-the-saltwind`
5) and one commit became a partial (`276f` 7). A partial leaves a different
frame behind than a whole revert does, so every later step in that slug is
judging different pixels. Expected, and worth stating so it is not read as
instability.

Both flags remain OPT-IN and nothing about the default changes here. This is
the strongest configuration measured so far and it has still never been looked
at: `ops/runtime/clean/creditline/run_stubs_scoped/REVIEW.md`, worst first,
which puts `akali` and `ahri` at the top.
