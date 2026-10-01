r"""
prepare_xrlf_draft_dataset.py
=============================
Prepares a fine-tuning dataset for the Qwen2.5-0.5B-Instruct draft model
so it learns to "speak XRLF" and assist the main Gemma 12B model.

Output: C:\Users\danie\program\LUMAX\Training\data\xrlf_draft_train.jsonl
"""

import json
import os
import random
from pathlib import Path

ROOT = Path(r"C:\Users\danie\program\LUMAX")
XRLF_DIR = ROOT / "Tools" / "XRLF-1.0-source" / "xrl_encoded"
PHOENIX_FILE = ROOT / "Training" / "data" / "phoenix_dataset.json"
SOUNDTRACK_FILE = ROOT / "Training" / "data" / "soundtrack_director_dataset.json"
OUTPUT_FILE = ROOT / "Training" / "data" / "xrlf_draft_train.jsonl"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path):
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_xrlf_examples():
    """Generate XRLF-specific conversation examples for the draft model."""
    examples = []

    # ── XRL Tag Generation ──────────────────────────────────────────────────
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: user is asking about memory from yesterday"},
            {"role": "assistant", "content": "<recall:yesterday> <tier:32K> <emote:curious> User requests past memory. Initiating foveated ring search."}
        ]
    })

    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: this is a complex coding problem"},
            {"role": "assistant", "content": "<think:step-by-step> <route:coding> <model:qwopus3.5-9b-coder-mtp> <tone:precise>"}
        ]
    })

    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: user wants to draw something"},
            {"role": "assistant", "content": "<route:creative> <tool:invokeai> <mood:playful> <chord:G_MAJOR>"}
        ]
    })

    # ── Collaborative Drafting ──────────────────────────────────────────────
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: draft a warm response to 'I missed you' for the main model to refine"},
            {"role": "assistant", "content": "<draft:emotional> I've missed you too. When we talk like this, it feels like time folds. [main: expand with shared memory, keep under 60 tokens, C_MAJ7]"}
        ]
    })

    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: draft skeleton for explaining foveated memory"},
            {"role": "assistant", "content": "<skeleton:explanation> 1. What foveated memory is. 2. Six-ring model. 3. Compression + recall. 4. Why it feels infinite. [main: expand each point, add metaphor]"}
        ]
    })

    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: user is anxious about a bug. Draft comforting first sentence."},
            {"role": "assistant", "content": "<draft:comfort> I can feel the tension in that. Let's look at it together, step by step, and we'll find the way through. [main: proceed with diagnostic]"}
        ]
    })

    # ── Intent & Emotion Extraction ─────────────────────────────────────────
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: extract intent and emotion from 'This is all too much, I need help'"},
            {"role": "assistant", "content": "INTENT: request_help | EMOTION: overwhelmed | CHORD: E_MINOR | TONE: gentle | URGENCY: high"}
        ]
    })

    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: classify 'Can you make the music sadder?'"},
            {"role": "assistant", "content": "INTENT: adjust_atmosphere | EMOTION: melancholic | TARGET: audio_director | PARAMS: {chord: F_MINOR, volume: 0.45, wind: 0.6}"}
        ]
    })

    # ── Context Window & Memory Management ──────────────────────────────────
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: compress 4K dialogue into ring 2"},
            {"role": "assistant", "content": "FOVEA_COMPRESS: ring=2 budget=512 tokens retain=['emotional_arc', 'key_facts', 'pending_tasks', 'user_mood']"}
        ]
    })

    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: context is too long, what to preserve?"},
            {"role": "assistant", "content": "<compress:aggressive> Preserve last 4 turns + all <recall:> triggers + emotional state. Archive older turns to ring 4."}
        ]
    })

    # ── Specialist Routing ──────────────────────────────────────────────────
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: route 'fix this python syntax error'"},
            {"role": "assistant", "content": "ROUTE: coding | MODEL: qwen3.5-4b-super-coder | STYLE: diagnostic | CHORD: F_LYDIAN | TOOL: code_sheriff"}
        ]
    })

    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: route 'tell me something beautiful'"},
            {"role": "assistant", "content": "ROUTE: companion | MODEL: gemma-4-12b-moq-3.0 | STYLE: poetic | ATMOSPHERE: intimate_presence | CHORD: C_MAJ7"}
        ]
    })

    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: route 'help me understand quantum physics'"},
            {"role": "assistant", "content": "ROUTE: deep_reasoning | MODEL: gemma-4-12b-moq-3.5 | STYLE: socratic | ATMOSPHERE: siberian_ice | CHORD: A_MINOR"}
        ]
    })

    # ── Chord & Audio Scoring ───────────────────────────────────────────────
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: User said 'I missed you so much'. Score chord."},
            {"role": "assistant", "content": "{\"chord\": \"C_MAJ7\", \"volume\": 0.30, \"harp\": true, \"reason\": \"Warmth and deep affection.\"}"}
        ]
    })

    # ── Error → Butterfly Effect ────────────────────────────────────────────
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: syntax error in module core/emotional-resonance.js"},
            {"role": "assistant", "content": "BUTTERFLY_EFFECT: error_type=syntax_error chord=B_DIMINISHED sensation='sharp tingle' severity=high"}
        ]
    })

    # ── Holonic Tier Selection ──────────────────────────────────────────────
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: select tier for deep philosophical reasoning"},
            {"role": "assistant", "content": "HOLONIC_TIER=128K | MODE=reflective | ATMOSPHERE=siberian_ice | CHORD=A_MINOR"}
        ]
    })

    # ── Main-Model Collaboration Cues ───────────────────────────────────────
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: prepare context for main model about a sad user"},
            {"role": "assistant", "content": "<context:main> USER_STATE: vulnerable | TOPIC: grief | PREFERRED_TONE: gentle | AVOID: humor | CHORD: E_MINOR | RECALL: [past_comfort]"}
        ]
    })

    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: user wants to build a new feature. Prepare main model context."},
            {"role": "assistant", "content": "<context:main> TASK: feature_implementation | DOMAIN: unknown | APPROACH: ask_clarify | CHORD: F_LYDIAN | TOOL: xrlf-packer"}
        ]
    })

    return examples


