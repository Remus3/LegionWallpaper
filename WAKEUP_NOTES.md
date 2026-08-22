# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18), and the 2026-07-27 loop-cycle-11 alpha-audit session (pruned 2026-07-29), and the 2026-08-01 three-repo-N=3 / hook-rule-correction session (pruned 2026-08-01), and the 2026-08-01 (evening) Stage-2-drain / L1 / dashboard-spine session (pruned 2026-08-01), and the 2026-08-01 (night) dashboard-spec-completion session (pruned 2026-08-01), and the 2026-08-01 (earlier) P3/P4/P5 + wiki-swap session and the 2026-08-01 (late) MCP-list/P1 session (both pruned 2026-08-02), and the 2026-08-02 all-five-recommendations/USM-flip/watchdog session (pruned 2026-08-09), and the 2026-08-10/11 intake/retry-degrades session + the 2026-08-11 detector-precision/recall session + the 2026-08-11 (evening) centre-overlay-inpaint session (all three pruned 2026-08-12), and the 2026-08-12 faint-mark REMOVAL lane session (pruned 2026-08-12), and the 2026-08-12 (later) overlay-registration-SCALE session (pruned 2026-08-12), and the 2026-08-12 QA-lane precision-census session (pruned 2026-08-12), and the 2026-08-12 veil-ring session (pruned 2026-08-13), and the 2026-08-12 clean-retry-degrades/one-engine session + the 2026-08-12 bare-pytest-wrong-tree session (both pruned 2026-08-16) - keep the last 3.

---

## 2026-08-22 (latest) - cleaning: fill solved, detection open, bar set to ZERO

Long operator-driven session. Two halves of the cleaning problem separated by
measurement, and the acceptance bar raised.

- **Disposed the 566-slug cleaning corpus gate-driven** (LEDGER 122): 460 clean
  approved, 19 of 20 auto inpainted, 87 held. `4.Cleaning Done` 6 -> 485.
- **Then the operator rejected ALL 87 automated candidates** over 4 review
  rounds (45 overlay filled, the same 45 un-filled, 40 region/faint/singleton,
  7 guard survivors). Zero accepted. Two real bugs of ours fell out: the 25%
  mask-coverage guard was gated on `faint` so the region lane repainted a median
  47.6% of its ROI, and 7 slugs were DETECTOR FALSE POSITIVES flagging in-art
  text (approved unedited; the "false positives are zero" claim is overturned).
- **The operator then hand-cleaned two slugs in IOPaint and captured all 128
  steps.** That is the ground truth everything below rests on.
  - per stroke: ~0.18% of frame (105) / 0.44% (107); LaMa changes ~12% of what
    is brushed in BOTH captures; stroke size scales INVERSELY with local
    gradient, exactly as the operator said.
  - the strokes are not a sweep: 30x overlap, median pixel brushed 19 times,
    median NEW area per stroke 3.0%, and 86% of convergence lands in the last 30
    of 82 steps as the mask grows 55x.
- **REPLAY of their masks through our fill: the operator PASSED it.** So the
  FILL was never the problem - every rejection was a mask failure.
- **Built the mask SCHEDULE** (residue -> contiguous run -> pad 5x -> tight crop
  -> commit): cleaned 105 from a derived footprint, DAMAGED 107 (worse than
  doing nothing) because its footprint covers real art.
- **Detection is the open problem and contrast is dead both ways:** absolute
  residue fires on art detail; relative residue (control-band calibrated) misses
  the mark entirely - it reports NO excess on frames that still carry the
  watermark, because a semi-transparent line is not busier than the art.
- **Template + schedule** (`tools/lw_clean_overlay_schedule.py`) is the best
  result: logo gone, art intact, credit line down to a faint ghost. Still FAILS
  the new bar.
