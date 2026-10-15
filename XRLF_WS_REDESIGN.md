# XRLF Memory Service — WS Redesign (Design Notes)

Status: **design agreed, not implemented**. Written 2026-10-06 so the work
survives session loss. Nothing here is deployed; the live runtime is untouched.

## Goal

Decouple *inference* from *memory* so any model — in any host process — can
attach to the XRLF foveated memory contract.

Current chain (single process, tightly coupled):

    client ──WS :8403──> IPCServer ──> XRLFRuntime ──> llama_cpp.Llama ──> libllama.so

`store_turn` is called by `XRLFRuntime` on every generation
(`runtime/xrlf_runtime.py:792,884,913,931`). `IPCServer`
(`Backend/app/IPC/websocket_server.py`) contains **zero** memory references —
the WS layer never touches memory directly; the runtime does it implicitly.

## Two modes, one substrate

Latency is a property of **requested** memory only. Ambient/associative influx
has no deadline, so it can do work that is too expensive to do inline.

| | Requested memory | Lazy influx |
|---|---|---|
| Trigger | model's query or emitted token | ambient, speculative, self-scheduled |
| Latency | must be now (~5ms) | none |
| Examples | `recall`, `weave`, `saccade`, `zoom` | resonance, constellation walks, associative drift |
| Cost if late | user-visible stall | none |
| Transport | control lane | transfer lane |

The point of separating them is **urgency**, not rarity or lifecycle. It also
frees `:8400` from having to be fast — it currently does synchronous TF-IDF
recall inline on the request path.

### Slow derivation is where depth comes from

When not racing the request, memory can accumulate complexity that fast recall
cannot reach. The substrate already implements a three-stage slow derivation
(`memory/membrane_engine.py:229-231`):

    CONSTELLATION_MIN_EDGE    = 3.0   co-recalls before an edge is "travelled"
    CONSTELLATION_MIN_MEMBERS = 3     smallest cluster worth crystallizing
    CONCLUSION_MIN_TOUCHED    = 5     surfaces before a cluster is "settled"

edges → members → settled conclusions. Each stage requires repetition over
time, which a synchronous request path structurally cannot supply.

Measured 2026-10-06 on the live membrane:

    turns           4301     growing (runtime live)
    co_recall          18    regrowing after contamination cleanup
    constellations     19    ← slow derivation IS producing
    summaries           0    ← compression slot, never written

`constellations` populated to 19 proves the slow path works. `summaries` being
empty is the clearest single piece of unfinished work: the compression tier was
designed and never wired.

Division of labour: the **slow** lane accrues co-recalls, crystallizes
constellations, settles conclusions and writes summaries; the **fast** lane
serves those settled conclusions plus direct recall. Precompute the expensive
part, serve it cheaply — which also keeps it off the VRAM-constrained
inference path.

## Two transport lanes

Separated by **duration**, not importance.

| | Control lane (`:8403` today, memory as events) | Transfer lane (`:8404`) |
|---|---|---|
| Duration | sub-100ms | long-lived / bulk |
| Shape | request → response | stream → stream |
| Blocking risk | low (recall is ~5ms) | expected — that is the purpose |
| Carries | `chat`, `memory.recall`, `memory.weave`, `tts.request`, `movement` | `memory.stream`, resonance replay, shadow-context sync, bulk export |

`:8403` is sequential per connection (`async for raw_message in websocket` →
`await self._safe_call(...)`, `Backend/app/IPC/websocket_server.py:405-418`), so
a long-lived transfer on the control lane would head-of-line-block every other
event on that connection. Different connections are unaffected — each client has
its own handler task.

Replies currently carry **no correlation id** (`_send`, line 1504-1510). Order is
preserved only because the loop is sequential. Any concurrency added needs ids.

Memory must stay **retrieval-only** on the control lane. A reflex that
generates would hold the loop for seconds; recall/weave at ~5ms cannot.

## No model reimplementation required

Memory is injected at **prompt level** — the runtime places retrieved text into
the message before the model sees it. Models hold no memory code because they
cannot; they read text. Proven 2026-10-06: bare, the runtime answered a
codeword question by echoing the question; with recall in the prompt it
answered correctly. Swapping the core model (3.6 / 3.2 / E2B) changes nothing
about the memory path — bundles do not own memory, the service does.

