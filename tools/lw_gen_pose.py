"""Shared OpenPose helper for lw-gen (M0 subtask b).

Extracts a normalized skeleton (body + optional hand/face keypoints) from a
generated candidate image so downstream ControlNet-OpenPose conditioning and
pose QA can consume a single, stable schema.

Design contract:
  - ALL torch / controlnet_aux imports stay LAZY inside functions (mirrors
    tools/lw_gen_run.py::_extract_pose) so unit tests import this module
    torch-free. The real OpenposeDetector is only constructed when a caller
    passes detector=None; unit tests inject a fake detector instead.
  - Preprocessing mirrors OpenposeDetector.__call__: np.array(image, uint8)
    -> HWC3 -> resize short side to 512 -> detect_poses(arr, hand, face). It is
    reimplemented here with numpy + PIL only (no cv2 / controlnet_aux) so the
    torch-free test env can exercise it.
  - Sentinels: a body keypoint may be None -> dropped (never coerced to the
    origin). A hand/face missing peak has its coord set to -1/W (a small
    negative) -> dropped by an x>=0 and y>=0 filter, never by == -1 or None.
"""

POSE_SCHEMA_VERSION = 1


def _hwc3(arr):
    """Mirror controlnet_aux.util.HWC3: return a 3-channel uint8 HWC array.

    Grayscale is broadcast to 3 channels; RGBA is alpha-composited over white.
    """
    import numpy as np

    assert arr.dtype == np.uint8
    if arr.ndim == 2:
        arr = arr[:, :, None]
    assert arr.ndim == 3
    _h, _w, c = arr.shape
    assert c in (1, 3, 4)
    if c == 3:
        return arr
    if c == 1:
        return np.concatenate([arr, arr, arr], axis=2)
    # c == 4
    color = arr[:, :, 0:3].astype(np.float32)
    alpha = arr[:, :, 3:4].astype(np.float32) / 255.0
    y = color * alpha + 255.0 * (1.0 - alpha)
    return y.clip(0, 255).astype(np.uint8)


def _resize_image(arr, resolution=512):
    """Mirror controlnet_aux.util.resize_image: scale the short side to
    resolution, rounding each dimension to the nearest multiple of 64.

    Uses PIL (available in the base env) rather than cv2. The short side is
    exactly `resolution` because resolution is a multiple of 64.
    """
    import numpy as np
    from PIL import Image

    h, w = int(arr.shape[0]), int(arr.shape[1])
    k = float(resolution) / float(min(h, w))
    h_new = int(round(h * k / 64.0)) * 64
    w_new = int(round(w * k / 64.0)) * 64
    resample = Image.Resampling.LANCZOS if k > 1 else Image.Resampling.BOX
    img = Image.fromarray(arr).resize((w_new, h_new), resample)
    return np.array(img, dtype=np.uint8)


def detect_candidate(image_path, detector=None, include_hand=True, include_face=True):
    """Run OpenPose detection on one candidate image, returning List[PoseResult].

    If detector is None the real OpenposeDetector is lazily constructed (this
    branch pulls torch / controlnet_aux and is never hit in unit tests). The
    image is loaded, preprocessed (HWC3 + short-side-512) exactly as
    OpenposeDetector.__call__ does, then handed to detector.detect_poses.
    `detector` is the test injection seam - a fake that records the array.
    """
    import numpy as np
    from PIL import Image

    if detector is None:
        from controlnet_aux import OpenposeDetector

        detector = OpenposeDetector.from_pretrained("lllyasviel/Annotators")

    img = Image.open(image_path).convert("RGB")
    arr = np.array(img, dtype=np.uint8)
    arr = _hwc3(arr)
    arr = _resize_image(arr, 512)
    return detector.detect_poses(arr, include_hand, include_face)


def _clean_limb(limb):
    """Drop hand/face keypoints carrying the negative missing-peak sentinel.

    Real hand/face Keypoints have only x and y; a missing peak is set to -1/W
    (a small negative). Keep only x>=0 and y>=0; tolerate absent scores.
    """
    out = []
    for kp in (limb or []):
        if kp is None:
            continue
        x = float(kp.x)
        y = float(kp.y)
        if x < 0.0 or y < 0.0:
            continue
        out.append({"x": x, "y": y, "score": float(getattr(kp, "score", 0.0) or 0.0)})
    return out


def poseresult_to_keypoints(pose_results, source=None):
    """Fold a List[PoseResult] into a normalized, JSON-ready dict. Pure.

    Picks the body with the max total_score (empty / bodyless -> body None),
    drops None body keypoints (never origin-coerced), and filters hand/face
    negative sentinels. Coordinates are already normalized to [0,1] by the
    detector and are passed through unchanged.
    """
    out = {
        "version": POSE_SCHEMA_VERSION,
        "source": source,
        "body": None,
        "left_hand": [],
        "right_hand": [],
        "face": [],
    }
    bodies = [p for p in (pose_results or []) if getattr(p, "body", None) is not None]
    if not bodies:
        return out

    best = max(bodies, key=lambda p: p.body.total_score)
    body = best.body
    kps = []
    for kp in (body.keypoints or []):
        if kp is None:
            continue  # body sentinel -> drop, never coerce to (0, 0)
        kps.append(
            {
                "x": float(kp.x),
                "y": float(kp.y),
                "score": float(getattr(kp, "score", 0.0) or 0.0),
            }
        )
    out["body"] = {"total_score": float(body.total_score), "keypoints": kps}
    out["left_hand"] = _clean_limb(best.left_hand)
    out["right_hand"] = _clean_limb(best.right_hand)
    out["face"] = _clean_limb(best.face)
    return out


def write_keypoints_json(batch_dir, cand_file, keypoints):
    """Atomically write keypoints to <batch_dir>/<stem>.pose.json.

    stem = cand_file without extension. Write to a sibling .tmp then replace
    so a concurrent reader never sees a partial file. Returns the target path.
    """
    import json
    from pathlib import Path

    stem = Path(cand_file).stem
    target = Path(batch_dir) / (stem + ".pose.json")
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(keypoints, ensure_ascii=True, indent=2), encoding="ascii")
    tmp.replace(target)
    return str(target)


def run_batch(batch_dir, detector=None):
    """Extract poses for every candidate in <batch_dir>/gen_manifest.json.

    Iterates manifest["candidates"] keyed off cand["file"], emitting one
    <stem>.pose.json per candidate. Returns the list of written paths.
    """
    import json
    from pathlib import Path

    bd = Path(batch_dir)
    manifest = json.loads((bd / "gen_manifest.json").read_text(encoding="ascii"))
    written = []
    for cand in manifest.get("candidates", []):
        cand_file = cand["file"]
        pose_results = detect_candidate(str(bd / cand_file), detector=detector)
        keypoints = poseresult_to_keypoints(pose_results, source=cand_file)
        written.append(write_keypoints_json(str(bd), cand_file, keypoints))
    return written


def _main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract OpenPose keypoints for every lw-gen batch candidate."
    )
    parser.add_argument(
        "batch_dir",
        help="Batch directory holding gen_manifest.json and candidate images.",
    )
    args = parser.parse_args(argv)
    for path in run_batch(args.batch_dir):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
