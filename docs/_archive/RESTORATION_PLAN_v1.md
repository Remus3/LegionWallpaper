# Image Restoration + Re-Render Plan

Status: PLAN ONLY - implement in a fresh session. Nothing here has been run.
Authored: 2026-06-14 (Legion). ASCII-only (no em/en dashes, no smart quotes).

## Goal

Fix two distinct defects in the wallpaper set now living in
`C:\Users\Administrator\Pictures\` (files numbered `0.png` .. `287.png`,
all currently 2560x1440):

1. AI-generation artifacts baked into the SOURCE art - malformed irises/eyes,
   off skin texture, weird highlights, stray generative artifacts.
2. Softness / slight out-of-focus introduced by MY upscale pipeline on the
   most recent batch (it was sharp in the source, soft in the output).

Deliver corrected 2560x1440 PNGs that replace the matching numbered files,
non-destructively (stage + review before overwrite).

## Root cause of the softness (own up to it)

Two batches were processed with different pipelines:

- `265.png` .. `280.png` (batch 1): ESRGAN realesrgan-x4plus x4 -> ONE
  HighQualityBicubic downscale to fit 1440. Mostly single-resample. Less soft.
- `281.png` .. `287.png` (batch 2): ESRGAN x4 -> bicubic UP to 8K (7680w) ->
  bicubic DOWN to 2560x1440. This is the softness culprit:
  - Double resample (up then down) compounds blur.
  - The bicubic up-to-8K invents zero real detail - it just interpolates a
    4096-wide ESRGAN output to 7680, then throws it away on the downscale.
  - No post-downscale sharpening (no unsharp mask) to restore acutance.
  - Worst offenders: smallest sources, most aggressive net upscale:
    `281.png` (source 1024x683), `286.png` (source 1167x685).

Lesson for the new pipeline: never up-then-down resample; upscale ONCE to >=
target, downscale ONCE with Lanczos, then a light unsharp mask. Drop the 8K
intermediate entirely (it was a no-op for detail and a net loss for sharpness).

## Two independent fixes (do both, gate each)

### Fix A - recover real high-res sources (attacks softness AND artifacts)

The originals in `need up` are GONE (folder is empty as of authoring). But the
filenames encoded their provenance: these are DeviantArt deviations. The
`-pre` suffix = DeviantArt PREVIEW (small) crop; `-fullview` = larger. Many
were saved at the tiny preview size, which is exactly why upscaling softened
them. Pulling the real full-resolution original removes the need to upscale a
postage stamp - and the artist's full-res upload often has fewer compression
artifacts.

Autonomous recovery path (preferred order):
1. Parse artist + deviation token + champion from the filename (table below).
2. Resolve the deviation page URL, then download the original/fullview with
   `gallery-dl` (handles DeviantArt natively, incl. original-quality with an
   optional OAuth client_id/secret in its config).
3. If the URL cannot be reconstructed from the token, reverse-image-search the
   PROCESSED `NNN.png` to find the source page, then gallery-dl it:
   - SauceNAO API (best for art; returns DeviantArt/Pixiv links; free key, rate
     limited) - https://saucenao.com/
   - Fallback: Google Lens / Yandex (manual or via a vision search API).
4. Only if no better source exists, keep the current source resolution and rely
   on Fix B + Fix C to clean and re-render.

Tools to install (none present except python+Pillow+requests+ffmpeg):
- `gallery-dl`  -> `py -m pip install gallery-dl`  (DeviantArt source pull)
- optional DeviantArt OAuth app for true-original downloads (else fullview).

### Fix B - face/eye restoration (attacks the AI artifacts directly)

Even the full-res original is AI-generated and may have malformed eyes/skin.
Run a face-restoration model that specifically repairs eyes, irises, and skin:
- CodeFormer (best eye/iris repair; fidelity weight `w` tunable 0.5-0.8 to keep
  likeness) - https://github.com/sczhou/CodeFormer
- or GFPGAN (simpler; bundled as `--face_enhance` in the Real-ESRGAN *python*
  package, which is NOT the ncnn exe we have).

Install options on this box (RTX 5070, Vulkan + CUDA capable):
- PyTorch route: `py -m pip install torch --index-url <cuda build>` then
  CodeFormer repo + weights. Heaviest but best quality and GPU-accelerated.
- NCNN route: a `codeformer-ncnn-vulkan` / `gfpgan-ncnn` prebuilt binary, same
  family as the existing `C:\Tools\realesrgan\realesrgan-ncnn-vulkan.exe`. No
  python deps. Prefer this for consistency if a trusted build is available.

Gate it: face restoration can alter likeness/style. Run on a COPY, diff
before/after, and only keep where it clearly fixes eyes without flattening the
art. Non-face artifacts (background highlights, body skin texture) are NOT
fixed by face models - flag those for manual inpainting or accept them.

### Fix C - the corrected re-render pipeline (replaces the soft one)

Per image, in ONE script (Pillow is already installed - no ImageMagick needed,
Pillow has LANCZOS + UnsharpMask):

1. Input = best available source (Fix A original, else current source).
2. AI upscale ONCE with the ncnn exe to the smallest scale that lands >= 2560
   wide. For these ILLUSTRATIONS prefer `realesrgan-x4plus-anime` (sharper on
   splash-art line/flat-color than the photo `realesrgan-x4plus`); A/B both.
   - source >= 1280w: x2 anime model is plenty (1280->2560).
   - source < 1280w: x4, but expect residual softness - Fix A is the real cure.
3. (optional) Fix B face restoration on the upscaled result.
4. Downscale ONCE to cover 2560x1440 with `Image.LANCZOS`, center-crop to exact
   2560x1440 (these are ~16:9 already; crop is minimal).
5. Light unsharp mask to restore acutance:
   `ImageFilter.UnsharpMask(radius=1.2, percent=80, threshold=2)` - tune per
   image; do NOT over-sharpen (halos).
6. Save PNG to a STAGING dir `need up\restored\NNN.png` - do not touch Pictures.

NO bicubic up-to-8K step. NO double resample. One up (ESRGAN), one down
(Lanczos), one USM.

## Source manifest (Pictures number -> provenance)

The `need up` originals are deleted, so this table (reconstructed from the
processing session) is the ONLY recovery key. Tokens are DeviantArt deviation
ids. Batch 2 (281-287) is the soft set - prioritize it.

| # | champion / title | artist | deviation token | source px | batch | notes |
|---|---|---|---|---|---|---|
| 265 | Akali | youngarthy | dm7vs7f | 1191x671 | 1 | name literally "arte feita por ia" (AI) |
| 266 | Camille | vexxsoul | dm5uzb7 | 1280x721 | 1 | |
| 267 | (unknown) | (none in name) | dm7e0ad-96e90863 | 1920x1080 | 1 | random-hash name; reverse-search only |
| 268 | Elementalist Lux | pebano1 | dm7tqlf | 1920x1080 | 1 | |
| 269 | Elise | pebano1 | dm73zmw | 1920x1080 | 1 | |
| 270 | High Noon Ashe | pebano1 | dm7cb0t | 1920x1080 | 1 | |
| 271 | Inkshadow Kai'Sa | pebano1 | dm7m9lz | 1920x1080 | 1 | |
| 272 | Jinx (Neon) | pebano1 | dm4bmdy | 1920x1080 | 1 | |
| 273 | Jinx Velvet Neon Bloom | vexxsoul | dlqik29 | 1280x720 | 1 | |
| 274 | LeBlanc | pebano1 | dm4l0za | 1920x1080 | 1 | |
| 275 | LeBlanc (The Deceiver) | aniaixxx | dm74hbc | 1920x1072 | 1 | |
| 276 | Nightmare Ahri | pebano1 | dm4uer9 | 1920x1080 | 1 | |
| 277 | Prestige Coven Akali | pebano1 | dm76tlz | 1920x1080 | 1 | |
| 278 | Shadowborn Fury | vexxsoul | dm5z7cn | 1280x721 | 1 | |
| 279 | Syndra (Coven) | kintanki1 | dm6e10u | 1920x1098 | 1 | |
| 280 | Zed | pebano1 | dm76bvl | 1920x1080 | 1 | |
| 281 | Ahri | amazing82 | dm8a32j | 1024x683 | 2 | SOFTEST - smallest source |
| 282 | Ashe | stellastria | dm78pds | 1194x669 | 2 | soft |
| 283 | Gothic Jinx 02 | hriful | dm8ng1v | 1192x670 | 2 | soft |
| 284 | Gwen | smalltavernx | dlv6t7c | 1194x669 | 2 | soft |
| 285 | Gwen (alt) | smalltavernx | dlv6xhr | 1194x669 | 2 | soft |
| 286 | Prestige KDA Ahri | taiarts | djp5u7j | 1167x685 | 2 | very soft - small source |
| 287 | Prestige Star Guardian Syndra | pebano1 | dm83o0p | 1920x1080 | 2 | soft from 8K roundtrip |

DeviantArt URL shape for gallery-dl seeds:
`https://www.deviantart.com/<artist>/art/<slug>-<numericId>`
The fullview CDN token in the filename (e.g. `dm8a32j`) maps to the deviation;
when the slug/numeric is unknown, search `deviantart.com <artist> <champion>`
or reverse-search the processed PNG via SauceNAO to get the exact URL, then
`gallery-dl <url>`.

