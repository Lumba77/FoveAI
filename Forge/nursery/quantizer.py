"""
Quantizer for Forge Nursery
Handles GGUF dequantization → training → MoQ requantization pipeline.
Uses Unsloth's llama.cpp binaries for GGUF operations.
"""

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# MoQ quantization types (Gemma 4 12B and Swarm 0.5B optimized)
QUANT_TYPES = {
    "moq-0.5b-fast": {
        "label": "MoQ 0.5B Fast (Swarm - 220MB)",
        "type": "Q3_K_M",
        "description": "Ultra-lightweight profile for cooperative swarm models",
    },
    "moq-0.5b-precise": {
        "label": "MoQ 0.5B Precise (Swarm - 290MB)",
        "type": "Q4_K_M",
        "description": "Optimized precision for logical/code speculators",
    },
    "moq-3.0": {
        "label": "MoQ 3.0 (Companion - 4.5GB)",
        "type": "Q4_K_M",
        "description": "Balanced quality/size for companion model",
    },
    "moq-3.5": {
        "label": "MoQ 3.5 (Coding - 5.2GB)",
        "type": "Q5_K_M",
        "description": "Higher precision for coding tasks",
    },
    "moq-4.0": {
        "label": "MoQ 4.0 (Max Quality - 7.8GB)",
        "type": "Q6_K",
        "description": "Maximum quality, larger size",
    },
    "q4_0": {
        "label": "Q4_0 (4-bit, 4.5GB)",
        "type": "Q4_0",
        "description": "Standard 4-bit quantization",
    },
    "q4_k_m": {
        "label": "Q4_K_M (4-bit K-quant, 4.8GB)",
        "type": "Q4_K_M",
        "description": "K-quant medium, good all-rounder",
    },
    "q5_k_m": {
        "label": "Q5_K_M (5-bit K-quant, 5.2GB)",
        "type": "Q5_K_M",
        "description": "5-bit K-quant, better quality",
    },
    "q8_0": {
        "label": "Q8_0 (8-bit, 8.5GB)",
        "type": "Q8_0",
        "description": "Near-lossless 8-bit",
    },
    "f16": {
        "label": "F16 (Full precision, 24GB)",
        "type": "F16",
        "description": "Full FP16, no quantization loss",
    },
}


@dataclass
class QuantizeJob:
    """Tracks a quantization job."""

    job_id: str
    input_path: str  # Path to merged FP16 model
    output_path: str
    quant_type: str  # Key from QUANT_TYPES
    status: str = "queued"
    progress: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "input_path": self.input_path,
            "output_path": self.output_path,
            "quant_type": self.quant_type,
            "status": self.status,
            "progress": self.progress,
            "error": self.error,
        }


