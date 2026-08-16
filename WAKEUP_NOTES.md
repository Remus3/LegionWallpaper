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

## 2026-08-16 (latest) - the base flip REVERSED; similarity cannot pick a base

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

---

## 2026-08-16 - the gen BASE study (ADR-010, reversed by ADR-011)

Commits `357b0a6` + the docs sync. LEDGER 114. The ROADMAP item asked for a base
decision; it got one, and the number it rests on is reproducible now.

- **The yardstick was recovered before it was used.** The 0.8373 real-vs-real
  ceiling in `docs/GEN_MODELS.md` had no recomputable definition - it lived in a
  dead scratchpad. `tools/lw_gen_medium.py` (TDD, 8 tests, torch-free import)
  re-derives it: mean pairwise CLIP ViT-L-14-quickgelu cosine over the 21 real
  Ahri splashes, **0.83732**. Landing on the recorded number is the validation.
- **Three-base A/B, matched seeds, adapter OFF, one fresh process per arm:**
  animagine **0.6843 (-0.153)**, RealVisXL **0.8609 (+0.024)**, DreamShaper XL
  **0.8448 (+0.008)**. RealVis also wins subject_cos 0.2892 / margin 0.0761 /
  3-of-3 QA. The shipped base was the ONLY arm below the ceiling and it cleared
  the subject floor while there.
- **DreamShaper XL had never been tried as a txt2img base** (on disk since
  2026-07-16 for cleaning). It needed a loader fix - `from_single_file` rejects a
  diffusers folder, and an fp16-only export needs `variant="fp16"` or
  from_pretrained silently builds an EMPTY module.
- **Operator ruled the flip** (one framed question - the metric is blind to the
  by-eye Vayne complaint that caused the 2026-07-11 move to animagine). ADR-010
  written, config flipped, **shipped default verified BY GENERATION before
  commit**: medium 0.8635 on fresh seeds.
- **The gpu-mutex guard caught my own gap** - `lw_gen_medium.encode_paths`
  touched cuda unheld. Wired and registered in `ACQUIRE_SITES`.
- **Do NOT read the flip as retiring the old complaint:** Ahri wears no glasses.
  The Vayne glasses case is untested on this recipe and is item (2) in the
  ROADMAP's next list.

---

## 2026-08-16 - IP-Adapter WINS where the LoRA lost

Six commits (`3cc6d8f` .. `f9f3ecd`). The untested lane flagged at the end of the
2026-08-15 session turned out to be the answer. LEDGER 107-113. Two of the six
commits are REVERTS recorded as findings, not failures - read 112 + 113 before
re-opening anything in this workstream.

- **A reference image carries identity; a trained per-champion LoRA did not.**
  Best scale **0.3**. Every adapter arm beats the no-adapter control on
  subject_cos, margin, CLIP-vs-real and luminance-vs-real.
- **The mechanism is the INVERSE of the LoRA's failure**, which is why this is
  believable rather than a lucky arm: the LoRA left subject_cos flat while
  off_cos climbed (drift toward generic anime); the adapter lifts subject_cos and
  pins off_cos. The margin gain is identity, not distractor collapse.
- **The control reproduced byte-identical** to yesterday's run at matched seeds -
  so the recipe has not drifted, and the adapter-off code path is provably inert.
- **Costs are real and are in the ledger:** sharpness falls hard and
  monotonically, and at scale >= 0.5 a second fox familiar hallucinates in. Best
  arm 0.3 is also the sharpest arm. Do not reach for a higher scale to chase
  identity without re-checking lap_var.
- **What it does NOT do:** facial structure and the red whisker markings are not
  transferred. That is expected of the GENERAL adapter (one global CLIP
  embedding) and is the specific thing plus-face should fix.
- **Provenance gap found and closed:** the general adapter + CLIP image encoder
  had been on disk since 2026-07-16, load-bearing and completely unrecorded in
  `docs/GEN_MODELS.md`. Both now recorded with real hashes, license verified live.
