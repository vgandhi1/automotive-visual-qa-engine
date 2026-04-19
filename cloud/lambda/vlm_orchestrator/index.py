"""Lambda-3: VLM invoke (or stub) + schema validation + Step Functions start."""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Dict, List, Tuple

import boto3

sfn = boto3.client("stepfunctions")
sm_runtime = boto3.client("sagemaker-runtime")
STATE_MACHINE_ARN = os.environ.get("REWORK_STATE_MACHINE_ARN", "")
ENDPOINT_NAME = os.environ.get("VLM_ENDPOINT_NAME", "")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    records = event.get("Records", [])
    if not records:
        return {"ok": False, "error": "no_records"}
    out: List[Dict[str, Any]] = []
    for rec in records:
        body = json.loads(rec["body"])
        vlm_json = _invoke_vlm(body)
        ok, err = _validate(vlm_json)
        if not ok:
            vlm_json = _manual_review_payload(body, err or "validation_failed")
        if STATE_MACHINE_ARN:
            exec_name = f"{_safe_execution_name(body.get('vin', 'unknown'))}-{uuid.uuid4().hex[:10]}"
            sfn.start_execution(
                stateMachineArn=STATE_MACHINE_ARN,
                name=exec_name[:80],
                input=json.dumps({"vlm": vlm_json, "edge": body}),
            )
        out.append({"vlm": vlm_json})
    return {"ok": True, "results": out}


def _invoke_vlm(body: Dict[str, Any]) -> Dict[str, Any]:
    if not ENDPOINT_NAME:
        return {
            "defect_type": "scratch",
            "severity": "minor",
            "location_description": "stubbed location",
            "repair_action": "sand and spot repaint",
            "rework_station": "paint_touch_up_bay",
            "repair_time_minutes": 30,
            "confidence": 0.9,
        }
    # Production path: call SageMaker endpoint with image bytes / payload format per model container.
    _ = body  # Reserved for image payload mapping
    response = sm_runtime.invoke_endpoint(
        EndpointName=ENDPOINT_NAME,
        ContentType="application/json",
        Body=json.dumps({"prompt": "return json per template", "edge": body}).encode(),
    )
    payload = response["Body"].read().decode("utf-8")
    return json.loads(payload)


_ALLOWED_DEFECT = {
    "scratch",
    "paint_drip",
    "weld_defect",
    "dent",
    "blister",
    "overspray",
    "contamination",
    "unknown",
}


def _validate(v: Dict[str, Any]) -> Tuple[bool, str | None]:
    try:
        if v.get("defect_type") not in _ALLOWED_DEFECT:
            return False, "defect_type"
        if v.get("severity") not in ("minor", "moderate", "major"):
            return False, "severity"
        if not isinstance(v.get("repair_action"), str):
            return False, "repair_action"
        if not isinstance(v.get("rework_station"), str):
            return False, "rework_station"
        conf = float(v.get("confidence", 0.0))
        if conf < 0 or conf > 1:
            return False, "confidence"
    except (TypeError, ValueError):
        return False, "schema"
    return True, None


def _manual_review_payload(body: Dict[str, Any], reason: str) -> Dict[str, Any]:
    return {
        "defect_type": "unknown",
        "severity": "moderate",
        "location_description": "manual_review",
        "repair_action": "manual_review",
        "rework_station": "manual_review",
        "repair_time_minutes": 0,
        "confidence": 0.0,
        "manual_review_reason": reason,
        "edge_vin": body.get("vin", ""),
    }


def _safe_execution_name(vin: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", str(vin))[:72]
    return safe or "execution"
