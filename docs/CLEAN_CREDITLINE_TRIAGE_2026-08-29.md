# Credit-line queue - flag-only vision triage of all 39 sheets (2026-08-29)

The queue's 39 sheets under the shipping default (`--scoped-revert` ON, `--stubs`
off) had never been looked at. This pass looked at every one of them and produced
a RANKED SHORTLIST so the operator's eye lands on the suspect sheets first.

**Authority limit, per ADR-008: this is a FLAG, never a verdict.** Nothing here
approves or rejects any slug, nothing moved in the pipeline, and no file under
`images\` was touched. A vision 2AFC is not reproducible and splash art has no
anatomical ground truth; the operator's eye on the 1:1 crop remains the gate.

The ranked artifact lives with the sheets it indexes, at
`ops/runtime/clean/creditline/run_scoped/TRIAGE.md` (gitignored runtime, like the
sheets). This file records the finding, which is tracked.

## How it was run

Five read-only agents, 8 sheets apiece, each given the same rubric: locate the
mark in the untouched panel, check those same positions in the cleaned panel,
then scan the whole cleaned panel for collateral damage to the artwork. Each
returned per-slug `residue` (NONE / TRACE / GHOST / LEGIBLE), `damage` (NONE /
MINOR / OBVIOUS), a confidence, and one line of what was actually seen and where.
Verdicts were merged against the measured facts already in `run_summary.json`
(mask px, blobs, held, partial, `still_reads`, status).

## The result

| measure | count of 39 |
|---|---|
| residue LEGIBLE | 28 |
| residue GHOST | 7 |
| residue NONE | 4 |
| damage OBVIOUS | 17 |
| damage MINOR | 16 |
| flagged (residue not NONE, or damage OBVIOUS) | 37 |
| **no flag raised** | **2** |

The two unflagged: `ashe-by-stellastria-dlzcque-fullview` and
`bayonetta-by-stellastria-dm7iiug-pre`.

**The reader and the eye disagree by an order of magnitude.** The run's OCR
reader finds a surviving line on 2 slugs; this pass reads one on 28. **26 slugs
the reader called silent still read as text at 1:1.** 21 slugs carrying
`status: clean` in `run_summary.json` are flagged here.

**This direction was already known - the magnitude is what is new.** ROADMAP
already recorded that reader-quiet overstates removal by about one step (259f
reads quiet at p70 with the line plainly legible; viego at p80 with a ghost
standing), and `REVIEW.md` already said a read proves failure while silence
proves nothing. What this pass adds is that the effect is not a one-step bias on
a few slugs, it is most of the queue.

**A second failure mode the reader never watched at all:** 17 slugs carry OBVIOUS
collateral damage to the artwork - a painted line cut where the mask crossed it,
a flattened blocky patch, a deformed silhouette. A credit-line reader is blind to
this by construction. It is independent of residue: `105-cleanup` and `123f` come
back residue NONE with damage OBVIOUS.

## Defect patterns worth naming

- **The `(c)` ring glyph survives.** The single most common failure - the ring at
  the far left of the line is left fully intact on at least 10 slugs while the
  letters after it are cleared (270f, 272-cleanup, 277f, 280f, evelynn,
  inkshadow-kai-sa, queen-of-the-saltwind, seraphine, blood-moon-priestess-mel,
  mecha-ahri). It is a compact isolated glyph, not a stroke in a word.
- **Mask left-edge truncation.** `124f` keeps a fully readable `SMAL` at panel
  x 0-70 with the rest of the line cleared; `syndra-...-dlsfcue-pre` shows the
  same `SMAL` at its left edge. The mask starts inboard of the mark.
- **Artwork's own text erased.** `266f` again - the poster's gold
  `PRECISION IS PERFECTION` is down to three orphan vertical strokes. This is the
  known 266f defect, still present under the shipping default.
- **Fill damage on thin bright structure.** Hair strands chopped into dashes
  (soraka), feather ribs and silver strand highlights smeared to mush (xayah),
  ember sparks and cape filigree wiped flat (queen-of-the-saltwind), a crescent
  horn's hollow interior filled and its outline bulged (syndra-dlsfcue).

## What is and is not verified

**Independently re-read by the merging session: 5 of 39** - `269f` (LEGIBLE, the
full `(c) PEBANO1.DEVIANTART.COM` still reads), `124f` (LEGIBLE, `SMAL` at the
left edge), `xayah` (LEGIBLE, embossed line across the full width), plus BOTH
unflagged slugs `ashe` and `bayonetta-dm7iiug` (confirmed clean, no letterforms,
gradients continuous). All 5 agreed with the agent that reported them, including
both of the consequential clear calls.

**The other 34 are single-agent observations and are NOT independently
confirmed.** They are a priority ordering for the operator's eye, not evidence.
Treat any individual note below the top of the list as a pointer to a sheet worth
opening, not as a measurement.

## What this does not settle

It does not decide the disposition of any slug - that is the operator's, per
ADR-008 and per the zero-residue bar (operator, 2026-08-22): ghost, banding and
faint all FAIL, and no scalar is a verdict. It does not reopen any settled lane
ruling: `--scoped-revert` stays ON and `--stubs` stays opt-in (ADR-009 / LEDGER
133), and nothing here was measured against an alternative configuration. It is a
census of the shipping default's output, nothing more.
