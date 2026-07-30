"""Model-free tests for tools/lw_anat_probe.py (S4 anatomical diagnostic probe).

The DWPose weights are gitignored and onnxruntime lives only in .venv-gen, so a
real DETECTION is a CAPABILITY, not the thing under test. Everything that IS the
thing under test runs against a FAKE detector and must never skip: the
COCO-WholeBody index mapping, the raw geometry, every outcome state, all six of
S3's refusal reasons, report assembly, the atomic write, the approved-milestone
selection, the zero-figure and multi-figure branches, and the
missing-metrics-module error path.

The METRIC side uses the REAL tools/lw_anat_metrics.py, not a stub - it is pure
stdlib geometry with no model dependency, so stubbing it would only test this
probe against an imagined contract. That already broke once: the module was
reworked (commit 49ec184) to return HeadSpineRefusal instead of None and to
delete classify_head_spine, and a stub would have kept passing.

Exactly one test carries a skipif, keyed on the CAPABILITY - onnxruntime
importable AND both .onnx files present.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import tools  # noqa: E402
from tools import lw_anat_metrics as lam  # noqa: E402
from tools import lw_anat_probe as lap  # noqa: E402
from tools import lw_gen_localizer_eval as lle  # noqa: E402

IMG_WH = (2560, 1440)

# An upright figure: 200 px shoulder span, 400 px spine (ratio 0.5, above S3's
# 0.35 floor), every joint above the confidence floor, head centred on the spine.
UPRIGHT = {
    0: (1280.0, 300.0, 0.91),   # nose
    1: (1260.0, 280.0, 0.88),   # left eye
    2: (1300.0, 280.0, 0.87),   # right eye
    3: (1230.0, 295.0, 0.60),   # left ear
    4: (1330.0, 295.0, 0.61),   # right ear
    5: (1180.0, 500.0, 0.93),   # left shoulder
    6: (1380.0, 500.0, 0.92),   # right shoulder
    11: (1200.0, 900.0, 0.80),  # left hip
    12: (1360.0, 900.0, 0.81),  # right hip
}


def head_shifted(dx):
    """UPRIGHT with the whole head displaced dx px off the spine axis."""
    return {**UPRIGHT, **{i: (UPRIGHT[i][0] + dx, UPRIGHT[i][1], UPRIGHT[i][2])
                          for i in (0, 1, 2, 3, 4)}}


# The census tail shape: a collapsed detection. 100 px of shoulder over 400 px of
# spine is a 0.25 ratio, under S3's MIN_SHOULDER_SPINE_RATIO of 0.35 - the two
# confirmed-bad census images measured 0.215 and 0.251.
COLLAPSED = {**UPRIGHT, 5: (1230.0, 500.0, 0.90), 6: (1330.0, 500.0, 0.90)}

# Sub-floor spine anchors - the binding constraint on 60 percent of the corpus.
LOW_CONF = {**UPRIGHT, 5: (1180.0, 500.0, 0.05), 11: (1200.0, 900.0, 0.04)}

# No head point clears the floor: 80 of the 173 unmeasurable census images.
NO_HEAD = {**UPRIGHT, **{i: (UPRIGHT[i][0], UPRIGHT[i][1], 0.02) for i in (0, 1, 2, 3, 4)}}

# Both shoulders on one point, and shoulder-mid coincident with hip-mid.
DEGENERATE_SHOULDERS = {**UPRIGHT, 5: (1280.0, 500.0, 0.9), 6: (1280.0, 500.0, 0.9)}
DEGENERATE_SPINE = {**UPRIGHT, 11: (1200.0, 500.0, 0.8), 12: (1360.0, 500.0, 0.8)}


def make_cwb(overrides, n=133):
    """133-slot COCO-WholeBody pixel list; overrides maps idx -> (x, y, conf)."""
    kps = [(0.0, 0.0, 0.0)] * n
    for idx, triple in overrides.items():
        kps[idx] = triple
    return kps


def detector_from_kps(kp_dicts, image_wh=IMG_WH, mean_scores=None, roi_source=lap.SRC_BOX):
    """A detector callable returning one figure per supplied keypoint mapping."""
    scores = mean_scores or [0.9 - 0.1 * i for i in range(len(kp_dicts))]

    def _detect(image_path):
        figs = [
            lap.DetectedFigure(keypoints=kp, mean_score=scores[i], roi_source=roi_source)
            for i, kp in enumerate(kp_dicts)
        ]
        return lap.Detection(image_wh=image_wh, figures=figs,
                             meta={"n_boxes": len(kp_dicts)})

    return _detect


def fake_detector(n_figures, base=None, bases=None, **kw):
    """n synthetic people from CWB-133 override dicts, each shifted 40 px apart.

    bases lets one image carry figures of DIFFERENT quality, which is the
    150-cleanup census case (3 figures, the top-scoring one a bad detection).
    """
    kp_dicts = []
    for i in range(n_figures):
        overrides = dict((bases[i] if bases else None) or base or UPRIGHT)
        shifted = {idx: (x + 40.0 * i, y, c) for idx, (x, y, c) in overrides.items()}
        kp_dicts.append(lap.kps133_to_anat(make_cwb(shifted)))
    return detector_from_kps(kp_dicts, **kw)


def missing_loader():
    raise lap.MetricsUnavailable("tools/lw_anat_metrics.py not importable: fake")


def only_figure(rep, image=0, fig=0):
    return rep["images"][image]["figures"][fig]


def report_for(base=None, n=1, min_conf=lap.DEFAULT_MIN_CONF, **kw):
    """A report over one synthetic image, measured by the REAL S3 module."""
    return lap.build_report(["x.png"], detector=fake_detector(n, base=base, **kw),
                            metrics_loader=lap.load_metrics, min_conf=min_conf)


# --- the index mapping ------------------------------------------------------
def test_anat_idx_reuses_the_existing_cwb_constant():
    assert lap.ANAT_IDX["nose"] == lle.CWB["nose"]
    assert lap.ANAT_IDX["left_shoulder"] == lle.CWB["Lshoulder"]
    assert lap.ANAT_IDX["right_shoulder"] == lle.CWB["Rshoulder"]


def test_anat_idx_covers_exactly_the_s3_contract_names():
    assert set(lap.ANAT_IDX) == set(lap.ANAT_KP_NAMES)
    assert len(lap.ANAT_KP_NAMES) == 9
    # Indices documented at lw_gen_localizer_eval.py:37-39 (COCO-17 body block).
    assert [lap.ANAT_IDX[n] for n in lap.ANAT_KP_NAMES] == [0, 1, 2, 3, 4, 5, 6, 11, 12]


def test_the_nine_names_are_exactly_what_s3_asks_for():
    """Drift here silently starves the metric, so pin it against the module."""
    assert set(lam.HEAD_POINT_NAMES) | set(lam.SPINE_POINT_NAMES) == set(lap.ANAT_KP_NAMES)
    assert set(lam.HEAD_POINT_NAMES) == set(lap.HEAD_JOINTS)
    assert set(lam.SPINE_POINT_NAMES) == set(lap.SPINE_JOINTS)


def test_mapping_keeps_pixel_coords_and_confidence():
    kp = lap.kps133_to_anat(make_cwb(UPRIGHT))
    assert set(kp) == set(lap.ANAT_KP_NAMES)
    assert kp["nose"] == (1280.0, 300.0, 0.91)
    assert kp["left_shoulder"] == (1180.0, 500.0, 0.93)
    assert kp["right_hip"] == (1360.0, 900.0, 0.81)
    # Not normalized: an anisotropic (x/w, y/h) map would put every value under 1.
    assert max(v[0] for v in kp.values()) > 1.0
    assert max(v[1] for v in kp.values()) > 1.0


def test_mapping_does_not_apply_a_confidence_floor():
    """S3 owns min_conf; the probe must hand over low-conf joints untouched."""
    kp = lap.kps133_to_anat(make_cwb({**UPRIGHT, 3: (1230.0, 295.0, 0.01)}))
    assert kp["left_ear"] == (1230.0, 295.0, 0.01)


def test_mapping_accepts_two_tuples_as_full_confidence():
    assert lap.kps133_to_anat([(1.0, 2.0)] * 133)["nose"] == (1.0, 2.0, 1.0)


def test_mapping_omits_joints_past_a_short_sequence():
    kp = lap.kps133_to_anat([(5.0, 6.0, 0.5)] * 7)
    assert "right_shoulder" in kp
    assert "left_hip" not in kp and "right_hip" not in kp


# --- geometry ---------------------------------------------------------------
def test_geometry_computes_raw_width_length_and_ratio():
    geo = lap.figure_geometry(lap.kps133_to_anat(make_cwb(UPRIGHT)))
    assert geo["shoulder_width_px"] == 200.0
    assert geo["spine_len_px"] == 400.0
    assert geo["shoulder_spine_ratio"] == 0.5
    assert geo["ratio_below_floor"] is False


def test_geometry_flags_a_collapsed_skeleton_on_the_ratio():
    geo = lap.figure_geometry(lap.kps133_to_anat(make_cwb(COLLAPSED)))
    assert geo["shoulder_width_px"] == 100.0
    assert geo["shoulder_spine_ratio"] == 0.25
    assert geo["ratio_below_floor"] is True


def test_geometry_mirrors_s3s_ratio_floor():
    """A drifted mirror would flag different figures than the module refuses."""
    assert lap.MIN_SHOULDER_SPINE_RATIO == lam.MIN_SHOULDER_SPINE_RATIO


def test_geometry_ignores_the_confidence_floor_by_design():
    """The 173 images S3 refuses are exactly the ones needing these numbers."""
    geo = lap.figure_geometry(lap.kps133_to_anat(make_cwb(LOW_CONF)))
    assert geo["shoulder_width_px"] == 200.0
    assert geo["spine_len_px"] == 400.0


def test_geometry_reports_none_rather_than_zero_for_missing_anchors():
    kp = lap.kps133_to_anat(make_cwb(UPRIGHT))
    del kp["left_hip"]
    geo = lap.figure_geometry(kp)
    assert geo["spine_len_px"] is None
    assert geo["shoulder_spine_ratio"] is None
    assert geo["ratio_below_floor"] is None
    assert geo["shoulder_width_px"] == 200.0


def test_low_confidence_joints_enumerates_every_offender():
    """S3 refuses on the first offender; triage needs all of them."""
    kp = lap.kps133_to_anat(make_cwb(LOW_CONF))
    assert lap.low_confidence_joints(kp, lap.SPINE_JOINTS, 0.3) == ["left_shoulder", "left_hip"]
    assert lap.low_confidence_joints(kp, lap.SPINE_JOINTS, 0.01) == []


# --- probe_image contract ---------------------------------------------------
def test_probe_image_returns_one_mapping_per_figure_without_reduction():
    out = lap.probe_image("x.png", detector=fake_detector(3))
    assert len(out) == 3
    assert all(set(m) == set(lap.ANAT_KP_NAMES) for m in out)
    xs = [m["nose"][0] for m in out]
    assert xs == sorted(xs) and len(set(xs)) == 3


def test_probe_image_zero_figures_is_an_empty_list():
    assert lap.probe_image("x.png", detector=fake_detector(0)) == []


# --- the measured outcome ---------------------------------------------------
def test_a_clean_figure_measures_and_carries_every_metric_field():
    fig = only_figure(report_for())
    assert fig["state"] == lap.STATE_MEASURED
    assert fig["state_group"] == lap.GROUP_MEASURED
    hs = fig["head_spine"]
    assert hs["measured"] is True
    # Head centroid sits exactly on the spine axis in this fixture.
    assert hs["offset_px"] == 0.0 and hs["offset_norm"] == 0.0
    assert hs["sign"] == 0
    assert hs["metrics_shoulder_width_px"] == 200.0
    assert hs["metrics_spine_len_px"] == 400.0
    assert hs["head_points_used"] == list(lam.HEAD_POINT_NAMES)
    assert hs["reason"] is None


def test_a_displaced_head_produces_a_signed_offset():
    hs = only_figure(report_for(base=head_shifted(100.0)))["head_spine"]
    assert hs["measured"] is True
    assert hs["offset_px"] == 100.0
    assert hs["offset_norm"] == 0.5
    assert hs["sign"] == 1
    hs_other = only_figure(report_for(base=head_shifted(-100.0)))["head_spine"]
    assert hs_other["offset_norm"] == -0.5
    assert hs_other["sign"] == -1


def test_triage_band_is_recorded_as_a_distribution_marker():
    """Ordering only. The census put the operator's one rejection at p43.5."""
    assert only_figure(report_for())["head_spine"]["triage_band"] == lam.BAND_TYPICAL
    assert only_figure(report_for(base=head_shifted(100.0)))["head_spine"]["triage_band"] \
        == lam.BAND_ABOVE_P90
    assert only_figure(report_for(base=head_shifted(130.0)))["head_spine"]["triage_band"] \
        == lam.BAND_ABOVE_P95