## Decided

**1. Inference path unchanged.** The model keeps talking to `llama-server`
directly over its normal HTTP/OpenAI-compatible API
(`/v1/chat/completions`, `/v1/models` — already proxied by
`foveated-memory/mcp-server.js`). No WS for inference.

**2. Memory gets its own low-latency WS line.** Separate contract, separate
lifecycle, so a memory-service restart is not indistinguishable from a model
failure. Rationale for WS over HTTP: clients are remote (Quest 3 and the WebXR
frontend reach :8400/:8402/:8403 on `0.0.0.0` over the LAN), so per-call HTTP
pays a handshake each time. The stronger argument is **server push** — HTTP
request/response cannot deliver memory unprompted.

**3. Reflex: prefetch, then interrupt.** On turn start, fire the memory
recall in parallel with generation and buffer the result — no stream mutation.
Only inject at a boundary that cannot corrupt output (sentence end, paragraph
break, completed tool call, closed code fence). Never mid-word, mid-JSON or
mid-code-block.

Chosen over mid-stream injection because the current implementation is
destructive: `Tools/xrlf-model/foveated-memory/core/recall-interceptor.js`
`collectStream()` calls `body.destroy()` on any trigger token, truncating the
in-flight answer. Because prefetch completes independently, the interrupt can be
a single re-issue carrying the injection rather than destroy-then-retry.

**4. Trigger must replace the explicit token.** Today saccades are regex
matches on model output:

    const SACCADE_REGEX = /<saccade:\s*"([^"]+)">/i;   // recall-interceptor.js:21

That is voluntary and explicit — the model must *choose* to emit a tag. The
instinct-driven version (iris contraction; attention returning to memory on its
own) needs the trigger to come from model state, not text. Cheapest viable
route: embed the running turn and fire on similarity threshold, keeping the
explicit tag as a manual override. An attention-based trigger is stricter but
needs llama.cpp cooperation.

**5. Isolation boundary is per-human, not per-persona.** `lumba` and every
persona/modus of `lumba` share access; other individuals do not.
`workspace_mode: "personal"` in `foveated-memory/config/default.json` already
does this (stores keyed per identity: `u_lumba`, `jen`, `lmstudio`, …).

## Backend: MembraneEngine, not NeDB

Two stores exist and are **not** unified. Measured 2026-10-06:

| Store | Backing | Extent | Written by |
|---|---|---|---|
| `XRLFRuntime` membrane | SQLite, `turns`/`summaries`/`identity`/`co_recall` | 18,838 turns (98.2% since cleaned) | every generation |
| `foveated-memory/memory_data/<ws>/memory.db` | NeDB + `nedb-promises` | 67 workspaces, 85MB | `:8400` HTTP chat path only |

A third generation exists at repo-root `memory_data/` (48 workspaces, 234 docs,
from 2026-08-29) — **divergent write target**, likely the same class of bug as
the contamination below.

The rich memory is the SQLite MembraneEngine. A WS service built against NeDB
would inherit near-empty per-identity scratch data.

## Embeddings: self-sufficient

`xrlf_embedder.py` (added 2026-10-06) — local MiniLM, no LM Studio, no network:

    Xenova/all-MiniLM-L6-v2 quantized ONNX, 22MB, 384-dim, CPU onnxruntime
    tokenizer from local tokenizer.json via `tokenizers` 0.23.2

Verified: `'hello'~'Hello' = 1.000` vs `'hello'~'what is 2+2?' = 0.159`
(margin +0.841). Replaces the LM Studio `/v1/embeddings` dependency in
`foveated-memory/server.js` `mode:'embedding'`, which silently falls back to
TF-IDF when LM Studio (`:1234`, normally offline) is down.

**Calibration caveat:** MiniLM similarity is compressed for short generic text —
`'hello'~'hi' = 0.814` but two synonymous biology sentences only `0.648`. A
fixed threshold will misfire. The Hebbian `co_recall` graph avoids this by
accumulating co-fire counts rather than cutting at a threshold.

## Why lexical recall failed

`MemoryStore.search()` (`foveated-memory/memory/store.js:180`) is bag-of-words
cosine over `_tokenize()`. Consequences, measured:

