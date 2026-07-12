"""M1 weapon-gate calibration harness (throwaway; design_weapon.md sec 6).

Cross-venv, three phases (run in order):
  crop    (.venv-gen)     : DWPose -> weapon_roi bbox -> padded ROI crop, both
                            wrists, for 19 official skins (GOOD) + all localizable
                            gen candidates (BAD). Writes crops/ + crops.json.
  score   (.venv-metrics) : WeaponClipScorer (ViT-L-14-quickgelu/openai) scores
                            every crop -> weapon_cos/weapon_off/lap_var. scores.json.
  analyze (any)           : per-source representative = max-weapon_cos wrist crop;
                            set T_weapon/T_wmargin at the good/bad midpoint and
                            report separation (good PASS / bad REJECT counts).

Not committed to tools/ - the durable artifacts are the config floors + a
GEN_RETUNE.md note. Faithful to production: the gate crops the same padded ROI.
"""
import glob
import json
import os
import sys

ROOT = r"C:\LegionWallpaper"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

OUT = os.path.join(ROOT, "images", "_gen_scratch", "weapon_calib")
CROPS = os.path.join(OUT, "crops")
CROPS_JSON = os.path.join(OUT, "crops.json")
SCORES_JSON = os.path.join(OUT, "scores.json")

GOOD_GLOB = os.path.join(ROOT, "tools", "models", "lora_datasets", "vayne", "*.jpg")
BAD_DIRS = ["vayne-controlnet-proto", "sweep_cn", "exp2_skel01", "exp3_clean", "exp4_volume"]
# derived/non-candidate images to skip in the candidate dirs
BAD_SKIP = ("skel", "overlay", "mask", "contact", "_skeleton")


def _label_for(path):
    """A collision-free label: <parent-dir>__<stem>."""
    parent = os.path.basename(os.path.dirname(path))
    stem = os.path.splitext(os.path.basename(path))[0]
    return f"{parent}__{stem}"


def _sources():
    good = sorted(glob.glob(GOOD_GLOB))
    bad = []
    for d in BAD_DIRS:
        for p in sorted(glob.glob(os.path.join(ROOT, "images", "_gen_scratch", d, "*.png"))):
            name = os.path.basename(p).lower()
            if any(tok in name for tok in BAD_SKIP):
                continue
            bad.append(p)
    return good, bad


def phase_crop():
    from PIL import Image

    from tools.lw_gen_localizer_eval import dwpose_backend
    from tools.lw_gen_weaponfix import pad_bbox, weapon_roi_from_keypoints

    os.makedirs(CROPS, exist_ok=True)
    good, bad = _sources()
    records = []
    for label_kind, paths in (("good", good), ("bad", bad)):
        for path in paths:
            label = _label_for(path)
            try:
                out = dwpose_backend(path)
            except Exception as exc:  # noqa: BLE001
                records.append({"kind": label_kind, "label": label, "source": path,
                                "wrist": None, "crop": None, "fallback": f"error:{exc}"})
                print(f"  ERR  {label_kind:4} {label}: {exc}")
                continue
            W, H = Image.open(path).size
            img = Image.open(path).convert("RGB")
            n_ok = 0
            for wrist in ("right", "left"):
                hand = out.right_hand if wrist == "right" else out.left_hand
                roi = weapon_roi_from_keypoints(out.kp_map, wrist, (W, H), hand)
                if not roi.ok:
                    records.append({"kind": label_kind, "label": label, "source": path,
                                    "wrist": wrist, "crop": None, "fallback": roi.fallback})
                    continue
                # TIGHT weapon-centered box: square of side 2*L centered on the
                # wrist (L = forearm length px), isolating the weapon instead of
                # the whole figure the wide ROI-disc union captures on splashes.
                import math as _m
                wk = "RWrist" if wrist == "right" else "LWrist"
                ek = "RElbow" if wrist == "right" else "LElbow"
                wn, en = out.kp_map[wk], out.kp_map[ek]
                wx, wy = wn[0] * W, wn[1] * H
                ex, ey = en[0] * W, en[1] * H
                L = _m.hypot(wx - ex, wy - ey)
                box = (int(max(0, wx - L)), int(max(0, wy - L)),
                       int(min(W, wx + L)), int(min(H, wy + L)))
                crop_path = os.path.join(CROPS, f"{label_kind}__{label}__{wrist}.png")
                img.crop(box).save(crop_path)
                records.append({"kind": label_kind, "label": label, "source": path,
                                "wrist": wrist, "crop": crop_path, "bbox": list(box),
                                "fallback": None})
                n_ok += 1
            print(f"  {label_kind:4} {label}: {n_ok}/2 wrists localized")
    with open(CROPS_JSON, "w", encoding="utf-8") as fo:
        json.dump(records, fo, indent=2)
    ok = sum(1 for r in records if r["crop"])
    print(f"\ncrop: {ok} crops from {len(good)} good + {len(bad)} bad sources -> {CROPS_JSON}")


# Cleaned prompt sets (design sec 6 fallback): top-2 positives, distractors with
# the two Vayne-aesthetic confounds ("bat wings", "a blurry dark shape") dropped.
CLEAN_POS = ["a wrist-mounted mechanical repeating crossbow",
             "a crossbow mounted on an armored forearm"]
