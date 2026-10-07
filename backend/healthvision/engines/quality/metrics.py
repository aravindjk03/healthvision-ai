"""Raw image-quality measurements. No thresholds here — FaceQualityService applies config."""
from __future__ import annotations

import cv2
import numpy as np


def brightness_mean(image_bgr: np.ndarray) -> float:
    return float(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY).mean())


def laplacian_variance(image_bgr: np.ndarray, max_side: int = 640) -> float:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    s = max(h, w)
    if s > max_side:
        gray = cv2.resize(gray, (int(w * max_side / s), int(h * max_side / s)), interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def face_crop(image_bgr: np.ndarray, bbox) -> np.ndarray:
    x, y, w, h = bbox
    return image_bgr[y:y + h, x:x + w]
