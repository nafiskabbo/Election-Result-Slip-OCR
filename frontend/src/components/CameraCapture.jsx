import { useCallback, useEffect, useRef, useState } from "react";
import InfoTip from "./InfoTip.jsx";

export async function openRearCamera() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Camera API is not available in this browser.");
  }
  const attempts = [
    {
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: 1920 },
        height: { ideal: 1080 },
      },
      audio: false,
    },
    { video: { facingMode: { ideal: "environment" } }, audio: false },
    { video: { facingMode: "environment" }, audio: false },
    { video: true, audio: false },
  ];
  let lastError;
  for (const constraints of attempts) {
    try {
      return await navigator.mediaDevices.getUserMedia(constraints);
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError || new Error("Could not open the camera.");
}

function blobToJpegFile(blob) {
  const name = `slip-${Date.now()}.jpg`;
  try {
    return new File([blob], name, { type: "image/jpeg", lastModified: Date.now() });
  } catch {
    return blob;
  }
}

function canvasToJpegFile(canvas) {
  return new Promise((resolve, reject) => {
    if (canvas.toBlob) {
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            reject(new Error("Could not capture the frame."));
            return;
          }
          resolve(blobToJpegFile(blob));
        },
        "image/jpeg",
        0.92,
      );
      return;
    }
    const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
    fetch(dataUrl)
      .then((res) => res.blob())
      .then((blob) => resolve(blobToJpegFile(blob)))
      .catch(reject);
  });
}

export default function CameraCapture({ stream, disabled, pageCount = 0, onCapture, onClose, onFallback }) {
  const videoRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [flash, setFlash] = useState(false);
  const capturingRef = useRef(false);

  const stopTracks = useCallback(() => {
    if (stream && typeof stream.getTracks === "function") {
      stream.getTracks().forEach((track) => track.stop());
    }
  }, [stream]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !stream) return undefined;

    video.setAttribute("playsinline", "true");
    video.setAttribute("webkit-playsinline", "true");
    video.muted = true;
    video.autoplay = true;
    video.srcObject = stream;

    const markReady = () => {
      if (video.videoWidth > 0) setReady(true);
    };

    const start = async () => {
      setError("");
      setReady(false);
      try {
        await video.play();
        markReady();
      } catch (err) {
        setError(err.message || "Could not start the camera preview.");
      }
    };

    video.addEventListener("loadedmetadata", markReady);
    start();
    return () => {
      video.removeEventListener("loadedmetadata", markReady);
      video.srcObject = null;
    };
  }, [stream]);

  const snap = useCallback(async () => {
    const video = videoRef.current;
    if (!video || !ready || capturingRef.current || disabled) return null;
    capturingRef.current = true;
    try {
      const w = video.videoWidth;
      const h = video.videoHeight;
      if (!w || !h) return null;
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      ctx.drawImage(video, 0, 0, w, h);
      return await canvasToJpegFile(canvas);
    } finally {
      capturingRef.current = false;
    }
  }, [ready, disabled]);

  const handleManualCapture = async () => {
    try {
      const file = await snap();
      if (!file) return;
      setFlash(true);
      window.setTimeout(() => setFlash(false), 160);
      onCapture(file);
    } catch (err) {
      setError(err.message || "Capture failed.");
    }
  };

  const handleClose = () => {
    stopTracks();
    onClose();
  };

  let status = ready ? "Ready" : "Starting…";
  if (error) status = error;

  return (
    <div className="camera-shell">
      <div className="camera-viewport">
        <video
          ref={videoRef}
          className="camera-video"
          autoPlay
          muted
          playsInline
        />
        <div className={`camera-overlay ${flash ? "flash" : ""}`} aria-hidden="true">
          <div className="camera-frame">
            <span className="camera-corner camera-corner-tl" />
            <span className="camera-corner camera-corner-tr" />
            <span className="camera-corner camera-corner-bl" />
            <span className="camera-corner camera-corner-br" />
          </div>
        </div>
        <div className="camera-status">
          <span className={error ? "fail" : ""}>{status}</span>
          {pageCount > 0 && <span className="camera-count">{pageCount} captured</span>}
        </div>
      </div>

      <div className="camera-toolbar">
        <button type="button" className="btn ghost camera-side" onClick={handleClose} disabled={disabled}>
          Close
        </button>

        <button
          type="button"
          className="camera-shutter"
          aria-label="Capture page"
          onClick={handleManualCapture}
          disabled={!ready || disabled}
        />

        <div className="camera-side camera-side-right">
          <InfoTip label="Camera tips" align="end">
            <p>Fit all four edges of the slip inside the brackets.</p>
            <p>Hold steady, avoid glare, and capture each page before uploading.</p>
          </InfoTip>
          {onFallback && (
            <button type="button" className="btn ghost" onClick={onFallback} disabled={disabled}>
              App
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