- **plus-face LANDED and was measured** (sha256 `677ad886...`, row filled). Three
  further evals ran the same day - see LEDGER 110 + 111. Short version: plus-face
  beats the general adapter on RealVisXL (best **loose 0.3**), the ranking INVERTS
  on animagine, and a tight-crop A/B came back NULL on identity.
- **NOTHING WAS PROMOTED and that is deliberate.** No config default changed, no
  adapter setting adopted. On the SHIPPED base (animagine) the MEDIUM fails
  independently of the adapter - it sits 0.11-0.19 below the real-vs-real ceiling
  (see next bullet) - so tuning adapter scale there optimizes the wrong variable.
  (The "0 of 18 hero-dominant" figure first cited here is RETRACTED - see 112.)
- **The gate is measurably blind.** Real-vs-real self-similarity ceiling **0.8373**:
  RealVisXL arms sit at/above it, animagine arms 0.11-0.19 BELOW, while animagine
  posts a near-best `subject_cos` 0.2909. NOT adopted as a gate - one champion only.
- **The fox familiar is NOT reference bleed.** It survived cutting 94 percent of
  reference context, unchanged across both crops and all scales. It is
  base/prompt/seed - attack it with a negative prompt, not adapter tuning.
- **NEXT, and it is the only thing that settles the crop question:** a tight crop
  from a HIGH-RESOLUTION Ahri source. Every splash in the local 21-image set has a
  78x82 native face, so cropping tighter necessarily blurs the reference and
  face-fraction cannot be separated from reference-sharpness. Do NOT re-crop the
  existing corpus - the confound is in the SOURCE.
- **Still untested across all four evals:** a FULL-FRAME reference at high scale
  (every run used a face crop, the input least able to carry copyable composition).
- **TWO MORE FIXES BUILT AND REVERTED after measurement (LEDGER 112 + 113).**
  Both looked right on paper. Neither survived. Do not re-open either.
  - **Composition tags (112):** the premise is RETRACTED. "0 of 18 hero-dominant"
    was BY-EYE and inverts under measurement - heads are **TOO BIG** (mean
    `head_frac` 0.0484 vs real median 0.0116) and **5 of 6 frames already sit
    inside the real key-art envelope**. `GEN_MODELS.md` struck accordingly.
  - **Long-prompt encoding (113):** the code is PROVEN CORRECT - bit-exact vs
    `pipe.encode_prompt`, short styles byte-identical 6/6. Reverted anyway:
    identity fell on **12 of 12 seeds** (p ~ 0.0002) and the ADR-005 rationale is
    FALSE - zero signature detections in 24/24 frames, and the shipped style
    never truncated those tokens at all.
- **The 77-token overrun is REAL and LEFT ALONE by operator call.** splash 139/149,
  splash-anime 97/125, splash-booru negative 93. Restoring the discarded text was
  measured and made things WORSE. Do not "fix" it on tidiness grounds.
- **Live trap worth remembering:** `lw_gen_run.run()` called twice in ONE process
  silently kills the second arm - no traceback, exit 0, zero images. One fresh
  process per arm, or a harness produces an empty arm that reads as a real null.
- **Process note for the gen workstream specifically:** three reasoning-derived
  fixes were proposed this session from correct-looking evidence; all three were
  refuted by cheap measurement. Verify before commit is earning its cost here.
- **Still open, untouched across both sessions:** `m1-gate-fund-or-close`
  (FUND/CLOSE), the two `g1-source-adequacy` policy questions, and the
  `legacy-audit-backfill` data call.

---

## 2026-08-15 - gen recon triple: render capture proven, LoRA path dead

One commit, one new tracked tool. Three background agents ran in parallel while
the main window stayed free (operator restated the subagent-first directive).
LEDGER 107.

- **The operator's question was: capture 360 views of every skin from the 3D
  models as trainer data for matching aesthetics + designs per champion.** The
  answer is that capture WORKS and is cheap, and the training premise is DEAD.
  Both halves are measured, not argued.
