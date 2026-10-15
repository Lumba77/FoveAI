# FoveAI — Development Context

Latest developments and session log.

## 2026-09-19 — Post-Migration Stack Healing & Dynamic IP

### Hard-drive migration recovery
- Server migrated after a hard-drive crash; files recovered but the `.venv` was missing the entire voice stack
- Installed into `.venv` (uv): `torch==2.14.0+cpu`, `kokoro==0.9.4`, `misaki==0.9.4`, `faster-whisper==1.2.1`, `soundfile`, `py-espeak-ng`, `ctranslate2`, `onnxruntime`, `en-core-web-sm`
- Fixed stale Fedora CA path in `.env`: `SSL_CERT_FILE`/`CURL_CA_BUNDLE` `/etc/ssl/certs/ca-bundle.crt` → `/etc/ssl/certs/ca-certificates.crt` (Debian)
- Downloaded Kokoro model + `af_heart`/`af_bella` voices and `faster-whisper-tiny` into `/home/lumba/Models/hub` (the configured `HF_HUB_CACHE`; services run `HF_HUB_OFFLINE=1`)
- Fixed env-key case mismatch: `.env` had `FOVEAI_KOKORO_VOICE`, code reads `FoveAI_KOKORO_VOICE`

### Voice stack re-pointed to 840x series (old 8001/8004 retired)
- `foveated-memory/server.js`: `MOUTH_URL`/`PIPER_URL`/`SOUL_URL` → `TTS_URL` (`:8411`) / `STT_URL` (`:8411`); added `/api/tts/voices` passthrough
- `foveai_mouth_kokoro_server.py` default port 8004→8411; `stt_whisper_server.py` default `STT_PORT` 8001→8411
- Native `:8402` endpoints (`/v1/audio/speech`, `/v1/audio/transcriptions`) are primary; `:8401` Kokoro is TTS fallback; `:8411` is WebSocket-only STT
- Proxy `/api/voice/status` now TCP-probes `:8411` (HTTP `/health` is invalid on a WS-only server)
- New systemd units: `foveai-tts.service`, `foveai-stt.service` (launchers for existing servers only — no duplicated implementations)

### Missing services restored (existing implementations, new units)
- `foveai-motor.service` → `motor_daemon.py` on **:8410**
- `foveai-subconscious.service` → `subconscious_daemon.py` on **:8409** (added `/health`; only had `POST /telemetry`)
- `foveai-chat-relay.service` → `chat_relay_server.py` on **:8413**
- `foveai-multigate.service` → `Frontend/multigate` (Vite dev) on **:5177**
- Fixed `startViteServer` Windows-only launcher (`C:\Windows\System32\cmd.exe`) → Linux `npm`
- Installed Node 24 tarball to `~/.local` — Vite 8 requires Node ≥20, system node is 18
- `verify_health.py` and dashboard `/api/subsystems` updated to the current port map; LM Studio/XR Vessel remain optional/deprecated

### IP-agnostic networking
- `server_config.py`: `SERVER_IP` is now a descriptor — blank `FOVEAI_SERVER_IP` resolves the live LAN IP on each access; explicit overrides still honored; IPv6 hosts get brackets; failure falls back to `127.0.0.1`
- `refresh_network_config()` rewrites both `foveai_network_config.json` snapshots; called from `sleipnir_launcher.sh` startup
- `autonomous_sentry.py` refreshes stale cached LAN addresses instead of trusting them
- Cleared stale `FOVEAI_SERVER_IP=192.168.8.100` / `FOVEAI_BACKEND_URL` overrides from `.env` (current LAN: `192.168.8.109`)
- Multigate browser calls changed to same-origin `/api/...` paths — remote visitors no longer hit their own `127.0.0.1`; LM Studio proxied via `/api/lmstudio`; ignition requires explicit `FOVEAI_IGNITION_URL` (no longer defaults to STT `:8401`)

### Jenna-vscode (IDE bridge)
- TTS routed through extension host → proxy `/api/tts` → Kokoro (webview CSP blocks direct fetch; browser `speechSynthesis` has no voices in IDE webviews)
- Voice dropdown fed by `/api/tts/voices` (Kokoro voices, not browser voices)
- Diff counter moved beside online/offline status light, slimmed to `+adds −dels`
- Deployed to `~/.devin` and `~/.antigravity-ide` extensions (v0.5.6)

