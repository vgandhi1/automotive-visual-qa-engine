"""CLIP zero-shot PASS vs DEFECT with confidence (Hugging Face; TensorRT optional later)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from transformers import CLIPModel, CLIPProcessor


@dataclass
class ClipResult:
    label: str  # "PASS" or "FAIL"
    confidence: float
    logits_pass: float
    logits_defect: float


class ClipInspector:
    def __init__(
        self,
        model_name: str,
        prompts_path: Path,
        device: str | None = None,
    ) -> None:
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model = CLIPModel.from_pretrained(model_name).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(model_name)
        self.model.eval()

        data = json.loads(Path(prompts_path).read_text(encoding="utf-8"))
        self.pass_prompts: List[str] = list(data["prompts"]["pass"])
        self.defect_prompts: List[str] = list(data["prompts"]["defect"])
        routing = data.get("routing", {})
        self.confidence_threshold: float = float(routing.get("confidence_threshold", 0.75))

    @torch.inference_mode()
    def infer(self, frame_bgr: np.ndarray) -> ClipResult:
        image = Image.fromarray(frame_bgr[:, :, ::-1])
        pass_inputs = self.processor(
            text=self.pass_prompts,
            images=image,
            return_tensors="pt",
            padding=True,
        )
        defect_inputs = self.processor(
            text=self.defect_prompts,
            images=image,
            return_tensors="pt",
            padding=True,
        )
        pass_inputs = {k: v.to(self.device) for k, v in pass_inputs.items()}
        defect_inputs = {k: v.to(self.device) for k, v in defect_inputs.items()}

        pass_out = self.model(**pass_inputs)
        defect_out = self.model(**defect_inputs)

        logit_pass = pass_out.logits_per_image.max(dim=-1).values.squeeze(0)
        logit_defect = defect_out.logits_per_image.max(dim=-1).values.squeeze(0)
        two = torch.stack([logit_pass, logit_defect], dim=0)
        probs = F.softmax(two, dim=0)
        if logit_defect > logit_pass:
            label = "FAIL"
            confidence = float(probs[1].item())
        else:
            label = "PASS"
            confidence = float(probs[0].item())

        return ClipResult(
            label=label,
            confidence=confidence,
            logits_pass=float(logit_pass.item()),
            logits_defect=float(logit_defect.item()),
        )

    def should_escalate(self, result: ClipResult) -> bool:
        """Low confidence triggers Tier-2 VLM path (plan.md)."""
        return result.confidence < self.confidence_threshold

    def patch_embedding_map(self, frame_bgr: np.ndarray) -> Tuple[torch.Tensor, int, int]:
        """
        Returns L2-normalized patch embeddings [1, P, D] and grid side length (sqrt(P)).
        """
        image = Image.fromarray(frame_bgr[:, :, ::-1])
        inputs = self.processor(images=image, return_tensors="pt")
        pixel_values = inputs["pixel_values"].to(self.device)
        vision = self.model.vision_model(
            pixel_values=pixel_values,
            return_dict=True,
        )
        last = vision.last_hidden_state
        last = self.model.vision_model.post_layernorm(last)
        patches = last[:, 1:, :]
        proj = self.model.visual_projection(patches)
        proj = proj / proj.norm(dim=-1, keepdim=True)
        num_patches = proj.shape[1]
        side = int(num_patches**0.5)
        if side * side != num_patches:
            raise ValueError("Non-square patch grid unsupported for saliency map")
        return proj, side, side

    @torch.inference_mode()
    def text_direction(self) -> torch.Tensor:
        """Unit vector in embedding space: mean(defect) - mean(pass), normalized."""
        pass_inputs = self.processor(text=self.pass_prompts, return_tensors="pt", padding=True)
        defect_inputs = self.processor(text=self.defect_prompts, return_tensors="pt", padding=True)
        pass_inputs = {k: v.to(self.device) for k, v in pass_inputs.items() if k in ("input_ids", "attention_mask")}
        defect_inputs = {
            k: v.to(self.device) for k, v in defect_inputs.items() if k in ("input_ids", "attention_mask")
        }

        pass_emb = self.model.get_text_features(**pass_inputs)
        defect_emb = self.model.get_text_features(**defect_inputs)
        pass_emb = pass_emb / pass_emb.norm(dim=-1, keepdim=True)
        defect_emb = defect_emb / defect_emb.norm(dim=-1, keepdim=True)
        direction = defect_emb.mean(dim=0) - pass_emb.mean(dim=0)
        direction = direction / direction.norm(dim=-1, keepdim=True)
        return direction

    def export_metadata(self) -> Dict[str, Any]:
        return {
            "model": self.model.config.name_or_path,
            "confidence_threshold": self.confidence_threshold,
            "pass_prompts": len(self.pass_prompts),
            "defect_prompts": len(self.defect_prompts),
        }
