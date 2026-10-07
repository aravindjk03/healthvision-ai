"""FaceQualityService — global + face-level checks and overall grade (docs/05 §4).

Grade policy ``worst_check``: overall grade = worst individual check.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from ..config.settings import QualityCfg
from ..domain.enums import QualityGrade
from ..engines.base import FaceDetection, Landmarks
from ..engines.quality import metrics

_ORDER = {QualityGrade.GOOD: 0, QualityGrade.ACCEPTABLE: 1, QualityGrade.POOR: 2}


def _check(name: str, grade: QualityGrade, value, detail: str) -> dict:
    return {"check": name, "grade": grade.value, "value": value, "detail": detail}


def worst(checks: list[dict]) -> QualityGrade:
    if not checks:
        return QualityGrade.GOOD
    return max((QualityGrade(c["grade"]) for c in checks), key=lambda g: _ORDER[g])


def failing(checks: list[dict]) -> list[str]:
    return [c["detail"] for c in checks if c["grade"] == QualityGrade.POOR]


class FaceQualityService:
    def __init__(self, cfg: QualityCfg):
        self.cfg = cfg

    def global_checks(self, image_bgr: np.ndarray) -> list[dict]:
        c = self.cfg
        h, w = image_bgr.shape[:2]
        short = min(h, w)
        res = _check("resolution", QualityGrade.GOOD if short >= c.min_image_short_side_px else QualityGrade.ACCEPTABLE,
                     short, f"image short side {short}px (recommended ≥ {c.min_image_short_side_px}px)")
        b = round(metrics.brightness_mean(image_bgr), 1)
        bt = c.brightness_threshold
        if b < bt.min_mean:
            bg = _check("brightness", QualityGrade.POOR, b, "image too dark")
        elif b > bt.max_mean:
            bg = _check("brightness", QualityGrade.POOR, b, "image too bright")
        else:
            bg = _check("brightness", QualityGrade.GOOD, b, "brightness OK")
        lv = round(metrics.laplacian_variance(image_bgr), 1)
        gb = _check("global_blur", QualityGrade.GOOD if lv >= c.global_blur_min else QualityGrade.POOR, lv,
                    "image sharp enough" if lv >= c.global_blur_min else "image too blurry")
        return [res, bg, gb]

    def face_checks(self, image_bgr: np.ndarray, det: FaceDetection, lm: Optional[Landmarks]) -> list[dict]:
        c = self.cfg
        out = []
        size = min(det.bbox[2], det.bbox[3])
        out.append(_check("face_size", QualityGrade.GOOD if size >= c.minimum_face_size_px else QualityGrade.POOR, size,
                          f"face {size}px" + ("" if size >= c.minimum_face_size_px else f" — move closer (≥ {c.minimum_face_size_px}px)")))
        crop = metrics.face_crop(image_bgr, det.bbox)
        if crop.size:
            fv = round(metrics.laplacian_variance(crop), 1)
            bt = c.blur_threshold
            g = QualityGrade.GOOD if fv >= bt.laplacian_var_good else (QualityGrade.ACCEPTABLE if fv >= bt.laplacian_var_min else QualityGrade.POOR)
            out.append(_check("face_blur", g, fv, {QualityGrade.GOOD: "face sharp", QualityGrade.ACCEPTABLE: "face slightly blurry",
                                                     QualityGrade.POOR: "face too blurry"}[g]))
            fb = round(metrics.brightness_mean(crop), 1)
            if fb < c.brightness_threshold.min_mean or fb > c.brightness_threshold.max_mean:
                out.append(_check("face_lighting", QualityGrade.POOR, fb, "face too dark" if fb < c.brightness_threshold.min_mean else "face too bright"))
            else:
                out.append(_check("face_lighting", QualityGrade.GOOD, fb, "face lighting OK"))
        if lm is None:
            out.append(_check("landmarks", QualityGrade.POOR, None, "facial landmarks not found"))
            return out
        vis = round(lm.visibility, 3)
        out.append(_check("visibility", QualityGrade.GOOD if vis >= c.occlusion.min_landmark_visibility else QualityGrade.POOR, vis,
                          "face fully visible" if vis >= c.occlusion.min_landmark_visibility else "part of the face is out of frame or occluded"))
        p, pc = lm.pose, c.pose_max_deg
        yaw, pitch, roll = abs(p["yaw"]), abs(p["pitch"]), abs(p["roll"])
        if yaw > pc.yaw_max or pitch > pc.pitch_max or roll > pc.roll_max:
            g, d = QualityGrade.POOR, "head turned or tilted too far — face the camera"
        elif yaw > pc.yaw_good or pitch > pc.pitch_good:
            g, d = QualityGrade.ACCEPTABLE, "head slightly turned"
        else:
            g, d = QualityGrade.GOOD, "facing the camera"
        out.append(_check("pose", g, {"yaw": p["yaw"], "pitch": p["pitch"], "roll": p["roll"]}, d))
        return out
