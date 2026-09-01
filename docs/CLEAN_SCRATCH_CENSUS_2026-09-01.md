# 3.Cleaning Scratch census - 2026-09-01

Generated after a full `lw_clean_pass` batch over the backlog. Every slug in
`3.Cleaning Scratch` was triaged; **not one auto-cleaned**. This file records
why, per slug, so the backlog is a decision and not a mystery.

`overlay_score` is the DETECTOR flag (calibrated on untouched frames, which all
of these are) and is used here ONLY for detection - never as a removal-quality
gate, per the 2026-08-12 ruling.


## DISPOSITION (operator ruling, 2026-09-01)

The ~63 DA-overlay frames are **NOT for deletion**. They go to a hand-clean lane
and their before/after pairs become the ground truth for an automated emulation.
Worklist and rationale: `docs/HANDCLEAN_WORKLIST_2026-09-01.md`. Extraction tool:
`tools/lw_overlay_from_pair.py`.

## Bands

| band | n | reading |
|---|---|---|
| `>= 0.15` (flag) | 41 | DA preview overlay, confirmed |
| `0.10 - 0.15` (defer) | 19 | DA preview overlay, likely |
| `< 0.10` | 12 | mixed - see below |
| shipped as clean-scan | 3 | faint-mark boxes verified at 1:1 as art/edge |
| excluded (ADR-009) | 4 | pre-ruling ladder casualties, all engines already rejected |

## Sub-0.10 band, identified by eye

| slug | score | reason | mark |
|---|---|---|---|
| `anime-poster-of-soraka-from-league-of-legends-by-givemenine-dg8j` | 0.092 | not_border | DA preview overlay |
| `209-cleanup` | 0.090 | not_border | artist signature (handwritten CHENBO 12.29.2024) |
| `mordekaiser-by-michalivan-d5s9q6h-pre` | 0.067 | not_border | DA preview overlay |
| `aurora-fanart-by-lulalakill-dlgo81i-pre` | 0.067 | low_conf | DA preview overlay |
| `p2402-kda-evelynn-by-namakx-dgykw2q-pre` | 0.064 | faint_mark | DA preview overlay |
| `karthasbasefinal-by-alexflores-d7q5tbt-fullview` | 0.061 | faint_mark | DA preview overlay |
| `brair-league-of-legends-by-kairahi-dles4n2-pre` | 0.061 | not_border | DA preview overlay |
| `dragon-slayer-pantheon-by-alexflores-d7fr57n-fullview` | 0.061 | faint_mark | DA preview overlay |
| `akali-godly-deer-by-ryoairtist-dm2su3h-fullview` | 0.058 | not_border | DA preview overlay |
| `dgk8f92-bc10d7a7-f520-4b4f-ad86-ac70f6d50293` | 0.056 | not_border | opaque artist banner (NAMAKX / NAMAKXIN P&M) |
| `dgfkw05-0dca21c7-cf08-4dee-9a8e-4045dc98c451` | 0.040 | not_border | opaque artist banner (NAMAKX / NAMAKXIN P&M) |
| `brand-by-michalivan-d5rvdrt-pre` | 0.036 | not_border | studio logo (PUPPETWORKS ANIMATION STUDIO) |


## CLEANED AND SHIPPED - the 7 non-DA marks (2026-09-01)

These were never the DA overlay. Each is an opaque or script mark that masked
LaMa removes cleanly, per ADR-005. Mask = a rect over the mark, extent read off
a coordinate grid and verified at 1:1 BEFORE and AFTER; outside-mask MAD is
0.000000 on all seven by construction. Two boxes under-covered on the first
pass (`PUPPETWORKS` lost 'ANIMATION STUDIO', `NAMAKXIN` lost its final N, which
survived as a hooked stroke) and were widened - the same under-cover lesson the
credit-line strips taught.

| slug | mark | mask | mask area |
|---|---|---|---|
| `209-cleanup` | artist signature (CHENBO 12.29.2024) | 123x76 | 0.2536% |
| `mordekaiser-by-michalivan-d5s9q6h-pre` | studio logo (PUPPETWORKS) | 200x112 | 0.6076% |
| `brand-by-michalivan-d5rvdrt-pre` | studio logo (PUPPETWORKS) | 194x110 | 0.5789% |
| `aurora-fanart-by-lulalakill-dlgo81i-pre` | script watermark (@lulalakill 2025) | 800x148 | 3.2118% |
| `p2402-kda-evelynn-by-namakx-dgykw2q-pre` | artist banner (NAMAKXIN P&M2402) | 646x150 | 2.6286% |
| `dgk8f92-bc10d7a7-f520-4b4f-ad86-ac70f6d50293` | artist banner (NAMAKXIN P&M2312) | 636x150 | 2.5879% |
| `dgfkw05-0dca21c7-cf08-4dee-9a8e-4045dc98c451` | artist banner (NAMAKXIN P&M2311) | 678x138 | 2.5381% |

All seven reached `4.Cleaning Done` at exactly 2560x1440.

## Full ranked list

