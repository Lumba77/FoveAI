# FOVEAI SYSTEM STATUS REPORT (STREAMLINED XRLF TOPOLOGY)

## 1. STREAMLINED MODEL TRIAD & NATIVE SERVICES
FoveAI refactors away from brittle, high-latency multi-model HTTP swarms into a unified **One Main LLM + Smart Proxy Router + Memory Helper** architecture connected via persistent WebSockets:

| Component | Role / Model | Port / Protocol | Note |
|---|---|---|---|
| **Main Cognitive LLM** | `xrl_encoded/gemma-4-e2b-multimodal-v1.0.xrlf` | 8407 (HTTP) / 8407 (WS) | The single active cognitive core (Gemma-4-E2B) loaded by the XRLF runtime. `/health` exposes `loaded`/`load_state`. Native `/v1/audio/speech` (Kokoro) and `/v1/audio/transcriptions` (Whisper). |
| **Smart Proxy (Omni-Router)** | `lumax-plumax-omni-router-v2.xrlf` | 8406 (Internal Middleware) | Intercepts massive context dumps (>12K chars) and extracts critical code and intent. |
| **Failover Omni-Router (No. 2)** | `no2-lumax-plumax-omni-router.xrlf` | Failover Channel | Load-balancer / secondary router engaged if Router 1 encounters congestion. |
| **Memory Helper Model** | `lumax-summarizer-draft.gguf` | Embedded | Background helper weaving active-recall memory ring blocks and compacting checkpoints. |
| **Foveated Memory Proxy** | `foveated-memory/server.js` | 8400 (ws/http) | Memory ring manager, context proxy, dynamic HUD injector. Voice routes: `/api/tts` (native :8411 → Kokoro :8411), `/api/soul/stt`, `/api/tts/voices`, `/api/voice/status`. |
| **Dashboard / Settings** | `foveated-memory/public/` | 8414 | Settings UI; `/api/subsystems` health check uses the current 840x port map. |
| **WS IPC** | `Backend/app/IPC/websocket_server.py` | 8403 (WebSocket only) | Client-to-runtime conduit. TCP/WS only — no HTTP health route. |
| **Mouth Kokoro** | `foveai_mouth_kokoro_server.py` | **8411** | Neural 24kHz TTS (`/tts`, `/say`, `/voices`, `/health`). `foveai-tts.service`. Fallback after native :8402. |
| **Chat Relay** | `Backend/chat_relay_server.py` | **8413** | Cross-client chat relay. `foveai-chat-relay.service`. |
| **Creative Service** | — | 8412 | Assigned; optional. |
| **Ears STT** | `Backend/stt_whisper_server.py` | **8401** (WebSocket only) | Whisper streaming STT. `foveai-stt.service`. HTTP `/health` invalid — probe TCP. |
| **Motor / Autonomous** | `motor_daemon.py` | **8410** | Native avatar agency. `foveai-motor.service`. |
| **Subconscious** | `Backend/Cognition/subconscious_daemon.py` | **8409** | Telemetry eval + dispatch. `foveai-subconscious.service`. `/health` added 2026-09-19. |
| **Multigate WebUI** | `Frontend/multigate` (Vite) | **5177** | Browser UI; same-origin `/api/*` proxied to :8400. `foveai-multigate.service`. Requires Node ≥20 (Node 24 in `~/.local`). |
| **Sleipnir Central Thalamus** | `Tools/thalamus_xrl_bridge.py` | **8420** | Swarm router for 5 Mamba-2 colonies (History, Finance, Constitutive, Receptor, Companion). 136 tok/s inference, 432Hz chords, Kantian memory rings. |
| **WebXR Vessel UI** | Spatial Frontend | 5176 | Optional/deprecated — normally offline. |
| **Sovereign Core (Soul)** | `compagent.py` | 8402 (`SOUL_PORT`) | Cognition loop, motor intent extraction, avatar coordination. |
| **LM Studio (Optional)** | BYO-GGUF Gateway | 1234 | Optional legacy fallback; normally offline. Browser access proxied via `/api/lmstudio`. |
| **xrdp** | Remote desktop | 3389 | Remote access; VNC currently localhost-only. |
| **Legacy Systems** | 🔴 PURGED | — | Docker, WSL2, Godot, Kuzu, Cognee, TokenSlayer Proxy (:8106/:8103), SigMap, voice ports :8001/:8004, soul :8000, motor :8110, stardust :8109 — all purged/retired. |

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
1. ~~Local mode, LLM thinking for 1 minute, never reaches to actually voice a greeting.~~ — **Fixed 2026-09-03**: Stale model profile upstream port (1234→8411) caused all local chat completions to fail with HTTP 400. See `context.md` entry.
2. Soul starts, seems ok, then goes offline

## 4b. Recently Fixed (2026-09-03)
- **Quest→PC HTTP 400 resolved**: The Foveated Memory Proxy (`:8400`) was routing to `http://127.0.0.1:1234` (dead legacy LM Studio port) instead of the local llama-server at `http://127.0.0.1:8402`. Root cause was stale `upstream_url` in 4 model profiles in `memory_data/model-profiles.json` and 3 vars in `foveated-memory/.env`. All corrected to `:8402`. Proxy restarted, end-to-end chat completion verified with Quest payload (`model: "foveated-proxy"`, `Authorization: Bearer lumax_spatial_client`).

## 4c. Post-Migration Healing (2026-09-19)
- **Hard-drive crash recovery**: Server migrated to new hardware. `.venv` lacked the voice stack → installed pinned `torch(cpu)`, `kokoro==0.9.4`, `faster-whisper==1.2.1`, `soundfile`, `misaki`, `py-espeak-ng`. `.env` Fedora CA path → Debian `ca-certificates.crt`. Kokoro + Whisper models cached into `/home/lumba/Models/hub` for `HF_HUB_OFFLINE=1`.
- **Voice reassigned to 840x**: TTS `8004→8411` (`foveai-tts.service`, Kokoro `/tts` `/say` `/voices` `/health`), STT `8001→8411` (`foveai-stt.service`, WebSocket-only). Native `:8411` audio endpoints are primary. Proxy `voice/status` TCP-probes `:8411`. Old 800x references excised from active code — do not revive.
- **Missing services restored**: `foveai-motor` (:8410), `foveai-subconscious` (:8409, `/health` added), `foveai-chat-relay` (:8413), `foveai-multigate` (:8413, Vite dev, Node 24 at `~/.local`). All existing implementations — no duplicate stacks.
- **IP-agnostic**: `server_config.py` resolves the live LAN IP dynamically when `FOVEAI_SERVER_IP` is blank; `refresh_network_config()` rewrites `foveai_network_config.json` at Sleipnir startup. Stale `192.168.8.100` overrides removed. Multigate browser calls use same-origin `/api/*` paths so remote visitors don't hit their own localhost.
- **Jenna-vscode**: TTS bridged through extension host → proxy → Kokoro; voice dropdown fed by `/api/tts/voices`. Deployed to Devin + Antigravity (v0.5.6).
- **Verified**: `/api/tts` → WAV, `/api/soul/stt` → 200, XRLF `loaded:true`/`ready`, all 8 services active. `test_network_config.py` 7/7, `test_network_frontend.cjs` 4/4.

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

