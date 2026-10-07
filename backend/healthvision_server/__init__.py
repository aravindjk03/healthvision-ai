"""HealthVision AI V1 backend."""
import os

# NFR-1 (local-first, nothing leaves the device): ONNX Runtime ≥ 1.2x ships usage telemetry
# that phones home. Disable it before onnxruntime is imported anywhere in the process.
os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")
