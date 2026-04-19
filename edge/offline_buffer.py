"""SQLite-backed queue for MQTT publish when offline (plan.md)."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class QueuedMessage:
    id: int
    topic: str
    payload: Dict[str, Any]
    qos: int
    retries: int


class OfflineBuffer:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mqtt_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                payload TEXT NOT NULL,
                qos INTEGER NOT NULL,
                retries INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def enqueue(self, topic: str, payload: Dict[str, Any], qos: int = 1) -> None:
        self._conn.execute(
            "INSERT INTO mqtt_queue (topic, payload, qos, retries, created_at) VALUES (?, ?, ?, 0, ?)",
            (topic, json.dumps(payload), qos, time.time()),
        )
        self._conn.commit()

    def dequeue_batch(self, limit: int = 32) -> List[QueuedMessage]:
        cur = self._conn.execute(
            "SELECT id, topic, payload, qos, retries FROM mqtt_queue ORDER BY id ASC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        out: List[QueuedMessage] = []
        for mid, topic, payload, qos, retries in rows:
            out.append(QueuedMessage(id=mid, topic=topic, payload=json.loads(payload), qos=qos, retries=retries))
        return out

    def delete(self, message_id: int) -> None:
        self._conn.execute("DELETE FROM mqtt_queue WHERE id = ?", (message_id,))
        self._conn.commit()

    def increment_retry(self, message_id: int) -> None:
        self._conn.execute(
            "UPDATE mqtt_queue SET retries = retries + 1 WHERE id = ?",
            (message_id,),
        )
        self._conn.commit()

    def size(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM mqtt_queue")
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        self._conn.close()
