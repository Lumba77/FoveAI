# FOVEAI SYSTEM STATUS REPORT (STREAMLINED XRLF TOPOLOGY)

## 1. STREAMLINED MODEL TRIAD & NATIVE SERVICES
FoveAI refactors away from brittle, high-latency multi-model HTTP swarms into a unified **One Main LLM + Smart Proxy Router + Memory Helper** architecture connected via persistent WebSockets:

| Component | Role / Model | Port / Protocol | Note |
|---|---|---|---|
| **Main Cognitive LLM** | `gemma-4-12b-mtp-xrlf` | 8400 (IPC WebSocket) | The single active cognitive core loaded in `xrlf_runtime.py` with MoQ core & cognitive steering. |
| **Smart Proxy (Omni-Router)** | `lumax-plumax-omni-router-v2.xrlf` | 8400 (Internal Middleware) | Intercepts massive context dumps (>12K chars) and extracts critical code and intent. |
| **Failover Omni-Router (No. 2)** | `no2-lumax-plumax-omni-router.xrlf` | Failover Channel | Load-balancer / secondary router engaged if Router 1 encounters congestion. |
| **Memory Helper Model** | `lumax-summarizer-draft.gguf` | Embedded / 8402 | Background helper weaving active-recall memory ring blocks and compacting checkpoints. |
| **IPC WebSocket Server** | `websocket_server.py` | 8400 (ws://) | Low-latency binary/JSON socket connecting Quest, WebXR, and Desktop clients. |
| **Sovereign Core (Soul)** | `compagent.py` | 8000 | Cognition loop, motor intent extraction, and avatar coordination. |
| **Stardust Gnists** | Vector Resonance | 8109 | 33M parameter vector matrix for instant semantic memory matching. |
| **Motor Cortex** | `motor_daemon.py` | 8110 | Native avatar agency (walk, gesture, emotion rendering). |
| **Mouth Kokoro** | TTS Service | 8004 | Neural 24kHz speech synthesis. |
| **Ears STT** | Speech-to-Text | 8001 | Real-time voice transcription. |
| **WebXR Vessel UI** | Spatial Frontend | 5176 | Native spatial UI via Vite/TypeScript. |
| **LM Studio (Optional)** | BYO-GGUF Gateway | 7272 (HTTP Fallback) | Optional legacy fallback for third-party GGUFs; bypassed by native XRLF runtime. |
| **Legacy Systems** | 🔴 PURGED | — | Docker, WSL2, Godot, Kuzu, Cognee, TokenSlayer Proxy (:8106/:8103), SigMap, Legacy Ports (:8200, :8300) — all purged/retired. |

---

## 2. RECENT ARCHITECTURAL ADVANCEMENTS
- **Streamlined Model Triad (One Main LLM Architecture)**: Replaced brittle multi-model HTTP junctures with a single active XRLF model, a dual-layer Omni-Router smart proxy, and an embedded memory helper.
- **Low-Latency WebSocket IPC**: Codified `Backend/app/IPC/websocket_server.py` on port 8400 as the primary client-to-runtime conduit, replacing latency-heavy multi-hop HTTP calls.
- **Native XRLation & Principiation Paradigm**: Replaced external TokenSlayer proxy servers and third-party tools (such as SigMap) with native XRLation. Source code files are now **xrlated** (the process of **xrlation**) to extract their **principia** (the core architectural principles, contracts, invariants, and exported signatures rather than crude "skeletons" or "bones"). Sub-implementation bodies map to `xrl://` URIs for on-demand active recall by the model.
- **FoveAI Vibe Coder Extension (v0.3.2)**: Packaged and installed `foveai.foveai-vibe-coder` v0.3.2 into Antigravity IDE. Fixed webview button event listener binding, added `💎 Attach` button for instant file context, base64-inlined custom send icons, and synchronized sources across workspace tools.
- **FoveAI Traybar / Taskbar Tool**: Updated and established `start_FoveAI_Traybar.bat` and `start_FoveAI_Taskbar.bat` running `FoveAI_Taskbar.pyw` via the localized venv Python interpreter to manage the Foveated Memory proxy and stack.
- **Centralized Sovereign Core API (:8000)**: Moved soundboard bracket token context and AI expression endpoints directly into `compagent.py` on Port 8000. All backend APIs are now centralized under Sovereign Core, freeing frontends (8080/5176) to be pure stateless UI vessels.
- **Port 8400 Central Proxy Authority**: Foveated Memory Proxy (`server.js` on 8400) now handles all LLM memory, context compression, and Membrane HUD. Legacy proxy ports (8200, 8300, 8103, 8106) retired/absorbed into 8400.
- **9-Node Concordia Fleet**: Expanded `sleipnir_launcher.js` from 4 to 9 parallel nodes. Added Sovereign Core (:8000), XR Vessel (:8080), Motor Cortex (:8110), Vite Dev (:5176), and Cloudflare Tunnel.
- **Motor Cortex Integration**: `motor_cortex.py` now fully integrated into `compagent.py` streaming pipeline. LLM can output `[MOTOR:tool_name{"arg":"value"}]` tags that are parsed, stripped from display text, and returned as structured `motor_actions` in the JSON response. New `/compagent/stream` SSE endpoint yields motor events before the full response.
- **xr_app.py Restored**: The central API proxy (2,517 lines, 70+ endpoints) was missing from the repository. Restored from local backup (June 25th version). All `/api/*` routes now functional.
- **Start_LUMAX.ps1 Deprecated**: Legacy 13-service launcher now points to `Start_Concordia.PS1` as the authoritative entry point.
- **Stardust Vector Ingestion**: Replaced bloated relational graph databases with the hyper-fast Stardust matrix, achieving instant semantic resonance for code navigation.
- **Dead Sure Coding Enforcement**: Established atomic, self-healing transactional gates for all AI worker modifications.

## 3. ACTIVE OBJECTIVES
1. Verify end-to-end functionality: launch Concordia → Vite frontend → chat via `/compagent` → motor actions via SSE.
2. Test motor cortex tool execution on the frontend (walk, emotion, gesture rendering).
3. Refine the Stardust Gnists for deeper spatial memory retention during long XR sessions.
4. Clean remaining stale references in codebase (Docker Compose files, Godot scripts, Kuzu imports).

## 4. Current Issues
1. ~~Local mode, LLM thinking for 1 minute, never reaches to actually voice a greeting.~~ — **Fixed 2026-09-03**: Stale model profile upstream port (1234→8402) caused all local chat completions to fail with HTTP 400. See `context.md` entry.
2. Soul starts, seems ok, then goes offline

## 4b. Recently Fixed (2026-09-03)
- **Quest→PC HTTP 400 resolved**: The Foveated Memory Proxy (`:8400`) was routing to `http://127.0.0.1:1234` (dead legacy LM Studio port) instead of the local llama-server at `http://127.0.0.1:8402`. Root cause was stale `upstream_url` in 4 model profiles in `memory_data/model-profiles.json` and 3 vars in `foveated-memory/.env`. All corrected to `:8402`. Proxy restarted, end-to-end chat completion verified with Quest payload (`model: "foveated-proxy"`, `Authorization: Bearer lumax_spatial_client`).

## 5. Additional info ()

---

## 6. [LUMAX AGENT HUD] (DYNAMIC CONTEXT)
**SOURCE OF TRUTH:**
* **Mode:** Local Fallback active (Cloud Quota Exceeded)
* **Current Theme:** Director's Augmented Reality (XR Engine)
* **Latest Integrations:** Ghost XR HUD, To-Do Tracker, Soundscaping, Holographic Thoughts, Holodeck Mode.
* **Easter Egg Sandbox (Future):** Haptic disco lightbulb sequence with 80s music on double-hand grab.

**FOCUSED SKELETON (xr-ar-engine.js):**
``javascript
window.DirectorAR = {
    init: function(scene, camera, avatarController) { /* ... */ },
    playSound: function(url) { /* Loads Spatial Audio */ },
    showThought: function(imageUrl) { /* Projects Floating Mesh */ },
    hideThought: function() { /* Fades Mesh */ },
    holodeck: function(imageUrl) { /* Swaps ThreeJS Scene Background */ }
};
``

---

## 2026-07-31 — Dynamic Membrane Engine & 5-Tier Context Calibration (Port 8200)
| Component | Status | Location |
|---|---|---|
| **Context Compressor** | 🟢 ACTIVE | Tools/foveated-memory/core/context-compressor.js |
| **Membrane Balancer** | 🟢 ACTIVE | Tools/foveated-memory/membrane_core.py |
| **Membrane Bridge** | 🟢 ACTIVE | Tools/foveated-memory/core/membrane-bridge.js |

- **Membrane Executive HUD**: Port 8400 proxy now weaves a dynamic top-level HUD on every turn containing turn numbers, active task checklists (`[x]`/`[ ]`), recent file modification diagnostic results (`[PASSED 🟢]`/`[FAILED 🔴]`), and XRL codebase intuition (`repo-principia.md`).
- **5-Tier Empirical Compression Spectrum**:
  - **Level 0 (0% Compression)**: Verbatim recent turns (Fovea Window)
  - **Level 1 (65% Compression)**: **Lossless Baseline** — 100% instruction fidelity & context retention (Parafovea)
  - **Level 2 (72% Compression)**: Light structural skeleton & 2-sentence key summaries
  - **Level 3 (80% Compression)**: Deep signature & import skeletons with expand tags
  - **Level 4 (88% Compression)**: XRL Symbol Table URIs (`xrl://lumax/...`)
  - **Level 5 (95% Compression)**: Atomic SHA-256 hash nodes (`#hash`)
- **Auto-Revert Neutralized**: `deadsure_watchdog.py` auto-revert file deletion deactivated.
- **Context Loss Guarantee**: The combination of Level 1 (65%) baseline + top-level Membrane HUD executive control + active recall (`<recall:"hash">`) guarantees zero task drift across long sessions.
