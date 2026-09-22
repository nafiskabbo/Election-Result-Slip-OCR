import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { formatDuration } from "../time.js";
import CameraCapture, { openRearCamera } from "./CameraCapture.jsx";
import InfoTip from "./InfoTip.jsx";
import ProcessingProgress, { initialProcess, progressFromEvent } from "./ProcessingProgress.jsx";

function buildPendingItem(file, index = 0) {
  return {
    id: `${Date.now()}-${index}-${Math.random().toString(36).slice(2, 7)}`,
    file,
    preview: URL.createObjectURL(file),
  };
}

function summarizeUpload(data) {
  const pages = data?.pages || [];
  const bySlip = new Map();

  for (const page of pages) {
    const grouping = page.grouping || {};
    const slipId = grouping.slip_id || page.slip_id;
    if (!slipId) continue;

    const missing = Array.isArray(grouping.missing_pages) ? grouping.missing_pages : [];
    const expected = grouping.expected_pages || page.page_total || 1;
    const received = Array.isArray(grouping.received_pages)
      ? grouping.received_pages
      : [page.page_number].filter(Boolean);

    const prior = bySlip.get(slipId);
    if (!prior) {
      bySlip.set(slipId, {
        slipId,
        ballotType: page.ballot_type || "",
        barcode: page.barcode_text || "",
        expected,
        received: [...new Set(received)].sort((a, b) => a - b),
        missing: [...missing].sort((a, b) => a - b),
        isComplete: Boolean(grouping.is_complete),
        status: grouping.status || "",
        pages: [page],
      });
      continue;
    }

    prior.pages.push(page);
    prior.expected = Math.max(prior.expected || 0, expected || 0);
    prior.received = [...new Set([...prior.received, ...received])].sort((a, b) => a - b);
    prior.missing = [...missing].sort((a, b) => a - b);
    prior.isComplete = Boolean(grouping.is_complete);
    prior.status = grouping.status || prior.status;
    if (page.barcode_text) prior.barcode = page.barcode_text;
    if (page.ballot_type) prior.ballotType = page.ballot_type;
  }

  const slips = [...bySlip.values()];
  const nextPrompts = slips
    .filter((slip) => !slip.isComplete && slip.missing.length > 0 && slip.expected > 1)
    .map((slip) => ({
      ...slip,
      nextPage: slip.missing[0],
    }));

  return {
    pageCount: pages.length,
    slipCount: slips.length,
    pages,
    slips,
    nextPrompts,
  };
}

