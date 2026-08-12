"""Faint-mark FLAG - gate v4, the last 3 recall misses (ROADMAP
`cleaning-detector-recall`).

The recall census left four `clean` images carrying a real artist mark after the
centre-overlay detector took the other eleven. All four DO carry a YOLO box -
they just score under the 0.35 detect floor, so the box is discarded before
`gate_decision` ever runs:

    110-cleanup                                      0.1366
    p2402-kda-evelynn-by-namakx-dgykw2q-pre          0.1228
    karthasbasefinal-by-alexflores-d7q5tbt-fullview  0.1135
    dragon-slayer-pantheon-by-alexflores-d7fr57n     0.0522

The census already ruled on how that signal may be used: a sub-floor box is a
good FLAG and a bad AUTO. So gate v4 sweeps YOLO down to `FAINT_CONF_MIN` and
uses the boxes between that floor and `DETECT_CONF` for one thing only -
promoting a `clean` verdict to `qa`.

Raw sub-floor boxes are too noisy to route on unfiltered, so one geometry prior
narrows them: a credit line, URL or signature is a WIDE thing. Measured over
every `clean` image carrying a sub-floor box, widths as a fraction of frame
width separate with nothing in the gap:

    real marks   0.076  0.100  0.157  0.176
    art texture  0.009  0.021  0.033

`FAINT_MIN_W_FRAC = 0.05` sits inside that gap rather than on its edge. The
prior is NOT universal and is not claimed to be: 4 of 28 `auto` boxes and 2 of
65 `qa` boxes on the live corpus are small square-ish marks that would fail it,
and the rule's one measured false flag is wide enough to pass it. It narrows a
noisy tier cheaply; it is not a classifier. A confident box is never
geometry-filtered.

The rule is applied as a POST-PASS over the v3 ladder, not as another ordered
rule, and that is the point of half the tests below: it can only ever turn
`clean` into `qa`. Placing it in the ladder above `n == 0` (which it must beat -
two of the three misses have no confident box at all) would have put it above
the `bottom_banner` / `corner_mark` rules too, and 7 currently-`auto` images on
the live corpus carry a qualifying faint box. Those 7 must not demote.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))
import lw_clean_pass as cp  # noqa: E402

_W, _H = 2560, 1440
_MID = (1280.0, 720.0)
_BOTTOM = (1280.0, 1300.0)


def _box(conf, x0, y0, x1, y1):
    return {"box": [float(x0), float(y0), float(x1), float(y1)],
            "conf": float(conf), "cls": 0}


def _wide(conf=0.12):
    """A credit-line-shaped sub-floor box: 400px wide on a 2560px frame."""
    return _box(conf, 1900, 1080, 2300, 1180)


def _narrow(conf=0.15):
    """astronaut-gnar's in-art hull text: 23px wide. Art, not a credit."""
    return _box(conf, 770, 828, 793, 863)


# ===========================================================================
# 1. the geometry filter
# ===========================================================================
def test_faint_filter_keeps_a_credit_shaped_box():
    assert cp.faint_mark_boxes([_wide()], _W, _H) == [_wide()]


def test_faint_filter_drops_a_narrow_box():
    assert cp.faint_mark_boxes([_narrow()], _W, _H) == []


def test_faint_filter_is_scale_free():
    """The floor is a FRACTION of frame width, so it must hold at any size."""
    half = _box(0.12, 950, 540, 1050, 590)          # 100px: 7.8% of 1280, 3.9% of 2560
    assert cp.faint_mark_boxes([half], 1280, 720) == [half]
    assert cp.faint_mark_boxes([half], _W, _H) == []


def test_faint_filter_drops_a_confident_box():
    """A box at or over the detect floor is not faint - the confident rules own
    it, and double-counting it here would demote real `auto` rows."""
    assert cp.faint_mark_boxes([_wide(conf=cp.DETECT_CONF)], _W, _H) == []


def test_faint_filter_drops_noise_under_the_sweep_floor():
    assert cp.faint_mark_boxes([_wide(conf=cp.FAINT_CONF_MIN - 0.01)],
                               _W, _H) == []


def test_faint_filter_needs_a_frame_size():
    """w == 0 must not raise or divide by zero - it means `unknown`, so no flag."""
    assert cp.faint_mark_boxes([_wide()], 0, 0) == []


