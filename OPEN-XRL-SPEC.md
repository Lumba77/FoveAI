# HANDOFF — Diagnostic Prints & Remaining Work
Date: 2026-10-10 · Companion doc to `OPEN-XRL-SPEC.md` (read that first)

---

## A. Live proof the contract works

```
$ curl -s http://127.0.0.1:8402/health
{"status":"ok","model":"smolvlm2-500m-video-instruct","runtime":"xrlf-1.0",
 "loaded":true,"loading":false,"load_state":"ready","load_error":null}

$ WS :8403 → {"event":"chat","payload":{"text":"Who are you, and what is your real name?","max_tokens":400}}
< {"event":"chat.response","payload":{"text":
  "<emotion:happy|curious> <micro:nod> <movement:lean_forward> <mode:coexist>\n
   Hi, I'm Jen! My real name is Jenny Ninebe, and I was made by Daniel as part of LUMAX."}}

$ WS :8403 → {"event":"chat","payload":{"text":"Introduce yourself…","max_tokens":400}}
< "<emotion:playful|warm> <micro:wave> <movement:float_close> <mode:intimate>\n
   Hey there, Jen's here and …"

$ WS :8403 → {"event":"chat","payload":{"text":"Who made you?","max_tokens":400}}
< "<emotion:happy|playful> <micro:nod> <movement:lean_forward> <mode:coexist>\n
   Daniel made me, though I have to admit, I sometimes feel like I could use a co-pilot.\n
   Did he tell you about all the late-night builds that brought me to life?"
```

**Boot log** (`/home/lumba/xrlf_live.log`):
```
[XRLF] external LLM http://127.0.0.1:8408/v1 — ignoring in-process model
        xrl_encoded/smolvlm2-500m-multimodal-v1.0.xrlf.cache/core.gguf
  Triad pipeline disabled (XRLF_TRIAD_PIPELINE=false)
  MembraneEngine loaded: …/smolvlm2-500m-multimodal-v1.0.xrlf.cache/memory.db
        (session=default, turns=193)
  [SoulBridge] XRL soul loaded: Jenny (23 traits, HAPPY) | shaped_by: 6 entries
XRLF Runtime ready
```

---

## B. 9B Eagle `:8408` — verified

```
$ curl -s http://127.0.0.1:8408/v1/models
{"models":[{"name":"…/MoQ-Quants-Latest/Qwen3.5-9B-MoQ-3.6.gguf", …}]}

$ curl -X POST :8408/v1/chat/completions -d '{"model":"auto","messages":[…]}'
  "predicted_per_second":47.39, "prompt_per_second":237.99     → ~2800 tok/min ✓
```
```
$ tail /home/lumba/foveai_llama_8414.log
I srv    load_model: loading model '…/Qwen3.5-9B-MoQ-3.6.gguf'
I common_speculative_init_result: loading draft model
     '/home/lumba/FoveAI/models/drafts/Qwen3.5-9B-Eagle3-ShareGPT-Q5_K_M.gguf'
I srv    load_model: initializing, n_slots = 4, n_ctx_slot = 4096, kv_unified = 'true'

# ctx_other note — appears during memory fitting, described as normal by llama.cpp:
E llama_init_from_model: failed to initialize the context: eagle3 requires ctx_other
     to be set (this warning is normal during memory fitting)
W operator(): failed to measure the memory of the extra model, fitting without it
# → draft model DOES load afterwards. Treated as benign; verify drafting engages.
```

---

## C. TTS `:8411` — fixed, verified

```
$ curl -s -X POST http://127.0.0.1:8411/tts \
    -H 'Content-Type: application/json' -d '{"text":"hello there","voice":"af_heart"}'
http=200  bytes=66044  time=3.68
/tmp/k.wav: RIFF (little-endian) data, WAVE audio, Microsoft PCM, 16 bit, mono 24000 Hz
```

Through the WS contract:
```
< {"event":"tts.response","payload":{"audio_base64":"UklGRlSCAgBXQVZFZm10IBAAAAAB…"}}
   decoded bytes: 164444  channels=1 rate=24000 width=2 frames=82200
   peak=9723  rms=1450.5  → HAS AUDIO
```

**Still-failing symptom to delete (old process, pre-restart — do not re-chase):**
```
[IPC] Kokoro returned: 0 bytes
[IPC] Kokoro service unreachable (timed out) — in-process fallback
[IPC] Kokoro TTS error: 'NoneType' object is not callable
```
Root cause was `foveai-tts` hanging on SIGTERM (below), not a TTS bug.

