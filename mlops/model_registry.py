"""Model registry metadata helpers (SageMaker / DynamoDB integration points)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ModelRecord:
    model_id: str
    version: str
    s3_path: str
    sha256_checksum: str
    deployment_status: str


def record_to_item(rec: ModelRecord) -> Dict[str, Any]:
    return {
        "model_id": rec.model_id,
        "version": rec.version,
        "s3_path": rec.s3_path,
        "sha256_checksum": rec.sha256_checksum,
        "deployment_status": rec.deployment_status,
    }


def parse_item(item: Dict[str, Any]) -> Optional[ModelRecord]:
    try:
        return ModelRecord(
            model_id=str(item["model_id"]),
            version=str(item["version"]),
            s3_path=str(item["s3_path"]),
            sha256_checksum=str(item["sha256_checksum"]),
            deployment_status=str(item.get("deployment_status", "UNKNOWN")),
        )
    except KeyError:
        return None
