// Thin API client: same-origin cookies, CSRF double-submit header, error envelope.

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;
  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function csrf(): string {
  const m = document.cookie.match(/(?:^|; )hv_csrf=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function request<T>(method: string, path: string, body?: unknown, extraHeaders: Record<string, string> = {}): Promise<T> {
  const headers: Record<string, string> = { ...extraHeaders };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (method !== "GET") headers["X-CSRF-Token"] = csrf();
  const res = await fetch(`/api/v1${path}`, { method, headers, body: payload, credentials: "same-origin" });
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) {
    const e = data?.error ?? {};
    throw new ApiError(res.status, e.code ?? "ERROR", e.message ?? `Request failed (${res.status})`, e.details ?? {});
  }
  return data as T;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, b?: unknown, h?: Record<string, string>) => request<T>("POST", p, b, h),
  patch: <T>(p: string, b?: unknown) => request<T>("PATCH", p, b),
  del: <T>(p: string) => request<T>("DELETE", p),
};

// ---- types (mirror docs/11) ----
export interface User { user_id: string; username: string; display_name: string; role: "USER" | "ADMINISTRATOR" }

export interface ConsentRow { purpose: Purpose; status: string; granted: boolean; since: string | null; policy_version: string | null; reprompt: boolean }
export type Purpose = "BMI" | "FACE_ANALYSIS" | "RECOGNITION";
export interface Notice { text: string; sha256: string; policy_version: string }
export interface ConsentState { consents: ConsentRow[]; notices: Record<Purpose, Notice>; policy_version: string }

export interface BmiResult {
  status: "VALID" | "INVALID_INPUT" | "NOT_APPLICABLE";
  bmi: number | null; bmi_display: string | null;
  category_code?: string | null; category_label?: string | null;
  calculation?: string; reference: { code: string; citation: string; version: string };
  warnings?: string[]; limitation: string; message?: string; guidance?: string | null;
  errors?: { field: string; code: string; message: string }[];
  action_points?: { value: number; label: string }[];
}

export interface QualityCheck { check: string; grade: "GOOD" | "ACCEPTABLE" | "POOR"; value: unknown; detail: string }
export interface Face { face_index: number; bbox: { x: number; y: number; w: number; h: number }; detection_confidence: number }

export interface ExpressionResult {
  status: "ESTIMATED" | "UNCERTAIN" | "NOT_AVAILABLE";
  expression: string | null; expression_label: string | null; display: string; context: string | null;
  probability_labels: Record<string, string>; confidence: number | null; confidence_label: string;
  confidence_band: "HIGH" | "MODERATE" | null; probabilities: Record<string, number> | null;
  observation: string | null; note: string; not_available_reason: string | null;
  model: { model_id: string; version: string };
  trace: { rule_id: string; thresholds: Record<string, number>; config_version: string; reasons: string[] };
}

export interface FaceAnalysis {
  session_id: string; observation_id: string; result_id: string;
  face: { face_state: string; face_count: number; faces: Face[] };
  quality: { grade: string; action: string; checks: QualityCheck[] } | null;
  pose: { yaw: number; pitch: number; roll: number } | null;
  landmarks: { detected: boolean; visibility: number | null; scheme: string | null; points?: number[][] };
  expression: ExpressionResult; message: string | null; models: Record<string, string>;
  config_version: string; latency_ms: Record<string, number>;
}

export interface VerifyResult {
  event_id: string; session_id: string; mode: string;
  decision: "MATCH" | "NO_MATCH" | "UNCERTAIN" | "NOT_PERFORMED";
  not_performed_reason: string | null; similarity: number | null;
  thresholds: { match: number; no_match: number; source: string };
  demo_uncalibrated: boolean; demo_banner: string | null; liveness: string; liveness_notice: string;
  quality: string | null; message: string; model_version: string; config_version: string;
  latency_ms: Record<string, number>;
}

export interface Dashboard {
  analysis_id: string; started_at: string; completed_at: string | null;
  calculated: { bmi: BmiResult | null };
  ai_estimates: {
    face: { face_state: string; face_count: number; faces: Face[]; pose: { yaw: number; pitch: number; roll: number } | null } | null;
    quality: { grade: string; checks: QualityCheck[] } | null;
    expression: ExpressionResult | null;
  };
  identity: { recognition: Omit<VerifyResult, "event_id" | "session_id" | "latency_ms"> | null };
  model_versions: Record<string, string>; config_version: string;
  latency_ms: Record<string, Record<string, number>>; notes: string[];
}

export interface ModelInfo {
  models: { model_id: string; model_type: string; name: string; version: string; license: string; license_status: string;
    status: string; reason: string | null; local_validation: string; known_limitations: string[]; warmup_ms: number | null }[];
  recognition_calibration: { state: string; file: string | null };
  liveness: { state: string }; fairness: string; keystore: { available: boolean; reason: string | null };
  config_version: string; production_readiness_gate: string;
  production_readiness_items: { id: string; criterion: string; status: string; reason: string | null }[];
}