# ===========================================================================
# 2. the gate wiring - it may ONLY promote `clean` to `qa`
# ===========================================================================
def test_faint_mark_flips_no_detections_to_qa():
    """p2402 + 110-cleanup: nothing above the floor, a credit line below it."""
    v, reason = cp.gate_decision(0, 0.0, False, 0.0, None, _W, _H, [],
                                 faint_boxes=[_wide()])
    assert (v, reason) == ("qa", "faint_mark")


def test_faint_mark_beats_the_lol_logo_keep():
    """karthasbasefinal: the wordmark KEEP fired while the artist's signature
    sat in the bottom-right corner at conf 0.114."""
    lol = ["LEAGUE OF LEGENDS"]
    assert cp.is_lol_logo(lol) is True
    v, reason = cp.gate_decision(1, 0.89, False, 0.6, _BOTTOM, _W, _H, lol,
                                 faint_boxes=[_wide(conf=0.114)])
    assert (v, reason) == ("qa", "faint_mark")


def test_faint_mark_never_demotes_an_auto():
    """7 currently-`auto` images on the live corpus carry a qualifying faint
    box. An `auto` is a stronger, already-localised signal - it stands."""
    for args, expected in (
        ((1, 0.9, True, 1.0, _BOTTOM, _W, _H, ["patreon.com/x"]),
         ("auto", "watermark_ocr")),
        ((1, 0.9, False, 0.5, _BOTTOM, _W, _H, []),
         ("auto", "bottom_banner")),
        ((1, 0.9, False, 0.5, (60.0, 60.0), _W, _H, []),
         ("auto", "corner_mark")),
    ):
        assert cp.gate_decision(*args, faint_boxes=[_wide()]) == expected


def test_faint_mark_never_rewrites_an_existing_qa_reason():
    """21 currently-`qa` images carry one. The reason a human already has is
    more specific than `faint_mark`; overwriting it would lose information."""
    v, reason = cp.gate_decision(1, 0.2, False, 0.5, _MID, _W, _H, [],
                                 overlay_score=0.9, faint_boxes=[_wide()])
    assert (v, reason) == ("qa", "centre_overlay")
    v2, reason2 = cp.gate_decision(1, 0.2, False, 0.5, _MID, _W, _H, [],
                                   faint_boxes=[_wide()])
    assert (v2, reason2) == ("qa", "low_conf")


def test_faint_mark_can_never_produce_an_auto():
    """The census ruled the sub-floor box a FLAG signal, not an AUTO one."""
    for centroid in (None, _MID, _BOTTOM, (60.0, 60.0)):
        for n, conf in ((0, 0.0), (1, 0.2)):
            v, _ = cp.gate_decision(n, conf, False, 0.5, centroid, _W, _H, [],
                                    faint_boxes=[_wide()])
            assert v != "auto"


def test_a_narrow_faint_box_leaves_clean_alone():
    """astronaut-gnar + kalista are correct KEEPs and must stay `clean`."""
    assert cp.gate_decision(0, 0.0, False, 0.0, None, _W, _H, [],
                            faint_boxes=[_narrow()]) == ("clean",
                                                         "no_detections")


def test_gate_default_is_unchanged_without_faint_boxes():
    """Every v3 caller passes none; behaviour must be identical."""
    assert cp.gate_decision(0, 0.0, False, 0.0, None, _W, _H, []) == (
        "clean", "no_detections")
    assert cp.gate_decision(1, 0.9, False, 0.5, _BOTTOM, _W, _H, []) == (
        "auto", "bottom_banner")
    assert cp.gate_decision(1, 0.89, False, 0.6, _BOTTOM, _W, _H,
                            ["LEAGUE OF LEGENDS"]) == ("clean", "lol_logo")


# ===========================================================================
# 3. the calibrated constants
# ===========================================================================
def test_constants_are_the_measured_values():
    assert cp.FAINT_CONF_MIN == pytest.approx(0.05)
    assert cp.DETECT_CONF == pytest.approx(0.35)
    assert cp.FAINT_MIN_W_FRAC == pytest.approx(0.05)


def test_width_floor_sits_inside_the_measured_gap():
    """Real marks 0.076 / 0.100 / 0.157 / 0.176 of frame width; art texture
    0.009 / 0.021 / 0.033. A floor outside that gap changes a measured
    verdict."""
    assert 0.033 < cp.FAINT_MIN_W_FRAC < 0.076


