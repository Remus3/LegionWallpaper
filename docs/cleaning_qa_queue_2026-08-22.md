# Cleaning QA queue - 87 slugs held in `3.Cleaning Scratch`

Written 2026-08-22 by the gate-driven disposition of the 566-slug cleaning
corpus (operator call, ROADMAP `clean-566-disposition`). These slugs carry a
detected mark the automatic lane will NOT touch: an unattended edit driven by
a flag score would spend the detector's zero-false-positive precision, so they
wait for the manual IOPaint lane. Everything else moved: 460 `clean` approved
to `4.Cleaning Done`, 19 of 20 `auto` inpainted (LaMa) and approved.

Masks + detect side-files are in `ops/runtime/clean/<slug>/` (gitignored).
ADR-009 binds: ONE engine per submission, no automatic ladder.

## centre_overlay (45)

semi-transparent DeviantArt centre overlay - the recall root cause; the removal lane is partial (median score 0.565 -> 0.112) but never auto

- `105-cleanup`
- `107-cleanup`
- `109-cleanup`
- `122`
- `123f`
- `124f`
- `221-cleanup`
- `225f`
- `239f`
- `244f`
- `245f`
- `261f`
- `262f`
- `266f`
- `270f`
- `273f`
- `278f`
- `284f`
- `285f`
- `287f`
- `32-cleanup`
- `9-cleanup`
- `aatrox-the-darkin-blade-in-flames-by-vexxsoul-dm6j4xi-pre`
- `ahri-by-stellastria-dmbclo0-pre`
- `ahri-league-of-legends-by-khanzaaiart-dmbzcmq-pre`
- `aidraw-2662100118-by-watercolornessie-dma7o8j-fullview`
- `ashe-by-stellastria-dlzcque-fullview`
- `bamboo-gal-seraphine-by-mrphantomknight-dm1rp4q-fullview`
- `bayonetta-by-stellastria-dm7iirw-pre`
- `bayonetta-by-stellastria-dm7iiug-pre`
- `caitlyn-by-pebano1-dm9fw9z-fullview`
- `dark-cosmic-ahri-by-pebano1-dlnxav6-pre`
- `dawnbringer-soraka-celestial-radiance-by-cherrynest-dml4dmh-full`
- `fierce-enforcer-of-piltover-by-vexxsoul-dm5crlf-pre`
- `inkshadow-kai-sa-by-pebano1-dm7m9lz-fullview`
- `mecha-ahri-by-smalltavernx-dia857d-pre`
- `meramora-artwork-by-meramora-dm9c8hi-pre`
- `miss-fortune-by-stellastria-dmcdsno-fullview`
- `riven-broken-blade-unbroken-will-by-vexxsoul-dm9po91-fullview`
- `seraphine-stage-of-brilliance-by-vexxsoul-dm5uzf1-pre`
- `syndra-league-of-legends-by-smalltavernx-dlsfckr-pre`
- `syndra-league-of-legends-by-smalltavernx-dlsfcue-pre`
- `the-ruined-king-viego-by-vexxsoul-dm6j4mu-pre`
- `viego-the-king-by-slimshadywallpaper-dhawigh-pre`
- `viego-the-ruined-king-by-slimshadywallpaper-dgemoim-pre`

## not_border (27)

boxed mark whose centroid is mid-frame, so the border rule cannot own it

- `106-cleanup`
- `177-cleanup`
- `186-cleanup`
- `193-cleanup`
- `209-cleanup`
- `219-cleanup`
- `269f`
- `272-cleanup`
- `276f`
- `277f`
- `280f`
- `281-cleanup`
- `286f`
- `akali-godly-deer-by-ryoairtist-dm2su3h-fullview`
- `anime-poster-of-soraka-from-league-of-legends-by-givemenine-dg8j`
- `blood-moon-priestess-mel-by-aiaida-dmhckey-pre`
- `brair-league-of-legends-by-kairahi-dles4n2-pre`
- `brand-by-michalivan-d5rvdrt-pre`
- `darius-the-hand-of-noxus-by-vexxsoul-dm8cizj-pre`
- `dgfkw05-0dca21c7-cf08-4dee-9a8e-4045dc98c451`
- `dgk8f92-bc10d7a7-f520-4b4f-ad86-ac70f6d50293`
- `evelynn-by-pebano1-dmc9764-pre`
- `mordekaiser-by-michalivan-d5s9q6h-pre`
- `queen-of-the-saltwind-by-rasrpunk-dmi98yq-fullview`
- `seraphine-by-pebano1-dmaj431-pre`
- `xayah-by-pebano1-dm44iab-fullview`
- `yunara-by-pebano1-dm7zwfb-fullview`

## faint_mark (12)

low-confidence box the faint lane flags but will not auto-edit

- `110-cleanup`
- `128-cleanup`
- `138-cleanup`
- `18-cleanup`
- `224f`
- `268f`
- `75f`
- `dbwtlkx-eeb94ce2-166d-4457-abc3-615a5bc07fd4`
- `dragon-slayer-pantheon-by-alexflores-d7fr57n-fullview`
- `image3`
- `karthasbasefinal-by-alexflores-d7q5tbt-fullview`
- `p2402-kda-evelynn-by-namakx-dgykw2q-pre`

## watermark_ocr (1)

OCR read a watermark string; `259f` is here because its inpaint FAILED the G2 verify gate, not because detection was unsure

- `259f`

## area_too_large (1)

dilated mask covers too much frame to inpaint safely

- `258-cleanup`

## low_conf (1)

single box under the auto floor

- `aurora-fanart-by-lulalakill-dlgo81i-pre`
