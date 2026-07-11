# LegionWallpaper Generator Sidecar (lw-gen) - DURABLE SPEC

> INGEST: copied into the repo 2026-07-10 from
> `C:\Users\Administrator\Desktop\LEGIONWALLPAPER_GENERATOR_SIDECAR_PLAN.md`
> (authored 2026-07-06). This is the durable, tracked spec of record for the
> lw-gen sidecar. The OPERATOR DECISIONS in section 9 are LOCKED (answered
> 2026-07-06): 16:9-only MVP (no ultrawide), model class picked by eye in
> Phase 0, HARD-GATE gen off when RC/League/vision is live, auto-intake ON at
> Phase 4, splash-first MVP style set. Do not re-litigate those five without
> explicit operator approval. Body below is the ingested plan verbatim,
> ASCII-clean.

---

# LegionWallpaper Generator Sidecar (lw-gen) - IMPLEMENTATION PLAN

Durable planning doc. Strict 7-bit ASCII. Local-first on the RTX 5070 (12GB GDDR7,
Blackwell sm_120). Authored 2026-07-06. All live claims below were probed against
C:\LegionWallpaper (torch 2.11.0+cu128, get_device_capability()==(12,0), RTX 5070,
12227 MiB, driver 610.62 - all CONFIRMED). This is a build spec, not a paste-prompt.

--------------------------------------------------------------------------------

## 0. WHAT THIS IS AND WHY

The operator wants a SIDECAR that GENERATES League-champion splash-art-style desktop
wallpapers from a text brief (subject + style + count), using free/open-source local
AI on the 5070. The generated images must FIRST pass a subject-matter QA gate (does
the image actually depict the requested champion), and only then enter the operator's
EXISTING numbered phase pipeline (0.Originals .. 8.End Review .. 9.Image Backup),
where they ride the same curation chain as scraped originals and must earn a human
pass at 8.End Review.

Design philosophy, inherited from the existing pipeline and NON-NEGOTIABLE:
- Heavy ML lives in gitignored side venvs, NEVER in requirements.txt (CI stays
  pytest/ruff/numpy/Pillow, torch-free).
- The filesystem is the handoff between stages (a batch dir + a manifest JSON).
- The sidecar is a PRODUCER of stage-0 inputs. It does NOT add or modify any numbered
  stage. The human 8.End Review stays the final arbiter.
- Strict 7-bit ASCII in every authored .py / .json / .md (no em/en-dash, no smart
  quotes). ' - ' for a clause break, '-' otherwise.

--------------------------------------------------------------------------------

## 1. EXECUTIVE SUMMARY + DATA FLOW

lw-gen is three thin batch scripts, each pinned to the venv that owns its deps. No
service, no port, no supervisor task. This matches the proven .venv-upscale /
.venv-metrics shell-out pattern exactly.

```
 operator brief (subject + style + count)
        |
        v
 +----------------------------------+
 | lw_gen_run.py     [.venv-gen]    |  diffusers txt2img, headless batch, fp16
 | build prompt from style template |  SDPA attention, cpu-offload DEFAULT
 | generate N candidates            |  1344x768 (16:9-native), 30 steps
 +----------------------------------+
        |  raw PNGs -> images/_gen_scratch/<batch-id>/   (gitignored, pipeline-invisible)
        v
 +----------------------------------+
 | lw_gen_qa.py      [.venv-metrics]|  ===== FIRST GATE: SUBJECT-MATTER QA =====
 | Stage A: CLIP subject match      |  (net-new; every wired metric today is full-reference)
 | Stage B: no-ref quality + CV blur|
 +----------------------------------+
        |  PASS candidates + gen_manifest.json (per-candidate scores)
        |  FAIL / near-miss -> images/_gen_scratch/<batch>/review/  (human eyeball, never deleted)
        v
 +----------------------------------+
 | lw_gen_promote.py [stdlib]       |  top-K, slugify, ATOMIC write into 0.Originals
 |                                  |  does NOT shell intake/annotate inline (see MUST-FIX 2/3)
 +----------------------------------+
        |
        v
 images/0.Originals/    (loose files; operator or a later step runs `intake --all`)
        |
        v
 EXISTING PIPELINE, UNCHANGED (first_pass ALREADY runs the DAT2 upscale internally):
   1.First Pass Scratch  -> 2.First Pass Done
   3.Cleaning Scratch    -> 4.Cleaning Done
   5.Final Scratch       -> 6.Final Done
   7.Last Scratch        -> 8.End Review   (HUMAN gate - final arbiter, unchanged)
                         -> 9.Image Backup
```

Hard ordering rule: Stage A (subject) gates Stage B (quality) gates promotion.
Upscaling a wrong-subject image wastes GPU, so subject is verified FIRST, exactly as
the operator required. From the atomic write onward a generated image is
indistinguishable from a scraped original EXCEPT for its `gen://` provenance tag - it
rides the exact existing chain and earns its 8.End Review pass under the same review.

The single most important correction from the adversarial review: the numbered
pipeline is a FIDELITY-RESTORATION chain, not a generic quality chain. first_pass
computes ms_ssim / lpips / lap_ratio between an UPSCALE OUTPUT and its SOURCE. For a
generation, the generated PNG IS the source; first_pass then upscales it and compares
upscale-vs-gen, which is structurally valid, but the metric FLOORS were calibrated on
scraped splash sources and must be re-validated for diffusion inputs before we claim
"rides the gate unchanged" (see Phase 2.5).

--------------------------------------------------------------------------------

## 2. TOOL + MODEL STACK + VRAM BUDGET (RTX 5070, 12GB Blackwell)

