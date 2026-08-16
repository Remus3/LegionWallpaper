# ADR-010: lw-gen base checkpoint is RealVisXL V5.0

**Date:** 2026-08-16
**Status:** Accepted

## Context

The gen reference lane ships on Animagine XL 4.0, adopted 2026-07-11 on an
operator-directed anime-flat direction after RealVisXL V5.0 drew by-eye
complaints on a Vayne recipe (mangled glasses, odd expression, too photoreal).

Measurement since has gone the other way. `docs/GEN_MODELS.md` records a
gate-independent yardstick - the real corpus's own self-similarity, **0.8373**
mean pairwise CLIP ViT-L-14-quickgelu cosine over the 21 official Ahri splashes.
Its definition had been lost to a session scratchpad; `tools/lw_gen_medium.py`
re-derives it and reproduces 0.83732 to four decimals, which is what validates
the definition rather than merely restating it.

A three-base A/B (matched seeds, adapter OFF, one fresh process per arm,
n=3, `docs/GEN_BASE_DECISION_2026-08-16.md`):

| base | medium vs 0.8373 | subject_cos | margin | lap_var | QA |
|---|---|---|---|---|---|
| animagine-xl-4.0 (shipped) | 0.6843 (**-0.1530**) | 0.2706 | 0.0512 | 537.8 | 2/3 |
| RealVisXL V5.0 | 0.8609 (**+0.0236**) | 0.2892 | 0.0761 | 490.0 | 3/3 |
| DreamShaper XL | 0.8448 (+0.0075) | 0.2691 | 0.0480 | 286.1 | 2/3 |

The shipped base is the only arm below the ceiling, and it clears the 0.26
subject floor while doing so - the gate blindness LEDGER 110 measured, seen from
the base side rather than the adapter side. By eye on the matched seed, the
animagine frame is a generic anime girl with the wrong costume and no tails or
orb; the RealVis frame is canonical, painterly and hero-dominant, and the 2026-
07-11 photoreal failure does not reproduce on this recipe.

Alternatives considered: (a) stay on animagine and accept the medium gap as the
cost of the anime direction; (b) DreamShaper XL, which also clears the ceiling
but costs sharpness and renders a looser costume canon; (c) close the
register/sampler confound with a larger sampler-controlled sweep before ruling -
declined because the animagine gap (0.153) is far wider than a sampler could
plausibly explain, and (c) remains available as a refinement.

## Decision

`lw-gen`'s base checkpoint is **RealVisXL V5.0**
(`tools/models/RealVisXL_V5.0/RealVisXL_V5.0_fp16.safetensors`) with the
natural-language `splash` style register. Operator ruling 2026-08-16, reversing
the 2026-07-11 anime-flat direction on measured evidence.

## Consequences

**Good:** The lane now generates inside the corpus distribution on the only
gate-independent measure available, and it does so with the adapter off, so the
IP-Adapter work (plus-face, loose crop, scale 0.3 - LEDGER 110/111) sits on a
base that no longer fails the medium independently. Subject identity, margin and
pass rate all improve at the same time, so nothing was traded for it.

**Trade-off:** The anime-flat look is given up. Animagine's canonical champion
knowledge (correct glasses/crossbows on Vayne) and its `splash-booru` register
are no longer the shipped path; the booru style block stays in
`tools/lw_gen_styles.json` and animagine stays on disk, so a per-brief override
via `--model-path` / `--style` remains one flag away.

**Watch for:**
- **The Vayne glasses case is UNTESTED on this recipe.** The 2026-07-11
  rejection was a Vayne judgement and Ahri wears no glasses. Re-check before
  treating the old complaint as retired.
- **Register/sampler confound on record:** animagine ran `splash-booru`
  (euler_a/28/5.5) and the other arms `splash` (dpmpp_2m_sde/karras), so the
  table compares recipe to recipe. A sampler-controlled re-run would tighten it.
- **The 0.8373 ceiling rests on ONE champion** (21 Ahri splashes) and is a
  MEASURE, not a gate. Do not wire it into QA on this evidence.
- n=3 per arm - direction-finding, not calibration.