## Implementation steps (new session)

1. Preflight: `py -m pip install gallery-dl`; confirm Pillow LANCZOS +
   UnsharpMask import; decide CodeFormer route (CUDA vs ncnn); confirm internet
   reachability. The ncnn upscaler is at
   `C:\Tools\realesrgan\realesrgan-ncnn-vulkan.exe`
   (models: realesrgan-x4plus, realesrgan-x4plus-anime, realesr-animevideov3-x2/x3/x4).
2. Build a working manifest CSV from the table above:
   `need up\manifest.csv` with columns
   num, champion, artist, token, source_url(blank), recovered_path(blank), status.
3. Source recovery (Fix A): for each row, resolve URL (token seed ->
   gallery-dl; else SauceNAO on `Pictures\NNN.png`), download original to
   `need up\sources\NNN.<ext>`, record actual resolution + url in manifest.
4. Re-render (Fix C) on the recovered source (fallback: current source) ->
   `need up\restored\NNN.png`. Use the anime model for these illustrations;
   A/B against the photo model on 2-3 images first and pick the sharper.
5. Artifact pass (Fix B) where eyes/skin are still malformed; CodeFormer w
   tuned for likeness; keep only clear wins.
6. Review gate: generate a contact sheet or side-by-side
   (original-source | old Pictures NNN | restored) for visual sign-off BEFORE
   any overwrite. Do not auto-replace.