Runtime is already proven. .venv-gen adds only python/torch-dependent packages, NO
new CUDA toolkit.

### 2.1 Engine
HuggingFace `diffusers` (import-and-call, headless, scriptable). Deps added to
.venv-gen: `diffusers`, `transformers`, `accelerate`, `safetensors`. ComfyUI-as-a-
service was rejected for MVP (ceremony: new port, supervisor task, graph-JSON version
coupling, liveness handling). ComfyUI is a DOCUMENTED FUTURE escape hatch for
ControlNet / inpaint / regional-prompt graphs only.

### 2.2 Base model - DECISION: painterly/semi-realistic SDXL finetune, NOT an anime finetune
This is the binding QUALITY risk (bigger than the CUDA runtime, which is already
retired). LoL champion splashes (Ambessa, Darius, Hecarim, Illaoi) are painterly
semi-realistic Western key art - the anti-anime aesthetic. A booru-tag anime finetune
(Illustrious-XL / Animagine-XL class) renders a flat cel-shaded anime figure labeled
"Ambessa", which then FALSELY PASSES the CLIP subject gate (CLIP scores concept match,
not art-style match). Wrong-style-but-right-concept is exactly CLIP's blind spot, so
an anime model would compound the QA weakness.

CANONICAL: evaluate painterly / semi-realistic SDXL 1.0 finetunes in the Phase-0
spike, judged BY EYE against real 0.Originals splashes. Candidate classes to try:
- A Juggernaut-XL / RealVisXL-class photoreal-leaning SDXL finetune (strong on
  muscular/armored/dramatic subjects).
- Base SDXL 1.0 + a splash-art / concept-art / key-art LoRA (the LoRA carries the
  painterly look; base SDXL carries anatomy).
- A dedicated "digital painting" or "concept art" SDXL finetune.
The spike picks ONE by eye; do not default to anime. Style-fidelity vs real
0.Originals is a Phase-0 ACCEPTANCE criterion, not just "a gen completes."

Why SDXL-lineage and not the alternatives:
- NOT SD1.5: 1024-native SDXL gives far better anatomy/composition for splash-art.
- NOT FLUX.1-dev: ~24GB fp16 / ~12GB nf4 eats the whole budget on a shared box, is
  slower per image, and its painterly finetunes are weaker than SDXL's today.
  FLUX-schnell is a FUTURE knob-check.
Model weights live in `tools/models/` (existing repo convention - the upscale models
already live there; do NOT invent `tools/gen_models/`). Weights are gitignored.

### 2.3 Refiner - OFF
The existing DAT2 4x upscale inside first_pass IS the finishing step. A diffusion
refiner is redundant VRAM pressure and would violate the no-double-resample rule.

### 2.4 LoRA / ControlNet / IP-Adapter - NONE at MVP
- LoRA: a splash-art style LoRA is likely REQUIRED to hit the painterly look (see 2.2);
  if used it is loaded via diffusers `load_lora_weights` in .venv-gen. A per-champion
  subject LoRA (tightest fidelity) is a FUTURE training pass, deferred.
- ControlNet (pose/depth): FUTURE, ComfyUI-graph-gated.
- IP-Adapter (seed style/subject from an existing 0.Originals splash): a strong FUTURE
  subject-fidelity lever, deferred to keep MVP small.

### 2.5 Subject-QA model - CLIP (must be freshly installed; the existing copy is BROKEN)
CRITICAL CORRECTION: the plan-of-record assumed "reuse the CLIP pyiqa already pulls
into .venv-metrics - no new install." That is FALSE, probed live:
- `pyiqa.create_metric('clipiqa')` FAILS with
  `ImportError: cannot import name 'packaging' from 'pkg_resources'`. The bundled
  OpenAI `clip` package does `from pkg_resources import packaging`, removed in
  setuptools 70.2.0 (the installed version). `import open_clip` also
  ModuleNotFoundError.
- The only wired pyiqa metrics today are full-reference (psnr/ssim/ms_ssim/lpips/
  dists) - useless for a reference-less generation.
So there is NO reusable working CLIP. Phase 2 MUST first establish a working CLIP.
CANONICAL path (the honest one): add `open-clip-torch` fresh into .venv-metrics and
load `ViT-L-14` directly. This is a new dep + a new ~1.7GB weight download. Budget
CLIP at ~1.5-2GB resident. (Alternative: pin setuptools<70 to un-break the bundled
clip - REJECTED as the default because it risks other .venv-metrics deps; if tried,
re-run the full metrics suite after. open-clip-torch is cleaner and self-contained.)
A heavier VLM (LLaVA-class caption-and-check) is rejected for MVP: +4-7GB VRAM,
slower, and CLIP cosine against a distractor set answers "is this the right champion"
directly and cheaply.

### 2.6 Quality read (Stage B)
- No-reference aesthetic: use a working no-ref metric. Preferred = the open-clip
  ViT-L we already load for Stage A, scored via a CLIP-IQA-style prompt pair
  ("a high quality image" vs "a low quality image") computed by hand - this avoids
  depending on pyiqa's broken clipiqa wrapper. If pyiqa's clipiqa is un-broken during
  Phase 2 it may be used instead; do not BLOCK on it.
- CV blur/banding: reuse `lw_g1_gate.laplacian_var(gray)` as a PRIMITIVE only. NOTE:
  the gate's real sharpness metric is a laplacian RATIO vs source (full-reference);
  there is no source here, so we define a NEW absolute no-reference laplacian-variance
  threshold and calibrate it (Phase 2). The "reuse verbatim" framing is wrong - we get
  the primitive, not the floor.

