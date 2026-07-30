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

---

## 2026-07-29 (session end) - 20 intaken, waterfall run, sub-shape B ruled

Commit `152d84f`. Detail: LEDGER 59. Suite 835 passed / 14 skipped, ruff clean,
drift gate 0, CI success on the full head sha.

- **20 originals intaken.** `0.Originals` EMPTY, 20 slugs in `1.First Pass
  Scratch`, `anomalies=0`. Verified by a rebuilt scan + directory count, not the
  CLI tally. NEXT for this batch is `/first-pass` (ROADMAP `batch20-first-pass`).
- **The recovery waterfall RAN** (the 46 refs skipped it). T0 `no_match` 20/20 vs
  the 292-file corpus - all novel. T1 fetched 20/20 QUOTA-FREE; T2 never needed.
  8 gained pixels (best 1159x689 -> 1920x1142), 12 held pixels and shed 6-7x of
  JPEG compression. Do NOT use `original=true` - the intermediary path already
  measured a gain and costs no quota.
- **Memory corrected:** `reference-deviantart-recovery` claimed quota-free
  recovery "buys little". Measured false. It is now a run-it-inline-always rule.
- **This batch DOES exercise the AI upscaler** - 12 are 1024-1600px wide, unlike
  the 46 refs which were all exactly 2560x1440 and took the passthrough branch.
- **Sub-shape B RULED: accept and record.** 10 of the 15 alpha slugs cleared for
  stage-2 cleaning, no reopen dance. Sub-shape A's 5 (`258-cleanup` `259f` `261f`
  `262f` `264-cleanup`) STILL HELD - cleaning writes on top of `_firstdone`.
- **Two defects FILED, not patched** - do not re-diagnose: `lw_recover`
  `_ARTIST_RE` mis-parses a hyphenated DA username (false `dead`, fetch path
  unaffected); `lw_first_pass.find_fetched_fullview` globs `.jpg` only so a PNG
  intermediary is skipped (cost zero this batch). Both have ROADMAP items.
- `style.jpg` + `style2.jpg` now tracked (lw-gen style refs, repo root).
