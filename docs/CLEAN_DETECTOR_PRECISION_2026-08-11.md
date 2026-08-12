# Cleaning detector precision census - 2026-08-11

ROADMAP item `clean-retry-degrades`, half 2 (`cleaning-detector-precision`).
Half 1 measured the retry ladder and is shipped (`2958338`, LEDGER 90). This is
the other half of the same operator review: **does the cleaner propose edits on
content that needed none?**

## Question, and what counts as an answer

The claim under test came from the 2026-08-02 cleaning-queue review: "the cleaner
FINDS work on images that need none", citing `vayne3` (team logos are design) and
`p08e8` (bottom band). A false positive is a slug where the gate returns `auto` -
i.e. it would inpaint unattended - on a region that should be KEPT. A `qa`
verdict is **not** a false positive: routing an ambiguous region to a human is
the gate working as designed.

ADR-005 sets the KEEP/REMOVE line: an artist signature, handle or credit URL is
REMOVED; the LEAGUE OF LEGENDS wordmark and in-art design are KEPT.

## Method

`tools/lw_clean_detector_probe.py` (read-only, never writes a stage folder):

1. **LABEL census** (stdlib) - reads every cleaning-stage manifest and derives an
   operator label from `REJECT` notes plus the `APPROVE_CLEAN` sha256.
2. **DETECT census** (cleaning venv) - re-runs `detect_image` and the *same*
   `gate_decision` the pipeline uses, on each slug's `_cleaninitial`. The initial
   is deliberate: it is the image the detector actually faced, before any inpaint
   moved pixels.
3. Every `auto` region was then **looked at** - cropped from the initial at the
   detected box and inspected - and classified REMOVE/KEEP against ADR-005.

Corpus: all 21 slugs in `3.Cleaning Scratch` + `4.Cleaning Done`. That is the
whole gated corpus; nothing was sampled or dropped.

## Result

**14 `auto` proposals. 14 are genuine artist marks. ZERO false positives.**

| verdict | slugs | of which wrongly proposed |
|---|---|---|
| `auto` (unattended edit) | 14 | **0** |
| `qa` (human decides) | 4 | n/a - not a proposal |
| `clean` (nothing to do) | 3 | n/a |

The two cited cases are **stale**, and both for reasons already recorded in code:

* `vayne3` now detects **nothing** (n=0 boxes). Its only OCR is a lone `@` glyph
  read out of the art, and the bare-`@` narrowing (`_HANDLE_RE`, pinned by
  `test_bare_at_glyph_is_not_watermark`) already removed that path. The team
  logos never produced a YOLO box in this census.
* `p08e8`'s fire is the real `@namakxin` signature, bottom-left. The operator's
  own approved `_cleandone` differs from `_cleaninitial` by 65122 pixels in that
  region: the removal was **approved**, so the detector was right. The
  2026-08-02 `REJECT` note ("no watermark or defect present") landed on the third
  working, not on the detector's box - which is why a reject note is a weak label
  and the approved sha256 is the strong one.

The same correction applies to `nguyen-ky-phuc-reyjin-leblanc-j-f1`: same reject
note, and its approved `_cleandone` removes a painted "Reyjin" signature (9719
changed pixels). Of the 3 slugs the operator has adjudicated, exactly **one**
(`vayne3`) settled on the uncleaned pixels, and on that one the detector proposes
nothing.

## Per-slug census

