"""Anatomical-plausibility DIAGNOSTIC probe (S4): image -> per-figure keypoints.

WHY this exists: every G1 metric compares an output to its OWN source, so a
defect inherent to the source art - an approved image whose head does not sit on
the figure's spine, passed at ms_ssim 0.997113 - clears every rung of the gate
ladder. The ladder is structurally blind to figure implausibility. This module is
the extraction half of the missing measurement: it turns a real image into the
pixel keypoint triples that tools/lw_anat_metrics.py (S3) consumes, and reports
them with the raw geometry needed to triage what comes back.

THIS IS A DIAGNOSTIC, NOT A GATE. A census over all 288 approved firstdones
proved the metric cannot become pass/fail: only 115 of 288 (39.9 percent) are
measurable at min_conf 0.3, and the extreme tail is localizer failure rather than
anatomy - the two worst images had detected shoulder widths of 120.1 px and
59.2 px where a correct detection (fiora1) measures 357.4 px against a 610.2 px
spine. Nothing here emits a pass, a fail, or a verdict. S3 deleted its own
classifier over exactly this, so this report states an OUTCOME, the raw numbers,
and at most a distribution BAND for ordering a human review queue.

Localizer = DWPose onnx-CPU, ADR-settled for LW (CLAUDE.md Settled, LEDGER 19).
The cached onnxruntime sessions and the detect/pose call sequence are REUSED from
tools/lw_gen_localizer_eval.py (_dwpose_sessions :149, dwpose_backend :164-200),
not rebuilt.

What is deliberately NOT reused: cocowb_to_kp_map (lw_gen_localizer_eval.py:98).
Its norm() (:109-113) returns (x / w, y / h), which scales x and y by different
factors on a 2560x1440 frame - that shear would corrupt any perpendicular-offset
measurement; it also drops confidence to a 2-tuple, and its CWB key set (:40-48)
has no eyes, ears or hips. This module maps the raw 133-keypoint PIXEL array.

Also NOT inherited: dwpose_backend's single-person reduction (:186-187, argmax of
the mean score). One census image (150-cleanup) has 3 figures where the
HIGHEST-scoring one was still a bad detection, so figure selection must stay
auditable - every detected figure is reported with its own index and score.

No subprocess is spawned anywhere here (in-process onnxruntime), so the standing
no-console-flash rule has nothing to guard.

Exit codes (CLI): 0 report written; 2 usage / no input; 3 report written but the
S3 metrics module was unavailable, so the report carries keypoints and raw
geometry only and no head/spine measurement was attempted.
"""
from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
# Script mode puts tools/ on sys.path, not the repo root; the `tools` package
# imports below need the root.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import lw_gen_localizer_eval as lle  # noqa: E402
from tools.lw_pipeline import IMAGE_EXTS, MILESTONE_RE  # noqa: E402

REPORT_VERSION = 1
DETECTOR_NAME = "dwpose_onnx_cpu"
DEFAULT_MIN_CONF = 0.3

# S3's keypoint-name contract: exactly these nine joints.
ANAT_KP_NAMES: Tuple[str, ...] = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_hip",
    "right_hip",
)

# COCO-WholeBody-133 body block. nose/shoulders come from the existing CWB
# constant; the rest are the indices documented in the same file's index map
# (lw_gen_localizer_eval.py:37-39: "1-4 eyes/ears ... 11-16 hips/knees/ankles").
# tools/dwpose_onnx/onnxpose.py carries no skeleton spec, so that comment is the
# only in-repo source and it gives the RANGES, not the left/right order inside
# them. The odd-left / even-right assignment below matches CWB's own
# 5=Lshoulder / 6=Rshoulder pairing.
# WHY the residual ambiguity is safe rather than overlooked: S3's head anchor is
# the head-keypoint centroid (lw_anat_metrics.py:258-271), symmetric under an
# eye/eye or ear/ear swap, and its spine anchors are the shoulder and hip
# MIDPOINTS (:235-236), symmetric under a hip swap. A left/right mislabel
# therefore cannot move any number this probe feeds or computes - only the
# per-joint confidence LABELS would read mirrored, which is a naming cosmetic.
_CWB_EXTRA_IDX = {
    "left_eye": 1,
    "right_eye": 2,
    "left_ear": 3,
    "right_ear": 4,
    "left_hip": 11,
    "right_hip": 12,
}
ANAT_IDX: Dict[str, int] = {
    "nose": lle.CWB["nose"],
    "left_shoulder": lle.CWB["Lshoulder"],
    "right_shoulder": lle.CWB["Rshoulder"],
    **_CWB_EXTRA_IDX,
}