def test_min_conf_is_honoured_end_to_end():
    """At 0.7 the ears drop out of the centroid, so the offset itself moves."""
    fig = only_figure(report_for(min_conf=0.7))
    assert fig["state"] == lap.STATE_MEASURED
    assert fig["head_points_above_min_conf"] == ["nose", "left_eye", "right_eye"]
    assert fig["head_spine"]["head_points_used"] == ["nose", "left_eye", "right_eye"]


# --- every one of S3's six refusal reasons ---------------------------------
def test_refusal_spine_point_low_conf():
    fig = only_figure(report_for(base=LOW_CONF))
    assert fig["state"] == lam.REFUSE_SPINE_POINT_LOW_CONF
    assert fig["state_group"] == lap.GROUP_CONFIDENCE
    assert fig["head_spine"]["measured"] is False
    # reason and detail both verbatim from the module.
    assert fig["head_spine"]["reason"] == "spine_point_low_conf"
    assert fig["head_spine"]["detail"] == "left_shoulder"
    assert fig["low_confidence_spine_joints"] == ["left_shoulder", "left_hip"]


def test_refusal_spine_point_missing():
    kp = lap.kps133_to_anat(make_cwb(UPRIGHT))
    del kp["left_hip"]
    rep = lap.build_report(["x.png"], detector=detector_from_kps([kp]),
                           metrics_loader=lap.load_metrics)
    fig = only_figure(rep)
    assert fig["state"] == lam.REFUSE_SPINE_POINT_MISSING
    assert fig["state_group"] == lap.GROUP_CONFIDENCE
    assert fig["head_spine"]["detail"] == "left_hip"
    assert fig["confidences"]["left_hip"] is None


