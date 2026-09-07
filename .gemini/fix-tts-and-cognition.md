# Plan: Fix TTS (Mouth) CUDA Issues, XTTS Imports, and Cognition Slowness

## Objective
Fix the critical CUDA errors in the `lumax_mouth` service, resolve the XTTS engine initialization failure, and optimize the cognition model (Qwen-VL) performance.

## Key Files & Context
- `Dockerfile`: Missing `libcudnn.so.8` and inconsistent venv usage.
- `Backend/Body/body_interface.py`: XTTS import logic prone to name collisions and incomplete error handling.
- `Backend/Mind/Cognition/lumax_engine.py`: Missing Flash Attention and optimized quantized model loading.
- `requirements_lumax.txt`: Missing essential libraries for quantized model acceleration and high-speed TTS.

## Implementation Steps

### 1. Fix CUDA Library Mismatch in Dockerfile
- Update `Dockerfile` to copy `libcudnn.so.8*` from the donor image.
- Standardize the `LD_LIBRARY_PATH` to ensure ONNX Runtime and Torch can find all CUDA/cuDNN libraries.
- Ensure symlinks for CUDA 11 compatibility are complete.

### 2. Resolve XTTS Import and Library Issues
- Add `xtts-onnx` and `auralis` (if applicable) to the dependencies.
- Fix the import logic in `body_interface.py` to prevent the model directory from shadowing the library.
- Improve the detection of XTTS files to be more robust.

### 3. Optimize Cognition Model (Qwen-VL)
- Update `lumax_engine.py` to explicitly request `attn_implementation="flash_attention_2"` if using Transformers.
- Add `auto-gptq` and `optimum` to `requirements_lumax.txt` to properly support the GPTQ-Int4 model.
- Ensure `bitsandbytes` is available for potential 4-bit/8-bit optimizations.

### 4. Clean Up Dependencies
- Consolidate common dependencies in `requirements_lumax.txt`.
- Fix the `docker-compose.yml` command if the `venv_mouth` is actually intended for use, or merge its requirements into the main environment to avoid "dependency hell" hacks.

## Verification & Testing
1. **Build Verification**: Ensure the Docker image builds without errors.
2. **CUDA Check**: Run `nvidia-smi` inside the container and verify `torch.cuda.is_available()` is True.
3. **TTS Test**: Call the `/tts` endpoint and verify it uses the XTTS (or optimized Piper) engine without falling back due to CUDA errors.
4. **Cognition Test**: Monitor response times for the `/compagent` endpoint to verify the speed improvement of the Qwen-VL model.
