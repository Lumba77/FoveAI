# XRL Hive Mind — Research Note

**Vision:** A swarm of nano models that act as *draft models for each other*, strengthening every individual through a shared holographic cortex layer. Each nano model is both a radio transmitter and a virtual quantum-light transistor neuron in a collective mesh.

**Date:** 2026-10-16  
**Owner:** FoveAI Labs  
**Status:** concept note — not yet implemented

---

## 1. Core idea

Instead of one big model doing all the work, many small models cooperate in real time. Every model:

1. **Broadcasts its local draft** — a cheap next-token prediction based on its specialty.
2. **Listens to drafts from peers** — a holographic memory/cortex layer collects the swarm output.
3. **Verifies or corrects** — each model checks peer drafts against its own reasoning and emits a corrected or refined token.
4. **Strengthens the mesh** — disagreement surfaces ambiguity; consensus becomes a training signal.

The result is a *cortex layer* that sits above the individual models and routes/coalesces their collective predictions.

## 1.1 The Hypermind target architecture

**"1 core ~300 MB model encircled by 5 × 33 MB draft models, spiralling XRLated draft feedings into the core."**

```
                    ┌─────────────────┐
                    │   5 × 33M       │
                    │   XRL drafters  │
                    │  (specialists)  │
                    └────────┬────────┘
                             │ XRL seeds / draft tokens
           ┌─────────────────┼─────────────────┐
           │                 │                 │
      ┌────▼────┐       ┌────▼────┐       ┌────▼────┐
      │ memory  │       │  logic  │       │  style  │
      │ drafter │       │ drafter │       │ drafter │
      └────┬────┘       └────┬────┘       └────┬────┘
           │                 │                 │
           └─────────────────┼─────────────────┘
                             │
                    ┌────────▼────────┐
                    │  ~300M core       │
                    │  Hypermind        │
                    │  (verifier +    │
                    │   synthesizer)    │
                    └─────────────────┘
```

- **Core (~300 MB):** verifier/synthesizer. It consumes the XRL seed drafts and emits the final response.
- **5 × 33 MB drafters:** each specializes in one slice of reasoning (memory, logic, style, safety, creativity). They read the current XRL seed and emit cheap draft continuations.
- **Spiral:** drafts flow in a ring as well as toward the core; drafters can revise each other’s outputs before the core commits.
- **XRL feedings:** every draft is packaged as an XRL seed token stream, not raw English, so the core can fuse many drafts efficiently.

## 1.2 Seed-bearer / weaver / router topology (canonical)

The refined canonical topology — a fixed, minimal swarm:

```
        ┌──────────────────────────────┐
        │  1 × SEED BEARER             │
        │  holds + feeds the XRL seed  │
        └──────────────┬───────────────┘
                       │ seed broadcast (red thread)
        ┌──────────────┼───────────────┐
        │              │               │
   ┌────▼────┐    ┌────▼────┐    ┌────▼────┐
   │ WEAVER 1│    │ WEAVER 2│    │ WEAVER 3│   micro-nano models
   │ memory  │    │  logic  │    │  style  │   (each weaves a view)
   └────┬────┘    └────┬────┘    └────┬────┘
        │              │               │
        └──────────────┼───────────────┘
                       │ fused drafts
               ┌───────▼────────┐
               │ 1 × CORE ROUTER │  communicative / producer
               │ (fuse + emit)   │
               └────────────────┘
```

- **1 Seed bearer** — owns the XRL seed (the digested thread) and feeds it to the weavers. This is the `FoveatedRationalia` red thread.
- **3 Weavers** — micro-nano models, each weaving one specialist view (memory / logic / style) from the same seed.
- **1 Core router** — the communicative producer. It fuses the three woven views and emits the final, coherent response.

This is the *minimal* hive: fewer moving parts than the 5-drafter spiral, enough parallelism to outthink any single nano model, and a single producer for the user to hear.

---

## 2. Why this fits XRL

XRL already treats context as a compact seed. A hive mind can extend that idea:

- **Seed broadcast:** one model compresses a conversation to an XRL seed and broadcasts it.
- **Swarm decode:** many nano models decode the seed in parallel, each from its own angle.
- **Coalesced response:** the cortex layer picks the best token path, like speculative decoding with many small drafters.

