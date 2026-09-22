import { useEffect, useMemo, useRef, useState } from "react";
import { api, apiUrl, fileUrl, statusLabel } from "../api.js";
import { formatDuration, formatExactTime, processingWindow } from "../time.js";
import Viewer from "./Viewer.jsx";
import Prompt from "./Prompt.jsx";
import Sheet from "./Sheet.jsx";
import { Icon } from "./Icons.jsx";
import ProcessingProgress, { initialProcess, progressFromEvent } from "./ProcessingProgress.jsx";
import ProcessingTimes from "./ProcessingTimes.jsx";

export default function Review({ slip, mobileTab = "photo", onReload, onInbox, notify }) {
  const [pageIndex, setPageIndex] = useState(0);
  const [highlight, setHighlight] = useState(null);
  const [prompt, setPrompt] = useState(null);
  const [draft, setDraft] = useState(slip || null);
  const [editOpen, setEditOpen] = useState(false);
  const [pageBusy, setPageBusy] = useState(false);
  const [process, setProcess] = useState(null);
  const replaceInputRef = useRef(null);
  const retryReplaceFileRef = useRef(null);
  const active = draft || slip;

  useEffect(() => {
    setDraft(slip || null);
    setPageIndex(0);
  }, [slip?.id]);

  const missing = useMemo(() => {
    if (!active) return [];
    const have = new Set((active.pages || []).map((p) => p.page_number));
    const gaps = [];
    for (let n = 1; n <= active.total_expected_pages; n += 1) {
      if (!have.has(n)) gaps.push(n);
    }
    return gaps;
  }, [active]);

  if (!active) {
    return (
      <section>
        <header className="page-head desktop-only-flex">
          <div className="page-title-row">
            <h1>Review</h1>
          </div>
        </header>
        <div className="empty">Select a slip from Inbox.</div>
      </section>
    );
  }

  const page = active.pages?.[pageIndex] || active.pages?.[0];
  const voteRelated = active.is_vote_related !== false;
  const complete = active.total_received_pages >= active.total_expected_pages;
  const partySum = (active.party_results || []).reduce((acc, row) => acc + (row.votes || 0), 0);
  const turnout = active.registered_voters
    ? ((active.total_votes_cast / active.registered_voters) * 100).toFixed(1)
    : "0.0";
  const needsCheck = (row) => {
    if (row.is_overridden) return false;
    const conf = row.confidence_score || 0;
    return (row.votes > 0 && conf < 0.72) || conf < 0.4;
  };
  const unchecked = (active.party_results || []).filter(needsCheck);
  const confClass = (row) => {
    const conf = row.confidence_score || 0;
    if (conf < 0.72) return "low";
    if (conf < 0.9) return "mid";
    return "high";
  };

  const refresh = async () => {
    const next = await api.getSlip(active.id);
    setDraft(next);
    return next;
  };

  const changeVotes = async (row, value) => {
    const votes = parseInt(value, 10) || 0;
    await api.updateParty(active.id, row.id, votes, "Operator corrected a party count");
    const val = await api.evaluate(active.id);
    setDraft((prev) => ({
      ...(prev || active),
      party_results: (prev || active).party_results.map((item) => (
        item.id === row.id ? { ...item, votes, is_overridden: true } : item
      )),
      validation_results: val.validation_results,
      has_errors: val.has_critical_error,
      has_warnings: val.has_warning,
    }));
    notify(`Updated ${row.party_code}`);
  };

  const changeField = async (field, value) => {
    await api.updateField(active.id, field, value, "Field corrected in review");
    setDraft((prev) => ({ ...(prev || active), [field]: value }));
    notify(`Updated ${field.replaceAll("_", " ")}`);
  };

  const runPrompt = (config) => setPrompt(config);

  const confirmLow = async () => {
    for (const row of unchecked) {
      await api.updateParty(active.id, row.id, row.votes, "Operator confirmed OCR count");
    }
    await refresh();
    notify(`Confirmed ${unchecked.length} count${unchecked.length === 1 ? "" : "s"}`);
  };

  const approve = async () => {
    try {
      await api.approve(active.id);
      notify("Slip approved", "pass");
      await onReload(active.id);
    } catch (err) {
      notify(err.message, "fail");
    }
  };

  const linkPage = () => runPrompt({
    title: "Link this page",
    body: "Paste the target slip id and a reason.",
    fields: ["target", "reason"],
    onSubmit: async ({ target, reason }) => {
      await api.linkPage(page.id, target, reason);
      notify("Page linked", "pass");
      await onReload(target);
    },
  });

  const unlinkPage = () => runPrompt({
    title: "Unlink this page",
    body: "Give a reason. The page becomes its own slip.",
    fields: ["reason"],
    onSubmit: async ({ reason }) => {
      await api.unlinkPage(page.id, reason);
      notify("Page unlinked");
      await refresh();
    },
  });

  const rejectSlip = () => runPrompt({
    title: "Reject this slip",
    body: "A reason of at least 5 characters is required.",
    fields: ["reason"],
    onSubmit: async ({ reason }) => {
      await api.reject(active.id, reason);
      notify("Slip rejected", "fail");
      await refresh();
    },
  });

  const flagSlip = () => runPrompt({
    title: "Flag for a supervisor",
    body: "Say what needs a second look.",
    fields: ["reason"],
    onSubmit: async ({ reason }) => {
      await api.flag(active.id, reason);
      notify("Slip flagged");
      await refresh();
    },
  });

  const replacePage = async (file) => {
    if (!file || !page) return;
    retryReplaceFileRef.current = file;
    setPageBusy(true);
    setProcess(initialProcess(1));
    try {
      const data = await api.replacePage(active.id, page.id, file, {
        onProgress: (event) => setProcess((prev) => progressFromEvent(event, prev)),
      });
      const duration = data.total_elapsed_seconds != null
        ? ` · ${formatDuration(data.total_elapsed_seconds)}`
        : "";
      retryReplaceFileRef.current = null;
      setEditOpen(false);
      notify(`Page image replaced${duration}`, "pass");
      setProcess(null);
      await onReload(active.id);
    } catch (err) {
      notify(err.message, "fail");
      setProcess((prev) => (prev ? {
        ...prev,
        failed: true,
        endedAt: prev.endedAt || new Date().toISOString(),
        message: err.message,
        remainingSeconds: 0,
      } : prev));
    } finally {
      setPageBusy(false);
    }
  };

  const removePage = async () => {
    if (!page) return;
    if (!window.confirm("Remove this page image? This cannot be undone.")) return;
    setPageBusy(true);
    try {
      const result = await api.deletePage(active.id, page.id);
      setEditOpen(false);
      if (result.slip_deleted) {
        notify("Page removed", "pass");
        onInbox();
        return;
      }
      notify("Page removed", "pass");
      await onReload(active.id);
    } catch (err) {
      notify(err.message, "fail");
    } finally {
      setPageBusy(false);
    }
  };

  const approveDisabled = !voteRelated || !complete || active.has_errors || unchecked.length > 0;
  const approveTitle = !voteRelated
    ? "This page is not a result slip"
    : !complete
    ? "Missing pages"
    : active.has_errors
      ? "Fix failed checks first"
      : unchecked.length > 0
        ? "Confirm low-confidence counts first"
        : "Approve";

  const countsBody = (
    <div className="form-body">
      <div className="meta">
        {voteRelated ? (
          <div className="reg">
            <span className="sub">Registered</span>
            <b>{active.registered_voters}</b>
          </div>
        ) : null}
        <span className={`chip ${(active.ballot_type || "").toLowerCase()}`}>{active.ballot_type}</span>
        {" "}
        <span className={`chip ${active.status}`}>{statusLabel(active.status)}</span>
        <h2>{active.station_name || (voteRelated ? "Station unread" : "No voting content")}</h2>
        <div className="sub">
          {voteRelated
            ? `VD ${active.voting_district} · ${active.slip_reference}`
            : active.slip_reference}
          {active.municipality ? ` · ${active.municipality}` : ""}
          {active.province ? ` · ${active.province}` : ""}
        </div>
        <ProcessingTimes
          started={processingWindow(active).started}
          ended={processingWindow(active).ended}
        />
        {page?.upload_timestamp ? (
          <div className="sub">
            Page {page.page_number} captured{" "}
            <time dateTime={page.upload_timestamp} title={formatExactTime(page.upload_timestamp)}>
              {formatExactTime(page.upload_timestamp)}
            </time>
          </div>
        ) : null}
      </div>

      {voteRelated ? (
        <>
          {complete ? (
            <div className="banner good">
              <b>Complete · {active.total_expected_pages}/{active.total_expected_pages}</b>
            </div>
          ) : (
            <div className="banner bad">
              <b>Missing page {missing.join(", ")}</b>
              <span className="sub">{active.total_received_pages}/{active.total_expected_pages}</span>
            </div>
          )}

          {unchecked.length > 0 && (
            <div className="banner warn">
              <b>Check {unchecked.length} low-confidence count{unchecked.length === 1 ? "" : "s"}</b>
              <button type="button" className="btn ghost" onClick={confirmLow}>Confirm highlighted</button>
            </div>
          )}

          <div className="table-wrap votes-wrap">
            <table className="data votes">
              <thead>
                <tr>
                  <th>Party</th>
                  <th className="num">Votes</th>
                  <th className="num">%</th>
                  <th>Sig</th>
                </tr>
              </thead>
              <tbody>
                {(active.party_results || []).map((row) => (
                  <tr
                    key={row.id}
                    className={needsCheck(row) ? "needs-check" : ""}
                    onPointerEnter={() => {
                      try { setHighlight(JSON.parse(row.bbox_json || "{}")); } catch { setHighlight(null); }
                    }}
                    onPointerLeave={() => setHighlight(null)}
                  >
                    <td>
                      {row.party_name}
                      <div className="sub">{row.party_code}</div>
                    </td>
                    <td className="num">
                      <input
                        type="number"
                        inputMode="numeric"
                        defaultValue={row.votes}
                        onBlur={(e) => {
                          if (String(e.target.value) !== String(row.votes)) changeVotes(row, e.target.value);
                        }}
                      />
                    </td>
                    <td className={`num conf ${confClass(row)}`}>{Math.round((row.confidence_score || 0) * 100)}</td>
                    <td>{row.signature_detected ? "✓" : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="recon">
            <div className="recon-row">
              <span>Party total</span>
              <strong>{partySum}</strong>
            </div>
            <div className="recon-row">
              <span>Valid</span>
              <input type="number" inputMode="numeric" defaultValue={active.total_valid_votes} onBlur={(e) => changeField("total_valid_votes", parseInt(e.target.value, 10) || 0)} />
            </div>
            <div className="recon-row">
              <span>Spoilt</span>
              <input type="number" inputMode="numeric" defaultValue={active.total_spoilt_votes} onBlur={(e) => changeField("total_spoilt_votes", parseInt(e.target.value, 10) || 0)} />
            </div>
            <div className="recon-row">
              <span>Cast</span>
              <input type="number" inputMode="numeric" defaultValue={active.total_votes_cast} onBlur={(e) => changeField("total_votes_cast", parseInt(e.target.value, 10) || 0)} />
            </div>
            <div className="recon-row">
              <span>Turnout</span>
              <strong>{turnout}%</strong>
            </div>
          </div>

          <ul className="checks">
            {(active.validation_results || []).map((item) => (
              <li key={item.rule_code + item.evaluated_at}>
                <span className={`mark ${item.status}`}>{item.status}</span>
                <span>{item.message}</span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <div className="banner warn">
          <b>Nothing related to voting was found on this page</b>
          <span className="sub">Vote counts are hidden so they are not mistaken for a result slip. Replace or remove the image if this was uploaded by mistake.</span>
        </div>
      )}
    </div>
  );

  const decisionButtons = (
    <>
      <button type="button" className="btn danger icon-text" onClick={rejectSlip}>
        <Icon name="reject" size={16} /> Reject
      </button>
      <button type="button" className="btn warn icon-text" onClick={flagSlip}>
        <Icon name="flag" size={16} /> Flag
      </button>
      {voteRelated ? (
        <button
          type="button"
          className="btn pass icon-text"
          disabled={approveDisabled}
          title={approveTitle}
          onClick={approve}
        >
          <Icon name="approve" size={16} /> Approve
        </button>
      ) : null}
    </>
  );

  return (
    <section className="review-section">
      <header className="page-head desktop-only-flex">
        <div className="page-title-row">
          <h1>Review</h1>
        </div>
        <button type="button" className="btn ghost" onClick={onInbox}>Back to inbox</button>
      </header>

      <div className={`workspace ${(active.ballot_type || "").toLowerCase()}`}>
        <div className={`review-photo-pane ${mobileTab === "photo" ? "mobile-show" : "mobile-hide"}`}>
          <Viewer
            src={fileUrl(page?.enhanced_file_path)}
            highlight={highlight}
            pageNumber={page?.page_number || pageIndex + 1}
            pageTotal={page?.page_total || active.pages?.length || 1}
            onPrevPage={() => setPageIndex((i) => Math.max(0, i - 1))}
            onNextPage={() => setPageIndex((i) => Math.min((active.pages?.length || 1) - 1, i + 1))}
            onEdit={() => setEditOpen(true)}
          />
        </div>

        <div className={`form-pane ${mobileTab === "counts" ? "mobile-show" : "mobile-hide"}`}>
          <div className="pane-bar counts-bar">
            <strong>Counts</strong>
            <div className="tools mobile-only">
              <button type="button" className="icon-btn" aria-label="Edit page image" title="Edit page image" onClick={() => setEditOpen(true)}>
                <Icon name="edit" size={18} />
              </button>
              <button type="button" className="icon-btn" aria-label="Link page" title="Link page" onClick={linkPage}>
                <Icon name="link" size={18} />
              </button>
              <button type="button" className="icon-btn" aria-label="Unlink page" title="Unlink page" onClick={unlinkPage}>
                <Icon name="unlink" size={18} />
              </button>
              <a
                className="icon-btn"
                href={apiUrl(`/api/export/slips/${active.id}/pdf`)}
                target="_blank"
                rel="noreferrer"
                aria-label="Export PDF"
                title="Export PDF"
              >
                <Icon name="pdf" size={18} />
              </a>
            </div>
            <div className="tools desktop-only-flex">
              <button type="button" className="btn ghost icon-text" onClick={() => setEditOpen(true)}>
                <Icon name="edit" size={16} /> Edit image
              </button>
              <button type="button" className="btn ghost" onClick={linkPage}>Link page</button>
              <button type="button" className="btn ghost" onClick={unlinkPage}>Unlink page</button>
              <a className="btn ghost" href={apiUrl(`/api/export/slips/${active.id}/pdf`)} target="_blank" rel="noreferrer">Export PDF</a>
            </div>
          </div>

          {countsBody}

          <div className="decision desktop-only-flex">
            {decisionButtons}
          </div>
        </div>
      </div>

      {mobileTab === "counts" && (
        <div className="review-sticky-actions mobile-only">
          {decisionButtons}
        </div>
      )}

      {prompt && (
        <Prompt
          title={prompt.title}
          body={prompt.body}
          fields={prompt.fields}
          onCancel={() => setPrompt(null)}
          onSubmit={async (values) => {
            try {
              await prompt.onSubmit(values);
              setPrompt(null);
            } catch (err) {
              notify(err.message, "fail");
            }
          }}
        />
      )}

      <input
        ref={replaceInputRef}
        type="file"
        accept="image/*,.pdf,application/pdf"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) replacePage(file);
        }}
      />

      <Sheet
        title="Edit page image"
        open={editOpen}
        onClose={() => { if (!pageBusy) { setEditOpen(false); setProcess(null); } }}
        footer={(
          <button
            type="button"
            className="btn danger"
            disabled={pageBusy || !page}
            onClick={removePage}
          >
            Remove this page
          </button>
        )}
      >
        <p className="sub">Replace the photo if the capture is wrong, or remove it from this slip.</p>
        {process ? (
          <ProcessingProgress
            progress={process}
            onRetry={process.failed && retryReplaceFileRef.current
              ? () => replacePage(retryReplaceFileRef.current)
              : undefined}
            onDismiss={process.failed ? () => setProcess(null) : undefined}
          />
        ) : null}
        <button
          type="button"
          className="btn"
          disabled={pageBusy || !page}
          onClick={() => replaceInputRef.current?.click()}
        >
          {pageBusy ? "Reading image…" : "Replace image"}
        </button>
      </Sheet>
    </section>
  );
}
