# Settling the veil amplitude (2026-08-12)

The feather work (`docs/CLEAN_VEIL_FEATHER_2026-08-12.md`) left one thing open
and flagged it as untouched: **is the veil's alpha right at all?**

The doubt was specific. `lw_clean_overlay._fit_veil_gain` calibrates the
amplitude by making a ring 16-24px INSIDE the support, after correction, equal a
ring 16-24px OUTSIDE it, uncorrected. Section 3 of the feather doc showed the
support is eroded to stop inside the veil's true edge - so the "outside"
reference ring may itself be veiled, and the rings also sample different ART
(image centre versus surround). Either would bias the fit.

**Verdict: the estimator is sound - the confound is refuted by a control - but
the shipped NUMBER was a boundary solution. The grid is widened, the matte is
REBUILT (section 7), and the whole correction moved by 5 percent: alpha 0.1332 ->
0.1398, or about 1 level of extra darkening on mid-grey art.**

## 1. The confound is refuted, by a clean-frame control

Run the SAME objective, with the SAME support, over 31 frames that carry no
overlay at all. If the fit were reading the centre-versus-surround difference in
the artwork, it would return a large alpha on unmarked art. It does not:

| gain | 0.5 | 2.0 | 3.5 | 5.0 | 8.0 | 12.5 | 18.5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| alpha | 0.013 | 0.053 | 0.093 | 0.133 | 0.213 | 0.333 | 0.493 |
| err, 31 MARKED frames | 20.55 | 16.29 | **14.33** | 15.26 | 22.46 | 53.47 | 120.24 |
| err, 31 CLEAN frames | **11.48** | 14.11 | 18.68 | 25.83 | 44.07 | 80.76 | 161.40 |

On clean art the objective is minimised at the smallest gain on the grid and
rises monotonically - it wants alpha 0. On marked art it has a genuine interior
minimum. The geometry is not manufacturing a veil.

## 2. But the shipped amplitude is a BOUNDARY solution

The cached matte records `alpha 0.1332 = raw 0.0266 x gain 5.0`, and 5.0 was
EXACTLY the last point of the old `VEIL_GAIN_GRID` (0.5..5.0). A value on the
last grid point is where the search stopped, not where the objective turned, and
it was written up as "an interior optimum".

Measured over 31 flagged frames on a grid extended to 19.75, the objective turns
at **gain 3.75 -> alpha 0.0999 (err 14.29)**, and 5.0 is already worse (15.26).

That is a DIFFERENT frame set from the one the matte is estimated on (the 19
confirmed slugs), and the difference between the two is itself the point - see
section 7: rebuilt on its own 19, the same objective picks gain **5.25**, one
step PAST the old ceiling, for alpha 0.1398. Swap the frame set and the estimate
moves by 40 percent. Do not read the 31-frame figure as "the true alpha"; read
it as the width of the estimator's uncertainty.

## 3. Why it barely matters: the objective's precision is ~1 SNR

The clean-frame row above is also a noise floor: even with no veil to fit, the
two rings differ by **11.48 levels** for purely artistic reasons. The veil signal
being fitted is about `alpha * (W - art)` ~ 14 levels. Signal is the same size as
the noise, which is why the curve is flat: gains 3.5 / 4.0 / 5.0 span err
14.33-15.26, i.e. **alpha anywhere in 0.09-0.13 fits the data about equally
well.** The estimator cannot do better than that with two rings.

## 4. What the picture says

`dark-cosmic-ahri` is the frame where the veil is most visible by eye - the
DeviantArt chevron sits over near-black cloth, so its blocks are unmistakable in
the original. Cut at 1:1, original / pre-pass-only / pre-pass + LaMa: the
algebraic pass at the current alpha **flattens the blocks into the cloth**. It
does not leave a bright residue (under-correction) and it does not leave a dark
blob (over-correction). Whatever the last 30 percent of the amplitude is worth,
it is not worth a visible defect in either direction.

## 5. Two measurements that did NOT settle it - do not redo them

- **Same-artwork clean/marked pair: none exists.** All 302 firstdones were
  signature-matched outside the mark band; the best cross-slug correlation in
  the corpus does not reach 0.85, so there are no duplicate artworks at all. And
  every separately fetched DeviantArt source for a flagged slug is watermarked
  too (15 checked, detector 0.15-0.65) - DA marks the intermediary, not just the
  preview.