def test_refusal_no_head_points():
    fig = only_figure(report_for(base=NO_HEAD))
    assert fig["state"] == lam.REFUSE_NO_HEAD_POINTS
    assert fig["state_group"] == lap.GROUP_CONFIDENCE
    assert fig["head_points_above_min_conf"] == []
    # S3 had the spine established before it refused, and passes it through.
    assert fig["head_spine"]["metrics_shoulder_width_px"] == 200.0


def test_refusal_implausible_geometry_is_the_census_tail():
    fig = only_figure(report_for(base=COLLAPSED))
    assert fig["state"] == lam.REFUSE_IMPLAUSIBLE_GEOMETRY
    assert fig["state_group"] == lap.GROUP_GEOMETRY
    assert fig["head_spine"]["detail"] == "shoulder_spine_ratio=0.2500"
    # The raw numbers that exposed the tail ship even though nothing was measured.
    assert fig["geometry"]["shoulder_width_px"] == 100.0
    assert fig["geometry"]["spine_len_px"] == 400.0
    assert fig["head_spine"]["offset_norm"] is None


def test_refusal_degenerate_shoulders():
    fig = only_figure(report_for(base=DEGENERATE_SHOULDERS))
    assert fig["state"] == lam.REFUSE_DEGENERATE_SHOULDERS
    assert fig["state_group"] == lap.GROUP_GEOMETRY
    assert fig["geometry"]["shoulder_width_px"] == 0.0


