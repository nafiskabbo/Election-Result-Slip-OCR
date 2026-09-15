import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import CameraCapture, { openRearCamera } from "./CameraCapture.jsx";

export default function Capture({ busy, setBusy, onDone, notify }) {
  const [packs, setPacks] = useState([]);
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

  useEffect(() => {
    api.samplePacks()
      .then((list) => setPacks((list || []).filter((pack) => pack.id !== "contest")))
      .catch((err) => notify(err.message, "fail"));
  }, []);

  useEffect(() => () => {
    pendingRef.current.forEach((item) => URL.revokeObjectURL(item.preview));
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

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
    notify("Page captured — add more or upload when the set is ready.", "info");
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
      notify(err.message || "Live camera is blocked. Using the phone camera app instead.", "warn");
      openNativeCamera();
    }
  };

  const runPack = async (packId) => {
    setBusy(true);
    setNote("Running the sample pack through enhancement and OCR…");
    try {
      const data = await api.loadPack(packId);
      notify(`${data.processed_pages_count} pages became ${data.affected_slips.length} slip${data.affected_slips.length === 1 ? "" : "s"}`, "pass");
      await onDone();
    } catch (err) {
      notify(err.message, "fail");
    } finally {
      setBusy(false);
      setNote("");
    }
  };

  return (
    <section>
      <header className="page-head">
        <div>
          <h1>Capture</h1>
          <p>
            Photograph each page so all four slip edges sit inside the frame, or drop files from a scanner or gallery.
            The desk still crops and deskews on the server, but a straight, well-lit shot reads better.
          </p>
        </div>
      </header>

      {cameraOpen && liveStream ? (
        <CameraCapture
          stream={liveStream}
          disabled={busy}
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
          <h2>Drop slips on the tray</h2>
          <p>JPEG, PNG, or PDF. Mixed batches are fine. Each page is enhanced before the numbers are read.</p>
          <div className="drop-actions">
            <button className="btn" type="button" onClick={() => galleryInputRef.current?.click()}>
              Choose files
            </button>
            <button className="btn ghost" type="button" onClick={openLiveCamera}>
              Use camera
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

      {pending.length > 0 && (
        <div className="capture-queue">
          <div className="capture-queue-head">
            <h2>{pending.length} page{pending.length === 1 ? "" : "s"} ready to upload</h2>
            <button className="btn" type="button" disabled={busy} onClick={uploadPending}>
              Upload {pending.length} page{pending.length === 1 ? "" : "s"}
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

      <div className="packs">
        {packs.map((pack) => (
          <article className="pack" key={pack.id}>
            <div>
              <h3>{pack.title}</h3>
              <p>{pack.blurb}</p>
            </div>
            <button className="btn" disabled={busy || !pack.available} onClick={() => runPack(pack.id)}>
              Load {pack.files.length} photos
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
