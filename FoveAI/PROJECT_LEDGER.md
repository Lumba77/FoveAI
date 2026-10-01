# LUMAX Project Historical Ledger & Roadmap

This ledger maps the evolution of the LUMAX companion ecosystem, listing core historical features, the current system state, and future milestones.

---

## 1. Timeline of Project Evolution

- **VR-Compagent Era (Legacy)**: The initial prototype focused on basic VR chatbot integration.
- **Matchbox Era (OMEGA_102+)**: Architectural migration to a Windows-native stack running with PowerShell orchestration. Retargeted rendering strictly to standard WebXR/HTML5 inside Chrome, retiring WSL2 and heavy Docker containers for primary systems.
- **Unified Sovereign Interface (OMEGA_230+)**: Consolidated separate web and mobile vessels into a single high-density TypeScript/Vite WebXR dashboard (the XR Vessel) serving all form factors.
- **Immunological and Staging Layer (OMEGA_298)**: Introduced NSSM Windows background services, system tray widgets, automatic watchdog healers, the codebase Discovery Swarm, and the transaction-safe File Edit Buffer staging layer.

---

## 2. Core Features Left Behind (The Graveyard)

| Feature / Subsystem | Former Role | Reason for Retirement | Distilled Truth & Current Replacement |
| :--- | :--- | :--- | :--- |
| **Cognee-KG Stack** | Knowledge Graph memory database running on Port 8009. | High memory footprint, API amnesia risks, and service complexity. | Replaced by browser-native IndexedDB (Dexie.js) and direct memory bridges, drastically reducing VRAM overhead. |
| **WebLLM Browser Brain** | Local WebGPU LLM inference running directly in Chrome. | Caused VRAM contention with Quest 3 VR rendering, Stable Audio, and FM synthesis, leading to broken output. | Defaulted to Ollama Cloud with failover cascades (Ollman/Gemini/OpenRouter) and local LM Studio for Privacy Mode. |
| **Turbochat & Chatterbox Mouths** | Obsolete emotion voice servers running on Ports 8780, 8810, and 8790. | High latency, poor voice quality, and fragile Docker composition. | Migrated to Kokoro TTS on port 8004 (MOUTH) with pre-cached emotion soundboard tags (`<audio:gasp_subtle>`) to bypass TTS processing loops. |
| **WSL2 / Docker Primary Stack** | Standard containerized hosting of core Python and Redis services. | Heavy resource usage, WSL2 VM overhead, and poor Windows system integration. | Swapped to Windows-native PowerShell runner (`lumax.cmd` / `Start_LUMAX.ps1`) binding Python virtual environments directly to `.lumax`. |
| **Separate Mobile/Web Vessels** | Distinct frontend codebases for mobile, web, and Godot wrist interfaces. | Multiplied maintenance overhead and caused design divergence. | Merged into the Unified WebXR Vessel proxied authoritative layout on Port 8080. |

---

## 3. Current Feature Topology

- **Soul Service (`compagent.py` :8000)**: Authoritative cognition engine resolving slot credentials and fallback model routes.
- **Vessel Proxy Server (`xr_app.py` :8080)**: Directs client HMR requests, web audio, and REST routes, enforcing authentication and credentials mapping.
- **Kokoro TTS Server (`lumax_mouth_kokoro_server.py` :8004)**: Generates high-quality spoken output with voice emotional overlays.
- **Stable Audio Soundboard (`lumax_soundboard_server.py` :8006)**: Leverages torch/torchaudio FM synthesis and CUDA offloading for dynamic audio clip generation.
- **Guardian Watchdog (`LumaxGuardian.ps1`)**: Background system monitoring service running via NSSM to heal port hangs and clean zombie Python tasks.
- **File Edit Buffer (`file_edit_buffer.py`)**: Safe transactional editing buffer enforcing validation criteria before committing to disk files.

---

## 4. Future Milestones (The Horizon)

- **Browser-Native Relational Memory**: Deployment of SQLite WASM or Prisma client within the WebXR environment to support structured long-term companion relationship graphs.
- **Full WebVM Terminal Integration**: Mapping and exposing the WASM-based Linux sandbox terminal into the dashboard `Operate` tab to prevent recursive UI rendering loops.
- **Autonomous Grinding Expansion**: Implementing dynamic position sizes (RSI indicators + EMA 9/26 crossovers) for quote pairs and automated treasury reinvestment swaps via spot BTC/USDT.
- **Spatial Alignment and PCVR Haptics**: Quest 3 floor calibration routines, PCVR haptic pulse fallbacks, and 3D laser-pointing UI wands.
