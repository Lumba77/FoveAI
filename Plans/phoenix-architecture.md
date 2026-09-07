# Phoenix Architecture — "No More Cloud Only"

## Vision
A 7B model that performs like 70B by operating on TokenSlayer-skeletonized input. The model learns to "expand" compressed skeletons internally, achieving 20x effective context capacity on the same hardware.

## Current Assets (Verified Working)

| Asset | Status | Details |
|-------|--------|---------|
| CUDA + RTX 4060 (8GB) | ✅ | `torch.cuda.is_available() = True` |
| Unsloth 2026.7.2 | ✅ | Imports successfully, can fine-tune |
| TokenSlayer CLI | ✅ | Levels 0-5, 94-98% reduction |
| TokenSlayer MCP Server | ✅ | 6 tools, auto-approved in mcp-config.json |
| TokenSlayer Proxy (port 8103) | ✅ | Context-aware tier selection, expansion endpoints |
| Repo Skeleton | ✅ | Micro (1.4K), Standard (7.9K), Full (25K) tokens |
| XRL Format | ✅ | Depth-aware annotations, XRB binary format |
| Existing Training Script | ✅ | `Training/train_concordia_worker.py` (Gemma-2-2B) |

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph "Phase A: Training Data Generation"
        A1[LUMAX Codebase] --> A2[TokenSlayer Level 3]
        A2 --> A3[Skeleton Files .skel]
        A1 --> A4[Full Source Files]
        A3 & A4 --> A5[Pair Generator]
        A5 --> A6[Training Dataset: skeleton→full]
    end

    subgraph "Phase B: Teacher Distillation"
        B1[70B Teacher Model<br/>Cloud API] --> B2[Generate Outputs<br/>from Skeletons]
        A6 --> B2
        B2 --> B3[Teacher Output Pairs]
    end

    subgraph "Phase C: Student Training"
        C1[7B Base Model<br/>Gemma-2-7B / Qwen2.5-7B] --> C2[LoRA Fine-Tune<br/>on RTX 4060]
        A6 --> C2
        B3 --> C2
        C2 --> C3[Phoenix 7B Student]
    end

    subgraph "Phase D: Expansion Head"
        D1[500M-1B Lightweight Model] --> D2[Train on skeleton→full]
        A6 --> D2
        D2 --> D3[Expansion Head ONNX]
    end

    subgraph "Phase E: Inference Pipeline"
        C3 --> E1[Phoenix Core<br/>7B 4-bit ~4GB]
        D3 --> E2[Expansion Head<br/>500M 4-bit ~0.3GB]
        E1 & E2 --> E3[Edge Device<br/>RTX 4060 ~5GB total]
    end
```

---

## Phase A: Training Data Generation

### A.1 Skeleton Generator Script
**File**: `Training/generate_phoenix_data.py`

Takes every Python/JS/TS file in the LUMAX codebase and generates:
1. **Skeleton** (TokenSlayer level 3 — imports + signatures)
2. **Full source** (original file)
3. **Pair record**: `{skeleton, full, filepath, language}`

### A.2 Data Format
```json
{
  "skeleton": "import os\nimport json\n\ndef load_config(path):\nasync def process_request(req):\nclass DataProcessor:",
  "full": "import os\nimport json\n\ndef load_config(path):\n    with open(path) as f:\n        return json.load(f)\n\nasync def process_request(req):\n    ...",
  "filepath": "Backend/Cognition/soul_core.py",
  "language": "python",
  "token_count_skeleton": 646,
  "token_count_full": 10722,
  "compression_ratio": 0.06
}
```

### A.3 Augmentation Strategy
- **Cross-file pairs**: Skeleton of file A → full of file B (teaches cross-file reasoning)
- **Partial skeletons**: Randomly drop 10-30% of signatures (teaches robustness)
- **Noisy skeletons**: Introduce minor errors in skeleton (teaches error correction)

### A.4 Expected Dataset Size
| Source | Files | Pairs per file | Total pairs |
|--------|-------|----------------|-------------|
| LUMAX Backend | ~50 | 3 (full + 2 augmented) | 150 |
| LUMAX Frontend | ~30 | 3 | 90 |
| TokenSlayer itself | ~10 | 3 | 30 |
| **Total** | **~90** | | **~270** |

*270 high-quality pairs is enough for a proof-of-concept. For production, we'd scale to 10,000+ pairs from open-source codebases.*

---

## Phase B: Teacher Distillation

### B.1 Teacher Selection
**Primary Teacher: `kimi-k2.7-code` (Ollama Cloud)**
- Moonshot AI's code specialist — trained specifically for code understanding/generation
- Available via Ollama Cloud (no API key needed)
- Perfect for skeleton→full code expansion task
- Estimated cost: ~$0.50-2.00 for 59 pairs

**Secondary Teacher: `deepseek-v4-pro` (Ollama Cloud)**
- Full DeepSeek V4 (not flash) — stronger reasoning for complex skeletons
- Provides a different "teaching style" for ensemble distillation
- Used for comparison and quality cross-validation

**Fallback: `glm-5.2` (Ollama Cloud)**
- Zhipu's latest — good instruction following, general purpose
- Used if primary teachers have issues

**Future: Local 70B (After Phoenix PoC)**
- Download Qwen2.5-72B or DeepSeek-67B
- Requires 140GB+ RAM/VRAM — not feasible on RTX 4060
- Would need cloud server rental

### B.2 Distillation Prompt Template
```
You are a code expansion expert. Given a skeletonized code file (imports + function signatures only), reconstruct the full implementation.

