"""
Forge/nursery/xrl_nano_trainer.py — Nano-Native XRL Trainer
============================================================
Train 33M–1B parameter models to read and write XRL seeds natively.

This trainer performs vocabulary surgery (adds XRL special tokens) and runs
a multi-stage SFT curriculum:

  1. Seed decoding      (seed → response)
  2. Seed encoding      (long context → seed)
  3. Autoencoding       (long context → seed → reconstruct)
  4. Rubble → principa  (noisy context → clean seed)
  5. Mixed / degree variation

It is intentionally lightweight so we can iterate fast on sub-1B models
before promoting methods to larger variants.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STATUS_QUEUED = "queued"
STATUS_LOADING = "loading_tokenizer"
STATUS_VOCAB = "vocab_surgery"
STATUS_TRAINING = "training"
STATUS_SAVING = "saving"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# XRL seed special tokens. These become native vocabulary entries so nano
# models can emit them in one token instead of spelling them out character
# by character.
XRL_SEED_TOKENS = [
    "<XRL-SEED>", "</XRL-SEED>",
    "<ANCHORS>", "</ANCHORS>",
    "<CONCEPTS>", "</CONCEPTS>",
    "<DIGEST>", "</DIGEST>",
    "<PRINCIPA>", "</PRINCIPA>",
    "<MEMBRANE>", "</MEMBRANE>",
    "<KV-HINT>", "</KV-HINT>",
    "<CONTINUE/>",
    "<RUBBLE>", "</RUBBLE>",
]


@dataclass
class NanoXRLJob:
    """Metadata for one nano-native XRL training run."""

    job_id: str
    base_model: str  # HF repo id, e.g. "HuggingFaceTB/SmolLM2-135M-Instruct"
    output_dir: str
    stages: list[str] = field(default_factory=lambda: [
        "seed_decode",
        "seed_encode",
        "autoencode",
        "rubble_to_principa",
        "mixed",
    ])
    max_seq_length: int = 1024
    lora_r: int = 4
    lora_alpha: int = 8
    lora_dropout: float = 0.05
    learning_rate: float = 5e-4
    batch_size: int = 1
    gradient_accumulation: int = 1
    epochs_per_stage: int = 1
    use_4bit: bool = True
    target_modules: list[str] = field(default_factory=lambda: [
        "q_proj", "v_proj", "up_proj", "down_proj"
    ])
    status: str = STATUS_QUEUED
    current_stage: str = ""
    progress: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "base_model": self.base_model,
            "output_dir": self.output_dir,
            "stages": self.stages,
            "max_seq_length": self.max_seq_length,
            "lora_r": self.lora_r,
            "lora_alpha": self.lora_alpha,
            "lora_dropout": self.lora_dropout,
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "gradient_accumulation": self.gradient_accumulation,
            "epochs_per_stage": self.epochs_per_stage,
            "use_4bit": self.use_4bit,
            "target_modules": self.target_modules,
            "status": self.status,
            "current_stage": self.current_stage,
            "progress": self.progress,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


class XRLNanoTrainer:
    """
    End-to-end trainer for nano-native XRL models.

    Phase 0 (current): the class exists, can do vocabulary surgery in memory,
    and exposes the training stages as a skeleton. No real training loop is
    run until datasets and base models are confirmed available.
    """

    def __init__(self, output_base: str | None = None):
        self.output_base = output_base or os.environ.get(
            "FORGE_NURSERY_MODELS_DIR", "/home/lumba/Models"
        )
        self.jobs: dict[str, NanoXRLJob] = {}

    def create_job(
        self,
        base_model: str,
        job_id: str | None = None,
        max_seq_length: int = 1024,
        lora_r: int = 4,
        learning_rate: float = 5e-4,
    ) -> NanoXRLJob:
        """Create a nano-native XRL training job."""
        if job_id is None:
            job_id = f"nano-xrl-{base_model.replace('/', '_')}-{int(time.time())}"
        output_dir = os.path.join(self.output_base, "foveai-labs", "nano-xrl-runs", job_id)
        os.makedirs(output_dir, exist_ok=True)

        job = NanoXRLJob(
            job_id=job_id,
            base_model=base_model,
            output_dir=output_dir,
            max_seq_length=max_seq_length,
            lora_r=lora_r,
            lora_alpha=lora_r * 2,
            learning_rate=learning_rate,
        )
        self.jobs[job_id] = job
        logger.info(f"Created nano XRL job {job_id} for {base_model}")
        return job

    def prepare_tokenizer(self, job: NanoXRLJob) -> Any:
        """
        Load the base tokenizer and add XRL seed tokens.

        Phase 0: returns a metadata dict describing the intended surgery.
        Phase 1+: will import transformers, resize embeddings, and return
        the real tokenizer/model pair.
        """
        job.status = STATUS_VOCAB
        report = {
            "base_model": job.base_model,
            "new_tokens": XRL_SEED_TOKENS,
            "new_token_count": len(XRL_SEED_TOKENS),
            "note": "Tokenizer vocab surgery placeholder. In Phase 1 this will call tokenizer.add_tokens(...) and model.resize_token_embeddings(...).",
        }
        logger.info(f"Vocab surgery report for {job.job_id}: {report}")
        return report

    def prepare_datasets(self, job: NanoXRLJob, raw_dataset_dir: str | None = None) -> str:
        """
        Build the multi-stage training JSONL files from the real nano corpus.

        Delegates to `xrl_nano_data.generate_full_corpus` to emit all four
        curriculum stages (seed_decode, seed_encode, rubble_to_principa,
        red_thread_weaving) into the job's dataset directory.
        """
        out_dir = Path(job.output_dir) / "datasets"
        out_dir.mkdir(parents=True, exist_ok=True)

        from .xrl_nano_data import generate_full_corpus

        counts = generate_full_corpus(out_dir)
        logger.info(f"Prepared nano corpus in {out_dir}: {counts}")
        return str(out_dir)

    def train(self, job_id: str) -> None:
        """
        Run the full nano-native XRL training loop.

        Phase 0: validates the job, performs placeholder tokenizer surgery,
        writes placeholder datasets, and marks the job complete without
        loading a real model.
        """
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError(f"Nano XRL job not found: {job_id}")

        try:
            job.status = STATUS_LOADING
            job.started_at = time.time()
            logger.info(f"Starting nano XRL training {job_id}")

            # 1. Vocab surgery (placeholder)
            self.prepare_tokenizer(job)

            # 2. Datasets (placeholder)
            self.prepare_datasets(job)

            # 3. Training loop placeholder
            job.status = STATUS_TRAINING
            for i, stage in enumerate(job.stages):
                job.current_stage = stage
                job.progress = i / max(1, len(job.stages))
                logger.info(
                    f"[{job_id}] stage={stage} progress={job.progress:.1%} "
                    f"(placeholder - no real training yet)"
                )
                # Phase 1+: _train_stage(job, stage)

            # 4. Save
            job.status = STATUS_SAVING
            meta_path = Path(job.output_dir) / "metadata.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(job.to_dict(), f, indent=2)

            job.status = STATUS_COMPLETED
            job.progress = 1.0
            job.completed_at = time.time()
            logger.info(f"Nano XRL job {job_id} skeleton complete -> {job.output_dir}")

        except Exception as e:
            job.status = STATUS_FAILED
            job.error = str(e)
            job.completed_at = time.time()
            logger.error(f"Nano XRL job {job_id} failed: {e}")

    def get_job(self, job_id: str) -> NanoXRLJob | None:
        return self.jobs.get(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        return [j.to_dict() for j in self.jobs.values()]


# Singleton
_default_nano_trainer: XRLNanoTrainer | None = None


def get_xrl_nano_trainer(output_base: str | None = None) -> XRLNanoTrainer:
    global _default_nano_trainer
    if _default_nano_trainer is None:
        _default_nano_trainer = XRLNanoTrainer(output_base=output_base)
    return _default_nano_trainer