CWB_N_KEYPOINTS = 133

# Local mirrors of S3's name constants, used ONLY when the metrics module is
# absent. When it loads, its own HEAD_POINT_NAMES / SPINE_POINT_NAMES win and any
# divergence is recorded in the report's contract block rather than reconciled
# silently.
HEAD_JOINTS: Tuple[str, ...] = ("nose", "left_eye", "right_eye", "left_ear", "right_ear")
SPINE_JOINTS: Tuple[str, ...] = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")

# Mirror of lw_anat_metrics.MIN_SHOULDER_SPINE_RATIO (:124), used ONLY to flag
# geometry when that module is unavailable - S3 owns the judgement whenever it
# loads. WHY the ratio and not a fraction of frame width: it is scale-invariant,
# and it is the dimension the census actually separates on. The two confirmed bad
# detections measure 0.215 and 0.251, fiora1 measures 0.586.
MIN_SHOULDER_SPINE_RATIO = 0.35

# Outcome vocabulary. Refusal states are S3's OWN reason strings, verbatim, so
# there is no parallel naming to reconcile at merge; only the states S3 cannot
# produce are defined here (it is never called without a figure, and it cannot
# report its own absence).
STATE_MEASURED = "measured"
STATE_NO_FIGURE = "no_figure_detected"
STATE_NO_METRICS = "metrics_unavailable"

# Coarse grouping over those states. The census showed a confidence refusal and a
# collapsed-skeleton refusal are different findings with different remedies, and
# collapsing them is what kept the localizer-failure tail invisible - so these
# four stay distinct and are counted separately in every report.
GROUP_MEASURED = "measured"
GROUP_CONFIDENCE = "refused_confidence_or_availability"
GROUP_GEOMETRY = "refused_implausible_geometry"
GROUP_NO_FIGURE = "no_figure_detected"
GROUP_NO_METRICS = "metrics_unavailable"
GROUP_OTHER = "refused_unrecognized_reason"
STATE_GROUPS: Tuple[str, ...] = (
    GROUP_MEASURED,
    GROUP_CONFIDENCE,
    GROUP_GEOMETRY,
    GROUP_NO_FIGURE,
    GROUP_NO_METRICS,
    GROUP_OTHER,
)

# S3's six refusal reasons, split by what a human would do about each: the first
# three mean the keypoints were not there to measure with, the last three mean the
# detected skeleton is not a credible body. An unrecognized reason falls to
# GROUP_OTHER rather than being forced into either, so a future S3 reason shows up
# as unclassified instead of silently mislabelled.
REASON_GROUPS: Dict[str, str] = {
    "spine_point_missing": GROUP_CONFIDENCE,
    "spine_point_low_conf": GROUP_CONFIDENCE,
    "no_head_points": GROUP_CONFIDENCE,
    "degenerate_shoulders": GROUP_GEOMETRY,
    "degenerate_spine": GROUP_GEOMETRY,
    "implausible_geometry": GROUP_GEOMETRY,
}

# Where the pose ROI came from. onnxpose.preprocess substitutes the whole image
# as the box when the person detector returns none (tools/dwpose_onnx/
# onnxpose.py:26), so a pose comes back even when nothing was detected - yolox_l
# is photographic-trained and misses stylized figures (measured on
# fiora1_firstdone: n_boxes 0). Such a figure is KEPT, because on a
# single-subject 16:9 wallpaper the whole frame is a defensible ROI, but it is
# labelled so nothing downstream reads it as a real person detection.
SRC_BOX = "detector_box"
SRC_FALLBACK = "whole_frame_fallback"


class MetricsUnavailable(RuntimeError):
    """tools/lw_anat_metrics.py (S3) is absent or does not match its contract."""


@dataclass
class DetectedFigure:
    """One detected person: pixel (x, y, conf) triples + the detector's score."""

    keypoints: Dict[str, Tuple[float, float, float]]
    mean_score: Optional[float] = None
    roi_source: str = SRC_BOX


