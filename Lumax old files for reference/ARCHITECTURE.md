# LUMAX Architecture & Feature Manual

> **Purpose:** This document is the living manual for the LUMAX system — covering architecture, all frontend features, how they work, and how to use them. It is written for both AI models and human developers.

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Frontend File Map](#2-frontend-file-map)
3. [Backend Service Map](#3-backend-service-map)
4. [Feature Walkthrough](#4-feature-walkthrough)
5. [Integration Points](#5-integration-points)
6. [Developer Guide](#6-developer-guide)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. System Architecture Overview

LUMAX is a **Windows-Native** AI avatar system with a 3D frontend and a distributed backend swarm. No Docker, no WSL2, no Godot.

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
│           Backend Swarm (9 nodes)            │
│                                              │
│  :8410  Sovereign Core (compagent.py)        │
│  :  Ears STT (speech-to-text)            │
│  :  Mouth Kokoro (text-to-speech)        │
│  :8101  XR Vessel API (xr_app.py, 70+ APIs)  │
│  :8400  Foveated Memory Proxy (OpenAI-compat    │
│         LLM gateway + XRL memory + dashboard) │
│  :8201  Foveated Memory Dashboard / Kiosk     │
│  :8109  Stardust Gnists (vector memory)       │
│  :8110  Motor Cortex (motor_daemon.py)        │
│  :8112  DeadSure Failsafe                     │
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
    ├── Foveated Memory Proxy (:8400) + Dashboard (:8201)
    ├── MCP Server
    ├── Core Solver
    ├── Stardust Neural (:8109)
    ├── Motor Cortex (:8110)
    ├── Sovereign Core (:8410)
    ├── XR Vessel API (:8101)
    ├── Vite Dev Server (:5176)
    └── Cloudflare Tunnel
```

---

## 2. Frontend File Map

All files in `Frontend/3D_Avatar_Chatbot/`:

### Core Entry Point

| File | Purpose |
|------|---------|
| [`index.html`](Frontend/3D_Avatar_Chatbot/index.html) | Main HTML shell. Loads all scripts, defines the DOM structure (chat panel, 3D canvas, topbar buttons, settings modals, AR overlay). Scripts load in dependency order: THREE.js → ViewerEngine → motor-bridge → LumaxIntegrationLayer → main.js |

### Application Controller

| File | Purpose |
|------|---------|
| [`src/main.js`](Frontend/3D_Avatar_Chatbot/src/main.js) | **5,233 lines.** The central application controller. Handles: config loading, avatar manifest loading, 3D scene setup, chat UI, speech recognition, TTS, LLM calls (streaming + non-streaming), emotion detection from text, settings persistence, AR overlay, proxy detection, quick prompts, inbox, todo system. |

### 3D Rendering

| File | Purpose |
|------|---------|
| [`src/ViewerEngine.js`](Frontend/3D_Avatar_Chatbot/src/ViewerEngine.js) | Three.js-based 3D engine. Loads VRM/GLB avatars, manages the single animation loop, handles camera controls, lighting, floor plane. Exposes `NEXUS_VIEWER` global. |
| [`src/gltf-viewer/`](Frontend/3D_Avatar_Chatbot/src/gltf-viewer/) | GLTF/VRM viewer components: `VRChatPanel.js`, `VRMediaPanel.js`, viewer core. |

### LUMAX Integration Layer (Ported from XR_Vessel)

| File | Purpose |
|------|---------|
| [`src/LumaxIntegrationLayer.js`](Frontend/3D_Avatar_Chatbot/src/LumaxIntegrationLayer.js) | **1,399 lines.** The bridge between the frontend and the LUMAX backend. Contains: behavior state machine (10 states), movement engine, emotional expression engine, micro-gesture system, 4-state system, bracket token injection, autonomous decision system, motor cortex SSE bridge. Exposes `window.LUMAX_INTEGRATION`. |
| [`src/motor-bridge.js`](Frontend/3D_Avatar_Chatbot/src/motor-bridge.js) | **311 lines.** SSE client connecting to Motor Cortex (:8110). Receives walk, emotion, gesture commands and routes them through LumaxIntegrationLayer. |
| [`src/LumaxHud3D.js`](Frontend/3D_Avatar_Chatbot/src/LumaxHud3D.js) | **615 lines.** 3D canvas-based HUD overlay (ported from XR_Vessel's XrIdeHud). Renders system vitals, telemetry, developer IDE overlay, media wall. Uses Orbitron font, cyberpunk styling. |

### UI Components

| File | Purpose |
|------|---------|
| [`src/OverlayManager.js`](Frontend/3D_Avatar_Chatbot/src/OverlayManager.js) | **157 lines.** Dynamic panel system. Loads HTML components via `fetch()`, injects into DOM overlay, re-executes scripts. Used by all dashboard panels. |
| [`src/PersonaContextBridge.js`](Frontend/3D_Avatar_Chatbot/src/PersonaContextBridge.js) | **369 lines.** Manages persona context caching, voice overrides, emotion mode mapping. Bridges between frontend and backend persona system. |
| [`src/PoseStudioPanel.js`](Frontend/3D_Avatar_Chatbot/src/PoseStudioPanel.js) | Pose/expression editor UI. |
| [`src/TrackingSettingsPanel.js`](Frontend/3D_Avatar_Chatbot/src/TrackingSettingsPanel.js) | Face/body tracking settings. |
| [`src/FaceTracker.js`](Frontend/3D_Avatar_Chatbot/src/FaceTracker.js) | Webcam-based face tracking for avatar expression mirroring. |
| [`src/VRGazeController.js`](Frontend/3D_Avatar_Chatbot/src/VRGazeController.js) | VR headset gaze tracking. |

### Dashboard Panels (HTML components loaded by OverlayManager)

| File | Purpose |
|------|---------|
| [`components/agency_panel.html`](Frontend/3D_Avatar_Chatbot/components/agency_panel.html) | Autonomous agency controls — toggle autonomy, set behavior mode, view decision logs |
| [`components/neural_panel.html`](Frontend/3D_Avatar_Chatbot/components/neural_panel.html) | Neural network visualization — Stardust vector activity, memory resonance |
| [`components/settings_panel.html`](Frontend/3D_Avatar_Chatbot/components/settings_panel.html) | System settings — LLM provider config, API keys, model selection |
| [`components/imagine_panel.html`](Frontend/3D_Avatar_Chatbot/components/imagine_panel.html) | Image generation — prompt-to-image via backend creativity service |
| [`components/monetize_panel.html`](Frontend/3D_Avatar_Chatbot/components/monetize_panel.html) | Monetization dashboard — token usage, API call stats, billing |
| [`components/soundboard_panel.html`](Frontend/3D_Avatar_Chatbot/components/soundboard_panel.html) | Soundboard — audio tags, flavour tags, bracket token management |
| [`components/persona_panel.html`](Frontend/3D_Avatar_Chatbot/components/persona_panel.html) | Persona management — select/switch AI personas, voice overrides |
| [`components/diagnostics_panel.html`](Frontend/3D_Avatar_Chatbot/components/diagnostics_panel.html) | System diagnostics — service health, latency, error logs |
| [`components/webvm_panel.html`](Frontend/3D_Avatar_Chatbot/components/webvm_panel.html) | WebVM terminal — in-browser Python/Node execution |
| [`components/model_hub_panel.html`](Frontend/3D_Avatar_Chatbot/components/model_hub_panel.html) | **Model Hub** — LLM provider switching, model selection, inference parameters, vision/structured toggles, cache purge |
| [`components/environment_mapping_panel.html`](Frontend/3D_Avatar_Chatbot/components/environment_mapping_panel.html) | **Environment Mapping** — environment presets, spatial boundaries, anchor points, save to backend |
| [`components/avatar_cameras_panel.html`](Frontend/3D_Avatar_Chatbot/components/avatar_cameras_panel.html) | **Avatar Cameras** — camera view presets, FOV/zoom/height sliders, render layer toggles, snapshot |
| [`components/environment_panel.html`](Frontend/3D_Avatar_Chatbot/components/environment_panel.html) | **Environment** — skybox/background presets, ambient/directional/shadow lighting, fog, floor grid |
| [`components/controllers_panel.html`](Frontend/3D_Avatar_Chatbot/components/controllers_panel.html) | **Controllers** — left/right controller status, mapping presets, button bindings, locomotion speed/turn sliders |

---

## 3. Backend Service Map

| Port | Service | File | Purpose |
|------|---------|------|---------|
| 8410 | Sovereign Core | `Backend/Cognition/compagent.py` | Central cognitive loop. Routes user input through LLM, returns responses with motor actions. |
|  | Ears STT | — | Speech-to-text service. |
|  | Mouth Kokoro | `Frontend/Mouth/lumax_mouth_kokoro_server.py` | Text-to-speech service. Python FastAPI server using Kokoro TTS pipeline. Serves audio/wav at 24kHz via POST `/tts`. Voice selection via `voice` param or `LUMAX_KOKORO_VOICE` env var. |
| 8101 | XR Vessel API | `Frontend/XR_Vessel/xr_app.py` | Legacy API proxy with 70+ endpoints. Soundboard context, avatar management, system status. |
| 8400 | Foveated Memory Proxy | `Tools/foveated-memory/server.js` | OpenAI-compatible LLM gateway. Routes cloud/local, applies XRL memory rings, exposes `/v1/models`, `/v1/chat/completions`, and control endpoints. |
| 8201 | Foveated Memory Dashboard | `Tools/foveated-memory/public/` | Settings panel, memory kiosk, and prompt UI served by the proxy. |
| 8103 | TokenSlayer | `Backend/Cognition/tokenslayer_proxy_server.py` | Smart context ingestion. Strips noise/syntax bloat, compresses code to structural skeletons (~85% reduction). |
| 8106 | TokenSlayer Proxy | — | Deprecated. Port 8400 is the single LLM gateway. |
| 8109 | Stardust Gnists | `Backend/Memory/stardust_encoder.py` | 33M parameter sentence-transformer vector matrix. Instant semantic memory matching. |
| 8110 | Motor Cortex | `Backend/Cognition/motor_daemon.py` | Native tool use: walk_forward, walk_to_target, change_emotion, trigger_micro_gesture. SSE stream. |
| 8112 | DeadSure Failsafe | — | Windows Scheduled Task-managed AI safety guard. |
| 8888 | Unsloth Gemma | — | Local LLM inference (Gemma-4 12B GGUF). |

---

## 4. Feature Walkthrough

### 4.1 Chat Interface

**How it works:**
- User types in the chat input or uses voice (STT)
- `handleUserMessage()` in [`main.js:3150`](Frontend/3D_Avatar_Chatbot/src/main.js:3150) processes input
- If an LLM provider is configured, it calls the LLM via `_handleStreamingResponse()` or `_handleNonStreamingResponse()`
- Streaming responses appear token-by-token in the chat bubble
- Non-streaming responses appear after the full response is received
- The system prompt is injected with bracket token context (see §4.7) before being sent to the LLM

**How to use:**
1. Click the ⚙️ Settings icon (top-right)
2. Select an AI provider (OpenAI, Claude, WatsonX, OllaBridge)
3. Enter API key and select a model
4. Click "Save Settings"
5. Type a message in the chat input and press Enter

### 4.2 Voice Input (STT)

**How it works:**
- Uses Web Speech API (`SpeechRecognition`) or backend Ears service (:)
- `initSpeechRecognition()` in [`main.js:3646`](Frontend/3D_Avatar_Chatbot/src/main.js:3646) sets up recognition
- Continuous listening mode via VAD pin toggle
- Auto-send option submits recognized text automatically

**How to use:**
1. Click the microphone button (🎤) next to the chat input
2. Speak — your words appear in the input field
3. Click again to stop, or enable auto-send for automatic submission

### 4.3 Text-to-Speech (TTS)

**How it works:**
- `speakText()` in [`main.js:3478`](Frontend/3D_Avatar_Chatbot/src/main.js:3478) checks `window.TTSProvider.isActive()` to decide which TTS engine to use
- **Kokoro TTS (primary):** If `LUMAX_TTS_ENABLED=true` in localStorage, uses the pluggable `window.TTSProvider` which POSTs to `/api/tts?text=...` (proxied through Nexus Proxy on port 5177 → Kokoro on port ). Returns audio/wav blob played via `AudioContext`.
- **Web Speech API (fallback):** If Kokoro is disabled, uses browser's built-in SpeechSynthesis. Voice selection with language filtering, gender preference (Any/Male/Female), rate and pitch controls.
- Bracket tokens (`<type:value>`) are stripped before TTS via `stripBracketTokens()` to prevent AI thought markers from being read aloud.
- Voice and speed are configurable via `.env` variables `LUMAX_KOKORO_VOICE` and `LUMAX_KOKORO_SPEED`, read by `_fetchEnvConfig()` and stored in localStorage.

**How to use:**
1. Set `LUMAX_TTS_ENABLED=true` in `.env` to enable Kokoro TTS
2. Set `LUMAX_KOKORO_VOICE` to the desired voice ID (e.g., `af_bella`, `af_heart` for Jen's voice)
3. Set `LUMAX_KOKORO_SPEED` to adjust speech rate (default `1.0`)
4. Restart the frontend — AI responses will be spoken with Kokoro's high-quality neural TTS
5. If Kokoro is unavailable, falls back to browser TTS automatically

### 4.4 3D Avatar Rendering

**How it works:**
- `ViewerEngine.js` loads VRM/GLB models via Three.js
- `loadAvatar()` in [`main.js:983`](Frontend/3D_Avatar_Chatbot/src/main.js:983) handles loading with IndexedDB caching
- Avatar manifest loaded from `/vendor/avatars/avatars.json`
- VRM Manager integration syncs user-installed avatars
- Single animation loop via `ViewerEngine.setAnimationLoop()`

**How to use:**
1. Select an avatar from the dropdown (top of chat panel)
2. The 3D avatar loads in the background
3. Use mouse drag to orbit, scroll to zoom
4. Click "Reset View" to re-center

### 4.5 Emotion System

**How it works:**
- `_applyEmotionFromText()` in [`main.js:3442`](Frontend/3D_Avatar_Chatbot/src/main.js:3442) analyzes AI response text for emotional keywords
- Maps to VRM blend shapes via `EMOTION_VRM_MAP` in [`LumaxIntegrationLayer.js`](Frontend/3D_Avatar_Chatbot/src/LumaxIntegrationLayer.js)
- Emotions: joy, anger, sadness, surprise, fear, disgust, neutral
- Also supports inline emotion tags from LLM responses

**How to use:**
- Automatic — the avatar's expression changes based on conversation context
- Manual emotion buttons in the UI for testing

### 4.6 Behavior State Machine (10 States)

**How it works:**
- Defined in [`LumaxIntegrationLayer.js`](Frontend/3D_Avatar_Chatbot/src/LumaxIntegrationLayer.js) as `BEHAVIOR_STATES`:
  - `CALM_IDLE` — Default standing pose with subtle breathing
  - `SOCIAL_TURN` — Turns toward the user
  - `CURIOUS_STEP` — Leans in curiously
  - `WANDER_NEARBY` — Small wandering steps
  - `EMOTIONAL_BURST` — Exaggerated emotional expression
  - `RETURNING_HOME` — Returns to home position
  - `RESTING` — Relaxed pose
  - `DEEP_IDLE` — Deep breathing, minimal movement (4-state)
  - `SLOW_BURN` — Gradual emotion buildup with micro-gestures (4-state)
  - `DREAMING` — Random emotional flickers, gaze shifts (4-state)
- Transitions driven by 5 internal drives: curiosity, restlessness, socialNeed, energy, expressiveness
- Each drive decays/recovers over time, creating natural-seeming behavior

**How to use:**
- Automatic — the avatar exhibits lifelike autonomous behavior
- Open the Agency panel to toggle autonomy on/off
- Manually set behavior state via the Agency panel dropdown

### 4.7 4-State System (Idle / Slow Burn / Dream)

**How it works:**
- `_updateFourStateSystem(delta)` in [`LumaxIntegrationLayer.js:532`](Frontend/3D_Avatar_Chatbot/src/LumaxIntegrationLayer.js:532) cycles through 3 modes every 30 seconds:
  - **idle** — Subtle breathing animation, neutral emotion
  - **slow_burn** — Gradual emotion intensity buildup, micro-gestures (head tilts, small hand movements)
  - **dream** — Random emotional flickers, gaze shifts, dreamy expressions
- Configurable cycle interval via `setFourStateCycleInterval(seconds)`
- Manual override via `setFourStateMode(mode)`

**How to use:**
- Automatic — the avatar cycles through states continuously
- Query current state via `window.LUMAX_INTEGRATION.getFourStateMode()`
- Adjust cycle speed in the Agency panel

### 4.8 Bracket Token System (Soundboard)

**How it works:**
- The AI can output `<audio:tag>` and `<flavour:tag>` tokens in responses
- `injectBracketTokens()` in [`LumaxIntegrationLayer.js:909`](Frontend/3D_Avatar_Chatbot/src/LumaxIntegrationLayer.js:909) fetches available tags from the backend and injects them into the system prompt
- Soundboard context fetched from Soul Core (`/api/soundboard/context`) with fallback to XR_Vessel API and hardcoded defaults
- Tags are parsed and executed as non-verbal expressions (sound effects, ambient audio)

**How to use:**
- Automatic — bracket tokens are injected into every LLM call
- View available tags in the Soundboard panel
- The AI will naturally use tags like `<audio:laugh>` or `<flavour:thoughtful>` in responses

### 4.9 Core Emotional Musical System & AI Soundtrack Director

**Architecture & Acoustic Life Pulse (432Hz Tuning):**
- **Jen's Harmonic Emotional Core (`compagent.py` & `MindCore.py`):**
  Jen's cognition engine defines 6 authentic **432Hz tuned Acoustic Life Pulse chords** that map directly to her psychological state:
  - ☀️ **C Major (432Hz):** `129.60Hz, 194.40Hz, 324.00Hz, 518.40Hz` — Profound joy and boundless curiosity.
  - 💖 **C Maj7 (432Hz):** `129.60Hz, 194.40Hz, 324.00Hz, 485.40Hz` — Warmth, emotional depth, and deep affection.
  - ⚡ **G Major (392Hz):** `98.00Hz, 147.00Hz, 245.00Hz, 392.00Hz` — Energized, playful, and high physical agency.
  - 🌌 **F Lydian (349Hz):** `87.20Hz, 130.80Hz, 218.00Hz, 485.40Hz` — Awe, exploration, and transcending limits.
  - 🌙 **A Minor (415Hz):** `103.70Hz, 155.60Hz, 259.30Hz, 346.00Hz` — Intimate reflection, grounding, and deep empathy.
  - 🌸 **E Minor (329Hz):** `82.20Hz, 123.40Hz, 195.50Hz, 329.00Hz` — Gentle vulnerability and profound connection.

- **5-Voice Polyphonic Pad & Cascading Harp Arpeggiator:**
  Implemented in both native Python (`Tools/lumax_top_bar/lumax_top_bar.py`) and WebAudio (`Frontend/XR_Vessel/src/senses/AmbientSoundEngine.ts`). Sub-bass lowpass filters were opened from 120Hz ➔ 1200Hz to eliminate muffled mud and allow crystalline 5-octave harmonics to shine.

- **Cinematic Film-Score Dynamic Range:**
  - **30% Baseline:** Subtle background pad atmosphere.
  - **10% Focus / Voice Ducking:** Automatically ducks when Jen speaks or user focuses.
  - **55% Emotional Swell:** Cinematic surges during shock, terror, awe, or dramatic scenes.

- **Reactive AI Soundtrack Director Model (`Backend/Cognition/MusicalDirector.py`):**
  Uses the 0.5B / 800MB Reflex Router model (`smart-router_gguf`) on Port 8400 (or trained 1B GGUF model in `~/.cache/huggingface/hub/lumax_forge`) to evaluate scene context in real-time (<40ms) and emit JSON soundtrack cues (`http://127.0.0.1:19847/soundtrack_cue`).

### 4.9 Motor Cortex Integration

**How it works:**
- `motor-bridge.js` opens an SSE connection to Motor Cortex (:8110)
- Receives structured commands: `walk_forward`, `walk_to_target`, `change_emotion`, `trigger_micro_gesture`
- Commands are routed through `LumaxIntegrationLayer` which translates them to avatar animations
- The LLM can output `[MOTOR:tool_name{"arg":"value"}]` tags that are parsed and executed

**How to use:**
- Automatic — the avatar walks, gestures, and expresses emotions based on AI responses
- Motor actions appear in the Diagnostics panel log

### 4.10 Micro-Gesture System

**How it works:**
- Defined in [`LumaxIntegrationLayer.js`](Frontend/3D_Avatar_Chatbot/src/LumaxIntegrationLayer.js) as `MICRO_GESTURES`:
  - `head_tilt`, `blink`, `eyebrow_raise`, `smirk`, `lip_purse`, `shoulder_shrug`, `finger_tap`, `weight_shift`, `breath_deep`, `gaze_shift`
- Each gesture has duration, intensity, and cooldown
- Triggered autonomously by the behavior engine or by motor cortex commands

**How to use:**
- Automatic — the avatar performs subtle micro-gestures during conversation
- Creates natural, lifelike behavior

### 4.11 3D HUD Overlay (LumaxHud3D)

**How it works:**
- `LumaxHud3D.js` renders a canvas-based 3D overlay (ported from XR_Vessel's XrIdeHud)
- Displays: system vitals (FPS, memory, latency), telemetry, developer IDE overlay, media wall
- Cyberpunk styling with Orbitron font, cyan/pink/green color scheme
- Semi-transparent dark background (`rgba(4, 8, 16, 0.62)`)

**How to use:**
- Toggle HUD visibility via the HUD button in the topbar
- HUD elements are rendered on top of the 3D scene

### 4.12 Dashboard Panels (OverlayManager)

**How it works:**
- `OverlayManager.js` provides a dynamic panel system
- Each panel is an HTML file in `components/` loaded via `fetch()`
- `overlayManager.open(title, componentUrl)` fetches HTML, injects into DOM, re-executes scripts
- Panels are registered in `index.html` with topbar buttons

**Available panels:**
| Panel | Button | Description |
|-------|--------|-------------|
| Agency | 🧠 | Autonomous behavior controls |
| Neural | 🔬 | Neural network visualization |
| Settings | ⚙️ | LLM provider config |
| Imagine | 🎨 | Image generation |
| Monetize | 💰 | Usage stats & billing |
| Soundboard | 🔊 | Audio tag management |
| Persona | 👤 | Persona switching |
| Diagnostics | 📊 | System health |
| WebVM | 💻 | In-browser terminal |
| Model Hub | 🤖 | LLM provider switching, model selection, inference params |
| Env Mapping | 🌐 | Environment presets, spatial boundaries, anchor points |
| Cameras | 📷 | Camera view presets, FOV/zoom/height, render layers |
| Environment | 🏞️ | Skybox, lighting, fog, floor grid |
| Controllers | 🎮 | Controller mapping, button bindings, locomotion |

**How to use:**
- Click any topbar button to open its panel
- Panels are draggable and can be closed with the X button
- Multiple panels can be open simultaneously

### 4.13 Persona System

**How it works:**
- `PersonaContextBridge.js` manages persona context with 60-second client-side cache
- Maps persona names to emotion modes and voice rates
- Provides voice overrides for TTS
- Bridges between frontend and backend persona system

**How to use:**
- Open the Persona panel to view available personas
- Select a persona to change the AI's personality and voice
- Persona affects both conversation style and avatar behavior

### 4.14 AR Overlay

**How it works:**
- `initAROverlay()` in [`main.js:4293`](Frontend/3D_Avatar_Chatbot/src/main.js:4293) sets up an AR-style DOM overlay
- Chat bubbles appear in AR space
- Voice input, send, place, scale, and exit controls
- To-do list integration

**How to use:**
- Click the AR button to toggle AR mode
- Chat bubbles float in 3D space
- Use place/scale buttons to position the AR content

### 4.15 Quick Prompts & Inbox

**How it works:**
- Quick prompts are predefined message templates stored in `localStorage` (`nexus_custom_prompts`)
- Two categories: `system` and `organic`
- Inbox fetches messages from the backend
- Prompt injector allows adding custom context to the next message

**How to use:**
- Click the quick prompts toggle to show/hide the prompt list
- Click a prompt to send it immediately
- Switch between system/organic tabs
- Open the prompt editor to add/remove custom prompts

### 4.16 To-Do System

**How it works:**
- `window.NexusTodos` array stores to-do items
- `window.addTodo()`, `window.completeAllTodos()`, `window.manualAddTodo()` manage the list
- AR overlay shows to-do count badge

**How to use:**
- Click the to-do button in AR mode
- Add tasks via prompt or manual entry
- Tasks persist for the session

### 4.17 Chat Persistence

**How it works:**
- Chat messages are persisted to `localStorage` (`nexus_chat_messages` and `nexus_chat_display`)
- `_persistChat()` and `_restoreChat()` in [`main.js:4124-4170`](Frontend/3D_Avatar_Chatbot/src/main.js:4124) handle save/load
- `ChatSessionHistory` class manages token-limited context (default 500 tokens)

**How to use:**
- Automatic — chat history persists across page reloads
- Clear history via the clear button in the chat panel

### 4.18 Settings Migration

**How it works:**
- Two one-time migration functions run at startup:
  - `migrateLegacySettings()` — Migrates legacy `ai_provider`/`ai_api_key` keys to unified `nexus_llm_settings` format
  - `migrateLegacyTTSSettings()` — Migrates legacy TTS keys to unified `nexus_settings_v1` format
- Ensures VR and desktop share the same settings

**How to use:**
- Automatic — runs once on first load with legacy settings

### 4.19 Proxy System

**How it works:**
- `__nexusDetectProxyUrl()` in [`main.js:4441`](Frontend/3D_Avatar_Chatbot/src/main.js:4441) detects the proxy server
- `__nexusProxyFetch()` routes all API calls through the proxy
- Supports OpenAI, Claude, WatsonX API calls through the proxy

**How to use:**
- Automatic — the proxy is auto-detected and used for all API calls

### 4.20 WatsonX Support

**How it works:**
- `callWatsonX()` in [`main.js:4583`](Frontend/3D_Avatar_Chatbot/src/main.js:4583) handles IBM WatsonX API calls
- `__getWatsonxBearer()` manages IAM token caching with automatic refresh
- Supports project ID configuration

**How to use:**
- Select "WatsonX" as provider in Settings
- Enter IBM Cloud API key and project ID
- Select a model from the WatsonX catalog

### 4.21 OllaBridge Support

**How it works:**
- `callLLM()` in [`main.js:3401`](Frontend/3D_Avatar_Chatbot/src/main.js:3401) handles OllaBridge (HomePilot/Ollama) connections
- Structured response parsing with `BridgeResponseAdapter`
- Pair token authentication via `__nexusWireOllaBridgePairButton()`

**How to use:**
- Select "OllaBridge" as provider in Settings
- Enter the bridge URL and pair token
- Click "Pair" to authenticate

### 4.22 Director Surprise

**How it works:**
- `window.triggerDirectorSurprise()` triggers a random "surprise" event
- Easter egg system for unexpected avatar behaviors

**How to use:**
- Call `window.triggerDirectorSurprise()` from the console
- Or trigger via specific conversation cues

### 4.23 Model Hub Panel

**How it works:**
- [`components/model_hub_panel.html`](Frontend/3D_Avatar_Chatbot/components/model_hub_panel.html) provides a unified interface for LLM provider and model selection
- Provider switching (OpenAI, Claude, WatsonX, OllaBridge) with per-provider model lists
- Inference parameters: temperature, max tokens, top-p, frequency/presence penalty
- Vision toggle enables multimodal input support; structured output toggle enables JSON mode
- Cache purge button clears the LLM response cache for fresh generations
- Interacts with `window.LLMManager` and `window.chatHistory` globals

**How to use:**
1. Click the 🤖 Model Hub button in the topbar (or via mobile drawer: XR/ENVIRONMENT → Model Hub)
2. Select an AI provider from the dropdown
3. Choose a model from the provider's model list
4. Adjust inference parameters as needed
5. Toggle vision/structured output for advanced use cases
6. Click "Purge Cache" to clear cached responses

### 4.24 Environment Mapping Panel

**How it works:**
- [`components/environment_mapping_panel.html`](Frontend/3D_Avatar_Chatbot/components/environment_mapping_panel.html) manages spatial environment mapping for XR/AR experiences
- Environment presets: room-scale, standing, seated, custom
- Spatial boundary visualization toggle (guardian/chaperone-style)
- Anchor point management — place, list, and remove spatial anchors
- Save/load environment maps to/from the backend via HTTP POST/GET
- Interacts with `window.NEXUS_VIEWER` for 3D scene integration

**How to use:**
1. Click the 🌐 Environment Mapping button in the topbar (or via mobile drawer: XR/ENVIRONMENT → Environment Mapping)
2. Select an environment preset
3. Toggle boundary visualization to see spatial limits
4. Place anchor points in the 3D scene
5. Click "Save to Backend" to persist the environment map

### 4.25 Avatar Cameras Panel

**How it works:**
- [`components/avatar_cameras_panel.html`](Frontend/3D_Avatar_Chatbot/components/avatar_cameras_panel.html) controls camera views for the 3D avatar scene
- Camera presets: front, side, top, orbit, close-up, custom
- FOV slider (10°–120°), zoom slider (0.5x–5x), height offset slider
- Render layer toggles: avatar, environment, UI, effects
- Snapshot button captures the current view as a data URL
- Interacts with `window.NEXUS_VIEWER` for camera manipulation

**How to use:**
1. Click the 📷 Avatar Cameras button in the topbar (or via mobile drawer: XR/ENVIRONMENT → Avatar Cameras)
2. Select a camera preset for quick positioning
3. Adjust FOV, zoom, and height for fine control
4. Toggle render layers to show/hide scene elements
5. Click "Snapshot" to capture the current view

### 4.26 Environment Panel

**How it works:**
- [`components/environment_panel.html`](Frontend/3D_Avatar_Chatbot/components/environment_panel.html) controls the 3D scene environment (skybox, lighting, fog, floor)
- Skybox/background presets: default, night, sunset, studio, grid, custom color
- Ambient light intensity/color, directional light intensity/color/position
- Shadow toggle with intensity slider
- Fog toggle with density and color controls
- Floor color, opacity, and grid overlay toggle
- Apply and Reset buttons for committing or reverting changes
- Interacts with `window.NEXUS_VIEWER` for scene property updates

**How to use:**
1. Click the 🏞️ Environment button in the topbar (or via mobile drawer: XR/ENVIRONMENT → Environment)
2. Select a skybox/background preset
3. Adjust lighting parameters (ambient, directional, shadow)
4. Configure fog and floor settings
5. Click "Apply" to commit changes, "Reset" to revert to defaults

### 4.27 Controllers Panel

**How it works:**
- [`components/controllers_panel.html`](Frontend/3D_Avatar_Chatbot/components/controllers_panel.html) manages VR/XR controller mapping and configuration
- Left/right controller status indicators (connected/disconnected, battery level)
- Mapping presets: default, smooth, creative, minimal, custom
- Per-button binding configuration: trigger, grip, thumbstick (x/y), A/B/X/Y buttons
- Locomotion speed slider (0.5x–3x), turn speed slider (smooth/snap)
- HMD-locked movement toggle for head-relative direction
- Apply and Calibrate buttons for committing bindings or re-calibrating
- Interacts with `window.NEXUS_VIEWER` and VR controller APIs

**How to use:**
1. Click the 🎮 Controllers button in the topbar (or via mobile drawer: XR/ENVIRONMENT → Controllers)
2. View controller connection status
3. Select a mapping preset or configure custom bindings
4. Adjust locomotion and turn speed
5. Toggle HMD-locked movement if desired
6. Click "Apply" to activate bindings, "Calibrate" to re-calibrate

### 4.28 Kokoro TTS System

**How it works:**
- The Kokoro TTS system is a **pluggable TTS provider** registered as `window.TTSProvider` in [`main.js:4699`](Frontend/3D_Avatar_Chatbot/src/main.js:4699)
- The proxy chain is: `speakText()` → `window.TTSProvider.speak(text)` → `GET /api/tts?text=...` → Nexus Proxy (`server.js:405`) → `POST http://127.0.0.1:/tts` → Kokoro Python server → audio/wav response
- `window.TTSProvider` exposes three methods:
  - `isActive()` — Returns `true` if `localStorage.getItem('LUMAX_TTS_ENABLED') === 'true'`
  - `speak(text)` — Fetches audio from `/api/tts?text=...&voice=...&speed=...`, plays via `AudioContext`, returns a Promise that resolves when speech ends
  - `stop()` — Aborts the current `AudioContext` source and fetch request
- Voice and speed are read dynamically from localStorage (set by `.env` via `_fetchEnvConfig()`)
- The Kokoro backend server ([`lumax_mouth_kokoro_server.py`](Frontend/Mouth/lumax_mouth_kokoro_server.py)) is a Python FastAPI service on port  that:
  - Loads the Kokoro TTS pipeline (MIT license, ~82M parameters)
  - Accepts POST `/tts` with `text`, `voice`, and `speed` parameters
  - Returns `audio/wav` at 24kHz sample rate
  - Supports emotion-mapped voice selection (e.g., `af_heart` for warm, `af_bella` for neutral)
- Bracket tokens are stripped before TTS via `stripBracketTokens()` in [`main.js:3695`](Frontend/3D_Avatar_Chatbot/src/main.js:3695) — removes all `<...>` patterns and standalone `<>` characters

**How to use:**
1. Ensure Kokoro server is running on port  (started by `sleipnir_launcher.js` as part of the LUMAX stack)
2. Set `LUMAX_TTS_ENABLED=true` in `.env`
3. Set `LUMAX_KOKORO_VOICE=af_heart` for Jen's warm voice, or `af_bella` for a neutral voice
4. Set `LUMAX_KOKORO_SPEED=1.0` (adjust higher/lower for faster/slower speech)
5. Restart the frontend — all AI speech will use Kokoro
6. To disable Kokoro and use browser TTS, set `LUMAX_TTS_ENABLED=false`

### 4.29 Memory Bridge (Personality & Chat Persistence)

**How it works:**
- The Memory Bridge is initialized by `_initMemoryBridge()` in [`main.js:4720`](Frontend/3D_Avatar_Chatbot/src/main.js:4720) and provides three functions:
  1. **Local Persistence** — Saves personality, user name, and chat history to `localStorage` keys (`lumax_personality`, `lumax_user_name`, `lumax_chat_history`, `lumax_greeting_seen`) whenever they change
  2. **Boot Restoration** — On page load, restores all memory data from `localStorage`. If the browser was cleansed (no localStorage data), fetches from `/api/memory/restore` endpoint
  3. **Server Backup** — Every 60 seconds, POSTs all memory data to `/api/memory/backup` (proxied through Nexus Proxy to Soul Core or dedicated memory service)
- The greeting system (`_initGreetingSystem()` at [`main.js:4780`](Frontend/3D_Avatar_Chatbot/src/main.js:4780)) is called after memory restore and checks `lumax_greeting_seen` to avoid repeat greetings
- Memory backup is gated by `LUMAX_MEMORY_BACKUP_ENABLED` in `.env`

**Data Flow:**
```
User chats → chatHistory updates → _persistChat() → localStorage
                                                      │
                                                      ├── Boot: _restoreChat() → chatHistory
                                                      │
                                                      └── Every 60s: POST /api/memory/backup
                                                              │
                                                              └── Boot (clean): GET /api/memory/restore
```

**How to use:**
- Automatic — personality, user name, and chat history persist across page reloads
- To clear memory, clear browser localStorage or set `LUMAX_MEMORY_BACKUP_ENABLED=false` in `.env`
- The greeting system speaks once per session — to reset, clear `lumax_greeting_seen` from localStorage

### 4.30 Greeting System

**How it works:**
- `_initGreetingSystem()` in [`main.js:4780`](Frontend/3D_Avatar_Chatbot/src/main.js:4780) runs after avatar load and memory restore
- Polls `window.NEXUS_AVATAR_LOADED` every 500ms (up to 30 seconds) to detect when the avatar is fully loaded
- Checks `localStorage.getItem('lumax_greeting_seen')` — only greets once per session
- Speaks: "Hello, thank you, welcome [userName], it's so happy to have you here"
- Sets `lumax_greeting_seen` to `'true'` to prevent repeat greetings
- Gated by `LUMAX_GREETING_ENABLED` in `.env`

**How to use:**
- Automatic — the avatar greets the user by name on first load
- To disable, set `LUMAX_GREETING_ENABLED=false` in `.env`
- To reset the greeting, delete `lumax_greeting_seen` from browser localStorage

### 4.31 Animation Pipeline (Phase 3 Engine)

**How it works:**
The 3D avatar animation is driven by a multi-stage pipeline that runs every frame in the render loop ([`ViewerEngine.js:1176-1211`](Frontend/3D_Avatar_Chatbot/src/gltf-viewer/ViewerEngine.js:1176)):

```
Render Loop Order:
1. AvatarManager.update(dt) — VRM sync (spring bones, expressions)
   └── autoUpdateHumanBones = false (set after fixTPose())
       Prevents VRM from overwriting procedural bone corrections

2. NEXUS_PROCEDURAL_ANIMATOR.update(t, dt) — Phase 3 procedural animation
   ├── fixTPose() — Corrects T-pose arms to natural resting position
   ├── Breathing — Subtle chest/abdomen oscillation
   ├── Head Look — Natural gaze toward points of interest
   ├── Base Pose — Idle stance with weight shifts
   └── Emotion Blendshapes — Facial expressions from EmotionEngine

3. BehaviorEngine (via AvatarAliveness) — State machine transitions
   ├── IDLE — Subtle breathing, micro-gestures
   ├── LISTENING — Attentive posture, slight head tilt
   ├── THINKING — Gaze shift, brow furrow
   └── SPEAKING — Lip sync visemes, gesture emphasis

4. LumaxIntegrationLayer.update(dt, camera) — High-level behavior
   ├── Behavior state machine (10 states)
   ├── 4-state system (idle / slow_burn / dream)
   ├── Motor cortex command processing
   └── Bracket token injection (no bone manipulation)
```

**Key Design Decisions:**
- **`autoUpdateHumanBones = false`** — VRM's `humanoid.autoUpdateHumanBones` defaults to `true`, which syncs normalized bones → raw bones every frame, overwriting ProceduralAnimator's `fixTPose()` corrections. Set to `false` after `fixTPose()` and initial `vrm.update(0)` sync in [`ProceduralAnimator.registerAvatar():628`](Frontend/3D_Avatar_Chatbot/src/ProceduralAnimator.js:628).
- **LumaxIntegrationLayer bone manipulation removed** — `_updateProceduralIdle()` previously called `head.lookAt(camera.position)` and manipulated spine bones directly, fighting Phase 3 every frame. Now a no-op — Phase 3 has full autonomy over bone animation.
- **VRM rotation** — VRM spec defines forward as -Z. Camera is at +Z. Conditional 180° Y-rotation is applied only for VRM models in [`AvatarManager.js:336`](Frontend/3D_Avatar_Chatbot/src/gltf-viewer/AvatarManager.js:336) and [`ViewerEngine.js:514`](Frontend/3D_Avatar_Chatbot/src/gltf-viewer/ViewerEngine.js:514). GLB models (which face +Z) are not rotated.
- **Head look direction** — Three.js `Object3D.lookAt()` aligns local +Z toward the target. VRM faces along -Z. So `head.lookAt(camera.position)` made the face point away. Fixed by negating the lookAt direction in [`LumaxIntegrationLayer.js:1117`](Frontend/3D_Avatar_Chatbot/src/LumaxIntegrationLayer.js:1117).

**Script Load Order (Phase 3 scripts):**
```
AnimationPresets.js → ProceduralAnimator.js → EmotionEngine.js →
LipSyncEngine.js → BehaviorEngine.js → AnimationManager.js →
AvatarAliveness.js → ClipAnimationLoader.js → VRMAAnimationLoader.js →
BVHAnimationLoader.js
```

**How to use:**
- Automatic — the avatar breathes, looks around, gestures, and expresses emotions autonomously
- To verify the pipeline is working, check the browser console for `[ProceduralAnimator]` and `[AvatarAliveness]` log messages
- If the avatar is in T-pose, check that `autoUpdateHumanBones` is set to `false` in `ProceduralAnimator.registerAvatar()`

### 4.32 .env Configuration for Frontend

**How it works:**
- The 3D Avatar Chatbot frontend reads configuration from `.env` via `_fetchEnvConfig()` in [`main.js:1050`](Frontend/3D_Avatar_Chatbot/src/main.js:1050)
- `.env` variables are fetched from the Nexus Proxy (`/api/env`) and stored in `localStorage` for the frontend to use
- The following frontend-specific variables are defined in [`.env:120`](.env:120):

| Variable | Default | Description |
|----------|---------|-------------|
| `LUMAX_TTS_ENABLED` | `true` | Enable Kokoro TTS (vs browser Web Speech API) |
| `LUMAX_KOKORO_VOICE` | `af_bella` | Kokoro voice ID. Use `af_heart` for Jen's warm voice |
| `LUMAX_KOKORO_SPEED` | `1.0` | Speech speed multiplier (0.5 = half speed, 2.0 = double) |
| `LUMAX_MEMORY_BACKUP_ENABLED` | `true` | Enable periodic memory backup to server |
| `LUMAX_GREETING_ENABLED` | `true` | Enable personalized greeting on avatar load |
| `LUMAX_USER_NAME` | `Darnell` | User's name for personalized greeting and memory |

**How to use:**
1. Edit `.env` in the project root
2. Set the desired values for the frontend variables
3. Restart the frontend (refresh browser) — `_fetchEnvConfig()` reads the new values
4. The values are cached in `localStorage` — to force a refresh, clear localStorage or restart the proxy server

---

## 5. Integration Points

### 5.1 Frontend → Backend Connections

| Frontend Component | Backend Service | Protocol | Endpoint |
|-------------------|----------------|----------|----------|
| `LumaxIntegrationLayer` | Motor Cortex (:8110) | SSE | `/motor/subscribe` |
| `LumaxIntegrationLayer` | Soul Core (:8410) | HTTP | `/api/soundboard/context` |
| `LumaxIntegrationLayer` | XR Vessel API (:8101) | HTTP | `/api/soundboard/context` (fallback) |
| `main.js` | Soul Core (:8410) | HTTP | `/compagent/stream` |
| `main.js` | Proxy (:3001) | HTTP | `/api/proxy` |
| `PersonaContextBridge` | Soul Core (:8410) | HTTP | `/api/persona/*` |
| `window.TTSProvider` (main.js) | Kokoro (:) via Nexus Proxy (:5177) | HTTP | `GET /api/tts?text=...&voice=...&speed=...` → `POST /tts` |
| `_initMemoryBridge()` (main.js) | Soul Core (:8410) via Nexus Proxy (:5177) | HTTP | `POST /api/memory/backup`, `GET /api/memory/restore` |
| `_fetchEnvConfig()` (main.js) | Nexus Proxy (:5177) | HTTP | `GET /api/env` |

### 5.2 Global Namespace

All frontend components expose themselves on the `window` object:

| Global | Source | Purpose |
|--------|--------|---------|
| `window.LUMAX_INTEGRATION` | `LumaxIntegrationLayer.js` | Central integration layer |
| `window.NEXUS_VIEWER` | `ViewerEngine.js` | 3D viewer engine |
| `window.NEXUS_ANIMATION_MANAGER` | `ViewerEngine.js` | Animation controller |
| `window.NEXUS_PROCEDURAL_ANIMATOR` | `ProceduralAnimator.js` | Phase 3 procedural animation engine |
| `window.NEXUS_AVATAR_LOADED` | `ViewerEngine.js` | Avatar load completion flag (boolean) |
| `window.overlayManager` | `OverlayManager.js` | Panel overlay system |
| `window.PersonaContextBridge` | `PersonaContextBridge.js` | Persona management |
| `window.SpeechService` | `SpeechService.js` | TTS/STT service |
| `window.TTSProvider` | `main.js` (registered at line 4699) | Pluggable TTS provider (Kokoro or Web Speech) |
| `window.LLMManager` | `LLMManager.js` | LLM provider manager |
| `window.chatHistory` | `main.js` | Chat session history |
| `window.NexusTodos` | `main.js` | To-do list |
| `window.NexusCustomPrompts` | `main.js` | Quick prompts |
| `window.sendBotResponseToVR` | `main.js` | VR response bridge |

### 5.3 Event System

Custom DOM events for cross-component communication:

| Event | Dispatched By | Purpose |
|-------|--------------|---------|
| `avatar-emotion` | `main.js` | Emotion change notification |
| `avatar-loaded` | `ViewerEngine.js` | Avatar load complete (sets `window.NEXUS_AVATAR_LOADED = true`) |
| `motor-command` | `motor-bridge.js` | Motor cortex command received |

---

## 6. Developer Guide

### 6.1 Adding a New Dashboard Panel

1. Create an HTML file in `components/` (e.g., `my_panel.html`)
2. Add a button in `index.html` with `onclick="overlayManager.open('My Panel', 'components/my_panel.html')"`
3. Register the button in `OverlayManager.js` if needed
4. The panel HTML can contain inline `<script>` tags — they will be re-executed on load

### 6.2 Adding a New Behavior State

1. Add the state to `BEHAVIOR_STATES` in [`LumaxIntegrationLayer.js`](Frontend/3D_Avatar_Chatbot/src/LumaxIntegrationLayer.js)
2. Add drive configuration in `DEFAULT_MOVEMENT_CONFIG`
3. Add transition logic in `_updateDrives()` or `_updateFourStateSystem()`
4. Add animation handling in the state switch block

### 6.3 Adding a New Backend Connection

1. Add the endpoint URL constant at the top of [`LumaxIntegrationLayer.js`](Frontend/3D_Avatar_Chatbot/src/LumaxIntegrationLayer.js)
2. Create a fetch/SSE method in the class
3. Call it from `init()` or `update()` as appropriate
4. Expose any public methods on `window.LUMAX_INTEGRATION`

### 6.4 Script Load Order (index.html)

```
1. THREE.js (vendor)
2. OrbitControls (vendor)
3. GLTFLoader (vendor)
4. ViewerEngine.js
5. motor-bridge.js
6. LumaxIntegrationLayer.js
7. LumaxHud3D.js
8. OverlayManager.js
9. PersonaContextBridge.js
10. FaceTracker.js
11. VRGazeController.js
12. main.js (last — depends on all above)
```

---

## 7. Troubleshooting

### Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Avatar not loading | ViewerEngine not ready | Check `window.NEXUS_VIEWER` exists |
| Avatar in T-pose | `autoUpdateHumanBones` still `true` | Check `ProceduralAnimator.registerAvatar()` sets `_vrm.humanoid.autoUpdateHumanBones = false` after `fixTPose()` |
| Avatar facing away | VRM model without 180° rotation | Check `AvatarManager.js:336` applies `root.rotation.y = Math.PI` only when `isVRM` is true |
| Head facing away | `lookAt` direction not negated for VRM | Check `LumaxIntegrationLayer.js:1117` negates the lookAt target for VRM's -Z forward |
| No AI response | No provider configured | Open Settings → configure provider |
| Streaming not working | Provider doesn't support streaming | Falls back to non-streaming automatically |
| Motor commands not executing | Motor Cortex not running | Check `:8110` is active |
| Soundboard tags not working | Soul Core not running | Falls back to XR_Vessel API, then defaults |
| HUD not showing | LumaxHud3D not initialized | Check console for errors |
| Panel not loading | Component URL incorrect | Check `components/` file exists |
| Voice not working | Microphone permission denied | Allow microphone access in browser |
| Kokoro TTS not speaking | `LUMAX_TTS_ENABLED` not `true` | Set `LUMAX_TTS_ENABLED=true` in `.env` and restart |
| Kokoro TTS wrong voice | `LUMAX_KOKORO_VOICE` not set | Set `LUMAX_KOKORO_VOICE=af_heart` for Jen's voice |
| Memory not persisting | `LUMAX_MEMORY_BACKUP_ENABLED` is `false` | Set `LUMAX_MEMORY_BACKUP_ENABLED=true` in `.env` |
| Greeting not speaking | `LUMAX_GREETING_ENABLED` is `false` or `lumax_greeting_seen` is set | Set `LUMAX_GREETING_ENABLED=true` or clear localStorage key |
| Bracket tokens read aloud | `stripBracketTokens()` not called | Check `speakText()` calls `stripBracketTokens()` before TTS |

### Debugging

- Open browser DevTools (F12)
- Check console for `[Nexus]` and `[LumaxIntegration]` prefixed logs
- Open Diagnostics panel for service health
- Call `window.debugAPIKeys()` in console to verify API key configuration

---

> **Last updated:** 2026-07-10
> **Maintainer:** LUMAX AI System
> **Note:** This document is auto-maintained. When adding new features, update the relevant section.
---

## XRL Context Checkpointing Layer (2026-07-14)

A transparent **context compression middleware** sits inside the Foveated Memory proxy (port 8400).

### Foveated Memory Proxy behavior notes
- **Single source of truth for LLM routing.** Port 8400 exposes an OpenAI-compatible `/v1` surface. Cloud mode forwards to Ollama Cloud (`LUMAX_PROXY_TARGET`); local mode forwards to LM Studio (`LM_STUDIO_URL`).
- **Memory is workspace-isolated by Bearer token.** The `Authorization` header value is sanitized into a workspace directory name; each token gets its own memory store under `Tools/foveated-memory/memory_data/`.
- **Model resolution.** `model: auto`, missing model, or cloud-provider-style model names are resolved to the configured default: `LUMAX_MODEL_CLOUD_ID` in cloud mode, `LUMAX_MODEL_LOCAL_ID` in local mode. Do not rely on upstream to interpret placeholder names.
- **Do not inject reasoning controls by default.** The proxy must not send `reasoning_effort` or `thinking_budget` unless the user explicitly requests them. Ollama Cloud treats these as signals to return only a `reasoning` field, leaving `content` empty.
- **Reasoning fallback.** Ollama Cloud returns chain-of-thought in `message.reasoning` / `delta.reasoning`. The proxy falls back to this field when `content` is empty, and maps it into the content stream for the client.
- **SSE newline handling.** Streamed responses must terminate each `data:` frame with real `\n\n` characters. Escaped `\\n` sequences are emitted literally and corrupt the output.

Every 8 turns: oldest batch summarized by LM Studio (7272) into a CKP:hash block (~60 tokens).
Last 4 turns kept verbatim. Cache stored in Tools/foveated-memory/memory_data/checkpoints/.

**Effect:** 30-turn session: ~80K tokens -> ~9K tokens (~89% reduction). Fully transparent.
**Files:** Tools/foveated-memory/core/context-compressor.js, Tools/foveated-memory/server.js

> Last updated: 2026-07-14
