"""USB / synthetic frame capture with optional ring buffer."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterator, Optional

import cv2
import numpy as np


@dataclass
class CaptureConfig:
    width: int = 1280
    height: int = 720
    fps: int = 30
    ring_buffer_frames: int = 10
    synthetic: bool = False
    camera_index: int = 0


class FrameRingBuffer:
    def __init__(self, maxlen: int) -> None:
        self._buf: Deque[np.ndarray] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, frame: np.ndarray) -> None:
        with self._lock:
            self._buf.append(frame.copy())

    def latest(self) -> Optional[np.ndarray]:
        with self._lock:
            if not self._buf:
                return None
            return self._buf[-1].copy()


class CameraCapture:
    def __init__(self, cfg: CaptureConfig) -> None:
        self.cfg = cfg
        self._cap: Optional[cv2.VideoCapture] = None
        self._buffer = FrameRingBuffer(cfg.ring_buffer_frames)

    def open(self) -> None:
        if self.cfg.synthetic:
            return
        self._cap = cv2.VideoCapture(self.cfg.camera_index)
        if not self._cap.isOpened():
            raise RuntimeError(
                "Camera not available. Use synthetic mode for CI or headless dev."
            )
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cfg.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cfg.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.cfg.fps)

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def read_frame(self) -> np.ndarray:
        if self.cfg.synthetic:
            return self._synthetic_frame()
        assert self._cap is not None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError("Failed to read camera frame")
        self._buffer.push(frame)
        return frame

    def frames(self, max_frames: Optional[int] = None) -> Iterator[np.ndarray]:
        n = 0
        while max_frames is None or n < max_frames:
            yield self.read_frame()
            n += 1
            if self.cfg.synthetic:
                time.sleep(1.0 / max(self.cfg.fps, 1))

    def _synthetic_frame(self) -> np.ndarray:
        """Deterministic RGB frame for tests (painted panel + mild noise)."""
        h, w = self.cfg.height, self.cfg.width
        base = np.zeros((h, w, 3), dtype=np.uint8)
        base[:] = (40, 55, 70)
        cv2.rectangle(base, (w // 6, h // 4), (5 * w // 6, 3 * h // 4), (120, 140, 160), -1)
        rng = np.random.default_rng(42 + int(time.time() * 1000) % 10_000)
        noise = rng.integers(-8, 9, size=base.shape, dtype=np.int16)
        out = np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        self._buffer.push(out)
        return out
