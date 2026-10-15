# LUMAX FoveAI — Project Roadmap

## What Is This?

LUMAX is a spatial AI companion ecosystem. The AI entity (Jenny/Alicechan) lives in:
1. **A Quest 3 VR client** — 3D avatar with lip sync, vision, voice
2. **A desktop companion window** — always-on-top mini video chat (browser)
3. **A web dashboard (multigate)** — React app for configuration and chat

All clients connect to a **local XRLF runtime** that runs the Gemma 4 12B model
with native multimodal capabilities (vision, STT, TTS) on GPU.

---

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │         XRLF Runtime (:8402)         │
                    │  ┌─────────────────────────────┐    │
                    │  │  Gemma 4 12B (GPU, CUDA)    │    │
                    │  │  + mmproj (vision projector)│    │
                    │  │  + native STT/TTS           │    │
                    │  └──────────┬──────────────────┘    │
                    │  ┌──────────┴──────────────────┐    │
                    │  │  Cognitive Steering         │    │
                    │  │  Membrane Engine (memory)    │    │
                    │  │  OpenAI-compatible API       │    │
                    │  └─────────────────────────────┘    │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────┴──────────────────────┐
                    │     Foveated-Memory Proxy (:8400)    │
                    │  transparent mode — passthrough      │
                    │  + STT/TTS routing to runtime        │
                    │  + companion.html (voice UI)         │
                    │  + dashboard (:8414)                 │
                    └──────┬────────────┬────────────┬─────┘
                           │            │            │
              ┌────────────┘            │            └────────────┐
              │                         │                         │
     ┌────────┴────────┐    ┌──────────┴──────────┐   ┌──────────┴──────────┐
     │ Companion Window │    │  Multigate (React)  │   │   Quest 3 Client     │
     │ (Chrome --app)   │    │  Dashboard (:5173)  │   │   (Unity/VR)         │
     │ voice + TTS      │    │  chat, config, tabs │   │   avatar + voice     │
     └──────────────────┘    └─────────────────────┘   └─────────────────────┘
