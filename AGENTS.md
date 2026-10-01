# FoveAI — Project Memory

Auto-synced | 500 observations

Stack: Python · FastAPI · Pydantic · pytest · Redis

# 🏛️ CORE ARCHITECTURE

CRITICAL: User-defined architecture constraints. Never violate them.

# Intellectual Property & Architecture Rules
Write your strict architectural boundaries here.
NeuroSync will automatically enforce these rules across all AI agents
and inject them into the memory context.

Example:
- NEVER use TailwindCSS. Only use vanilla CSS.
- NEVER write class components. Only use functional React components.

# 🧠 CORE LESSONS (SELF-CORRECTION)

CRITICAL: Persisted lessons. Do not repeat past mistakes.

# 🧠 Agent Lessons

This file is a self-optimizing loop. When an AI agent makes a mistake and you correct it,
tell the agent to document the pattern here so it mathematically never repeats the mistake.

# 📋 Lessons
- persistent_memory's `_lock` is a non-reentrant `threading.Lock` — never call a helper that acquires it (get_plan, update_plan, etc.) from inside another `with _lock:` block; it deadlocks silently (futex wait). Fetch rows on the open connection instead. (2026-09-20: activate_due_tasks deadlock.)
- Silent-failure audit pattern: when a subsystem "stopped working," check (1) is it deployed — compagent had no systemd unit; (2) is the entry point live — `lifespan=lifespan` was commented out of the FastAPI constructor, killing the whole autonomous runtime; (3) are calls raising into `except→logger.debug` swallows — the Director called a retired slot name and died silently on every call; (4) env case — `FOVEAI_*` vs `FoveAI_*` mismatch silently ignored settings until the `soul_state` normalizer. (2026-09-20)
- Tasks/todos share one substrate: `agent_plans` in persistent_memory. Jen's `<self:todo>` tags, coder models' `todo_add/todo_done`, and scheduled/recurring/Director-hidden work are all plan steps or plan statuses (`scheduled`, `proposed`). Do not create parallel todo/plan stores — coder_todos.json was migrated into a `[CODER]` plan. Scheduling columns: `scheduled_for`, `recurrence`, `origin`.
- Multigate password gate intercepts EVERYTHING not in its allowlist (`/api/`, `/v1/`, `/xrlf/`, `/health`). When `FoveAI_WEBUI_PASSWORD` is set, requests to `/webvm`, `/netdata`, `/settings.html` etc. return the gate's `Xarel — Enter` login HTML — which looks like "the proxy is broken / SPA fallback is eating the route." Before debugging vite proxy middleware, test with a computed `xarel_auth` cookie (sha256('xarel|'+password)[0:32]) or check whether the response contains `<title>Xarel — Enter`. (2026-09-20: hours lost diagnosing /webvm as a vite proxy bug.)
- Vite 8 proxy/middleware quirk: middlewares registered via `server.middlewares.use()` inside `configureServer` run BEFORE vite's internal stack (proxy, public dir, SPA fallback); a returned post-hook runs AFTER. To serve files with custom headers (WebVM's COOP/COEP), use a direct `configureServer` middleware (`webvmStatic` in vite.config.ts) streaming from `Frontend/XR_Vessel/public/webvm` — do NOT rely on `server.proxy` entries for non-`/api` paths or on header-setting post-hooks.
- NEVER dump raw process environments (`/proc/<pid>/environ`, `env`, `printenv`, `os.environ`) to output — they contain live API keys/passwords. Grep for the SPECIFIC keys you need instead (e.g. `tr '\0' '\n' < /proc/PID/environ | grep -E '^(GPU|CUDA)'`). Same for `.env` files — read individual keys, never cat the whole file. (2026-09-11: leaked NVIDIA/Gemini/service keys into session transcript this way.)
- Ensure all variables are typed before pushing.
- Headless Unity builds (`client_quest/build_apk.sh`) need `DISPLAY=:0` on this machine (Xwayland on tty2/Budgie session) — Unity 6 editor aborts at startup without an X display even in `-batchmode`. Script compilations also fail if a new package assembly (e.g. `Unity.XR.Hands`) isn't added to `FoveAI.Runtime.asmdef` references.
- Audit for existing/unwired features before writing new ones. Search for panels, managers, and services by name first; prefer wiring/extending what exists (e.g. VRBrowserPanel, ChatRelayPanel) over parallel new classes. Created-but-never-hooked-up code is common in this repo — check scene references and live ports before assuming a feature works or is missing.
- Audio Multiplexing ("All Should Hear All"): Audio events, synthesized voice (TTS), Director narrations, and avatar speech must be multiplexed and broadcast to all connected endpoints (Quest 3 WebSocket :8403, WebXR Spatial Frontend :5176) and local PC speakers simultaneously. No client or headset entity is left in an isolated audio silo.
- Replace, don't merge: When architectural components, ports, or protocols are updated, cleanly replace and excise legacy references instead of appending alongside them. Merging old and new leaves zombie references that poison AI context and runtime HUDs.
- XRLF readiness: `foveated-memory/public/settings.html` checks `/health.loaded`; the API must return the live boolean `runtime.loaded`, not just HTTP 200. Omitting it causes a false 90-second startup timeout. This readiness flag does not verify inference or GPU offload.
- Isolated API health regression tests (no model loading): `.venv/bin/python -B -m unittest discover -s tests -p 'test_api_health.py' -v`.
- Network regression checks: `.venv/bin/python -B -m unittest discover -s tests -p 'test_network_config.py' -v` and `node --test tests/test_network_frontend.cjs` (requires Multigate's installed TypeScript). Empty `FOVEAI_SERVER_IP` selects live LAN detection; `server_config.py --refresh-network-config` refreshes the root/Frontend network snapshots and is called by Sleipnir startup. Browser service requests should use same-origin proxy paths, not the visitor's localhost. Ignition needs an explicit server-side `FOVEAI_IGNITION_URL`; port 8409 belongs to STT.
- Post-migration voice/service port map (2026-09-19, soul added 2026-09-20): Soul API `:8405` (`foveai-soul.service`, compagent — persona/DNA/tasks/kiosk; NOT `:8402` which is XRLF, NOT `:8000` which is retired), TTS `:8406` (`foveai-tts.service`, Kokoro `/tts` `/say` `/voices` `/health`), STT `:8409` (`foveai-stt.service`, WebSocket-only — probe TCP not HTTP), native audio on `:8402` (`/v1/audio/speech`, `/v1/audio/transcriptions`), Motor `:8410`, Subconscious `:8411`, Chat Relay `:8407`, Multigate `:5177` (Vite, needs Node ≥20 — Node 24 at `~/.local`). Legacy `:8001`/`:8004`/`:8000`/`:8110` are retired; do not revive to satisfy stale health checks. LM Studio `:1234` and XR Vessel `:5176` are optional/normally offline, not failures.
- Migration traps: `.env` may reference OS-specific paths from the old distro (Fedora `/etc/ssl/certs/ca-bundle.crt` vs Debian `ca-certificates.crt`); services run `HF_HUB_OFFLINE=1` so models must be pre-cached into the configured `HF_HUB_CACHE` (`/home/lumba/Models/hub`), not `~/.cache`; the Kokoro voice env key is mixed-case `FoveAI_KOKORO_VOICE`.
- llama-cpp-python CUDA build (0.3.35, in-venv CUDA 13.3 toolchain, sm_89/RTX 4060, driver 595.99): requires `GGML_CUDA_NO_VMM=1` or the runtime aborts in `ggml_cuda_pool_vmm::free` during decode. Set in `sleipnir_launcher.sh` and `FoveAI_Taskbar_Linux.py`. GPU offload verified working (2.8GB VRAM, ~4s chat responses).
- Verify llama.cpp GPU capability with `llama_cpp.llama_supports_gpu_offload()`; the runtime's "Full GPU Offload" guardrail message describes requested allocation and is not proof that the installed backend supports it.
- Default local model: `xrl_encoded/gemma-4-e2b-multimodal-v1.0.xrlf` (Gemma 4 E2B, not 12B). Root/proxy local-model settings, YAML `model`, and YAML `models.primary` were aligned on 2026-09-06; 12B remains an explicit UI alternative.
- Benchmark hardening (2026-09-07, RESOLVED): Hardened `builder/probes/benchmark_suite.py` and `benchmark_run.py`. Excised data-leaching logic: numeric extractor no longer scans intermediate reasoning for the expected answer, multi-number sets ("18 and 19") are compared via float sets, `_is_correct` prohibits substring/empty passes (eliminating `p in e` leaks), and MCQ parser resolves options from final conclusions and option texts without false-positive English article collisions. Multimodal test spoofing excised: `ApiResponder` preserves true `image_url` and `input_audio` payloads without substituting text spoilers, and pure-Python in-memory PNG/WAV generators provide verifiable sensory benchmarks checked against semantic keywords. Unit test coverage added: `tests/test_benchmark_suite.py` (12/12 passing). Stale port 8300 updated to 8402 in `benchmark_run.py` and `auto_benchmark.ps1`.
- Prompt review (2026-09-06, RESOLVED): SoulBridge no longer zeroes PrincipiaApplicator output — both compose as separate layers (task guidance → memory → identity) in `_inject_system`. MindCore validator now only checks movement brackets for XR_VESSEL/VR_GODOT, not DESKTOP_JEN/MOBILE_JEN. Directives, memory, and sensory context are preserved.
- Dependency management (2026-09-06): Rebuilt venv with UV on Python 3.12 (not 3.14 — too new, missing wheels). Requirements split into `requirements.txt` (core, pinned), `requirements-dev.txt`, `requirements-optional.txt`. kokoro upgraded 0.7.16→0.9.4 (fixed numpy pin conflict). opencv pinned to 4.10.0.84 (5.x required numpy>=2). Install: `uv venv .venv --python 3.12 && uv pip install -r requirements.txt`.
- Chat handler fix (2026-09-06, RESOLVED): The local patched `Gemma4ChatHandler` in `llama_bridge/gemma4_handler.py` was written for llama-cpp-python 0.3.16 and produces garbled output (repeated emoji tokens) with 0.3.35's mtmd interface. Switched `llama_engine.py` to prefer the native `Gemma4ChatHandler` from `llama_cpp.llama_chat_format` (0.3.34+). The local handler remains as fallback. Inference verified: Jen responds correctly with personality, monologue, and avatar tokens.
- Tray/runtime alignment (2026-09-06): `FoveAI_Taskbar_Linux.py` now uses `site.getsitepackages()` instead of hardcoded Python 3.14 GI path. Direct model launch (`select_persona_model`) now passes `--port 8402 --ws-port 8403` and `XRLF_REPO_ENABLED=true`, matching `sleipnir_launcher.sh`. WS port 8403 health check changed from HTTP `/health` to TCP-only (it's a WebSocket server, not HTTP).
- SoftLayer integration (2026-09-06): `Frontend/XR_Vessel/src/softlayer/SoftLayerLoader.ts` fetches JS configs and modules from `/softlayer/` and `/softlayer/modules/` endpoints, executes them in a sandboxed `FoveAI` API context, and supports lifecycle hooks (`onLoad`, `onUpdate`, `onUnload`). Hot-reloadable via `foveaiSoftLayer.reloadModule(name)`. Wired into `main.ts` after avatar init. Tray has a "SoftLayer Modules" submenu for reloading configs and modules.
- Avatar frozen pose fix (2026-09-06): `MovementEngine.ts` autonomous household presence re-enabled — `makeDecision()` is called when the LLM hasn't sent a movement command for `decisionInterval` seconds. Produces gentle wandering, micro-gestures, curious steps, and rest states. Toggle via `FoveAI.setParam("avatar.autonomousMode", true/false)`. Jump action in `AvatarManager.ts` now falls back to procedural idle instead of freezing when no jump clip exists.
- Live webcam plaster (2026-09-06): `SpatialEnvironment.ts` now projects the rigged room webcam as a live `THREE.VideoTexture` onto scanned wall/screen surfaces. Portrait orientation handled via 90° UV rotation. `buildRoomScene()` is now called after Quest Scene API data ingestion (was never called before — room meshes were ingested but never rendered). SoftLayer params: `webcamPlaster.enabled`, `webcamPlaster.orientation`, `webcamPlaster.opacity`. Tray has toggle and orientation menu entries. The avatar's spatial description now includes webcam plaster status so the LLM knows it can see through the webcam.
- "Be Jen" first-person POV (2026-09-06): Press **V** in the XR Vessel to toggle first-person mode — the render camera follows Jen's head bone position+rotation every frame, so you see the world through her eyes. Also toggleable via SoftLayer param `avatar.jenPOV` in `behavior_config.js`, the `FoveAI.jenPOV.toggle()` API, or the tray menu. When active, XR rendering is temporarily bypassed per-frame so the canvas shows Jen's view directly. The camera uses a 70° FOV and a small eye offset (forward+up from the head bone center) for a natural perspective.
- Director spooky voice & Avalanche music (2026-09-06): `DirectorVoiceEngine.ts` gives the Off-Scene Director a deep, pitch-down Leonard Cohen-style narrator voice (pitch=0, rate=0.7, low-pass filter at 800Hz, 4s reverb tail). The "Avalanche" dark ambient music mode plays a procedural slow minor chord progression (Am-F-G-Am, 16s per chord) with sub-bass pulse, detune drift, and ghost overtones — inspired by Leonard Cohen's "Avalanche". Press **M** to toggle music. The engine connects to the XRLF WebSocket (port 8403) and automatically speaks narrator lines and starts music during horror/mystery/surreal Director events. SoftLayer params: `director.voicePitch`, `director.voiceRate`, `director.voiceVolume`, `director.reverbAmount`, `director.filterCutoff`, `director.avalancheMusic`, `director.avalancheVolume`. Tray has test-voice and toggle-music entries.
- Director Codec2 radio effect (2026-09-06): The Director's narrator voice now has a FreeDV/Codec2-style radio transmission quality — squelch-open burst ("ksssh") before speech, continuous bandpass-filtered static bed underneath, and squelch-close burst when speech ends. Simulated entirely with Web Audio API (no external WASM needed): white noise through bandpass filters at 800-1500Hz, gain envelopes for squelch character. Toggle via `director.radioEffect` SoftLayer param, intensity via `director.radioIntensity` (0=clean, 1=heavy static). The Director sounds like he's speaking through an old HF radio from beyond.
- Director "Mount Zion" reverb (2026-09-06): The narrator voice reverb retuned to "soft but dark reverberated from Mount Zion" — an 8-second convolution tail with 40ms pre-delay (sound crosses a vast stone plateau before the first reflection), heavy low-frequency bias (one-pole LP at 0.15 coefficient for a dark, warm tail), 200ms soft smoothstep attack (gentle reflections, not percussive), slow exponential decay (power 1.8 — the tail lingers like incense smoke), stereo decorrelation (different PRNG seeds per channel for wide, otherworldly imaging), and a 55Hz stone-resonance rumble woven into the tail. Voice defaults retuned: rate 0.65 (slower, softer), volume 0.7 (let the reverb breathe), reverbAmount 0.65 (wet — the reverb IS the character), filterCutoff 600Hz (darker, no harshness).

# 🛡️ GLOBAL SAFETY RULES

- NEVER run `rm -rf`, `del /s`, `rmdir`, `format`, or any command that deletes files/directories without EXPLICIT user approval.
- NEVER run `DROP TABLE`, `DELETE FROM`, `TRUNCATE`, or any destructive database operation without backup confirmation.
- NEVER run `git push --force`, `git reset --hard`, or any command that rewrites shared history.
- NEVER run `npm publish`, `docker rm`, `terraform destroy`, or any irreversible deployment command.
- NEVER pipe remote scripts to shell (`curl | bash`, `wget | sh`).
- ALWAYS show the command first and wait for approval before running anything that modifies system state.
- When in doubt — show the command first, wait for approval.

# 🧭 ACTIVE CONTEXT

Source of truth: .neurosync/rules/neurosync_auto.md

# 📝 NOTE: 8897 uncommitted file(s) in working tree.

# 🔀 Decisions

- decision in state.json
- decision in tundra.log.json

# 🔁 Learned Patterns

- decision in state.json (seen 7x)
- decision in tundra.log.json (seen 15x)
- decision in tundra.log.json (seen 12x)
- decision in tundra.log.json (seen 6x)
- decision in tundra.log.json (seen 7x)

---
*Auto-synced by NeuroSync 🧠 on September 2, 2026*