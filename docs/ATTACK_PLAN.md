# ATTACK PLAN - next 2-4 weeks (authored 2026-07-16, Fable 5, playbook P1)

Evidence-grounded leap plan. Ranked by throughput-unblocked-per-effort.
Ground truth at authoring (pipeline_state.json 2026-07-16T22:15:34Z):
first_done=207, clean_scratch=21, clean_done=0, final/last/end_review=0,
passed=8. NOTHING has ever flowed past Stage 2. Stage 3/4/5 tooling ABSENT
(no lw_final_pass.py / lw_last_pass.py / lw_end_review.py; ComfyUI + anime
face detector not on disk; G3 vision key absent). Stage-2 auto-clean SOLVED
in principle (LEDGER 30, lw_clean_iopaint): triage 9 CLEAN-AUTO / 7 PARTIAL /
2 MANUAL of 18 (+3 gate-FP KEEPs = the 21). Supervisor/runtime unwritten and
operator-gated (ROADMAP task-registration item). 16 loose files sat in
0.Originals at 22:58 probe.

## Item 1 - Close Stage-2 to zero (drain the 21, open the 190)

- Goal: every clean_scratch slug dispositioned: auto-cleaned + submitted to
  needauth, or routed MANUAL; then clean-scan the 190 clean firstdones so the
  full corpus watermark state is known.
- Steps: land the 3 pass-improvements from docs/research/IOPAINT_TRIAGE.md
  (full-width banner band; chroma-thr default ~12; namakx template-mask or
  adaptive dark_thr) -> clears ~6 of 7 PARTIALs; re-run worker over CLEAN-AUTO
  9 + cleared PARTIALs -> save-working --tool iopaint + submit needauth;
  route fantasy-design + prestige-coven-xayah (+ fury-sona if fidelity
  demands) to the manual IOPaint lane; then batch clean-scan the 190.
- Acceptance: clean_scratch contains ONLY manual-lane slugs; needauth queue
  holds the auto-cleaned set; clean-scan report for 190 committed; every
  auto-clean passes the outside-mask identity assertion (OUTSIDE_SSIM_MIN).
- Tier: 1 (lw_clean_iopaint.py module changes + batch runs); gate/threshold
  edits classify up to 2 only if the gate contract changes.
- Model plan: Opus 4.8 main thread; sonnet subagents for batch-run babysitting
  + per-slug verdict tables. Est: 1-2 sessions.
- Non-goals: NO Dekel rework (capped, parked - Settled); NO cluster/matte
  path repair (known broken, separate later item); NO new engines.

## Item 2 - Stage-3 final pass MVP (unblock the entire downstream pipe)

- Goal: lw_final_pass.py exists and moves images 4.Cleaning Done ->
  6.Final Done: debanding + exact 2560x1440 conformance + G1/G2 gate re-run.
  Use the spec's own fallback: face/eye repair SKIPPED when ComfyUI absent
  (record "face-repair skipped" in manifest) - pure-Python MVP, zero new
  heavy dependencies.
- Acceptance: TDD suite for conformance math + gate wiring; >=5 real images
  flow cleaning_done -> final_done with manifests + PIPELINE_LOG entries;
  G1/G2 pass or explainable FLAG on each; no upscale added (single-upscale
  contract holds).
- Tier: 2 (new pipeline stage engine; full suite + restart-equivalent checks).
- Model plan: Opus 4.8 orchestrator; worktree build agents on disjoint files
  (engine / tests / command doc), verifier gate before merge. Est: 2 sessions.
- Non-goals: NO ComfyUI install this item; NO CodeFormer/GFPGAN ever on
  illustrations (contract); NO aspect-crop policy invention (separate ADR if
  needed).

## Item 3 - Stage-4/5 minimal rail: first images DELIVERED end-to-end

- Goal: last-pass regression script (fresh-eyes re-gate vs all milestones,
  revert-only) + end-review finalize path (G3 vision-audit recorded SKIPPED
  while no Anthropic key configured, per spec fallback). First 5-milestone
  set reaches 9.Image Backup + approved 2560x1440 PNG in Pictures.
- Acceptance: >=5 images finalized live (PIPELINE_LOG FINALIZE entries +
  files in backup + Pictures); END-TO-END pipe demonstrated 0.Originals ->
  delivered; regression path proven by forcing one deliberate FAIL -> demote
  to 7.Last Scratch with reason.
- Tier: 2. Model plan: Opus 4.8 + worktree agents + verifier. Est: 1-2
  sessions after Item 2.
- Non-goals: NO --deliver automation without operator gate (contract); NO
  supervisor dependency (stays operator-driven).

## Item 4 - Corpus throughput housekeeping (cheap, parallelizable)

- Goal: intake the 16 loose 0.Originals; work the manual re-source queue
  (xayah1/camille1/kaisa1/fiora1 Battle Academia) + corpus-crop-redo trio
  (#115 Hwei / #247 Shyvana / #253 Soraka) per ROADMAP.
- Acceptance: 0.Originals empty; per-slug PIPELINE_LOG entries; re-sourced
  images intaken or explicitly parked with reason.
- Tier: 0-1 (existing tooling, batch ops). Model plan: single Opus session,
  sonnet subagents per batch; can interleave with Item 1 waits. Est: 1
  session.
- Non-goals: no tooling changes.

## Item 5 - Aspect-conformance policy (decision before code)

- Goal: settle the non-16:9 fullview gap (33/67 tier-1 fullviews non-16:9,
  memory project-first-pass-recipe-validated) with an ADR: crop grammar vs
  outpaint vs per-image operator call. Then wire the chosen rule into the
  Stage-3 conformance step (Item 2 consumes the decision).
- Acceptance: ADR-007 committed with the rule + 3 worked examples; Item 2
  implements it; no image silently stretched (hard rule).
- Tier: decision = docs; implementation rides Item 2 (Tier 2).
- Model plan: Fable/Opus single judgment session, evidence subagents. Est:
  0.5 session. Non-goals: no new generation/outpaint engine build this item.

## Explicitly NOT in this plan

- Supervisor/runtime daemon + LW-* scheduled-task registration: operator-gated
  (ROADMAP), zero image-throughput yield today. Revisit after Item 3 proves
  the pipe.
- lw-gen weapon quality: PARKED at ceiling (LEDGER 26, Settled).
- Dekel improvements + cluster/matte repair: parked R&D (LEDGER 29).
- Monitor thumbnails: dormant lane, cosmetic.

## Sequence

Item 1 -> Item 2 (Item 5 decision slots before Item 2's conformance step;
Item 4 interleaves anywhere) -> Item 3 -> re-plan from delivered-image reality.
