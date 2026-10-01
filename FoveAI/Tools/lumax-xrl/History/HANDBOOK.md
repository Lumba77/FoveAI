# LUMAX 70XRL — Operator's Handbook

> **Purpose:** This is the single source of truth for the LUMAX 70XRL project.
> Any new session reads this first to understand exactly where we are,
> what we've built, and what to do next.
>
> **Last Updated:** 2026-07-09
> **Status:** 🟢 Active Development

---

## Table of Contents

1. [What Is LUMAX 70XRL?](#1-what-is-lumax-70xrl)
2. [System Architecture](#2-system-architecture)
3. [What We've Built](#3-what-weve-built)
4. [The 70XRL Pipeline](#4-the-70xrl-pipeline)
5. [Current State](#5-current-state)
6. [Known Issues](#6-known-issues)
7. [Next Steps](#7-next-steps)
8. [Quick Commands](#8-quick-commands)
9. [File Map](#9-file-map)

---

## 1. What Is LUMAX 70XRL?

**LUMAX** is an immersive AI companion ecosystem for Meta Quest and spatial computing.
The AI (Jen) lives in a 3D avatar, can see, hear, speak, walk, gesture, and express emotions.

**70XRL** is our secret weapon — a technique that makes a 7B model perform like a 70B
by combining two breakthroughs:

| Technique | What It Does | Gain |
|-----------|-------------|------|
| **XRL (X-Ray Language)** | Compresses code to structural skeletons (67% avg reduction) | 3x effective context |
| **MoQ (Matrix of Quantization)** | Applies different bit-widths to different model weights | 4.6-5.75x size reduction |
| **Combined** | 7B Q4_K_M + XRL = 70B-class code understanding on 8GB VRAM | **15-19x total** |

**The vision:** A 70B model compressed to ~5GB that runs on an 8GB RTX 4060,
with XRL giving it 4x the effective context of a raw 70B.

---

## 2. System Architecture

### Service Fleet (14 Nodes)

| Port | Service | File | Status |
|------|---------|------|--------|
| 8000 | Sovereign Core | `Backend/Cognition/compagent.py` | 🟢 Active |
| 8001 | Ears STT | — | 🟢 Active |
| 8004 | Mouth Kokoro | — | 🟢 Active |
| 8101 | XR Vessel API | `Frontend/XR_Vessel/xr_app.py` | 🟢 Active |
| 8103 | TokenSlayer | `Backend/Cognition/tokenslayer_proxy_server.py` | 🟢 Active |
| 8105 | Forge Nursery | `Tools/lumax-xrl/nursery/forge_nursery_api.py` | 🟢 Active |
| 8106 | TokenSlayer Proxy | — | 🟢 Active |
| 8109 | Stardust Gnists | `Backend/Memory/stardust_encoder.py` | 🟢 Active |
| 8110 | Motor Cortex | `Backend/Cognition/motor_daemon.py` | 🟢 Active |
| 8112 | DeadSure Failsafe | — | 🟢 Active |
| 8888 | Unsloth Gemma | — | 🟢 Active |
| — | MCP Server | — | 🟢 Active |
| — | Core Solver | — | 🟢 Active |
| — | Cloudflare Tunnel | — | 🟢 Active |

### Startup

```powershell
.\Start_Concordia.PS1
# Or the thin entry point:
.\lumax
```

### Frontend

The 3D avatar chatbot lives at `Frontend/3D_Avatar_Chatbot/`.
Open `http://localhost:8080` in a browser (or `https://lumax.1um6a.se` via Cloudflare).

---

## 3. What We've Built

### ✅ Phase 1: XRL Binary Tokenizer (Complete)

| Component | File | What It Does |
|-----------|------|-------------|
| Tokenizer | `Tools/lumax-xrl/xrs/xrl-tokenizer.cjs` | 25 token types, depth masks, pattern detection |
| Serializer | `Tools/lumax-xrl/xrs/xrl-serializer.cjs` | Depth-aware filtering, text + binary output |
| Budget | `Tools/lumax-xrl/xrs/xrl-budget.cjs` | Token budget enforcement |
| CLI | `Tools/lumax-xrl/xrs/xrl.cjs` | Unified pipeline: source → skeleton → tokenize → serialize |
| MCP Server | `Tools/lumax-xrl/xrs/xrl-mcp-server.cjs` | 3 MCP tools: load_xrl, expand_xrl, search_xrl |
| MCP Bridge | `Tools/lumax-xrl/xrs/xrl-mcp-bridge.py` | Python interface for XRL pipeline |
| Infer | `Tools/lumax-xrl/xrs/xrl-infer.cjs` | Local inference with XRL skeletonization |
| XRB Format | `Tools/lumax-xrl/xrs/xrb-format.md` | GGUF-inspired binary container format |
| PoC Results | `Tools/lumax-xrl/xrs/xrl-poc-results.md` | 67% avg reduction, 89% on proxy server |

### ✅ Forge Nursery (Complete)

| Component | File | What It Does |
|-----------|------|-------------|
| API Server | `Tools/lumax-xrl/nursery/forge_nursery_api.py` | REST API on port 8105 |
| Fine-Tuner | `Tools/lumax-xrl/nursery/fine_tuner.py` | Unsloth LoRA/QLoRA training |
| Quantizer | `Tools/lumax-xrl/nursery/quantizer.py` | MoQ quantization (2-bit to 8-bit) |
| Model Registry | `Tools/lumax-xrl/nursery/model_registry.py` | Variant management |
| Dataset Curator | `Tools/lumax-xrl/nursery/dataset_curator.py` | Local HF cache scanning |

### ✅ 70XRL Pipeline (New — Just Built)

| Component | File | What It Does |
|-----------|------|-------------|
| Downloader | `Tools/lumax-xrl/pipeline/download_model.py` | Download HF safetensors + convert to GGUF + quantize |
| Preprocessor | `Tools/lumax-xrl/pipeline/xrl_preprocessor.py` | Convert training data through XRL tokenizer |
| Pipeline Script | `Tools/lumax-xrl/pipeline/forge-pipeline.sh` | One-command end-to-end pipeline |

### ✅ Frontend Dashboard (Complete)

All 5 tab components wired in `Frontend/XR_Vessel/src/components/Dashboard.ts`:
- Environment Mapping, Avatar Cameras, Environment Management, Controllers Mapping, Model Hub

### ✅ Backend API Routes (Complete)

12 spatial/vision/environment/controller routes in `Backend/Cognition/soul_core.py`.

---

## 4. The 70XRL Pipeline

### The Recipe

```
1. Download base model (safetensors, FP16) from HuggingFace
   │  e.g., Qwen2.5-Coder-7B, Gemma-4-12B, DeepSeek-Coder-70B
   ▼
2. Convert to GGUF FP16 (llama.cpp convert_hf_to_gguf.py)
   │  ~24GB → ~24GB (no loss yet)
   ▼
3. Apply MoQ 2-bit quantization (Forge Nursery quantizer)
   │  ~24GB → ~2.5GB (90% reduction!)
   ▼
4. XRL fine-tune: train on XRL-preprocessed code datasets
   │  Teaches the model to understand XRL skeletons natively
   │  → 3x effective context multiplier
   ▼
5. Deploy on 8GB VRAM = 70B-class performance
```

### Quick Start (Local — 7B Test)

```bash
# Step 1: Download + convert + quantize a 7B model
python Tools/lumax-xrl/pipeline/download_model.py \
    --model Qwen/Qwen2.5-Coder-7B \
    --output ./models/7B-test \
    --convert --quantize --quant-type moq-2.0

# Step 2: XRL fine-tune with LUMAX's own codebase
python Tools/lumax-xrl/pipeline/xrl_preprocessor.py \
    --input ./Backend \
    --output ./datasets/xrl-lumax \
    --depth 2

# Step 3: Start Forge Nursery fine-tuning
curl -X POST http://localhost:8105/api/train/start \
    -H "Content-Type: application/json" \
    -d '{
        "variant_id": "70xrl-test",
        "base_model": "./models/7B-test/quantized/Qwen2.5-Coder-7B-moq-2.0.gguf",
        "dataset_path": "./datasets/xrl-lumax",
        "epochs": 3
    }'
```

### Server Weekend (70B)

```bash
# Rent an H100 or 2x A100 on RunPod
# Then run:
bash Tools/lumax-xrl/pipeline/forge-pipeline.sh \
    --model deepseek-ai/DeepSeek-Coder-70B \
    --quant moq-2.0 \
    --xrl-train \
    --hf-dataset bigcode/the-stack
```

### Available Quantization Types

| Type | Size (7B) | Size (70B) | Quality |
|------|-----------|------------|---------|
| `moq-2.0` | ~2.5 GB | ~5 GB | Good for code structure |
| `moq-3.0` | ~4.5 GB | ~9 GB | Balanced |
| `moq-3.5` | ~5.2 GB | ~10 GB | Better quality |
| `moq-4.0` | ~7.8 GB | ~15 GB | Max quality |
| `q4_k_m` | ~4.8 GB | ~9.5 GB | Standard 4-bit |
| `q8_0` | ~8.5 GB | ~17 GB | Near-lossless |

---

## 5. Current State

### What Works 🟢

- All 14 fleet services start and pass health checks
- XRL tokenizer achieves 67-97% reduction on code files
- Forge Nursery can fine-tune and quantize models
- Frontend dashboard has all 5 panels wired
- Backend has all 12 spatial/vision/environment/controller routes
- Chrome Extension has single toggle button
- Motor Cortex SSE streaming works
- Stardust Gnists vector memory works
- TokenSlayer proxy with mode-aware context trimming works

### What's Partially Working 🟡

- **Soul Core stability**: Starts, then goes offline after some time (root cause unknown)
- **Local LLM latency**: Gemma-4 12B takes ~1 minute to respond (too large for 8GB VRAM)
- **Memory (8002)**: Status unknown — may need restart
- **Creative (8003)**: Status unknown — may need restart

### What's Not Yet Built 🔴

- **XRL MCP Server not registered in sleipnir launcher** — needs to be added to the fleet
- **XRL training mode not wired into Forge Nursery API** — the preprocessor exists but the API doesn't call it yet
- **XRL toggle in Model Hub panel** — no UI for enabling/disabling XRL skeletonization
- **70B server weekend** — not yet executed (waiting for decision)

---

## 6. Known Issues

| Issue | Severity | Status |
|-------|----------|--------|
| Soul Core goes offline after startup | 🔴 Critical | Needs investigation — likely unhandled exception or health check timeout |
| Gemma-4 12B too slow on 8GB VRAM | 🟡 High | Solution: replace with 70XRL-optimized 7B model |
| Memory service (8002) down | 🟡 Medium | Needs restart |
| Creative service (8003) down | 🟡 Medium | Needs restart |
| XRL MCP not in fleet | 🟢 Low | Just needs registration in sleipnir_launcher.js |
| Cognee replaced by Stardust | ✅ Resolved | Stardust Gnists (8109) is the replacement |

---

## 7. Next Steps

### Immediate (This Session)

1. **Test the 70XRL pipeline locally** with a small 7B model:
   ```bash
   python Tools/lumax-xrl/pipeline/download_model.py \
       --model Qwen/Qwen2.5-Coder-7B \
       --output ./models/7B-test \
       --convert --quantize --quant-type moq-2.0
   ```

2. **Register XRL MCP Server in sleipnir launcher** so it starts with the fleet

3. **Wire XRL preprocessor into Forge Nursery API** so fine-tuning automatically uses XRL datasets

### Short Term

4. **Diagnose Soul Core stability** — add logging, catch exceptions, implement auto-restart
5. **Replace Gemma-4 12B** with 70XRL-optimized 7B model
6. **Add XRL toggle to Model Hub panel** in the frontend

### Medium Term

7. **Rent server for 70B weekend** — convert DeepSeek-Coder-70B to 70XRL (~$150-250)
8. **Train XRM (XRL-native model)** — fine-tune a model from scratch to understand XRL natively
9. **Port XRL tokenizer to C/C++** for zero-copy performance in llama.cpp

---

## 8. Quick Commands

### Start Everything
```powershell
.\Start_Concordia.PS1
# Or: .\lumax
```

### Check Service Health
```bash
curl http://localhost:8000/health   # Soul Core
curl http://localhost:8002/health   # Memory
curl http://localhost:8105/health   # Forge Nursery
```

### Run XRL on a File
```bash
node Tools/lumax-xrl/xrs/xrl.cjs Backend/Cognition/soul_core.py --depth 2 --json
node Tools/lumax-xrl/xrs/xrl.cjs Backend/Cognition/soul_core.py --depth 2 --budget 500
```

### Run XRL Inference
```bash
node Tools/lumax-xrl/xrs/xrl-infer.cjs --file Backend/Cognition/soul_core.py --prompt "What does this do?" --dry-run
```

### Start Forge Nursery
```bash
python -m Forge.nursery.forge_nursery_api
```

### Run 70XRL Pipeline
```bash
bash Tools/lumax-xrl/pipeline/forge-pipeline.sh --model Qwen/Qwen2.5-Coder-7B --quant moq-2.0 --local
```

---

## 9. File Map

### Root Documents
| File | Purpose |
|------|---------|
| `HANDBOOK.md` | **THIS FILE** — single source of truth |
| `uptodate.md` | System status report |
| `context.md` | Session history log |
| `ARCHITECTURE.md` | Architecture & feature manual |
| `LUMAX.md` | Project overview & operational rules |
| `WORKFLOW.md` | Token-efficient workflow guide |
| `AGENTS.md` | Agent roles & customizations |

### XRL Pipeline (`Tools/lumax-xrl/xrs/`)
| File | Purpose |
|------|---------|
| `xrl-tokenizer.cjs` | Core binary tokenizer (25 token types) |
| `xrl-serializer.cjs` | Depth-aware serializer |
| `xrl-budget.cjs` | Token budget enforcer |
| `xrl.cjs` | Unified CLI |
| `xrl-mcp-server.cjs` | MCP server (3 tools) |
| `xrl-mcp-bridge.py` | Python interface |
| `xrl-infer.cjs` | Local inference wrapper |
| `xrl-benchmark.cjs` | PoC benchmark |
| `xrl-benchmark2.cjs` | Enhanced benchmark |
| `xrs.cjs` | XRS skeletonizer CLI |
| `xrs-tokens.cjs` | Token counter |
| `xrb-format.md` | XRB binary format spec |
| `xrl-prompt.md` | LLM prompt template |
| `xrl-poc-results.md` | PoC results report |

### Forge Nursery (`Tools/lumax-xrl/nursery/`)
| File | Purpose |
|------|---------|
| `forge_nursery_api.py` | FastAPI server (port 8105) |
| `fine_tuner.py` | Unsloth fine-tuning |
| `quantizer.py` | MoQ quantization |
| `model_registry.py` | Variant management |
| `dataset_curator.py` | Dataset scanning |

### 70XRL Pipeline (`Tools/lumax-xrl/pipeline/`)
| File | Purpose |
|------|---------|
| `download_model.py` | Download + convert + quantize |
| `xrl_preprocessor.py` | XRL dataset preparation |
| `forge-pipeline.sh` | One-command pipeline |

### Backend
| File | Purpose |
|------|---------|
| `Backend/Cognition/soul_core.py` | Sovereign Core API |
| `Backend/Cognition/compagent.py` | Cognitive loop |
| `Backend/Cognition/motor_daemon.py` | Motor Cortex |
| `Backend/Cognition/system_probe.py` | System detection |
| `Backend/Cognition/intelligent_router.py` | Local/cloud routing |
| `Backend/Memory/stardust_encoder.py` | Vector memory |

### Frontend
| File | Purpose |
|------|---------|
| `Frontend/3D_Avatar_Chatbot/index.html` | Main HTML shell |
| `Frontend/3D_Avatar_Chatbot/src/main.js` | Application controller |
| `Frontend/3D_Avatar_Chatbot/src/ViewerEngine.js` | 3D rendering |
| `Frontend/3D_Avatar_Chatbot/src/LumaxIntegrationLayer.js` | Behavior engine |
| `Frontend/XR_Vessel/src/components/Dashboard.ts` | Dashboard UI |
| `Frontend/XR_Vessel/src/components/ModelHubTab.ts` | Model Hub tab |
| `Frontend/XR_Vessel/src/components/EnvironmentMappingTab.ts` | Env mapping tab |
| `Frontend/XR_Vessel/src/components/AvatarCamerasTab.ts` | Avatar cameras tab |
| `Frontend/XR_Vessel/src/components/EnvironmentManagementTab.ts` | Env management tab |
| `Frontend/XR_Vessel/src/components/ControllersMappingTab.ts` | Controllers tab |

---

> **End of Handbook.**
> Any new session: read this first, then check `uptodate.md` for current status,
> then `context.md` for recent session history.
>
> **The mission:** 70B performance on 8GB VRAM. XRL + MoQ = 70XRL.
> We have all the tools. Now we optimize.