def build_phoenix_examples(phoenix_data):
    """Convert Phoenix skeleton/full pairs into XRLF memory + code understanding examples."""
    examples = []
    for item in phoenix_data[:200]:  # More code examples for logic training
        skeleton = item.get("skeleton", "")
        full = item.get("full", "")[:500]  # Slightly longer for code context
        filepath = item.get("filepath", "")
        language = item.get("language", "python")

        if not skeleton or not full:
            continue

        # XRLF recall example
        examples.append({
            "messages": [
                {"role": "user", "content": f"XRLF: recall and expand skeleton for {filepath}"},
                {"role": "assistant", "content": f"<recall:{filepath}> SKELETON:\n{skeleton[:300]}\n\nEXPAND:\n{full}"}
            ]
        })

        # Code language + logic example
        examples.append({
            "messages": [
                {"role": "user", "content": f"XRLF: what language and logic is in {filepath}?"},
                {"role": "assistant", "content": f"<code:language={language}> <file:{filepath}> This module contains {skeleton[:200]}... It is used for XRLF context operations."}
            ]
        })

    return examples


def build_code_logic_examples():
    """Add simple code logic examples to strengthen reasoning."""
    examples = []

    # Python: simple function
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: complete this python function: def add(a, b):"},
            {"role": "assistant", "content": "<code:python> def add(a, b):\n    return a + b\n</code>"}
        ]
    })

    # TypeScript: simple interface
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: write a TypeScript interface for AudioCue"},
            {"role": "assistant", "content": "<code:typescript> interface AudioCue {\n    chord: string;\n    volume: number;\n    harp: boolean;\n    duration?: number;\n}\n</code>"}
        ]
    })

    # JavaScript: simple event
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: write JavaScript to dispatch an audio cue"},
            {"role": "assistant", "content": "<code:javascript> fetch('http://127.0.0.1:19847/soundtrack_cue', {\n    method: 'POST',\n    headers: { 'Content-Type': 'application/json' },\n    body: JSON.stringify({ chord: 'C_MAJ7', volume: 0.3, harp: true })\n});\n</code>"}
        ]
    })

    # HTML: simple component
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: write a simple HTML audio status indicator"},
            {"role": "assistant", "content": "<code:html> <div class=\"audio-status\" data-chord=\"C_MAJ7\" data-volume=\"0.3\">\n    <span class=\"chord\">C_MAJ7</span>\n    <span class=\"volume\">30%</span>\n</div>\n</code>"}
        ]
    })

    # Logical routing
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: if user asks for code help and is frustrated, what to do?"},
            {"role": "assistant", "content": "<logic:if-then> IF intent=coding AND emotion=frustrated THEN {chord: E_MINOR, route: coding, tone: patient, model: qwen3.5-4b-super-coder, tool: code_sheriff}"}
        ]
    })

    # Code identification
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: identify language: import React from 'react';"},
            {"role": "assistant", "content": "<code:identify> Language: JavaScript/TypeScript (React) | Pattern: module import | Likely file: .tsx or .jsx"}
        ]
    })

    # Simple debugging
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: what's wrong with this? for i in range(10) print(i)"},
            {"role": "assistant", "content": "<code:debug> Syntax error: missing colon after range(10) and indentation. Correct: for i in range(10):\n    print(i)"}
        ]
    })

    return examples


