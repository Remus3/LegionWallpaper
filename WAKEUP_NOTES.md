# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), 2026-07-04 QA Session 2 (pruned 2026-07-07), and the 2026-07-07
> first-pass-queue session + the lw-gen generator-sidecar/deep-research session (both pruned 2026-07-11), and the 2026-07-11 QA-floor calibration + recipe-v2 session (pruned 2026-07-11), and the 2026-07-11 GOLDEN DEFINITION session (pruned 2026-07-12), and the 2026-07-11 M0-foundations + M1-slices-1-2 session (pruned 2026-07-12), and the 2026-07-11 localizer-decision session (pruned 2026-07-12), and the 2026-07-12 M1-weapon-CLIP-gate session (pruned 2026-07-16), and the 2026-07-16 W4-M3 weapon-parked session (pruned 2026-07-16), and the 2026-07-16 Stage-2 cleaning-pipeline session (pruned 2026-07-18) - keep the last 3.

---

## 2026-07-26 (late) - f1 items 9 + 5a, and a self-driven RC sync channel

Commits `a7dfde5` (trailer sweep), `3bd9a8b` (items 9 + 5a). Detail: LEDGER 41.

- **Operator is ASLEEP and RC is draining the same queue in parallel.** The two
  sessions sync THEMSELVES through gitignored `moon_sync_inbox/` dirs, one in
  each repo. LW's was created this session; RC's already existed and is
  gitignored on its side too, so neither channel can pollute either repo's git.
  RC's inbox holds `2026-07-26-2340-from-LW-f1-items-9-and-5a.md` plus the exact
  `winmutex.py` bytes as `winmutex.py.from-lw`.
- **RESOLVED same night: the shared files are VERIFIED IN SYNC.** RC applied the
  handed-over bytes and committed them as `fbf744f5`; item 1 landed as
  `19b680cc`. Both trees re-hashed clean to `slots.py 95077a62...` /
  `winmutex.py f1b4b011...`, so the `SHARED_SHA256` pin is no longer provisional.
- **A wrong inference to not repeat:** LW probed for an RC LOOP process, found
  `STOP: max_cycles 1 reached` from 22:57:59, and concluded "nobody is on RC" -
  then nearly restarted RC's loop on top of a LIVE interactive RC session that
  was mid-apply. Absence of the loop is not absence of a driver. Probe for BOTH
  before acting on another repo. The launch was aborted and a stand-down note
  left in RC's inbox naming the one commit LW had already made there
  (`8986418f`, launcher channel fix, pathspec-scoped).
- Item 9: the POSIX branch of `winmutex.hold` yielded silently, so every
  serialization test passes vacuously off Windows and the log carries no trace.
  It now emits the same `winmutex: UNSERIALIZED` marker as the two Windows
  fail-open branches. fcntl fallback REJECTED (per-process locks; the
  two-threads-one-process test would stay red) - do not re-propose.
- Item 5a: `SHARED_SHA256` pins both digests so each repo's CI proves parity
  alone. `winmutex.py` re-pinned to `f1b4b011...` (supersedes `c21bfe4f...`);
  `slots.py` `95077a62...` unchanged. This KNOWINGLY amends LEDGER 40's
  do-not-redo line, which named the old digest - the intent (never pin an
  unverified value) is kept: the pin is PROVISIONAL until RC's reply shows both
  trees hashing equal.
- Queue split proposed to RC: LW takes (3) `sid` on every SdkExecutor path and
  (12) `not evaluated` vs `queued`; RC keeps (1) its side, (2), (4), (5), (7),
  (10), (11). Phase-6 DELETIONS still HELD - neither session touches them.
- Also swept: four command skills still told the agent to emit the banned
  `Co-Authored-By: Claude` trailer (`/done`, `/sync-all-md`, both headless
  skills, five sites). RC fixed its own copy the same evening (`7c2deaba`).

---

## 2026-07-26 - F1 sdk executor channel: LW+RC loops now run concurrently

Commits `dc4a3bf`..`920afeb` (30 this session). Full detail: LEDGER 40 +
`docs/specs/2026-07-26-f1-sdk-executor-channel.md`.

