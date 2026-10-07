"""Model C — MediaPipe Face Landmarker (478 points) run on an expanded detector crop.

Outputs geometry only: points, a visibility estimate, head pose and the 5 alignment
keypoints. Nothing here is interpreted as a health or emotion finding.
"""
from __future__ import annotations

import math
import threading
from typing import Optional

import cv2
import numpy as np

from ..base import EngineInfo, FaceDetection, LandmarkEngine, Landmarks

# Subject's right eye appears on the image left. Order matches the ArcFace 5-point template:
# image-left eye, image-right eye, nose tip, image-left mouth corner, image-right mouth corner.
_KP5_IDX = [468, 473, 1, 61, 291]
_REGIONS = {
    "eyes": [33, 133, 159, 145, 362, 263, 386, 374, 468, 473],
    "nose": [1, 2, 4, 5, 98, 327, 168],
    "mouth": [61, 291, 0, 17, 13, 14, 78, 308],
    "jaw": [234, 454, 152, 172, 397, 136, 365, 58, 288],
}
_CROP_EXPAND = 0.5


class MediaPipeLandmarker(LandmarkEngine):
    def __init__(self, info: EngineInfo, model_path: str):
        super().__init__(info)
        from mediapipe.tasks.python import BaseOptions, vision

        opts = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            num_faces=1,
            output_facial_transformation_matrixes=True,
            output_face_blendshapes=False,
        )
        self._lm = vision.FaceLandmarker.create_from_options(opts)
        self._lock = threading.Lock()

    def landmarks(self, image_bgr: np.ndarray, detection: FaceDetection) -> Optional[Landmarks]:
        import mediapipe as mp

        H, W = image_bgr.shape[:2]
        x, y, w, h = detection.bbox
        side = max(w, h) * (1 + 2 * _CROP_EXPAND)
        cx, cy = x + w / 2, y + h / 2
        x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
        x1, y1 = int(min(W, cx + side / 2)), int(min(H, cy + side / 2))
        crop = np.ascontiguousarray(cv2.cvtColor(image_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2RGB))
        if crop.size == 0:
            return None
        with self._lock:
            res = self._lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=crop))
        if not res.face_landmarks:
            return None
        cw, ch = x1 - x0, y1 - y0
        pts = np.array([[p.x * cw + x0, p.y * ch + y0] for p in res.face_landmarks[0]], dtype=np.float32)

        def in_bounds(idx):
            p = pts[idx]
            return float(np.mean((p[:, 0] >= 0) & (p[:, 0] < W) & (p[:, 1] >= 0) & (p[:, 1] < H)))

        region_vis = {k: in_bounds(v) for k, v in _REGIONS.items()}
        pose = {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}
        if res.facial_transformation_matrixes:
            R = np.asarray(res.facial_transformation_matrixes[0])[:3, :3]
            pose = {
                "yaw": math.degrees(math.atan2(-R[2, 0], math.hypot(R[0, 0], R[1, 0]))),
                "pitch": math.degrees(math.atan2(R[2, 1], R[2, 2])),
                "roll": math.degrees(math.atan2(R[1, 0], R[0, 0])),
            }
        kp5 = [(float(pts[i, 0]), float(pts[i, 1])) for i in _KP5_IDX]
        return Landmarks(points=pts, scheme="mediapipe_478", visibility=min(region_vis.values()),
                         region_visibility=region_vis, pose={k: round(v, 1) for k, v in pose.items()},
                         keypoints5=kp5)

    def close(self) -> None:
        # MediaPipe's own __del__ can deadlock if it runs during garbage collection after the
        # app has shut down, so close explicitly and drop the reference.
        lm, self._lm = getattr(self, "_lm", None), None
        if lm is not None:
            with self._lock:
                lm.close()

    def warm_up(self) -> None:
        self.landmarks(np.zeros((256, 256, 3), np.uint8), FaceDetection((64, 64, 128, 128), 1.0))
