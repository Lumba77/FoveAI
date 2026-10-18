# XRL Nano-Native Training — Design Memo

**Question:** How do we combine cutting-edge technology to make 33M–1B nano models actually use the XRL protocol, natively, through training?

**Answer:** Treat the XRL seed as a *learned interlingua* and train nano models to speak it end-to-end: read a long context, emit a compact XRL seed, and decode that seed back into a useful continuation.

**Date:** 2026-10-16  
**Owner:** FoveAI Labs  
**Status:** architecture + dataset skeleton

---

## 1. Why nano-first is the right place to start

- **Fast iteration:** A 135M model trains in minutes, not days, on a single GPU.
- **Cheap ablation:** We can test tokenizer changes, seed formats, and curricula rapidly.
- **Selective evolution:** Only methods that survive the nano stage get promoted to 1B–2B and beyond.
- **Edge deployment:** A nano model that speaks XRL can run on Quest, phone, or embedded clients as a local context compressor/decompressor.

Cutting-edge candidates for nano models:

| Family | Size | Why it fits |
|---|---|---|
| **SmolLM2** | 135M / 360M / 1.7B | HuggingFace's on-device series, strong instruction following, Apache-2.0. |
| **Qwen2.5-0.5B-Coder** | 0.5B | Already in FoveAI registry (`qwen25_coder_05b`), code-aware, GGUF available. |
| **Gemma-4-E2B** | ~2B | Multimodal, already the FoveAI default background model. |
| **Mamba / RWKV** | variable | Sub-quadratic attention → longer effective context, ideal for context compression. |
| **MiniMax / Phi / MobileLLM** | variable | Phone-optimized architectures. |

---

## 2. The XRL native task

We don't just compress text. We train the model on a *three-part* task:

```
[Long Context]  →  [XRL Seed]  →  [Target Continuation]
          (encode)        (decode)
```

1. **Encoder mode:** Given a long conversation/context, produce an XRL seed.
2. **Decoder mode:** Given an XRL seed + a new user message, produce the next useful assistant response.
3. **Autoencoding mode:** Long context → seed → reconstruct the key facts and style of the long context.

This is analogous to how humans take meeting notes: we don't memorize every word, we compress to a short set of bullet points and then act from those bullets.

---

## 3. XRL seed as learned interlingua

The seed is not English and not raw JSON. It is a **structured, token-efficient representation** that the model learns to read and write. A seed has slots:

```
<XRL-SEED degree=3 profile=code>
<ANCHORS>
- user: "How do I sort a list in Python?"
- assistant: "Use list.sort() for in-place, sorted() for new list."
</ANCHORS>
<CONCEPTS>python list sorting in-place sorted-function</CONCEPTS>
<DIGEST>User wants concise Python sorting guidance.</DIGEST>
<PRINCIPA>Be brief. Prefer code examples.</PRINCIPA>
<MEMBRANE>HUD: active ring=code; confidence=0.94</MEMBRANE>
<CONTINUE/>
</XRL-SEED>
```

Special tokens (`<XRL-SEED>`, `<ANCHORS>`, `<CONCEPTS>`, `<DIGEST>`, `<PRINCIPA>`, `<MEMBRANE>`, `<CONTINUE/>`) are added to the tokenizer vocabulary so the model can emit them cheaply.

---

## 4. Training recipe

### 4.1 Base model

Start with an **instruct-tuned nano model**:
- Primary: `HuggingFaceTB/SmolLM2-135M-Instruct` or `SmolLM2-360M-Instruct`
- Local fallback: `Qwen/Qwen2.5-Coder-0.5B-Instruct`
- We avoid pre-training from scratch; we only add XRL special tokens and fine-tune.

### 4.2 Vocabulary surgery

Add ~20 special tokens to the tokenizer:

```python
new_tokens = [
    "<XRL-SEED>", "</XRL-SEED>",
    "<ANCHORS>", "</ANCHORS>",
    "<CONCEPTS>", "</CONCEPTS>",
    "<DIGEST>", "</DIGEST>",
    "<PRINCIPA>", "</PRINCIPA>",
    "<MEMBRANE>", "</MEMBRANE>",
    "<KV-HINT>", "</KV-HINT>",
    "<CONTINUE/>",
    "<RUBBLE>", "</RUBBLE>",
]
```

Resize embeddings + LM head. This is a tiny change for nano models.

