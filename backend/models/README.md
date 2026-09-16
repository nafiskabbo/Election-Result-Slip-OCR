# Digit CNN models + fine-tune pipeline

## Weights (`backend/models/`)

| File | Role |
|------|------|
| `mnist_emnist_blank_cnn_v1.onnx` | Stock MNIST+EMNIST+blank (Plom). Fallback. |
| `digit_cnn_mnist_emnist_aug_v1.onnx` | Hard-augment + handwriting fine-tune output. |

Source for stock weights: [deepshah23/digit-blank-classifier-cnn](https://huggingface.co/deepshah23/digit-blank-classifier-cnn)

Desk production still uses heuristic ICR (`digit_icr.py`) + RapidOCR small for print / RESULT-box fallback. The fine-tuned ONNX is used when `digit_backend=cnn` (accuracy compare).

## Fine-tune scripts (`backend/digit_finetune/`)

```bash
./run.sh digit-export
pip install -r requirements-train.txt
./run.sh digit-train --epochs 5
# with real slip handwriting (confirmed):
./run.sh digit-train --include-handwriting --i-confirm-handwriting
```

Cell crops live in `backend/digit_finetune/data/cells/` (gitignored). Drop extra AI digit images there later and extend the manifest after reviewing accuracy.
