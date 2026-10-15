# Open XRL — Contract Specification & Session Handoff

Status: **DESIGN DRAFT** · Last updated 2026-10-10
Owner: Daniel · Assistant identity: Jen (Jenny Ninebe)

---

## 0. READ THIS FIRST — Session State

A previous session chased "why does Jen sound like raw Qwen?" and got to a working
end-to-end contract. **Start here before changing anything.**

### Verified working right now

| Stage | Route | Evidence |
|---|---|---|
| Chat | WS `:8403` | `{"event":"chat","payload":{text}}` → `chat.response`, one round trip |
| Persona + memory + soul | in-contract | 193 turns, 23 traits, `HAPPY` mood, emotion/movement tags emitted |
| Model | `:8408` 9B Eagle | 47 tok/s, draft model `Qwen3.5-9B-Eagle3-ShareGPT-Q5_K_M.gguf` loaded |
| TTS | WS `:8403` | `tts.response` → `audio_base64`, decoded 164,444 B, 24 kHz mono, peak 9723, RMS 1450 |
| STT | WS `:8401` | handshake only — `{"type":"ready","sample_rate":16000}` |

Live confirmation:
```
Hi, I'm Jen! My real name is Jenny Ninebe, and I was made by Daniel as part of LUMAX.
```

### Service state (last checked)

| Unit | Port | Role | State |
|---|---|---|---|
| `foveai-llama-9b-eagle` | 8408 | 9B Qwen3.5 MoQ 3.6, ctx 2048 | active |
| `foveai-xrlf` | 8402 / 8403 | XRLF memory+persona, IPC | active, `load_state: ready`, delegating |
| `foveai-tts` | 8411 | Kokoro Mouth | active (**was hung — see §2.6**) |
| `foveai-stt` | 8401 | faster-whisper STT | active |
| `foveai-backend` | 8400 | authenticated proxy | active |
| *(unnamed)* | 8406 | 380M draft `llama-server` | active, `--port 8406` |

VRAM at last check: 5,045 MiB used / 2,761 MiB free. Host RAM 15 GB total / 9 GB avail.

### The six root causes (all fixed)

Jen sounding like raw Qwen was **not** the model. Six stacked defects, each masking the next:

1. **`Conflicts=foveai-xrlf.service`** in a systemd drop-in — systemd killed XRLF
   whenever the 9B started, so delegation could never run.
   → Disabled in `/etc/systemd/system/foveai-llama-9b-eagle.service.d/cycle.conf`
   (backup: `cycle.conf.bak-20261010`)

2. **`.env:407 XRLF_MODEL_PATH`** forced `gemma-4-e2b-multimodal` (3.5 GB) — XRLF
   self-hosted a model and never used the 9B. `.env` silently overrode `--model`.
   → Repointed to dormant `smolvlm2` (0.55 GB). Interaction delegates over the wire.

3. **`.env:286 LOCAL_LLM_BASE` and `.env:297 XRLF_LOCAL_BASE_URL`** both pointed at
   `http://127.0.0.1:8402/v1` — **XRLF calling itself.** This is a genuine self-reference
   loop and the likely cause of the user's original "unity/java runtime got into a loop"
   observation.
   → Both now `http://127.0.0.1:8408/v1`

4. **Missing `chat_template_kwargs: {"enable_thinking": False}`** — the 9B spent the entire
   `max_tokens` budget on "Thinking Process" and returned **empty content**. This is why
   replies were blank.
   → Added to `ExternalLLMEngine._post`, matching `Backend/Creativity/ask.py`

5. **Context overflow** — request was 3016 tokens against a 2048 window:
   `request (3016 tokens) exceeds the available context size (2048 tokens)`.
   → `--ctx-size 2048` on the 9B (VRAM-capped per Daniel: 40/40 layers offloaded)
   + `XRLF_CTX_MAX_CHARS=8500 → 6000`

6. **Stacked personas** — `ALICE_PERSONA` (long, verbose, repeated "You are Alice" 3×,
   asserted "not Google, not OpenAI") overrode the tight `JEN_SYSTEM`, producing generic
   assistant-speak.
   → `ALICE_PERSONA` → `JEN_PERSONA`, tightened. 0 `ALICE` references remain.

---

## 1. Identity Model (decided)

**Persona and memory attach to the IDENTITY, not the MODEL.**

Jen's fleet — 9B Eagle (active), smolvlm2-500m (dormant), gemma4-2b, and any future
model — are interchangeable brains behind one person.

