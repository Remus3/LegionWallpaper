# Hand-clean worklist - DA overlay frames (2026-09-01)

63 frames in `3.Cleaning Scratch` carry the DeviantArt preview overlay, which is
TWO objects: a `(c) ARTIST.DEVIANTART.COM` credit line and a large faint logo
veil, both mid-frame and both crossing the subject. The automated lanes cannot
clear them (see `docs/CLEAN_SCRATCH_CENSUS_2026-09-01.md`).

**These are NOT for deletion.** The plan is to hand-correct them, then study the
before/after pairs to build an automated emulation - the same route that turned
manual IOPaint into `lw_clean_iopaint`.

## Why a hand-cleaned pair is worth so much

Blind matte estimation on these frames sits at SNR ~1 (settled ruling), because
it must separate the mark from the art with neither known. A hand-cleaned
`after` gives the art directly, so the overlay follows in closed form:

```
obs = orig*(1-alpha) + W*alpha        ->        alpha = (obs - orig) / (W - orig)
```

One good pair therefore measures the matte where the mark is, instead of
inferring it. `tools/lw_overlay_from_pair.py` does that extraction.

## Order of work

Ranked by detail in the overlay band (ascending). Low detail = a smooth
background under the mark = both the easiest hand-clean AND the cleanest matte
extraction, since less art texture contaminates the recovered alpha. Work down
from the top; the first few are the ones that teach us the most.

Launch the editor:

```
& "$env:LOCALAPPDATA\Python\pythoncore-3.11-64\python.exe" -m iopaint start --model=lama --device=cuda --port=8080
```

Then open http://127.0.0.1:8080 and load the file for the slug you are on.

Adopt a finished file back into the pipeline (the G2 outside-mask assertion
still runs):

```
python tools/lw_pipeline.py save-working <slug> --adopt --from <hand-fixed.png> --tool iopaint-manual
```

