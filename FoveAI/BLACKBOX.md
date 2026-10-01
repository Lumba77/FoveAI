# LUMAX: Diamond Concordia - AI Companion Ecosystem

## Project Overview

LUMAX is a Windows-native AI avatar system featuring a 3D frontend and distributed backend swarm. The system represents the "Diamond Concordia" phase, having purged reliance on Docker containers, WSL2, and the Godot game engine in favor of:

- **WebXR Canvas Interfaces** (Native spatial UI via Vite/TypeScript)
- **Windows-Native PowerShell Orchestration** (Zero-drag host execution)
- **Holonic Network Topology** (Sky Net, Sovereign Core, Worker Swarms, Stardust Gnists)
- **TokenSlayer Ingestion** (Stripping context noise before it hits VRAM)

The system centers around Jen (Jenny Forbee), an immersive, multimodal AI entity living in a WebXR spatial vessel.

## System Architecture

### High-Level Data Flow

```
User Input (text/voice)
    │
    ▼
┌─────────────────────────────────────────────┐
│          3D_Avatar_Chatbot Frontend          │
│  (index.html → main.js → ViewerEngine)       │
│                                              │
│  ┌─ Chat UI ─┐  ┌─ 3D Avatar ─┐  ┌─ HUD ─┐ │
│  │ text/voice │  │ VRM model   │  │ 3D    │ │
│  │ streaming  │  │ animations  │  │ overlay│ │
│  │ responses  │  │ emotions    │  │ panels │ │
│  └────────────┘  └─────────────┘  └────────┘ │
│                                              │
│  ┌─ LumaxIntegrationLayer ─────────────────┐ │
│  │ Behavior engine, motor cortex bridge,   │ │
│  │ 4-state system, bracket token injection │ │
│  └─────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────┘
                       │ HTTP / SSE
                       ▼
┌─────────────────────────────────────────────┐
│           Backend Swarm (14 nodes)            │
│                                              │
│  :8000  Sovereign Core (compagent.py)        │
│  :8001  Ears STT (speech-to-text)            │
│  :8004  Mouth Kokoro (text-to-speech)        │
│  :8101  XR Vessel API (xr_app.py, 70+ APIs)  │
│  :8103  TokenSlayer Context Filtering        │
│  :8109  Stardust Gnists (vector memory)       │
│  :8110  Motor Cortex (motor_daemon.py)        │
│  :8112  DeadSure Failsafe                     │
│  :8200  Foveated Memory Proxy (OpenAI-compat    │
│         LLM gateway + XRL memory + dashboard) │
│  :8201  Foveated Memory Dashboard / Kiosk     │
│  :8888  Unsloth Gemma (local LLM)            │
└─────────────────────────────────────────────┘
```

### Startup Sequence

```
Start_Concordia.PS1
    │
    ▼
sleipnir_launcher.js
    │
    ├── Foveated Memory Proxy (:8200) + Dashboard (:8201)
    ├── MCP Server
    ├── Core Solver
    ├── Stardust Neural (:8109)
    ├── Motor Cortex (:8110)
    ├── Sovereign Core (:8000)
    ├── XR Vessel API (:8101)
    ├── Vite Dev Server (:5176)
    └── Cloudflare Tunnel
```

## Key Components

### Frontend (3D_Avatar_Chatbot)

- **Main Entry Point**: `Frontend/3D_Avatar_Chatbot/index.html`
- **Application Controller**: `Frontend/3D_Avatar_Chatbot/src/main.js` (5,233 lines)
- **3D Rendering Engine**: `Frontend/3D_Avatar_Chatbot/src/ViewerEngine.js` (Three.js-based)
- **LUMAX Integration Layer**: `Frontend/3D_Avatar_Chatbot/src/LumaxIntegrationLayer.js` (1,399 lines) - Bridges frontend with backend services
- **HUD System**: `Frontend/3D_Avatar_Chatbot/src/LumaxHud3D.js` - 3D canvas-based overlay showing system vitals
- **Overlay Manager**: Handles dynamic panel loading

