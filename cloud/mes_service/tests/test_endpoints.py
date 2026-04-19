from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True


def test_log_pass_memory() -> None:
    r = client.post(
        "/inspection/pass",
        json={
            "vin": "VIN123",
            "result": "PASS",
            "inspection_time": "2026-01-01T00:00:00Z",
            "image_s3_url": "s3://bucket/key.jpg",
            "clip_confidence": 0.9,
        },
    )
    assert r.status_code == 200
