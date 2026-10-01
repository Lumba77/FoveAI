import argparse
import logging
import os

# Setup logging for the compiler factory
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("AI_Forge")

# Define base directories
MODEL_DIR = os.getenv("FoveAI_MODELS_ROOT", os.getenv("HF_HOME", "F:/Lumax/Models"))
ENGINE_DIR = os.getenv(
    "TRT_ENGINE_DIR",
    os.path.join(os.path.dirname(MODEL_DIR), "engines").replace("\\", "/"),
)
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(ENGINE_DIR, exist_ok=True)


def compile_imagination():
    """Phase 1: SDXL Turbo TensorRT Download"""
    logger.info("Starting Phase 1: Imagination - Downloading SDXL Turbo TensorRT...")

    model_repo = "stabilityai/sdxl-turbo-tensorrt"
    model_name = "sdxl-turbo-trt"

    out_dir = os.path.join(MODEL_DIR, model_name)

    try:
        from huggingface_hub import snapshot_download

        if not os.path.exists(out_dir):
            logger.info(f"Downloading {model_repo} from Hugging Face...")
            snapshot_download(
                repo_id=model_repo, local_dir=out_dir, local_dir_use_symlinks=False
            )
        else:
            logger.info(f"SDXL Turbo TRT already exists at {out_dir}. Skipping.")

        # Also download a suitable ControlNet (SDXL based)
        cn_repo = "xinsir/controlnet-canny-sdxl-1.0"
        cn_dir = os.path.join(MODEL_DIR, "controlnet-canny-sdxl")
        if not os.path.exists(cn_dir):
            logger.info(f"Downloading {cn_repo} from Hugging Face...")
            snapshot_download(
                repo_id=cn_repo, local_dir=cn_dir, local_dir_use_symlinks=False
            )

    except Exception as e:
        logger.error(f"Failed Phase 1: Imagination - Download failed: {e}")


def compile_ears_and_voice():
    """Phase 2: Whisper & Piper Optimization"""
    logger.info("Starting Phase 2: Sensory (Audio) - Downloading Whisper & Piper...")

    try:
        from huggingface_hub import snapshot_download

        # Whisper (Faster-Whisper Large V3 Turbo)
        whisper_repo = "Systran/faster-whisper-large-v3-turbo-ct2"
        whisper_dir = os.path.join(MODEL_DIR, "whisper-large-v3-turbo")
        if not os.path.exists(whisper_dir):
            logger.info(f"Downloading {whisper_repo}...")
            snapshot_download(
                repo_id=whisper_repo,
                local_dir=whisper_dir,
                local_dir_use_symlinks=False,
            )

        # Piper (ONNX voices are already optimized)
        # We'll download Amy Medium as the default
        piper_repo = "rhasspy/piper-voices"
        piper_dir = os.path.join(MODEL_DIR, "piper-voices")
        if not os.path.exists(piper_dir):
            logger.info(f"Downloading {piper_repo}...")
            # We only need the specific voice file, but snapshot works too
            snapshot_download(
                repo_id=piper_repo,
                local_dir=piper_dir,
                local_dir_use_symlinks=False,
                allow_patterns=["en/en_US/amy/medium/*"],
            )

    except Exception as e:
        logger.error(f"Failed Phase 2: Sensory (Audio) - Download failed: {e}")


def compile_local_brains():
    """Phase 4: Qwen2.5-3B ONNX Model Download & Optimization"""
    logger.info(
        "Starting Phase 4: Brain - Downloading & Optimizing Qwen2.5-3B ONNX Model..."
    )

    # Define the new target ONNX model (3B version)
    model_repo = "littleceasar/qwen2.5-3b-abliterated-onnx"
    model_name = "Qwen2.5-3B-ONNX"

    onnx_model_dir = os.path.join(MODEL_DIR, model_name)
    engine_out_dir = os.path.join(ENGINE_DIR, f"{model_name}-optimized")
    os.makedirs(engine_out_dir, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download

        if not os.path.exists(onnx_model_dir):
            logger.info(f"Downloading {model_repo} from Hugging Face...")
            snapshot_download(
                repo_id=model_repo,
                local_dir=onnx_model_dir,
                local_dir_use_symlinks=False,
            )
            logger.info(f"Qwen2.5 3B ONNX Model Download Complete: {onnx_model_dir}")
        else:
            logger.info(
                f"Qwen2.5 3B ONNX model already exists at {onnx_model_dir}. Skipping."
            )

    except Exception as e:
        logger.error(f"Failed Phase 4: Brain - Download/Optimization failed: {e}")


def compile_sensory_brain():
    """Phase 5: SmolLM2-360M ONNX Model Download & Optimization (for Eyes)"""
    logger.info(
        "Starting Phase 5: Sensory Brain - Downloading & Optimizing SmolLM2-360M ONNX Model (Eyes)..."
    )

    model_repo = "isotnek/SmolLM2-360M-Instruct-heretic"
    model_name = "SmolLM2-360M-ONNX"

    onnx_model_dir = os.path.join(MODEL_DIR, model_name)
    engine_out_dir = os.path.join(ENGINE_DIR, f"{model_name}-optimized")
    os.makedirs(engine_out_dir, exist_ok=True)

    try:
        from huggingface_hub import snapshot_download

        if not os.path.exists(onnx_model_dir):
            logger.info(f"Downloading {model_repo} from Hugging Face...")
            snapshot_download(
                repo_id=model_repo,
                local_dir=onnx_model_dir,
                local_dir_use_symlinks=False,
            )
            logger.info(f"SmolLM2 ONNX Model Download Complete: {onnx_model_dir}")
        else:
            logger.info(
                f"SmolLM2 ONNX model already exists at {onnx_model_dir}. Skipping."
            )

    except Exception as e:
        logger.error(
            f"Failed Phase 5: Sensory Brain - Download/Optimization failed: {e}"
        )


def main():
    parser = argparse.ArgumentParser(description="VR-Compagent Hardware Compiler Forge")
    parser.add_argument(
        "--phase",
        choices=["all", "imagination", "sensory", "brain", "sensory_brain"],
        default="all",
        help="Which subset of models to compile.",
    )
    args = parser.parse_args()

    logger.info("========================================")
    logger.info("Initializing VR-Compagent AI Forge...")

    if args.phase in ["all", "imagination"]:
        compile_imagination()
    if args.phase in ["all", "sensory"]:
        compile_ears_and_voice()
    if args.phase in ["all", "brain"]:
        compile_local_brains()
    if args.phase in ["all", "sensory_brain"]:
        compile_sensory_brain()

    logger.info("Forge processes complete.")


if __name__ == "__main__":
    main()
