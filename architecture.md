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
│  │  8411            │    │  8401            │                   │
│  └─────────────────┘    └──────────────────┘                   │
│         │                       │                               │
│         ▼                       ▼                               │
│  ┌─────────────────┐    ┌──────────────────┐                   │
│  │  Memory Proxy    │    │  Chat Relay      │                   │
│  │  8400/8414       │    │  8413            │                   │
│  └─────────────────┘    └──────────────────┘                   │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐     │
│  │ Motor        │  │ Subconscious │  │ Multigate WebUI  │     │
│  │ 8410         │  │ 8409         │  │ 5177             │     │
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

# 2026-10-06Addendum — Theme & Profile subsystem topology (current wiring)

```
Theme Machine (multigate) ──► /api/theme/generate ──────► theme_api.py :8415 (FastAPI)
        │ click "apply"            │ (VLM pipeline → MasterTheme JSON stream)
        ▼                          ▼
  /api/theme/set_active ────► theme_api.py POST set_active
        │                          │ 1) persist theme/active_theme.json
        │                          │ 2) WS broadcast :8415/ws/theme (legacy)
        │                          │ 3) HTTP relay → :8413/internal/theme-broadcast
        ▼                          ▼
  websocket_server.py :8403 ──broadcast_theme()──► all /ws/theme listeners
                                                   (theme_sync.js on every FoveAI page:
                                                    multigate, XR_Vessel, webvm, dash pages)
        │
        ▼ (fetch on load)
  GET /api/themes  ──► vite rewrite ──► :8400 /themes ──► Backend/themes/manifest.json
  GET /foveai-aurora.css ──► :8415 FileResponse (theme/<name>.css)

Profile Pictures:
  PersonaTab ──POST /api/profile/picture (dataURL)──► :8400
      → media/gallery/<user>/profile_<id>.<ext>   (COLLECT — new file per upload)
      → gallery.json + profile_pictures.json (index + current pointer)
      → auth.json users[].profilePicture (mirrored)
  AvatarWindow ──GET /api/profile/picture──► current gallery URL (or fallback)

# 2026-10-12 Addendum — Host Developer Cockpit, Open XRL Agent Contract & Memory Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            HOST DEVELOPER COCKPIT                           │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     XRL COGNITION HUD (Top Banner)                    │  │
│  │   🧠 Model: Tier-B (9B MoQ) │ 📂 Repo: ~/FoveAI │ ⚡ Vitals: GPU/RAM  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│       │                                                               │     │
│  ┌────▼───────────────────────────────────────────────────────────────▼──┐  │
│  │  Padded Interactive Prompt (bash / agy)                                │  │
│  │  - 2cm overscan margins (TV/monitor dead-space protection)             │  │
│  │  - 50,000-line scrollback buffer                                       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│       │                                                               │     │
│  ┌────▼───────────────────────────────────────────────────────────────▼──┐  │
│  │  Lifted Status Bar: Live Telemetry (CPU, RAM, GPU, VRAM, IO, Net)      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1. Open XRL Contract Provisioning
- **Agent Directory Structure**: Managed via `Tools/open_xrl_agent_provision.py`. Creates `/agent/<name>` with ed25519 keypair, `XRL_CONTRACT.json` (specification `xrl-memory/1.0`), and dedicated foveated memory ring storage.
- **WebSocket IPC & Memory Bus**: Real-time event streams on `ws://127.0.0.1:8403` handling `xrl.memory.register`, `deposit`, and `recall`.
- **Active Resonance Ring**: Influx and telemetry tail accessible over HTTP via `:8400/api/resonance/tail`.

### 2. Dual-Tier Model Residency (`runtime/residency.py`)
- **Tier A (Lightweight Multimodal)**: `gemma-4-e2b-multimodal-v1.0` on `:8407`. Runs continuously alongside desktop and VR.
- **Tier B (Flagship Interactive)**: `Qwen3.5-9B-MoQ-3.6` + `Eagle3` draft on `:8408`. Captures full VRAM for high-speed chain-of-thought, with a 30s auto-unload timer to release GPU memory when idle.
- **Hot-swapping**: Programmatic control via `foveai mind`, `python -m runtime.residency load A|B`, or `/swap` inside the console.

### 3. Multi-Layer Memory Recall (`/usr/local/bin/recall`)
A unified human-accessible recall pipeline querying across three distinct storage tiers:
1. **Shadow Context Blocks**: Multi-turn dialogue snapshots stored in `foveated-memory/memory_data/shadow-context/` as structured JSON.
2. **SQLite Agent Database**: `db/agent_memory.db` across `agent_memories`, `agent_journal` (1,300+ entries), and `agent_thoughts`.
3. **Resonance Ring Bus**: Live telemetry memory units on port `:8400`.

### 4. Zero-Memorization Master Control (`/usr/local/bin/foveai-menu`)
- Interactive arrow-key navigation interface invoked by running `foveai` with no arguments.
- Unifies fleet boot (`sleipnir_launcher.sh`), clean teardown (`foveai --unload`), model hot-swapping, interactive chat, memory recall, and tmux overscan HUD without requiring command memorization.

