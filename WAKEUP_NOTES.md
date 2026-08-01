# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18), and the 2026-07-27 loop-cycle-11 alpha-audit session (pruned 2026-07-29) - keep the last 3.

---

## 2026-08-01 - the loop was wedged for five days; run dashboard shipped

Detail: LEDGER 62. Suite 1178 -> **1346 passed / 16 skipped / 0 failed**, ruff
clean, drift 0 breaches, CI green. HEAD `7879af2`, 14 commits. Six worktree
slices, all verifier-gated; two REFUTED and reworked rather than merged.

- **THE PRIORITY NEXT SESSION, operator-directed 2026-08-01: DRAIN STAGE 2.**
  Merge B5/B6 first (below) since they are cheap and already committed, then
  spend the session on the product rather than more infrastructure.
  **Nothing has EVER flowed past Stage 2** - `clean_scratch: 21, clean_done: 0`,
  unchanged since the attack plan was written 2026-07-16. Everything shipped on
  2026-08-01 was infrastructure.
  The work is already triaged in `docs/research/IOPAINT_TRIAGE.md`:
  **CLEAN-AUTO 9 | PARTIAL 7 | MANUAL 2** (+3 gate-FP KEEPs = the 21). Three
  PARTIAL fixes are already CONFIRMED in that doc and just need landing:
  `--chroma-thr 12` clears `spirit-blossom-ahri-mono-01`; a full-width banner
  band `(860,958,1720,1035)` + chroma clears `viego-...slimshadywallpaper`;
  widen region right + chroma clears `aidraw-...watercolornessie`. That takes
  PARTIAL 7 -> 4.
  Route to the manual IOPaint lane, do not fight them: `fantasy-design-...aivio`
  (ornate filigree smeared) and `prestige-coven-xayah-...pebano1` (busy feathers,
  a KNOWN LaMa failure) - plus `fury-tempest-sona` if fidelity demands, since it
  has no residue but softens folds and gold trim.
  Then re-run the worker over CLEAN-AUTO 9 + the cleared PARTIALs ->
  `save-working --tool iopaint` -> `submit`. Acceptance: `3.Cleaning Scratch`
  holds ONLY manual-lane slugs and the needauth queue holds the auto-cleaned set.
  Tooling: `tools/lw_clean_iopaint.py`, venv `C:\Tools\lw-clean\venv`, ritual
  `.claude/commands/cleaning-pass.md`. HARD RULE: never inpaint without a mask,
  and every auto-clean must pass the outside-mask identity assertion.
  **Note this will be the FIRST real exercise of the GPU mutex** - B4 wired
  `lw_clean_iopaint` and `lw_clean_pass`, so a cleaning run now acquires
  `Global\LW_GPU` and will wait up to 1800s then raise `GpuBusy` if a sibling
  repo holds the card. If that fires, it is the guard working, not a bug.

- **ALSO OWED.** Two slices were IN FLIGHT when the session ended, both recorded
  `in_progress` in `ops/runtime/slice_manifest.json`:
  - **B5** persist verifier verdicts - **COMMITTED `d570d42` on branch
    `worktree-agent-a902870319ee6443d`, NOT verified and NOT merged.** Nothing
    to salvage; run the `verifier` subagent against it, then merge. It reports
    1340 passed / 16 skipped and a backfill of the live manifest. Note it also
    fixed the same flaky `status_age_s` bound that `7879af2` fixed on main, so
    expect a conflict in `tests/test_lw_rundash.py` and keep main's version.
    ROADMAP `rundash-instrumentation`.
  - **B6** wire the 3 remaining CUDA consumers - branch
    **COMMITTED `a76a05d` on branch `slice-b6-gpu-mutex-remaining`** - note that
    is NOT a `worktree-agent-*` name. Nothing to redo; verify then merge.
    It reports 1367 passed / 16 skipped and, critically, that **NO CUDA consumer
    in the tree is left unwired** - which is the answer RC and RM are waiting on.
    ROADMAP `gpu-mutex-inert` carries the constraints; read them first.
    It also CORRECTED a premise I gave it: `winmutex.hold`'s timeout bounds the
    WAIT TO ACQUIRE, not the hold duration (`winmutex.py:96-101`), so a long
    training run cannot time itself out and needs no bespoke constant.