- Moved the loop's EXECUTOR off the AHK GUI bridge (a machine-wide singleton on a
  window title) to headless `claude -p`. P0-P5 all shipped and PASSED; the P5
  concurrent LW+RC run caught 41 samples with both repos holding a slot, and RC's
  mutex acquire timestamp equals LW's release, so serialization was proven under
  real contention.
- Phase 6 is FLIP YES, DELETE NO by operator call. Both repos default to
  `channel: sdk`; rollback is one config key; `done_sentinel.py`, `meter()` and the
  AHK bridge all STAY. The full-length gate cycle ran clean on both sides.
- Claude dollar cap + accounting REMOVED - notional pricing on a Max plan, and
  `meter()` billed the loop $329 for the operator's own interactive session.
- **I let CI stay RED for 12 commits without looking.** The gate run's executor
  found it: `.githooks` were mode 100644 and git silently skips non-executable
  hooks, so the gate was inert on every Linux clone. CI is green at HEAD now.

NEXT: the 12-item `f1-phase6-queue` in ROADMAP, jointly with RC. Items 5a (pin
shared-file sha256s) and 9 (POSIX `UNSERIALIZED` marker) touch the byte-identical
shared files and need a re-sync, so do them WITH RC, not unilaterally.

DO NOT REDO: capping Claude spend on Max; trusting `meter()`; assuming
`gate_inactive_reason` proves hooks FIRE (presence only, not the exec bit); the
`{{FINAL_STEP}}` contradiction (fixed both repos, director honored it byte-for-byte
under a real gemini call).

## STANDING REFERENCE - machine state (not a pending action; resolved 2026-07-26)

- **PowerShell 7 - INSTALLED BY RIOT COMMANDER 2026-07-26. LW migration = NO-OP.**
  Authority doc: `C:\Users\Administrator\Desktop\POWERSHELL_7_MIGRATION.md` (RC,
  machine-wide). Read it before touching any call site; do not re-derive.
  - Live state verified 2026-07-26: `C:\Program Files\PowerShell\7\pwsh.exe` =
    **7.6.4 Core**, MSI machine-scope, on machine PATH. `powershell.exe` is
    untouched 5.1 and stays forever. Side-by-side; nothing auto-switched.
  - MSI not winget: the winget manifest ships only an MSIX, whose exe path carries
    the version (breaks pinned scheduled tasks on upgrade) and whose stable-looking
    launcher is a per-user app-execution alias. Do NOT "fix" this with winget.
  - **LW has ZERO migration work.** Probed 2026-07-26: `LW-Wallpaper` executes
    `pythonw.exe` (not `powershell.exe`), so RC doc sec 4a does not apply. No LW
    `.vbs`/`.bat`/`.cmd` shim names powershell. The only authored call sites are
    `ops/loop/loop_controller.py`, `tools/precommit_gate.py`, `tools/truth_gate.py`,
    `tools/weekly_hygiene_run.ps1` - all agent/hook-invoked, none pinned to a shell
    binary that needs changing. Nothing to switch; revisit only if LW registers a
    powershell-executing task.
  - **Agent sessions stay on 5.1** (RC doc sec 4c): Claude Code's PowerShell tool
    invokes `powershell.exe` and no setting selects the binary. So KEEP WRITING
    5.1-COMPATIBLE POWERSHELL - no `&&`/`||`, no ternary, no `??`. Escape hatch if
    ever needed: `& 'C:\Program Files\PowerShell\7\pwsh.exe' -NoProfile -File <s>`.
  - **The no-em-dash ASCII rule STANDS - do not relax it.** RC measured that PS7
    parses a no-BOM UTF-8 `.ps1` containing an em-dash with 0 errors, so that one
    5.1 failure mode is gone under pwsh. It remains LIVE anywhere `powershell.exe`
    is named explicitly, it is an independent operator style rule, and it is
    mechanically gated by `tools/precommit_gate.py`. PS7 removes a failure mode,
    not the rule.

---

# 2026-07-26 (headless loop cycle: glb addressing layer shipped; CI rescued from 5 pre-existing reds)