def test_refusal_degenerate_spine():
    fig = only_figure(report_for(base=DEGENERATE_SPINE))
    assert fig["state"] == lam.REFUSE_DEGENERATE_SPINE
    assert fig["state_group"] == lap.GROUP_GEOMETRY
    assert fig["geometry"]["spine_len_px"] == 0.0


def test_every_refusal_reason_the_module_defines_is_groupable():
    """An ungrouped reason is a contract change, and must not slip in silently."""
    assert set(lam.REFUSAL_REASONS) == set(lap.REASON_GROUPS)
    for reason in lam.REFUSAL_REASONS:
        assert lap.REASON_GROUPS[reason] in (lap.GROUP_CONFIDENCE, lap.GROUP_GEOMETRY)


def test_an_unknown_future_reason_falls_to_a_visible_bucket():
    measure = {"measured": False, "reason": "some_new_reason_from_a_later_s3"}
    assert lap._figure_state(measure) == ("some_new_reason_from_a_later_s3", lap.GROUP_OTHER)


# --- the four outcome classes, never collapsed -----------------------------
def test_no_figure_detected_is_its_own_state():
    rep = lap.build_report(["a.png"], detector=fake_detector(0),
                           metrics_loader=lap.load_metrics)
    img = rep["images"][0]
    assert img["state"] == lap.STATE_NO_FIGURE
    assert img["figure_count"] == 0 and img["figures"] == []
    assert img["multi_figure"] is False
    assert rep["summary"]["state_groups"][lap.GROUP_NO_FIGURE] == 1