- **NEW STANDARD:** zero watermark; ghost / banding / faint all fail. Next
  session runs five tracks in parallel, PRIMARY being a **healing-brush fill**
  (exemplar + gradient-domain Poisson blending, "like photoshops healing
  brush") - deterministic, no hallucination, preserves lines by construction.
  Plan: `docs/CLEAN_NEXT_SESSION_PLAN_2026-08-22.md`.
- **Do NOT redo:** lattice tiling of any kind (it signs its own boundaries into
  the result), blanket mask escalation (destroys art), absolute or relative
  contrast residue as a starting detector, and more LaMa fill variants before
  the healing brush is tried.

---

## 2026-08-22 - clean-566 disposed gate-driven, cleaning scratch 566 -> 87

Operator answered the standing block with shape (1) (gate-driven).

- **Shipped:** `tools/lw_clean_dispose.py` + `tests/test_lw_clean_dispose.py`
  (7 tests, TDD RED-first). The driver re-decides no verdict and moves no slug
  itself - every transition is an `lw_pipeline` subprocess, so ADR-008 / ADR-009
  refusals are RECORDED and skipped, never forced; approvals carry
  `--actor tool:auto-approve`.
- **Disposition:** triage regenerated read-only first and reproduced the
  2026-08-17 split EXACTLY (460 clean / 86 qa / 20 auto over 566). Then 460
  `clean` approved, 19 of 20 `auto` inpainted (simple-lama) + approved, 87 held.
  `4.Cleaning Done` 6 -> 485, `3.Cleaning Scratch` 566 -> 87, needs_attention 0.
- **`259f`** is the 20th auto: inpainted, FAILED the G2 verify gate, fell to the
  QA queue. That is the gate working - do not "fix" it by relaxing verify.
- **Held set** with per-slug reason: `docs/cleaning_qa_queue_2026-08-22.md`
  (45 centre_overlay / 27 not_border / 12 faint_mark / 3 singletons).
- **OPEN:** the operator's 13 named `ref_*` slugs are recorded NOWHERE in the
  repo; the gate held 9 as `qa`, the other 4 were approved with the clean bucket.
  Reopen route if named: `save-working --tool operator-select` -> submit ->
  approve (no reverse stage transition exists).
- **Do NOT redo:** the disposition is not idempotent - an already-moved slug
  fails `save-working` with `not in any scratch`, which is the intended refusal.

---

## 2026-08-17 - corpus drained to cleaning, Pictures 1:1, two console-flash fixes

Operator-driven session, mostly pipeline throughput plus three shipped fixes.

- **Shipped:** `2028026` first-pass directed-crop override (`--crop-overrides`,
  `anchored_crop_box`, named sides are a PERMISSION not a demand - horizontal
  grants on a too-tall frame are dropped); `6db5443` Done-N folder is now pruned
  AT the transition (supersedes the FM-02 retention half; verified per-slug
  before delete, `PRUNE_SKIPPED` on anything unproven); `d916f9a` +
  `690ffb7` two console-flash fixes - LW-CIWatchdog ran `python.exe` every 2 min
  (now `pythonw.exe` + Hidden), LW-WeeklyHygiene had no `-WindowStyle Hidden`.
  Suite 2058 passed / 18 skipped, ruff clean, CI green.
- **Pipeline:** intaked 243 (225 `ref_*` restaged from `reference_pictures` +
  18 new operator drops), first pass 242 PASS / 1 FAIL / 0 held, approved, all
  staged to cleaning. `3.Cleaning Scratch` = **566**, `first_done` = 0,
  `2.First Pass Done` fully drained by the new prune, 0 stale folders anywhere.
- **Pictures = 555**, deduped to 0 duplicate-content pairs and 0 slugs with two
  entries; every file is in the rotator deck, 0 orphans in the owed half.
- **BLOCKED ON OPERATOR:** cleaning triage is DONE (566 rows: 460 clean / 86 qa
  / 20 auto) but the destructive half was NOT run - awaiting the gate-driven vs
  blanket-approve call, and whether `qa` stops at scratch with the named 13.
- **Do NOT redo:** the 750px thumbnail `1000040081-...-375w-2x` FAIL is
  unfixable - DeviantArt's authoritative fetch returns the same 750x437 bytes.

---

## 2026-08-16 - face realism shipped, face-key overturned, deformity cause found

Commits `34d366a` `e132d00` `3f2b9bc` `b90b260` `ea05ef3`. LEDGER 116-120.

- **SHIPPED: the splash-booru face-realism block** (116). Register moved from
  0.153 BELOW the corpus ceiling to 0.011 below it, subject and margin both up,
  sharpness held. Two tokenizer facts drove it: `photorealistic, 3d render` were
  already INERT past the 77-token cut, and a naive insertion pushed
  `text, signature, watermark` out of the window (fixed by priority ordering).
- **OVERTURNED: the face-key result I reported** (119). I claimed 24/29 frames
  "in the corpus band"; the operator's frame-by-frame verdict was ~6 acceptable
  of 30. The band is NOT a quality gate. The operator named the mechanism
  ("mascara like black line, blowing out colors") and it measured out exactly -
  0.10-0.25 percent of each frame crushed to <= 8 levels, up to 113 levels of
  darkening on Katarina. Fixed: shading-only correction, bounded movement, and
  a zero-padding blur bug that biased the split. Per-champion bands replace the
  Ahri-only global target (corpus default +16.9, not +24.3).
- **CAUSE FOUND for the non-Ahri deformity** (120), nothing shipped: the POSE
  STACK is responsible, not the realism block, and **the base knows these
  champions** - a minimal prompt renders Miss Fortune canonical where the full
  style gave a deformed figure in generic leather. `official splash art` summons
  the splash title card and the text negative does not suppress it.
- **OPERATOR DIRECTION for next session:** go with `canon` (minimal positive +
  full protective negative) and try a text-specific negative to kill the title
  card.
- **Do NOT redo:** the base A/B (ADR-011 settled it), the face-key mechanism
  investigation (three defects fixed and pinned), or the realism-block
  attribution (exonerated by the norealism arm).

---

## 2026-08-16 - the base flip REVERSED; similarity cannot pick a base

LEDGER 115, ADR-011. Same day as ADR-010, and the reversal is the finding.

- **Operator inspected every candidate frame** from all three arms. Animagine
  holds League and corpus conventions on ALL of them. RealVisXL violates hand
  conventions, weapon/tool canon and facial likeness. DreamShaper violates the
  corpus look outright. Both are DROPPED as base candidates.
- **The measure ranked the two failing bases FIRST.** CLIP corpus similarity is
  global image statistics - register, palette, lighting - and is blind to hands,
  weapon canon and likeness. It is a MEASURE and never selects a base. Do not
  re-run a base A/B scored on it.
- **My by-eye read was the load-bearing error.** I called the animagine frame
  off-canon and the RealVis frame canonical from ONE frame each, conflating anime
  register with off-canon - the same error the metric makes, reported as if it
  corroborated the metric. Retracted in place in the evidence doc.
- **Kept because still right:** `tools/lw_gen_medium.py`, the diffusers-folder
  base loader, the gpu-mutex wiring, the weightless-checkout config pin fix.
- **NEXT (operator):** more-real faces ON animagine, not uncanny. Prompt /
  adapter / sampler on this base. Note the adapter ranking INVERTS on animagine
  (plus-face 0.5 best; general 0.3 worse than control), so nothing from the
  RealVis tuning transfers.
