# gen reference lane - the BASE decision, measured

_2026-08-16. Evidence for the `gen-reference-lane` ROADMAP item. n=3 per arm,
matched seeds, adapter OFF - direction-finding, not calibration._

## The yardstick is a repo artifact now, not a dead scratchpad number

`docs/GEN_MODELS.md` records a real-vs-real self-similarity ceiling of **0.8373**
whose definition lived only in a session scratchpad. It is recovered and
re-derived: **mean pairwise cosine of CLIP ViT-L-14-quickgelu/openai image
embeddings over the 21 official Ahri splashes** in
`tools/models/lora_datasets/ahri`. `tools/lw_gen_medium.py` reproduces it to four
decimals (0.83732...), which is what validates the definition - a different
measure would not land on the recorded number.

An arm's score is the mean cosine of every arm image against every real image;
`delta` is that minus the ceiling. Below the ceiling = measurably outside the
corpus distribution. It is a MEASURE, not a gate.

## The three-base A/B

Same subject (Ahri), same 16:9, same `--seed 20260816` so all three arms drew the
SAME three per-image seeds (2014205137 / 1502121425 / 2002287815). Each base ran
in its own fresh process (the `run()`-twice trap). No IP-Adapter on any arm - the
base is the variable.

| base | medium vs 0.8373 | subject_cos | margin | lap_var | QA |
|---|---|---|---|---|---|
| animagine-xl-4.0 (SHIPPED, `splash-booru`) | **0.6843 (-0.1530)** | 0.2706 | 0.0512 | 537.8 | 2/3 PASS |
| RealVisXL V5.0 (`splash`) | **0.8609 (+0.0236)** | **0.2892** | **0.0761** | 490.0 | **3/3 PASS** |
| DreamShaper XL (`splash`) | **0.8448 (+0.0075)** | 0.2691 | 0.0480 | 286.1 | 2/3 PASS |

The animagine number reproduces LEDGER 110's range (0.6427-0.7305) and the
RealVis number sits just above its range (0.8467-0.8542) - a different style
block and no adapter, so agreement at this level is confirmation, not identity.

**RealVisXL dominates on every axis measured** - medium, subject, margin, pass
rate - and it does so with the adapter OFF, which is the point: LEDGER 110 found
the medium fails independently of the adapter, and this says the same thing from
the other side.

**DreamShaper XL is the new fact.** It was on disk since 2026-07-16 (downloaded
for the cleaning lane) and had never been evaluated as a txt2img base. It clears
the ceiling too. It needed a loader change - `from_single_file` rejects a
diffusers FOLDER - so `tools/lw_gen_run.py` now resolves the load kind before the
multi-GB load (`base_load_kind` / `pretrained_variant`; an fp16-only export needs
`variant="fp16"` or `from_pretrained` silently builds an EMPTY module).

## By eye, on the matched seed 2014205137

Corroborates the metric rather than substituting for it:

- **RealVis**: canonical costume (pink/blue/gold), orb, fox tails, hero-dominant
  key-art composition, painterly - NOT the "too photoreal" failure that got this
  base flipped away from on 2026-07-11. Face and expression are clean.
- **animagine**: generic anime girl - wrong costume, wrong palette, no tails, no
  orb, heavy bloom. The medium failure and an identity failure at once, on a
  frame whose `subject_cos` (0.2706) still clears the 0.26 gate floor. This is
  the gate blindness in one image.
- **DreamShaper**: credible painterly splash art, hero-dominant, slightly less
  canonical costume than RealVis and softer (`lap_var` 286 vs 490).

## Confounds, stated

1. **Register differs by base, deliberately.** animagine ran `splash-booru`,
   the other two `splash` - LEDGER 110 verified a natural-language prompt on
   animagine scores 0/3 and renders a different champion, so `splash-booru` is
   the FAIR register for it. The consequence is that these are recipe-to-recipe
   comparisons and the style blocks carry different samplers (euler_a/28/5.5 vs
   dpmpp_2m_sde/karras). A sampler-controlled re-run is the way to close this.
2. **CLIP cosine is global similarity, not medium in isolation.** It carries
   subject and composition too. On the animagine arm that is not a confound so
   much as an accounting of the same failure twice.
3. **n=3, one champion, one prompt per base.** Direction-finding.
4. **The metric is blind to the reason RealVis was dropped.** The 2026-07-11
   flip was a by-eye call on Vayne (mangled glasses, odd expression), and no
   number here measures that. The Ahri frames look clean, but Ahri wears no
   glasses.

## What this does and does not settle

Settled by measurement: the shipped base sits **0.153 below** the corpus's own
self-similarity while passing the subject gate, and **two locally-available
bases clear that ceiling**. Nothing here was promoted and no config default was
changed.

NOT settled by measurement: whether the anime direction is the product. That was
an operator call, and reversing it is an operator call.
