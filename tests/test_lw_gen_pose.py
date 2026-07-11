"""CI-safe tests for tools/lw_gen_pose.py (torch-free, no real detector).

Proves: the module imports under base python with torch/controlnet_aux kept
lazy; body None-keypoint sentinels are dropped (never coerced to origin);
hand/face negative missing-peak sentinels are filtered by x>=0 and y>=0;
multi-body picks max total_score; zero bodies returns an empty schema; the
preprocessing mirrors OpenposeDetector.__call__ (HWC3 3-channel uint8, short
side 512); keypoints are normalized in [0,1] and written atomically; and
run_batch emits one pose json per manifest candidate keyed off cand["file"].
NO torch and NO controlnet_aux are imported - a fake detector is injected.
"""
import json
import os
import sys
from collections import namedtuple

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools import lw_gen_pose as lgp  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes - mirror the real NamedTuple shapes without importing controlnet_aux.
# PoseResult(body, left_hand, right_hand, face); BodyResult has .keypoints
# (list of Keypoint or None) + .total_score; Keypoint has .x .y .score.
# ---------------------------------------------------------------------------
FakeKeypoint = namedtuple("FakeKeypoint", ["x", "y", "score"])
FakeBody = namedtuple("FakeBody", ["keypoints", "total_score"])
FakePose = namedtuple("FakePose", ["body", "left_hand", "right_hand", "face"])


class RecordingDetector:
    """Fake detector that captures the array handed to detect_poses."""

    def __init__(self, poses=None):
        self.captured = None
        self._poses = [] if poses is None else poses

    def detect_poses(self, arr, include_hand=False, include_face=False):
        self.captured = arr
        return self._poses


# ---------------------------------------------------------------------------
# 1. Import safety (lazy torch/controlnet_aux proof).
# ---------------------------------------------------------------------------
def test_import_is_torch_free():
    assert "torch" not in sys.modules
    assert "controlnet_aux" not in sys.modules
    assert callable(lgp.detect_candidate)


# ---------------------------------------------------------------------------
# 2. Body None-keypoint sentinel is dropped, not coerced to origin.
# ---------------------------------------------------------------------------
def test_body_none_sentinel_dropped():
    kps = [FakeKeypoint(0.5, 0.6, 0.9), None, FakeKeypoint(0.7, 0.8, 0.8), None]
    body = FakeBody(keypoints=kps, total_score=5.0)
    pose = FakePose(body=body, left_hand=None, right_hand=None, face=None)
    out = lgp.poseresult_to_keypoints([pose], source="x")
    kept = out["body"]["keypoints"]
    assert len(kept) == 2  # both None entries dropped
    xs = [k["x"] for k in kept]
    ys = [k["y"] for k in kept]
    # None sentinels were NOT collapsed to (0, 0): the bbox min corner stays real.
    assert min(xs) > 0.0 and min(ys) > 0.0


# ---------------------------------------------------------------------------
# 3. Hand negative missing-peak sentinel (-1/W) is filtered.
# ---------------------------------------------------------------------------
def test_hand_negative_sentinel_dropped():
    hand = [FakeKeypoint(-0.0007, 0.5, 0.0), FakeKeypoint(0.4, 0.6, 0.9)]
    body = FakeBody(keypoints=[FakeKeypoint(0.5, 0.5, 0.9)], total_score=3.0)
    pose = FakePose(body=body, left_hand=hand, right_hand=None, face=None)
    out = lgp.poseresult_to_keypoints([pose], source="x")
    lh = out["left_hand"]
    assert len(lh) == 1
    assert lh[0]["x"] == 0.4
    assert all(k["x"] >= 0.0 and k["y"] >= 0.0 for k in lh)