- **Your headless loop could not start and had not been able to for five days.**
  `RUNNING.lock` named a pid recycled to an unrelated conhost. Fixed `e63a50d`.
  Do NOT re-investigate.
- **The shared lane cap stays at 2.** RC proposed 3 and Red Moon has already
  WRITTEN 3, so the bucket is 3 wide whenever RM acquires first - RM was asked to
  set it back today. LW cannot agree until B6 lands; 6 of 9 CUDA consumers are
  wired. Both siblings are waiting on that answer.
- **The run dashboard is live** at 127.0.0.1:8900 (`tools/lw_rundash.py`,
  `pythonw`, read-only). Every evidence chip reads NOT OBSERVED until B5 lands.
- **Do NOT collapse `lw_httpd.parse_ts` and `lw_rundash_state.parse_iso`.** First
  reads a naive stamp as UTC, second as LOCAL - 5 hours apart on this machine.
  `loop_controller.py:303` writes naive LOCAL, so `parse_iso` is correct.
- Inbox is clear: RC and RM both answered today. Port blocks settled three ways,
  `slots.py` confirmed byte-identical at `95077a62...5054f9`.

**Do-not-redo:** the recycled-pid fix; the `null`-evicts-cache fix; the DWPose
correction (it is onnx-CPU, not a GPU consumer); the port registry AST widening;
the flaky `time.time()` bound in `test_lw_rundash.py`.

---

## 2026-07-30 (headless run) - the halo flags are our own sharpening; batch20 is at NEEDAUTH

Detail: LEDGER 61. Suite 1093 -> **1169 passed / 16 skipped / 0 failed**, ruff
clean, CI green on every push. HEAD `34634b8`. Four worktree slices, every one
verifier-gated before merge; one was REFUTED and reworked rather than merged.

- **OWED, and it is yours: 17 batch20 slugs sit at NEEDAUTH.** 10 PASS, 7 FLAG,
  0 FAIL. Approve or reject via `lw_pipeline.py approve|reject <slug>` -
  approval is operator-only by design. 3 more are HELD on `aspect_crop_heavy`
  (~0.156 area loss vs the 0.08 cap): `puppet-master-syndra` and both
  `spirit-blossom-vayne` slugs. Crop policy is product direction; NOT decided
  unattended.
- **Read this before you approve the 7 flagged ones.** All 7 flags are the same
  reason - `halo_pct` over 0.05 - and the census says the mask we apply is what
  makes it. Skip the USM: max `halo_pct` 0.1196 -> **0.0062**, 0 of 17 over the
  line, so the upscaler is not the source and ADR-004 is not implicated. But
  with no mask **6 of the 16 gated slugs fall through `lap_ratio`'s 1.0 HARD
  FAIL floor**. usm35 clears every halo flag with the weakest gated `lap_ratio`
  at 1.1399; usm50 leaves 2. Nothing was changed - see ROADMAP
  `usm-halo-calibration`, evidence `docs/USM_HALO_CENSUS_2026-07-30.md`.
- **Do NOT pick a USM percent or a threshold on the halo numbers alone.** The
  census deliberately did not recompute ms_ssim/lpips/dists per variant, so the
  fidelity cost of a milder mask is UNMEASURED. Measuring that is the next
  cheap slice, and it is what makes the decision safe. A one-axis threshold pick
  is what got the anatomy gate rejected on 2026-07-29.
- **A ROADMAP premise was wrong and is now corrected.** `parse_artist` did not
  capture `wallpaperart` for a hyphenated DeviantArt username - it returned
  `None`; the character class cannot cross an underscore. One root cause, not
  two. A non-200 oEmbed is now `inconclusive`, never `dead`.
- **A verifier stopped a false claim from merging.** The first-pass slice
  asserted single-extension dirs keep the old `sorted()[0]` winner; they do not
  when names differ in case. Behavior was fine, the claim was untested. An
  unasserted claim is not a green slice.
- Approvals now record `gate_check` as `pass` / `override` / `no_audit`, so an
  approval over a FAIL is greppable. The 12 legacy manifests were NOT
  backfilled - mutating approved data is your call.
- Closed with no commit: `.venv-gen` had no `pytest`, so the anatomy probe's
  capability-gated real-model test could never run. Installed; 51 pass there.

**Do-not-redo:** `original: true` on DeviantArt (weekly quota); re-intaking a
fetched fullview through `0.Originals`; proposing a halo threshold or USM
percent as final on the halo axis alone; a different upscaler model (ADR-004 is
settled and the census exonerates it).