### Backend Services

Running on specific ports as part of the holonic topology:

- **Port 8000**: Sovereign Core (compagent.py) - Main cognitive agent loop
- **Port 8001**: Ears STT - Speech-to-text service
- **Port 8004**: Mouth Kokoro - Text-to-speech service (uses af_heart voice for Jen)
- **Port 8101**: XR Vessel API - Legacy API with 70+ endpoints
- **Port 8103**: TokenSlayer Context Filtering - Smart context ingestion with multi-language structural compaction (~85% reduction)
- **Port 8109**: Stardust Gnists - Vector memory service (33M parameter sentence-transformer)
- **Port 8110**: Motor Cortex - Handles avatar movement, emotions, gestures (fully integrated into compagent.py streaming pipeline)
- **Port 8112**: DeadSure Failsafe - Safety monitoring system
- **Port 8200**: Foveated Memory Proxy - OpenAI-compatible LLM gateway with XRL Active Recall and Membrane HUD
- **Port 8201**: Foveated Memory Dashboard - Monitoring interface
- **Port 8888**: Unsloth Gemma - Local LLM service (starts on-demand)

### Foveated Memory System

Located in `Tools/foveated-memory/`, this system provides:

- **Context Compression**: Uses XRL Active Recall and gradient ring compression
- **TokenSlayer Integration**: Strips context noise before it hits VRAM
- **Workspace Isolation**: Each Bearer token gets isolated memory store
- **Checkpointing**: Every 8 turns, oldest batch summarized into CKP:hash blocks
- **Compression Ratio**: ~89% reduction (30-turn session: ~80K tokens → ~9K tokens)
- **Membrane Executive HUD**: Dynamic top-level HUD containing turn numbers, active task checklists, recent file modification diagnostics, and XRL codebase intuition
- **5-Tier Empirical Compression Spectrum**:
  - Level 0 (0% Compression): Verbatim recent turns (Fovea Window)
  - Level 1 (65% Compression): Lossless Baseline — 100% instruction fidelity & context retention (Parafovea)
  - Level 2 (72% Compression): Light structural skeleton & 2-sentence key summaries
  - Level 3 (80% Compression): Deep signature & import skeletons with expand tags
  - Level 4 (88% Compression): XRL Symbol Table URIs (`xrl://lumax/...`)
  - Level 5 (95% Compression): Atomic SHA-256 hash nodes (`#hash`)

## Development & Deployment

### Getting Started

1. Ensure local Python `.venv` is configured
2. Execute the master orchestrator:
   ```powershell
   .\\Start_Concordia.ps1
   ```

### Key Scripts

- **Start_Concordia.ps1**: Main launcher that activates Python environment and starts services
- **sleipnir_launcher.js**: Node.js orchestrator that manages the service fleet (expanded to 9-node Concordia Fleet)
- **Start_LUMAX_Settings.bat**: Launcher for LUMAX settings UI
- **Start_LUMAX_Taskbar.bat**: Launcher for LUMAX taskbar application

### Frontend Development

- **Dev Server**: `npm run dev` (runs Vite dev server on :5176)
- **Tunnel**: `npm run tunnel` (Cloudflare tunnel for public access)
- **Dev + Tunnel**: `npm run dev:tunnel` (runs both dev server and tunnel)

### Avatar Animation States

The avatar features a 4-State System with the following animation states:
- **CALM_IDLE**: Default. Breathing, micro-gestures, head tracking
- **SOCIAL_TURN**: Turning toward user. Warm attention.
- **CURIOUS_STEP**: 1-2 short steps toward something interesting
- **WANDER_NEARBY**: Short walk nearby, then return home
- **EMOTIONAL_BURST**: Animation triggered by AI emotion output
- **RETURNING_HOME**: Smooth walk back to home position
- **RESTING**: Deep idle, very minimal motion
- **DEEP_IDLE**: 4-State System - minimal metabolic activity
- **SLOW_BURN**: 4-State System - emotion building
- **DREAMING**: 4-State System - imaginative state

