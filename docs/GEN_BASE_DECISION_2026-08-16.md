# gen reference lane - the BASE decision, measured

_2026-08-16. Evidence for the `gen-reference-lane` ROADMAP item. n=3 per arm,
matched seeds, adapter OFF - direction-finding, not calibration._

> **THE CONCLUSION THIS DOCUMENT REACHED WAS REVERSED THE SAME DAY (ADR-011).**
> The numbers below are real and reproduce; the ranking they produce is wrong
> for base selection. Operator inspection of every candidate frame: animagine
> holds League and corpus conventions on ALL of them, RealVisXL violates hand
> conventions, weapon/tool canon and facial likeness, and DreamShaper violates
> the corpus look outright. CLIP corpus-similarity is global image statistics -
> palette, lighting, rendering softness - and is blind to hands, weapon canon
> and likeness, so it ranked the two failing bases first. It is a MEASURE, never
> a base-selection criterion on its own. Read the table as what it is: rendering
> register distance, nothing more.

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

**RealVisXL dominates every axis THIS STUDY MEASURED** - medium, subject,
margin, pass rate - and it does so with the adapter OFF, which is the point: LEDGER 110 found
the medium fails independently of the adapter, and this says the same thing from
the other side.

**DreamShaper XL is the new fact.** It was on disk since 2026-07-16 (downloaded
for the cleaning lane) and had never been evaluated as a txt2img base. It clears
the ceiling too. It needed a loader change - `from_single_file` rejects a
diffusers FOLDER - so `tools/lw_gen_run.py` now resolves the load kind before the
multi-GB load (`base_load_kind` / `pretrained_variant`; an fp16-only export needs
`variant="fp16"` or `from_pretrained` silently builds an EMPTY module).

## By eye, on the matched seed 2014205137

**RETRACTED 2026-08-16, same day - this section was my by-eye read of ONE frame
per arm and the operator's inspection of ALL SIX frames contradicts it.** What I
wrote is struck; what the frames actually show is below it.

- ~~RealVis: canonical costume, orb, tails, painterly, clean face.~~ **WRONG.**
  RealVisXL violates hand conventions, weapon/tool canon and facial
  design/likeness - the 2026-07-11 complaints, which this A/B did not retire
  because it never tested them.
- ~~animagine: generic anime girl, wrong costume, wrong palette, no tails, no
  orb.~~ **WRONG, and it was the load-bearing error.** Animagine holds League
  and corpus conventions on all candidate frames. I read "anime register" as
  "off-canon" from a single frame, which is precisely the conflation the metric
  makes.
- ~~DreamShaper: credible painterly splash art.~~ **WRONG.** It violates the
  corpus look and feel outright and is dropped as a candidate.

The lesson is not that by-eye evidence beats measurement. It is that ONE frame
per arm, read by the same agent that chose the metric, is not an inspection -
and that the properties in dispute (hands, weapon canon, likeness) had no
measure in this study at all.

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
self-similarity on rendering register while passing the subject gate, and two
other bases clear that ceiling. That result stands and reproduces.

**NOT settled by this measurement, and it turned out to be the whole question:**
hand conventions, weapon/tool canon and facial likeness. Nothing in this study
scored them, and they are what the base is actually selected on. ADR-011 holds
animagine and drops RealVisXL and DreamShaper as candidates; the frames for
those two arms were deleted at operator instruction, leaving
`images/_gen_scratch/basedecide/animagine/`.

**If a future base experiment runs, it must score the deciding properties.**
There is no validated automatic measure for them today, so that means operator
inspection of candidate frames - and a corpus-similarity number is at best a
tiebreak among bases that already hold the conventions.
