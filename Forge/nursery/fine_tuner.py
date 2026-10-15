"""
Fine-Tuner for Forge Nursery
Wraps Unsloth's LoRA/QLoRA fine-tuning API for Gemma 4 12B variants.
"""

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Training job states
STATUS_QUEUED = "queued"
STATUS_LOADING = "loading_model"
STATUS_TRAINING = "training"
STATUS_SAVING = "saving"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"


@dataclass
class TrainingConfig:
    """Configuration for a fine-tuning job."""

    variant_id: str
    base_model_path: str
    output_dir: str
    datasets: list[str] = field(default_factory=list)  # HF dataset IDs
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    learning_rate: float = 2e-4
    epochs: int = 3
    batch_size: int = 2
    gradient_accumulation: int = 4
    max_seq_length: int = 2048
    use_4bit: bool = True
    target_modules: list[str] = field(
        default_factory=lambda: [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ]
    )
    max_samples: int = 5000


@dataclass
class TrainingJob:
    """Tracks a running or completed training job."""

    job_id: str
    config: TrainingConfig
    status: str = STATUS_QUEUED
    progress: float = 0.0  # 0.0 to 1.0
    current_step: int = 0
    total_steps: int = 0
    loss: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    error: str | None = None
    output_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "variant_id": self.config.variant_id,
            "status": self.status,
            "progress": round(self.progress, 3),
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "loss": round(self.loss, 4) if self.loss else 0,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "output_path": self.output_path,
        }


