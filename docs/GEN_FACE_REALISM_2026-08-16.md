# splash-booru face realism - measured, shipped

_2026-08-16. Operator direction: "tweak animagine faces more real without going
uncanny." n=3 per arm, matched seeds (2014205137 / 1502121425 / 2002287815),
one fresh process per arm. Direction-finding, not calibration._

## Two facts found before any arm ran

1. **`photorealistic, 3d render` in the splash-booru negative were already
   INERT.** The negative is 93 tokens against CLIP's 77-token window and both
   sat in the discarded tail. Nothing was pushing this base away from realism.
2. **The positive had 8 tokens of headroom** (69/77), and CLI `prompt_extra`
   inserts near the FRONT, so any addition longer than that pushes the quality
   tail (`masterpiece, high score, great score, absurdres`) out of the window.
   Every "add realism tags" arm below is also spending that tail.

## Round A - what moves the face

| arm | change | subject | margin | sharpness | register vs 0.8373 |
|---|---|---|---|---|---|
| A0 | control (shipped style) | 0.2706 | 0.0512 | 537.8 | 0.6843 (-0.153) |
| A1 | pos `realistic face, detailed eyes` | - | - | - | - |
| A2 | neg anti-doll block | - | - | - | - |
| A3 | both, full realism block | - | - | - | - |
| A6 | A3 + `yellow eyes` | 0.2770 | 0.0562 | 484.5 | **0.8350 (-0.002)** |

By eye on the matched seed: A1 improved face modeling but drifted the eyes to
magenta - off Ahri's canon gold. A3 gave the largest structural gain (modeled
nose, lips, eye sockets) and drifted the eyes grey. A6 kept A3's structure and
restored canon eye colour. A2 alone was a small, canon-safe gain.

**The result that outranks the face work:** the realism block moved this base's
rendering register from **0.153 below** the corpus self-similarity ceiling to
**0.002 below it** - the gap ADR-010 flipped the base over, closed on the
SHIPPED base by a prompt change. Caveat per ADR-011: this measures rendering
register only and is blind to hands, weapon canon and likeness.

## Round B - the reference lever (operator-supplied crops)

A6's prompt held fixed; only the IP-Adapter reference varied.

| arm | reference | subject | margin | sharpness | register |
|---|---|---|---|---|---|
| B1 | none | 0.2770 | 0.0562 | **484.5** | **0.8350** |
| B2 | ref1 (Jinx) plus-face 0.3 | 0.2577 | 0.0209 | 411.8 | 0.7248 |
| B3 | ref1 plus-face 0.5 | 0.2143 | **-0.0252** | 267.4 | 0.6610 |
| B4 | ref3 plus-face 0.3 | 0.2882 | **0.0646** | 470.7 | 0.7450 |
| B5 | real Ahri splash 0.3 | **0.2909** | 0.0645 | 268.5 | 0.8343 |
| B6 | ref1 general 0.3 | 0.2763 | 0.0455 | 268.2 | 0.7937 |

**A face reference carrying a competing champion identity is not a style
transfer.** ref1 is Jinx: at 0.3 it pulls Ahri's hair blue-black and drops
subject below the 0.26 floor; at 0.5 the margin goes NEGATIVE and the arm is
0/3. ref3 - a face with no strong champion identity - is the opposite: best
margin in the round, sharpness kept. Only the real-Ahri reference (B5) holds
both identity and register, and it costs 45 percent of sharpness.

The five operator crops sit at ~50 percent face fraction with sharpness
1740-4613 at CLIP's 224. That is the framing LEDGER 111 called "tight" (51
percent) but WITHOUT its blur confound (108), so the open question from that
item - face fraction separated from reference sharpness - is answered: tight
framing is not what hurt; the blurred reference was.

## Round C - what is actually shippable

`yellow eyes` is Ahri-specific and cannot enter a champion-agnostic style
block, so the realism block was re-measured without it.

| arm | change | subject | margin | sharpness | register |
|---|---|---|---|---|---|
| C1 | positive only | 0.2896 | 0.0544 | 366.9 | 0.7958 (-0.042) |
| C2 | positive + anti-doll negative | 0.2811 | 0.0620 | 256.4 | 0.8344 (-0.003) |
| C3 | C2 minus `cel shading` | 0.2843 | 0.0597 | 267.2 | 0.8218 (-0.016) |

