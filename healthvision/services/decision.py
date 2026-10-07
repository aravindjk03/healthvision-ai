"""DecisionEngine — pure functions turning raw scores + config thresholds into states (docs/03 §5)."""

from __future__ import annotations

import math
from dataclasses import dataclass

from healthvision.config import Config
from healthvision.domain import (
    ConfidenceBand, DecisionTrace, ExpressionStatus, FaceDetection, FaceState, QualityGrade,
    RecognitionDecision,
)


def face_count(detections: list[FaceDetection], config: Config) -> tuple[FaceState, list[FaceDetection], DecisionTrace]:
    cfg = config["face_detection"]
    primary = [d for d in detections if d.score >= cfg["face_detection_threshold"]]
    secondary = [d for d in detections if d.score >= cfg["min_secondary_face_confidence"]]
    if not primary:
        state = FaceState.NO_FACE
    elif len(secondary) > 1:
        state = FaceState.MULTIPLE_FACES
    else:
        state = FaceState.ONE_FACE
    trace = DecisionTrace(
        rule_id="face_count.v1",
        inputs={"scores": [round(d.score, 4) for d in detections]},
        thresholds={"face_detection_threshold": cfg["face_detection_threshold"],
                    "min_secondary_face_confidence": cfg["min_secondary_face_confidence"]},
        threshold_source="config",
        config_version=config.version,
        outcome=str(state),
    )
    return state, (secondary if state == FaceState.MULTIPLE_FACES else primary), trace


@dataclass
class ExpressionDecision:
    status: ExpressionStatus
    label: str | None
    confidence: float | None
    band: ConfidenceBand | None
    probabilities: dict[str, float]
    trace: DecisionTrace


def expression(raw_probs: dict[str, float], quality: QualityGrade, config: Config) -> ExpressionDecision:
    cfg = config["expression"]
    thr = cfg["expression_confidence_threshold"]
    allowed = set(cfg["classes"])
    mapped: dict[str, float] = {}
    excluded = 0.0
    for label, p in raw_probs.items():
        target = cfg["class_map"].get(label)
        if target is None or target not in allowed:
            excluded += p
            continue
        mapped[target] = mapped.get(target, 0.0) + p
    total = sum(mapped.values())
    if cfg["renormalize_after_exclusion"] and total > 0:
        mapped = {k: v / total for k, v in mapped.items()}
    temperature = float(cfg["temperature"])
    if temperature != 1.0 and mapped:
        logits = {k: math.log(max(v, 1e-12)) / temperature for k, v in mapped.items()}
        peak = max(logits.values())
        expd = {k: math.exp(v - peak) for k, v in logits.items()}
        s = sum(expd.values())
        mapped = {k: v / s for k, v in expd.items()}
    probs = dict(sorted(mapped.items(), key=lambda kv: kv[1], reverse=True))
    ranked = list(probs.items())
    reasons: list[str] = []
    thresholds = {"high": thr["high"], "moderate": thr["moderate"], "min_top2_margin": cfg["min_top2_margin"],
                  "temperature": temperature, "max_excluded_mass": cfg["max_excluded_mass"]}

    status, label, conf, band = ExpressionStatus.UNCERTAIN, None, None, None
    if not ranked:
        reasons.append("no configured classes")
    else:
        top_label, top_p = ranked[0]
        second_p = ranked[1][1] if len(ranked) > 1 else 0.0
        conf = top_p
        if excluded > cfg["max_excluded_mass"]:
            reasons.append(f"excluded-class mass {excluded:.2f} above limit")
        elif top_p < thr["moderate"]:
            reasons.append(f"top probability {top_p:.2f} below moderate threshold")
        elif top_p - second_p < cfg["min_top2_margin"]:
            reasons.append(f"margin {top_p - second_p:.2f} below min_top2_margin")
        else:
            status, label = ExpressionStatus.ESTIMATED, top_label
            band = ConfidenceBand.HIGH if top_p >= thr["high"] else ConfidenceBand.MODERATE
            if quality == QualityGrade.ACCEPTABLE and band == ConfidenceBand.HIGH:
                band = ConfidenceBand.MODERATE
                reasons.append("quality ACCEPTABLE caps band at MODERATE")
    trace = DecisionTrace(
        rule_id="expression.v1",
        inputs={"raw_probabilities": {k: round(v, 4) for k, v in raw_probs.items()},
                "excluded_mass": round(excluded, 4), "quality": str(quality)},
        thresholds=thresholds,
        threshold_source="config",
        config_version=config.version,
        outcome=f"{status}" + (f":{label}:{band}" if label else ""),
        reasons=reasons,
    )
    return ExpressionDecision(status, label, conf, band, probs, trace)


def recognition(best_similarity: float, t_match: float, t_no_match: float, threshold_source: str,
                config: Config) -> tuple[RecognitionDecision, DecisionTrace]:
    if best_similarity >= t_match:
        decision = RecognitionDecision.MATCH
    elif best_similarity < t_no_match:
        decision = RecognitionDecision.NO_MATCH
    else:
        decision = RecognitionDecision.UNCERTAIN
    trace = DecisionTrace(
        rule_id="recognition.v1",
        inputs={"best_similarity": round(best_similarity, 4)},
        thresholds={"recognition_threshold": t_match, "no_match_threshold": t_no_match},
        threshold_source=threshold_source,
        config_version=config.version,
        outcome=str(decision),
        reasons=["DEMO_UNCALIBRATED"] if threshold_source == "demo_uncalibrated" else [],
    )
    return decision, trace