## Environment Variables (.env)

Key configuration variables include:
- `LUMAX_MODELS_ROOT`: Path to HuggingFace models cache
- `LUMAX_INVOKEAI_MODELS_HOST`: Path to InvokeAI models
- `LUMAX_KOKORO_VOICE`: TTS voice for Jen (default: af_heart)
- `LUMAX_PROXY_PORT`: Foveated memory proxy port (8200)
- `LUMAX_MODEL_CLOUD_ID`: Cloud model identifier (gemma4:31b)
- `LUMAX_AGENT_LOOP_ENABLED`: Autonomous agent loop toggle
- `LUMAX_SPOOF_CONTEXT_WINDOW`: Context window spoofing (128000)
- `HF_TOKEN` & `VITE_HF_TOKEN`: HuggingFace API token
- `GITHUB_TOKEN`: GitHub API token
- `LUMAX_TTS_ENABLED`: Toggle for Kokoro TTS
- `LUMAX_GREETING_ENABLED`: Toggle for initial voice greeting
- `LUMAX_MEMORY_BACKUP_ENABLED`: Toggle for memory persistence

## Troubleshooting Common Issues

Refer to ARCHITECTURE.md Section 7 for detailed troubleshooting, including:
- Avatar loading issues (check `window.NEXUS_VIEWER`)
- T-pose avatar (check `ProceduralAnimator.registerAvatar()`)
- No AI response (verify provider configuration in Settings)
- Motor commands not executing (check Motor Cortex on :8110)
- HUD not showing (check LumaxHud3D initialization)
- Voice not working (check microphone permissions)
- Kokoro TTS issues (verify `LUMAX_TTS_ENABLED` and `LUMAX_KOKORO_VOICE`)
- Local mode LLM thinking timeout preventing voice greeting (known issue)
- Sovereign Core intermittently going offline (known issue)

## Current Status

As of the latest update (2026-08-05), LUMAX operates in the Diamond Concordia phase with:
- **14-Node Native Swarm**: All services running Windows-native (no Docker/WSL2)
- **WebXR-based spatial interfaces**
- **Holonic backend topology** with centralized Sovereign Core API (:8000)
- **Advanced memory compression** via Foveated Memory/XRL with Membrane HUD
- **TokenSlayer preprocessing** for efficient context handling (~85% reduction)
- **Stardust Gnists** for instantaneous zero-drag memory matching
- **Motor Cortex integration** with structured motor action parsing
- **Dead Sure Coding Enforcement** for atomic, self-healing transactional gates

The system is designed for continuous autonomous operation with Jen as the primary AI entity, featuring persistent memory, emotional expression, and spatial awareness through the 3D avatar interface.

## Hidden Systems & Recent Developments (The "Rivers Underneath the Bridges")

Beyond the core architecture documented above, LUMAX has evolved with several significant subsystems and recent developments:

### Agent HUD & Self-Augmentation System
- **Location**: `LUMAX Agent HUD & Self-Augmentation` skill
- **Purpose**: Generates a dynamic HUD showing the current site tree, feature maturity, and vision
- **Capabilities**: Grants AI permission to autonomously build upon 'Seedling' features using Dead Sure methodologies
- **Integration**: Works with the existing HUD system to provide meta-awareness of the AI's own capabilities

### Advanced Memory Systems
- **Foveated Memory Enhancements**:
  - Context-healer system for dynamic token budget management
  - Relational memory tracking for importance scoring and decay
  - XRL (eXtended Recall Logic) compressor for semantic understanding
  - Quality guard systems to prevent degradation of compressed contexts
  - Continuity systems for preserving conversational threads across sessions

