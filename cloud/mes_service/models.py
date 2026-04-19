from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DefectRecord(BaseModel):
    vin: str
    inspection_time: str
    defect_type: str
    severity: str
    location_description: str
    repair_action: str
    rework_station: str
    image_s3_url: str
    clip_confidence: float
    vlm_confidence: float
    vlm_model_version: str = Field(default="stub")


class InspectionResult(BaseModel):
    vin: str
    result: str
    inspection_time: str
    image_s3_url: str
    clip_confidence: float


class HealthResponse(BaseModel):
    ok: bool
    backend: str
