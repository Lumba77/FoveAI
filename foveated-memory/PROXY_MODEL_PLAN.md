# Proxy Memory Model — Training Plan

## Overview

A small (~0.5B-1B parameter) model that handles ALL memory management for the
main companion model. It runs on GPU alongside the main model (~300-600MB at Q4),
taking on the cognitive load of:

1. **Importance scoring** (10-grade, 5-dimensional) — real-time, no latency
2. **Preservation strategy selection** — crystalline, tone-first, logic-only, etc.
3. **Memory retrieval** — which memories are relevant to the current topic
4. **Context window assembly** — which memories to include, how compressed
5. **Automatic decompression** — uncompressing memories related to current topic
6. **Temporal zoom curation** — producing rich summaries of past time periods

## Why a Trained Model Instead of Heuristics + LLM Calls

The current 3-tier system (heuristic → async LLM → on-demand LLM) works but has
limitations:

- **Heuristics are crude** — they miss nuance, context, and domain-specific signals
- **LLM calls add latency** — can't run concurrently with the main model on same GPU
- **LLM calls are expensive** — each scoring call uses 200-500 tokens of GPU time
- **No learned preferences** — the system can't learn what THIS user finds important

A trained proxy model solves all of these:
- **Fast** — 0.5B model runs in ~50ms on GPU, no noticeable latency
- **Concurrent** — small enough to share GPU with the 12B main model
- **Cheap** — 50ms of GPU time vs 2-5 seconds for a 12B LLM call
- **Personalized** — can be fine-tuned on the user's conversation patterns

## Architecture

```
┌─────────────────────────────────────────────────┐
│                    GPU (8GB VRAM)                │
│                                                  │
│  ┌──────────────┐    ┌──────────────────────┐   │
│  │  Main Model  │    │  Proxy Memory Model  │   │
│  │  (12B Q4)    │    │  (0.5B Q4)           │   │
│  │  ~6GB VRAM   │    │  ~400MB VRAM         │   │
│  │              │    │                      │   │
│  │  Generates   │    │  Scores importance   │   │
│  │  responses   │    │  Selects memories    │   │
│  │              │    │  Assembles context   │   │
│  └──────┬───────┘    └──────────┬───────────┘   │
│         │                       │                │
│         └───────────┬───────────┘                │
│                     │                            │
│              ┌──────┴──────┐                     │
│              │ Memory Store │                     │
│              │  (NeDB/JSON) │                     │
│              └─────────────┘                     │
└─────────────────────────────────────────────────┘
```

## Training Data

### Source 1: Labeled Conversation Data
Generate training data by running the current 3-tier system on real conversations:
- Use the 12B model to score messages (Tier 2 LLM refinement)
- Collect (message, role, importance_scores) pairs
- ~10,000 scored messages for initial training

### Source 2: Synthetic Edge Cases
Generate synthetic messages that test specific scoring dimensions:
- High personal, low logic: "I'm feeling vulnerable today"
- High logic, low emotional: "The API returns 500 on null input"
- Filler: "ok", "thanks", "yeah"
- Glowing stars: "I love you", "I decided to quit my job"
- ~5,000 synthetic examples

### Source 3: User-Specific Fine-Tuning
After initial training, fine-tune on the specific user's conversation patterns:
- Collect (message, importance_scores) from the user's actual conversations
- The model learns what THIS user finds important
- ~1,000 user-specific examples for LoRA fine-tuning

## Training Tasks

### Task 1: Importance Scoring
```
Input:  [MSG] "Remember my dog Rex is named after my grandfather"
Output: {"logic":3,"emotional":5,"personal":8,"actionable":2,"overall":7,"strategy":"crystalline","categories":["personal"]}
```

### Task 2: Memory Retrieval
```
Input:  [QUERY] "my dog" [MEMORIES] hash1:topic1|hash2:topic2|...
Output: {"relevant": ["hash1"], "reason": "personal pet reference"}
```

### Task 3: Context Assembly
```
Input:  [BUDGET] 2000 [MESSAGES] 400 messages with importance scores
Output: {"ring0": [...], "ring1": [...], ...}  // which messages go in which ring
```

### Task 4: Temporal Zoom Curation
```
Input:  [ZOOM] "last month" [MESSAGES] 50 messages from that period
Output: {"summary": "...", "glowingStars": [...], "scoredMessages": [...]}
```

## Base Model Selection

- **Qwen2.5-0.5B** — small, fast, good at structured output
- **Llama-3.2-1B** — slightly larger, better reasoning
- **Phi-3.5-mini** — Microsoft, good at JSON output

Recommend: **Qwen2.5-0.5B** — smallest, fastest, sufficient for scoring task.
At Q4 quantization: ~400MB VRAM, ~50ms inference time.

## Training Pipeline

1. **Collect** — Run 3-tier system for 2 weeks, accumulate scored messages
2. **Synthesize** — Generate edge cases with the 12B model
3. **Format** — Convert to instruction-tuning format (messages-shaped)
4. **SFT** — Supervised fine-tune on (input, output) pairs
5. **Evaluate** — Compare proxy model scores vs 12B LLM scores
6. **Deploy** — Export as GGUF, load alongside main model
7. **Personalize** — LoRA fine-tune on user's conversation patterns

## Integration Point

The proxy model plugs into `importance-scorer.js`:

```javascript
// When XRLF_PROXY_MEMORY_MODEL is set, score() uses the proxy model
function score(text, role = 'user') {
    if (proxyModelActive) {
        return proxyModel.score(text, role);  // ~50ms, real-time
    }
    return scoreHeuristic(text, role);  // fallback
}
```

## Milestone Roadmap

- [x] 3-tier importance system (heuristic + LLM + audit) — DONE
- [ ] Collect 10,000 scored messages from real conversations
- [ ] Generate 5,000 synthetic edge cases
- [ ] Train Qwen2.5-0.5B on importance scoring task
- [ ] Evaluate against 12B LLM scores (target: >85% agreement)
- [ ] Deploy proxy model alongside main model
- [ ] Add memory retrieval task to proxy model
- [ ] Add context assembly task to proxy model
- [ ] User-specific LoRA fine-tuning pipeline
