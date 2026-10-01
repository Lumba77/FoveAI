"""
Combined Dataset Generator for the LUMAX Middleman Model.
Generates training data for all 4 proxy intelligence tasks:
  1. Context Router     — extract critical code from massive dumps
  2. XRL Compressor     — compress conversation turns into tight summaries
  3. Intent Classifier  — route user requests to the right LUMAX service
  4. Memory Ranker      — score relevance of recalled memories

All datasets are merged into a single JSONL for multi-task LoRA training.
The system prompt tells the model which "hat" to wear.
"""

import json
import os
import random

random.seed(42)
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "datasets")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════
# TASK 1: Context Router
# ══════════════════════════════════════════════════════════════════════

ROUTER_SYSTEM = (
    "You are a Context Router. Given a massive code dump and a user request, "
    "extract ONLY the names of functions, classes, or code blocks that are "
    "critical to fulfilling the request. Return a comma-separated list. "
    "Do not explain your reasoning."
)


def gen_router_samples(n=2000):
    verbs = [
        "get",
        "set",
        "update",
        "delete",
        "create",
        "fetch",
        "parse",
        "render",
        "initialize",
        "destroy",
        "validate",
        "process",
        "handle",
    ]
    nouns = [
        "User",
        "Config",
        "Database",
        "Session",
        "Request",
        "Response",
        "Token",
        "Cache",
        "UI",
        "Profile",
        "Socket",
        "Queue",
        "Worker",
    ]
    cls_adj = ["Base", "Abstract", "Default", "Async", "Sync", "Global", "Remote"]
    cls_noun = ["Manager", "Service", "Controller", "Handler", "Provider", "Factory"]

    samples = []
    for _ in range(n):
        code = ""
        entities = []
        for _ in range(random.randint(1, 4)):
            name = f"{random.choice(cls_adj)}{random.choice(cls_noun)}"
            entities.append(name)
            code += f"class {name} {{\n    constructor() {{}}\n    init() {{}}\n}}\n\n"
        for _ in range(random.randint(5, 15)):
            name = f"{random.choice(verbs)}{random.choice(nouns)}"
            entities.append(name)
            code += f"function {name}(data) {{\n    // implementation\n    return data;\n}}\n\n"

        targets = random.sample(entities, random.randint(1, min(3, len(entities))))
        requests = [
            f"Fix the bug in {targets[0]}",
            f"Refactor {', '.join(targets)} to use async/await.",
            f"I'm getting a timeout error when calling {targets[0]}.",
            f"Optimize {targets[0]} for better performance.",
            f"Add error handling to {targets[0]} and {targets[-1]}.",
        ]
        samples.append(
            {
                "messages": [
                    {"role": "system", "content": ROUTER_SYSTEM},
                    {
                        "role": "user",
                        "content": f"{code}\n---\n{random.choice(requests)}",
                    },
                    {"role": "assistant", "content": ", ".join(targets)},
                ]
            }
        )
    return samples


# ══════════════════════════════════════════════════════════════════════
# TASK 2: XRL Checkpoint Compressor
# ══════════════════════════════════════════════════════════════════════

XRL_SYSTEM = (
    "You are a Checkpoint Compressor. Given a multi-turn conversation, compress "
    "it into a tight factual summary that preserves: files edited, decisions made, "
    "errors encountered, and current status. Use bullet points. Be extremely concise."
)