def test_the_four_outcomes_land_in_four_separate_buckets():
    rep = lap.build_report(
        ["a.png", "b.png", "c.png", "d.png"],
        detector=_mixed_detector(),
        metrics_loader=lap.load_metrics,
    )
    groups = rep["summary"]["state_groups"]
    assert groups[lap.GROUP_MEASURED] == 1
    assert groups[lap.GROUP_CONFIDENCE] == 1
    assert groups[lap.GROUP_GEOMETRY] == 1
    assert groups[lap.GROUP_NO_FIGURE] == 1
    # Fine-grained states keep S3's own vocabulary alongside the grouping.
    assert set(rep["summary"]["states"]) == {
        lap.STATE_MEASURED, lam.REFUSE_SPINE_POINT_LOW_CONF,
        lam.REFUSE_IMPLAUSIBLE_GEOMETRY, lap.STATE_NO_FIGURE,
    }


def _mixed_detector():
    """One detector answering differently per call: measured, low-conf, bad, none."""
    answers = [UPRIGHT, LOW_CONF, COLLAPSED, None]
    calls = {"n": 0}

    def _detect(image_path):
        base = answers[calls["n"]]
        calls["n"] += 1
        kps = [] if base is None else [lap.kps133_to_anat(make_cwb(base))]
        return lap.Detection(image_wh=IMG_WH, figures=[
            lap.DetectedFigure(keypoints=kp, mean_score=0.5) for kp in kps
        ], meta={"n_boxes": len(kps)})

    return _detect


