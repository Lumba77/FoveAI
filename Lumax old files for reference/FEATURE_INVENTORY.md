# Lumax feature inventory

**Purpose:** Live data for the Web UI **Feature Map** tab (`GET /api/feature_inventory`).  
**Format:** Numbered `## N.` sections (maps to categories in `frontend/Web_Vessel/feature_inventory_parser.py`) and **pipe tables** with a header row, separator row, and body rows. Tier cells use bold letters: **`A`** … **`D`** (e.g. **`A/B`**).

**Note:** This file was recreated in-repo when the previous large inventory was not recoverable from git history. Extend tables as you ship or change behaviour.

---

## 1. Docker / runtime

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `POST /api/dev/aider` | **A** | `frontend/XR_Vessel/xr_app.py` — run_aider_agent |
| `GET /api/web/scrape` | **A** | `frontend/XR_Vessel/xr_app.py` — scrape_web_page |
| `POST /api/vision/upload/phone_camera` | **A** | `frontend/XR_Vessel/xr_app.py` — upload_phone_camera_image |
| `POST /api/vision/capture` | **A** | `frontend/XR_Vessel/xr_app.py` — request_vision_capture |
| `GET /api/vision/feed/{source_id}` | **A** | `frontend/XR_Vessel/xr_app.py` — get_vision_feed |
| `GET /api/vision/sources` | **A** | `frontend/XR_Vessel/xr_app.py` — list_vision_sources |
| `GET /api/album-art/download/{session_id}` | **A** | `frontend/XR_Vessel/xr_app.py` — download_artwork_zip |
| `POST /api/album-art/upscale` | **A** | `frontend/XR_Vessel/xr_app.py` — upscale_artwork |
| `POST /api/album-art/choose` | **A** | `frontend/XR_Vessel/xr_app.py` — choose_artwork |
| `POST /api/album-art/generate/song` | **A** | `frontend/XR_Vessel/xr_app.py` — generate_song_art |
| `POST /api/album-art/generate/album` | **A** | `frontend/XR_Vessel/xr_app.py` — generate_album_art |
| `DELETE /api/album-art/session/{session_id}` | **A** | `frontend/XR_Vessel/xr_app.py` — delete_album_art_session |
| `GET /api/album-art/session/{session_id}` | **A** | `frontend/XR_Vessel/xr_app.py` — get_album_art_session |
| `POST /api/album-art/session/create` | **A** | `frontend/XR_Vessel/xr_app.py` — create_album_art_session |
| `GET /api/album-art/reference/controlnet` | **A** | `frontend/XR_Vessel/xr_app.py` — get_controlnet_presets_api |
| `GET /api/album-art/reference/colors` | **A** | `frontend/XR_Vessel/xr_app.py` — get_reference_colors |
| `GET /api/album-art/reference/styles` | **A** | `frontend/XR_Vessel/xr_app.py` — get_reference_styles |
| `GET /api/album-art/reference/albums` | **A** | `frontend/XR_Vessel/xr_app.py` — get_reference_albums |
| `POST /api/director/apply` | **A** | `frontend/XR_Vessel/xr_app.py` — post_director_apply |
| `GET /api/director/reports` | **A** | `frontend/XR_Vessel/xr_app.py` — get_director_reports |
| `POST /api/director/analyze` | **A** | `frontend/XR_Vessel/xr_app.py` — post_director_analyze |
| `GET /api/director/status` | **A** | `frontend/XR_Vessel/xr_app.py` — get_director_status |
| `GET /api/director/heal/status` | **A** | `frontend/XR_Vessel/xr_app.py` — get_director_heal_status |
| `POST /api/director/heal` | **A** | `frontend/XR_Vessel/xr_app.py` — post_director_heal |
| `POST /api/inbox/notify-crash` | **A** | `frontend/XR_Vessel/xr_app.py` — notify_crash_via_email |
| `POST /api/inbox/send-test-email` | **A** | `frontend/XR_Vessel/xr_app.py` — send_test_email |
| `PUT /api/inbox/email-config` | **A** | `frontend/XR_Vessel/xr_app.py` — update_email_config |
| `GET /api/inbox/email-config` | **A** | `frontend/XR_Vessel/xr_app.py` — get_email_config |
| `GET /api/inbox/crash-report/{report_id}` | **A** | `frontend/XR_Vessel/xr_app.py` — get_crash_report_details |
| `GET /api/inbox/unread-count` | **A** | `frontend/XR_Vessel/xr_app.py` — get_inbox_unread_count |
| `GET /api/inbox/messages` | **A** | `frontend/XR_Vessel/xr_app.py` — get_inbox_messages |
| `GET /api/inbox/crash-reports` | **A** | `frontend/XR_Vessel/xr_app.py` — get_crash_reports |
| `GET /api/discovery/reports` | **A** | `frontend/XR_Vessel/xr_app.py` — get_discovery_reports |
| `POST /api/swarm/launch` | **A** | `frontend/XR_Vessel/xr_app.py` — post_swarm_launch |
| `GET /api/swarm/state` | **A** | `frontend/XR_Vessel/xr_app.py` — get_swarm_state_endpoint |
| `POST /api/dreamscape/generate` | **A** | `frontend/XR_Vessel/xr_app.py` — post_dreamscape_generate |
| `GET /api/state/current` | **A** | `frontend/XR_Vessel/xr_app.py` — get_current_state |
| `POST /api/state/switch` | **A** | `frontend/XR_Vessel/xr_app.py` — switch_lumax_state |
| `POST /api/dreamscape/preheat` | **A** | `frontend/XR_Vessel/xr_app.py` — preheat_dreamscape |
| `GET /api/dreamscape/settings` | **A** | `frontend/XR_Vessel/xr_app.py` — get_dreamscape_settings |
| `GET /api/dream/catalog` | **A** | `frontend/XR_Vessel/xr_app.py` — get_dream_catalog |
| `GET /api/creativity/status` | **A** | `frontend/XR_Vessel/xr_app.py` — get_creativity_status |
| `GET /api/creativity/health` | **A** | `frontend/XR_Vessel/xr_app.py` — get_creativity_health |
| `GET /api/architecture/raw` | **A** | `frontend/XR_Vessel/xr_app.py` — get_architecture_raw |
| `GET /api/architecture` | **A** | `frontend/XR_Vessel/xr_app.py` — get_architecture |
| `GET /api/fmap` | **A** | `frontend/XR_Vessel/xr_app.py` — get_feature_map |
| `GET /api/consent/microsoft/disconnect` | **A** | `frontend/XR_Vessel/xr_app.py` — consent_microsoft_disconnect |
| `GET /api/consent/google/disconnect` | **A** | `frontend/XR_Vessel/xr_app.py` — consent_google_disconnect |
| `POST /api/consent/sync` | **A** | `frontend/XR_Vessel/xr_app.py` — consent_sync_all |
| `GET /api/consent/microsoft/callback` | **A** | `frontend/XR_Vessel/xr_app.py` — consent_microsoft_callback |
| `GET /api/consent/microsoft/auth` | **A** | `frontend/XR_Vessel/xr_app.py` — consent_microsoft_auth |
| `GET /api/consent/google/callback` | **A** | `frontend/XR_Vessel/xr_app.py` — consent_google_callback |
| `GET /api/consent/google/auth` | **A** | `frontend/XR_Vessel/xr_app.py` — consent_google_auth |
| `GET /api/consent/status` | **A** | `frontend/XR_Vessel/xr_app.py` — consent_status |
| `GET /api/announcements` | **A** | `frontend/XR_Vessel/xr_app.py` — get_announcements |
| `GET /api/config/ui` | **A** | `frontend/XR_Vessel/xr_app.py` — get_ui_config |
| `POST /api/diagnostics/run` | **A** | `frontend/XR_Vessel/xr_app.py` — run_diagnostics |
| `POST /api/presence/heartbeat` | **A** | `frontend/XR_Vessel/xr_app.py` — presence_heartbeat |
| `POST /api/proxy/lmstudio/chat` | **A** | `frontend/XR_Vessel/xr_app.py` — proxy_lmstudio_chat |
| `POST /api/proxy/lmstudio/unload` | **A** | `frontend/XR_Vessel/xr_app.py` — proxy_lmstudio_unload |
| `POST /api/proxy/lmstudio/load` | **A** | `frontend/XR_Vessel/xr_app.py` — proxy_lmstudio_load |
| `GET /api/proxy/lmstudio/available` | **A** | `frontend/XR_Vessel/xr_app.py` — list_available_models |
| `GET /api/proxy/lmstudio/models` | **A** | `frontend/XR_Vessel/xr_app.py` — proxy_lmstudio_models |
| `GET /api/branding` | **A** | `frontend/XR_Vessel/xr_app.py` — proxy_branding |
| `POST /api/nav/push` | **A** | `frontend/XR_Vessel/xr_app.py` — proxy_nav_push |
| `GET /api/nav/pull` | **A** | `frontend/XR_Vessel/xr_app.py` — proxy_nav_pull |
| `POST /api/soul/lmstudio/hotswap` | **A** | `frontend/XR_Vessel/xr_app.py` — hotswap_lmstudio_model |
| `POST /api/soul/provider` | **A** | `frontend/XR_Vessel/xr_app.py` — set_soul_provider |
| `GET /api/soul/vitals` | **A** | `frontend/XR_Vessel/xr_app.py` — proxy_soul_vitals |
| `POST /api/proxy/soul/compagent` | **A** | `frontend/XR_Vessel/xr_app.py` — proxy_soul_compagent |
| `POST /api/cloud/chat` | **A** | `frontend/XR_Vessel/xr_app.py` — proxy_cloud_chat |
| `POST /api/soul/stt` | **A** | `frontend/XR_Vessel/xr_app.py` — proxy_soul_stt |
| `POST /api/soundboard/generate` | **A** | `frontend/XR_Vessel/xr_app.py` — generate_soundboard_sound |
| `GET /api/soundboard/health` | **A** | `frontend/XR_Vessel/xr_app.py` — proxy_soundboard_health |
| `GET /api/soundboard/context` | **A** | `frontend/XR_Vessel/xr_app.py` — get_soundboard_context |
| `GET /api/soundboard/list` | **A** | `frontend/XR_Vessel/xr_app.py` — list_soundboard_sounds |
| `GET /api/brain/diagnostic` | **A** | `frontend/XR_Vessel/xr_app.py` — brain_diagnostic |
| `POST /api/chat/provider` | **A** | `frontend/XR_Vessel/xr_app.py` — set_chat_provider |
| `GET /api/chat/provider` | **A** | `frontend/XR_Vessel/xr_app.py` — get_chat_provider |
| `POST /api/vessel/lms_settings` | **A** | `frontend/XR_Vessel/xr_app.py` — save_lms_settings |
| `GET /api/vessel/lms_settings` | **A** | `frontend/XR_Vessel/xr_app.py` — get_lms_settings |
| `POST /api/vessel/personas` | **A** | `frontend/XR_Vessel/xr_app.py` — save_personas |
| `GET /api/vessel/personas` | **A** | `frontend/XR_Vessel/xr_app.py` — get_personas |
| `POST /api/handshake` | **A** | `frontend/XR_Vessel/xr_app.py` — post_handshake |
| `POST /api/auth/logout` | **A** | `frontend/XR_Vessel/xr_app.py` — post_logout |
| `POST /api/auth/login` | **A** | `frontend/XR_Vessel/xr_app.py` — post_auth_login |
| `GET /api/auth/status` | **A** | `frontend/XR_Vessel/xr_app.py` — get_auth_status |
| `GET /monetize/ideas/plan` | **A** | `frontend/XR_Vessel/xr_app.py` — root_proxy_monetize_ideas_plan |
| `POST /monetize/ideas/certify` | **A** | `frontend/XR_Vessel/xr_app.py` — root_proxy_monetize_ideas_certify |
| `POST /monetize/ideas/scan` | **A** | `frontend/XR_Vessel/xr_app.py` — root_proxy_monetize_ideas_scan |
| `GET /monetize/ideas` | **A** | `frontend/XR_Vessel/xr_app.py` — root_proxy_monetize_ideas |
| `POST /monetize/remove_agent` | **A** | `frontend/XR_Vessel/xr_app.py` — root_proxy_monetize_remove_agent |
| `POST /monetize/add_agent` | **A** | `frontend/XR_Vessel/xr_app.py` — root_proxy_monetize_add_agent |
| `POST /monetize/control` | **A** | `frontend/XR_Vessel/xr_app.py` — root_proxy_monetize_control |
| `POST /monetize/treasury/config` | **A** | `frontend/XR_Vessel/xr_app.py` — root_proxy_monetize_treasury_config |
| `POST /monetize/config` | **A** | `frontend/XR_Vessel/xr_app.py` — root_proxy_monetize_config |
| `GET /monetize/status` | **A** | `frontend/XR_Vessel/xr_app.py` — root_proxy_monetize_status |
| `GET /api/monetize/ideas/plan` | **A** | `frontend/XR_Vessel/xr_app.py` — get_monetize_ideas_plan_proxy |
| `POST /api/monetize/ideas/certify` | **A** | `frontend/XR_Vessel/xr_app.py` — post_monetize_ideas_certify_proxy |
| `POST /api/monetize/ideas/scan` | **A** | `frontend/XR_Vessel/xr_app.py` — post_monetize_ideas_scan_proxy |
| `GET /api/monetize/ideas` | **A** | `frontend/XR_Vessel/xr_app.py` — get_monetize_ideas_proxy |
| `POST /api/monetize/remove_agent` | **A** | `frontend/XR_Vessel/xr_app.py` — post_monetize_remove_agent_proxy |
| `POST /api/monetize/add_agent` | **A** | `frontend/XR_Vessel/xr_app.py` — post_monetize_add_agent_proxy |
| `POST /api/monetize/control` | **A** | `frontend/XR_Vessel/xr_app.py` — post_monetize_control_proxy |
| `POST /api/monetize/treasury/config` | **A** | `frontend/XR_Vessel/xr_app.py` — post_monetize_treasury_config_proxy |
| `POST /api/monetize/config` | **A** | `frontend/XR_Vessel/xr_app.py` — post_monetize_config_proxy |
| `GET /api/monetize/status` | **A** | `frontend/XR_Vessel/xr_app.py` — get_monetize_status_proxy |
| `GET /api/soul/thought_stream` | **A** | `frontend/XR_Vessel/xr_app.py` — proxy_thought_stream |
| `POST /api/kokoro/tts` | **A** | `frontend/XR_Vessel/xr_app.py` — proxy_kokoro_tts |
| `POST /api/mouth/tts` | **A** | `frontend/XR_Vessel/xr_app.py` — proxy_mouth_tts |
| `GET /api/memory/restore/drive` | **A** | `frontend/XR_Vessel/xr_app.py` — memory_restore_drive |
| `POST /api/memory/backup/drive` | **A** | `frontend/XR_Vessel/xr_app.py` — memory_backup_drive |
| `GET /api/memory/status` | **A** | `frontend/XR_Vessel/xr_app.py` — memory_status |
| `POST /api/memory/restore` | **A** | `frontend/XR_Vessel/xr_app.py` — memory_restore_post |
| `POST /api/memory/import` | **A** | `frontend/XR_Vessel/xr_app.py` — memory_import |
| `POST /api/memory/add` | **A** | `frontend/XR_Vessel/xr_app.py` — memory_add |
| `GET /api/memory/context` | **A** | `frontend/XR_Vessel/xr_app.py` — memory_context |
| `POST /api/memory/search` | **A** | `frontend/XR_Vessel/xr_app.py` — memory_search |
| `POST /api/dev/cline_llm` | **A** | `frontend/XR_Vessel/xr_app.py` — cline_llm_proxy |
| `GET /api/dev/token_slayer/stats` | **A** | `frontend/XR_Vessel/xr_app.py` — token_slayer_stats |
| `POST /api/dev/cline` | **A** | `frontend/XR_Vessel/xr_app.py` — cline_tool_proxy |
| `GET /api/memory/restore` | **A** | `frontend/XR_Vessel/xr_app.py` — memory_restore |
| `POST /api/memory/backup` | **A** | `frontend/XR_Vessel/xr_app.py` — memory_backup |
| `GET /api/code/config` | **A** | `frontend/XR_Vessel/code_agency_routes.py` — code_config |
| `GET /api/code/git/status` | **A** | `frontend/XR_Vessel/code_agency_routes.py` — code_git_status |
| `POST /api/code/exec` | **A** | `frontend/XR_Vessel/code_agency_routes.py` — code_exec |
| `GET /api/code/search` | **A** | `frontend/XR_Vessel/code_agency_routes.py` — code_search |
| `POST /api/code/edit` | **A** | `frontend/XR_Vessel/code_agency_routes.py` — code_edit |
| `POST /api/code/write` | **A** | `frontend/XR_Vessel/code_agency_routes.py` — code_write |
| `GET /api/code/read` | **A** | `frontend/XR_Vessel/code_agency_routes.py` — code_read |
| `GET /api/code/ls` | **A** | `frontend/XR_Vessel/code_agency_routes.py` — code_ls |
| `PUT /tts/backend` | **A** | `frontend/Physical_Interface/body_interface.py` — put_tts_backend |
| `GET /tts/backend` | **A** | `frontend/Physical_Interface/body_interface.py` — get_tts_backend |
| `POST /tts` | **A** | `frontend/Physical_Interface/body_interface.py` — handle_tts |
| `POST /stt` | **A** | `frontend/Physical_Interface/body_interface.py` — handle_stt |
| `TTSBody` | **A** | `frontend/Mouth/lumax_mouth_kokoro_server.py` — TTSBody |
| `POST /synthesize` | **A** | `frontend/Mouth/lumax_mouth_kokoro_server.py` — synthesize |
| `GET /voices` | **A** | `frontend/Mouth/lumax_mouth_kokoro_server.py` — voices |
| `docker-compose.yml` default **Awake lean** (soul, ears, mouth, memory) | **A** | Profiles **lumax-desk-extras** (ops+Ollama), **lumax-sleep-embers** (embers), **creativity**/**creative**; VR-lite / VR-bare / **state-creative** merges optional |
| `lumax_soul` — `compagent` + GGUF / local LLM | **A** | Bind mount `LUMAX_REPO_ROOT` → `/app`; models under `/app/models` |
| `lumax_ears` — STT :8001 + TTS :8002 (F5 + Piper) | **A** | Depends on healthy `lumax_mouth_emotion` for default F5-TTS |
| `lumax_mouth_emotion` — F5-TTS Emotion-CFG HTTP :8780 | **B** | Checkpoints on host (`LUMAX_F5_EMOTION_CKPT_DIR` → `/ckpts`); `Scripts/lumax_mouth_emotion_server.py` |
| `lumax_mouth` — F5-TTS Gradio SWivid :7860 | **C** | Profile `swivid-mouth`; use when `LUMAX_F5TTS_ENGINE=swivid` |
| `lumax_mouth_spark` — Spark-TTS 0.5B HTTP :8810 | **C** | Profile `spark-mouth`; `LUMAX_F5TTS_ENGINE=spark`; mount `SparkAudio/Spark-TTS-0.5B` at `LUMAX_SPARK_MODEL_DIR` |
| `lumax_ops` — Web UI :8080 + AutonomousSentry | **A** | `LUMAX_WEBUI_PASSWORD`; Docker socket for heal |
| `lumax_memory` — Redis | **A** | Soul / embers use `REDIS_HOST` |
| `lumax_ollama_backup` — Ollama :11434 | **A** | Embeds, helpers, sentry solver; not always main chat path |
| `lumax_embers` — idle / slow-burn | **B** | Profile **lumax-sleep-embers** (off in default Awake/LIVE lean) |
| Compose profiles (`lumax-desk-extras`, `lumax-sleep-embers`, `creativity`/`creative`, `agent`) | **C** | Desk utilities, embers, `lumax_creativity`, `lumax_agent` optional |

---

## 2. Unified XR Vessel (The Sovereign Interface)

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `SessionImporter` | **A** | `backend/Memory/session_importer.py` — SessionImporter |
| `POST /consolidate` | **A** | `backend/Memory/memory_service.py` — api_consolidate |
| `GET /history/{session_id}` | **A** | `backend/Memory/memory_service.py` — api_history |
| `POST /search` | **A** | `backend/Memory/memory_service.py` — api_search |
| `POST /store` | **A** | `backend/Memory/memory_service.py` — api_store |
| `MemoryServer` | **A** | `backend/Memory/lumax_mcp_server.py` — MemoryServer |
| `LocalLLM` | **A** | `backend/Memory/lumax_mcp_server.py` — LocalLLM |
| `ProjectContext` | **A** | `backend/Cognition/soul_coder_chat.py` — ProjectContext |
| `POST /api/history/clear` | **A** | `backend/Cognition/soul_coder_chat.py` — clear_history |
| `GET /api/history` | **A** | `backend/Cognition/soul_coder_chat.py` — get_history |
| `SoulCoderState` | **A** | `backend/Cognition/soul_coder_api.py` — SoulCoderState |
| `POST /api/production-mode` | **A** | `backend/Cognition/soul_coder_api.py` — production_mode |
| `POST /api/test-mode` | **A** | `backend/Cognition/soul_coder_api.py` — test_mode |
| `POST /api/switch-model` | **A** | `backend/Cognition/soul_coder_api.py` — switch_model |
| `POST /api/resume` | **A** | `backend/Cognition/soul_coder_api.py` — resume_model |
| `POST /api/pause` | **A** | `backend/Cognition/soul_coder_api.py` — pause_model |
| `GET /api/status` | **A** | `backend/Cognition/soul_coder_api.py` — get_status |
| `GET /health` | **A** | `backend/Cognition/soul_coder_api.py` — health_check |
| `VectorMemory` | **A** | `backend/Cognition/memory.py` — VectorMemory |
| `RedisMemory` | **A** | `backend/Cognition/memory.py` — RedisMemory |
| `ChatHistory` | **A** | `backend/Cognition/memory.py` — ChatHistory |
| `ChatMessage` | **A** | `backend/Cognition/memory.py` — ChatMessage |
| `POST /api/generate` | **A** | `backend/Cognition/compagent.py` — handle_ollama_generate |
| `GET /api/tags` | **A** | `backend/Cognition/compagent.py` — handle_ollama_tags |
| `POST /soul_runtime_config` | **A** | `backend/Cognition/compagent.py` — handle_soul_runtime_config |
| `GET /soul_runtime_status` | **A** | `backend/Cognition/compagent.py` — soul_runtime_status |
| `GET /api/models/inventory` | **A** | `backend/Cognition/compagent.py` — get_models_inventory |
| `GET /soul_dna` | **A** | `backend/Cognition/compagent.py` — get_soul_dna |
| `GET /api/version` | **A** | `backend/Cognition/compagent.py` — handle_ollama_version |
| `GET /api/ps` | **A** | `backend/Cognition/compagent.py` — handle_ollama_ps |
| `POST /memory/embed` | **A** | `backend/Cognition/compagent.py` — memory_embed |
| `GET /memory/notes` | **A** | `backend/Cognition/compagent.py` — memory_get_notes |
| `POST /memory/note` | **A** | `backend/Cognition/compagent.py` — memory_add_note |
| `GET /api/thought_stream` | **A** | `backend/Cognition/compagent.py` — handle_thought_stream |
| Unified Web Server `frontend/XR_Vessel/xr_app.py` | **A** | Authoritative OMEGA_085 entry point; proxies Soul, Memory, and Vite dev server |
| Integrated WebUI Root `/` | **A** | Serves the browser-centric XR Vessel interface by default (proxies to :5176 or serves :8080 build) |
| Feature Map tab — this file via `/api/fmap` | **A** | `FEATURE_INVENTORY.md` at repo root parsed by `xr_app.py` |
| Branding / `lumax_ui_config` | **B** | `GET /api/ui_config`, nav labels in `frontend/XR_Vessel` |
| Clinical Dashboard `frontend/XR_Vessel/src/components/Dashboard.ts` | **A** | Live PC vitals, navigation, and API bridge |
| Diagnostic Matrix `frontend/XR_Vessel/src/components/DiagnosisTab.ts` | **A** | 40x14 clinical matrix with dynamic Cross-Hair Highlighting and sticky headers |
| Self-Assessment & Auto-Mirror | **A** | Distraction-free survey modal; allows users to let JEN auto-mirror their psychiatric profile |

---

## 3. Backend (Mind / soul)

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `backend/Cognition/compagent.py` — `/compagent` | **A** | Main chat, streaming optional |
| `backend/Cognition/lumax_engine.py` — GGUF, adaptive `n_ctx` | **A** | `LUMAX_LOCAL_N_CTX`, `LUMAX_GGUF_CHAT_TEMPLATE_PATH`, thinking strip |
| `backend/Cognition/MindCore.py` — `clean_response`, thought / emotion | **A** | Qwen `<redacted_thinking>` → JSON `thought` |
| `backend/Cognition/memory.py` — Redis + Chroma | **B** | `chromadb`, `ollama` embed client |
| Optional Cognee / cloud repertoire | **C** | Env-gated |

---

## 4. Godot / VR

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `frontend/XR_Vessel` — OpenXR / Nexus | **B** | Godot project path varies per checkout |
| `Synapse.gd` — soul HTTP, `response_received` | **A** | `thought` + `text` for VR UI |
| `backend/WebUI.gd` — in-world panels | **B** | SubViewport / tactile keyboard |
| Native HTML chat `backend/Web/chat.html` | **C** | Optional wrist / debug HTML |

---

## 5. Mobile

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `frontend/Mobile_Vessel` | **C** | Capacitor / Vite stack — verify active branch |
| Shared `lumax_ui_config` for mobile section | **C** | Same JSON schema as web where wired |

---

## 6. Tests

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `POST /v1/chat/completions` | **B** | `Forge/proxy_server.py` — chat_completions |
| `MemoryVault` | **B** | `Forge/memory_vault.py` — MemoryVault |
| `ForgeCore` | **B** | `Forge/forge_core.py` — ForgeCore |
| `ForgeStatus` | **B** | `Forge/forge_api.py` — ForgeStatus |
| `SessionStatus` | **B** | `Forge/forge_api.py` — SessionStatus |
| `GET /memory/nodes/{node_id}/expand` | **B** | `Forge/forge_api.py` — expand_memory_node |
| `GET /memory/nodes/active` | **B** | `Forge/forge_api.py` — get_active_memory_nodes |
| `POST /api/librarian/map` | **B** | `Forge/forge_api.py` — trigger_map |
| `POST /api/librarian/prune` | **B** | `Forge/forge_api.py` — trigger_prune |
| `POST /checkpoint` | **B** | `Forge/forge_api.py` — create_checkpoint |
| `GET /api/sessions/{session_id}/status` | **B** | `Forge/forge_api.py` — get_session_status |
| `GET /api/sessions/{session_id}/events` | **B** | `Forge/forge_api.py` — get_session_events |
| `POST /api/sessions/{session_id}/prompt` | **B** | `Forge/forge_api.py` — send_prompt |
| `POST /api/sessions/{session_id}/stop` | **B** | `Forge/forge_api.py` — stop_session |
| `POST /api/sessions/spawn` | **B** | `Forge/forge_api.py` — spawn_session |
| `GET /api/sessions` | **B** | `Forge/forge_api.py` — list_sessions |
| `Scripts/AUTOTEST*.ps1`, `testrun_docker.ps1` | **B** | Local / CI smoke |
| `frontend/XR_Vessel/scripts/diagnostic/*` | **C** | Godot integrity helpers |

---

## 7. Ops & scripts

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `frontend/Immune/autonomous_sentry.py` | **A** | Preflight, heal, outbox |
| `Scripts/Start_Lumax_VR.ps1` | **B** | Phased compose + VR merges; script map **`Scripts/README.md`** |
| `Scripts/f5_tts_gradio_launch.py` | **B** | Mouth image CMD |
| `backend/preflight/*` | **B** | Checks, agentic solver |

---

## 8. Cross-surface

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| Env parity: `.env` + `env.vr.example` | **A** | `LUMAX_REPO_ROOT`, `LUMAX_MODELS_ROOT`, soul URLs |
| TTS: F5 primary, Piper fallback | **A** | `LUMAX_F5TTS_URL`, `LUMAX_F5TTS_REF_AUDIO`, `handle_file()` for Gradio 5 |
| STT → soul → TTS pipeline | **A** | Web UI diagnostics path |

---

## 9. Windows Service & Tray

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `Service/LumaxService.ps1` — NSSM background runner | **A** | Auto-start on boot; SLEEP/AWAKE lifecycle; watchdogs all services |
| `Service/LumaxTray.ps1` — System tray widget | **A** | Colored dot (red/green/amber); toggle ON/OFF; balloon tips for wake ritual; stale-state auto-heal |
| `Service/LumaxGuardian.ps1` — Autonomous watchdog & healer | **A** | 4-layer resilience: service registration, running check, port health, tray respawn; survives Windows Updates |
| Guardian: NSSM auto-reinstall | **A** | Downloads NSSM if missing; re-registers service after Windows Update removal |
| Guardian: Port health check & restart | **A** | Tests ports 8000/8001/8002/8004/8080; restarts service if ports dead |
| Guardian: Proactive zombie kill (`Clear-ZombiePorts`) | **A** | Kills orphaned Python processes holding LUMAX ports before spawn |
| Guardian: Orphaned Python hunter (`Clear-OrphanedPython`) | **A** | Detects Python processes without NSSM parent service and terminates |
| Guardian: Diff-based incremental backup | **A** | SHA256 hash scan every 5 min; only changed `.py`/`.ps1`/`.json`/`.md`/`.html`/`.env`/`.gd` files copied |
| Guardian: Daily full ZIP backup | **A** | Complete snapshot once daily if changes detected; auto-sync to cloud |
| Guardian: Cloud sync (OneDrive / Google Drive) | **A** | Auto-detects cloud paths; copies backups to user's own account |
| Guardian: Backup pruning | **B** | Incrementals kept 7 days, full zips 30 days |
| Discovery Swarm — self-discovery system | **A** | `backend/Cognition/discovery_swarm.py` — Mapper + Archivist + Auditor drones scan codebase |
| Discovery Swarm: Mapper drone | **A** | Scans `.py`/`.ps1`/`.yml`/`.md`/`.gd` for endpoints, classes, functions, services, TODOs |
| Discovery Swarm: Archivist drone | **A** | Cross-references inventory structure; finds empty categories and orphaned file refs |
| Discovery Swarm: Auditor drone | **A** | Audits `.env`, `requirements*.txt`, configs not referenced in inventory |
| Discovery Swarm: Director Manager | **A** | Synthesizes drone reports into `DirectorProposal` with category/tier guesses |
| Discovery Swarm: Report persistence | **A** | JSON reports saved to `.logs/discovery_reports/` with SHA timestamp |
| Discovery Swarm: Web UI notification inbox | **A** | Banner inbox shows discovery findings; one-click launch from UI |
| Discovery Swarm: REST API | **A** | `POST /api/discovery/launch`, `GET /api/discovery/state`, `GET /api/discovery/notification` |
| Service + Console coexistence | **A** | Console adopts service PIDs from `lumax_service_status.json` — no duplicates |
| Wake ritual on SLEEP→AWAKE | **B** | LLM-generated unique greeting via `/compagent`; sleep duration + time-of-day context |
| Startup CRASH detection with grace period | **B** | 8-second grace period + immediate-exit detection + log-tail reading in `Start_LUMAX.ps1` |
| `Service/Install_Lumax_Service.ps1` — NSSM installer | **A** | Downloads NSSM if missing; registers `LumaxService`; adds tray to Startup; installs Guardian scheduled task |
| `Service/Uninstall_Lumax_Service.ps1` — Service remover | **A** | `-KeepData` switch preserves `.venv`, config, tokens, logs; removes Guardian task |
| `Service/lumax_service_config.json` — Avatar config | **B** | `AvatarName`, `AutoWake`, `SleepTimeoutSec`, `WakeOnVoice`, `EnableVad` |

---

## 10. Memory & Consent Data

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `backend/Memory/memory_service.py` — MEMORY service (:8002) | **A** | FastAPI; Redis session cache + ChromaDB vector ANN + Kuzu graph traversal |
| Consent endpoints in `xr_app.py` (:8080) | **A** | `/api/consent/google/*`, `/api/consent/microsoft/*` — no separate server |
| `frontend/ConsentBridge/google_oauth.py` — Google OAuth | **B** | Read-only scopes: Gmail, Calendar, Contacts, Profile |
| `frontend/ConsentBridge/ms_oauth.py` — Microsoft OAuth | **B** | Read-only scopes: User.Read, Contacts.Read, Calendars.Read, Mail.ReadBasic |
| Local token storage | **A** | `.cache/google_tokens.json`, `.cache/ms_tokens.json` — never leaves machine |
| Consent data sync to MEMORY | **A** | Profile, contacts, calendar events, email metadata → graph nodes at :8002 |

---

## 11. Install / Uninstall Infrastructure

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| `Install.ps1` — Unified Windows installer (v2.0) | **A** | `.venv` + dependencies + service + tray + PATH in one command |
| `Uninstall.ps1` — Reversible uninstall | **A** | `-KeepData` preserves `.venv`, config, tokens, memories, logs for fast iteration |
| `Service/Register_Global_Lumax.ps1` — PATH registration | **B** | Adds repo root to system PATH so `lumax` works from any directory |
| `Service/Unregister_Global_Lumax.ps1` — PATH cleanup | **B** | Removes repo root from system PATH |
| System audit on install | **B** | CPU, RAM, GPU detection; warns if <16GB RAM |

---

## 12. Gaps & next steps

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| Restore historical rows if found | **D** | Older `FEATURE_INVENTORY.md` may exist on another clone / backup |
| Streaming chat UX | **C** | Non-stream default; optional NDJSON |
| VR "thought" overlay / toasts | **C** | Parity with Web UI toasts when enabled |
| Memory graph visualization | **C** | Kuzu graph explorer in WebUI |
| Consent data scheduling (auto-sync) | **C** | Periodic refresh of Google/Microsoft data without manual trigger |
| Backup encryption at rest | **C** | Optional password-protected ZIP for sensitive `.env`/tokens |
| Backup web UI restore panel | **C** | One-click restore from incremental or full backup in WebUI |

---

## 14. Architecture Map

| Artifact / diagram | Tier | Notes |
| --- | --- | --- |
| `ARCHITECTURE.md` — System topology | **A** | 7 Mermaid diagrams: service graph, dependencies, data flow, profile matrix, state machine, dashboard layout, file map |
| High-level backend/frontend/Service topology | **A** | `graph TB` — User → Tray/Console → SVC → Mind + Body + Storage |
| Service dependency graph | **A** | `graph LR` — Core vs Optional vs External layers |
| Data flow: conversation turn | **A** | `sequenceDiagram` — User → EARS → SOUL → MEMORY → MOUTH |
| Service profile matrix | **A** | Table: which services run in AWAKE/LIVE/SLEEP/CODE/CREATIVE |
| State machine: life cycle | **A** | `stateDiagram-v2` — LOADING → AWAKE → LIVE/SLEEP/CRASH |
| Console dashboard layout | **B** | `block-beta` — Service blocks, meters, controls |
| File organization map | **B** | `graph TD` — Root → backend/frontend/Service/Scripts/Tools/Forge |
| Mermaid rendering | **A** | Native in GitHub, GitLab, VS Code Mermaid extension |

---

## 15. Troubleshooter Crew

> Component definitions for the "librarian" — high-resolution role assignments.

| Agent / role | Responsibility | Signal / trigger | Files |
| --- | --- | --- | --- |
| **Service Watchdog** | Monitor service health, restart crashed processes | Any service PID exits unexpectedly | `Service/LumaxService.ps1`, `frontend/Immune/autonomous_sentry.py` |
| **Port Scout** | Detect port conflicts, zombie Python processes | Console shows "none running" or adoption fails | `Start_LUMAX.ps1` adoption logic |
| **Syntax Sentinel** | Catch PowerShell backtick-in-string, Python syntax | Install fails, service won't start | `Install.ps1`, `Start_LUMAX.ps1` |
| **Env Curator** | Validate `.env` + `lumax_service_config.json` coherence | Missing vars, wrong paths | `.env`, `Service/lumax_service_config.json` |
| **Venv Steward** | Ensure `.venv` exists, dependencies current, no conflicts | Import errors on startup | `Install.ps1`, `requirements_lumax.txt` |
| **OAuth Gatekeeper** | Manage consent tokens, refresh, revoke | User clicks "Connect Google/Microsoft" | `frontend/ConsentBridge/*.py`, `.cache/` |
| **Memory Archivist** | Consolidate session history, vector embeddings, graph nodes | Night sleep consolidation or manual sync | `backend/Memory/memory_service.py`, `backend/Memory/*.db` |
| **Dashboard Cartographer** | Keep ARCHITECTURE.md and FEATURE_INVENTORY.md in sync | New service added, port changed, state added | `ARCHITECTURE.md`, `FEATURE_INVENTORY.md` |
| **State Mechanic** | Verify SLEEP/AWAKE/LIVE/CODE/CREATIVE transitions | Wrong services running, tray state mismatch | `Start_LUMAX.ps1` `Update-State`, `LumaxService.ps1` |
| **Log Archaeologist** | Parse `.logs/` for crash signatures, startup errors | Service crash-loop, WEBUI exits immediately | `.logs/*_err.log`, `lumax_service.log` |
| **NSSM Shepherd** | Windows service install/uninstall, PATH registry | Service not starting after reboot | `Service/Install_Lumax_Service.ps1`, `Service/Uninstall_Lumax_Service.ps1` |
| **Docker Bosun** | Container health, compose profiles, image builds | Docker stack not starting, port conflicts | `docker-compose*.yml`, `Scripts/docker_vr_lite_up.ps1` |
| **Godot Rigger** | VR vessel build, Oculus manifest, ADB push | XR build fails, Quest not connecting | `frontend/XR_Vessel/`, `Scripts/Clean_and_Rebuild_XR.ps1` |
| **TTS Dispatcher** | Route TTS requests to correct engine (Turbo/Piper/F5/Spark/VoxCPM) | Voice not playing, wrong voice, timeout | `frontend/Physical_Interface/turbochat_server.py`, `backend/Cognition/compagent.py` |
| **STT Listener** | Verify Silero VAD + Whisper pipeline | No transcription, VAD not triggering | `frontend/Physical_Interface/body_interface.py`, `frontend/CON_vessel/vad_bridge.py` |
| **Soul Therapist** | Diagnose LLM inference failures (GGUF load, context overflow, cloud fallback) | Soul responds with errors, uses CPU only, crashes | `backend/Cognition/compagent.py`, `backend/Cognition/lumax_engine.py` |
| **Creative Smith** | Image generation pipeline, Spandrel upscale, dream catharsis | Dream images fail, creativity service offline | `backend/Creativity/creative_service.py` |
| **Network Weaver** | Quest LAN, ADB reverse, port forwarding, firewall | Quest cannot reach soul, timeout on headset | `Scripts/connect_quest.ps1`, `frontend/Immune/autonomous_sentry.py` |
| **Crew Dispatcher** | Spawn and coordinate troubleshooters, collect reports | User reports "something is wrong" | `ARCHITECTURE.md` section 15, `FEATURE_INVENTORY.md` |

---

## 13. Meta

| Feature / capability | Tier | Notes |
| --- | --- | --- |
| This file — edit in repo root | **A** | Override path: `LUMAX_FEATURE_INVENTORY_PATH` |
| Parser `feature_inventory_parser.py` | **A** | Tables under `## N.` headings; tier markers `**A**` in cells |
| `.dockerignore` — does not exclude this file | **A** | Must exist on host for bind-mounted `/app` |