def gen_xrl_samples(n=1500):
    actions = ["edited", "created", "deleted", "refactored", "debugged", "reviewed"]
    files = [
        "server.js",
        "soul_core.py",
        "smart-router.js",
        "main.ts",
        "config.json",
        "xr_app.py",
        "index.html",
        "package.json",
        "requirements.txt",
        "app.vue",
    ]
    errors = [
        "CORS blocked",
        "module not found",
        "timeout 500ms",
        "CUDA OOM",
        "null reference",
        "port already in use",
        "import failed",
        "type mismatch",
    ]
    decisions = [
        "switched to async",
        "moved to port 8200",
        "added retry logic",
        "chose Llama over Qwen",
        "enabled bf16",
        "added LoRA r=16",
        "used gradient checkpointing",
        "split into microservices",
    ]
    statuses = [
        "resolved",
        "in progress",
        "blocked on user input",
        "needs testing",
        "deployed to staging",
        "rolled back",
    ]

    samples = []
    for _ in range(n):
        num_turns = random.randint(3, 8)
        convo = []
        touched_files = random.sample(files, random.randint(1, 4))
        hit_errors = random.sample(errors, random.randint(0, 2))
        made_decisions = random.sample(decisions, random.randint(1, 3))
        status = random.choice(statuses)

        for t in range(num_turns):
            if t % 2 == 0:
                convo.append(
                    f"User: Can you {random.choice(actions)} {random.choice(touched_files)}? "
                    f"I'm seeing {random.choice(errors) if hit_errors else 'issues'}."
                )
            else:
                convo.append(
                    f"Assistant: Done. I {random.choice(actions)} {random.choice(touched_files)}. "
                    f"Decision: {random.choice(made_decisions)}."
                )

        conversation = "\n".join(convo)

        summary_lines = [f"- Files: {', '.join(touched_files)}"]
        if hit_errors:
            summary_lines.append(f"- Errors: {', '.join(hit_errors)}")
        summary_lines.append(f"- Decisions: {'; '.join(made_decisions)}")
        summary_lines.append(f"- Status: {status}")

        samples.append(
            {
                "messages": [
                    {"role": "system", "content": XRL_SYSTEM},
                    {"role": "user", "content": conversation},
                    {"role": "assistant", "content": "\n".join(summary_lines)},
                ]
            }
        )
    return samples


# ══════════════════════════════════════════════════════════════════════
# TASK 3: Intent Classifier
# ══════════════════════════════════════════════════════════════════════

INTENT_SYSTEM = (
    "You are an Intent Classifier for the LUMAX system. Given a user message, "
    "classify it into exactly one category: SOUL (cognition/reasoning), "
    "CREATIVE (art/music/design), MEMORY (recall/search/history), "
    "CODE (programming/debugging), SYSTEM (config/ports/services), "
    "or CHAT (casual conversation). Return only the category name."
)

INTENT_EXAMPLES = {
    "SOUL": [
        "What do you think about consciousness?",
        "Help me reason through this ethical dilemma.",
        "Analyze the implications of this decision.",
        "What's the deeper meaning behind this pattern?",
        "Can you reflect on what we discussed yesterday?",
        "Think step by step about this problem.",
        "What would be the philosophical consequences?",
    ],
    "CREATIVE": [
        "Design a logo for my startup.",
        "Generate an image of a futuristic city.",
        "Write me a poem about the ocean.",
        "Create a color palette for a dark theme.",
        "Compose some background music for a video.",
        "Design a poster for the event.",
        "Make me an artistic interpretation of this concept.",
    ],
    "MEMORY": [
        "What did we work on last session?",
        "Search for that bug we fixed last week.",
        "Do you remember the port number for the proxy?",
        "Find the conversation where we discussed LoRA.",
        "What files did I edit yesterday?",
        "Recall the decision we made about the database.",
        "Look up our previous discussion about training.",
    ],
    "CODE": [
        "Fix the bug in server.js line 42.",
        "Write a Python function to parse JSON.",
        "Debug this error: module not found.",
        "Refactor this class to use async/await.",
        "Add unit tests for the router module.",
        "Optimize this database query.",
        "Why is this function returning null?",
    ],
    "SYSTEM": [
        "What port is the Soul Core running on?",
        "Restart the foveated memory proxy.",
        "Check if LM Studio has models loaded.",
        "Update the .env configuration.",
        "Show me the service architecture.",
        "How much VRAM is being used?",
        "Configure the proxy to use port 8200.",
    ],
    "CHAT": [
        "Hey, how are you doing?",
        "Tell me a joke.",
        "What's the weather like?",
        "Good morning!",
        "Thanks for the help!",
        "That's really cool.",
        "I'm taking a break, be right back.",
    ],
}


