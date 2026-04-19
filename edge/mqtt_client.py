"""AWS IoT Core MQTT publisher (TLS) with offline fallback."""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt

from offline_buffer import OfflineBuffer

logger = logging.getLogger(__name__)


class MqttPublisher:
    def __init__(
        self,
        host: str,
        port: int,
        client_id: str,
        topic_prefix: str,
        qos: int,
        use_tls: bool,
        ca_path: Optional[str],
        cert_path: Optional[str],
        key_path: Optional[str],
        offline_buffer: OfflineBuffer,
        max_retries: int = 5,
        on_publish_failed: Optional[Callable[[str, Dict[str, Any], int], None]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.topic_prefix = topic_prefix
        self.qos = qos
        self.use_tls = use_tls
        self.ca_path = ca_path
        self.cert_path = cert_path
        self.key_path = key_path
        self.offline_buffer = offline_buffer
        self.max_retries = max_retries
        self.on_publish_failed = on_publish_failed
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv5,
        )
        self._connected = threading.Event()
        self._lock = threading.Lock()

        def on_connect(client: mqtt.Client, userdata: Any, flags: Any, rc: int, properties: Any = None) -> None:
            if rc == 0:
                self._connected.set()
                logger.info("MQTT connected (reason code=%s)", rc)
            else:
                logger.warning("MQTT connect failed rc=%s", rc)

        def on_disconnect(client: mqtt.Client, userdata: Any, rc: int, properties: Any = None) -> None:
            self._connected.clear()
            logger.info("MQTT disconnected rc=%s", rc)

        self._client.on_connect = on_connect
        self._client.on_disconnect = on_disconnect

    def connect(self) -> None:
        if self.use_tls:
            if not (self.ca_path and self.cert_path and self.key_path):
                raise ValueError("TLS enabled but certificate paths are missing")
            self._client.tls_set(ca_certs=self.ca_path, certfile=self.cert_path, keyfile=self.key_path)
        self._client.connect(self.host, self.port, keepalive=60)
        self._client.loop_start()

    def close(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def vehicle_topic(self, vin: str, suffix: str) -> str:
        return f"{self.topic_prefix}/{vin}/inspection/{suffix}"

    def publish_json(self, topic: str, payload: Dict[str, Any]) -> bool:
        body = json.dumps(payload, separators=(",", ":"))
        with self._lock:
            if not self._connected.is_set():
                self.offline_buffer.enqueue(topic, payload, self.qos)
                return False
            info = self._client.publish(topic, body, qos=self.qos)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                self.offline_buffer.enqueue(topic, payload, self.qos)
                return False
        return True

    def flush_offline(self) -> int:
        """Attempt to drain queue with exponential backoff; returns remaining size."""
        pending = self.offline_buffer.dequeue_batch()
        flushed = 0
        for msg in pending:
            if not self._connected.is_set():
                break
            try:
                body = json.dumps(msg.payload, separators=(",", ":"))
                info = self._client.publish(msg.topic, body, qos=msg.qos)
                if info.rc == mqtt.MQTT_ERR_SUCCESS:
                    self.offline_buffer.delete(msg.id)
                    flushed += 1
                else:
                    self._bump_retry(msg.id, msg.retries)
            except OSError:
                self._bump_retry(msg.id, msg.retries)
        return self.offline_buffer.size()

    def _bump_retry(self, message_id: int, retries: int) -> None:
        if retries + 1 >= self.max_retries:
            self.offline_buffer.delete(message_id)
            if self.on_publish_failed:
                # Do not log payload contents (may include image metadata).
                self.on_publish_failed("max_retries", {}, message_id)
            return
        self.offline_buffer.increment_retry(message_id)
        time.sleep(min(30.0, (2**retries) * 0.25 + random.random() * 0.1))


def build_publisher_from_env(
    offline: OfflineBuffer,
    iot_endpoint: Optional[str] = None,
) -> Optional[MqttPublisher]:
    """Optional factory when real certs are present."""
    endpoint = iot_endpoint or os.environ.get("AWS_IOT_ENDPOINT")
    if not endpoint:
        return None
    return MqttPublisher(
        host=endpoint,
        port=8883,
        client_id=os.environ.get("MQTT_CLIENT_ID", "automotive-edge"),
        topic_prefix=os.environ.get("MQTT_TOPIC_PREFIX", "vehicles"),
        qos=int(os.environ.get("MQTT_QOS", "1")),
        use_tls=True,
        ca_path=os.environ.get("AWS_IOT_CA"),
        cert_path=os.environ.get("AWS_IOT_CERT"),
        key_path=os.environ.get("AWS_IOT_KEY"),
        offline_buffer=offline,
    )
