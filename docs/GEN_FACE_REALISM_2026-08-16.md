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