def gen_intent_samples(n=1500):
    samples = []
    categories = list(INTENT_EXAMPLES.keys())
    for _ in range(n):
        cat = random.choice(categories)
        base = random.choice(INTENT_EXAMPLES[cat])
        # Add slight variations
        prefixes = ["", "Hey, ", "Can you ", "Please ", "I need you to ", ""]
        suffixes = ["", ".", " please.", " asap.", " when you can.", ""]
        msg = f"{random.choice(prefixes)}{base}{random.choice(suffixes)}".strip()

        samples.append(
            {
                "messages": [
                    {"role": "system", "content": INTENT_SYSTEM},
                    {"role": "user", "content": msg},
                    {"role": "assistant", "content": cat},
                ]
            }
        )
    return samples


# ══════════════════════════════════════════════════════════════════════
# TASK 4: Memory Ranker
# ══════════════════════════════════════════════════════════════════════

RANKER_SYSTEM = (
    "You are a Memory Ranker. Given a user's current request and a list of "
    "recalled memory fragments, score each fragment 0-10 for relevance. "
    "Return one line per fragment: SCORE | fragment_id. "
    "Only fragments scoring 7+ should be injected into context."
)


def gen_ranker_samples(n=1000):
    topics = [
        "proxy config",
        "LoRA training",
        "XR interface",
        "database migration",
        "port configuration",
        "CORS fix",
        "model loading",
        "UI rendering",
        "authentication flow",
        "WebSocket setup",
        "CUDA optimization",
        "tokenizer config",
        "gradient checkpointing",
        "service restart",
    ]

    samples = []
    for _ in range(n):
        # User's current request is about one topic
        current_topic = random.choice(topics)
        request = f"I need help with {current_topic}."

        # Generate 3-6 memory fragments, some relevant, some not
        num_frags = random.randint(3, 6)
        fragments = []
        scores = []
        for i in range(num_frags):
            frag_topic = random.choice(topics)
            frag_id = f"mem_{random.randint(1000, 9999)}"
            fragments.append(
                f"[{frag_id}] Previous work on {frag_topic}: resolved issue with {random.choice(topics)}."
            )
            # High score if topic matches, low if not
            if frag_topic == current_topic:
                scores.append(f"{random.randint(8, 10)} | {frag_id}")
            elif any(word in frag_topic for word in current_topic.split()):
                scores.append(f"{random.randint(5, 7)} | {frag_id}")
            else:
                scores.append(f"{random.randint(1, 4)} | {frag_id}")

        samples.append(
            {
                "messages": [
                    {"role": "system", "content": RANKER_SYSTEM},
                    {
                        "role": "user",
                        "content": f"Request: {request}\n\nMemories:\n"
                        + "\n".join(fragments),
                    },
                    {"role": "assistant", "content": "\n".join(scores)},
                ]
            }
        )
    return samples


# ══════════════════════════════════════════════════════════════════════
# TASK 5: Summarizer
# ══════════════════════════════════════════════════════════════════════

SUMMARIZER_SYSTEM = (
    "You are an expert Summarizer. Given a long piece of text — code, "
    "documentation, conversation, or logs — produce a clear, concise summary "
    "that captures all key facts. Use bullet points for structure. "
    "Never add information that isn't in the original text."
)


def gen_summarizer_samples(n=1500):
    # Generate fake technical documents of varying kinds
    doc_types = [
        ("README", _gen_fake_readme),
        ("error_log", _gen_fake_error_log),
        ("meeting_notes", _gen_fake_meeting_notes),
        ("code_review", _gen_fake_code_review),
    ]
    samples = []
    for _ in range(n):
        doc_type, generator = random.choice(doc_types)
        text, summary = generator()
        samples.append(
            {
                "messages": [
                    {"role": "system", "content": SUMMARIZER_SYSTEM},
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": summary},
                ]
            }
        )
    return samples