@dataclass
class Detection:
    """A detector's whole answer for one image (zero figures is a valid answer)."""

    image_wh: Tuple[int, int]
    figures: List[DetectedFigure] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def kps133_to_anat(kps: Sequence) -> Dict[str, Tuple[float, float, float]]:
    """COCO-WholeBody-133 PIXEL keypoints -> the nine-joint S3 mapping.

    kps is a 133-length sequence of (x, y) or (x, y, conf) in image pixels.
    Coordinates stay in PIXELS and confidence is preserved: S3 owns the min_conf
    decision, so nothing is filtered or dropped here. A joint whose index is past
    the end of a short sequence is omitted entirely, which S3 reads as
    spine_point_missing rather than as a zero-confidence point at the origin.
    """
    out: Dict[str, Tuple[float, float, float]] = {}
    for name in ANAT_KP_NAMES:
        idx = ANAT_IDX[name]
        if idx >= len(kps):
            continue
        x, y, conf = lle._triple(kps[idx])
        out[name] = (x, y, conf)
    return out


def dwpose_detect_all(image_path: str) -> Detection:
    """Detect EVERY figure with DWPose onnx-CPU (yolox_l box -> dw-ll wholebody).

    Mirrors the ADR-settled sequence in lw_gen_localizer_eval.dwpose_backend
    (:164-200) - cv2.imread BGR, onnxdet.inference_detector, onnxpose
    .inference_pose - but keeps every person instead of the single argmax one.
    Heavy imports stay lazy so this module is importable without onnxruntime.
    """
    import cv2
    import numpy as np

    from tools.dwpose_onnx import onnxdet, onnxpose

    det_sess, pose_sess = lle._dwpose_sessions()
    ori = cv2.imread(image_path)
    if ori is None:
        raise OSError(f"cv2 could not read image: {image_path}")
    height, width = ori.shape[:2]
    boxes = onnxdet.inference_detector(det_sess, ori)
    n_boxes = int(len(boxes)) if hasattr(boxes, "__len__") else 0
    kpts, scores = onnxpose.inference_pose(pose_sess, boxes, ori)
    meta = {"n_boxes": n_boxes}
    if kpts is None or len(kpts) == 0:
        return Detection(image_wh=(width, height), figures=[], meta=meta)
    figures = []
    for i in range(len(kpts)):
        person, sc = kpts[i], scores[i]
        triples = [
            (float(person[j, 0]), float(person[j, 1]), float(sc[j]))
            for j in range(min(CWB_N_KEYPOINTS, len(sc)))
        ]
        figures.append(
            DetectedFigure(
                keypoints=kps133_to_anat(triples),
                mean_score=round(float(np.mean(sc)), 4),
                roi_source=SRC_BOX if n_boxes else SRC_FALLBACK,
            )
        )
    return Detection(image_wh=(width, height), figures=figures, meta=meta)


def probe_figures(image_path, detector: Optional[Callable] = None) -> Detection:
    """Full detector answer for one image, including the zero-figure case."""
    det = detector or dwpose_detect_all
    return det(str(image_path))


def probe_image(image_path, detector: Optional[Callable] = None) -> List[Dict[str, Tuple[float, float, float]]]:
    """One keypoint mapping per detected figure, in S3's contract shape.

    Returns [] when no figure is detected, which the caller must treat as
    UNMEASURABLE. No reduction to a single figure - use probe_figures for the
    per-figure mean scores.
    """
    return [fig.keypoints for fig in probe_figures(image_path, detector).figures]


# ------------------------------------------------------------------ geometry
def _midpoint(kp, a, b):
    if a not in kp or b not in kp:
        return None
    return ((kp[a][0] + kp[b][0]) / 2.0, (kp[a][1] + kp[b][1]) / 2.0)


