"""SAP OData or mock rework ticket creation (URL from env only — no user-controlled hosts)."""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Tuple
from urllib.parse import urlparse


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    sap_url = os.environ.get("SAP_API_URL", "")
    if not sap_url:
        return {"ok": False, "error": "sap_not_configured"}

    parsed = urlparse(sap_url)
    if parsed.scheme not in ("https", "http"):
        return {"ok": False, "error": "invalid_scheme"}
    if parsed.hostname in (None, ""):
        return {"ok": False, "error": "invalid_host"}

    vin = str(event.get("vin") or event.get("edge", {}).get("vin") or "")
    vlm = event.get("vlm") or event
    payload = {
        "vin": vin,
        "defect_type": vlm.get("defect_type"),
        "severity": vlm.get("severity"),
        "repair_action": vlm.get("repair_action"),
        "rework_station": vlm.get("rework_station"),
        "plant_location": event.get("plant_location"),
        "creation_time": datetime.now(timezone.utc).isoformat(),
    }

    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("SAP_API_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    status, data = _http_post_json(sap_url, body, headers)
    if status not in (200, 201):
        return {"ok": False, "status": status}
    return {"ok": True, "sap": data}


def _http_post_json(url: str, body: bytes, headers: Dict[str, str]) -> Tuple[int, Any]:
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            raw = resp.read().decode("utf-8")
            status = int(getattr(resp, "status", 200))
            try:
                return status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return status, {"raw": raw}
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            parsed = {"detail": "upstream_error"}
        return int(exc.code), parsed
    except urllib.error.URLError:
        return 0, {"detail": "network_error"}
