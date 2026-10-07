"""API error type rendered with the standard envelope (docs/11 §2)."""
from __future__ import annotations


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def consent_required(purpose: str) -> ApiError:
    names = {"BMI": "BMI", "FACE_ANALYSIS": "Face analysis", "RECOGNITION": "Recognition"}
    return ApiError(403, "CONSENT_REQUIRED", f"{names.get(purpose, purpose)} consent is required.", {"purpose": purpose})


def not_found() -> ApiError:
    return ApiError(404, "NOT_FOUND", "Not found.")
