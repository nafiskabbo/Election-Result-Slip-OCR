# Digit CNN models + fine-tune pipeline

## Weights (`backend/models/`)

| File | Role |
|------|------|
| `mnist_emnist_blank_cnn_v1.onnx` | Stock MNIST+EMNIST+blank (Plom). Fallback. |
| `digit_cnn_mnist_emnist_aug_v1.onnx` | **Old** hard-augment model. Kept. Not used in the desk. |
| `digit_cnn_iec_hybrid_v2.onnx` | **New** model trained on hybrid-cleaned 4-box crops. Not used in the desk until compare says so. |

Desk production is **heuristic ICR + RapidOCR** (`DIGIT_BACKEND=heuristic`). The CNN is only used when `digit_backend=cnn` or `cnn-hybrid` (accuracy compare).

## Fine-tune scripts (`backend/digit_finetune/`)

Per-cell labels live in `tests/fixtures/sample_gold.json` as `vote_cells` (four entries: digit `0–9` or `null` for empty; Ø is `0`). Export uses the same scale + dash-wipe + box split as hybrid.

```bash
./run.sh digit-export
pip install -r requirements-train.txt
./run.sh digit-train --epochs 6
./run.sh digit-train --include-handwriting --i-confirm-handwriting --epochs 8
./run.sh accuracy --compare-cnn-models --files ResultSlip.jpg,Result_Slip_2024_Previous_Election_Sample.jpg,Result_Slip_2024_Previous_Election_Sample_lower.jpg
```

New weights write to `digit_cnn_iec_hybrid_v2.onnx`. v1 is never overwritten by the default train command.
