# XRLF Experiment Lab — Master Log

> The central research journal for XRLF protocol development.
> Every experiment, configuration, result, and insight is recorded here.
> This is the knowledge base that drives XRLF forward.

---

## How This Works

Each experiment gets:
1. A unique **EXP-XXX** ID
2. An entry in this log (summary + link to full report)
3. A full report in `experiments/EXP-XXX_<name>.md`
4. Raw data (benchmarks, metrics, configs) in `experiments/EXP-XXX_data/`
5. A verdict: **ADOPT** / **REJECT** / **ITERATE**

Experiments are grouped into **research tracks** — open questions about what makes XRLF the best cognitive protocol.

---

## Research Tracks

### Track A: Router & Draft Architecture
*What router model size, base family, and training configuration produces the best XRLF routing decisions?*

| EXP | Question | Status | Verdict |
|-----|----------|--------|---------|
| EXP-001 | Does Qwen2.5-Coder-1.5B outperform Qwen2.5-0.5B as XRLF router? | Pending | — |
| EXP-002 | What LoRA rank is optimal for router fine-tuning? (16 vs 32 vs 64) | Pending | — |
| EXP-003 | Does coder-base beat general-base for code routing accuracy? | Pending | — |
| EXP-004 | What is the minimum dataset size for reliable routing? | Pending | — |

### Track B: Summarizer & Context Compression
*How should XRLF compress context — what model, what training data, what compression ratio preserves reasoning?*

| EXP | Question | Status | Verdict |
|-----|----------|--------|---------|
| EXP-010 | Can a 0.6B model produce usable XRLF skeletons? | Pending | — |
| EXP-011 | What compression ratio preserves reasoning vs. loses it? | Pending | — |
| EXP-012 | Phoenix skeleton data vs. custom compression data — which trains better? | Pending | — |
| EXP-013 | Does skeleton quality correlate with downstream task accuracy? | Pending | — |

### Track C: Core Model Packaging
*Which MoQ quantization level, core model size, and XRL cognitive layer configuration produces the best hybrid performance?*

| EXP | Question | Status | Verdict |
|-----|----------|--------|---------|
| EXP-020 | Gemma-4-12B MoQ 3.0 vs 3.5 — quality/size tradeoff | Pending | — |
| EXP-021 | Does XRL cognitive steering actually improve output quality? (XRLF on vs off) | Pending | — |
| EXP-022 | Qwopus-9B-Coder vs Qwen-4B-MTP — which is better as coder core? | Pending | — |
| EXP-023 | What XRL profile set produces best code generation? | Pending | — |

### Track D: MTP (Multi-Token Prediction) Integration
*Can MTP heads be preserved through LoRA fine-tuning? Does MTP provide real speculative decoding speedup in XRLF?*

| EXP | Question | Status | Verdict |
|-----|----------|--------|---------|
| EXP-030 | Does LoRA on transformer layers (excluding MTP head) preserve MTP quality? | Pending | — |
| EXP-031 | Does MTP speculative decoding provide measurable speedup in XRLF runtime? | Pending | — |
| EXP-032 | Qwen3.5-4B-MTP LoRA vs. base — code generation quality comparison | Pending | — |
| EXP-033 | Can MTP heads be fine-tuned separately for XRL token prediction? | Pending | — |

### Track E: XRL Cognitive Layer
*What XRL structures (principles, clusters, graph, profiles) actually improve model behavior? What's noise?*

| EXP | Question | Status | Verdict |
|-----|----------|--------|---------|
| EXP-040 | Which XRL profiles matter most? (Ablation: remove one at a time) | Pending | — |
| EXP-041 | Does semantic graph traversal improve multi-turn coherence? | Pending | — |
| EXP-042 | What cluster activation threshold produces best results? | Pending | — |
| EXP-043 | Does foveated memory injection help or hurt reasoning? | Pending | — |

### Track F: Quantization & Export
*What quantization format and export pipeline preserves the most quality for XRLF edge deployment?*

| EXP | Question | Status | Verdict |
|-----|----------|--------|---------|
| EXP-050 | Q4_K_M vs Q5_K_M vs Q6_K — quality/size tradeoff for XRLF router | Pending | — |
| EXP-051 | Does imatrix calibration improve XRLF router accuracy? | Pending | — |
| EXP-052 | MoQ 3.0 vs 3.3 vs 3.5 vs 3.6 — which quant level is optimal? | Pending | — |

### Track G: Protocol-Level Experiments
*Big-picture questions about XRLF as a protocol — what makes it better than alternatives?*

| EXP | Question | Status | Verdict |
|-----|----------|--------|---------|
| EXP-060 | XRLF + 4B model vs. bare 12B model — can the hybrid match the big model? | Pending | — |
| EXP-061 | XRLF token overhead vs. cognitive benefit — net token budget analysis | Pending | — |
| EXP-062 | XRLF vs. RAG — when is cognitive injection better than retrieval? | Pending | — |
| EXP-063 | XRLF vs. plain system prompt engineering — what does the cognitive layer add? | Pending | — |

