# LW Stage-2 R&D: Semi-transparent Watermark Removal (halo-ghost problem)

Date: 2026-07-16 (status updated 2026-08-11)
Status: **glyph15+SDXL = current-best interim; proper Dekel = the zero-halo fix, DEFERRED to a fresh session (operator-chosen).**

> **2026-08-11 UPDATE - a partial Dekel now EXISTS for the DeviantArt centre
> overlay** (`tools/lw_clean_overlay.py`, `docs/CLEAN_OVERLAY_DETECTOR_2026-08-11.md`).
> Steps 1 (collection + registration) and 5 (reconstruct by inverting the
> matting equation) of section 3 are implemented; the mark's detector score
> falls 0.565 -> 0.112 median over 19 frames, 17 of them under the flag. Steps 3
> and 4 - Levin matting-Laplacian alpha and IRLS - are NOT, and the residue
> proves it: a faint ghost survives on every frame. Two measurements from that
> attempt are worth keeping: a per-pixel least-squares fit of the matting
> equation reaches only R^2 0.10 on this corpus (seed error exceeds the mark),
> and re-estimating W per pixel DIVERGES (mean post-removal score 0.149 -> 0.174
> -> 0.254) because alpha and W trade off without a prior. That is precisely the
> gap items 3-4 exist to close.
Scope: removing baked-in semi-transparent artist-credit banners (e.g.
`@namakxin PATREON.COM/NAMAKXIN`, `PEBANO1.DEVIANTART.COM`, `VEXXSOUL.DEVIANTART`)
from LoL splash art at the cleaning stage (ADR-005: signatures are REMOVED).

---

## 0. The problem, stated correctly

The corpus watermarks are SEMI-TRANSPARENT text. The compositing model is
`J = a*W + (1-a)*I` where J=observed, I=true underlying art, W=watermark color
(white for namakx), a=per-pixel alpha (0 off-text, ramps 0->~0.5-0.9 over 1-2px
at each glyph edge, high in stroke cores).

The **halo ghost is an ALPHA-ESTIMATION problem, not an inpainting problem.**
At glyph edges the alpha ramps over 1-2px. A binary mask either includes those
partial-alpha pixels (over-removal / a fill must invent them) or excludes them
(a faint halo survives). The only artifact-free fix is to recover a CONTINUOUS
alpha matte + W, then invert the equation `I = (J - a*W)/(1-a)` -- this
reconstructs the partial-alpha edge pixels EXACTLY, with no halo and no
hallucination. Every generative filler (LaMa/SDXL/FLUX) approximates or invents
the edge; only explicit (W, a) recovery removes it at the root.

---

## 1. Methods tried this session (all on the namakx cluster) + why each failed

| # | Method | Content preserved | Watermark gone | Verdict |
|---|--------|-------------------|----------------|---------|
| 1 | Block mask (dilated bbox) + SDXL | NO - hallucinates | YES | operator-rejected (invents magenta/blue; hard seam) |
| 2 | Tight top-hat stroke mask + LaMa/classical | yes | NO - halo | mask misses semi-transparent extent |
| 3 | Wide top-hat mask | no - catches art | partial | blobby (grabs bright art highlights) |
| 4 | Template alpha de-blend (median whitening, W=255) | yes | NO - faint ghost | alpha underestimated (median bg contaminated by dense text) |
| 5 | De-blend + classical/LaMa core-fill | yes | fainter ghost | opaque cores lack signal to recover |
| 6 | Pragmatic joint multi-image optimization | yes | ghost | PLATEAUS - lacks matting-Laplacian alpha + sub-pixel alignment + IRLS |
| 7 | Accurate cross-image glyph matte + LaMa | yes | faint ghost | LaMa fill over structured art is slightly off-tone |
| 8 | Accurate glyph matte + SDXL (tight) | yes | faint ghost | same edge-halo escapes the mask |
| 9 | **glyph15: accurate glyph dilated 15px + SDXL** | **yes (faithful)** | **YES (text gone)** | **CURRENT BEST** - minor smudge on dense small-text line only |

Fundamental tension confirmed: precise masks preserve content but leave a faint
halo; block masks erase the halo but hallucinate. glyph15 threads it by
expanding the ACCURATE glyph matte enough to swallow the 1-2px halo while
staying text-shaped (so SDXL continues the surroundings, not a big-block invent).

---

## 2. Current-best recipe: glyph15+SDXL (the interim, use if we ship before Dekel)

Prereq: a repeated watermark at a consistent position across a cluster (verified
for namakx: 5 imgs, all 2560x1440, bbox x~853-1706).

1. **Accurate glyph matte** from cross-image consistency (the watermark is the
   ONLY structure common to all backgrounds): for each image in the cluster crop
   the common watermark region; `whiten_i = clip((gray - medianBlur(gray,21)) /
   (255 - bg), 0, 1)`; `shape = GaussianBlur(median_k(whiten_i), 3)`. This
   isolates a clean glyph matte (proven: coverage ~8.5%).
2. **Glyph mask** = `shape > 0.09`, dilated by a **15px** ellipse (covers the
   soft halo; still text-shaped, not a rectangle). ~15-25% coverage.