The positive carries most of the register gain; the negative carries the rest.
**A prediction was refuted here:** `cel shading` was expected to be the source
of the softness, so C3 dropped it - sharpness did not recover (267 vs 256) and
0.013 of register was lost. The softness comes from the rest of the block.

## Shipped

`tools/lw_gen_styles.json` `splash-booru`:

- positive gains `semi-realistic, realistic face, detailed skin` (79 tokens,
  drops only `absurdres`).
- negative leads with `flat color, cel shading, doll face, plastic skin,
  smooth featureless skin`, and is REORDERED by priority - anti-doll, quality
  core, text/signature/watermark, anatomy core, glasses, pose - because at 103
  tokens the tail is discarded and the naive insertion pushed **`text,
  signature, watermark` out of the window**. What now falls off the end is the
  redundant finger/limb duplicates and the score tags.
- `photorealistic, 3d render` DELETED (measured inert, and contrary).

**Verified by generation with the shipped style and no CLI extras:** subject
**0.2843**, margin **0.0592**, sharpness **519.5**, 2/3 PASS, register
**0.8268 (-0.0105)**. Against the old control that is +0.0137 subject, +0.0080
margin, register 0.6843 -> 0.8268, and sharpness held (537.8 -> 519.5) - the
reorder recovered the sharpness that C2 was spending (256.4).

