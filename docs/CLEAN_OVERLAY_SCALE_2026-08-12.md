# Overlay registration: scale, not just shift - 2026-08-12

`110-cleanup` was the one frame neither cleaning lane could clear. The faint lane
is structurally wrong for it (a low-alpha mark under a raised bright threshold),
and the overlay lane - the right lane - reduced it and left the credit line
plainly legible. This closes it, and it turned out not to be a one-image fix.

## Root cause

`best_shift` registers TRANSLATION only. The overlay is composited at a fixed
size on the DeviantArt-served image, and a `_firstdone` is that image resampled
to 2560x1440 - so a frame whose source arrived at a different resolution carries
the mark at a different PIXEL size, and no shift can align it.

Swept a scale factor applied to the template across every flagged slug scoring
under 0.25, plus the case:

| slug | native | best | at scale |
|---|---|---|---|
| `110-cleanup` | 0.1090 | **0.5052** | 1.12 |
| `122` | 0.1696 | **0.6542** | 1.12 |
| `270f` | 0.1548 | 0.1889 | 0.94 |
| `dark-cosmic-ahri` | 0.1508 | 0.1565 | 0.92 |
| `inkshadow-kai-sa` | 0.1758 | 0.1864 | 1.02 |
| the other 9 | - | no gain at all | 1.00 |

Two frames, not one, and both at the SAME 1.12 - and both jump into the range the
well-registered frames already occupy (`mecha-ahri` 0.696, `123f` 0.635), which
is what a correct registration looks like rather than a lucky correlation. So
this is a source-resolution family, not a per-image quirk.

## Two boundaries the fix has to respect

**The scale search is for REMOVAL, never for the gate.** Measured on the top of
the clean population, a max-over-scales lifts
`wallpapersden-com-hd-sejuani-league-of-legends-1920x1080` from 0.1213 to
0.1537 - over the 0.15 flag, a false positive manufactured by the search itself.
That is the same lesson the shift window learned when a +-90/+-200px search
lifted clean frames to 0.095 faster than it lifted positives. `overlay_score`
is unchanged and a test asserts it never grows a scale parameter; only
`best_registration` searches, and it only runs on frames already judged to carry
the mark.

**A non-native scale must be DECISIVE.** Correctly-registered frames still wobble
under a scale search - up to 1.22x the native score (`270f`) - and accepting an
argmax would misregister a frame that was already right. The measured separation
is wide: noise peaks at 1.22x, the two real ones at 3.86x and 4.63x. So
`SCALE_ACCEPT_RATIO = 2.0`, sitting far from both, and a refusal keeps scale 1.0.
That is the safe direction - a wrong scale is a wrong edit, a refused one is only
today's behaviour.

## Blast radius

`best_registration` over all 32 `centre_overlay` slugs plus `110-cleanup`
(pure numpy, no GPU):

```
33 frames, 2 re-registered at a new scale: ['110-cleanup', '122']
31 frames register EXACTLY as before  (same shift, scale 1.0)
```

`scale2d_centered` returns its input untouched at s == 1.0, so those 31 frames
take a bit-identical pixel path and the LEDGER 95/96 candidates stand. Spot-check
on two of them confirms it live: `mecha-ahri` 0.6958 -> 0.0737 and `245f`
0.5858 -> 0.0903, both well under the flag, both at shift/scale unchanged.

## Result

| slug | before | after | by eye |
|---|---|---|---|
| `110-cleanup` | 0.1090 | **0.0868** | credit line GONE, art continuous |
| `122` | 0.1696 | **0.0941** | credit line GONE, faint smudge trace |

Before the fix `110-cleanup` left `(C) SMALLTAVERNX.DEVIANTART.COM` fully
readable on every attempt - the overlay lane at native scale (0.109 -> 0.1042),
the same lane with `--pad 260` (0.109 -> 0.1031), and the faint lane, whose
raised threshold cannot see a low-alpha mark at all (its score went UP,
0.1090 -> 0.1203).

Registration for both: shift (24, -1) at scale 1.12, against (16, -16) at 1.00
before.

Every changed pixel on all four verified frames falls inside one of the lane's
two editors - the algebraic inversion's removal band, or masked LaMa's ROI box.
Nothing is unexplained:

```
110-cleanup   changed 101017   unexplained 0
122           changed  97829   unexplained 0
mecha-ahri    changed  90954   unexplained 0
245f          changed  84532   unexplained 0
```

The per-ROI count alone would have looked alarming (6-11k pixels change outside
the ROI box) and is not a defect: the matting inversion legitimately edits
sub-threshold alpha across the whole band, which is why the in-process tripwire
compares the post-LaMa frame against the PRE-PASS frame rather than the original.

## Notes

* `122` was already flagged at 0.1696 and so already had a candidate from the
  LEDGER 95/96 pass - produced at the wrong scale. It is worth regenerating.
* `110-cleanup`'s gate verdict is unchanged and still `qa/faint_mark`: its
  DETECTION score is 0.109, under the 0.15 overlay flag, and detection did not
  gain the scale search. The faint lane's `FAINT_OVERLAY_DEFER` is what routes it
  to `--overlay`, so the chain now completes without touching a gate threshold.

Reproduce:

```
C:\Tools\lw-clean\venv\Scripts\python.exe tools\lw_clean_iopaint.py 110-cleanup --image "images\2.First Pass Done\110-cleanup\110-cleanup_firstdone.png" --overlay --out-dir ops\runtime\clean\overlay_scale\110-cleanup
```
