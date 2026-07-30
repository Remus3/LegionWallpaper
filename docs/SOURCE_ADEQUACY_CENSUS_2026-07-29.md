# Source-adequacy census - 2026-07-29

Companion to `ANATOMY_CENSUS_2026-07-29.md`. Same root cause, larger blast radius,
and unlike the anatomy question this one is objectively measurable with no
perceptual judgement required.

## The root cause, stated once

G1 scores the output against ITS OWN SOURCE. `ms_ssim`, `lpips`, `dists`,
`lap_ratio`, `halo_pct` and `band_delta` are all relative measures. So any defect
or deficiency that is PRESENT IN THE SOURCE is invisible to the gate: a faithful
upscale of an inadequate source scores near 1.0 and PASSes.

The anatomy census found one instance of this (implausible figure geometry). The
census below finds a second, affecting far more images.

## Method

Read every `images/2.First Pass Done/*/manifest.json` and pulled the last
transition carrying an `audit.upscale_audit` block - the recorded `src_dims`,
`out_dims`, verdict, crop flag and area loss. Manifest-only; no model, no pixels.

288 manifests. 276 carry an `upscale_audit`.

## Finding 1 - 105 of 276 approved images came from a source below the target

The product promises an approved 2560x1440 PNG. 105 of 276 (38 percent) were
produced from a source smaller than that in at least one dimension.

The 12 smallest sources, all verdict PASS:

| src dims | upscale factor | cropped | slug |
|----------|----------------|---------|------|
| 800x450 | 3.20x | no | image3 |
| 1024x576 | 2.50x | yes | ahri-league-of-legends-by-swanrs-dmekbfn-fullv |
| 1024x576 | 2.50x | yes | kayle-new-splash-by-su-ke-d85w02l-fullview |
| 1024x576 | 2.50x | yes | riot-girl-tristana-by-miasus-da2tbz2-fullview |
| 1024x577 | 2.50x | no | eclipse-leona-promo-art-by-su-ke-dct4fz0-fullv |
| 1163x654 | 2.20x | yes | true-damage-qiyana-league-of-legends-by-snatti |
| 1164x655 | 2.20x | yes | gentleman-gnar-league-of-legends-by-miasus-d8z |
| 1173x660 | 2.18x | yes | crystalis-motus-janna-by-niphrimit-dl3e4na-pre |
| 1184x666 | 2.16x | yes | league-of-legends-a-death-knot-by-venom-rules- |
| 1192x670 | 2.15x | no | astronaut-gnar-and-poppy-splash-art-league-of- |
| 1192x670 | 2.15x | no | brand-by-michalivan-d5rvdrt-pre |
| 1192x670 | 2.15x | no | league-of-legends-shan-hai-lillia-by-kevin-gli |

`image3` at 800x450 carries roughly one tenth the true pixel information of a
native 2560x1440 frame, and G1 scored it PASS - correctly, because it IS a
faithful 3.2x rendering of a 800x450 image. The metric is not wrong; it is
answering a different question than "is this wallpaper-grade".

This matters more than the anatomy finding because it is deterministic. An
upscale-factor precondition needs no model, no keypoints and no perception - just
`src_dims` against the 2560x1440 target, which the manifest ALREADY records.

Note this is a QUALITY CEILING claim, not a claim that all 105 look bad. Several
are probably fine. The defect is that nothing in the ladder ever asked.

## Finding 2 - 12 approved images have no recorded G1 audit at all

These reached `2.First Pass Done` with no `upscale_audit` in any transition, so
there is no record of what model ran, at what scale, from what source dimensions,
or what the gate said:

```
dark-cosmic-ahri-by-pebano1-dlnxav6-pre
dfz5w2g-8ba7345b-5776-4d83-b939-4ca7d045f545
dfzlox4-7e2bdc64-36ce-41fa-80b0-c83f97fdf5f5
dfzypoo-482973ff-dfb0-44e4-a90c-386714d27faf
dfzypou-30bef263-c754-4a26-9797-484757b1c4cf
dfzypp1-251c5c37-e25f-496e-a9a6-4900304e6fa5
dgfkw05-0dca21c7-cf08-4dee-9a8e-4045dc98c451
dgk8f8n-398197d0-65d6-4299-8f0b-afdd9021c395
dgk8f92-bc10d7a7-f520-4b4f-ad86-ac70f6d50293
fiora2
inkshadow-kai-sa-by-pebano1-dm7m9lz-fullview
p08e8-shadow-hunter-vayne-by-namakx-dg9ydp9-pre
```