export default function Capture({
  busy,
  setBusy,
  onDone,
  notify,
  onCameraActiveChange,
  registerCloseCamera,
}) {
  const [over, setOver] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [liveStream, setLiveStream] = useState(null);
  const [pending, setPending] = useState([]);
  const [process, setProcess] = useState(null);
  const [lastResult, setLastResult] = useState(null);
  const [scanPrompt, setScanPrompt] = useState(null);
  const pendingRef = useRef(pending);
  pendingRef.current = pending;
  const streamRef = useRef(null);
  streamRef.current = liveStream;
  const galleryInputRef = useRef(null);
  const cameraInputRef = useRef(null);
  const nextPageFileRef = useRef(null);
  const pushedCameraRef = useRef(false);
  const autoProcessRef = useRef(false);
  const promptQueueRef = useRef([]);

  useEffect(() => () => {
    pendingRef.current.forEach((item) => URL.revokeObjectURL(item.preview));
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  useEffect(() => {
    onCameraActiveChange?.(cameraOpen && !!liveStream);
    return () => onCameraActiveChange?.(false);
  }, [cameraOpen, liveStream, onCameraActiveChange]);

  const closeCamera = ({ fromHistory = false } = {}) => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
    }
    setLiveStream(null);
    setCameraOpen(false);
    if (!fromHistory && pushedCameraRef.current) {
      pushedCameraRef.current = false;
      window.history.back();
    } else {
      pushedCameraRef.current = false;
    }
  };

  useEffect(() => {
    registerCloseCamera?.(closeCamera);
    return () => registerCloseCamera?.(null);
  });

  useEffect(() => {
    if (!(cameraOpen && liveStream)) return undefined;
    window.history.pushState({ camera: true, page: "capture" }, "");
    pushedCameraRef.current = true;
    const onPop = () => {
      pushedCameraRef.current = false;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      setLiveStream(null);
      setCameraOpen(false);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [cameraOpen, liveStream]);

  const finishCapture = async () => {
    setScanPrompt(null);
    promptQueueRef.current = [];
    setLastResult(null);
    setProcess(null);
    await onDone();
  };

  const handleUploadResult = (data) => {
    const summary = summarizeUpload(data);
    setLastResult(summary);

    const pages = summary.pageCount;
    const slips = summary.slipCount;
    const duration = data.total_elapsed_seconds != null
      ? ` · ${formatDuration(data.total_elapsed_seconds)}`
      : "";
    notify(
      `${pages} page${pages === 1 ? "" : "s"} grouped into ${slips} slip${slips === 1 ? "" : "s"}${duration}`,
      "pass",
    );

    const touched = new Set(summary.slips.map((slip) => slip.slipId));
    const kept = promptQueueRef.current.filter((item) => !touched.has(item.slipId));
    const next = [...summary.nextPrompts, ...kept];
    promptQueueRef.current = next;
    setScanPrompt(next[0] || null);

    return summary;
  };

  const runFiles = async (fileList, { stayOnCapture = false } = {}) => {
    const files = Array.from(fileList || []);
    if (!files.length) return null;
    setBusy(true);
    setProcess(initialProcess(files.length));
    setScanPrompt(null);
    try {
      const data = await api.upload(files, {
        onProgress: (event) => setProcess((prev) => progressFromEvent(event, prev)),
      });
      const summary = handleUploadResult(data);
      if (!summary.nextPrompts.length && !stayOnCapture) {
        await new Promise((resolve) => window.setTimeout(resolve, 900));
        await finishCapture();
      }
      return summary;
    } catch (err) {
      notify(err.message, "fail");
      setProcess((prev) => (prev ? {
        ...prev,
        failed: true,
        endedAt: prev.endedAt || new Date().toISOString(),
        message: err.message,
        remainingSeconds: 0,
      } : prev));
      return null;
    } finally {
      setBusy(false);
    }
  };

  const queueFiles = (fileList, { message } = {}) => {
    const files = Array.from(fileList || []).filter(Boolean);
    if (!files.length) return;
    setPending((prev) => [
      ...prev,
      ...files.map((file, index) => buildPendingItem(file, prev.length + index)),
    ]);
    notify(
      message
        || (files.length === 1 ? "Page added" : `${files.length} pages added`),
      "info",
    );
  };

  const uploadPending = async () => {
    if (!pending.length) return;
    const files = pending.map((item) => item.file);
    setPending((prev) => {
      prev.forEach((item) => URL.revokeObjectURL(item.preview));
      return [];
    });
    await runFiles(files, { stayOnCapture: true });
  };

  const addCameraPage = async (file) => {
    if (autoProcessRef.current || scanPrompt) {
      closeCamera({ fromHistory: false });
      autoProcessRef.current = false;
      await runFiles([file], { stayOnCapture: true });
      return;
    }
    queueFiles([file], { message: "Page captured" });
  };

  const removePending = (id) => {
    setPending((prev) => {
      const item = prev.find((p) => p.id === id);
      if (item) URL.revokeObjectURL(item.preview);
      return prev.filter((p) => p.id !== id);
    });
  };

  const openNativeCamera = () => {
    cameraInputRef.current?.click();
  };

  const openLiveCamera = async (event) => {
    event?.stopPropagation?.();
    event?.preventDefault?.();
    try {
      const stream = await openRearCamera();
      setLiveStream(stream);
      setCameraOpen(true);
    } catch (err) {
      notify(err.message || "Live camera blocked — opening phone camera.", "warn");
      openNativeCamera();
    }
  };

  const startNextPageCamera = async () => {
    if (!scanPrompt) return;
    autoProcessRef.current = true;
    await openLiveCamera();
  };

  const startNextPageUpload = () => {
    if (!scanPrompt) return;
    nextPageFileRef.current?.click();
  };

  const cameraGuide = scanPrompt
    ? `Scan page ${scanPrompt.nextPage} of ${scanPrompt.expected}`
    : "Fill the box with the slip";

  const cameraStatusExtra = scanPrompt
    ? `${scanPrompt.ballotType || "Slip"} · missing ${scanPrompt.missing.join(", ")}`
    : null;

  return (
    <section className={cameraOpen && liveStream ? "capture-camera" : ""}>
      {!(cameraOpen && liveStream) && (
        <header className="page-head desktop-only-flex">
          <div className="page-title-row">
            <h1>Capture</h1>
            <InfoTip label="Capture help">
              <p>Photograph each page so the slip fills the box. Everything outside the box is dropped.</p>
              <p>Add several pages from the camera or gallery, then process them together. If OCR sees a multi-page slip, you will be asked to scan the next missing page.</p>
            </InfoTip>
          </div>
        </header>
      )}

      {process && !(cameraOpen && liveStream) ? <ProcessingProgress progress={process} /> : null}

      {scanPrompt && !busy && !(cameraOpen && liveStream) && (
        <div className="modal-back" role="dialog" aria-modal="true" aria-labelledby="scan-next-title">
          <div className="modal scan-next-modal" onClick={(e) => e.stopPropagation()}>
            <h3 id="scan-next-title">Scan the next page</h3>
            <p>
              This {scanPrompt.ballotType ? `${scanPrompt.ballotType.toLowerCase()} ` : ""}
              slip has {scanPrompt.expected} page{scanPrompt.expected === 1 ? "" : "s"}.
              {" "}Received page{scanPrompt.received.length === 1 ? "" : "s"}{" "}
              {scanPrompt.received.join(", ") || "—"}.
              {" "}Please add page {scanPrompt.nextPage}.
            </p>
            {scanPrompt.missing.length > 1 ? (
              <p className="scan-next-extra">Still missing: {scanPrompt.missing.join(", ")}</p>
            ) : null}
            <div className="modal-actions scan-next-actions">
              <button type="button" className="btn ghost" onClick={finishCapture}>
                Finish later
              </button>
              <button type="button" className="btn ghost" onClick={startNextPageUpload}>
                Choose file
              </button>
              <button type="button" className="btn" onClick={startNextPageCamera}>
                Use camera
              </button>
            </div>
          </div>
        </div>
      )}

      <input
        ref={nextPageFileRef}
        type="file"
        accept="image/*,.pdf,application/pdf"
        hidden
        onChange={async (e) => {
          const files = Array.from(e.target.files || []);
          e.target.value = "";
          if (!files.length) return;
          await runFiles(files, { stayOnCapture: true });
        }}
      />

      {cameraOpen && liveStream ? (
        <CameraCapture
          stream={liveStream}
          disabled={busy}
          pageCount={pending.length}
          guideText={cameraGuide}
          statusExtra={cameraStatusExtra}
          onCapture={addCameraPage}
          onClose={() => {
            autoProcessRef.current = false;
            closeCamera({ fromHistory: false });
          }}
          onFallback={() => {
            autoProcessRef.current = Boolean(scanPrompt);
            closeCamera({ fromHistory: false });
            openNativeCamera();
          }}
        />
      ) : busy ? null : (
        <div
          className={`drop ${over ? "over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            queueFiles(e.dataTransfer.files);
          }}
        >
          <h2>Add slip pages</h2>
          <p className="drop-hint">Select or capture multiple pages, then process them all together.</p>
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
              queueFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <input
            ref={cameraInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            hidden
            onChange={async (e) => {
              const files = Array.from(e.target.files || []);
              e.target.value = "";
              if (!files.length) return;
              if (autoProcessRef.current || scanPrompt) {
                autoProcessRef.current = false;
                await runFiles(files, { stayOnCapture: true });
                return;
              }
              queueFiles(files);
            }}
          />
        </div>
      )}

      {pending.length > 0 && !busy && !(cameraOpen && liveStream) && (
        <div className="capture-queue">
          <div className="capture-queue-head">
            <h2>{pending.length} page{pending.length === 1 ? "" : "s"} ready</h2>
            <button className="btn" type="button" disabled={busy} onClick={uploadPending}>
              Process pages
            </button>
          </div>
          <ul className="capture-thumbs">
            {pending.map((item, index) => (
              <li key={item.id}>
                <img src={item.preview} alt={`Captured page ${index + 1}`} />
                <span className="capture-thumb-label">Page {index + 1}</span>
                <button type="button" className="btn ghost" disabled={busy} onClick={() => removePending(item.id)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {lastResult && !busy && !(cameraOpen && liveStream) && (
        <div className="capture-results">
          <div className="capture-results-head">
            <h2>Processed results</h2>
            {!scanPrompt ? (
              <button className="btn" type="button" onClick={finishCapture}>
                Open inbox
              </button>
            ) : null}
          </div>
          <ul className="capture-result-list">
            {lastResult.slips.map((slip) => (
              <li key={slip.slipId}>
                <div className="capture-result-title">
                  {slip.ballotType || "Slip"}
                  {slip.barcode ? ` · ${slip.barcode}` : ""}
                </div>
                <div className="capture-result-meta">
                  Pages {slip.received.join(", ") || "—"} of {slip.expected}
                  {slip.isComplete
                    ? " · complete"
                    : slip.missing.length
                      ? ` · missing ${slip.missing.join(", ")}`
                      : " · incomplete"}
                </div>
              </li>
            ))}
          </ul>
          {lastResult.pages.length > 0 ? (
            <ul className="capture-page-list">
              {lastResult.pages.map((page) => (
                <li key={page.page_id}>
                  Page {page.page_number || "?"} of {page.page_total || "?"}
                  {page.ballot_type ? ` · ${page.ballot_type}` : ""}
                  {page.barcode_text ? ` · ${page.barcode_text}` : ""}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </section>
  );
}