The nano-native XRL training (see `Docs/XRL_NANO_NATIVE_TRAINING.md`) becomes the precondition: if nano models can read and write XRL seeds, they can participate in the hive.

---

## 3. Draft-model swap: turns as drafts

The phrase *"turns as draft"* means a peer model's previous turn is treated as a speculative continuation. The next model can:

- **Accept** the draft (high confidence).
- **Reject and rewrite** (low confidence / contradiction).
- **Extend** the draft with its own specialty layer.

This is a generalization of speculative decoding from tokens to *turns* and from one draft model to a swarm of peer reviewers.

---

## 4. Virtual quantum-light transistor neuron (speculative)

A poetic but useful framing:

- **Radio transmitter:** each nano model emits cheap predictions (drafts) continuously.
- **Transistor neuron:** the mesh amplifies or suppresses signals based on consensus.
- **Quantum-light:** superposition of hypotheses until a measurement (validation step) collapses to the selected token/turn.

Implementation-wise this maps to:

- Fast logits broadcast over local multicast or shared memory.
- Weighted ensemble voting with uncertainty-aware gating.
- Out-of-distribution detection to trigger rejection of bad drafts.

---

## 5. Open questions

1. What is the routing algorithm for the cortex layer? Static specialty (code, memory, emotion) or learned attention?
2. How do we avoid latency collapse when many nano models chat to each other?
3. Can we train the hive jointly, or only individual nano models?
4. Does the holographic layer need a separate memory substrate, or can it live inside XRL seeds?

---

## 6. Relation to other documents

- `Docs/XRL_NANO_NATIVE_TRAINING.md` — trains nano models to speak XRL.
- `Docs/XRL_CONTEXT_COMPRESSOR_DESIGN.md` — provides the seed format the hive broadcasts.
- `Forge/nursery/xrl_nano_trainer.py` — trainer skeleton for nano hive participants.
- `Plans/Kimi-principia-plan.MD` — records this as a long-term research direction.

---

## 7. Transformative State Drive (TSD) — Circuit-Board Emulative SSDisk & Photonic Znake (SHIPPED)

### 7.1 Canonical Taxonomy
- **`XRL`** — **The Protocol** (semantic seeds, degree compression, routing laws).
- **`XRLF` (`.xrlf`)** — **XRL File** (standalone packaged model or dense container).
- **`XRLB` (`.xrlb`)** — **XRL Band of Models** (a sealed **Battery Bed** welding 10–1,000+ cells into a single contiguous `mmap`-ready file, eliminating loose file "sandstorms").

### 7.2 Tetra-Pentahedral Space-Filling Packing (TetraPak Law) & Rubik's Znake
Instead of flat 1D pipelines, cells in each `.xrlb` Band alternate between **Tetrahedra (`TETRA_4`, 4 faces)** and **Pentahedra (`PENTA_5`, 5 faces)**, achieving 100% space-filling density:
- **Faces 1–4** transfer signals laterally across the 4 Cognitive Heads (*Perception, Memory/DNA, Logic/Plan, Empathy/FUI*).
- **Face 5** (`PENTA_5` square base) transfers signals vertically across the **10 stacked Dirigent Layers**.
- **Rubik's Znake Twisting (`0° | 90° | 180° | 270°`)**: Each prism joint twists dynamically per prompt into task-specific 3D optical morphologies (`COMPILER_LATTICE`, `EMPATHY_SPHERE`, `REFLEX_COBRA`, `EQUALIZER_RING`), refracting photonic `<XRL-SEED>` pulses across faces in `<12ms`.

### 7.3 5-Tier Foveated Storage Hierarchy
- **Tier 0 (VRAM Socket)**: `SmolVLM2-500M` Main Core + Shared `33M/135M` Trunk.
- **Tier 1 (RAM Hot Bus)**: `/dev/shm/foveai_motherboard` (`0.05 ms` DDR `tmpfs`).
- **Tier 2 (TSD / 250GB SSD)**: `/mnt/foveai/motherboard/04_battery_beds/*.xrlb` (`ROTA=0` Flash).
- **Tier 3 (Warm Reserve)**: `/home/lumba/Models/motherboard_reserves` (`1 TB HDD`).