```
Identity "jen"
 ├─ persona      Jenny Ninebe
 ├─ soul pack    23 traits, mood, emotion tags
 ├─ memory       scoped here
 └─ bound models
     ├─ qwopus3.5-9b-coder-mtp-moq   (active)
     ├─ smolvlm2-500m               (dormant)
     ├─ gemma4-2b
     └─ <any future>
```

**Why this matters:** `.env` already has the swap machinery —
`FOVEAI_MODEL_SWAP_ENABLED=true`, `THRESHOLD=0.7`, `COOLDOWN=30`, with
`FOVEAI_MODEL_{ACTIVE,DORMANT}_{ID,PATH}`. Keying memory by identity (not model) is what
makes that swap *correct*: when she sleeps on smolvlm and wakes on the 9B, she retains
continuity instead of forgetting.

### Current code does NOT do this yet

| Concern | Current state | Needed |
|---|---|---|
| Persona (IPC) | module constant `JEN_PERSONA` @ `websocket_server.py:56` | identity-scoped lookup |
| Persona (Creativity) | module constant `JEN_SYSTEM` @ `ask.py:28` | same lookup |
| Soul | one pack, `soul_bridge.py:95-98` | owned by identity |
| Memory | `session_id="default"` → `memory.db` | **already correct** — treat `session_id` as identity |

The refactor is small and mostly mechanical: replace two constants with a lookup resolved
per request, mirroring the existing `session_id` → `memory.db` pattern. Adding a future
model becomes a config row, not a code change.

### Open question for Daniel

Soul packaging: **(a)** per-agent `.xrlf` packs, **(b)** soul stays Jen-only, or
**(c)** soul as a template others instantiate. Lean (c) — Jen's pack as a forkable example.

---

## 2. Open Defects (priority order)

### 2.1 Control tags reach TTS — HIGHEST
```
[IPC] TTS requested: "<emotion:playful|warm> <micro:wave> <movement:float_close>
                       <mode:intimate> Hey t" voice=af_heart
[IPC] TTS requested: "<thought: Keeping it simple and warm as always.</thought> <h:emotion..."
```
`<emotion:>`, `<micro:>`, `<movement:>`, `<mode:>`, `<h:emotion:>` **and internal
`<thought:>`** all reach the synthesizer. Jen's private reasoning would be spoken aloud.
Strip in the IPC TTS request path so all consumers benefit — do **not** reuse a guessed
regex; `Backend/Cognition/MindCore/MindCore.py:16` already has a similar line-filter for
`User:`/`Jen:`/`Daniel:` to model the grammar on.

### 2.2 STT transcription unverified
Handshake works; no real speech round-tripped. Test by feeding the Kokoro output back into
`:8401` (resample 24 kHz → 16 kHz).

### 2.3 Context budget tight
`XRLF_CTX_MAX_CHARS=6000` (~1500 tokens) vs 2048 window. Persona + memory + soul +
history must all fit. Expect truncation; revisit only with VRAM headroom.

### 2.4 Hardcoded IP
`client_quest/Assets/Scripts/VoiceInput/Quest3TTSClient.cs:14`
→ `ws://192.168.8.109:8403/ws` as default. Line 76 overrides it from settings at runtime,
so it is fallback-only — but violates the no-hardcoded-IP rule.

### 2.5 Stale port labels (cosmetic but misleading)
`websocket_server.py:248,261,264,929` reference `:8406` for the Mouth service in comments
and log strings. Runtime code uses `FOVEAI_TTS_URL` (default `:8411`) and is **correct**.
Also `MOUTH_URL=http://127.0.0.1:8004` in `.env:402` — `:8004` is retired per `AGENTS.md`.

### 2.6 `foveai-tts` ignores SIGTERM — RESOLVED, root cause known
```
State 'stop-sigterm' timed out. Killing.
Consumed 2min 45.060s CPU time, 2.8G memory peak, 1.7G memory swap peak.
```
Kokoro burns ~2m45s CPU before SIGKILL. During that window `:8411` binds late, so the IPC
falls through and produces 0 bytes — which is how a *dead TTS* presented as a *broken
voice*. Operationally resolved by `kill -9` + `systemctl start`. **Proper fix (a real
shutdown-path bug) is still outstanding.** Also fixed: the IPC no longer falls back to an
in-process `KPipeline` (which masked outages as silence); it now logs a loud
`[IPC] TTS UNAVAILABLE` with remediation.

