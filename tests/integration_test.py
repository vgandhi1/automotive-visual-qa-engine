"""Local integration checks for cloud Lambda handlers (no AWS required)."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ROOT = Path(__file__).resolve().parents[1]


def test_rework_router_maps_station() -> None:
    mod = _load("rework_router", ROOT / "cloud/lambda/rework_router/index.py")
    out = mod.handler({"vlm": {"rework_station": "weld_rework_bay", "defect_type": "weld_defect"}}, None)
    assert out["plant_location"] == "Building_1_Line_1"


def test_edge_frame_processor_metrics_only(monkeypatch) -> None:
    mod = _load("edge_frame", ROOT / "cloud/lambda/edge_frame_processor/index.py")

    class _FakeCW:
        def put_metric_data(self, **_kwargs):
            return {}

    monkeypatch.setattr(mod, "cloudwatch", _FakeCW())
    out = mod.handler({"vin": "TESTVIN1234567890", "clip_label": "PASS", "clip_confidence": 0.91}, None)
    assert out["ok"] is True


def test_vlm_orchestrator_stub_starts_no_sfn_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("REWORK_STATE_MACHINE_ARN", raising=False)
    mod = _load("vlm", ROOT / "cloud/lambda/vlm_orchestrator/index.py")
    evt = {"Records": [{"body": '{"vin":"VIN","device_id":"d"}'}]}
    out = mod.handler(evt, None)
    assert out["ok"] is True
    assert out["results"][0]["vlm"]["defect_type"] == "scratch"
