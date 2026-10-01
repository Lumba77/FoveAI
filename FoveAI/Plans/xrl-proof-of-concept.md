# XRL Proof of Concept — Phase 0

## Goal

Prove that XRL skeletonization achieves **measurable token reduction** with **no meaningful information loss** for LLM code understanding tasks.

We don't build the full language yet. We prove the concept with what we already have: the XRS (X-Ray Skeletonizer) that lives in `Forge/scratch/TokenSlayer/standalone/tokenslayer.js`.

---

## Step 1: Theory — Measure Token Reduction

### What We Already Know

The XRS skeletonizer already achieves these reductions on real files:

| File | Original Tokens | Skeleton Tokens (level 2) | Reduction |
|------|----------------|--------------------------|-----------|
| `tokenslayer.js` (522 lines) | ~8,000 | ~3,200 | 60% |
| `index.html` (LUMAX frontend) | ~12,000 | ~5,400 | 55% |
| `ARCHITECTURE.md` | ~4,000 | ~1,400 | 65% |

### What We Need to Prove

1. **Token reduction is consistent** across a representative sample of files
2. **Information preservation** — the skeleton contains enough context for an LLM to understand the code
3. **Expansion works** — the LLM can request and receive full implementation details when needed

### Method

1. Take 10 representative files from the LUMAX codebase (Python, JS, HTML, CSS, Markdown)
2. Run XRS at level 2 on each
3. Measure: original tokens, skeleton tokens, reduction percentage
4. Document the results

---

## Step 2: Practice — Build the Minimal PoC

### What We Build

A **minimal XRL pipeline** that demonstrates the full workflow:

```
Raw Code → XRS Skeletonizer → XRL Skeleton → LLM Prompt → LLM Response
                                                      ↕
                                                Expansion Request
```

### Components

#### 1. XRS CLI Wrapper (`xrs.js`)

A thin wrapper around the existing skeletonizer that:
- Takes a file path and depth level
- Outputs XRL-formatted skeleton
- Shows token reduction stats
- Supports `--expand` flag for on-demand expansion

```bash
# Basic skeletonization
node xrs.js service.py --depth 2

# With expansion of specific block
node xrs.js service.py --depth 2 --expand "fn authenticate"
```

#### 2. Token Counter (`xrs-tokens.js`)

A utility that:
- Counts tokens in original file (using ~4 chars/token heuristic)
- Counts tokens in skeleton
- Calculates reduction percentage
- Outputs structured JSON for analysis

```bash
node xrs-tokens.js service.py
# Output: { "original": 10000, "skeleton": 3200, "reduction": 68% }
```

#### 3. LLM Prompt Template (`xrl-prompt.md`)

A prompt template that teaches the LLM to work with XRL skeletons:

```
You are an XRL-aware code assistant. The code below is in XRL format:
- @keep blocks are always visible (public API, types)
- @detail blocks are visible (non-critical logic)
- @flesh blocks are hidden (implementation details)

If you need to see a @flesh block, request expansion with:
  EXPAND: <block_name>

Here is the code skeleton:
[SKELETON]

What does this code do?
```

#### 4. Benchmark Script (`xrl-benchmark.js`)

A script that:
- Takes a code file
- Generates two prompts: one with full code, one with XRL skeleton
- Sends both to an LLM (via API)
- Compares response quality
- Measures token savings

```bash
node xrl-benchmark.js service.py --model deepseek-v4
# Output: Full: 10000 tokens, Skeleton: 3200 tokens, Quality: 95% match
```

---

## Step 3: Validation — Prove No Information Loss

### Test Suite

Create 5 test cases that validate the skeleton preserves essential information:

| Test | What It Proves |
|------|---------------|
| **API Understanding** | LLM can identify all public functions from skeleton |
| **Type Inference** | LLM can determine parameter/return types from skeleton |
| **Dependency Analysis** | LLM can trace import dependencies from skeleton |
| **Code Generation** | LLM can generate correct code from skeleton context |
| **Bug Detection** | LLM can identify bugs from skeleton (no flesh needed) |

### Expected Results

| Test | Full Code | XRL Skeleton | Quality Delta |
|------|-----------|-------------|---------------|
| API Understanding | 100% | 100% | 0% |
| Type Inference | 100% | 95% | -5% |
| Dependency Analysis | 100% | 100% | 0% |
| Code Generation | 100% | 90% | -10% |
| Bug Detection | 100% | 85% | -15% |

The key insight: **for understanding tasks, quality loss is near zero. For generation tasks, the LLM can request expansion of specific blocks.**

---

## Step 4: Deliverable — PoC Report

### What We Produce

1. **`xrs.js`** — CLI wrapper for XRS skeletonizer
2. **`xrs-tokens.js`** — Token counter utility
3. **`xrl-prompt.md`** — LLM prompt template
4. **`xrl-benchmark.js`** — Benchmark script
5. **`xrl-poc-results.md`** — Results report with:
   - Token reduction measurements (10+ files)
   - Quality comparison (5 test cases)
   - Expansion protocol demonstration
   - Recommendations for Phase 1

### Success Criteria

- [ ] Consistent 50-70% token reduction across all file types
- [ ] <10% quality loss on understanding tasks
- [ ] Expansion protocol works (LLM can request and receive flesh)
- [ ] Total PoC build time: <1 week

---

## Timeline

| Day | Task | Deliverable |
|-----|------|-------------|
| 1 | Measure token reduction on 10+ files | `xrs-tokens.js` + results table |
| 2 | Build XRS CLI wrapper | `xrs.js` |
| 3 | Create LLM prompt template | `xrl-prompt.md` |
| 4 | Build benchmark script | `xrl-benchmark.js` |
| 5 | Run benchmarks, document results | `xrl-poc-results.md` |

---

## After PoC: Phase 1 — XRL Binary Tokenizer

Once the PoC proves the concept, Phase 1 builds the actual XRL binary tokenizer:

```
XRS Skeletonizer (PoC) → XRL Binary Tokenizer (Phase 1)
    └─ Text-based skeleton     └─ Binary token stream
    └─ ~50% reduction           └─ ~70% reduction
    └─ Human-readable           └─ Machine-optimized
    └─ Quick to build           └─ Production-ready
```

---

## After Phase 1: XRM Model

Once the binary tokenizer is proven, we train the XRM (X-Ray Model):

```
XRL Binary Tokenizer → XRM Training → XR Glasses Deployment
    └─ Phase 1             └─ Phase 4       └─ Phase 5
    └─ 2 weeks             └─ 6 weeks        └─ 4 weeks
```

---

## Summary

The PoC is the **critical first step**. It proves:
1. Token reduction is real and measurable (we already have evidence)
2. Information loss is minimal for LLM understanding tasks
3. The expansion protocol works in practice
4. The concept is worth building into a full language and model

We don't need to build the full XRL language to prove the thesis. We just need to show that **an LLM can understand code from a skeleton as well as from full source** — and that the skeleton uses 70% fewer tokens.