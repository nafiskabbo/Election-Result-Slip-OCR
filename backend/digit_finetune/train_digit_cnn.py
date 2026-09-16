"""Fine-tune a digit+blank CNN from MNIST / EMNIST Digits (+ hard IEC augment).

Default: train on public MNIST+EMNIST only (safe to run now).

Handwriting from sample_slips cells is OFF unless you pass BOTH:
  --include-handwriting --i-confirm-handwriting

Usage:
  pip install -r requirements-train.txt
  python -m backend.digit_finetune.export_result_cells
  python -m backend.digit_finetune.train_digit_cnn --epochs 5
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.digit_finetune.hard_augment import BLANK_CLASS, hard_augment_digit, make_blank_canvas

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
DEFAULT_OUT_ONNX = MODELS_DIR / "digit_cnn_mnist_emnist_aug_v1.onnx"
DEFAULT_CELLS = Path(__file__).resolve().parent / "data" / "cells"
RUNS_DIR = Path(__file__).resolve().parent / "runs"


def _require_torch():
    try:
        import torch
        import torch.nn as nn
        import torchvision
        from torch.utils.data import DataLoader, Dataset
    except ImportError as exc:
        raise SystemExit(
            "Training requires torch + torchvision. Install with:\n"
            "  pip install -r requirements-train.txt\n"
            f"({exc})"
        ) from exc
    return torch, nn, torchvision, DataLoader, Dataset


def build_model(nn, num_classes: int = 11):
    """Compact CNN: 28×28 → 11 classes (0–9 + blank)."""

    class DigitBlankCNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv2d(1, 32, 3, padding=1),
                nn.ReLU(inplace=True),
                nn.Conv2d(32, 32, 3, padding=1),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(2),
                nn.Conv2d(32, 64, 3, padding=1),
                nn.ReLU(inplace=True),
                nn.Conv2d(64, 64, 3, padding=1),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(2),
                nn.Dropout(0.25),
            )
            self.classifier = nn.Sequential(
                nn.Flatten(),
                nn.Linear(64 * 7 * 7, 128),
                nn.ReLU(inplace=True),
                nn.Dropout(0.4),
                nn.Linear(128, num_classes),
            )

        def forward(self, x):
            return self.classifier(self.features(x))

    return DigitBlankCNN()


def _load_public_pairs(torchvision, max_per_class: int) -> List[Tuple[np.ndarray, int]]:
    root = RUNS_DIR / "torchvision_data"
    root.mkdir(parents=True, exist_ok=True)
    pairs: List[Tuple[np.ndarray, int]] = []

    mnist = torchvision.datasets.MNIST(root=str(root), train=True, download=True)
    for img, label in mnist:
        arr = np.array(img, dtype=np.uint8)
        pairs.append((arr, int(label)))

    try:
        emnist = torchvision.datasets.EMNIST(
            root=str(root), split="digits", train=True, download=True
        )
        for img, label in emnist:
            # EMNIST digits are often transposed relative to MNIST.
            arr = np.array(img, dtype=np.uint8).T
            pairs.append((arr, int(label)))
    except Exception as exc:  # noqa: BLE001
        print(f"EMNIST Digits unavailable ({exc}); continuing with MNIST only.")

    # Cap per digit class for faster iteration; keep balance.
    by_c: dict = {i: [] for i in range(10)}
    for img, lab in pairs:
        if lab in by_c:
            by_c[lab].append(img)
    capped: List[Tuple[np.ndarray, int]] = []
    for lab, imgs in by_c.items():
        random.shuffle(imgs)
        for img in imgs[:max_per_class]:
            capped.append((img, lab))

    # Synthetic blanks
    for _ in range(max_per_class):
        capped.append((np.zeros((28, 28), dtype=np.uint8), BLANK_CLASS))

    random.shuffle(capped)
    return capped


def _load_handwriting_pairs(cells_dir: Path) -> List[Tuple[np.ndarray, int]]:
    man_path = cells_dir / "manifest.json"
    if not man_path.exists():
        raise SystemExit(f"No cell manifest at {man_path}. Run export_result_cells first.")
    payload = json.loads(man_path.read_text(encoding="utf-8"))
    pairs: List[Tuple[np.ndarray, int]] = []
    for entry in payload.get("cells") or []:
        if entry.get("label_source") != "gold_decompose":
            continue
        label = entry.get("label")
        path = cells_dir / entry["file"]
        if not path.exists():
            continue
        cell = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if cell is None:
            continue
        if label is None:
            pairs.append((cell, BLANK_CLASS))
        else:
            pairs.append((cell, int(label)))
    print(f"Loaded {len(pairs)} gold-decomposed handwriting cells from {cells_dir}")
    return pairs


def train(
    *,
    epochs: int = 5,
    batch_size: int = 128,
    lr: float = 1e-3,
    max_per_class: int = 4000,
    include_handwriting: bool = False,
    confirm_handwriting: bool = False,
    cells_dir: Path = DEFAULT_CELLS,
    out_onnx: Path = DEFAULT_OUT_ONNX,
    seed: int = 42,
) -> Path:
    torch, nn, torchvision, DataLoader, Dataset = _require_torch()
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    if include_handwriting and not confirm_handwriting:
        raise SystemExit(
            "Refusing to train on actual written slip cells without confirmation.\n"
            "Re-run with: --include-handwriting --i-confirm-handwriting"
        )

    pairs = _load_public_pairs(torchvision, max_per_class=max_per_class)
    if include_handwriting and confirm_handwriting:
        hw = _load_handwriting_pairs(cells_dir)
        # Oversample handwriting so it is not drowned by MNIST.
        for _ in range(8):
            pairs.extend(hw)
        random.shuffle(pairs)

    class AugDataset(Dataset):
        def __init__(self, items):
            self.items = items

        def __len__(self):
            return len(self.items)

        def __getitem__(self, idx):
            img, lab = self.items[idx]
            aug, lab2 = hard_augment_digit(img, int(lab))
            x = torch.from_numpy(aug).unsqueeze(0)
            y = torch.tensor(lab2, dtype=torch.long)
            return x, y

    n = len(pairs)
    n_val = max(500, int(n * 0.08))
    val_items = pairs[:n_val]
    train_items = pairs[n_val:]
    train_loader = DataLoader(AugDataset(train_items), batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(AugDataset(val_items), batch_size=batch_size, shuffle=False, num_workers=0)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(nn).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    crit = nn.CrossEntropyLoss()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    best_acc = -1.0
    best_path = RUNS_DIR / "best_digit_blank.pt"

    for epoch in range(1, epochs + 1):
        model.train()
        total, correct, loss_sum = 0, 0, 0.0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            opt.zero_grad()
            logits = model(x)
            loss = crit(logits, y)
            loss.backward()
            opt.step()
            loss_sum += float(loss.item()) * x.size(0)
            pred = logits.argmax(1)
            correct += int((pred == y).sum().item())
            total += x.size(0)
        train_acc = correct / max(1, total)

        model.eval()
        v_total, v_correct = 0, 0
        with torch.no_grad():
            for x, y in val_loader:
                x, y = x.to(device), y.to(device)
                pred = model(x).argmax(1)
                v_correct += int((pred == y).sum().item())
                v_total += x.size(0)
        val_acc = v_correct / max(1, v_total)
        print(
            f"epoch {epoch}/{epochs}  loss={loss_sum/max(1,total):.4f}  "
            f"train_acc={train_acc:.3f}  val_acc={val_acc:.3f}"
        )
        if val_acc >= best_acc:
            best_acc = val_acc
            torch.save({"model": model.state_dict(), "val_acc": val_acc, "epoch": epoch}, best_path)

    # Load best and export ONNX
    ckpt = torch.load(best_path, map_location=device, weights_only=False)
    model.load_state_dict(ckpt["model"])
    model.eval()
    out_onnx.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.zeros(1, 1, 28, 28, device=device)
    torch.onnx.export(
        model,
        dummy,
        str(out_onnx),
        input_names=["input"],
        output_names=["logits"],
        dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
        dynamo=False,
    )
    print(f"Exported ONNX → {out_onnx} (best val_acc={best_acc:.3f})")
    # Touch blank path so import side-effects stay quiet
    _ = make_blank_canvas()
    return out_onnx


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--batch-size", type=int, default=128)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--max-per-class", type=int, default=4000)
    p.add_argument(
        "--include-handwriting",
        action="store_true",
        help="Include gold-decomposed sample_slips cells (requires confirmation flag).",
    )
    p.add_argument(
        "--i-confirm-handwriting",
        action="store_true",
        help="Required with --include-handwriting to train on actual written text.",
    )
    p.add_argument("--cells-dir", type=Path, default=DEFAULT_CELLS)
    p.add_argument("--out-onnx", type=Path, default=DEFAULT_OUT_ONNX)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)
    train(
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        max_per_class=args.max_per_class,
        include_handwriting=args.include_handwriting,
        confirm_handwriting=args.i_confirm_handwriting,
        cells_dir=args.cells_dir,
        out_onnx=args.out_onnx,
        seed=args.seed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
