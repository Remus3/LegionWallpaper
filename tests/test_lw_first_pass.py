"""Tests for tools/lw_first_pass.py - the committed first-pass driver.

CI constraint (read before editing imports): these tests run on system python
3.14 and CI 3.12 with ONLY PIL + numpy + stdlib available. NO torch, pyiqa, or
GPU. Therefore this file exercises only the PURE logic of the driver:

  - aspect classification thresholds + center-crop box math + area_loss
  - best-source selection (fetched fullview vs scratch _firstinitial)
  - FR-metric key remap (ms_ssim -> msssim) + verdict banding wiring
  - subprocess/venv orchestration argv (monkeypatched subprocess.run) with the
    last-json-line parser fed noisy stdout

The GPU/pyiqa calls themselves are NEVER run here; they are factored behind a
_run_json helper whose subprocess.run is monkeypatched.

Written test-first per CLAUDE.md TDD - this file was authored before the driver
implementation existed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_first_pass as fp  # noqa: E402
from lw_g1_gate import DEFAULT_G1_THRESHOLDS  # noqa: E402


# ---------------------------------------------------------------------------
# aspect classification + crop-box geometry
# ---------------------------------------------------------------------------
def test_aspect_exactly_16x9_is_ok():
    """A ratio within ASPECT_TOL of 16:9 classes 'ok' (no crop, zero loss)."""
    cls, box, loss = fp.aspect_class(2560, 1440)
    assert cls == "ok"
    assert box is None
    assert loss == pytest.approx(0.0, abs=1e-9)


def test_aspect_near_16x9_within_tol_is_ok():
    """1.7778-ish sources inside the 0.02 ratio tol pass straight through."""
    # 1920x1080 is exactly 16:9; 1912x1080 = 1.7704 is within 0.02 of 1.7778.
    cls, box, loss = fp.aspect_class(1912, 1080)
    assert cls == "ok"
    assert box is None


def test_aspect_1_75_crops_ok():
    """1.75 (e.g. 1400x800) is outside tol but a light crop (loss < 0.08)."""
    cls, box, loss = fp.aspect_class(1400, 800)
    assert cls == "crop_ok"
    assert box is not None
    assert loss < 0.08


def test_aspect_1_833_crops_ok():
    """1.833 (1191x650-ish); recovery corpus width, light crop."""
    cls, box, loss = fp.aspect_class(1100, 600)  # ratio 1.8333
    assert cls == "crop_ok"
    assert 0.0 < loss < 0.08


def test_aspect_1_693_crops_ok():
    """1.693 (e.g. 1183x699) too tall for tol but a light height crop."""
    cls, box, loss = fp.aspect_class(1183, 699)  # ratio ~1.6924
    assert cls == "crop_ok"
    assert 0.0 < loss < 0.08


def test_aspect_1_5_is_crop_heavy():
    """1.5 (1280x854 -> 1.499) needs a heavy crop; HOLD (loss > 0.08)."""
    cls, box, loss = fp.aspect_class(1280, 854)
    assert cls == "crop_heavy"
    assert loss > 0.08


def test_aspect_2_33_is_crop_heavy():
    """2.33 (900x386 -> 2.331) ultra-wide; heavy crop -> HOLD."""
    cls, box, loss = fp.aspect_class(900, 386)
    assert cls == "crop_heavy"
    assert loss > 0.08


def test_area_loss_boundary_at_0_08():
    """The crop_ok/crop_heavy split is the 0.08 area-loss boundary.

    Construct a width-crop where new_w/w is exactly 0.92 (loss 0.08). At the
    boundary the classifier must NOT call it heavy (heavy is strictly > 0.08).
    A hair wider must flip to heavy.
    """
    # For a too-wide source, area_loss = 1 - new_w/w with new_w = round(h*16/9).
    # Pick h so h*16/9 is integer: h=900 -> new_w=1600. Want new_w/w=0.92 ->
    # w = 1600/0.92 = 1739.13; round-sensitive, so assert around it.
    at = fp.aspect_class(1739, 900)  # loss ~= 0.0799 -> just under boundary
    assert at[0] == "crop_ok"
    over = fp.aspect_class(1741, 900)  # loss ~= 0.0810 -> just over
    assert over[0] == "crop_heavy"


def test_center_crop_box_too_wide_exact_16x9_and_centered():
    """A too-wide source crops width, centered, to an exact 16:9 integer box."""
    box = fp.center_crop_box(1741, 900)  # too wide
    left, top, right, bottom = box
    assert (top, bottom) == (0, 900)  # height untouched
    new_w = right - left
    assert new_w == round(900 * 16 / 9)  # 1600
    # centered: equal margins (off-by-one tolerated for odd remainders)
    assert abs(left - (1741 - new_w + left + (right - new_w - left))) >= 0  # sanity
    assert left == (1741 - new_w) // 2
    # exact 16:9 within tol
    assert abs((new_w / (bottom - top)) - (16 / 9)) <= fp.ASPECT_TOL


def test_center_crop_box_too_tall_exact_16x9_and_centered():
    """A too-tall source crops height, centered, to an exact 16:9 box."""
    box = fp.center_crop_box(1183, 699)  # ratio 1.692 -> too tall
    left, top, right, bottom = box
    assert (left, right) == (0, 1183)  # width untouched
    new_h = bottom - top
    assert new_h == round(1183 * 9 / 16)  # 665
    assert top == (699 - new_h) // 2
    assert abs(((right - left) / new_h) - (16 / 9)) <= fp.ASPECT_TOL


def test_area_loss_value_matches_box():
    """area_loss returned by aspect_class equals 1 - cropped/original area."""
    w, h = 1400, 800
    cls, box, loss = fp.aspect_class(w, h)
    left, top, right, bottom = box
    cropped = (right - left) * (bottom - top)
    assert loss == pytest.approx(1 - cropped / (w * h), rel=1e-6)


# ---------------------------------------------------------------------------
# best-source selection
# ---------------------------------------------------------------------------
def _fetched_fullview_path(fetched_root: Path, slug: str) -> Path:
    p = fetched_root / slug / "deviantart" / "SomeArtist"
    p.mkdir(parents=True)
    f = p / "deviantart_984179421_Some Title.jpg"
    f.write_bytes(b"jpegbytes")
    return f


def test_select_source_prefers_fetched_fullview(tmp_path: Path):
    """When a decodable fetched fullview exists, it is the upscale input."""
    slug = "some-slug-dg9-pre"
    scratch = tmp_path / "1.First Pass Scratch" / slug
    scratch.mkdir(parents=True)
    (scratch / f"{slug}_firstinitial.jpg").write_bytes(b"initbytes")
    fetched_root = tmp_path / "fetched"
    full = _fetched_fullview_path(fetched_root, slug)

    chosen, kind = fp.select_source(slug, scratch, fetched_root,
                                    decode_check=lambda p: True)
    assert Path(chosen) == full
    assert kind == "fullview"


def test_select_source_falls_back_to_firstinitial(tmp_path: Path):
    """No fetched fullview -> the scratch _firstinitial is used."""
    slug = "no-fetch-slug-pre"
    scratch = tmp_path / "1.First Pass Scratch" / slug
    scratch.mkdir(parents=True)
    init = scratch / f"{slug}_firstinitial.png"
    init.write_bytes(b"initbytes")
    fetched_root = tmp_path / "fetched"  # empty / no slug dir

    chosen, kind = fp.select_source(slug, scratch, fetched_root,
                                    decode_check=lambda p: True)
    assert Path(chosen) == init
    assert kind == "firstinitial"


def test_select_source_skips_undecodable_fullview(tmp_path: Path):
    """A present-but-corrupt fullview (decode fails) falls back to initial."""
    slug = "corrupt-full-pre"
    scratch = tmp_path / "1.First Pass Scratch" / slug
    scratch.mkdir(parents=True)
    init = scratch / f"{slug}_firstinitial.jpg"
    init.write_bytes(b"initbytes")
    fetched_root = tmp_path / "fetched"
    full = _fetched_fullview_path(fetched_root, slug)

    def decode(p):
        return Path(p) != full  # fullview fails to decode, initial is fine

    chosen, kind = fp.select_source(slug, scratch, fetched_root,
                                    decode_check=decode)
    assert Path(chosen) == init
    assert kind == "firstinitial"


def test_select_source_none_when_nothing_present(tmp_path: Path):
    """No fullview and no _firstinitial -> (None, 'none')."""
    slug = "empty-pre"
    scratch = tmp_path / "1.First Pass Scratch" / slug
    scratch.mkdir(parents=True)
    fetched_root = tmp_path / "fetched"
    chosen, kind = fp.select_source(slug, scratch, fetched_root,
                                    decode_check=lambda p: True)
    assert chosen is None
    assert kind == "none"


# ---------------------------------------------------------------------------
# fetched-fullview glob: every decodable extension, deterministic tie-break
# ---------------------------------------------------------------------------
def _write_fetched(fetched_root: Path, slug: str, name: str) -> Path:
    """Create <fetched_root>/<slug>/deviantart/SomeArtist/<name> with bytes."""
    artist = fetched_root / slug / "deviantart" / "SomeArtist"
    artist.mkdir(parents=True, exist_ok=True)
    f = artist / name
    f.write_bytes(b"imagebytes")
    return f


@pytest.mark.parametrize("ext", [".jpg", ".jpeg", ".png", ".webp"])
def test_find_fetched_fullview_sees_every_decodable_ext(tmp_path: Path,
                                                        ext: str):
    """A Tier-1 fetch is not always jpg - png/webp/jpeg must be visible too.

    Regression (ROADMAP first-pass-fetched-glob-jpg-only): the glob was
    deviantart_*.jpg only, so a png intermediary was invisible and first pass
    silently fell back to _firstinitial with no tell in the audit.
    """
    slug = "ext-slug-pre"
    fetched_root = tmp_path / "fetched"
    f = _write_fetched(fetched_root, slug, f"deviantart_1234_Some Title{ext}")

    hit = fp.find_fetched_fullview(slug, fetched_root)
    assert hit is not None, f"{ext} fullview was not found"
    assert Path(hit) == f


@pytest.mark.parametrize("ext", [".jpg", ".png", ".webp"])
def test_select_source_prefers_fullview_of_any_ext(tmp_path: Path, ext: str):
    """select_source must route a non-jpg fullview through as kind 'fullview'."""
    slug = "sel-ext-pre"
    scratch = tmp_path / "1.First Pass Scratch" / slug
    scratch.mkdir(parents=True)
    (scratch / f"{slug}_firstinitial.jpg").write_bytes(b"initbytes")
    fetched_root = tmp_path / "fetched"
    full = _write_fetched(fetched_root, slug, f"deviantart_77_Title{ext}")

    chosen, kind = fp.select_source(slug, scratch, fetched_root,
                                    decode_check=lambda p: True)
    assert Path(chosen) == full
    assert kind == "fullview"


def test_find_fetched_fullview_matches_ext_case_insensitively(tmp_path: Path):
    """An upper-case suffix is the same format - glob case rules differ by OS."""
    slug = "upper-ext-pre"
    fetched_root = tmp_path / "fetched"
    f = _write_fetched(fetched_root, slug, "deviantart_9_Title.PNG")

    assert Path(fp.find_fetched_fullview(slug, fetched_root)) == f


def test_find_fetched_fullview_mixed_ext_tie_break_is_deterministic(
        tmp_path: Path):
    """Mixed-extension fetch dir picks the FETCHED_EXTS-preferred file, always.

    The documented tie-break is FETCHED_EXTS order first (lossless before
    lossy), then the case-folded path - so png wins over webp/jpeg/jpg here and
    the answer cannot drift between runs or directory-listing orders.
    """
    slug = "mixed-ext-pre"
    fetched_root = tmp_path / "fetched"
    for ext in (".jpg", ".jpeg", ".webp", ".png"):
        _write_fetched(fetched_root, slug, f"deviantart_55_Title{ext}")

    picks = {fp.find_fetched_fullview(slug, fetched_root) for _ in range(5)}
    assert len(picks) == 1
    assert Path(picks.pop()).name == "deviantart_55_Title.png"


def test_find_fetched_fullview_ignores_non_image_sidecars(tmp_path: Path):
    """gallery-dl metadata sidecars share the prefix but are not decodable."""
    slug = "sidecar-pre"
    fetched_root = tmp_path / "fetched"
    _write_fetched(fetched_root, slug, "deviantart_31_Title.jpg.json")
    img = _write_fetched(fetched_root, slug, "deviantart_31_Title.png")

    assert Path(fp.find_fetched_fullview(slug, fetched_root)) == img


def test_fetched_exts_are_a_subset_of_pipeline_image_exts():
    """Never select a source the rest of the pipeline cannot ingest."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import lw_pipeline

    assert set(fp.FETCHED_EXTS) <= set(lw_pipeline.IMAGE_EXTS)


