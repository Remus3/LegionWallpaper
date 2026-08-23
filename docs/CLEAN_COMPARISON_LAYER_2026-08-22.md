# Track B: something in the stack can finally see a broken line

Forty-five of forty-five automated cleaning candidates were rejected for one
stated reason - lines from outside the matte do not re-align - and nothing in
the repo could measure it. Every gate here counts how much a region changed or
how loud it is; none of them knew that a blade edge entering the top of a credit
line has to come out of the bottom, in the right place, at the right angle.

`tools/lw_clean_lines.py` builds that knowledge and scores a fill against it.

## How the layer is built

From readable art only, BEFORE anything is filled:

1. **Crossings.** Where strong oriented structure meets the mark's boundary. The
   gradient is computed mask-aware - central differences that fall back to
   one-sided rather than read a masked pixel - so not one pixel of the mark
   contributes to the prediction. This is the same trap track A found in the
   busyness measure, and it is closed the same way: a property test wrecks every
   pixel under the mark and requires the layer to come out byte-identical.
   Each cluster of boundary pixels yields ONE crossing at its magnitude-weighted
   centre, with a direction from the cluster's structure tensor (which handles
   the sign ambiguity that averaging raw gradient directions cannot).
2. **Chords.** Each crossing is paired with the one on the far side that faces
   it, agrees in direction, lies on its ray, and whose connecting segment
   actually crosses the mark. The pair becomes a cubic through both points,
   leaving each along its own direction: a prediction about a line that has to
   exist inside the filled region.
3. **Expectation.** The same probe, taken on readable art at the same line just
   outside the mark, so measured and expected are like for like.

The probe answers both shapes real art uses - a step (region boundary) and a
ridge (a thin stroke) - and takes the larger. A small alignment tolerance
(1.5px) is allowed because art curves; it is far below the misalignment the eye
objects to, so "nearly right" passes and "a line, somewhere" does not.

## What it can tell apart

Unit-level, on synthetic art with a line crossing a credit-line-shaped mark:

| fill | median ratio |
|---|---|
| the true art | >= 0.7, verdict intact |
| erased (flattened, what a membrane fill does) | <= 0.3, verdict broken |
| **misaligned** (a line IS there, 7px off) | <= 0.4, verdict broken |

The third row is the whole point. That frame has plenty of contrast inside the
mark - a contrast measure passes it - and it is exactly the defect the operator
named.

## Against the four captures, with labels nobody derived from a measure

The layer is built ONCE per capture from the marked frame and every variant is
scored against those same chords. Labels: the operator's frame and the LaMa fill
were accepted; the healing brush smeared 105 and mangled 107 at 1:1; the
membrane estimate is a blur inside the mark by construction.

median ratio (`python tools/lw_clean_lines_census.py`):

| slug | chords | original | operator | lama | heal | behind |
|---|---|---|---|---|---|---|
| 105 | 4 | 0.986 | **0.934** | **0.909** | 0.535 | 0.297 |
| 107 | 1 | 1.229 | **1.151** | **1.131** | 0.610 | 0.164 |
| 209 | 0 | - | - | - | - | - |
| dgk | 0 | - | - | - | - | - |

intact fraction: operator 1.00 and lama 1.00 on both; heal 0.75 / 1.00; behind
0.25 / 0.00. Every verdict agrees with the label, and the ordering agrees with
the eye.

**209 and dgk produce no chords at all, and that is correct.** A painted
signature on a smooth panel and a block on soft snow have no lines crossing
them to break. The layer reports `no-evidence`, never a pass - the distinction
that a scalar gate cannot make and that got frames approved before.

## Honest limits

- **Low recall.** Four chords on 105, one on 107, none on the other two. This is
  a high-precision, low-recall signal: when it says broken it has been right,
  and it abstains often. It is evidence for a per-step decision, not a
  frame-level verdict on its own.
- **It is sensitive to the crossing threshold, in a way that matters.** At
  `GRAD_MIN` 3.0 the layer picks up weak boundary structure that does not
  actually continue, and scores the operator's OWN accepted frame at 0.354 -
  a false alarm. The default 6.0 keeps only crossings whose expected contrast is
  real. Do not lower it without re-running the census.
- **The pairing tolerances are not knife-edge.** The ordering (operator and lama
  above heal and behind) held on all twelve combinations of angle 30/45/60 and
  ray 6/10. The angle constraint was never binding; `RAY_TOL` was, and at 6.0 it
  was inconsistent with the 30-degree angle tolerance beside it, so it is now
  10.0 - which doubles the chords found on 105 and changes no ordering.
- **`original` scores highest of all.** The mark supplies its own contrast along
  the predicted path, so a marked frame flatters itself. The layer scores FILLS;
  it is not a detector.

## Wired

`lw_clean_tiled.run_schedule(..., lines=True)` (CLI `--lines`) builds the layer
once from the frame before any fill and records a per-step verdict in the plan
(`n_chords`, `lines_per_step`). It RECORDS and does not gate: acting on the
verdict is track C, and nothing here approves a candidate on a scalar
(LEDGER 101-103, and the operator's eye remains the bar).

15 tests in `tests/test_lw_clean_lines.py`, written first (RED confirmed),
including the readable-art-only property test and the schedule integration.
Artifacts: `ops/runtime/clean/behind/lines_census.json` (gitignored).