# --- report assembly -------------------------------------------------------
def test_report_never_frames_output_as_a_gate_verdict():
    rep = report_for(n=2)
    blob = json.dumps(rep["images"]).lower()
    assert "verdict" not in json.dumps(rep).lower()
    assert "pass" not in blob and "fail" not in blob
    assert "not a gate" in rep["purpose"]


def test_report_records_confidences_for_every_joint_the_metric_depends_on():
    fig = only_figure(report_for())
    assert set(fig["confidences"]) == set(lap.ANAT_KP_NAMES)
    assert fig["confidences"]["left_shoulder"] == 0.93
    assert fig["confidences"]["right_hip"] == 0.81
    for name in lam.SPINE_POINT_NAMES:
        assert fig["confidences"][name] is not None


def test_report_records_geometry_on_measured_and_refused_alike():
    measured = only_figure(report_for())["geometry"]
    refused = only_figure(report_for(base=LOW_CONF))["geometry"]
    for geo in (measured, refused):
        assert geo["shoulder_width_px"] == 200.0
        assert geo["spine_len_px"] == 400.0


def test_report_single_and_multi_figure_are_distinguishable():
    rep1 = report_for(n=1)
    rep2 = report_for(n=2)
    assert rep1["images"][0]["multi_figure"] is False
    assert rep1["images"][0]["figure_count"] == 1
    assert rep2["images"][0]["multi_figure"] is True
    assert rep2["images"][0]["figure_count"] == 2
    assert [f["index"] for f in rep2["images"][0]["figures"]] == [0, 1]
    assert rep2["summary"]["multi_figure_images"] == 1
    assert rep2["summary"]["figures"] == 2


def test_a_multi_figure_image_keeps_a_bad_figure_visible_next_to_a_good_one():
    """150-cleanup: 3 figures, and the top-scoring one was a bad detection."""
    rep = lap.build_report(
        ["m.png"],
        detector=fake_detector(2, bases=[COLLAPSED, UPRIGHT], mean_scores=[0.86, 0.40]),
        metrics_loader=lap.load_metrics,
    )
    figs = rep["images"][0]["figures"]
    assert [f["mean_score"] for f in figs] == [0.86, 0.40]
    assert [f["state"] for f in figs] == [lam.REFUSE_IMPLAUSIBLE_GEOMETRY, lap.STATE_MEASURED]
    assert [f["index"] for f in figs] == [0, 1]


def test_report_flags_a_whole_frame_fallback_roi():
    rep = lap.build_report(["f.png"],
                           detector=fake_detector(1, roi_source=lap.SRC_FALLBACK),
                           metrics_loader=lap.load_metrics)
    assert only_figure(rep)["roi_source"] == lap.SRC_FALLBACK
    assert rep["summary"]["whole_frame_fallback_images"] == 1


def test_report_records_the_index_map_and_contract_alignment():
    rep = report_for()
    assert rep["kp_indices"]["left_hip"] == 11
    assert rep["contract"]["source"] == "lw_anat_metrics"
    assert rep["contract"]["matches_module"] is True
    assert rep["contract"]["ratio_floor"] == lam.MIN_SHOULDER_SPINE_RATIO
    assert rep["contract"]["unrecognized_refusal_reasons"] == []


def test_report_is_json_round_trippable():
    again = json.loads(json.dumps(report_for()))
    assert again["images"][0]["image_wh"] == [2560, 1440]
    assert again["images"][0]["figures"][0]["keypoints"]["nose"] == [1280.0, 300.0, 0.91]
    assert again["kp_names"] == list(lap.ANAT_KP_NAMES)


# --- the missing / broken metrics module -----------------------------------
def test_the_real_module_satisfies_load_metrics():
    """Guards the rework: requiring a DELETED symbol would reject the module."""
    assert lap.load_metrics() is lam
    assert not hasattr(lam, "classify_head_spine")


