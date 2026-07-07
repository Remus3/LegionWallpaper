# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04), 2026-07-04 QA Session 1 (pruned
> 2026-07-05), and 2026-07-04 QA Session 2 (pruned 2026-07-07) - keep the last 3.

---

# 2026-07-07 (first-pass queue fully worked: needauth + crop-held + bucket-C recovery + 9 working triaged)

Operator-driven review pass. Commits 6c6006a + d441993 + 0c9b1f5 (last is
docs-only, CI path-ignored; first two CI green). `2.First Pass Done` 121 -> 179.

**Needauth (53 live):** 49 APPROVED, 4 REJECTED (xayah1/camille1/kaisa1/fiora1 -
source ingest artifact, a foreign strip on top; NOT a process fail).
**Crop-held (12):** A+B 4 hand-cropped to 16:9 + re-run + approved
(chengwei-pan-1/2, rey-jinn-up-2, tina-wei). Bucket-C 4 recovered + approved
(darius/fantasy-aivio/fury-sona via gallery-dl original=true; mfortune1 via local
2560x1440 twin Pictures/145_cleanup.png); 4 discarded (inkshadow, ashe, syndra,
wp-vayne). **9 working triaged:** image1/2/4/5 (800x450 alphacoders thumbs)
DISCARDED; elise-8k (clean 8K, spurious lpips-only downscale-only FAIL)
force-submitted + approved; 4 messups PARKED for manual re-source.

**NEXT:** (1) manual re-source the 4 messups (Battle Academia splashes; drop a
clean 1920x1080+ into 0.Originals + re-intake; Tier-0 found no local twin, no
token) OR (2) start the cleaning pass (Stage 2, /cleaning-pass) on the 179 Done.
**Do NOT redo:** the 57 approvals, the crop+recovery flow, the discards, elise
force-submit - all shipped. select_source prefers data/recovery/fetched/<slug>
fullviews over scratch _firstinitial (the crop-wrong-file trap; see LEDGER 12).

---

# 2026-07-05 (V3 promoted to primary + golden n=12 + dark-cosmic; recovery scaffolding; G0 gate; ADR-004/005)

Resolved + promoted IllustrationJaNai V3 detail DAT2 to the PRIMARY first-pass
upscaler (ADR-004; LEDGER item 5). V3's OpenModelDB link is dead - it ships only
via the MangaJaNai v3.0.0 GitHub release (direct HTTPS, no gdrive dance); fetched
the DAT2 detail weight (sha eb9faf6a, 139,793,020 bytes, self-computed checksum),
spandrel-loaded (arch=DAT/4x). A/B'd V1 vs V3 through `lw_golden regress`: V3 wins
golden n=10 (MS-SSIM 8/10, LPIPS 9/10, halo 7/10) + both new defect cases, and
clears BOTH high-halo flags (fiora2 0.072->0.043, inkshadow 0.075->0.043). Widened
calibration to n=14 golden-comparable - thresholds HOLD (the 3 lap<1.0 'fails'
were big-4K-source common-scale-upscale artifacts, a G0 source-gate gap now in
ROADMAP). Re-froze the golden set at n=12 on V3 (pv d9ec8125 -> 6d43a6d4; added
`coven-ashe-lol-df49jt0-pre` jpeg-artifact + `1341679-banding`); all 12 PASS with
ZERO flags; regress self-check PASS 12/12 pv_changed=False. Reprocessed
`dark-cosmic-ahri-by-pebano1-dlnxav6-pre` from its recovered Tier-0 source
(`Pictures/288.png`, 2560x1440, pHash dP=4 vs the 1192x670 G0-fail preview) -> V3
first-pass (PASS) -> submitted to `_firstneedauth`.

**Do NOT redo:** the V3 weight (gitignored `tools/models/`); the n=12 V3 freeze;
the A/B. Suite 190 passed / 3 skipped; only `data/golden/golden_set.json`
tracked-dirty. **Process scar:** killed a pathological 8K source (caitlyn
7680x4320) mid-widening that pinned the 12GB card at 11.5GB - verified the PID by
working-set/CPU/GPU correlation, NOT blind nvidia-smi. **Also shipped this session (2026-07-05, continuous):** (a) source-recovery
waterfall scaffolding `tools/lw_recover.py` (LEDGER item 6, commit b61c1a5) -
Tier 0 local pHash/dHash match usable NOW, Tier 1 token-decode + oEmbed work now,
Tier 1 gallery-dl + Tier 2 SauceNAO gated on keys, the SauceNAO multipart-POST a
flagged TODO; (b) the G0 over-target source-gate (LEDGER item 7, commit 6cffc3d) -
first-pass routes sources already covering 2560x1440 to a downscale-only path
(closes the widening gap); (c) artist-signature ruling ADR-005 (REMOVE at the
cleaning scratch stage - closes the last queued ADR-002 decision). Full suite now
226 passed / 3 skipped; commits 37741ea, b61c1a5, 6cffc3d all pushed.