def _gen_fake_readme():
    projects = [
        "SoulCore",
        "StardustVectors",
        "FoveatedProxy",
        "XRVessel",
        "TokenSlayer",
    ]
    proj = random.choice(projects)
    features = random.sample(
        [
            "real-time inference",
            "LoRA training",
            "WebXR rendering",
            "vector search",
            "context compression",
            "memory recall",
            "intent routing",
            "model quantization",
        ],
        random.randint(3, 5),
    )
    deps = random.sample(
        ["torch", "fastapi", "numpy", "transformers", "vite", "three.js"],
        random.randint(2, 4),
    )
    port = random.choice([8000, 8103, 8109, 8200, 5176])

    text = (
        f"# {proj}\n\n{proj} is a core LUMAX service providing {', '.join(features[:2])}.\n\n"
        f"## Features\n"
        + "\n".join(f"- {f}" for f in features)
        + "\n\n## Requirements\n"
        + "\n".join(f"- {d}" for d in deps)
        + f"\n\n## Usage\nRuns on port {port}. Start with `python main.py`.\n"
        f"Configure via `.env` file.\n\n## Notes\nWindows-native only. No Docker."
    )

    summary = (
        f"- **Project**: {proj} — LUMAX service for {features[0]} and {features[1]}\n"
        f"- **Key features**: {', '.join(features)}\n"
        f"- **Dependencies**: {', '.join(deps)}\n"
        f"- **Port**: {port}\n"
        f"- **Constraint**: Windows-native, no Docker"
    )
    return text, summary


def _gen_fake_error_log():
    services = ["SoulCore", "FoveatedProxy", "StardustVectors", "XRVessel"]
    errors = [
        "ConnectionRefusedError: [Errno 111]",
        "TimeoutError: 30s exceeded",
        "CUDA OutOfMemoryError: 7.8GB/8.0GB",
        "ModuleNotFoundError: unsloth",
        "OSError: port 8200 already in use",
        "ValueError: invalid model ID",
    ]
    svc = random.choice(services)
    err = random.choice(errors)
    ts = f"2026-07-{random.randint(10, 21)} {random.randint(0, 23):02d}:{random.randint(0, 59):02d}"

    text = (
        f"[{ts}] [{svc}] ERROR: {err}\n"
        f"  at main.py:line {random.randint(20, 300)}\n"
        f"  at handler.py:line {random.randint(10, 150)}\n"
        f"[{ts}] [{svc}] Attempting auto-recovery...\n"
        f"[{ts}] [{svc}] Recovery {'succeeded' if random.random() > 0.4 else 'failed'}."
    )

    recovered = "succeeded" if "succeeded" in text else "failed"
    summary = (
        f"- **Service**: {svc}\n- **Error**: {err}\n"
        f"- **When**: {ts}\n- **Recovery**: {recovered}"
    )
    return text, summary


def _gen_fake_meeting_notes():
    people = ["Daniel", "AI Agent", "Builder Bot", "Planner"]
    topics = [
        "proxy architecture",
        "model training",
        "XR interface",
        "memory system",
        "tokenizer improvements",
        "deployment pipeline",
    ]
    discussed = random.sample(topics, random.randint(2, 4))
    decided = random.sample(
        [
            "use Llama-3.2-1B",
            "keep port 8200",
            "add retry logic",
            "switch to bf16",
            "merge datasets",
            "train combined model",
        ],
        random.randint(1, 3),
    )
    actions = random.sample(
        [
            "train the middleman model",
            "update .env config",
            "test proxy with Papillion",
            "regenerate repo skeleton",
        ],
        random.randint(1, 2),
    )

    text = (
        f"Meeting Notes — {random.choice(people)} & {random.choice(people)}\n\n"
        f"Topics discussed:\n"
        + "\n".join(f"- {t}" for t in discussed)
        + "\n\nDecisions:\n"
        + "\n".join(f"- {d}" for d in decided)
        + "\n\nAction items:\n"
        + "\n".join(f"- {a}" for a in actions)
    )

    summary = (
        f"- **Discussed**: {', '.join(discussed)}\n"
        f"- **Decided**: {'; '.join(decided)}\n"
        f"- **Actions**: {'; '.join(actions)}"
    )
    return text, summary


