# FoveAI Micro-Principia
*2026-10-11 13:07 | Tier: micro | .xrl-ignore active*

## Tree
  Backend/Cognition/
  Backend/Memory/
  Backend/Creativity/
  Backend/Monetizing/
  Backend/preflight/
  Frontend/multigate/src/
  Frontend/XR_Vessel/src/
  Frontend/Copilot/src/
  Frontend/Mouth/
  theme/
  foveated-memory/core/
  Scripts/
  Tools/
  Docs/
  Plans/
  tests/

## Ports
Proxy/Memory:8400 | XRLF:8402 | Soul/Compagent:8405 | TTS:8406 | ChatRelay:8407 | STT:8409 | Motor:8410 | Subconscious:8411 | Multigate:5177

## Files
  Backend/Cognition/compagent.py (8405) — Check chain and return first healthy endpoint.
  Backend/Cognition/MindCore.py — Drop lines that mimic chat history (User:/Jen:/Daniel:), which models often paste into replies.
  Backend/Cognition/MindCore/MindCore.py — Drop lines that mimic chat history (User:/Jen:/Daniel:), which models often paste into replies.
  Backend/Cognition/autonomous_core.py — Autonomous Core — Jen's Independent Runtime Service.
  Backend/Cognition/persistent_memory.py — Persistent Agent Memory — SQLite-backed memory that survives across sessions and turns.
  Backend/Cognition/soul_core.py (8405) — Find a free port starting from `start`.
  Backend/Cognition/tokenslayer_proxy_server.py (8200) — Load the atomic hash → signature mapping.
  Backend/Cognition/motor_cortex.py — Returns the OpenAI-compatible JSON schema for Jen's physical motor tools.
  Backend/Cognition/intelligent_router.py — Intelligent Router — Real-Time Local/Cloud Decision Engine
  Backend/Cognition/autonomous_agent.py (8410) — Autonomous Agent Loop — Jen's continuous runtime for true freedom.
  Backend/Cognition/swarm_orchestrator.py — Swarm Orchestrator — Tiered Multi-Agent Problem Solver with Director Manager.
  Backend/Cognition/memory.py — CREATE TABLE IF NOT EXISTS agent_chat_history (
  Backend/Cognition/ag_coder.py — Load keys from .env directly
  Backend/Cognition/visualize_architecture.py — Points to stable-diffusion-v1-5
  Backend/Cognition/visualize_relay.py — ── 1. DRAW THE RELAY TOPOLOGY (CANNY TEMPLATE) ──────────────────────────────
  Backend/Memory/memory_service.py (8413) — Night-time consolidation: Kuzu graph layer deprecated.
  Backend/Memory/foveai_mcp_server.py (8413) — FoveAI Memory MCP Server v3.0 - Local LLM Middleman Edition
  Backend/Memory/smart_context.py (8104) — Leverages the Stardust Gnists to query the repository layout,
  Backend/Memory/import_foveai_sessions.py — Import FoveAI sessions from backend/Cognition/sessions.json to MCP memory
  Backend/Memory/quantum_neuron.py — Simulates a phase-aware quantum neuron using complex-valued weight matrices.
  Backend/Memory/session_importer.py — FoveAI Session Importer & Summarizer
  Backend/Memory/stardust_encoder.py — Transforms raw text intent into an isolated coordinate vector.
  Backend/Creativity/creative_service.py (8412) — Return 'cuda' if CUDA is available and compiled, else 'cpu'.
  Backend/Creativity/invokeai_catalog_bridge.py — Merge InvokeAI-style inventory (CSV export) into Lumax dream catalog entries.
  Backend/Creativity/spandrel_upscale.py — Spandrel-based super-resolution for Dreamscape enhance mode (InvokeAI-compatible checkpoints).
  Backend/Creativity/start_creative_with_env.py — Start the creative service with environment variables loaded from .env file.
  Backend/Monetizing/agent_core.py — FoveAI Monetizing Agent Core
  Backend/Monetizing/coinex_integration.py — FoveAI CoinEx Integration Module (V2)
  Backend/Monetizing/treasury_manager.py — FoveAI Monetizing Treasury Manager
  Backend/Monetizing/agent_bookkeeper.py — Initializes or reads the persistent netbooking sheet.
  Backend/Monetizing/idea_engine.py — FoveAI Monetizing Idea Engine
  Backend/Monetizing/machine_state.py — FoveAI Monetizing Machine State Monitor
  Backend/Monetizing/mentor_analyzer.py — LLM Mentor Analyzer - Cloud-based trading review
  Backend/Monetizing/migrate_to_sqlite.py — FoveAI Monetizing — JSON to SQLite Migration
  Backend/Monetizing/monetizing_db.py — FoveAI Monetizing Database — SQLite persistence layer
  Backend/Monetizing/paper_trading_engine.py — FoveAI Paper Trading Engine — Swarm Training with Golden Cross Strategy
  Backend/Monetizing/run_monetizing_system.py — FoveAI Monetizing System Runner
  Backend/Monetizing/security.py — FoveAI Monetizing Security Module
  Backend/Monetizing/test_real_trading.py — Add parent directory to path for imports
  Backend/preflight/agentic_solver.py — Load Mind/Cognition/cloud_repertoire.py without package imports (sentry cwd is Backend/).
  Backend/preflight/checks.py — Active mouth stack: turbo or chatterbox.
  Backend/preflight/json_util.py — Human-edited playbook files (watchdog policy, unstable features, etc.).

## Connections
  soul_core.py (8405) → ? (7272)
  soul_core.py (8405) → ? (8888)
  soul_core.py (8405) → ? (11434)
  ghost_brain.py (?) → server.js (8400)
  generate_middleman_dataset.py (?) → server.js (8400)
  generate_middleman_dataset.py (?) → server.js (8400)

## Routes
  `/` → Backend/Cognition/compagent.py
  `/actions` → Backend/Cognition/autonomous_core.py
  `/api/agent/actions` → Backend/Cognition/compagent.py
  `/api/agent/activity` → Backend/Cognition/compagent.py
  `/api/agent/context` → Backend/Cognition/compagent.py
  `/api/agent/goals/active` → Backend/Cognition/compagent.py
  `/api/agent/goals/{goal_id}/abandon` → Backend/Cognition/compagent.py
  `/api/agent/goals/{goal_id}/complete` → Backend/Cognition/compagent.py
  `/api/agent/goals/{goal_id}/progress` → Backend/Cognition/compagent.py
  `/api/agent/goals/{goal_id}` → Backend/Cognition/compagent.py
  `/api/agent/goals` → Backend/Cognition/compagent.py
  `/api/agent/goals` → Backend/Cognition/compagent.py
  `/api/agent/journal` → Backend/Cognition/compagent.py
  `/api/agent/memory/{key}` → Backend/Cognition/compagent.py
  `/api/agent/memory` → Backend/Cognition/compagent.py
  `/api/agent/message` → Backend/Cognition/compagent.py
  `/api/agent/messages/mark` → Backend/Cognition/compagent.py
  `/api/agent/messages` → Backend/Cognition/compagent.py
  `/api/agent/plan/{plan_id}` → Backend/Cognition/compagent.py
  `/api/agent/plan` → Backend/Cognition/compagent.py
  `/api/agent/plans` → Backend/Cognition/compagent.py
  `/api/agent/queue/stats` → Backend/Cognition/compagent.py
  `/api/agent/start` → Backend/Cognition/compagent.py
  `/api/agent/status` → Backend/Cognition/compagent.py
  `/api/agent/stop` → Backend/Cognition/compagent.py
  `/api/agent/thoughts` → Backend/Cognition/compagent.py
  `/api/avatar/camera` → Backend/Cognition/soul_core.py
  `/api/camera/stream` → api/server.py
  `/api/chat/provider` → Backend/Cognition/soul_core.py
  `/api/chat/provider` → Backend/Cognition/soul_core.py
  `/api/chat` → Backend/Cognition/compagent.py
  `/api/chat` → Backend/Cognition/soul_core.py
  `/api/controllers/mapping/reset` → Backend/Cognition/soul_core.py
  `/api/controllers/mapping` → Backend/Cognition/soul_core.py
  `/api/controllers/mapping` → Backend/Cognition/soul_core.py
  `/api/controllers/status` → Backend/Cognition/soul_core.py
  `/api/dream/catalog` → Backend/Creativity/creative_service.py
  `/api/dream` → Backend/Creativity/creative_service.py
  `/api/environment/config` → Backend/Cognition/soul_core.py
  `/api/environment/plaster_texture/{direction}` → Backend/Cognition/compagent.py
  `/api/environment/plaster_texture` → Backend/Cognition/compagent.py
  `/api/environment/plaster_texture` → Backend/Cognition/compagent.py
  `/api/environment/plaster_texture` → api/server.py
  `/api/environment/preset` → Backend/Cognition/soul_core.py
  `/api/environment/reset` → Backend/Cognition/soul_core.py
  `/api/environment/settings` → Backend/Cognition/soul_core.py
  `/api/environment/status` → Backend/Cognition/soul_core.py
  `/api/expand/{filepath:path}` → Backend/Cognition/tokenslayer_proxy_server.py
  `/api/expand` → Backend/Cognition/tokenslayer_proxy_server.py
  `/api/generate` → Backend/Cognition/compagent.py
  `/api/health` → Backend/Creativity/creative_service.py
  `/api/health` → api/server.py
  `/api/models/inventory` → Backend/Cognition/compagent.py
  `/api/nav/pull` → Backend/Cognition/compagent.py
  `/api/nav/push` → Backend/Cognition/compagent.py
  `/api/preheat` → Backend/Creativity/creative_service.py
  `/api/presence/heartbeat` → Backend/Cognition/compagent.py
  `/api/ps` → Backend/Cognition/compagent.py
  `/api/router/decide` → Backend/Cognition/soul_core.py
  `/api/router/status` → Backend/Cognition/soul_core.py
  `/api/semantic-summary` → Backend/Cognition/tokenslayer_proxy_server.py
  `/api/skeletonize` → Backend/Cognition/tokenslayer_proxy_server.py
  `/api/soul/cognitive-state` → Backend/Cognition/soul_core.py
  `/api/soul/cognitive-state` → Backend/Cognition/soul_core.py
  `/api/soul/director/plans/{name}` → Backend/Cognition/compagent.py
  `/api/soul/env` → Backend/Cognition/soul_core.py
  `/api/soul/env` → Backend/Cognition/soul_core.py
  `/api/soul/kiosk/apps/{owner}/{app}/file` → Backend/Cognition/compagent.py
  `/api/soul/kiosk/apps/{owner}/{app}/file` → Backend/Cognition/compagent.py
  `/api/soul/kiosk/apps` → Backend/Cognition/compagent.py
  `/api/soul/kiosk/apps` → Backend/Cognition/compagent.py
  `/api/soul/kiosk/assist` → Backend/Cognition/compagent.py
  `/api/soul/kiosk/build` → Backend/Cognition/compagent.py
  `/api/soul/kiosk/download/{owner}/{app}/{artifact}` → Backend/Cognition/compagent.py
  `/api/soul/kiosk/targets` → Backend/Cognition/compagent.py
  `/api/soul/kiosk/templates` → Backend/Cognition/compagent.py
  `/api/soul/personality_presets` → Backend/Cognition/compagent.py
  `/api/soul/personality` → Backend/Cognition/soul_core.py
  `/api/soul/softlayer/assist` → Backend/Cognition/compagent.py
  `/api/soul/softlayer/modules/{name}` → Backend/Cognition/compagent.py
  `/api/soul/softlayer/modules/{name}` → Backend/Cognition/compagent.py
  `/api/soul/softlayer/modules` → Backend/Cognition/compagent.py
  `/api/soul/soul_dna` → Backend/Cognition/compagent.py
  `/api/soul/tasks/{plan_id}/approve` → Backend/Cognition/compagent.py
  `/api/soul/tasks/{plan_id}/context` → Backend/Cognition/compagent.py
  `/api/soul/tasks/{plan_id}/reject` → Backend/Cognition/compagent.py
  `/api/soul/tasks` → Backend/Cognition/compagent.py
  `/api/soul/tasks` → Backend/Cognition/compagent.py
  `/api/soul/update_soul` → Backend/Cognition/compagent.py
  `/api/soul/vitals` → Backend/Cognition/soul_core.py
  `/api/soul/webvm/{path:path}` → Backend/Cognition/compagent.py
  `/api/soundboard/context` → Backend/Cognition/compagent.py
  `/api/spatial/map/reset` → Backend/Cognition/soul_core.py
  `/api/spatial/scan/start` → Backend/Cognition/soul_core.py
  `/api/spatial/scan/stop` → Backend/Cognition/soul_core.py
  `/api/spatial/status` → Backend/Cognition/soul_core.py
  `/api/state/switch` → Backend/Creativity/creative_service.py
  `/api/status/overview` → Backend/Cognition/soul_core.py
  `/api/system/probe` → Backend/Cognition/soul_core.py
  `/api/system/status` → Backend/Cognition/soul_core.py
  `/api/system/summary` → Backend/Cognition/soul_core.py
  `/api/tags` → Backend/Cognition/compagent.py
  `/api/theme/active` → theme/theme_api.py
  `/api/theme/generate` → theme/theme_api.py
  `/api/theme/set_active` → theme/theme_api.py
  `/api/themes` → theme/theme_api.py
  `/api/thought_stream` → Backend/Cognition/compagent.py
  `/api/tier-info` → Backend/Cognition/tokenslayer_proxy_server.py
  `/api/upscale/display` → Backend/Creativity/creative_service.py
  `/api/version` → Backend/Cognition/compagent.py
  `/api/vision/status` → Backend/Cognition/soul_core.py
  `/api/xrl/expand` → Backend/Cognition/tokenslayer_proxy_server.py
  `/api/xrl/prune` → Backend/Cognition/tokenslayer_proxy_server.py
  `/api/xrl/resolve` → Backend/Cognition/tokenslayer_proxy_server.py
  `/api/xrl/status` → Backend/Cognition/tokenslayer_proxy_server.py
  `/avatar_profile` → Backend/Cognition/compagent.py
  `/avatar_profile` → Backend/Cognition/compagent.py
  `/compagent/stream` → Backend/Cognition/compagent.py
  `/compagent/stream` → Backend/Cognition/soul_core.py
  `/compagent` → Backend/Cognition/compagent.py
  `/compagent` → Backend/Cognition/soul_core.py
  `/consolidate` → Backend/Memory/memory_service.py
  `/context/holographic_slice` → Backend/Memory/smart_context.py
  `/context` → Backend/Cognition/autonomous_core.py
  `/control/start` → Backend/Cognition/autonomous_core.py
  `/control/stop` → Backend/Cognition/autonomous_core.py
  `/creative` → Backend/Cognition/autonomous_core.py
  `/director/plans/{name}` → Backend/Cognition/compagent.py
  `/encode` → Backend/Memory/stardust_encoder.py
  `/foveai-aurora.css` → theme/theme_api.py
  `/foveai_theme_sync.js` → theme/theme_api.py
  `/goal/{goal_id}` → Backend/Cognition/autonomous_core.py
  `/goal` → Backend/Cognition/autonomous_core.py
  `/goals` → Backend/Cognition/autonomous_core.py
  `/health` → Backend/Cognition/autonomous_core.py
  `/health` → Backend/Cognition/compagent.py
  `/health` → Backend/Cognition/soul_core.py
  `/health` → Backend/Cognition/tokenslayer_proxy_server.py
  `/health` → Backend/Creativity/creative_service.py
  `/health` → Backend/Memory/memory_service.py
  `/health` → Backend/Memory/smart_context.py
  `/health` → Backend/Memory/stardust_encoder.py
  `/health` → Backend/chat_relay_server.py
  `/health` → Frontend/Mouth/foveai_mouth_kokoro_server.py
  `/health` → api/server.py
  `/history/{session_id}` → Backend/Memory/memory_service.py
  `/history` → Backend/chat_relay_server.py
  `/internal/slow_burn/tick` → Backend/Cognition/compagent.py
  `/journal` → Backend/Cognition/autonomous_core.py
  `/kiosk/apps/{owner}/{app}/file` → Backend/Cognition/compagent.py
  `/kiosk/apps/{owner}/{app}/file` → Backend/Cognition/compagent.py
  `/kiosk/apps` → Backend/Cognition/compagent.py
  `/kiosk/apps` → Backend/Cognition/compagent.py
  `/kiosk/assist` → Backend/Cognition/compagent.py
  `/kiosk/build` → Backend/Cognition/compagent.py
  `/kiosk/download/{owner}/{app}/{artifact}` → Backend/Cognition/compagent.py
  `/kiosk/targets` → Backend/Cognition/compagent.py
  `/kiosk/templates` → Backend/Cognition/compagent.py
  `/load` → api/server.py
  `/memory/embed` → Backend/Cognition/compagent.py
  `/memory/note` → Backend/Cognition/compagent.py
  `/memory/notes` → Backend/Cognition/compagent.py
  `/memory/status` → api/server.py
  `/memory/{key}` → Backend/Cognition/autonomous_core.py
  `/memory` → Backend/Cognition/autonomous_core.py
  `/message` → Backend/Cognition/autonomous_core.py
  `/messages/mark` → Backend/Cognition/autonomous_core.py
  `/messages` → Backend/Cognition/autonomous_core.py
  `/mode` → Backend/Cognition/autonomous_core.py
  `/mode` → Backend/Cognition/autonomous_core.py
  `/monetize/add_agent` → Backend/Cognition/compagent.py
  `/monetize/config` → Backend/Cognition/compagent.py
  `/monetize/control` → Backend/Cognition/compagent.py
  `/monetize/ideas/certify` → Backend/Cognition/compagent.py
  `/monetize/ideas/plan` → Backend/Cognition/compagent.py
  `/monetize/ideas/scan` → Backend/Cognition/compagent.py
  `/monetize/ideas` → Backend/Cognition/compagent.py
  `/monetize/remove_agent` → Backend/Cognition/compagent.py
  `/monetize/status` → Backend/Cognition/compagent.py
  `/monetize/treasury/config` → Backend/Cognition/compagent.py
  `/personality_presets` → Backend/Cognition/compagent.py
  `/plan/{plan_id}` → Backend/Cognition/autonomous_core.py
  `/plan/{plan_id}` → Backend/Cognition/autonomous_core.py
  `/plan` → Backend/Cognition/autonomous_core.py
  `/plans` → Backend/Cognition/autonomous_core.py
  `/queue/stats` → Backend/Cognition/autonomous_core.py
  `/say` → Frontend/Mouth/foveai_mouth_kokoro_server.py
  `/search` → Backend/Memory/memory_service.py
  `/send` → Backend/chat_relay_server.py
  `/softlayer/assist` → Backend/Cognition/compagent.py
  `/softlayer/modules/{module_name}.js` → api/server.py
  `/softlayer/modules/{name}` → Backend/Cognition/compagent.py
  `/softlayer/modules/{name}` → Backend/Cognition/compagent.py
  `/softlayer/modules` → Backend/Cognition/compagent.py
  `/softlayer/modules` → api/server.py
  `/softlayer/{module_name}.js` → Tools/softlayer_server.py
  `/softlayer/{module_name}.js` → api/server.py
  `/softlayer/{module_name}.js` → tools/softlayer_server.py
  `/softlayer` → Tools/softlayer_server.py
  `/softlayer` → api/server.py
  `/softlayer` → tools/softlayer_server.py
  `/soul/status` → api/server.py
  `/soul_dna` → Backend/Cognition/compagent.py
  `/soul_runtime_config` → Backend/Cognition/compagent.py
  `/soul_runtime_status` → Backend/Cognition/compagent.py
  `/status` → Backend/Cognition/autonomous_core.py
  `/store` → Backend/Memory/memory_service.py
  `/swarm_match` → Backend/Memory/stardust_encoder.py
  `/switch_model` → Backend/Cognition/compagent.py
  `/synthesize` → Frontend/Mouth/foveai_mouth_kokoro_server.py
  `/tasks/{plan_id}/approve` → Backend/Cognition/compagent.py
  `/tasks/{plan_id}/context` → Backend/Cognition/compagent.py
  `/tasks/{plan_id}/reject` → Backend/Cognition/compagent.py
  `/tasks` → Backend/Cognition/compagent.py
  `/tasks` → Backend/Cognition/compagent.py
  `/thoughts` → Backend/Cognition/autonomous_core.py
  `/tts` → Frontend/Mouth/foveai_mouth_kokoro_server.py
  `/unload` → api/server.py
  `/update_resonance` → Backend/Memory/stardust_encoder.py
  `/update_soul` → Backend/Cognition/compagent.py
  `/v1/audio/speech` → Frontend/Mouth/foveai_mouth_kokoro_server.py
  `/v1/audio/speech` → api/server.py
  `/v1/audio/transcriptions` → api/server.py
  `/v1/capabilities` → api/server.py
  `/v1/chat/completions` → Backend/Cognition/soul_core.py
  `/v1/chat/completions` → Backend/Cognition/tokenslayer_proxy_server.py
  `/v1/chat/completions` → Backend/Memory/smart_context.py
  `/v1/chat/completions` → api/server.py
  `/v1/completions` → api/server.py
  `/v1/context` → api/server.py
  `/v1/diagnostics` → api/server.py
  `/v1/images/understand` → api/server.py
  `/v1/models` → Backend/Cognition/tokenslayer_proxy_server.py
  `/v1/models` → Backend/Memory/smart_context.py
  `/v1/models` → api/server.py
  `/v1/packages` → api/server.py
  `/vitals` → Backend/Cognition/compagent.py
  `/vitals` → Backend/Cognition/soul_core.py
  `/voices` → Frontend/Mouth/foveai_mouth_kokoro_server.py
  `/vram/lock` → Backend/Cognition/compagent.py
  `/vram/unlock` → Backend/Cognition/compagent.py
  `/webvm/{path:path}` → Backend/Cognition/compagent.py

## Arch
- Win-Native | Holonic Loop 1.0T
- MCP: foveai-memory(17) + tokenslayer(6) | LLM: Qwen3.5-4B
- Context: compress_search_results default | summarize_context when heavy
- Expand: use `expand_node` MCP tool or read specific line ranges