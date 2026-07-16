"""Tests for tools/lw_clean_pass.py - the Stage-2 cleaning harness.

Written test-first per CLAUDE.md TDD: this file was authored before the harness
implementation existed (the 27 PURE tests below drove the module into being).

CI constraint (read before editing imports): the PURE tests run on system
python 3.14 and CI 3.12 with ONLY numpy + PIL + stdlib available - NO torch,
ultralytics, easyocr, simple_lama_inpainting, or cv2, and NO GPU. Every ML
integration test (28-31) starts with pytest.importorskip on the ML deps, so it
SKIPS cleanly wherever those are absent (CI + system python) and only runs under
C:\\Tools\\lw-clean\\venv. NEVER touch images/** - all fixtures are tmp_path +
synthetic PIL/numpy images with a painted-on text box.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_pass as cp  # noqa: E402


# ---------------------------------------------------------------------------
# synthetic-image helpers (pure numpy / PIL, no ML)
# ---------------------------------------------------------------------------
def _gradient(h, w):
    """A smooth horizontal ramp 0..255 as an HxWx3 uint8 array."""
    row = np.linspace(0, 255, w, dtype=np.float64)
    g = np.repeat(row[None, :], h, axis=0)
    return np.stack([g, g, g], axis=2).astype(np.uint8)


def _hard_step(h, w, col):
    """A hard black/white vertical step at column `col` (HxWx3 uint8)."""
    a = np.zeros((h, w, 3), dtype=np.uint8)
    a[:, col:, :] = 255
    return a


# ===========================================================================
# 1. classify_ocr_string
# ===========================================================================
def test_classify_ocr_string_hits_and_misses():
    for hit in ("uhdpaper.com", "www.foo", "@handle", "ARTSTATION",
                "DeviantArt", "something.com", "user on artstation"):
        assert cp.classify_ocr_string(hit) is True
    for miss in ("Ahri", "", "Vayne", "shadow hunter"):
        assert cp.classify_ocr_string(miss) is False
    # case-insensitive + substring
    assert cp.classify_ocr_string("VISIT UHDPAPER.COM NOW") is True


# ===========================================================================
# 2. in_border_band
# ===========================================================================
def test_in_border_band_edges_center_boundary():
    w, h = 1000, 500
    # all four outer-10% edges
    assert cp.in_border_band(10, 250, w, h) is True      # left
    assert cp.in_border_band(990, 250, w, h) is True     # right
    assert cp.in_border_band(500, 10, w, h) is True      # top
    assert cp.in_border_band(500, 490, w, h) is True     # bottom
    # dead center is not
    assert cp.in_border_band(500, 250, w, h) is False
    # exact-10% boundary counts as in-band (inclusive)
    assert cp.in_border_band(100, 250, w, h) is True     # cx == 0.10*w


# ===========================================================================
# 3. dilated_union_area_pct
# ===========================================================================
def test_dilated_union_area_pct_known_overlap_empty():
    w, h = 200, 200
    # empty -> 0
    assert cp.dilated_union_area_pct([], w, h) == 0.0
    # a single 10x10 box dilated by 15 -> 40x40 = 1600 px of 40000 = 4.0 pct
    one = cp.dilated_union_area_pct([[50, 50, 60, 60]], w, h, dilate_px=15)
    assert one == pytest.approx(1600 / 40000 * 100.0, rel=1e-6)
    # two IDENTICAL boxes counted once (union), same area as one
    two = cp.dilated_union_area_pct([[50, 50, 60, 60], [50, 50, 60, 60]],
                                    w, h, dilate_px=15)
    assert two == pytest.approx(one, rel=1e-6)


# ===========================================================================
# 4. union_boxes
# ===========================================================================
def test_union_boxes_merges_overlap_keeps_disjoint():
    # overlapping pair -> single envelope box
    merged = cp.union_boxes([[0, 0, 40, 40], [20, 20, 60, 60]])
    assert len(merged) == 1
    assert merged[0] == [0, 0, 60, 60]
    # disjoint pair (clear gap) -> both preserved
    disj = cp.union_boxes([[0, 0, 10, 10], [100, 100, 120, 120]])
    assert len(disj) == 2


# ===========================================================================
# 5. dilate_box
# ===========================================================================
def test_dilate_box_clamps_at_edges():
    w, h = 100, 80
    # near top-left corner: clamps to 0, never negative
    b = cp.dilate_box([2, 3, 20, 20], w, h, dilate_px=15)
    assert b[0] == 0 and b[1] == 0
    assert b[2] == 35 and b[3] == 35
    # near bottom-right: clamps to w/h, never over
    b2 = cp.dilate_box([90, 70, 99, 79], w, h, dilate_px=15)
    assert b2[2] == w and b2[3] == h
    assert b2[0] >= 0 and b2[1] >= 0


# ===========================================================================
# 6-11. gate_decision (v2: bottom-banner accept + LoL-logo keep)
#   signature: gate_decision(n, conf_max, ocr_hit, area_pct, centroid, w, h,
#                            ocr_texts) -> (verdict, reason)
# ===========================================================================
_W, _H = 1000, 500                 # a 2:1 frame for the gate tests
_TOP_LEFT = (50, 50)               # top-edge + left corner (outer-10pct)
_MID = (500, 250)                  # dead center (no band, not bottom)
_BOTTOM = (500, 0.92 * _H)         # bottom-center banner (cy = 0.92*h)
_BOTTOM_LEFT = (80, 460)           # bottom band + left corner


def test_gate_auto_high_conf_small_border():
    # top-left corner, high conf, tiny area, no OCR -> corner_mark auto
    v, reason = cp.gate_decision(1, 0.6, False, 1.0, _TOP_LEFT, _W, _H, [])
    assert v == "auto"
    assert reason == "corner_mark"


def test_gate_qa_low_conf():
    v, reason = cp.gate_decision(1, 0.4, False, 1.0, _TOP_LEFT, _W, _H, [])
    assert v == "qa"
    assert reason == "low_conf"


def test_gate_auto_ocr_rescue():
    # conf below 0.5 but an OCR hit rescues it via the watermark_ocr path
    v, reason = cp.gate_decision(1, 0.4, True, 1.0, _MID, _W, _H, [])
    assert v == "auto"
    assert reason == "watermark_ocr"


def test_gate_qa_area_too_large():
    # bottom-band banner but area over the 8pct auto ceiling -> QA
    v, reason = cp.gate_decision(1, 0.9, False, 12.0, _BOTTOM, _W, _H, [])
    assert v == "qa"
    assert reason == "area_too_large"


def test_gate_qa_not_border():
    # mid-frame, high conf, small area, no OCR -> not_border QA
    v, reason = cp.gate_decision(1, 0.9, False, 1.0, _MID, _W, _H, [])
    assert v == "qa"
    assert reason == "not_border"


def test_gate_clean_zero_detections():
    v, reason = cp.gate_decision(0, 0.0, False, 0.0, None, _W, _H, [])
    assert v == "clean"
    assert reason == "no_detections"


# --- gate v2 new behaviour ---
def test_gate_bottom_banner_auto():
    # bottom-center artist-credit banner: cy=0.92h, conf 0.7, area 3pct
    v, reason = cp.gate_decision(1, 0.7, False, 3.0, _BOTTOM, _W, _H, [])
    assert (v, reason) == ("auto", "bottom_banner")


def test_gate_lol_logo_kept_not_inpainted():
    # garbled "LEAGUE OF LEGENDS" wordmark -> KEEP (clean), never auto-inpaint
    v, reason = cp.gate_decision(1, 0.9, False, 2.0, _BOTTOM_LEFT, _W, _H,
                                 ["JLPAGUEo", "LECENDS"])
    assert (v, reason) == ("clean", "lol_logo")


def test_gate_watermark_ocr_from_texts_auto():
    # a real patreon URL in the OCR texts routes to auto even with ocr_hit False
    v, reason = cp.gate_decision(1, 0.5, False, 3.0, _MID, _W, _H,
                                 ["PATREON.COM/NAMAKXIN"])
    assert (v, reason) == ("auto", "watermark_ocr")


# ===========================================================================
# gate v2 fuzzy OCR helpers: is_lol_logo / is_watermark_text
# ===========================================================================
def test_is_lol_logo_matches_garbled_league_only():
    for hit in (["JLPAGUEo", "LECENDS"], ["LEAGUE", "OF", "LEGENDS"],
                ["LEGENDS"]):
        assert cp.is_lol_logo(hit) is True
    for miss in (["Ahri"], [""], [], ["PATREON.COM/NAMAKXIN"]):
        assert cp.is_lol_logo(miss) is False


def test_is_watermark_text_matches_hosts_and_urls():
    for hit in (["PEBANO1.DEVIANTART"], ["patreon.com/x"], ["@handle"],
                ["uhdpaper.com"]):
        assert cp.is_watermark_text(hit) is True
    for miss in (["Ahri"], [""], [], ["JLPAGUEo", "LECENDS"]):
        assert cp.is_watermark_text(miss) is False


# ===========================================================================
# 12. masked_identity
# ===========================================================================
def test_masked_identity_outside_is_identity_tripwire():
    base = _gradient(64, 64)
    changed = base.copy()
    mask = np.zeros((64, 64), dtype=bool)
    mask[24:40, 24:40] = True          # inpaint region
    changed[24:40, 24:40] = 0          # differ ONLY inside the mask
    ssim_out, mad_out = cp.masked_identity(base, changed, mask)
    assert ssim_out == pytest.approx(1.0, abs=1e-9)
    assert mad_out == pytest.approx(0.0, abs=1e-9)
    # flip a single OUTSIDE pixel -> mad must rise above zero
    changed2 = changed.copy()
    changed2[2, 2, :] = 255 - changed2[2, 2, :]
    _, mad_out2 = cp.masked_identity(base, changed2, mask)
    assert mad_out2 > 0.0


# ===========================================================================
# 13. patch_change_ssim
# ===========================================================================
def test_patch_change_ssim_identical_vs_different():
    patch = _gradient(32, 32)
    assert cp.patch_change_ssim(patch, patch) == pytest.approx(1.0, abs=1e-9)
    other = np.zeros((32, 32, 3), dtype=np.uint8)
    full = np.full((32, 32, 3), 255, dtype=np.uint8)
    assert cp.patch_change_ssim(other, full) < 0.5


# ===========================================================================
# 14. seam_ring_ssim
# ===========================================================================
def test_seam_ring_ssim_smooth_high_step_low():
    h, w = 40, 40
    ring = np.zeros((h, w), dtype=bool)
    ring[:, 15:25] = True
    smooth = _gradient(h, w)
    step = _hard_step(h, w, col=20)
    s_smooth = cp.seam_ring_ssim(smooth, ring)
    s_step = cp.seam_ring_ssim(step, ring)
    assert s_smooth > 0.9
    assert s_step < s_smooth
    assert s_step < 0.9


# ===========================================================================
# 15-19. verify_verdict
# ===========================================================================
def test_verify_verdict_pass():
    r = cp.verify_verdict(0.999, 0.4, 0.7, False, 0.95)
    assert r["verdict"] == "pass"
    assert r["flags"] == []


def test_verify_verdict_discard_on_outside_violation():
    r1 = cp.verify_verdict(0.98, 0.4, 0.7, False, 0.95)
    assert r1["verdict"] == "discard"
    r2 = cp.verify_verdict(0.999, 2.0, 0.7, False, 0.95)
    assert r2["verdict"] == "discard"


def test_verify_verdict_fail_noop():
    r = cp.verify_verdict(0.999, 0.4, 0.97, False, 0.95)
    assert r["verdict"] == "fail"


def test_verify_verdict_fail_residue():
    r = cp.verify_verdict(0.999, 0.4, 0.7, True, 0.95)
    assert r["verdict"] == "fail"


def test_verify_verdict_flag_seam_still_passes():
    r = cp.verify_verdict(0.999, 0.4, 0.7, False, 0.90)
    assert r["verdict"] == "pass"
    assert "seam" in r["flags"]


# ===========================================================================
# residue-REDUCTION decision (root-cause: judge the drop, not the absolute)
# ===========================================================================
def test_residue_decision_reduction_and_floor():
    # cleared: after well below keep_frac*before -> residue gone (pass)
    assert cp._residue_decision(40, 0) is False
    # barely reduced: after still ~= before -> residue remains (fail)
    assert cp._residue_decision(40, 38) is True
    # nothing was there (before under the floor) -> never a fail
    assert cp._residue_decision(2, 2) is False


# ===========================================================================
# 20. build_save_working_cmd
# ===========================================================================
def test_build_save_working_cmd_tokens_and_params():
    params = {"mask_bbox": [10, 20, 30, 40], "conf": 0.87,
              "mask_area_pct": 1.2, "engine": "simple-lama"}
    argv = cp.build_save_working_cmd("myslug", r"C:\out\cand.png", params)
    i = argv.index("save-working")
    assert argv[i + 1] == "myslug"
    assert argv[argv.index("--from") + 1] == r"C:\out\cand.png"
    assert argv[argv.index("--tool") + 1] == "lama"
    back = json.loads(argv[argv.index("--params") + 1])
    assert back["mask_bbox"] == [10, 20, 30, 40]
    assert back["conf"] == 0.87


# ===========================================================================
# 21. build_cleanscan_cmds
# ===========================================================================
def test_build_cleanscan_cmds_savework_then_submit():
    cmds = cp.build_cleanscan_cmds("slug", r"C:\s\slug_cleaninitial.png")
    assert len(cmds) == 2
    sw, sub = cmds
    assert "save-working" in sw
    assert sw[sw.index("--from") + 1] == r"C:\s\slug_cleaninitial.png"
    assert sw[sw.index("--tool") + 1] == "clean-scan"
    assert json.loads(sw[sw.index("--params") + 1])["clean_scan"] is True
    assert "submit" in sub
    assert sub[sub.index("submit") + 1] == "slug"


# ===========================================================================
# 22. triage_record
# ===========================================================================
def test_triage_record_schema_and_serializable():
    rec = cp.triage_record("slug", "img.png", [[1, 2, 3, 4]], 0.8, 1.5, "auto")
    assert set(rec) >= {"slug", "image", "boxes", "conf", "mask_area_pct",
                        "verdict"}
    assert rec["verdict"] in {"auto", "qa", "clean"}
    json.dumps(rec)   # must not raise


# ===========================================================================
# 23. atomic_write_json / atomic_write_png
# ===========================================================================
def test_atomic_writes_round_trip_no_temp(tmp_path):
    jp = tmp_path / "x.json"
    cp.atomic_write_json(str(jp), {"a": 1, "b": [2, 3]})
    assert json.loads(jp.read_text(encoding="utf-8")) == {"a": 1, "b": [2, 3]}
    pp = tmp_path / "y.png"
    im = Image.new("RGB", (4, 4), (10, 20, 30))
    cp.atomic_write_png(str(pp), im)
    with Image.open(pp) as back:
        assert back.size == (4, 4)
    # a numpy array is also accepted
    arr = np.full((5, 5, 3), 128, dtype=np.uint8)
    pp2 = tmp_path / "z.png"
    cp.atomic_write_png(str(pp2), arr)
    assert pp2.is_file()
    # no leftover temp files
    assert not list(tmp_path.glob("*.part"))
    assert not list(tmp_path.glob("*.tmp"))


# ===========================================================================
# 24. select_working_image
# ===========================================================================
def test_select_working_image_prefers_highest_working(tmp_path):
    d = tmp_path / "3.Cleaning Scratch" / "slug"
    d.mkdir(parents=True)
    # empty -> None
    assert cp.select_working_image(str(d), "slug") is None
    (d / "slug_cleaninitial.png").write_bytes(b"x")
    got = cp.select_working_image(str(d), "slug")
    assert got is not None and got.endswith("slug_cleaninitial.png")
    (d / "slug_cleanworking_01.png").write_bytes(b"x")
    (d / "slug_cleanworking_02.png").write_bytes(b"x")
    got2 = cp.select_working_image(str(d), "slug")
    assert got2.endswith("slug_cleanworking_02.png")


# ===========================================================================
# 25. highpass_border_score
# ===========================================================================
def test_highpass_border_score_box_beats_flat():
    flat = np.full((120, 120, 3), 128, dtype=np.uint8)
    box = flat.copy()
    box[0:10, 0:60, :] = 0          # black strip inside the top border band
    box[0:10, 30:31, :] = 255       # a bright line -> strong edges
    s_flat = cp.highpass_border_score(flat)
    s_box = cp.highpass_border_score(box)
    assert s_box > s_flat


# ===========================================================================
# 26. lazy-import proof (CI-safety): the 5 ML modules unimportable
# ===========================================================================
def test_lazy_import_with_ml_modules_absent(monkeypatch):
    for m in ("torch", "ultralytics", "easyocr", "simple_lama_inpainting",
              "cv2"):
        monkeypatch.setitem(sys.modules, m, None)  # None -> import raises
    monkeypatch.delitem(sys.modules, "lw_clean_pass", raising=False)
    import lw_clean_pass as fresh   # must import with ML deps unavailable
    # every pure fn still works - including the difflib gate helpers, which are
    # stdlib-only and must NEVER reach for torch/easyocr/cv2.
    assert fresh.classify_ocr_string("uhdpaper.com") is True
    assert fresh.gate_decision(0, 0.0, False, 0.0, None, 100, 100, [])[0] \
        == "clean"
    assert fresh.is_lol_logo(["LEGENDS"]) is True
    assert fresh.is_watermark_text(["patreon.com/x"]) is True
    assert fresh._residue_decision(40, 0) is False
    assert fresh.dilate_box([2, 3, 20, 20], 100, 80, 15)[0] == 0
    argv = fresh.build_submit_cmd("s")
    assert "submit" in argv


# ===========================================================================
# 27. dry-run writes no pixels
# ===========================================================================
def test_process_slug_dry_run_writes_no_pixels(tmp_path, monkeypatch):
    scratch = tmp_path / "3.Cleaning Scratch" / "slug"
    scratch.mkdir(parents=True)
    img = scratch / "slug_cleaninitial.png"
    Image.new("RGB", (64, 64), (120, 120, 120)).save(img)
    before = {p.name for p in scratch.iterdir()}
    # zero detections, no ML needed
    monkeypatch.setattr(cp, "detect_image", lambda *a, **k: {
        "boxes": [], "confs": [], "ocr_texts": [], "ocr_hit": False})
    out_dir = tmp_path / "out"
    res = cp.process_slug("slug", image=str(img), out_dir=str(out_dir),
                          dry_run=True)
    assert isinstance(res, dict)
    assert res["verdict"] in {"auto", "qa", "clean"}
    # no PNG anywhere under out_dir; input dir untouched
    if out_dir.exists():
        assert not list(out_dir.glob("**/*.png"))
    assert {p.name for p in scratch.iterdir()} == before


# ===========================================================================
# 28-31. INTEGRATION (skip unless the ML venv is present)
# ===========================================================================
def _skip_unless_ml():
    for m in ("torch", "ultralytics", "easyocr", "simple_lama_inpainting",
              "cv2"):
        pytest.importorskip(m)


def test_integration_selfcheck_reports_all_deps():
    _skip_unless_ml()
    info = cp.selfcheck()
    for dep in ("torch", "ultralytics", "easyocr", "simple_lama", "cv2"):
        assert dep in info
        assert info[dep].get("version")
    assert info.get("signatures")


def test_integration_simplelama_smoke_polarity_and_composite():
    _skip_unless_ml()
    import torch
    from simple_lama_inpainting import SimpleLama
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    lama = SimpleLama(device=dev)
    base = np.full((64, 64, 3), 200, dtype=np.uint8)
    base[24:40, 24:40, :] = [255, 0, 0]         # a red block to be removed
    mask = np.zeros((64, 64), dtype=np.uint8)
    mask[24:40, 24:40] = 255                     # white = inpaint
    mask_bool = mask > 127
    out = cp.inpaint_lama(base, mask, lama)
    out_arr = np.asarray(out.convert("RGB"))
    ssim_out, mad_out = cp.masked_identity(base, out_arr, mask_bool)
    # composite rule: outside the mask must be byte-identical
    assert mad_out == pytest.approx(0.0, abs=1e-6)
    assert ssim_out == pytest.approx(1.0, abs=1e-6)
    # correct polarity: the masked region actually changed
    diff = np.mean(np.abs(base[mask_bool].astype(np.float64)
                          - out_arr[mask_bool].astype(np.float64)))
    assert diff > 1.0


def test_integration_yolo_smoke_attr_shape():
    _skip_unless_ml()
    from ultralytics import YOLO
    model = YOLO(cp.WEIGHTS_PATH)
    arr = np.full((256, 256, 3), 200, dtype=np.uint8)
    dets = cp.detect_yolo(arr, model, imgsz=256, conf=0.1)
    assert isinstance(dets, list)
    for d in dets:
        assert set(d) >= {"box", "conf", "cls"}
        assert len(d["box"]) == 4


def test_integration_easyocr_smoke_en_chsim(tmp_path):
    _skip_unless_ml()
    import easyocr
    # The clean venv's Pillow 9.5.0 freetype segfaults on any truetype draw, so
    # the readable text fixture is rendered by the system python (working
    # Pillow) in a subprocess, then OCR'd here. Confirms the en+ch_sim path.
    strip = tmp_path / "ocr_strip.png"
    script = (
        "from PIL import Image, ImageDraw, ImageFont;"
        "im=Image.new('RGB',(360,90),(255,255,255));"
        "f=ImageFont.truetype(r'C:\\Windows\\Fonts\\arial.ttf',44);"
        "ImageDraw.Draw(im).text((10,20),'uhdpaper.com',fill=(0,0,0),font=f);"
        "im.save(r'" + str(strip) + "')"
    )
    proc = subprocess.run([cp.SYS_PY, "-c", script], capture_output=True,
                          text=True, creationflags=cp.NO_WINDOW)
    if proc.returncode != 0 or not strip.is_file():
        pytest.skip("could not render OCR fixture via system python: "
                    + (proc.stderr or "")[-200:])
    reader = easyocr.Reader(["en", "ch_sim"], gpu=False)
    arr = np.asarray(Image.open(strip).convert("RGB"))
    dets = cp.detect_ocr(arr, reader)
    assert isinstance(dets, list)
    assert any(cp.classify_ocr_string(d["text"]) for d in dets)


def test_integration_text_energy_reduction_path(tmp_path):
    # The live residue check reads the DROP in text-energy, not the absolute
    # after-count (root-cause fix). A clean flat fill over a text strip must
    # drop the energy and read as residue-gone; the same strip twice must not.
    _skip_unless_ml()
    import easyocr
    strip = tmp_path / "energy_strip.png"
    script = (
        "from PIL import Image, ImageDraw, ImageFont;"
        "im=Image.new('RGB',(360,90),(255,255,255));"
        "f=ImageFont.truetype(r'C:\\Windows\\Fonts\\arial.ttf',44);"
        "ImageDraw.Draw(im).text((10,20),'uhdpaper.com',fill=(0,0,0),font=f);"
        "im.save(r'" + str(strip) + "')"
    )
    proc = subprocess.run([cp.SYS_PY, "-c", script], capture_output=True,
                          text=True, creationflags=cp.NO_WINDOW)
    if proc.returncode != 0 or not strip.is_file():
        pytest.skip("could not render energy fixture via system python: "
                    + (proc.stderr or "")[-200:])
    reader = easyocr.Reader(["en", "ch_sim"], gpu=False)
    before = np.asarray(Image.open(strip).convert("RGB"))
    after = np.full_like(before, 255)          # a clean flat fill
    bbox = [0, 0, before.shape[1], before.shape[0]]
    e_before = cp.text_energy(before, bbox, reader)
    e_after = cp.text_energy(after, bbox, reader)
    assert e_before > e_after                  # the fill removed text-energy
    assert cp._residue_decision(e_before, e_after) is False   # residue gone
    assert cp._residue_decision(e_before, e_before) is True    # no reduction
