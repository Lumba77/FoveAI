# FoveAI Architecture Overview

## Purpose
FoveAI (Diamond Concordia) is a spatial AI companion ecosystem. A multimodal AI entity (Jen / Jenny Forbee) lives in a WebXR spatial vessel on Quest 3, with all heavy inference running on the PC host. The Quest client is a lightweight ~12.5 MB streaming vessel (`AliceVR.apk`).

## System Topology

```
┌─────────────────────────────────────────────────────────────────┐
│                      PC HOST BACKEND                            │
│                                                                 │
│  ┌─────────────────┐    ┌──────────────────┐                   │
│  │  Main LLM        │    │  Smart Proxy     │                   │
│  │  8402/8403       │◄──►│  8400            │                   │
│  │  xrlf runtime    │    │  omni-router     │                   │
│  └─────────────────┘    └──────────────────┘                   │
│         │                       │                               │
│         ▼                       ▼                               │
│  ┌─────────────────┐    ┌──────────────────┐                   │
│  │  Kokoro TTS      │    │  Whisper STT     │                   │
│  │  8406            │    │  8409            │                   │
│  └─────────────────┘    └──────────────────┘                   │
│         │                       │                               │
│         ▼                       ▼                               │
│  ┌─────────────────┐    ┌──────────────────┐                   │
│  │  Memory Proxy    │    │  Chat Relay      │                   │
│  │  8400/8401       │    │  8407            │                   │
│  └─────────────────┘    └──────────────────┘                   │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐     │
│  │ Motor        │  │ Subconscious │  │ Multigate WebUI  │     │
│  │ 8410         │  │ 8411         │  │ 5177             │     │
│  └──────────────┘  └──────────────┘  └──────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
         │ WebSocket (8403)
         ▼
┌─────────────────┐
│  Quest 3 VR     │
│  AliceVR.apk    │
│  ~12.5 MB       │
└─────────────────┘
```

## Core Runtime Architecture

The runtime follows a layered pipeline:

1. **XRLFRuntime** (`runtime/xrlf_runtime.py`) — orchestrator. Loads .xrlf files, manages the model lifecycle, builds system prompts from cognitive layers.
2. **LlamaEngine** (`llama_bridge/llama_engine.py`) — llama.cpp wrapper. Handles GGUF loading, GPU offload, MTP/speculative decoding, streaming, and (since 2026-10-01) repetition-loop guard with token burst cap.
3. **SoulBridge** (`runtime/soul_bridge.py`) — personality layer. Manages life fragments, memory summarization, context adaptation with hysteresis.
4. **TriadPipeline** (`runtime/triad_pipeline.py`) — router/summarizer. Intent/emotion/hint parsing, signal detection, graph concept enrichment.
5. **VRAMGuardrail** (`runtime/vram_guard.py`) — concurrency + VRAM governor. Slot acquisition, 8GB ceiling, configurable safety reserve, Linux nvidia-smi / Windows GlobalMemoryStatusEx.
6. **MemoryPlanner** (`runtime/memory_planner.py`) — VRAM/RAM tiling and context capping.
7. **MemoryShaping** (`runtime/memory_shaping.py`) — recall compression, session digestion with word-boundary keyword matching.
8. **CognitiveSteering** (`runtime/cognitive_steering.py`) — system prompt construction, PrincipiaApplicator with style hint cap.
9. **ScrollWatcher** (`runtime/scroll_watcher.py`) — scroll file cache with delete invalidation.
10. **RigGuard** (`runtime/rig_guard.py`) — watchdog for language server bloat, Unity zombie workers, runaway git processes, system RAM telemetry.

## Security Posture (2026-10-01 Audit)

After the 2026-10-01 code audit and remediation:

- **Path traversal**: All file-serving endpoints validate paths (resolve + containment check, reject `..` and absolute paths).
- **Concurrency**: Hot-swap operations serialized with dedicated lock; inference has its own lock.
- **CORS**: Configurable origin allowlist via env var; defaults to permissive for local dev.
- **OOM protection**: Triple-layer repetition guard + hard token burst cap.
- **Silent failures**: Tray and context-collector exceptions now logged via `print()`.
- **Config**: All secrets read from `.env`/env vars — no hardcoded credentials.
- **VRAM**: Configurable safety reserve; Linux and Windows paths correctly gated.
- **Windows/NTFS migration**: All `os.name`/`sys.platform` guards verified intentional and correct; no broken Windows-only paths in active runtime code.

See `uptodate.md` §3 for full details.

## Configuration

All configuration via environment variables and `.env` file. Key env vars:

| Variable | Default | Purpose |
|---|---|---|
| `FOVEAI_SAFETY_RESERVE_GB` | 1.0 (Linux) / 1.8 (Windows) | VRAM safety floor |
| `FOVEAI_CORS_ORIGINS` | (empty → `["*"]`) | Comma-separated CORS origins |
| `SOUL_CONFIG_PATH` | `.xrlf/config/soul.config.xrlf` | Soul config path |
| `XRLF_REP_THRESHOLD_CHARS` | 256 | Repetition guard tail window |
| `XRLF_REP_THRESHOLD_COUNT` | 3 | Repetition guard trigger count |
| `XRLF_MAX_TOKENS_BURST` | 4096 | Hard cap on generated tokens/turn |
| `XRLF_REPO_ENABLED` | false | XRLF reactor master switch |
