"""SQLAlchemy ORM tables (docs/08 §2). Portable to PostgreSQL."""
from __future__ import annotations

from sqlalchemy import (Float, ForeignKey, Index, Integer, LargeBinary, String, Text, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(80))
    username: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="USER")
    status: Mapped[str] = mapped_column(String, default="ACTIVE")
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)
    deleted_at: Mapped[str | None] = mapped_column(String, nullable=True)


class UserConsent(Base):
    __tablename__ = "user_consents"
    consent_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    purpose: Mapped[str] = mapped_column(String)
    consent_status: Mapped[str] = mapped_column(String)
    timestamp: Mapped[str] = mapped_column(String)
    policy_version: Mapped[str] = mapped_column(String)
    notice_text_sha256: Mapped[str] = mapped_column(String)
    revoked_at: Mapped[str | None] = mapped_column(String, nullable=True)
    supersedes_consent_id: Mapped[str | None] = mapped_column(ForeignKey("user_consents.consent_id"), nullable=True)
    channel: Mapped[str] = mapped_column(String, default="ui")
    __table_args__ = (Index("ix_consent_user_purpose_ts", "user_id", "purpose", "timestamp"),)


class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"
    session_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    started_at: Mapped[str] = mapped_column(String)
    completed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    config_version: Mapped[str] = mapped_column(ForeignKey("config_versions.config_version"))
    latency_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    consent_snapshot_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="OPEN")
    expires_at: Mapped[str] = mapped_column(String)
    __table_args__ = (Index("ix_session_user_started", "user_id", "started_at"),)


class BmiRecord(Base):
    __tablename__ = "bmi_records"
    record_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    height: Mapped[float] = mapped_column(Float)
    weight: Mapped[float] = mapped_column(Float)
    input_json: Mapped[str] = mapped_column(Text)
    age_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bmi: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    reference: Mapped[str] = mapped_column(String)
    input_sha256: Mapped[str] = mapped_column(String)
    config_version: Mapped[str] = mapped_column(String)
    result_json: Mapped[str] = mapped_column(Text)
    trace_json: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[str] = mapped_column(String)
    expires_at: Mapped[str] = mapped_column(String)


class FaceObservation(Base):
    __tablename__ = "face_observations"
    observation_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    purpose: Mapped[str] = mapped_column(String)
    input_sha256: Mapped[str] = mapped_column(String)
    image_width: Mapped[int] = mapped_column(Integer)
    image_height: Mapped[int] = mapped_column(Integer)
    face_count: Mapped[int] = mapped_column(Integer)
    face_state: Mapped[str] = mapped_column(String)
    bboxes_json: Mapped[str] = mapped_column(Text)
    quality_grade: Mapped[str | None] = mapped_column(String, nullable=True)
    quality_checks_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    pose_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    models_json: Mapped[str] = mapped_column(Text)
    config_version: Mapped[str] = mapped_column(String)
    timestamp: Mapped[str] = mapped_column(String)
    expires_at: Mapped[str] = mapped_column(String)


