# XRLF — Next Natural Steps: Implementation Plan

## Background

The `gemma-4-12b-xrl.xrlf` file (4.7 GB) exists. The runtime, memory engine, and multimodal hooks are scaffolded.
The four requested steps are:

1. **Benchmark** — reasoning + multimodal tests vs. source models
2. **Build-process docs** — replicable, version-pinned guide
3. **Memory engine init** — six-ring foveated memory + persistence verification
4. **Multimodal validation** — image/audio/video hook smoke tests

### Repo-alignment corrections from audit

This plan has been updated to match the current codebase rather than the original aspirational design:

- `MembraneEngine` already uses a single SQLite table with a `ring` integer column; separate tables are not required for the current implementation. See [memory/membrane_engine.py](memory/membrane_engine.py).
- The active ring sequence is currently: identity, task, ruecent, working, background, archive. This matches the runtime’s actual architecture and should be treated as the canonical model unless a deliberate schema refactor is planned.
- The multimodal hook layer already supports graceful stub-mode fallback and auto-detection. The validation step should test hook firing and schema validity, not require full local model tooling. See [tools/mm_hooks.py](tools/mm_hooks.py).
- Benchmarking should be conditional on the runtime environment: full GGUF-vs-XRLF comparison is only valid when a real core model is available; otherwise the benchmark should operate in stub mode and report steering-quality / hook-fire metrics instead of model-accuracy claims.

---

## Step 1 — Benchmark the XRLF Model

### Goal
Run a structured benchmark suite that compares the XRLF hybrid against the bare Gemma-4-12B GGUF core (and optionally a cloud baseline).

### What will be created

#### [NEW] `builder/probes/benchmark_suite.py`
A self-contained benchmark runner with:
- **Reasoning track** — GSM8K-lite (20 math word problems), ARC-Easy (20 science MCQs), MMLU-lite (20 general knowledge MCQs)
- **Coherence track** — multi-turn conversation coherence score (ROUGE-L self-similarity)
- **Multimodal track** — asks the model to describe a synthetic test image (checks hook fires, not model accuracy)
- **Speed track** — tokens/sec and time-to-first-token for XRLF vs. stub-only
- Outputs a `benchmark_results_<timestamp>.json` + human-readable Markdown table
- If a real GGUF core is absent, the benchmark should run in **compatibility mode** and clearly label the results as steering/hook smoke metrics, not model-quality scoring.

#### [NEW] `benchmark_run.py` (repo root)
One-command entry point:
```bash
python benchmark_run.py            # full suite
python benchmark_run.py --quick    # 5 questions per track
python benchmark_run.py --track reasoning
```

### Dependencies
- Runtime must load (the `.xrlf` exists)
- `llama-cpp-python` in venv for actual generation; if absent, runs in **stub mode** (validates XRL steering logic only)
- Benchmark mode must be explicit: `--mode full|stub|quick`

---

## Step 2 — Document the Build Process

### Goal
A single canonical `BUILD.md` that another engineer (or future Claude session) can follow to reproduce the current `.xrlf` from scratch.

### What will be created

#### [NEW] `BUILD.md` (repo root)
Sections:
1. **Prerequisites** — Python 3.11, venv, GGUF source path, CUDA version, flash-attn wheel
2. **Environment setup** — exact pip install commands from `requirements.txt`
3. **Source model distillation** — how XRL JSON artifacts were generated (Qwen3.5-4B probe → `xrl_encoded/`)
4. **XRLF packing** — `python run_xrlf.py --pack`
5. **Verification** — `python run_xrlf.py --test`
6. **File manifest** — size, SHA-256, description of every section in the packed `.xrlf`
7. **Extending the format** — how to add a new XRL section or swap the core GGUF
8. **Known issues & platform notes** (Windows-native, flash-attn WHL path, VRAM budgets)

#### [NEW] `_forge/build_manifest.py`
Auto-generates the file manifest section of `BUILD.md` by reading the `.xrlf` header + section table.

---

## Step 3 — Initialize the Memory Engine

### Goal
Start the six-ring foveated memory, write known seeds, close session, reopen and confirm retrieval — proving persistence.

### What will be created

#### [NEW] `memory/init_memory.py`
- Initialises `MembraneEngine` for a named session (`default`)
- Writes six seed memories (one per conceptual ring: identity, principles, recent context, episodic, semantic, procedural)
- Closes the engine (flushes SQLite)
- Re-opens and retrieves each ring — asserts 6/6 recall
- Prints a pass/fail table