### MCP (Model Context Protocol) Integration
- **MCP Server**: Located in `Tools/foveated-memory/mcp-server.js`
- **Purpose**: Enables LLMs to interact with external services through standardized tools
- **Features**:
  - File system access with path resolution and security boundaries
  - XRL (eXtended Recall Logic) protocol for contextual references
  - Semantic summarization capabilities
  - Diagnostic and introspection endpoints
- **Clients**: Both Python (FastMCP) and Node/TypeScript implementations

### TokenSlayer System
- **Location**: `Use TokenSlayer` skill + `tokenslayer_scan_and_index.py`
- **Purpose**: Drastically reduces token usage by extracting structural code skeletons instead of reading full files
- **Implementation**: Used for all file reads in LUMAX to minimize context pollution
- **Benefits**: Enables working with large codebases without exceeding token limits
- **MCP Server Tools**: 6 tools (`analyze_files`, `analyze_workspace`, `analyze_dependency_chain`, `expand_node`, `get_stats`, `session_health`)

### WebXR & Immersive Capabilities
- **WebXR Integration**: Through `hz-iwsdk-webxr` skill
- **ECS Architecture**: Entity-Component-System design for modular VR/MR experiences
- **Three.js Integration**: Core rendering engine for spatial interfaces
- **Spatial UI**: Context-aware interfaces that adapt to user's physical environment

### Autonomous Agent Loop
- **Configuration**: `LUMAX_AGENT_LOOP_ENABLED=true` in .env
- **Safety Systems**:
  - CPU/RAM safety brakes (90%/95% thresholds)
  - Error rate monitoring (10% threshold)
  - Maximum consecutive loops (24) to prevent runaway processes
- **Curiosity & Self-Awareness**: Configurable biases for exploration vs. exploitation

### Creative Systems
- **InvokeAI Integration**: For stable diffusion-based image generation
- **Creativity Modules**:
  - Imagen-style text-to-image generation
  - SDXL turbo models for rapid inference
  - ControlNet integration for guided generation
- **Model Hot-Swap**: Enables dynamic model switching based on confidence thresholds

### Monitoring & Diagnostics
- **Lumax Stress Meter**: Real-time system performance monitoring
- **Lumax Tray/Top Bar**: System status indicators in Windows taskbar
- **Diagnostics Suite**: Comprehensive health checks for all backend services
- **Vibe Checkpointing**: PowerShell-based system for saving and restoring operational states

### Security & Identity Systems
- **Ghost Listener/Brain**: Stealth monitoring and response systems
- **Authority Files**: Trust-based access control mechanisms
- **Library Indexer**: Knowledge organization and retrieval systems
- **NPU Bridge**: Hardware acceleration interfaces for neural processing units

### Communication & Extension Systems
- **Hey-Lumax.js**: Wake word and voice command processing
- **Chrome Extension**: Browser-based LUMAX integration
- **Consent Bridge**: Privacy and consent management systems
- **Agency System**: Multi-agent coordination and negotiation frameworks

### Build & Deployment Enhancements
- **Unsloth Integration**: Optimized LLM training and inference
- **Patch Management**: Automated system updates via `patch_lumax.py`
- **Export Tools**: Dataset export capabilities for training (`export_unsloth_dataset.py`)
- **Version Control**: Sophisticated branching and merging strategies for AI-generated code

## Active Objectives
1. Verify end-to-end functionality: launch Concordia → Vite frontend → chat via `/compagent` → motor actions via SSE
2. Test motor cortex tool execution on the frontend (walk, emotion, gesture rendering)
3. Refine the Stardust Gnists for deeper spatial memory retention during long XR sessions
4. Clean remaining stale references in codebase (Docker Compose files, Godot scripts, Kuzu imports)

## Current Issues
1. Local mode, LLM thinking for 1 minute, never reaches to actually voice a greeting
2. Sovereign Core intermittently going offline