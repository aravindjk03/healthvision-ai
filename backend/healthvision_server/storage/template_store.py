"""TemplateStore — the ONLY module that reads or writes face_templates (docs/08, docs/07 §4).

Templates are never returned by the API, logged, exported or included in reports.
"""
from __future__ import annotations

import numpy as np
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from ..core.util import dumps, iso, iso_in_days, uuid7
from .crypto import EnvelopeCipher, Sealed
from .orm import FaceTemplate


class TemplateStore:
    def __init__(self, cipher: EnvelopeCipher | None, max_age_days: int):
        self._cipher = cipher
        self._max_age_days = max_age_days

    @property
    def available(self) -> bool:
        return self._cipher is not None

    @staticmethod
    def _aad(user_id: str, enrollment_id: str) -> bytes:
        return f"{user_id}|{enrollment_id}".encode()

    def store(self, s: Session, user_id: str, enrollment_id: str, embedding: np.ndarray, frame_quality: dict) -> str:
        assert self._cipher is not None
        sealed = self._cipher.seal(embedding.astype(np.float32).tobytes(), self._aad(user_id, enrollment_id))
        tid = uuid7()
        s.add(FaceTemplate(template_id=tid, enrollment_id=enrollment_id, user_id=user_id, ciphertext=sealed.ciphertext,
                           nonce=sealed.nonce, wrapped_dek=sealed.wrapped_dek, kek_id=sealed.kek_id,
                           frame_quality_json=dumps(frame_quality), created_at=iso(),
                           expires_at=iso_in_days(self._max_age_days)))
        return tid

    def load(self, s: Session, user_id: str, enrollment_id: str) -> list[np.ndarray]:
        """Decrypt the user's own templates into memory for one comparison."""
        assert self._cipher is not None
        rows = s.scalars(select(FaceTemplate).where(FaceTemplate.user_id == user_id,
                                                     FaceTemplate.enrollment_id == enrollment_id)).all()
        out = []
        for r in rows:
            pt = self._cipher.open(Sealed(r.ciphertext, r.nonce, r.wrapped_dek, r.kek_id), self._aad(user_id, enrollment_id))
            out.append(np.frombuffer(pt, dtype=np.float32).copy())
        return out

    def crypto_shred(self, s: Session, *, user_id: str | None = None, enrollment_id: str | None = None,
                     expired_before: str | None = None) -> int:
        """Destroy wrapped DEKs (overwrite), then delete the rows. Returns the number shredded."""
        conds = []
        if user_id:
            conds.append(FaceTemplate.user_id == user_id)
        if enrollment_id:
            conds.append(FaceTemplate.enrollment_id == enrollment_id)
        if expired_before:
            conds.append(FaceTemplate.expires_at < expired_before)
        if not conds:
            raise ValueError("crypto_shred requires a scope")
        ids = s.scalars(select(FaceTemplate.template_id).where(*conds)).all()
        if ids:
            s.execute(update(FaceTemplate).where(FaceTemplate.template_id.in_(ids))
                      .values(wrapped_dek=b"\x00" * 60, ciphertext=b"", nonce=b"\x00" * 12))
            s.flush()
            s.execute(delete(FaceTemplate).where(FaceTemplate.template_id.in_(ids)))
        return len(ids)

    def count(self, s: Session, enrollment_id: str) -> int:
        return len(s.scalars(select(FaceTemplate.template_id).where(FaceTemplate.enrollment_id == enrollment_id)).all())
