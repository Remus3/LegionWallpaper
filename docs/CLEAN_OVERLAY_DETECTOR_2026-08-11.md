# Centre-overlay detector - build + calibration, 2026-08-11

Answers the top item of `docs/CLEAN_DETECTOR_RECALL_2026-08-11.md`: **11 of the
14 measured false negatives are one object**, the semi-transparent DeviantArt
centre overlay (`(C) NAME.DEVIANTART.COM` plus the DA logo, alpha-composited
across the middle of the frame).

## Why not just lower the YOLO floor

The recall census measured three independent failures on this object, so no
single threshold fixes it:

* YOLO scores it **0.11-0.25** against a 0.35 detect floor, and two of the
  misses carry **no box at any confidence** - partly a model limitation.
* EasyOCR returns garble for low-alpha text over busy art, so
  `is_watermark_text` never sees "deviantart".
* Its centroid is mid-frame, so every geometry rule answers `qa` anyway.

And dropping the floor was measured to be the wrong lever: a low-conf box is a
good FLAG (13 of 17 low-conf `clean` images are real misses) but a bad AUTO
signal, and precision on the gated corpus is currently 0 false positives in 14
proposals.

## What it exploits instead

The overlay is the SAME pixels in the SAME place on every image the site serves.
So median-stacking the high-pass of frames that carry it cancels the art and
leaves the mark. Measured: the stack of 11 confirmed positives renders the logo
and the URL **legibly**; the stack of 8 confirmed-clean frames renders nothing.

    template = median over marked frames of (luma - local mean), in the band
    score    = best masked normalized correlation of one frame's high-pass
               against that template, over a tight shift window

`tools/lw_clean_overlay.py`, pure numpy + PIL (FFT correlation), no GPU.

Three decisions, each measured rather than assumed:

| decision | value | why (leave-one-ARTIST-out over the corpus positives) |
|---|---|---|
| clip the high-pass | +-8 levels | the mark is low-amplitude; without the clip one hard art edge dominates. Positive median 0.112 -> **0.220** |
| search shifts | +-3.0% h, +-1.6% w | a firstdone is a crop+downscale of a varying source, so the mark lands tens of px off. Weakest positive -0.02 -> **0.100** |
| keep the window TIGHT | not +-90/+-200px | a wide search buys clean frames a lucky alignment faster than it buys positives: clean max 0.071 -> 0.095 |

## Calibration

Template built from **19 slugs confirmed by eye** to carry the overlay (the 11
from the recall census plus 8 the first calibration pass ranked highly and that
were then verified). All 302 firstdones were scored against it, and the effect
read on the 229 `clean` verdicts - the only place a false negative can live:

| threshold | `clean` images flipped to `qa` | verified real marks | carry no mark |
|---|---|---|---|
| 0.12 | 19 | 16 | **3** |
| **0.15** | **15** | **15** | **0** |
| 0.20 | 14 | 14 | 0 |

`OVERLAY_SCORE_MIN = 0.15` is the largest-recall setting that still costs
nothing. Over the whole corpus it flags 45 of 302, but most of those were
already `auto` or `qa` - the flag's real work is the 15 images that were
silently `clean`.

The 19 template slugs (re-run the build whenever this list grows):

```
245f 105-cleanup 107-cleanup 110-cleanup 124f 123f 230-cleanup 261f
ahri-by-stellastria-dmbclo0-pre bayonetta-by-stellastria-dm7iiug-pre
bayonetta-by-stellastria-dm7iirw-pre ashe-by-stellastria-dlzcque-fullview
miss-fortune-by-stellastria-dmcdsno-fullview mecha-ahri-by-smalltavernx-dia857d-pre
syndra-league-of-legends-by-smalltavernx-dlsfckr-pre
syndra-league-of-legends-by-smalltavernx-dlsfcue-pre
seraphine-stage-of-brilliance-by-vexxsoul-dm5uzf1-pre
the-ruined-king-viego-by-vexxsoul-dm6j4mu-pre
ahri-league-of-legends-by-khanzaaiart-dmbzcmq-pre
```

