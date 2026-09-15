import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import CameraCapture, { openRearCamera } from "./CameraCapture.jsx";
import InfoTip from "./InfoTip.jsx";

export default function Capture({ busy, setBusy, onDone, notify, onCameraActiveChange }) {
  const [over, setOver] = useState(false);
  const [note, setNote] = useState("");
  const [cameraOpen, setCameraOpen] = useState(false);
  const [liveStream, setLiveStream] = useState(null);
  const [pending, setPending] = useState([]);
  const pendingRef = useRef(pending);
  pendingRef.current = pending;
  const streamRef = useRef(null);
  streamRef.current = liveStream;
  const galleryInputRef = useRef(null);
  const cameraInputRef = useRef(null);

  useEffect(() => () => {
    pendingRef.current.forEach((item) => URL.revokeObjectURL(item.preview));
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  useEffect(() => {
    onCameraActiveChange?.(cameraOpen && !!liveStream);
    return () => onCameraActiveChange?.(false);
  }, [cameraOpen, liveStream, onCameraActiveChange]);

  const runFiles = async (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setBusy(true);
    setNote(`Reading ${files.length} file${files.length === 1 ? "" : "s"}…`);
    try {
      const data = await api.upload(files);
      notify(`${data.processed_pages_count} pages grouped into ${data.affected_slips.length} slip${data.affected_slips.length === 1 ? "" : "s"}`, "pass");
      await onDone();
    } catch (err) {
      notify(err.message, "fail");
    } finally {
      setBusy(false);
      setNote("");
    }
  };

  const uploadPending = async () => {
    if (!pending.length) return;
    const files = pending.map((item) => item.file);
    setPending((prev) => {
      prev.forEach((item) => URL.revokeObjectURL(item.preview));
      return [];
    });
    await runFiles(files);
  };

  const addCameraPage = (file) => {
    const preview = URL.createObjectURL(file);
    setPending((prev) => [...prev, { id: `${Date.now()}-${prev.length}`, file, preview }]);
    notify("Page captured", "info");
  };

  const removePending = (id) => {
    setPending((prev) => {
      const item = prev.find((p) => p.id === id);
      if (item) URL.revokeObjectURL(item.preview);
      return prev.filter((p) => p.id !== id);
    });
  };

  const closeCamera = () => {
    if (liveStream) {
      liveStream.getTracks().forEach((track) => track.stop());
    }
    setLiveStream(null);
    setCameraOpen(false);
  };

  const openNativeCamera = () => {
    cameraInputRef.current?.click();
  };

  const openLiveCamera = async (event) => {
    event.stopPropagation();
    event.preventDefault();
    try {
      const stream = await openRearCamera();
      setLiveStream(stream);
      setCameraOpen(true);
    } catch (err) {
      notify(err.message || "Live camera blocked — opening phone camera.", "warn");
      openNativeCamera();
    }
  };

  return (
    <section className={cameraOpen && liveStream ? "capture-camera" : ""}>
      {!(cameraOpen && liveStream) && (
        <header className="page-head">
          <div className="page-title-row">
            <h1>Capture</h1>
            <InfoTip label="Capture help">
              <p>Photograph each page so the slip fills the box. Everything outside the box is dropped.</p>
              <p>JPEG, PNG, and PDF are accepted. Multi-page slips can be captured one page at a time, then uploaded together.</p>
            </InfoTip>
          </div>
        </header>
      )}

      {cameraOpen && liveStream ? (
        <CameraCapture
          stream={liveStream}
          disabled={busy}
          pageCount={pending.length}
          onCapture={addCameraPage}
          onClose={closeCamera}
          onFallback={() => {
            closeCamera();
            openNativeCamera();
          }}
        />
      ) : (
        <div
          className={`drop ${over ? "over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            runFiles(e.dataTransfer.files);
          }}
        >
          <h2>Add slips</h2>
          <div className="drop-actions">
            <button className="btn" type="button" onClick={openLiveCamera}>
              Use camera
            </button>
            <button className="btn ghost" type="button" onClick={() => galleryInputRef.current?.click()}>
              Choose files
            </button>
          </div>
          <input
            ref={galleryInputRef}
            type="file"
            multiple
            accept="image/*,.pdf,application/pdf"
            hidden
            onChange={(e) => {
              runFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <input
            ref={cameraInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            hidden
            onChange={(e) => {
              const files = Array.from(e.target.files || []);
              files.forEach(addCameraPage);
              e.target.value = "";
            }}
          />
        </div>
      )}

      {pending.length > 0 && !(cameraOpen && liveStream) && (
        <div className="capture-queue">
          <div className="capture-queue-head">
            <h2>{pending.length} page{pending.length === 1 ? "" : "s"}</h2>
            <button className="btn" type="button" disabled={busy} onClick={uploadPending}>
              Upload
            </button>
          </div>
          <ul className="capture-thumbs">
            {pending.map((item, index) => (
              <li key={item.id}>
                <img src={item.preview} alt={`Captured page ${index + 1}`} />
                <button type="button" className="btn ghost" disabled={busy} onClick={() => removePending(item.id)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {busy && <div className="progress">{note || "Working…"}</div>}
    </section>
  );
}
