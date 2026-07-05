# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined, pruned 2026-07-04) and 2026-07-04 QA Session 1 (pruned
> 2026-07-05) - keep the last 3.

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

---

# 2026-07-04 (QA Session 2 - IJN primary path live + G1 gate frozen n=10)

Commit dca6071. IllustrationJaNai V1 DAT2 (spandrel/torch) is now the PRIMARY
first-pass upscaler and the G1 gate is frozen on it. Downloaded + extracted the
V1 DAT2 weights to `tools/models/` (gitignored; OpenModelDB -> Google-Drive zip
bundle, confirm-token dance), spandrel loads DAT/4x on the RTX 5070. Built 3
committed modules (TDD, subagent slices, CI-safe via importorskip):
`lw_upscale.py` (spandrel + ncnn backends, seam-exact tiling), `lw_g1_gate.py`
(the REAL overshoot detector replacing the crude edge-diff proxy, plus
laplacian/banding/common-scale-FR/verdict), and a `lw_pipeline annotate` verb
(provenance + G1 metrics into manifests; closes task_fb503c0a). Ran the 10
approved images through IJN and G1-scored IJN vs the realesrgan-anime fallback
with identical code: **IJN wins 10/10 on MS-SSIM, LPIPS, AND halo_pct.** Froze
AUDIT_GATES 1.4; fixed a band_delta hard-fail bug (was fail>0 - it wrongly
hard-failed the BETTER upscaler 8/10 on ~0.004 noise; demoted to advisory
flag). Suite 183 passed / 2 skipped, ruff clean, pushed.

**Premise CORRECTED (operator ruling):** `reference_pictures/*_cleanup.png` are
"original-not-found" MARKERS, NOT finished ground-truth. The Session 1 "GT vs
finished ref" band is VOID - G1 scores self-metrics only; every image still
needs work. Saved to memory (`project-no-finished-ground-truth`).

**Do NOT redo:** venvs + V1 DAT2 weights (downloaded, gitignored under
`tools/models/` + `.venv-*/`); the 10 first-pass images. **Next:** golden set of
approved (input, output) pairs - the prereq for any GT-vs-approved regression,
since none exists yet; widen n past 10; trial V3detail DAT2 (its OpenModelDB
gdrive link was unresolved this session). **Queued (unchanged):** recovery
campaign (149 pending, 75 `niphrimit` `-pre`); artist-signature policy; API
keys (SauceNAO + DeviantArt).
