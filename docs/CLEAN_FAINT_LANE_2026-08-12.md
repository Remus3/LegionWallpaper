# Faint-mark REMOVAL lane - 2026-08-12

The removal half of `docs/CLEAN_FAINT_MARK_2026-08-11.md`. Gate v4 flags five
images to `qa/faint_mark`; this is what happens to them next.

## The first finding: the family is not one object

The centre-overlay work could build one recipe because all 32 frames carried the
same mark. These five do not, and measuring that first is what kept the lane
from being one threshold fitted to a mixture:

| slug | mark | disposition |
|---|---|---|
| `karthasbasefinal-by-alexflores-d7q5tbt-fullview` | "Alex Flores" brush signature | **cleaned** |
| `dragon-slayer-pantheon-by-alexflores-d7fr57n-fullview` | the same signature | **cleaned** |
| `p2402-kda-evelynn-by-namakx-dgykw2q-pre` | stylised wordmark ON busy art | **manual** (refused) |
| `110-cleanup` | low-alpha DA centre overlay | **defer** to `--overlay` |
| `dbwtlkx-eeb94ce2-...` | none (the known false flag) | cleaned, 0.8% mask - a near no-op |

So the lane does one job well, and refuses two others by name rather than
producing a candidate that looks finished and is not.

## The lane

`lw_clean_iopaint.py --faint`. It reuses the existing masked-LaMa path whole -
same `build_watermark_mask`, same paste-back, same outside-ROI tripwire, same
save-working/submit printout, never auto-applies. Three things are new.

**The ROI is derived, not declared.** Every other region in that file is a
hand-measured preset. Here the detector's own sub-floor boxes ARE the
localisation - throwing them away is the bug gate v4 fixed - so the region is
their union, extended by any OCR box that *overlaps* one. That extension is load
bearing: `p2402`'s YOLO box stops at x=2348 while OCR reads the wordmark out to
x=2482, and inpainting a partial mark leaves the rest legible. Overlap is
required rather than proximity, because both alexflores frames carry the LEAGUE
OF LEGENDS wordmark in the opposite corner and that logo is a KEEP.

**The bright threshold is raised, `BRIGHT_THR` 10 -> `FAINT_BRIGHT_THR` 42.**
The default was calibrated for an opaque bottom-centre credit strip. A brush
signature sits ON painted art, and painted art reads well above +10 from its own
local median, so at the default the mask swallows the picture. Mask coverage of
the ROI by threshold:

| slug | 10 | 22 | 34 | 42 |
|---|---|---|---|---|
| `karthasbasefinal` | 32.6% | 18.5% | 15.7% | **14.3%** |
| `dragon-slayer-pantheon` | 28.1% | 22.3% | 22.1% | **22.0%** |

Read as pictures, not numbers: at 34 one cloud streak still survives on
`karthasbasefinal` and at 42 none does, while the signature stays fully covered
on both. 42 is the smallest swept step leaving no art component.

**Two refusals and an outcome check.**

* `FAINT_COVERAGE_MAX = 25.0` - a mark is a small part of its own ROI. At 42,
  `p2402` masks 30-33% of its ROI because the wordmark sits on busy crystal art
  that no threshold separates from it. The lane refuses BEFORE the GPU, leaves
  the mask on disk as the evidence, and prints the manual IOPaint launch line.
  Calibrated on n=3, so it is a tripwire and not a classifier - but it errs
  toward refusing, and a refusal routes to a human.
* `FAINT_OVERLAY_DEFER = 0.10` - a faint box says something is here, not WHICH
  object. This line is a measurement rather than a fit: over the 209 `clean`
  firstdones the centre-overlay score runs p50 0.0596 / p90 0.0770 / p99 0.1042
  / max 0.1213, so 0.10 means "out of the clean distribution". The four
  non-overlay flags score 0.048-0.064; `110-cleanup` scores 0.109. It only ever
  ROUTES between two lanes - it cannot edit a pixel or move a gate verdict.
* After the pass the lane RE-DETECTS on the candidate and reports any qualifying
  faint box still inside the ROI as `status: residual`. Coverage is a proxy; the
  detector is the measurement, and it is the same one that flagged the slug.

## Verified

Live run over all five, `--faint`, candidates in
`ops/runtime/clean/faint_lane/<slug>/`:

```
karthasbasefinal        CLEANED   coverage 14.1%   changed 4570 px   outside ROI 0
dragon-slayer-pantheon  CLEANED   coverage 22.1%   changed 6774 px   outside ROI 0
dbwtlkx-eeb94ce2        CLEANED   coverage  0.8%   changed  936 px   outside ROI 0
p2402-kda-evelynn       MANUAL    coverage 33.4%   (ceiling 25%)
110-cleanup             DEFER     overlay score 0.1090 (defer at 0.10)
```

The outside-ROI counts were re-measured from the files on disk, not taken from
the in-process tripwire. Both signatures were cropped and looked at before and
after: the signature is gone on both, the background reads continuously across
where it was, and the only visible cost is a soft patch on
`dragon-slayer-pantheon` where a bright art fleck fell inside the mask.

The false flag `dbwtlkx` is the useful negative control: with no mark present the
lane finds 936 pixels to touch out of 3.7M, so a false flag reaching this lane
costs a near no-op rather than a repainted frame.

## Dead ends, measured - do not redo

* **The dark-outline adjacency gate for `p2402`.** The wordmark is white fill
  with a dark outline and the art beside it is bright cyan, so "bright AND
  within N px of a dark-diff pixel" looks like the separator. It is not: the
  art's own crevices satisfy it at every reach tried (r4/r7/r11 -> 30.9% /
  32.8% / 34.4% coverage, the art blob intact in all three).
* **The faint lane on the DA overlay (`110-cleanup`).** Structurally wrong, not
  merely untuned: the overlay is LOW alpha, so its glyphs differ from the local
  median by far less than 42. The credit line stays legible at 19.0% coverage,
  the chroma term adds almost nothing (19.9%), and the frame's overlay score
  goes UP, 0.1090 -> 0.1203. This is what `FAINT_OVERLAY_DEFER` exists to stop.
* **A bigger pad on the overlay lane for `110-cleanup`.** The derived ROI does
  under-cover its credit line (x 852-1518 against a mark spanning 627-1538), and
  widening it to `--pad 260` does fix the clipping - but the line is still
  legible afterwards and the score barely moves (0.109 -> 0.1031). The binding
  constraint there is REGISTRATION, not the ROI: this frame correlates with the
  template at 0.109 against the flagged family's 0.310 median, so the matte
  lands imperfectly. That belongs to the overlay item, not to this lane.

## Still open

`p2402` and `110-cleanup` are queued for the manual IOPaint lane and nothing
automates them. `110-cleanup`'s real fix is the overlay lane's registration on
weakly-correlating frames.

Reproduce:

```
C:\Tools\lw-clean\venv\Scripts\python.exe tools\lw_clean_iopaint.py <slug> --image "images\2.First Pass Done\<slug>\<slug>_firstdone.png" --faint --out-dir ops\runtime\clean\faint_lane\<slug>
```