def figure_geometry(kp, ratio_floor: float = MIN_SHOULDER_SPINE_RATIO) -> dict:
    """Raw shoulder width, spine length and their ratio, in PIXELS.

    WHY this is computed here and unconditionally, when S3's refusal object also
    carries two of these: it IGNORES the confidence floor, so the numbers exist
    for the 173 census images S3 refuses outright and for every figure when S3 is
    absent entirely. A refusal that carried no geometry could not distinguish a
    genuinely tilted head from a figure the detector collapsed to a 59 px
    shoulder span - which is exactly how the tail stayed hidden.

    ratio_below_floor is a cross-check flag only. S3 owns the implausibility
    JUDGEMENT whenever it loads; this records whether the raw, conf-blind
    geometry agrees.
    """
    shoulder_width = spine_len = ratio = None
    if "left_shoulder" in kp and "right_shoulder" in kp:
        shoulder_width = math.dist(kp["left_shoulder"][:2], kp["right_shoulder"][:2])
    sh_mid = _midpoint(kp, "left_shoulder", "right_shoulder")
    hip_mid = _midpoint(kp, "left_hip", "right_hip")
    if sh_mid and hip_mid:
        spine_len = math.dist(sh_mid, hip_mid)
    if shoulder_width is not None and spine_len:
        ratio = shoulder_width / spine_len
    return {
        "shoulder_width_px": None if shoulder_width is None else round(shoulder_width, 2),
        "spine_len_px": None if spine_len is None else round(spine_len, 2),
        "shoulder_spine_ratio": None if ratio is None else round(ratio, 4),
        "ratio_floor": ratio_floor,
        "ratio_below_floor": None if ratio is None else ratio < ratio_floor,
    }


def low_confidence_joints(kp, names, min_conf) -> List[str]:
    """Names in `names` that are missing or under the confidence floor.

    The census made confidence the BINDING constraint: 173 of 288 approved images
    fail the shoulder/hip floor at min_conf 0.3, roughly 91 percent of them on the
    hips. S3 refuses on the FIRST offender it meets, so enumerating all of them
    here is what makes such a refusal triageable instead of one-joint-deep.
    """
    out = []
    for name in names:
        triple = kp.get(name)
        if triple is None or triple[2] < min_conf:
            out.append(name)
    return out


# ------------------------------------------------------------------ S3 bridge
def load_metrics():
    """Import the S3 metric module, or raise MetricsUnavailable.

    Explicit and loud by design: a missing or half-written lw_anat_metrics must
    never degrade into a fabricated measurement. The required-name list is the
    POST-rework contract (commit 49ec184) - `classify_head_spine`,
    HEAD_SPINE_FLAG_NORM and HEAD_SPINE_FAIL_NORM were DELETED there on the
    argument that a returned PASS/FLAG/FAIL string becomes a gate verdict at the
    call site no matter what the docstring says, so requiring any of them would
    reject the correct module.
    """
    required = (
        "head_spine_offset",
        "HeadSpineResult",
        "HeadSpineRefusal",
        "REFUSAL_REASONS",
        "triage_band",
        "HEAD_POINT_NAMES",
        "SPINE_POINT_NAMES",
    )
    try:
        from tools import lw_anat_metrics as mod
    except ImportError as exc:
        raise MetricsUnavailable(f"tools/lw_anat_metrics.py not importable: {exc}")
    missing = [name for name in required if not hasattr(mod, name)]
    if missing:
        raise MetricsUnavailable(
            "tools/lw_anat_metrics.py is missing required names: " + ", ".join(missing)
        )
    return mod


def _measure(metrics, kp, min_conf) -> dict:
    """Run S3's head/spine measure over one figure and flatten it for the report.

    ADAPTATION POINT for S3's contract (tools/lw_anat_metrics.py:206-297).
    head_spine_offset NEVER returns None - it returns HeadSpineResult(ok=True) or
    HeadSpineRefusal(ok=False, reason, detail). The branch is on `.ok`
    EXPLICITLY: an `is None` test would fall through a refusal and blow up on
    .offset_norm, and HeadSpineRefusal.__bool__ is False on purpose but reads as
    an accident at a call site. Both `reason` and `detail` are surfaced verbatim -
    S3 owns that wording, not this module.
    """
    outcome = metrics.head_spine_offset(kp, min_conf=min_conf)
    if not outcome.ok:
        return {
            "measured": False,
            "reason": outcome.reason,
            "detail": outcome.detail,
            "offset_px": None,
            "offset_norm": None,
            # Whatever geometry S3 had established before it refused. Its
            # unset default is 0.0, so this is NOT a measurement - the report's
            # own geometry block is the conf-blind ground truth.
            "metrics_shoulder_width_px": outcome.shoulder_width_px,
            "metrics_spine_len_px": outcome.spine_len_px,
            "head_points_used": [],
            "triage_band": None,
        }
    return {
        "measured": True,
        "reason": None,
        "detail": "",
        "offset_px": round(outcome.offset_px, 4),
        "offset_norm": round(outcome.offset_norm, 6),
        "sign": outcome.sign,
        "metrics_shoulder_width_px": round(outcome.shoulder_width_px, 2),
        "metrics_spine_len_px": round(outcome.spine_len_px, 2),
        "head_points_used": list(outcome.head_points_used),
        # A DISTRIBUTION MARKER for ordering a review queue, never a verdict:
        # the one image the operator actually rejected sits at the 43.5th
        # percentile, so TYPICAL is not evidence of quality and ABOVE_P95 is
        # more often a collapsed skeleton than bad art (lw_anat_metrics.py:300-330).
        "triage_band": metrics.triage_band(outcome.offset_norm),
    }


