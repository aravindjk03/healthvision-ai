"""5-point similarity alignment to the ArcFace canonical 112×112 template (docs/03 §4)."""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

ARCFACE_112 = np.array(
    [(38.2946, 51.6963), (73.5318, 51.5014), (56.0252, 71.7366), (41.5493, 92.3655), (70.7299, 92.2041)],
    dtype=np.float32,
)


def align_112(image_bgr: np.ndarray, keypoints5) -> Optional[np.ndarray]:
    src = np.asarray(keypoints5, dtype=np.float32)
    if src.shape != (5, 2) or not np.all(np.isfinite(src)):
        return None
    M, _ = cv2.estimateAffinePartial2D(src, ARCFACE_112, method=cv2.LMEDS)
    if M is None:
        return None
    return cv2.warpAffine(image_bgr, M, (112, 112), borderValue=0)


def expression_crop(aligned_112: np.ndarray) -> np.ndarray:
    """FER+ input: centre of the aligned face, grayscale, 64×64, raw 0–255 float."""
    gray = cv2.cvtColor(aligned_112, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA).astype(np.float32)
