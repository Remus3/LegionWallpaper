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
import datetime
import json
import os
import random
import subprocess
import sys
from collections import namedtuple

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
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
# Generation (LAZY torch/diffusers - never reached in CI).
# --------------------------------------------------------------------------
def _load_pipeline(config, model_abs, fast):
    """Lazily build a diffusers text2image pipeline. Heavy imports live here."""
    try:
        import torch  # noqa: F401
        from diffusers import StableDiffusionXLPipeline
    except Exception as exc:  # noqa: BLE001 - degrade, never dump a raw import error
        raise GenError(
            "generator backend unavailable (torch/diffusers not importable in "
            ".venv-gen). See docs/GEN_MODELS.md Phase-0 setup.",
            code=4,
        ) from exc
    try:
        pipe = StableDiffusionXLPipeline.from_single_file(
            model_abs, torch_dtype=torch.bfloat16
        )
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


def _generate_candidates(pipe, plan, style_def, config, res, pos, neg, batch_dir,
                         count, round_no, start_index):
    """Generate `count` candidate PNGs; return their manifest candidate dicts."""
    sampler = style_def.get("sampler") or config.get("sampler") or {}
    steps = int(sampler.get("steps", 30))
    base_cfg = float(sampler.get("cfg", 5.5))
    # round>=2 bumps cfg and emphasises the subject aliases (regen escalation).
    cfg = base_cfg + 0.5 * (round_no - 1)
    round_pos = pos
    if round_no >= 2:
        emphasis = ", ".join(plan["subject_aliases"])
        round_pos = f"{pos}, {emphasis}"

    out = []
    for i in range(count):
        idx = start_index + i
        seed = random.randint(0, 2**31 - 1)
        fname = f"cand_{idx:02d}.png"
        fpath = os.path.join(batch_dir, fname)
        try:
            import torch
            generator = torch.Generator(device="cuda").manual_seed(seed)
            image = pipe(
                prompt=round_pos, negative_prompt=neg,
                width=res[0], height=res[1],
                num_inference_steps=steps, guidance_scale=cfg,
                generator=generator,
            ).images[0]
            image.save(fpath)
        except GenError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise GenError(f"generation failed on {fname}: {exc}", code=4) from exc
        out.append({
            "file": fname, "seed": seed, "round": round_no,
            "subject_cos": None, "off_cos": None, "margin": None,
            "aesthetic": None, "lap_var": None,
            "stage_a_pass": None, "stage_b_pass": None,
            "verdict": "PENDING", "reason": None,
        })
    return out


# --------------------------------------------------------------------------
# Subprocess chain (QA in the metrics venv, promote in base python).
# --------------------------------------------------------------------------
def _venv_python(config, key, root=ROOT):
    venvs = config.get("venvs") or {}
    return os.path.join(root, venvs.get(key, f".venv-{key}"), "Scripts", "python.exe")


def _shell_stage(python_exe, script, batch_dir, tag):
    proc = subprocess.run(
        [python_exe, script, batch_dir],
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

    cli = {
        "subject": args.subject, "style": args.style, "n": args.n,
        "aspect": args.aspect, "prompt_extra": args.prompt_extra,
        "negative_extra": args.negative_extra, "seed": args.seed,
        "max_regen_rounds": args.max_regen_rounds, "top_k": args.top_k,
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

    manifest = build_manifest(plan, config, style_def, res, pos, neg, batch_id, args.fast)
    manifest_path = os.path.join(batch_dir, "gen_manifest.json")

    model_abs = os.path.join(ROOT, config["model_path"])
    pipe = _load_pipeline(config, model_abs, args.fast)

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
            needed, round_no, produced,
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