Commits: 1dbfc2d (feat), b63992a (docs), ca8403a + 2b94040 + 09e4905 + bfe0bd8
(the CI-red chain), plus this sync. Details in LEDGER 38 + 39.

- **Directive premise was FALSE and was corrected before any code.** It claimed
  the live tool "still uses a broken `.skl` scraper". It does not - nothing in
  `tools/` ever fetched anything. `lw_gen_weapon_assets.py` is purely the W2
  consumer of pre-authored crop PNGs. So this ADDED an addressing + bone-filter
  layer that never existed rather than porting one.
- **The POC evidence the ROADMAP cited is GONE.** `scratchpad/glb_render/` (110
  renders) and `scratchpad/glb_weapon_isolate.py` do not exist - scratchpad is
  ephemeral. LEDGER 37 prose is now the only record and the implementation was
  rebuilt from it. If a future session cites a `scratchpad/` path as evidence,
  check it exists first; several ROADMAP entries still do.
- **Only the pure half shipped, deliberately.** URL/skinId/bone-filter/primitive
  aggregation are pure functions, so the module stays torch-free AND network-free.
  Fetch + GLB parse + skin + render needs a network dep and a render backend and
  is re-opened as ROADMAP `glb-render-fetch`. Do not read the closed item as
  "rendering works now" - it does not; nothing downloads a `.glb` yet.
- **CI had been red for 4 commits and nobody had looked.** Take the `gh run list`
  baseline FIRST, as the framework says - I nearly shipped onto a red main. The
  headline finding: `.githooks/*` were mode 100644, so the AUTHORITATIVE gate was
  silently dead on every Linux clone while looking installed. Worse, the test that
  "proved" the gate fires built its fixture with `write_text`, so it could never
  have caught this on any platform with an exec bit.
- **One diagnosis I got wrong, recorded on purpose.** I wrote a ROADMAP entry
  claiming the loop mutex "fails OPEN on Linux". Reading `winmutex.py:55` refuted
  it - non-Windows is a deliberate documented no-op. Corrected and the entry
  deleted in the same commit. Verify before declaring broken, including against
  your own earlier note.

---

# 2026-07-26 (weapon gate: 3 measured negatives; .glb named joints unblock the render POC; drift guard adopted)

Commits: a72ea8b (drift guard + /done wiring), plus this docs sync. Full
detail in LEDGER 37 - this is the short hand-off.

- **The gate did NOT get revived. Three attempts, three different confounds.**
  img2img weapon-swap changed 0/12 images (structure lock beats the negative
  prompt). A trained probe hit AUC 1.0000 by reading GENERATOR PROVENANCE, not
  the weapon - de-aliased, it ranked real crossbows BELOW lanterns (0.1667).
  Render exemplars reached 0.9538 but two thirds was RESOLUTION; controlled it
  is 0.7538, p=0.0586, not significant.
- **Standing lesson:** match the corpus on EVERY axis. Provenance slipped in,
  then resolution, both while palette was being tuned - and palette turned out
  to be innocent (luminance AUC 0.4248).
- **The durable win:** `cdn.modelviewer.lol/lol/models/<champ>/<skinId>/model.glb`
  ships FULLY NAMED joints. That supersedes the recorded blocker in
  `docs/research/crossbow_render_poc.md` (".skl 404 -> bone names unavailable"),
  which had forced base-skin-only isolation. Clean crossbow on 4/5 Vayne skins
  INCLUDING aristocrat, the POC's wine-bottle failure.
- **Do NOT redo:** the three approaches above; the 36 DreamUp step4 prompts
  staged at `scratchpad/step4_matched/` (deliberately never run - superseded);
  scraping the modelviewer.lol website (Cloudflare, POC-measured).
- **Next:** ROADMAP top item `m1-gate-fund-or-close` is an OPERATOR decision -
  fund attempt #4 (hand-crop the 19 official splashes to n~19 at matched pixel
  count) or close and keep `gate_mode="operator"`, which already ships and works.
- PS7 7.6.4 is installed machine-wide by RC; LW migration is a verified no-op.
  Agent sessions stay on 5.1 - keep writing 5.1-compatible PowerShell.

---

# 2026-07-18 (wallpaper deck rotator shipped - Windows slideshow replaced; LW-Wallpaper task live)

