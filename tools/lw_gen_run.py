"""Legion Wallpaper - generator sidecar Phase-1 driver (lw-gen run).

Owns the batch: resolves a brief/CLI plan, hard-gates on RC-live (League/Riot
running), sets the Blackwell CUDA env, generates N candidate PNGs into a
gitignored scratch batch dir, then (unless --no-chain) shells the stateless QA
scorer and the promoter as subprocesses in their own venvs.

The 3 gen scripts interlock ONLY via the batch dir + gen_manifest.json, never by
importing each other. lw_gen_run is the round-loop owner (regen lives here; QA is
a stateless scorer, promote is a pure producer of stage-0 inputs).

CI constraint (torch-free): this module imports ONLY stdlib + slugify from
lw_pipeline at top level. torch/diffusers are imported LAZILY inside the
generation function, which is never reached in CI (provisioning check refuses
first when .venv-gen / the model weight is absent). Every pure-logic function
(load_config, load_styles, load_brief, resolve_plan, resolve_resolution,
rc_live_check, rc_live_gate, build_prompts, check_provisioned) is unit-tested
without torch or a real subprocess.

Provenance: generated images carry source_url gen://lw-gen/<batch-id>, tool
lw-gen. They are personal-use only and never uploaded to the recovery corpus.
"""
from __future__ import annotations

import argparse
import contextlib as _contextlib
import datetime
import importlib.util as _importlib_util
import json
import os
import random
import subprocess
import sys
from collections import namedtuple
from pathlib import Path as _Path

# --------------------------------------------------------------------------
# Machine-wide GPU serialization (ops/loop/winmutex.py GPU_MUTEX)
# --------------------------------------------------------------------------
# One RTX 5070, shared by every headless loop on this machine. winmutex NAMES
# the mutex; the tool that touches CUDA is what ACQUIRES it - that placement is
# the only one under which a hand-run of this module is protected too, which is
# what the winmutex docstring promises.
#
# LEAF ONLY, and this module is the one HYBRID in the repo: run() is both a CUDA
# worker (SDXL, in process) and an orchestrator (it shells lw_gen_qa.py into
# .venv-metrics and lw_gen_weaponpass.py into .venv-gen). A Windows named mutex
# is re-entrant per THREAD, not per process tree, so if run() held across
# _shell_stage and that child ever acquired, the parent would block on its own
# child forever. The hold therefore lives in _load_pipeline and
# _generate_candidates and never in run() - the accepted cost is that the SDXL
# pipe stays resident on the card between the two, which no placement short of
# the deadlocking one can avoid.
#
# This is one of four copies (lw_upscale / lw_clean_sdxl / lw_g1_gate /
# lw_gen_run). A shared tools/ helper is not importable from all four venvs;
# this module runs under .venv-gen.
#
# 1800s: the longest legitimate single hold is one generation round, minutes
# not hours, so half an hour is generous for a healthy holder and still only a
# third of the 5400s headless cycle deadline - leaving the cycle room to LOG
# the failure and finish. timeout=None would instead turn a wedged holder in
# another repo into an invisible hang.
GPU_MUTEX_TIMEOUT_S = 1800.0
_WINMUTEX_MOD = "lw_loop_winmutex"
_GPU_TAG = "lw_gen_run"


def _bind_gpu_busy():
    """Bind tools/lw_gpu_busy.py BY PATH. See lw_g1_gate._bind_gpu_busy for why.

    Load-bearing here specifically: lw_gen_weaponpass reaches this module as
    `tools.lw_gen_run` while lw_gen_train_weapon_lora reaches it as
    `lw_gen_run`. The fixed sys.modules key is what makes both see the same
    class object. The raise still happens before any candidate PNG is saved.
    """
    mod = sys.modules.get("lw_gpu_busy")
    if mod is None:
        path = _Path(__file__).resolve().parent / "lw_gpu_busy.py"
        spec = _importlib_util.spec_from_file_location("lw_gpu_busy", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load lw_gpu_busy from {path}")
        mod = _importlib_util.module_from_spec(spec)
        sys.modules["lw_gpu_busy"] = mod
        spec.loader.exec_module(mod)
    return mod


# The ONE GpuBusy. Never re-declare it here - see tools/lw_gpu_busy.py.
GpuBusy = _bind_gpu_busy().GpuBusy


def _gpu_log(msg):
    """Append one line to logs/YYYY-MM-DD.log. Never raises.

    Not print(): under pythonw.exe there is no stdout at all. The daily log is
    what the operator already reads, and it is what makes a hold window
    measurable after a concurrent run.
    """
    try:
        stamp = datetime.datetime.now()
        log_dir = _Path(__file__).resolve().parent.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / f"{stamp:%Y-%m-%d}.log", "a", encoding="utf-8") as fo:
            fo.write(f"{stamp:%H:%M:%S} [{_GPU_TAG}] {msg}\n")
    except OSError:
        pass