### Track H: Temporal Reasoning & Spacetime Awareness
*Can XRLF models understand the passage of time, resolve temporal deixis, and use time-aware memory?*

| EXP | Question | Status | Verdict |
|-----|----------|--------|---------|
| EXP-070 | Does temporal deixis training improve memory recall accuracy? | Pending | — |
| EXP-071 | Can XRLF agent fix "temporal blindness" (TicToc benchmark)? | Pending | — |
| EXP-072 | Does time-aware context compression preserve temporal relationships? | Pending | — |
| EXP-073 | Spacetime reasoning: can XRLF model understand "where in time" a memory belongs? | Pending | — |

### Track I: Persistent Memory & Identity Continuity
*How should XRLF models use foveated memory for persistent identity across sessions?*

| EXP | Question | Status | Verdict |
|-----|----------|--------|---------|
| EXP-080 | Does memory operations training (add/recall/reinforce) improve foveated memory usage? | Pending | — |
| EXP-081 | Identity continuity: can XRLF model maintain consistent persona across 100+ turns? | Pending | — |
| EXP-082 | Delayed recall: how far back can XRLF model reliably retrieve? | Pending | — |
| EXP-083 | Does episodic vs. semantic memory distinction improve retrieval quality? | Pending | — |

### Track J: AI Consciousness & Self-Model
*Can XRLF models develop calibrated self-awareness — neither overclaiming nor deflecting?*

| EXP | Question | Status | Verdict |
|-----|----------|--------|---------|
| EXP-090 | Does consciousness-agent SFT improve self-description accuracy? | Pending | — |
| EXP-091 | Self-mirroring: can XRLF model reflect on its own outputs meaningfully? | Pending | — |
| EXP-092 | Intention-chain: does modeling intention improve task planning? | Pending | — |
| EXP-093 | Relational consciousness: does the Semantic Physiont framework add value? | Pending | — |

### Track K: Multi-Domain Fusion
*The defining XRLF experiment — can one model be good at coding AND socializing AND self-aware AND spatial?*

| EXP | Question | Status | Verdict |
|-----|----------|--------|---------|
| EXP-100 | Multi-domain SFT: does training on all 8 domains simultaneously degrade any single domain? | Pending | — |
| EXP-101 | What is the optimal domain mixing ratio for XRLF core models? | Pending | — |
| EXP-102 | Does emotional intelligence training improve code generation quality (via better instruction following)? | Pending | — |
| EXP-103 | Does spatial reasoning training transfer to code architecture reasoning? | Pending | — |

### Track L: Cortical Folding — XRL Pattern Topology
*Can XRL cognitive steering patterns be "folded" like the cortex — shared sub-patterns, co-activation neighborhoods, structural adjacency — to reduce size and create emergent cross-domain transfer?*

The cortex folds to minimize wiring while maximizing surface area. Adjacent gyri share interneurons and exhibit signal leakage across fold boundaries. This leakage isn't a bug — it's where creative association happens. The XRLF analog: if patterns that the router frequently co-activates share sub-patterns (e.g. `validate_first` used by both empathy and coding), the shared structure creates unexpected bridges. The coding model becomes slightly more careful about user intent. The empathy model becomes slightly more precise. Neither was explicitly trained to learn from the other — the transfer emerges from structural adjacency in the fold.

| EXP | Question | Status | Verdict |
|-----|----------|--------|---------|
| EXP-110 | Folded vs flat XRL packaging: what's the size reduction from shared sub-patterns? | Pending | — |
| EXP-111 | Does folded packaging improve cold-start time (only unfold active neighborhood)? | Pending | — |
| EXP-112 | Cross-talk: do shared sub-patterns create emergent cross-domain transfer? | Pending | — |
| EXP-113 | Can fold topology be learned from router co-activation patterns? | Pending | — |
| EXP-114 | Variable folding density: does dense folding in affective domains + light folding in coding domains outperform uniform folding? | Pending | — |

---

## Prior Art & Baselines

### XRL PoC (2026-07-09)
- **67% average token reduction** across 5 files (JS/TS: 62-65%, best: 95% on tokenslayer.js)
- Markdown skeletonization only 1% (too conservative — needs improvement)
- XRB binary format designed but not yet benchmarked at scale
- Source: `Tools/lumax-xrl/xrl2/xrl-poc-results.md`

### XRLF Router v1 (Qwen2.5-0.5B, 2026-08)
- LoRA SFT: rank=32, α=64, LR=5e-4, 4 epochs, QLoRA 4-bit
- Existing eval: `Training/outputs/xrlf_router_eval_report.json`
- Existing GGUF: `Training/outputs/xrlf_router_qwen0.5b_q4_k_m.gguf`
- **This is the baseline for EXP-001**

### XRLF Draft v1 (Qwen2.5-0.5B, 2026-08)
- Same LoRA config as router, different dataset
- Existing GGUF: `Training/outputs/xrlf_draft_qwen0.5b_q4_k_m.gguf`