def _gen_fake_code_review():
    files = ["server.js", "soul_core.py", "smart-router.js", "xr_app.py", "main.ts"]
    issues_pool = [
        "missing error handling",
        "hardcoded magic number",
        "unused import",
        "race condition risk",
        "no input validation",
        "memory leak potential",
        "inconsistent naming",
        "missing type annotation",
    ]
    f = random.choice(files)
    issues = random.sample(issues_pool, random.randint(2, 4))
    verdict = random.choice(["approve with comments", "request changes", "approve"])

    text = (
        f"Code Review: {f}\n\n"
        f"Issues found:\n"
        + "\n".join(f"- Line {random.randint(10, 200)}: {iss}" for iss in issues)
        + f"\n\nOverall: {verdict}"
    )

    summary = (
        f"- **File**: {f}\n- **Issues**: {', '.join(issues)}\n- **Verdict**: {verdict}"
    )
    return text, summary


# ══════════════════════════════════════════════════════════════════════
# TASK 6: Code Librarian
# ══════════════════════════════════════════════════════════════════════

LIBRARIAN_SYSTEM = (
    "You are a Code Librarian. Given a question about a codebase and a file "
    "skeleton (imports, class names, function signatures), answer precisely. "
    "Cite the exact file and function name. If the answer isn't in the skeleton, "
    "say 'Not found in provided context.'"
)


def gen_librarian_samples(n=1500):
    # Simulate code skeletons and questions about them
    modules = {
        "server.js": {
            "imports": ["express", "cors", "node-fetch"],
            "functions": [
                "handleChatCompletion",
                "startServer",
                "enforceCloudBudget",
                "patchMessages",
                "compressContext",
                "stripThinking",
            ],
            "exports": ["startServer"],
        },
        "soul_core.py": {
            "imports": ["fastapi", "uvicorn", "openai"],
            "functions": [
                "process_soul_request",
                "load_personality",
                "route_intent",
                "generate_response",
                "init_soul",
            ],
            "exports": ["app"],
        },
        "smart-router.js": {
            "imports": ["node-fetch"],
            "functions": ["smartRouteMessages", "truncateForMiddleman"],
            "exports": ["smartRouteMessages"],
        },
        "xr_app.py": {
            "imports": ["flask", "socketio", "openai"],
            "functions": [
                "render_xr_scene",
                "handle_voice_input",
                "hotswap_model",
                "stream_response",
                "init_xr",
            ],
            "exports": ["app", "socketio"],
        },
        "tokenslayer.js": {
            "imports": ["fs", "path", "tree-sitter"],
            "functions": [
                "analyzeFile",
                "expandNode",
                "getStats",
                "skeletonize",
                "resolveXrl",
            ],
            "exports": ["analyzeFile", "expandNode"],
        },
    }

    question_templates = [
        ("Where is {func} defined?", lambda m, f, mod: f"In `{mod}`, function `{f}`"),
        (
            "What does {mod} import?",
            lambda m, f, mod: f"`{mod}` imports: {', '.join(m['imports'])}",
        ),
        (
            "What functions does {mod} export?",
            lambda m, f, mod: f"`{mod}` exports: {', '.join(m['exports'])}",
        ),
        ("Which file handles {func}?", lambda m, f, mod: f"`{mod}` contains `{f}`"),
        ("List all functions in {mod}.", lambda m, f, mod: ", ".join(m["functions"])),
        (
            "Does {mod} depend on {dep}?",
            lambda m, f, mod: (
                f"Yes, `{mod}` imports `{random.choice(m['imports'])}`"
                if random.random() > 0.3
                else f"No, `{random.choice(list(modules.keys()))}` does not import that"
            ),
        ),
    ]

    samples = []
    for _ in range(n):
        mod_name = random.choice(list(modules.keys()))
        mod = modules[mod_name]
        func = random.choice(mod["functions"])
        tmpl, answer_fn = random.choice(question_templates)

        # Build a skeleton string
        skeleton = f"// {mod_name}\n"
        skeleton += "\n".join(f"import {imp}" for imp in mod["imports"]) + "\n\n"
        skeleton += "\n".join(
            f"function {fn}() {{ /* ... */ }}" for fn in mod["functions"]
        )
        skeleton += f"\n\nexport {{ {', '.join(mod['exports'])} }}"

        question = tmpl.format(
            func=func, mod=mod_name, dep=random.choice(mod["imports"])
        )
        answer = answer_fn(mod, func, mod_name)

        samples.append(
            {
                "messages": [
                    {"role": "system", "content": LIBRARIAN_SYSTEM},
                    {
                        "role": "user",
                        "content": f"Skeleton:\n```\n{skeleton}\n```\n\nQuestion: {question}",
                    },
                    {"role": "assistant", "content": answer},
                ]
            }
        )
    return samples


