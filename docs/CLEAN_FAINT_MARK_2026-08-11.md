# Faint-mark FLAG (gate v4) - the last 4 recall misses - 2026-08-11

Closes the remainder of `docs/CLEAN_DETECTOR_RECALL_2026-08-11.md`. That census
found 14 false negatives; the centre-overlay detector (LEDGER 93-96) took 11 of
them. This is the other 3 - plus `110-cleanup`, an overlay case whose score
(0.121) sits under the 0.15 overlay flag, so it was still `clean` as well.

## The finding that made it cheap

The census recorded two of the four as having "no box at all". That was true of
the MISSED REGION at the sweep floor it used, not of the frame - and one of the
two turns out to be boxed lower down. Swept to conf 0.02, all four carry a YOLO
box on the mark itself:

| slug | mark | box conf | prior verdict |
|---|---|---|---|
| `110-cleanup` | SMALLTAVERNX.DEVIANTART.COM credit line | 0.1366 | clean/no_detections |
| `p2402-kda-evelynn-by-namakx-dgykw2q-pre` | NAMAKXIN P&M2402 wordmark | 0.1228 | clean/no_detections |
| `karthasbasefinal-by-alexflores-d7q5tbt-fullview` | "Alex Flores" brush signature | 0.1135 | clean/lol_logo |
| `dragon-slayer-pantheon-by-alexflores-d7fr57n-fullview` | "Alex Flores" brush signature | **0.0522** | clean/lol_logo |

So this never needed a new model. The production floor is `conf=0.35`, and every
one of these was thrown away before `gate_decision` saw it.

## The rule

`detect_image` now runs YOLO ONCE at `FAINT_CONF_MIN` and splits the result at
`DETECT_CONF` into `yolo` (what the confident rules have always seen) and
`faint`. The split is free rather than a second inference: NMS never suppresses
a box with a weaker one, so the sweep filtered back to 0.35 reproduces the old
run - measured identical on 39 of 39 firstdones. `boxes` and `confs` exclude the
faint tier, so mask geometry, `conf_max` and `area_pct` are byte-unchanged.

`gate_decision` applies the flag as a POST-PASS over the v3 ladder, not as
another ordered rule, and that is the whole safety argument. Two of the four
misses carry no confident box, so an ordered placement would have to sit above
the `n == 0` rule - which is above `bottom_banner` / `corner_mark` too, and
**7 currently-`auto` images on the live corpus carry a qualifying faint box**.
Those 7 would have silently demoted to `qa`. As a post-pass the rule is provably
incapable of it: it reads the v3 verdict and only ever rewrites `clean` -> `qa`.
It also leaves an existing `qa` reason alone (21 live rows), because whatever
the ladder already named is more specific than `faint_mark`.

## The two calibrated constants

**`FAINT_CONF_MIN = 0.05`.** Swept the whole live 302-image corpus at 0.05 and
counted the marginal effect on the `clean` set:

| floor | clean rows flipped | real | false |
|---|---|---|---|
| 0.10 | 3 | 3 | 0 |
| 0.07 | 4 | 3 | 1 |
| 0.05 | 5 | 4 | 1 |

0.05 ships because it is the only setting that reaches the 0.0522 signature, and
nothing else in the stack can (see the dead ends below). The price is ONE extra
image in a ~67-image human queue. 0.10 is the zero-false alternative and is one
constant away; the flag can never edit anything unattended either way.

**`FAINT_MIN_W_FRAC = 0.05`.** The raw faint tier is too noisy to route on, so
one prior narrows it: a credit line, URL or signature is a WIDE thing. Box width
over frame width, over every `clean` firstdone carrying a sub-floor box:

```
real marks   0.076  0.100  0.157  0.176
art texture  0.009  0.021  0.033
```

0.05 sits inside that gap rather than on its edge. The prior is **not** universal
and is not claimed to be. It fails in both directions, measured: 4 of 28 live
`auto` boxes and 2 of 65 `qa` boxes are small square-ish marks it would reject,
and the one false flag it lets through is 0.154 of frame width - too wide for the
prior to catch. It cheaply narrows a noisy tier; it is not a classifier.

## Result on the live corpus

`--corpus firstdone`, all 302 `_firstdone` images:

```
gate v3   26 auto / 62 qa / 214 clean
gate v4   26 auto / 67 qa / 209 clean
```

**Exactly 5 rows change, all `clean` -> `qa/faint_mark`, no `auto` lost.**
Every one was cropped and looked at:

| slug | verified |
|---|---|
| `110-cleanup` | REAL - `SMALLTAVERNX.DEVIANTART.COM` reads plainly at 2x |
| `p2402-kda-evelynn-...` | REAL - `NAMAKXI N` over `P & M 2402`, fully legible |
| `karthasbasefinal-...` | REAL - "Alex Flores" signature, bottom-right |
| `dragon-slayer-pantheon-...` | REAL - the same signature, same corner |
| `dbwtlkx-eeb94ce2-...` | **FALSE** - blurred stonework, top-left, no mark |

On the KEEP side, `--corpus cleaning` (the 21 gated slugs) produces **zero**
`faint_mark` rows and all 14 `auto` proposals stand, so the measured
0-false-positive precision is untouched.

## Dead ends, measured - do not redo

* **Tiled / SAHI-style inference at native resolution.** The obvious fix for a
  small object under a downsampling detector, and it is WORSE here, not better.
  Over 1024px tiles at 25 percent overlap: `karthasbasefinal`'s signature scored
  0.1135 full-frame and vanished entirely in the tiles; `p2402` LOST its 0.1228
  wordmark box and gained a 0.4613 box on unrelated art in the top-left. The
  weights were trained on whole frames and the context is load-bearing.
* **EasyOCR on the signature.** Cropped the corner and read it at 1x, 2x and 4x
  Lanczos. Every scale returns either nothing or garble at confidence 0.00
  (`'/^'`, `'4'`). Brush script is not text to this reader at any scale.
* **A per-artist signature template**, the `lw_clean_overlay` playbook. Not
  built, and deliberately: the corpus holds exactly 2 alexflores images and both
  are already known, so a template stacked from one and scored on the other is a
  lookup table for a set of size 2, not a detector. The centre-overlay case
  earned that method with 32 frames across many artists.

Reproduce:

```
C:\Tools\lw-clean\venv\Scripts\python.exe tools\lw_clean_detector_probe.py --corpus firstdone --out ops\runtime\clean_recall_census_gatev4.json
```
