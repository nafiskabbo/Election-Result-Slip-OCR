"""Hard augmentations for IEC-style RESULT digit cells (MNIST/EMNIST fine-tune)."""

from __future__ import annotations

import random
from typing import Optional, Tuple

import cv2
import numpy as np

BLANK_CLASS = 10


def _to_u8(img: np.ndarray) -> np.ndarray:
    if img.dtype == np.uint8:
        return img
    x = np.clip(img, 0.0, 1.0) if img.max() <= 1.0 + 1e-6 else img
    if x.max() <= 1.0 + 1e-6:
        return (x * 255.0).astype(np.uint8)
    return np.clip(x, 0, 255).astype(np.uint8)


def ink_on_black(img: np.ndarray) -> np.ndarray:
    """Return 28×28 (or HxW) white-ink-on-black like MNIST."""
    g = _to_u8(img)
    if g.ndim == 3:
        g = cv2.cvtColor(g, cv2.COLOR_BGR2GRAY)
    # If mostly white background, invert so ink is bright.
    if float(np.mean(g)) > 127:
        g = 255 - g
    return g


def draw_dashed_box(canvas: np.ndarray, *, density: float = 0.55) -> np.ndarray:
    """Overlay IEC-like dashed box borders on a digit canvas (ink-on-black)."""
    out = canvas.copy()
    h, w = out.shape[:2]
    color = int(random.randint(140, 230))
    thickness = 1 if min(h, w) < 40 else random.choice([1, 1, 2])
    # Outer rectangle
    cv2.rectangle(out, (1, 1), (w - 2, h - 2), color, thickness)
    # Dashes: punch gaps
    gap = max(2, int(min(h, w) * 0.08))
    for edge in ("top", "bottom", "left", "right"):
        if edge in ("top", "bottom"):
            y = 1 if edge == "top" else h - 2
            x = 2
            while x < w - 2:
                if random.random() > density:
                    out[max(0, y - thickness) : y + thickness + 1, x : min(w, x + gap)] = 0
                x += gap * 2
        else:
            x = 1 if edge == "left" else w - 2
            y = 2
            while y < h - 2:
                if random.random() > density:
                    out[y : min(h, y + gap), max(0, x - thickness) : x + thickness + 1] = 0
                y += gap * 2
    return out


def slash_zero(canvas: np.ndarray) -> np.ndarray:
    """Draw a diagonal slash through a zero (Ø style)."""
    out = canvas.copy()
    h, w = out.shape[:2]
    color = int(random.randint(160, 255))
    thickness = max(1, min(h, w) // 14)
    cv2.line(out, (int(w * 0.25), int(h * 0.75)), (int(w * 0.75), int(h * 0.25)), color, thickness)
    return out


def morph_thickness(canvas: np.ndarray, thicker: bool) -> np.ndarray:
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    if thicker:
        return cv2.dilate(canvas, k, iterations=random.randint(1, 2))
    return cv2.erode(canvas, k, iterations=1)


def elasticish(canvas: np.ndarray, alpha: float = 4.0, sigma: float = 3.0) -> np.ndarray:
    """Cheap elastic-style warp via smoothed random displacement."""
    h, w = canvas.shape[:2]
    dx = cv2.GaussianBlur((np.random.rand(h, w) * 2 - 1).astype(np.float32), (0, 0), sigma) * alpha
    dy = cv2.GaussianBlur((np.random.rand(h, w) * 2 - 1).astype(np.float32), (0, 0), sigma) * alpha
    xs, ys = np.meshgrid(np.arange(w), np.arange(h))
    map_x = (xs + dx).astype(np.float32)
    map_y = (ys + dy).astype(np.float32)
    return cv2.remap(canvas, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)


def hard_augment_digit(
    img: np.ndarray,
    label: int,
    *,
    size: int = 28,
    force_box: Optional[bool] = None,
) -> Tuple[np.ndarray, int]:
    """Apply aggressive IEC-domain augment; may rewrite label 0→0 with slash.

    Returns (28×28 float32 [0,1] ink-on-black, label).
    Blank class (10) stays mostly empty with optional dashed box / noise.
    """
    g = ink_on_black(img)
    if g.shape[0] != size or g.shape[1] != size:
        g = cv2.resize(g, (size, size), interpolation=cv2.INTER_AREA)

    if label == BLANK_CLASS:
        canvas = np.zeros((size, size), dtype=np.uint8)
        if random.random() < 0.75 or force_box:
            canvas = draw_dashed_box(canvas, density=random.uniform(0.35, 0.7))
        if random.random() < 0.35:
            noise = (np.random.randn(size, size) * random.uniform(4, 14)).astype(np.float32)
            canvas = np.clip(canvas.astype(np.float32) + noise, 0, 255).astype(np.uint8)
        if random.random() < 0.25:
            canvas = cv2.GaussianBlur(canvas, (3, 3), 0)
        return canvas.astype(np.float32) / 255.0, BLANK_CLASS

    # Geometric
    angle = random.uniform(-22, 22)
    scale = random.uniform(0.75, 1.25)
    tx = random.uniform(-0.12, 0.12) * size
    ty = random.uniform(-0.12, 0.12) * size
    M = cv2.getRotationMatrix2D((size / 2, size / 2), angle, scale)
    M[0, 2] += tx
    M[1, 2] += ty
    g = cv2.warpAffine(g, M, (size, size), flags=cv2.INTER_LINEAR, borderValue=0)

    if random.random() < 0.55:
        g = elasticish(g, alpha=random.uniform(2.5, 6.0), sigma=random.uniform(2.0, 4.0))

    if random.random() < 0.45:
        pts1 = np.float32([[2, 2], [size - 3, 1], [1, size - 3]])
        jitter = random.uniform(-2.5, 2.5)
        pts2 = np.float32(
            [
                [2 + jitter, 2 - jitter],
                [size - 3 - jitter, 1 + jitter],
                [1 + jitter, size - 3 - jitter],
            ]
        )
        M2 = cv2.getAffineTransform(pts1, pts2)
        g = cv2.warpAffine(g, M2, (size, size), borderValue=0)

    if random.random() < 0.5:
        g = morph_thickness(g, thicker=random.random() < 0.6)

    # Slashed zero (common on IEC slips)
    if label == 0 and random.random() < 0.55:
        g = slash_zero(g)

    # Photocopy / phone-photo noise
    if random.random() < 0.6:
        noise = (np.random.randn(size, size) * random.uniform(6, 22)).astype(np.float32)
        g = np.clip(g.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    if random.random() < 0.4:
        g = cv2.GaussianBlur(g, (3, 3), random.uniform(0.2, 1.1))
    if random.random() < 0.35:
        alpha = random.uniform(0.7, 1.45)
        beta = random.uniform(-25, 25)
        g = np.clip(g.astype(np.float32) * alpha + beta, 0, 255).astype(np.uint8)

    # Dashed RESULT box border (critical domain gap)
    if force_box is True or (force_box is None and random.random() < 0.85):
        g = draw_dashed_box(g, density=random.uniform(0.3, 0.75))

    # Speckle / dropouts
    if random.random() < 0.3:
        mask = np.random.rand(size, size) < 0.02
        g = g.copy()
        g[mask] = 0

    return g.astype(np.float32) / 255.0, int(label)


def make_blank_canvas(size: int = 28) -> np.ndarray:
    return np.zeros((size, size), dtype=np.float32)