CLEAN_DIS = ["a longbow", "a sword blade", "a rifle", "an axe", "a spear",
             "an empty gloved hand"]


def _scores_path(variant):
    return SCORES_JSON if variant == "" else SCORES_JSON.replace(".json", f"_{variant}.json")


def phase_score(variant=""):
    from tools.lw_gen_qa import WeaponClipScorer

    with open(os.path.join(ROOT, "tools", "lw_gen_config.json"), encoding="utf-8") as fo:
        config = json.load(fo)
    if variant == "clean":
        config.setdefault("weapon", {})
        config["weapon"] = dict(config["weapon"])
        config["weapon"]["positives"] = CLEAN_POS
        config["weapon"]["distractors"] = CLEAN_DIS
    scorer = WeaponClipScorer(config).load()

    with open(CROPS_JSON, encoding="utf-8") as fo:
        records = json.load(fo)
    scored = 0
    for r in records:
        if not r.get("crop"):
            continue
        s = scorer(r["crop"])
        r["weapon_cos"] = s.weapon_cos
        r["weapon_off"] = s.weapon_off
        r["lap_var"] = s.lap_var
        scored += 1
    with open(_scores_path(variant), "w", encoding="utf-8") as fo:
        json.dump(records, fo, indent=2)
    print(f"score[{variant or 'full'}]: {scored} crops scored -> {_scores_path(variant)}")


def _reps(records):
    """Per source image, the localizable wrist crop with the max weapon_cos."""
    by_src = {}
    for r in records:
        if not r.get("crop") or "weapon_cos" not in r:
            continue
        cur = by_src.get(r["source"])
        if cur is None or r["weapon_cos"] > cur["weapon_cos"]:
            by_src[r["source"]] = r
    return list(by_src.values())


def _stats(vals):
    v = sorted(vals)
    n = len(v)
    if not n:
        return {}
    return {"n": n, "min": v[0], "max": v[-1], "median": v[n // 2],
            "mean": sum(v) / n}


def phase_analyze(variant=""):
    with open(_scores_path(variant), encoding="utf-8") as fo:
        records = json.load(fo)
    reps = _reps(records)
    good = [r for r in reps if r["kind"] == "good"]
    bad = [r for r in reps if r["kind"] == "bad"]

    g_cos = [r["weapon_cos"] for r in good]
    b_cos = [r["weapon_cos"] for r in bad]
    g_mar = [r["weapon_cos"] - r["weapon_off"] for r in good]
    b_mar = [r["weapon_cos"] - r["weapon_off"] for r in bad]

    print("=== weapon_cos (per-source representative = max over wrists) ===")
    print("  GOOD (official skins):", _stats(g_cos))
    print("  BAD  (gen candidates):", _stats(b_cos))
    print("=== margin (weapon_cos - weapon_off) ===")
    print("  GOOD:", _stats(g_mar))
    print("  BAD :", _stats(b_mar))

    def best_threshold(good_vals, bad_vals):
        """Threshold maximizing (good>=T) + (bad<T); midpoint of the best gap."""
        cands = sorted(set(good_vals + bad_vals))
        best_t, best_score = None, -1
        for i in range(len(cands) + 1):
            t = (cands[i - 1] + cands[i]) / 2 if 0 < i < len(cands) else (
                cands[0] - 0.01 if i == 0 else cands[-1] + 0.01)
            score = sum(1 for v in good_vals if v >= t) + sum(1 for v in bad_vals if v < t)
            if score > best_score:
                best_score, best_t = score, t
        return best_t

    t_weapon = best_threshold(g_cos, b_cos)
    t_wmargin = best_threshold(g_mar, b_mar)
    g_pass = sum(1 for r in good if r["weapon_cos"] >= t_weapon
                 and (r["weapon_cos"] - r["weapon_off"]) >= t_wmargin)
    b_rej = sum(1 for r in bad if not (r["weapon_cos"] >= t_weapon
                and (r["weapon_cos"] - r["weapon_off"]) >= t_wmargin))
    print("\n=== chosen thresholds (max-separation midpoint) ===")
    print(f"  T_weapon  = {t_weapon:.4f}")
    print(f"  T_wmargin = {t_wmargin:.4f}")
    print(f"  GOOD PASS: {g_pass}/{len(good)}   BAD REJECT: {b_rej}/{len(bad)}")
    print("\n  worst GOOD (lowest cos):")
    for r in sorted(good, key=lambda r: r["weapon_cos"])[:5]:
        print(f"    {r['label']:32} cos={r['weapon_cos']:.3f} off={r['weapon_off']:.3f} "
              f"wrist={r['wrist']}")
    print("  strongest BAD (highest cos):")
    for r in sorted(bad, key=lambda r: -r["weapon_cos"])[:5]:
        print(f"    {r['label']:32} cos={r['weapon_cos']:.3f} off={r['weapon_off']:.3f} "
              f"wrist={r['wrist']}")


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else ""
    variant = sys.argv[2] if len(sys.argv) > 2 else ""
    if phase == "crop":
        phase_crop()
    elif phase == "score":
        phase_score(variant)
    elif phase == "analyze":
        phase_analyze(variant)
    else:
        print("usage: weapon_calib.py {crop|score [clean]|analyze [clean]}", file=sys.stderr)
        sys.exit(2)
