"""CI-safe data-contract tests for the lw-gen sidecar config/styles/brief JSON.

Torch-free, stdlib-only. Validates: files load as JSON, are strict 7-bit
ASCII, carry every required key, and the style templates expose the
{subject}/{prompt_extra}/{negative_extra} format slots that str.format fills.
"""
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(REPO_ROOT, "tools", "lw_gen_config.json")
STYLES_PATH = os.path.join(REPO_ROOT, "tools", "lw_gen_styles.json")
BRIEF_PATH = os.path.join(REPO_ROOT, "briefs", "ambessa.json")

STYLE_SLOTS = ("{subject}", "{prompt_extra}", "{negative_extra}")


def _load(path):
    with open(path, encoding="utf-8") as fo:
        raw = fo.read()
    return raw, json.loads(raw)


def _assert_ascii(raw, path):
    base = os.path.basename(path)
    for i, ch in enumerate(raw):
        assert ord(ch) < 128, (
            f"non-ASCII char {ch!r} (U+{ord(ch):04X}) at index {i} in {base}"
        )


# --- load + ASCII ---------------------------------------------------------

def test_config_loads_and_is_ascii():
    raw, cfg = _load(CONFIG_PATH)
    _assert_ascii(raw, CONFIG_PATH)
    assert isinstance(cfg, dict)


def test_styles_loads_and_is_ascii():
    raw, styles = _load(STYLES_PATH)
    _assert_ascii(raw, STYLES_PATH)
    assert isinstance(styles, dict)


def test_brief_loads_and_is_ascii():
    raw, brief = _load(BRIEF_PATH)
    _assert_ascii(raw, BRIEF_PATH)
    assert isinstance(brief, dict)


# --- config required keys -------------------------------------------------

def test_config_required_keys():
    _, cfg = _load(CONFIG_PATH)
    for key in (
        "model_path", "lora_path", "clip_model", "clip_pretrained",
        "sampler", "resolution", "gen", "env", "qa", "distractors",
        "top_k", "venvs", "rc_live",
    ):
        assert key in cfg, f"config missing key: {key}"


def test_config_sampler_shape():
    _, cfg = _load(CONFIG_PATH)
    sampler = cfg["sampler"]
    for key in ("name", "scheduler", "steps", "cfg"):
        assert key in sampler, f"sampler missing key: {key}"


def test_config_resolution_is_16_9_only():
    _, cfg = _load(CONFIG_PATH)
    res = cfg["resolution"]
    assert "16:9" in res, "resolution must expose the 16:9 MVP entry"
    assert res["16:9"] == [1344, 768]
    # MVP: 16:9 is the ONLY supported aspect.
    assert list(res.keys()) == ["16:9"], "MVP resolution must be 16:9-only"


def test_config_gen_block():
    _, cfg = _load(CONFIG_PATH)
    gen = cfg["gen"]
    for key in ("offload", "tiled_vae", "attention", "fast_path"):
        assert key in gen, f"gen missing key: {key}"
    assert gen["attention"] == "sdpa"


def test_config_env_blackwell():
    _, cfg = _load(CONFIG_PATH)
    env = cfg["env"]
    assert env.get("TORCH_CUDA_ARCH_LIST") == "12.0"
    assert env.get("CUDA_MODULE_LOADING") == "LAZY"


def test_config_qa_thresholds():
    _, cfg = _load(CONFIG_PATH)
    qa = cfg["qa"]
    for key in ("T_subj", "T_margin", "T_aes", "T_blur"):
        assert key in qa, f"qa missing threshold: {key}"
        assert isinstance(qa[key], (int, float))


def test_config_qa_calibration_note():
    # The QA-floor calibration rationale must ride as a sibling string key (JSON
    # cannot hold comments). T_blur was calibrated off its seed placeholder on a
    # real candidate sweep 2026-07-11; the note records the provenance + floors.
    _, cfg = _load(CONFIG_PATH)
    assert "_note_qa_calibration" in cfg
    assert isinstance(cfg["_note_qa_calibration"], str)


def test_config_distractors():
    _, cfg = _load(CONFIG_PATH)
    distractors = cfg["distractors"]
    assert isinstance(distractors, list)
    assert len(distractors) >= 10
    for name in ("Darius", "Garen", "blank canvas", "landscape photo"):
        assert name in distractors, f"distractor missing: {name}"


