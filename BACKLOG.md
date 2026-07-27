# Legion Wallpaper - Backlog

_Aspirational / longer-term items. When an item moves to active work, migrate it to `ROADMAP.md` "Open items"._
_Shipped items live in git log + `docs/LEDGER.md`; this file is for things NOT yet done._
_Product is defined by ADR-002/ADR-003 (staged self-auditing restoration pipeline); sections fill as aspirational items emerge._

---

## Product

- _No aspirational product items yet; active work lives in `ROADMAP.md`._

## Platform / observability

- _No items yet. Candidates once the product runs: metrics endpoint, health rollups, log retention tooling._

## Data pipeline

- _No items yet. Candidates: image manifests, provenance records, gate-metric retention._

## Developer experience

- _No items yet. Candidates: pre-commit hooks hardening, suite speed, local tooling._

## Reliability / hardening

- _No items yet. Candidates: supervisor edge cases, crash-loop backoff, watchdog coverage._

## Speculative

- _No items yet. Ideas with no committed path land here first._

## Research / inspiration

### 2026-07-26 - 3DSkinViewer / modelviewer.lol - canonical 3D geometry source - UNEXPLORED

Source: `https://github.com/Ventoba/3DSkinViewer` (operator-supplied, not yet
evaluated hands-on). Probed 2026-07-26: MIT, 6 commits, 2 stars, 0 forks, 1 open
issue - a small personal project. README: "A pengu plugin that lets you see any
Skin in Collection tab as a 3D model, based on modelviewer.lol".

**Why it may matter (NOT yet verified):** the plugin is a thin client; the
interesting artifact is whatever `modelviewer.lol` serves - LoL champion 3D
models. The M1 weapon work is blocked precisely because there is no way to render
Vayne's canonical wrist crossbow from arbitrary angles: the CLIP region gate is
dead (LEDGER 21 / `docs/research/GEN_RETUNE.md` sec "WEAPON-GATE CALIBRATION"),
the weapon LoRA is data-starved (9-19 crops), and DreamUp text-gen cannot render a
wrist-mounted device at all (it produces hand-held tactical crossbows). A real 3D
mesh would supply unlimited canonical views for LoRA training, W3 IP-Adapter
reference images, and gate positives - the exact gap every prior approach hit.

**RESOLVED 2026-07-26 - operator rulings + prior work on disk.** Q1-Q4 as first
drafted are answered; do NOT re-ask them.
1. **Programmatic access to modelviewer.lol: NO, already measured.**
   `docs/research/crossbow_render_poc.md` (2026-07-16) records modelviewer.lol
   (Khada) as Cloudflare-protected + loading via in-app blobs, explicitly NOT
   scrapeable. Do not retry the website-scrape route.
2. **Asset-distribution concern: CLOSED by operator ruling.** Assets are already
   public and widely used across public sites. LW is private-use regardless
   (RESTORATION_PLAN sec 10), so nothing ships either way.
3. **`.skn` path: PROVEN AND ALREADY BUILT, but it is NOT a reason to skip the
   GUI.** The CommunityDragon acquire -> pyritofile parse -> bone-set isolate ->
   headless moderngl render chain works (`.venv-poc`, 16 crops produced). Its ONE
   recorded hard limit is per-skin weapon isolation: the skeleton is shared across
   skins, themed skins bind capes/wings/a wine bottle to the same bone indices, and
   CDragon 404s the `.skl` so bone NAMES are unavailable. Clean isolation was
   achieved on BASE ONLY. Operator's point: a local interactive viewer is a
   curation surface for exactly that gap - choose angle + variant by eye per
   champion / skin / chroma instead of guessing bone sets. The GUI and the headless
   renderer are complementary, not either/or.
4. **rc_live conflict: EXCEPTION GRANTED (operator).** The hard gate targets VRAM
   contention from a concurrently-running game or another GPU project on this box -
   not League-client mods as a category. Asset capture while nothing else contends
   for the GPU is fine.

**The one genuinely open question:** does 3DSkinViewer render LOCALLY in-client in
a way that permits capture - sidestepping the Cloudflare/blob wall that killed the
website scrape - and can a GUI-made selection (champion / skin / chroma / angle) be
exported back to drive the already-working `.skn` render pipeline? If it is just a
local view of the same unreachable blobs, it adds nothing over the headless path.

**Consumer matters - read this before citing the POC's negative verdict.** The POC
verdict is negative for the WEAPON LORA specifically: 4 clean base renders took
training 6 -> 10 crops, v2 == v1, same plateau, concluded to be a CEILING of the
masked-inpaint + thin-LoRA method on stylized splash art rather than a data-quantity
problem. That finding does NOT transfer to the GATE. A canonicity classifier
(the 2026-07-26 DreamUp corpus work) is a different consumer with a different
failure mode - its blocker is a provenance confound in the training corpus, and
unlimited canonical multi-angle renders are an untested candidate fix for it.
Do not cite "renders did not help" as a reason to skip gate-positive experiments.

**Do-not-redo context:** SDPose-Wholebody (mmcv wall) and the ViT-L-14 region gate
are both settled dead ends - see CLAUDE.md "Settled". This item does not reopen
either; it attacks the upstream data problem instead.
