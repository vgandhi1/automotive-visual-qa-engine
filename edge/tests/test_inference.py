import json
from pathlib import Path

import pytest

pytest.importorskip("torch")
pytest.importorskip("transformers")
pytest.importorskip("numpy")
import numpy as np

from clip_inference import ClipInspector


@pytest.mark.slow
def test_clip_runs_on_synthetic_frame(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    prompts = {
        "prompts": {"pass": ["a clean surface"], "defect": ["a scratched surface"]},
        "routing": {"confidence_threshold": 0.75},
    }
    p = tmp_path / "prompts.json"
    p.write_text(json.dumps(prompts), encoding="utf-8")
    inspector = ClipInspector(model_name="openai/clip-vit-base-patch32", prompts_path=p)
    frame = np.zeros((128, 128, 3), dtype=np.uint8)
    frame[:] = (200, 200, 200)
    res = inspector.infer(frame)
    assert res.label in ("PASS", "FAIL")
    assert 0.0 <= res.confidence <= 1.0
