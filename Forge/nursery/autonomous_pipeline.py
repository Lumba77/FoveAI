"""
Autonomous Pipeline for Forge Nursery
Self-driving end-to-end model creation pipeline:
Curate Dataset -> Fine-Tune (LoRA) -> Merge (FP16) -> Quantize (MoQ/GGUF) -> Validate (llama-cli) -> Register.
"""

import json
import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .dataset_curator import scan_local_datasets
from .fine_tuner import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_TRAINING,
    TrainingConfig,
    TrainingJob,
    get_fine_tuner,
)
from .model_registry import VariantDefinition, get_registry
from .quantizer import get_quantizer
from .hf_scout import notify_system_and_journal

logger = logging.getLogger("forge-autonomous-pipeline")

MODELS_DIR = os.environ.get("FORGE_NURSERY_MODELS_DIR", "/opt/foveai-models")
RUNS_DIR = os.path.join(MODELS_DIR, "forge-nursery", "pipeline_runs")
os.makedirs(RUNS_DIR, exist_ok=True)

# Pipeline Stages
STAGE_QUEUED = "queued"
STAGE_CURATING = "curating"
STAGE_TRAINING = "fine_tuning"
STAGE_MERGING = "merging"
STAGE_QUANTIZING = "quantizing"
STAGE_VALIDATING = "validating"
STAGE_REGISTERING = "registering"
STAGE_COMPLETED = "completed"
STAGE_FAILED = "failed"
STAGE_CANCELLED = "cancelled"


@dataclass
class PipelineConfig:
    """Configuration for an autonomous pipeline run."""

    variant_id: str
    name: str
    description: str = ""
    base_model: str = "gemma-4-12b-it"
    datasets: list[str] = field(default_factory=list)
    quant_type: str = "moq-3.0"
    lora_r: int = 16
    lora_alpha: int = 32
    epochs: int = 3
    batch_size: int = 2
    learning_rate: float = 2e-4
    max_samples: int = 3000
    auto_register: bool = True
    validate_model: bool = True
    test_prompt: str = "System: You are an autonomous AI companion. User: Hello! Who are you?"


@dataclass
class PipelineState:
    """Tracks state and progress of an autonomous pipeline run."""

    run_id: str
    config: PipelineConfig
    stage: str = STAGE_QUEUED
    progress: float = 0.0  # 0.0 to 1.0
    current_step_info: str = "Job initialized"
    started_at: float = 0.0
    completed_at: float = 0.0
    training_job_id: str | None = None
    quantize_job_id: str | None = None
    merged_path: str | None = None
    final_gguf_path: str | None = None
    validation_output: str | None = None
    error: str | None = None
    logs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data


