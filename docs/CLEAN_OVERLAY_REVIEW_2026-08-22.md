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