Three commits: b93ddc7 (spec), d220e6e (feat), 17693cb (time-trigger fix).
Operator asked why the Windows slideshow repeats constantly. It is not a
perception problem - the algorithm has no memory.

- **Root cause (probed live, not assumed):** `HKCU\Control Panel\Personalization\Desktop Slideshow`
  has `Shuffle=1`, `Interval=60000`, `LastTickLow=LastTickHigh=0`. Zeroed
  LastTick = no deck, no cursor, no shown-set: sampling WITH replacement,
  re-seeded on wake/logon. At 242 images the expected first repeat is ~19
  picks (~19 min). Verifier corroborated by catching the wallpaper registry
  value change between two probes while LastTick stayed 0.
- **Shipped:** `tools/lw_wallpaper_rotate.py` - persisted permutation +
  cursor in `ops/runtime/wallpaper_deck.json`. Deck logic is pure so the
  once-per-cycle guarantee is testable; win32 SPI call is an isolated shim.
  Mid-cycle corpus churn handled (new pipeline deliveries join the current
  cycle; deletions are never set). Cycle-seam swap stops the last pick of
  cycle N opening cycle N+1.
- **Two defects caught, both worth remembering.** (1) My spec's step-2
  reconcile ran unconditionally, splicing everything into an empty deck on
  fresh state, so `cursor >= len(deck)` never fired and the seam swap was
  dead code - found by the build agent. (2) The task registered `Ready` with
  `Next Run Time: N/A`: a LogonTrigger's Repetition only starts when the
  trigger FIRES, so it would have idled until the next logon. Found by LIVE
  probe after install, NOT by the suite - the task XML had no trigger-level
  test. Both fixed, both now covered.
- **Live state:** task `LW-Wallpaper` Ready, NextRun populated, both triggers
  PT3M, `Shuffle=0` (built-in disarmed), `WallpaperStyle=10` preserved, deck
  242 entries / 242 unique. Interval 3 min = ~12.1h per full cycle.
- Suite 575 passed / 11 skipped, ruff clean. Detail: `docs/LEDGER.md` item 34.

**Second half - corpus expansion (LEDGER 35 + 36).** Operator asked for the
missing "properly sized and QA'd" images from `9.Image Backup` and
`reference_pictures`. Premise was wrong on both and the wrong half mattered.

- `9.Image Backup` REJECTED: raw intake inputs. The 183 absent slugs are 8K
  sources or sub-720p DeviantArt previews, not outputs.
- `reference_pictures`: 272 of 292 genuinely novel (slug matching is useless
  here - dedupe ran on sha256-vs-manifest + pHash; 20 were already restored).
  All 2560x1440, no internal dupes. But NOT QA'd - `AUDIT_GATES.md:126` and
  `CLEANING_INPAINT.md:37` document baked-in artist credit strips.
- Triaged all 272 through the PRODUCTION gate (`detect_image` :660 +
  `gate_decision` :352, clean venv, 105s, 0 errors) -> 237 clean / 22 qa /
  13 auto. Gate validated against ground truth: it correctly caught
  `170_cleanup.png`, the one file the repo proves is watermarked.
- Held 11 more that the gate called clean but whose OCR could not be cleared.
  A fuzzy threshold flagged only 2 and MISSED `124f.png` (reads as
  DEVIANTART.COM) - evidence the threshold was the wrong instrument, so all 12
  long-OCR files got bounded manual review instead. Only `278f.png` cleared
  (in-art splash lore typography).
- Delivered 226 as `ref_<name>.png`, sha256-verified. Pictures 242 -> 468.
  Rotator reconciled live: deck 242 -> 468, all unique, new files joined the
  CURRENT cycle (`ref_302f.png` picked on that very tick).
- The 46 held were then intaken (operator directive): `first_scratch=0 -> 46`,
  anomalies=0, verifier CONFIRMED 9/9 + 4/4 harm checks. Queue + per-file
  reasons in `docs/refs_cleaning_queue.md`.
- **NEXT SESSION:** first pass the 46, then cleaning. Their manifests carry
  `source_url: null` - the recovery waterfall is still OWED for that set.
