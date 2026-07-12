"""Detector-agnostic weapon-localizer evaluation harness (M1 weapon pass).

Runs a pluggable wholebody pose BACKEND over the 6 recall-gate samples, derives
the weapon ROI with tools.lw_gen_weaponfix.weapon_roi_from_keypoints (reused
unchanged - slices 1-2), renders a per-image overlay (both wrist ROIs + joint
markers + fallback reason) plus a contact sheet, and writes a JSON summary. The
operator visually scores the wrist-on-weapon hit-rate off the contact sheet;
acceptance = clearly beat OpenPose's 1/6, target >= 4/6.

Backend boundary = a callable  image_path -> BackendOutput(kp_map, left_hand,
right_hand). Two output shapes feed the SAME weaponfix geometry:
  - OpenPose (baseline, no download): reuses tools.lw_gen_pose + slice-2's
    body_to_kp_map / pose_to_weapon_inputs (OpenPose-18, already normalized).
  - SDPose-Wholebody / DWPose (later): COCO-WholeBody-133 in PIXEL coords ->
    cocowb_to_kp_map (below). Neck is DERIVED as the shoulder midpoint.

cocowb_to_kp_map is NEW, not a slice-2 rebuild: COCO-WholeBody has different
indices than OpenPose-18 and no neck slot. It is pure (stdlib only) so it unit
-tests torch-free; every heavy import (torch / controlnet_aux / the onnx or
diffusion backends) stays lazy inside its backend function.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
# Allow `python tools/lw_gen_localizer_eval.py ...` (script mode puts tools/ on
# sys.path, not the repo root) to still import the `tools` package.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# --- COCO-WholeBody-133 index map (mmpose spec) -----------------------------
# body COCO-17: 0 nose; 1-4 eyes/ears; 5 L-shoulder 6 R-shoulder; 7 L-elbow
#   8 R-elbow; 9 L-wrist 10 R-wrist; 11-16 hips/knees/ankles. 17-22 feet(6).
#   23-90 face(68). 91-111 left hand(21). 112-132 right hand(21).
CWB = {
    "nose": 0,
    "Lshoulder": 5,
    "Rshoulder": 6,
    "LElbow": 7,
    "RElbow": 8,
    "LWrist": 9,
    "RWrist": 10,
}
CWB_LEFT_HAND = (91, 112)   # slice bounds [start, stop)
CWB_RIGHT_HAND = (112, 133)

# 6 recall-gate samples -> full-res source (name, repo-relative path).
SAMPLES: List[Tuple[str, str]] = [
    ("seed22", "images/_gen_scratch/exp3_clean/seed22.png"),
    ("seed33", "images/_gen_scratch/exp3_clean/seed33.png"),
    ("seed800", "images/_gen_scratch/exp4_volume/seed800.png"),
    ("cand_01", "images/_gen_scratch/vayne-controlnet-proto/cand_01.png"),
    ("cand_02", "images/_gen_scratch/vayne-controlnet-proto/cand_02.png"),
    ("seed42", "images/_gen_scratch/exp4_volume/seed42.png"),
]


@dataclass
class BackendOutput:
    """A backend's detection, normalized to the weaponfix contract.

    kp_map holds the six weaponfix keys (nose/neck/RElbow/RWrist/LElbow/LWrist)
    as normalized (x, y) in [0, 1] or None. left_hand / right_hand are lists of
    normalized (x, y) hand keypoints for the respective side (never None).
    """

    kp_map: Dict[str, Optional[Tuple[float, float]]]
    left_hand: List[Tuple[float, float]] = field(default_factory=list)
    right_hand: List[Tuple[float, float]] = field(default_factory=list)
    meta: dict = field(default_factory=dict)  # diagnostics (raw scores, n_boxes)


def _triple(pt):
    """Unpack a keypoint as (x, y, conf); a 2-tuple implies conf 1.0."""
    if len(pt) >= 3:
        return float(pt[0]), float(pt[1]), float(pt[2])
    return float(pt[0]), float(pt[1]), 1.0


def _hand_pts(kps, bounds, w, h, min_conf):
    lo, hi = bounds
    out = []
    for idx in range(lo, hi):
        if idx >= len(kps):
            break
        x, y, c = _triple(kps[idx])
        if c < min_conf:
            continue
        out.append((x / w, y / h))
    return out


def cocowb_to_kp_map(kps, img_wh, min_conf: float = 0.3):
    """COCO-WholeBody-133 (PIXEL coords) -> weaponfix kp_map + per-side hands.

    kps is a length-133 sequence of (x, y) or (x, y, conf) in image pixels;
    img_wh = (W, H). Returns (kp_map, left_hand, right_hand): kp_map values are
    normalized (x, y) in [0, 1] or None (conf below min_conf, or a shoulder
    missing for the derived neck); the hand lists are normalized (x, y) points
    with sub-floor points dropped. Pure stdlib - no numpy / torch.
    """
    w, h = float(img_wh[0]), float(img_wh[1])

    def norm(idx):
        x, y, c = _triple(kps[idx])
        if c < min_conf:
            return None
        return (x / w, y / h)

    kp_map = {
        "nose": norm(CWB["nose"]),
        "RElbow": norm(CWB["RElbow"]),
        "RWrist": norm(CWB["RWrist"]),
        "LElbow": norm(CWB["LElbow"]),
        "LWrist": norm(CWB["LWrist"]),
    }
    ls = norm(CWB["Lshoulder"])
    rs = norm(CWB["Rshoulder"])
    kp_map["neck"] = (
        ((ls[0] + rs[0]) / 2.0, (ls[1] + rs[1]) / 2.0) if ls and rs else None
    )
    left_hand = _hand_pts(kps, CWB_LEFT_HAND, w, h, min_conf)
    right_hand = _hand_pts(kps, CWB_RIGHT_HAND, w, h, min_conf)
    return kp_map, left_hand, right_hand


# --- backends ---------------------------------------------------------------
def openpose_backend(image_path: str) -> BackendOutput:
    """OpenPose baseline backend (reuses M0 + slice-2; lazy torch)."""
    from tools import lw_gen_pose, lw_gen_weaponfix

    poses = lw_gen_pose.detect_candidate(image_path)
    kp_map = lw_gen_weaponfix.body_to_kp_map(poses)
    _, rh = lw_gen_weaponfix.pose_to_weapon_inputs(poses, "right")
    _, lh = lw_gen_weaponfix.pose_to_weapon_inputs(poses, "left")
    return BackendOutput(kp_map=kp_map, left_hand=lh or [], right_hand=rh or [])


_DW_MODELS = ROOT / "tools/models/dwpose"
_DW_SESSIONS: dict = {}
_KP6 = ("nose", "neck", "RElbow", "RWrist", "LElbow", "LWrist")


def _dwpose_sessions():
    """Lazily build + cache the two CPU onnxruntime sessions (det + pose)."""
    if not _DW_SESSIONS:
        import onnxruntime as ort

        prov = ["CPUExecutionProvider"]
        _DW_SESSIONS["det"] = ort.InferenceSession(
            str(_DW_MODELS / "yolox_l.onnx"), providers=prov
        )
        _DW_SESSIONS["pose"] = ort.InferenceSession(
            str(_DW_MODELS / "dw-ll_ucoco_384.onnx"), providers=prov
        )
    return _DW_SESSIONS["det"], _DW_SESSIONS["pose"]


def dwpose_backend(image_path: str, min_conf: float = 0.3) -> BackendOutput:
    """DWPose onnx-CPU backend: yolox_l person box -> dw-ll 133-kpt wholebody.

    Reads the image BGR (cv2, matching the reference impl), detects person
    boxes, runs pose, picks the highest-mean-score person, and feeds the raw
    133-keypoint PIXEL array through cocowb_to_kp_map. meta records the raw
    key-joint scores + box count so the confidence floor is calibratable from
    one run (DWPose is photographic-trained; scores on stylized art are the
    empirical unknown).
    """
    import cv2
    import numpy as np

    from tools.dwpose_onnx import onnxdet, onnxpose

    det_sess, pose_sess = _dwpose_sessions()
    ori = cv2.imread(image_path)  # BGR, HxWx3
    H, W = ori.shape[:2]
    boxes = onnxdet.inference_detector(det_sess, ori)
    kpts, scores = onnxpose.inference_pose(pose_sess, boxes, ori)
    if kpts is None or len(kpts) == 0:
        return BackendOutput(kp_map={k: None for k in _KP6}, meta={"n_boxes": 0})
    idx = int(np.argmax(scores.mean(axis=1)))
    person, sc = kpts[idx], scores[idx]  # (133,2) px, (133,)
    kps133 = [(float(person[i, 0]), float(person[i, 1]), float(sc[i])) for i in range(133)]
    kp_map, lh, rh = cocowb_to_kp_map(kps133, (W, H), min_conf=min_conf)
    meta = {
        "n_boxes": int(len(boxes)) if hasattr(boxes, "__len__") else 0,
        "person_mean_score": round(float(sc.mean()), 4),
        "scores": {
            "nose": round(float(sc[0]), 3),
            "Lshoulder": round(float(sc[5]), 3), "Rshoulder": round(float(sc[6]), 3),
            "LElbow": round(float(sc[7]), 3), "RElbow": round(float(sc[8]), 3),
            "LWrist": round(float(sc[9]), 3), "RWrist": round(float(sc[10]), 3),
        },
    }
    return BackendOutput(kp_map=kp_map, left_hand=lh, right_hand=rh, meta=meta)


BACKENDS: Dict[str, Callable[[str], BackendOutput]] = {
    "openpose": openpose_backend,
    "dwpose": dwpose_backend,
}


# --- rendering (I/O; PIL only) ----------------------------------------------
_MARKER = {
    "RWrist": (255, 40, 40),
    "RElbow": (255, 150, 0),
    "LWrist": (40, 120, 255),
    "LElbow": (0, 200, 220),
    "nose": (255, 240, 0),
    "neck": (40, 220, 40),
}
_ROI_R = (255, 40, 40)   # right-wrist ROI tint
_ROI_L = (40, 120, 255)  # left-wrist ROI tint


def _tint(base_rgba, mask_bool, color, alpha=0.42):
    import numpy as np
    from PIL import Image

    rgba = np.zeros((mask_bool.shape[0], mask_bool.shape[1], 4), dtype=np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = color
    rgba[..., 3] = (mask_bool.astype(np.uint8) * int(255 * alpha))
    return Image.alpha_composite(base_rgba, Image.fromarray(rgba, "RGBA"))


def render_overlay(image_path, kp_map, roi_r, roi_l, title):
    from PIL import Image, ImageDraw

    base = Image.open(image_path).convert("RGBA")
    W, H = base.size
    for roi, col in ((roi_r, _ROI_R), (roi_l, _ROI_L)):
        if roi.ok and roi.mask_binary is not None:
            base = _tint(base, roi.mask_binary, col)
    draw = ImageDraw.Draw(base)
    r = max(6, W // 120)
    for name, col in _MARKER.items():
        pt = kp_map.get(name)
        if pt is None:
            continue
        cx, cy = pt[0] * W, pt[1] * H
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col, outline=(0, 0, 0))
    tag = f"R:{roi_r.fallback or 'OK'}  L:{roi_l.fallback or 'OK'}"
    draw.rectangle([0, 0, W, max(28, H // 22)], fill=(0, 0, 0))
    draw.text((8, 4), f"{title}   {tag}", fill=(255, 255, 255))
    return base.convert("RGB")


def contact_sheet(overlay_paths, out_path, cols=3, cell_w=640):
    from PIL import Image

    imgs = [Image.open(p).convert("RGB") for p in overlay_paths]
    if not imgs:
        return None
    rows = (len(imgs) + cols - 1) // cols
    cell_h = int(cell_w * imgs[0].height / imgs[0].width)
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (24, 24, 24))
    for i, im in enumerate(imgs):
        thumb = im.resize((cell_w, cell_h))
        sheet.paste(thumb, ((i % cols) * cell_w, (i // cols) * cell_h))
    sheet.save(out_path)
    return out_path


def run(backend_name: str, out_dir: Optional[str] = None) -> dict:
    """Run one backend over the 6 samples -> overlays + contact sheet + summary."""
    from tools.lw_gen_weaponfix import weapon_roi_from_keypoints
    from PIL import Image

    backend = BACKENDS[backend_name]
    outd = Path(out_dir) if out_dir else ROOT / "images/_gen_scratch/localizer_eval" / backend_name
    outd.mkdir(parents=True, exist_ok=True)

    overlays, summary = [], {}
    for name, rel in SAMPLES:
        src = ROOT / rel
        W, H = Image.open(src).size
        out = backend(str(src))
        roi_r = weapon_roi_from_keypoints(out.kp_map, "right", (W, H), out.right_hand)
        roi_l = weapon_roi_from_keypoints(out.kp_map, "left", (W, H), out.left_hand)
        ov = render_overlay(str(src), out.kp_map, roi_r, roi_l, name)
        ov_path = outd / f"{name}_overlay.png"
        ov.save(ov_path)
        overlays.append(str(ov_path))
        summary[name] = {
            "img_wh": [W, H],
            "kp_map": {k: (list(v) if v else None) for k, v in out.kp_map.items()},
            "right": {"ok": roi_r.ok, "fallback": roi_r.fallback},
            "left": {"ok": roi_l.ok, "fallback": roi_l.fallback},
            "meta": out.meta,
        }
    sheet = contact_sheet(overlays, str(outd / "contact_sheet.png"))
    (outd / "summary.json").write_text(json.dumps(summary, indent=2), encoding="ascii")
    return {"backend": backend_name, "out_dir": str(outd), "sheet": sheet, "summary": summary}


def _main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="Weapon-localizer eval over the 6 recall-gate samples.")
    ap.add_argument("backend", choices=sorted(BACKENDS), help="pose backend to evaluate")
    ap.add_argument("--out", default=None, help="output dir (default images/_gen_scratch/localizer_eval/<backend>)")
    args = ap.parse_args(argv)
    result = run(args.backend, args.out)
    print(json.dumps(result["summary"], indent=2))
    print("sheet:", result["sheet"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
