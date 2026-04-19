"""Anomaly ROI from CLIP patch-text saliency (plan.md Option B)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import cv2
import numpy as np
import torch

from clip_inference import ClipInspector


@dataclass
class CropResult:
    crop_bgr: np.ndarray
    bbox_xyxy: Tuple[int, int, int, int]


def _percentile_threshold(heatmap: np.ndarray, percentile: float) -> float:
    flat = heatmap.reshape(-1)
    return float(np.percentile(flat, percentile))


def extract_anomaly_crop(
    inspector: ClipInspector,
    frame_bgr: np.ndarray,
    crop_size: int = 500,
    saliency_percentile: float = 90.0,
) -> CropResult:
    direction = inspector.text_direction()
    patch_emb, gh, gw = inspector.patch_embedding_map(frame_bgr)
    scores = torch.matmul(patch_emb, direction).squeeze(0)
    heat = scores.reshape(1, 1, gh, gw)
    heat = torch.nn.functional.interpolate(
        heat.float(),
        size=(frame_bgr.shape[0], frame_bgr.shape[1]),
        mode="bilinear",
        align_corners=False,
    )
    heatmap = heat.squeeze().detach().cpu().numpy()
    heatmap = np.maximum(heatmap, 0)
    thr = _percentile_threshold(heatmap, saliency_percentile)
    mask = heatmap >= thr
    ys, xs = np.where(mask)
    if ys.size == 0 or xs.size == 0:
        h, w = frame_bgr.shape[:2]
        cx, cy = w // 2, h // 2
        x1, y1 = max(cx - crop_size // 2, 0), max(cy - crop_size // 2, 0)
    else:
        y1, y2 = int(ys.min()), int(ys.max())
        x1, x2 = int(xs.min()), int(xs.max())
        cy = (y1 + y2) // 2
        cx = (x1 + x2) // 2
        x1 = max(cx - crop_size // 2, 0)
        y1 = max(cy - crop_size // 2, 0)

    x2 = min(x1 + crop_size, frame_bgr.shape[1])
    y2 = min(y1 + crop_size, frame_bgr.shape[0])
    x1 = max(x2 - crop_size, 0)
    y1 = max(y2 - crop_size, 0)

    crop = frame_bgr[y1:y2, x1:x2].copy()
    if crop.shape[0] != crop_size or crop.shape[1] != crop_size:
        crop = cv2.resize(crop, (crop_size, crop_size), interpolation=cv2.INTER_AREA)
    return CropResult(crop_bgr=crop, bbox_xyxy=(x1, y1, x2, y2))
