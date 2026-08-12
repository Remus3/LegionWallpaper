# Cleaning detector recall census - 2026-08-11

Companion to `docs/CLEAN_DETECTOR_PRECISION_2026-08-11.md`. That census asked
"does the cleaner propose edits it should not?" (answer: no, 0/14). This one asks
the mirror question: **how many marked images does the detector MISS?**

## Why the gated corpus cannot answer this

The 21-slug cleaning queue IS the `auto` output of this same detector's
2026-07-16 triage of 228 firstdones (LEDGER 27). Scoring recall on it is
circular. A false negative can only exist where the gate said `clean` and
nothing was ever routed - i.e. in `2.First Pass Done`. So the population here is
**all 302 `_firstdone` images**, none of which have ever been through cleaning.

## Method

`tools/lw_clean_detector_probe.py --corpus firstdone --low-conf 0.10`

1. Re-runs `detect_image` + `gate_decision` on every one of the 302 firstdones.
2. Additionally sweeps YOLO at conf **0.10** (the production floor is 0.35),
   recorded separately as `yolo_low`. This separates "the detector cannot see
   it" from "the gate threw it away".
3. The 229 `clean` verdicts are split into four strata, then **looked at**:

   | stratum | definition | size | reviewed |
   |---|---|---|---|
   | S1 | `clean/lol_logo` - the wordmark KEEP rule fired | 5 | all 5 |
   | S2 | a low-conf box inside the border band | 3 | all 3 |
   | S3 | a low-conf box outside the band (where a centre overlay hides) | 9 | all 9 |
   | S4 | no box at any conf, no OCR signal | 212 | 14 sampled (seeded) |

   S1-S3 are censused, not sampled: those counts are exact. S4 is a seeded
   random sample, half DeviantArt-sourced slugs and half not.

A false negative = the gate said `clean` while the frame carries an artist
credit URL, handle, signature or credit strip (ADR-005 REMOVE content).

## Result

Gate verdicts over the 302 unrouted firstdones: **27 `auto` / 46 `qa` /
229 `clean`.**

| stratum | reviewed | false negatives | correct KEEP |
|---|---|---|---|
| S1 `lol_logo` | 5 | **4** | 1 (sylas) |
| S2 low-conf in band | 3 | **1** | 1 (kalista) + 1 ambiguous |
| S3 low-conf out of band | 9 | **8** | 1 (astronaut-gnar: in-art hull text) |
| S4 no signal (sample) | 14 of 212 | **1** | 13 |

**14 false negatives confirmed by eye**, 13 of them in the 17 fully-censused
images of S1-S3. Extrapolating S4's 1/14 across its 212 images gives roughly
**15 more**, so the estimate for the whole `clean` set is **~28 of 229 (~12%)**,
with a wide interval (the S4 term alone spans about 3 to 66 images).

Stated as recall: of the images that carry a mark, the gate currently routes
somewhere between roughly half and three quarters of them. The exact figure
depends on how many of the 46 `qa` images carry real marks, which this census
did not label - but a `qa` is flagged, not missed, so it is counted as caught.

The confirmed misses, with what YOLO scored on the missed region:

| slug | what was missed | best box conf | gate verdict |
|---|---|---|---|
| `dragon-slayer-pantheon-by-alexflores-d7fr57n-fullview` | "Alex Flores" painted signature | **no box at all** | clean/lol_logo |
| `karthasbasefinal-by-alexflores-d7q5tbt-fullview` | "Alex Flores" painted signature | 0.114 | clean/lol_logo |
| `seraphine-stage-of-brilliance-by-vexxsoul-dm5uzf1-pre` | (C) VEXXSOUL.DEVIANTART.COM centre overlay | 0.205 | clean/lol_logo |
| `the-ruined-king-viego-by-vexxsoul-dm6j4mu-pre` | (C) VEXXSOUL.DEVIANTART.COM centre overlay | 0.144 | clean/lol_logo |
| `245f` | SMALLTAVERNX.DEVIANTART.COM centre overlay | 0.149 | clean/no_detections |
| `105-cleanup` | SLIMSHADYWALLPAPER.DEVIANTART.COM centre overlay | 0.254 | clean/no_detections |
| `107-cleanup` | SMALLTAVERNWALLPAPER.DEVIANTART.COM centre overlay | 0.254 | clean/no_detections |
| `110-cleanup` | SMALLTAVERNX.DEVIANTART.COM centre overlay | 0.137 | clean/no_detections |
| `124f` | DEVIANTART.COM centre overlay | 0.154 | clean/no_detections |
| `ahri-by-stellastria-dmbclo0-pre` | STELLASTRIA.DEVIANTART.COM centre overlay | 0.149 | clean/no_detections |
| `bayonetta-by-stellastria-dm7iiug-pre` | STELLASTRIA.DEVIANTART.COM centre overlay | 0.117 | clean/no_detections |
| `p2402-kda-evelynn-by-namakx-dgykw2q-pre` | NAMAKXIN P&M2402 wordmark, mid-right | 0.123 | clean/no_detections |
| `syndra-league-of-legends-by-smalltavernx-dlsfckr-pre` | SMALLTAVERNX.DEVIANTART.COM centre overlay | 0.212 | clean/no_detections |
| `syndra-league-of-legends-by-smalltavernx-dlsfcue-pre` | SMALLTAVERNX.DEVIANTART.COM centre overlay | **no box at all** | clean/no_detections |

