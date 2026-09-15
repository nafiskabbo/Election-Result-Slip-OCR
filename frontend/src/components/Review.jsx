import { useEffect, useMemo, useState } from "react";
import { api, apiUrl, fileUrl, statusLabel } from "../api.js";
import Viewer from "./Viewer.jsx";
import Prompt from "./Prompt.jsx";
import { Icon } from "./Icons.jsx";

export default function Review({ slip, onReload, onInbox, notify }) {
  const [pageIndex, setPageIndex] = useState(0);
  const [highlight, setHighlight] = useState(null);
  const [prompt, setPrompt] = useState(null);
  const [draft, setDraft] = useState(slip || null);
  const [mobileTab, setMobileTab] = useState("photo");
  const active = draft || slip;

  useEffect(() => {
    setDraft(slip || null);
    setPageIndex(0);
    setMobileTab("photo");
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

  const approveDisabled = !complete || active.has_errors || unchecked.length > 0;
  const approveTitle = !complete
    ? "Missing pages"
    : active.has_errors
      ? "Fix failed checks first"
      : unchecked.length > 0
        ? "Confirm low-confidence counts first"
        : "Approve";

  const countsBody = (
    <div className="form-body">
      <div className="meta">
        <div className="reg">
          <span className="sub">Registered</span>
          <b>{active.registered_voters}</b>
        </div>
        <span className={`chip ${(active.ballot_type || "").toLowerCase()}`}>{active.ballot_type}</span>
        {" "}
        <span className={`chip ${active.status}`}>{statusLabel(active.status)}</span>
        <h2>{active.station_name || "Station unread"}</h2>
        <div className="sub">
          VD {active.voting_district} · {active.slip_reference}
          {active.municipality ? ` · ${active.municipality}` : ""}
          {active.province ? ` · ${active.province}` : ""}
        </div>
      </div>

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
      <button
        type="button"
        className="btn pass icon-text"
        disabled={approveDisabled}
        title={approveTitle}
        onClick={approve}
      >
        <Icon name="approve" size={16} /> Approve
      </button>
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

      <div className="review-mobile-tabs mobile-only">
        <button
          type="button"
          className={mobileTab === "photo" ? "active" : ""}
          onClick={() => setMobileTab("photo")}
        >
          <Icon name="photo" size={16} /> Photo
        </button>
        <button
          type="button"
          className={mobileTab === "counts" ? "active" : ""}
          onClick={() => setMobileTab("counts")}
        >
          <Icon name="counts" size={16} /> Counts
        </button>
      </div>

      <div className={`workspace ${(active.ballot_type || "").toLowerCase()}`}>
        <div className={`review-photo-pane ${mobileTab === "photo" ? "mobile-show" : "mobile-hide"}`}>
          <div className="pane-bar">
            <div className="tools page-tabs">
              {(active.pages || []).map((item, idx) => (
                <button
                  key={item.id}
                  type="button"
                  className={idx === pageIndex ? "btn" : "btn ghost"}
                  onClick={() => setPageIndex(idx)}
                >
                  Page {item.page_number}/{item.page_total}
                </button>
              ))}
            </div>
          </div>
          <Viewer src={fileUrl(page?.enhanced_file_path)} highlight={highlight} />
        </div>

        <div className={`form-pane ${mobileTab === "counts" ? "mobile-show" : "mobile-hide"}`}>
          <div className="pane-bar">
            <strong>Counts</strong>
            <div className="tools mobile-only">
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
    </section>
  );
}
