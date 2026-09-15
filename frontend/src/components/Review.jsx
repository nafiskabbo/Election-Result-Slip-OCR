import { useEffect, useMemo, useState } from "react";
import { api, apiUrl, fileUrl, statusLabel } from "../api.js";
import Viewer from "./Viewer.jsx";
import Prompt from "./Prompt.jsx";

export default function Review({ slip, onReload, onInbox, notify }) {
  const [pageIndex, setPageIndex] = useState(0);
  const [highlight, setHighlight] = useState(null);
  const [prompt, setPrompt] = useState(null);
  const [draft, setDraft] = useState(slip || null);
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
        <header className="page-head">
          <div>
            <h1>Review</h1>
            <p>Open a slip from the inbox to check it against the photograph.</p>
          </div>
        </header>
      </section>
    );
  }

  const page = active.pages?.[pageIndex] || active.pages?.[0];
  const complete = active.total_received_pages >= active.total_expected_pages;
  const partySum = (active.party_results || []).reduce((acc, row) => acc + (row.votes || 0), 0);
  const turnout = active.registered_voters
    ? ((active.total_votes_cast / active.registered_voters) * 100).toFixed(1)
    : "0.0";

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

  const approve = async () => {
    try {
      await api.approve(active.id);
      notify("Slip approved", "pass");
      await onReload(active.id);
    } catch (err) {
      notify(err.message, "fail");
    }
  };

  return (
    <section>
      <header className="page-head">
        <div>
          <h1>Review</h1>
          <p>Read the photograph, correct anything the OCR missed, then approve only when the set is complete.</p>
        </div>
        <button className="btn ghost" onClick={onInbox}>Back to inbox</button>
      </header>

      <div className={`workspace ${(active.ballot_type || "").toLowerCase()}`}>
        <div>
          <div className="pane-bar">
            <div className="tools">
              {(active.pages || []).map((item, idx) => (
                <button
                  key={item.id}
                  className={idx === pageIndex ? "btn" : "btn ghost"}
                  onClick={() => setPageIndex(idx)}
                >
                  Page {item.page_number} of {item.page_total}
                </button>
              ))}
            </div>
          </div>
          <Viewer src={fileUrl(page?.enhanced_file_path)} highlight={highlight} />
        </div>

        <div className="form-pane">
          <div className="pane-bar">
            <strong>Extracted counts</strong>
            <div className="tools">
              <button className="btn ghost" onClick={() => runPrompt({
                title: "Link this page",
                body: "Paste the target slip id and a reason of at least 5 characters.",
                fields: ["target", "reason"],
                onSubmit: async ({ target, reason }) => {
                  await api.linkPage(page.id, target, reason);
                  notify("Page linked", "pass");
                  await onReload(target);
                },
              })}>Link page</button>
              <button className="btn ghost" onClick={() => runPrompt({
                title: "Unlink this page",
                body: "Give a reason of at least 5 characters. The page becomes its own slip.",
                fields: ["reason"],
                onSubmit: async ({ reason }) => {
                  await api.unlinkPage(page.id, reason);
                  notify("Page unlinked");
                  await refresh();
                },
              })}>Unlink</button>
              <a className="btn ghost" href={apiUrl(`/api/export/slips/${active.id}/pdf`)} target="_blank" rel="noreferrer">PDF</a>
            </div>
          </div>

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
                <div>
                  <b>All expected pages are here</b>
                  {active.total_expected_pages} of {active.total_expected_pages} linked.
                </div>
              </div>
            ) : (
              <div className="banner bad">
                <div>
                  <b>Missing page {missing.join(", ")}</b>
                  {active.total_received_pages} of {active.total_expected_pages} received. Approval stays blocked until the rest arrive.
                </div>
              </div>
            )}

            <div className="table-wrap" style={{ maxHeight: 280 }}>
              <table className="data votes">
                <thead>
                  <tr>
                    <th>Party</th>
                    <th className="num">Votes</th>
                    <th className="num">Conf.</th>
                    <th>Agent</th>
                  </tr>
                </thead>
                <tbody>
                  {(active.party_results || []).map((row) => (
                    <tr
                      key={row.id}
                      onMouseEnter={() => {
                        try { setHighlight(JSON.parse(row.bbox_json || "{}")); } catch { setHighlight(null); }
                      }}
                      onMouseLeave={() => setHighlight(null)}
                    >
                      <td>
                        {row.party_name}
                        <div className="sub">{row.party_code}</div>
                      </td>
                      <td className="num">
                        <input
                          type="number"
                          defaultValue={row.votes}
                          onBlur={(e) => {
                            if (String(e.target.value) !== String(row.votes)) changeVotes(row, e.target.value);
                          }}
                        />
                      </td>
                      <td className="num conf">{Math.round((row.confidence_score || 0) * 100)}%</td>
                      <td>{row.signature_detected ? "Signed" : "—"}</td>
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
                <span>Valid votes</span>
                <input type="number" defaultValue={active.total_valid_votes} onBlur={(e) => changeField("total_valid_votes", parseInt(e.target.value, 10) || 0)} />
              </div>
              <div className="recon-row">
                <span>Spoilt</span>
                <input type="number" defaultValue={active.total_spoilt_votes} onBlur={(e) => changeField("total_spoilt_votes", parseInt(e.target.value, 10) || 0)} />
              </div>
              <div className="recon-row">
                <span>Votes cast</span>
                <input type="number" defaultValue={active.total_votes_cast} onBlur={(e) => changeField("total_votes_cast", parseInt(e.target.value, 10) || 0)} />
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

            <div className="decision">
              <div className="tools">
                <button className="btn danger" onClick={() => runPrompt({
                  title: "Reject this slip",
                  body: "A reason of at least 5 characters is required.",
                  fields: ["reason"],
                  onSubmit: async ({ reason }) => {
                    await api.reject(active.id, reason);
                    notify("Slip rejected", "fail");
                    await refresh();
                  },
                })}>Reject</button>
                <button className="btn warn" onClick={() => runPrompt({
                  title: "Flag for a supervisor",
                  body: "Say what needs a second look.",
                  fields: ["reason"],
                  onSubmit: async ({ reason }) => {
                    await api.flag(active.id, reason);
                    notify("Slip flagged");
                    await refresh();
                  },
                })}>Flag</button>
              </div>
              <button
                className="btn pass"
                disabled={!complete || active.has_errors}
                title={!complete ? "Missing pages" : active.has_errors ? "Fix failed checks first" : "Approve"}
                onClick={approve}
              >
                Approve
              </button>
            </div>
          </div>
        </div>
      </div>

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
