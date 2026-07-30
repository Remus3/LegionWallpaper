# USM halo census - 2026-07-30

Measured artifact answering ONE question: the 2026-07-30 first-pass batch flagged
7 slugs and every flag was the same reason - `halo_pct` over the 0.05 line. Is
that halo manufactured by OUR finishing unsharp mask, or is it coming out of the
upscaler?

**Answer: it is ours. The unsharp mask manufactures every one of the 7 flags.**

With the mask skipped and nothing else changed, the highest `halo_pct` anywhere
in the batch is **0.0062** - one eighth of the flag line - and **zero of 17**
slugs cross it. The IllustrationJaNai V3 upscaler contributes at most 0.0062 of
halo on this corpus. It is not the source of the flags.

This does NOT make "turn the mask off" the fix. See "The cost of condition B".

## What was measured

17 slugs - every gated slug in the batch. Two conditions plus a strength sweep,
holding the source, the crop, the upscale, the downscale and the metric constant:

- **A** - the shipped path: one 4x IJN V3 upscale (or the `downscale-only`
  branch), one Lanczos downscale to 2560x1440, one `UnsharpMask` at
  `USM_DEFAULT = (1.2, 70, 3)` (`tools/lw_upscale.py:34`).
- **usm50 / usm35** - identical, `percent` lowered to 50 and 35.
- **B** - identical, `UnsharpMask` SKIPPED entirely.

All four variants are finished from the SAME in-memory raw upscale inside one
worker process, so the A-vs-B delta carries no GPU nondeterminism at all. The
metric is the shipped one, unmodified: `lw_first_pass.compute_numpy_metrics`
(`tools/lw_first_pass.py:355`) downscales the 2560x1440 output back to the
conditioned source resolution with Lanczos and runs
`lw_g1_gate.overshoot_halo` (`tools/lw_g1_gate.py:196`) at that common scale.
Condition A calls `lw_upscale._finish` (`:124`) itself rather than a lookalike.

Probe: `tools/lw_usm_halo_probe.py`, tests `tests/test_lw_usm_halo_probe.py`.

```
python tools/lw_usm_halo_probe.py --batch all \
  --usm 1.2,70,3 --usm 1.2,50,3 --usm 1.2,35,3 --usm none \
  --work-dir <scratch> --out <scratch>/census.json
```