### 2.7 VRAM budget (fp16, batch 1, SDXL, REAL free budget ~9.5GB not 12GB)
CRITICAL CORRECTION: live nvidia-smi shows ~2332 MiB already used at idle (desktop /
Chrome / DWM). Real free was ~9612 MiB when probed, and LESS during any concurrent RC
/ League / vision / OBS activity on this 1-PC box. Budget against ~9.5GB free, and
make VRAM-saving the DEFAULT.

| Stage | Process / venv | Config | Est peak VRAM | Notes |
|---|---|---|---|---|
| Generation | lw_gen_run / .venv-gen | SDXL fp16, cpu-offload ON (default), tiled VAE decode, SDPA | ~3-4 GB resident, ~5-6 GB peak w/ offload | offload is DEFAULT here, not fallback |
| Generation (fast path, opt-in) | same | all-resident, no offload | ~7 GB resident, ~9-10 GB peak | ONLY when the box is idle-verified; risks OOM on a busy card |
| VAE decode spike | same | tiled decode | +0.5-1 GB | tiled decode ON by default (classic SDXL OOM point) |
| Subject QA | lw_gen_qa / .venv-metrics | open-clip ViT-L | ~1.5-2 GB | runs AFTER gen process EXITS - full card free |
| Upscale (inside first_pass) | lw_upscale / .venv-upscale | DAT2 4x tiled (512 tile) | ~4-6 GB | already tuned to 12GB; gen process long gone |

The three heavy stages NEVER co-reside (separate subprocess per venv; process teardown
returns all VRAM). But the DESKTOP baseline DOES co-reside, which is why offload +
tiled-decode are the default and why gen should be gated behind an "is RC/League live"
check (reuse the RC health-probe pattern) or simply run only when the box is idle.

--------------------------------------------------------------------------------

## 3. OPERATOR-INPUT SURFACE

One command, small memorable flag set. Two modes: inline (quick) and brief file
(repeatable per-champion batches). lw_gen_qa and lw_gen_promote run automatically as
the tail of lw_gen_run (it shells into the other two venvs); split invocation is for
debugging.

```
# inline (quick)
py -m lw_gen_run --subject "Ambessa" --style splash --n 4

# brief file (repeatable, git-diffable)
py -m lw_gen_run --brief briefs/ambessa.json
```

Brief JSON (all ASCII, operator-authored):

```json
{
  "subject": "Ambessa",
  "subject_aliases": ["Ambessa", "Noxus general", "war paint", "greatsword warrior"],
  "style": "splash",
  "n": 4,
  "aspect": "16:9",
  "prompt_extra": "dramatic backlight, storm sky",
  "negative_extra": "",
  "seed": null,
  "qa_subject_floor": 0.26,
  "qa_margin_floor": 0.05,
  "max_regen_rounds": 1
}
```

Defaults tuned for LOW friction and bounded GPU spend (see MUST-FIX 8 rationale):
- `n = 4` (not 8), `max_regen_rounds = 1` (regen is OPT-IN, not the default),
  `aspect = "16:9"`, `style = "splash"`, random seed, top-K = 3.
- Default behavior: generate 4, QA, promote what passes, dump the rest to
  `_gen_scratch/<batch>/review/` for eyeballs, with NO auto-regen. Auto-regen at
  N rounds is a power-user flag.
- `subject` selects prompt template + QA target text. `subject_aliases` feed the QA
  acceptance vocabulary (a splash depicts Ambessa without a literal label).
- `style` picks a template (section 5). `aspect` maps to a fixed resolution table in
  config - the template does NOT encode pixels. MVP supports 16:9 ONLY (see 5.x).
- Sampler internals (model / steps / cfg / resolution table) live in
  `tools/lw_gen_config.json`, edited rarely. The operator should never tune a sampler
  per wallpaper.

--------------------------------------------------------------------------------

## 4. SUBJECT-MATTER QA GATE (THE FIRST GATE - net-new capability)

Runs in .venv-metrics. Two stages, both no-reference (a fresh generation has no
ground-truth image). Ordering is a HARD rule: Stage A gates Stage B gates promotion.

Prerequisite (Phase 2, blocking): a WORKING CLIP must exist. The existing
pyiqa/clipiqa import is BROKEN (section 2.5). Install `open-clip-torch` into
.venv-metrics and load `ViT-L-14` directly. Do NOT claim zero-install QA.

