"""Device Shadow / OTA metadata (local file stub for dev; boto3 on device)."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelVersions:
    clip_model_version: str
    vlm_model_version: str
    prompts_version: str
    timestamp: str


class ModelManager:
    def __init__(self, shadow_path: Path) -> None:
        self.shadow_path = shadow_path
        shadow_path.parent.mkdir(parents=True, exist_ok=True)
        if not shadow_path.exists():
            self._write_default()

    def _write_default(self) -> None:
        payload = {
            "state": {
                "reported": {
                    "clip_model_version": "openai/clip-vit-base-patch32",
                    "vlm_model_version": "stub",
                    "prompts_version": "1",
                    "timestamp": "1970-01-01T00:00:00Z",
                }
            }
        }
        self.shadow_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def read_reported(self) -> Dict[str, Any]:
        data = json.loads(self.shadow_path.read_text(encoding="utf-8"))
        return dict(data.get("state", {}).get("reported", {}))

    def verify_checksum(self, file_path: Path, expected_sha256: str) -> bool:
        h = hashlib.sha256()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        ok = h.hexdigest() == expected_sha256
        if not ok:
            logger.error("Checksum mismatch for artifact (expected digest did not match)")
        return ok