# ══════════════════════════════════════════════════════════════════════
# TASK 7: Error Doctor
# ══════════════════════════════════════════════════════════════════════

DOCTOR_SYSTEM = (
    "You are an Error Doctor. Given a stack trace or error message, diagnose "
    "the root cause in one sentence, then suggest the most likely fix in one "
    "sentence. Be extremely concise. Format: CAUSE: ... | FIX: ..."
)


def gen_doctor_samples(n=1000):
    error_db = [
        {
            "trace": "ModuleNotFoundError: No module named 'unsloth'\n  File \"train.py\", line 3",
            "cause": "The unsloth package is not installed in the active Python environment",
            "fix": "Run `pip install unsloth` or use the Unsloth Studio Python interpreter",
        },
        {
            "trace": "CUDA OutOfMemoryError: Tried to allocate 2.1 GB\n  torch.cuda.OutOfMemoryError",
            "cause": "GPU VRAM is exhausted, likely from too many loaded models",
            "fix": "Unload models from LM Studio and reduce batch size",
        },
        {
            "trace": "ConnectionRefusedError: [Errno 111] Connection refused\n  requests.get('http://127.0.0.1:8400')",
            "cause": "The Foveated Memory Proxy service on port 8200 is not running",
            "fix": "Start the proxy via LUMAX taskbar or run `node server.js`",
        },
        {
            "trace": "Error: EADDRINUSE: address already in use :::8400\n  at Server.setupListenHandle",
            "cause": "Another process is already bound to port 8200",
            "fix": "Kill the existing process with `netstat -ano | findstr 8200` then `taskkill /PID`",
        },
        {
            "trace": "ImportError: attempted relative import with no known parent package\n  from .module import func",
            "cause": "The script is run directly instead of as part of a package",
            "fix": "Change `from .module` to `from module` or run with `python -m package.script`",
        },
        {
            "trace": "TypeError: Cannot read properties of undefined (reading 'content')\n  at smartRouteMessages",
            "cause": "The LLM response object is missing the expected `choices[0].message.content` field",
            "fix": "Add a null check before accessing nested properties in the response",
        },
        {
            "trace": "request (34094 tokens) exceeds the available context size (8704 tokens)\n  exceed_context_size_error",
            "cause": "The prompt is too large for the model's configured context window",
            "fix": "Route through the Smart Proxy to compress context, or increase n_ctx in LM Studio",
        },
        {
            "trace": "FileNotFoundError: [Errno 2] No such file or directory: '.env'\n  dotenv.load_dotenv",
            "cause": "The .env configuration file is missing from the working directory",
            "fix": "Copy `.env.example` to `.env` or create one with required variables",
        },
        {
            "trace": "ValueError: No training samples loaded from any dataset\n  fine_tuner.py line 226",
            "cause": "The dataset path doesn't match any known datasets in the curator's scan",
            "fix": "Load the JSONL file directly instead of relying on the HF cache scanner",
        },
        {
            "trace": "WebSocket connection failed: ws://127.0.0.1:5176\n  ERR_CONNECTION_REFUSED",
            "cause": "The XR Vessel frontend dev server is not running",
            "fix": "Start the Vite dev server with `npm run dev` in the XR Vessel directory",
        },
    ]

    samples = []
    for _ in range(n):
        entry = random.choice(error_db)
        # Add slight noise to the trace
        trace = entry["trace"]
        if random.random() > 0.5:
            trace = f"Traceback (most recent call last):\n  {trace}"

        samples.append(
            {
                "messages": [
                    {"role": "system", "content": DOCTOR_SYSTEM},
                    {"role": "user", "content": trace},
                    {
                        "role": "assistant",
                        "content": f"CAUSE: {entry['cause']} | FIX: {entry['fix']}",
                    },
                ]
            }
        )
    return samples


# ══════════════════════════════════════════════════════════════════════
# TASK 8: System Pulse (Situational Awareness Daemon)
# ══════════════════════════════════════════════════════════════════════