def test_missing_metrics_module_is_an_explicit_state_not_a_silent_fallback():
    rep = lap.build_report(["e.png"], detector=fake_detector(1),
                           metrics_loader=missing_loader)
    assert rep["metrics_module"]["available"] is False
    assert "not importable" in rep["metrics_module"]["error"]
    fig = only_figure(rep)
    assert fig["state"] == lap.STATE_NO_METRICS
    assert fig["state_group"] == lap.GROUP_NO_METRICS
    assert fig["head_spine"] is None
    assert "not importable" in fig["metrics_error"]
    assert lap.STATE_MEASURED not in rep["summary"]["states"]
    # Keypoints and geometry still ship - extraction is independent of S3.
    assert fig["keypoints"]["nose"] == [1280.0, 300.0, 0.91]
    assert fig["geometry"]["shoulder_width_px"] == 200.0
    assert rep["contract"]["source"] == "local_mirrors"


def test_load_metrics_rejects_an_incomplete_module(monkeypatch):
    class _Half:
        head_spine_offset = staticmethod(lambda kp, min_conf=0.3: None)
        HeadSpineResult = object

    monkeypatch.setattr(tools, "lw_anat_metrics", _Half(), raising=False)
    monkeypatch.setitem(sys.modules, "tools.lw_anat_metrics", _Half())
    with pytest.raises(lap.MetricsUnavailable) as exc:
        lap.load_metrics()
    assert "triage_band" in str(exc.value)
    assert "HeadSpineRefusal" in str(exc.value)


# --- atomic write ----------------------------------------------------------
def test_write_report_is_atomic_and_leaves_no_tmp(tmp_path):
    target = tmp_path / "nested" / "report.json"
    out = lap.write_report(report_for(), target)
    assert out == target and target.is_file()
    assert not (target.parent / (target.name + ".tmp")).exists()
    assert json.loads(target.read_text(encoding="ascii"))["tool"] == "lw_anat_probe"


def test_write_report_replaces_an_existing_report(tmp_path):
    target = tmp_path / "r.json"
    target.write_text("stale", encoding="ascii")
    lap.write_report(report_for(n=2), target)
    assert json.loads(target.read_text(encoding="ascii"))["summary"]["figures"] == 2


def test_report_is_pure_ascii(tmp_path):
    lap.write_report(report_for(), tmp_path / "r.json")
    (tmp_path / "r.json").read_bytes().decode("ascii")


# --- approved-image selection ---------------------------------------------
def test_approved_images_selects_only_done_milestones(tmp_path):
    slug = tmp_path / "fiora1"
    slug.mkdir()
    for name in ("fiora1_firstdone.png", "fiora1_firstinitial.png",
                 "fiora1_firstworking_01.png", "fiora1_firstneedauth.png",
                 "manifest.json", "notes.txt"):
        (slug / name).write_text("x", encoding="ascii")
    other = tmp_path / "ahri2"
    other.mkdir()
    (other / "ahri2_lastdone.jpg").write_text("x", encoding="ascii")
    (other / "ahri2_lastdone.psd").write_text("x", encoding="ascii")

    names = [p.name for p in lap.approved_images(tmp_path)]
    assert sorted(names) == ["ahri2_lastdone.jpg", "fiora1_firstdone.png"]


def test_approved_images_rejects_a_non_directory(tmp_path):
    f = tmp_path / "f.png"
    f.write_text("x", encoding="ascii")
    with pytest.raises(NotADirectoryError):
        lap.approved_images(f)


# --- CLI -------------------------------------------------------------------
def test_cli_single_image_writes_a_report(tmp_path, monkeypatch):
    monkeypatch.setattr(lap, "dwpose_detect_all", fake_detector(2))
    out = tmp_path / "cli.json"
    assert lap._main(["--image", "any.png", "--out", str(out)]) == 0
    rep = json.loads(out.read_text(encoding="ascii"))
    assert rep["summary"]["figures"] == 2 and rep["images"][0]["multi_figure"] is True
    assert rep["summary"]["state_groups"][lap.GROUP_MEASURED] == 2


