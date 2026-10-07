import { useCallback, useEffect, useRef, useState } from "react";

export interface Captured { blob: Blob; url: string; captureMs: number }

interface Props {
  onCapture: (c: Captured) => void;
  captureLabel?: string;
  disabled?: boolean;
}

/** Camera (getUserMedia) or file upload. Live preview stays in the browser for framing
 *  guidance only; nothing is sent until the user presses CAPTURE / chooses a file. */
export default function CameraCapture({ onCapture, captureLabel = "Capture", disabled }: Props) {
  const [mode, setMode] = useState<"camera" | "upload">("camera");
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setReady(false);
  }, []);

  useEffect(() => {
    if (mode !== "camera") { stop(); return; }
    let cancelled = false;
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Camera is not available in this browser. Use Upload instead.");
      return;
    }
    navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" }, audio: false })
      .then((s) => {
        if (cancelled) { s.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = s;
        if (videoRef.current) { videoRef.current.srcObject = s; videoRef.current.play().catch(() => undefined); }
      })
      .catch(() => setError("Camera permission was denied or no camera was found. Use Upload instead."));
    return () => { cancelled = true; stop(); };
  }, [mode, stop]);

  const capture = () => {
    const v = videoRef.current;
    if (!v || !v.videoWidth) return;
    const t0 = performance.now();
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    const ctx = canvas.getContext("2d")!;
    // un-mirror: the preview is mirrored for comfort, the captured image is not
    ctx.drawImage(v, 0, 0);
    canvas.toBlob((b) => {
      if (b) onCapture({ blob: b, url: URL.createObjectURL(b), captureMs: Math.round(performance.now() - t0) });
    }, "image/jpeg", 0.92);
  };

  const onFile = (f: File | undefined) => {
    if (!f) return;
    if (!/^image\/(jpeg|png)$/.test(f.type)) { setError("Please choose a JPEG or PNG image."); return; }
    setError(null);
    onCapture({ blob: f, url: URL.createObjectURL(f), captureMs: 0 });
  };

  return (
    <div className="capture">
      <div className="seg" role="tablist">
        <button role="tab" aria-selected={mode === "camera"} className={mode === "camera" ? "on" : ""} onClick={() => setMode("camera")}>Camera</button>
        <button role="tab" aria-selected={mode === "upload"} className={mode === "upload" ? "on" : ""} onClick={() => setMode("upload")}>Upload</button>
      </div>
      {mode === "camera" ? (
        <div className="viewfinder">
          <video ref={videoRef} muted playsInline className="mirror" aria-label="Camera preview"
            onPlaying={() => setReady(true)} />
          <svg className="oval" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
            <ellipse cx="50" cy="48" rx="19" ry="33" />
          </svg>
          <div className="guide">Position one face inside the frame.</div>
        </div>
      ) : (
        <label className="dropzone">
          <input type="file" accept="image/jpeg,image/png" onChange={(e) => onFile(e.target.files?.[0])} />
          <span>Choose a JPEG or PNG photo (max 10 MB)</span>
          <span className="muted small">Position one face inside the frame. The photo is analysed on this device and not stored.</span>
        </label>
      )}
      {error && <div className="error">{error}</div>}
      {mode === "camera" && (
        <button className="btn primary" onClick={capture} disabled={!ready || disabled}>{captureLabel}</button>
      )}
    </div>
  );
}