class ForgeQuantizer:
    """
    Manages GGUF quantization using Unsloth's bundled llama.cpp binaries.
    Pipeline: FP16 merged model → GGUF conversion → MoQ quantization.
    """

    def __init__(self, models_dir: str = None):
        self.models_dir = models_dir or os.path.join(
            os.path.expanduser("~"), ".cache", "huggingface", "hub"
        )
        self.output_base = os.path.join(self.models_dir, "lumax-forge")
        self.jobs: dict[str, QuantizeJob] = {}

        # Locate llama.cpp binaries (bundled with Unsloth)
        self._llama_cpp_dir = self._find_llama_cpp()

    def _find_llama_cpp(self) -> str | None:
        """Find llama.cpp binaries from Unsloth installation."""
        # Check Unsloth's bundled llama.cpp
        candidates = [
            os.path.join(os.path.expanduser("~"), ".unsloth", "llama.cpp"),
            os.path.join(os.path.expanduser("~"), ".cache", "unsloth", "llama.cpp"),
            # Fallback: system-installed
            "C:\\llama.cpp",
        ]

        for candidate in candidates:
            convert_py = os.path.join(candidate, "convert_hf_to_gguf.py")
            quantize_exe = os.path.join(
                candidate, "build", "bin", "Release", "quantize.exe"
            )
            if os.path.exists(convert_py) or os.path.exists(quantize_exe):
                logger.info(f"Found llama.cpp at: {candidate}")
                return candidate

        logger.warning("llama.cpp not found. Quantization will be unavailable.")
        return None

    def create_job(
        self,
        input_path: str,
        variant_id: str,
        quant_type: str = "moq-3.0",
    ) -> QuantizeJob:
        """Create a new quantization job."""
        import time

        if quant_type not in QUANT_TYPES:
            raise ValueError(
                f"Unknown quant type: {quant_type}. Options: {list(QUANT_TYPES.keys())}"
            )

        job_id = f"quant-{variant_id}-{int(time.time())}"
        output_path = os.path.join(self.output_base, variant_id, f"gguf-{quant_type}")
        os.makedirs(output_path, exist_ok=True)

        job = QuantizeJob(
            job_id=job_id,
            input_path=input_path,
            output_path=output_path,
            quant_type=quant_type,
        )
        self.jobs[job_id] = job
        logger.info(f"Created quantization job: {job_id} ({quant_type})")
        return job

    def run_quantize(self, job: QuantizeJob) -> bool:
        """
        Execute the full quantization pipeline:
        1. Convert HF model → GGUF (FP16)
        2. Quantize GGUF to target type
        """
        if not self._llama_cpp_dir:
            job.status = "failed"
            job.error = "llama.cpp not found. Install Unsloth or llama.cpp."
            return False

        try:
            job.status = "converting"
            job.progress = 0.1

            # Step 1: Convert HF model to GGUF FP16
            gguf_fp16_path = self._convert_to_gguf(job)
            if not gguf_fp16_path:
                return False

            job.progress = 0.5
            job.status = "quantizing"

            # Step 2: Quantize to target type
            quant_type_info = QUANT_TYPES[job.quant_type]
            # Make the output file name dynamic based on the variant_id (rather than hardcoded gemma-4-12b)
            output_file = os.path.join(
                job.output_path, f"{job.job_id.replace('quant-', '')}.gguf"
            )

            success = self._quantize_gguf(
                input_path=gguf_fp16_path,
                output_path=output_file,
                quant_type=quant_type_info["type"],
            )

            if success:
                job.status = "completed"
                job.progress = 1.0
                logger.info(f"Quantization complete: {output_file}")

                # Save metadata
                meta = {
                    "job_id": job.job_id,
                    "quant_type": job.quant_type,
                    "quant_label": quant_type_info["label"],
                    "input_path": job.input_path,
                    "output_file": output_file,
                }
                with open(os.path.join(job.output_path, "quant_meta.json"), "w") as f:
                    json.dump(meta, f, indent=2)

                return True
            else:
                job.status = "failed"
                job.error = "Quantization step failed"
                return False

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            logger.error(f"Quantization failed: {e}")
            return False

    def _convert_to_gguf(self, job: QuantizeJob) -> str | None:
        """Convert HuggingFace model to GGUF FP16 format."""
        convert_script = os.path.join(self._llama_cpp_dir, "convert_hf_to_gguf.py")

        if not os.path.exists(convert_script):
            # Try the newer unified convert script
            convert_script = os.path.join(self._llama_cpp_dir, "convert_hf_to_gguf.py")

        if not os.path.exists(convert_script):
            job.error = f"convert_hf_to_gguf.py not found in {self._llama_cpp_dir}"
            job.status = "failed"
            return None

        output_path = os.path.join(job.output_path, "model-fp16.gguf")

        cmd = [
            "python",
            convert_script,
            job.input_path,
            "--outfile",
            output_path,
            "--outtype",
            "f16",
        ]

        logger.info(f"Converting to GGUF: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

        if result.returncode != 0:
            job.error = f"GGUF conversion failed: {result.stderr}"
            job.status = "failed"
            logger.error(job.error)
            return None

        logger.info(f"GGUF FP16 created: {output_path}")
        return output_path

    def _quantize_gguf(
        self,
        input_path: str,
        output_path: str,
        quant_type: str,
    ) -> bool:
        """Quantize a GGUF file to the target quantization type."""
        # Find quantize binary
        quantize_exe = None
        for candidate in [
            os.path.join(
                self._llama_cpp_dir, "build", "bin", "Release", "quantize.exe"
            ),
            os.path.join(self._llama_cpp_dir, "build", "bin", "quantize.exe"),
            os.path.join(self._llama_cpp_dir, "quantize.exe"),
            os.path.join(self._llama_cpp_dir, "build", "bin", "quantize"),
        ]:
            if os.path.exists(candidate):
                quantize_exe = candidate
                break

        if not quantize_exe:
            # Try building it
            logger.warning("quantize binary not found, attempting build...")
            quantize_exe = self._build_quantize()

        if not quantize_exe:
            job_error = "quantize binary not found and build failed"
            logger.error(job_error)
            return False

        cmd = [quantize_exe, input_path, output_path, quant_type]

        logger.info(f"Quantizing: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)

        if result.returncode != 0:
            logger.error(f"Quantization failed: {result.stderr}")
            return False

        logger.info(f"Quantized model created: {output_path}")
        return True

    def _build_quantize(self) -> str | None:
        """Attempt to build the quantize binary from llama.cpp source."""
        build_dir = os.path.join(self._llama_cpp_dir, "build")
        os.makedirs(build_dir, exist_ok=True)

        try:
            # CMake configure
            subprocess.run(
                ["cmake", "..", "-DLLAMA_CUDA=ON"],
                cwd=build_dir,
                capture_output=True,
                timeout=300,
                check=True,
            )
            # Build quantize target only
            subprocess.run(
                [
                    "cmake",
                    "--build",
                    ".",
                    "--target",
                    "quantize",
                    "--config",
                    "Release",
                ],
                cwd=build_dir,
                capture_output=True,
                timeout=600,
                check=True,
            )

            quantize_exe = os.path.join(build_dir, "bin", "Release", "quantize.exe")
            if os.path.exists(quantize_exe):
                logger.info(f"Built quantize: {quantize_exe}")
                return quantize_exe
        except subprocess.CalledProcessError as e:
            logger.error(f"Build failed: {e.stderr}")

        return None

    def get_job(self, job_id: str) -> QuantizeJob | None:
        return self.jobs.get(job_id)

    def list_jobs(self) -> list[dict]:
        return [j.to_dict() for j in self.jobs.values()]

    def list_quant_types(self) -> dict:
        """Return available quantization types with descriptions."""
        return QUANT_TYPES

    def get_quantized_models(self, variant_id: str) -> list[dict]:
        """List all quantized GGUF files for a variant."""
        variant_dir = os.path.join(self.output_base, variant_id)
        if not os.path.exists(variant_dir):
            return []

        models = []
        for entry in os.listdir(variant_dir):
            if entry.startswith("gguf-"):
                quant_dir = os.path.join(variant_dir, entry)
                meta_path = os.path.join(quant_dir, "quant_meta.json")
                gguf_files = list(Path(quant_dir).glob("*.gguf"))

                info = {
                    "quant_type": entry.replace("gguf-", ""),
                    "directory": quant_dir,
                    "files": [str(f) for f in gguf_files],
                }

                if os.path.exists(meta_path):
                    with open(meta_path) as f:
                        info["meta"] = json.load(f)

                models.append(info)

        return models


# Singleton
_quantizer: ForgeQuantizer | None = None


def get_quantizer(models_dir: str = None) -> ForgeQuantizer:
    global _quantizer
    if _quantizer is None:
        _quantizer = ForgeQuantizer(models_dir=models_dir)
    return _quantizer