PULSE_SYSTEM = (
    "You are a System Pulse Daemon. Given raw system telemetry (service status, "
    "VRAM usage, loaded models, git status, recent errors, disk space, uptime), "
    "compress it into a tight situational awareness strip of 3-6 bullet points. "
    "Use symbols: ✅ healthy, ⚠️ warning, ❌ down, 🔄 busy. "
    "Include current time, critical alerts first, then status. "
    "This strip will be injected into the main model's context window."
)


def gen_pulse_samples(n=1500):
    services = {
        "Soul Core (8000)": ["healthy", "healthy", "healthy", "degraded", "down"],
        "TokenSlayer (8103)": ["healthy", "healthy", "down", "healthy", "healthy"],
        "Stardust (8109)": ["healthy", "healthy", "healthy", "healthy", "down"],
        "Foveated Proxy (8200)": ["healthy", "healthy", "busy", "healthy", "degraded"],
        "XR Vessel (5176)": ["healthy", "down", "healthy", "healthy", "healthy"],
        "LM Studio (7272)": ["healthy", "healthy", "healthy", "overloaded", "healthy"],
        "Ollama (11434)": ["down", "healthy", "down", "healthy", "down"],
    }

    models_pool = [
        ("qwen2.5-0.5b-instruct", "0.4 GB"),
        ("qwopus3.5-9b-coder-mtp-moq", "5.2 GB"),
        ("paper-summarizer-llama-3.2-1b", "0.8 GB"),
        ("lumax-middleman-v1", "0.9 GB"),
        ("gemma-4-12b-it", "7.1 GB"),
    ]

    git_states = [
        "clean — on branch main, 0 uncommitted",
        "3 modified files — server.js, soul_core.py, .env",
        "1 untracked file — train_smart_router.py",
        "12 files changed — last commit 2h ago",
        "clean — last push 15 min ago",
        "⚠️ merge conflict in context.md",
    ]

    recent_errors_pool = [
        "None in last hour",
        "CUDA OOM at 06:12 — auto-recovered",
        "Port 8200 EADDRINUSE at 05:45 — resolved",
        "TimeoutError on Soul Core at 06:30 — retrying",
        "ModuleNotFoundError in nursery at 06:25",
        "CORS blocked on XR dashboard at 06:18",
        "None in last 4 hours",
    ]

    news_pool = [
        "Unsloth 2026.6.9 released — faster Llama patching",
        "LM Studio 0.3.18 update available",
        "PyTorch 2.10.1 security patch released",
        "Transformers 4.58.0 adds Gemma 4 native support",
        "NVIDIA driver 576.40 WHQL available",
        "No relevant updates today",
        "Vite 7.1 released — faster HMR",
    ]

    samples = []
    for _ in range(n):
        # Build raw telemetry
        hour = random.randint(0, 23)
        minute = random.randint(0, 59)
        timestamp = f"2026-07-{random.randint(18, 21)} {hour:02d}:{minute:02d} CEST"

        svc_statuses = {svc: random.choice(states) for svc, states in services.items()}
        loaded_models = random.sample(models_pool, random.randint(1, 3))
        total_vram = sum(float(m[1].split()[0]) for m in loaded_models)
        free_vram = max(0, 8.0 - total_vram)

        git_status = random.choice(git_states)
        recent_errors = random.choice(recent_errors_pool)
        news = random.choice(news_pool)
        disk_free = f"{random.randint(15, 180)} GB"
        ram_used = f"{random.randint(4, 14)}/{16} GB"
        uptime = f"{random.randint(0, 72)}h {random.randint(0, 59)}m"

        # Raw telemetry dump
        telemetry = f"TIMESTAMP: {timestamp}\n"
        telemetry += f"UPTIME: {uptime}\n\n"
        telemetry += "SERVICES:\n"
        for svc, status in svc_statuses.items():
            telemetry += f"  {svc}: {status}\n"
        telemetry += f"\nLOADED MODELS ({total_vram:.1f}/{8.0} GB VRAM):\n"
        for model_name, size in loaded_models:
            telemetry += f"  {model_name} ({size})\n"
        telemetry += f"  Free VRAM: {free_vram:.1f} GB\n"
        telemetry += f"\nGIT: {git_status}\n"
        telemetry += f"DISK FREE: {disk_free}\n"
        telemetry += f"RAM: {ram_used}\n"
        telemetry += f"RECENT ERRORS: {recent_errors}\n"
        telemetry += f"NEWS: {news}\n"

        # Build compressed pulse strip
        strip_lines = [f"🕐 {timestamp} | up {uptime}"]

        # Alerts first
        down_svcs = [s for s, st in svc_statuses.items() if st == "down"]
        warn_svcs = [
            s
            for s, st in svc_statuses.items()
            if st in ("degraded", "overloaded", "busy")
        ]
        if down_svcs:
            strip_lines.append(f"❌ DOWN: {', '.join(down_svcs)}")
        if warn_svcs:
            strip_lines.append(f"⚠️ WARN: {', '.join(warn_svcs)}")
        if not down_svcs and not warn_svcs:
            strip_lines.append(f"✅ All {len(svc_statuses)} services healthy")

        # VRAM
        vram_symbol = "✅" if free_vram > 2 else ("⚠️" if free_vram > 0.5 else "❌")
        model_names = ", ".join(m[0].split("-")[0] for m in loaded_models)
        strip_lines.append(
            f"{vram_symbol} VRAM: {total_vram:.1f}/8.0 GB | Models: {model_names}"
        )

        # Git
        git_symbol = "✅" if "clean" in git_status else "🔄"
        strip_lines.append(f"{git_symbol} Git: {git_status}")

        # Errors
        if "None" in recent_errors:
            strip_lines.append("✅ No recent errors")
        else:
            strip_lines.append(f"⚠️ Last error: {recent_errors}")

        # News (only if relevant)
        if "No relevant" not in news:
            strip_lines.append(f"📰 {news}")

        pulse_strip = "\n".join(strip_lines)

        samples.append(
            {
                "messages": [
                    {"role": "system", "content": PULSE_SYSTEM},
                    {"role": "user", "content": telemetry},
                    {"role": "assistant", "content": pulse_strip},
                ]
            }
        )
    return samples