```
C:\Tools\lw-clean\venv\Scripts\python.exe tools\lw_clean_detector_probe.py --build-overlay-template <slugs...>
```

The template is a derivative of a third party's watermark, so it is written to
`ops/runtime/clean/overlay_template.npz` (**gitignored**) and rebuilt locally -
it is never tracked in this public repo. A missing template means the flag is
simply OFF and the gate reproduces v2 verdicts exactly, which is also why CI
(where no template exists) exercises the wiring with synthetic fixtures.

## Gate v3

`gate_decision` gains one rule and one keyword, `overlay_score=0.0`:

```
1. n > 0, (ocr_hit or watermark_text), area <= 8%  -> auto / watermark_ocr
2. overlay_score >= 0.15                          -> qa   / centre_overlay
3. n == 0                                         -> clean / no_detections
4. lol_logo and not watermark_text                -> clean / lol_logo
5..9  bottom_banner / corner_mark / area_too_large / low_conf / not_border
```

Three deliberate placements:

* **FLAG only.** Rule 2 can only produce `qa`. An unattended edit driven by a
  correlation score would spend the measured 0-false-positive precision, and the
  fill problem for this object (alpha estimation) is not solved yet - see
  `docs/research/WATERMARK_REMOVAL_RND.md`.
* **Above `n == 0` and `lol_logo`.** Two of the misses carry no box at all, and
  two more (seraphine, the-ruined-king-viego) are frames where the wordmark KEEP
  fired while a DA overlay sat mid-frame.
* **Below `watermark_ocr`.** A read watermark is a stronger, already-localised
  signal than a whole-frame correlation.

Reordering `watermark_ocr` above the `lol_logo` rule is a no-op: `ocr_hit`
implies `watermark_text`, and the KEEP rule requires `not watermark_text`, so
the two can never both match.

## Live result - the whole corpus re-gated

The 302-image census was re-run end to end with the template in place, so these
are the gate's actual verdicts, not a projection:

| | v2 | v3 |
|---|---|---|
| `auto` | 27 | 26 |
| `qa` | 46 | 62 |
| `clean` | 229 | **214** |

38 rows changed. The shape of the change:

* **15 `clean` -> `qa/centre_overlay`** - the recall fix, every one verified.
  Two of them are `clean/lol_logo`: seraphine and the-ruined-king-viego, the
  exact frames where the wordmark KEEP fired over a DA overlay.
* **22 `qa` -> `qa/centre_overlay`** - same routing, better reason. These were
  already going to a human as `not_border` / `low_conf` / `area_too_large`; now
  the queue says WHAT was found.
* **1 `auto` -> `qa`** - `239f`, score 0.447. It carries a bottom banner AND a
  centre overlay (verified). Auto would have cleaned the banner and left the
  overlay in an image eligible for approval, so `qa` is the correct answer and
  this is the intended cost of putting rule 2 above the geometry rules.

## REMOVAL (added 2026-08-11)

Detection was half the job. `docs/research/WATERMARK_REMOVAL_RND.md` section 0
says the halo is an ALPHA-ESTIMATION problem: a binary mask either keeps the
1-2px partial-alpha ramp (halo survives) or eats it (a filler must invent it),
and the only artifact-free path is to recover a continuous alpha plus W and
invert `J = (I - aW)/(1 - a)`. That needs a collection carrying the same mark -
which the detector had already assembled.

**Method** (`estimate_matte` / `remove_overlay`, pure numpy + PIL):

1. **Register** every frame to the template (`best_shift`). Pooling an
   unregistered collection is the plateau the R&D plan calls its biggest
   missing piece.
2. **Seed the background** by interpolating DOWN COLUMNS across the mark's own
   region. A median filter was the obvious seed and is the recorded failure of
   R&D method 4 ("alpha underestimated, median bg contaminated by dense text") -
   inside a dense text line every pixel in the window is mark. Columns not rows:
   the mark is ~30px tall and ~1000px wide, so a column fill bridges 30px of
   unknown art instead of a thousand. Measured, the row-wise seed biased alpha
   ~20 percent low.
