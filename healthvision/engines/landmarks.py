"""Model C — landmark engines. Geometry only; never interpreted medically (docs/05 §5)."""

from __future__ import annotations

import threading
from pathlib import Path

import cv2
import numpy as np

from healthvision.domain import FaceDetection, Landmarks
from healthvision.engines.base import EngineInfo
from healthvision.engines.pose import pose_from_five_points

# MediaPipe 478-point indices.
_R_EYE = (33, 133)        # image-left eye (subject's right)
_L_EYE = (362, 263)       # image-right eye (subject's left)
_NOSE_TIP = 1
_MOUTH_R = 61             # image-left mouth corner
_MOUTH_L = 291            # image-right mouth corner


def _pose_from_matrix(result) -> dict[str, float] | None:
    """Head pose from MediaPipe's facial transformation matrix (more stable than generic-model PnP)."""
    mats = getattr(result, "facial_transformation_matrixes", None)
    if not mats:
        return None
    rot = np.asarray(mats[0], dtype=np.float64)[:3, :3]
    (pitch, yaw, roll), *_ = cv2.RQDecomp3x3(rot)
    return {"yaw": round(float(yaw), 1), "pitch": round(float(pitch), 1), "roll": round(float(roll), 1)}


class MediaPipeLandmarker:
    def __init__(self, task_path: Path, version: str, crop_padding: float):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(task_path)),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=1,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._padding = crop_padding
        self._lock = threading.Lock()   # shared across Streamlit sessions
        self._info = EngineInfo("landmarks.mediapipe_face_landmarker", version, "mediapipe")

    def info(self) -> EngineInfo:
        return self._info

    def landmarks(self, image_bgr: np.ndarray, detection: FaceDetection) -> Landmarks | None:
        h, w = image_bgr.shape[:2]
        x, y, bw, bh = detection.bbox
        pad_x, pad_y = int(bw * self._padding), int(bh * self._padding)
        x0, y0 = max(0, x - pad_x), max(0, y - pad_y)
        x1, y1 = min(w, x + bw + pad_x), min(h, y + bh + pad_y)
        crop = image_bgr[y0:y1, x0:x1]
        if crop.size == 0:
            return None
        rgb = np.ascontiguousarray(crop[:, :, ::-1])
        with self._lock:
            result = self._landmarker.detect(self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb))
        if not result.face_landmarks:
            return None
        ch, cw = crop.shape[:2]
        lm = result.face_landmarks[0]
        norm = np.array([(p.x, p.y) for p in lm], dtype=np.float64)
        in_crop = float(np.mean((norm[:, 0] >= 0) & (norm[:, 0] <= 1) & (norm[:, 1] >= 0) & (norm[:, 1] <= 1)))
        pts = norm * np.array([cw, ch]) + np.array([x0, y0])
        in_image = float(np.mean((pts[:, 0] >= 0) & (pts[:, 0] < w) & (pts[:, 1] >= 0) & (pts[:, 1] < h)))

        def mid(a: int, b: int) -> tuple[float, float]:
            return (float((pts[a, 0] + pts[b, 0]) / 2), float((pts[a, 1] + pts[b, 1]) / 2))

        kps5 = [mid(*_R_EYE), mid(*_L_EYE), tuple(pts[_NOSE_TIP]), tuple(pts[_MOUTH_R]), tuple(pts[_MOUTH_L])]
        kps5 = [(float(px), float(py)) for px, py in kps5]
        pose = _pose_from_matrix(result) or pose_from_five_points(kps5)
        return Landmarks(scheme="mediapipe_478", points=pts, visibility=round(min(in_crop, in_image), 3),
                         pose=pose, keypoints5=kps5)


class FivePointLandmarker:
    """Fallback engine using detector keypoints when MediaPipe is unavailable."""

    def __init__(self):
        self._info = EngineInfo("landmarks.fivepoint", "1", "python")

    def info(self) -> EngineInfo:
        return self._info

    def landmarks(self, image_bgr: np.ndarray, detection: FaceDetection) -> Landmarks | None:
        if not detection.keypoints5:
            return None
        h, w = image_bgr.shape[:2]
        pts = np.array(detection.keypoints5, dtype=np.float64)
        inside = float(np.mean((pts[:, 0] >= 0) & (pts[:, 0] < w) & (pts[:, 1] >= 0) & (pts[:, 1] < h)))
        return Landmarks(scheme="fivepoint", points=pts, visibility=round(inside, 3),
                         pose=pose_from_five_points(detection.keypoints5), keypoints5=list(detection.keypoints5))