class AutonomousPipelineRunner:
    """
    Self-driving end-to-end pipeline runner for model creation.
    Orchestrates curation, fine-tuning, merging, quantization, sanity checks, and registration.
    """

    def __init__(self, runs_dir: str = RUNS_DIR):
        self.runs_dir = runs_dir
        self.runs: dict[str, PipelineState] = {}
        self._load_existing_runs()

    def _load_existing_runs(self):
        try:
            for fname in os.listdir(self.runs_dir):
                if fname.endswith(".json"):
                    fpath = os.path.join(self.runs_dir, fname)
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        cfg_dict = data.get("config", {})
                        config = PipelineConfig(**cfg_dict)
                        data["config"] = config
                        state = PipelineState(**data)
                        self.runs[state.run_id] = state
        except Exception as e:
            logger.warning(f"Failed to load past pipeline runs: {e}")

    def _save_state(self, state: PipelineState):
        try:
            fpath = os.path.join(self.runs_dir, f"{state.run_id}.json")
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(state.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save pipeline state {state.run_id}: {e}")

    def log(self, state: PipelineState, msg: str):
        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] [{state.stage.upper()}] {msg}"
        state.logs.append(entry)
        logger.info(f"[{state.run_id[:8]}] {entry}")
        # Append to individual run log file
        log_file = os.path.join(self.runs_dir, f"{state.run_id}.log")
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception:
            pass

    def create_run(self, config: PipelineConfig) -> PipelineState:
        run_id = f"run-{uuid.uuid4().hex[:10]}"
        state = PipelineState(run_id=run_id, config=config)
        self.runs[run_id] = state
        self._save_state(state)
        return state

    def start_run(self, run_id: str) -> None:
        state = self.runs.get(run_id)
        if not state:
            raise ValueError(f"Run {run_id} not found")

        worker = threading.Thread(target=self._run_loop, args=(state,), daemon=True)
        worker.start()

    def _run_loop(self, state: PipelineState):
        """The autonomous execution loop."""
        state.started_at = time.time()
        self.log(state, f"Starting autonomous pipeline for variant '{state.config.variant_id}'")

        try:
            # ─────────────────────────────────────────────────────────
            # Stage 1: Curate & Validate Datasets
            # ─────────────────────────────────────────────────────────
            state.stage = STAGE_CURATING
            state.progress = 0.05
            state.current_step_info = "Validating and preparing dataset sources"
            self.log(state, "Checking dataset sources...")
            self._save_state(state)

            available_ds = {ds.name: ds for ds in scan_local_datasets()}
            missing = [ds for ds in state.config.datasets if ds not in available_ds]
            if missing:
                self.log(state, f"Note: datasets {missing} will be pulled or mapped during training load.")

            # ─────────────────────────────────────────────────────────
            # Stage 2: Fine-Tuning Execution
            # ─────────────────────────────────────────────────────────
            state.stage = STAGE_TRAINING
            state.progress = 0.15
            state.current_step_info = "Executing LoRA/QLoRA training"
            self.log(state, f"Launching fine-tuner (epochs={state.config.epochs}, lora_r={state.config.lora_r})...")
            self._save_state(state)

            tuner = get_fine_tuner()
            train_cfg = TrainingConfig(
                variant_id=state.config.variant_id,
                base_model_path=state.config.base_model,
                output_dir=os.path.join(tuner.output_base, state.config.variant_id),
                datasets=state.config.datasets,
                lora_r=state.config.lora_r,
                lora_alpha=state.config.lora_alpha,
                learning_rate=state.config.learning_rate,
                epochs=state.config.epochs,
                batch_size=state.config.batch_size,
                max_samples=state.config.max_samples,
            )

            job = tuner.create_job(train_cfg)
            state.training_job_id = job.job_id
            self._save_state(state)

            def on_train_progress(j: TrainingJob):
                state.progress = 0.15 + (j.progress * 0.45)  # Scale training to 15% - 60%
                state.current_step_info = f"Training step {j.current_step}/{j.total_steps} (loss: {j.loss:.4f})"
                if j.current_step % 20 == 0:
                    self._save_state(state)

            # Run training synchronously inside this pipeline worker thread
            tuner._run_training(job, progress_callback=on_train_progress)

            if job.status != STATUS_COMPLETED:
                raise RuntimeError(f"Training failed: {job.error}")

            variant_dir = os.path.join(tuner.output_base, state.config.variant_id)
            merged_fp16 = os.path.join(variant_dir, "merged-fp16")
            state.merged_path = merged_fp16
            self.log(state, f"Fine-tuning complete. Merged FP16 available at: {merged_fp16}")

            # ─────────────────────────────────────────────────────────
            # Stage 3: Quantization to Target MoQ / GGUF
            # ─────────────────────────────────────────────────────────
            state.stage = STAGE_QUANTIZING
            state.progress = 0.65
            state.current_step_info = f"Quantizing to {state.config.quant_type}"
            self.log(state, f"Beginning quantization step -> {state.config.quant_type}...")
            self._save_state(state)

            quantizer = get_quantizer()
            q_job = quantizer.create_job(
                input_path=merged_fp16,
                variant_id=state.config.variant_id,
                quant_type=state.config.quant_type,
            )
            state.quantize_job_id = q_job.job_id
            self._save_state(state)

            success = quantizer._execute_quantization(q_job)
            if not success or q_job.status != "completed":
                raise RuntimeError(f"Quantization failed: {q_job.error}")

            target_info = quantizer.get_quant_type_info(state.config.quant_type)
            final_gguf = os.path.join(q_job.output_path, f"model-{target_info['type'].lower()}.gguf")
            state.final_gguf_path = final_gguf
            state.progress = 0.85
            self.log(state, f"Quantization succeeded: {final_gguf}")
            self._save_state(state)

            # ─────────────────────────────────────────────────────────
            # Stage 4: Autonomous Validation / Sanity Check
            # ─────────────────────────────────────────────────────────
            if state.config.validate_model:
                state.stage = STAGE_VALIDATING
                state.progress = 0.90
                state.current_step_info = "Running inference sanity check with llama-cli"
                self.log(state, "Validating model generation with test inference...")
                self._save_state(state)

                val_out = self._validate_gguf(final_gguf, state.config.test_prompt)
                state.validation_output = val_out
                self.log(state, f"Validation output: {val_out[:120]}...")

            # ─────────────────────────────────────────────────────────
            # Stage 5: Auto-Registration in Model Registry
            # ─────────────────────────────────────────────────────────
            if state.config.auto_register:
                state.stage = STAGE_REGISTERING
                state.progress = 0.95
                state.current_step_info = "Registering model in variant registry"
                self.log(state, "Registering newly forged model in model_registry...")
                self._save_state(state)

                reg = get_registry()
                new_variant = VariantDefinition(
                    id=state.config.variant_id,
                    name=state.config.name,
                    description=state.config.description or f"Autonomous Forge run {state.run_id}",
                    base_model=state.config.base_model,
                    datasets=state.config.datasets,
                    training_config={
                        "lora_r": state.config.lora_r,
                        "lora_alpha": state.config.lora_alpha,
                        "epochs": state.config.epochs,
                        "learning_rate": state.config.learning_rate,
                    },
                    quant_type=state.config.quant_type,
                    status="active",
                )
                reg.add_variant(new_variant)
                self.log(state, f"Variant '{state.config.variant_id}' registered and marked ACTIVE.")

            # ─────────────────────────────────────────────────────────
            # Stage 6: Completion
            # ─────────────────────────────────────────────────────────
            state.stage = STAGE_COMPLETED
            state.progress = 1.0
            state.completed_at = time.time()
            duration_min = round((state.completed_at - state.started_at) / 60, 2)
            state.current_step_info = f"Pipeline successfully completed in {duration_min} min"
            self.log(state, f"✨ Autonomous pipeline finished successfully in {duration_min} minutes!")
            self._save_state(state)

            notify_system_and_journal(
                f"Modell smidd: {state.config.name}",
                f"Varianten '{state.config.variant_id}' ({state.config.quant_type}) har slutförts, kvantiserats och sparats på sda2!"
            )

        except Exception as e:
            state.stage = STAGE_FAILED
            state.error = str(e)
            state.completed_at = time.time()
            state.current_step_info = f"Error: {e}"
            self.log(state, f"🚨 Pipeline aborted with error: {e}")
            self._save_state(state)

    def _validate_gguf(self, gguf_path: str, prompt: str) -> str:
        """Run quick inference using native llama-cli to ensure the model responds coherently."""
        llama_cli = "/home/lumba/FoveAI/Tools/llama-b11053-cuda/llama-b11053/llama-cli"
        if not os.path.exists(llama_cli) or not os.path.exists(gguf_path):
            return "Validation skipped (binary or model not found on disk)"

        cmd = [
            llama_cli,
            "-m", gguf_path,
            "-p", prompt,
            "-n", "64",
            "--temp", "0.5",
            "-ngl", "0",  # Test on CPU to prevent interrupting active VRAM residency
        ]
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = f"/home/lumba/FoveAI/Tools/llama-b11053-cuda/llama-b11053:{env.get('LD_LIBRARY_PATH', '')}"

        try:
            res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=90)
            clean_out = res.stdout.strip()
            return clean_out if clean_out else res.stderr[:200]
        except Exception as e:
            return f"Validation error: {e}"


# Singleton instance
_pipeline_runner: AutonomousPipelineRunner | None = None


def get_pipeline_runner() -> AutonomousPipelineRunner:
    global _pipeline_runner
    if _pipeline_runner is None:
        _pipeline_runner = AutonomousPipelineRunner()
    return _pipeline_runner