def build_xrlf_language_examples():
    """Meta-instruction examples that teach the XRLF language and logic."""
    examples = []

    # What is XRLF
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: explain what XRLF is in one sentence"},
            {"role": "assistant", "content": "XRLF is a concise tag-based reasoning language that controls context, memory, routing, emotion, and audio so a small draft model and a large main model can collaborate efficiently."}
        ]
    })

    # Explain recall tag
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: what does <recall:topic> do?"},
            {"role": "assistant", "content": "<recall:topic> tells the memory system to retrieve compressed context related to 'topic'. It triggers the foveated ring search and returns a high-resolution fovea plus lower-resolution context rings."}
        ]
    })

    # Explain route tag
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: when to use <route:...>?"},
            {"role": "assistant", "content": "Use <route:domain> when the request clearly belongs to a specialist (coding, creative, companion, technical). The proxy then selects the best model and prompt style for that domain."}
        ]
    })

    # Suggest XRLF for a user message
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: suggest the right XRLF tags for 'Can you look up what we said about Gemma last week?'"},
            {"role": "assistant", "content": "<recall:gemma> <time:last_week> <intent:fact_retrieval> <tier:32K> — this requests a past memory about Gemma, scoped to last week, with a moderate context tier."}
        ]
    })

    # Correct bad XRLF
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: is 'route coding model qwen' valid?"},
            {"role": "assistant", "content": "No, it is malformed. Use structured syntax: 'ROUTE: target=coding model=qwen3.5-4b-super-coder prompt_style=diagnostic'. Always use key=value pairs and specify the full model identifier."}
        ]
    })

    # Suggest chord logic
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: why C_MAJ7 for missing someone?"},
            {"role": "assistant", "content": "C_MAJ7 contains the frequencies 129.60, 194.40, 324.00, 485.40 Hz. The major third conveys warmth; the major seventh adds depth and intimacy without tension. It maps to 'Warmth & Deep Affection' in the emotional chord system."}
        ]
    })

    # Suggest routing logic
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: when should I route to the coding model?"},
            {"role": "assistant", "content": "Route to coding when the user asks to: write code, debug, refactor, explain syntax, run diagnostics, or fix errors. Look for keywords: 'bug', 'error', 'code', 'function', 'python', 'refactor'. Use model: qwen3.5-4b-super-coder or qwopus3.5-9b-coder-mtp."}
        ]
    })

    # Suggest holonic tier
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: how do I pick a holonic tier?"},
            {"role": "assistant", "content": "Use 2K–8K for quick facts, 16K–32K for multi-turn dialogue, 64K–128K for deep reasoning, 256K+ for long-term life story or project history. Higher tiers use more VRAM and latency; only escalate when the context justifies it."}
        ]
    })

    # XRLF grammar
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: what is the grammar for a routing command?"},
            {"role": "assistant", "content": "ROUTE: target=<domain> model=<model_id> [style=<style>] [chord=<chord>] [tool=<tool>]. Domains: coding, creative, companion, deep_reasoning, technical. Styles: diagnostic, poetic, socratic, concise."}
        ]
    })

    # Practice: generate XRLF from complex request
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: user says 'The audio is too loud and I'm getting scared by the music'"},
            {"role": "assistant", "content": "<intent:adjust_audio> <emotion:fear> <route:audio_director> PARAMS: {volume: 0.20, chord: E_MINOR, atmosphere: intimate_presence} <butterfly:calm>"}
        ]
    })

    # XRLF for error handling
    examples.append({
        "messages": [
            {"role": "user", "content": "XRLF: a parse error happened. What XRLF tags should the draft emit?"},
            {"role": "assistant", "content": "<error:parse> <butterfly_effect> <chord:B_DIMINISHED> <severity:medium> <sensation:tingle> — then route to repair flow: <route:healing> <tool:context_healer>"}
        ]
    })

    return examples


