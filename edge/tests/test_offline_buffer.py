from pathlib import Path

from offline_buffer import OfflineBuffer


def test_offline_buffer_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "q.db"
    buf = OfflineBuffer(db)
    buf.enqueue("vehicles/VIN/inspection/frame_raw", {"ok": True}, qos=1)
    assert buf.size() == 1
    batch = buf.dequeue_batch()
    assert len(batch) == 1
    buf.delete(batch[0].id)
    assert buf.size() == 0
    buf.close()