def test_config_venvs():
    _, cfg = _load(CONFIG_PATH)
    venvs = cfg["venvs"]
    assert venvs.get("gen") == ".venv-gen"
    assert venvs.get("metrics") == ".venv-metrics"


def test_config_rc_live_block():
    _, cfg = _load(CONFIG_PATH)
    rc = cfg["rc_live"]
    assert rc.get("mode") == "refuse"
    assert rc.get("flag_path") == "ops/runtime/rc_live.flag"
    procs = rc.get("processes")
    assert isinstance(procs, list)
    for p in (
        "LeagueClient.exe", "LeagueClientUx.exe",
        "League of Legends.exe",
    ):
        assert p in procs, f"rc_live process missing: {p}"
    # RiotClientServices.exe is DELIBERATELY excluded: it is a non-GPU background
    # launcher that lingers idle after the game closes, so gating on it would
    # permanently block gen on any box with the Riot client installed (see the
    # _note_rc_live key in the config). Vanguard (vgtray/vgc) is likewise excluded.
    assert "RiotClientServices.exe" not in procs
    for anti_cheat in ("vgtray.exe", "vgc.exe"):
        assert anti_cheat not in procs


def test_config_top_k():
    _, cfg = _load(CONFIG_PATH)
    assert cfg["top_k"] == 3


# --- styles ---------------------------------------------------------------

def test_styles_has_three_named_styles():
    _, styles = _load(STYLES_PATH)
    for name in ("splash", "portrait", "landscape-ambient"):
        assert name in styles, f"styles missing: {name}"


def test_styles_each_has_positive_negative_sampler():
    _, styles = _load(STYLES_PATH)
    for name, block in styles.items():
        assert "positive" in block, f"{name} missing positive"
        assert "negative" in block, f"{name} missing negative"
        assert "sampler" in block, f"{name} missing sampler"
        for key in ("name", "scheduler", "steps", "cfg"):
            assert key in block["sampler"], f"{name} sampler missing {key}"


def test_styles_positive_has_all_slots():
    _, styles = _load(STYLES_PATH)
    for name, block in styles.items():
        pos = block["positive"]
        assert "{subject}" in pos, f"{name} positive missing {{subject}}"
        assert "{prompt_extra}" in pos, f"{name} positive missing {{prompt_extra}}"


def test_styles_negative_has_negative_extra_slot():
    _, styles = _load(STYLES_PATH)
    for name, block in styles.items():
        assert "{negative_extra}" in block["negative"], (
            f"{name} negative missing {{negative_extra}}"
        )


def test_styles_str_format_fills_slots():
    _, styles = _load(STYLES_PATH)
    for name, block in styles.items():
        pos = block["positive"].format(
            subject="Ambessa", prompt_extra="storm sky", negative_extra="",
        )
        neg = block["negative"].format(
            subject="Ambessa", prompt_extra="", negative_extra="ugly",
        )
        # After formatting, no unfilled placeholders remain.
        for slot in STYLE_SLOTS:
            assert slot not in pos, f"{name} positive left slot {slot}"
            assert slot not in neg, f"{name} negative left slot {slot}"
        assert "Ambessa" in pos
        assert "ugly" in neg


def test_splash_negative_excludes_wallpaper_failure_modes():
    _, styles = _load(STYLES_PATH)
    neg = styles["splash"]["negative"]
    for token in (
        "anime", "cel shading", "chibi", "watermark", "multiple characters",
        "photorealistic", "extra fingers", "off-model face",
    ):
        assert token in neg, f"splash negative should exclude: {token}"


# --- brief ----------------------------------------------------------------

def test_brief_required_keys():
    _, brief = _load(BRIEF_PATH)
    for key in (
        "subject", "subject_aliases", "style", "n", "aspect",
        "prompt_extra", "negative_extra", "seed",
        "qa_subject_floor", "qa_margin_floor", "max_regen_rounds",
    ):
        assert key in brief, f"brief missing key: {key}"


def test_brief_values():
    _, brief = _load(BRIEF_PATH)
    assert brief["subject"] == "Ambessa"
    assert isinstance(brief["subject_aliases"], list)
    assert "Ambessa" in brief["subject_aliases"]
    assert brief["style"] == "splash"
    assert brief["aspect"] == "16:9"
    assert brief["seed"] is None


def test_brief_style_exists_in_styles():
    _, brief = _load(BRIEF_PATH)
    _, styles = _load(STYLES_PATH)
    assert brief["style"] in styles, "brief style not defined in styles.json"