| slug | verdict | reason | n | conf_max | area % | centroid (rel) | what the region actually is |
|---|---|---|---|---|---|---|---|
| `aatrox-the-darkin-blade-in-flames-by-vexxsoul-` | auto | watermark_ocr | 1 | 0.85 | 1.64 | 0.48, 0.69 | (C) VEXXSOUL.DEVIANTART.COM banner - REMOVE |
| `aidraw-2662100118-by-watercolornessie-dma7o8j-` | auto | watermark_ocr | 1 | 0.53 | 0.84 | 0.48, 0.69 | (C) WATERCOLORNESSIE.DEVIANTART.COM banner - REMOVE |
| `caitlyn-love-confession-lol-skin-splash-art-4k` | clean | no_detections | 0 | 0.00 | 0.00 | - | no mark anywhere in frame - KEEP |
| `dfz5w2g-8ba7345b-5776-4d83-b939-4ca7d045f545` | auto | watermark_ocr | 2 | 0.69 | 4.59 | 0.50, 0.89 | @namakxin + PATREON.COM/NAMAKXIN - REMOVE |
| `dfzlox4-7e2bdc64-36ce-41fa-80b0-c83f97fdf5f5` | auto | watermark_ocr | 1 | 0.00 | 6.36 | 0.50, 0.89 | @namakxin + PATREON.COM/NAMAKXIN - REMOVE |
| `dfzypoo-482973ff-dfb0-44e4-a90c-386714d27faf` | auto | watermark_ocr | 2 | 0.00 | 4.00 | 0.50, 0.91 | @namakxin + PATREON.COM/NAMAKXIN - REMOVE |
| `dfzypou-30bef263-c754-4a26-9797-484757b1c4cf` | auto | watermark_ocr | 2 | 0.54 | 4.39 | 0.50, 0.91 | @namakxin + PATREON.COM/NAMAKXIN - REMOVE |
| `dfzypp1-251c5c37-e25f-496e-a9a6-4900304e6fa5` | auto | watermark_ocr | 2 | 0.00 | 4.28 | 0.50, 0.91 | @namakxin + PATREON.COM/NAMAKXIN - REMOVE |
| `dgk8f8n-398197d0-65d6-4299-8f0b-afdd9021c395` | auto | bottom_banner | 1 | 0.91 | 2.28 | 0.13, 0.94 | NAMAKXIN P&M2312 wordmark - REMOVE |
| `fantasy-design-by-aivio-dkdq5p7-pre` | qa | not_border | 1 | 0.79 | 1.61 | 0.52, 0.73 | routed to a human (qa) - not a proposal |
| `fury-tempest-sona-by-ryoairtist-dm7ziam-pre` | qa | not_border | 1 | 0.87 | 1.72 | 0.50, 0.73 | routed to a human (qa) - not a proposal |
| `image3` | auto | bottom_banner | 1 | 0.80 | 0.82 | 0.14, 0.99 | bottom-edge fan-art credit strip - REMOVE |
| `kayle-new-splash-by-su-ke-d85w02l-fullview` | auto | bottom_banner | 1 | 0.69 | 0.55 | 0.07, 0.98 | cyan stylised artist signature, bottom-left - REMOVE |
| `prestige-coven-xayah-by-pebano1-dmc27t0-pre` | qa | not_border | 1 | 0.85 | 1.42 | 0.48, 0.69 | routed to a human (qa) - not a proposal |
| `spirit-blossom-ahri-mono-01-by-hriful-dk79ceq-` | auto | bottom_banner | 1 | 0.63 | 0.81 | 0.08, 0.98 | deviantart.com/hriful strip - REMOVE |
| `syndra-coven-league-of-legends-by-kintanki1-dm` | auto | watermark_ocr | 1 | 0.68 | 1.34 | 0.50, 0.69 | (C) KINTANKI.DEVIANTART.COM banner - REMOVE |
| `the-ruined-king-viego-by-vexxsoul-dm6j4mu-pre` | clean | lol_logo | 1 | 0.76 | 0.45 | 0.13, 0.93 | LEAGUE OF LEGENDS wordmark - KEEP correct, but see the CORRECTION below |
| `viego-the-king-by-slimshadywallpaper-dhawigh-p` | qa | low_conf | 1 | 0.39 | 0.92 | 0.52, 0.69 | routed to a human (qa) - not a proposal |
| `nguyen-ky-phuc-reyjin-leblanc-j-f1` | auto | bottom_banner | 1 | 0.92 | 0.39 | 0.97, 0.96 | 'Reyjin' painted signature, bottom-right - REMOVE |
| `p08e8-shadow-hunter-vayne-by-namakx-dg9ydp9-pr` | auto | watermark_ocr | 1 | 0.91 | 2.27 | 0.10, 0.94 | '@namakxin' signature - REMOVE (operator approved its removal) |
| `vayne3` | clean | no_detections | 0 | 0.00 | 0.00 | - | no detection at all (n=0) - KEEP |

## CORRECTION (added 2026-08-11 by the recall census)

`the-ruined-king-viego-by-vexxsoul-dm6j4mu-pre` was annotated above as a fully
correct KEEP. The wordmark KEEP is correct, but the recall census then viewed
the FULL frame and found a semi-transparent `(C) VEXXSOUL.DEVIANTART.COM` centre
overlay this gate does NOT catch (best YOLO box 0.144, under the 0.35 detect
floor). So that row is a correct KEEP **and** a false NEGATIVE at the same time.
The precision result is unaffected - it counts unattended `auto` proposals, and
this slug proposes nothing - but the annotation is corrected here rather than
left to read as "nothing to find". See
`docs/CLEAN_DETECTOR_RECALL_2026-08-11.md`.

The general lesson: this census looked at the DETECTED BOX for each `auto`, and
at the full frame only where a verdict was `clean`. Judging a box tells you
whether a proposal is right; it does not tell you what else is in the picture.

## Ruling

**No rule is narrowed.** The acceptance criterion allowed either a narrowed rule
with a test, or "evidence the detector is already precise and the item closes
with that number". The number is 0 false positives in 14 unattended proposals
over the whole gated corpus, so narrowing now would only cost recall - and
CLAUDE.md says to widen or narrow **only on test evidence**.

What ships instead is the regression net:
`tests/test_lw_clean_detector_precision.py` pins all 21 measured rows (real OCR
strings, real geometry) to the verdict they produced, plus a KEEP-set test
asserting no measured KEEP slug may ever become `auto`. Any future rule change
that flips a corpus case fails CI with the slug named.

## What this does NOT close

* **Recall was not measured.** This census answers precision only. `caitlyn` is
  the one slug where a wallpaper-host name in the slug (`uhdpaper`) suggested a
  mark; the frame was inspected and carries none, so `clean` is correct there.
  A false-negative census would need a different labelled set.
* **The `qa` lane is unchanged** - 4 slugs still wait on a human, which is the
  designed behaviour, not a defect.
* **The cross-engine ladder** (lama -> sdxl -> iopaint) is still fired by the
  operator/skill on REJECT, not by a code default. That is the remaining open
  half of `clean-retry-degrades`.

Reproduce:

```
C:\Tools\lw-clean\venv\Scripts\python.exe tools\lw_clean_detector_probe.py --out ops\runtime\clean_detector_census.json
```

`--labels-only` runs the stdlib half with no GPU.