def test_cli_returns_3_when_the_metrics_module_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(lap, "dwpose_detect_all", fake_detector(1))
    monkeypatch.setattr(lap, "load_metrics", missing_loader)
    out = tmp_path / "cli.json"
    assert lap._main(["--image", "any.png", "--out", str(out)]) == 3
    rep = json.loads(out.read_text(encoding="ascii"))
    assert rep["metrics_module"]["available"] is False
    assert rep["images"][0]["figures"][0]["state"] == lap.STATE_NO_METRICS


def test_cli_stage_dir_probes_every_approved_image(tmp_path, monkeypatch):
    for slug in ("a1", "b2"):
        d = tmp_path / slug
        d.mkdir()
        (d / f"{slug}_firstdone.png").write_text("x", encoding="ascii")
        (d / f"{slug}_firstinitial.png").write_text("x", encoding="ascii")
    monkeypatch.setattr(lap, "dwpose_detect_all", fake_detector(1))
    out = tmp_path / "stage.json"
    assert lap._main(["--stage-dir", str(tmp_path), "--out", str(out)]) == 0
    rep = json.loads(out.read_text(encoding="ascii"))
    assert rep["summary"]["images"] == 2
    assert all("done" in i["path"] for i in rep["images"])


def test_cli_min_conf_reaches_the_report(tmp_path, monkeypatch):
    monkeypatch.setattr(lap, "dwpose_detect_all", fake_detector(1))
    out = tmp_path / "c.json"
    lap._main(["--image", "a.png", "--out", str(out), "--min-conf", "0.7"])
    assert json.loads(out.read_text(encoding="ascii"))["min_conf"] == 0.7


def test_cli_returns_2_on_an_empty_stage_dir(tmp_path):
    (tmp_path / "empty").mkdir()
    assert lap._main(["--stage-dir", str(tmp_path), "--out", str(tmp_path / "x.json")]) == 2


# --- the one capability-gated test ----------------------------------------
def _dwpose_capability():
    """True only when onnxruntime + cv2 import AND both DWPose .onnx files exist."""
    try:
        import cv2  # noqa: F401
        import onnxruntime  # noqa: F401
    except ImportError:
        return False
    models = lap.ROOT / "tools/models/dwpose"
    return (models / "yolox_l.onnx").is_file() and (models / "dw-ll_ucoco_384.onnx").is_file()


REAL_IMAGE = lap.ROOT / "images/2.First Pass Done/fiora1/fiora1_firstdone.png"


@pytest.mark.skipif(not _dwpose_capability() or not REAL_IMAGE.is_file(),
                    reason="needs onnxruntime + the gitignored DWPose weights + a corpus image")
def test_real_dwpose_detection_reproduces_the_fiora1_reference():
    det = lap.dwpose_detect_all(str(REAL_IMAGE))
    assert det.image_wh == (2560, 1440)
    assert det.figures, "a fullview wallpaper must yield at least one figure"
    kp = det.figures[0].keypoints
    assert set(kp) == set(lap.ANAT_KP_NAMES)
    # Operator's independent reference measurement of this image.
    geo = lap.figure_geometry(kp)
    assert geo["shoulder_width_px"] == pytest.approx(357.4, abs=0.1)
    assert geo["spine_len_px"] == pytest.approx(610.2, abs=0.1)
    assert det.figures[0].mean_score == pytest.approx(0.3594, abs=0.001)
    res = lam.head_spine_offset(kp)
    assert res.ok
    assert abs(res.offset_px) == pytest.approx(51.69, abs=0.05)
    assert abs(res.offset_norm) == pytest.approx(0.1446, abs=0.0005)
    assert list(res.head_points_used) == list(lam.HEAD_POINT_NAMES)
