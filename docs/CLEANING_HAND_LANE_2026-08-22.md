# Hand IOPaint work order - the 80 slugs no automated lane could clean

Every automated candidate produced for the QA queue was reviewed by the
operator on 2026-08-22 and REJECTED: 45 centre_overlay (filled and un-filled),
then 27 region + 3 singleton + 10 faint, then the 7 that survived the shared
coverage guard. Zero accepted. Seven further slugs turned out to be detector
false positives carrying no mark at all and were approved unedited, which is
why 80 remain rather than 87.

This is the hand lane. Start the UI once:

```
& "$env:LOCALAPPDATA\Python\pythoncore-3.11-64\python.exe" -m iopaint start --model=lama --device=cuda --port=8080
```

then open http://127.0.0.1:8080 and work a slug at a time. Re-entry per slug,
once the edited PNG is saved somewhere outside the pipeline folders:

```
python tools/lw_pipeline.py save-working <slug> --from <edited.png> --tool iopaint
python tools/lw_pipeline.py submit <slug>
python tools/lw_pipeline.py approve <slug>
```

ADR-009 binds: ONE engine per submission. The `_iopaint_mask.png` column is the
mask the automated lane derived - useful as a STARTING point in the UI, and a
warning where its coverage is high, since a high-coverage mask is what produced
the rejected over-repaint. A blank cell means no mask was ever written.

