# QA-lane precision census - gate v4, live 302-image corpus (2026-08-12)

Closes the last unmeasured part of ROADMAP `cleaning-detector-recall` (open item d).
The recall census counted a `qa` verdict as "caught" without ever asking whether the
flagged frame carries a real mark, so the HUMAN QUEUE's precision was unknown. This
census labels all 67 `qa` rows of `ops/runtime/clean_recall_census_gatev4.json`
(population: every `_firstdone` in `2.First Pass Done`, gate v4).

Method: every claim below is backed by a crop that was actually LOOKED AT - the same
standard the precision and recall censuses were settled by, not a proxy metric.
`tools/lw_clean_qa_crops.py` crops what each row actually flagged (the overlay
template's own support bbox for `centre_overlay`, the YOLO / faint box union for
every other reason), tiles them into labelled contact sheets, and adds an amplified
high-pass tile for `centre_overlay` because that mark is deliberately low-amplitude.
Ambiguous cells were re-cropped at 1:1 or 2x before being called. Sheets live in
`ops/runtime/clean/qa_precision/` (gitignored - they are crops of third-party art).

## Two precisions, because they differ

- **Region precision** - is the thing the gate BOXED (or correlated on) a real mark?
- **Frame precision** - does the frame carry a real mark ANYWHERE, i.e. was routing
  it to the human queue the right call?

They disagree on exactly one row (`258-cleanup`), and that disagreement is the
useful finding: the gate can be right for the wrong reason.

## Result

| reason | n | region TP | region precision | frame TP | frame precision |
|---|---|---|---|---|---|
| centre_overlay | 32 | 32 | **100.0%** | 32 | **100.0%** |
| not_border | 28 | 25 | **89.3%** | 25 | **89.3%** |
| faint_mark | 5 | 4 | **80.0%** | 4 | **80.0%** |
| low_conf | 1 | 1 | 100% (n=1) | 1 | 100% (n=1) |
| area_too_large | 1 | 0 | 0% (n=1) | 1 | 100% (n=1) |
| **all qa** | **67** | **62** | **92.5%** | **63** | **94.0%** |

So the human queue is not full of noise: **63 of 67 frames handed to a human do carry
a mark**, and 62 of 67 flagged regions ARE the mark. Wilson 95% on the frame figure
is roughly 85-98%.

### The 5 region misses, named

| slug | reason | what the box actually contains | frame |
|---|---|---|---|
| `177-cleanup` | not_border | "SK telecom" jersey logo + "FAKER" nameplate - photo content | no mark |
| `186-cleanup` | not_border | "unto DARKNESS" / "unto LIGHT" - the poster's own typography | no mark |
| `193-cleanup` | not_border | a painted snowflake | no mark |
| `dbwtlkx-eeb94ce2-...` | faint_mark | brick-wall texture, conf 0.0765 | no mark |
| `258-cleanup` | area_too_large | the two letterbox bars | **carries `TYSIUUUL.DEVIANTART.COM`** |

`258-cleanup` is the interesting one: the boxes are junk, the routing is correct, and
its `overlay_score` 0.1254 sits just under the 0.15 flag - a near miss that a second
signal caught.

### Confirmed positives worth noting

- `32-cleanup` reads clean at sheet scale; at 2x the `.COM` glyphs of a site
  watermark are unambiguous. Called TP on the zoom, not on the sheet.
- `209-cleanup` is a painted artist signature ("CHENZ" + date), TP under ADR-005.
- `brand-by-michalivan` / `mordekaiser-by-michalivan` box a PUPPETWORKS studio logo
  plus the Riot copyright line - overlay text, not art.
- `darius-the-hand-of-noxus` boxes BOTH the `vexxsoul` credit line and the art's own
  "IN NOXUS, STRENGTH" caption. Scored TP on the credit line; a remover must not
  take the caption with it.
- `aurora-fanart-by-lulalakill` (the single `low_conf` row) is a large script
  `@lulalakill 2025` signature - low confidence, entirely real.

## What this does NOT justify changing

No threshold moves out of this census.

1. **The 4 no-mark frames do not separate on any recorded field.** Their
   `conf_max` (0.72-0.79) sits inside the TP range, `n_boxes` and `area_pct` overlap,
   and `ocr_hit` is False across nearly the whole `qa` population. Any cut that drops
   them drops real marks with them.
2. **`not_border` is doing its job.** Its 3 misses are all art that YOLO reads as
   text-like (a jersey, a caption, a snowflake). That is exactly the case the reason
   exists to hand to a human rather than auto-edit, and at 89.3% it is cheap.
3. **`faint_mark` at 4/5 is the gate v4 flag behaving as designed** (LEDGER 97): it
   buys 4 recall misses for 1 wasted human look.

## Reproduce

```
python tools/lw_clean_qa_crops.py --reason centre_overlay --per-sheet 3
python tools/lw_clean_qa_crops.py --reason not_border --per-sheet 4
python tools/lw_clean_qa_crops.py --reason faint_mark --per-sheet 2
```

Sheets land in `ops/runtime/clean/qa_precision/`. `--slug <slug>` re-cuts one row.