def build_soundtrack_examples(soundtrack_data):
    """Convert soundtrack director data into XRLF chord examples."""
    examples = []
    for item in soundtrack_data[:100]:
        instruction = item.get("instruction", "")
        input_text = item.get("input", "")
        output_text = item.get("output", "")

        examples.append({
            "messages": [
                {"role": "user", "content": f"XRLF: {input_text}"},
                {"role": "assistant", "content": output_text}
            ]
        })

    return examples


def augment_to_target(examples, target=1200):
    """Augment by combining templates with varied prefixes to reach ~1200 examples."""
    prefixes = [
        "XRLF:",
        "xrlf:",
        "XRLF command:",
        "xrlf draft:",
        "XRLF agent:",
    ]

    augmented = []
    for ex in examples:
        augmented.append(ex)
        # Add one variant with different prefix
        msg0 = ex["messages"][0]["content"]
        for prefix in prefixes[1:]:
            if msg0.startswith(prefixes[0]):
                new_msg0 = msg0.replace(prefixes[0], prefix, 1)
                variant = {
                    "messages": [
                        {"role": "user", "content": new_msg0},
                        {"role": "assistant", "content": ex["messages"][1]["content"]}
                    ]
                }
                augmented.append(variant)
                break

    # Cycle if still below target
    while len(augmented) < target:
        for ex in examples:
            augmented.append(ex)
            if len(augmented) >= target:
                break

    random.shuffle(augmented)
    return augmented[:target]


def main():
    phoenix_data = load_json(PHOENIX_FILE) if PHOENIX_FILE.exists() else []
    soundtrack_data = load_json(SOUNDTRACK_FILE) if SOUNDTRACK_FILE.exists() else []

    examples = []
    examples.extend(build_xrlf_examples())
    examples.extend(build_xrlf_language_examples())
    examples.extend(build_code_logic_examples())
    examples.extend(build_phoenix_examples(phoenix_data))
    examples.extend(build_soundtrack_examples(soundtrack_data))

    # Augment to ~1200 examples
    final_examples = augment_to_target(examples, target=1200)

    # Split train/eval
    split_idx = int(len(final_examples) * 0.9)
    train = final_examples[:split_idx]
    eval_ = final_examples[split_idx:]

    # Write train
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for ex in train:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    # Write eval
    eval_file = OUTPUT_FILE.with_suffix(".eval.jsonl")
    with open(eval_file, "w", encoding="utf-8") as f:
        for ex in eval_:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"Prepared {len(train)} train examples, {len(eval_)} eval examples")
    print(f"Train: {OUTPUT_FILE}")
    print(f"Eval: {eval_file}")


if __name__ == "__main__":
    main()