#### [MODIFY] `memory/membrane_engine.py`
- Preserve the current single-table SQLite layout with a `ring` column and `session_id` filtering.
- Add explicit `ring_label` metadata support if needed for reporting, but do not change the engine to separate tables unless a deliberate refactor is required.
- Add `get_by_ring(ring_id)` retrieval method that queries the existing `ring` field.

### Canonical ring mapping
The repo’s active ring model is:

1. `identity` (ring 0)
2. `task` (ring 1)
3. `recent` (ring 2)
4. `working` (ring 3)
5. `background` (ring 4)
6. `archive` (ring 5)

This should be the default naming used in scripts and benchmark output unless the ring structure is intentionally refactored.

### Verification
```bash
python memory/init_memory.py
```
Expected output:
```
Ring 0 [identity]    ✅ persisted
Ring 1 [task]        ✅ persisted
Ring 2 [recent]      ✅ persisted
Ring 3 [working]     ✅ persisted
Ring 4 [background]  ✅ persisted
Ring 5 [archive]     ✅ persisted
All 6 rings verified. Persistence: OK.
```

---

## Step 4 — Multimodal Validation

### Goal
Confirm that image, audio, and video hooks are wired and fire correctly (hook-smoke test, not model-quality test).

### What will be created

#### [NEW] `tools/validate_mm_hooks.py`
- Loads the XRLF runtime in stub mode
- Sends a synthetic 4×4 pixel PNG (programmatically generated — no external file needed)
- Sends a 0.5-second sine-wave WAV (generated in-memory)
- Sends a frame sequence descriptor (video stub — hook fires with a text frame list)
- For each: asserts the hook was called, captures the hook's return, and checks schema validity
- Prints hook fire log

#### [MODIFY] `tools/mm_hooks.py`
- Add an `on_hook_fire` callback slot (for test instrumentation)
- Add `validate_schema(result)` helper
- Keep stub-mode fallback compatible with the current auto-detect design; do not assume external tools are installed
- Validation should accept either a real tool result or a synthetic stub result, as long as the schema and hook fire event are well-formed

---

## Execution Order

| # | Task | Command | ETA |
|---|------|---------|-----|
| 1 | Extend `membrane_engine.py` | code edit | — |
| 2 | Create `memory/init_memory.py` | code | — |
| 3 | Run memory init + verify | `python memory/init_memory.py` | 30s |
| 4 | Create `_forge/build_manifest.py` | code | — |
| 5 | Create `BUILD.md` | code | — |
| 6 | Create `tools/validate_mm_hooks.py` | code | — |
| 7 | Create `builder/probes/benchmark_suite.py` | code | — |
| 8 | Create `benchmark_run.py` | code | — |
| 9 | Run self-test gate | `python run_xrlf.py --test` | 60s |
| 10 | Run benchmark quick | `python benchmark_run.py --quick` | 120s |
| 11 | Run multimodal validation | `python tools/validate_mm_hooks.py` | 30s |

---

## Open Questions / Resolved by repo audit

> [!IMPORTANT]
> **Q1 — Benchmark baseline**: Should the benchmark also compare against the raw GGUF (bare `llama-cpp-python` without XRL steering), or just run XRLF in isolation and score against known correct answers?
>
> **Resolution**: Treat this as conditional. Full GGUF-vs-XRLF comparison is only valid when the runtime can load a real GGUF core. Otherwise the benchmark should run in stub mode and report hook/steering diagnostics rather than claiming model-quality results.

> [!IMPORTANT]
> **Q2 — Memory ring semantics**: The current `membrane_engine.py` stores all entries in a single SQLite table. Do you want the six rings to be separate tables, or a single table with a `ring_id` column (simpler, recommended)?
>
> **Resolution**: The current repo has already chosen the single-table approach with a `ring` integer. Keep that design unless a deliberate schema refactor is approved.

> [!NOTE]
> **Q3 — Multimodal tool availability**: For audio and image hooks, are any local tools installed (e.g. Kokoro TTS, Whisper STT, any vision encoder)? If not, the validation will run in **stub mode** (fire and log, no actual processing) — which is sufficient for hook verification.
>
> **Resolution**: This is already supported by the `tool` layer’s auto-detect + stub fallback behavior. Hook validation should assert the hook fired and returned schema-valid payloads, regardless of tool availability.

> [!NOTE]
> **Q4 — BUILD.md SHA generation**: Should `build_manifest.py` compute SHA-256 of the full `.xrlf` at pack time (slow, ~5 GB hashing), or only hash individual XRL sections (fast, kilobytes)?
>
> **Resolution**: For speed and reproducibility, prefer per-section hashing for the manifest and reserve full-file SHA-256 only for explicit release builds.