def test_sweep_floor_reaches_the_faintest_measured_mark():
    """dragon-slayer-pantheon's brush signature boxes at 0.0522 and nothing
    else in the stack sees it - tiled inference and OCR at 1x/2x/4x were both
    measured blind to it. A floor above 0.0522 re-opens that miss."""
    assert cp.FAINT_CONF_MIN <= 0.0522


# ===========================================================================
# 4. the three measured rows, pinned to their live geometry
# ===========================================================================
_MEASURED = [
    # slug, box (x0,y0,x1,y1) at 2560x1440, conf, expected verdict
    ("110-cleanup", (1131.9, 1018.0, 1533.9, 1042.6), 0.1366, "qa"),
    ("dragon-slayer-pantheon-by-alexflores-d7fr57n-fullview",
     (2338.0, 1327.0, 2533.0, 1426.0), 0.0522, "qa"),
    ("p2402-kda-evelynn-by-namakx-dgykw2q-pre",
     (1897.0, 1077.0, 2347.0, 1178.0), 0.123, "qa"),
    ("karthasbasefinal-by-alexflores-d7q5tbt-fullview",
     (2255.0, 1351.0, 2511.0, 1440.0), 0.114, "qa"),
    ("astronaut-gnar-and-poppy-splash-art-league-of-by-deivcalviz-de2r",
     (770.6, 828.0, 793.6, 863.0), 0.152, "clean"),
    ("kalista-kalista-league-of-legends-league-of-legends-riot-games-h",
     (2506.2, 818.0, 2560.0, 859.7), 0.114, "clean"),
    ("viego-the-ruined-king-by-dada-wallpaperart-dmhz060-pre",
     (2322.0, 1359.4, 2406.9, 1406.6), 0.204, "clean"),
    # The rule's ONE measured false flag, pinned so it stays visible rather
    # than folded into a pass rate: blurred stonework, 394px wide, so the width
    # prior cannot reject it. Accepted at FAINT_CONF_MIN 0.05 as the price of
    # reaching the 0.0522 signature above.
    ("dbwtlkx-eeb94ce2-166d-4457-abc3-615a5bc07fd4",
     (0.0, 4.0, 394.6, 270.9), 0.0765, "qa"),
]


@pytest.mark.parametrize("slug,box,conf,expected", _MEASURED,
                         ids=[m[0][:24] for m in _MEASURED])
def test_measured_faint_rows(slug, box, conf, expected):
    """Live boxes from the 2026-08-11 low-conf sweep over all 302 firstdones.
    The three real marks flip; the two correct KEEPs and the one ambiguous
    scribble do not. Changing FAINT_MIN_W_FRAC breaks this on purpose."""
    v, _ = cp.gate_decision(0, 0.0, False, 0.0, None, _W, _H, [],
                            faint_boxes=[_box(conf, *box)])
    assert v == expected


# ===========================================================================
# 5. the sweep wiring - one inference, split at the detect floor
# ===========================================================================
def test_detect_image_splits_the_sweep(monkeypatch, tmp_path):
    """detect_image must run YOLO ONCE at the sweep floor and split, not run it
    twice. Measured 2026-08-11 over 39 images: the conf=0.10 result filtered to
    >= 0.35 is identical to the conf=0.35 result, so the split is free."""
    from PIL import Image
    p = tmp_path / "x.png"
    Image.new("RGB", (64, 36), (10, 10, 10)).save(p)

    calls = []

    def fake_yolo(arr, model, imgsz=1024, conf=cp.DETECT_CONF, iou=0.5):
        calls.append(conf)
        return [_box(0.9, 0, 0, 10, 5), _box(0.2, 20, 0, 30, 5)]

    monkeypatch.setattr(cp, "detect_yolo", fake_yolo)
    monkeypatch.setattr(cp, "detect_ocr", lambda a, r: [])
    monkeypatch.setattr(cp, "load_models",
                        lambda *a, **k: {"yolo": None, "reader": None,
                                         "device": "cpu"})
    det = cp.detect_image(str(p))
    assert calls == [cp.FAINT_CONF_MIN]
    assert [d["conf"] for d in det["yolo"]] == [0.9]
    assert [d["conf"] for d in det["faint"]] == [0.2]
    assert det["confs"] == [0.9], "conf_max must not see the faint tier"
    assert det["boxes"] == [[0.0, 0.0, 10.0, 5.0]], "faint boxes are not mask boxes"
