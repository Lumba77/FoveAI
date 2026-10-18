"""
Forge/nursery/xrl_trainer.py — XRL Semantic Steering Trainer
==============================================================
Coordinates training an "optimal base model medium" to master:

  1. Semantic and logic steering (profile/concept-driven generation).
  2. Self-converting context feed (history -> XRL seed -> minimal prompt).
  3. Rubble -> principa (turn noise -> principia-consistent seed).
  4. Membronic benign artifacts (HUD/memory-ring-flavored context helpers).

This is a training *coordinator*, not a full training loop. It prepares
jobs, datasets, and evaluation gates. The actual LoRA/SFT loop reuses
`ForgeFineTuner`.

Vision: Using an optimal base model medium, we train the XRL model in
semantic and logic steering, and its self-converting feed of context —
rubble -> principa aided with membronic benign artifacts.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

from .fine_tuner import ForgeFineTuner, TrainingConfig, get_fine_tuner
from .model_registry import get_registry

logger = logging.getLogger(__name__)

STATUS_QUEUED = "queued"
STATUS_PREP = "preparing_data"
STATUS_TRAINING = "training"
STATUS_EVAL = "evaluating"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"


@dataclass
class XRLTrainingJob:
    """Metadata for one XRL semantic-steering training run."""

    job_id: str
    variant_id: str
    objective: str = "semantic-and-logic-steering"
    curriculum: list[str] = field(
        default_factory=lambda: [
            "self-converting-context",
            "rubble-to-principa",
            "membronic-benign-artifacts",
        ]
    )
    base_model_path: str = ""
    datasets: list[str] = field(default_factory=list)
    xrl_degree_target: int = 3
    quality_gate: str = "MoQ-3.6 equivalent at 2.6x compression on 1B-2B models"
    config: dict[str, Any] = field(default_factory=dict)
    status: str = STATUS_QUEUED
    output_path: str | None = None
    started_at: float = 0.0
    completed_at: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "variant_id": self.variant_id,
            "objective": self.objective,
            "curriculum": self.curriculum,
            "base_model_path": self.base_model_path,
            "datasets": self.datasets,
            "xrl_degree_target": self.xrl_degree_target,
            "quality_gate": self.quality_gate,
            "config": self.config,
            "status": self.status,
            "output_path": self.output_path,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


class XRLTrainer:
    """
    Coordinates XRL semantic-steering training for FoveAI Labs.
    """

    def __init__(self, models_dir: str | None = None):
        self.models_dir = models_dir or os.environ.get(
            "FORGE_NURSERY_MODELS_DIR", "/home/lumba/Models"
        )
        self.output_base = os.path.join(self.models_dir, "foveai-labs", "xrl-runs")
        os.makedirs(self.output_base, exist_ok=True)
        self.fine_tuner = get_fine_tuner(models_dir=self.models_dir)
        self.jobs: dict[str, XRLTrainingJob] = {}
        # Nano-first prototyping: use sub-1B / 1B-2B models to lay the basis
        # for a selective-evolution workflow with fast iteration.
        self.nano_first: bool = True

    def create_job(
        self,
        variant_id: str,
        base_model_path: str | None = None,
        datasets: list[str] | None = None,
        xrl_degree_target: int = 3,
        nano: bool | None = None,
    ) -> XRLTrainingJob:
        """
        Create an XRL training job from a registry variant.
        """
        registry = get_registry()
        variant = registry.variants.get(variant_id)
        if not variant:
            raise ValueError(f"Variant not found in registry: {variant_id}")

        xrl_training = variant.xrl_training or {}
        objective = xrl_training.get("objective", "semantic-and-logic-steering")
        curriculum = xrl_training.get(
            "curriculum",
            ["self-converting-context", "rubble-to-principa", "membronic-benign-artifacts"],
        )
        cfg = xrl_training.get("training_config", {})

        use_nano = nano if nano is not None else self.nano_first
        if use_nano:
            cfg = self._nano_config(cfg)

        job_id = f"xrl-{variant_id}-{int(time.time())}"
        job = XRLTrainingJob(
            job_id=job_id,
            variant_id=variant_id,
            objective=objective,
            curriculum=curriculum,
            base_model_path=base_model_path or variant.base_model,
            datasets=datasets or xrl_training.get("datasets", []),
            xrl_degree_target=xrl_degree_target,
            quality_gate=xrl_training.get(
                "quality_gate",
                "MoQ-3.6 equivalent at 2.6x compression on 1B-2B models",
            ),
            config=cfg,
        )
        job.config["nano_first"] = use_nano
        self.jobs[job_id] = job
        logger.info(f"Created XRL training job: {job_id} for variant {variant_id}")
        return job

    def prepare_training_data(self, job: XRLTrainingJob) -> str:
        """
        Prepare synthetic/curated training examples for the XRL curriculum.
        Returns the path to a JSONL file of {text, ...} samples.

        Phase 0: writes a placeholder dataset describing the curriculum.
        Phase 1+: will call dataset curators and context-seed generators.
        """
        job.status = STATUS_PREP
        out_dir = os.path.join(self.output_base, job.job_id)
        os.makedirs(out_dir, exist_ok=True)
        dataset_path = os.path.join(out_dir, "train.jsonl")

        # Placeholder seed examples. In production these come from:
        #   - self-converting-context: pairs of [long context] -> [compressed XRL seed]
        #   - rubble-to-principa: noisy chat logs -> principia-aligned summaries
        #   - membronic-benign-artifacts: memory ring snippets -> helpful HUD nuggets
        samples = []
        for concept in job.curriculum:
            samples.append(
                {
                    "text": f"[XRL TRAINING EXAMPLE] {job.objective} | {concept} | degree={job.xrl_degree_target} | quality_gate={job.quality_gate}",
                    "metadata": {
                        "variant_id": job.variant_id,
                        "curriculum_item": concept,
                        "xrl_degree": job.xrl_degree_target,
                    },
                }
            )

        with open(dataset_path, "w", encoding="utf-8") as f:
            for sample in samples:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")

        logger.info(f"Prepared {len(samples)} placeholder samples at {dataset_path}")
        return dataset_path

    def start_job(self, job_id: str) -> None:
        """Start the underlying LoRA/SFT training job."""
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError(f"XRL training job not found: {job_id}")

        dataset_path = self.prepare_training_data(job)

        # Map XRL job to the generic fine-tuner config.
        # Micro-mode uses tiny efficient target modules; full runs use the
        # full projection set.
        target_modules = job.config.get(
            "target_modules",
            ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        )
        if job.config.get("nano_first"):
            target_modules = ["q_proj", "v_proj", "up_proj", "down_proj"]

        cfg = TrainingConfig(
            variant_id=job.variant_id,
            base_model_path=job.base_model_path,
            output_dir=os.path.join(self.output_base, job.job_id, "output"),
            datasets=job.datasets or [dataset_path],
            lora_r=job.config.get("lora_r", 32),
            lora_alpha=job.config.get("lora_alpha", 64),
            lora_dropout=job.config.get("lora_dropout", 0.05),
            learning_rate=job.config.get("learning_rate", 1e-4),
            epochs=job.config.get("epochs", 5),
            batch_size=job.config.get("batch_size", 2),
            gradient_accumulation=job.config.get("gradient_accumulation", 4),
            max_seq_length=job.config.get("max_seq_length", 2048),
            use_4bit=job.config.get("use_4bit", True),
            target_modules=target_modules,
            max_samples=job.config.get("max_samples", 5000),
        )

        ft_job = self.fine_tuner.create_job(cfg)
        job.started_at = time.time()
        job.status = STATUS_TRAINING

        def _on_progress(ft_job):
            logger.info(
                f"[{ft_job.job_id}] progress={ft_job.progress:.2%} loss={ft_job.loss:.4f}"
            )

        self.fine_tuner.start_job(ft_job.job_id, progress_callback=_on_progress)
        logger.info(f"Started LoRA training for XRL job {job_id} via {ft_job.job_id}")

    @staticmethod
    def _nano_config(base_config: dict[str, Any]) -> dict[str, Any]:
        """
        Shrink a training configuration for nano-first prototyping.
        Sub-1B / 1B-2B models, tiny LoRA, minimal epochs, short sequences —
        fast iteration for selective-evolution workflows.
        """
        cfg = dict(base_config)
        cfg["lora_r"] = min(cfg.get("lora_r", 32), 4)
        cfg["lora_alpha"] = min(cfg.get("lora_alpha", 64), 8)
        cfg["epochs"] = min(cfg.get("epochs", 5), 1)
        cfg["batch_size"] = 1
        cfg["gradient_accumulation"] = 1
        cfg["max_seq_length"] = min(cfg.get("max_seq_length", 2048), 512)
        cfg["max_samples"] = 128
        cfg["learning_rate"] = 1e-3  # higher LR acceptable for nano runs
        return cfg

    def evaluate(self, job_id: str) -> dict[str, Any]:
        """
        Evaluate a trained XRL model against the quality gate.
        Phase 0: returns a placeholder report.
        Phase 1+: runs builder/probes/benchmark_suite.py against a packed XRLF.
        """
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError(f"XRL training job not found: {job_id}")

        job.status = STATUS_EVAL
        report = {
            "job_id": job_id,
            "quality_gate": job.quality_gate,
            "compression_target": "2.6x",
            "xrl_degree_target": job.xrl_degree_target,
            "status": "placeholder",
            "notes": "Run benchmark_suite.py on the packed XRLF to fill this report.",
        }
        job.status = STATUS_COMPLETED
        job.completed_at = time.time()
        logger.info(f"Evaluation placeholder for {job_id}: {report}")
        return report

    def get_job(self, job_id: str) -> XRLTrainingJob | None:
        return self.jobs.get(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        return [j.to_dict() for j in self.jobs.values()]


# Singleton
_default_trainer: XRLTrainer | None = None


def get_xrl_trainer(models_dir: str | None = None) -> XRLTrainer:
    global _default_trainer
    if _default_trainer is None:
        _default_trainer = XRLTrainer(models_dir=models_dir)
    return _default_trainer
