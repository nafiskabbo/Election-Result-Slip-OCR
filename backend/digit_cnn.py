"""Handwritten digit CNN (MNIST + EMNIST Digits + blank) for RESULT boxes.

Experimental alternative to heuristic ICR. Production hybrid does not use this
unless digit_backend is ``cnn`` or ``cnn-hybrid``.

v1 = MNIST/EMNIST + heavy dashed-box augment (kept on disk).
v2 = hybrid-cleaned IEC cells + residual-dash / resolution augment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

MODEL_NAME = "mnist_emnist_blank_cnn_v1.onnx"
AUG_MODEL_NAME = "digit_cnn_mnist_emnist_aug_v1.onnx"
HYBRID_MODEL_NAME = "digit_cnn_iec_hybrid_v2.onnx"
MODEL_PATH = Path(__file__).resolve().parent / "models" / MODEL_NAME
AUG_MODEL_PATH = Path(__file__).resolve().parent / "models" / AUG_MODEL_NAME
HYBRID_MODEL_PATH = Path(__file__).resolve().parent / "models" / HYBRID_MODEL_NAME
MODEL_URL = (
    "https://huggingface.co/deepshah23/digit-blank-classifier-cnn/"
    f"resolve/main/{MODEL_NAME}"
)
BLANK_CLASS = 10

_sessions: Dict[str, object] = {}
_load_errors: Dict[str, str] = {}
_requested_model = "v1"
_active_model: Optional[str] = None
_load_error: Optional[str] = None


def _normalize_model_key(name: Optional[str]) -> str:
    raw = (name or _requested_model or "v1").strip().lower()
    if raw in {"v2", "hybrid", "new", HYBRID_MODEL_NAME.lower()}:
        return "v2"
    if raw in {"stock", "base", MODEL_NAME.lower()}:
        return "stock"
    return "v1"


def set_active_model(name: str) -> None:
    """Select v1 (old) or v2 (hybrid-trained) for subsequent classify calls."""
    global _requested_model, _load_error, _active_model
    _requested_model = _normalize_model_key(name)
    _load_error = _load_errors.get(_requested_model)
    path = model_path_for(_requested_model)
    _active_model = path.name if path is not None else None


def hybrid_model_available() -> bool:
    return HYBRID_MODEL_PATH.exists() and HYBRID_MODEL_PATH.stat().st_size > 1000


def model_path_for(key: str) -> Optional[Path]:
    key = _normalize_model_key(key)
    if key == "v2" and hybrid_model_available():
        return HYBRID_MODEL_PATH
    if key == "stock" and MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 1000:
        return MODEL_PATH
    if AUG_MODEL_PATH.exists() and AUG_MODEL_PATH.stat().st_size > 1000:
        return AUG_MODEL_PATH
    if MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 1000:
        return MODEL_PATH
    return None


def model_available() -> bool:
    return model_path_for("v1") is not None or hybrid_model_available()


def ensure_model() -> Path:
    """Return local ONNX path for the requested model; never overwrite v1."""
    key = _normalize_model_key(_requested_model)
    path = model_path_for(key)
    if path is not None:
        return path
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    from urllib.request import urlretrieve

    urlretrieve(MODEL_URL, MODEL_PATH)
    if not (MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 1000):
        raise RuntimeError(f"Failed to download digit CNN model to {MODEL_PATH}")
    return MODEL_PATH


def _get_session(key: Optional[str] = None):
    global _load_error, _active_model
    model_key = _normalize_model_key(key)
    if model_key in _sessions:
        return _sessions[model_key]
    if model_key in _load_errors:
        _load_error = _load_errors[model_key]
        return None
    try:
        import onnxruntime as ort

        path = model_path_for(model_key)
        if path is None:
            if model_key == "v2":
                _load_errors[model_key] = f"missing {HYBRID_MODEL_NAME}"
                _load_error = _load_errors[model_key]
                return None
            path = ensure_model()
        sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        _sessions[model_key] = sess
        _active_model = path.name
        return sess
    except Exception as exc:  # noqa: BLE001
        _load_errors[model_key] = str(exc)
        _load_error = str(exc)
        return None


def active_model_name() -> Optional[str]:
    if not model_available():
        return None
    if _active_model:
        return _active_model
    path = model_path_for(_requested_model)
    return path.name if path is not None else None


def cell_to_mnist_tensor(cell_bgr: np.ndarray) -> Tuple[np.ndarray, float]:
    """Crop border, keep ink blob, center on 28×28 white-on-black MNIST canvas."""
    return _cell_to_tensor(cell_bgr, crop_frac=0.22, min_ink=45)


def cell_to_hybrid_tensor(cell_bgr: np.ndarray) -> Tuple[np.ndarray, float]:
    """Milder crop for dash-wiped hybrid cells (keep faint centered 1s)."""
    return _cell_to_tensor(cell_bgr, crop_frac=0.10, min_ink=28)


def _cell_to_tensor(
    cell_bgr: np.ndarray,
    *,
    crop_frac: float,
    min_ink: int,
) -> Tuple[np.ndarray, float]:
    if cell_bgr is None or cell_bgr.size == 0:
        return np.zeros((28, 28), dtype=np.float32), 0.0
    g = cv2.cvtColor(cell_bgr, cv2.COLOR_BGR2GRAY) if cell_bgr.ndim == 3 else cell_bgr
    h, w = g.shape[:2]
    m = max(2, int(min(h, w) * crop_frac))
    g = g[m : h - m, m : w - m]
    if g.size == 0:
        return np.zeros((28, 28), dtype=np.float32), 0.0
    g = cv2.GaussianBlur(g, (3, 3), 0)
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(th)
    out = np.zeros_like(th)
    ink = 0
    for i in range(1, num):
        x, y, bw, bh, area = stats[i]
        if area < 28:
            continue
        aspect = bh / float(max(1, bw))
        cx = (x + bw / 2.0) / float(out.shape[1])
        if bw <= 5 and aspect > 2.5 and (cx < 0.20 or cx > 0.80):
            continue
        if bh <= 5 and bw > 16:
            continue
        if bw >= g.shape[1] * 0.72 and bh <= g.shape[0] * 0.22:
            continue
        if bh >= g.shape[0] * 0.72 and bw <= g.shape[1] * 0.22:
            continue
        out[labels == i] = 255
        ink += int(area)

    dens = ink / float(max(1, out.size))
    if ink < min_ink:
        return np.zeros((28, 28), dtype=np.float32), dens

    ys, xs = np.where(out > 0)
    digit = out[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    dh, dw = digit.shape
    scale = 20.0 / float(max(dh, dw, 1))
    nh = max(1, int(round(dh * scale)))
    nw = max(1, int(round(dw * scale)))
    digit = cv2.resize(digit, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((28, 28), dtype=np.uint8)
    yoff = (28 - nh) // 2
    xoff = (28 - nw) // 2
    canvas[yoff : yoff + nh, xoff : xoff + nw] = digit
    return canvas.astype(np.float32) / 255.0, dens


def classify_cell_cnn(
    cell_bgr: np.ndarray,
    *,
    model: Optional[str] = None,
) -> Tuple[Optional[int], float]:
    """Return (digit or None for empty/blank, confidence)."""
    key = _normalize_model_key(model)
    tensor_fn = cell_to_hybrid_tensor if key == "v2" else cell_to_mnist_tensor
    tensor, dens = tensor_fn(cell_bgr)
    min_dens = 0.008 if key == "v2" else 0.012
    if dens < min_dens:
        return None, 0.92

    sess = _get_session(key)
    if sess is None:
        return None, 0.0

    inp = tensor.reshape(1, 1, 28, 28)
    logits = sess.run(None, {"input": inp})[0][0]
    exp = np.exp(logits - float(np.max(logits)))
    probs = exp / float(np.sum(exp))
    idx = int(np.argmax(probs))
    conf = float(probs[idx])
    blank_p = float(probs[BLANK_CLASS]) if len(probs) > BLANK_CLASS else 0.0
    if idx == BLANK_CLASS:
        return None, conf
    if conf < 0.58 or blank_p >= conf * 0.75:
        return None, max(conf, blank_p)
    return idx, conf


def load_error() -> Optional[str]:
    return _load_error
