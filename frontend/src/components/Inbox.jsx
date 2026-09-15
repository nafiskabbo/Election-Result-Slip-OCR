import { useEffect, useRef, useState } from "react";
import { api, apiUrl, statusLabel } from "../api.js";
import { Icon } from "./Icons.jsx";
import Sheet from "./Sheet.jsx";

export default function Inbox({
  slips,
  counts,
  filters,
  onFiltersChange,
  onOpen,
  onCapture,
  notify,
}) {
  const [search, setSearch] = useState(filters.search || "");
  const [status, setStatus] = useState(filters.status || "");
  const [ballotType, setBallotType] = useState(filters.ballot_type || "");
  const [sheetOpen, setSheetOpen] = useState(false);
  const searchTimer = useRef(null);

  useEffect(() => {
    setSearch(filters.search || "");
    setStatus(filters.status || "");
    setBallotType(filters.ballot_type || "");
  }, [filters.search, filters.status, filters.ballot_type]);

  const commit = (next) => {
    onFiltersChange({
      search: next.search ?? search,
      status: next.status ?? status,
      ballot_type: next.ballot_type ?? ballotType,
    });
  };

  const onSearchChange = (value) => {
    setSearch(value);
    window.clearTimeout(searchTimer.current);
    searchTimer.current = window.setTimeout(() => {
      commit({ search: value });
    }, 280);
  };

  useEffect(() => () => window.clearTimeout(searchTimer.current), []);

  const clear = async () => {
    if (!window.confirm("Clear every captured slip from this desk?")) return;
    await api.clearSlips();
    setSearch("");
    setStatus("");
    setBallotType("");
    await onFiltersChange({ search: "", status: "", ballot_type: "" });
    notify("Inbox cleared");
  };

  const applySheet = () => {
    commit({ status, ballot_type: ballotType });
    setSheetOpen(false);
  };

  const filterActive = Boolean(filters.status || filters.ballot_type);

  return (
    <section>
      <header className="page-head desktop-only-flex">
        <div className="page-title-row">
          <h1>Inbox</h1>
        </div>
        <div className="toolbar page-actions">
          <button type="button" className="btn ghost" onClick={clear}>Clear inbox</button>
          <button type="button" className="btn" onClick={onCapture}>Capture slips</button>
        </div>
      </header>

      <div className="mobile-inbox-actions mobile-only">
        <button type="button" className="btn ghost icon-text" onClick={clear}>
          <Icon name="clear" size={16} /> Clear
        </button>
        <button type="button" className="btn icon-text" onClick={onCapture}>
          <Icon name="capture" size={16} /> Capture
        </button>
      </div>

      <div className="counts">
        <div className="count"><b>{counts.total}</b><span>Total</span></div>
        <div className="count pass"><b>{counts.approved}</b><span>Approved</span></div>
        <div className="count warn"><b>{counts.pending}</b><span>Ready</span></div>
        <div className="count fail"><b>{counts.incomplete}</b><span>Missing</span></div>
        <div className="count"><b>{counts.flagged}</b><span>Flagged</span></div>
      </div>

      <div className="toolbar inbox-toolbar desktop-only-flex">
        <input
          className="search"
          value={search}
          placeholder="Search VD, station, or reference"
          onChange={(e) => onSearchChange(e.target.value)}
        />
        <select
          value={ballotType}
          onChange={(e) => {
            setBallotType(e.target.value);
            commit({ ballot_type: e.target.value });
          }}
        >
          <option value="">All ballots</option>
          <option value="Provincial">Provincial</option>
          <option value="Regional">Regional</option>
          <option value="National">National</option>
        </select>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            commit({ status: e.target.value });
          }}
        >
          <option value="">All statuses</option>
          <option value="pending_review">Ready</option>
          <option value="incomplete">Missing pages</option>
          <option value="approved">Approved</option>
          <option value="flagged">Flagged</option>
          <option value="rejected">Rejected</option>
        </select>
        <a className="btn ghost" href={apiUrl("/api/export/csv")}>Export CSV</a>
      </div>

      <div className="toolbar inbox-toolbar mobile-only">
        <input
          className="search"
          value={search}
          placeholder="Search VD, station…"
          enterKeyHint="search"
          onChange={(e) => onSearchChange(e.target.value)}
        />
        <button
          type="button"
          className={`icon-btn ${filterActive ? "active" : ""}`}
          aria-label="Filters"
          onClick={() => setSheetOpen(true)}
        >
          <Icon name="filter" size={20} />
        </button>
        <a className="icon-btn" href={apiUrl("/api/export/csv")} aria-label="Export CSV">
          <Icon name="export" size={20} />
        </a>
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

      <Sheet
        title="Filters"
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        footer={(
          <button type="button" className="btn" onClick={applySheet}>Apply filters</button>
        )}
      >
        <label className="sheet-field">
          Ballot type
          <select value={ballotType} onChange={(e) => setBallotType(e.target.value)}>
            <option value="">All ballots</option>
            <option value="Provincial">Provincial</option>
            <option value="Regional">Regional</option>
            <option value="National">National</option>
          </select>
        </label>
        <label className="sheet-field">
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            <option value="pending_review">Ready</option>
            <option value="incomplete">Missing pages</option>
            <option value="approved">Approved</option>
            <option value="flagged">Flagged</option>
            <option value="rejected">Rejected</option>
          </select>
        </label>
        <button
          type="button"
          className="btn ghost"
          onClick={() => {
            setStatus("");
            setBallotType("");
            onFiltersChange({ search, status: "", ballot_type: "" });
            setSheetOpen(false);
          }}
        >
          Clear filters
        </button>
      </Sheet>
    </section>
  );
}
