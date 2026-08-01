"""Legion Wallpaper - M1 weapon pass stage (detect -> mask -> inpaint), W1 rung.

The 4th gen-sidecar stage script. Wires the adopted DWPose localizer
(tools/lw_gen_localizer_eval.dwpose_backend) into a real, masked SDXL inpaint
re-roll of the wrist-mounted weapon region, honoring the interlock contract
(lw_gen_run.py:7-10): this stage shares ONLY the batch dir + gen_manifest.json,
it is never imported by run/qa/promote. Design of record:
docs/research/golden_designs/design_weapon.md (sec 3 W1, sec 4 mask, sec 5 API,
sec 6 identity assert, sec 7 integration).

Two modes:
  PROPOSE (wrist is None): render both-wrist ROI overlays into weapon_review/
    for the operator to pick the rig side. Mutates no candidate, inpaints
    nothing.
  FIX (wrist in {"left","right"}): per candidate, DWPose -> select side ->
    weapon_roi_from_keypoints. A fallback (no mask) routes to review with a
    sidecar + note, never inpaints. An ok ROI drives one masked inpaint roll,
    a HARD paste-back composite (out-of-mask pixels stay byte-identical), the
    outside-identity assertion, a cand_XX_wfix.png write, cand[file] advance,
    a cand_XX.weapon.json sidecar, and an atomic manifest write.

CI constraint (torch-free): this module imports ONLY stdlib + numpy + the two
torch-free project modules (lw_gen_run stage helpers, lw_gen_weaponfix geometry)
at top level. torch / diffusers / cv2 / onnxruntime are imported LAZILY inside
the real backend + real inpainter builders, which the test suite never reaches
(it injects stub backend + stub inpainter). The pure helpers
(select_wrist_inputs / paste_back / assert_outside_identity) are unit-tested
without any heavy dep.

GPU_MUTEX (ops/loop/winmutex.py), and why this module is SPLIT. This is the
second hybrid in the repo after lw_gen_run: run_pass() is a CUDA worker (the
masked SDXL rolls, in process) AND an orchestrator (the real weapon gate shells
`lw_gen_qa.py --weapon-crop` into .venv-metrics, where lw_gen_qa acquires the
same mutex). A Windows named mutex is re-entrant per THREAD, not per process
tree, so a hold spun around the fix loop - which interleaves _inpaint_roll with
active_gate(crop_pil) - would block the parent on its own child forever. The
acquisitions therefore live in _build_real_inpainter (weights onto the card) and
in the real _inpaint closure (one roll), both of which return before the gate is
ever called. run_pass itself must never acquire; _inpaint_roll must not either,
because the test suite drives it with a stub inpainter and CI has no business
taking a machine-wide lock. No fifth copy of the helper: this module already
imports lw_gen_run, runs in the same .venv-gen, and calls gr.gpu_lock directly.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np

# Allow both `python tools/lw_gen_weaponpass.py <batch>` (script mode puts tools/
# on sys.path, not the repo root) and `from tools import lw_gen_weaponpass` to
# resolve the `tools` namespace package. Mirror lw_gen_localizer_eval's shim.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import lw_gen_localizer_eval as loc  # noqa: E402
from tools import lw_gen_run as gr  # noqa: E402
from tools.lw_gen_weaponfix import (  # noqa: E402
    forearm_frame, pad_bbox, weapon_roi_from_keypoints,
)
from tools.lw_gen_weapon_assets import (  # noqa: E402  (torch-free: PIL lazy)
    affine_transplant, load_assets, pick_asset,
)
from tools.lw_gen_qa import (  # noqa: E402  (torch-free: gate logic + dataclass only)
    VERDICT_PASS, VERDICT_REJECT, WeaponScore, resolve_weapon_thresholds,
    weapon_grade,
)

# --- W1 defaults (design_weapon.md sec 5) -----------------------------------
WEAPON_PROMPT = (
    "vayne, league of legends, wrist-mounted repeating crossbow, mechanical "
    "crossbow gauntlet on forearm, bat wing crossbow limbs, silver metal, "
    "loaded silver bolt, intricate mechanical detail, masterpiece, absurdres"
)
WEAPON_NEG = (
    "sword, blade, longbow, rifle, gun, axe, spear, staff, empty hand, "
    "extra fingers, deformed weapon, worst quality"
)
WEAPON_STEPS = 32
WEAPON_GUIDANCE = 6.0

_STAGE = "wfix"

# ROI crop padding for the weapon gate (design_weapon.md sec 6: bbox padded 10%).
WEAPON_CROP_PAD = 0.10
# No console flash for the metrics-venv subprocess (Legion no-flash rule).
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# --------------------------------------------------------------------------
# Pure helpers (torch-free; unit-tested directly).
# --------------------------------------------------------------------------
def select_wrist_inputs(out, wrist):
    """Return (kp_map, side_hand) for the chosen wrist from a BackendOutput.

    The kp_map is passed through whole (the geometry reads the side keys); the
    hand list is the right_hand for wrist=="right" else the left_hand.
    """
    hand = out.right_hand if wrist == "right" else out.left_hand
    return out.kp_map, hand


def paste_back(cand_arr, inpainted_arr, mask_binary):
    """Hard paste-back: where mask_binary is True -> inpainted, else candidate.

    Outside-mask pixels are byte-identical to the candidate (np.where copies the
    candidate value verbatim). Result carries the candidate's dtype.
    """
    cand = np.asarray(cand_arr)
    inpainted = np.asarray(inpainted_arr)
    mask = np.asarray(mask_binary, dtype=bool)
    if cand.ndim == 3 and mask.ndim == 2:
        mask = mask[:, :, None]
    return np.where(mask, inpainted, cand).astype(cand.dtype)


def assert_outside_identity(orig_arr, final_arr, mask_binary):
    """Raise AssertionError unless final == orig on every pixel OUTSIDE the mask.

    The cleaning-pass-style non-regression guard (design_weapon.md sec 6): a
    weapon fix must never touch a pixel the mask did not cover.
    """
    orig = np.asarray(orig_arr)
    final = np.asarray(final_arr)
    mask = np.asarray(mask_binary, dtype=bool)
    if not np.array_equal(final[~mask], orig[~mask]):
        raise AssertionError(
            "weapon pass mutated pixels OUTSIDE the weapon mask "
            "(paste-back identity violated)"
        )


def _inpaint_roll(inpainter, cand_img, mask_pil, cand_arr, mask_binary,
                  prompt, negative, strength, seed, ip_adapter_image=None):
    """One masked re-roll -> paste-back composite array (out-of-mask identical).

    Module-level (not a loop closure) so both gate lanes share it without a
    loop-variable-binding smell. ip_adapter_image (W3, mechanism C) is threaded
    into the inpainter ONLY when non-None: W1/W2 callers omit it, so the closure
    is invoked with the exact 6-arg contract it always had (byte-identical).
    """
    if ip_adapter_image is not None:
        inp = inpainter(cand_img, mask_pil, prompt, negative, strength, seed,
                        ip_adapter_image=ip_adapter_image)
    else:
        inp = inpainter(cand_img, mask_pil, prompt, negative, strength, seed)
    if inp.size != cand_img.size:
        inp = inp.resize(cand_img.size)
    return paste_back(cand_arr, np.asarray(inp.convert("RGB")), mask_binary)


def _asset_ip_image(asset, bg=(128, 128, 128)):
    """Composite the picked crossbow crop (RGBA) onto a neutral RGB background.

    The W3 IP-Adapter concept image (design_weapon.md sec 3 W3): the clean weapon
    crop on a flat neutral field, so the image encoder keys on the crossbow, not a
    distracting background. Returns an RGB PIL image (the crop's own alpha is the
    composite matte). Torch-free: PIL only, imported lazily.
    """
    from PIL import Image

    crop = Image.open(asset.png_path).convert("RGBA")
    base = Image.new("RGB", crop.size, bg)
    base.paste(crop, (0, 0), crop)
    return base


# --------------------------------------------------------------------------
# I/O helpers (atomic writes per project hard rule).
# --------------------------------------------------------------------------
def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fo:
        fo.write(json.dumps(data, indent=2) + "\n")
        fo.flush()
        os.fsync(fo.fileno())
    os.replace(tmp, path)


def _atomic_write_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="ascii") as fo:
        fo.write(text)
        fo.flush()
        os.fsync(fo.fileno())
    os.replace(tmp, path)


def _raw_stem(cand_file):
    """The RAW candidate stem (stage suffix + .png stripped): cand_00."""
    stem = cand_file[:-4] if cand_file.lower().endswith(".png") else cand_file
    for suf in ("_wfix", "_repair", "_finish"):
        if stem.endswith(suf):
            return stem[: -len(suf)]
    return stem


def _weapon_sidecar_path(batch_dir, cand_file):
    return os.path.join(batch_dir, _raw_stem(cand_file) + ".weapon.json")


def _load_config_safe():
    """Load tools/lw_gen_config.json; {} when absent (pre-provisioning safe)."""
    path = os.path.join(ROOT, "tools", "lw_gen_config.json")
    try:
        with open(path, encoding="utf-8") as fo:
            return json.load(fo)
    except (OSError, ValueError):
        return {}


# --------------------------------------------------------------------------
# Real SDXL inpainter builder (LAZY torch/diffusers - never reached in CI).
# --------------------------------------------------------------------------
def _build_real_inpainter(config, ip_adapter=None, weapon_lora=None):
    """Construct the SDXL inpaint closure by reusing lw_gen_run's base loader.

    AutoPipelineForInpainting.from_pipe(base, controlnet=None) yields a plain
    StableDiffusionXLInpaintPipeline sharing the base weights (zero extra VRAM;
    design_weapon.md sec 5). The returned closure matches the injectable
    inpainter contract: (image, mask_image, prompt, negative_prompt, strength,
    seed, ip_adapter_image=None) -> PIL.Image.

    ip_adapter (W3 mechanism C, design_weapon.md sec 3 W3 / sec 5), when a dict
    {path, subfolder, weight_name, image_encoder_folder, scale}, loads the
    IP-Adapter weights + CLIP image encoder onto the pipe and sets the concept
    scale. Default None => byte-identical W1/W2 behavior (no adapter, no
    ip_adapter_image kwarg on the inpipe call).

    weapon_lora (W4 mechanism D, design_weapon.md sec 3/5 W4), when a dict
    {path, adapter_name, scale, trigger}, loads a pass-scoped weapon-concept
    LoRA onto the inpaint UNet at the given scale (the trigger prepends the
    prompt in the caller, not here). The returned closure exposes .unload_lora
    so the pass can tear the LoRA down afterward (it must not leak into the
    shared base gen pipe). Default None => no LoRA (byte-identical W1/W2/W3).
    """
    from diffusers import AutoPipelineForInpainting

    model_abs = os.path.join(ROOT, config["model_path"])
    # GPU_MUTEX (see the module header): every line in this block pushes weights
    # onto the card. gr._load_pipeline acquires the SAME mutex on the same
    # thread, so this is a nested acquire - safe, because a Windows named mutex
    # is recursive and both blocks are symmetric `with` statements (N acquires,
    # N releases). tests/test_gpu_mutex_wiring covers it against the real
    # primitive, because the non-Windows branch is a no-op and would never show
    # a non-recursive lock wedging here.
    with gr.gpu_lock("cuda"):
        base = gr._load_pipeline(config, model_abs, fast=False)
        inpipe = AutoPipelineForInpainting.from_pipe(base, controlnet=None)

        if ip_adapter is not None:
            inpipe.load_ip_adapter(
                ip_adapter["path"], subfolder=ip_adapter["subfolder"],
                weight_name=ip_adapter["weight_name"],
                image_encoder_folder=ip_adapter["image_encoder_folder"],
            )
            inpipe.set_ip_adapter_scale(ip_adapter["scale"])
        # The base pipe got enable_model_cpu_offload (gr._load_pipeline) BEFORE
        # load_ip_adapter registered the CLIP image_encoder, so that encoder was
            # never offload-hooked and stayed on CPU -> a CUDA/CPU device
            # mismatch when it encodes ip_adapter_image (observed e2e
            # 2026-07-16). The SDXL inpaint offload seq DOES include
            # image_encoder (text_encoder->text_encoder_2->image_encoder->unet
            # ->vae), so re-running offload here rebuilds the hooks WITH the
            # encoder present (enable_model_cpu_offload calls remove_all_hooks
            # first, so this is idempotent). Gated on offload being the active
            # strategy (the fast/all-resident path is already .to cuda, and
            # re-enabling would wrongly force offload on).
            if ((config or {}).get("gen") or {}).get("offload", True):
                inpipe.enable_model_cpu_offload()

        if weapon_lora is not None:
            inpipe.load_lora_weights(
                weapon_lora["path"], adapter_name=weapon_lora["adapter_name"])
            inpipe.set_adapters(
                [weapon_lora["adapter_name"]],
                adapter_weights=[weapon_lora["scale"]])
            # Mirror the W3 offload fix: the LoRA layers were patched onto the
            # UNet AFTER enable_model_cpu_offload built its hooks, so re-run
            # offload (idempotent - remove_all_hooks first) to hook the new
            # params. Gated on offload being active (the all-resident path is
            # already .to cuda).
            if ((config or {}).get("gen") or {}).get("offload", True):
                inpipe.enable_model_cpu_offload()

    def _inpaint(image, mask_image, prompt, negative_prompt, strength, seed,
                 ip_adapter_image=None):
        import torch

        # GPU_MUTEX around ONE roll, and no wider. run_pass's clip lane calls
        # the weapon gate between rolls, and that gate shells lw_gen_qa.py into
        # .venv-metrics where it acquires this same mutex - a Windows named
        # mutex is re-entrant per THREAD, not per process tree, so a hold spun
        # around the roll loop would block the parent on its own child forever.
        # Acquiring HERE, inside the real closure, is also what keeps the hold
        # off the stub inpainter every test injects.
        with gr.gpu_lock("cuda"):
            generator = torch.Generator("cuda").manual_seed(int(seed))
            extra = {}
            if ip_adapter_image is not None:
                extra["ip_adapter_image"] = ip_adapter_image
            return inpipe(
                prompt=prompt, negative_prompt=negative_prompt,
                image=image, mask_image=mask_image, strength=float(strength),
                num_inference_steps=WEAPON_STEPS, guidance_scale=WEAPON_GUIDANCE,
                width=image.width, height=image.height, generator=generator,
                **extra,
            ).images[0]

    if weapon_lora is not None:
        _inpaint.unload_lora = inpipe.unload_lora_weights
    return _inpaint


# --------------------------------------------------------------------------
# Real weapon gate builder (LAZY subprocess to .venv-metrics - never in CI).
# --------------------------------------------------------------------------
def _build_real_gate(config):
    """Build the weapon gate closure: score a ROI crop in the metrics venv.

    Returns (crop_pil) -> WeaponScore. Saves the crop to a temp PNG, shells
    `lw_gen_qa.py --weapon-crop <png>` under the metrics-venv python (open-clip
    lives there, never in .venv-gen), parses the JSON line, maps to WeaponScore.
    CREATE_NO_WINDOW keeps the subprocess console hidden (Legion no-flash rule).
    Never reached in CI - tests inject a stub gate.
    """
    import subprocess
    import tempfile

    venvs = (config or {}).get("venvs", {}) or {}
    metrics_venv = venvs.get("metrics", ".venv-metrics")
    metrics_py = os.path.join(ROOT, metrics_venv, "Scripts", "python.exe")
    qa_script = os.path.join(ROOT, "tools", "lw_gen_qa.py")

    def _gate(crop_pil):
        fd, tmp = tempfile.mkstemp(suffix=".png", prefix="wcrop_")
        os.close(fd)
        try:
            crop_pil.save(tmp)
            proc = subprocess.run(
                [metrics_py, qa_script, "--weapon-crop", tmp],
                capture_output=True, text=True, creationflags=_CREATE_NO_WINDOW,
            )
            data = json.loads(proc.stdout.strip().splitlines()[-1])
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return WeaponScore(
            float(data["weapon_cos"]), float(data["weapon_off"]), float(data["lap_var"])
        )

    return _gate


# --------------------------------------------------------------------------
# Review routing (a fallback never inpaints; it records why + a note).
# --------------------------------------------------------------------------
def _route_to_review(batch_dir, cand_file, wrist, rung, fallback, min_conf):
    review_dir = os.path.join(batch_dir, "weapon_review")
    os.makedirs(review_dir, exist_ok=True)
    note = os.path.join(review_dir, _raw_stem(cand_file) + ".note.txt")
    _atomic_write_text(
        note,
        f"weapon pass routed to review: fallback={fallback} "
        f"wrist={wrist} rung={rung} file={cand_file}\n",
    )
    sidecar = {
        "wrist": wrist, "rung": rung, "roi_bbox": None,
        "fallback": fallback, "outside_mask_identical": None,
        "min_conf": min_conf, "strength": None, "seed": None,
        "inpainted": False,
    }
    _atomic_write_json(_weapon_sidecar_path(batch_dir, cand_file), sidecar)


# --------------------------------------------------------------------------
# Batch driver.
# --------------------------------------------------------------------------
def weapon_pass(batch_dir, wrist=None, rung="w1", rolls=4, strength=0.92,
                min_conf=0.3, only=None, config=None, backend=None,
                inpainter=None, gate=None, assets=None):
    """Run the M1 W1 weapon pass over a batch dir; return the manifest dict.

    wrist is None -> PROPOSE (both-wrist overlays, no mutation). wrist set ->
    FIX (detect -> mask -> gated inpaint rolls -> paste-back -> advance). Up to
    `rolls` masked re-rolls are tried; each is scored by the weapon-region CLIP
    gate (design_weapon.md sec 6) and the FIRST gated PASS wins (STOP rule). If
    no roll passes, the best near-miss is dropped in weapon_review/ and cand
    [file] stays raw. backend defaults to dwpose_backend, inpainter to a real-
    SDXL closure, gate to a metrics-venv scorer shell; all three are injectable
    so pure tests never load onnx/torch/open-clip. `only` (a cand file name),
    when set, restricts the pass to that candidate. Atomic writes throughout.

    rung selects the fix mechanism. "w1" (default) is the keypoint-masked inpaint
    re-roll (design_weapon.md sec 3 W1). "w2" is the reference transplant: fit a
    real crossbow crop to the wrist (forearm_frame + affine_transplant), then run
    the SAME masked inpaint over the w2_strength ladder (sec 3 W2). W2 uses the
    operator lane only (the CLIP gate is dead, LEDGER 21): every strength roll is
    saved to weapon_review/ for operator blessing and cand[file] never advances.
    "w3" is the W2 transplant PLUS IP-Adapter concept guidance on the masked
    inpaint (mechanism C, sec 3 W3): the same crop is also composited onto a
    neutral field and fed as ip_adapter_image at weapon.ip_adapter_scale over the
    w3_strength ladder, giving strength headroom pure W2 harmonize lacks. W3 is
    operator-lane only too; a null weapon.ip_adapter_path routes to review with a
    no_ip_adapter fallback. `assets` (a list of AssetMeta) overrides the config-
    loaded crop library; when None the W2/W3 rungs load config weapon.assets
    (resolved against ROOT).
    """
    from PIL import Image  # lazy; CI has Pillow

    if config is None:
        config = _load_config_safe()
    weapon_cfg = (config or {}).get("weapon") or {}
    prompt = weapon_cfg.get("prompt") or WEAPON_PROMPT
    negative = weapon_cfg.get("negative") or WEAPON_NEG

    if backend is None:
        backend = loc.dwpose_backend

    manifest_path = os.path.join(batch_dir, "gen_manifest.json")
    with open(manifest_path, encoding="utf-8") as fo:
        manifest = json.load(fo)
    candidates = manifest.get("candidates", [])

    # ---- PROPOSE: emit both-wrist overlays, mutate nothing. ----
    if wrist is None:
        review_dir = os.path.join(batch_dir, "weapon_review")
        os.makedirs(review_dir, exist_ok=True)
        for cand in candidates:
            cand_file = cand.get("file")
            if not cand_file or (only is not None and cand_file != only):
                continue
            src = os.path.join(batch_dir, cand_file)
            if not os.path.exists(src):
                continue
            out = backend(src, min_conf=min_conf)
            width, height = Image.open(src).size
            roi_r = weapon_roi_from_keypoints(out.kp_map, "right", (width, height), out.right_hand)
            roi_l = weapon_roi_from_keypoints(out.kp_map, "left", (width, height), out.left_hand)
            overlay = loc.render_overlay(src, out.kp_map, roi_r, roi_l, _raw_stem(cand_file))
            overlay.save(os.path.join(review_dir, _raw_stem(cand_file) + "_overlay.png"))
        return manifest

    # ---- FIX: detect -> mask -> rolls; gate_mode decides acceptance. ----
    # gate_mode "operator" (DEFAULT): the ViT-L-14 CLIP region gate is a DEAD
    # gate - calibration 2026-07-12 (docs/research/GEN_RETUNE.md) showed it cannot
    # separate canonical-crossbow crops from wrong-weapon crops (margin negative on
    # every crop; the canonical default skin fails a floor 6 bad candidates clear),
    # the T_aes-precedent operator-lane fallback GOLDEN_DEFINITION.md:120 mandates.
    # So run the rolls, save EVERY attempt to weapon_review/ for operator blessing,
    # never auto-advance. gate_mode "clip": auto-accept the first gated PASS - kept
    # wired for a FUTURE separating scorer (weapon-concept LoRA / fine-tuned CLIP).
    gate_mode = (weapon_cfg.get("gate_mode") or "operator").lower()
    wthresh = resolve_weapon_thresholds(config, manifest)
    active_inpainter = inpainter
    active_gate = gate
    review_dir = os.path.join(batch_dir, "weapon_review")

    # W2/W3 rung setup (design_weapon.md sec 3/4): the crop library + strength
    # ladders. assets= wins; else load config weapon.assets (absolute or ROOT-
    # relative). The SAME crop library feeds the W2 transplant and the W3
    # transplant + IP-Adapter concept-guidance rung (mechanism C).
    w2_strengths = weapon_cfg.get("w2_strength") or [0.35, 0.45, 0.5]
    w3_strengths = weapon_cfg.get("w3_strength") or [0.55, 0.65, 0.75]
    rung_assets = []
    if rung in ("w2", "w3"):
        if assets is not None:
            rung_assets = assets
        else:
            assets_cfg = weapon_cfg.get("assets") or ""
            assets_dir = (assets_cfg if os.path.isabs(assets_cfg)
                          else os.path.join(ROOT, assets_cfg))
            rung_assets = load_assets(assets_dir)

    # W3 rung: the IP-Adapter concept-guidance config (design_weapon.md sec 3 W3 /
    # sec 5). A null ip_adapter_path routes each candidate to review with a
    # no_ip_adapter fallback (weights not provisioned). Path resolves against ROOT
    # when relative (mirror the assets_dir pattern); the rest carry code defaults
    # so a lean config still loads the vit-h SDXL adapter.
    ipa_cfg = None
    if rung == "w3":
        ipa_path = weapon_cfg.get("ip_adapter_path")
        if ipa_path:
            ipa_abs = (ipa_path if os.path.isabs(ipa_path)
                       else os.path.join(ROOT, ipa_path))
            ipa_scale = weapon_cfg.get("ip_adapter_scale")
            ipa_cfg = {
                "path": ipa_abs,
                "subfolder": weapon_cfg.get("ip_adapter_subfolder") or "sdxl_models",
                "weight_name": (weapon_cfg.get("ip_adapter_weight")
                                or "ip-adapter_sdxl_vit-h.safetensors"),
                "image_encoder_folder": (weapon_cfg.get("ip_adapter_encoder")
                                         or "models/image_encoder"),
                "scale": 0.7 if ipa_scale is None else ipa_scale,
            }

    # W4 rung: pass-scoped weapon-concept LoRA (design_weapon.md sec 5 W4). A null
    # weapon_lora_path OR a missing pytorch_lora_weights.safetensors routes each
    # candidate to review with a no_lora fallback (the LoRA is not trained yet).
    # Path resolves against ROOT when relative (mirror ipa_path).
    lora_cfg = None
    if rung == "w4":
        lp = weapon_cfg.get("weapon_lora_path")
        if lp:
            lp_abs = lp if os.path.isabs(lp) else os.path.join(ROOT, lp)
            weights = os.path.join(lp_abs, "pytorch_lora_weights.safetensors")
            if os.path.isfile(weights):
                lora_cfg = {
                    "path": lp_abs,
                    "adapter_name": weapon_cfg.get("weapon_lora_adapter") or "vayne_weapon",
                    "scale": (0.8 if weapon_cfg.get("weapon_lora_scale") is None
                              else weapon_cfg.get("weapon_lora_scale")),
                    "trigger": weapon_cfg.get("weapon_lora_trigger") or "vaynecrossbow",
                }

    for cand in candidates:
        cand_file = cand.get("file")
        if not cand_file or (only is not None and cand_file != only):
            continue
        src = os.path.join(batch_dir, cand_file)
        if not os.path.exists(src):
            continue

        out = backend(src, min_conf=min_conf)
        kp_map, hand = select_wrist_inputs(out, wrist)
        cand_img = Image.open(src).convert("RGB")
        width, height = cand_img.size

        # ---- W2 rung: reference transplant + guided inpaint (mechanism A). ----
        # Own gate ladder: forearm_frame (no_forearm) -> asset pick (no_asset) ->
        # ROI mask -> affine-paste the crossbow crop -> the SAME masked inpaint at
        # each w2_strength. Operator lane only (the CLIP gate is dead, LEDGER 21):
        # save every strength roll to weapon_review/, never auto-advance. A clip
        # lane is deferred until a separating scorer exists (design_weapon.md sec 6).
        if rung == "w2":
            frame = forearm_frame(kp_map, wrist, (width, height))
            if frame is None:
                _route_to_review(batch_dir, cand_file, wrist, rung, "no_forearm", min_conf)
                continue
            wx, wy, vhx, vhy, forearm_len = frame
            asset = pick_asset(rung_assets, wrist, (vhx, vhy))
            if asset is None:
                _route_to_review(batch_dir, cand_file, wrist, rung, "no_asset", min_conf)
                continue
            roi = weapon_roi_from_keypoints(kp_map, wrist, (width, height), hand)
            if not roi.ok:
                _route_to_review(batch_dir, cand_file, wrist, rung, roi.fallback, min_conf)
                continue
            if active_inpainter is None:
                active_inpainter = _build_real_inpainter(config)

            pasted = affine_transplant(cand_img, asset, (wx, wy), (vhx, vhy), forearm_len)
            cand_arr = np.asarray(cand_img)
            feathered = (np.clip(roi.mask_feathered, 0.0, 1.0) * 255.0).astype(np.uint8)
            mask_pil = Image.fromarray(feathered, mode="L")
            base_seed = int(cand.get("seed") or 0)
            os.makedirs(review_dir, exist_ok=True)
            roll_files = []
            for i, stg in enumerate(w2_strengths):
                # Inpaint the TRANSPLANTED image; paste back into the ORIGINAL so
                # out-of-mask pixels stay byte-identical to the raw candidate.
                final_arr = _inpaint_roll(
                    active_inpainter, pasted, mask_pil, cand_arr, roi.mask_binary,
                    prompt, negative, stg, base_seed + i)
                assert_outside_identity(cand_arr, final_arr, roi.mask_binary)
                rf = _raw_stem(cand_file) + f"_w2roll{i}.png"
                Image.fromarray(final_arr).save(os.path.join(review_dir, rf))
                roll_files.append(rf)
            sidecar = {
                "wrist": wrist, "rung": rung,
                "roi_bbox": list(roi.bbox) if roi.bbox else None,
                "fallback": None, "outside_mask_identical": True,
                "min_conf": min_conf, "strengths": list(w2_strengths),
                "verdict": "REVIEW", "reason": "clip_gate_dead",
                "gate_mode": gate_mode, "asset": asset.file,
                "rolls_tried": len(roll_files), "review_files": roll_files,
                "meta": getattr(out, "meta", {}) or {},
            }
            _atomic_write_json(_weapon_sidecar_path(batch_dir, cand_file), sidecar)
            continue

        # ---- W3 rung: reference transplant + IP-Adapter guided inpaint (mech C). ----
        # W2 geometry (affine-fit a real crossbow crop onto the wrist so STRUCTURE is
        # canonical) PLUS IP-Adapter concept guidance on the masked inpaint: the clean
        # weapon crop on a neutral field feeds ip_adapter_image at scale ~0.7, giving
        # the strength headroom pure W2 harmonize lacks (design_weapon.md sec 3 W3 /
        # sec 5). Gate ladder: no_forearm -> no_asset -> no_ip_adapter -> roi. Operator
        # lane only (the CLIP gate is dead, LEDGER 21): save every strength roll to
        # weapon_review/, never auto-advance.
        if rung == "w3":
            frame = forearm_frame(kp_map, wrist, (width, height))
            if frame is None:
                _route_to_review(batch_dir, cand_file, wrist, rung, "no_forearm", min_conf)
                continue
            wx, wy, vhx, vhy, forearm_len = frame
            asset = pick_asset(rung_assets, wrist, (vhx, vhy))
            if asset is None:
                _route_to_review(batch_dir, cand_file, wrist, rung, "no_asset", min_conf)
                continue
            if ipa_cfg is None:
                _route_to_review(batch_dir, cand_file, wrist, rung, "no_ip_adapter", min_conf)
                continue
            roi = weapon_roi_from_keypoints(kp_map, wrist, (width, height), hand)
            if not roi.ok:
                _route_to_review(batch_dir, cand_file, wrist, rung, roi.fallback, min_conf)
                continue
            if active_inpainter is None:
                active_inpainter = _build_real_inpainter(config, ip_adapter=ipa_cfg)

            pasted = affine_transplant(cand_img, asset, (wx, wy), (vhx, vhy), forearm_len)
            ip_img = _asset_ip_image(asset)
            cand_arr = np.asarray(cand_img)
            feathered = (np.clip(roi.mask_feathered, 0.0, 1.0) * 255.0).astype(np.uint8)
            mask_pil = Image.fromarray(feathered, mode="L")
            base_seed = int(cand.get("seed") or 0)
            os.makedirs(review_dir, exist_ok=True)
            roll_files = []
            for i, stg in enumerate(w3_strengths):
                # Inpaint the TRANSPLANTED image under IP-Adapter concept guidance;
                # paste back into the ORIGINAL so out-of-mask pixels stay identical.
                final_arr = _inpaint_roll(
                    active_inpainter, pasted, mask_pil, cand_arr, roi.mask_binary,
                    prompt, negative, stg, base_seed + i, ip_adapter_image=ip_img)
                assert_outside_identity(cand_arr, final_arr, roi.mask_binary)
                rf = _raw_stem(cand_file) + f"_w3roll{i}.png"
                Image.fromarray(final_arr).save(os.path.join(review_dir, rf))
                roll_files.append(rf)
            sidecar = {
                "wrist": wrist, "rung": rung,
                "roi_bbox": list(roi.bbox) if roi.bbox else None,
                "fallback": None, "outside_mask_identical": True,
                "min_conf": min_conf, "strengths": list(w3_strengths),
                "verdict": "REVIEW", "reason": "clip_gate_dead",
                "gate_mode": gate_mode, "asset": asset.file,
                "ip_adapter": {"scale": ipa_cfg["scale"],
                               "weight": ipa_cfg["weight_name"]},
                "rolls_tried": len(roll_files), "review_files": roll_files,
                "meta": getattr(out, "meta", {}) or {},
            }
            _atomic_write_json(_weapon_sidecar_path(batch_dir, cand_file), sidecar)
            continue

        # ---- W4 rung: LoRA-guided W1 masked reroll (mechanism D). ----
        # A weapon-concept LoRA rides the inpaint pipe (pass-scoped, unloaded
        # after) and the trigger token prepends the prompt; otherwise a plain W1
        # masked reroll (no transplant). design_weapon.md sec 3/5 W4. Gate ladder:
        # no_lora -> roi. Operator lane only (CLIP gate dead, LEDGER 21): save
        # every roll to weapon_review/, never auto-advance.
        if rung == "w4":
            if lora_cfg is None:
                _route_to_review(batch_dir, cand_file, wrist, rung, "no_lora", min_conf)
                continue
            roi = weapon_roi_from_keypoints(kp_map, wrist, (width, height), hand)
            if not roi.ok:
                _route_to_review(batch_dir, cand_file, wrist, rung, roi.fallback, min_conf)
                continue
            if active_inpainter is None:
                active_inpainter = _build_real_inpainter(config, weapon_lora=lora_cfg)
            w4_prompt = f"{lora_cfg['trigger']}, {prompt}"
            cand_arr = np.asarray(cand_img)
            feathered = (np.clip(roi.mask_feathered, 0.0, 1.0) * 255.0).astype(np.uint8)
            mask_pil = Image.fromarray(feathered, mode="L")
            base_seed = int(cand.get("seed") or 0)
            os.makedirs(review_dir, exist_ok=True)
            roll_files = []
            for roll in range(max(1, int(rolls))):
                final_arr = _inpaint_roll(
                    active_inpainter, cand_img, mask_pil, cand_arr, roi.mask_binary,
                    w4_prompt, negative, strength, base_seed + roll)
                assert_outside_identity(cand_arr, final_arr, roi.mask_binary)
                rf = _raw_stem(cand_file) + f"_w4roll{roll}.png"
                Image.fromarray(final_arr).save(os.path.join(review_dir, rf))
                roll_files.append(rf)
            sidecar = {
                "wrist": wrist, "rung": rung,
                "roi_bbox": list(roi.bbox) if roi.bbox else None,
                "fallback": None, "outside_mask_identical": True,
                "min_conf": min_conf, "strength": strength,
                "verdict": "REVIEW", "reason": "clip_gate_dead",
                "gate_mode": gate_mode, "rolls": rolls,
                "lora": {"scale": lora_cfg["scale"], "trigger": lora_cfg["trigger"],
                         "adapter": lora_cfg["adapter_name"]},
                "rolls_tried": len(roll_files), "review_files": roll_files,
                "meta": getattr(out, "meta", {}) or {},
            }
            _atomic_write_json(_weapon_sidecar_path(batch_dir, cand_file), sidecar)
            continue

        roi = weapon_roi_from_keypoints(kp_map, wrist, (width, height), hand)
        if not roi.ok:
            _route_to_review(batch_dir, cand_file, wrist, rung, roi.fallback, min_conf)
            continue

        if active_inpainter is None:
            active_inpainter = _build_real_inpainter(config)

        cand_arr = np.asarray(cand_img)
        feathered = (np.clip(roi.mask_feathered, 0.0, 1.0) * 255.0).astype(np.uint8)
        mask_pil = Image.fromarray(feathered, mode="L")
        base_seed = int(cand.get("seed") or 0)

        # ---- operator lane (dead-gate default): save every roll for eyeball. ----
        if gate_mode != "clip":
            os.makedirs(review_dir, exist_ok=True)
            roll_files = []
            for roll in range(max(1, int(rolls))):
                final_arr = _inpaint_roll(
                    active_inpainter, cand_img, mask_pil, cand_arr, roi.mask_binary,
                    prompt, negative, strength, base_seed + roll)
                assert_outside_identity(cand_arr, final_arr, roi.mask_binary)
                rf = _raw_stem(cand_file) + f"_wroll{roll}.png"
                Image.fromarray(final_arr).save(os.path.join(review_dir, rf))
                roll_files.append(rf)
            sidecar = {
                "wrist": wrist, "rung": rung,
                "roi_bbox": list(roi.bbox) if roi.bbox else None,
                "fallback": None, "outside_mask_identical": True,
                "min_conf": min_conf, "strength": strength,
                "verdict": "REVIEW", "reason": "clip_gate_dead",
                "gate_mode": gate_mode, "rolls": rolls,
                "rolls_tried": len(roll_files), "review_files": roll_files,
                "meta": getattr(out, "meta", {}) or {},
            }
            _atomic_write_json(_weapon_sidecar_path(batch_dir, cand_file), sidecar)
            continue

        # ---- clip lane: gated rolls, first PASS wins (STOP rule). ----
        if active_gate is None:
            active_gate = _build_real_gate(config)
        crop_box = pad_bbox(roi.bbox, WEAPON_CROP_PAD, (width, height))
        accepted = None
        best = None
        rolls_tried = 0
        for roll in range(max(1, int(rolls))):
            rolls_tried += 1
            seed = base_seed + roll
            final_arr = _inpaint_roll(
                active_inpainter, cand_img, mask_pil, cand_arr, roi.mask_binary,
                prompt, negative, strength, seed)
            crop_pil = Image.fromarray(final_arr).crop(crop_box)
            wscore = active_gate(crop_pil)
            g = weapon_grade(wscore, wthresh)
            if best is None or wscore.weapon_cos > best[3].weapon_cos:
                best = (roll, seed, final_arr, wscore)
            if g.verdict == VERDICT_PASS:
                accepted = (roll, seed, final_arr, wscore)
                break

        if accepted is not None:
            roll_idx, seed, final_arr, wscore = accepted
            g = weapon_grade(wscore, wthresh)
            assert_outside_identity(cand_arr, final_arr, roi.mask_binary)
            new_file = gr.stage_filename(cand_file, _STAGE)
            Image.fromarray(final_arr).save(os.path.join(batch_dir, new_file))
            gr.advance_cand_file(cand, new_file, _STAGE)
            sidecar = {
                "wrist": wrist, "rung": rung,
                "roi_bbox": list(roi.bbox) if roi.bbox else None,
                "fallback": None, "outside_mask_identical": True,
                "min_conf": min_conf, "strength": strength,
                "verdict": VERDICT_PASS, "reason": None, "gate_mode": gate_mode,
                "weapon_cos": wscore.weapon_cos, "weapon_off": wscore.weapon_off,
                "weapon_margin": g.margin, "chosen_roll": roll_idx,
                "chosen_seed": seed, "rolls": rolls, "rolls_tried": rolls_tried,
                "meta": getattr(out, "meta", {}) or {},
            }
            _atomic_write_json(_weapon_sidecar_path(batch_dir, new_file), sidecar)
            _atomic_write_json(manifest_path, manifest)
        else:
            # STOP rule: no gated PASS in the budget -> operator review lane. Drop
            # the best near-miss for eyeball; cand[file] stays raw (never advanced).
            roll_idx, seed, final_arr, wscore = best
            g = weapon_grade(wscore, wthresh)
            os.makedirs(review_dir, exist_ok=True)
            Image.fromarray(final_arr).save(
                os.path.join(review_dir, _raw_stem(cand_file) + "_wbest.png"))
            sidecar = {
                "wrist": wrist, "rung": rung,
                "roi_bbox": list(roi.bbox) if roi.bbox else None,
                "fallback": None, "outside_mask_identical": None,
                "min_conf": min_conf, "strength": strength,
                "verdict": VERDICT_REJECT, "reason": g.reason, "gate_mode": gate_mode,
                "weapon_cos": wscore.weapon_cos, "weapon_off": wscore.weapon_off,
                "weapon_margin": g.margin, "chosen_roll": roll_idx,
                "chosen_seed": seed, "rolls": rolls, "rolls_tried": rolls_tried,
                "meta": getattr(out, "meta", {}) or {},
            }
            _atomic_write_json(_weapon_sidecar_path(batch_dir, cand_file), sidecar)

    # W4 LoRA is pass-scoped: unload so it never leaks into the shared base gen
    # pipeline (design_weapon.md:183). Guard: only when a w4 inpainter was built
    # or injected and exposes the teardown handle.
    if rung == "w4":
        unload = getattr(active_inpainter, "unload_lora", None)
        if callable(unload):
            unload()

    return manifest


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="lw_gen_weaponpass.py",
        description="Legion Wallpaper weapon pass (M1 W1): detect -> mask -> inpaint.",
    )
    p.add_argument("batch_dir", help="path to images/_gen_scratch/<batch-id>/")
    p.add_argument("--wrist", choices=["left", "right"], default=None,
                   help="rig side to fix; absent (or --propose) => propose mode")
    p.add_argument("--propose", action="store_true",
                   help="emit both-wrist overlays into weapon_review/, inpaint nothing")
    p.add_argument("--weapon-rung", dest="weapon_rung", default="w1")
    p.add_argument("--rolls", type=int, default=4)
    p.add_argument("--strength", type=float, default=0.92)
    p.add_argument("--weapon-min-conf", dest="weapon_min_conf", type=float, default=0.3)
    p.add_argument("--only", default=None, help="restrict to one cand file (cand_XX.png)")
    return p


def _log_error(exc):
    """Append the raw error to logs/ - never surface it to the user."""
    try:
        import datetime

        logs = os.path.join(ROOT, "logs")
        os.makedirs(logs, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d")
        with open(os.path.join(logs, f"{stamp}.log"), "a", encoding="utf-8") as fo:
            fo.write(f"[lw_gen_weaponpass] {type(exc).__name__}: {exc}\n")
    except OSError:
        pass


def main(argv=None):
    args = build_parser().parse_args(argv)
    wrist = None if args.propose else args.wrist
    try:
        manifest = weapon_pass(
            args.batch_dir, wrist=wrist, rung=args.weapon_rung, rolls=args.rolls,
            strength=args.strength, min_conf=args.weapon_min_conf, only=args.only,
        )
    except gr.GpuBusy as exc:
        # Would otherwise fall into the broad arm below and be reported as
        # "generator not provisioned", which is untrue and sends the operator
        # to the wrong runbook. Contention is expected at N=3.
        print("weapon pass skipped - the GPU is held by another run and did not "
              "free in time. Nothing was written; re-run once it frees.",
              file=sys.stderr)
        _log_error(exc)
        return 1
    except Exception as exc:  # noqa: BLE001 - never surface a raw torch/onnx trace
        print("weapon pass failed - generator not provisioned or a backend/inpaint "
              "error (see logs). Run the Phase-0 setup (docs/GEN_MODELS.md).",
              file=sys.stderr)
        _log_error(exc)
        return 1

    n = len(manifest.get("candidates", []))
    mode = "propose" if wrist is None else f"fix({wrist})"
    print(f"weapon pass [{mode}] over {n} candidate(s) -> {args.batch_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
