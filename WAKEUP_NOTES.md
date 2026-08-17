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

## 2026-08-17 (latest) - corpus drained to cleaning, Pictures 1:1, two console-flash fixes

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
