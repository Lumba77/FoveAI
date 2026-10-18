# XRL Context Compressor (XCC) — Design Memo

**Vision headline:** *"Model context conversion to XRL raw data, automated function makes models faster than draft models."*

**Date:** 2026-10-16  
**Owner:** FoveAI Labs  
**Status:** architecture + placeholder skeleton

---

## 1. The problem we are solving

Today the runtime keeps the full conversation history in the prompt and recomputes attention over every token on every turn. Draft models (Eagle3, MTP) speed up *token generation* but do not reduce the *context window* cost. We want a compressor that turns the model's own accumulated context into a compact XRL representation, so the next turn starts from a small seed instead of a long history.

**Success criterion:** 2.6x size reduction on 1B–2B models at MoQ 3.6-equivalent quality; aspirational stretch is Gemma-4 12B at XRL-2 beating Qwen3.5-9B MoQ 3.6.

---

## 2. What MoQ and friends teach us

| Technique | Lesson for XCC |
|---|---|
| **MoQ / K-quants / imatrix** | Not all weights are equally important; allocate precision by sensitivity. **Analog:** not all context tokens are equally important; allocate detail by semantic salience. |
| **MTP / speculative decoding** | Predict several future tokens cheaply. **Analog:** predict the *shape* of the conversation (profiles, clusters, key facts) and expand only when needed. |
| **Triad pipeline summarizer** | A small CPU model can compress old turns into a short summary. **Analog:** make the compression a first-class runtime service, not a one-off preprocess. |
| **Membrane bridge / HUD weaving** | The system already weaves repo skeleton + diagnostics into context before the LLM sees it. **Analog:** the compressor can weave a "model-state skeleton" the same way. |
| **Foveated memory rings** | Steep per-ring compression: identity kept verbatim, archive heavily summarized. **Analog:** tiered context seed with verbatim anchors and compressed background. |
| **Context-healer 3/7 contract** | Rigid budget enforcement prevents death spirals. **Analog:** the compressor must never expand the seed beyond the canonical budget. |

---

## 3. Core concept: XRL context seed

An **XRL context seed** is a compact, structured prior that stands in for the full conversation history. It is not a text summary alone; it is a *lossy semantic representation* that the runtime can decode into a minimal but sufficient prompt.

The seed contains:

- `degree`: XRL compression level (0–9).
- `profile`: active task profile(s) and their confidence.
- `anchors`: verbatim user/assistant utterances that must survive compression.
- `concepts`: extracted graph concepts / activated clusters.
- `digest`: a short narrative or structured digest of older turns.
- `kv_hint`: optional hint for KV-cache retention / eviction.
- `version`: seed format version for forward compatibility.

---

## 4. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  XRLFRuntime.chat()                                          │
│   - assembles steered_messages (system + memory + history)   │
│   - asks XCC for a context seed                              │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  XRLContextCompressor       │
        │  - encode(seed, new_turn)   │
        │  - decode(seed, user_msg) │
        │  - fit_budget(...)          │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  MembraneEngine             │
        │  - persists seed in SQLite  │
        │  - weaves seed into ring    │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  LlamaEngine / ExternalLLM  │
        │  - receives compressed ctx  │
        │  - can apply KV hints       │
        └─────────────────────────────┘
```

---

## 5. Degrees of compression

| Degree | Name | Target use | Size vs. raw | Quality guard |
|---|---|---|---|---|
| 0 | Lossless | Debugging / small chats | 1.0x | Exact replay |
| 1 | Atomic | Extreme memory pressure | ~5–8x | Heavy benchmark gate |
| 2 | Aspirational | Gemma-4 12B stretch goal | ~3–4x | Must beat MoQ 3.6 |
| **3** | **Target** | **Default efficiency sweet spot** | **~2.6x** | **MoQ 3.6 equivalent** |
| 4–6 | Standard | Daily use | 1.5–2x | Within 1% of full ctx |
| 7–9 | Light | Short chats / low pressure | 1.1–1.4x | Near lossless |

---

## 6. Implementation phases

### Phase 0 — Skeleton / pass-through (now)
- `runtime/xrl_context_compressor.py` exists.
- `XRLFRuntime` instantiates it and calls `fit_context()`.
- By default it returns the input unchanged.
- Proves wiring without breaking inference.

### Phase 1 — Heuristic text compressor
- Drop stopwords, deduplicate, collapse repeated assistant boilerplate.
- Keep verbatim user messages and key assistant claims.
- Store the seed in `MembraneEngine` memory DB.

### Phase 2 — Structured semantic compressor
- Replace old turns with `{profile, concepts, digest, anchors}`.
- Use existing `ProfileSelector`, `ClusterActivator`, `GraphTraverser` outputs.
- Add a new `XRL_CONTEXT_SEED` section to XRLF schema for persistence.

### Phase 3 — Model-assisted compression
- Use a small CPU model (router/summarizer) to write the digest.
- Benchmark full-ctx vs. seed-ctx on `builder/probes/benchmark_suite.py`.
- Tune degree mapping until XRL-3 hits 2.6x / MoQ 3.6 quality.

### Phase 4 — KV-native compression (research)
- Directly compress KV cache state instead of prompt text.
- Requires llama.cpp-level support or custom decode hooks.
- Long-term moonshot.

---

## 7. Integration points

- `runtime/xrlf_runtime.py` — create `self._context_compressor` in `__init__`, load it in `_load_xrl_layers()`, call `fit_context()` before `_llama.chat()`.
- `memory/membrane_engine.py` — add `store_seed()` / `load_seed()` methods; treat seed as Ring-3/4 background with fast lookup.
- `runtime/memory_planner.py` — seed degree can lower the effective `n_ctx` budget, freeing VRAM.
- `llama_bridge/llama_engine.py` — KV hints may later map to `type_k`/`type_v` choices or context-window pinning.
- `foveated-memory/core/context-healer.js` — proxy can request seed metadata from `:8402/health` or an internal endpoint and enforce the 3/7 contract on the *decoded* prompt.

---

## 8. Metrics and validation

- **Compression ratio:** decoded-prompt chars / raw-prompt chars.
- **Quality:** pass rate on `builder/probes/benchmark_suite.py` relative to full-context baseline.
- **Speed:** time-to-first-token (TTFT) reduction.
- **Stability:** no quality cliff across 50+ turn sessions.

---

## 9. Open questions

1. Should the seed be symmetric (same encode/decode path) or asymmetric (cheap decode, expensive encode)?
2. Do we persist seeds across sessions in XRLF or only in memory DB?
3. How do we handle multi-modal content (images/audio) in seeds?
4. Should degree be global per model or per-conversation?

---

## 10. Files touched by this design

- `runtime/xrl_context_compressor.py` (new)
- `runtime/xrlf_runtime.py` (wiring)
- `memory/membrane_engine.py` (seed persistence, future)
- `formats/xrlf_schema.py` (`XRL_CONTEXT_SEED` section, future)
- `Docs/XRL_CONTEXT_COMPRESSOR_DESIGN.md` (this memo)
- `Plans/Kimi-principia-plan.MD` (derived state update)
