"""Evaluation helpers (precision/recall stubs for portfolio wiring)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class BinaryMetrics:
    precision: float
    recall: float
    f1: float


def confusion_counts(y_true: List[int], y_pred: List[int]) -> Tuple[int, int, int, int]:
    tp = fp = tn = fn = 0
    for t, p in zip(y_true, y_pred):
        if t == 1 and p == 1:
            tp += 1
        elif t == 0 and p == 1:
            fp += 1
        elif t == 0 and p == 0:
            tn += 1
        else:
            fn += 1
    return tp, fp, tn, fn


def binary_metrics(y_true: List[int], y_pred: List[int]) -> BinaryMetrics:
    tp, fp, tn, fn = confusion_counts(y_true, y_pred)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return BinaryMetrics(precision=precision, recall=recall, f1=f1)


def to_json(metrics: BinaryMetrics) -> Dict[str, float]:
    return {"precision": metrics.precision, "recall": metrics.recall, "f1": metrics.f1}
