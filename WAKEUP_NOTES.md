# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session (pruned 2026-07-11) - keep the last 3.

---

# 2026-07-11 (GOLDEN DEFINITION shipped: rubric v1.1 + full corpus deep dive + iterative path)

Fable-5 ultraplan session (4 workflows, ~100 agents, all adversarially verified /
spot-audited FAITHFUL). Deliverables all committed:

**docs/research/GOLDEN_DEFINITION.md REWRITTEN** = rubric v1.1 (12-element table w/
severity + addressability + stage-field scorecard), golden bar (7 conditions + stop
condition n>=3 GOLD from 2 batches), M0-M4 orchestrator spec, QA fix plan. Full pass
designs + 10 adversarial verdicts: docs/research/golden_designs/ (weapon, face_hands,
finish, qa_fix, rubric + VERDICTS.md).

**Corpus deep dive (operator-directed):** ALL 179 firstdone + 273 reference_pictures
reviewed at full res (6 imgs/agent); pHash correlation 19 exact pairs (Tier-0 rule,
scratch correlate via tools/lw_recover). Artifacts: docs/research/corpus/ (notes JSONs,
audits, CORPUS_PREMISE.md, CORPUS_ANCHORS.md, ref_correlation.json).
Key findings: anime-flat = 1.6 pct niche of operator taste (all 9 Vayne 5s are
painterly-semireal; nearest reachable band = anime-painterly-hybrid); corpus-sanctioned
WEAPON DODGE LANE (wing-rig/folded/blur/absent - 7 of 9 Vayne 5s dodge); focal-face
quality = highest-leverage axis; hands always gloved/hidden; generated text/watermark =
auto-reject; scale anchored 1-5 (min promotion bar = 3).
Engine fact verified: _extract_pose discards keypoints (lw_gen_run.py:413); M0 fixes.

**BLOCKING on operator:** (1) GOLDEN_DEFINITION.md sec 6 Q1-Q4 (glasses shape, style
band steer, dodge-lane ratify, scorecard adopt); (2) champion labels -
docs/research/corpus/CHAMPION_UNKNOWNS.md (78 true unknowns + 44 hedged, numbered,
reply "N = champ"; backfill into notes JSONs on receipt).
**NEXT session:** M0 foundations (config Animagine flip + tests, tools/lw_gen_pose.py
+ recall gate, manifest cand[file] contract, plan B), then M1 weapon pass.
ops/budget_saver/ = operator lean-config experiment, left untracked.

---

# 2026-07-11 (lw-gen QA-floor CALIBRATION + recipe v2 sweep; golden-definition seeded)

Shipped commit 2894e0b (QA floors calibrated on a real Vayne sweep) + a docs sync
(this /done). See LEDGER 16.

**QA floors calibrated (DONE - do not redo):** measured real ClipScorer scores;
set T_subj 0.26 / T_margin 0.05->0.045 / T_blur 100->150 / T_aes 0.45 (kept, but
T_aes is a NON-DISCRIMINATIVE no-op - everything scores 0.500-0.504). 6/6 good PASS,
misses REJECT. gen suite 67/67 green.

**Recipe v2 (operator-in-the-loop sweep, DONE - do not redo the sweep):**
controlnet_scale tight (1.10) OUT, loose-mid (0.35-0.55) wins; POSE SOURCE is the
lever (curated skel_01 leap >> default crouch; `_extract_pose` shares ONE skeleton
per batch - pose variety still needs the deferred cycling feature); fixed a
156-vs-77-token prompt truncation (Animagine quality tags were being cut); feminine
cues + male/androgynous negatives fixed a male-read; clean-DoF prompt killed FX
chaos. Recipe v2 strings: `images/_gen_scratch/exp3_clean/index.json`.

**Plateau + gate finding:** raw single-pass SDXL tops out at "good fan splash", not
golden. Operator accepted seed22 which the gate WRONGLY rejected as blurry - global
lap_var is confounded by DoF; needs a subject/face-region sharpness fix in
`tools/lw_gen_qa.py` (deferred).