SKELETON:
{skeleton}

TASK: Write the complete implementation. Follow these rules:
1. Preserve ALL signatures exactly as shown
2. Implement each function with realistic, working code
3. Use appropriate error handling
4. Follow Python best practices
5. Output ONLY the complete file content, no explanations

FULL IMPLEMENTATION:
```

### B.3 Distillation Strategy
**Multi-Teacher Ensemble:**
1. Send each skeleton to `kimi-k2.7-code` → get teacher_output_kimi
2. Send each skeleton to `deepseek-v4-pro` → get teacher_output_pro
3. Compare both against original_full using BLEU/ROUGE/CodeBLEU
4. Store best output as primary teacher, second as secondary
5. Student trains on: skeleton → best_teacher_output

**Quality Gate:**
- If teacher output matches original_full within 80%+ structural similarity → mark as "high quality"
- If teacher output is structurally different but functionally correct → mark as "alternative implementation"
- If teacher output is garbage → skip pair, log for review

### B.4 Teacher Output Storage
```json
{
  "skeleton": "...",
  "teacher_output": "...",
  "original_full": "...",
  "filepath": "Backend/Cognition/soul_core.py"
}
```

---

## Phase C: Student Training

### C.1 Base Model Selection
| Model | Size | 4-bit VRAM | Why |
|-------|------|------------|-----|
| Gemma-2-2B-it | 2B | ~1.5GB | Already tested, fits easily |
| Qwen2.5-7B | 7B | ~4GB | Target model, fits RTX 4060 |
| DeepSeek-Coder-6.7B | 6.7B | ~4GB | Best for code, strong alternative |

**Recommendation**: Start with **Gemma-2-2B** for rapid prototyping, then scale to **Qwen2.5-7B** for production.

### C.2 Training Configuration
```python
# From train_concordia_worker.py (verified working)
max_seq_length = 4096
load_in_4bit = True
lora_r = 16
lora_alpha = 32
batch_size = 2
gradient_accumulation = 4
max_steps = 200  # More steps for real data
learning_rate = 2e-4
```

### C.3 Training Objective
**Primary**: Skeleton → Full code reconstruction
**Secondary**: Skeleton → Teacher output (distillation)
**Loss**: Cross-entropy on the full output tokens

### C.4 Training Loop
```
for each epoch:
  for each batch:
    skeleton_tokens = tokenize(batch.skeleton)
    full_tokens = tokenize(batch.full)
    
    # Forward pass on skeleton
    outputs = model(skeleton_tokens)
    
    # Loss against full output
    loss = cross_entropy(outputs.logits, full_tokens)
    
    # Backward pass
    loss.backward()
    optimizer.step()
```

---

## Phase D: Expansion Head

### D.1 Architecture
```
Input: Skeleton tokens (from Phoenix 7B output)
  ↓
Embedding Layer (d_model=768)
  ↓
2x Transformer Decoder Layers (d_model=768, n_heads=12)
  ↓
Linear Projection (d_model → vocab_size)
  ↓
Output: Full text tokens
```

### D.2 Training
- **Model**: 500M-1B parameters
- **Data**: Same skeleton→full pairs from Phase A
- **Objective**: Given skeletonized output from Phoenix 7B, expand to full natural language/code
- **Quantization**: 4-bit for inference, fits in ~0.3GB

### D.3 ONNX Export
```python
import torch.onnx

dummy_input = torch.randint(0, 32000, (1, 512))  # skeleton tokens
torch.onnx.export(
    expansion_head,
    dummy_input,
    "phoenix_expansion.onnx",
    opset_version=17,
    input_names=["skeleton_tokens"],
    output_names=["full_tokens"],
    dynamic_axes={"skeleton_tokens": {0: "batch", 1: "seq_len"}}
)
```

---

## Phase E: Inference Pipeline

### E.1 Runtime Architecture
```mermaid
flowchart LR
    Input[Raw Input] --> TS[TokenSlayer<br/>Skeletonize]
    TS --> P7B[Phoenix 7B<br/>4-bit ~4GB VRAM]
    P7B --> EH[Expansion Head<br/>500M 4-bit ~0.3GB VRAM]
    EH --> Output[Full Output]