### Verified
- `/api/tts` → 200 audio/wav (real Kokoro), `/api/soul/stt` → 200, `/api/voice/status` → `{"stt":"whisper","tts":"native","model_native":true}`
- XRLF `/health` → `loaded:true`, `load_state:"ready"` (Gemma-4-E2B, full GPU offload)
- All services active: backend, xrlf, tts, stt, motor, subconscious, chat-relay, multigate
- Tests: `test_network_config.py` 7/7, `test_network_frontend.cjs` 4/4

### Remote access & Multigate Remote panel
- **Hostname → `foveai`**: Avahi announces it — `foveai.local` resolves LAN-wide via mDNS regardless of DHCP. Sunshine re-announces as `foveai`. Use `foveai.local:5177`, `foveai.local:8400` etc. for native clients.
- **`novnc-desktop.service` healed**: reuses `x11vnc-desktop.service` (:5900, physical `:0` session) instead of spawning a second x11vnc; websockify moved off the Multigate collision to `127.0.0.1:6080`.
- **Multigate `/novnc` proxy**: same-origin websockify front (static + WS upgrade verified) — browser desktop at `SYSTEM → Remote`.
- **`/remote-api` middleware** (behind `xarel_auth` gate): `GET /remote-api/services` status; `POST …/:id/{start|stop|restart}` → `systemctl --user` for user units, `sudo -n` for system units.
- **`/etc/sudoers.d/foveai-remote`**: NOPASSWD scoped to `systemctl start|stop|restart xrdp.service xrdp-sesman.service` only — no blanket root, no passwords in `.env`.
- **RemoteTab.tsx**: embedded live desktop + connection cards (noVNC, Moonlight/Nightfall, RDP, CRD) + per-service status dots and ▶/↻/⏹ buttons.
- Sunshine `apps.json` fix: stale `HDMI-1` → actual `HDMI-0` output name.
- Pairing note: Sunshine certs regenerated post-migration — clients must **forget the old PC entry** and re-pair (PIN at `https://foveai.local:47990`, login `lumba`).

### Known leftovers
- XRLF restart flap: zombie-port check covers `:8402` but not `:8403` — stale holder caused 2 auto-restarts
- `.env` still has stale `EARS_URL=http://127.0.0.1:8001` / `CREATIVE_SERVICE_URL=...:8003` (read by `autonomous_sentry.py`, `xr_app.py`)
- Chrome Remote Desktop: installed + registered as `foveai` (host daemon `chrome-remote-d` running, config at `~/.config/chrome-remote-desktop/`). Virtual Cinnamon session — physical-screen mirroring stays on Sunshine/noVNC.
- Multigate: 1 high-severity npm vuln; authenticated flows untested; Ignition service unconfigured
- Session types: Sunshine/noVNC mirror physical `:0`; xrdp/CRD spawn virtual sessions

