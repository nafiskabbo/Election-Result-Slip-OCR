import { useEffect, useId, useRef, useState } from "react";

export default function InfoTip({ label = "Info", children, align = "start" }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const onPointer = (event) => {
      if (!rootRef.current?.contains(event.target)) setOpen(false);
    };
    const onKey = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <span className={`info-tip align-${align}`} ref={rootRef}>
      <button
        type="button"
        className="info-tip-btn"
        aria-label={label}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        i
      </button>
      {open && (
        <div className="info-tip-panel" id={panelId} role="dialog" aria-label={label}>
          {children}
        </div>
      )}
    </span>
  );
}