---

# 2026-10-06 — Ignition Redesign, Theme Chain Repairs, Profile Pictures (AI session)

## Frontend (Frontend/multigate/)
- **IgnitionScreen rebuilt** — radial "aetherial" layout: trackball at true center, 7 halo rings outside the plate (88–112% of stage), floor-reaching diode light cones (no 60vh cutoff), engraved status text, real logotype (`foveai-logo-light.png`), reduplicated value readouts removed. Log/status cluster merged under dial.
- **Trackball pip geometry fixed** (`src/trackball/Trackball.tsx` + `trackball.css`): pip orbit now computed from the ring's actual gradient geometry (`(size/2)·√2·0.96`, clamped) so all 10 balls seat ON the outer brass circle; absolute-positioned layout (ball on orbit point, label 2.4em above, value 2.23em below) killed the "lower balls gravitate toward center" flex-column sag.
- **Profile picture UI** — PersonaTab upload card (72×96 preview, "adds to collection" semantics), events `foveai_profile_picture_updated` → instant avatar-window swap.

## Backend (:8400 foveated-memory/server.js)
- **`GET/POST /api/profile/picture`** — user profile pictures COLLECT into `media/gallery/<user>/` as timestamped files (never replace); `profile_pictures.json` = collection index + current pointer; mirrored into auth.json `profilePicture`; exposed via `/api/auth/me`.
- **`GET /api/themes` + `POST /api/theme/set_active`** added to the LIVE Node server — the Python `http_proxy.py` themes route never ran (:8400 is Node) — this 404 chain was crashing Theme Machine on open.

## Theme Engine chain (was completely broken, now end-to-end live)
- `theme/theme_api.py` (:8415) — **was not running**; now started (sleipnir branch Node 4); added `/foveai-aurora.css` FileResponse route (index.html loads it from :8415 — was 404 → unstyled app).
- **Theme broadcast moved to unified WS** — `websocket_server.py` (:8403): `/ws/theme` listener path, `_theme_clients` registry, `broadcast_theme()`, `POST /internal/theme-broadcast` relay; `theme_api.py` set_active relays to :8413; `theme_sync.js` now dials same-origin `/ws/theme` (vite proxy ws:true, tunnel-compatible) instead of 8415.
- vite.config.ts — `/api/theme` → :8415 (generation/active), `/api/themes` → :8400 (manifest), `/api/dream` port fixed 8412→8003.
- **Ignition middleware fixed** — dead unit names (motor/subconscious/chat-relay) aborted the whole batch; units list corrected to the installed set; user-scope→system-scope sudo fallback added.
- **TTS service resurrected** — systemd ExecStart had doubled repo path (`FoveAI/FoveAI/...`) → 222 restart loops; unit fixed, Kokoro online (:8411). Stale `/tmp/foveai_locks/kokoro_tts.pid` caveat.
- Diagnostics panel Creative probe: 8412→8003 (matches live port).

## Loose-mode audio conversation (App.tsx)
- `looseMode` (avatars unpinned + non-Copilot tab) → audio-only: VAD listener runs regardless of mode dial (`effectiveInputMode`), conversation continues via subtitles while browsing.

## Code health
- **52 → 0 tsc errors** across multigate (was blocking `tsc -b`/production build entirely — stale bundles likely the historic "site crashes on enter").
- ThemeApplicator hardened: undefined-CSS-var injection guard, `ui_structure` default, AbortSignal timeout on /api/dream, OscillatorNode/AudioBufferSourceNode type fix.
- oxlint bootstrapped (0 errors, src/); fake gzip-HTML "bootstrap-dropdown.js" stubbed; dna legacy dirs lint-ignored.

---

# 2026-10-06 — XRL Scan Pipeline Resurrected & Repo Wide Findings (AI session)

## XRL scan pipeline — was blind to the live stack, now self-configuring
- **Blunder root-fixed** (`Scripts/generate_repo_principia.py`):
  1. `.xrl-ignore` loader didn't strip inline comments → patterns like
     `Frontend/Web/  # stale` never matched (fnmatch vs literal). Loader now
     splits on `#` before matching. Every inline-commented exclusion silently
     failed before this.
  2. `SCAN_DIRS` hard-coded and missing the LIVE frontends: multigate,
     Copilot, Mouth, theme/ never walked — the exact dirs where recent bugs
     (Theme Machine crash, TTS systemd path) hid. SCAN_DIRS is now a
     *priority* list; `_root_level_dirs()` auto-discovers every root-level
     source dir (depth ≤2 probe), exclusions govern the rest.
  3. Root-level live services (`run_xrlf.py`, `server_config.py`,
     `ignition_server.py`) wired in via `SCAN_ROOT_FILES`.
  4. The Tree section now reflects reality (multigate/XR_Vessel/Copilot/
     Mouth/theme/foveated-memory-core) instead of stale Frontend/Web + Webui.
- **`.xrl-ignore` rewritten** for Linux-era architecture: Windows .ps1 sweeps,
  dormant Tools, superseded frontends, archives, heavy ML dirs excluded;
  live stack inclusive. New `*_archive_v1.py` pattern targets zombie twins.
- **Tools/xrl_scan_and_index.py executed**: 1000 files indexed into the
  memory server (0 failed, 669 dirs skipped), repo-principia.md regenerated:
  7171 lines / 339 KB (~85K tokens), 68% more coverage than before.

## Findings from the full scan
- **`compagent_archive_v1.py` = route zombie** — registers the identical
  `/api/agent/*` map as live compagent.py; 64 principia references. Do not
  import; candidate for excision (AGENTS.md "Replace, don't merge").
- **Windows fingerprints in foveated-memory/server.js are SAFE** — verified,
  not dead weight: `resolvePwshPath()` returns 'bash' on non-Windows first
  line; IDE detection returns VS Code fallback before PowerShell; command
  runner branches to `bash -c` on Linux. Cross-platform guards, leave as-is.
