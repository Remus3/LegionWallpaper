"""Cleaning DETECTOR PRECISION - the measured gate verdict of every gated slug.

ROADMAP `clean-retry-degrades`, half 2 (`cleaning-detector-precision`). The item
opened on the claim that "the cleaner FINDS work on images that need none",
citing vayne3 (team logos are design) and p08e8 (bottom band). Measured
2026-08-11 by `tools/lw_clean_detector_probe.py` over the WHOLE gated corpus -
all 21 cleaning-stage slugs, detect + gate re-run on each `_cleaninitial` (the
image the detector actually faced, before any inpaint moved pixels):

  * 14 slugs gate to `auto`. Every one of the 14 was then looked at directly:
    all 14 are an artist credit URL, a social handle, a signature or a credit
    strip - i.e. content ADR-005 says is REMOVED. ZERO false positives.
  * 4 gate to `qa` (a human decides) and 3 to `clean`. `qa` is not a false
    positive; it is the gate declining to guess.
  * The two cited cases are stale: vayne3 now detects NOTHING (the bare-"@"
    narrowing pinned by test_bare_at_glyph_is_not_watermark closed it), and
    p08e8's fire is the real "@namakxin" signature whose removal the operator
    APPROVED - its `_cleandone` differs from `_cleaninitial` by 65122 pixels.

This table is the regression net for that measurement. Each row is one real
slug's real detector output; the assertion is the gate verdict it produced on
the day the corpus was censused. Narrowing or widening any rule that flips a
row fails here, which is the "tightest matching set first" discipline from
CLAUDE.md: widen only on test evidence.

Pure + stdlib/numpy only (gate_decision and its helpers take no ML), so this
runs in CI with no GPU. OCR strings are byte-exact as EasyOCR returned them,
with non-ASCII glyphs written as backslash-u escapes to keep the source 7-bit.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tools"))
import lw_clean_pass as cp  # noqa: E402

# slug, n_boxes, conf_max, area_pct, centroid, w, h, ocr_texts, (verdict, reason)
CORPUS = [
    (
        "aatrox-the-darkin-blade-in-flames-by-vexxsoul-dm6j4xi-pre",
        1, 0.8507, 1.6414, (1241.3, 993.3), 2560, 1440,
        ["E", "D4 RKIN", "8LAD ", "4I AM", "NOT YOUR", "SALVATION", "I AM", "YOUR", "\u53e8", "DBIMANTART", "DF", "A A I  R O X", "ATROY"],
        ("auto", "watermark_ocr"),
    ),
    (
        "aidraw-2662100118-by-watercolornessie-dma7o8j-fullview",
        1, 0.5313, 0.8375, (1237.0, 993.1), 2560, 1440,
        ["WATGRGG", "@RN", "3BUACRR"],
        ("auto", "watermark_ocr"),
    ),
    (
        "caitlyn-love-confession-lol-skin-splash-art-4k-wallpaper-uhdpape",
        0, 0.0, 0.0, None, 2560, 1440,
        ["@"],
        ("clean", "no_detections"),
    ),
    (
        "dfz5w2g-8ba7345b-5776-4d83-b939-4ca7d045f545",
        2, 0.6935, 4.595, (1282.3, 1288.4), 2560, 1440,
        ["\u5c0f", "@nalcin", "PATREONCOM/NAMAKXIN"],
        ("auto", "watermark_ocr"),
    ),
    (
        "dfzlox4-7e2bdc64-36ce-41fa-80b0-c83f97fdf5f5",
        1, 0.0, 6.3633, (1279.5, 1278.9), 2560, 1440,
        ["PATREONCOM/NAMAKXIN", "@MMCXi"],
        ("auto", "watermark_ocr"),
    ),
    (
        "dfzypoo-482973ff-dfb0-44e4-a90c-386714d27faf",
        2, 0.0, 3.9964, (1284.4, 1307.2), 2560, 1440,
        ["'", "\u4ee4", "@naMalcxin", "PATREONCOM/NAMAKXIN"],
        ("auto", "watermark_ocr"),
    ),
    (
        "dfzypou-30bef263-c754-4a26-9797-484757b1c4cf",
        2, 0.536, 4.3865, (1283.4, 1312.6), 2560, 1440,
        ["\u3002", "D", "@NMAM", "PATREONCOMINAMAKXIN", "#"],
        ("auto", "watermark_ocr"),
    ),
    (
        "dfzypp1-251c5c37-e25f-496e-a9a6-4900304e6fa5",
        2, 0.0, 4.2795, (1285.1, 1313.0), 2560, 1440,
        ["I", "", "", "@IaMaLXM", "210", "PATREONCOM/NAMAKXIN"],
        ("auto", "watermark_ocr"),
    ),
    (
        "dgk8f8n-398197d0-65d6-4299-8f0b-afdd9021c395",
        1, 0.9142, 2.2781, (336.7, 1349.4), 2560, 1440,
        ["N A M A KX |N", "P & M 2 3I2", "SU"],
        ("auto", "bottom_banner"),
    ),
    (
        "fantasy-design-by-aivio-dkdq5p7-pre",
        1, 0.7855, 1.615, (1320.3, 1053.3), 2560, 1440,
        ["MI", "NTRT @m"],
        ("qa", "not_border"),
    ),
    (
        "fury-tempest-sona-by-ryoairtist-dm7ziam-pre",
        1, 0.8696, 1.7181, (1280.3, 1048.2), 2560, 1440,
        ["\u300e /ARTISPTEIJMART@"],
        ("qa", "not_border"),
    ),
    (
        "image3",
        1, 0.8003, 0.8226, (353.5, 1426.8), 2560, 1440,
        [],
        ("auto", "bottom_banner"),
    ),
    (
        "kayle-new-splash-by-su-ke-d85w02l-fullview",
        1, 0.6936, 0.552, (188.3, 1409.0), 2560, 1440,
        ["\u300b", "/5767 CI"],
        ("auto", "bottom_banner"),
    ),
    (
        "prestige-coven-xayah-by-pebano1-dmc27t0-pre",
        1, 0.8456, 1.4195, (1228.6, 994.4), 2560, 1440,
        ["@T", "UEVIt"],
        ("qa", "not_border"),
    ),
    (
        "spirit-blossom-ahri-mono-01-by-hriful-dk79ceq-pre",
        1, 0.6269, 0.8079, (196.7, 1411.5), 2560, 1440,
        ["CewawnlkauCGODualouRiRU"],
        ("auto", "bottom_banner"),
    ),
    (
        "syndra-coven-league-of-legends-by-kintanki1-dm6e10u-fullview",
        1, 0.6817, 1.3389, (1292.7, 999.0), 2560, 1440,
        ["WTMNOVDEVIANTARTS"],
        ("auto", "watermark_ocr"),
    ),
    (
        "the-ruined-king-viego-by-vexxsoul-dm6j4mu-pre",
        1, 0.7599, 0.4486, (335.8, 1339.1), 2560, 1440,
        ["TH E", "R U ] N E D", "KiN G", "IB", "50 VEREIG N", "0F", "SHAD0 WS", " AM", "NOT", "A KING", "1 AM", "NOT", "A GOD.", "1 AM", "RUINED.\"", "LEAGUEor LEGENDS"],
        ("clean", "lol_logo"),
    ),
    (
        "viego-the-king-by-slimshadywallpaper-dhawigh-pre",
        1, 0.3931, 0.921, (1321.7, 994.7), 2560, 1440,
        ["OMUA", "@", "D\u4ec2", "TTCOM"],
        ("qa", "low_conf"),
    ),
    (
        "nguyen-ky-phuc-reyjin-leblanc-j-f1",
        1, 0.9245, 0.3934, (2493.7, 1379.2), 2560, 1440,
        ["F@"],
        ("auto", "bottom_banner"),
    ),
    (
        "p08e8-shadow-hunter-vayne-by-namakx-dg9ydp9-pre",
        1, 0.9147, 2.2705, (260.5, 1356.0), 2560, 1440,
        ["@nMaci"],
        ("auto", "watermark_ocr"),
    ),
    (
        "vayne3",
        0, 0.0, 0.0, None, 2560, 1440,
        ["@"],
        ("clean", "no_detections"),
    ),
]

# The slugs whose measured verdict is NOT `auto`: the gate proposes no unattended
# edit on these. vayne3 is the operator-adjudicated clean case - its APPROVE_CLEAN
# sha256 equals its `_cleaninitial`, so the operator kept the uncleaned pixels.
KEEP_SLUGS = tuple(row[0] for row in CORPUS if row[8][0] != "auto")


@pytest.mark.parametrize("row", CORPUS, ids=[r[0][:28] for r in CORPUS])
def test_gate_reproduces_measured_corpus_verdict(row):
    (_slug, n, conf, area, centroid, w, h, ocr, expected) = row
    ocr_hit = any(cp.classify_ocr_string(t) for t in ocr)
    got = cp.gate_decision(n, conf, ocr_hit, area, centroid, w, h, ocr)
    assert got == expected


@pytest.mark.parametrize("row", [r for r in CORPUS if r[8][0] != "auto"],
                         ids=[r[0][:28] for r in CORPUS if r[8][0] != "auto"])
def test_measured_keep_cases_are_never_auto(row):
    """A rule change may re-route a KEEP slug to qa, but never to auto."""
    (_slug, n, conf, area, centroid, w, h, ocr, _expected) = row
    ocr_hit = any(cp.classify_ocr_string(t) for t in ocr)
    verdict, _reason = cp.gate_decision(n, conf, ocr_hit, area, centroid, w, h,
                                        ocr)
    assert verdict != "auto"


def test_vayne3_the_cited_false_positive_detects_nothing():
    """vayne3 opened this item; the census measured n=0 detections on it.

    Kept as its own test because the cited evidence must not be un-learned: the
    bare "@" glyph OCR'd out of the art is NOT a watermark, and with no YOLO box
    the gate never reaches a border rule at all.
    """
    assert cp.is_watermark_text(["@"]) is False
    assert cp.gate_decision(0, 0.0, False, 0.0, None, 2560, 1440, ["@"]) == (
        "clean", "no_detections")
    assert "vayne3" in KEEP_SLUGS
