"""Tests for tools/lw_clean_creditline.py - reading the DA credit line.

The mask-generation finding of 2026-08-22: the centre-overlay template locates
the DA LOGO well (correlation 0.75, and the rendered mask sits on it) but never
the CREDIT LINE, because the template is a median over mixed uploaders and the
line carries the uploader's name - SLIMSHADYWALLPAPER on 105, SMALLTAVERNWALLPAPER
on 107 - so the text averages out of the stack while the logo survives.

The credit line is text, so it is read rather than thresholded. What makes that
different in kind from the residue detectors already falsified is that the hit
VERIFIES ITSELF: the string contains DEVIANTART.

The reader is injected here, so easyocr never enters CI. The garbled strings
below are the actual reads observed on the two gold captures.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import lw_clean_creditline as CL  # noqa: E402


class FakeReader:
    """easyocr's readtext contract, with scripted answers."""

    def __init__(self, per_call):
        self.per_call = list(per_call)
        self.calls = 0

    def readtext(self, img, detail=1):
        self.calls += 1
        i = min(self.calls - 1, len(self.per_call) - 1)
        return self.per_call[i]


def _frame(h=1440, w=2560):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    v = 110.0 + 30.0 * np.sin(yy / 40.0) * np.cos(xx / 55.0)
    return np.clip(np.dstack([v, v * 0.95, v * 0.9]), 0, 255).astype(np.uint8)