**NEXT (operator directive):** fable-5 ultraplan + adversarial FULL-RES review ->
develop the golden rubric from `docs/research/GOLDEN_DEFINITION.md` (operator seed
critique + failure taxonomy; WEAPON is the #1 blocker). Iterative passes, not
superficial. Accepted refs: exp3_clean/seed22+seed33, exp4_volume/seed800,
proto/cand_01+cand_02 (all in `images/_gen_scratch/`, full-res).

---

# 2026-07-11 (lw-gen GENERATOR SIDECAR built + provisioned + Phase-0 proven; then DEEP-RESEARCH RETUNE pivot - HEADLESS)

New sidecar `lw-gen` (generate LoL-champion splash wallpapers -> subject-QA gate
-> feed 0.Originals). Commits: b2fc3a2 (sidecar run/qa/promote + /generate +
67 CI-safe tests), 7d6a3ca (Phase-0 provision + live proof), 5aec00d (subject-LoRA
loading hook + --lora-path/--no-lora).

**Proven live - DO NOT REDO:** `.venv-gen` (torch 2.11 cu128 + diffusers 0.39 +
peft 0.19 + tensorboard); open-clip `ViT-L-14-quickgelu` QA in `.venv-metrics`
(plain ViT-L-14 mismatches - MUST be quickgelu); RealVisXL V5.0 fp16 base
(`tools/models/RealVisXL_V5.0/`, sha in docs/GEN_MODELS.md) + its diffusers-format
copy `tools/models/realvisxl5_diffusers/`; sm_120 (12,0) gen ~3.4 it/s; the ddragon
splash-fetcher (chroma-filter + pHash-dedupe, scratchpad `fetch_splashes.py`);
SDXL LoRA training runs (diffusers `train_dreambooth_lora_sdxl.py` v0.39.0-matched,
UNet-only rank16 1500 steps ~23 min, fits 1024px in 11GB) - but rank16/1500
OVERFIT+blurred. rc_live gate lists ONLY the game/client (NOT RiotClientServices/
Vanguard - those are idle non-GPU). Loader uses `StableDiffusionXLPipeline.from_single_file`
(AutoPipeline has no from_single_file).

**PIVOT (operator, headless):** first gen results REJECTED - non-canonical faces,
broken fingers/hands, too photoreal (RealVis wrong feel), uncanny valley. New
mandate: UNLIMITED DEEP-RESEARCH ULTRA. Mine ALL `2.First Pass Done` (179 imgs,
70 champs; `firstdone_by_champ.json`) + official ddragon skins to build per-champion
+ general-style ARCHETYPES, retune against them. Acceptance = SIMILARITY to real
first-pass-done + official base/extra skins AND artifact/uncanny-free (detect bad
hands/faces). **Next champion = VAYNE** (6 curated firstdone + 19 official splashes
in `tools/models/lora_datasets/vayne/`). Baseline RealVis already recognizes KNOWN
champs well (Ahri baseline QA 4/4) - subject gap is for NEW champs (Ambessa).

**RETUNE - WINNING RECIPE LOCKED (full journey + rubric in docs/research/GEN_RETUNE.md):**
Deep-research workflow wbnpch0uo (archetypes) + posing research -> iterated through
RealVis-painterly (fixed too-photoreal), img2img-from-real (fixed palette/pose but BLURRED
faces - rejected), to the FINAL recipe. Commits this session: cc2875a e35ea14 f67c8f4
065679b e7f98ea d77dbe2 8e30892 f0ac578.
- **WINNING RECIPE = Animagine XL 4.0 (anime base) + ControlNet-OpenPose (skeleton from a
  real splash) + cowboy-shot detail-tag booru prompt.** Operator directed anime-flat
  (overriding the anime ban) + flagged mangled glasses / odd faces / blotchy-blur / bad hands.
  Animagine KNOWS champions from booru data (Vayne: clean red glasses, dual crossbows,
  ponytail, navy+red) + clean anime faces. ControlNet-OpenPose (xinsir SDXL, controlnet_aux
  OpenposeDetector hand_and_face) transplants a real natural pose + pins hand chirality (kills
  the mirrored 2nd-left-hand) while keeping SHARP txt2img detail (no img2img blur).
  Batch vayne-controlnet-tuned = production quality, hits the operator bar.
- Integrated first-class in lw_gen_run: `--model-path` (base override), `--controlnet-pose
  <ref>` / `--controlnet-scale` (config controlnet_openpose_path), `--lora-path`/`--no-lora`,
  `--init-image`/`--img2img-strength`. Style `splash-booru` (posing+detail vocab, lean
  negatives). Brief briefs/vayne_animagine.json. 67 gen tests green, CI-safe (lazy imports).
- Provisioned + gitignored (tools/models/): RealVisXL_V5.0, animagine-xl-4.0-opt.safetensors,
  controlnet-openpose-sdxl (xinsir), lora_datasets/{vayne,ahri} (ddragon fetch), yolo/ (unused
  - hand DETECTION is a dead end on painted hands, do NOT build detect-repair). .venv-gen has
  torch2.11cu128 + diffusers0.39 + peft + controlnet_aux + ultralytics + tensorboard.
- DO NOT REDO: the base/model choices, ControlNet integration, the img2img/anime exploration (settled),
  hand-detection repair (dead end). Full recipe + rejected paths in docs/research/GEN_RETUNE.md.
- **NEXT = THRESHOLD ITERATION (operator, new session):** dial in the knobs on the winning
  recipe - controlnet_scale (0.75), img2img_strength, cfg/steps, and the QA floors in
  lw_gen_config.json qa{} (T_subj .26 / T_margin .05 / T_aes .45 / T_blur 100.0). Also
  per-candidate skeleton cycling (pose variety in one batch), then a full QA+promote pass.

**Continuity/headless:** full authority, commit+push on green. Self-continue across
sessions via Gemini + AHK (`gemini-headless-upgrade` skill) targeting THIS window
(named **"Image"**). State lives on disk (git + this file + docs/LEDGER.md + memory
`project-lw-gen-deep-research`).

