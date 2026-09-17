import { useEffect, useRef, useState } from "react";
import { Icon } from "./Icons.jsx";

function touchDistance(a, b) {
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
}

export default function Viewer({
  src,
  highlight,
  pageNumber,
  pageTotal,
  onPrevPage,
  onNextPage,
  onEdit,
}) {
  const wrapRef = useRef(null);
  const imgRef = useRef(null);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [rotation, setRotation] = useState(0);
  const scaleRef = useRef(scale);
  const panRef = useRef(pan);
  const gesture = useRef(null);
  scaleRef.current = scale;
  panRef.current = pan;

  const multiPage = (pageTotal || 0) > 1;
  const canPrev = multiPage && pageNumber > 1;
  const canNext = multiPage && pageNumber < pageTotal;

  const fit = () => {
    const wrap = wrapRef.current;
    const img = imgRef.current;
    if (!wrap || !img || !img.naturalWidth) return;
    const pad = 16;
    const sx = (wrap.clientWidth - pad) / img.naturalWidth;
    const sy = (wrap.clientHeight - pad) / img.naturalHeight;
    setScale(Math.min(sx, sy, 1.4));
    setPan({ x: 0, y: 0 });
  };

  useEffect(() => {
    setRotation(0);
    setPan({ x: 0, y: 0 });
  }, [src]);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap) return undefined;

    const onTouchStart = (e) => {
      if (e.touches.length === 2) {
        gesture.current = {
          mode: "pinch",
          dist: touchDistance(e.touches[0], e.touches[1]),
          scale: scaleRef.current,
        };
      } else if (e.touches.length === 1) {
        gesture.current = {
          mode: "pan",
          x: e.touches[0].clientX - panRef.current.x,
          y: e.touches[0].clientY - panRef.current.y,
        };
      }
    };

    const onTouchMove = (e) => {
      if (!gesture.current) return;
      if (gesture.current.mode === "pinch" && e.touches.length === 2) {
        e.preventDefault();
        const ratio = touchDistance(e.touches[0], e.touches[1]) / gesture.current.dist;
        setScale(Math.min(4, Math.max(0.4, gesture.current.scale * ratio)));
      } else if (gesture.current.mode === "pan" && e.touches.length === 1) {
        setPan({
          x: e.touches[0].clientX - gesture.current.x,
          y: e.touches[0].clientY - gesture.current.y,
        });
      }
    };

    const onTouchEnd = () => {
      gesture.current = null;
    };

    wrap.addEventListener("touchstart", onTouchStart, { passive: true });
    wrap.addEventListener("touchmove", onTouchMove, { passive: false });
    wrap.addEventListener("touchend", onTouchEnd);
    wrap.addEventListener("touchcancel", onTouchEnd);
    return () => {
      wrap.removeEventListener("touchstart", onTouchStart);
      wrap.removeEventListener("touchmove", onTouchMove);
      wrap.removeEventListener("touchend", onTouchEnd);
      wrap.removeEventListener("touchcancel", onTouchEnd);
    };
  }, []);

  const onPointerDown = (e) => {
    if (e.pointerType === "touch") return;
    gesture.current = { mode: "pan", x: e.clientX - pan.x, y: e.clientY - pan.y };
    wrapRef.current?.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e) => {
    if (e.pointerType === "touch" || !gesture.current || gesture.current.mode !== "pan") return;
    setPan({ x: e.clientX - gesture.current.x, y: e.clientY - gesture.current.y });
  };
  const onPointerUp = () => {
    if (gesture.current?.mode === "pan") gesture.current = null;
  };

  const onWheel = (e) => {
    e.preventDefault();
    const next = Math.min(4, Math.max(0.4, scale * (e.deltaY < 0 ? 1.12 : 0.9)));
    setScale(next);
  };

  const bboxStyle = highlight ? {
    left: `calc(50% + ${pan.x}px + ${(highlight.x - (imgRef.current?.naturalWidth || 0) / 2) * scale}px)`,
    top: `calc(50% + ${pan.y}px + ${(highlight.y - (imgRef.current?.naturalHeight || 0) / 2) * scale}px)`,
    width: `${(highlight.width || 0) * scale}px`,
    height: `${(highlight.height || 0) * scale}px`,
    transform: `rotate(${rotation}deg)`,
  } : null;

  return (
    <div className="viewer-pane">
      <div className="photo-toolbar">
        <div className="page-switcher">
          {multiPage ? (
            <>
              <button
                type="button"
                className="icon-btn"
                aria-label="Previous page"
                disabled={!canPrev}
                onClick={onPrevPage}
              >
                ‹
              </button>
              <span className="page-switcher-label">
                {pageNumber} / {pageTotal}
              </span>
              <button
                type="button"
                className="icon-btn"
                aria-label="Next page"
                disabled={!canNext}
                onClick={onNextPage}
              >
                ›
              </button>
            </>
          ) : (
            <span className="page-switcher-label single">Page 1</span>
          )}
        </div>
        <div className="tools viewer-tools">
          <button className="icon-btn" type="button" aria-label="Zoom in" onClick={() => setScale((s) => Math.min(4, s * 1.2))}>+</button>
          <button className="icon-btn" type="button" aria-label="Zoom out" onClick={() => setScale((s) => Math.max(0.4, s * 0.8))}>−</button>
          <button className="icon-btn" type="button" aria-label="Fit" onClick={fit}>Fit</button>
          <button className="icon-btn" type="button" aria-label="Rotate" onClick={() => setRotation((r) => r + 90)}>⟲</button>
          {onEdit ? (
            <button className="icon-btn" type="button" aria-label="Edit page image" title="Edit page image" onClick={onEdit}>
              <Icon name="edit" size={16} />
            </button>
          ) : null}
        </div>
      </div>
      <div
        className="canvas"
        ref={wrapRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onWheel={onWheel}
      >
        {src ? (
          <img
            ref={imgRef}
            src={src}
            alt="Result slip"
            onLoad={fit}
            draggable={false}
            style={{ transform: `translate(-50%, -50%) translate(${pan.x}px, ${pan.y}px) scale(${scale}) rotate(${rotation}deg)` }}
          />
        ) : (
          <p className="empty">No page image</p>
        )}
        {highlight && <div className="bbox" style={bboxStyle} />}
      </div>
    </div>
  );
}
