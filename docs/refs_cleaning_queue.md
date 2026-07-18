# reference_pictures - held for cleaning / review

Generated 2026-07-18 by the ref triage sweep (LEDGER 35). These are the
reference_pictures NOT delivered to Pictures: either the production
watermark gate flagged them, or a manual review of their OCR text could
not rule out a site or signature watermark.

Entry point is 0.Originals plus `lw_pipeline intake`, NOT a hand-move into
3.Cleaning Scratch - every file staged there carries a manifest.json and a
hand-move would bypass provenance.

## Gate-flagged (35)

| file | verdict | reason | boxes | area % |
|---|---|---|---|---|
| `0.png` | auto | bottom_banner | 1 | 0.844 |
| `134_cleanup.png` | auto | bottom_banner | 2 | 0.887 |
| `14_cleanup.png` | auto | bottom_banner | 1 | 0.907 |
| `150_cleanup.png` | auto | corner_mark | 3 | 1.258 |
| `170_cleanup.png` | auto | bottom_banner | 2 | 1.244 |
| `180_cleanup.png` | auto | corner_mark | 1 | 0.203 |
| `190_cleanup.png` | auto | bottom_banner | 1 | 0.232 |
| `230_cleanup.png` | auto | watermark_ocr | 2 | 0.892 |
| `239f.png` | auto | bottom_banner | 2 | 1.199 |
| `254f.png` | auto | bottom_banner | 1 | 0.529 |
| `259f.png` | auto | watermark_ocr | 3 | 0.909 |
| `264_cleanup.png` | auto | watermark_ocr | 2 | 0.629 |
| `274f.png` | auto | watermark_ocr | 2 | 1.427 |
| `106_cleanup.png` | qa | not_border | 1 | 1.341 |
| `122.png` | qa | not_border | 2 | 5.944 |
| `123f.png` | qa | low_conf | 1 | 0.67 |
| `177_cleanup.png` | qa | not_border | 2 | 1.024 |
| `186_cleanup.png` | qa | not_border | 2 | 1.562 |
| `193_cleanup.png` | qa | not_border | 1 | 0.198 |
| `209_cleanup.png` | qa | not_border | 1 | 0.24 |
| `219_cleanup.png` | qa | not_border | 1 | 1.365 |
| `221_cleanup.png` | qa | not_border | 1 | 1.205 |
| `225f.png` | qa | not_border | 1 | 0.516 |
| `258_cleanup.png` | qa | area_too_large | 4 | 9.567 |
| `262f.png` | qa | not_border | 2 | 0.843 |
| `266f.png` | qa | low_conf | 1 | 0.596 |
| `269f.png` | qa | not_border | 1 | 1.196 |
| `270f.png` | qa | not_border | 1 | 1.178 |
| `272_cleanup.png` | qa | not_border | 1 | 1.184 |
| `276f.png` | qa | not_border | 1 | 1.086 |
| `277f.png` | qa | not_border | 1 | 1.202 |
| `280f.png` | qa | not_border | 1 | 1.075 |
| `281_cleanup.png` | qa | not_border | 1 | 1.563 |
| `286f.png` | qa | not_border | 2 | 1.115 |
| `32_cleanup.png` | qa | area_too_large | 2 | 9.242 |

## Held on manual review (11)

Gate said clean (no detections) but OCR returned >= 10 alnum chars that
could not be cleared as in-art typography. Held because the cost is
asymmetric: a wrongly-held image waits in a queue, a wrongly-delivered one
puts a watermark on the desktop. CJK glyphs are stripped below (7-bit ASCII
rule); the count is noted instead.

| file | ocr text (ascii-only) | concern |
|---|---|---|
| `105_cleanup.png` | `USHARWAPAPODEUAN` | PAPO/DEUAN fragment |
| `107_cleanup.png` | `SIALLTAVERNWALLPAPEROJARTOOII` | contains WALLPAPER |
| `110_cleanup.png` | `RTIRFBTSTSSW` | unreadable garble |
| `124f.png` | `NUVORUCDEVIIKARTCON2` | reads as DEVIANTART.COM |
| `127_cleanup.png` | `6AINGBI9EX` | unreadable garble |
| `153_cleanup.png` | `UIIITMIIIIIIOIITJIIINCJ` | unreadable garble |
| `196f.png` | `1H2NO [+7 CJK]` | CJK run - signature class |
| `229f.png` | `4E3UI [+8 CJK]` | CJK run - signature class |
| `245f.png` | `SMALTNVERNOEL80` | TAVERN fragment, sibling of 107 |
| `261f.png` | `SLIMSHADAPERDEVIAN` | reads as DEVIAN(TART) |
| `84f.png` | `1241NINI490 [+5 CJK]` | CJK run - signature class |

Delivered and NOT in this list: 226 files, copied to Pictures as
`ref_<name>.png`. `278f.png` was reviewed and DELIVERED - its 62-char OCR
run is in-art splash lore typography, not a watermark.

