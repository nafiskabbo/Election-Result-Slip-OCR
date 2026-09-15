import { useEffect, useState } from "react";
import { api } from "../api.js";

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
      <header className="page-head">
        <div>
          <h1>Rules</h1>
          <p>Critical failures block approval. Warnings stay visible but do not stop a supervisor.</p>
        </div>
      </header>
      <div className="rule-list">
        {rules.map((rule) => (
          <article className="rule" key={rule.rule_code}>
            <div className="rule-top">
              <div>
                <strong>{rule.name}</strong> <code>{rule.rule_code}</code>
              </div>
              <label>
                <input
                  type="checkbox"
                  checked={rule.is_active}
                  onChange={(e) => patch(rule.rule_code, { is_active: e.target.checked })}
                />{" "}
                Active
              </label>
            </div>
            <p>{rule.description}</p>
            <label>
              Severity{" "}
              <select
                value={rule.severity}
                onChange={(e) => patch(rule.rule_code, { severity: e.target.value })}
              >
                <option value="error">Critical, blocks approval</option>
                <option value="warning">Warning only</option>
              </select>
            </label>
          </article>
        ))}
      </div>
    </section>
  );
}