- **No GUI / OBS / OCR / machine-control needed.** CommunityDragon serves every
  skin's own `.skn` + `_tx_cm.png` script-only, unblocked. The operator-assist
  lane stays in reserve for chromas and anything CDragon does not serve.
- **The `.skl` 404 only ever blocked WEAPON ISOLATION.** For whole-mesh renders
  it is irrelevant. Proven by the aristocrat control, recorded in the POC as an
  outright failure, which renders clean first try.
- **PRESERVED: `tools/lw_render_skn.py` + 13 tests.** The original POC code was
  LOST with an ephemeral scratchpad (`LEDGER.md:2861`); the rebuild was sitting
  in scratchpad about to be lost the same way. GPU imports are deferred so the
  camera math tests in the main env; `.venv-poc` is still required to render.
- **Ahri LoRA scored: FAILS, worse than no LoRA.** `subject_cos` flat across all
  arms, `off_cos` rising - it drifts toward generic anime, it does not learn
  Ahri. Trained on RealVisXL, not the current Animagine base. Never sampled from
  before this run.
- **Root cause, found independently by two agents:** one generic caption
  averaged over mutually contradictory skins. The proposal to capture EVERY skin
  scales exactly that failure mode.
- **NEXT (nothing is blocked on it):** base model + ControlNet + IP-Adapter is
  the stronger lane and IP-Adapter is still untested. A retried champion LoRA is
  one skin / clean captions / ~400 steps. Render capture is parked and cheap for
  the DISCRIMINATIVE consumer only - `m1-gate-fund-or-close`, still operator-gated.
- **Operator decision still open:** the FUND/CLOSE call on m1. Also unanswered -
  the two `g1-source-adequacy` policy questions and the `legacy-audit-backfill`
  data call, both untouched this session.

---

## 2026-08-13 - /sync-all-md pass: four stale structural facts

One commit (`b80e7cb`), docs only. Suite **1975 passed / 18 skipped** run fresh
this turn, ruff clean, hygiene trio green, drift_guard 0 breaches / 4 notes.
LEDGER 106. No ROADMAP item moved - nothing shipped but doc congruence.

- **Canonical facts established live, not read off a doc:** 1992 collected /
  1975 passed / 18 skipped; no product VERSION constant exists yet; 3 `LW-*`
  scheduled tasks Ready (matches the OPERATIONS roster of 3 registered + 2
  unregistered rows); stages 2.First Pass Done=302, 3.Cleaning Scratch=18.
- **Fixed:** README ADR list stopped at ADR-008 (ADR-009 shipped in `74a6b09`);
  ARCHITECTURE named lw_ports allocations "(monitor=8901)" while
  `tools/lw_ports.py:33-34` also pins `RUNDASH = 8900`; ARCHITECTURE's component
  map had NO `tools/lw_rundash.py` entry; OPERATIONS claimed "HTTP health
  endpoints: TBD (no ports exist)" while both read-only servers serve
  `/api/health` today.
- **Cross-reference sweep: 0 genuinely broken refs** across the 7 living docs.
  The only non-existent targets are the documented-TBD set
  (`ops/lw_supervisor.py`, `ops/runtime/health.json`, `agents/**`,
  `tests/test_bare_py_ban.py`) - all four are named as absent by the doc citing
  them. Do NOT "fix" these; they are intentional placeholders.
- **Two calls left OPEN for the operator, deliberately not applied:** (1) the
  gemini-vendor docs (`GEMINI.md`, `docs/GEMINI_AUDIT_CONFIG.md`,
  `docs/GEMINI_REVIEW_CONSUMPTION.md`, `tools/gemini_audit_prompt.md`,
  `ops/loop/{director,auditor}_prompt.md`) are still tracked as live though the
  vendor retired 2026-08-02 - CLAUDE.md keeps `gemini_audit.ps1` as the rollback
  path, so quarantining them is an operator decision, not a sync decision;
  (2) 13 `MEMORY.md` index lines exceed the 150-char cap (longest 248) - that is
  `/consolidate-memory`'s job, flagged only.
- WAKEUP already at the keep-3 limit before this entry; prune re-run at wrap.