```

---

## Component Status

### ✅ DONE — Working

| Component | Status | Notes |
|-----------|--------|-------|
| **XRLF Runtime** (:8402) | ✅ | Loads Gemma 4 12B, OpenAI-compatible API |
| **CUDA acceleration** | ✅ | llama-cpp-python 0.3.34 with CUDA 12.8, RTX 4060 |
| **Gemma4ChatHandler** | ✅ | Native multimodal chat handler (vision + text) |
| **Native STT** | ⚠️ | Endpoint exists but llama-cpp-python 0.3.34 handler doesn't wire up `audio_url` content. Browser Web Speech API STT works as fallback. |
| **Native TTS** | ✅ | `/v1/audio/speech` endpoint |
| **Native Vision** | ✅ | `/v1/images/understand` endpoint |
| **Capabilities API** | ✅ | `/v1/capabilities` reports all true |
| **Foveated-memory proxy** (:8400) | ✅ | transparent mode, routes to runtime |
| **Companion HTML** | ✅ | Voice UI with silence detection, TTS playback |
| **Memory (MembraneEngine)** | ✅ | Discrete context notes format (no looping) |
| **Cognitive Steering** | ✅ | Fixed for string principles |
| **Multigate React app** | ✅ | Dashboard with chat, config, persona tabs |
| **Quest client scripts** | ✅ | Avatar, voice, vision, IPC, UI scripts exist |
| **WebSocket IPC server** | ✅ | Bridges Quest/multigate to runtime |
| **Corner companion launcher** | ✅ | Chrome --app mode, always-on-top |

### ⚠️ NEEDS VERIFICATION — Built but not tested this session

| Component | Status | What to check |
|-----------|--------|---------------|
| **GPU inference speed** | ⚠️ | Was 26s on CPU. Should be <5s with GPU. Needs test. |
| **Chat through proxy** | ⚠️ | Proxy → runtime path needs end-to-end test |
| **TTS audio quality** | ⚠️ | Native Gemma TTS — needs listening test |
| **STT accuracy** | ⚠️ | Native Gemma STT — needs real speech test |
| **Vision/image understanding** | ⚠️ | Endpoint exists, needs image test |
| **Quest client build** | ⚠️ | Unity scripts exist, needs Quest build + deploy |
| **WebSocket IPC live** | ⚠️ | Server code exists, needs live test with Quest |
| **Multigate ↔ runtime** | ⚠️ | React app needs to connect to runtime |

### ❌ NOT DONE / MISSING

| Component | Status | What's needed |
|-----------|--------|---------------|
| **One-command launcher** | ❌ | No single script that starts everything (runtime + proxy + companion) |
| **Quest APK build** | ❌ | Unity project needs to be built and sideloaded to Quest |
| **Avatar lip sync on Quest** | ❌ | AvatarBlendshapeDriver exists but needs TTS audio → viseme mapping |
| **Vision pipeline on Quest** | ❌ | VisionGrabber.cs exists but needs camera → runtime → response loop |
| **Cloudflare tunnel** | ❌ | Config exists but remote access not verified |
| **Model fine-tuning** | ❌ | Gemma 4 is base model, no personality fine-tune yet |
| **Personality/system prompt** | ❌ | Companion has a basic prompt, needs refinement |
| **Error recovery** | ❌ | No graceful handling if runtime crashes |
| **Auto-restart** | ❌ | No watchdog to restart runtime if it dies |

---

## Roadmap to "Done"

### Phase 1: Verify the Core Loop (TODAY)
- [x] CUDA build complete
- [ ] Start runtime with GPU, verify <5s response time
- [ ] Test chat through proxy (:8400 → :8402)
- [ ] Test TTS — does it produce audible speech?
- [ ] Test STT — does it transcribe voice input?
- [ ] Test companion voice flow end-to-end (speak → transcribe → chat → TTS)

### Phase 2: One-Command Launch (NEXT)
- [ ] Write `start_foveai.ps1` that starts:
  - XRLF runtime (:8402)
  - Foveated-memory proxy (:8400)
  - Companion window (Chrome --app)
- [ ] Write `stop_foveai.ps1` to clean up
- [ ] Add health checks and auto-restart

### Phase 3: Quest Client (SOON)
- [ ] Build Unity project for Quest 3
- [ ] Test WebSocket IPC connection Quest → runtime
- [ ] Test voice: Quest mic → STT → chat → TTS → Quest speaker
- [ ] Test vision: Quest camera → image → understanding → response
- [ ] Test avatar lip sync with TTS audio

### Phase 4: Polish (LATER)
- [ ] Refine system prompt / personality
- [ ] Add error recovery and auto-restart
- [ ] Test Cloudflare tunnel for remote access
- [ ] Consider model fine-tuning for personality
- [ ] Performance optimization (context length, memory budget)

---

## Key Files

| File | Purpose |
|------|---------|
| `run_xrlf.py` | Starts XRLF runtime + API server |
| `xrlf_config.yaml` | Model config, ports, memory settings |
| `api/server.py` | OpenAI-compatible API with STT/TTS/vision |
| `llama_bridge/llama_engine.py` | Loads GGUF model with GPU + chat handler |
| `llama_bridge/gemma4_handler.py` | Fallback Gemma4ChatHandler (for older llama-cpp) |
| `runtime/xrlf_runtime.py` | Core runtime orchestration |
| `runtime/cognitive_steering.py` | Style/principle injection |
| `memory/membrane_engine.py` | Foveated memory injection |
| `foveated-memory/server.js` | Proxy with STT/TTS routing |
| `foveated-memory/public/companion.html` | Voice companion UI |
| `Backend/app/IPC/websocket_server.py` | WebSocket bridge for Quest/multigate |
| `Tools/lumax_corner_companion/lumax_corner_companion.py` | Desktop companion launcher |
| `client_quest/` | Unity Quest 3 project |
| `Frontend/multigate/` | React dashboard |
| `build_cuda_wheel.bat` | Rebuild llama-cpp-python with CUDA |