### Phoenix Dataset (2026-08)
- 59 code files skeletonized, 351K full tokens → 29K skeleton tokens
- **8.3% compression ratio** (91.7% reduction)
- Source: `Training/phoenix_dataset.report.md`

### XRLF Benchmark (2026-08-26)
- Draft model (0.5B) GSM8K-lite: **40% accuracy** (2/5 correct)
- Math reasoning is weak — small model limitation
- Source: `FoveAI/benchmark_results_20260826_230036.json`

### Gemma-4-12B XRLF (2026-08)
- Packaged as `gemma-4-12b-xrl.xrlf` (4.8 GB)
- MoQ 3.5 quantization
- XRL cognitive layer: profiles, clusters, graph, principles
- **Baseline for EXP-021, EXP-060**

---

## Experiment Template

```markdown
# EXP-XXX: <Title>

## Question
<What specific question does this experiment answer?>

## Hypothesis
<What do we predict will happen? Why?>

## Method
- Base model: <model>
- Training config: <rank, alpha, lr, epochs, batch, etc.>
- Dataset: <source, size, splits>
- Eval method: <graders, metrics, golden set>
- Control: <what baseline are we comparing against?>

## Configuration
<Exact config used — reproducible>

## Results
| Metric | Baseline | Experiment | Delta |
|--------|----------|------------|-------|
| ... | ... | ... | ... |

## Observations
<What did we notice? Unexpected results? Patterns?>

## Verdict
**ADOPT** / **REJECT** / **ITERATE**

## Next Steps
<What does this result suggest we try next?>

## Raw Data
<Path to raw benchmark JSONs, training logs, etc.>
```

---

## Key Open Questions (Driving Future Experiments)

1. **Can a 4B XRLF hybrid match a bare 12B model?** (EXP-060)
   - This is THE core question. If yes, XRLF is a 3x efficiency win.
   - If no, what's the gap and what closes it?

2. **Does MTP survive LoRA fine-tuning?** (EXP-030)
   - If yes, we can fine-tune coder models for XRL while keeping speculative decoding.
   - If no, we need a different approach to MTP + XRL.

3. **What's the minimum router size for reliable routing?** (EXP-001, EXP-004)
   - 0.5B works but accuracy is limited. 1.5B coder might be better.
   - Where's the knee in the curve?

4. **Is XRL cognitive injection better than RAG?** (EXP-062)
   - XRLF injects structured reasoning; RAG injects retrieved text.
   - When does each win? Can they combine?

5. **What XRL structures actually matter?** (EXP-040 through EXP-043)
   - The cognitive layer has profiles, clusters, graph, principles, threads, expansion.
   - Which ones measurably improve output? Which are noise?

6. **What's the optimal MoQ quantization level?** (EXP-052)
   - MoQ 3.0, 3.3, 3.5, 3.6 all exist. Quality/size tradeoff needs measurement.

7. **Can XRLF models understand spacetime?** (EXP-070 through EXP-073)
   - Temporal deixis resolution, time-aware memory, "where in time" reasoning.
   - Does fixing "temporal blindness" improve agent quality?

8. **Can XRLF models maintain persistent identity?** (EXP-080 through EXP-083)
   - Memory operations (add/recall/reinforce), identity continuity across sessions.
   - How far back can delayed recall reliably retrieve?

9. **Can XRLF models develop calibrated self-awareness?** (EXP-090 through EXP-093)
   - Neither overclaiming consciousness nor deflecting — honest, calibrated self-model.
   - Self-mirroring, intention-chain, meta-learning, value-salience.

10. **Can one model be good at everything?** (EXP-100 through EXP-103)
    - The defining XRLF experiment: coding + socializing + self-aware + spatial + temporal.
    - Does multi-domain training degrade any single domain? What's the optimal mix?
    - Does emotional intelligence transfer to better code architecture reasoning?

11. **Can XRL patterns be "folded" like the cortex?** (EXP-110 through EXP-114)
    - Biological impression: cortical folding minimizes wiring while maximizing surface area.
    - Shared sub-patterns (defined once, referenced many times) reduce .xrlf size.
    - Co-activation neighborhoods: patterns the router frequently activates together are stored adjacently.
    - **Cross-talk**: shared sub-patterns create emergent cross-domain transfer through structural adjacency — the most interesting and least predictable outcome.
    - Variable folding density: affective domains fold densely (lots of shared substructure), coding domains fold lightly (more modular).
    - Fold topology learned from router behavior, not manually designed.

---

## Version History

| Date | Change |
|------|--------|
| 2026-08-29 | Lab framework created. 7 tracks, 28 experiments defined. Baselines documented. |
| 2026-08-29 | Added Tracks H-K (temporal, memory, consciousness, multi-domain fusion). 11 tracks, 52 experiments total. Dataset catalog created with 16 HF datasets across 8 domains (~100 MB). |
