# XRLF System Architecture & Specification (v1.5)

## 1. Overview & Core Philosophy
The **eXtensible Neural Representation Format (XRLF v1.5)** is FoveAI's native container format designed to unify high-speed local LLM inference, multi-token speculative decoding (MTP), Mixture of Quantizations (MoQ), and spatial VR/AR client execution.

### Architectural Invariant: PC-Centric Backend Execution
- **PC Host Core**: All heavy AI models (LLMs, VLM vision engines, neural TTS, streaming STT) execute **100% on the host PC**.
- **Lightweight Quest VR Client**: Models are **NOT needed on Quest**. The Quest headset runs a lightweight VR vessel (`AliceVR.apk`, ~12.5 MB) that streams spatial motion opcodes and thoughts from the PC backend over local Wi-Fi.

---

## 2. Active Model & Service Specifications (PC Host)

### Primary Flagship Cognitive Core (PC Host GPU)
- **Container File**: `xrl_encoded/qwopus3.5-9b-coder-mtp-moq.xrlf` (4.66 GB)
- **Base Architecture**: Qwen3.5-9B Coder MoQ with MTP speculative decoding
- **GPU VRAM Offload**: **100% (40/40 layers)** on NVIDIA RTX 4060 (8GB VRAM)
- **KV Cache Quantization**: `type_k=Q4_0`, `type_v=Q4_0`
- **Memory Allocation**: Locked VRAM memory (`use_mlock=True`), VRAM floor safety ~1.8 GB preserved
- **Context Window**: `n_ctx: 4096`
- **Serving Endpoints**: REST API at `http://127.0.0.1:8402` & WebSocket IPC at `ws://127.0.0.1:8403`

### Active Neural Audio Daemon & Sound Effects Stack
- **Audio Daemon / Kokoro TTS**: Neural 24kHz speech synthesizer daemon (`foveai_mouth_kokoro_server.py` on `:8411`, service `foveai-tts.service`)
- **Audio Daemon / Whisper STT**: Real-time streaming speech-to-text (`stt_whisper_server.py` on `:8401`, service `foveai-stt.service`)
- **Audio Effects App & Soundboard**: Spatial impulse audio, soundboard triggers, and active voice routing

---

## 3. Build & System Safety Limits
- **Lightweight Standalone Quest Client**: Quest APK (`client_quest/AliceVR.apk`) contains only VRM avatar models, spatial UI shaders, and WebSocket bridge (~12.5 MB).
- **CPU Safety Ceiling**: Unity IL2CPP / Gradle APK builds are strictly capped to **max 10 CPU cores**:
  ```bash
  nice -n 15 ionice -c 3 taskset -c 0-9
  ```
  This preserves 2 CPU cores free for OS responsiveness, preventing host system freezes.

---

## 4. Port Topology Map

| Port | Protocol | Subsystem | Description |
|---|---|---|---|
| **8402** | HTTP | XRLF Local LLM Server | Main REST API, OpenAI `/v1/chat/completions`, native TTS/STT hooks |
| **8403** | WS | XRLF WebSocket IPC | Real-time bi-directional streaming conduit for avatar motion & thoughts |
| **8400** | HTTP/WS | Foveated Memory Proxy | Memory ring manager, context compressor, dynamic HUD injector |
| **8414** | HTTP | FoveAI Dashboard | Web UI settings & subsystem health monitor |
| **8411** | HTTP | Audio Daemon (Kokoro TTS) | Neural 24kHz speech synthesizer (`foveai-tts.service`) |
| **8413** | HTTP/WS | Chat Relay Server | Cross-client message dispatcher (`foveai-chat-relay.service`) |
| **8401** | WS | Audio Daemon (Whisper STT) | Real-time audio transcription daemon (`foveai-stt.service`) |
| **8410** | HTTP/WS | Motor Cortex Daemon | Avatar pose & agency controller (`foveai-motor.service`) |
| **8409** | HTTP | Subconscious Daemon | Telemetry evaluation & cognitive dispatch (`foveai-subconscious.service`) |
| **5177** | HTTP | Multigate WebUI | Vite-powered web interface |

---

## 5. Quest Client IPC Pipeline

```
┌──────────────────────────────────────────────┐
│  Quest 3 VR Client (AliceVR.apk ~12.5 MB)    │
│  - NO models on Quest (PC handles 100% LLM)   │
│  - Connects to PC Proxy via WebSocket/HTTP   │
└──────────────────────┬───────────────────────┘
                       │ HTTP / WS (:8400 / :8403)
                       ▼
┌──────────────────────────────────────────────┐
│  Foveated Memory Proxy (:8400)               │
│  - Inject dynamic HUD & active memory ring   │
│  - Route to local 9B Flagship engine on PC   │
└──────────────────────┬───────────────────────┘
                       │ HTTP POST (:8402)
                       ▼
┌──────────────────────────────────────────────┐
│  XRLF Runtime on PC (:8402 / :8403)          │
│  - qwopus3.5-9b-coder-mtp-moq.xrlf (Active)  │
│  - 100% GPU Offload (40/40 layers, Q4_0 KV)  │
│  - Neural Audio Daemon & Effects Active      │
└──────────────────────────────────────────────┘
```
