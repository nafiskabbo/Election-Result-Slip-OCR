import { useEffect, useState } from "react";
import { api } from "../api.js";
import InfoTip from "./InfoTip.jsx";

export default function Rules({ notify }) {
  const [rules, setRules] = useState([]);

  const load = () => api.rules().then(setRules);

  useEffect(() => { load().catch((err) => notify(err.message, "fail")); }, []);

  const patch = async (code, payload) => {
    await api.updateRule(code, payload);
    notify(`Updated ${code}`);
    await load();
  };

  return (
    <section>
      <header className="page-head desktop-only-flex">
        <div className="page-title-row">
          <h1>Rules</h1>
          <InfoTip label="Rules help">
            <p>Critical failures block approval. Warnings stay visible but do not stop a supervisor.</p>
          </InfoTip>
        </div>
      </header>
      <div className="mobile-rules-tip mobile-only">
        <InfoTip label="Rules help">
          <p>Critical failures block approval. Warnings stay visible but do not stop a supervisor.</p>
        </InfoTip>
        <span className="sub">Severity meanings</span>
      </div>
      <div className="rule-list">
        {rules.map((rule) => (
          <article className="rule" key={rule.rule_code}>
            <div className="rule-top">
              <div>
                <strong>{rule.name}</strong> <code>{rule.rule_code}</code>
              </div>
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={rule.is_active}
                  onChange={(e) => patch(rule.rule_code, { is_active: e.target.checked })}
                />
                Active
              </label>
            </div>
            <p>{rule.description}</p>
            <label className="severity-label">
              Severity
              <select
                value={rule.severity}
                onChange={(e) => patch(rule.rule_code, { severity: e.target.value })}
              >
                <option value="error">Critical</option>
                <option value="warning">Warning</option>
              </select>
            </label>
          </article>
        ))}
      </div>
    </section>
  );
}
