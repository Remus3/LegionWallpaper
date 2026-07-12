# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11) - keep the last 3.

---

# 2026-07-11 (M1 localizer decision - DWPose onnx-CPU adopted, 5/6)

Shipped + pushed (commit 7e21c9d), full suite 387 passed / 3 skipped:
- **Spike outcome:** DWPose onnx-CPU ADOPTED as the M1 auto-suggestion localizer -
  5/6 wrist-on-weapon on the 6 recall_gate samples (seed22 / seed33 / seed800 /
  cand_01 / seed42 hit; cand_02 miss) vs OpenPose 1/6. Cleared the operator's >= 4/6 bar.
- **SDPose-Wholebody REJECTED (do NOT retry):** its pipeline hard-imports mmpose +
  pins mmcv==2.2.0 = the Blackwell / torch-2.11 wall (also torch 2.8 / transformers
  4.57 / xformers; 5.32GB). NOT drop-in as the handoff assumed. Operator approved the
  DWPose onnx download (351MB, fashn-ai HF mirror) instead.
- **Built:** tools/lw_gen_localizer_eval.py (detector-agnostic harness + cocowb_to_kp_map
  COCO-WholeBody-133 adapter + openpose/dwpose backends) feeding the REUSED
  weapon_roi_from_keypoints; tools/dwpose_onnx/ vendored onnx helpers (no mmcv). +7
  tests. Models gitignored (tools/models/dwpose). min_conf=0.3 (scores clean [0,1]).

**NEXT session:** wire dwpose_backend into lw_gen_run's real detect -> mask -> inpaint
path (operator-in-the-loop picks the weapon-side wrist -> kp_map -> weapon_roi_from_keypoints
-> inpaint + hard outside-mask identity assert + re-QA via cand[file]). Do NOT redo the
localizer spike, slices 1-2, or re-attempt SDPose. Still operator-blocked:
GOLDEN_DEFINITION.md sec 6 Q1-Q4.

---

# 2026-07-11 (M0 foundations + M1 weapon slices 1-2 + upstream-localizer exploration)

Shipped + pushed, all green (full suite 380 passed / 3 skipped):
- **M0 (a934243):** config Animagine flip (model_path -> the single-file
  animagine-xl-4.0-opt.safetensors; steps 28); tools/lw_gen_pose.py OpenPose helper;
  cand[file] contract (stage_filename / new_candidate_record / advance_cand_file +
  stage + provenance). Recall gate PASSED 6/6 (operator).
- **Corpus (7826b22 / e27054f / ba308ff):** all 122 champion labels applied
  (#32 -> Qiyana, #102 -> Zaahen); CHAMPION_ATTRIBUTED_330.md generated; operator's
  32 corrections backfilled into notes_*.json champion + is_vayne. CROP_REDO_QUEUE.md
  = #115 Hwei / #247 Shyvana / #253 Soraka.
- **M1 slices (693920f, e5bcdc5):** tools/lw_gen_weaponfix.py = pure
  weapon_roi_from_keypoints geometry + first-class fallbacks (+13) and the raw-pose
  -> COCO-18 kp_map adapter with anti-compaction lock (+7).

KEY PIVOT (empirical): weapon-mask contact sheet showed the geometry is SOUND but
OpenPose WRIST is unreliable on stylized art (1/4 auto-masks hit the weapon). CLIP
mask-validator DEAD; ControlNet skeleton-reuse NOT viable (drift, settled
VERDICTS.md); DWPose blocked (mmcv/Blackwell). Operator: in-the-loop regardless.

**NEXT session (operator-directed order):** M1 localizer - try **SDPose-Wholebody
FIRST** (github T-S-Liang/SDPose-OOD, HF teemosliang/SDPose-Wholebody) as the
auto-suggestion; acceptance = beat OpenPose 1/6, target >= 4/6 wrist-on-weapon on the
6 images/_gen_scratch/recall_gate/ samples. If it misses -> **DWPose onnxruntime-CPU
spike** same session (pip install onnxruntime + ~343MB: yolox_l.onnx +
dw-ll_ucoco_384.onnx; operator approves the download). If BOTH miss -> a SEPARATE
later session builds the **manual IOPaint lane**. REUSE tools/lw_gen_weaponfix.py -
do NOT rebuild slices 1-2. Do NOT redo: M0, corpus labeling, the CLIP + skeleton-reuse
dead-ends. Still operator-blocked: GOLDEN_DEFINITION.md sec 6 Q1-Q4.

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