**STATE update (later 2026-07-05):** dark-cosmic APPROVED -> `2.First Pass Done`
(_firstdone). Recovery keys IN - `API-Key-SauceNAO.txt` (40 chars) +
`API-Key-DeviantArt.txt` (client-id/secret); `%APPDATA%/gallery-dl/config.json`
written with the app creds + quota-friendly (original=false, quality=100,
intermediary=true). **DeviantArt AUTHORIZED** (operator ran `gallery-dl oauth:deviantart`
2026-07-05; refresh-token cached) - all recovery keys live. **NEXT (active -
recovery activation):** (1) finish the
SauceNAO image-upload POST in `lw_recover.saucenao_search` (flagged TODO; TDD);
(2) build + run a campaign driver - enumerate the 149 pending, Tier-0 corpus =
`Pictures/` + `Desktop/Found`, run `run_waterfall`, record provenance via
`lw_pipeline annotate`. **Then:** monitor polish (lw_monitor 127.0.0.1:8901,
`docs/research/LW_MONITOR_SPEC.md` section 8, UI Fixture Ritual); G3 Haiku
win-or-tie; V3denoise per-image halftone alternative.

**STATE update 2 (recovery activated + monitor polished, 2026-07-05):** the
"NEXT (active)" above is DONE. (1) SauceNAO multipart POST wired (real image
upload; live-verified parsed shape + quota long_remaining=94). (2) Campaign
driver `tools/lw_recover_campaign.py` built (TDD, 11 tests) + RAN on the live
170 pending previews (backlog grew past the noted 149): 102 Tier-0 local pHash,
67 real DeviantArt fullview fetches, 1 SauceNAO (Pixiv, dead deviation), 0
manual, 0 errors. **Root-caused + fixed a live DeviantArt clampdown regression:**
oEmbed now 404s on `/deviation/<id>` and needs the canonical
`/<artist>/art/x-<id>` URL (rebuilt from the `_by_<artist>_` filename); the fetch
stays on authoritative gallery-dl OAuth. Provenance annotated via `lw_pipeline
annotate` on the two manifest-bearing slugs; loose targets record provenance in
`data/recovery/matches.json`. `.gitignore` now ignores all recovery runtime
outputs (fetched art + personal-path caches). Suite 243 passed / 3 skipped.
Commits 5c2cf42 (code) + ea74508 (docs); LEDGER item 8. **Monitor polish (LEDGER
item 9):** verified lw_monitor live against real state (renders 11
First-Pass-Done + 120 pending; log tail + page all HTTP 200), created the "LW
Monitor" Desktop shortcut (section 8), confirmed the page ASCII-clean; thumbnail
generation found DORMANT (no producer writes `thumb` fields) so the spec
thumbs-root RISK is RESOLVED/deferred. **Do NOT redo:** the POST, the oEmbed
artist-URL fix, the driver + this run, the shortcut. **NEXT:** dark-cosmic
downstream stages (cleaning pass); a thumbnail producer if monitor thumbs are
wanted; per-image `original=true` 4K escalation for quota-capped fullviews; G3
Haiku win-or-tie; V3denoise halftone alternative.

**STATE update 3 (recovered backlog first-passed, 2026-07-05):** Task 1 executed.
Ground-truth CORRECTED the "1280px cap" (that was the oEmbed PREVIEW dim; fetched
fullviews are median 1440w, 19/68 >=2560). Operator forks: budget = gate-triggered
original=true (cost 0 this batch); non-16:9 = auto-crop when area-loss <=8 percent
else HOLD. Validated the full chain live (p08e8 PASS) THEN built + committed
`tools/lw_first_pass.py` (resumable first-pass driver, 27 tests, verifier-green,
live-proven on aatrox; commit 82aacc2). `intake --all` (119 -> scratch, 0
anomalies) -> real-upscale batch of 47 = 38 PASS + 9 FLAG + 0 FAIL; 10 crop_heavy
HELD. **49 in _firstneedauth** (approve/reject queue). Suite 270 passed / 3
skipped. **Deferred (cause):** 61 downscale-only need distinct G1 handling
(lap_ratio floor invalid for a no-upscale path; the LEDGER-7 false-soft) - now the
top ROADMAP NEXT. **Do NOT redo:** the driver, the 47-batch, the 10 holds, the 2
pilots. LEDGER item 10.

---

# 2026-07-04 (golden set - first-pass drift-regression harness shipped)

Commits 8e8b9a0 + 936d99b + e0a1250. Built `tools/lw_golden.py` (freeze +
regress) - the drift-detection harness, adapted for no-ground-truth (operator
ruling: no finished refs; reference of record = the current blessed IJN
first-pass output, not perfection). Flow: brainstorm -> spec
(`docs/research/GOLDEN_SET.md`) -> plan
(`docs/superpowers/plans/2026-07-04-golden-set.md`) -> TDD build; heavy deps
INJECTED so the tool is CI-testable. Operator blessed all 10, froze
`data/golden/golden_set.json` (TRACKED, pv d9ec8125, 10 cases; image bytes
gitignored + sha-pinned). Regress self-check PASSED 10/10 within epsilon (also
proves IJN upscale determinism). Suite 190 passed / 3 skipped; CI green.

Do NOT redo: the golden freeze (done); the 10 baselines. Two process scars in
LEDGER item 4: a stray `&` spawned a duplicate torch job -> pagefile OOM
(WinError 1455); nearly taskkill'd dwm/explorer/claude by trusting `nvidia-smi`
compute-apps blindly - ALWAYS verify a PID name before taskkill. Next: widen n
past 10; trial V3 DAT2 via `lw_golden regress`; add banding/JPEG-artifact
defect-class cases to the golden set.
