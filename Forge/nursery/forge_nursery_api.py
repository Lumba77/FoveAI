"""
Forge Nursery API — FastAPI service on port 8105
Provides REST endpoints for variant management, fine-tuning, and quantization.
Integrated with XR_Vessel WebUI under OPERATIONS menu.
"""

import logging
import os
import threading

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .dataset_curator import load_dataset_for_training, scan_local_datasets
from .fine_tuner import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_QUEUED,
    STATUS_TRAINING,
    TrainingConfig,
    TrainingJob,
    get_fine_tuner,
)
from .model_registry import VariantDefinition, get_registry
from .quantizer import get_quantizer
from .autonomous_pipeline import PipelineConfig, get_pipeline_runner
from .hf_scout import get_model_scout

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("forge-nursery-api")

# ─── FastAPI App ───────────────────────────────────────────
app = FastAPI(
    title="Forge Nursery API",
    description="Fine-tuning pipeline for Gemma 4 12B variants",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Pydantic Models ───────────────────────────────────────


class VariantCreateRequest(BaseModel):
    variant_id: str = Field(..., description="Unique variant identifier")
    name: str = Field(..., description="Display name")
    description: str = Field("", description="Variant description")
    base_model: str = Field("gemma-4-12b-it", description="Base model to fine-tune")
    datasets: list[str] = Field(default_factory=list, description="HF dataset IDs")
    lora_r: int = Field(16, description="LoRA rank")
    lora_alpha: int = Field(32, description="LoRA alpha")
    epochs: int = Field(3, description="Training epochs")
    learning_rate: float = Field(2e-4, description="Learning rate")
    quant_type: str = Field("moq-3.0", description="Quantization type after training")


class TrainingStartRequest(BaseModel):
    variant_id: str = Field(..., description="Variant to train")
    max_samples: int = Field(5000, description="Max samples per dataset")


class QuantizeRequest(BaseModel):
    variant_id: str = Field(..., description="Variant to quantize")
    input_path: str = Field(..., description="Path to merged FP16 model")
    quant_type: str = Field("moq-3.0", description="Target quantization type")


class DatasetPreviewRequest(BaseModel):
    dataset_id: str = Field(..., description="Dataset ID to preview")
    max_samples: int = Field(5, description="Number of samples to return")


# ─── Health & Info ─────────────────────────────────────────


@app.get("/health")
async def health():
    return {"status": "ok", "service": "forge-nursery", "port": 8105}


@app.get("/api/status")
async def get_status():
    """Get overall Forge Nursery status."""
    registry = get_registry()
    fine_tuner = get_fine_tuner()
    quantizer = get_quantizer()

    variants = registry.list_variants()
    training_jobs = fine_tuner.list_jobs()
    quant_jobs = quantizer.list_jobs()

    return {
        "variants": len(variants),
        "active_training_jobs": sum(
            1 for j in training_jobs if j["status"] in (STATUS_QUEUED, STATUS_TRAINING)
        ),
        "completed_training_jobs": sum(
            1 for j in training_jobs if j["status"] == STATUS_COMPLETED
        ),
        "failed_training_jobs": sum(
            1 for j in training_jobs if j["status"] == STATUS_FAILED
        ),
        "quant_jobs": len(quant_jobs),
        "llama_cpp_available": quantizer._llama_cpp_dir is not None,
    }


# ─── Variant Management ────────────────────────────────────


@app.get("/api/variants")
async def list_variants():
    """List all registered variants."""
    registry = get_registry()
    return registry.list_variants()


@app.get("/api/variants/{variant_id}")
async def get_variant(variant_id: str):
    """Get a specific variant definition."""
    registry = get_registry()
    variant = registry.get_variant(variant_id)
    if not variant:
        raise HTTPException(status_code=404, detail=f"Variant not found: {variant_id}")
    return variant.to_dict()


@app.post("/api/variants")
async def create_variant(req: VariantCreateRequest):
    """Create a new variant definition."""
    registry = get_registry()

    if registry.get_variant(req.variant_id):
        raise HTTPException(
            status_code=409, detail=f"Variant already exists: {req.variant_id}"
        )

    variant = VariantDefinition(
        id=req.variant_id,
        name=req.name,
        description=req.description,
        base_model=req.base_model,
        datasets=req.datasets,
        training_config={
            "lora_r": req.lora_r,
            "lora_alpha": req.lora_alpha,
            "epochs": req.epochs,
            "learning_rate": req.learning_rate,
        },
        quant_type=req.quant_type,
    )

    registry.add_variant(variant)
    logger.info(f"Created variant: {req.variant_id}")
    return variant.to_dict()


@app.delete("/api/variants/{variant_id}")
async def delete_variant(variant_id: str):
    """Delete a variant definition."""
    registry = get_registry()
    if not registry.get_variant(variant_id):
        raise HTTPException(status_code=404, detail=f"Variant not found: {variant_id}")
    registry.remove_variant(variant_id)
    return {"deleted": variant_id}


# ─── Dataset Operations ────────────────────────────────────


@app.get("/api/datasets")
async def list_datasets():
    """Scan and list all locally available datasets."""
    datasets = scan_local_datasets()
    return [
        {
            "id": ds.name,
            "path": ds.path,
            "size_mb": round(ds.size_bytes / (1024 * 1024), 2) if ds.size_bytes else 0,
            "format": ds.format,
            "sample_count": ds.sample_count,
        }
        for ds in datasets
    ]


@app.post("/api/datasets/preview")
async def preview_dataset(req: DatasetPreviewRequest):
    """Preview samples from a dataset."""
    datasets = scan_local_datasets()
    ds_map = {ds.name: ds for ds in datasets}

    if req.dataset_id not in ds_map:
        raise HTTPException(
            status_code=404, detail=f"Dataset not found: {req.dataset_id}"
        )

    ds_info = ds_map[req.dataset_id]
    samples = load_dataset_for_training(ds_info, max_samples=req.max_samples)

    return {
        "dataset_id": req.dataset_id,
        "total_available": ds_info.sample_count,
        "samples": samples[: req.max_samples],
    }


# ─── Training Jobs ─────────────────────────────────────────


@app.get("/api/training/jobs")
async def list_training_jobs():
    """List all training jobs."""
    fine_tuner = get_fine_tuner()
    return fine_tuner.list_jobs()


@app.get("/api/training/jobs/{job_id}")
async def get_training_job(job_id: str):
    """Get a specific training job status."""
    fine_tuner = get_fine_tuner()
    job = fine_tuner.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job.to_dict()


@app.post("/api/training/start")
async def start_training(req: TrainingStartRequest):
    """Start a fine-tuning job for a variant."""
    registry = get_registry()
    fine_tuner = get_fine_tuner()

    variant = registry.get_variant(req.variant_id)
    if not variant:
        raise HTTPException(
            status_code=404, detail=f"Variant not found: {req.variant_id}"
        )

    # Build training config from variant definition
    tc = variant.training_config or {}
    config = TrainingConfig(
        variant_id=req.variant_id,
        base_model_path=variant.base_model,
        output_dir=os.path.join(fine_tuner.output_base, req.variant_id),
        datasets=variant.datasets,
        lora_r=tc.get("lora_r", 16),
        lora_alpha=tc.get("lora_alpha", 32),
        epochs=tc.get("epochs", 3),
        learning_rate=tc.get("learning_rate", 2e-4),
        max_samples=req.max_samples,
    )

    job = fine_tuner.create_job(config)
    fine_tuner.start_job(job.job_id)

    logger.info(f"Started training job: {job.job_id} for variant {req.variant_id}")
    return job.to_dict()


@app.post("/api/training/jobs/{job_id}/cancel")
async def cancel_training(job_id: str):
    """Cancel a running training job."""
    fine_tuner = get_fine_tuner()
    if fine_tuner.cancel_job(job_id):
        return {"cancelled": job_id}
    raise HTTPException(
        status_code=404, detail=f"Job not found or not cancellable: {job_id}"
    )


# ─── Quantization ──────────────────────────────────────────


@app.get("/api/quantize/types")
async def list_quant_types():
    """List available quantization types."""
    quantizer = get_quantizer()
    return quantizer.list_quant_types()


@app.get("/api/quantize/jobs")
async def list_quantize_jobs():
    """List all quantization jobs."""
    quantizer = get_quantizer()
    return quantizer.list_jobs()


@app.get("/api/quantize/models/{variant_id}")
async def list_quantized_models(variant_id: str):
    """List quantized GGUF files for a variant."""
    quantizer = get_quantizer()
    return quantizer.get_quantized_models(variant_id)


@app.post("/api/quantize/start")
async def start_quantize(req: QuantizeRequest):
    """Start quantization of a merged model."""
    quantizer = get_quantizer()

    if not quantizer._llama_cpp_dir:
        raise HTTPException(
            status_code=503,
            detail="llama.cpp not found. Quantization unavailable. Install Unsloth or llama.cpp.",
        )

    job = quantizer.create_job(
        input_path=req.input_path,
        variant_id=req.variant_id,
        quant_type=req.quant_type,
    )

    # Run in background thread
    thread = threading.Thread(target=quantizer.run_quantize, args=(job,), daemon=True)
    thread.start()

    logger.info(f"Started quantization job: {job.job_id}")
    return job.to_dict()


# ─── Full Pipeline ─────────────────────────────────────────


class ForgeRequest(BaseModel):
    variant_id: str = Field(..., description="Variant to forge")
    max_samples: int = Field(5000, description="Max training samples")
    quant_type: str = Field("moq-3.0", description="Target quantization type")
    auto_quantize: bool = Field(True, description="Auto-quantize after training")


@app.post("/api/forge")
async def forge_variant(req: ForgeRequest):
    """
    Full pipeline: train + quantize a variant in one request.
    Training runs async; quantization triggers automatically on completion.
    """
    registry = get_registry()
    fine_tuner = get_fine_tuner()
    quantizer = get_quantizer()

    variant = registry.get_variant(req.variant_id)
    if not variant:
        raise HTTPException(
            status_code=404, detail=f"Variant not found: {req.variant_id}"
        )

    tc = variant.training_config or {}
    config = TrainingConfig(
        variant_id=req.variant_id,
        base_model_path=variant.base_model,
        output_dir=os.path.join(fine_tuner.output_base, req.variant_id),
        datasets=variant.datasets,
        lora_r=tc.get("lora_r", 16),
        lora_alpha=tc.get("lora_alpha", 32),
        epochs=tc.get("epochs", 3),
        learning_rate=tc.get("learning_rate", 2e-4),
        max_samples=req.max_samples,
    )

    job = fine_tuner.create_job(config)

    # Define a progress callback that auto-triggers quantization
    def on_training_complete(training_job: TrainingJob):
        if training_job.status == STATUS_COMPLETED and req.auto_quantize:
            if training_job.output_path and quantizer._llama_cpp_dir:
                logger.info(f"Auto-quantizing {req.variant_id} after training...")
                qjob = quantizer.create_job(
                    input_path=training_job.output_path,
                    variant_id=req.variant_id,
                    quant_type=req.quant_type,
                )
                quantizer.run_quantize(qjob)
            else:
                logger.warning("Cannot auto-quantize: no output path or no llama.cpp")

    fine_tuner.start_job(job.job_id, progress_callback=on_training_complete)

    logger.info(f"Started forge pipeline: {job.job_id} for variant {req.variant_id}")
    return {
        "job_id": job.job_id,
        "variant_id": req.variant_id,
        "status": "started",
        "auto_quantize": req.auto_quantize,
        "quant_type": req.quant_type if req.auto_quantize else None,
    }


# ─── Autonomous Pipeline Endpoints ─────────────────────────


class AutonomousPipelineStartRequest(BaseModel):
    variant_id: str = Field(..., description="Unique variant identifier")
    name: str = Field(..., description="Display name")
    description: str = Field("", description="Variant description")
    base_model: str = Field("gemma-4-12b-it", description="Base model name or path")
    datasets: list[str] = Field(default_factory=list, description="Dataset IDs or paths")
    quant_type: str = Field("moq-3.0", description="Target quantization profile")
    lora_r: int = Field(16, description="LoRA rank")
    lora_alpha: int = Field(32, description="LoRA alpha")
    epochs: int = Field(3, description="Training epochs")
    batch_size: int = Field(2, description="Batch size")
    learning_rate: float = Field(2e-4, description="Learning rate")
    max_samples: int = Field(3000, description="Max training samples")
    auto_register: bool = Field(True, description="Auto-register upon completion")
    validate_model: bool = Field(True, description="Run inference sanity test after quant")


@app.post("/api/pipeline/start")
async def start_autonomous_pipeline(req: AutonomousPipelineStartRequest):
    """
    Launch a fully autonomous end-to-end model creation pipeline:
    Curate -> Fine-Tune -> Merge FP16 -> Quantize MoQ -> Validate -> Register.
    """
    runner = get_pipeline_runner()
    cfg = PipelineConfig(
        variant_id=req.variant_id,
        name=req.name,
        description=req.description,
        base_model=req.base_model,
        datasets=req.datasets,
        quant_type=req.quant_type,
        lora_r=req.lora_r,
        lora_alpha=req.lora_alpha,
        epochs=req.epochs,
        batch_size=req.batch_size,
        learning_rate=req.learning_rate,
        max_samples=req.max_samples,
        auto_register=req.auto_register,
        validate_model=req.validate_model,
    )
    state = runner.create_run(cfg)
    runner.start_run(state.run_id)
    return {
        "status": "started",
        "run_id": state.run_id,
        "variant_id": req.variant_id,
        "stage": state.stage,
    }


@app.get("/api/pipeline/runs")
async def list_pipeline_runs():
    """List all autonomous pipeline runs and their current states."""
    runner = get_pipeline_runner()
    return [r.to_dict() for r in runner.runs.values()]


@app.get("/api/pipeline/runs/{run_id}")
async def get_pipeline_run(run_id: str):
    """Get the current state and progress of an autonomous pipeline run."""
    runner = get_pipeline_runner()
    state = runner.runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return state.to_dict()


@app.get("/api/pipeline/runs/{run_id}/logs")
async def get_pipeline_run_logs(run_id: str):
    """Get the live logs of a specific pipeline run."""
    runner = get_pipeline_runner()
    state = runner.runs.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return {"run_id": run_id, "logs": state.logs}


# ─── Model Scout & Open XRL Provisioning Endpoints ──────────


@app.get("/api/scout/search")
async def scout_models(query: str = "Qwen3.5 MoQ", limit: int = 10):
    """Search Hugging Face for GGUF/MoQ models suitable for FoveAI & Open XRL."""
    scout = get_model_scout()
    candidates = scout.search_candidates(query=query, limit=limit)
    return [c.to_dict() for c in candidates]


class ModelAdoptRequest(BaseModel):
    repo_id: str = Field(..., description="HuggingFace repo ID")
    filename: str = Field(..., description="GGUF filename inside repo")
    variant_id: str | None = Field(None, description="Optional custom variant ID")
    display_name: str | None = Field(None, description="Optional display name")
    quant_type: str = Field("moq", description="Quantization profile")


@app.post("/api/scout/adopt")
async def adopt_model(req: ModelAdoptRequest):
    """
    Download a model to /opt/foveai-models/hub, run a sanity benchmark,
    and provision an Open XRL contract profile in the model registry.
    """
    scout = get_model_scout()
    try:
        result = scout.adopt_model_with_xrl(
            repo_id=req.repo_id,
            filename=req.filename,
            variant_id=req.variant_id,
            display_name=req.display_name,
            quant_type=req.quant_type,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Adoption failed: {e}")


# ─── Main ──────────────────────────────────────────────────


def main():
    """Start the Forge Nursery API server."""
    logger.info("Starting Forge Nursery API on port 8105...")
    uvicorn.run(
        "Forge.nursery.forge_nursery_api:app",
        host="0.0.0.0",
        port=8105,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
