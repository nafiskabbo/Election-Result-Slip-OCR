export default function Sheet({ title, open, onClose, children, footer }) {
  if (!open) return null;

  return (
    <div className="sheet-back" onClick={onClose} role="presentation">
      <div
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sheet-handle" aria-hidden="true" />
        <header className="sheet-head">
          <h3>{title}</h3>
          <button type="button" className="btn ghost" onClick={onClose}>
            Done
          </button>
        </header>
        <div className="sheet-body">{children}</div>
        {footer ? <div className="sheet-foot">{footer}</div> : null}
      </div>
    </div>
  );
}
