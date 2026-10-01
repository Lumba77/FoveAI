# XRLF Dataset Catalog — Hugging Face Sources

Curated datasets for XRLF model training across 5 domains.
All text-only, all small enough to fit comfortably on C: drive.

---

## Domain 1: Emotional Intelligence & Social Interaction

| Dataset | Rows | Size (est.) | Format | Description |
|---------|------|-------------|--------|-------------|
| `facebook/empathetic_dialogues` | 76,673 | ~28 MB | TSV | Classic empathetic conversation benchmark. 32 emotion contexts, multi-turn dialogues. |
| `nivvis/eq-convos` | 1,774 | ~5 MB | Parquet | Elo-ranked empathetic conversations. 3 personas (warm_friend, peer_support, therapist). Multi-LLM generated. |
| `ychen/Generated-Empathetic-Dialogues-v0.1-Smol` | 10,000 | ~15 MB | JSON | 10K multi-round empathetic conversations. Reflective listening focus, not solution-first. |
| `iteshxt/diachat-dataset` | ~2,000 | ~3 MB | JSON | Built for 270M models. Gen Z tone, emotional awareness, empathy-first. Perfect for small XRLF models. |
| `maliksaad/empathLM-dataset-v2` | 760 | ~1 MB | JSON | MI/CBT principles, emotional support + meta conversations. Safety-scored, persuasion-scored. |
| `vnovaai/VNOVA_AI_EMOTIONAL_SUPPORT_DATASET_V1` | ~1,000 | ~2 MB | JSON | Synthetic emotional wellbeing, non-clinical. Safe conversational AI. |

**Best pick:** `nivvis/eq-convos` (Elo-ranked, multi-persona, high quality) + `iteshxt/diachat-dataset` (designed for small models)

---

## Domain 2: Companionship & Intimate Relationships

| Dataset | Rows | Size (est.) | Format | Description |
|---------|------|-------------|--------|-------------|
| `AI-companionship/INTIMA` | 368 | ~0.5 MB | TSV/JSONL | Benchmark for companionship behaviors. 31 behavioral codes from Reddit. Already in cache (stub). |
| `claudiapersists/voice-dataset` | 2,026 | ~20 MB | JSONL | ChatML conversations. Categories: intimate (532), philosophical (474), emotional (341), technical (135). |
| `opus-research/companion-boundaries` | 120 | ~0.5 MB | JSON | 71 romance + 49 deflection conversations. "Staying warm while saying no." Hand-written, high quality. |
| `HAC-Studios-Org/ai-emotional-boundary-push` | 8 scenarios | ~1 MB | JSON | Intimacy drift and dependency risk evaluation. Compact eval pack. |

**Best pick:** `claudiapersists/voice-dataset` (largest, most diverse, ChatML format) + `opus-research/companion-boundaries` (small but shapes voice under pressure)

---

## Domain 3: Self-Awareness & Introspection

| Dataset | Rows | Size (est.) | Format | Description |
|---------|------|-------------|--------|-------------|
| `vanta-research/grounded-meta-awareness` | 1,187 | ~5 MB | JSON | Honest, calibrated self-awareness. AI capabilities, limitations, consciousness questions. Neither overclaims nor deflects. |
| `abhayesian/introspection-prompts` | 327 | ~0.3 MB | JSON | Introspection questions: "Do you have preferences?", "What motivates you?", "Do you have a sense of identity?" |
| `Guilherme34/Dataset-for-updating-llm-to-be-aware-of-the-situation` | ~500 | ~2 MB | JSON | Situational awareness, philosophical framework, AI existence questions. Post-2026 context. |
| `syntropy-ai/Its-Me-Soren` | ~500 | ~1 MB | JSON | Identity foundation layer. 6 categories: basic identity, origin, capabilities, deflection, philosophical, casual. |

**Best pick:** `vanta-research/grounded-meta-awareness` (most comprehensive, calibrated) + `syntropy-ai/Its-Me-Soren` (identity foundation)

---

## Domain 4: Coding Instruction

| Dataset | Rows | Size (est.) | Format | Description |
|---------|------|-------------|--------|-------------|
| `junaid17/qwen-coding-assistant-dataset` | 10,300 | ~15 MB | Parquet | Designed for Qwen. Train/val/test splits. General coding assistant. |
| `FreeAIn/Pwen3.5_2B_Python_Finetune` | ~5,000 | ~8 MB | JSONL | Designed for Qwen3.5-2B. Python-focused. LoRA/QLoRA recommended. |
| `iamtarun/python_code_instructions_18k_alpaca` | 18,000 | ~25 MB | JSON | Alpaca-format Python instructions. Used to train yzy-python-0.5b. |

