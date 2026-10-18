"""
Model Registry for FoveAI Labs
Tracks efficient model variants, compression profiles, and semantic compression degrees.
"""

import json
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "model_registry.json")


@dataclass
class VariantDefinition:
    """A model variant definition with semantic compression profile."""

    id: str
    name: str
    description: str = ""
    base_model: str = "gemma-4-12b-it"
    architecture: str = "dense-transformer"  # dense-transformer | hybrid-mamba-attn | mamba2-ssd | hybrid-mamba-moe
    datasets: list[str] = field(default_factory=list)
    training_config: dict = field(default_factory=dict)
    quant_type: str = "moq-3.0"
    xrl_degree: int = 0  # 0-9 XRL compression/quality degree (higher = more compressed)
    compression_profile: str = ""  # human-readable compression recipe
    xrl_training: dict = field(default_factory=dict)  # XRL semantic/logic steering curriculum
    created_at: str = ""
    status: str = "defined"  # defined, training, trained, quantized, active

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "base_model": self.base_model,
            "architecture": self.architecture,
            "datasets": self.datasets,
            "training_config": self.training_config,
            "quant_type": self.quant_type,
            "xrl_degree": self.xrl_degree,
            "compression_profile": self.compression_profile,
            "xrl_training": self.xrl_training,
            "created_at": self.created_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VariantDefinition":
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            base_model=data.get("base_model", "gemma-4-12b-it"),
            architecture=data.get("architecture", "dense-transformer"),
            datasets=data.get("datasets", []),
            training_config=data.get("training_config", {}),
            quant_type=data.get("quant_type", "moq-3.0"),
            xrl_degree=data.get("xrl_degree", 0),
            compression_profile=data.get("compression_profile", ""),
            xrl_training=data.get("xrl_training", {}),
            created_at=data.get("created_at", ""),
            status=data.get("status", "defined"),
        )


class ModelRegistry:
    """Manages variant definitions with JSON persistence."""

    def __init__(self, registry_path: str = REGISTRY_PATH):
        self.registry_path = registry_path
        self.variants: dict[str, VariantDefinition] = {}
        self._load()

    def _load(self):
        """Load variants from JSON file."""
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, "r") as f:
                    data = json.load(f)
                for vdata in data.get("variants", {}).values():
                    variant = VariantDefinition.from_dict(vdata)
                    self.variants[variant.id] = variant
                logger.info(f"Loaded {len(self.variants)} variants from registry")
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")
        else:
            logger.info("No registry file found, starting empty")

    def _save(self):
        """Persist variants to JSON file."""
        data = {"variants": {vid: v.to_dict() for vid, v in self.variants.items()}}
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        with open(self.registry_path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"Saved {len(self.variants)} variants to registry")

    def get_variant(self, variant_id: str) -> VariantDefinition | None:
        return self.variants.get(variant_id)

    def list_variants(self) -> list[dict]:
        return [v.to_dict() for v in self.variants.values()]

    def add_variant(self, variant: VariantDefinition):
        import datetime

        variant.created_at = datetime.datetime.now().isoformat()
        self.variants[variant.id] = variant
        self._save()

    def remove_variant(self, variant_id: str):
        if variant_id in self.variants:
            del self.variants[variant_id]
            self._save()

    def update_status(self, variant_id: str, status: str):
        variant = self.variants.get(variant_id)
        if variant:
            variant.status = status
            self._save()


# Singleton
_registry: ModelRegistry | None = None


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
