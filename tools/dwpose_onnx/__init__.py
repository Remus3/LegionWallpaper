"""Vendored DWPose onnx-CPU inference helpers (IDEA-Research/DWPose, onnx branch).

onnxdet.inference_detector(session, oriImg) -> Nx4 person boxes (xyxy px).
onnxpose.inference_pose(session, out_bbox, oriImg) -> (N,133,2) keypoints px,
(N,133) scores. Consumed by tools.lw_gen_localizer_eval.dwpose_backend. Kept
here unmodified so the mmcv/mmpose stack (blocked on torch 2.11 / Blackwell) is
never imported - only onnxruntime + cv2 + numpy.
"""
