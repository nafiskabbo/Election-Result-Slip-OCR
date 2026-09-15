import { useEffect, useState } from "react";
import { api } from "../api.js";
import InfoTip from "./InfoTip.jsx";

export default function Log() {
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    api.audit().then(setLogs).catch(() => setLogs([]));
  }, []);

  return (
    <section>
      <header className="page-head">
        <div className="page-title-row">
          <h1>Log</h1>
          <InfoTip label="Log help">
            <p>Every capture, edit, link, and approval is appended here. Old rows are not rewritten.</p>
          </InfoTip>
        </div>
      </header>
      <div className="audit-list">
        {logs.length === 0 && <div className="empty">No audit entries yet.</div>}
        {logs.map((item) => (
          <article className="audit-item" key={item.id}>
            <header>
              <strong>{item.action.replaceAll("_", " ")}</strong>
              <span className="sub">{item.timestamp}</span>
            </header>
            <p>
              {item.user_name || item.user_id}
              {item.field_name ? ` · ${item.field_name}` : ""}
              {item.old_value != null ? ` · ${item.old_value} → ${item.new_value}` : ""}
            </p>
            {item.reason ? <div className="sub">{item.reason}</div> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