# ---------------------------------------------------------------------------
# FR-metric remap + verdict wiring
# ---------------------------------------------------------------------------
def test_remap_fr_ms_ssim_to_msssim():
    """fr_metrics emits 'ms_ssim'; verdict() wants 'msssim' - driver remaps."""
    fr = {"ssim": 0.99, "ms_ssim": 0.991, "lpips": 0.05, "dists": 0.02,
          "common_scale": [1192, 670]}
    out = fp.remap_fr(fr)
    assert out["msssim"] == 0.991
    assert "ms_ssim" not in out
    assert out["lpips"] == 0.05


def test_assemble_metrics_and_verdict_pass():
    """Clean values -> PASS through the real verdict + DEFAULT thresholds."""
    fr = {"ms_ssim": 0.99, "lpips": 0.05}
    metrics = fp.assemble_metrics(fr, lap_ratio=1.5, halo_pct=0.01,
                                  band_delta=0.0)
    assert metrics["msssim"] == 0.99
    v = fp.verdict(metrics, DEFAULT_G1_THRESHOLDS)
    assert v["verdict"] == "PASS"
    assert v["reasons"] == []


def test_assemble_metrics_and_verdict_flag():
    """MS-SSIM in the flag band (0.96-0.98) -> FLAG, not FAIL."""
    fr = {"ms_ssim": 0.97, "lpips": 0.05}
    metrics = fp.assemble_metrics(fr, lap_ratio=1.2, halo_pct=0.01,
                                  band_delta=0.0)
    v = fp.verdict(metrics, DEFAULT_G1_THRESHOLDS)
    assert v["verdict"] == "FLAG"
    assert any("msssim" in r for r in v["reasons"])