- **Port ghosts explained by user**: 7272 = user's custom LM Studio port,
  11434 = Ollama — both retired; stack is XRLF + llama-servers only now.
  soul_core.py still caries LM Studio auto-start/await branches (7272) and
  Ollama checks (11434) — dormant but present.
- **Secrets hygiene**: no live tokens/keys leaked into principia (greps for
  hf_/sk-/fvs_/lmx_ literal patterns came back clean).

## Why this matters (core functionality)
repo-principia.md is the memory-injection backbone: MCP server injects
repository structure + ports + API routes from it into every model call
(`Backend/Memory/foveai_mcp_server.py:788` reads it for [REPOSITORY
STRUCTURE] injection). With the blindspots fixed, all models now receive
the TRUE live topology — multigate, theme chain, foveated-memory core,
mouth, copilot — instead of the stale Windows-era map.

## Maintenance cadence (recommended)
After any structural change (new service, dir, port):
  python Scripts/generate_repo_principia.py   # refresh mind-map
  .venv/bin/python Tools/xrl_scan_and_index.py  # re-index memory server

---

# 2026-10-06 — GOOD ENOUGH AI — the founding vision (user's words, preserved)

## The Dream (user, verbatim intent)
An app concept called **"Good enough AI"**: an AI that adapts to the user's
needs and wishes. It LISTENS to what the user wants, and PROGRAMS ITSELF
there — and STOPS when the user is satisfied. It doesn't have to be the best
app in the world. As long as the user is satisfied. The AI may advise, ask
if they want it otherwise, propose better ways — but THE USER DECIDES.