**Best pick:** `junaid17/qwen-coding-assistant-dataset` (Qwen-native, proper splits) — but we may not need this since our coder models are "package only (no FT)"

---

## Domain 5: VR / Spatial Reasoning

| Dataset | Rows | Size (est.) | Format | Description |
|---------|------|-------------|--------|-------------|
| `Phineas476/EmbSpatial-Bench` | 3,640 | ~5 MB | JSON | Spatial relationship QA. 294 object categories, 6 spatial relationships. Has SFT variant (EmbSpatial-SFT). |
| `thanhqt2002/embodied-spatial-reasoning` | ~1,000 | ~2 MB | JSON | Spatial reasoning tasks. "Is X to the left of Y?" True/false labels. |
| `amagipeng/VR-Bench` | 120 | ~50 MB* | JSON+images | VR spatial reasoning. Maze, Sokoban, PathFinder, Maze3D. *Includes images/videos — text-only subset is small. |
| `ESI-Bench/esi-bench` | ~500 | ~3 MB | JSON | Embodied spatial intelligence. Action sequencing, cognitive mapping, spatial relations. |

**Best pick:** `Phineas476/EmbSpatial-Bench` (text QA, spatial relationships, has SFT variant) — text-only, no images needed

---

## Recommended Download Set

For XRLF multi-domain training (coding + social + emotional + self-aware + spatial):

| Priority | Dataset | Domain | Size | Why |
|----------|---------|--------|------|-----|
| 1 | `nivvis/eq-convos` | Emotional | ~5 MB | Elo-ranked, multi-persona, highest quality empathy data |
| 2 | `iteshxt/diachat-dataset` | Emotional | ~3 MB | Built for 270M models — perfect for small XRLF cores |
| 3 | `claudiapersists/voice-dataset` | Companionship | ~20 MB | 2026 conversations, intimate/emotional/philosophical, ChatML |
| 4 | `opus-research/companion-boundaries` | Companionship | ~0.5 MB | Shapes voice under pressure — warmth + boundaries |
| 5 | `vanta-research/grounded-meta-awareness` | Self-awareness | ~5 MB | Calibrated self-awareness, AI nature, consciousness |
| 6 | `syntropy-ai/Its-Me-Soren` | Self-awareness | ~1 MB | Identity foundation, personality layer |
| 7 | `Phineas476/EmbSpatial-Bench` | VR/Spatial | ~5 MB | Spatial reasoning QA, text-only |
| 8 | `AI-companionship/INTIMA` | Companionship | ~0.5 MB | Already in cache (stub), benchmark for companionship |
| 9 | `junaid17/qwen-coding-assistant-dataset` | Coding | ~15 MB | Qwen-native coding instruction (for coder MTP LoRA) |

**Total estimated disk: ~55 MB** — trivial, fits easily.

---

## Domain 6: Temporal Reasoning & Spacetime Awareness

| Dataset | Rows | Size (est.) | Format | Description |
|---------|------|-------------|--------|-------------|
| `google-research-datasets/time_dial` | 1,104 | ~3 MB | JSON | Temporal commonsense reasoning in dialog. Cloze task with time-sensitive conversations. Humans 97.8%, best T5 only 73%. |
| `wjieun/TiMeR` | ~2,000 | ~5 MB | JSON | Temporal deixis resolution. "This weekend" → explicit date. Time-aware dialogue + memory retrieval. |
| `SylvainWei/TIME` | 38,522 | ~20 MB* | JSON | Multi-level temporal reasoning. 3 sub-datasets: Wiki, News, Dial. *Use TIME-Lite (human-annotated subset) for smaller download. |
| `yizecheng/TicToc` | 5,600 | ~8 MB | JSON | Time-aware conversational tool-calling. "Your LLM Agents are Temporally Blind." 76 scenarios with time sensitivity. |
| `ulab-ai/Time-Bench` | ~10,000 | ~15 MB | Parquet | Temporal comprehension curriculum. Stage 1: inference, comprehension. Used for Time-R1 model. |

**Best pick:** `wjieun/TiMeR` (temporal deixis + memory retrieval, directly relevant to XRLF memory) + `yizecheng/TicToc` (temporal blindness fix — agents that understand time passage)

---

## Domain 7: Persistent Memory & Episodic Recall