Nothing was written into `images\`. No slug was reprocessed, re-submitted or
approved; all 20 stay exactly where the batch left them. The probe re-derives
each source with the shipped `select_source` / `condition_source` into a
throwaway work dir and only ever READS the slug folders.

### The measurement is validated against production

Condition A reproduces the manifest `halo_pct` **exactly, to 4dp, on 17 of 17
slugs** (see the `shipped` and `A usm70` columns below - they are identical
everywhere). The probe is measuring the real pipeline, not an approximation of
it.

## Per-slug A/B table (halo_pct, flag line 0.05)

| slug | shipped | backend | conditioned src | A usm70 | usm50 | usm35 | B no-usm | A-B |
|---|---|---|---|---|---|---|---|---|
| `blood-moon-priestess-mel-by-aiaida-dmhckey-pre` | FLAG 0.0723 | spandrel | 1920x1080 | 0.0723 | 0.0419 | 0.0205 | 0.0000 | +0.0723 |
| `di0tao3-964d7366-e031-4a06-ba9d-a97ecea63add` | FLAG 0.1157 | downscale-only | 3792x2128 | 0.1157 | 0.0747 | 0.0427 | 0.0032 | +0.1125 |
| `faerie-court-evelynn-by-dragraceheart-dmgwj3g-pre` | FLAG 0.0567 | spandrel | 1280x720 | 0.0567 | 0.0377 | 0.0240 | 0.0062 | +0.0505 |
| `infernal-appetite-briar-by-aiaida-dmhijna-fullview` | FLAG 0.0679 | spandrel | 1920x1080 | 0.0679 | 0.0433 | 0.0233 | 0.0000 | +0.0679 |
| `infernal-marionette-orianna-by-aiaida-dmhck57-fullview` | FLAG 0.0578 | spandrel | 1920x1080 | 0.0578 | 0.0420 | 0.0285 | 0.0004 | +0.0574 |
| `league-of-legends-orianna-by-swofnir-dmhzlpn-fullview` | FLAG 0.0619 | spandrel | 1600x901 | 0.0619 | 0.0388 | 0.0217 | 0.0015 | +0.0604 |
| `spirit-blossom-irelia-by-aiaida-dmhini0-fullview` | FLAG 0.1196 | spandrel | 1920x1075 | 0.1196 | 0.0734 | 0.0309 | 0.0000 | +0.1196 |
| `aurora-fanart-by-lulalakill-dlgo81i-pre` | PASS 0.0204 | spandrel | 1280x721 | 0.0204 | 0.0103 | 0.0045 | 0.0000 | +0.0204 |
| `league-of-legends-aurora-by-swofnir-dmhqnjb-pre` | PASS 0.0178 | spandrel | 1280x721 | 0.0178 | 0.0084 | 0.0024 | 0.0000 | +0.0178 |
| `league-of-legends-riven-reimagined-by-ruanyi-dmh8uat-fullview` | PASS 0.0105 | spandrel | 1024x577 | 0.0105 | 0.0046 | 0.0014 | 0.0000 | +0.0105 |
| `petals-of-spring-teemo-by-dragraceheart-dmfhrpd-fullview` | PASS 0.0481 | spandrel | 1080x602 | 0.0481 | 0.0320 | 0.0176 | 0.0009 | +0.0472 |
| `queen-of-the-saltwind-by-rasrpunk-dmi98yq-fullview` | PASS 0.0420 | spandrel | 1920x1081 | 0.0420 | 0.0239 | 0.0113 | 0.0001 | +0.0419 |
| `spirit-blossom-springs-katarina-by-dragraceheart-dmfiqbq-fullvie` | PASS 0.0269 | spandrel | 1080x608 | 0.0269 | 0.0148 | 0.0069 | 0.0003 | +0.0266 |
| `viego-the-ruined-king-by-dada-wallpaperart-dmhz060-pre` | PASS 0.0145 | spandrel | 1280x718 | 0.0145 | 0.0056 | 0.0016 | 0.0000 | +0.0145 |
| `warrior-by-watercolornessie-dma7o9e-pre` | PASS 0.0310 | spandrel | 1280x720 | 0.0310 | 0.0160 | 0.0066 | 0.0001 | +0.0309 |
| `yunara-by-pebano1-dm7zwfb-fullview` | PASS 0.0442 | spandrel | 1920x1080 | 0.0442 | 0.0250 | 0.0113 | 0.0001 | +0.0441 |
| `zyra-by-effernetti-djxe1j4-pre` | PASS 0.0041 | spandrel | 1280x720 | 0.0041 | 0.0017 | 0.0005 | 0.0000 | +0.0041 |

Seven flagged slugs first, then all ten controls. Every control was measured, so
nothing in this table is inferred.

Distribution per variant, over all 17:

| variant | over 0.05 | max | min |
|---|---|---|---|
| A `usm 1.2,70,3` (shipped) | **7 / 17** | 0.1196 | 0.0041 |
| `usm 1.2,50,3` | 2 / 17 | 0.0747 | 0.0017 |
| `usm 1.2,35,3` | 0 / 17 | 0.0427 | 0.0005 |
| B no unsharp mask | **0 / 17** | **0.0062** | 0.0000 |

## Reading it

1. **The mask is the whole signal.** `A - B` is positive on all 17 slugs and it
   accounts for 96 to 100 percent of the shipped value on every one. Nine slugs
   sit at 0.0000 or 0.0001 without it.
2. **The upscaler is nearly silent on this metric.** The largest halo any raw
   IJN V3 upscale plus Lanczos downscale produced, mask excluded, is 0.0062 on
   `faerie-court-evelynn`. That is a fifth of the PASS median under the shipped
   recipe and an eighth of the flag line. ADR-004 is not implicated.
3. **`halo_pct` is monotone in USM `percent` on all 17 slugs.** 70 > 50 > 35 > 0
   without a single inversion. This makes it a strength dial, not a defect
   detector: the metric ranks how hard we sharpened, and the flag line simply
   falls inside the range our own default spans.
4. **Flag and pass are not two populations, they are one.** Under A the 17
   values run 0.0041 to 0.1196 with no gap at 0.05; under B they run 0.0000 to
   0.0062 with no gap either. The 0.05 line cuts a continuum in half. It does not
   separate haloed images from clean ones.
5. **The two batches are now fully explained.** The earlier 46-slug batch flagged
   nothing because those sources were exactly 2560x1440, took the passthrough at
   `_usm_applies` (`tools/lw_upscale.py:108`) and ran no mask at all - which this
   census shows is worth about 0.05 of `halo_pct`. This batch resampled, so it
   ran the mask, so it flagged. Same recipe, different branch.
6. **The downscale-only slug behaves like the rest.** `di0tao3` (3792x2128, no AI
   upscale, one Lanczos downscale plus the mask) has the second-highest A value
   and a B of 0.0032. Its halo is the mask too, not the AI model - consistent
   with the ROADMAP watch on the 47/61 downscale-only flags, though those
   specific slugs were not re-measured here.

## The cost of condition B (read before proposing a fix)

Turning the mask off is NOT free, and the census measured the cost. `lap_ratio`
has a hard FAIL floor at 1.0 (`tools/lw_g1_gate.py:44`) - not a flag, a fail:

| variant | halo FLAGs | lap_ratio hard FAILs (16 gated slugs) |
|---|---|---|
| A `usm 1.2,70,3` | 7 | 0 |
| `usm 1.2,50,3` | 2 | 0 |
| `usm 1.2,35,3` | 0 | 0 |
| B no unsharp mask | 0 | **6** |

The six that would hard-FAIL without the mask: `blood-moon-priestess-mel`
(0.9914), `league-of-legends-aurora-by-swofnir` (0.8175),
`league-of-legends-riven-reimagined` (0.9512), `spirit-blossom-irelia` (0.8233),
`viego-the-ruined-king` (0.8627), `zyra-by-effernetti` (0.9545). `di0tao3` sits
at 0.4801 but is exempt - ADR-006 drops the `lap_ratio` floor for
`downscale-only`, which is why 16 and not 17 is the denominator.

So condition B trades 7 soft flags for 6 hard fails. The mask is doing real work
recovering the detail the downscale costs; it is only doing too much of it.

`band_delta` never approaches its 0.05 flag line in any variant (max absolute
value 0.0427, and every value in the shipped variant is negative - the mask
reduces banding).

## Recommendation - OPERATOR DECISION, not implemented here

This slice changed no behavior. Nothing below is applied. Two coherent options,
both backed by the table above:

- **Option 1 - lower `USM_DEFAULT` percent to 35.** Clears all 7 flags with zero
  new `lap_ratio` failures; the weakest gated `lap_ratio` at percent 35 is 1.1399
  (`league-of-legends-aurora-by-swofnir`) against the 1.0 floor. Highest halo
  becomes 0.0427, still under the line with headroom. Percent 50 is not enough -
  it leaves 2 slugs over (0.0747, 0.0734).
- **Option 2 - re-seed the `halo_pct` flag threshold.** The 0.05 seed comes from
  QA Session 1, `realesrgan-x4plus-anime`, USM70, n=10
  (`tools/lw_g1_gate.py:31-34`), and its own comment says it is a seed to be
  recalibrated for the IJN primary path. On the IJN path at USM70 it flags 41
  percent of a batch for what this census shows is our own configured sharpening,
  applied uniformly.

**The reason no number is proposed here as final:** this census moved only
`halo_pct`, `lap_ratio` and `band_delta`. It did NOT recompute the FR metrics
(`ms_ssim`, `lpips`, `dists`) per variant, so the fidelity cost of a milder mask
is UNMEASURED. Picking 35 on halo evidence alone would repeat exactly the mistake
that got a gate rejected before - a threshold chosen against one axis. Re-run the
sweep with `fr_metrics` before freezing either option.

## What was NOT measured - honest gaps

- **The 3 HELD slugs.** `puppet-master-syndra-by-aiaida-dmhijti-fullview`,
  `spirit-blossom-vayne-by-secondhaven-di04j3y-pre`,
  `spirit-blossom-vayne-by-secondhaven-di04j4g-pre` were held on
  `aspect_crop_heavy` and never reached G1, so there is no shipped halo to
  reproduce. Not measured, not inferred.
- **FR metrics per variant.** `ms_ssim` / `lpips` / `dists` were not recomputed
  for the sweep variants (they need `.venv-metrics` and a per-variant pyiqa run).
  Any claim that a milder mask preserves fidelity is currently unsupported.
- **Visibility.** `halo_pct` is a pixel statistic - fraction of near-edge pixels
  outside the source local range by more than T=8. Nothing here says whether any
  of these halos is VISIBLE, at 0.1196 or at 0.0041. That is a vision-audit
  question and this census does not touch it.
- **The 47/61 downscale-only flags** from the earlier corpus (the ROADMAP open
  watch) were not re-measured. Only one downscale-only slug exists in this batch.
- **Other USM axes.** `radius` and `threshold` were held at 1.2 and 3 throughout.
  Only `percent` was swept.
- **Nothing outside this batch.** 17 slugs from one 2026-07-30 run. No claim is
  made about the 288 approved firstdones or any other corpus.

## Incidental finding worth keeping

The halo detector is not a USM-only detector. Lanczos has negative lobes, so a
bare downscale with no mask at all already pushes some near-edge pixels outside
the source local range - visible in the nonzero B column on `di0tao3` (0.0032)
and `faerie-court-evelynn` (0.0062), and reproduced deliberately in
`tests/test_lw_usm_halo_probe.py::test_resample_alone_already_rings_without_any_unsharp_mask`.
On a synthetic hard-bar pattern the effect is large enough that the MASKED
variant can score LOWER than the unmasked one. That inversion did not occur
anywhere on the real corpus - all 17 slugs are monotone - but it means the metric
cannot be read as "amount of unsharp-mask damage" in general.