class ForgeFineTuner:
    """
    Manages Unsloth fine-tuning jobs for Gemma 4 12B.
    Runs training in a background thread with progress callbacks.
    """

    def __init__(self, models_dir: str = None):
        self.models_dir = models_dir or os.environ.get(
            "FORGE_NURSERY_MODELS_DIR", "/opt/foveai-models"
        )
        self.output_base = os.path.join(self.models_dir, "forge-nursery", "runs")
        self.jobs: dict[str, TrainingJob] = {}
        self._lock = threading.Lock()
        os.makedirs(self.output_base, exist_ok=True)

    def create_job(self, config: TrainingConfig) -> TrainingJob:
        """Create and queue a new training job."""
        job_id = f"forge-{config.variant_id}-{int(time.time())}"
        job = TrainingJob(job_id=job_id, config=config)
        with self._lock:
            self.jobs[job_id] = job
        logger.info(f"Created training job: {job_id}")
        return job

    def start_job(
        self,
        job_id: str,
        progress_callback: Callable[[TrainingJob], None] | None = None,
    ) -> None:
        """Start a queued training job in a background thread."""
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        thread = threading.Thread(
            target=self._run_training,
            args=(job, progress_callback),
            daemon=True,
        )
        thread.start()

    def _run_training(
        self,
        job: TrainingJob,
        progress_callback: Callable[[TrainingJob], None] | None = None,
    ) -> None:
        """Execute the Unsloth fine-tuning pipeline."""
        try:
            job.status = STATUS_LOADING
            job.started_at = time.time()
            self._notify(job, progress_callback)

            # Step 1: Load base model with Unsloth
            model, tokenizer = self._load_model(job.config)

            # Step 2: Load and prepare datasets
            job.status = STATUS_LOADING
            self._notify(job, progress_callback)
            dataset = self._prepare_dataset(job.config, tokenizer)

            # Step 3: Apply LoRA adapters
            model = self._apply_lora(model, job.config)

            # Step 4: Train
            job.status = STATUS_TRAINING
            self._notify(job, progress_callback)
            self._train(model, tokenizer, dataset, job, progress_callback)

            # Step 5: Save merged model
            job.status = STATUS_SAVING
            self._notify(job, progress_callback)
            output_path = self._save_model(model, tokenizer, job)

            job.status = STATUS_COMPLETED
            job.progress = 1.0
            job.completed_at = time.time()
            job.output_path = output_path
            self._notify(job, progress_callback)
            logger.info(f"Training completed: {job.job_id} -> {output_path}")

        except Exception as e:
            job.status = STATUS_FAILED
            job.error = str(e)
            job.completed_at = time.time()
            self._notify(job, progress_callback)
            logger.error(f"Training failed: {job.job_id}: {e}")

    def _load_model(self, config: TrainingConfig):
        """Load Gemma 4 12B with Unsloth optimizations."""
        try:
            import torch
            from unsloth import FastLanguageModel

            logger.info(f"Loading base model from: {config.base_model_path}")

            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name="unsloth/gemma-4-12b-it",  # Use Unsloth's optimized version
                max_seq_length=config.max_seq_length,
                dtype=None,  # Auto-detect
                load_in_4bit=config.use_4bit,
            )

            return model, tokenizer

        except ImportError:
            raise RuntimeError("Unsloth is not installed. Run: pip install unsloth")
        except Exception as e:
            # Fallback: try loading from local GGUF path via transformers
            logger.warning(f"Unsloth load failed ({e}), trying local path...")
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            model = AutoModelForCausalLM.from_pretrained(
                "google/gemma-4-12b-it",
                torch_dtype=torch.float16,
                device_map="auto",
                load_in_4bit=config.use_4bit,
            )
            tokenizer = AutoTokenizer.from_pretrained("google/gemma-4-12b-it")
            return model, tokenizer

    def _prepare_dataset(self, config: TrainingConfig, tokenizer):
        """Load and tokenize datasets for training."""
        from datasets import Dataset

        from .dataset_curator import load_dataset_for_training, scan_local_datasets

        all_samples = []
        local_datasets = {ds.name: ds for ds in scan_local_datasets()}

        for ds_id in config.datasets:
            if ds_id in local_datasets:
                ds_info = local_datasets[ds_id]
                samples = load_dataset_for_training(
                    ds_info,
                    max_samples=config.max_samples // len(config.datasets),
                )
                all_samples.extend(samples)
                logger.info(f"Loaded {len(samples)} samples from {ds_id}")
            else:
                logger.warning(f"Dataset not found locally: {ds_id}")

        if not all_samples:
            raise ValueError("No training samples loaded from any dataset")

        # Convert to HuggingFace Dataset
        hf_dataset = Dataset.from_list(all_samples)

        # Tokenize
        def tokenize_fn(examples):
            return tokenizer(
                examples["text"],
                truncation=True,
                max_length=config.max_seq_length,
                padding="max_length",
            )

        tokenized = hf_dataset.map(tokenize_fn, batched=True, remove_columns=["text"])
        return tokenized

    def _apply_lora(self, model, config: TrainingConfig):
        """Apply LoRA adapters to the model."""
        from unsloth import FastLanguageModel

        model = FastLanguageModel.get_peft_model(
            model,
            r=config.lora_r,
            target_modules=config.target_modules,
            lora_alpha=config.lora_alpha,
            lora_dropout=config.lora_dropout,
            bias="none",
            use_gradient_checkpointing="unsloth",
            random_state=42,
        )
        return model

    def _train(self, model, tokenizer, dataset, job: TrainingJob, callback):
        """Run the training loop."""
        from transformers import TrainingArguments
        from trl import SFTTrainer

        job.total_steps = (
            len(dataset) // (job.config.batch_size * job.config.gradient_accumulation)
        ) * job.config.epochs

        training_args = TrainingArguments(
            per_device_train_batch_size=job.config.batch_size,
            gradient_accumulation_steps=job.config.gradient_accumulation,
            warmup_steps=5,
            num_train_epochs=job.config.epochs,
            learning_rate=job.config.learning_rate,
            fp16=not job.config.use_4bit,
            bf16=False,
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="linear",
            seed=42,
            output_dir=os.path.join(self.output_base, "checkpoints", job.job_id),
        )

        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=dataset,
            dataset_text_field="text",
            max_seq_length=job.config.max_seq_length,
            args=training_args,
        )

        # Custom progress callback
        class ProgressCallback:
            def on_log(self, args, state, control, logs=None, **kwargs):
                if logs and "loss" in logs:
                    job.loss = logs["loss"]
                if state:
                    job.current_step = state.global_step
                    if job.total_steps > 0:
                        job.progress = min(job.current_step / job.total_steps, 0.99)
                if callback:
                    callback(job)

        trainer.add_callback(ProgressCallback())
        trainer.train()

    def _save_model(self, model, tokenizer, job: TrainingJob) -> str:
        """Save the fine-tuned model in multiple formats."""
        variant_dir = os.path.join(self.output_base, job.config.variant_id)
        os.makedirs(variant_dir, exist_ok=True)

        # Save LoRA adapters
        lora_path = os.path.join(variant_dir, "lora-adapter")
        model.save_pretrained(lora_path)
        tokenizer.save_pretrained(lora_path)

        # Save merged model (FP16)
        merged_path = os.path.join(variant_dir, "merged-fp16")
        model.save_pretrained_merged(merged_path, tokenizer, save_method="merged_16bit")
        logger.info(f"Saved merged model to: {merged_path}")

        # Save job metadata
        meta = {
            "job_id": job.job_id,
            "variant_id": job.config.variant_id,
            "base_model": job.config.base_model_path,
            "datasets": job.config.datasets,
            "training_config": {
                "lora_r": job.config.lora_r,
                "lora_alpha": job.config.lora_alpha,
                "epochs": job.config.epochs,
                "learning_rate": job.config.learning_rate,
            },
            "completed_at": job.completed_at,
        }
        with open(os.path.join(variant_dir, "metadata.json"), "w") as f:
            json.dump(meta, f, indent=2)

        return merged_path

    def _notify(self, job: TrainingJob, callback):
        """Notify progress callback if set."""
        if callback:
            try:
                callback(job)
            except Exception:
                pass

    def get_job(self, job_id: str) -> TrainingJob | None:
        return self.jobs.get(job_id)

    def list_jobs(self) -> list[dict]:
        return [j.to_dict() for j in self.jobs.values()]

    def cancel_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if job and job.status in (STATUS_QUEUED, STATUS_LOADING, STATUS_TRAINING):
            job.status = STATUS_CANCELLED
            job.completed_at = time.time()
            return True
        return False


# Singleton instance
_fine_tuner: ForgeFineTuner | None = None


def get_fine_tuner(models_dir: str = None) -> ForgeFineTuner:
    global _fine_tuner
    if _fine_tuner is None:
        _fine_tuner = ForgeFineTuner(models_dir=models_dir)
    return _fine_tuner
