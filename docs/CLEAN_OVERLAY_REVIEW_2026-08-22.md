# Centre-overlay lane - operator review 2026-08-22: 45 of 45 REJECTED

The overlay lane produced a candidate for every one of the 45 `centre_overlay`
slugs and every candidate FAILED operator review. Nothing was approved and
nothing left `3.Cleaning Scratch`.

This is the sharpest instance yet of the standing ruling that a detection score
is not a quality gate: the lane moved the median `overlay_score` 0.2712 -> 0.0647
with zero frames left at or above the 0.15 flag, and the eye rejected all 45.
Do not read a post-removal score as evidence of a clean frame (LEDGER 101-103).

## The four defect classes, in the operator's words

**A (17 slugs)** - "the painting for the logo is blurry but any
lines/patterns from outside the matte +buffered area do not re-align correctly
which resullts in misalignment of any lines from outside of the matte : the
signature is moderately resolved but missing the (c) portion"

**B (25 slugs)** - as A, "but leaving behind smudges"

**C (1 slug)** - as A, but "the (c) is resolved but is happenstance
due to light on dark"

**D (2 slugs)** - as C, "with the caveat that the signature was
already partially removed"

## What the classes point at

Two distinct defects, and they belong to different stages:

1. **Blur, smudges and misaligned lines** are the LaMa residual FILL. The
   algebraic pre-pass inverts the matting equation per pixel, so it physically
   cannot displace a line or invent one; a fill can and does. Registration is
   not the obvious culprit - the fitted shift is 0 or +-1px on 43 of 45 frames
   (outliers: one 24px, one 30px, one scale 1.12).
2. **The missing (c) and the residual signature** are removal being too WEAK,
   which is the already-documented partial state of the overlay removal half.

The review sheet now shows three columns per slug - before, algebraic-only
(no fill), and after (LaMa fill) - so the next operator pass can answer the one
question that decides the lane: is the un-filled algebraic result shippable, or
does the mark still read at 1:1 without the fill?

## Per-slug verdicts (sheet order)

| # | slug | class |
|---|---|---|
| 1 | `105-cleanup` | A |
| 2 | `107-cleanup` | A |
| 3 | `109-cleanup` | C |
| 4 | `122` | B |
| 5 | `123f` | B |
| 6 | `124f` | D |
| 7 | `221-cleanup` | B |
| 8 | `225f` | D |
| 9 | `239f` | B |
| 10 | `244f` | B |
| 11 | `245f` | B |
| 12 | `261f` | B |
| 13 | `262f` | A |
| 14 | `266f` | A |
| 15 | `270f` | A |
| 16 | `273f` | A |
| 17 | `278f` | A |
| 18 | `284f` | B |
| 19 | `285f` | B |
| 20 | `287f` | B |
| 21 | `32-cleanup` | B |
| 22 | `9-cleanup` | B |
| 23 | `aatrox-the-darkin-blade-in-flames-by-vexxsoul-dm6j4xi-pre` | B |
| 24 | `ahri-by-stellastria-dmbclo0-pre` | B |
| 25 | `ahri-league-of-legends-by-khanzaaiart-dmbzcmq-pre` | B |
| 26 | `aidraw-2662100118-by-watercolornessie-dma7o8j-fullview` | B |
| 27 | `ashe-by-stellastria-dlzcque-fullview` | B |
| 28 | `bamboo-gal-seraphine-by-mrphantomknight-dm1rp4q-fullview` | B |
| 29 | `bayonetta-by-stellastria-dm7iirw-pre` | B |
| 30 | `bayonetta-by-stellastria-dm7iiug-pre` | B |
| 31 | `caitlyn-by-pebano1-dm9fw9z-fullview` | A |
| 32 | `dark-cosmic-ahri-by-pebano1-dlnxav6-pre` | A |
| 33 | `dawnbringer-soraka-celestial-radiance-by-cherrynest-dml4dmh-full` | A |
| 34 | `fierce-enforcer-of-piltover-by-vexxsoul-dm5crlf-pre` | A |
| 35 | `inkshadow-kai-sa-by-pebano1-dm7m9lz-fullview` | A |
| 36 | `mecha-ahri-by-smalltavernx-dia857d-pre` | B |
| 37 | `meramora-artwork-by-meramora-dm9c8hi-pre` | A |
| 38 | `miss-fortune-by-stellastria-dmcdsno-fullview` | B |
| 39 | `riven-broken-blade-unbroken-will-by-vexxsoul-dm9po91-fullview` | A |
| 40 | `seraphine-stage-of-brilliance-by-vexxsoul-dm5uzf1-pre` | A |
| 41 | `syndra-league-of-legends-by-smalltavernx-dlsfckr-pre` | B |
| 42 | `syndra-league-of-legends-by-smalltavernx-dlsfcue-pre` | B |
| 43 | `the-ruined-king-viego-by-vexxsoul-dm6j4mu-pre` | A |
| 44 | `viego-the-king-by-slimshadywallpaper-dhawigh-pre` | B |
| 45 | `viego-the-ruined-king-by-slimshadywallpaper-dgemoim-pre` | A |

