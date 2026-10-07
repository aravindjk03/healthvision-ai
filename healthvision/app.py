"""Application facade: wires services for one user session. The UI talks only to this object."""

from __future__ import annotations

from typing import Any

from healthvision.config import Config
from healthvision.domain import ConsentPurpose
from healthvision.registry import ModelRegistry
from healthvision.runtime import Engines
from healthvision.services.bmi import BmiResult, BmiService
from healthvision.services.consent import ConsentService
from healthvision.services.face_analysis import FaceAnalysisResult, FaceAnalysisService
from healthvision.services.recognition import RecognitionResult, RecognitionService
from healthvision.services.report import build_report, render_pdf
from healthvision.services.store import AnalysisSession, DataStore


class HealthVisionApp:
    def __init__(self, config: Config, registry: ModelRegistry, engines: Engines, store: DataStore):
        self.config = config
        self.registry = registry
        self.engines = engines
        self.store = store
        self.consent = ConsentService(config, store)
        self.bmi = BmiService(config)
        self.faces = FaceAnalysisService(config, engines, self.consent)
        self.recognition = RecognitionService(config, engines, self.consent, self.faces, store)

    # ---- analysis sessions --------------------------------------------------------------------
    def start_analysis(self) -> AnalysisSession:
        a = AnalysisSession(config_version=self.config.version, consent_snapshot=self.consent.snapshot())
        self.store.analyses[a.session_id] = a
        self.store.current_analysis_id = a.session_id
        return a

    def current(self) -> AnalysisSession:
        return self.store.current_analysis() or self.start_analysis()

    def calculate_bmi(self, **kwargs: Any) -> BmiResult:
        self.consent.require(ConsentPurpose.BMI)
        result = self.bmi.calculate(**kwargs)
        if result.bmi is not None:
            self.current().bmi = result
        return result

    def analyze_face(self, data: bytes) -> FaceAnalysisResult:
        result = self.faces.analyze(data)
        self.current().face = result
        return result

    def verify(self, data: bytes) -> RecognitionResult:
        result = self.recognition.verify(data)
        self.current().recognition = result
        return result

    def model_versions(self) -> dict[str, str]:
        e = self.engines
        out = {"bmi": "bmi.v1 (" + self.config["bmi"]["reference"] + ")"}
        for name, eng in (("detector", e.detector), ("landmarks", e.landmarks), ("expression", e.expression),
                          ("embedding", e.embedder), ("liveness", e.liveness)):
            out[name] = eng.info().key if eng is not None else "UNAVAILABLE"
        return out

    def report(self, analysis: AnalysisSession, include_recognition: bool) -> tuple[dict[str, Any], bytes]:
        rep = build_report(analysis, include_recognition, self.model_versions(), self.consent.snapshot(),
                           self.config.version)
        pdf = render_pdf(rep)
        self.store.reports.append({"report_id": rep["report_id"], "analysis_id": analysis.session_id,
                                   "created_at": rep["created_at"], "pdf": pdf,
                                   "include_recognition": include_recognition})
        self.store.audit.record("REPORT_GENERATION", target_id=rep["report_id"],
                                include_recognition=include_recognition)
        return rep, pdf

    def delete_all(self) -> dict[str, int]:
        from healthvision.services.recognition import shred_enrollment
        counts = {"analyses": len(self.store.analyses), "reports": len(self.store.reports),
                  "recognition_events": len(self.store.recognition_events),
                  "face_templates": shred_enrollment(self.store, "USER_DELETED")}
        self.store.analyses.clear()
        self.store.reports.clear()
        self.store.recognition_events.clear()
        self.store.current_analysis_id = None
        self.store.audit.record("DATA_DELETION", scope="ALL", counts=counts)
        return counts

    def readiness_gate(self) -> dict[str, bool]:
        calibrated = self.recognition.thresholds()[2] == "calibration_file"
        return {
            "Models validated on local data": False,
            "Recognition thresholds calibrated": calibrated,
            "Bias / fairness testing performed": False,
            "False acceptance / rejection measured": False,
            "Expression performance measured": False,
            "Liveness validated": False,
            "Security tested (pen test)": False,
            "Privacy controls validated (DPIA)": False,
        }