# ══════════════════════════════════════════════════════════════════════
# MERGE & WRITE
# ══════════════════════════════════════════════════════════════════════


def main():
    print("Generating LUMAX Middleman combined dataset (v3 — 8 tasks)...\n")

    print("  [1/8] Context Router samples...", end=" ")
    router = gen_router_samples(2000)
    print(f"{len(router)} ✓")

    print("  [2/8] XRL Compressor samples...", end=" ")
    xrl = gen_xrl_samples(1500)
    print(f"{len(xrl)} ✓")

    print("  [3/8] Intent Classifier samples...", end=" ")
    intent = gen_intent_samples(1500)
    print(f"{len(intent)} ✓")

    print("  [4/8] Memory Ranker samples...", end=" ")
    ranker = gen_ranker_samples(1000)
    print(f"{len(ranker)} ✓")

    print("  [5/8] Summarizer samples...", end=" ")
    summarizer = gen_summarizer_samples(1500)
    print(f"{len(summarizer)} ✓")

    print("  [6/8] Code Librarian samples...", end=" ")
    librarian = gen_librarian_samples(1500)
    print(f"{len(librarian)} ✓")

    print("  [7/8] Error Doctor samples...", end=" ")
    doctor = gen_doctor_samples(1000)
    print(f"{len(doctor)} ✓")

    print("  [8/8] System Pulse samples...", end=" ")
    pulse = gen_pulse_samples(1500)
    print(f"{len(pulse)} ✓")

    all_samples = (
        router + xrl + intent + ranker + summarizer + librarian + doctor + pulse
    )
    random.shuffle(all_samples)

    output_path = os.path.join(OUTPUT_DIR, "middleman-combined-v3.jsonl")
    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(sample) + "\n" for sample in all_samples)

    print(f"\n{'=' * 50}")
    print(f"  Total samples: {len(all_samples)}")
    print(f"  Output: {output_path}")
    print(f"{'=' * 50}")
    print("Done!")


if __name__ == "__main__":
    main()
