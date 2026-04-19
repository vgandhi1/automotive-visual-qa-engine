"""MES-style defect/pass logging (DynamoDB when configured, else in-memory)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from models import DefectRecord, HealthResponse, InspectionResult

logger = logging.getLogger("mes")

app = FastAPI(title="Automotive MES Integration", version="0.1.0")

_DEFECT_TABLE = os.environ.get("DEFECT_LOG_TABLE", "")
_METRICS_TABLE = os.environ.get("INSPECTION_METRICS_TABLE", "")
_SNS_TOPIC_ARN = os.environ.get("DEFECT_SNS_TOPIC_ARN", "")

_memory_defects: List[Dict[str, Any]] = []
_memory_passes: List[Dict[str, Any]] = []


def _ddb():
    import boto3

    return boto3.resource("dynamodb")


def _sns():
    import boto3

    return boto3.client("sns")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    backend = "dynamodb" if _DEFECT_TABLE else "memory"
    return HealthResponse(ok=True, backend=backend)


@app.post("/defect/log")
def log_defect(record: DefectRecord) -> JSONResponse:
    item = record.model_dump()
    if _DEFECT_TABLE:
        try:
            _ddb().Table(_DEFECT_TABLE).put_item(Item=item)
        except OSError:
            logger.exception("dynamodb_put_failed")
            raise HTTPException(status_code=503, detail="storage_unavailable")
        if _SNS_TOPIC_ARN:
            try:
                _sns().publish(
                    TopicArn=_SNS_TOPIC_ARN,
                    Message=json.dumps({"type": "defect", "vin": record.vin}),
                )
            except OSError:
                logger.warning("sns_publish_failed")
    else:
        _memory_defects.append(item)
    return JSONResponse({"status": "logged", "vin": record.vin})


@app.post("/inspection/pass")
def log_pass(record: InspectionResult) -> JSONResponse:
    item = record.model_dump()
    if _METRICS_TABLE:
        try:
            _ddb().Table(_METRICS_TABLE).put_item(Item=item)
        except OSError:
            logger.exception("dynamodb_put_failed")
            raise HTTPException(status_code=503, detail="storage_unavailable")
    else:
        _memory_passes.append(item)
    return JSONResponse({"status": "logged", "result": "PASS"})


@app.get("/defect/{vin}")
def get_defect_history(vin: str) -> Any:
    if _DEFECT_TABLE:
        try:
            resp = _ddb().Table(_DEFECT_TABLE).query(
                KeyConditionExpression="vin = :vin",
                ExpressionAttributeValues={":vin": vin},
            )
            return resp.get("Items", [])
        except OSError:
            logger.exception("dynamodb_query_failed")
            raise HTTPException(status_code=503, detail="storage_unavailable")
    return [r for r in _memory_defects if r.get("vin") == vin]