## Round 2, same day: the algebraic-only column was reviewed too - 2 of 45

The operator reviewed the un-filled (algebraic-only) column and passed exactly
two frames, both on the SIGNATURE only:

- `32-cleanup`
- `9-cleanup`

All other 43 failed. That answers the question the three-column sheet was built
to ask, and it answers it against the fill hypothesis: dropping LaMa does NOT
make the lane shippable, because the removal itself is too weak. Fill tuning is
moot until removal is stronger - do not spend a pass on it.

## The lane's own instrumentation carries NO signal about the outcome

Every recorded parameter for the two passing frames sits INSIDE the failing
distribution - measured, not assumed:

| field | pass (n=2) med/min/max | fail (n=43) med/min/max |
|---|---|---|
| score_before | 0.2528 / 0.2325 / 0.2731 | 0.2712 / 0.1508 / 0.6958 |
| score_after | 0.0748 / 0.0645 / 0.0850 | 0.0647 / 0.0487 / 0.0942 |
| gain | 2.0 / 2.0 / 2.0 | 2.0 / 2.0 / 2.0 |
| seed_px | 17744 | 17778 / 17713 / 21127 |
| mask_px | 34938 / 32195 / 37682 | 43455 / 28315 / 59519 |
| mask coverage pct | 11.90 / 10.96 / 12.83 | 14.80 / 8.69 / 20.31 |

Both passes fitted shift (-1, 0) at scale 1.0, but three FAILING frames fitted
the same shift, so registration does not separate them either.

The consequence is structural, not cosmetic: the single global gain (2.0) was
fitted by grid search against the DETECTOR'S OWN post-removal score, and the
operator's two reviews have now falsified that score as a proxy for correctness
at both ends - it called all 45 clean when none were, and it cannot tell the two
acceptable frames from the 43 unacceptable ones. Any further tuning loop that
optimizes against it is optimizing against a measure known to be blind. A
stronger removal needs a different objective with an anchor the eye agrees with.

## Round 3: the region, singleton and faint lanes were reviewed - all fail, two causes

The operator reviewed the other three sheets. Verdict on every candidate:
"all of them fail as the entirety of the cropped regions are being blurred out
in the image". Two separate problems came out of it.

### Cause 1: the coverage guard was gated on the wrong thing (our bug)

The faint lane REFUSES to inpaint when the mask covers more than 25% of the ROI.
That guard was written `if faint and not faint_mask_ok(cov)`, so the region lane
walked straight past it. Measured over the region lane's own records:

| lane | n | median mask coverage | over 25% | over 40% |
|---|---|---|---|---|
| not_border (region) | 27 | 47.6% | 24 | 16 |
| singletons (region) | 3 | 30.9% | 2 | 1 |
| faint | 7 | 10.5% | 1 | 1 |

A mask covering half the ROI is the picture, not a mark - which is exactly what
the operator saw. The guard's own reasoning was never faint-specific, so it is
now shared (`COVERAGE_MAX`, `mask_coverage_ok`), and a refusal DELETES any
candidate a previous permissive run left on disk, so a stale after-image cannot
keep appearing in the review sheet as if it were a result. Re-run under the
guard: region 27 -> 3 candidates, singletons 3 -> 1, faint 12 -> 9. The rest
refuse to the human lane, which is the correct answer, not a regression.

### Cause 2: the detector has FALSE POSITIVES - in-art content is not a mark

Seven slugs were flagged on content that is part of the artwork. The operator
named each one:

| slug | lane | what was flagged |
|---|---|---|
| `177-cleanup` | region | "faker on the jacket is not a signature/logo to remove" |
| `186-cleanup` | region | "unto darkness unto light is not a signature/logo to remove" |
| `193-cleanup` | region | "snowflake is not a signature/logo to remove" |
| `darius-the-hand-of-noxus-by-vexxsoul-dm8cizj-pre` | region | "no mercy no retreat in noxus, strength and its icon ... on the left side" |
| `75f` | faint | "is not a signature/logo to remove" |
| `dbwtlkx-eeb94ce2-166d-4457-abc3-615a5bc07fd4` | faint | "is not a signature/logo to remove" |
| `image3` | faint | "is not a signature/logo to remove" |

This OVERTURNS the standing "false positives are currently zero" claim, which
came from the 2026-08-11 precision census. Note what the two censuses actually
measured: that one scored the detector's own bottom-band output, and these seven
are in-art TEXT and ICONOGRAPHY - lore lines, a jersey name, a faction motto and
its icon, a snowflake. Nothing in the gate distinguishes typography that belongs
to the picture from typography stamped on top of it, and the corpus is League
splash art, where in-art lettering is common. These seven frames carry no mark
to remove and must not be inpainted at all.

### Disposition of the seven: approved UNEDITED (operator call, same day)

They carry no mark, so they took the same unedited passthrough the 460 `clean`
slugs took - `save-working --tool clean-scan` -> `submit` -> `approve`, original
pixels intact, no inpainting, `--actor tool:auto-approve` so the ADR-008 rail
sees a non-operator approver. 7 of 7 landed; `4.Cleaning Done` 485 -> 492,
`3.Cleaning Scratch` 87 -> 80.

