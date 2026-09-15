import { useEffect, useRef, useState } from "react";

export default function Viewer({ src, highlight }) {
  const wrapRef = useRef(null);
  const imgRef = useRef(null);
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [rotation, setRotation] = useState(0);
  const drag = useRef(null);

  const fit = () => {
    const wrap = wrapRef.current;
    const img = imgRef.current;
    if (!wrap || !img || !img.naturalWidth) return;
    const pad = 24;
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
    const img = imgRef.current;
    if (!img) return;
    const onLoad = () => fit();
    img.addEventListener("load", onLoad);
    return () => img.removeEventListener("load", onLoad);
  }, []);

  const onPointerDown = (e) => {
    drag.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
    wrapRef.current.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e) => {
    if (!drag.current) return;
    setPan({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y });
  };
  const onPointerUp = () => { drag.current = null; };

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
      <div className="pane-bar">
        <strong>Slip photograph</strong>
        <div className="tools">
          <button className="btn ghost" type="button" onClick={() => setScale((s) => Math.min(4, s * 1.2))}>Zoom in</button>
          <button className="btn ghost" type="button" onClick={() => setScale((s) => Math.max(0.4, s * 0.8))}>Zoom out</button>
          <button className="btn ghost" type="button" onClick={fit}>Fit</button>
          <button className="btn ghost" type="button" onClick={() => setRotation((r) => r + 90)}>Rotate</button>
          <button className="btn ghost" type="button" onClick={() => { setRotation(0); fit(); }}>Reset</button>
        </div>
      </div>
      <div
        className="canvas"
        ref={wrapRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onWheel={onWheel}
      >
        {src ? (
          <img
            ref={imgRef}
            src={src}
            alt="Result slip"
            onLoad={fit}
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