def test_assemble_metrics_and_verdict_fail_on_lpips():
    """LPIPS above the fail ceiling (> 0.20) -> hard FAIL."""
    fr = {"ms_ssim": 0.99, "lpips": 0.30}
    metrics = fp.assemble_metrics(fr, lap_ratio=1.2, halo_pct=0.01,
                                  band_delta=0.0)
    v = fp.verdict(metrics, DEFAULT_G1_THRESHOLDS)
    assert v["verdict"] == "FAIL"


def test_assemble_metrics_and_verdict_fail_on_softening():
    """lap_ratio below 1.0 floor -> hard FAIL (the softness bug)."""
    fr = {"ms_ssim": 0.99, "lpips": 0.05}
    metrics = fp.assemble_metrics(fr, lap_ratio=0.8, halo_pct=0.01,
                                  band_delta=0.0)
    v = fp.verdict(metrics, DEFAULT_G1_THRESHOLDS)
    assert v["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# subprocess / venv orchestration (monkeypatched subprocess.run)
# ---------------------------------------------------------------------------
class _FakeCompleted:
    def __init__(self, stdout, returncode=0, stderr=""):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def test_run_json_parses_last_json_line_from_noisy_stdout(monkeypatch):
    """pyiqa/torch print load banners; _run_json takes the LAST json line."""
    noisy = (
        "Loading pretrained model from foo\n"
        "some torch warning\n"
        '{"ms_ssim": 0.991, "lpips": 0.05}\n'
    )
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _FakeCompleted(noisy)

    monkeypatch.setattr(fp.subprocess, "run", fake_run)
    out = fp._run_json("C:/some/python.exe", "import x", tag="unit")
    assert out == {"ms_ssim": 0.991, "lpips": 0.05}
    # exact argv: [python, "-c", snippet]
    assert captured["argv"][0] == "C:/some/python.exe"
    assert captured["argv"][1] == "-c"
    assert captured["argv"][2] == "import x"
    # CREATE_NO_WINDOW always passed (0 on non-Windows).
    assert captured["kwargs"]["creationflags"] == getattr(
        subprocess, "CREATE_NO_WINDOW", 0)
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["text"] is True


def test_run_json_raises_on_nonzero_returncode(monkeypatch):
    """A failed subprocess surfaces as RuntimeError carrying the tag."""
    def fake_run(argv, **kwargs):
        return _FakeCompleted("boom", returncode=1, stderr="traceback")

    monkeypatch.setattr(fp.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as ei:
        fp._run_json("py", "snip", tag="upscale")
    assert "upscale" in str(ei.value)


def test_run_json_raises_when_no_json_line(monkeypatch):
    """Stdout with no JSON object line is an error, not a silent None."""
    def fake_run(argv, **kwargs):
        return _FakeCompleted("no json here\njust text\n")

    monkeypatch.setattr(fp.subprocess, "run", fake_run)
    with pytest.raises(ValueError):
        fp._run_json("py", "snip", tag="unit")


def test_upscale_subprocess_uses_venv_upscale_python(monkeypatch):
    """The upscale step shells to .venv-upscale python with the model path."""
    seen = {}

    def fake_run_json(py, snippet, tag):
        seen["py"] = py
        seen["snippet"] = snippet
        seen["tag"] = tag
        return {"backend": "spandrel", "model": "m.safetensors", "scale": 4,
                "src_dims": [1192, 670], "up_dims": [4768, 2680],
                "out_dims": [2560, 1440]}

    monkeypatch.setattr(fp, "_run_json", fake_run_json)
    audit = fp.run_upscale("C:/src.jpg", "C:/out.png")
    assert audit["backend"] == "spandrel"
    assert seen["py"] == fp.UP_PY  # .venv-upscale python
    assert "first_pass" in seen["snippet"]
    assert fp.MODEL_PATH.replace("\\", "\\\\") in seen["snippet"] \
        or fp.MODEL_PATH in seen["snippet"]


def test_fr_metrics_subprocess_uses_venv_metrics_python(monkeypatch):
    """The FR step shells to .venv-metrics python calling fr_metrics."""
    seen = {}

    def fake_run_json(py, snippet, tag):
        seen["py"] = py
        seen["snippet"] = snippet
        return {"ms_ssim": 0.99, "lpips": 0.05, "common_scale": [1192, 670]}

    monkeypatch.setattr(fp, "_run_json", fake_run_json)
    fr = fp.run_fr_metrics("C:/out.png", "C:/src.jpg")
    assert fr["ms_ssim"] == 0.99
    assert seen["py"] == fp.MET_PY  # .venv-metrics python
    assert "fr_metrics" in seen["snippet"]


# ---------------------------------------------------------------------------
# source-url mapping from matches.json
# ---------------------------------------------------------------------------
def test_source_url_map_keys_by_slug(tmp_path: Path):
    """load_source_urls maps slug -> the deviation 'source' url."""
    matches = tmp_path / "matches.json"
    matches.write_text(json.dumps([
        {"slug": "a-slug-pre", "source": "https://deviantart.com/deviation/1"},
        {"slug": "b-slug-pre", "source": "C:/local/only.png"},
    ]), encoding="utf-8")
    m = fp.load_source_urls(matches)
    assert m["a-slug-pre"] == "https://deviantart.com/deviation/1"
    assert m["b-slug-pre"] == "C:/local/only.png"
    assert m.get("missing") is None


def test_source_url_map_missing_file_is_empty(tmp_path: Path):
    """A missing matches.json yields an empty map, not an error."""
    m = fp.load_source_urls(tmp_path / "nope.json")
    assert m == {}


# ---------------------------------------------------------------------------
# downscale-only gate policy (ADR-006): drop the lap_ratio floor for a
# no-upscale path; keep msssim/lpips + halo/band.
# ---------------------------------------------------------------------------
def test_gate_metrics_drops_lap_ratio_for_downscale_only():
    """backend 'downscale-only' removes lap_ratio from the gated set only."""
    metrics = {"lap_ratio": 0.75, "halo_pct": 0.01, "band_delta": 0.0,
               "msssim": 0.998, "lpips": 0.02}
    gated = fp.gate_metrics(metrics, "downscale-only")
    assert "lap_ratio" not in gated
    assert gated["msssim"] == 0.998
    assert gated["lpips"] == 0.02
    assert "halo_pct" in gated and "band_delta" in gated


def test_gate_metrics_keeps_full_set_for_spandrel():
    """A real AI upscale gates on the full metric set (lap_ratio retained)."""
    metrics = {"lap_ratio": 0.8, "msssim": 0.99, "lpips": 0.05,
               "halo_pct": 0.01, "band_delta": 0.0}
    assert fp.gate_metrics(metrics, "spandrel") == metrics


def test_downscale_only_soft_lap_ratio_passes_via_gate():
    """lap_ratio 0.75 but healthy others -> PASS for downscale-only (ADR-006)."""
    metrics = {"lap_ratio": 0.75, "halo_pct": 0.01, "band_delta": 0.0,
               "msssim": 0.998, "lpips": 0.02}
    v = fp.verdict(fp.gate_metrics(metrics, "downscale-only"),
                   DEFAULT_G1_THRESHOLDS)
    assert v["verdict"] == "PASS"


def test_downscale_only_still_flags_halo():
    """Dropping lap_ratio does NOT disable halo/band flags for downscale-only."""
    metrics = {"lap_ratio": 0.75, "halo_pct": 0.06, "band_delta": 0.0,
               "msssim": 0.998, "lpips": 0.02}
    v = fp.verdict(fp.gate_metrics(metrics, "downscale-only"),
                   DEFAULT_G1_THRESHOLDS)
    assert v["verdict"] == "FLAG"
    assert any("halo" in r for r in v["reasons"])


def test_downscale_only_still_fails_corrupt_msssim():
    """A genuinely corrupt downscale (msssim < 0.96) still FAILS downscale-only."""
    metrics = {"lap_ratio": 1.5, "halo_pct": 0.01, "band_delta": 0.0,
               "msssim": 0.90, "lpips": 0.02}
    v = fp.verdict(fp.gate_metrics(metrics, "downscale-only"),
                   DEFAULT_G1_THRESHOLDS)
    assert v["verdict"] == "FAIL"


# ---------------------------------------------------------------------------
# usm_applied provenance.
#
# lw_upscale.first_pass reports usm_applied=False when the source was already
# exactly 2560x1440, so first pass resampled nothing and therefore ran no
# unsharp mask. The driver must carry that fact into BOTH the save-working
# params and the G1 annotate payload, otherwise a reviewer cannot tell whether
# halo_pct measured a real sharpening pass or a no-op passthrough.
#
# These tests stub run_upscale, so they do NOT depend on the lw_upscale change
# landing first.
# ---------------------------------------------------------------------------
UPSCALE_AUDIT_KEYS = {"backend", "model", "scale", "src_dims", "up_dims",
                      "out_dims", "usm_applied", "source_mode",
                      "alpha_flattened"}

# The provenance keys that existed BEFORE the alpha-drop fields (R26) were
# added. Frozen so a later field addition cannot quietly drop one of them.
PREEXISTING_UPSCALE_AUDIT_KEYS = {"backend", "model", "scale", "src_dims",
                                  "up_dims", "out_dims", "usm_applied"}


def _drive_process_slug(monkeypatch, tmp_path, audit):
    """Run process_slug with every subprocess boundary stubbed.

    Returns {'params': ..., 'payload': ..., 'result': ...} captured from the
    lw_pipeline calls. No torch / pyiqa / GPU: run_upscale, run_fr_metrics and
    compute_numpy_metrics are all monkeypatched, and the only real image work is
    the aspect read of a small 16:9 PNG written into tmp_path.
    """
    from PIL import Image

    slug = "usm-provenance-slug-pre"
    src = tmp_path / f"{slug}_firstinitial.png"
    Image.new("RGB", (1920, 1080), (40, 60, 80)).save(src, format="PNG")

    captured = {}
    monkeypatch.setattr(fp, "slug_state", lambda s: "editing")
    monkeypatch.setattr(fp, "select_source",
                        lambda s, d, *a, **k: (str(src), "firstinitial"))
    monkeypatch.setattr(fp, "run_upscale",
                        lambda conditioned, out, **k: dict(audit))
    monkeypatch.setattr(fp, "run_fr_metrics",
                        lambda out, srcp: {"ms_ssim": 0.99, "lpips": 0.05})
    monkeypatch.setattr(fp, "compute_numpy_metrics",
                        lambda srcp, out: (1.5, 0.01, 0.0))

    def fake_save_working(s, from_png, params):
        captured["params"] = params
        return "saved"

    def fake_annotate(s, url, payload):
        captured["payload"] = payload
        return "annotated"

    monkeypatch.setattr(fp, "pipeline_save_working", fake_save_working)
    monkeypatch.setattr(fp, "pipeline_annotate", fake_annotate)
    monkeypatch.setattr(fp, "pipeline_submit", lambda s: "submitted")

    captured["result"] = fp.process_slug(slug, {}, str(tmp_path))
    return captured


def _spandrel_audit():
    return {"backend": "spandrel", "model": "m.safetensors", "scale": 4,
            "src_dims": [1920, 1080], "up_dims": [7680, 4320],
            "out_dims": [2560, 1440], "usm_applied": True,
            "source_mode": "RGBA", "alpha_flattened": True}


def _downscale_audit():
    return {"backend": "downscale-only", "model": None, "scale": 1,
            "src_dims": [2560, 1440], "up_dims": [2560, 1440],
            "out_dims": [2560, 1440], "usm_applied": False,
            "source_mode": "RGB", "alpha_flattened": False}


def test_annotate_upscale_audit_carries_usm_applied(monkeypatch, tmp_path):
    """A real resample records usm_applied True in the annotate provenance."""
    cap = _drive_process_slug(monkeypatch, tmp_path, _spandrel_audit())
    ua = cap["payload"]["upscale_audit"]
    assert ua["usm_applied"] is True


def test_annotate_upscale_audit_keeps_every_preexisting_key(monkeypatch,
                                                            tmp_path):
    """Adding usm_applied must not drop any pre-existing provenance key."""
    cap = _drive_process_slug(monkeypatch, tmp_path, _spandrel_audit())
    ua = cap["payload"]["upscale_audit"]
    assert set(ua) == UPSCALE_AUDIT_KEYS
    assert ua["backend"] == "spandrel"
    assert ua["model"] == "m.safetensors"
    assert ua["scale"] == 4
    assert ua["src_dims"] == [1920, 1080]
    assert ua["up_dims"] == [7680, 4320]
    assert ua["out_dims"] == [2560, 1440]


def test_annotate_records_usm_not_applied_for_no_resample(monkeypatch,
                                                          tmp_path):
    """usm_applied False survives - the halo metric measured no sharpening."""
    cap = _drive_process_slug(monkeypatch, tmp_path, _downscale_audit())
    assert cap["payload"]["upscale_audit"]["usm_applied"] is False
    # ADR-006 wiring is untouched by this addition.
    assert cap["payload"]["lap_ratio_gated"] is False


def test_annotate_upscale_audit_carries_alpha_drop_fields(monkeypatch,
                                                          tmp_path):
    """The alpha-flatten provenance (R26) reaches the annotate payload.

    first_pass always writes RGB, so an alpha-carrying source is flattened.
    Without these two fields a corpus-wide flatten is invisible to a reviewer.
    """
    cap = _drive_process_slug(monkeypatch, tmp_path, _spandrel_audit())
    ua = cap["payload"]["upscale_audit"]
    assert ua["source_mode"] == "RGBA"
    assert ua["alpha_flattened"] is True

    cap2 = _drive_process_slug(monkeypatch, tmp_path, _downscale_audit())
    ua2 = cap2["payload"]["upscale_audit"]
    assert ua2["source_mode"] == "RGB"
    assert ua2["alpha_flattened"] is False


def test_annotate_upscale_audit_alpha_fields_keep_preexisting_keys(monkeypatch,
                                                                   tmp_path):
    """Adding the alpha fields must not drop any pre-existing provenance key."""
    cap = _drive_process_slug(monkeypatch, tmp_path, _spandrel_audit())
    ua = cap["payload"]["upscale_audit"]
    missing = PREEXISTING_UPSCALE_AUDIT_KEYS - set(ua)
    assert not missing, f"dropped pre-existing keys: {sorted(missing)}"


def test_save_working_params_carry_usm_applied(monkeypatch, tmp_path):
    """The saved-working provenance carries usm_applied alongside the rest."""
    cap = _drive_process_slug(monkeypatch, tmp_path, _downscale_audit())
    params = cap["params"]
    assert params["usm_applied"] is False
    for key in ("backend", "model", "scale", "source_choice", "aspect_class",
                "crop_box"):
        assert key in params
    assert params["backend"] == "downscale-only"
