"""Head-pose estimation helpers (geometry only)."""

from __future__ import annotations

import math


def pose_from_five_points(kps: list[tuple[float, float]]) -> dict[str, float]:
    """Coarse pose from eyes, nose, mouth corners (fallback when dense landmarks are unavailable)."""
    (rx, ry), (lx, ly), (nx, ny), (rmx, rmy), (lmx, lmy) = kps
    roll = math.degrees(math.atan2(ly - ry, lx - rx))
    eye_mid_x, eye_mid_y = (rx + lx) / 2, (ry + ly) / 2
    mouth_mid_y = (rmy + lmy) / 2
    iod = max(1e-6, math.hypot(lx - rx, ly - ry))
    offset = max(-1.0, min(1.0, (nx - eye_mid_x) / (iod * 0.5)))
    yaw = math.degrees(math.asin(offset)) * 0.6
    face_h = max(1e-6, mouth_mid_y - eye_mid_y)
    ratio = (ny - eye_mid_y) / face_h        # ~0.55 for a frontal face
    pitch = (ratio - 0.55) * 90
    return {"yaw": round(yaw, 1), "pitch": round(pitch, 1), "roll": round(roll, 1)}
