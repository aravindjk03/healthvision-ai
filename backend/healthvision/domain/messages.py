"""User-facing message catalogue (docs/01 §6). All result wording comes from here so
the wording lint has one place to check."""

EXPRESSION_LABEL = "Facial expression estimate: {label}"
EXPRESSION_OBSERVATION = "Visible facial expression is consistent with a {cls}-expression classification."
EXPRESSION_UNCERTAIN = "Expression could not be estimated reliably from this image."
EXPRESSION_NOTE = (
    "Facial expression is an AI estimate based on visible facial features and should not be "
    "interpreted as a definitive measure of emotional state."
)
CONFIDENCE_LABEL = "model confidence (not a probability of emotion)"
BMI_NOTE = "BMI is a screening measure and does not constitute a medical diagnosis."
BMI_LIMITATION = (
    "BMI is a screening measure and does not constitute a medical diagnosis. It does not "
    "distinguish fat from muscle mass and does not account for body-fat distribution."
)
BMI_PEDIATRIC = (
    "Adult BMI categories do not apply under 18. Pediatric assessment uses BMI-for-age "
    "percentiles (WHO/CDC growth references), which this version does not provide."
)
BMI_ASSUME_ADULT = "Categories assume an adult (18+)."
BMI_PLAUSIBILITY = "Please check the entered values."
NO_FACE = "No face detected. Please retake the image."
MULTIPLE_FACES = "Multiple faces detected. Please ensure only one person is in frame."
POOR_QUALITY = "Image quality too low: {reasons}. Please retake."
ALIGNMENT_FAILED = "Could not align the face. Please face the camera."
MODEL_UNAVAILABLE = "Expression analysis is unavailable on this device."
RECOGNITION_NOTICE = "Facial recognition uses biometric information to verify or identify an enrolled person."
LIVENESS = "Liveness detection is not implemented in this version."
LIVENESS_FULL = (
    "Liveness detection is not implemented in this version. Verification can be fooled by "
    "photos or screens. Do not use for security decisions."
)
DEMO_UNCALIBRATED = "Demo mode — recognition threshold not calibrated on validation data"
DASHBOARD_FOOTER = (
    "These outputs are separate measurements and should not be interpreted as a medical "
    "diagnosis or definitive emotional state."
)
VERIFY_MESSAGES = {
    "MATCH": "Verified — matches your enrolled identity",
    "NO_MATCH": "Not verified — does not match your enrolled identity",
    "UNCERTAIN": "Uncertain — the result is borderline. Please retry with better lighting, facing the camera.",
    "NOT_PERFORMED": "Verification was not performed: {reason}",
}
POSITIONING = (
    "HealthVision AI automates BMI calculation, estimates visible facial expressions, and can "
    "verify an enrolled identity — each as a separate, explainable measurement, subject to consent."
)

# Consent notices (their SHA-256 is stored with each consent row).
CONSENT_NOTICES = {
    "BMI": (
        "BMI calculation uses the height, weight and optional age/sex you enter. Results are "
        "stored for {days} days so you can see your history. BMI is a screening measure and "
        "does not constitute a medical diagnosis."
    ),
    "FACE_ANALYSIS": (
        "Facial expression analysis processes a photo you capture or upload, on this device only. "
        "The photo is not stored; only the derived results (face detected, image quality, "
        "expression estimate) are kept for {days} days. Facial expression is an AI estimate and "
        "not a measure of how you feel."
    ),
    "RECOGNITION": (
        "Facial recognition uses biometric information to verify or identify an enrolled person.\n"
        "• Purpose: verify that you are the person who enrolled on this device.\n"
        "• What is stored: an encrypted face template (a list of numbers), not your photo.\n"
        "• How long: until you revoke this permission or delete your data.\n"
        "• Liveness detection is not implemented in this version.\n"
        "• You can keep using BMI and expression analysis without allowing this."
    ),
}