---

## 2026-07-29 (headless run) - nightly red fixed; the anatomy gate MEASURED AND REJECTED

Detail: LEDGER 60. Suite 835 -> **1093 passed / 16 skipped / 0 failed**, ruff
clean, drift guard 0 breaches, CI green. Five slices merged, all verified against
ground truth rather than on an agent's word.

- **The nightly CI red is fixed and PROVEN, not just locally green.** The
  gate-arming step existed only in the `check` job, never in `nightly-full-suite` -
  ROADMAP's f1-phase6 item (6) was marked DONE but covered one job of two. Shipped
  as a workflow-parity guard so a third job cannot regress it. I mutation-tested the
  guard (removing the arming fails 3 of its 4 tests) and proved the fix on the real
  runner via `workflow_dispatch` `30509939447` - both jobs green. **A guard that
  passes is not a guard that works; test it by breaking the thing it guards.**
- **The operator's fiora1 note produced a negative result, and that IS the
  deliverable.** G1 is a FIDELITY gate, so a defect INHERENT TO THE SOURCE scores
  near 1.0 - fiora1 passed at `ms_ssim 0.997113` with zero reasons. I built the
  head-spine metric, measured it over all 288 approved firstdones, and the census
  refuted gating it: fiora1 sits at the **43.5th percentile**, BELOW median badness,
  so any threshold catching it flags over half an approved corpus. Ships as a
  diagnostic; `classify_head_spine` deleted outright. **The census is what stopped a
  plausible-looking gate from shipping - a threshold picked before measuring the
  corpus would have been a confound, exactly as the standing lesson says.**
- **60 percent of the corpus cannot be measured at all, and it is a FRAMING
  constraint.** 157-159 of the 173 unmeasurable images fail on HIP confidence
  because splash art is cropped at the waist. This rules out the obvious follow-up:
  a better pose model cannot find hips that are outside the crop.
- **I had to correct my own census.** "0 zero-figure detections" is what the code
  reports and it is misleading - `yolox_l` finds NO person box on 21 of 60 sampled
  images (35 percent), and `tools/dwpose_onnx/onnxpose.py:26` then silently
  substitutes the whole frame as the pose ROI. fiora1 is one of those, so its
  headline number came from a whole-frame fallback. **A fallback that makes failure
  look like success is worse than an error.**
- **I also shipped a WRONG premise to an agent and caught it.** I told the probe
  slice to reuse `cocowb_to_kp_map`; verifying the code myself showed it returns
  ANISOTROPICALLY normalized coords (`x/w, y/h`), drops confidence, and exposes no
  eyes/ears/hips. It would have sheared every measurement silently. Corrected
  mid-flight to the raw 133-keypoint pixel array.
- **The worktree phantom red was real and had a dangerous sibling.**
  `tools/install_git_hooks.py:75` derived the expected hooks dir from the WORKING
  TREE, so every linked worktree reported the tracked gate INERT while it was armed
  - three agents each burned time re-diagnosing it. The sweep found the actual
  hazard: the installer's `main()` would have REWRITTEN the shared
  `core.hooksPath`, mutating the main checkout. Verified live it is unmutated.
  Fixed with an anti-rubber-stamp test that makes a real worktree commit with a
  banned glyph and asserts it is blocked.
- **A second, bigger blind spot found by chasing the same root cause - NOT acted
  on.** 105 of 276 approved images came from sources below 2560x1440 (worst:
  800x450, a 3.2x blowup, PASS); 12 have no G1 audit (legacy, backfill owed); 10 of
  those were built with the FALLBACK upscaler. Left as ROADMAP items because the
  threshold POLICY and the 10 reprocesses are operator calls - and because
  `APPROVE_FIRST` is an operator judgement by design.
- **Incident:** a session limit killed five agents at once mid-flight. Main checkout
  recovered clean on `main`; one dead agent's uncommitted files were salvaged from
  its worktree rather than rewritten; one slice's work was lost and re-dispatched.
  The manifest tooling built this same run (S2) is what makes that recoverable next
  time.

**NEXT:** three new ROADMAP items, all operator-gated -
`g1-source-adequacy` (policy call), `legacy-audit-backfill` (12 backfills + 10
reprocess decision), `anat-vision-review` (may a vision reviewer REJECT?).
