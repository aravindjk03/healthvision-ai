"""User-facing message catalogue (docs/01 §6). All result wording comes from here so
the wording lint has one place to check."""

EXPRESSION_LABEL = "Facial expression estimate: {label}"
EXPRESSION_OBSERVATION = "The face in this photo shows {desc}."
EXPRESSION_UNCERTAIN = (
    "We need a clearer view to estimate the expression — try facing the camera in soft, even light."
)
EXPRESSION_NOTE = (
    "This is an AI estimate of the visible facial expression in one photo. It describes the face "
    "at that moment, not how you feel inside."
)
CONFIDENCE_LABEL = "model confidence in the visible expression"

# Positive, faithful display wording. Internal classes (HAPPY, SAD, …) stay unchanged for
# traceability; what the user sees describes the visible facial features, which is what the
# model actually measures, in calm, non-judgmental language.
EXPRESSION_DISPLAY = {
    "HAPPY": "Smiling",
    "NEUTRAL": "Calm / neutral",
    "SURPRISED": "Surprised",
    "SAD": "Downcast",
    "ANGRY": "Frowning",
    "FEARFUL": "Wide-eyed",
    "DISGUSTED": "Nose wrinkled",
}
EXPRESSION_DESCRIPTION = {
    "HAPPY": "a warm smile",
    "NEUTRAL": "a calm, relaxed expression",
    "SURPRISED": "raised brows and an open expression",
    "SAD": "a softer, downturned expression",
    "ANGRY": "lowered, drawn-together brows",
    "FEARFUL": "widened eyes",
    "DISGUSTED": "a wrinkled nose",
}
EXPRESSION_CONTEXT_POSITIVE = "A lovely, bright expression in this photo."
EXPRESSION_CONTEXT_STEADY = "A calm, steady expression in this photo."
EXPRESSION_CONTEXT_MOMENT = (
    "Faces change from moment to moment — this captures just one instant, and it says nothing "
    "about who you are or how your day is going. Feel free to take another photo anytime."
)
EXPRESSION_CONTEXT = {
    "HAPPY": EXPRESSION_CONTEXT_POSITIVE,
    "NEUTRAL": EXPRESSION_CONTEXT_STEADY,
    "SURPRISED": "An open, attentive expression in this photo.",
    "SAD": EXPRESSION_CONTEXT_MOMENT,
    "ANGRY": EXPRESSION_CONTEXT_MOMENT,
    "FEARFUL": EXPRESSION_CONTEXT_MOMENT,
    "DISGUSTED": EXPRESSION_CONTEXT_MOMENT,
}

BMI_NOTE = "BMI is a helpful screening number; a healthcare professional can put it in full context for you."
BMI_LIMITATION = (
    "BMI is a screening measure, not a medical diagnosis. It works best alongside other measures, "
    "because it does not separate muscle from fat or show where body fat is carried."
)
# Encouraging, factual context per WHO adult category. No medical advice, no judgement.
BMI_GUIDANCE = {
    "UNDERWEIGHT": "Your BMI is below the WHO adult normal range. A healthcare professional can help you "
                   "understand what this means for you.",
    "NORMAL": "Great — your BMI is within the WHO adult normal range.",
    "OVERWEIGHT": "Your BMI is a little above the WHO adult normal range. BMI is only one number — a "
                  "healthcare professional can help you see the full picture.",
    "OBESE_I": "Your BMI is above the WHO adult normal range. BMI is only one number — a healthcare "
               "professional can help you see the full picture and any next steps.",
    "OBESE_II": "Your BMI is above the WHO adult normal range. BMI is only one number — a healthcare "
                "professional can help you see the full picture and any next steps.",
    "OBESE_III": "Your BMI is above the WHO adult normal range. BMI is only one number — a healthcare "
                 "professional can help you see the full picture and any next steps.",
}
BMI_PEDIATRIC = (
    "For people under 18, BMI is read using age-specific growth charts (WHO/CDC BMI-for-age "
    "percentiles), so adult categories are not shown. This version shows the number only."
)
BMI_ASSUME_ADULT = "Categories assume an adult (18+)."
BMI_PLAUSIBILITY = "Please double-check the entered values."
NO_FACE = "Let's try again — make sure your face is inside the frame."
MULTIPLE_FACES = "Multiple faces detected. Please make sure only one person is in the frame."
POOR_QUALITY = "Almost there — {reasons}. Please retake the photo."
ALIGNMENT_FAILED = "Nearly there — please face the camera directly and retake."
MODEL_UNAVAILABLE = "Expression analysis is unavailable on this device."
RECOGNITION_NOTICE = "Facial recognition uses biometric information to verify or identify an enrolled person."
LIVENESS = "Liveness detection is not implemented in this version."
LIVENESS_FULL = (
    "Liveness detection is not implemented in this version. Verification can be fooled by "
    "photos or screens. Do not use for security decisions."
)
DEMO_UNCALIBRATED = "Demo mode — recognition threshold not calibrated on validation data"
DASHBOARD_FOOTER = (
    "These are separate measurements to help you reflect — not a medical diagnosis or a reading "
    "of how you feel."
)
VERIFY_MESSAGES = {
    "MATCH": "Verified — matches your enrolled identity",
    "NO_MATCH": "Not verified — this photo does not match your enrolled identity",
    "UNCERTAIN": "Almost — the result is borderline. Please retry facing the camera in good light.",
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
