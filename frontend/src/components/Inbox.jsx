import { useState } from "react";
import { api, apiUrl, statusLabel } from "../api.js";

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
        <div>
          <h1>Inbox</h1>
          <p>Slips waiting to be checked. Incomplete sets stay here until the missing pages arrive.</p>
        </div>
        <div className="toolbar" style={{ margin: 0 }}>
          <button className="btn ghost" onClick={clear}>Clear inbox</button>
          <button className="btn" onClick={onCapture}>Capture slips</button>
        </div>
      </header>

      <div className="counts">
        <div className="count"><b>{counts.total}</b><span>Captured</span></div>
        <div className="count pass"><b>{counts.approved}</b><span>Approved</span></div>
        <div className="count warn"><b>{counts.pending}</b><span>Ready to check</span></div>
        <div className="count fail"><b>{counts.incomplete}</b><span>Missing pages</span></div>
        <div className="count"><b>{counts.flagged}</b><span>Flagged</span></div>
      </div>

      <div className="toolbar">
        <input
          className="search"
          value={search}
          placeholder="Search VD, station, or reference"
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
          <option value="pending_review">Ready to check</option>
          <option value="incomplete">Missing pages</option>
          <option value="approved">Approved</option>
          <option value="flagged">Flagged</option>
          <option value="rejected">Rejected</option>
        </select>
        <button className="btn ghost" onClick={apply}>Filter</button>
        <a className="btn ghost" href={apiUrl("/api/export/csv")}>Export CSV</a>
      </div>

      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Reference</th>
              <th>Ballot</th>
              <th>Station</th>
              <th className="num">Valid votes</th>
              <th>Pages</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {slips.length === 0 && (
              <tr>
                <td colSpan="7" className="empty">
                  Nothing captured yet. Load the contest photographs from Capture to see grouping.
                </td>
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
                    <div className="sub">{slip.registered_voters} registered</div>
                  </td>
                  <td>
                    <span className={`chip ${complete ? "approved" : "incomplete"}`}>
                      {slip.total_received_pages} of {slip.total_expected_pages}
                    </span>
                  </td>
                  <td>
                    <span className={`chip ${slip.status}`}>{statusLabel(slip.status)}</span>
                    {slip.has_errors ? <div className="sub">Checks failed</div> : null}
                  </td>
                  <td>
                    <div className="row-actions">
                      <button className="btn ghost" onClick={() => onOpen(slip.id)}>Open</button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