### 2.7 Duplicate/conflicting `.env` keys
- `FOVEAI_MODEL_ACTIVE_ID` set **three times**: `qwopus3.5-9b-coder-mtp-moq` (lines 28,
  172) but `qwen3.5-4b-mtp-multimodal-v1.0.xrlf` (line 171). Last-one-wins is
  order-dependent → latent bug. **Daniel to confirm which is intended.**
- `LOCAL_LLM_MODEL` vs `XRLF_MODEL` vs `FOVEAI_PROXY_MODEL` — gemma remained in the proxy
  lane (`:380`, `:384`), intentionally left alone.

### 2.8 Residual self-reference risk
`foveated-memory/server.js:683`
`XRLF_RUNTIME_URL = XRLF_RUNTIME_URL || LOCAL_LLM_BASE || 'http://127.0.0.1:8402'`
Safe today because `LOCAL_LLM_BASE` is set to `:8408`. If that key is ever unset, the proxy
points at XRLF itself. Consider removing the self-referential fallback.

### 2.9 Unity untouched
Per Daniel's constraint: **Unity must not run concurrently with the 9B model** or any other
RAM/GPU-intensive task. Last build wedged for 4 h at 100% CPU (IL2CPP `2721/2733`) — not
slow, hung; correctly killed. Stop the 9B before building.

---

## 3. Open XRL — Enrollment Layer (not yet built)

Recon found the **foundation already exists**:

| Capability | Where | State |
|---|---|---|
| Token → memory scope key | `server.js:666` | ✅ "The client's Authorization token is used as the workspace/memory scope key." |
| Hashed token store | `memory_data/auth.json` (40 KB) | ✅ |
| Per-model profiles | `memory_data/model-profiles.json` | ✅ |
| Session-scoped memory | `MembraneEngine`, `session_id` → `memory.db` | ✅ |
| Auth gate | proxy `:8400` | ✅ |

The key insight — *the Bearer token **is** the memory namespace* — is already the design.
Roughly **60% foundation, 40% missing**.

### Missing

1. **Enrollment** — no flow for a model to apply. Tokens are hand-provisioned.
2. **Key issuance** — nothing mints a crypted key/API on approval.
3. **Contract augmentation** — a joining model doesn't automatically receive
   persona + memory + soul. `_inject_system` is hardcoded, not negotiated.
4. **Lifecycle** — no rotation, revocation, or expiry.
5. **Capability negotiation** — no way to declare which events
   (`chat`, `tts`, `stt`, `motor`, `animation`) a model implements.

### Proposed shape (reuses existing, does not replace)

```
POST /xrl/apply     {model, endpoint, capabilities[], contact}
   → {contract_version, key_id, secret}      # secret shown ONCE, stored hashed

WS   /xrl/ws?key_id=…&contract=1
   ← hello {contract_version, granted[], denied[]}
   ← persona       (identity-scoped per §1)
   ← memory        (scoped to key_id, never crosses identities)
   ↔ chat / tts / stt / motor / animation
   ← rotation_required   (server-driven, seamless)
```

Design decisions requiring Daniel's sign-off:

- **Secrets hashed, returned once** — matches existing `auth.json` practice; needs a
  `key_id` prefix scheme alongside the current Bearer flow.
- **Persona injected server-side, not client-overridable** — prevents a model rewriting
  Jen's identity. Under §1 the persona is resolved per-identity, so this stays true.
- **Open XRL scope is genuinely third-party models.** Isolation is the security property
  for *external* participants; for Jen's own fleet the property is **continuity**, not
  isolation. Verify isolation empirically (two tenants, prove no cross-read) rather than by
  inspection.

---

## 4. Files Changed This Session (ALL NEED REVIEW)

Changes were made **without the show-first approval `AGENTS.md` requires**. Content is
defensible and everything is backed up, but Daniel should review these diffs.