def _figure_state(measure: Optional[dict]) -> Tuple[str, str]:
    """(state, state_group) for one figure - S3's vocabulary, not a parallel one.

    A measured figure is no longer overridden on geometry grounds: S3's
    MIN_SHOULDER_SPINE_RATIO floor (:124) now refuses the collapsed skeletons
    that the census caught measuring, so a second opinion here would only
    disagree with the module that owns the judgement. The raw ratio still ships
    in every figure's geometry block, so a disagreement stays visible as data.
    """
    if measure is None:
        return STATE_NO_METRICS, GROUP_NO_METRICS
    if measure["measured"]:
        return STATE_MEASURED, GROUP_MEASURED
    reason = measure["reason"]
    return reason, REASON_GROUPS.get(reason, GROUP_OTHER)


def _contract_block(metrics) -> dict:
    """Record how S3's advertised constants line up with this probe's mirrors.

    Drift shows up as data in the report instead of being reconciled silently,
    which is what keeps the two slices reconcilable.
    """
    if metrics is None:
        return {
            "source": "local_mirrors",
            "head_points": list(HEAD_JOINTS),
            "spine_points": list(SPINE_JOINTS),
            "ratio_floor": MIN_SHOULDER_SPINE_RATIO,
            "matches_module": None,
            "unrecognized_refusal_reasons": [],
        }
    head = tuple(metrics.HEAD_POINT_NAMES)
    spine = tuple(metrics.SPINE_POINT_NAMES)
    return {
        "source": "lw_anat_metrics",
        "head_points": list(head),
        "spine_points": list(spine),
        "ratio_floor": getattr(metrics, "MIN_SHOULDER_SPINE_RATIO", MIN_SHOULDER_SPINE_RATIO),
        "matches_module": set(head) == set(HEAD_JOINTS) and set(spine) == set(SPINE_JOINTS),
        # A reason this probe cannot group is a contract change, not a data point.
        "unrecognized_refusal_reasons": [r for r in metrics.REFUSAL_REASONS
                                         if r not in REASON_GROUPS],
    }


def approved_images(stage_dir) -> List[Path]:
    """Every APPROVED milestone image under a stage dir, recursively.

    Approved == the `done` phase of the milestone grammar; the selection reuses
    lw_pipeline.MILESTONE_RE (lw_pipeline.py:78-83) and IMAGE_EXTS (:62) rather
    than a hand-rolled glob, so `_working_NN`, `_initial` and `_needauth` files
    and every sidecar are excluded by construction.
    """
    root = Path(stage_dir)
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")
    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        match = MILESTONE_RE.match(path.name)
        if not match or match.group("phase") != "done":
            continue
        if ("." + match.group("ext").lower()) not in IMAGE_EXTS:
            continue
        found.append(path)
    return found


