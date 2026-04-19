"""Lambda-4: map VLM output to plant route + SAP payload."""

from __future__ import annotations

from typing import Any, Dict


_STATION_MAP = {
    "paint_touch_up_bay": {"plant_location": "Building_3_Line_2", "cost_center": "CC-PAINT"},
    "full_repaint_booth": {"plant_location": "Building_3_Line_2", "cost_center": "CC-PAINT"},
    "weld_rework_bay": {"plant_location": "Building_1_Line_1", "cost_center": "CC-WELD"},
    "body_shop": {"plant_location": "Building_2_Line_1", "cost_center": "CC-BODY"},
    "manual_review": {"plant_location": "QC_OFFICE", "cost_center": "CC-QC"},
}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    vlm = event.get("vlm") or event
    station = str(vlm.get("rework_station", "manual_review"))
    meta = _STATION_MAP.get(station, _STATION_MAP["manual_review"])
    return {
        "rework_station": station,
        "plant_location": meta["plant_location"],
        "cost_center": meta["cost_center"],
        "defect_type": vlm.get("defect_type"),
        "severity": vlm.get("severity"),
        "repair_action": vlm.get("repair_action"),
        "vlm_confidence": vlm.get("confidence"),
    }