### 4.3 Dataset construction (synthetic + curated)

Three parallel corpora:

#### A. Long → Seed (encoder)

Input: a conversation of N turns.  
Target: a seed with anchors (first + last user + key assistant claims), concepts, digest.

Generate from public chat datasets (e.g., Open-Platypus, SmolTalk) by:
1. Taking a long prompt/response pair.
2. Asking a larger teacher model (Qwen3.5-9B, Gemma-4-12B) to write the XRL seed.
3. Filtering seeds that preserve answer correctness.

#### B. Seed → Response (decoder)

Input: a seed + a new user message.  
Target: the correct assistant response.

This teaches the model that a seed is sufficient to continue coherently.

#### C. Rubble → Principa (purification)

Input: noisy context — repeated fragments, mis-grammar, tangents, partial code errors.  
Target: a clean, principia-aligned seed that drops the noise and keeps the signal.

This is the “membronic benign artifact” skill: turn chaotic context into a helpful HUD-like summary.

### 4.4 Training objective

Standard causal LM loss on the *target* part:

```
[Long context] <XRL-SEED> ... </XRL-SEED> [continuation]
                              ^^^^^^^^^^^
                              loss computed here
```

Optionally add a small auxiliary loss for seed correctness (e.g., ROUGE-L between seed reconstruction and original key facts).

### 4.5 Curriculum stages

| Stage | Epochs | Task | Goal |
|---|---|---|---|
| 1 | 1 | Seed decoding (seed → response) | Learn XRL tokens and structure. |
| 2 | 1 | Seed encoding (long → seed) | Learn what to keep vs. drop. |
| 3 | 1 | Autoencoding (long → seed → reconstruct) | Learn semantically lossy compression. |
| 4 | 1 | Rubble → principa | Learn noise rejection. |
| 5 | 1 | Mixed + degree variation | Generalize across XRL degrees 1–5. |

---

## 5. Cutting-edge accelerators

| Tech | How we use it |
|---|---|
| **Unsloth** | Fast QLoRA fine-tuning, 2x speed, lower VRAM for 135M–1B models. |
| **DPO / ORPO** | After SFT, preference-optimize seeds for compactness vs. completeness. |
| **Distillation** | Teacher (Gemma-4-12B / Qwen3.5-9B) writes seeds; nano student mimics them. |
| **MiniSpec / structured generation** | Force valid seed XML/JSON with outlines; no malformed outputs. |
| **Activation checkpointing + FA2** | Train longer sequences on the same GPU. |
| **LLM-as-judge** | Gemini / local 9B scores seed quality during evaluation. |

---

## 6. Evaluation

- **Compression ratio:** raw tokens / seed tokens.
- **Downstream accuracy:** run `builder/probes/benchmark_suite.py` using only the seed as context.
- **Human/LLM-judge coherence:** seed + new question → response rated 1–5.
- **Token efficiency:** measure per-response cost vs. full-context baseline.

Success gate for nano promotion:
> A 135M–360M model, given a 4K-token context, produces a seed ≤ 1.5K tokens and answers downstream questions at ≥ 90% of the full-context score.

---

## 7. Integration into FoveAI

1. **Local compressor on phone/Quest:** tiny 135M model converts local chat history into an XRL seed before sending to the PC backend.
2. **Server-side memory ring:** nano model continuously compresses the foveated memory rings into seeds.
3. **XRLF packer:** trained nano compressor/decoder can be bundled as a `CORE_NANO_XRL` section inside `.xrlf` files.
4. **Runtime:** `XRLContextCompressor` can optionally call a local nano model instead of heuristics.

---

## 8. Files and next actions

- `Forge/nursery/xrl_nano_trainer.py` — nano-specific trainer (vocab surgery, SFT, DPO).
- `Forge/nursery/dataset_curator.py` — generate XRL seed pairs from raw chats.
- `runtime/xrl_context_compressor.py` — later swap heuristic `_decode_seed()` for nano model call.
- `Plans/Kimi-principia-plan.MD` — record nano-native XRL strategy.
- `Docs/XRL_NANO_NATIVE_TRAINING.md` — this memo.

---

## 9. Open questions

1. Should we use raw text seeds or a compact binary token representation?
2. Do we train one model for both encode/decode, or two specialists?
3. How do we represent multi-modal content (image captions, audio transcriptions) in seeds?
4. Should seeds be human-readable for debugging, or purely machine tokens?