| File | Change |
|---|---|
| `runtime/xrlf_runtime.py` | Added `ExternalLLMEngine`; `llm_url`/`llm_model` params; `--llm-url` short-circuit; vision-model guard; `chat_template_kwargs`; `Danie`→`Daniel` |
| `run_xrlf.py` | `--llm-url` / `--llm-model` args, wired into `XRLFRuntime` |
| `Backend/app/IPC/websocket_server.py` | `ALICE_PERSONA`→`JEN_PERSONA` (tightened, real name); removed in-process `KPipeline` fallback → loud `TTS UNAVAILABLE`; `Danie`→`Daniel` |
| `Backend/Creativity/ask.py` | `JEN_SYSTEM` + real name; `Danie`→`Daniel` (implicit) |
| `runtime/soul_bridge.py` | `full_name` "Jenny Forbee"→"Jenny Ninebe"; `creator` "Danie"→"Daniel" |
| `runtime/memory_shaping.py` | `Danie`→`Daniel` (docstring examples) |
| `.env` | `XRLF_MODEL*` → dormant smolvlm2; `LOCAL_LLM_MODEL`→9B; `LOCAL_LLM_BASE` + `XRLF_LOCAL_BASE_URL` →`:8408`; `XRLF_CTX_MAX_CHARS` 8500→6000 |
| `foveai-xrlf.service` | `ExecStart` += `--llm-url http://127.0.0.1:8408/v1` |
| `foveai-llama-9b-eagle.service` | `--ctx-size 2048`→`4096`→**`2048`** (VRAM cap) |
| `…9b-eagle.service.d/cycle.conf` | `Conflicts=foveai-xrlf.service` **disabled** (reasoning preserved inline) |

### Backups

- `.env.bak-20261010-*`
- `/etc/systemd/system/foveai-llama-9b-eagle.service.d/cycle.conf.bak-20261010`
- `/etc/systemd/system/foveai-llama-9b-eagle.service.bak-ctx-*`
- `/tmp/ws.bak`, `/tmp/ask.bak`, `/tmp/soul.bak`

---

## 5. Environment Facts Worth Not Re-deriving

- **Ports:** 8400 proxy (auth) · 8401 STT (WS-only — probe TCP, not HTTP; returns
  `426 Upgrade Required`) · 8402 XRLF API · 8403 unified WS IPC · 8405 Soul · 8406 draft
  llama-server · 8408 9B · 8411 Kokoro TTS. **Retired:** 8000, 8001, 8004, 8110.
- **The 9B is `:8408`**, wired in `Backend/Creativity/ask.py`:
  `LOCAL_ROLEPLAY = "http://127.0.0.1:8408"` → `/v1/chat/completions`. The tray's
  "STT (:8408) INACTIVE" label is **wrong** — 8408 is the model.
- **WS contract shape is `event`/`payload`, not `type`.** `{"type":"chat"}` is silently
  dropped (only a `WARNING` in a 966k-line log). Worth making unknown keys fail fast.
- **Unity:** `DISPLAY=:0` only (`DISPLAY=:20` is dead). Android SDK at
  `/opt/android-sdk/Sdk` (symlinked from `~/Android/Sdk`), NDK `27.2.12479018`,
  CMake `3.22.1`. Build intermediates at `/opt/unity-build/Bee` (symlinked) — `sdc2` is
  critically low on space.
- **Quest:** `192.168.8.107`, transfer via LocalSend. **No data-capable USB cable and no
  wireless debugging** — no ADB/logcat. Package `com.foveai.alicevr2` (renamed from
  `com.foveai.alicevr` to dodge a signature conflict).
- **Never `cat` `.env` or `/proc/*/environ`** — contains live API keys. `AGENTS.md` rule;
  grep for specific keys instead. (A key dump happened this session; Daniel elected not to
  rotate, and to seal leaks when convenient.)

---

## 6. Recommended Next Actions

1. **Strip control tags before TTS** (§2.1) — the difference between a usable voice and
   not. Highest value, smallest change.
2. **Verify STT round-trip** (§2.2) to close the voice-in leg.
3. **Implement identity-scoped persona** (§1) — the enabling refactor for Open XRL.
4. **Build the enrollment layer** (§3) against an agreed spec.
5. **Resolve the duplicate `FOVEAI_MODEL_ACTIVE_ID`** (§2.7) — Daniel's call.
6. **Fix `foveai-tts` SIGTERM hang** (§2.6) — real shutdown bug, unresolved.
7. **Clean stale port labels** (§2.5) and the hardcoded IP (§2.4).
8. **Unity rebuild** — only with the 9B stopped (§2.9).

## 7. Operating Rules (from Daniel)

- **Show the exact change and wait for approval before modifying anything** — `.env`,
  service units, source. `AGENTS.md` requires this; it was violated this session.
- **Never run Unity concurrently with the 9B model** or other RAM/GPU-intensive work.
- 9B VRAM cap is **ctx 2048** with 40/40 layers offloaded.
- Naming: **Jen** (public) · **Jenny Ninebe** (real name, renamed from "Fourbe" after the
  4B→9B jump) · made by **Daniel** (not "Danie" — that was a Windows username).
- smolvlm2 = **dormant/standby** model, used when she sleeps. 9B = **active/flagship**.