class ExpressionResult(Base):
    __tablename__ = "expression_results"
    result_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    observation_id: Mapped[str] = mapped_column(ForeignKey("face_observations.observation_id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String)
    expression: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_band: Mapped[str | None] = mapped_column(String, nullable=True)
    probabilities_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    not_available_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    model_version: Mapped[str] = mapped_column(String)
    thresholds_json: Mapped[str] = mapped_column(Text)
    config_version: Mapped[str] = mapped_column(String)
    result_json: Mapped[str] = mapped_column(Text)
    trace_json: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[str] = mapped_column(String)
    expires_at: Mapped[str] = mapped_column(String)


class FaceEnrollment(Base):
    __tablename__ = "face_enrollments"
    enrollment_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    consent_id: Mapped[str] = mapped_column(ForeignKey("user_consents.consent_id"))
    template_reference: Mapped[str] = mapped_column(String)
    model_version: Mapped[str] = mapped_column(String)
    embedding_dim: Mapped[int] = mapped_column(Integer)
    template_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)
    revoked_at: Mapped[str | None] = mapped_column(String, nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    __table_args__ = (
        Index("ux_one_active_enrollment", "user_id", unique=True, sqlite_where=text("status = 'ACTIVE'"),
              postgresql_where=text("status = 'ACTIVE'")),
    )


class FaceTemplate(Base):
    __tablename__ = "face_templates"
    template_id: Mapped[str] = mapped_column(String, primary_key=True)
    enrollment_id: Mapped[str] = mapped_column(ForeignKey("face_enrollments.enrollment_id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    nonce: Mapped[bytes] = mapped_column(LargeBinary)
    wrapped_dek: Mapped[bytes] = mapped_column(LargeBinary)
    kek_id: Mapped[str] = mapped_column(String)
    frame_quality_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String)
    expires_at: Mapped[str] = mapped_column(String)


class RecognitionEvent(Base):
    __tablename__ = "recognition_events"
    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    mode: Mapped[str] = mapped_column(String)
    claimed_identity: Mapped[str | None] = mapped_column(String, nullable=True)
    matched_identity: Mapped[str | None] = mapped_column(String, nullable=True)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision: Mapped[str] = mapped_column(String)
    not_performed_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    liveness_status: Mapped[str] = mapped_column(String)
    quality_grade: Mapped[str | None] = mapped_column(String, nullable=True)
    model_version: Mapped[str] = mapped_column(String)
    threshold_match: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_no_match: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_source: Mapped[str] = mapped_column(String)
    enrollment_id: Mapped[str | None] = mapped_column(String, nullable=True)
    input_sha256: Mapped[str] = mapped_column(String)
    config_version: Mapped[str] = mapped_column(String)
    consent_snapshot_json: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str] = mapped_column(Text)
    trace_json: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[str] = mapped_column(String)
    expires_at: Mapped[str] = mapped_column(String)
    __table_args__ = (Index("ix_recog_user_ts", "user_id", "timestamp"),)


class Report(Base):
    __tablename__ = "reports"
    report_id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("analysis_sessions.session_id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    include_recognition: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    report_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String)
    expires_at: Mapped[str] = mapped_column(String)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    audit_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[str] = mapped_column(String)
    actor_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String, nullable=True)
    event_type: Mapped[str] = mapped_column(String)
    target_type: Mapped[str | None] = mapped_column(String, nullable=True)
    target_id: Mapped[str | None] = mapped_column(String, nullable=True)
    outcome: Mapped[str] = mapped_column(String)
    details_json: Mapped[str] = mapped_column(Text)
    prev_hash: Mapped[str] = mapped_column(String)
    entry_hash: Mapped[str] = mapped_column(String)


class ConfigVersion(Base):
    __tablename__ = "config_versions"
    config_version: Mapped[str] = mapped_column(String, primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String)
    content_json: Mapped[str] = mapped_column(Text)
    first_seen_at: Mapped[str] = mapped_column(String)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    model_key: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String)
    sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    license: Mapped[str | None] = mapped_column(String, nullable=True)
    license_status: Mapped[str | None] = mapped_column(String, nullable=True)
    registry_entry_json: Mapped[str] = mapped_column(Text)
    first_seen_at: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    session_token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    created_at: Mapped[str] = mapped_column(String)
    last_seen_at: Mapped[str] = mapped_column(String)
    expires_at: Mapped[str] = mapped_column(String)
    csrf_token_hash: Mapped[str] = mapped_column(String)
    user_agent_hash: Mapped[str] = mapped_column(String)


class AppFlag(Base):
    """Internal flags (e.g. the audit-purge permission checked by audit triggers)."""
    __tablename__ = "_app_flags"
    name: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[int] = mapped_column(Integer)
