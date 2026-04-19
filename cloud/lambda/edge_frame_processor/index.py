"""Lambda-1: high-confidence PASS/FAIL path — metrics + optional S3 archive."""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any, Dict

import boto3

s3 = boto3.client("s3")
cloudwatch = boto3.client("cloudwatch")
BUCKET = os.environ.get("INSPECTION_BUCKET", "")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    body = _coerce_body(event)
    vin = str(body.get("vin", ""))
    if not vin:
        return {"ok": False, "error": "missing_vin"}

    confidence = float(body.get("clip_confidence", 0.0))
    label = str(body.get("clip_label", ""))
    cloudwatch.put_metric_data(
        Namespace="automotive/quality/edge",
        MetricData=[
            {
                "MetricName": "ClipConfidence",
                "Dimensions": [{"Name": "vin", "Value": vin[:8]}],
                "Value": confidence * 100.0,
                "Unit": "None",
            },
            {
                "MetricName": "PassFrame",
                "Value": 1.0 if label == "PASS" else 0.0,
                "Unit": "Count",
            },
        ],
    )

    if BUCKET and body.get("frame_jpeg_base64"):
        raw = base64.b64decode(body["frame_jpeg_base64"])
        key = f"images/raw/{time.strftime('%Y/%m/%d')}/vehicle-{vin}-{int(time.time())}.jpg"
        s3.put_object(Bucket=BUCKET, Key=key, Body=raw, ContentType="image/jpeg")

    return {"ok": True, "vin": vin, "recorded": True}


def _coerce_body(event: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(event.get("body"), str):
        try:
            return json.loads(event["body"])
        except json.JSONDecodeError:
            return {}
    return event