These are LEGACY, not a live bug. Verified: all 12 were created 2026-07-04 or
2026-07-05, predating both ADR-004 (the IllustrationJaNai V3 DAT2 promotion, also
2026-07-05) and the `upscale_audit` block. The current code path in
`tools/lw_first_pass.py:process_slug` always writes `upscale_audit` on the normal
route; the only annotate that omits it is the `crop_heavy` HOLD path, and a HELD
slug never reaches `2.First Pass Done`. So no fix is owed - a BACKFILL is.

### Finding 2b - 10 of those were built with the FALLBACK upscaler

Cross-referencing the `SAVE_WORKING` tool per slug makes the 12 much more
interesting. Corpus-wide upscaler tally across all 288:

| upscaler | count |
|----------|-------|
| `lw_first_pass` (audit records the model) | 171 |
| `4x_IllustrationJaNai_V3detail_DAT2_28k_bf16.safetensors` | 116 |
| `realesrgan-x4plus-anime` | 10 |

Those 10 realesrgan images are exactly 10 of the 12 with no audit:

```
dfz5w2g-8ba7345b-5776-4d83-b939-4ca7d045f545
dfzlox4-7e2bdc64-36ce-41fa-80b0-c83f97fdf5f5
dfzypoo-482973ff-dfb0-44e4-a90c-386714d27faf
dfzypou-30bef263-c754-4a26-9797-484757b1c4cf
dfzypp1-251c5c37-e25f-496e-a9a6-4900304e6fa5
dgfkw05-0dca21c7-cf08-4dee-9a8e-4045dc98c451
dgk8f8n-398197d0-65d6-4299-8f0b-afdd9021c395
dgk8f92-bc10d7a7-f520-4b4f-ad86-ac70f6d50293
fiora2
inkshadow-kai-sa-by-pebano1-dm7m9lz-fullview
```

`realesrgan-ncnn-vulkan x4plus-anime` is the documented FALLBACK upscaler; ADR-004
settled `IllustrationJaNai V3 detail DAT2` as primary on a golden A/B sweep. So
these 10 carry BOTH defects at once - they were produced by the inferior upscaler
AND have no gate record proving what they scored. They are the corpus's clearest
reprocessing candidates, and the reopen procedure for a done slug already exists.

The remaining 2 of the 12 (`dark-cosmic-ahri-...-dlnxav6-pre` via `ijn-v3detail-dat2`,
and `p08e8-shadow-hunter-vayne-...-dg9ydp9-pre` via `lw_upscale`) used acceptable
upscalers under older tool names and are audit-gaps only.

NOT ACTED ON IN THIS RUN, deliberately: reprocessing 10 approved slugs mutates
corpus state, and the final `APPROVE_FIRST` step is an operator judgement on image
quality by design (`actor=operator` in every manifest). Regenerating them would
leave 10 images sitting in the approval queue on the operator's behalf. That is a
decision to hand over, not to take unattended.

## Finding 3 - one FAIL-verdict image was approved

| slug | src dims | verdict | reason |
|------|----------|---------|--------|
| wallpapersden-com-elise-8k-league-of-legends-7680x | 7680x4324 | FAIL | `lpips 0.224447 > fail 0.2` |

This one is a DOWNSCALE from 8K, so it is the opposite problem - the source was
ample and the pipeline lost perceptual similarity anyway. An operator approval over
a hard FAIL is legitimate (the operator is the final authority) but it is currently
INDISTINGUISHABLE in the manifest from an approval over a PASS. An override should
be recorded as an override.

Verdict distribution across the 276: PASS 178, FLAG 97, FAIL 1. Cropped: 59 yes,
217 no.

## Proposed rulings - NOT self-approved, these need operator intent

1. **Add a source-adequacy precondition to G1.** Deterministic, cheap, testable,
   no new dependency, and computable from data the manifest already records. The
   open question is the POLICY, which is the operator's call: is a 2.5x upscale
   from 1024x576 acceptable, and does an inadequate source mean FLAG (surface it)
   or FAIL (refuse it)? A threshold guess here would repeat the mistake the
   anatomy census caught, so it is not being guessed.
2. **Backfill the 12 missing audits** or mark them explicitly as pre-audit legacy.
   Per this project's data-fix discipline, preventing future gaps is not enough -
   the existing rows need correcting too.
3. **Record operator overrides explicitly** so an approval over FAIL is
   distinguishable from an approval over PASS.

## Do-not-redo

- Do not "fix" this by loosening or retuning the G1 fidelity metrics. They are
  correct at their job. The gap is a MISSING ABSOLUTE precondition, not a
  miscalibrated relative one.
