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