| slug | score | reason |
|---|---|---|
| `mecha-ahri-by-smalltavernx-dia857d-pre` | 0.696 | centre_overlay |
| `123f` | 0.634 | centre_overlay |
| `syndra-league-of-legends-by-smalltavernx-dlsfckr-pre` | 0.620 | centre_overlay |
| `bayonetta-by-stellastria-dm7iiug-pre` | 0.595 | centre_overlay |
| `245f` | 0.586 | centre_overlay |
| `miss-fortune-by-stellastria-dmcdsno-fullview` | 0.585 | centre_overlay |
| `ashe-by-stellastria-dlzcque-fullview` | 0.581 | centre_overlay |
| `124f` | 0.572 | centre_overlay |
| `ahri-by-stellastria-dmbclo0-pre` | 0.565 | centre_overlay |
| `syndra-league-of-legends-by-smalltavernx-dlsfcue-pre` | 0.557 | centre_overlay |
| `bayonetta-by-stellastria-dm7iirw-pre` | 0.448 | centre_overlay |
| `239f` | 0.444 | centre_overlay |
| `244f` | 0.437 | centre_overlay |
| `284f` | 0.436 | centre_overlay |
| `225f` | 0.397 | centre_overlay |
| `285f` | 0.369 | centre_overlay |
| `105-cleanup` | 0.363 | centre_overlay |
| `107-cleanup` | 0.336 | centre_overlay |
| `viego-the-ruined-king-by-slimshadywallpaper-dgemoim-pre` | 0.332 | centre_overlay |
| `109-cleanup` | 0.320 | centre_overlay |
| `bamboo-gal-seraphine-by-mrphantomknight-dm1rp4q-fullview` | 0.288 | centre_overlay |
| `32-cleanup` | 0.273 | centre_overlay |
| `262f` | 0.271 | centre_overlay |
| `287f` | 0.260 | centre_overlay |
| `9-cleanup` | 0.233 | centre_overlay |
| `dawnbringer-soraka-celestial-radiance-by-cherrynest-dml4dmh-full` | 0.210 | centre_overlay |
| `261f` | 0.209 | centre_overlay |
| `266f` | 0.205 | centre_overlay |
| `seraphine-stage-of-brilliance-by-vexxsoul-dm5uzf1-pre` | 0.203 | centre_overlay |
| `273f` | 0.203 | centre_overlay |
| `ahri-league-of-legends-by-khanzaaiart-dmbzcmq-pre` | 0.194 | centre_overlay |
| `fierce-enforcer-of-piltover-by-vexxsoul-dm5crlf-pre` | 0.183 | centre_overlay |
| `221-cleanup` | 0.178 | centre_overlay |
| `riven-broken-blade-unbroken-will-by-vexxsoul-dm9po91-fullview` | 0.177 | centre_overlay |
| `inkshadow-kai-sa-by-pebano1-dm7m9lz-fullview` | 0.176 | centre_overlay |
| `278f` | 0.171 | centre_overlay |
| `122` | 0.170 | centre_overlay |
| `meramora-artwork-by-meramora-dm9c8hi-pre` | 0.159 | centre_overlay |
| `caitlyn-by-pebano1-dm9fw9z-fullview` | 0.158 | centre_overlay |
| `270f` | 0.155 | centre_overlay |
| `dark-cosmic-ahri-by-pebano1-dlnxav6-pre` | 0.151 | centre_overlay |
| `276f` | 0.149 | not_border |
| `286f` | 0.148 | not_border |
| `277f` | 0.144 | not_border |
| `269f` | 0.139 | not_border |
| `evelynn-by-pebano1-dmc9764-pre` | 0.137 | not_border |
| `yunara-by-pebano1-dm7zwfb-fullview` | 0.131 | not_border |
| `seraphine-by-pebano1-dmaj431-pre` | 0.127 | not_border |
| `blood-moon-priestess-mel-by-aiaida-dmhckey-pre` | 0.126 | not_border |
| `258-cleanup` | 0.125 | area_too_large |
| `280f` | 0.121 | not_border |
| `272-cleanup` | 0.117 | not_border |
| `268f` | 0.112 | faint_mark |
| `106-cleanup` | 0.112 | not_border |
| `219-cleanup` | 0.111 | not_border |
| `queen-of-the-saltwind-by-rasrpunk-dmi98yq-fullview` | 0.109 | not_border |
| `110-cleanup` | 0.109 | faint_mark |
| `xayah-by-pebano1-dm44iab-fullview` | 0.108 | not_border |
| `281-cleanup` | 0.108 | not_border |
| `224f` | 0.102 | faint_mark |
| `anime-poster-of-soraka-from-league-of-legends-by-givemenine-dg8j` | 0.092 | not_border |
| `209-cleanup` | 0.090 | not_border |
| `mordekaiser-by-michalivan-d5s9q6h-pre` | 0.067 | not_border |
| `aurora-fanart-by-lulalakill-dlgo81i-pre` | 0.067 | low_conf |
| `p2402-kda-evelynn-by-namakx-dgykw2q-pre` | 0.064 | faint_mark |
| `karthasbasefinal-by-alexflores-d7q5tbt-fullview` | 0.061 | faint_mark |
| `brair-league-of-legends-by-kairahi-dles4n2-pre` | 0.061 | not_border |
| `dragon-slayer-pantheon-by-alexflores-d7fr57n-fullview` | 0.061 | faint_mark |
| `akali-godly-deer-by-ryoairtist-dm2su3h-fullview` | 0.058 | not_border |
| `dgk8f92-bc10d7a7-f520-4b4f-ad86-ac70f6d50293` | 0.056 | not_border |
| `dgfkw05-0dca21c7-cf08-4dee-9a8e-4045dc98c451` | 0.040 | not_border |
| `brand-by-michalivan-d5rvdrt-pre` | 0.036 | not_border |