- **Two served resolutions of the same artwork: no lever.** Five slugs hold the
  same art at two sizes (e.g. `mecha-ahri` 1194 and 1600 wide). Resampled into
  common art coordinates the annulus between the two veil footprints reads alpha
  **0.000-0.004, indistinguishable from its own controls** - i.e. the overlay
  scales WITH the served image here, so both copies are veiled identically and
  the pair carries no information about amplitude. (This does not contradict
  LEDGER 99's 1.12 scale finding, which is about the ratio between a source's
  resolution and the 2560-wide pipeline frame.)
- **A "notch" estimator** - using the unveiled interior of the chevron that the
  support's closing (`VEIL_CLOSE` 51) fills in - gave 0.065 +- 0.017, but its
  veiled/notch pixel sets do not survive inspection: on `dark-cosmic-ahri` it
  reports alpha 0.024 for a frame whose veil is plainly ~0.13 by eye. The
  consensus-whitening quartile used to pick "definitely veiled" pixels does not
  land reliably on the flat veil. Treat that number as refuted, not as evidence.
- **A floor test** (a white veil at alpha a makes a covered pixel impossible
  below a*W) is defeated by the same problem: the recorded support contains the
  chevron's unveiled notch, so 19 of 31 frames show sub-floor pixels that are
  simply not veiled.

## 6. What changed

- `VEIL_GAIN_GRID` extends to 10.0 (was 5.0), well past the measured optimum.
- `_fit_veil_gain` emits a `RuntimeWarning` when the winning gain lands on the
  last grid point, so a boundary solution can never again be recorded as a fit.
- Pinned by
  `tests/test_lw_clean_overlay_veil.py::test_a_gain_on_the_grid_ceiling_is_reported_as_a_boundary_solution`.

## 7. The matte REBUILT on the wider grid

Rebuilt from the same 19 confirmed slugs against the same wide template:

```
veil alpha=0.140 (raw 0.027 x gain 5.25), support 38375 px, residual step 12.45
```

**The fit is now interior** (5.25 of a 0.5..10.0 grid, no ceiling warning), and
it landed ONE STEP past the old ceiling - so the boundary was costing 5 percent,
UPWARD. The 31-frame curve pointed the other way (3.75); that is the SNR-1 point
made concrete, not a contradiction.

Diffed against the backed-up matte, **the veil alpha is the only thing that
moved**: stroke alpha, `W` and the veil support are bit-identical
(`0.1332 -> 0.1398`, +5.0%, = +1.1 levels of darkening on mid-grey art).

Blast radius over all 33 candidates, re-cut with the rebuilt matte:

| | alpha 0.1332 | alpha 0.1398 |
| --- | --- | --- |
| median detector score | 0.0664 | **0.0645** |
| worst score | 0.0955 | **0.0942** |
| under the 0.15 flag | 33 of 33 | **33 of 33** |
| median mask px | 41349 | 41433 (+0.2%) |

Per-frame the score moves by a median of +0.0002, worst +0.0040
(`miss-fortune`), best -0.0090 (`mecha-ahri`); 14 frames improve, 18 worsen -
a wash, exactly what a flat objective predicts. Off disk, the pre-pass frame
changes by **1-2 levels over 13-16 percent of the ROI, maximum 2 levels**, and
by eye on `dark-cosmic-ahri` the chevron still flattens into the cloth with no
dark blob.

The previous matte is kept at
`ops/runtime/clean/_backup_2026-08-12/overlay_matte_wide.npz`; the ring-era and
0.1332-feather candidate sets (`overlay_lane/`, `overlay_feather/`) are both
superseded by `overlay_rebuilt/`. The non-wide `overlay_matte.npz` was NOT
rebuilt - nothing in the removal lane or the gate reads it (`load_overlay_pair`
takes the wide pair; `overlay_score` uses the template).

## Reproduce

```
C:\Tools\lw-clean\venv\Scripts\python.exe tools\lw_clean_detector_probe.py --wide --build-overlay-matte <the 19 confirmed slugs listed in docs/CLEAN_OVERLAY_DETECTOR_2026-08-11.md>
C:\Tools\lw-clean\venv\Scripts\python.exe tools\lw_clean_iopaint.py <slug> --overlay --image <firstdone> --out-dir ops\runtime\clean\overlay_rebuilt\<slug>
```

The probes for sections 1-3 are one-offs; the objective curve is
`_fit_veil_gain`'s own loop evaluated over `VEIL_GAIN_GRID` on band images from
`band_of`, marked set = the 33 flagged slugs minus `110-cleanup` and `122`
(they register at scale 1.12, so the unscaled support does not land on them),
clean set = 31 unflagged firstdones sampled from `2.First Pass Done`.