```

### E.2 Memory Budget (RTX 4060 - 8GB)
| Component | Size | Notes |
|-----------|------|-------|
| Phoenix 7B (4-bit) | ~4.0 GB | Qwen2.5-7B or DeepSeek-Coder-6.7B |
| Expansion Head (4-bit) | ~0.3 GB | 500M params |
| KV Cache (20x smaller) | ~0.3 GB | Skeletonized input = 5% tokens |
| CUDA overhead | ~1.0 GB | PyTorch, CUDA kernels |
| **Total** | **~5.6 GB** | **2.4 GB headroom** |

### E.3 Performance Projections
| Metric | Without Phoenix | With Phoenix | Improvement |
|--------|----------------|-------------|-------------|
| Effective context | 4K tokens | 80K tokens | **20x** |
| Max file size | ~200 lines | ~4,000 lines | **20x** |
| Inference speed | 30 tok/s | 35 tok/s | **~15% faster** |
| VRAM usage | 6 GB | 5.6 GB | **~7% less** |

---

## Implementation Roadmap

### Sprint 1: Data Pipeline (1-2 days) ✅
- [x] Create `Training/generate_phoenix_data.py`
- [x] Run TokenSlayer on all LUMAX source files
- [x] Generate 270+ skeleton→full pairs
- [x] Validate pair quality (manual spot-check 10 pairs)

### Sprint 2: Teacher Distillation (1 day) ✅
- [x] Create `Training/distill_teacher.py`
- [x] Send skeletons to DeepSeek V4 via Ollama Cloud API
- [x] Store teacher outputs
- [x] Compare teacher vs original (quality check)

### Sprint 3: Student Training (2-3 days) ✅
- [x] Create `Training/train_phoenix_student.py`
- [x] Fine-tune Gemma-2-2B on skeleton→full pairs
- [x] Evaluate reconstruction accuracy
- [x] Scale to Qwen2.5-7B if 2B results are promising

### Sprint 4: Expansion Head (1-2 days) ✅
- [x] Create `Training/train_expansion_head.py`
- [x] Train 500M expansion head
- [x] Export to ONNX
- [x] Test end-to-end pipeline

### Sprint 5: Benchmarking (1 day) ✅
- [x] Create `Training/benchmark_phoenix.py`
- [x] Compare Phoenix 7B vs raw 7B on code tasks
- [x] Compare Phoenix 7B vs 70B teacher (quality)
- [x] Measure VRAM, speed, accuracy

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| 7B doesn't fit in 8GB VRAM | Medium | High | Use 2B for PoC, then try 7B with more aggressive quantization (2-bit) |
| Teacher distillation degrades quality | Medium | Medium | Keep original full code as ground truth; use teacher for style transfer only |
| Expansion head is too large | Low | Medium | Reduce to 300M params or use distillation from 500M→300M |
| Training data is too small | High | Medium | Augment with open-source codebases (GitHub Python repos) |
| Model overfits to LUMAX codebase | Medium | High | Add validation split, test on unseen code |

---

## Success Criteria

1. **Phoenix 7B can reconstruct full code from skeleton with >90% accuracy** (measured by BLEU or exact match on function bodies)
2. **End-to-end pipeline runs on RTX 4060 with <6GB VRAM**
3. **Effective context window is 20x larger** (can process 4,000-line files vs 200-line files)
4. **Output quality matches or exceeds raw 7B** on code generation tasks
5. **Expansion head exports to ONNX and runs in <100ms** on RTX 4060

---

## "No More Cloud Only" — The Slogan in Practice

```mermaid
flowchart TD
    subgraph "Before Phoenix"
        B1[70B Model<br/>Cloud Only] --> B2[$5-10/day API costs]
        B1 --> B3[Latency: 2-5 seconds]
        B1 --> B4[Privacy: Data leaves device]
    end

    subgraph "After Phoenix"
        P1[Phoenix 7B<br/>Local on RTX 4060] --> P2[$0/day API costs]
        P1 --> P3[Latency: 0.5-1 second]
        P1 --> P4[Privacy: All local]
        P1 --> P5[Performance: 70B-level]
    end
```

The Phoenix architecture compresses the **input** (via TokenSlayer) and the **model** (via distillation) simultaneously, achieving 70B-level performance on a 7B that fits in 8GB VRAM. No cloud required.