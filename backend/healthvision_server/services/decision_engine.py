"""DecisionEngine — pure functions converting raw scores + configured thresholds into states.
Every call returns (outcome, DecisionTrace). No model runs here (docs/03 §5)."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Optional

from ..config.settings import ExpressionCfg, FaceDetectionCfg
from ..domain.enums import (ExpressionBand, ExpressionStatus, FaceState, QualityGrade,
                            RecognitionDecision)


@dataclass
class DecisionTrace:
    rule_id: str
    inputs: dict
    thresholds: dict
    threshold_source: str
    config_version: str
    outcome: str
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def face_count(scores: list[float], cfg: FaceDetectionCfg, config_version: str) -> tuple[FaceState, list[int], DecisionTrace]:
    faces = [i for i, s in enumerate(scores) if s >= cfg.face_detection_threshold]
    secondary = [i for i, s in enumerate(scores) if s >= cfg.min_secondary_face_confidence]
    if not faces:
        state = FaceState.NO_FACE
    elif len(secondary) > 1:
        state = FaceState.MULTIPLE_FACES      # conservative: a weaker 2nd face still blocks
    else:
        state = FaceState.ONE_FACE
    tr = DecisionTrace("face_count.v1", {"scores": [round(s, 4) for s in scores]},
                       {"face_detection_threshold": cfg.face_detection_threshold,
                        "min_secondary_face_confidence": cfg.min_secondary_face_confidence},
                       "config", config_version, state.value)
    return state, faces, tr


@dataclass
class ExpressionDecision:
    status: ExpressionStatus
    label: Optional[str]
    confidence: Optional[float]
    band: Optional[ExpressionBand]
    probabilities: Optional[dict[str, float]]
    not_available_reason: Optional[str]
    trace: DecisionTrace


def expression(raw_probs: Optional[dict[str, float]], *, face_state: str, quality: Optional[str],
               stop_reason: Optional[str], cfg: ExpressionCfg, config_version: str) -> ExpressionDecision:
    thr = {"high": cfg.expression_confidence_threshold.high, "moderate": cfg.expression_confidence_threshold.moderate,
           "min_top2_margin": cfg.min_top2_margin, "temperature": cfg.temperature,
           "max_excluded_mass": cfg.max_excluded_mass}

    def na(reason: str) -> ExpressionDecision:
        tr = DecisionTrace("expression.v1", {"face_state": face_state, "quality": quality}, thr, "config",
                           config_version, ExpressionStatus.NOT_AVAILABLE.value, [reason])
        return ExpressionDecision(ExpressionStatus.NOT_AVAILABLE, None, None, None, None, reason, tr)

    if face_state != FaceState.ONE_FACE:
        return na(face_state)
    if quality == QualityGrade.POOR:
        return na("POOR_QUALITY")
    if stop_reason:
        return na(stop_reason)
    if raw_probs is None:
        return na("MODEL_UNAVAILABLE")

    # class_map + exclusion + renormalisation
    mapped: dict[str, float] = {c: 0.0 for c in cfg.classes}
    excluded = 0.0
    for label, p in raw_probs.items():
        target = cfg.class_map.get(label)
        if target is None:
            excluded += p
        elif target in mapped:
            mapped[target] += p
    total = sum(mapped.values())
    reasons: list[str] = []
    if cfg.renormalize_after_exclusion and total > 0:
        mapped = {k: v / total for k, v in mapped.items()}
    # temperature scaling on log-probabilities
    if cfg.temperature != 1.0:
        logs = {k: math.log(max(v, 1e-12)) / cfg.temperature for k, v in mapped.items()}
        m = max(logs.values())
        ex = {k: math.exp(v - m) for k, v in logs.items()}
        z = sum(ex.values())
        mapped = {k: v / z for k, v in ex.items()}
    ranked = sorted(mapped.items(), key=lambda kv: kv[1], reverse=True)
    (top1, p1), (_, p2) = ranked[0], ranked[1]
    inputs = {"raw": {k: round(v, 5) for k, v in raw_probs.items()}, "excluded_mass": round(excluded, 5),
              "quality": quality, "top1": top1, "top1_prob": round(p1, 5), "top2_prob": round(p2, 5)}
    probs = {k: round(v, 4) for k, v in ranked}

    if excluded > cfg.max_excluded_mass:
        reasons.append("EXCLUDED_MASS_TOO_HIGH")
    if p1 < cfg.expression_confidence_threshold.moderate:
        reasons.append("LOW_CONFIDENCE")
    if (p1 - p2) < cfg.min_top2_margin:
        reasons.append("SMALL_MARGIN")
    if reasons:
        tr = DecisionTrace("expression.v1", inputs, thr, "config", config_version, ExpressionStatus.UNCERTAIN.value, reasons)
        return ExpressionDecision(ExpressionStatus.UNCERTAIN, None, round(p1, 4), None, probs, None, tr)

    band = ExpressionBand.HIGH if p1 >= cfg.expression_confidence_threshold.high else ExpressionBand.MODERATE
    if quality == QualityGrade.ACCEPTABLE and band == ExpressionBand.HIGH:
        band = ExpressionBand.MODERATE
        reasons.append("BAND_CAPPED_BY_ACCEPTABLE_QUALITY")
    tr = DecisionTrace("expression.v1", inputs, thr, "config", config_version, ExpressionStatus.ESTIMATED.value, reasons)
    return ExpressionDecision(ExpressionStatus.ESTIMATED, top1, round(p1, 4), band, probs, None, tr)


def recognition(best_similarity: float, t_match: float, t_nomatch: float, source: str,
                config_version: str, n_templates: int) -> tuple[RecognitionDecision, DecisionTrace]:
    if best_similarity >= t_match:
        d = RecognitionDecision.MATCH
    elif best_similarity < t_nomatch:
        d = RecognitionDecision.NO_MATCH
    else:
        d = RecognitionDecision.UNCERTAIN
    reasons = ["DEMO_UNCALIBRATED"] if source == "demo_uncalibrated" else []
    tr = DecisionTrace("recognition.v1", {"best_similarity": round(best_similarity, 5), "templates_compared": n_templates},
                       {"match": t_match, "no_match": t_nomatch}, source, config_version, d.value, reasons)
    return d, tr