def _winmutex():
    """Bind ops/loop/winmutex.py BY PATH (the loop_controller._bind pattern).

    ops/loop has no __init__.py, and .venv-gen does not have the repo root on
    sys.path, so a package-style import would fail everywhere the code actually
    executes while passing in CI.
    """
    mod = sys.modules.get(_WINMUTEX_MOD)
    if mod is not None:
        return mod
    path = _Path(__file__).resolve().parent.parent / "ops" / "loop" / "winmutex.py"
    spec = _importlib_util.spec_from_file_location(_WINMUTEX_MOD, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load winmutex from {path}")
    mod = _importlib_util.module_from_spec(spec)
    sys.modules[_WINMUTEX_MOD] = mod
    spec.loader.exec_module(mod)
    return mod


@_contextlib.contextmanager
def gpu_lock(device="cuda", log=None):
    """Hold GPU_MUTEX around real CUDA work. A no-op when device is not cuda.

    The CPU fallback must NOT take it: serializing CPU work across repos buys
    nothing and costs throughput. A winmutex import failure DEGRADES to unheld
    with the same UNSERIALIZED marker winmutex itself emits - the mutex is a
    cross-repo governor, not a dependency of this tool, and a venv that cannot
    see it must still be able to generate.
    """
    if str(device) != "cuda":
        yield None
        return

    def sink(msg):
        _gpu_log(msg)
        if log is not None:
            log(msg)

    try:
        wm = _winmutex()
    except Exception as exc:  # noqa: BLE001 - a governor must never be fatal
        sink(f"winmutex: UNSERIALIZED GPU - cannot bind ops/loop/winmutex.py "
             f"({type(exc).__name__}: {exc}); proceeding WITHOUT the lock")
        yield None
        return

    try:
        with wm.hold(wm.GPU_MUTEX, timeout=GPU_MUTEX_TIMEOUT_S, log=sink) as handle:
            yield handle
    except wm.MutexTimeout as exc:
        sink(f"winmutex: TIMEOUT on {wm.GPU_MUTEX} after {GPU_MUTEX_TIMEOUT_S}s "
             f"- another process still holds the GPU; abandoning this step")
        raise GpuBusy(
            f"GPU busy elsewhere for more than {GPU_MUTEX_TIMEOUT_S}s") from exc

# slugify is stdlib-only in lw_pipeline (no torch/PIL on that path), so importing
# it here is CI-safe. Mirror the sibling path-shim pattern (LEDGER.md:310).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lw_pipeline import slugify  # noqa: E402

# CREATE_NO_WINDOW: 0 on non-Windows so the module still imports/tests in CI
# (Legion focus-steal rule - never flash a console).
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "tools", "lw_gen_config.json")
STYLES_PATH = os.path.join(ROOT, "tools", "lw_gen_styles.json")
DEFAULT_OUT_ROOT = os.path.join("images", "_gen_scratch")

MVP_ASPECT = "16:9"

# rc_live_check states.
RC_LIVE = "live"
RC_CLEAR = "clear"
RC_UNKNOWN = "unknown"

RcStatus = namedtuple("RcStatus", ["state", "source", "reason"])


