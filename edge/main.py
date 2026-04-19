"""Edge orchestration: capture → CLIP → optional crop → MQTT / offline queue."""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict

import cv2
import yaml

from anomaly_crop import extract_anomaly_crop
from capture import CameraCapture, CaptureConfig
from clip_inference import ClipInspector
from model_manager import ModelManager
from mqtt_client import MqttPublisher
from offline_buffer import OfflineBuffer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("edge.main")


def load_config(path: Path) -> Dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return dict(raw)


def _expand_env(obj: Any) -> Any:
    if isinstance(obj, str):
        if obj.startswith("${") and obj.endswith("}"):
            key = obj[2:-1]
            return os.environ.get(key, obj)
        return obj
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(v) for v in obj]
    return obj


def run(args: argparse.Namespace) -> None:
    cfg_path = Path(args.config)
    cfg = _expand_env(load_config(cfg_path))
    device_id = str(cfg.get("device_id", "edge-unknown"))
    vin = str(cfg.get("vin", "UNKNOWNVIN"))
    prompts_path = Path(cfg.get("paths", {}).get("prompts_json", "prompts.json"))
    if not prompts_path.is_absolute():
        prompts_path = cfg_path.parent / prompts_path

    model_cfg = cfg.get("model", {})
    inspector = ClipInspector(
        model_name=str(model_cfg.get("name", "openai/clip-vit-base-patch32")),
        prompts_path=prompts_path,
    )

    cam_cfg = CaptureConfig(
        width=int(cfg.get("camera", {}).get("width", 1280)),
        height=int(cfg.get("camera", {}).get("height", 720)),
        fps=int(cfg.get("camera", {}).get("fps", 30)),
        ring_buffer_frames=int(cfg.get("camera", {}).get("ring_buffer_frames", 10)),
        synthetic=bool(args.synthetic or cfg.get("camera", {}).get("synthetic", False)),
    )

    offline_path = Path(cfg.get("offline", {}).get("sqlite_path", "edge_offline_queue.db"))
    if not offline_path.is_absolute():
        offline_path = cfg_path.parent / offline_path
    buffer = OfflineBuffer(offline_path)

    mqtt_cfg = cfg.get("mqtt", {})
    publisher: MqttPublisher | None = None
    if mqtt_cfg.get("enabled", True) and not args.mqtt_offline_only:
        host = str(mqtt_cfg.get("host", "")).replace("${IOT_ENDPOINT}", os.environ.get("AWS_IOT_ENDPOINT", ""))
        if host and not host.startswith("${"):
            publisher = MqttPublisher(
                host=host,
                port=int(mqtt_cfg.get("port", 8883)),
                client_id=str(mqtt_cfg.get("client_id", f"automotive-edge-{device_id}")).replace(
                    "${device_id}", device_id
                ),
                topic_prefix=str(mqtt_cfg.get("topic_prefix", "vehicles")),
                qos=int(mqtt_cfg.get("qos", 1)),
                use_tls=bool(mqtt_cfg.get("use_tls", True)),
                ca_path=_nullable_path(mqtt_cfg.get("ca_path")),
                cert_path=_nullable_path(mqtt_cfg.get("cert_path")),
                key_path=_nullable_path(mqtt_cfg.get("key_path")),
                offline_buffer=buffer,
                max_retries=int(cfg.get("offline", {}).get("max_retries", 5)),
            )
            try:
                publisher.connect()
            except OSError as exc:
                logger.warning("MQTT connect failed; using offline buffer only: %s", type(exc).__name__)
                publisher = None
        else:
            logger.warning("MQTT host not configured; using offline buffer only")

    shadow = ModelManager(cfg_path.parent / "device_shadow_stub.json")

    cam = CameraCapture(cam_cfg)
    cam.open()
    try:
        for frame in cam.frames(max_frames=args.max_frames):
            t0 = time.perf_counter()
            result = inspector.infer(frame)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            meta = shadow.read_reported()
            payload_common = {
                "device_id": device_id,
                "vin": vin,
                "clip_label": result.label,
                "clip_confidence": round(result.confidence, 4),
                "inference_latency_ms": round(dt_ms, 2),
                "model_reported": meta,
            }

            escalate = inspector.should_escalate(result)
            if escalate:
                crop = extract_anomaly_crop(inspector, frame, crop_size=500)
                ok, buf = cv2.imencode(".jpg", crop.crop_bgr)
                if not ok:
                    raise RuntimeError("JPEG encode failed")
                b64 = base64.b64encode(buf.tobytes()).decode("ascii")
                msg = {
                    **payload_common,
                    "escalate": True,
                    "crop_jpeg_base64": b64,
                    "bbox": list(crop.bbox_xyxy),
                }
                topic = (publisher.vehicle_topic(vin, "anomaly_crop") if publisher else f"vehicles/{vin}/inspection/anomaly_crop")
                _publish_or_queue(publisher, buffer, topic, msg)
            else:
                ok, buf = cv2.imencode(".jpg", frame)
                if not ok:
                    raise RuntimeError("JPEG encode failed")
                b64 = base64.b64encode(buf.tobytes()).decode("ascii")
                msg = {
                    **payload_common,
                    "escalate": False,
                    "frame_jpeg_base64": b64,
                }
                topic = (publisher.vehicle_topic(vin, "frame_raw") if publisher else f"vehicles/{vin}/inspection/frame_raw")
                _publish_or_queue(publisher, buffer, topic, msg)

            if publisher:
                remaining = publisher.flush_offline()
                if remaining:
                    logger.info("Offline MQTT queue size=%s", remaining)

            logger.info(
                "inspection vin=%s label=%s conf=%.3f escalate=%s t=%.1fms",
                vin,
                result.label,
                result.confidence,
                escalate,
                dt_ms,
            )
    finally:
        cam.close()
        if publisher:
            publisher.close()
        buffer.close()


def _nullable_path(val: Any) -> str | None:
    if val is None or val == "null":
        return None
    s = str(val)
    if s.startswith("${"):
        return None
    return s


def _publish_or_queue(pub: MqttPublisher | None, buffer: OfflineBuffer, topic: str, msg: Dict[str, Any]) -> None:
    if pub is None:
        buffer.enqueue(topic, msg, qos=1)
        return
    ok = pub.publish_json(topic, msg)
    if not ok:
        logger.info("Buffered MQTT message topic=%s", topic)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Automotive edge inspection loop")
    p.add_argument("--config", default="config.yaml", help="Path to edge config YAML")
    p.add_argument("--synthetic", action="store_true", help="Use synthetic frames (no camera)")
    p.add_argument("--max-frames", type=int, default=None, help="Stop after N frames")
    p.add_argument(
        "--mqtt-offline-only",
        action="store_true",
        help="Never connect to MQTT; write all publishes to SQLite queue",
    )
    return p


if __name__ == "__main__":
    run(build_arg_parser().parse_args())