Champion-specific canon (Ahri's `yellow eyes`) belongs in the brief's
`prompt_extra`. The IP-Adapter stays a per-brief option in the B5 shape - a
real splash of the champion being generated, plus-face 0.3, at a sharpness
cost - never a default, and never another champion's face.

Pinned by `tests/test_lw_gen_data.py`: the realism block must be present, the
negative guards must sit inside the first 20 tags, and the anti-realism tags
must stay deleted. Re-measure with a CLIP tokenizer if the negative is
reordered - the test pins position as a proxy, not the token count itself.


## The pasted-on face - measured, and what fixed it

Operator, on the shipped frames: still reads as a face cropped onto the body,
"perhaps due to light and shadows not matching reference plane & rest of the
body." That is measurable, and the measure was calibrated on the corpus first.

**Instrument v1 was dead and is recorded as a null.** Comparing the face box's
shading-gradient angle against a torso BAND below it spread p10 15 to p90 148
degrees on the REAL corpus - that band is hair, costume and background, not a
lighting plane.

**Instrument v2 compares skin to skin.** The face's own centre pixels seed a
chroma model, that model masks skin frame-wide, and face-skin is compared with
body-skin on level and on modelling (luminance std). On the 21 real splashes:

    level_offset    median +24.3   (p10 -3.0, p90 +45.0)
    modelling_ratio median  0.83   (p10 0.64, p90 1.26)

Real splash art keys the face well above body skin and gives it nearly the same
modelling. The shipped generator produced **+9.9 / 0.62** - under-keyed and
flatter than the body it sits on, which is the pasted-on read exactly.

**Nine arms failed to move it.** Four lighting-tag arms (rim/backlight,
chiaroscuro, an anti-flat negative, and all combined) and two CFG arms (7.5,
9.0) all landed between -6.6 and +9.4 on level; the anti-flat negative INVERTED
it. Then face-region img2img refinement at 3x effective resolution (ROI 344px ->
1024, strengths 0.25/0.35/0.45) moved level the WRONG way at every strength
(-0.1 / -2.0 / -2.6) while modelling stayed at 0.61. **That rules out "the face
is flat because it is rendered small"** - more pixels bought detail, not
integration. A defect worth noting in that arm: the face-pass prompt carried no
champion canon, so the eyes drifted magenta.

**`tools/lw_gen_facekey.py` fixes it in pixels**, and three defects were found
and fixed by measurement on the way:

1. **Feather dilution** - the first prototype blurred the skin mask directly.
   A skin mask is speckled (eyes, brows, lips punch holes), so the blurred
   interior never reaches 1.0 and only a fraction of the computed shift landed.
   It missed its target and moved level DOWN. The mask is now closed before
   feathering, so the interior saturates.
2. **Non-convergent iteration** - "apply, then apply the residual" pushed one
   frame +13.5 -> -2.7, because each pass shifts which pixels the mask selects.
   Each pass is now kept only if it moves the frame CLOSER, with a damped step
   search (1.0 / 0.6 / 0.3) so an overshooting frame gets a smaller correction
   rather than none.
3. **Band regressions** - distance-only acceptance took 3 of 57 frames that were
   already INSIDE the corpus band and pushed them out. Being in the band now
   outranks being nearer its centre.

The correction is multiplicative on luminance (an additive lift greys the skin),
and the skin mask carries the same luminance window the yardstick uses - the
tool must not grade itself on an easier scale than the corpus was measured with.

**Validated over 57 frames** - every frame generated in this study:

    in corpus band   15/57 (26%)  ->  51/57 (89%)
    median level     +5.0         ->  +20.7      (corpus +24.3)
    median ratio      0.615       ->    0.764    (corpus 0.83)
    regressions       none

Six frames stay out of band and the tool leaves them alone rather than damaging
them; on the shipped trio it is 2 of 3, with the third refused at every step
size. An independent probe (a separately-written script) reads a smaller move
than the tool's own numbers on the same frames - same direction, same sign,
smaller magnitude - so the honest claim is that this closes most of the gap on
most frames, not all of it on all of them.

NOT wired into the pipeline: it is a manual tool that writes a before/after
report with an in-band verdict per frame. Whether generated frames should be
auto-corrected is an operator call, and the residual case (a face whose skin
statistics resist every step size) is unexplained.


## Cross-champion validation (operator-directed)

Six champions, 5 frames each on the shipped style, one fresh process per
champion, then keyed.

| champion | frames | scored | in band | median level | median ratio |
|---|---|---|---|---|---|
| Jinx | 5 | 5 | 1/5 -> 4/5 | +11.5 -> +18.0 | 0.58 -> 0.73 |
| Katarina | 5 | 5 | 0/5 -> 4/5 | +22.1 -> +22.0 | 0.37 -> 0.69 |
| Lux | 5 | 5 | 1/5 -> 4/5 | +16.4 -> +17.9 | 0.42 -> 0.77 |
| Miss Fortune | 5 | 5 | 0/5 -> 4/5 | +9.4 -> +21.3 | 0.39 -> 0.78 |
| Vayne | 5 | 4 | 1/4 -> 3/4 | +0.9 -> +18.2 | 0.59 -> 0.73 |
| Yasuo | 5 | 5 | 3/5 -> 5/5 | -1.1 -> +17.2 | 0.66 -> 0.74 |
| **TOTAL** | **30** | **29** | **6/29 -> 24/29** | | |

Every champion improved, no frame regressed out of band, and the correction
generalises past the champion it was calibrated on. Katarina is the clearest
case of what it actually repairs: her level was already fine (+22.1) while her
modelling ratio was the worst in the set (0.37), and the correction moved the
ratio (0.69) without disturbing the level - it is not a brightness knob.

**THE TARGET IS CHAMPION-DEPENDENT, and that is a real limit on the numbers
above.** Re-measuring the band on the 18 detectable real Vayne splashes against
the 21 real Ahri:

    ahri   level median +22.5 (p10  -2.6, p90 +50.0)   ratio 0.81 (0.64..1.25)
    vayne  level median +18.0 (p10 -11.3, p90 +60.2)   ratio 0.98 (0.72..1.53)

Same direction and heavily overlapping, so one global target is defensible -
but Vayne's real art keys the face 4.5 levels less and carries a fifth more
face modelling than Ahri's. A per-champion band would be tighter, and nothing
here justifies treating +24.3 / 0.83 as universal.

**A defect the Vayne set caught:** one frame had no detectable face and the tool
DROPPED it - the output folder came back with 4 of 5 images. A batch tool that
silently loses frames is worse than one that declines to correct them, so a
frame with no face (or too little skin to measure) is now copied through
unchanged and recorded in the report with a `skipped` reason. Pinned by
`test_a_frame_with_no_detectable_face_is_passed_through_not_dropped`. Output
counts are now 5/5 for every champion.


## OPERATOR VERDICT: the correction failed, and the band does not track quality

Frame-by-frame review by the operator, against my measure's 24/29 "in band":

    ahri      01 ok, 02 ok, 03 failed (no change applied)
    jinx      04 a little okay; 01 02 03 05 failed
    katarina  all five failed
    lux       01 a little okay; 02 03 04 05 failed
    miss f.   all five failed
    vayne     01 okay, 03 would be okay but the shadows are too black;
              02 04 05 failed
    yasuo     01 and 05 okay; 02 03 04 failed

Roughly **6 acceptable out of 30** against **24 of 29 "in band"**. The band is
NOT a quality gate. This is the second time in one day that a corpus-statistics
measure ranked output the operator rejects (ADR-011 was the first), and the
lesson is the same: a distribution match is not an aesthetic verdict.

**The named mechanism was real and is now measured.** The operator called it
"mascara like black line and blowing out the colors/shadows/highlights". The
correction scaled raw luminance about its mean, so every deviation was
amplified - including the one-pixel dark strokes that draw lashes, lash lines
and lip lines. Measured over the six champion sets: **0.10-0.25 percent of each
frame newly crushed to <= 8 levels, and darkening of up to 113 levels on
Katarina**, the champion that failed entirely and had the largest gain (her
modelling ratio 0.37 hit the 1.8 gain clip).

**Three defects behind it, all fixed:**

1. **Correction applied to raw luminance instead of shading only.** It now
   splits luminance into low-frequency shading and high-frequency detail,
   corrects the shading, and adds the detail back untouched.
2. **Movement was unbounded.** A pixel may now lose at most `MAX_DARKEN` (12)
   levels and gain at most `MAX_BRIGHTEN` (70), and any step that newly crushes
   or blows out more than 0.05 percent of the frame is refused outright. The
   gain clip fell from 1.8 to 1.35.
3. **The blur padded with zeros**, which depressed the low-frequency term near
   the border; the detail term absorbed the deficit and the correction
   double-counted it - a synthetic frame overshot its target by +22 levels.
   Padding is now edge-replicate everywhere except the mask feather, which
   genuinely wants a taper to nothing at the frame edge.

Measured after the fixes, same frames: **max darkening 113 -> 5 levels, crush
0.25 -> 0.011 percent, blowout to zero**.

## Per-champion bands (operator-directed)

Built from real art in the local corpus - `tools/lw_gen_facekey_bands.json`,
`--champion NAME` selects one. A champion needs >= 5 real images to get its own
band; otherwise the corpus-wide default is used, and the tool PRINTS which it
took.

    ahri     n=30  level +22.4  ratio 0.79
    vayne    n=24  level +14.3  ratio 0.94
    camille  n=5   level +33.3  ratio 0.85
    yasuo    n=5   level +16.4  ratio 0.87
    janna    n=6   level +14.5  ratio 0.74
    vex      n=6   level +11.6  ratio 0.88
    samira   n=5   level  +7.0  ratio 0.78
    _default n=259 level +16.9  ratio 0.84

**This retires the global target and shows it was biased.** The old +24.3 came
from Ahri alone; the corpus-wide median is **+16.9**, so every non-Ahri face was
being pushed about 7 levels too bright before the unbounded gain did the rest.
Champion spread is wide - camille +33.3 against samira +7.0 - so one number was
never going to fit. Jinx, Katarina, Lux and Miss Fortune have 2-3 local images
each and get the default; a proper band for them needs more real art.

**Honest cost of the fix:** in-band fell from 24/29 to 9/29. The old number was
bought with the damage above, so it was never worth what it appeared to be. The
correction is now small and safe; whether small and safe is worth applying at
all is an operator call on the frames, not a call the measure can make.

## Separate and larger finding: non-Ahri generation is deformed

Operator, on the same review: content "aside from ahri - are all vastly
deformed, incorrect positioning and drawing". That is about GENERATION, not
about the face key, and it is the first time the shipped style has been looked
at on champions other than Ahri - every arm in this study, and in LEDGER
107-116, used Ahri. The style's realism block and the whole splash-booru recipe
are tuned on a single champion. Tracked in `ROADMAP.md`.