**CORRECTION 2026-08-11 (same day, `docs/CLEAN_FAINT_MARK_2026-08-11.md`):**
the two "no box at all" rows above are wrong as stated. That was measured at the
`--low-conf 0.10` sweep floor this census used, not at any confidence. Swept to
0.02, `dragon-slayer-pantheon` carries a box on the signature at **0.0522** and
`syndra-...-dlsfcue-pre` is covered by the centre-overlay detector regardless.
So no row in the table below is beyond the reach of a lowered floor - which is
what gate v4 does. The "partly a model limitation" claim under Root cause is
withdrawn; it was a floor limitation.

## Root cause

**11 of the 14 are the same object: the semi-transparent DeviantArt centre
overlay** - the `(C) NAME.DEVIANTART.COM` wordmark plus the DA logo, painted
across the middle of the frame at low alpha. It fails on every axis at once:

* **Below the detect floor.** `detect_yolo` runs at `conf=0.35`; these score
  0.11-0.25. Two carry no box even at 0.10, so this is partly a model
  limitation, not only a threshold.
* **Illegible to OCR.** EasyOCR returns garble or nothing for low-alpha text
  over busy art, so `is_watermark_text` never sees "deviantart".
* **Wrong geometry for the gate.** Its centroid sits mid-frame, so even a
  boxed one lands on `qa/not_border` (rule 8) rather than `auto` - it would be
  flagged for a human, never auto-cleaned.

The other 3 misses are a thin painted **signature** (2, one with no box at any
conf - YOLO simply does not fire on brush-script signatures) and an artist
**wordmark placed away from the bottom band** (1).

**The `lol_logo` whole-image KEEP rule is NOT the binding cause anywhere
measured.** It looks guilty - it fired on all 4 S1 misses - but in each of those
the missed mark also had no box above the 0.35 floor, so removing the rule would
not have caught them. Do not "fix" recall by weakening the wordmark KEEP; that
would only re-open the false positives the precision census showed are currently
zero.

## What would actually move recall

Ranked by measured share of the misses:

1. **A targeted centre-overlay path (11 of 14).** The DA overlay is a
   near-constant template - same font, same logo, low alpha, spanning the middle
   third. That is a template/alpha-matting problem, not a YOLO-confidence
   problem, and `docs/research/WATERMARK_REMOVAL_RND.md` already frames the
   alpha-estimation half of it. Detection first: a mid-frame low-conf box plus a
   template match is a cheap, testable signal.
2. **Do not simply drop the conf floor.** 17 of 229 clean images have a
   low-conf box and 13 of those are real misses, so the signal is informative
   (about 76 percent precision as a FLAG) - but that is a `qa` routing signal,
   not an `auto` one. Routing it to `auto` would spend the 0-false-positive
   result the precision census just measured.
3. **Signatures need their own detector.** YOLO gives brush-script signatures
   either no box or ~0.11. Nothing in the current stack sees them.

## Limits of this census

* S4 (212 images) was sampled at n=14, so its contribution is an estimate with a
  wide interval, not a count. Everything in S1-S3 is a full census.
* The 46 `qa` images were not labelled: this census measures misses, not the
  human queue's contents.
* One S2 case (`viego-the-ruined-king-by-dada-wallpaperart-dmhz060-pre`) was
  called **ambiguous** - a cyan brush scribble bottom-right that may be a
  signature or may be art - and is counted as neither.
* Marks were judged from a full view plus zoomed border strips. A mark smaller
  than that view resolves could still have been missed by the reviewer, which
  biases this count DOWN, never up.

Reproduce:

```
C:\Tools\lw-clean\venv\Scripts\python.exe tools\lw_clean_detector_probe.py --corpus firstdone --low-conf 0.10 --out ops\runtime\clean_recall_census.json
```