class GenError(Exception):
    """Friendly, exit-coded generator error (never a raw traceback to the user)."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------
# Data loading (pure stdlib).
# --------------------------------------------------------------------------
def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise GenError(f"required file missing: {path}", code=2)
    except (OSError, ValueError) as exc:
        raise GenError(f"could not read JSON {path}: {exc}", code=2)


def load_config(path=CONFIG_PATH):
    return _read_json(path)


def load_styles(path=STYLES_PATH):
    return _read_json(path)


def load_brief(path):
    if not path:
        return {}
    data = _read_json(path)
    if not isinstance(data, dict):
        raise GenError(f"brief must be a JSON object: {path}", code=2)
    return data


# --------------------------------------------------------------------------
# Plan resolution: CLI overrides brief overrides config/style defaults.
# --------------------------------------------------------------------------
def resolve_plan(cli, config, styles, brief=None):
    """Merge CLI dict (None == not given) over a brief over defaults -> plan dict.

    cli keys: subject, style, n, aspect, prompt_extra, negative_extra, seed,
    max_regen_rounds, top_k. Precedence per key: CLI value if not None, else the
    brief value if present-and-not-None, else the documented default.
    """
    brief = brief or {}

    def pick(key, default=None):
        if cli.get(key) is not None:
            return cli[key]
        val = brief.get(key)
        if val is not None:
            return val
        return default

    subject = pick("subject")
    if not subject:
        raise GenError("no subject: pass --subject or a --brief with a subject", code=2)

    style = pick("style", "splash")
    if style not in styles:
        raise GenError(
            f"unknown style {style!r}; known: {', '.join(sorted(styles))}", code=2
        )

    aliases = brief.get("subject_aliases")
    if not aliases:
        aliases = [subject]

    plan = {
        "subject": subject,
        "subject_aliases": list(aliases),
        "style": style,
        "n": int(pick("n", 4)),
        "aspect": pick("aspect", MVP_ASPECT),
        "prompt_extra": pick("prompt_extra", "") or "",
        "negative_extra": pick("negative_extra", "") or "",
        "seed": pick("seed", None),
        "max_regen_rounds": int(pick("max_regen_rounds", 1)),
        "top_k": int(pick("top_k", config.get("top_k", 3))),
    }
    init_rel = pick("init_image", None)
    plan["init_image"] = (
        (init_rel if os.path.isabs(init_rel) else os.path.join(ROOT, init_rel))
        if init_rel else None
    )
    plan["img2img_strength"] = float(pick("img2img_strength", 0.55))
    cn_rel = pick("controlnet_pose", None)
    plan["controlnet_pose"] = (
        (cn_rel if os.path.isabs(cn_rel) else os.path.join(ROOT, cn_rel))
        if cn_rel else None
    )
    plan["controlnet_scale"] = float(pick("controlnet_scale", 0.75))
    if plan["n"] < 1:
        raise GenError("n must be >= 1", code=2)
    if plan["max_regen_rounds"] < 1:
        raise GenError("max_regen_rounds must be >= 1", code=2)
    return plan


def resolve_resolution(aspect, config):
    """MVP aspect guard: only 16:9 is supported; anything else is a friendly refuse."""
    if aspect != MVP_ASPECT:
        raise GenError(
            f"aspect {aspect!r} is not supported at MVP - only {MVP_ASPECT} is wired. "
            "Ultrawide/other aspects are deferred (a separate multi-target refactor).",
            code=2,
        )
    res = (config.get("resolution") or {}).get(aspect)
    if not res or len(res) != 2:
        raise GenError(f"config resolution missing {aspect}", code=2)
    return int(res[0]), int(res[1])


def build_prompts(style_def, subject, prompt_extra, negative_extra):
    """str.format the style templates (unused slots are ignored by .format)."""
    fmt = {"subject": subject, "prompt_extra": prompt_extra, "negative_extra": negative_extra}
    try:
        pos = style_def["positive"].format(**fmt)
        neg = style_def["negative"].format(**fmt)
    except KeyError as exc:
        raise GenError(f"style template references unknown slot {exc}", code=2)
    return pos, neg


# --------------------------------------------------------------------------
# RC-live hard gate (pure stdlib, injectable for tests).
# --------------------------------------------------------------------------
def _default_process_lister():
    """Return a list of running process image names, or None if unknowable.

    Uses `tasklist` (Windows) with CREATE_NO_WINDOW. A non-zero exit or an OS
    error means we cannot evaluate -> None (treated as UNKNOWN by the caller).
    """
    try:
        proc = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True, text=True, creationflags=NO_WINDOW,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    names = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        first = line.split(",")[0].strip().strip('"')
        if first:
            names.append(first)
    return names


def rc_live_check(config, process_lister=None, flag_path=None):
    """Detect a live RC/League session. Order: flag file -> process scan.

    Returns an RcStatus(state, source, reason) where state is one of RC_LIVE /
    RC_CLEAR / RC_UNKNOWN. flag_path, when given, is checked verbatim (the caller
    resolves it against the repo root); process_lister is injectable for tests
    and must return a list of names or None when the process set is unknowable.
    """
    rc = config.get("rc_live") or {}

    if flag_path and os.path.exists(flag_path):
        return RcStatus(RC_LIVE, "flag", f"rc_live flag present: {flag_path}")

    lister = process_lister if process_lister is not None else _default_process_lister
    try:
        names = lister()
    except Exception:  # noqa: BLE001 - a broken lister must not crash the gate
        names = None
    if names is None:
        return RcStatus(RC_UNKNOWN, "process-scan", "could not enumerate running processes")

    watch = {p.lower() for p in rc.get("processes", [])}
    running = {str(n).lower() for n in names}
    hit = sorted(watch & running)
    if hit:
        return RcStatus(RC_LIVE, "process", f"League/Riot process running: {', '.join(hit)}")
    return RcStatus(RC_CLEAR, "process", "no RC-live signal detected")


def rc_live_gate(status, force=False, allow_when_unsure=False):
    """Decide whether generation may proceed given an RcStatus.

    Returns (ok: bool, message: str). LIVE refuses unless --force. UNKNOWN refuses
    conservatively unless --allow-when-unsure or --force. CLEAR always proceeds.
    """
    if status.state == RC_LIVE:
        if force:
            return True, f"WARNING: --force overriding RC-live gate ({status.reason})"
        return False, (
            "Refusing to generate while a League/Riot session is live "
            f"({status.reason}). Close the client and retry."
        )
    if status.state == RC_UNKNOWN:
        if force or allow_when_unsure:
            return True, f"Proceeding despite unknown RC-live state ({status.reason})"
        return False, (
            f"Refusing (conservative): {status.reason}. "
            "Pass --allow-when-unsure to proceed anyway, or --force."
        )
    return True, ""


# --------------------------------------------------------------------------
# Provisioning check (friendly refuse when the generator is not set up yet).
# --------------------------------------------------------------------------
def check_provisioned(config, root=ROOT):
    """Return (ok, message). ok is False (with a friendly message) if the gen
    venv python or the model weight is absent - so the script is safe to invoke
    before any Phase-0 download exists."""
    venvs = config.get("venvs") or {}
    gen_venv = venvs.get("gen", ".venv-gen")
    gen_py = os.path.join(root, gen_venv, "Scripts", "python.exe")
    model_rel = config.get("model_path")
    model_abs = os.path.join(root, model_rel) if model_rel else None

    missing = []
    if not os.path.exists(gen_py):
        missing.append(f"generator venv ({gen_venv})")
    if not model_abs or not os.path.exists(model_abs):
        missing.append(f"model weight ({model_rel})")
    if missing:
        return False, (
            "generator not provisioned yet - missing " + "; ".join(missing) + ". "
            "Run the Phase-0 setup (see docs/GEN_MODELS.md); no weights are "
            "downloaded yet."
        )
    return True, ""


# --------------------------------------------------------------------------
# Environment (Blackwell / RTX 5090) - set before any torch import.
# --------------------------------------------------------------------------
def apply_env(config):
    for key, val in (config.get("env") or {}).items():
        os.environ[key] = str(val)
    # Never let a stale CUDA_VISIBLE_DEVICES=-1 hide the GPU.
    if os.environ.get("CUDA_VISIBLE_DEVICES") == "-1":
        del os.environ["CUDA_VISIBLE_DEVICES"]


# --------------------------------------------------------------------------
# Batch scaffolding + manifest.
# --------------------------------------------------------------------------
def make_batch_id(subject, style, now=None):
    now = now or datetime.datetime.now()
    return f"{slugify(subject)}-{style}-{now.strftime('%Y%m%d%H%M%S')}"


def _atomic_write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)


def build_manifest(plan, config, style_def, res, pos, neg, batch_id, fast):
    sampler = style_def.get("sampler") or config.get("sampler") or {}
    gen = config.get("gen") or {}
    return {
        "batch_id": batch_id,
        "subject": plan["subject"],
        "subject_aliases": plan["subject_aliases"],
        "style": plan["style"],
        "aspect": plan["aspect"],
        "model": config.get("model_path"),
        "clip_model": config.get("clip_model"),
        "created_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "prompt": pos,
        "negative": neg,
        "config_snapshot": {
            "steps": sampler.get("steps"),
            "cfg": sampler.get("cfg"),
            "sampler": sampler.get("name"),
            "resolution": [res[0], res[1]],
            "offload": bool(gen.get("offload", True)) and not fast,
            "tiled_vae": bool(gen.get("tiled_vae", True)),
            "attention": gen.get("attention", "sdpa"),
        },
        "candidates": [],
        "promote": {},
    }


# --------------------------------------------------------------------------
# Candidate file/stage contract (PURE + torch-free - safe to import in CI).
# --------------------------------------------------------------------------
_STAGE_SUFFIXES = ("wfix", "repair", "finish")


def stage_filename(raw_file, stage):
    """Build a stage-tagged candidate filename from the RAW stem every call.

    Stages never accrete: stage_filename('cand_00_wfix.png', 'repair') is
    'cand_00_repair.png', not 'cand_00_wfix_repair.png'.
    """
    stem = raw_file[:-4] if raw_file.lower().endswith(".png") else raw_file
    stripped = True
    while stripped:
        stripped = False
        for suf in _STAGE_SUFFIXES:
            token = "_" + suf
            if stem.endswith(token):
                stem = stem[:-len(token)]
                stripped = True
                break
    return f"{stem}_{stage}.png"


def new_candidate_record(fname, seed, round_no):
    """The raw manifest candidate record for a freshly generated PNG.

    'stage'/'provenance' are appended at the END (append-fields-with-defaults
    convention) so every existing consumer of the record keeps working.
    """
    return {
        "file": fname, "seed": seed, "round": round_no,
        "subject_cos": None, "off_cos": None, "margin": None,
        "aesthetic": None, "lap_var": None,
        "stage_a_pass": None, "stage_b_pass": None,
        "verdict": "PENDING", "reason": None,
        "stage": "raw", "provenance": [fname],
    }


def advance_cand_file(cand, new_file, stage):
    """Point cand at a rewritten file, tag the stage, record the prior file.

    Uses .get(...) so records predating the stage/provenance fields are
    tolerated (the prior file is still appended to the provenance chain).
    """
    prior = cand.get("file")
    provenance = list(cand.get("provenance", []))
    if prior is not None:
        provenance.append(prior)
    cand["file"] = new_file
    cand["stage"] = stage
    cand["provenance"] = provenance
    return cand


# --------------------------------------------------------------------------
# Generation (LAZY torch/diffusers - never reached in CI).
# --------------------------------------------------------------------------
def resolve_ip_adapter(ip_adapter):
    """Resolve + VALIDATE an IP-Adapter spec. Returns (root_abs, weight_abs).

    Checks the weight FILE, not just the adapter root. The root is always present
    once tools/models/ip-adapter exists, so a root-only check let a wrong or
    undownloaded --ip-adapter-weight-name through to diffusers.load_ip_adapter,
    where it failed AFTER a multi-GB base checkpoint had already loaded. Two
    failure modes made that worse than slow: the diffusers-level error does not
    name the file, and omitting the flag falls back to the general adapter, so a
    run meant to exercise plus-face would silently produce general-adapter
    results. Pure path logic - no torch, so it is callable early and testable.

    Raises GenError(code=4) naming the missing path, and lists what IS present
    so an operator can see at a glance which variants were actually downloaded.
    """
    root_abs = (ip_adapter["path"] if os.path.isabs(ip_adapter["path"])
                else os.path.join(ROOT, ip_adapter["path"]))
    if not os.path.isdir(root_abs):
        raise GenError(f"ip_adapter path not found: {ip_adapter['path']}", code=4)
    sub = ip_adapter.get("subfolder") or ""
    weight_abs = os.path.join(root_abs, sub, ip_adapter["weight_name"])
    if not os.path.isfile(weight_abs):
        have = []
        sub_abs = os.path.join(root_abs, sub)
        if os.path.isdir(sub_abs):
            have = sorted(f for f in os.listdir(sub_abs)
                          if f.endswith((".safetensors", ".bin")))
        listing = ", ".join(have) if have else "(none)"
        raise GenError(
            f"ip_adapter weight not found: {ip_adapter['weight_name']} "
            f"(looked in {os.path.join(sub, '') if sub else root_abs}); "
            f"weights present: {listing}",
            code=4)
    return root_abs, weight_abs


def _load_pipeline(config, model_abs, fast, controlnet_path=None, ip_adapter=None):
    """Lazily build a diffusers text2image pipeline, optionally ControlNet-conditioned
    (OpenPose skeleton control). Heavy imports live here.

    ip_adapter, when a dict {path, subfolder, weight_name, image_encoder_folder,
    scale}, loads IP-Adapter weights + the CLIP image encoder onto the txt2img
    pipe and sets the concept scale (mirrors lw_gen_weaponpass._build_real_inpainter,
    which does the same on the inpaint pipe). Default None => byte-identical
    behavior to before this parameter existed (no adapter, no image_encoder, no
    ip_adapter_image kwarg on the pipe call).
    """
    try:
        import torch  # noqa: F401
    except Exception as exc:  # noqa: BLE001 - degrade, never dump a raw import error
        raise GenError(
            "generator backend unavailable (torch/diffusers not importable in "
            ".venv-gen). See docs/GEN_MODELS.md Phase-0 setup.",
            code=4,
        ) from exc
    # The hold covers weight loading + device placement. It cannot be widened to
    # cover generation as well, because run()'s round loop shells lw_gen_qa.py
    # between the two - see the module header on the hybrid case.
    try:
        with gpu_lock("cuda"):
            return _load_pipeline_locked(config, model_abs, fast, controlnet_path,
                                         ip_adapter=ip_adapter)
    except GpuBusy as exc:
        raise GenError(
            "the GPU is held by another run and did not free in time; "
            "generation skipped. See logs/ for the winmutex trace.",
            code=4) from exc


def _load_pipeline_locked(config, model_abs, fast, controlnet_path, ip_adapter=None):
    """The body of _load_pipeline, run while GPU_MUTEX is held."""
    import torch

    try:
        if controlnet_path:
            from diffusers import ControlNetModel, StableDiffusionXLControlNetPipeline
            cn_abs = (controlnet_path if os.path.isabs(controlnet_path)
                      else os.path.join(ROOT, controlnet_path))
            if not os.path.exists(cn_abs):
                raise GenError(f"controlnet model not found: {controlnet_path}", code=4)
            controlnet = ControlNetModel.from_pretrained(cn_abs, torch_dtype=torch.bfloat16)
            pipe = StableDiffusionXLControlNetPipeline.from_single_file(
                model_abs, controlnet=controlnet, torch_dtype=torch.bfloat16
            )
        else:
            from diffusers import StableDiffusionXLPipeline
            pipe = StableDiffusionXLPipeline.from_single_file(
                model_abs, torch_dtype=torch.bfloat16
            )
        # Optional subject LoRA (sharpens a specific champion's identity). Applied
        # before device placement / offload. lora_path may be a dir or a
        # .safetensors file; both are accepted by load_lora_weights.
        lora_rel = config.get("lora_path")
        if lora_rel:
            lora_abs = lora_rel if os.path.isabs(lora_rel) else os.path.join(ROOT, lora_rel)
            if not os.path.exists(lora_abs):
                raise GenError(f"lora_path set but not found: {lora_rel}", code=4)
            pipe.load_lora_weights(lora_abs)
        # Optional IP-Adapter (reference-image concept guidance). Loaded BEFORE
        # device placement on purpose: SDXL txt2img's model_cpu_offload_seq is
        # text_encoder->text_encoder_2->image_encoder->unet->vae, so registering
        # the CLIP image_encoder first is what gets it offload-hooked. Loading it
        # after enable_model_cpu_offload leaves the encoder unhooked on CPU and
        # the run dies with a CUDA/CPU device mismatch the moment it encodes
        # ip_adapter_image - the exact ordering gotcha hit end-to-end on the
        # inpaint pipe (lw_gen_weaponpass.py:262-274).
        if ip_adapter is not None:
            ip_abs, _weight_abs = resolve_ip_adapter(ip_adapter)
            pipe.load_ip_adapter(
                ip_abs, subfolder=ip_adapter["subfolder"],
                weight_name=ip_adapter["weight_name"],
                image_encoder_folder=ip_adapter["image_encoder_folder"],
            )
            pipe.set_ip_adapter_scale(float(ip_adapter["scale"]))
        gen = config.get("gen") or {}
        # cpu-offload manages device placement itself; calling .to("cuda") first
        # conflicts with it, so only move to cuda on the all-resident fast path.
        if gen.get("offload", True) and not fast:
            pipe.enable_model_cpu_offload()
        else:
            pipe = pipe.to("cuda")
        if gen.get("tiled_vae", True) and hasattr(pipe, "vae"):
            try:
                pipe.vae.enable_tiling()
            except Exception:  # noqa: BLE001 - tiling is best-effort
                pass
        return pipe
    except GenError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise GenError(f"could not load the generator model: {exc}", code=4) from exc


def _extract_pose(ref_abs, res):
    """Extract an OpenPose skeleton (with hand keypoints) from a real splash, sized to
    res, for ControlNet pose conditioning. Lazy controlnet_aux import - never in CI."""
    from controlnet_aux import OpenposeDetector
    from PIL import Image
    detector = OpenposeDetector.from_pretrained("lllyasviel/Annotators")
    img = Image.open(ref_abs).convert("RGB").resize((res[0], res[1]))
    return detector(img, hand_and_face=True, output_type="pil").resize((res[0], res[1]))


def _generate_candidates(pipe, plan, style_def, config, res, pos, neg, batch_dir,
                         count, round_no, start_index, init_image=None,
                         control_image=None, ip_adapter_image=None):
    """Generate `count` candidate PNGs; return their manifest candidate dicts.

    When control_image is given, `pipe` is a ControlNet pipeline conditioned on an
    OpenPose skeleton (natural pose + correct hand chirality, sharp txt2img detail) at
    plan['controlnet_scale']. Else when init_image is given, `pipe` is image2image
    seeded from a real reference at plan['img2img_strength']. Else plain txt2img."""
    sampler = style_def.get("sampler") or config.get("sampler") or {}
    steps = int(sampler.get("steps", 30))
    base_cfg = float(sampler.get("cfg", 5.5))
    # round>=2 bumps cfg and emphasises the subject aliases (regen escalation).
    cfg = base_cfg + 0.5 * (round_no - 1)
    round_pos = pos
    if round_no >= 2:
        emphasis = ", ".join(plan["subject_aliases"])
        round_pos = f"{pos}, {emphasis}"

    # Only ever present when the caller loaded an IP-Adapter; an empty dict means
    # every pipe call below is byte-identical to the pre-IP-Adapter code path.
    ip_kw = {} if ip_adapter_image is None else {"ip_adapter_image": ip_adapter_image}

    out = []
    # ONE hold for the whole round rather than one per candidate: the pipe is
    # already resident, and releasing between candidates would only hand another
    # process a card LW still occupies. The caller shells lw_gen_qa AFTER this
    # returns, never inside - see the module header on the hybrid case.
    try:
        with gpu_lock("cuda"):
            for i in range(count):
                idx = start_index + i
                seed = random.randint(0, 2**31 - 1)
                fname = f"cand_{idx:02d}.png"
                fpath = os.path.join(batch_dir, fname)
                try:
                    import torch
                    generator = torch.Generator(device="cuda").manual_seed(seed)
                    if control_image is not None:
                        image = pipe(
                            prompt=round_pos, negative_prompt=neg,
                            image=control_image,
                            controlnet_conditioning_scale=float(
                                plan.get("controlnet_scale", 0.75)),
                            width=res[0], height=res[1],
                            num_inference_steps=steps, guidance_scale=cfg,
                            generator=generator, **ip_kw,
                        ).images[0]
                    elif init_image is not None:
                        image = pipe(
                            prompt=round_pos, negative_prompt=neg,
                            image=init_image,
                            strength=float(plan.get("img2img_strength", 0.55)),
                            num_inference_steps=steps, guidance_scale=cfg,
                            generator=generator, **ip_kw,
                        ).images[0]
                    else:
                        image = pipe(
                            prompt=round_pos, negative_prompt=neg,
                            width=res[0], height=res[1],
                            num_inference_steps=steps, guidance_scale=cfg,
                            generator=generator, **ip_kw,
                        ).images[0]
                    image.save(fpath)
                except GenError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    raise GenError(f"generation failed on {fname}: {exc}",
                                   code=4) from exc
                out.append(new_candidate_record(fname, seed, round_no))
    except GpuBusy as exc:
        raise GenError(
            "the GPU is held by another run and did not free in time; "
            "generation skipped. See logs/ for the winmutex trace.",
            code=4) from exc
    return out


# --------------------------------------------------------------------------
# Subprocess chain (QA in the metrics venv, promote in base python).
# --------------------------------------------------------------------------
def _venv_python(config, key, root=ROOT):
    venvs = config.get("venvs") or {}
    return os.path.join(root, venvs.get(key, f".venv-{key}"), "Scripts", "python.exe")


def _shell_stage(python_exe, script, batch_dir, tag, extra_args=None):
    proc = subprocess.run(
        [python_exe, script, batch_dir] + list(extra_args or []),
        capture_output=True, text=True, creationflags=NO_WINDOW,
    )
    if proc.returncode != 0:
        raise GenError(
            f"[{tag}] failed (rc={proc.returncode}): {(proc.stderr or '')[-400:]}",
            code=5,
        )
    return proc.stdout


def _count_passes(manifest):
    return sum(1 for c in manifest.get("candidates", []) if c.get("verdict") == "PASS")


# --------------------------------------------------------------------------
# Orchestration.
# --------------------------------------------------------------------------
def run(args, config=None, styles=None):
    config = config if config is not None else load_config()
    styles = styles if styles is not None else load_styles()
    # CLI LoRA override (used by the per-champion subject-LoRA flow).
    if getattr(args, "no_lora", False):
        config = dict(config)
        config["lora_path"] = None
    elif getattr(args, "lora_path", None):
        config = dict(config)
        config["lora_path"] = args.lora_path
    # CLI base-model override (test an alternate checkpoint, e.g. an anime SDXL base).
    if getattr(args, "model_path", None):
        config = dict(config)
        config["model_path"] = args.model_path

    cli = {
        "subject": args.subject, "style": args.style, "n": args.n,
        "aspect": args.aspect, "prompt_extra": args.prompt_extra,
        "negative_extra": args.negative_extra, "seed": args.seed,
        "max_regen_rounds": args.max_regen_rounds, "top_k": args.top_k,
        "init_image": getattr(args, "init_image", None),
        "img2img_strength": getattr(args, "img2img_strength", None),
        "controlnet_pose": getattr(args, "controlnet_pose", None),
        "controlnet_scale": getattr(args, "controlnet_scale", None),
    }
    brief = load_brief(args.brief) if args.brief else {}
    plan = resolve_plan(cli, config, styles, brief)

    # Aspect guard (before any heavy work).
    res = resolve_resolution(plan["aspect"], config)

    # RC-live hard gate (before importing torch).
    rc = config.get("rc_live") or {}
    flag_rel = rc.get("flag_path")
    flag_abs = os.path.join(ROOT, flag_rel) if flag_rel else None
    status = rc_live_check(config, flag_path=flag_abs)
    ok, msg = rc_live_gate(status, force=args.force, allow_when_unsure=args.allow_when_unsure)
    if msg:
        print(msg)
    if not ok:
        raise GenError("RC-live gate refused generation.", code=3)

    # Provisioning check - safe to invoke before any download exists.
    prov_ok, prov_msg = check_provisioned(config)
    if not prov_ok:
        raise GenError(prov_msg, code=4)

    apply_env(config)

    style_def = styles[plan["style"]]
    pos, neg = build_prompts(style_def, plan["subject"], plan["prompt_extra"],
                             plan["negative_extra"])

    if plan["seed"] is not None:
        random.seed(plan["seed"])

    batch_id = make_batch_id(plan["subject"], plan["style"])
    out_root = args.out_root or DEFAULT_OUT_ROOT
    if not os.path.isabs(out_root):
        out_root = os.path.join(ROOT, out_root)
    batch_dir = os.path.join(out_root, batch_id)
    os.makedirs(batch_dir, exist_ok=True)

    # IP-Adapter reference-image guidance (identity/concept transfer without a
    # trained LoRA). None unless --ip-adapter-image was passed, so the default
    # path never loads an adapter and never changes a pixel.
    ip_adapter = None
    ip_adapter_image = None
    ip_ref_abs = None
    ip_ref_rel = getattr(args, "ip_adapter_image", None)
    if ip_ref_rel:
        ip_ref_abs = (ip_ref_rel if os.path.isabs(ip_ref_rel)
                      else os.path.join(ROOT, ip_ref_rel))
        if not os.path.exists(ip_ref_abs):
            raise GenError(f"ip_adapter_image not found: {ip_ref_rel}", code=2)
        from PIL import Image
        ip_adapter_image = Image.open(ip_ref_abs).convert("RGB")
        ip_adapter = {
            "path": (getattr(args, "ip_adapter_path", None)
                     or (config.get("weapon") or {}).get("ip_adapter_path")
                     or "tools/models/ip-adapter"),
            "subfolder": "sdxl_models",
            # Default = the general adapter (one global CLIP ViT-H embedding, so it
            # transfers palette/costume but not facial structure). Override to
            # ip-adapter-plus-face_sdxl_vit-h.safetensors for the face-tuned
            # patch-embedding variant - see docs/GEN_MODELS.md IP-Adapter table.
            "weight_name": (getattr(args, "ip_adapter_weight_name", None)
                            or "ip-adapter_sdxl_vit-h.safetensors"),
            "image_encoder_folder": "models/image_encoder",
            "scale": float(getattr(args, "ip_adapter_scale", None) or 0.5),
        }
        # Validate NOW, not at pipe-build time: loading the base checkpoint is
        # multi-GB and minutes long, and failing after it for a typo'd weight
        # name wastes the whole load. Fail before anything heavy happens.
        resolve_ip_adapter(ip_adapter)

    manifest = build_manifest(plan, config, style_def, res, pos, neg, batch_id, args.fast)
    if ip_adapter is not None:
        # Provenance only, and only when the adapter is actually on - a default
        # run's manifest is unchanged.
        manifest["ip_adapter"] = dict(ip_adapter, reference_image=ip_ref_abs)
    manifest_path = os.path.join(batch_dir, "gen_manifest.json")

    model_abs = os.path.join(ROOT, config["model_path"])

    # ControlNet-OpenPose (natural pose + correct hand chirality, keeping sharp txt2img
    # detail): extract a skeleton from a real splash and condition on it. Takes
    # precedence over img2img. config.controlnet_openpose_path = the ControlNet model dir.
    control_image = None
    init_image = None
    if plan.get("controlnet_pose"):
        if not os.path.exists(plan["controlnet_pose"]):
            raise GenError(f"controlnet_pose ref not found: {plan['controlnet_pose']}", code=2)
        cn_path = config.get("controlnet_openpose_path")
        if not cn_path:
            raise GenError(
                "controlnet_pose set but config.controlnet_openpose_path is missing", code=4
            )
        pipe = _load_pipeline(config, model_abs, args.fast, controlnet_path=cn_path,
                              ip_adapter=ip_adapter)
        control_image = _extract_pose(plan["controlnet_pose"], res)
    else:
        pipe = _load_pipeline(config, model_abs, args.fast, ip_adapter=ip_adapter)
        # img2img: seed from a real reference splash (inherits pose, palette, hands).
        # Derive an image2image pipe from the loaded base (from_pipe reuses weights).
        if plan.get("init_image"):
            if not os.path.exists(plan["init_image"]):
                raise GenError(f"init_image not found: {plan['init_image']}", code=2)
            from PIL import Image
            from diffusers import AutoPipelineForImage2Image
            init_image = Image.open(plan["init_image"]).convert("RGB").resize(
                (res[0], res[1])
            )
            pipe = AutoPipelineForImage2Image.from_pipe(pipe)

    metrics_py = _venv_python(config, "metrics")
    qa_script = os.path.join(ROOT, "tools", "lw_gen_qa.py")
    promote_script = os.path.join(ROOT, "tools", "lw_gen_promote.py")

    produced = 0
    for round_no in range(1, plan["max_regen_rounds"] + 1):
        needed = plan["n"] - _count_passes(manifest)
        if needed <= 0:
            break
        new_cands = _generate_candidates(
            pipe, plan, style_def, config, res, pos, neg, batch_dir,
            needed, round_no, produced, init_image=init_image,
            control_image=control_image, ip_adapter_image=ip_adapter_image,
        )
        produced += len(new_cands)
        manifest["candidates"].extend(new_cands)
        _atomic_write_json(manifest_path, manifest)

        if args.no_chain:
            continue

        _shell_stage(metrics_py, qa_script, batch_dir, "qa")
        manifest = _read_json(manifest_path)  # QA rewrote it in place
        if _count_passes(manifest) > 0:
            break

    # Weapon pass (M1 W1): a masked SDXL inpaint re-roll of the wrist weapon
    # region, then a full-image re-QA so verdicts reflect the fixed files. It
    # shares only the batch dir + manifest (interlock contract). Propose mode
    # (no --wrist) emits both-wrist overlays and returns without inpainting.
    if getattr(args, "weapon_fix", False) and not args.no_chain:
        gen_py = _venv_python(config, "gen")
        weaponpass_script = os.path.join(ROOT, "tools", "lw_gen_weaponpass.py")
        if args.wrist:
            weapon_args = [
                "--wrist", args.wrist,
                "--weapon-rung", args.weapon_rung or "w1",
                "--weapon-min-conf", str(args.weapon_min_conf or 0.3),
            ]
            if args.weapon_only:
                weapon_args += ["--only", args.weapon_only]
            _shell_stage(gen_py, weaponpass_script, batch_dir, "weapon", weapon_args)
            _shell_stage(metrics_py, qa_script, batch_dir, "qa")
            manifest = _read_json(manifest_path)
            # fall through to promote (verdicts now reflect the wfix files)
        else:
            _shell_stage(gen_py, weaponpass_script, batch_dir, "weapon", ["--propose"])
            manifest = _read_json(manifest_path)
            _print_summary(batch_dir, batch_id, manifest, args.no_chain)
            print("weapon propose: overlays in weapon_review/ - re-run with "
                  "--weapon-fix --wrist {left,right} to inpaint")
            return 0

    if not args.no_chain:
        _shell_stage(sys.executable, promote_script, batch_dir, "promote")
        manifest = _read_json(manifest_path)

    _print_summary(batch_dir, batch_id, manifest, args.no_chain)
    return 0


def _print_summary(batch_dir, batch_id, manifest, no_chain):
    print(f"batch scratch: {batch_dir}")
    promote = manifest.get("promote") or {}
    promoted = promote.get("promoted") or []
    review = promote.get("review") or []
    if promoted:
        print("promoted:")
        for p in promoted:
            print(f"  {p.get('dest')}")
    if review:
        print(f"review (near-miss, kept for eyeball): {os.path.join(batch_dir, 'review')}")
    if no_chain:
        print("(--no-chain: QA + promote were skipped; run them manually)")
    py = sys.executable
    print("next: intake the promoted stage-0 inputs, then annotate provenance:")
    print(f"  {py} tools/lw_pipeline.py intake --all")
    print(f"  source_url = gen://lw-gen/{batch_id}  tool = lw-gen")


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="lw_gen_run.py",
        description="Legion Wallpaper generator sidecar - batch run + QA/promote chain.",
    )
    p.add_argument("--subject")
    p.add_argument("--style", default=None, help="style key (default splash)")
    p.add_argument("--n", type=int, default=None, help="candidate count (default 4)")
    p.add_argument("--aspect", default=None, help="aspect (MVP: 16:9 only)")
    p.add_argument("--brief", default=None, help="path to a brief JSON (CLI flags override it)")
    p.add_argument("--prompt-extra", dest="prompt_extra", default=None)
    p.add_argument("--negative-extra", dest="negative_extra", default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--max-regen-rounds", dest="max_regen_rounds", type=int, default=None)
    p.add_argument("--top-k", dest="top_k", type=int, default=None)
    p.add_argument("--out-root", dest="out_root", default=None)
    p.add_argument("--fast", action="store_true", help="all-resident (disables offload)")
    p.add_argument("--no-chain", dest="no_chain", action="store_true",
                   help="skip the QA + promote subprocess chain")
    p.add_argument("--allow-when-unsure", dest="allow_when_unsure", action="store_true",
                   help="proceed when RC-live state cannot be determined")
    p.add_argument("--force", action="store_true",
                   help="bypass the RC-live gate (discouraged; warns)")
    p.add_argument("--lora-path", dest="lora_path", default=None,
                   help="override config lora_path (subject LoRA dir or .safetensors)")
    p.add_argument("--no-lora", dest="no_lora", action="store_true",
                   help="force generation with NO subject LoRA (baseline)")
    p.add_argument("--init-image", dest="init_image", default=None,
                   help="img2img: seed generation from a real reference splash (path)")
    p.add_argument("--img2img-strength", dest="img2img_strength", type=float,
                   default=None,
                   help="img2img denoise strength 0-1 (default 0.55; lower = closer to reference)")
    p.add_argument("--model-path", dest="model_path", default=None,
                   help="override config model_path (test an alternate base checkpoint)")
    p.add_argument("--controlnet-pose", dest="controlnet_pose", default=None,
                   help="ControlNet-OpenPose: real splash to extract a pose skeleton from "
                        "(natural pose + correct hands, sharp txt2img)")
    p.add_argument("--controlnet-scale", dest="controlnet_scale", type=float, default=None,
                   help="ControlNet conditioning scale 0-1 (default 0.75)")
    p.add_argument("--ip-adapter-image", dest="ip_adapter_image", default=None,
                   help="IP-Adapter reference image (path). Carries identity/concept "
                        "from a real reference without a trained LoRA. Omit = adapter off.")
    p.add_argument("--ip-adapter-scale", dest="ip_adapter_scale", type=float, default=None,
                   help="IP-Adapter conditioning scale 0-1 (default 0.5)")
    p.add_argument("--ip-adapter-path", dest="ip_adapter_path", default=None,
                   help="override the IP-Adapter model root (default "
                        "config.weapon.ip_adapter_path, else tools/models/ip-adapter)")
    p.add_argument("--ip-adapter-weight-name", dest="ip_adapter_weight_name", default=None,
                   help="IP-Adapter weight filename inside sdxl_models/ (default "
                        "ip-adapter_sdxl_vit-h.safetensors; use "
                        "ip-adapter-plus-face_sdxl_vit-h.safetensors for the face variant)")
    p.add_argument("--weapon-fix", dest="weapon_fix", action="store_true",
                   help="run the M1 weapon pass after gen/QA (masked inpaint re-roll)")
    p.add_argument("--wrist", choices=["left", "right"], default=None,
                   help="weapon rig side; omit with --weapon-fix for propose mode")
    p.add_argument("--weapon-rung", dest="weapon_rung", default="w1",
                   help="weapon pass rung (default w1: masked inpaint re-roll)")
    p.add_argument("--weapon-only", dest="weapon_only", default=None,
                   help="restrict the weapon pass to one cand file (cand_XX.png)")
    p.add_argument("--weapon-min-conf", dest="weapon_min_conf", type=float, default=None,
                   help="pose keypoint confidence floor for the weapon pass (default 0.3)")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except GenError as exc:
        print(f"lw-gen: {exc}", file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    raise SystemExit(main())
