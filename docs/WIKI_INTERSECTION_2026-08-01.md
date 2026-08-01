# The corpus/wiki intersection, measured - 77 confirmed (2026-08-01)

The open question `docs/MCP_LIFT_P3_2026-08-01.md` refused to guess at:

> **That this helps the EXISTING corpus.** The wiki hosts OFFICIAL Riot splash
> art. A large part of LW's corpus is fan art off DeviantArt and wallpaper
> aggregators, which no wiki hosts. [...] the honest next step is to count that
> intersection before building anything.

Counted. **77 corpus images are confirmed to be the same artwork as a canonical
wiki splash, and every one of those 77 has a wiki source at or above the
2560x1440 target - median 7.4x the target pixel count.**

## Method, and why it is not a name match

A name match cannot answer this: most of the corpus is fan art OF a champion,
not the official splash, so "Ahri appears on the wiki" says nothing about
whether any particular Ahri image is recoverable from it. The match is made on
pixels.

1. **Wiki index.** `Category:High definition champion skins`, walked to the end:
   **2047 HD titles, 173 champions**. One category walk, not 173 per-champion
   prefix walks - the prefix path is what produced the `Vel'Koz` false zero in
   the P3 probe.
2. **Corpus index.** `docs/research/corpus/CHAMPION_ATTRIBUTED_330.md` - 330
   attributed images, 111 champion labels, all 330 paths verified present on
   disk.
3. **Join on a normalized champion key** (case-folded, non-alphanumerics
   stripped) so `Kaisa`/`Kai'Sa`, `Lee Sin`/`LeeSin`, `Velkoz`/`Vel'Koz` collapse
   to one key. Without this the join loses `Lee Sin`, `Miss Fortune`,
   `Xin Zhao`, `Renata Glasc` and `Kai'Sa` - the same class of miss twice over.
4. **Thumbnails, not originals.** `iiurlwidth=256` on every candidate: 998
   distinct HD titles fetched as thumbs rather than ~6 GB of full splashes.
5. **Two independent metrics.** dHash (64-bit, structural) for the sweep, then
   every candidate re-scored with a normalized mean-absolute-difference on a
   64x36 grayscale. Both views are computed twice - whole frame and centre-cropped
   to 16:9 - because a corpus image is always 16:9 after first pass while a wiki
   splash is ~1.64:1, so some crop always happened.

## Controls, reported before the count

Positive controls are corpus rows whose own description says "official splash";
negatives are rows described as fan art or AI-generated.

| control | n | min | median | max |
|---|---|---|---|---|
| POSITIVE ("official splash") | 29 | 0 | **3** | 27 |
| NEGATIVE (fan art / ai-gen) | 26 | 1 | **21** | 27 |

Medians 3 vs 21 separate cleanly. The tails overlap, so the tails are not
counted on one metric alone - which is what the second metric is for:

| dHash band | n | MAD min | MAD median | MAD max |
|---|---|---|---|---|
| strong, d<=6 | 81 | 0.19 | **2.73** | 23.75 |
| grey, d 7-14 | 14 | 8.31 | 19.25 | 55.33 |
| far, d>=25 (sample) | 32 | **32.49** | 51.75 | 72.34 |

**False-positive check: 0 of the 32 far-band rows were accepted by the second
metric.** The two metrics are not measuring the same thing twice.

## The count

Of **292** attemptable rows (38 of the 330 carry group-splash or non-LoL labels
like "K/DA group", "Star Guardian group", "Non-champion / non-LoL / UI", which no
single-champion wiki file can match):

- 81 rows at dHash d<=6, of which **73 are confirmed by both metrics**
- **8 rows are dHash-only and are NOT counted** (see below)
- 4 grey-zone rows (d 7-8) are rescued by the second metric
- **Total confirmed: 77**

77 confirmed = **23.3 percent of the 330 attributed corpus**, 26.4 percent of the
292 attempted. 58 sit in `2.First Pass Done`, 19 in `reference_pictures`. They
cover 50 distinct champions and map to 77 DISTINCT wiki files - no two corpus
images matched the same file, which is a sanity check the join could have failed.

**This is a LOWER bound on the whole corpus.** The 122 images in
`CHAMPION_UNKNOWNS.md` were never swept, and only attributed images can be
matched at all.

## The 8 dHash-only rows are a category, not noise

They are not counted, and they are worth naming because they will recur:

```
d=3  mad=23.75  star-guardian-kaisa-by-fudoyuseivn...   -> Kai'Sa StarGuardianSkin HD
d=2  mad=20.14  camille-petals-of-spring-lol-skin...    -> Camille PetalsofSpringSkin HD
d=1  mad=19.25  jayce-petals-of-spring-lol-skin...      -> Jayce PetalsofSpringSkin HD
d=4  mad=16.83  foreseen-yasuo-wallpaper-4k-by-fudo...  -> Yasuo ForeseenSkin HD
d=3  mad=16.02  yasuo-petals-of-spring-lol-skin...      -> Yasuo PetalsofSpringSkin HD
d=2  mad=14.24  soraka-soraka-league-of-legends...      -> Soraka DawnbringerSkin HD
d=5  mad=13.95  snow-moon-ahri-wallpaper-4k-by-fudo...  -> Ahri SnowMoonSkin HD
d=0  mad=13.57  18_cleanup.png                          -> Nilah OriginalSkin HD
```

Same composition, different pixels - fan-made 4K wallpapers DERIVED from the
official splash, and aggregator re-treatments of it. Structure agrees, content
does not. These are exactly the rows a canonical-source tier must NOT silently
replace: the operator chose that treatment. A single-metric gate would have
swapped all 8.

## The payoff, measured

For all 77 confirmed matches, the wiki file's declared dimensions against LW's
2560x1440 target:

- **77 of 77 are at or above target. Zero below.**
- pixel count vs target: **min 1.44x, median 7.43x, max 19.32x**

So for these 77, a canonical fetch would put first pass on its downscale-only
passthrough branch - the same branch the 46 refs took - instead of an AI upscale.
That is the ADR-002 "one AI upscale" rule becoming a no-op because the source is
already better than the target.

## What this does NOT establish

- **That the wiki file is better than what LW already holds for a given slug.**
  Resolution is not fidelity. The comparison here is wiki-vs-target, not
  wiki-vs-`_firstinitial`. Several corpus sources are themselves 4K/8K
  aggregator files. A per-slug comparison against the held `_firstinitial` is
  still owed before any swap.
- **That a swap is wanted.** The 8 dHash-only rows show the corpus deliberately
  contains derived treatments; the 77 confirmed ones may include chosen crops or
  edits too.
- **Licensing.** Unchanged and unexamined - see ADR-005 and RESTORATION_PLAN
  section 9.

## Next, if a Tier-0.5 canonical-source step is funded

1. Per-slug `_firstinitial` vs wiki-file comparison for the 77 - the only thing
   that turns "a canonical source exists" into "this specific image improves".
2. Sweep the 122 `CHAMPION_UNKNOWNS.md` images to close the lower bound.
3. Two metrics minimum, and the dHash-only band routed to operator review rather
   than auto-accepted or dropped.
4. `?format=original` and fetched-sha256 provenance from the P3 rules.

Do-not-redo:

- Do NOT match on champion name. It answers a different question.
- Do NOT accept a match on one metric. 8 of 81 disagree, and they disagree in a
  systematic way (derived wallpapers), not randomly.
- Do NOT walk per-champion prefixes to build the wiki index - one category walk
  is complete and cannot produce a name-shaped false zero.
- Do NOT fetch full splashes to compare. 256px thumbs separate the bands by a
  factor of 12 in the median.