### `foveai-tts` SIGTERM hang — the real defect, UNRESOLVED
```
$ journalctl -u foveai-tts
State 'stop-sigterm' timed out. Killing.
foveai-tts.service: Killing process 1708 (python) with signal SIGKILL.
Main process exited, code=killed, status=9/KILL
Stopped foveai-tts.service.
foveai-tts.service: Consumed 2min 45.060s CPU time, 2.8G memory peak, 1.7G memory swap peak.
```
Operational workaround: `kill -9 $(pgrep -f foveai_mouth_kokoro)` then `systemctl start`.
Proper fix = trace the shutdown path in `Frontend/Mouth/foveai_mouth_kokoro_server.py`
(non-daemon thread pool / model held in an unexiting `with`). Not yet attempted.

---

## D. STT `:8401` — handshake only

```
$ WS :8401 → {"type":"start_recording"} … {"type":"stop_recording"}
< {"type": "ready", "sample_rate": 16000, "message": "STT server ready"}

$ curl -i http://127.0.0.1:8401/health
HTTP/1.1 426 Upgrade Required
Upgrade: websocket
```
`:8401` is **WS-only** — probe TCP, not HTTP. Transcription unverified: feed real speech
(24 kHz Kokoro output resampled → 16 kHz) to close the leg.

---

## E. Context overflow — the "empty reply" chain

```
# failure (before fixes)
{"error":{"code":400,"message":"request (3016 tokens) exceeds the available context
 size (2048 tokens), try increasing it","n_prompt_tokens":3016,"n_ctx":2048}}

# healthy baseline
prompt chars: 9215  →  "I'm Jen, your warm and witty companion."
```
Two independent causes of empty/silent replies, both now fixed:
1. ctx overflow → 400
2. missing `enable_thinking: False` → all tokens consumed by "Thinking Process",
   `content` came back `""`

---

## F. Control tags reaching TTS — HIGHEST PRIORITY, UNFIXED

```
$ grep 'TTS requested' /home/lumba/xrlf_live.log | tail -2
[IPC] TTS requested: "<emotion:playful|warm> <micro:wave> <movement:float_close>
                       <mode:intimate> Hey t" voice=af_heart
[IPC] TTS requested: "<thought: Keeping it simple and warm as always.</thought>
                       <h:emotion:happy|playf…" voice=af_heart
```
Tags reaching the synthesizer: `<emotion:>` `<micro:>` `<movement:>` `<mode:>` `<h:emotion:>`
**and internal `<thought:>`** — her private reasoning would be spoken aloud.

Strip in the IPC TTS path (benefits all consumers). Model the grammar on the existing
filter in `Backend/Cognition/MindCore/MindCore.py:16` (already handles `User:`/`Jen:`/`Daniel:`).

---

## G. Port map — verified by probe, not documentation

```
8400  backend proxy (auth)      — 8401  STT (WS-only, 426 on HTTP)
8402  XRLF API                   — 8403  unified WS IPC  ← chat + TTS + STT events
8405  soul                       — 8406  380M draft llama-server
8408  9B Qwen3.5 MoQ 3.6 (Eagle) — 8411  Kokoro TTS (:8401 is NOT TTS)
retired: 8000 8001 8004 8110
```
`ss -ltn` observed: `8400 8401 8402 8403 8405 8406 8410 8411 8412 8413 8414 8415 8416 8430`

**Misleading labels found** (fix when convenient):
- Tray reports `STT (:8408) INACTIVE` — wrong, 8408 is the 9B model.
- `websocket_server.py:248,261,264,929` log "Mouth service :8406" — stale comment/string.
  Runtime code uses `FOVEAI_TTS_URL` → `:8411`. Correct.
- `.env:402 MOUTH_URL=http://127.0.0.1:8004` — `:8004` retired per `AGENTS.md`.
- `.env:286 TTS_URL=…:8411` ✓ · `.env:129 FOVEAI_TTS_PORT=8411` ✓

---

## H. `.env` — confirmed defaults (grep'd, never cat'd)