3. **Shape** the matte as the median over the collection of `(I-J)/(W-J)`.
4. **Fit one global gain** against the detector's own post-removal score.

**Why a per-pixel least-squares fit was abandoned.** It was implemented first -
regress `I-J = aW - aJ` over the collection - and measured on the real corpus:
median R^2 **0.10**. The model explains a tenth of a pixel's cross-frame
variation because the seed error is bigger than the mark, so an R^2 gate either
threw away 93 percent of the mark or let art through, and spatial pooling of the
statistics made it worse (R^2 0.101 -> 0.079 -> 0.071 at windows 1/3/5). The
median-of-ratios is the estimator that survives that noise.

**Why W is constant.** R&D section 3 says estimate W, do not pin it. Estimating
it PER PIXEL was implemented and **diverged**: alpha and W trade off (only their
product is identifiable without a prior), so re-solving W and re-fitting drove
the mean post-removal score **0.149 -> 0.174 -> 0.254** across three rounds while
W drifted from ~154 to ~87. Pinning W and fitting one gain is the stable half of
the model until the matting-Laplacian priors exist.

**Gain calibration** (mean post-removal detector score over the collection):

| gain | 1.0 | 1.5 | **2.0** | 2.5 | 3.0 |
|---|---|---|---|---|---|
| mean score after | 0.258 | 0.133 | **0.120** | 0.141 | 0.166 |

A clear interior optimum - itself evidence that the shape is right and only its
scale was off. The fitted gain is stored in the matte and lands in the slug's
manifest params.

**Measured result over the 19 confirmed frames:**

* detector score **median 0.565 -> 0.112**; **17 of 19** fall under the 0.15
  flag. The two that do not: `107-cleanup` (0.150, borderline) and
  `110-cleanup` (0.109 -> 0.173, the frame whose mark sits 32px off and which
  the detector already scored worst).
* the matte covers 1.4 percent of the band, max alpha 0.363, and pixels outside
  it are copied through byte-for-byte, so AG 1.3 outside-identity holds by
  construction rather than by measurement.
* mean change where edited: 12-19 levels.

**HONEST LIMITATION - the mark is reduced, not erased.** Viewed at 1:1 a faint
ghost of the text remains on every frame tried. The score drop is real and the
reconstruction is faithful (no hallucination, no invented content), but this is
NOT operator-grade output: the operator rejected LaMa and block-SDXL for less
visible damage. So the removal ships as a **QA-lane candidate generator**:

```
python tools\lw_clean_detector_probe.py --build-overlay-matte <confirmed slugs...>
python tools\lw_clean_detector_probe.py --remove-overlay <slug>
```

which writes `<slug>_overlay_cand.png` plus a JSON of before/after scores into
`ops/runtime/clean/<slug>/` and PRINTS the `save-working --tool overlay-dekel` +
`submit` commands. It never mutates pipeline state, and nothing about it routes
to `auto`. Closing the last of the ghost needs the rest of the R&D section 3
programme - Levin matting-Laplacian alpha and IRLS - which is exactly what that
document already predicted would be required.

## Known limitations

* **`110-cleanup` still scores under threshold** (0.121). Its overlay is fainter
  and further off-centre than the window and template cover. One of 19 known
  positives; documented rather than chased with a looser threshold that was
  measured to cost clean images.
* **Detection only.** Flagged images go to the human QA queue; nothing in this
  change removes an overlay.
* **The template is corpus-specific.** A different watermark family (Patreon
  banners, artist signatures - the other 3 of the 14 misses) needs its own
  template or its own detector; signatures in particular get no YOLO box at all.
* The score is **not** alpha-invariant: correlation is normalised by the band's
  own energy, which is mostly art, so a fainter mark on busier art scores lower.
  That is why the threshold is calibrated on the corpus rather than reasoned
  from first principles.

Tests: `tests/test_lw_clean_overlay.py` (16, synthetic fixtures + the gate
wiring invariants, CI-safe with no GPU and no template).