7. On approval: copy `restored\NNN.png` over `Pictures\NNN.png` (verify each is
   exactly 2560x1440 first). Keep `restored\` + `sources\` as backup.

## Acceptance criteria

- Every replaced file is exactly 2560x1440 PNG (re-run the dimension audit:
  width==2560 and height==1440 for all, 0 off-spec).
- Restored images are visibly sharper than the batch-2 outputs at 100 percent
  (no soft/out-of-focus look) without sharpening halos.
- Eyes/irises corrected where Fix B was applied; no likeness destruction.
- Non-recoverable items (no better source, artifact not face-localized) are
  listed in the manifest with status=accepted + reason - no silent skips.
- Originals/sources retained; replacement was review-gated, not automatic.

## Risks / caveats

- These are AI-generated fan art - there is no artifact-free "ground truth".
  Full-res recovery reduces NEW (upscale) softness and compression artifacts
  but the art's own generative flaws may persist; Fix B is the only lever there
  and it can alter style. Gate it.
- DeviantArt original-quality download may need an OAuth app; fullview is the
  no-auth fallback and is usually still much larger than the saved `-pre`.
- Token-to-URL reconstruction is unreliable; treat reverse-search (SauceNAO) as
  the dependable resolver and the token/artist as a seed only.
- `267.png` has no provenance in its name (random hash) - reverse-search only;
  may be unrecoverable.
- CodeFormer/GFPGAN via PyTorch pulls a large CUDA stack; prefer an ncnn build
  for footprint/consistency with the existing toolchain if one is trusted.
- Respect rate limits (SauceNAO free tier) and DeviantArt ToS for downloads.

## File locations

- Targets to fix: `C:\Users\Administrator\Pictures\265.png` .. `287.png`
  (batch 2, 281-287, is the priority soft set).
- This plan: `C:\Users\Administrator\Desktop\need up\RESTORATION_PLAN.md`
- New working dirs (create): `need up\sources\`, `need up\restored\`,
  `need up\manifest.csv`
- Upscaler: `C:\Tools\realesrgan\realesrgan-ncnn-vulkan.exe`
- Python: `C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe`
