"""FaceQualityService — global and face-level checks (docs/05 §4). Overall grade = worst check."""

from __future__ import annotations

import cv2
import numpy as np

from healthvision.config import Config
from healthvision.domain import GRADE_ORDER, FaceDetection, Landmarks, QualityCheck, QualityGrade, QualityResult

G, A, P = QualityGrade.GOOD, QualityGrade.ACCEPTABLE, QualityGrade.POOR


def _worst(checks: list[QualityCheck]) -> QualityGrade:
    return max((c.grade for c in checks), key=lambda g: GRADE_ORDER[g], default=G)


def _band(value: float, good: float, minimum: float) -> QualityGrade:
    return G if value >= good else A if value >= minimum else P


class FaceQualityService:
    def __init__(self, config: Config):
        self.config = config
        self.q = config["quality"]

    def _brightness(self, gray: np.ndarray, name: str) -> QualityCheck:
        b = self.q["brightness_threshold"]
        mean = float(gray.mean())
        if b["min_mean"] + b["good_margin"] <= mean <= b["max_mean"] - b["good_margin"]:
            grade, msg = G, ""
        elif b["min_mean"] <= mean <= b["max_mean"]:
            grade, msg = A, ""
        else:
            grade = P
            msg = "Image is too dark" if mean < b["min_mean"] else "Image is too bright"
        return QualityCheck(name, round(mean, 1), grade, msg)

    def global_checks(self, image_bgr: np.ndarray, original_size: tuple[int, int]) -> QualityResult:
        w, h = original_size
        short = min(w, h)
        res_grade = _band(short, self.q["good_image_short_side_px"], self.q["min_image_short_side_px"])
        checks = [QualityCheck("resolution", f"{w}x{h}", res_grade,
                               "Image resolution is too low" if res_grade == P else "")]
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        checks.append(self._brightness(gray, "brightness_global"))
        return QualityResult(_worst(checks), checks)

    def face_checks(self, image_bgr: np.ndarray, detection: FaceDetection, landmarks: Landmarks | None,
                    aligned: np.ndarray | None, scale: float) -> QualityResult:
        """scale = original_px / working_px, so face size is judged in the original image."""
        checks: list[QualityCheck] = []
        h, w = image_bgr.shape[:2]
        x, y, bw, bh = detection.bbox

        size_px = min(bw, bh) * scale
        min_size = self.q["minimum_face_size_px"]
        g = _band(size_px, 1.5 * min_size, min_size)
        checks.append(QualityCheck("face_size", round(size_px), g,
                                   "Face is too small — move closer to the camera" if g == P else ""))

        raw = detection.raw
        if raw is not None:
            rx, ry, rw, rh = (float(v) for v in raw[:4])
            ix0, iy0, ix1, iy1 = max(0.0, rx), max(0.0, ry), min(float(w), rx + rw), min(float(h), ry + rh)
            inside = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0) / max(1.0, rw * rh)
        else:
            inside = 1.0
        vis = self.q["visibility"]
        g = _band(inside, vis["bbox_inside_good"], vis["bbox_inside_min"])
        checks.append(QualityCheck("face_visibility", round(inside, 3), g,
                                   "Face is partly outside the frame" if g == P else ""))

        if landmarks is None:
            checks.append(QualityCheck("landmarks", "not detected", P, "Facial features could not be located"))
        else:
            occ = self.q["occlusion"]
            g = _band(landmarks.visibility, occ["good_landmark_visibility"], occ["min_landmark_visibility"])
            checks.append(QualityCheck("occlusion", landmarks.visibility, g,
                                       "Part of the face appears hidden" if g == P else ""))
            pm = self.q["pose_max_deg"]
            yaw, pitch, roll = (abs(landmarks.pose[k]) for k in ("yaw", "pitch", "roll"))
            if yaw <= pm["yaw_good"] and pitch <= pm["pitch_good"] and roll <= pm["roll_good"]:
                g = G
            elif yaw <= pm["yaw_max"] and pitch <= pm["pitch_max"] and roll <= pm["roll_max"]:
                g = A
            else:
                g = P
            checks.append(QualityCheck("pose", dict(landmarks.pose), g,
                                       "Face is turned too far — please look at the camera" if g == P else ""))

        if aligned is not None:
            gray = cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY)
            checks.append(self._brightness(gray, "brightness_face"))
            ct = self.q["contrast_threshold"]
            contrast = float(gray.std())
            g = _band(contrast, ct["good"], ct["min"])
            checks.append(QualityCheck("contrast", round(contrast, 1), g, "Face has too little contrast" if g == P else ""))
            bt = self.q["blur_threshold"]
            lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            g = _band(lap, bt["laplacian_var_good"], bt["laplacian_var_min"])
            checks.append(QualityCheck("blur", round(lap, 1), g, "Image is blurry — hold still" if g == P else ""))
        else:
            checks.append(QualityCheck("alignment", "failed", P, "Could not align the face — please face the camera"))

        return QualityResult(_worst(checks), checks)
