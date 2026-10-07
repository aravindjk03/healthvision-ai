# HealthVision AI: browser-only version

A single-page version of HealthVision AI that runs **entirely in the browser**. It uses the same four
model files as the full app (YuNet, MediaPipe Face Landmarker, FER+, SFace), executed with
ONNX Runtime Web and MediaPipe Tasks. No server, and photos never leave the device.

It supports photo upload (no live camera), BMI, face analysis, enroll + verify (templates kept in
tab memory only) and a dashboard. It has no accounts, history, reports or audit log; use the full
app for those.

Build: `npm install && python build.py` → `dist/`. Model files are split into base64 text parts,
which the page re-joins byte-for-byte, because the hosting it was built for serves only web file types.