3. **SDXL inpaint** on that mask via `tools/lw_clean_sdxl.py --checkpoint
   animagine` (Animagine XL 4.0). Paste-back keeps outside-mask byte-identical.
4. Known residual: the dense small-text line (`PATREON.COM/...`) merges under a
   15px dilation into a bar -> soft smudge. TUNABLE: adaptive dilation (less on
   dense small text, more on large sparse text), or a second targeted pass.

Artifacts of this session live in the session scratchpad (de_blend_template.py,
joint_deblend.py, glyph_lama.py, compute_glyph_masks.py, sweet_spot.py) - logic
captured here; those temp scripts are NOT in the repo.

---

## 3. THE PLAN: implement Dekel properly (next session, the zero-halo fix)

Dekel et al. "On the Effectiveness of Visible Watermarks" (CVPR 2017) is the
method purpose-built to estimate (W, continuous alpha) from a repeated-watermark
COLLECTION, then invert the matting equation. Pure numpy/scipy/opencv/skimage ->
**zero cu128/Blackwell/mmcv risk, runs on CPU.** Our clusters are the gift it needs.

My pragmatic joint-opt (method 6) is ~60% there. The missing 40% that kills the
halo, in order:

1. **Watermark seed:** `W_m = a*W` from the **median of image gradients** across
   the collection + **Poisson reconstruction** (background gradients cancel; the
   consistent watermark gradient survives). Do NOT fix W=255 - estimate it.
2. **Per-image sub-pixel alignment:** Chamfer-match + estimate a small
   translation/affine per image so the mark registers before pooling. Skipping
   this is a classic plateau cause with the observed position jitter (bbox y
   varied 1131-1170). LIKELY my biggest missing piece.
3. **Levin closed-form matting-Laplacian alpha** (the halo-killer - a scalar or
   Gaussian-blurred alpha will NOT work; needs the continuous sub-pixel matte).
   scikit-image + scipy.sparse give the matting Laplacian.
4. **IRLS alternating minimization** over {W, alpha, per-image I_k} with L1
   image-gradient sparsity priors on I_k and watermark-gradient priors.
5. **Final reconstruction by inverting the matting equation**, not by inpainting.
6. **Pool aggressively** to beat the 5-image limit: feed EVERY image bearing the
   same artist mark into one solve (combine clusters + one-offs of the same
   artist after alignment - Dekel needs the mark consistent, not the position).
7. **Reuse the payoff on one-offs:** a well-estimated (W, alpha) per artist is a
   reusable asset - for a lone signature, template-match to localize, then invert
   the matting equation directly (no per-image optimization needed).

Start from the rohitrango scaffold (median-gradient + Poisson + Chamfer detect
already present; it explicitly omits the matting/IRLS core - that is the hard
part you write): https://github.com/rohitrango/automatic-watermark-detection

Same-day fallback baseline for ONE-OFF signatures (no cluster to pool):
**SLBR** https://github.com/bcmi/SLBR-Visible-Watermark-Removal (CLWD weights,
torch>=1.0, no mmcv - runs on 2.11 cu128; but trained on 256px LOGOS so expect
residue/blur out-of-distribution; `test_custom.py`). WDNet is a distant 3rd
(same logo distribution, fiddlier). MorphoMod/RIRCI/WMFormer rejected (hallucinate
or no weights). Segmentation helper if wanted: Diffusion-Dynamics/watermark-segmentation
(MIT, SegFormer, gives a soft-mask prior to feed the solve).

---

## 4. Data notes for next session

- **namakx cluster (5, white text):** dfz5w2g, dfzlox4, dfzypoo, dfzypou, dfzypp1.
  Region x[848:1712] y[1122:1430] on 2560x1440. Same "@namakxin PATREON.COM/NAMAKXIN".
- **pebano1 cluster:** dark-cosmic-ahri, inkshadow-kai-sa, prestige-coven-xayah,
  xayah-by-pebano1, evelynn, seraphine (blue-ish "PEBANO1.DEVIANTART" - estimate W per-cluster).
- **Other repeated/one-off:** vexxsoul (aatrox/fierce/riven/the-ruined-king),
  smalltavernx, slimshadywallpaper, kintanki1, michalivan(puppetworks), hriful, etc.
- **The 21 auto slugs are staged in images/3.Cleaning Scratch** with the failed
  block-SDXL as a working milestone (needauth rejected during wrap). Reprocess
  each with the Dekel result: save-working --from <dekel> --tool dekel + submit.
- **Not watermarks (do NOT process):** caitlyn-love-confession (@ false positive),
  vayne3 (carved-stone art false positive). Both re-verified 2026-08-11: the gate
  now returns `clean` on each, and the census found no mark in either frame.
  **CORRECTED 2026-08-11:** `the-ruined-king-viego` was listed here as "LoL logo,
  keep". The wordmark KEEP is right, but the frame ALSO carries a
  `(C) VEXXSOUL.DEVIANTART.COM` centre overlay that the gate missed entirely
  (best YOLO box 0.144, under the 0.35 floor) - it is a false NEGATIVE, not a
  false positive. See `docs/CLEAN_DETECTOR_RECALL_2026-08-11.md`.