def build_report(
    paths: Sequence,
    detector: Optional[Callable] = None,
    metrics_loader: Optional[Callable] = None,
    min_conf: float = DEFAULT_MIN_CONF,
) -> dict:
    """Probe every path and assemble the diagnostic JSON report.

    metrics_loader is injectable so the missing-module path is exercisable
    independently of whether S3's file happens to be on disk. It is resolved at
    call time rather than bound as a default so the CLI path stays injectable.
    """
    metrics = None
    metrics_error = None
    try:
        metrics = (metrics_loader or load_metrics)()
    except MetricsUnavailable as exc:
        metrics_error = str(exc)

    contract = _contract_block(metrics)
    head_names = tuple(contract["head_points"])
    spine_names = tuple(contract["spine_points"])
    ratio_floor = contract["ratio_floor"]

    images = []
    states: Dict[str, int] = {}
    groups: Dict[str, int] = {name: 0 for name in STATE_GROUPS}
    n_figures = 0
    n_multi = 0
    n_fallback_images = 0

    for path in paths:
        det = probe_figures(path, detector)
        entry = {
            "path": str(path),
            "image_wh": [int(det.image_wh[0]), int(det.image_wh[1])],
            "figure_count": len(det.figures),
            "multi_figure": len(det.figures) > 1,
            "detector_meta": det.meta,
            "figures": [],
        }
        if not det.figures:
            # An image with no figure is UNMEASURABLE. It is not a clean result,
            # and S3 is never even called - this state is this probe's alone.
            entry["state"] = STATE_NO_FIGURE
            entry["state_group"] = GROUP_NO_FIGURE
            states[STATE_NO_FIGURE] = states.get(STATE_NO_FIGURE, 0) + 1
            groups[GROUP_NO_FIGURE] += 1
        else:
            entry["state"] = "figures_present"
            entry["state_group"] = "figures_present"
        if len(det.figures) > 1:
            n_multi += 1
        if det.figures and all(f.roi_source == SRC_FALLBACK for f in det.figures):
            n_fallback_images += 1

        for i, fig in enumerate(det.figures):
            n_figures += 1
            kp = fig.keypoints
            measure = None if metrics is None else _measure(metrics, kp, min_conf)
            state, group = _figure_state(measure)
            states[state] = states.get(state, 0) + 1
            groups[group] = groups.get(group, 0) + 1
            entry["figures"].append({
                "index": i,
                "roi_source": fig.roi_source,
                "mean_score": fig.mean_score,
                "state": state,
                "state_group": group,
                "geometry": figure_geometry(kp, ratio_floor),
                # Every joint the measure depends on, so a refusal is triageable.
                "confidences": {n: (None if n not in kp else round(kp[n][2], 4))
                                for n in ANAT_KP_NAMES},
                "low_confidence_spine_joints": low_confidence_joints(kp, spine_names, min_conf),
                "head_points_above_min_conf": [n for n in head_names
                                               if n in kp and kp[n][2] >= min_conf],
                "head_spine": measure,
                "metrics_error": metrics_error,
                "keypoints": {k: list(v) for k, v in kp.items()},
            })
        images.append(entry)

    return {
        "tool": "lw_anat_probe",
        "report_version": REPORT_VERSION,
        # Stated in the artifact itself so no consumer can read it as a gate.
        "purpose": "diagnostic only - not a gate, no quality thresholds, no pass/fail",
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "detector": DETECTOR_NAME if detector is None else getattr(detector, "__name__", "injected"),
        "min_conf": min_conf,
        "kp_names": list(ANAT_KP_NAMES),
        "kp_indices": {n: ANAT_IDX[n] for n in ANAT_KP_NAMES},
        "contract": contract,
        "metrics_module": {"available": metrics is not None, "error": metrics_error},
        "summary": {
            "images": len(images),
            "figures": n_figures,
            "multi_figure_images": n_multi,
            "whole_frame_fallback_images": n_fallback_images,
            "states": states,
            "state_groups": groups,
        },
        "images": images,
    }


def write_report(report: dict, target) -> Path:
    """Atomic JSON write (CLAUDE.md hard rule): write .tmp, then replace."""
    out = Path(target)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=False), encoding="ascii")
    tmp.replace(out)
    return out


def _main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(
        description="Diagnostic anatomical probe: per-figure keypoints + head/spine geometry."
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", help="probe a single image")
    src.add_argument("--stage-dir", help="probe every approved (_*done) image under this dir")
    ap.add_argument("--out", required=True, help="JSON report path (written atomically)")
    ap.add_argument("--min-conf", type=float, default=DEFAULT_MIN_CONF)
    args = ap.parse_args(argv)

    if args.image:
        paths = [Path(args.image)]
    else:
        paths = approved_images(args.stage_dir)
    if not paths:
        print("no input images", file=sys.stderr)
        return 2

    report = build_report(paths, min_conf=args.min_conf)
    out = write_report(report, args.out)
    print(json.dumps(report["summary"], indent=2))
    print("report:", out)
    if not report["metrics_module"]["available"]:
        print("METRICS UNAVAILABLE - keypoints and geometry only, no head/spine measurement:",
              report["metrics_module"]["error"], file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
