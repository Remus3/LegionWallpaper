# WAKEUP_NOTES - LW hand-off ledger

> Newest-first. Keep only the last 2-3 sessions here at FULL fidelity; archive
> older sessions verbatim to `docs/history_notes.md` (append a pointer line to
> this banner when you prune). Per-item completion records live in
> `docs/LEDGER.md`; open work lives in `ROADMAP.md` + `BACKLOG.md`.
> Archived to `docs/history_notes.md`: the two 2026-07-03 sessions (genesis +
> product-defined) - pruned 2026-07-04 to keep the last 3.

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

---

# 2026-07-04 (QA Session 1 - first-pass stack live + G1 calibrated n=10)

First real pipeline runs. Installed the first-pass ML stack (py3.12,
`.venv-upscale` = torch 2.11+cu128 + spandrel on RTX 5070, `.venv-metrics` =
pyiqa 99 metrics); gallery-dl + imagehash on 3.14. Ran 10 images intake ->
first-pass -> operator-approved into `2.First Pass Done` (fiora2 + a 9-image
Found-original batch), full manifest audit trails. G1 calibrated n=10
(realesrgan-x4plus-anime fallback, USM70): MS-SSIM 0.984-0.993, LPIPS
0.047-0.144, GT LPIPS <= 0.097; tighter seeds in `AUDIT_GATES.md` 1.4 (pass
msssim >= 0.98, lpips <= 0.12).

Key: `reference_pictures` is a FR ground-truth goldmine (pHash dP=0 matches).
Found corpus (`Desktop\Found`, 121 folders) = 21 real originals + 97 still
`-pre`. Laplacian ratio is source-dependent, NOT an over-sharpen ceiling - need
a real overshoot detector.

**Do NOT redo:** the ML venv installs (done + gitignored `.venv-*/`); the 10
approved first-pass images. **Gaps:** no manifest verb for provenance/metrics
(ROADMAP NOW + spawned task); IllustrationJaNai primary weights still TODO (this
run used the ncnn fallback). **Next:** QA Session 2 - IJN primary path +
recalibrate; then the recovery campaign (149 pending, 75 `niphrimit` `-pre`).
**Queued:** artist-signature policy (watermarks on all Found originals);
LongPathsEnabled (deferred).