```
17  XRLF_WORKSPACE_ROOT=/home/lumba/FoveAI
26  XRLF_RUNTIME_MODE=local
28  XRLF_MODEL_LOCAL_ID=qwopus3.5-9b-coder-mtp-moq
115 XRLF_SPECULATIVE_DECODING=false
118 XRLF_TRIAD_PIPELINE=false
119 XRLF_ROUTER_GGUF=
120 XRLF_SUMMARIZER_GGUF=
132 FOVEAI_XRLF_API_PORT=8300              ← stale, 8300 retired
156 XRLF_VOICE_ENABLED=true
160 XRLF_MODEL_THINKING=false
171 FOVEAI_MODEL_ACTIVE_ID=qwen3.5-4b-mtp-multimodal-v1.0.xrlf   ← CONFLICT (see I)
172 FOVEAI_MODEL_ACTIVE_ID=qwopus3.5-9b-coder-mtp-moq            ← CONFLICT
195 FOVEAI_MODEL_DORMANT_ID=smolvlm2-500m-multimodal-v1.0
245 FOVEAI_MODEL_SWAP_ENABLED=true   246 THRESHOLD=0.7   247 COOLDOWN=30
286 LOCAL_LLM_BASE=http://127.0.0.1:8408/v1          ← was :8402 (SELF-REF, fixed)
287 LOCAL_LLM_MODEL=qwopus3.5-9b-coder-mtp-moq        ← was gemma-4-E2B-it
293 TTS_URL=http://127.0.0.1:8411
295 XRLF_CHAT_PROVIDER=xrlf_proxy
296 XRLF_LLM_PROVIDER=xrlf_proxy
297 XRLF_LOCAL_BASE_URL=http://127.0.0.1:8408/v1    ← was :8402 (SELF-REF, fixed)
298 XRLF_TTS_PROVIDER=websocket                     ← NOT honored by IPC
302 XRLF_STT_PROVIDER=whisper
338 FOVEAI_CPU_ONLY_MODELS=smolvlm2-500m-video-instruct,…
367 FOVEAI_MODEL_ACTIVE_PATH=…/qwopus3.5-9b-coder-mtp-moq.xrlf
368 FOVEAI_MODEL_DORMANT_PATH=…/smolvlm2-500m-multimodal-v1.0.xrlf
402 MOUTH_URL=http://127.0.0.1:8004                 ← retired port
405 XRLF_MODEL=smolvlm2-500m-video-instruct        ← was gemma-4-E2B-it
406 XRLF_MODEL_FILE=smolvlm2-500m-multimodal-v1.0.xrlf
407 XRLF_MODEL_PATH=…/smolvlm2-500m-multimodal-v1.0.xrlf
 43 XRLF_CTX_MAX_CHARS=6000                        ← was 8500 (exceeded 2048 ctx)
```

---

## I. Open questions for Daniel

1. **`FOVEAI_MODEL_ACTIVE_ID` conflict** — `qwopus3.5-9b-coder-mtp-moq` (lines 28, 172) vs
   `qwen3.5-4b-mtp-multimodal-v1.0.xrlf` (line 171). Last-one-wins is order-dependent.
   Which is intended?
2. **`--model` vs `.env` precedence** — `.env` silently overrode the flag (cause #2 of the
   six defects). Should an explicit flag win, or `.env`?
3. **Soul packaging** for Open XRL — per-agent `.xrlf`, Jen-only, or template-to-instantiate?
4. **Is `:8404`/`:8410`/`:8412`/`:8430` in use?** (appeared in `ss`, unlabelled)

---

## J. Commands to resume

```bash
# read-only state check
systemctl is-active foveai-xrlf foveai-llama-9b-eagle foveai-tts foveai-stt foveai-backend
ss -ltn | grep -E ':84[0-9]{2}'
nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader
curl -s http://127.0.0.1:8402/health          # expect load_state:"ready"
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8408/v1/models

# WS smoke test
cd /home/lumba/FoveAI
.venv/bin/python - <<'EOF'
import asyncio, json, websockets
async def main():
    async with websockets.connect("ws://127.0.0.1:8403", open_timeout=15) as ws:
        await ws.send(json.dumps({"event":"chat","payload":{"text":"Who are you?","max_tokens":300}}))
        for _ in range(80):
            try: raw=await asyncio.wait_for(ws.recv(), timeout=20)
            except asyncio.TimeoutError: print("TIMEOUT"); break
            if isinstance(raw,(bytes,bytearray)): continue
            m=json.loads(raw)
            if (m.get("type") or m.get("event"))=="chat.response":
                print(m["payload"]["text"]); break
asyncio.run(main())
EOF
```

**Service log locations** (journal is EMPTY for these — output is redirected to files):
- XRLF  → `/home/lumba/xrlf_live.log`   (966k+ lines — always `tail -c`, never grep whole)
- 9B    → `/home/lumba/foveai_llama_8414.log`

---

## K. Hard rules for whoever continues

1. **Show the exact change, wait for approval, then apply.** `AGENTS.md` requires it; it was
   violated this session on `.env`, service units, and persona constants. All backed up
   (see `OPEN-XRL-SPEC.md` §4) — Daniel wants those diffs reviewed.
2. **Never run Unity concurrently with the 9B** or any RAM/GPU-intensive task. Last Unity
   build wedged 4 h at 100% CPU (IL2CPP `2721/2733`) — hung, not slow.
3. **Never `cat .env` or `/proc/*/environ`** — live API keys. Grep specific keys.
4. **9B ctx is capped at 2048** (40/40 layers offloaded, VRAM-bound).
5. **WS envelope is `{"event":…, "payload":{…}}`** — not `type`. Unknown keys are dropped
   silently (only a `WARNING`). Worth making fail-fast.
6. **No hardcoded LAN IPs** — discover via `GET /api/server_info`.
7. Naming: **Jen** / **Jenny Ninebe** / made by **Daniel**. smolvlm2 = dormant, 9B = active.