### Stage A - SUBJECT PRESENCE (primary; must pass first)
- Load open-clip ViT-L once per batch.
- `subject_cos` = cosine(image_embed, text "a wallpaper of {subject}, a League of
  Legends champion" + aliases, mean-pooled).
- `off_cos` = max cosine against a DISTRACTOR set (other champion names, "blank art",
  "generic anime character", "generic character").
- PASS iff the correct-subject text is the ARGMAX over distractors AND clears a floor:

```
subject_cos = clip_cos(img, subject_target_text)     # higher = on-subject
off_cos     = max(clip_cos(img, distractor_texts))
margin      = subject_cos - off_cos

STAGE_A_PASS  iff  subject_cos >= T_subj (default 0.26)     # absolute confidence
             AND  margin      >= T_margin (default 0.05)    # beats every distractor
```

`T_subj` = absolute on-subject confidence; `T_margin` guards a generic image that
weakly matches everything. Argmax-over-distractors (not a bare floor) is what rejects
"rendered the wrong champion." HONEST LIMITATION: CLIP scores CONCEPT, not ART STYLE,
so an anime-styled correct champion can pass - which is precisely why section 2.2
forbids an anime base model. The base-model choice is part of the QA guarantee.

### Stage B - BASELINE QUALITY (secondary; only on Stage-A pass)
- `aesthetic` = no-ref quality score (open-clip prompt-pair per 2.6), rejects
  melted/garbled outputs that still color-match.
- `lap_var` = `lw_g1_gate.laplacian_var(gray)` primitive with a NEW absolute
  no-reference threshold (calibrated in Phase 2; NOT the gate's source-ratio floor).

```
STAGE_B_PASS  iff  aesthetic >= T_aes (default 0.45)
             AND  lap_var   >= T_blur (new no-ref sharpness floor, calibrated)
```

### Decision logic (per candidate, per round)

```
for each candidate:
    if not STAGE_A_PASS: REJECT (reason = wrong_subject | weak_margin)
    elif not STAGE_B_PASS: REJECT (reason = degenerate | blurry)
    else: PASS, rank by subject_cos

round result:
    passes = [c for c if PASS]
    if len(passes) >= 1: promote top-K by subject_cos (default K=3), STOP
    elif round < max_regen_rounds (default 1, i.e. no regen by default):
        REGENERATE: fresh seed; round>=2 also CFG +0.5 + append failing-alias emphasis
    else (cap hit, zero passes):
        write best-scoring near-miss to images/_gen_scratch/<batch>/review/ for HUMAN eyes
        (never a silent black-hole; operator decides)
```

- Every candidate gets `<image>.qa.json` (subject_cos, off_cos, margin, aesthetic,
  lap_var, verdict, reason, round, seed, model, prompt) - mirrors the existing
  `fr_metrics` sidecar convention and is the labeled data for threshold tuning.
- `gen_manifest.json` at batch root aggregates per-candidate scores + the promote
  decisions.
- Thresholds calibrated ONCE (Phase 2) against known-good 0.Originals exemplars +
  deliberately-wrong-subject negatives.

HONEST LIMITATION: CLIP subject-QA is probabilistic. It will occasionally pass a
close-but-wrong champion or reject a heavily-stylized-but-correct one. Mitigations:
argmax-over-distractors, painterly (non-anime) base model, operator eyeball on
REJECTs, and the human 8.End Review backstop. The gate cuts obvious garbage cheaply;
it is not a perfect classifier.

--------------------------------------------------------------------------------

## 5. STYLIZATION + CONTROL PIPELINE (base -> style -> upscale -> target)

Style presets live in `tools/lw_gen_styles.json`, keyed by the `style` field - DATA,
not code. Each preset is a positive/negative template pair with `{subject}`,
`{prompt_extra}`, `{negative_extra}` slots via trivial `str.format()` (no template DSL).

```json
{
  "splash": {
    "positive": "splash art of {subject}, League of Legends champion, painterly semi-realistic key art, dynamic action pose, cinematic composition, dramatic rim lighting, richly detailed, desktop wallpaper, {prompt_extra}",
    "negative": "anime, cel shaded, flat colors, chibi, text, watermark, signature, logo, ui, hud, healthbar, border, frame, low quality, blurry, jpeg artifacts, extra limbs, extra fingers, deformed hands, multiple characters, collage, {negative_extra}",
    "sampler": {"name": "dpmpp_2m_sde", "scheduler": "karras", "steps": 30, "cfg": 5.5}
  },
  "portrait":          { "positive": "... centered bust, shallow depth of field ...", "...": "..." },
  "landscape-ambient": { "positive": "... {subject} in a Runeterra environment, environment-led, subject smaller ...", "...": "..." }
}
```

Design rule for the negative block: aggressively exclude the WALLPAPER failure modes
(text/watermark/ui/border/healthbar), the SUBJECT-QA failure modes (deformed anatomy,
multiple characters), AND the STYLE failure mode (anime/cel-shaded/chibi) so the
generator's own guardrails align with all downstream gates. Ship 3 styles at MVP:
`splash` (default), `portrait`, `landscape-ambient`. Style is decoupled from subject:
any champion x any style is a two-field change.

### Resolution + aspect - 16:9 ONLY at MVP (ultrawide is OUT)
CRITICAL CORRECTION: the pipeline is hardcoded 16:9. `lw_first_pass.TARGET = (2560,
1440)`; `_finish` RAISES on non-16:9; `aspect_class` HOLDs off-16:9 inputs rather than
producing a 21:9 output. So any 21:9 / ultrawide generation would be cropped to 16:9
or stuck in scratch forever. The probe did NOT confirm ultrawide is a real target.
Therefore:
- MVP generates 16:9 ONLY, at SDXL-native `1344x768` (1.05M px, on-manifold; note this
  is 1.75:1, slightly off true 16:9 1.78:1 - fine after DAT2 + the pipeline's center
  handling). Never diffuse at 4K (blows VRAM + SDXL degrades off-native).
- Ultrawide 3440x1440 is DEFERRED. It is NOT a sidecar feature: it needs a real
  multi-target refactor of `TARGET` / `_finish` / `aspect_class` plus a wide-bucket
  gen + outpaint step. Logged as an open question for the operator (section 8).
- `1536x640`-class "21:9" is explicitly REJECTED even as a future default: it is
  0.98M px (under manifold) and 2.40:1 (cinemascope, not 21:9), and off-bucket SDXL
  duplicates subjects (the exact "multiple characters" failure).

### Full stylization -> 4K chain (CORRECTED: no double upscale)

```
1. GENERATE   diffusers txt2img, painterly SDXL finetune, style template applied,
              1344x768 (16:9-native), cpu-offload + tiled VAE decode + SDPA   [.venv-gen]
2. STYLE      applied AT generation via the positive/negative template (no separate pass)
3. CONTROL    NONE at MVP (ControlNet / IP-Adapter are FUTURE, ComfyUI-graph-gated)
4. SUBJECT-QA CLIP gate (section 4)                                          [.venv-metrics]
5. PROMOTE    top-K -> 0.Originals (loose file, gen:// provenance)           [stdlib]
6. PIPELINE   EXISTING first_pass runs the DAT2 4x upscale + Lanczos-to-2560x1440
              + single clamped unsharp INTERNALLY (STEP 3 of first_pass).    [.venv-upscale]
              The sidecar does NOT run lw_upscale separately - that would be a
              double-resample. One resample, inside the existing stage.
```

--------------------------------------------------------------------------------

## 6. INTEGRATION WITH THE REAL PHASE FOLDERS/DRIVERS

Confirmed chain (probed live):
`0.Originals -> 1.First Pass Scratch -> 2.First Pass Done -> 3.Cleaning Scratch ->
4.Cleaning Done -> 5.Final Scratch -> 6.Final Done -> 7.Last Scratch -> 8.End Review
-> 9.Image Backup` (+ `reference_pictures` untouched). `lw_pipeline` transition T1
(`intake`) = 0.Originals -> first scratch; T7 (`finalize`) = 8.End Review pass ->
9.Image Backup.

### Integration seam = 0.Originals ONLY.
`lw_gen_promote.py` job, corrected for three mechanical contract failures found in the
adversarial review:

1. Take each promoted candidate; reuse `lw_pipeline.slugify` (lowercase, `[a-z0-9-]`,
   <=64, reserved-name guard) to build a pipeline-legal base name, e.g.
   `ambessa-splash-a1b2`.
2. ATOMIC write into 0.Originals. Use LegionWallpaper's OWN primitives, not a Riot
   Commander convention that does not exist here: prefer `Ops.safe_copy`
   (copy + fsync + SHA256-verify) or a local retry-wrapped `os.replace`. The repo's
   `Ops.write_json` uses a bare `os.replace` with NO retry - do not copy that; add the
   retry locally to survive a transient WinError 5 under concurrent pipeline read.
   Assert width < 2560 AND height < 1440 before the drop (1344x768 passes), so a
   future config edit cannot silently flip first_pass into the downscale-only metric
   path where the lap_ratio floor is invalid.
3. DO NOT shell `intake` inline. `cmd_intake` enforces `MIN_AGE_SECONDS = 10.0` (file
   mtime must be >=10s old) plus a `PROBE_SECONDS = 2.0` size-stability re-probe. A
   just-written file is ~0s old and would be SILENTLY SKIPPED ("modified too
   recently"). CANONICAL default: promote writes the loose file to 0.Originals and
   STOPS. The operator (or a later Phase-4 step) runs `py lw_pipeline.py intake --all`.
   This matches the "producer of stage-0 inputs only" boundary.
4. DO NOT guess the post-intake slug. `cmd_intake` calls `unique_slug(...)` which
   appends `-2`, `-3`... on collision and RAISES on a hash-equal re-intake.
   `cmd_annotate` locates a slug via find_scratch -> find_done -> backup ONLY (never
   0.Originals) and needs the EXACT final slug. So annotate CANNOT run in promote.
   Correct order when annotation is wired (Phase 3/4): (a) drop file, (b) run
   `intake --all`, (c) PARSE intake stdout (`intake <file> -> <slug>`) or re-scan and
   match by original filename/hash to recover the ACTUAL slug, (d) THEN
   `annotate <recovered-slug> --source-url gen://lw-gen/<batch-id> --tool lw-gen
   --metrics @gen_manifest_slice.json`. Never reconstruct the slug.

### Why raw output stays OUTSIDE the numbered folders
The pipeline's `_analyze_folder` scanner parses every file in `images/0..9` and flags
UNPARSED_FILE anomalies (verified). Un-QA'd generations must never sit in a numbered
folder. `images/_gen_scratch/` is gitignored (matched by `images/**` with no
`.gitkeep`) and pipeline-invisible; only QA-passed, slugified files cross into
0.Originals.

### The g1 gate is FIDELITY, not quality - re-calibration is required (Phase 2.5)
`lw_first_pass` steps 4-6 and `lw_g1_gate.verdict` compute `ms_ssim`, `lpips(alex)`,
and `lap_ratio = laplacian_var(output)/laplacian_var(source)` between the first-pass
OUTPUT and its source. For a generation the generated PNG is the source, so the
comparison (upscale-vs-gen) is structurally valid, BUT the floors (`ms_ssim>=0.98`,
`lpips<=0.12`, `lap_ratio>=1.0`) were calibrated on scraped DeviantArt splash sources,
NOT diffusion output. Before Phase 3, run a labeled calibration batch (10+ real
generations through first_pass), record observed metric ranges, and if they
systematically FAIL, add a gen-provenance threshold profile keyed off
`man["source_url"].startswith("gen://")` rather than reusing DEFAULT_G1_THRESHOLDS
blindly. Do NOT claim "g1 unchanged" until that batch exists.

### Files
- New: `tools/lw_gen_run.py`, `tools/lw_gen_qa.py`, `tools/lw_gen_promote.py`,
  `tools/lw_gen_styles.json`, `tools/lw_gen_config.json`, `briefs/*.json`,
  `docs/GEN_MODELS.md`.
- New gitignored: `.venv-gen`, `tools/models/<gen checkpoint>` (existing models dir),
  `images/_gen_scratch/`.
- Reused unchanged: `tools/lw_pipeline.py` (slugify / intake T1 / annotate /
  finalize T7), `tools/lw_g1_gate.py` (laplacian_var primitive), `tools/lw_upscale.py`
  (DAT2 4x, called by first_pass), `.venv-metrics` (+ open-clip-torch), `.venv-upscale`.
- Untouched: stages 1-9 logic and the human 8.End Review gate.
- gitignore check: confirm `.venv-*`, `images/**`, and `tools/models/*` cover the new
  dirs; add a line if `tools/models/*` is not already ignored.

--------------------------------------------------------------------------------

## 7. INSTALL / SETUP ON BLACKWELL

Binding hardware constraint already satisfied (probe-confirmed) - no CUDA/PyTorch
upgrade needed.
- Both existing venvs run torch 2.11.0+cu128 (CUDA 12.8), well past the 2.7.0+cu128
  floor that first shipped sm_120 (Blackwell) kernels. `get_device_capability()`
  returns `(12,0)` live. The 5070 is generation-ready as-is.
- Build .venv-gen from the SAME interpreter the other venvs use:
  `C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe` (3.12.10).

```
# 1. create the new side-venv (gitignored, like .venv-upscale / .venv-metrics)
C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe -m venv C:\LegionWallpaper\.venv-gen

# 2. install the SAME cu128 torch channel the box already runs (do NOT let pip pull a CPU/cu12x wheel)
C:\LegionWallpaper\.venv-gen\Scripts\python.exe -m pip install torch==2.11.0+cu128 torchvision==0.26.0+cu128 --index-url https://download.pytorch.org/whl/cu128

# 3. add the generation stack (pure-python / torch-dependent; no new CUDA toolkit; NO xformers)
C:\LegionWallpaper\.venv-gen\Scripts\python.exe -m pip install diffusers transformers accelerate safetensors

# 4. add a working CLIP into .venv-metrics (the existing pyiqa/clip import is BROKEN)
C:\LegionWallpaper\.venv-metrics\Scripts\python.exe -m pip install open-clip-torch

# 5. download ONE painterly/semi-realistic SDXL finetune (safetensors) into tools\models\ (gitignored)
#    plus, if the spike shows anime leakage, one splash-art/key-art LoRA.

# 6. LIVE PROOF (retire the runtime + attention risks before building on top):
C:\LegionWallpaper\.venv-gen\Scripts\python.exe -c "import torch; print(torch.cuda.get_device_capability())"
   # MUST print (12, 0)  -> confirms sm_120 kernels load on the 5070
```

Blackwell gotchas the naive recipe omits (add to the launcher env):
- Set `TORCH_CUDA_ARCH_LIST=12.0` and `CUDA_MODULE_LOADING=LAZY` in the lw_gen_run
  process environment (sm_120 is not always auto-detected).
- Ensure `CUDA_VISIBLE_DEVICES` is NOT `-1` (a stray `-1` silently disables the GPU).
- Pin the attention backend to torch SDPA explicitly; do NOT install xformers (no
  guaranteed sm_120 wheel). `attention-slicing` is the SLOW path - SDPA is the right
  Blackwell default. attention-slicing may still be enabled as an additional VRAM
  saver, but SDPA is the compute backend.
- Enable `enable_model_cpu_offload()` and tiled VAE decode BY DEFAULT (section 2.7).

Discipline:
- Heavy ML NEVER enters requirements.txt (CI stays pytest/ruff/numpy/Pillow,
  torch-free). .venv-gen follows the exact .venv-* pattern.
- Avoid `uvx` (dies under Vanguard's .data lock on this box); use the persistent venv.

--------------------------------------------------------------------------------

## 8. PHASED ROADMAP (each phase independently shippable, with acceptance)

### Phase 0 - Spike (no repo change): retire the REAL binding risk (art style), not CUDA
Build .venv-gen, install the stack, add open-clip-torch to .venv-metrics, download one
painterly SDXL finetune (+ optional splash LoRA), and generate one Ambessa batch in a
throwaway script.
ACCEPTANCE:
- `torch.cuda.get_device_capability()` returns `(12,0)` live; SDPA active; GPU visible
  (no CUDA_VISIBLE_DEVICES=-1).
- A 1344x768 SDXL gen completes; peak VRAM measured WITH the real desktop resident
  present (not a clean card) stays within ~9.5GB free (offload + tiled decode ON).
- STYLE-FIDELITY: the output looks like a painterly LoL splash judged BY EYE against
  real 0.Originals - NOT flat anime. This is the gating acceptance; if the chosen model
  fails it, swap model/LoRA before proceeding.
- open-clip ViT-L loads and scores an image in .venv-metrics (proves the QA foundation
  is un-broken).
Nothing committed.

### Phase 1 - Generator to scratch (no promotion)
Land `lw_gen_run.py` + `lw_gen_styles.json` + `lw_gen_config.json`. Output to
`images/_gen_scratch/<batch-id>/` only. All torch/diffusers imports LAZY (inside
functions), mirroring lw_first_pass, so no CI-collected test can import torch.
ACCEPTANCE:
- `py -m lw_gen_run --subject X --style splash --n 4` produces 4 raw PNGs in scratch.
- ruff-clean; `.venv-gen` / `tools/models/*gen*` / `_gen_scratch` gitignored; nothing
  heavy in requirements.txt; `pytest tests/` collects green with no .venv-gen present.

### Phase 2 - Subject-QA gate (the operator's required first gate)
Land `lw_gen_qa.py` in the .venv-metrics lane on top of a WORKING open-clip ViT-L.
Calibrate `T_subj` / `T_margin` / `T_aes` / `T_blur` (the last is a NEW no-ref
laplacian floor) against labeled known-good 0.Originals + known-wrong-subject
negatives. Write `.qa.json` sidecars + `gen_manifest.json`; the (default-off) regen
loop; the `_gen_scratch/<batch>/review/` human-triage folder.
ACCEPTANCE:
- open-clip ViT-L is installed and scoring (the broken clip is bypassed).
- A wrong-subject generation is REJECTED before promotion; a correct one PASSES;
  `gen_manifest.json` records per-candidate scores.
- A pytest keeps all torch/pyiqa imports LAZY, mocks the CLIP scorer, and asserts
  (a) Stage-A-before-Stage-B ordering and (b) argmax-over-distractors logic -
  CI-safe because the model call is mocked (matches how lw_g1_gate tests avoid torch).

### Phase 2.5 - Calibration + intake-contract proof (NEW, gates Phase 3)
This phase exists because the numbered pipeline is a fidelity chain, not a quality
chain, and three intake contracts were assumed away.
ACCEPTANCE:
- Run 10+ real generations through `intake --all` + first_pass MANUALLY; record the g1
  metric distributions (ms_ssim / lpips / lap_ratio) for diffusion inputs. If they
  systematically FAIL, define a `gen://`-keyed threshold profile; document the numbers.
- Prove the intake contract end-to-end on ONE image: write to 0.Originals, wait the
  >10s age gate, run `intake --all`, RECOVER the actual slug from intake stdout, run
  `annotate <slug> --source-url gen://... --metrics @slice.json`, and confirm the
  manifest records gen provenance.
- Confirm `py lw_pipeline.py scan` reports ZERO UNPARSED_FILE anomalies.

### Phase 3 - Promotion + wiring (manual intake handoff)
Land `lw_gen_promote.py`; chain the 3 scripts into one `lw_gen_run` command. Promote
writes QA-passed, slugified, size-asserted loose files into 0.Originals using the
repo's own atomic-write primitive + local WinError-5 retry. Promote does NOT shell
intake/annotate inline (contract failures, section 6). It prints the drop paths and
the exact `intake --all` command for the operator.
ACCEPTANCE:
- One command takes a brief in and lands QA-passed, slugified PNGs in 0.Originals with
  `gen://` provenance queued for annotate.
- `lw_pipeline scan` reports ZERO UNPARSED_FILE; after a manual `intake --all` the
  image flows through 1.First Pass under existing drivers with NO stage-code change and
  the (Phase-2.5-validated) g1 profile.

### Phase 4 - Full automated integration + ergonomics (IN SCOPE - auto-intake confirmed on)
End-to-end brief -> 0.Originals -> (auto `intake --all` with slug recovery) ->
first_pass -> g1 -> stages, in one invocation. Add an `lw_gen` view to `lw_monitor` +
facts to `lw_facts`; `briefs/` per-champion presets; `--resume` to re-QA an existing
scratch batch; a `gen://`-source publish-filter guarantee; ComfyUI-graph fallback docs
if inpaint/ControlNet is ever wanted.
ACCEPTANCE:
- A single command yields a 2560x1440 wallpaper at 8.End Review awaiting the human
  pass; monitor/facts surface generated-vs-scraped provenance; the human 8.End Review
  remains the only manual gate; slug recovery (not reconstruction) is proven in an
  automated run.

--------------------------------------------------------------------------------

## 9. RISKS, LICENSING/IP, OPEN QUESTIONS

### Risks (ranked by real bindingness, corrected from the plan-of-record)
1. ART-STYLE MISMATCH (the true binding quality risk). An anime finetune produces
   wrong-style art that CLIP happily passes. Mitigation: painterly/semi-realistic SDXL
   finetune chosen BY EYE in Phase 0; anime excluded in the negative prompt; a
   style-fidelity acceptance gate in Phase 0. Fix BEFORE any sidecar code.
2. CLIP QA FOUNDATION DOES NOT IMPORT TODAY. `pyiqa clipiqa` fails (setuptools>=70.2
   removed `pkg_resources.packaging`); open_clip absent. Mitigation: install
   open-clip-torch fresh, budget ~1.5-2GB. Fix BEFORE writing the QA gate.
3. REAL FREE VRAM ~9.5GB, NOT 12GB, on a shared box (desktop baseline ~2.3GB + RC /
   League / vision / OBS). Mitigation: cpu-offload + tiled VAE decode are DEFAULT (not
   fallback); HARD-GATE gen off when RC/League/vision is live (operator-confirmed
   2026-07-06 - RC health probe wired into lw_gen_run at Phase 1, auto-refuse); measure
   peak with the real desktop resident in Phase 0. Fix BEFORE relying on the fast path.
4. INTAKE CONTRACT MECHANICS: MIN_AGE_SECONDS=10 skip, unpredictable post-intake slug,
   annotate-needs-manifest ordering. Mitigation: promote does not inline intake/
   annotate; operator (or Phase 4) runs `intake --all` and the slug is RECOVERED from
   stdout, never reconstructed. Fix BEFORE promote.
5. FIDELITY-GATE CALIBRATION: g1 floors were tuned on scraped sources. Mitigation:
   Phase 2.5 calibration batch + a `gen://`-keyed threshold profile if needed. Fix
   BEFORE claiming the gate is unchanged.
6. ULTRAWIDE UNSUPPORTED: pipeline is hardcoded 16:9. Mitigation: 16:9-only MVP;
   ultrawide is a separate multi-target refactor, deferred (open question below).
7. laplacian_var reuse is a primitive, not a drop-in floor: needs its own no-ref
   calibration (Phase 2). Minor but do not claim "reuse verbatim."
8. Blackwell attention/env gotchas: use SDPA (no xformers), set TORCH_CUDA_ARCH_LIST /
   CUDA_MODULE_LOADING, avoid CUDA_VISIBLE_DEVICES=-1. Fix in the launcher.
9. THROUGHPUT for a solo op: n=4 + max_regen_rounds=1 defaults keep a failing brief to
   a few minutes of GPU, not 8-16. Auto-regen is opt-in.
10. os.replace transient WinError 5 on the 0.Originals write under concurrent pipeline
    read: use the repo's own primitive + a LOCAL retry (do not import a Riot Commander
    convention that does not exist in this repo).

### Licensing / IP
- Record the EXACT model + version + license in a tracked `docs/GEN_MODELS.md` line
  BEFORE download, not "confirmed later." SDXL finetunes ship under varied terms
  (CreativeML-OpenRAIL-M, Fair-AI-Public-License, or custom); confirm the specific
  checkpoint permits personal-use image generation.
- Output is personal, solo, non-distributed fan-art. Riot's Legal Jibber Jabber
  permits non-commercial fan creations but PROHIBITS distribution/sale and any implied
  Riot endorsement. Concrete guarantees baked into the design:
  (a) `docs/GEN_MODELS.md` with model/version/license/date before Phase-0 download;
  (b) generated-origin images are personal-use only - NEVER uploaded to the DeviantArt
  recovery corpus, sold, or redistributed;
  (c) the `gen://lw-gen/<batch-id>` source_url is ALWAYS set so any future publish path
  can filter generated images out.
- Model weights stay gitignored regardless (matches `images/**` + `.venv-*`
  discipline: the PROCESS is shareable and tracked, the heavy binaries never are).

### OPERATOR DECISIONS (answered 2026-07-06 - LOCKED, no longer open)
1. Ultrawide (3440x1440): NO. 16:9-only MVP stands. Ultrawide stays OUT of this sidecar
   (it would be a separate multi-target pipeline refactor).
2. Model class: UNDECIDED - Phase 0 tries BOTH (photoreal finetune Juggernaut/RealVis
   class AND base SDXL + splash-art LoRA), pick by eye vs real 0.Originals. No pre-steer.
3. Hard-gate when RC/League live: YES, HARD-GATE (auto-refuse). Wiring the RC health
   probe into lw_gen_run is a PHASE-1 build requirement (not a deferred knob): if RC /
   League / vision is live, the generator refuses to start. See risk #3.
4. Auto-intake: ON. The Phase-4 sidecar runs `intake --all` itself (>10s age wait + slug
   RECOVERY from stdout, never reconstruction). Phase 4 is IN SCOPE, not optional.
5. MVP style set: UNDECIDED, leaning SPLASH-first. Build splash as the primary MVP style;
   portrait / landscape-ambient are fast-follows once splash quality is proven by eye.

### ASCII hygiene
All new .py / .json / .md authored 7-bit ASCII (no em/en-dash, no smart quotes),
matching the repo's precommit hygiene lineage.

--------------------------------------------------------------------------------

## 10. NET-NEW vs REUSED (at a glance)

- NET-NEW code: `tools/lw_gen_run.py`, `tools/lw_gen_qa.py`, `tools/lw_gen_promote.py`,
  `tools/lw_gen_styles.json`, `tools/lw_gen_config.json`, `briefs/*.json`,
  `docs/GEN_MODELS.md`.
- NET-NEW dep: `open-clip-torch` in .venv-metrics (the existing CLIP is broken).
- REUSED: `lw_pipeline.py` (slugify / intake / annotate / finalize),
  `lw_g1_gate.py` (laplacian_var primitive), `lw_upscale.py` (DAT2 4x, invoked by
  first_pass), `.venv-metrics`, `.venv-upscale`.
- UNTOUCHED: stages 1-9 pipeline logic and the human 8.End Review gate.

--------------------------------------------------------------------------------

## APPENDIX - cited source lines (verified live against C:\LegionWallpaper)

- `tools/lw_pipeline.py`: slugify (L129), cmd_intake (L626) + MIN_AGE_SECONDS (L67) +
  PROBE_SECONDS, eligibility_reason "modified too recently" (L609-623), unique_slug
  collision suffix (L580-595), cmd_annotate find_scratch->find_done->backup (L1129-1155),
  _analyze_folder / UNPARSED_FILE (L346), Ops.write_json bare os.replace (L192),
  Ops.safe_copy copy+fsync+SHA256 (L194).
- `tools/lw_g1_gate.py`: laplacian_var (L165), fr_metrics default
  psnr/ssim/ms_ssim/lpips/dists (L375-392).
- `tools/lw_first_pass.py`: TARGET=(2560,1440) 16:9 hardcoded (L71), _finish raises on
  non-16:9 (L15-16), STEP 3 calls lw_upscale.first_pass (DAT2 IllustrationJaNai V3),
  downscale-only Lanczos path with invalid lap_ratio (L225-227).
- `tools/lw_upscale.py`: _tile_infer tile=512 (L122), tuned to the 12GB ceiling.
- `.venv-metrics`: `pyiqa.create_metric('clipiqa')` fails
  (ImportError pkg_resources.packaging); open_clip absent - QA foundation is BROKEN
  until open-clip-torch is installed.
- Runtime: torch 2.11.0+cu128, cuda 12.8, get_device_capability()==(12,0), RTX 5070,
  12227 MiB total, ~9612 MiB free at probe (~2332 MiB desktop baseline), driver 610.62.

Sources consulted: diffusers Blackwell issue #13680 (sm_120 not auto-detected;
TORCH_CUDA_ARCH_LIST / CUDA_MODULE_LOADING; xformers gap); RTX 5070 SDXL/Flux 12GB
notes; Illustrious vs Animagine finetune comparison (booru-tag anime aesthetic).