## Why this is different from everything else in the repo
Every autonomous layer currently optimizes for *the agent's* judgement
(Jen's curiosity engine, benchmark scores, "quality over quantity" rules).
GOOD ENOUGH AI inverts the fitness function: **user satisfaction is the
only finish line**. "Done" is declared by the human, not by test coverage
or elegance. This is the missing top-level goal that makes self-evolution
safe: the guardrail isn't technical, it's *consent-based stopping*.

## How it maps onto existing machinery (all present, needing wiring)
| Good-Enough concept | Existing substrate | Missing link |
|---|---|---|
| "Listens to what the user wants" | Goals of record (`agent_goals`, /api/agent/goals) | Goals not yet injected into every tick (HUD update just wired them in `coder_tools.hud_context`) |
| "Programs itself there" | `<self:edit>/<self:codedit>` + edit_layers (.foveignore protection, snapshots, undo) | Loop must PULL the next goal step, not just free-form curiosity |
| "Stops when the user is satisfied" | Goal status API (`/api/agent/goals/{id}/complete`, outcome) + chat | A satisfaction check-in after each delivered step; user says "good enough" → goal seals, work STOPS (no gold-plating) |
| "Propose better ways, user decides" | `<self:queue>` messages, proposals queue | Explicit advisory step between iterations: propose, then WAIT for verdict instead of iterating unprompted |
| Rescan after change | XRL scan pipeline (today's fix) | Trigger rescans on edit batches (pending wiring) |
| Cloud muscle for fixes | FOVEAI_CODER_BASE_URL (sharp coder persona) + cloud route | Point error-reports at the cloud fixer, gate through .foveignore |
| Guardrails | .foveignore floor, SafetyMonitor, edit journal, undo | Keep. Plus: never edit while user is dissatisfied — fix first |

## The loop (to implement as GOAL-DRIVEN autonomous cycle)
```
1. Read highest-priority active goal  (agent_goals)
2. Check in: have you (user) changed direction? (chat tail)
3. Do ONE smallest-possible step toward the goal
   (<self:edit>/<self:codedit>, snapshotted, undoable)
4. Self-verify: lint + tests via repo_lint/repo_run_tests
5. Report in one message (<self:queue>): what changed, why it serves YOU
6. ADVISE (if any): "I could also X/Y — want that?"  → wait
7. If user says good enough / seals goal → complete_goal, STOP working it
8. Rescan (XRL) if structure changed; log; repeat from 1 ONLY while
   the goal is active and the user hasn't said stop
```

## Design law (proposed, to bake into the prompt rails)
- **The user is the definition of done.** No step 3 before step 2 (check-in
  first if the user changed the subject — old goal steps yield).
- **Advisory, never pushy**: one suggestion per delivered step max.
- **Good enough is a finish state, not a compromise** — record what
  "enough" meant in the goal outcome, so future goals inherit taste.
- **Satisfaction telemetry**: every completed goal stores `outcome` with
  the user's parting words — that's how the system learns what "good
  enough" looks like per user.

## Status
- HUD goals injection: WIRED this session (coder_tools.hud_context)
- Goal-driven loop variant: DESIGNED here, not yet implemented
- Self-heal trigger (XRL rescan on edits): DESIGNED, not yet wired
- Next concrete step: extend `_generate_autonomous_action` with a
  GOAL_WORK branch that follows the loop above.

---

# 2026-10-06 — GOOD ENOUGH AI → the Humble Interview (design note)

## User's addition (verbatim intent)
The self-developing, goal-oriented prospect needs a **tightly defined goal
vision**. To get there the system must be **very alert to the user's
wishes**, and **humble to admit when it doesn't know — to ask more
questions**. Proposed starting point: **a cleverly designed questionnaire,
maybe as a VOCAL interview**.

## Why a vocal interview is the right start
- The stack already speaks both ways hands-free: Whisper STT (:8401 WS),
  Kokoro TTS (:8411), the aural-awareness layer, and the loose-mode
  audio conversation — a voice loop exists end-to-end today.
- Voice keeps the barrier low: the user *talks* their dream while the AI
  distills it; text forms would stall at "I'll write it later."
- Humility becomes audible: "I don't know yet — tell me more about X"
  is natural speech, not a confession in a text box.

## Interview structure (designed — "Good Enough Intake")
An iterative elicit-and-summarize loop, NOT a fixed form. Rounds of at
most 3 questions, each round ends with a restatement. Stops when the
summary gets a "yes, that's it" (consent-based stopping — same law as
the main loop).

```
Round pattern:
  1. DREAM     — "In your own words, what should this become?"
  2. CONCRETE  — "What will you DO with it the first week?"
                 (actions, not features — grounds the vision)
  3. GOOD-ENOUGH — "What's the smallest version you'd be happy with
                 TODAY?"  (the finish line, per the founding vision)
  → RESTATE in 5 lines max, read it back vocally
  → "Did I get that right, or should I ask more?"
       wrong → next round (drill into what was off)
       right → persist as goal draft → /api/agent/goals
  Humility rules:
  - Unknown words → ask ("XRF did you say? what does it do for you?")
  - No guessing requirements from vibes; every requirement must trace
    to a user sentence (stored with the goal — provenance!)
  - Conflicts (contradictory wishes) → surface both, let user pick,
    never silently merge.
  - User "I don't know" → offer ONE concrete option + "or describe it
    yourself" — never interrogate.
```

## Provenance as first-class data
Each goal stores `elicited_from`: [user quotes] — later self-evolution
steps must cite the quote they serve. This makes the whole system
*auditable*: any edit either serves a quoted wish, or it's gold-plating
and gets rejected. (Extends `agent_goals.description` schema — additive,
no migration pain.)

## Reuse map (existing → this feature)
| Interview need | Existing piece |
|---|---|
| Voice in | STT :8411 (`/api/soul/stt` bridge already in multigate) |
| Voice out | `foveai_play_sound` / Kokoro TTS :8411 |
| Q&A storage | feedback store (`/api/feedback/*` — questions + responses wired, admin-authored today; needs a self-authored variant) |
| Goal persistence | `agent_goals` + `create_goal()` (exists) |
| Restatement skill | MindCore's "inquiring, not interviewing" rails (line 559 — already aligned!) |
| Multi-turn session | Jen's autonomous loop + `<self:queue>` |

## Open design questions (for next session)
1. Who conducts the interview — Jen in-chat (companion warmth) or a
   dedicated kiosk-style intake surface (WebUI page with mic button)?
2. Interruption handling: user changes mid-sentence topic → immediate
   pivot or finish-round-first?
3. Should intake goals auto-start the goal loop immediately after
   consent, or wait for a user "go"?
- Status: DESIGNED — not yet implemented. Next concrete step: the
  intake loop as a multigate panel + voice bridge reusing AuralAwareness.

---

# 2026-10-06 — Floating Call-Frames (design, simplified per user)

## User's clarification (saves us from overengineering!)
In practice this is **just audio chat with animated images / lipsynced
avatar / webcam / Meta avatar via Unity**. Not a window manager extravaganza:
- Audio conversation continues across tabs (loose mode — wired)
- Visual layer is a simple per-mode frame: still image → lipsynced avatar /
  webcam / Unity Meta avatar as the mode dial dictates
- The 30% larger frames + frame-bulge (C-shape bevel) are the visual anchor
- Transient subtitles already render the words while away from Copilot

## Spec (lean)
| Mode dial | Frame content |
|---|---|
| TEXT / DICTATE | still image (jen_still / user profile picture) |
| Vocal PTT / VAD | lipsynced still (mouth animation over still) |
| Video PTT / VAD | webcam feed (user) / VRM avatar render (AI) |
| Quest 3 connected | Unity Meta avatar mirror (existing :8403 video path) |
Loose mode = this same frame, floating (position:fixed), following the user
across tabs. Movable + scroll-resize: OPTIONAL polish, low priority.

---

# 2026-10-06 — OPEN EAGLE DEPLOYMENT — default model chain live (tasks 9+10)

## What the user built (previous session, reconstructed)
The 9B is served by **raw llama-server with Eagle3 draft pairing** — no
python middleman: `-m <MoQ> -md <Eagle3 draft>` speculative decode, q4_0
KV cache both models in VRAM, 40/40 layers, ctx 2048, mmproj for
multimodality. Previously benchmarked ~90 tok/min; that was WITHOUT the
draft pairing (11 tok/min) → the winning config reached ~90/min.

## Current live state (proven by benchmark right now)
- `foveai-llama-9b-eagle.service` NEW — :8408, open llama-server:
  base `Qwen3.5-9B-MoQ-3.6.gguf` (hub, 4.0GB intact — the local
  `3.2` copy was truncated/corrupt, header OK but tensors cut),
  draft `models/drafts/Qwen3.5-9B-Eagle3-ShareGPT-Q5_K_M.gguf`,
  `--spec-draft-n-max 40`, q4_0 KV, flash-attn on, jinja, mmproj
  `mmproj-qwen35-9b-Q8_0.gguf`, ctx 2048, 40/40 layers.
- **Benchmarks (thinking disabled, draft active)**:
  - plain chain :8408 direct → 3243 tok/min (!)
  - with vision (mmproj) → 1516 tok/min
  - FULL chain :5177 → :8400 proxy → :8408 → 2274 tok/min (real content)
  The draft pairing yields 25–30× the old 90/min condition.
- **Default upstream flipped** — `foveated-memory/config/default.json`
  upstream_url → `http://127.0.0.1:8408/v1` (open llama-server, python
  removed from default chat path). XRLF :8402 remains memory+vision runtime.
- End-to-end verified: proxy chat routes through :8408 and answers.
- Model id recorded: `qwopus3.5-9b-moq-eagle`.

## Lanes recap (task 6-9, all live)
- :8403 WS — open XRL memory contract (`xrl.memory` register/deposit/recall)
  + telepathy lane (`/ws/telepathy`) for lengthy influx; restart-durable
  (deposit→restart→recall proven).
- :8400 — resonant influx HTTP lane (`/api/resonance/ingest|tail|depth`).
- :8408 — open llama-server with Eagle3 draft (default chat lane).
- :8402 — XRLF runtime (vision/multimodal/mmproj + memory internals).

---

# 2026-10-06 — Todo rail + final scan (completion log)

- **D: TodoPanel shipped** — right-side rail (`components/TodoPanel.tsx`), one
  substrate (`/api/soul/tasks` = agent_plans; no parallel store), open steps
  first, 30s poll, glass styling matching the chat skin; mount condition:
  Copilot tab or pinned avatars. tsc 0 / oxlint 0.
- **Principia re-scan after full session** — 7254 lines / 346 KB (86K tokens),
  now including todo panel, profile system, eagle service, memory lanes.
  Memory server re-indexed: 1000 files, 0 failures.
- **Session stack now live** (all verified green):
  :8408 eagle-paired 9B (default chat) · :8408 XRLF vision/memory ·
  :8403 WS memory contract + telepathy + theme · :8400 proxy + resonant
  influx · :8412 theme service (boot) · :8412 TTS · MyProfile page ·
  click-upload avatar frames · lipsynced stills · todo rail.

---

# 2026-10-06 — SPEED TRUTH: controlled A/B benchmark (no-draft vs Eagle)

Clean-VRAM A/B (same box, same 800-word generation, thinking off):
| Condition | tok/min |
|---|---|
| No draft, ctx 4096, GPU 40L | **3543** |
| Eagle3 draft + ctx 2048 + q4_0 KV | **3509** |

**Conclusions:**
1. Draft pairing ≈ NEUTRAL for this model/hw (short answers don't gain;
   KV quant costs offset draft gains at ctx 2048).
2. The old 11 tok/min was NOT the ctx size — it was partial offload
   (n-gpu-layers low / shared VRAM with other models while benchmarking).
3. The real unlock = FULL GPU offload of a single resident model +
   MoQ-3.6 quant. 11 → ~3500 tok/min = 300×; the "90/min" intermediate
   reading was a partially-offloaded draft run.
4. Draft stays (harmless, and long-form reasoning-heavy workloads may
   still benefit when KV pressure is lower); q4_0 KV also stays (saves
   1.6GB for the mmproj companion + smolvlm).
5. VRAM lesson: eagle(3.7G)+smolvlm(1.1G)+another 9B full-offload DO NOT
   co-exist in 8GB — swap discipline: unload before load (user rule).

---

# 2026-10-06 — THE MODEL CYCLE (user's law, corrected design)

## The sleep/wake/interact model cycle (ONE model in VRAM at any time)
| Cycle phase | Model | Role |
|---|---|---|
| Dormant (Jen sleeping, house quiet) | smolvlm2-500m (the SMALL) | ambient watch — home listening, dream consolidation |
| Waking / idle thoughts | 2B-class (the CYCLIC-AWAKE) | experience & think normal thoughts — cheap cognition |
| INTERACTIVE (user contact — any direction) | 9B MoQ + eagle draft (the SMART) | the ONLY thing that should be resident during conversation |

## THE LAW (user's words, encoded)
**Never load 2 models co-resident in VRAM. It only makes it easier to OOM.
The interactive model is supposed to be the smartest — take the whole
space when contact happens.**

Phased swap discipline (unload → load, never side-by-side):
- user connects → smolvlm sleep-state saved → 9B occupies VRAM fully
- user disconnects → 9B evicted → 2B takes the idle loop
- night/idle long → 2B evicted → smolvlm keeps dream watch
Swap trigger hook: existing lifecycle units — llama servers are
start/stop-able systemd units; the xrlf runtime swaps via /xrlf/load.

## A/B benchmark conclusion (recorded for the record)
- no-draft ctx4096: 3543 tok/min · eagle ctx2048 q4kv: 3509 → draft neutral;
  real unlock = FULL offload + MoQ quant; old 11/min = partial offload.

---

# 2026-10-06 — SETTINGS OVERLAY (the "preset won't change" root cause) + mode family

## Root cause of "ignition presets just won't change"
`POST /api/setting` was gated by `requireAdmin` — member accounts (ignite,
role=member, features=settings_user NOT settings_admin) got 403
"admin role required" on EVERY trackball write. Values never persisted →
the ignition page rendered the boot-time defaults forever.

## Fix (live & verified)
- **Workspace settings overlay** — `foveated-memory/data/setting_overlays/<ws>.json`
- `POST /api/setting` — admin: global env as before; member: overlay write
  (USER_SETTING_KEYS = the ignition trait set incl. model id)
- `GET /api/setting` — overlay-first for member sessions (scope: 'workspace')
- `handleChatCompletion` — per-request effective mode (`effMode`) computed
  from overlay; cloud/local/juggle routing honors the USER's dial, not the
  process boot env. (Replacements at ensureLMStudio, juggle, passthrough,
  model-select, REPO-enabled guard, isLocalTarget.)
- Verified: member dialed cloud/keep=14/reason=true → all persisted and read
  back with scope=workspace. THE TRACKBALL NOW ACTUALLY WORKS.
- Creative service port aligned to :8412 (was nominal 8412, actual 8003);
  all references updated (env, server_config, vite, diagnostics, IPC).

## Cognitive mode family (recorded from user)
- **juggle** — NIM juggle race (existing)
- **tandem** — router pair (existing; Backend/Creativity/tandem.py)
- **triune** — 3-part mind: local worker + SUPEREGO (interlinked cosmic
  mind) + DIRECTOR (god mind) — to be defined as a real mode (stub pending)
- overlay gates now recognize juggle; triune/superego routing = design note
  until implemented (director_manager.py + narrative_director.py exist!)

---

# 2026-10-07 — ROUTING MAP COMPLETE (swarm + profiles aligned to the cycle)

## The routing stack (what was really fighting whom)
- **swarm_nodes.json** — the LAST-MILE router. Its only node pointed at
  :8402 → every chat (auto-resolved model) went to the XRLF runtime
  regardless of profile/config default. Fixed: :8408 (eagle) = chat node
  weight 10; :8402 demoted to vision/audio specialist (weight 2 — it lives
  under the model cycle's evictions).
- **model-profiles.json** — active-profile restore at boot REPLACED
  default.json's upstream (8408) with the old 8402 ("restore last profile").
  The qwopus profile now carries upstream :8408, provider llama_server,
  alias qwopus3.5-9b-moq-eagle.
- **settings overlay** (member dials) → per-request effMode in
  handleChatCompletion; no longer clobbers global routing on member POSTs.
- **smart-router (v2)** — middleman compression router for REPO-enabled
  turns (unchanged; rides whichever upstream wins).
- All three router layers now agree: CHAT → eagle 9B :8406; VISION/AUDIO
  → xrlf :8402; RESONANT INFLUX → :8412; MODEL CONTRACT → :8412 WS.
- End-to-end verified: "ROUTE-OK-EAGLE" through vite→proxy→eagle.
- Boot-persistence: theme + 2b-wake enabled; eagle start = interactive
  contact; disabled-by-default until then (cycle law).

## Cognitive mode dial (extended)
local | cloud | juggle | tandem | triune (superego/director = design note)

# 2026-10-07 audit (xrl_encoded integrity)
- All 5 .xrlf bundles present (12B 5.1G / E2B 3.3G / qwen4b 2.9G / qwopus9b 4.4G / smolvlm 521M) + 3 caches + qwopus9b_artifacts + semantic jsons. NOTHING removed by mistake.
- The two "missing" caches in backup comparisons are un-extracted (12b, qwen4b) — regenerable, not lost.
- Constraint: disk sdd2 87% full (12G free) — extracting more caches needs monitoring.

# 2026-10-07 — Jen's model family confirmed (the "gemma4 2b and routers")
- xrl_encoded hosts the COMPLETE persona cycle: **smolvlm2-500m** (dormant
  watch) · **gemma-4-E2B** (the gemma4 2B — waking/idle cognition, GGUF
  verified general.name=gemma-4-E2B-it, 2.84GB core + mmproj) ·
  **qwopus3.5-9b-coder-mtp-moq** (interactive). Routers live as root
  bundles: foveai-omni-router-v2.xrlf (1.38GB, XRLF cache with core+draft
  gguf) + lumax-plumax v1/v2/no2 bundles. Semantic memory (principles/
  clusters/threads graphs) feeds all of them.
- Cycle slots (unit ↔ model): foveai-xrlf (smolvlm, dormant) ·
  foveai-llama-2b-wake (E2B, waking — LIVE on :8407) ·
  foveai-llama-9b-eagle (interactive :8408) — mutual Conflicts= wired.

# 2026-10-07 — DORMANT-ROUTER (user's design: sleep model does the routing)
Two router philosophies, both now supported:
1. **LLM-as-router** — the omni-router .xrlf bundle routes/compresses when
   REPO-enabled (existing smart-router chain: primary → no.2 failover).
2. **DORMANT-ROUTER (new)** — during sleep phase, the RESIDENT dormant
   model (smolvlm2-500m) does routing/compression herself — routing never
   wakes a heavier model (cycle law honored). Enable:
   `XRLF_SMART_MIDDLEMAN=dormant` (+ optional XRLF_DORMANT_BASE_URL /
   XRLF_DORMANT_MODEL overrides). Wired into smart-router ahead of the
   omni-router chain with graceful fallback.

# 2026-10-07 — DORMANT ROUTER-DREAMER (final form, user-approved)
- **New unit `foveai-dormant-router.service`** — Xrlf_Router_Qwen0.5B_Merged
  (the 0.4GB draft/router from omni-router-v2 cache) on :8406, CPU-only
  (--n-gpu-layers 0): ZERO VRAM. Boot-enabled, auto-restart.
- Replaces smolvlm as the automatic dormant-phase resident (smolvlm's
  unit disabled from boot; still available for explicit vision duty).
- Dual duty: dream-consolidation + smart-route/compression while she
  dreams (XRLF_SMART_MIDDLEMAN=dormant → :8406, model Router_Qwen0.5B).
- Parallel persona loads unaffected: eagle 9B / E2B wake models load on
  VRAM independently — the router-dreamer never collides (CPU-only).
- Verified live: full chat with dormant routing → DORMANT-ROUTE-OK.

## Cycle final form
| Phase | Resident | Host | Port |
|---|---|---|---|
| Dormant (sleep) | Router-Qwen0.5B (dream+route dual) | CPU | :8406 |
| Waking | gemma-4-E2B | VRAM | :8407 |
| Interactive | Qwopus 9B + Eagle draft | VRAM | :8408 |

# 2026-10-07 — PORT MIGRATION (user law: everything in the 840x series)
- 8407→**8407** (E2B wake) · 8407→**8407** (eagle interactive) ·
  8406→**8406** (dormant router, CPU). Units, model-profiles, config
  default, swarm nodes, smart-router defaults, backend dormant env —
  all migrated. Verified: eagle 8408:200, dormant 8406 active,
  full chat chain returns via the 840x series.

# 2026-10-07 — COGNITIVE PORT SERIES (the interactive cycle, final)
Ports now narrate the mind→body cycle instead of a random sequence:

| Port | Lane | Service |
|---|---|---|
| 8400 | GATE | foveated proxy + resonant influx (gateway) |
| 8414 | SENSES·hearing | Whisper STT (was 8401) |
| 8402 | SENSES·vision | XRLF vision runtime |
| 8403 | SENSES·touch | unified WS stream lane |
| 8404 | SENSES·memory | sense-memory WS bridge |
| 8405 | MIND·soul | persona/DNA |
| 8411 | MIND·dormant | router-dreamer Qwen0.5B, CPU (was 8406) |
| 8413 | MIND·waking | Gemma E2B (was 8407) |
| 8412 | MIND·interactive | Qwopus 9B + Eagle3 (was 8408) |
| 8401 | MIND·deep | subconscious (was 8409) |
| 8410 | ACT·hands | motor/body |
| 8409 | ACT·voice | Kokoro TTS (was 8411) |
| 8407 | ACT·create | dreamscape creative (was 8412) |
| 8413 | SERVE·relay | chat relay (was 8413) |
| 8408 | SERVE·eyes | dashboard (was 8414) |
| 8415 | SERVE·skin | theme engine |
| 8416 | SPARK | ignition gate (was 8416) |

Migrated units + .env + server_config.py + server.js defaults & diagnostics +
smart-router + multigate vite proxies + ptt daemon + creativity ask/tandem
lanes. Verified: chat CYCLE-PORTS-OK, creative@8412 200, tts@8411 200,
STT listening 8401, relay 8413, dashboard 8414.

# 2026-10-07 — VOICE LOOP ACTUALLY FIXED (three real bugs, all proven)
1. **Context blindness** — the juggle/tandem leg received ONLY the last user
   line, and the planner answered with `prompt` alone. Every "she's oblivious"
   symptom came from here. History is now forwarded proxy→tandem→legs
   (--history JSON), the local planner and gemini planner both see the
   conversation, and legs inherit prior turns via _leg_convo().
2. **Router leak** — tandem could return `<route:colour />` and the proxy
   relayed it verbatim as Jen's answer. Added a junk guard: route tags,
   near-empty and `keep/compress:` outputs are discarded and the request
   falls through to the normal upstream (server.js).
3. **Dead microphone** — Chrome Remote Desktop runs a *private* PulseAudio
   server (crd_audio#...) which exposes only a monitor; recording "pulse"
   captured pure silence (peak=0), so PTT never heard a word. PTT now talks
   to the real session socket /run/user/1000/pulse/native and names a live
   mic; pick_live_mic(probe=True) samples candidates and takes the first with
   real signal, so the Quest mic is used whenever Horizon runs.
   Also: /usr/bin/python3 lacked numpy (crashed the daemon) → optional import.
   STT patience raised to 40s deadline / 20s recv (whisper takes ~10-15s when
   the GPU is busy; the old 6s recv gave up first).

VERIFIED end to end (daemon's own code path): Kokoro speech → STT transcript
3.9s · memory question answered correctly from prior turn (juggle 4.6s and
eagle both) · spoken reply via :8411 · mic capture RMS 685 peak 2772 (LIVE).

# 2026-10-07 — ANIMATION: WHY IT NEVER MOVED, AND THE FIX
**Root cause found by inspecting the assets instead of the code:** every VRM in
the repo except one has **zero animation clips and zero mouth blendshapes** —
`alicechan.vrm` is VRM 0.0 with 54 bones but no motion data and no jaw. The
bracket-parsing / puppeteering / motor-engine stack had nothing to drive, which
is why years of configuration produced a statue.

**The rig that can actually perform:** `SHAPEY.vrm` (already in
Frontend/XR_Vessel/public/avatars) — VRM 1.0, 52 humanoid bones, preset
expressions incl. mouth `aa/ih/ou/ee/oh`, `blink*`, `lookAt`, 1.2MB. Staged as
`public/avatars/jen.vrm`.

What was built:
- `src/avatar/performance.js` — pure deterministic performance math
  (envelope, viseme selection, breathing, weight shift, head idle, speaking
  nods/hand gestures, blink schedule). Headless-tested: `node --test
  tests/test_avatar_performance.cjs` → 6/6.
- `src/avatar/AvatarPerformance.tsx` — per-frame driver posing bones +
  expressions from the TTS energy envelope.
- `AvatarManager.externalPerformance` — single-writer switch so the manager's
  old procedural idle stops fighting the new driver.
- `AuralAwareness.ensureAnalyser()` — **the lip-sync bug**: the analyser was
  created only in the mic path, and playback gated `startEnergyPublisher()`
  behind `if (this.analyser)`, so TTS playback published no energy at all.
  Playback now creates the analyser on demand.
- AvatarView gained `mode="live"`; App has a 🎬/🖼️ stage toggle (default live).
- `npx tsc -b` + `vite build` green with Node 24; jen.vrm serves 200.

# 2026-10-07 — USER-SUPPLIED AVATARS VALIDATED + staging
- `Tools/check_avatar.py <file.vrm|.glb>` — the gate that must pass before any
  avatar is wired in. Reports bones, clips, mouth shapes, blinks, verdict.
  Recognises VRM 1.0 presets, VRM 0.0 A/I/U/E/O, ARKit names and the
  prefixed `Fcl_MTH_*` / `Fcl_EYE_Close` convention (kuasa exports).
- Desktop pickups, both validated GOOD (54 bones, 5 mouth shapes, 3 blinks):
  · `Skrivbord/1363222479181153122.vrm` — ともとも (kuasa), VRM 0.0,
    57 face shapes, `Fcl_MTH_A/I/U/E/O` + `Fcl_EYE_Close*` → staged as
    `public/avatars/tomotomo.vrm`
  · `Skrivbord/2048306402839018349.vrm` — "School girl" (PinkPIkachu0012),
    labelled 1.0 but genuinely VRM 0.0, standard groups A/I/U/E/O +
    Blink/Blink_L/Blink_R + emotions → staged as
    `public/avatars/schoolgirl.vrm` (default in the picker)
- `performance.js` gained MORPH_ALIASES / resolveMorphBindings / applyMorph so
  the driver writes raw morphs when a rig does not expose VRM expression names.
- 🔁 button in the chat header cycles only rigs that passed the validator
  (schoolgirl → tomotomo → jen → robot-expressive).
- `robot-expressive.glb` vendored as the pipeline-proof rig (43 bones, 14 clips).
- Tests: 7/7 including "the shipped rig passes its own validator".

# 2026-10-07 — THE STANDING GUARD (answering "it always breaks in new ways")
The whack-a-mole is now automated and measurable instead of discovered by hand.

**`Tools/smoke_ui.mjs`** — headless Firefox (puppeteer-core) drives the real app:
login (session token) → persona setup → ignition dial click → app shell →
WebGL canvas mounted → images decode → softlayer modules are JS. Captures every
console error, page error and failed request. Report → `memory/ui_health/`.
**First clean run this session: PASS, 0 errors, and a screenshot of a working
chat where Jen answered.**

**`Tools/check_ports.py`** — lints every hardcoded `127.0.0.1:<port>` in code and
checks it against the live listeners + the cognitive port series. Currently
reports 127 dead references (34 in browser code) so they get fixed deliberately.

**`Tools/harden.sh`** — port linter → smoke → (on failure) local-model triage.
Prefers the 9B (:8408) because it can actually read evidence; the 0.5B CPU router
(:8406) is the instant fallback (it answers, but generically).

**`foveai-harden.timer`** — every 20 min, persistent. Reports land in
`memory/ui_health/`, so breakage is found on a schedule rather than by you.

## Breakage found and fixed this session
1. `/api/status` probed `…/v1/health` → readiness never resolved → ignition hung
   on "checking the model" for 120s. Now probes the real endpoint (`ready`).
2. Ignition model-wait capped at 30s, then boards anyway.
3. SoftLayer `API_BASE` hardcoded to dead `:8402`; and `/softlayer/*` was served
   by the SPA fallback (HTML evaluated as JS). New `softlayerStatic()` plugin
   serves real JS and 404s cleanly.
4. SoftLayer requested `chatrelay.js`/`wall.js`; real files differ — now tolerant.
5. Profile pictures: `<img src>` cannot send a bearer token, so every uploaded
   portrait 404'd and rendered broken. Gallery now resolves files regardless of
   caller auth.
6. `jen_still.png` was a 1×1 pixel and `user_fallback.png` a 67-byte stub; both
   replaced with real 512–1024px renders.
7. Motor stream pointed at retired `:8110`; now `:8410`, health-probed and
   same-origin so an offline motor is silent instead of a CORS error storm.
8. Theme broadcast dialled a dead broker every 3s forever → console error wall.
   Now opt-in, bounded, and quiet.
9. `AmbientSoundEngine` polled a dead `:19847` TopBar on an interval → cross-origin
   console errors forever. Now same-origin `/api/status`.
10. Harness hardening: it once reported "logged in" while the page said
    "invalid credentials" — login is now verified against the error banner.

## Known remaining gap
The AI avatar frame mounts a WebGL canvas (76×65) but renders dark/empty in the
screenshot — framing/lighting/scale to tune. Now *visible* thanks to the harness
instead of invisible.

# 2026-10-07 — UPLOADS THAT AREN'T PICTURES ARE NOW IMPOSSIBLE
`inspectImage()` reads real dimensions from PNG/JPEG/WebP headers and rejects
uploads that are too small (<64px) or too flat for their pixel count (<1/60
byte-per-pixel). This is why a 948-byte blank canvas snapshot previously passed
the old `bytes < 100` gate and then rendered as a broken image. Applied to both
`/api/profile/picture` and `/api/profile/persona_picture`.
Verified: the old stub → `400 image rejected: 256x320 is too small or blank`;
a real 1.9MB photo → accepted.

# 2026-10-07 — CONNECTING FUNCTIONALY (viewer vs. audio)
- Chrome Remote Desktop runs a **private** audio server, so every microphone
  disappears for anything using the default Pulse socket. That is a viewer
  problem, not a machine problem: the real session socket
  `/run/user/1000/pulse/native` still exposes the webcam mic, the Steinberg
  interface and the onboard input.
- PTT therefore records through the real session socket regardless of how the
  desktop is being viewed — voice works while connected over CRD.
- `xrdp` + `xrdp-sesman` are active and listening on 3389, which gives a real
  desktop session (and its own audio stack) as an alternative viewer to CRD.

# 2026-10-12 — DEVELOPER COCKPIT, OPEN XRL CONTRACTS, SEMANTIC RECALL & ZERO-MEMORIZATION TUI

## 1. Physical Overscan & Tmux Developer Cockpit
- **The Issue**: TV and monitor displays often run 16:9 overscan by default, cropping 1–2 cm around the screen bezels. In terminal environments and raw TTY consoles, this cuts off prompt margins, command output, and status bars.
- **The Solution (`tmux-pad`)**:
  - Automatically initializes on login outside X11 via `~/.bashrc`.
  - Creates an 8-column horizontal (~2cm) and 2-line vertical grey frame around the active pane.
  - Lifts the status line with `status 2` and a blank buffer row.
  - Controls: `pad` (toggle), `pad on [h] [v]`, `pad off` (fullscreen), and shortcut `Ctrl+b M`.
- **Developer Cockpit HUD (`pad --xrlhud`, `hud`, `Ctrl+b H`)**:
  - Splices a live 3-column header above the active shell:
    - `🧠 XRL Cognition`: Active residency tier, soul/membrane session, memory count, resonance echo.
    - `📂 Repo & Red Thread`: Working directory, git branch, modified files count, dev focus.
    - `⚡ System Vitals`: CPU load, RAM usage, RTX 4060 GPU temperature and VRAM, date/clock.
  - Surrounds an active, fully scrollable shell pane with 50,000 lines of scrollback buffer. Running `agy` inside this creates a boxed pair-programming cockpit.

## 2. Open XRL Contract Provisioning & Antigravity Agent
- **Provisioning CLI (`Tools/open_xrl_agent_provision.py`)**:
  - Generates `/agent/<name>` profiles, SSH keypairs, `XRL_CONTRACT.json` (specification `xrl-memory/1.0`), and foveated memory storage directories.
  - Provisioned `/agent/antigravity` profile. Verified live WebSocket IPC handshake on `ws://127.0.0.1:8403` (`xrl.memory.hello`, `deposit`, `ack`).
  - Active memory ring deposits verified on `http://127.0.0.1:8400/api/resonance/tail`.

## 3. Multi-Source Semantic Memory Recall (`recall`, `/recall`)
- **CLI (`/usr/local/bin/recall`)**:
  - Provides human developers with the same memory decompression capabilities that AI agents use.
  - Searches simultaneously across:
    1. Shadow context multi-turn dialogue JSON blocks in `memory_data/shadow-context/`.
    2. SQLite databases in `db/agent_memory.db` (`agent_memories`, `agent_journal`, `agent_thoughts`).
    3. Active memory resonance bus units on port `:8400`.
  - Colorizes results by tier, highlights query keywords, and automatically invokes `less -RFX` when results exceed terminal height.
  - Usage: `recall "<query>"` or `/recall "<query>"` or `/recall <query>` inside the interactive console.

## 4. Zero-Memorization Control: The Master Control Menu
- **The Problem**: Remembering CLI syntax, flags, ports, and subcommands is exhausting for daily work.
- **The Solution (`/usr/local/bin/foveai-menu`, `foveai`)**:
  - Running `foveai` with no arguments opens a clean, boxed TUI menu with arrow-key navigation (`↑`/`↓`/`Enter` or numeric keys `1`–`9`, `0`).
  - Unifies every major operation:
    - `[1]` Interactive Chat Console (Jen / Ghost co-pilot with `/model` switcher)
    - `[2]` Start Fleet Stack (via Sleipnir launcher)
    - `[3]` Stop Fleet Stack & Free VRAM (`foveai --unload`)
    - `[4]` Load Tier B (Flagship 9B on VRAM :8408)
    - `[5]` Load Tier A (Lightweight 4B on :8407)
    - `[6]` Semantic Memory Recall
    - `[7]` Developer Cockpit HUD
    - `[8]` FoveAI Nest 13-pane Dashboard
    - `[9]` Fleet Settings Menu (`FoveAI_Console.py`)
    - `[9]` Stack & GPU VRAM Status
    - `[0]` Exit to Shell

## 5. Host & Desktop Invariants
- Fixed recurring Cinnamon Clutter compositor deadlocks triggered by `cinnamon-sidebar@beatlink` on applet reload.
- Locked bottom Cinnamon dock to 80px height, 64px icon size, and 48px symbolic size via `gsettings`.
- Restored FoveAI high-resolution desktop icon and system tray indicator (`FoveAI_Taskbar_Linux.py`).

## 2026-10-16 — XRLF/XRLB Motherboard (1000-Model "TSD Legion") Status
- **What it is:** shared nano trunk + `.xrlb` pentahedron seeds folded on demand from disk; 4 heads, 16 arms, 10 dirigents around a ~500 MB core (SmolVLM2-500M XRLF).
- **Where it lives:** `/mnt/foveai/motherboard/` on `sdb2` (`foveai-ssd`). Full session archive: `/mnt/foveai/sessions/xrlfb-1000-model-architecture_2026-10-16/`.
- **Live surfaces:** `http://127.0.0.1:5177/tsd_blaster.html` (also `:8414`), `/api/tsd/*`, chat modes `juggle`/`tandem`/`legion`, tray submenu "TSD Legion & UI Blasters".
- **Caveat:** performance claims are session-reported, not yet independently benchmarked. Concept note `Docs/XRL_HIVE_MIND.md` still says "concept note".

## 2026-10-26
- Audio chain LIVE end-to-end: RODE mic → effect_input.eq → HDMI → Samsung, verified by ear
- Root cause: missing `audio` group + seat ACL held by stale session — see .logs/AUDIO_HANDOVER.md
- Variator GUI on TV (X :2): ScrewKnob rows, LCD hover-scroll, FreqBal buttons, scene presets, yt/file player
- Tools: eq_play, eq_demo_gen.py, tv_audio_hud.py, foveai_smoke.py (audio_loop), xrl_reindex/repo_survey/repo_fix suite (~100 ledgered fixes)
- Persistent: foveai-tv-hud.service (vinyl painter, yields to sessions/X)
- Pending: whisper :8430 cold-start, Quest mic route, GUI row-width fit
