# Architecture Diagram

## Current Service Map (2026-09-19, post-migration)

```
LAN clients (Quest, browsers, IDE extensions)
        │  LAN IP is dynamic — server_config.SERVER_IP resolves it live;
        │  foveai_network_config.json snapshots refreshed at Sleipnir startup
        ▼
┌────────────────────────────────────────────────────────────┐
│  Foveated Memory Proxy  :8400  (HTTP + WS, memory rings,   │
│  voice routing, /api/subsystems health)                    │
│  Dashboard / settings   :8401  (served alongside proxy)    │
└──────────────┬─────────────────────────────────────────────┘
               │
    ┌──────────┼───────────────┬──────────────┬─────────────┐
    ▼          ▼               ▼              ▼             ▼
 XRLF      WS IPC :8403    Kokoro TTS     Whisper STT   Chat Relay
 runtime   (WS only)       :8406          :8409         :8407
 :8402                                  (WS only)
 (HTTP, native
  TTS+STT,
  Soul/compagent)

 Motor :8410 · Subconscious :8411 · Creative :8408 (optional)
 Multigate WebUI :5177 (same-origin /api/* → :8400)
 Optional/offline: XR Vessel :5176, LM Studio :1234
 Retired: voice :8001/:8004, soul :8000, motor :8110,
 stardust :8109, tokenslayer :8103/:8106, old proxy :8200
```

## Quest → PC Backend Connection (2026-09-03 verified)

```
+-------------------+         HTTP POST          +-------------------+         HTTP POST        +-------------------+
| Quest 3 APK       |  ──────────────────────>   | Foveated Memory   |  ───────────────────>  | Local llama-server|
| DirectXRLFClient  |  /v1/chat/completions      | Proxy (server.js) |  /v1/chat/completions  | (:8402)           |
| :8400             |  Bearer lumax_spatial_client| :8400            |                        | qwen3.5-4b-moq    |
| model:"foveated-  |  Content-Type: app/json    | Node.js           |                        | XRLF model format  |
|  proxy"           |                            | mode: local       |                        |                   |
+-------------------+                            +-------------------+                        +-------------------+
                                                         │
                                                         │ Config sources (priority order):
                                                         │ 1. memory_data/active-model.json → restoreActiveProfile()
                                                         │ 2. memory_data/model-profiles.json (upstream_url per model)
                                                         │ 3. foveated-memory/.env (XRLF_LOCAL_BASE_URL, XRLF_RUNTIME_URL)
                                                         │ 4. config/default.json (upstream_url fallback)
                                                         │
                                                         │ Dashboard: :8401/api/status
                                                         │ Health:    :8400/health
                                                         +──────────────────────────────────────────────
```

**Critical fix (2026-09-03):** Model profiles in `memory_data/model-profiles.json` had stale `upstream_url = http://127.0.0.1:1234/v1` (legacy LM Studio port). The local llama-server runs on `:8402`. The `restoreActiveProfile()` function at startup overrode the correct default with the stale profile URL, causing all local chat completions to fail with HTTP 400. Fixed by correcting 4 profiles and 3 `.env` vars from `:1234` to `:8402`.

**Key files:**
- `client_quest/Assets/Scripts/VoiceInput/DirectXRLFClient.cs` — Quest HTTP client (UnityWebRequest to `:8400/v1/chat/completions`)
- `client_quest/Assets/Scripts/IPC/ConfigLoader.cs` — Loads `AppConfig.json` with server IP and port map
- `foveated-memory/server.js` — Proxy server (port 8400), model resolution, upstream routing
- `foveated-memory/core/model-profile-loader.js` — Profile registry, `applyProfile()`, `restoreActiveProfile()`
- `foveated-memory/memory_data/model-profiles.json` — Per-model upstream URLs and cognitive mode
- `foveated-memory/memory_data/active-model.json` — Last active model (survives restarts)
- `foveated-memory/.env` — Runtime config (`XRLF_COGNITIVE_MODE`, `XRLF_LOCAL_BASE_URL`, `XRLF_RUNTIME_URL`)
- `foveated-memory/config/default.json` — Fallback defaults

---

```
+------------------+
| LUMAX UI          |
| collects requests |
+------------------+
        |
        v
+------------------+
| Orchestrator      |
| routes work       |
+------------------+
   |                 |
   |                 +--------------------+
   |                                      |
   v                                      v
+------------------+                 +------------------+
| Validator        |                 | State Manager    |
| checks payloads  |                 | stores/loads     |
+------------------+                 +------------------+
        |                                 |
        +-----------------+---------------+
                          |
                          v
+------------------+
| Rule Engine      |
| applies policies |
+------------------+
        |
        v
+------------------+
| API Client       |
| calls external   |
| services         |
+------------------+
        |
        v
+------------------+
| External APIs    |
| providers        |
+------------------+
        |
        v
+------------------+
| Response Mapper  |
| normalizes data  |
+------------------+
        |
        v
+------------------+
| State Manager    |
| updates state    |
+------------------+
        |
        +----> Orchestrator
```