| # | slug | band detail | overlay score | file |
|---|---|---|---|---|
| 1 | `123f` | 2.25 | 0.634 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/123f/123f_cleaninitial.png) |
| 2 | `122` | 2.71 | 0.170 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/122/122_cleaninitial.png) |
| 3 | `219-cleanup` | 3.66 | 0.111 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/219-cleanup/219-cleanup_cleaninitial.png) |
| 4 | `110-cleanup` | 3.67 | 0.109 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/110-cleanup/110-cleanup_cleaninitial.png) |
| 5 | `9-cleanup` | 3.75 | 0.233 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/9-cleanup/9-cleanup_cleaninitial.png) |
| 6 | `269f` | 3.85 | 0.139 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/269f/269f_cleaninitial.png) |
| 7 | `284f` | 4.49 | 0.436 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/284f/284f_cleaninitial.png) |
| 8 | `mecha-ahri-by-smalltavernx-dia857d-pre` | 4.52 | 0.696 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/mecha-ahri-by-smalltavernx-dia857d-pre/mecha-ahri-by-smalltavernx-dia857d-pre_cleaninitial.png) |
| 9 | `245f` | 4.52 | 0.586 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/245f/245f_cleaninitial.png) |
| 10 | `106-cleanup` | 4.65 | 0.112 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/106-cleanup/106-cleanup_cleaninitial.png) |
| 11 | `277f` | 4.88 | 0.144 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/277f/277f_cleaninitial.png) |
| 12 | `239f` | 4.93 | 0.444 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/239f/239f_cleaninitial.png) |
| 13 | `270f` | 4.94 | 0.155 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/270f/270f_cleaninitial.png) |
| 14 | `276f` | 4.95 | 0.149 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/276f/276f_cleaninitial.png) |
| 15 | `262f` | 5.09 | 0.271 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/262f/262f_cleaninitial.png) |
| 16 | `258-cleanup` | 5.28 | 0.125 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/258-cleanup/258-cleanup_cleaninitial.png) |
| 17 | `107-cleanup` | 5.38 | 0.336 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/107-cleanup/107-cleanup_cleaninitial.png) |
| 18 | `ashe-by-stellastria-dlzcque-fullview` | 5.65 | 0.581 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/ashe-by-stellastria-dlzcque-fullview/ashe-by-stellastria-dlzcque-fullview_cleaninitial.png) |
| 19 | `272-cleanup` | 5.67 | 0.117 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/272-cleanup/272-cleanup_cleaninitial.png) |
| 20 | `273f` | 6.2 | 0.203 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/273f/273f_cleaninitial.png) |
| 21 | `124f` | 6.32 | 0.572 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/124f/124f_cleaninitial.png) |
| 22 | `266f` | 6.48 | 0.205 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/266f/266f_cleaninitial.png) |
| 23 | `caitlyn-by-pebano1-dm9fw9z-fullview` | 6.48 | 0.158 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/caitlyn-by-pebano1-dm9fw9z-fullview/caitlyn-by-pebano1-dm9fw9z-fullview_cleaninitial.png) |
| 24 | `miss-fortune-by-stellastria-dmcdsno-fullview` | 6.6 | 0.585 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/miss-fortune-by-stellastria-dmcdsno-fullview/miss-fortune-by-stellastria-dmcdsno-fullview_cleaninitial.png) |
| 25 | `evelynn-by-pebano1-dmc9764-pre` | 6.61 | 0.137 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/evelynn-by-pebano1-dmc9764-pre/evelynn-by-pebano1-dmc9764-pre_cleaninitial.png) |
| 26 | `221-cleanup` | 6.65 | 0.178 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/221-cleanup/221-cleanup_cleaninitial.png) |
| 27 | `brair-league-of-legends-by-kairahi-dles4n2-pre` | 6.74 | 0.061 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/brair-league-of-legends-by-kairahi-dles4n2-pre/brair-league-of-legends-by-kairahi-dles4n2-pre_cleaninitial.png) |
| 28 | `105-cleanup` | 6.78 | 0.363 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/105-cleanup/105-cleanup_cleaninitial.png) |
| 29 | `286f` | 6.95 | 0.148 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/286f/286f_cleaninitial.png) |
| 30 | `244f` | 7.12 | 0.437 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/244f/244f_cleaninitial.png) |
| 31 | `bayonetta-by-stellastria-dm7iiug-pre` | 7.13 | 0.595 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/bayonetta-by-stellastria-dm7iiug-pre/bayonetta-by-stellastria-dm7iiug-pre_cleaninitial.png) |
| 32 | `ahri-by-stellastria-dmbclo0-pre` | 7.38 | 0.565 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/ahri-by-stellastria-dmbclo0-pre/ahri-by-stellastria-dmbclo0-pre_cleaninitial.png) |
| 33 | `viego-the-ruined-king-by-slimshadywallpaper-dgemoim-pre` | 7.38 | 0.332 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/viego-the-ruined-king-by-slimshadywallpaper-dgemoim-pre/viego-the-ruined-king-by-slimshadywallpaper-dgemoim-pre_cleaninitial.png) |
| 34 | `280f` | 7.4 | 0.121 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/280f/280f_cleaninitial.png) |
| 35 | `225f` | 7.45 | 0.397 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/225f/225f_cleaninitial.png) |
| 36 | `261f` | 7.58 | 0.209 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/261f/261f_cleaninitial.png) |
| 37 | `278f` | 7.58 | 0.171 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/278f/278f_cleaninitial.png) |
| 38 | `281-cleanup` | 7.66 | 0.108 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/281-cleanup/281-cleanup_cleaninitial.png) |
| 39 | `dark-cosmic-ahri-by-pebano1-dlnxav6-pre` | 7.72 | 0.151 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/dark-cosmic-ahri-by-pebano1-dlnxav6-pre/dark-cosmic-ahri-by-pebano1-dlnxav6-pre_cleaninitial.png) |
| 40 | `anime-poster-of-soraka-from-league-of-legends-by-givemenine-dg8j` | 7.88 | 0.092 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/anime-poster-of-soraka-from-league-of-legends-by-givemenine-dg8j/anime-poster-of-soraka-from-league-of-legends-by-givemenine-dg8j_cleaninitial.png) |
| 41 | `yunara-by-pebano1-dm7zwfb-fullview` | 7.96 | 0.131 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/yunara-by-pebano1-dm7zwfb-fullview/yunara-by-pebano1-dm7zwfb-fullview_cleaninitial.png) |
| 42 | `queen-of-the-saltwind-by-rasrpunk-dmi98yq-fullview` | 8.0 | 0.109 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/queen-of-the-saltwind-by-rasrpunk-dmi98yq-fullview/queen-of-the-saltwind-by-rasrpunk-dmi98yq-fullview_cleaninitial.png) |
| 43 | `inkshadow-kai-sa-by-pebano1-dm7m9lz-fullview` | 8.04 | 0.176 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/inkshadow-kai-sa-by-pebano1-dm7m9lz-fullview/inkshadow-kai-sa-by-pebano1-dm7m9lz-fullview_cleaninitial.png) |
| 44 | `285f` | 8.54 | 0.369 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/285f/285f_cleaninitial.png) |
| 45 | `32-cleanup` | 8.63 | 0.273 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/32-cleanup/32-cleanup_cleaninitial.png) |
| 46 | `syndra-league-of-legends-by-smalltavernx-dlsfcue-pre` | 8.85 | 0.557 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/syndra-league-of-legends-by-smalltavernx-dlsfcue-pre/syndra-league-of-legends-by-smalltavernx-dlsfcue-pre_cleaninitial.png) |
| 47 | `268f` | 8.86 | 0.112 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/268f/268f_cleaninitial.png) |
| 48 | `dawnbringer-soraka-celestial-radiance-by-cherrynest-dml4dmh-full` | 9.18 | 0.210 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/dawnbringer-soraka-celestial-radiance-by-cherrynest-dml4dmh-full/dawnbringer-soraka-celestial-radiance-by-cherrynest-dml4dmh-full_cleaninitial.png) |
| 49 | `109-cleanup` | 9.25 | 0.320 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/109-cleanup/109-cleanup_cleaninitial.png) |
| 50 | `bamboo-gal-seraphine-by-mrphantomknight-dm1rp4q-fullview` | 9.25 | 0.288 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/bamboo-gal-seraphine-by-mrphantomknight-dm1rp4q-fullview/bamboo-gal-seraphine-by-mrphantomknight-dm1rp4q-fullview_cleaninitial.png) |
| 51 | `seraphine-by-pebano1-dmaj431-pre` | 9.42 | 0.127 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/seraphine-by-pebano1-dmaj431-pre/seraphine-by-pebano1-dmaj431-pre_cleaninitial.png) |
| 52 | `syndra-league-of-legends-by-smalltavernx-dlsfckr-pre` | 10.22 | 0.620 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/syndra-league-of-legends-by-smalltavernx-dlsfckr-pre/syndra-league-of-legends-by-smalltavernx-dlsfckr-pre_cleaninitial.png) |
| 53 | `fierce-enforcer-of-piltover-by-vexxsoul-dm5crlf-pre` | 11.96 | 0.183 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/fierce-enforcer-of-piltover-by-vexxsoul-dm5crlf-pre/fierce-enforcer-of-piltover-by-vexxsoul-dm5crlf-pre_cleaninitial.png) |
| 54 | `xayah-by-pebano1-dm44iab-fullview` | 11.98 | 0.108 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/xayah-by-pebano1-dm44iab-fullview/xayah-by-pebano1-dm44iab-fullview_cleaninitial.png) |
| 55 | `ahri-league-of-legends-by-khanzaaiart-dmbzcmq-pre` | 12.32 | 0.194 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/ahri-league-of-legends-by-khanzaaiart-dmbzcmq-pre/ahri-league-of-legends-by-khanzaaiart-dmbzcmq-pre_cleaninitial.png) |
| 56 | `287f` | 12.48 | 0.260 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/287f/287f_cleaninitial.png) |
| 57 | `seraphine-stage-of-brilliance-by-vexxsoul-dm5uzf1-pre` | 12.64 | 0.203 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/seraphine-stage-of-brilliance-by-vexxsoul-dm5uzf1-pre/seraphine-stage-of-brilliance-by-vexxsoul-dm5uzf1-pre_cleaninitial.png) |
| 58 | `bayonetta-by-stellastria-dm7iirw-pre` | 13.22 | 0.448 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/bayonetta-by-stellastria-dm7iirw-pre/bayonetta-by-stellastria-dm7iirw-pre_cleaninitial.png) |
| 59 | `akali-godly-deer-by-ryoairtist-dm2su3h-fullview` | 13.35 | 0.058 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/akali-godly-deer-by-ryoairtist-dm2su3h-fullview/akali-godly-deer-by-ryoairtist-dm2su3h-fullview_cleaninitial.png) |
| 60 | `224f` | 15.96 | 0.102 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/224f/224f_cleaninitial.png) |
| 61 | `blood-moon-priestess-mel-by-aiaida-dmhckey-pre` | 16.28 | 0.126 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/blood-moon-priestess-mel-by-aiaida-dmhckey-pre/blood-moon-priestess-mel-by-aiaida-dmhckey-pre_cleaninitial.png) |
| 62 | `meramora-artwork-by-meramora-dm9c8hi-pre` | 17.65 | 0.159 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/meramora-artwork-by-meramora-dm9c8hi-pre/meramora-artwork-by-meramora-dm9c8hi-pre_cleaninitial.png) |
| 63 | `riven-broken-blade-unbroken-will-by-vexxsoul-dm9po91-fullview` | 17.81 | 0.177 | [open](file:///C:/LegionWallpaper/images/3.Cleaning%20Scratch/riven-broken-blade-unbroken-will-by-vexxsoul-dm9po91-fullview/riven-broken-blade-unbroken-will-by-vexxsoul-dm9po91-fullview_cleaninitial.png) |
