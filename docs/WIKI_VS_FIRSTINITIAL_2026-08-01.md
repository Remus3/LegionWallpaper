# The 77, compared against the held `_firstinitial` - 46 favour the wiki (2026-08-01)

`docs/WIKI_INTERSECTION_2026-08-01.md` confirmed 77 corpus images as the same
artwork as a canonical wiki splash, and reported that all 77 wiki files sit at or
above the 2560x1440 target at a median 7.43x the target pixel count. It also said
plainly what that did NOT establish:

> **That the wiki file is better than what LW already holds for a given slug.**
> Resolution is not fidelity. The comparison here is wiki-vs-target, not
> wiki-vs-`_firstinitial`.

Now compared. **The 7.43x headline does not survive: 23 of the 77 held sources
have MORE pixels than the wiki file, and on raw sharpness the wiki file is the
softer of the two in 35 of 77.** What rescues the case is that the held file's
extra sharpness is mostly ringing - LW's own halo detector says so - which leaves
**46 of 77 favouring the wiki and 31 to keep or hold**.

## What "held source" means here, and the bug that nearly hid it

The held source is what first pass actually started from: `<slug>_firstinitial.*`
beside the output for a staged slug, or the reference picture itself for one
never staged. Resolved: **58 `_firstinitial`, 19 reference pictures**, all 77.

The `_firstinitial` keeps the SOURCE's extension, not `.png` - `shyvana1` holds a
`.png`, `drx-...-lea` and `dark-fire-sword-...` hold `.jpg`. The first run of this
comparison globbed a hard-coded `.png`, found nothing for all 58 staged rows, and
fell back to comparing the 2560x1440 `_firstdone` OUTPUT as if it were the
source. That run was killed and discarded. It would have answered a different
question at full confidence.

## Axis 1 - native pixel count

| | n |
|---|---|
| wiki has more pixels | **54 / 77** |
| held source is equal or larger | **23 / 77** |

`px_ratio` (wiki / held): min **0.25**, median **4.34**, max **36.18**.

Every one of the 23 is an aggregator 8K file - held at 7680x4320 against a wiki
original of 3840x2160 to 7000x3940. `wallpapersden-com-elise-8k` is held at
7680x4324 against a 7000x3940 wiki file; `fright-night-...-zeri` is held at
7680x4320 against 3840x2160, a 4x pixel deficit.

So "the wiki has 7.43x the target's pixels" was true and irrelevant to this
question. The corpus is not made of 1215x717 files.

## Axis 2 - detail at common scale, from ORIGINALS

Both sides rendered to 2560x1440 through the same 16:9 centre-crop + LANCZOS
path, scored with `tools/lw_g1_gate.laplacian_var` so the numbers are in the
pipeline's own units.

**The first attempt at this axis fetched the wiki side as a MediaWiki
`iiurlwidth=2560` thumbnail, which meant the wiki image was resampled by their
thumbnailer while a held reference picture at exactly 2560x1440 was not resampled
at all.** Every worst-scoring row was such a file - a confound signature. Measured
on a 16-row spread (worst, middle, best), original-vs-thumbnail Laplacian ratio:
min 0.953, **median 1.041**, max 1.274. Real, but far too small to explain ratios
of 0.18, so the axis stands - and the numbers below are recomputed from the
original bytes anyway. The correction moved 5-8 rows across the bands and changed
no direction:

| band | from thumbnails | **from originals** |
|---|---|---|
| wiki softer (<0.9) | 40 | **35** |
| a wash (0.9-1.1) | 7 | **13** |
| wiki sharper (>=1.1) | 30 | **29** |

`lap_ratio` (wiki / held) from originals: min **0.203**, median **0.922**, max
**7.598**.

## The adjudication - is the held file's extra sharpness real?

Laplacian variance rewards SHARPENING, not detail, and most of this corpus came
from aggregators that ship pre-sharpened re-treatments. LW already owns the
detector for exactly this question - `overshoot_halo`, the reason the USM census
exists - so it is used here rather than a second definition of quality.

Run with the WIKI original as reference and the held file as candidate: does the
held file push pixels outside the reference's local dynamic range near its strong
edges? The reverse direction is the control.

Over the 35 rows where the held file is sharper:

| | median | max |
|---|---|---|
| **held** `halo_pct` vs wiki reference | **0.1032** | 0.5505 |
| **wiki** `halo_pct` vs held reference | **0.0089** | 0.4646 |

**26 of those 35 are over the 0.05 G1 halo line.** The asymmetry is the finding:
the held file rings against the authentic original at twice the gate's threshold,
while the wiki original comes back clean against the held file at a median an
order of magnitude lower. The extra high-frequency energy is largely artifact.

Worst offenders, all held files ringing hard against their canonical twin:

```
halo=0.5505  lap x0.226  px x7.842   178_cleanup.png   -> Zyra PrestigeCovenSkin HD
halo=0.4619  lap x0.269  px x4.02    111_cleanup.png   -> Diana BloodMoonSkin HD
halo=0.3954  lap x0.218  px x7.597   162f.png          -> Lissandra PrestigePorcelainSkin HD
halo=0.3799  lap x0.431  px x7.43    22_cleanup.png    -> Vladimir MasqueoftheBlackRoseSkin HD
halo=0.3720  lap x0.861  px x36.184  spirit-blossom-irelia-4k -> Irelia SpiritBlossomSkin HD
```

## Verdict, per slug

| outcome | n |
|---|---|
| **wiki is a clear upgrade** - more pixels AND sharper | **22** |
| **held is sharper but HALOED** - wiki is the cleaner source | **24** |
| keep what we hold, or inconclusive | **31** |

**46 of 77 favour the wiki.** The 22 clear upgrades are concentrated exactly where
you would expect: held widths of 1163, 1192, 1500 and 1920 px (median held pixel
count 1.7 MPix), the fudoyuseivn and DeviantArt-preview sources that never had
the resolution. Best case `league-of-legends-shan-hai-lillia` - held 1192x670,
wiki 25x the pixels and 7.6x the detail.

The 31 to keep break down as **23 where the wiki file has fewer pixels** (the 8K
aggregator set) and **13 that are a sharpness wash** (categories overlap). Zero
of them are held at exactly 2560x1440 - those all landed in the haloed group.

## What this still does not establish

- **That the 46 should be swapped.** Cleaner is not the same as wanted: the
  intersection sweep already found 8 rows that are deliberate derived treatments,
  and a haloed-but-chosen file is still the operator's choice. This ranks
  candidates; it does not authorise a replacement.
- **Crop and aspect.** Every measurement here is on a 16:9 centre crop of both
  sides. A wiki original at ~1.64:1 needs a real crop decision, and centre is an
  assumption, not a policy - the same open question as
  `first-pass-alpha-letterbox` sub-shape A.
- **The other 253 attributed images and the 122 unknowns.** Untouched.
- **Licensing.** Unchanged and unexamined.

## Do-not-redo

- Do NOT glob `<slug>_firstinitial.png`. It keeps the source's extension; a
  hard-coded `.png` silently compares the `_firstdone` output instead and looks
  like it worked.
- Do NOT compare a MediaWiki thumbnail against a native-resolution local file.
  Measured cost: median 1.041, max 1.274 on Laplacian variance - small, but it
  lands entirely on one side of the comparison.
- Do NOT read Laplacian variance alone as detail. 26 of the 35 rows it scored in
  the held file's favour are over LW's own halo line.
- Do NOT carry the "median 7.43x the target" figure into a source decision. Its
  denominator is the target, not the held file, and 23 held sources are larger
  than their wiki twin.
