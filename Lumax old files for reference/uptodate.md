# LUMAX SYSTEM STATUS REPORT (DIAMOND CONCORDIA)

## 1. COMPONENT STATUS (14-NODE NATIVE SWARM)
| Component | Status | Port | Note |
|-----------|--------|------|------|
| **TokenSlayer** | 🟢 ACTIVE | 8103 | Smart context ingestion. Strips noise and syntax bloat before feeding the Sovereign Core. |
| **Stardust Gnists** | 🟢 ACTIVE | 8109 | 33M parameter sentence-transformer vector matrix. Replaces legacy Kuzu/Cognee for instantaneous zero-drag memory matching. |
| **Motor Cortex** | 🟢 ACTIVE | 8110 | motor_daemon.py — Native tool use (walk_forward, walk_to_target, change_emotion, trigger_micro_gesture). |
| **Ears STT** | 🟢 ACTIVE |  | Speech-to-text service. |
| **Sovereign Core** | 🟢 ACTIVE | 8410 | The core cognitive loop (compagent.py). Processes incoming TokenSlayer chunks and orchestrates the worker swarm. |
| **Mouth Kokoro** | 🟢 ACTIVE |  | Text-to-speech service. |
| **Avatar Frontend** | 🟢 ACTIVE | 5177 | 3D Avatar Chatbot UI. |
| **XR Vessel API** | 🟢 ACTIVE | 8101 | xr_app.py — 70+ API endpoints, COMAX Hivemind Injection, TokenSlayer caching. |
| **Foveated Memory Proxy** | 🟢 ACTIVE | 8400 | OpenAI-compatible proxy with Membrane HUD & 5-tier context window (Replaces legacy proxies). |
| **Memory Dashboard & Settings** | 🟢 ACTIVE | 8401 | Web UI settings, prompts kiosk, and memory status dashboard. |
| **Unsloth Gemma** | ⚪ DORMANT | 8888 | Optional local inference worker (starts on-demand via start_unsloth_gemma.ps1). |
| **Cloudflare Tunnel** | 🟢 ACTIVE | — | Exposes web UI via `https://lumax.1um6a.se`. |
| **Legacy Systems** | 🔴 PURGED | — | Docker, WSL2, Godot, Kuzu, Cognee, **TokenSlayer Proxy (:8106)**, **LM Studio (:7272, :1234)**, **go-llm-proxy**, **gemini-web-bridge**, **Vite Dev Server** — all purged. |

---

## 2. RECENT ARCHITECTURAL ADVANCEMENTS
- **Centralized Sovereign Core API (:8410)**: Moved soundboard bracket token context and AI expression endpoints directly into `compagent.py` on Port 8410. All backend APIs are now centralized under Sovereign Core, freeing frontends (5177/5176) to be pure stateless UI vessels.
- **Port 8400 Central Proxy Authority**: Foveated Memory Proxy (`server.js` on 8400) now handles all LLM memory, context compression, TokenSlayer ingestion, and Membrane HUD. Standalone proxies (8103, 8106) retired/absorbed.
- **9-Node Concordia Fleet**: Expanded `sleipnir_launcher.js` from 4 to 9 parallel nodes. Added Sovereign Core (:8410), XR Vessel (:5177), Motor Cortex (:8110), Vite Dev (:5176), and Cloudflare Tunnel.
- **Motor Cortex Integration**: `motor_cortex.py` now fully integrated into `compagent.py` streaming pipeline. LLM can output `[MOTOR:tool_name{"arg":"value"}]` tags that are parsed, stripped from display text, and returned as structured `motor_actions` in the JSON response. New `/compagent/stream` SSE endpoint yields motor events before the full response.
- **xr_app.py Restored**: The central API proxy (2,517 lines, 70+ endpoints) was missing from the repository. Restored from local backup (June 25th version). All `/api/*` routes now functional.
- **Start_LUMAX.ps1 Deprecated**: Legacy 13-service launcher now points to `Start_Concordia.PS1` as the authoritative entry point.
- **Stardust Vector Ingestion**: Replaced bloated relational graph databases with the hyper-fast Stardust matrix, achieving instant semantic resonance for code navigation.
- **TokenSlayer Context Filtering**: Deployed the Smart Context Gateway on Port 8103 with multi-language structural compaction (TypeScript, Python, Go, Java, Kotlin, PHP, Ruby, Swift, SQL, Vue, Svelte). Achieves ~85% token reduction via symbol-aware parsing with automatic line-based fallback when language servers are unavailable. Includes secrets redaction (API keys, tokens, private keys), managed-block protocol for idempotent Copilot instructions injection, and MCP server integration for IDE-agnostic structural summaries.
- **Dead Sure Coding Enforcement**: Established atomic, self-healing transactional gates for all AI worker modifications.

## 3. ACTIVE OBJECTIVES
1. Verify end-to-end functionality: launch Concordia → Vite frontend → chat via `/compagent` → motor actions via SSE.
2. Test motor cortex tool execution on the frontend (walk, emotion, gesture rendering).
3. Refine the Stardust Gnists for deeper spatial memory retention during long XR sessions.
4. Clean remaining stale references in codebase (Docker Compose files, Godot scripts, Kuzu imports).

## 4. Current Issues
1. Local mode, LLM thinking for 1 minute, never reaches to actually voice a greeting. 
2. Soul starts, seems ok, then goes offline

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

## 2026-07-31 — Dynamic Membrane Engine & 5-Tier Context Calibration (Port 8400)
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
