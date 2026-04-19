"""Lambda-2: anomaly crop validation, Dynamo audit, enqueue VLM work."""

from __future__ import annotations

import base64
import json
import os
import time
from typing import Any, Dict

import boto3

sqs = boto3.client("sqs")
dynamodb = boto3.resource("dynamodb")
QUEUE_URL = os.environ.get("VLM_QUEUE_URL", "")
TABLE_NAME = os.environ.get("ANOMALY_AUDIT_TABLE", "")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    body = event if isinstance(event, dict) and "clip_confidence" in event else {}
    if isinstance(event.get("body"), str):
        try:
            body = json.loads(event["body"])
        except json.JSONDecodeError:
            body = {}

    vin = str(body.get("vin", ""))
    b64 = body.get("crop_jpeg_base64")
    if not vin or not b64:
        return {"ok": False, "error": "invalid_payload"}

    try:
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, TypeError):
        return {"ok": False, "error": "invalid_base64"}

    if len(raw) < 1024:
        return {"ok": False, "error": "crop_too_small"}

    if TABLE_NAME:
        table = dynamodb.Table(TABLE_NAME)
        table.put_item(
            Item={
                "vin": vin,
                "inspection_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "device_id": body.get("device_id", ""),
                "clip_confidence": str(body.get("clip_confidence", "")),
                "ttl": int(time.time()) + 86400 * 365 * 2,
            }
        )

    if QUEUE_URL:
        sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(body))

    return {"ok": True, "enqueued": bool(QUEUE_URL)}