- `"hello"` and `"Hello"` are identical vectors → co-fired 2,641 times
- Boilerplate outranks meaning: long prompts match on generic vocabulary
- `co_recall` held 464 edges over only **229 of 18,838 turns** (1.2%); the
  "forms" it found were string-equality cliques, not cognitive structures

## The contamination bug (fixed upstream, cleaned here)

Summarizer/retitler in `foveated-memory/server.js` built
`"Analyze this chat snippet (last 10 turns of session)…"` and sent it to
`XRLF_RUNTIME_URL` (`:8402`), which persisted it via `store_turn`. Self-
amplifying: 9,210 turns, peak 2,681/day ≈ one per 30s, all under
`session_id: "default"`. Bounded to 2026-09-06 → 09-24 (the Nobara→Mint
window); it stopped when the repo was re-restored with the `xrlf_utility`
guard already present.

**No code change was needed.** `ChatCompletionRequest` declares
`xrlf_utility` (`api/server.py:95`), all 3 internal callers set it, and
`XRLFRuntime.chat()` returns early on `utility` *before* any `store_turn`.
Verified empirically: a `xrlf_utility:true` request left no trace in `turns`.

Cleanup (2026-10-06), archive-not-delete, integrity checked at each step:

    turns      18,838 → 9,628 → 4,287
    archived   14,551 total
      9,210  scaffolding:summarization-prompt
      5,341  scaffolding:summarizer-response   ← assistant side, found in 2nd pass
    co_recall  464 → 0 (archived as derived-from-scaffolding; every edge was
                     computed from poisoned co-fires)

Durable copies: `~/memory-archive/memory-cleaned-20261006.db`, plus
`~/membrane-prearchive-20261006-154615.db` and `…prearchive2-…`.

Residual: 3,961 of 4,287 (92.4%) are avatar markup
(`<emotion:happy> <micro:nod> …`); only 10/400 sampled carry a `thought` tag,
substance is the text after the tags. Heavy duplication remains
(`x224` empty, `x76` copies of one SPECTRAL-42 test string). Kept deliberately —
templated but not scaffolding. 326 plain turns.

## Known open items

- **`summaries` table is empty (0 rows)** — the compression tier. This is the
  clearest unfinished piece: slow derivation exists and works
  (`constellations` = 19), but nothing writes summarized conclusions. Wiring a
  background worker that settles constellations into summaries is the natural
  first job for the transfer lane.
- **Ambient influx needs a budget and decay.** Resonance arriving with no
  deadline still lands on the channel the user reads. Without a cap and
  fade-out, old resonance piles up rather than informing.
- **No model reimplementation needed** — see above. Any model served by
  `llama-server` gains memory by prompt injection alone.

- **Eagle3/DFlash unreachable from FoveAI.** llama-cpp-python 0.3.35 binding has
  zero eagle3/dflash references; `libllama.so` exports no `common_speculative_*`
  (that orchestration is statically linked into the `llama-server` binary).
  Verified working standalone: `-md <draft> --spec-type draft-eagle3 -ngl 99
  -ngld 99 -c 4096 -ctk q4_0 -ctv q4_0 --spec-draft-p-min 0.75` → **56.85 tok/s
  vs 11.88 baseline (4.8x), 84.9% acceptance**. Drafts must share the target's
  248,320-token vocab; the router draft in `lumax-…cache/draft.gguf` has **11**
  and is a router, not a draft.
- **Semantic analysis never completed.** Unbounded n×n similarity matrix filled
  RAM → swap to `/mnt/swapfile` on the SSD → IO stall and freeze. Rerun only
  chunked, with similarity accumulated on disk and approximate clustering.
  Do not repeat the n² approach. Machine is 15Gi RAM with 9Gi swap
  (2G spinner pri -1, 8G SSD pri 10).
- **`recall-interceptor.js` heuristic**: `<80 tensors → MTP head`. Both the
  Eagle3 (14) and DFlash (69) drafts would be misrouted as MTP. The gemma
  drafts (49) also route there, which suggests no draft path has ever truly run.
- **Windows-era memory not recovered.** Membrane spans 2026-09-06 → 10-06 only.
  Old NVMe not attached; recovering it is worth doing, read-only mount, targeted
  paths only. `.neurosync/store.json` (86MB, unexamined) is the most promising
  local archive of pre-Linux developer dialogue.