def _box(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


# ------------------------------------------------- the self-verifying string
def test_the_garbled_reads_from_both_gold_captures_are_accepted():
    for text in ("SLMSHADYWAALPAPERDEVIANTAR",
                 "SMALLTAVERNWALLPAPERDEVIANFARTcON",
                 "SLZMSHADYWAALPAPERDEMIANTAR",
                 "SMALLTAVERNWALLPAPERDEVIAN ARTGOM"):
        assert CL.looks_like_credit(text), text


def test_half_a_read_is_not_enough_on_its_own():
    """easyocr splits 107's line, and neither half carries the host. This is
    why the reads are joined into a line BEFORE they are verified."""
    assert not CL.looks_like_credit("SMALLTAVERNWALLPAPERDEVIAN")
    assert not CL.looks_like_credit("ARTGOM")


def test_art_text_is_not_mistaken_for_a_credit_line():
    for text in ("LEAGUE OF LEGENDS", "RIOT GAMES", "SEASON 2024",
                 "ARCANE", "", "DEV", "COM"):
        assert not CL.looks_like_credit(text), text


def test_a_read_too_short_to_carry_the_host_is_rejected():
    assert not CL.looks_like_credit("DEVIANT")


def test_the_match_is_a_window_not_a_whole_string_comparison():
    """The read is a run-on of the uploader and the host."""
    assert CL.looks_like_credit("SOMEVERYLONGUPLOADERNAMEDEVIANTARTCOM")


# --------------------------------------------------------------- geometry
def test_the_band_is_where_both_captures_put_the_line():
    y0, y1 = CL.band_slice(1440)
    assert y0 <= 962 and y1 >= 1031, "105's line must be inside the band"
    assert y0 <= 982 and y1 >= 1019, "107's line must be inside the band"


def test_a_read_is_mapped_back_into_frame_coordinates():
    img = _frame()
    y0, _y1 = CL.band_slice(img.shape[0])
    reader = FakeReader([[(_box(100, 30, 500, 70), "XWALLPAPERDEVIANTARTCOM",
                           0.7)]])
    hits = CL.detect(img, reader)
    assert len(hits) == 1
    bx = hits[0]["box"]
    assert bx[0] == 100 and bx[2] == 501
    assert bx[1] == y0 + 30 and bx[3] == y0 + 71


def test_reads_that_are_not_credit_lines_are_dropped():
    img = _frame()
    reader = FakeReader([[(_box(10, 10, 90, 40), "LEAGUE OF LEGENDS", 0.9)]])
    assert CL.detect(img, reader) == []


def test_both_enhancements_are_offered_to_the_reader():
    """Neither wins on both captures, so both are run."""
    img = _frame()
    reader = FakeReader([[]])
    CL.detect(img, reader)
    assert reader.calls == 2


def test_the_same_line_found_by_both_views_is_one_hit():
    img = _frame()
    one = [(_box(100, 30, 500, 70), "XWALLPAPERDEVIANTARTCOM", 0.7)]
    two = [(_box(102, 31, 503, 71), "XWALLPAPERDEVIANTAR", 0.6)]
    assert len(CL.detect(img, FakeReader([one, two]))) == 1


def test_a_low_confidence_read_can_be_filtered_out():
    img = _frame()
    reader = FakeReader([[(_box(100, 30, 500, 70), "XWALLPAPERDEVIANTARTCOM",
                           0.2)]])
    assert CL.detect(img, reader, min_conf=0.5) == []


# ------------------------------------------------------------------- mask
def test_the_mask_pads_the_read_the_way_the_operator_brushes_it():
    img = _frame()
    hits = [{"box": [1029, 983, 1492, 1016], "text": "x", "conf": 0.7,
             "view": "highpass"}]
    m = CL.mask_from_hits(img.shape, hits)
    ys, xs = np.nonzero(m)
    assert xs.min() == 1029 - CL.PAD and xs.max() + 1 == 1492 + CL.PAD
    assert ys.min() == 983 - CL.PAD and ys.max() + 1 == 1016 + CL.PAD


def test_the_mask_never_leaves_the_band():
    img = _frame()
    y0, y1 = CL.band_slice(img.shape[0])
    hits = [{"box": [10, y0, 200, y1], "text": "x", "conf": 0.7, "view": "hp"}]
    m = CL.mask_from_hits(img.shape, hits, pad=200)
    ys, _xs = np.nonzero(m)
    assert ys.min() >= y0 and ys.max() < y1


def test_no_hits_means_no_mask_rather_than_a_frame_sized_one():
    img = _frame()
    m = CL.mask_from_hits(img.shape, [])
    assert not m.any()


def test_reads_split_across_one_line_are_joined_before_verifying():
    img = _frame()
    reader = FakeReader([[(_box(100, 30, 480, 70), "SMALLTAVERNWALLPAPERDEVIAN",
                           0.7),
                          (_box(490, 31, 560, 69), "ARTGOM", 0.5)], []])
    hits = CL.detect(img, reader)
    assert len(hits) == 1
    assert hits[0]["parts"] == 2
    assert "ARTGOM" in hits[0]["text"]
    assert hits[0]["box"][0] == 100 and hits[0]["box"][2] == 561


def test_two_lines_both_land_in_the_mask():
    img = _frame()
    hits = [{"box": [100, 900, 300, 930], "text": "a", "conf": 0.7, "view": "h"},
            {"box": [800, 960, 1200, 1000], "text": "b", "conf": 0.7,
             "view": "h"}]
    m = CL.mask_from_hits(img.shape, hits)
    assert m[900:930, 100:300].all() and m[960:1000, 800:1200].all()


def test_detection_is_deterministic():
    img = _frame()
    hits = [(_box(100, 30, 500, 70), "XWALLPAPERDEVIANTARTCOM", 0.7)]
    a = CL.detect(img, FakeReader([hits]))
    b = CL.detect(img, FakeReader([hits]))
    assert a == b


def test_the_enhancements_are_readable_images():
    img = _frame()
    y0, y1 = CL.band_slice(img.shape[0])
    views = CL.enhancements(img[y0:y1])
    assert len(views) == 2
    for _name, v in views:
        assert v.dtype == np.uint8 and v.shape == (y1 - y0, img.shape[1], 3)


# --------------------------------------------------- narrowing to the glyphs
def _with_text(img, y0, y1, x0, x1, stride=9):
    """Bright thin strokes inside a band - stand-ins for glyphs."""
    out = img.copy()
    out[y0:y1, x0:x1:stride] = 245
    out[y0:y1, x0 + 1:x1:stride] = 245
    return out


def test_the_glyph_mask_stays_inside_the_verified_box():
    img = _frame()
    box = np.zeros(img.shape[:2], dtype=bool)
    box[960:1010, 900:1500] = True
    g = CL.glyph_mask(_with_text(img, 970, 1000, 950, 1450), box)
    assert not (g & ~box).any()


def test_the_glyph_mask_finds_the_strokes_and_drops_the_gaps():
    img = _with_text(_frame(), 970, 1000, 950, 1450)
    box = np.zeros(img.shape[:2], dtype=bool)
    box[960:1010, 900:1500] = True
    g = CL.glyph_mask(img, box)
    assert 0 < int(g.sum()) < int(box.sum()), "a slab is the wrong shape"
    strokes = np.zeros_like(box)
    strokes[970:1000, 950:1450:9] = True
    assert (g & strokes).sum() > 0.5 * strokes.sum()


def test_the_glyph_mask_is_a_no_op_on_an_empty_box():
    img = _frame()
    empty = np.zeros(img.shape[:2], dtype=bool)
    assert not CL.glyph_mask(img, empty).any()


def test_growing_the_glyph_mask_only_ever_adds():
    img = _with_text(_frame(), 970, 1000, 950, 1450)
    box = np.zeros(img.shape[:2], dtype=bool)
    box[960:1010, 900:1500] = True
    tight = CL.glyph_mask(img, box, grow=2)
    wide = CL.glyph_mask(img, box, grow=6)
    assert int(wide.sum()) > int(tight.sum())
    assert (tight & ~wide).sum() == 0


# --------------------------------------------------------- census image choice
def _touch(root, slug, *names):
    os.makedirs(os.path.join(root, slug), exist_ok=True)
    for n in names:
        open(os.path.join(root, slug, n), "wb").close()


def test_the_negative_set_reads_the_approved_output_not_the_clean_input(tmp_path):
    """The precision question is about the frame the operator APPROVED.

    The first census read `_cleaninitial` out of `4.Cleaning Done` - the frame
    handed TO cleaning, which still carries its mark - so `230-cleanup` firing
    there was never a false positive, and the 118 quiet frames said nothing
    about precision either. The negative set has to read `_cleandone`.
    """
    import lw_clean_creditline_census as CEN
    root = str(tmp_path)
    _touch(root, "230-cleanup", "230-cleanup_cleaninitial.png",
           "230-cleanup_cleandone.png")
    got = CEN.approved_of(root, "230-cleanup")
    assert got.endswith("230-cleanup_cleandone.png")


def test_a_done_slug_without_an_approved_frame_is_skipped_not_downgraded(tmp_path):
    import lw_clean_creditline_census as CEN
    root = str(tmp_path)
    _touch(root, "nope", "nope_cleaninitial.png", "nope_firstinitial.png")
    assert CEN.approved_of(root, "nope") is None


# ------------------------------------------------- masking only the credit run
def test_group_lines_keeps_every_part_box():
    """Reading joins parts; masking has to be able to take them apart again."""
    reads = [((100, 200, 300, 240), "SMALLTAVERNWALLPAPERDEVIAN", 0.7),
             ((305, 201, 380, 239), "ARTCOM", 0.6)]
    lines = CL.group_lines(reads)
    assert len(lines) == 1
    assert lines[0]["boxes"] == [[100, 200, 300, 240], [305, 201, 380, 239]]


def test_the_gap_between_two_reads_of_one_line_is_masked_too():
    """MEASURED 2026-08-22: every narrower rule than the line box lost the mark.

    Splitting on gaps dropped the run that did not itself spell the host - 261f
    `SLIMSNAD=` 87px left of `APERDEVIAN`, 286f `PEBANOL` 67px left of `MIANTART
    COM` - halving the mask and leaving the credit line on the frame. Unioning
    the part boxes withholds only the gaps, which on 105 is 79px of 22075, and
    that was still enough to flip a blob to revert and leave a readable line.
    """
    line = CL.group_lines([
        ((1029, 981, 1171, 1013), "SLIMSNAD=", 0.8),
        ((1258, 984, 1425, 1011), "APERDEVIANTART", 0.6),
    ])[0]
    m = CL.mask_from_hits((1440, 2560), [line], pad=0)
    assert m[981:1013, 1029:1171].all()
    assert m[984:1011, 1258:1425].all()
    assert m[990:1005, 1180:1250].all(), "the gap between the reads is the mark"


def test_the_mask_covers_every_part_of_the_line():
    """266f is not solvable by cutting up reads - see credit_boxes.

    easyocr returns `P E R F E C T I g WExXsou_DEVIANT}` as ONE read spanning
    the poster's gold tagline AND the credit line, so no partition separates
    them. The mask takes the whole line and 266f stays an open failure for the
    eye, wanting a discriminator inside the box rather than a better split.
    """
    line = CL.group_lines([
        ((10, 20, 60, 40), "PRECISION IS PERFECTION", 0.6),
        ((200, 20, 260, 40), "XDEVIANTARTCOM", 0.5),
    ])[0]
    m = CL.mask_from_hits((100, 300), [line], pad=0, band=(0.0, 1.0))
    assert m[20:40, 10:60].all()
    assert m[20:40, 200:260].all()


# ------------------------------------------- the logo the read box never sees
#
# MEASURED 2026-08-29 over all 39 queue slugs: the mask's left edge was
# `box_x0 - PAD` and nothing else, while the mark's true left extent varies -
# 20px on small type, 35px on large type, 43px at scale 1.2, and 96px or more
# where OCR drops leading letters (124f reads TAVERIUM for SMALLTAVERN...).
# Ring ink lay outside the mask on 22 of the 39 slugs. A constant pad cannot
# track a mark whose geometry scales with the type.
LOGO = dict(cx=996, cy=995, r=13, thick=5)


def _disc_ring(img, cx, cy, r, thick, level=215):
    """A logo-shaped blob: a ring outline, like the DA mark left of the line."""
    out = img.copy()
    y0, y1 = cy - r - thick, cy + r + thick + 1
    x0, x1 = cx - r - thick, cx + r + thick + 1
    yy, xx = np.mgrid[y0:y1, x0:x1]
    d = np.hypot(yy - cy, xx - cx)
    out[y0:y1, x0:x1][(d >= r - thick / 2.0) & (d <= r + thick / 2.0)] = level
    return out


def _ridges(img, y0, y1, x0, x1, period=14, level=205):
    """Artwork: diagonal ridge lines that never stop - 105-cleanup's mountains.

    Measured on that frame, ink columns run unbroken from the read box back
    past 90px. An ink walk has to refuse this and keep its pad.
    """
    out = img.copy()
    yy, xx = np.mgrid[y0:y1, x0:x1]
    out[y0:y1, x0:x1][((yy + xx) % period) < 3] = level
    return out


def _line_hit(x0=1017, y0=972, x1=1586, y1=1018):
    return {"box": [x0, y0, x1, y1], "text": "XDEVIANTARTCOM", "conf": 0.7}


def test_a_logo_left_of_the_read_box_is_masked_when_the_image_is_given():
    """270f: the ring sits at 984..1009 and the read box starts at 1017."""
    img = _disc_ring(_with_text(_frame(), 980, 1012, 1022, 1500, stride=11),
                     **LOGO)
    m = CL.mask_from_hits(img.shape, [_line_hit()], img=img)
    ring = np.zeros(img.shape[:2], dtype=bool)
    ring[LOGO["cy"] - LOGO["r"] - 2:LOGO["cy"] + LOGO["r"] + 3,
         LOGO["cx"] - LOGO["r"] - 2:LOGO["cx"] + LOGO["r"] + 3] = True
    assert (ring & ~m).sum() == 0, "the logo has to be inside the mask"


def test_the_fixed_pad_alone_leaves_that_logo_outside_the_mask():
    """The characterisation of the defect: no image, no measurement, no reach."""
    img = _disc_ring(_with_text(_frame(), 980, 1012, 1022, 1500, stride=11),
                     **LOGO)
    m = CL.mask_from_hits(img.shape, [_line_hit()])
    assert not m[:, LOGO["cx"] - LOGO["r"] - LOGO["thick"]].any()


def test_the_walk_crosses_the_gap_between_the_logo_and_the_first_letter():
    """Measured on 270f: 12 empty columns sit between ring and first letter."""
    assert CL.LEFT_GAP > 12


def test_ink_that_runs_on_past_the_cap_is_refused_not_followed():
    """105-cleanup is a control and its artwork ink never stops.

    The mark is a BOUNDED object, so a run still going at the cap is not part
    of it. Refusing such a run outright - rather than truncating it at the cap
    - is what keeps the walk off the ridge lines.
    """
    img = _ridges(_with_text(_frame(), 980, 1012, 1022, 1500, stride=11),
                  960, 1030, 700, 1017)
    m = CL.mask_from_hits(img.shape, [_line_hit()], img=img)
    xs = np.nonzero(m.any(axis=0))[0]
    assert int(xs.min()) == 1017 - CL.PAD


def test_the_extension_never_reaches_past_the_hard_cap():
    img = _ridges(_with_text(_frame(), 980, 1012, 1022, 1500, stride=11),
                  960, 1030, 300, 1017, period=40)
    m = CL.mask_from_hits(img.shape, [_line_hit()], img=img)
    xs = np.nonzero(m.any(axis=0))[0]
    assert int(xs.min()) >= 1017 - CL.PAD - CL.LEFT_MAX


# ------------------------------------------------------------ the hop budget
#
# MEASURED 2026-08-30 over all 39 slugs, against the NCC-registered ring left
# edge as the true mark start. An unbounded walk CHAINS: each hop is legal on
# its own, and on 270f it takes the ring, then crosses a 4-column gap onto a
# 5-column speck at 972..976, and keeps going - 90px of extension where the
# mark starts 36px out, i.e. 55px of artwork pulled into the mask on a frame
# already flagged for collateral damage. Over-reach past the true mark start,
# whole queue: unlimited median 2 / p90 25 / max 67 with 5 slugs past 20px,
# against hop<=1 median 0 / p90 5 / max 15 with none past 20px.
def _bar(img, y0, y1, x0, x1, level=215):
    """A bright bar. Narrower than HP_WIN, so every column of it reads as ink."""
    out = img.copy()
    out[y0:y1, x0:x1] = level
    return out


def test_the_walk_takes_one_mark_component_and_does_not_chain():
    """270f in miniature: the logo, then a decoy 9 columns further left."""
    img = _with_text(_frame(), 980, 1012, 1022, 1500, stride=11)
    img = _disc_ring(img, cx=996, cy=995, r=10, thick=5)
    img = _disc_ring(img, cx=960, cy=995, r=10, thick=5)
    m = CL.mask_from_hits(img.shape, [_line_hit()], img=img)
    assert m[985:1005, 983:1010].all(), "the logo itself must be masked"
    assert not m[:, 947:960].any(), "the decoy past it must not be"


def test_a_narrow_speck_does_not_spend_the_hop_budget():
    """286f, 221-cleanup and queen-of-the-saltwind all put a 5-7px speck
    between the read box and the logo. A speck is not a mark component - the
    logo runs 17-34px wide everywhere it was registered - so it is taken
    without costing the hop that the logo needs."""
    img = _with_text(_frame(), 980, 1012, 1022, 1500, stride=11)
    img = _bar(img, 985, 1005, 1006, 1012)
    img = _disc_ring(img, cx=982, cy=995, r=10, thick=5)
    m = CL.mask_from_hits(img.shape, [_line_hit()], img=img)
    assert m[985:1005, 969:996].all(), "the logo past the speck must be masked"


def test_the_hop_budget_and_the_speck_width_are_named_numbers():
    """One number each, so the coverage/over-reach trade can be moved."""
    assert CL.LEFT_HOPS == 1
    assert 0 < CL.LEFT_STUB < 17


def test_the_measured_extension_is_off_when_no_image_is_offered():
    """mask_from_hits keeps working on a shape alone - the callers that have
    no pixels to hand must not change behaviour."""
    m = CL.mask_from_hits((1440, 2560), [_line_hit()])
    xs = np.nonzero(m.any(axis=0))[0]
    assert int(xs.min()) == 1017 - CL.PAD


def test_the_walk_starts_from_the_leftmost_box_of_the_line():
    img = _disc_ring(_with_text(_frame(), 980, 1012, 1022, 1500, stride=11),
                     **LOGO)
    assert CL.left_extent(img, [1017, 972, 1586, 1018]) <= 984


# ------------------------------------- a bright highlight must not raise the bar
#
# MEASURED 2026-08-29: `thr = percentile(hp[box_mask], 88)` is set by whatever
# is brightest anywhere INSIDE the box, so one bright art highlight drops the
# overlay's own strokes. On soraka-...-givemenine the padded box covers the
# ring completely and 305 of 508 ring pixels still fall below the threshold.
def _faint_text(img, y0, y1, x0, x1, stride=16, delta=26):
    out = img.astype(np.float64)
    out[y0:y1, x0:x1:stride] += delta
    out[y0:y1, x0 + 1:x1:stride] += delta
    return np.clip(out, 0, 255).astype(np.uint8)


def _highlight(img, y0, y1, x0, x1):
    out = img.astype(np.float64)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    patch = 128.0 + 120.0 * np.sin(xx / 2.0) * np.cos(yy / 3.0)
    out[y0:y1, x0:x1] = np.dstack([patch] * 3)
    return np.clip(out, 0, 255).astype(np.uint8)


def _faint_case():
    img = _faint_text(_frame(), 970, 1000, 950, 1400)
    img = _highlight(img, 960, 1010, 1420, 1560)
    box = np.zeros(img.shape[:2], dtype=bool)
    box[960:1010, 900:1600] = True
    strokes = np.zeros_like(box)
    strokes[970:1000, 950:1400:16] = True
    return img, box, strokes


def test_a_bright_highlight_inside_the_box_does_not_hide_the_strokes():
    img, box, strokes = _faint_case()
    g = CL.glyph_mask(img, box)
    assert (g & strokes).sum() > 0.5 * strokes.sum()


def test_the_percentile_alone_is_what_loses_those_strokes():
    """The characterisation: the box-global percentile lands in the highlight."""
    img, box, strokes = _faint_case()
    lum = np.asarray(img, dtype=np.float64).mean(axis=2)
    hp = np.abs(CL._highpass(lum, win=CL.HP_WIN))
    thr = float(np.percentile(hp[box], CL.GLYPH_PCT))
    assert (box & (hp >= thr) & strokes).sum() < 0.1 * strokes.sum()


def test_the_robust_threshold_only_ever_adds_to_the_percentile_rule():
    """Currently-good slugs keep every pixel they had - the rule is a union."""
    img = _with_text(_frame(), 970, 1000, 950, 1450)
    box = np.zeros(img.shape[:2], dtype=bool)
    box[960:1010, 900:1500] = True
    lum = np.asarray(img, dtype=np.float64).mean(axis=2)
    hp = np.abs(CL._highpass(lum, win=CL.HP_WIN))
    thr = float(np.percentile(hp[box], CL.GLYPH_PCT))
    old = box & (hp >= thr)
    assert (old & ~CL.glyph_mask(img, box, grow=0)).sum() == 0


def test_the_local_ink_test_is_not_a_global_percentile():
    """A stroke on a quiet background reads as ink whether or not a much
    brighter feature exists elsewhere in the frame.

    Compared more than one LOCAL_WIN away from the highlight, since the test is
    local and makes no claim about pixels the highlight is a neighbour of.
    """
    quiet = _faint_text(_frame(), 970, 1000, 950, 1400)
    loud = _highlight(quiet.copy(), 960, 1010, 1420, 1560)
    far = (slice(970, 1000), slice(950, 1420 - CL.LOCAL_WIN))
    a = CL.local_ink(quiet)[far]
    b = CL.local_ink(loud)[far]
    assert int(a.sum()) > 0
    assert np.array_equal(a, b)