# ---------------------------------------------------------------------------
# 4. Multi-body: the max total_score body wins.
# ---------------------------------------------------------------------------
def test_multibody_picks_max_total_score():
    b1 = FakeBody(keypoints=[FakeKeypoint(0.1, 0.1, 0.5)], total_score=3.0)
    b2 = FakeBody(keypoints=[FakeKeypoint(0.9, 0.9, 0.5)], total_score=8.0)
    p1 = FakePose(body=b1, left_hand=None, right_hand=None, face=None)
    p2 = FakePose(body=b2, left_hand=None, right_hand=None, face=None)
    out = lgp.poseresult_to_keypoints([p1, p2], source="x")
    assert out["body"]["total_score"] == 8.0
    assert out["body"]["keypoints"][0]["x"] == 0.9


# ---------------------------------------------------------------------------
# 5. Zero bodies -> empty schema, body None, no crash.
# ---------------------------------------------------------------------------
def test_zero_body_returns_empty():
    out = lgp.poseresult_to_keypoints([], source="x")
    assert out["body"] is None
    assert out["left_hand"] == []
    assert out["right_hand"] == []
    assert out["face"] == []


# ---------------------------------------------------------------------------
# 6. Preprocessing mirrors OpenposeDetector.__call__: HWC3 3-channel uint8,
#    short side resized to 512.
# ---------------------------------------------------------------------------
def test_preprocess_mirrors_call(tmp_path):
    p = tmp_path / "tiny.png"
    Image.fromarray(np.zeros((100, 200, 3), dtype=np.uint8)).save(p)
    det = RecordingDetector()
    lgp.detect_candidate(str(p), detector=det)
    arr = det.captured
    assert arr is not None
    assert arr.dtype == np.uint8
    assert arr.ndim == 3 and arr.shape[2] == 3  # HWC3
    assert min(arr.shape[0], arr.shape[1]) == 512  # short side 512


# ---------------------------------------------------------------------------
# 7. Normalized coords in [0,1] + atomic write (tmp -> replace) + schema.
# ---------------------------------------------------------------------------
def test_keypoints_normalized_and_atomic(tmp_path):
    body = FakeBody(keypoints=[FakeKeypoint(0.25, 0.75, 0.9)], total_score=4.0)
    hand = [FakeKeypoint(0.1, 0.2, 0.5)]
    pose = FakePose(body=body, left_hand=hand, right_hand=None, face=None)
    kp = lgp.poseresult_to_keypoints([pose], source="cand_00.png")
    for k in kp["body"]["keypoints"] + kp["left_hand"]:
        assert 0.0 <= k["x"] <= 1.0 and 0.0 <= k["y"] <= 1.0

    lgp.write_keypoints_json(str(tmp_path), "cand_00.png", kp)
    target = tmp_path / "cand_00.pose.json"
    assert target.exists()
    data = json.loads(target.read_text(encoding="ascii"))
    assert "version" in data
    assert data["source"] == "cand_00.png"
    # Atomic write left no temp artifact behind.
    assert list(tmp_path.glob("*.tmp")) == []


# ---------------------------------------------------------------------------
# 8. run_batch emits one cand_<NN>.pose.json per manifest candidate.
# ---------------------------------------------------------------------------
def test_run_batch_one_json_per_candidate(tmp_path):
    for name in ("cand_00.png", "cand_01.png"):
        Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(tmp_path / name)
    manifest = {"candidates": [{"file": "cand_00.png"}, {"file": "cand_01.png"}]}
    (tmp_path / "gen_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True), encoding="ascii"
    )
    pose = FakePose(
        body=FakeBody(keypoints=[FakeKeypoint(0.5, 0.5, 0.9)], total_score=5.0),
        left_hand=None,
        right_hand=None,
        face=None,
    )
    stub = RecordingDetector(poses=[pose])
    lgp.run_batch(str(tmp_path), detector=stub)
    assert (tmp_path / "cand_00.pose.json").exists()
    assert (tmp_path / "cand_01.pose.json").exists()
    data = json.loads((tmp_path / "cand_01.pose.json").read_text(encoding="ascii"))
    assert data["source"] == "cand_01.png"