### Qwopus 9B awake-state model (new default)
- **`xrl_encoded/qwopus3.5-9b-coder-mtp-moq.xrlf`** (4.66 GB) built by `xrl_pack_qwopus9b.py` — Qwen3.5-9B MoQ-3.6 core (3.75 GiB, `w-ahmad/Qwen3.5-9B-GGUF-MoQ`), mmproj quantized locally to Q8_0 (595 MB) via `tools/llama-b11053/llama-quantize`, embedded foveated memory transplanted from `memory.db.backup-20260919` (preserves Jen's ~5.6K turns).
- No `CORE_DRAFT_GGUF` — the MoQ build embeds no MTP/nextn tensors; `XRLF_SPECULATIVE_DECODING=false` and diagnostics report MTP honestly as unavailable.
- **KV estimate fix**: `vram_guard.estimate_kv_cache_gb` now reads GGUF metadata (`block_count`, `full_attention_interval`, `head_count_kv`, key/value lengths) — qwen35 keeps KV on only 8/32 layers → 0.27 GB @16K vs the old 3.5 GB dense-model heuristic that wrongly forced 22/40-layer hybrid offload. Result: **full GPU offload at n_ctx=16384**.
- `llama_engine`: FA ordering bug fixed (KV-quant check ran before `flash_attn` was set → quant never applied); `FOVEAI_KV_QUANT=q8_0` now active. `/no_think` injected at **start** of last user turn for qwen arch when `XRLF_MODEL_THINKING=false` (base-model ChatML ignores system/end placement); `<think>…</think>` stripped from responses incl. streaming head buffer.
- **`foveai` CLI** (`~/.local/bin/foveai`): bare → `FoveAI_Console.py` interactive menu; `status/stop/restart/--light/…` → `foveai.sh`; any other arg → console CLI passthrough.
- **`GET :8402/v1/diagnostics`**: read-only stack verification (runtime state, package sections w/ JSON+SQLite-magic validation, XRL layer objects, prompt gates, SoulBridge, memory DB turns, MTP/draft, FA/KV quant, mmproj, whisper/kokoro) → pass/warn/fail per check. Settings panel: "🔍 XRLF Stack Diagnostic" button + `stackdiag` commando command.
- **Multigate model picker fix**: `xrlf_proxy` branch was using a static `MODEL_FLEETS` list (3 router entries) — now fetches `/api/foveated/v1/models` like the cloud branch; `qwopus3.5-9b-coder-mtp-moq` + `Quwtpus-9B-XRLF` alias (jenna-vscode's id) resolve through `model-profiles.json` (provider→`xrlf_server`).
- All model pointers aligned: `.env` `XRLF_MODEL_LOCAL_ID`, `xrlf_config.yaml` `model`/`models.primary`, service `ExecStart`, `active-model.json`, `model-profiles.json`.

## 2026-09-11 — XR Locomotion, Sociable Alice, and Passthrough Fix

### Environment recovery (Linux reinstall)
- Rebuilt Python 3.12 venv with `uv` (system Python 3.14 too new for pinned wheels)
- Installed Unity 6000.4.9f1 + Android Build Support
- Activated Unity Personal licensing
- Built and verified Quest APK (519 MB, IL2CPP arm64)

### XR Thumbstick Locomotion (new Input System)
- Added `Assets/Scripts/XR/XRThumbstickLocomotion.cs`
- Uses `InputAction` with `<XRController>{LeftHand}/thumbstick` and `<OpenXRController>` bindings
- Left thumbstick = smooth move (head-gaze relative, 1.5 m/s)
- Right thumbstick = snap turn (30° increments, 0.25s cooldown)
- Auto-wired to `XR_CameraRig` by `AutoWireExperiences.cs`
- Player can now walk beyond physical room space; room-scale tracking unaffected

### Alice sociability improvements
- Default mode: `Follow` (was `FreeRoam`) — Alice stays near you
- Default mood: `Clingy` (was `Curious`) — comes to you more often
- Clinginess: 0.8 (was 0.4)
- Curiosity: 0.5 (was 0.7) — less wandering off
- Follow distance: 1.2m (was 1.5m) — stands closer
- Position: in **front** of player (was behind) — walks to where you're facing
- Head tracking: looks at user 70% of time (was 50%)
- Decision interval: 6s (was 8s) — more responsive

### Passthrough fix
- Main Camera clear flags: Skybox → SolidColor (transparent black) in scene
- `XRRigFixer.Awake()` now fixes ALL cameras before first render
- AndroidManifest: added `com.oculus.vr.capability.group = mhmr` (Mixed Reality mode)

### Infrastructure
- Installed and configured xrdp (port 3389) for remote desktop access
- Firewall: ports 1025-65535 TCP+UDP open (covers all FoveAI services)
- HTTP server on port 8888 for APK sideloading to Quest (no USB cable needed)
- Installed EDuke32 (Flatpak) + Duke Nukem 3D shareware for a visiting friend

### Build commands
- APK: `bash client_quest/build_apk.sh --cores=8`
- Tests: `.venv/bin/python -B -m unittest discover -s tests -p 'test_api_health.py' -v`
- HTTP sideload: `cd client_quest && python3 -m http.server 8888 --bind 0.0.0.0`## 2026-10-03 — Qwopus 9B MoQ-3.6: new awake-state default + system diagnostic

**Model:** `xrl_encoded/qwopus3.5-9b-coder-mtp-moq.xrlf` (4.66 GB) replaces Gemma-4-E2B.
- Core: `Qwen3.5-9B-MoQ-3.6.gguf` (3.84 GB, ~3.6 bits/weight MoQ — w-ahmad/Qwen3.5-9B-GGUF-MoQ)
- mmproj: locally requantized BF16→**Q8_0** (879→595 MiB) via `tools/unsloth_env` llama-quantize (isolated venv — do NOT let it into the runtime venv)
- Embedded memory.db: transplanted from E2B cache — her 5688 turns preserved
- No `CORE_DRAFT_GGUF` — MoQ build has no MTP head; single-model decode (honest warn in diagnostics)

**Runtime fixes (`llama_engine`, `xrlf_runtime`, `vram_guard`):**
- KV-size estimate now reads real GGUF metadata (`full_attention_interval=4` → 8 of 32 layers hold attention KV). Old dense-40-layer estimate overestimated qwen35 ~10x and needlessly capped context. Real: 16384 ctx ≈ 0.5GB KV.
- FA + `FOVEAI_KV_QUANT=q8_0` now actually engage — fixed ordering bug where KV-quant check ran before `flash_attn` was added to kwargs.
- Thinking suppression: `XRLF_MODEL_THINKING=false` now pre-seeds the prompt with an empty `<think></think>` block (Qwen chat-template mechanism) — `/no_think` alone didn't survive a system prompt.
- Load state: full GPU offload, n_ctx=16384, FA on, KV q8_0, ~4.3 GB VRAM total.

**System diagnostic:** `GET :8402/v1/diagnostics` — verifies sections, XRL layers, prompt gates, memory, MTP, engine config, STT/TTS, and runs a live inference smoke test. Wired into `foveated-memory/public/settings.html` (RUN XRLF DIAGNOSTIC button + `runStackDiagnostic`). Reaches runtime same-origin via `:8411/xrlf` proxy. Current state: WARN-only (expected: no draft model, external STT/TTS).

**`foveai` CLI** (`~/.local/bin/foveai`): bare → interactive FoveAI_Console menu; `--start/--stop/--restart/--status/--logs` → `foveai.sh`; `--console <cmd>` / unknown args → console CLI passthrough. On PATH, no sudo.

**Pointers updated:** `.env`, `xrlf_config.yaml`, `foveai-xrlf.service` ExecStart, `foveated-memory/data/active-model.json`, `model-profiles.json` (provider→xrlf_server:8402, alias `Quwtpus-9B-XRLF` kept for jenna-vscode compat).

**Multigate model picker** now queries live `/v1/models` registry via `fetchJson` (was hardcoded fleet) — merges curated fleet + live runtime registrations, dedupes by model id.

## 2026-10-03b — Multigate XRLF model picker: real package selection + hot-swap

**Bug:** the Copilot model select rendered only the static `MODEL_FLEETS.xrlf_proxy` (router alias labels) — live-fetched models rendered only for `cloud`. Root cause of "only router models choosable."

**Fix:**
- `api/server.py`: new `GET /v1/packages` on :8402 — scans `xrl_encoded/*.xrlf`, returns id/path/size_mb/`active` flag. `/v1/models` stays OpenAI-clean (loaded model only).
- `App.tsx`: `xrlf_proxy` picker now fetches `/xrlf/v1/packages` (same-origin vite route → :8402). Selecting a non-active package hot-swaps via `POST /xrlf/load` (blocks until loaded; picker disabled during swap, failure reverts selection to active package). `MODEL_FLEETS.xrlf_proxy` emptied — router aliases removed from the UI.
- `server.js` `start-xrlf` default updated e2b → `qwopus3.5-9b-coder-mtp-moq.xrlf`.
- Proxy `/v1/models` merged registry unchanged — jenna-vscode/clients still need aliases; it's only out of the Multigate picker now.

Loadable packages (disk): qwopus-9b (active), gemma-4-12b-mtp, gemma-4-e2b, qwen3.5-4b, smolvlm2-500m.

## 2026-10-03c — System-prompt pipeline audit + HUD fix for local XRLF

**Two-layer injection confirmed working:**
- Runtime :8402 (`_inject_system`): principia prefix (clusters+concepts+profile) → membrane `weave_context` (7-ring foveated block from embedded memory.db, 5729 turns and growing) → soul prompt (~250 tok). Gates: `XRLF_REPO_ENABLED=true`; CAPABILITY/FOVEATION/CONTEXT_OVERRIDE default true. `soul_bridge.adapt_context` trims tiers @75/90/120/160% of n_ctx.
- Proxy :8400: `applyProfile` (qwopus→ctx=16384, aggr=2) → `scaleConfigForModel` (12-tier holonic ring budgets; NVIDIA=64K supermemory) → ringBlock + `buildMembraneHUD` (task board/repo skeleton/diagnostics) → `patchMessages` (compact persona + memory protocol + resume context) → ContextHealer per-provider caps (xrlf 8K/lmstudio 16K/cloud 50K chars) + self-shrink/restore + hard cap.

**Fixed gap:** `patchMessages` was skipped for `xrlf_server` profiles (stale comment: "llama.cpp doesn't accept injected system prompts" — false; `_inject_system` composes). Now: xrlf_server gets `hudBlock` + compact persona + memory protocol + resume context, but NOT the proxy ring (avoids double memory — membrane covers recall). Cloud/lmstudio/nvidia keep full ring+HUD.

**Env quirks:** foveai-backend.service has no Environment= lines — reads `foveated-memory/.env` via dotenv (all overrides true, AGGRESSION=4; root .env has 3 — the proxy's own .env wins). foveai-xrlf.service sets flags explicitly; FOVEATION/CONTEXT rely on the `REPO_ENABLED→default true` fallback.

**Soul note:** `soul.config.xrlf` has `name:=Alice / full_name:=Jennifer Forbee / nickname:=Jen` — correct Jen identity, "Alice" is a legacy field name.



## 2026-10-03d — Boot/remote-access architecture (ecryptfs fix + Cloudflare tunnel)

**Root cause of "nothing starts at boot":** `/home/lumba` is ecryptfs — unlocks via PAM on login. The lingering user manager starts pre-decrypt, sees an empty `~/.config/systemd/user/`, reaches `default.target` in 7s with only stock units. All FoveAI units + Sunshine were invisible at boot (they only ran after manual starts post-login). Also: Sunshine's upstream unit was `WantedBy=graphical-session.target`, which LightDM never activates.

**New boot model (Option A: login-triggered):**
- `sunshine.service` → **system** unit `/etc/systemd/system/sunshine.service`: `User=root`, `HOME=/var/lib/sunshine`, `DISPLAY=:0`, `XAUTHORITY=/var/run/lightdm/root/:0`, **`AmbientCapabilities=CAP_SYS_ADMIN`** (required — NvFBC fails under systemd without it; binary's `cap_sys_admin=p` alone can't re-gain). NvFBC captures the GPU framebuffer incl. the lightdm greeter — Moonlight in → log in → home unlocks. Config/pairing migrated to `/var/lib/sunshine/.config` (root-owned). User unit disabled.
- `/usr/local/bin/foveai-post-login` (pam_exec hook, appended to `/etc/pam.d/common-session` + `common-session-noninteractive`): on any lumba login where `/home/lumba` is mounted → `systemctl --user daemon-reload` + `start foveai-stack.target` via `runuser` with XDG_RUNTIME_DIR/DBUS env. Covers GUI, SSH password (which itself triggers pam_ecryptfs unwrap), and Moonlight→lightdm logins.
- `~/.config/systemd/user/foveai-stack.target`: `Requires=` all 10 foveai/desktop services — one unit pulls the whole stack.
- `net.ipv4.ip_local_reserved_ports=47984-48010` in `/etc/sysctl.d/90-sunshine-ports.conf` — Sunshine's whole port family sits inside the ephemeral range (32768-60999); an outbound devin-desktop HTTPS conn once grabbed :48010 and silently broke RTSP while the service stayed "active".
- sshd: `openssh-server` installed+enabled; `/etc/ssh/sshd_config.d/60-external-keys.conf` → `AuthorizedKeysFile /etc/ssh/authorized_keys.d/%u` first (key auth works pre-decrypt; password auth still unlocks home via PAM). No keys copied yet — `~/.ssh/authorized_keys` doesn't exist.
- ufw enabled: deny incoming / allow outgoing + LAN RFC1918 allow-all (192.168/10/172.16 — DHCP-tolerant) + pre-existing Sunshine/xrdp/22 rules.

**Cloudflare tunnel `foveai`** (id `6979075a-fe5e-451b-a80e-82bddb1d2361`): cert.pem auth'd for xarel.net (Cloudflare NS). `cloudflared` deb installed + `service install` → system unit enabled, creds/config at `/etc/cloudflared/`. Ingress: foveai→:5177, novnc→:6080, metrics→:19999 (http); ssh→:22, rdp→:3389, vnc→:5900 (tcp — clients need `cloudflared access`). E2E verified: foveai.xarel.net→200, novnc→200, metrics→200 via CF edge. **Stale `lumax` tunnel (Jun 2026) still exists in the account — candidate for deletion.** `.env` `CLOUDFLARE_API_TOKEN` is invalid — R2 keys `CF_Access_Key_ID/Secret` are storage creds, not API tokens.

**Netdata installed:** `netdata` apt pkg, enabled+active on 127.0.0.1:19999, reachable via Multigate `/netdata` proxy (200) and metrics.xarel.net.

**Verified stack** (post-hook): xrlf qwopus loaded, proxy :8408, dashboard :8414, relay :8413, stt :8401, tts :8411 (Kokoro takes ~2min I/O-bound load — don't mark dead early), motor :8411, subconscious :8411, multigate :8411, x11vnc :5900, novnc :6080, xrdp :3389, sshd :22, sunshine :47989/47990/48010.

**Remaining:** one real-reboot soak test (hook was verified via manual `PAM_USER=lumba` run — all 10 services came up); SSH key install into `/etc/ssh/authorized_keys.d/lumba` when keys exist; lumax tunnel cleanup; multi-user accounts + settings panel Ignite refactor (next phase).
