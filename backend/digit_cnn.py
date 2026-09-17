"""Handwritten digit CNN (MNIST + EMNIST Digits + blank) for RESULT boxes.

Model: deepshah23/digit-blank-classifier-cnn (Plom exam-box digit ONNX).
Classes 0–9 = digits, class 10 = blank/empty.

This is an experimental alternative to the heuristic ICR in digit_icr.py.
It is not trained on IEC dashed boxes or slashed zeros (Ø).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

MODEL_NAME = "mnist_emnist_blank_cnn_v1.onnx"
AUG_MODEL_NAME = "digit_cnn_mnist_emnist_aug_v1.onnx"
MODEL_PATH = Path(__file__).resolve().parent / "models" / MODEL_NAME
AUG_MODEL_PATH = Path(__file__).resolve().parent / "models" / AUG_MODEL_NAME
MODEL_URL = (
    "https://huggingface.co/deepshah23/digit-blank-classifier-cnn/"
    f"resolve/main/{MODEL_NAME}"
)
BLANK_CLASS = 10

_session = None
_load_error: Optional[str] = None
_active_model: Optional[str] = None


def model_available() -> bool:
    for path in (AUG_MODEL_PATH, MODEL_PATH):
        if path.exists() and path.stat().st_size > 1000:
            return True
    return False


def ensure_model() -> Path:
    """Return local ONNX path; prefer hard-augment fine-tune if present."""
    if AUG_MODEL_PATH.exists() and AUG_MODEL_PATH.stat().st_size > 1000:
        return AUG_MODEL_PATH
    if MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 1000:
        return MODEL_PATH
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    from urllib.request import urlretrieve

    urlretrieve(MODEL_URL, MODEL_PATH)
    if not (MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 1000):
        raise RuntimeError(f"Failed to download digit CNN model to {MODEL_PATH}")
    return MODEL_PATH


def _get_session():
    global _session, _load_error, _active_model
    if _session is not None:
        return _session
    if _load_error:
        return None
    try:
        import onnxruntime as ort

        path = ensure_model()
        _active_model = path.name
        _session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        return _session
    except Exception as exc:  # noqa: BLE001 — surface as soft failure for accuracy compare
        _load_error = str(exc)
        return None


def active_model_name() -> Optional[str]:
    ensure = model_available()
    if not ensure:
        return None
    if _active_model:
        return _active_model
    if AUG_MODEL_PATH.exists() and AUG_MODEL_PATH.stat().st_size > 1000:
        return AUG_MODEL_NAME
    return MODEL_NAME


def cell_to_mnist_tensor(cell_bgr: np.ndarray) -> Tuple[np.ndarray, float]:
    """Crop border, keep ink blob, center on 28×28 white-on-black MNIST canvas."""
    if cell_bgr is None or cell_bgr.size == 0:
        return np.zeros((28, 28), dtype=np.float32), 0.0
    g = cv2.cvtColor(cell_bgr, cv2.COLOR_BGR2GRAY) if cell_bgr.ndim == 3 else cell_bgr
    h, w = g.shape[:2]
    m = max(2, int(min(h, w) * 0.22))
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
        # Drop long border-hugging dashes (IEC box rules).
        if bw >= g.shape[1] * 0.72 and bh <= g.shape[0] * 0.22:
            continue
        if bh >= g.shape[0] * 0.72 and bw <= g.shape[1] * 0.22:
            continue
        out[labels == i] = 255
        ink += int(area)

    dens = ink / float(max(1, out.size))
    if ink < 45:
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


def classify_cell_cnn(cell_bgr: np.ndarray) -> Tuple[Optional[int], float]:
    """Return (digit or None for empty/blank, confidence)."""
    tensor, dens = cell_to_mnist_tensor(cell_bgr)
    if dens < 0.012:
        return None, 0.92

    sess = _get_session()
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
    # Prefer blank when the digit call is weak or dashed-box noise competes.
    if conf < 0.58 or blank_p >= conf * 0.75:
        return None, max(conf, blank_p)
    return idx, conf


def load_error() -> Optional[str]:
    return _load_error
