import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Capture({ busy, setBusy, onDone, notify }) {
  const [packs, setPacks] = useState([]);
  const [over, setOver] = useState(false);
  const [note, setNote] = useState("");

  useEffect(() => {
    api.samplePacks().then(setPacks).catch((err) => notify(err.message, "fail"));
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
          <p>Drop photographs or PDFs of result slips. The desk crops, reads the barcode, and groups pages that belong together.</p>
        </div>
      </header>

      <div
        className={`drop ${over ? "over" : ""}`}
        onClick={() => document.getElementById("fileInput").click()}
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
        <button className="btn" type="button">Choose files</button>
        <input
          id="fileInput"
          type="file"
          multiple
          accept=".jpg,.jpeg,.png,.pdf"
          hidden
          onChange={(e) => runFiles(e.target.files)}
        />
      </div>

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
