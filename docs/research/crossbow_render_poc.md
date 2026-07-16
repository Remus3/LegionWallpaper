# 3D crossbow-render pipeline - recipe + findings (2026-07-16)

A proven capability to extract a League champion's WEAPON geometry from datamined
3D assets and render it isolated, headless, as training-reference images. Built +
tested this session for the W4 Vayne weapon-concept LoRA. **Result for that use:
NEGATIVE** - the renders did not break the weapon-LoRA plateau (see "Verdict").
Kept as a documented, reusable capability; do NOT re-attempt it to fix the weapon
LoRA (measured dead end).

## Why this exists

Vayne's 2D splash art is low-res and stylizes/occludes the crossbow, and the
splash pool is exhausted for clean canonical-crossbow crops (only ~6 clean exist -
the 5 hand-made assets + dragonslayer). The 3D in-game models are geometry-accurate
and multi-angle, so they looked like a better training source. modelviewer.lol
(Khada) has all 20 variants but is Cloudflare-protected + loads via in-app blobs
(NOT scrapeable). CommunityDragon serves the raw game files with no bot-block.

## Pipeline (proven, pip/venv only - no system installs)

venv: `.venv-poc` (Python 3.12), `pip install numpy pillow moderngl pyritofile`
(trimesh/scipy/networkx were used only for exploration, not the final path).

### 1. Acquire (CommunityDragon raw game files)
Discovery: fetch a skin dir URL and grep `href=` in the HTML listing for filenames.
Base Vayne (skin dir = `base`, all-lowercase):
- mesh: `https://raw.communitydragon.org/latest/game/assets/characters/vayne/skins/base/vayne.skn`
- body texture (CDragon auto-converts dds->png): `.../skins/base/vayne_base_tx_cm.png`
- skin bin (resolves asset refs): `https://raw.communitydragon.org/latest/game/data/characters/vayne/skins/skin0.bin`

Per-skin: every Vayne skin ships its OWN `.skn` (none reuse base). Dirs + mesh names:
`skin03`=`vayne_dragon.skn` (dragonslayer), `skin02`=`vayne_victorian.skn`
(aristocrat), `skin11`=`vayne_skin11.skn` (project), `skin25`=`vayne_skin25.skn`
(sentinel). Texture per skin = `vayne_<suffix>_tx_cm.png`.

Sub-blocker: the `.skl` skeleton is NOT exported by CDragon (404) -> bone NAMES are
unavailable (only bone INDICES ship, inside the .skn). Obtainable via a raw WAD
extract if ever needed (still pip-only, pyritofile reads WAD/SKL).

### 2. Parse + isolate the weapon
Parse `.skn` with pyritofile (base Vayne = SKN v2, single Maya-material submesh
`lambert5SG1`, 6509 verts / 9886 tris, per-vertex bone indices+weights + UVs).
The task's "named Body/Weapon submeshes" premise is FALSE - LoL champ meshes are
commonly single-material. Isolate the weapon by BONE SET instead.

Base Vayne crossbow bones (fist dropped for a clean crop): `{9,39,40,41,42,59,60,64,65}`
(the fist bones `{10,53,54,55,56,58}` were identified via a per-bone color-render
pass and excluded). This yields a clean crossbow: brass limbs + pulleys, silver
receiver, red wrist-cuff, no hand.

**Isolation caveat (the real limit):** Vayne's SKELETON is shared across skins, so
the same bone INDICES exist on every skin - but themed skins BIND large decoration
geometry to those same bones (aristocrat bone 10 = 566 verts of dress/bottle;
dragonslayer/sentinel bind wings/capes/boots). So the base bone set isolates cleanly
ONLY on base. Themed-skin isolation needs the `.skl` bone-names or per-skin
connected-component + manual curation - beyond a quick automated pass.

### 3. Render (headless, this Windows box)
`moderngl.create_standalone_context()` works headless on the RTX 5070 (hardware GL
3.3), offscreen FBO -> Pillow PNG. Textured fragment shader samples the `tx_cm`
texture via the parsed UVs with **flip_v=FALSE** (verified; True is garbled).
Render N angles on neutral gray `(128,128,128)`, letterbox to 1024 (reuse
`tools/lw_gen_curate_weapon_crops.letterbox_to_square` + `CROSSBOW_CAPTION`).

## What was produced
16 crops (base + dragonslayer + project + sentinel, 4 angles each); aristocrat
dropped (isolated a wine-bottle prop). Only **base = 4 clean textured crossbows**;
the 3 themed skins isolated poorly (fragmented / spiky-mask / sword-hilt-ambiguous)
per the isolation caveat above.

## Verdict (why this is parked)
The 4 clean base renders were added to the training set (6 -> 10) and a v2 LoRA was
retrained + e2e'd on seed22/33/800. **v2 == v1** - identical dark-bat-wing /
silver-shard plateau, no improvement. Combined with the W2/W3/W4-v1 plateau and the
LoRA-scale sweep (0.8 -> 1.1, also no change), this confirms the weapon reads as a
crossbow-ADJACENT mechanical device, never a textbook repeating crossbow, as a
CEILING of the masked-inpaint + thin-LoRA approach on stylized splash art - NOT a
training-data-quantity problem. So the full 20-skin render pipeline is not justified
for this concept. Operator parked the weapon-quality quest at this ceiling
(2026-07-16). rung=="w4" stays wired + available (M3, commit 0c255d8); it just
can't beat the ceiling.

## If ever reused (other champions / purposes)
The acquire + parse + headless-render chain is low-risk and fully scriptable. The
one hard part is per-skin weapon isolation (needs the `.skl` bone-names or
per-skin curation). Do NOT reuse it expecting to fix the Vayne weapon LoRA.
