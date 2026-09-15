import { useState } from "react";
import { api, apiUrl, statusLabel } from "../api.js";
import InfoTip from "./InfoTip.jsx";

export default function Inbox({ slips, counts, onRefresh, onOpen, onCapture, notify }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [ballotType, setBallotType] = useState("");

  const apply = () => onRefresh({ search, status, ballot_type: ballotType });

  const clear = async () => {
    if (!window.confirm("Clear every captured slip from this desk?")) return;
    await api.clearSlips();
    await onRefresh();
    notify("Inbox cleared");
  };

  return (
    <section>
      <header className="page-head">
        <div className="page-title-row">
          <h1>Inbox</h1>
          <InfoTip label="Inbox help">
            <p>Slips waiting to be checked. Incomplete sets stay here until missing pages arrive.</p>
          </InfoTip>
        </div>
        <div className="toolbar page-actions">
          <button type="button" className="btn ghost" onClick={clear}>Clear</button>
          <button type="button" className="btn" onClick={onCapture}>Capture</button>
        </div>
      </header>

      <div className="counts">
        <div className="count"><b>{counts.total}</b><span>Total</span></div>
        <div className="count pass"><b>{counts.approved}</b><span>Approved</span></div>
        <div className="count warn"><b>{counts.pending}</b><span>Ready</span></div>
        <div className="count fail"><b>{counts.incomplete}</b><span>Missing</span></div>
        <div className="count"><b>{counts.flagged}</b><span>Flagged</span></div>
      </div>

      <div className="toolbar">
        <input
          className="search"
          value={search}
          placeholder="Search VD, station…"
          enterKeyHint="search"
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && apply()}
        />
        <select value={ballotType} onChange={(e) => setBallotType(e.target.value)}>
          <option value="">All ballots</option>
          <option value="Provincial">Provincial</option>
          <option value="Regional">Regional</option>
          <option value="National">National</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="pending_review">Ready</option>
          <option value="incomplete">Missing</option>
          <option value="approved">Approved</option>
          <option value="flagged">Flagged</option>
          <option value="rejected">Rejected</option>
        </select>
        <button type="button" className="btn ghost" onClick={apply}>Filter</button>
        <a className="btn ghost" href={apiUrl("/api/export/csv")}>CSV</a>
      </div>

      <div className="table-wrap desktop-only">
        <table className="data">
          <thead>
            <tr>
              <th>Reference</th>
              <th>Ballot</th>
              <th>Station</th>
              <th className="num">Valid</th>
              <th>Pages</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {slips.length === 0 && (
              <tr>
                <td colSpan="7" className="empty">Nothing captured yet.</td>
              </tr>
            )}
            {slips.map((slip) => {
              const complete = slip.total_received_pages >= slip.total_expected_pages;
              return (
                <tr key={slip.id} className={(slip.ballot_type || "").toLowerCase()}>
                  <td>
                    <strong>{slip.slip_reference}</strong>
                    <div className="sub">VD {slip.voting_district}</div>
                  </td>
                  <td>
                    <span className={`chip ${(slip.ballot_type || "").toLowerCase()}`}>{slip.ballot_type}</span>
                  </td>
                  <td>
                    <div>{slip.station_name || "Station unread"}</div>
                    <div className="sub">{[slip.municipality, slip.province].filter(Boolean).join(", ")}</div>
                  </td>
                  <td className="num">
                    {slip.total_valid_votes}
                    <div className="sub">{slip.registered_voters} reg.</div>
                  </td>
                  <td>
                    <span className={`chip ${complete ? "approved" : "incomplete"}`}>
                      {slip.total_received_pages}/{slip.total_expected_pages}
                    </span>
                  </td>
                  <td>
                    <span className={`chip ${slip.status}`}>{statusLabel(slip.status)}</span>
                    {slip.has_errors ? <div className="sub">Checks failed</div> : null}
                  </td>
                  <td>
                    <div className="row-actions">
                      <button type="button" className="btn ghost" onClick={() => onOpen(slip.id)}>Open</button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="slip-cards mobile-only">
        {slips.length === 0 && <div className="empty">Nothing captured yet.</div>}
        {slips.map((slip) => {
          const complete = slip.total_received_pages >= slip.total_expected_pages;
          return (
            <button
              type="button"
              key={slip.id}
              className={`slip-card ${(slip.ballot_type || "").toLowerCase()}`}
              onClick={() => onOpen(slip.id)}
            >
              <div className="slip-card-top">
                <strong>{slip.slip_reference}</strong>
                <span className={`chip ${slip.status}`}>{statusLabel(slip.status)}</span>
              </div>
              <div className="slip-card-meta">
                <span className={`chip ${(slip.ballot_type || "").toLowerCase()}`}>{slip.ballot_type}</span>
                <span className={`chip ${complete ? "approved" : "incomplete"}`}>
                  {slip.total_received_pages}/{slip.total_expected_pages}
                </span>
              </div>
              <div className="slip-card-station">{slip.station_name || "Station unread"}</div>
              <div className="sub">VD {slip.voting_district} · {slip.total_valid_votes} valid</div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
