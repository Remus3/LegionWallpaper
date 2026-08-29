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
