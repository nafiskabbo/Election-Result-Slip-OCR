import { useState } from "react";

export default function Prompt({ title, body, fields, onSubmit, onCancel }) {
  const [values, setValues] = useState({});

  return (
    <div className="modal-back" onClick={onCancel}>
      <form
        className="modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit(values);
        }}
      >
        <h3>{title}</h3>
        <p>{body}</p>
        {fields.includes("target") && (
          <input
            type="text"
            placeholder="Target slip id"
            value={values.target || ""}
            onChange={(e) => setValues((v) => ({ ...v, target: e.target.value }))}
            required
          />
        )}
        {fields.includes("reason") && (
          <textarea
            rows="3"
            placeholder="Reason"
            value={values.reason || ""}
            onChange={(e) => setValues((v) => ({ ...v, reason: e.target.value }))}
            required
            minLength={5}
          />
        )}
        <div className="modal-actions">
          <button type="button" className="btn ghost" onClick={onCancel}>Cancel</button>
          <button type="submit" className="btn">Save</button>
        </div>
      </form>
    </div>
  );
}