| slug | last automated status | mask coverage | derived mask |
|---|---|---|---|
| `105-cleanup` | cleaned (overlay path) | 12.489% | yes |
| `106-cleanup` | cleaned | 35.135% | yes |
| `107-cleanup` | cleaned (overlay path) | 10.915% | yes |
| `109-cleanup` | cleaned (overlay path) | 17.647% | yes |
| `110-cleanup` | cleaned (overlay path) | 10.513% | yes |
| `122` | cleaned (overlay path) | 8.688% | yes |
| `123f` | cleaned (overlay path) | 10.787% | yes |
| `124f` | cleaned (overlay path) | 13.348% | yes |
| `128-cleanup` | residual | 2.597% | yes |
| `138-cleanup` | never ran | - | yes |
| `18-cleanup` | cleaned | 10.522% | yes |
| `209-cleanup` | cleaned | 47.646% | yes |
| `219-cleanup` | cleaned | 32.381% | yes |
| `221-cleanup` | cleaned (overlay path) | 17.568% | yes |
| `224f` | cleaned (overlay path) | 16.774% | yes |
| `225f` | cleaned (overlay path) | 13.96% | yes |
| `239f` | cleaned (overlay path) | 16.682% | yes |
| `244f` | cleaned (overlay path) | 15.741% | yes |
| `245f` | cleaned (overlay path) | 11.285% | yes |
| `258-cleanup` | cleaned | 20.923% | yes |
| `259f` | cleaned | 30.93% | yes |
| `261f` | cleaned (overlay path) | 17.693% | yes |
| `262f` | cleaned (overlay path) | 14.107% | yes |
| `266f` | cleaned (overlay path) | 10.977% | yes |
| `268f` | cleaned (overlay path) | 18.42% | yes |
| `269f` | cleaned | 39.738% | yes |
| `270f` | cleaned (overlay path) | 14.803% | yes |
| `272-cleanup` | cleaned | 45.212% | yes |
| `273f` | cleaned (overlay path) | 13.201% | yes |
| `276f` | cleaned | 49.051% | yes |
| `277f` | cleaned | 50.28% | yes |
| `278f` | cleaned (overlay path) | 13.057% | yes |
| `280f` | cleaned | 51.915% | yes |
| `281-cleanup` | cleaned | 51.018% | yes |
| `284f` | cleaned (overlay path) | 14.243% | yes |
| `285f` | cleaned (overlay path) | 16.698% | yes |
| `286f` | cleaned | 54.165% | yes |
| `287f` | cleaned (overlay path) | 14.706% | yes |
| `32-cleanup` | cleaned (overlay path) | 10.962% | yes |
| `9-cleanup` | cleaned (overlay path) | 12.83% | yes |
| `aatrox-the-darkin-blade-in-flames-by-vexxsoul-dm6j4xi-pre` | cleaned (overlay path) | 20.311% | yes |
| `ahri-by-stellastria-dmbclo0-pre` | cleaned (overlay path) | 11.04% | yes |
| `ahri-league-of-legends-by-khanzaaiart-dmbzcmq-pre` | cleaned (overlay path) | 19.607% | yes |
| `aidraw-2662100118-by-watercolornessie-dma7o8j-fullview` | cleaned (overlay path) | 13.635% | yes |
| `akali-godly-deer-by-ryoairtist-dm2su3h-fullview` | cleaned | 50.065% | yes |
| `anime-poster-of-soraka-from-league-of-legends-by-givemenine-dg8j` | cleaned | 55.315% | yes |
| `ashe-by-stellastria-dlzcque-fullview` | cleaned (overlay path) | 14.044% | yes |
| `aurora-fanart-by-lulalakill-dlgo81i-pre` | cleaned | 45.866% | yes |
| `bamboo-gal-seraphine-by-mrphantomknight-dm1rp4q-fullview` | cleaned (overlay path) | 15.634% | yes |
| `bayonetta-by-stellastria-dm7iirw-pre` | cleaned (overlay path) | 18.411% | yes |
| `bayonetta-by-stellastria-dm7iiug-pre` | cleaned (overlay path) | 9.619% | yes |
| `blood-moon-priestess-mel-by-aiaida-dmhckey-pre` | cleaned | 53.837% | yes |
| `brair-league-of-legends-by-kairahi-dles4n2-pre` | cleaned | 43.676% | yes |
| `brand-by-michalivan-d5rvdrt-pre` | cleaned | 16.833% | yes |
| `caitlyn-by-pebano1-dm9fw9z-fullview` | cleaned (overlay path) | 15.103% | yes |
| `dark-cosmic-ahri-by-pebano1-dlnxav6-pre` | cleaned (overlay path) | 15.135% | yes |
| `dawnbringer-soraka-celestial-radiance-by-cherrynest-dml4dmh-full` | cleaned (overlay path) | 14.795% | yes |
| `dgfkw05-0dca21c7-cf08-4dee-9a8e-4045dc98c451` | cleaned | 27.585% | yes |
| `dgk8f92-bc10d7a7-f520-4b4f-ad86-ac70f6d50293` | cleaned | 24.483% | yes |
| `dragon-slayer-pantheon-by-alexflores-d7fr57n-fullview` | cleaned | 22.135% | yes |
| `evelynn-by-pebano1-dmc9764-pre` | cleaned | 48.308% | yes |
| `fierce-enforcer-of-piltover-by-vexxsoul-dm5crlf-pre` | cleaned (overlay path) | 17.721% | yes |
| `inkshadow-kai-sa-by-pebano1-dm7m9lz-fullview` | cleaned (overlay path) | 14.862% | yes |
| `karthasbasefinal-by-alexflores-d7q5tbt-fullview` | cleaned | 14.135% | yes |
| `mecha-ahri-by-smalltavernx-dia857d-pre` | cleaned (overlay path) | 14.421% | yes |
| `meramora-artwork-by-meramora-dm9c8hi-pre` | cleaned (overlay path) | 15.544% | yes |
| `miss-fortune-by-stellastria-dmcdsno-fullview` | cleaned (overlay path) | 10.214% | yes |
| `mordekaiser-by-michalivan-d5s9q6h-pre` | cleaned | 22.684% | yes |
| `p2402-kda-evelynn-by-namakx-dgykw2q-pre` | never ran | - | yes |
| `queen-of-the-saltwind-by-rasrpunk-dmi98yq-fullview` | cleaned | 52.813% | yes |
| `riven-broken-blade-unbroken-will-by-vexxsoul-dm9po91-fullview` | cleaned (overlay path) | 18.808% | yes |
| `seraphine-by-pebano1-dmaj431-pre` | cleaned | 69.684% | yes |
| `seraphine-stage-of-brilliance-by-vexxsoul-dm5uzf1-pre` | cleaned (overlay path) | 17.147% | yes |
| `syndra-league-of-legends-by-smalltavernx-dlsfckr-pre` | cleaned (overlay path) | 16.154% | yes |
| `syndra-league-of-legends-by-smalltavernx-dlsfcue-pre` | cleaned (overlay path) | 16.731% | yes |
| `the-ruined-king-viego-by-vexxsoul-dm6j4mu-pre` | cleaned (overlay path) | 18.703% | yes |
| `viego-the-king-by-slimshadywallpaper-dhawigh-pre` | cleaned (overlay path) | 11.151% | yes |
| `viego-the-ruined-king-by-slimshadywallpaper-dgemoim-pre` | cleaned (overlay path) | 12.45% | yes |
| `xayah-by-pebano1-dm44iab-fullview` | cleaned | 57.024% | yes |
| `yunara-by-pebano1-dm7zwfb-fullview` | cleaned | 50.158% | yes |

Total: 80 slugs in `3.Cleaning Scratch`.
