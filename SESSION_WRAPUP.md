# Session Wrap-Up — Native Multimodal + CUDA

## Goal
Enable native multimodal (STT, TTS, Vision) capabilities of the Gemma 4 12B model
within the XRLF runtime, with GPU acceleration for real-time voice companion use.

## Architecture Overview

```
[Companion HTML] → [Proxy :8400] → [XRLF Runtime :8402]
   (voice UI)       (foveated-memory)   (llama.cpp + Gemma 4)
                     transparent mode     GPU (RTX 4060)
                                          ↓
                                     Native endpoints:
                                     /v1/chat/completions
                                     /v1/audio/transcriptions (STT)
                                     /v1/audio/speech (TTS)
                                     /v1/images/understand (Vision)
                                     /v1/capabilities
```

## Files Changed

### Core Runtime
| File | Change |
|------|--------|
| `llama_bridge/llama_engine.py` | Use `create_chat_completion` when chat_handler is loaded (native template). Fall back to local `gemma4_handler.py` if native import fails. |
| `llama_bridge/gemma4_handler.py` | **NEW** — Extracted `MTMDChatHandler` + `Gemma4ChatHandler` from llama-cpp-python 0.3.34 source. Works with 0.3.16+ (has mtmd_cpp but not the handler class). |
| `runtime/xrlf_runtime.py` | Fixed `Tools` vs `tools` case-sensitivity for MMHookRegistry import. |
| `runtime/cognitive_steering.py` | Fixed `_extract_style_hints` — principles can be strings, not just dicts. |
| `memory/membrane_engine.py` | Reformatted `weave_context()` to use discrete background notes instead of raw `USER:`/`ASSISTANT:` dialogue. Prevents model from looping on old conversation patterns. |
| `api/server.py` | Added `/v1/audio/transcriptions`, `/v1/audio/speech`, `/v1/images/understand`, `/v1/capabilities` endpoints. Fixed mtmd context lazy-init in capability check. |
| `xrlf_config.yaml` | Switched model to `gemma-4-12b-mtp-xrlf-3.0.xrlf` (real Gemma 4). |

### Proxy (foveated-memory)
| File | Change |
|------|--------|
| `server.js` | Renamed `LM_STUDIO_URL` → `XRLF_RUNTIME_URL` (13 occurrences). Default port 1234 → 8402. |
| `core/context-compressor.js` | Same rename. |
| `.env` | `XRLF_RUNTIME_URL=http://127.0.0.1:8402`, `XRLF_PROXY_MODE=transparent` |
| `switch-model.ps1` | Updated to use `XRLF_RUNTIME_URL` and port 8402. |

### Companion
| File | Change |
|------|--------|
| `public/companion.html` | `continuous=false`, 2.5s silence detection, auto-send after pause. |

### Build
| File | Change |
|------|--------|
| `build_cuda_wheel.bat` | **NEW** — Builds llama-cpp-python 0.3.34 with CUDA using VS 2022 BuildTools + NMake. |

### Documentation
| File | Change |
|------|--------|
| `AGENT.md` | Added lessons: CUDA build process, XRLF_RUNTIME_URL rename, memory injection format. |

## CUDA Build
- **Problem**: venv was moved from `Tools/xrlf-model/.venv` to `FoveAI/.venv`. Prebuilt abetlen CUDA wheels for Windows only go up to v0.3.4. Gemma 4 needs 0.3.34+.
- **Solution**: Build from source with `build_cuda_wheel.bat` (NMake + VS 2022 BuildTools + CUDA 12.8).
- **Status**: Compiling (82%+)

## Verification Checklist (after build completes)
1. `llama_cpp.llama_supports_gpu_offload()` returns `True`
2. `Gemma4ChatHandler` imports from `llama_cpp.llama_chat_format`
3. Runtime starts on :8402 with GPU
4. `/v1/capabilities` returns `vision: true, audio_stt: true, tts: true`
5. Chat response time < 5s for simple queries (with GPU)
6. TTS produces audio
7. Companion voice flow works end-to-end