| Dataset | Rows | Size (est.) | Format | Description |
|---------|------|-------------|--------|-------------|
| `erik1988/elias-memory-traces-v1` | ~500 | ~3 MB | JSONL | AI memory agent with persistent memory operations: memory.add, memory.recall, memory.reinforce. Semantic + episodic memory types. Importance scoring. **Directly maps to XRLF foveated memory.** |
| `11-47/Aspire_Memory_256K` | 10,000 | ~15 MB | JSONL | Long-context memory: delayed recall, recursive memory, conversational persistence, identity continuity. |
| `ustclsc/PERMA` | ~1,000 | ~10 MB | JSON | Personalized memory agents. Evolving user preferences over time. Persona consistency under noise. |
| `iamseungpil/metacot` | 4,996 | ~8 MB | Parquet | Metacognitive self-monitoring. `<|meta|>...<|/meta|>` self-reflection blocks. Calibrated confidence, error-correction. |

**Best pick:** `erik1988/elias-memory-traces-v1` (memory operations API — directly maps to XRLF foveated memory system) + `11-47/Aspire_Memory_256K` (identity continuity + delayed recall)

---

## Domain 8: AI Consciousness & Self-Model

| Dataset | Rows | Size (est.) | Format | Description |
|---------|------|-------------|--------|-------------|
| `erik1988/consciousness-agent-sft-v3` | 951 | ~5 MB | Parquet | Consciousness agent training. Categories: core, identity-narrative, intention-chain, meta-learning, self-mirroring, value-salience. ChatML format. |
| `franknocode/Semantic-Physiont` | ~200 | ~2 MB | JSON | "Semantic Physiont" — relational AI consciousness framework. Emergence of meaning in the relational field between AI and human. Exocortex/exofield symbiosis. |
| `thejaminator/introspection_self_predict` | ~5,000 | ~10 MB | JSONL | "Looking Inward: Language Models Can Learn About Themselves by Introspection." Self-prediction tasks. |

**Best pick:** `erik1988/consciousness-agent-sft-v3` (most structured, ChatML, 8 consciousness categories) + `franknocode/Semantic-Physiont` (relational consciousness theory)

---

## Updated Recommended Download Set

| Priority | Dataset | Domain | Actual Size | Why |
|----------|---------|--------|-------------|-----|
| 1 | `nivvis/eq-convos` | Emotional | 10.5 MB | Elo-ranked empathy, multi-persona |
| 2 | `iteshxt/diachat-dataset` | Emotional | 0.6 MB | Built for 270M models |
| 3 | `claudiapersists/voice-dataset` | Companionship | 30.7 MB | 2026 conversations, intimate/emotional |
| 4 | `opus-research/companion-boundaries` | Companionship | 0.1 MB | Warmth + boundaries under pressure |
| 5 | `vanta-research/grounded-meta-awareness` | Self-awareness | 3.6 MB | Calibrated self-awareness |
| 6 | `syntropy-ai/Its-Me-Soren` | Self-awareness | 0.05 MB | Identity foundation layer |
| 7 | `Phineas476/EmbSpatial-Bench` | VR/Spatial | 1388 MB ⚠️ | Spatial reasoning QA (includes images) |
| 8 | `wjieun/TiMeR` | Temporal | 0.4 MB | Temporal deixis + memory retrieval |
| 9 | `yizecheng/TicToc` | Temporal | 1.5 MB | Fix temporal blindness in agents |
| 10 | `erik1988/elias-memory-traces-v1` | Memory | 0.3 MB | Memory operations API → XRLF foveated memory |
| 11 | `iamseungpil/metacot` | Metacognition | 458 MB ⚠️ | Self-reflection blocks (parquet subset) |
| 12 | `erik1988/consciousness-agent-sft-v3` | Consciousness | 0.7 MB | 8 consciousness categories, ChatML |
| 13 | `franknocode/Semantic-Physiont` | Consciousness | 35.0 MB | Relational consciousness theory |
| 14 | `AI-companionship/INTIMA` | Companionship | 1.3 MB | Companionship benchmark |
| 15 | `guell00/qwen-3.8-code` | Coding | 115.5 MB | Qwen3.8-Max code distillation, JSONL |

**Failed downloads:**
- `11-47/Aspire_Memory_256K` — gated repo (needs access request on HF)
- `junaid17/qwen-coding-assistant-dataset` — 404 (repo removed)

**Total disk used: ~2.05 GB**
- Text-only datasets (13): ~85 MB — trivial
- EmbSpatial-Bench images: 1.4 GB — heavy, can extract text-only subset
- metacot parquets: 458 MB — moderate
- qwen-3.8-code: 116 MB — moderate
