# Foveated Memory — Universal Plugin Architecture Plan
## `foveated-memory-proxy` v2.0 — Updated Design

---

## Design Decisions (Confirmed)

| Question | Decision |
|---|---|
| **Scope** | Per-workspace / per-project memory stores. Personal conversations = exclusive to participants. Work conversations = shared domain, with optional LLM anonymization pass |
| **Persistence** | Always permanent — disk-persisted across sessions. This is the core purpose. |
| **Target** | Universal standalone Node.js package — installable anywhere, on Windows natively, no browser required |
| **Identity** | Persona-agnostic + configurable. Context determines scope: personal = exclusive, work = anonymizable shared domain |

---

## The True Foveated Memory — Gradient Ring Architecture

This is the core architectural leap. Rather than just a retrieval tag, the system loads a **static foveated ring structure** into every context window at session start. Like the actual retina — maximum resolution at the centre, graceful degradation outward.

```
╔══════════════════════════════════════════════════════════════════════╗
║  CONTEXT WINDOW (4096 tokens total)                                  ║
║                                                                      ║
║  ┌────────────────────────────────────────────────────────────────┐  ║
║  │ SYSTEM PROMPT + IDENTITY BLOCK              ~200 tokens        │  ║
║  └────────────────────────────────────────────────────────────────┘  ║
║                                                                      ║
║  ┌──────── FOVEATED MEMORY RING BLOCK ──────────────────────────┐   ║
║  │                                                               │   ║
║  │  ● RING 0 — FOVEA (6 raw messages)            ~180 tokens    │   ║
║  │    Compression: 0%  │  Recency: now  │  Full resolution       │   ║
║  │                                                               │   ║
║  │  ○ RING 1 — PARAFOVEA (recent themes)          ~80 tokens    │   ║
║  │    Compression: ~50%  │  Recency: this session               │   ║
║  │                                                               │   ║
║  │  ○ RING 2 — NEAR PERIPHERY (this week)         ~60 tokens    │   ║
║  │    Compression: ~75%  │  Topic + key phrases                 │   ║
║  │                                                               │   ║
║  │  ○ RING 3 — MID PERIPHERY (this month)         ~40 tokens    │   ║
║  │    Compression: ~88%  │  Topic + timestamp only              │   ║
║  │                                                               │   ║
║  │  ○ RING 4 — FAR PERIPHERY (deep past)          ~25 tokens    │   ║
║  │    Compression: ~95%  │  XRL hash anchors                    │   ║
║  │                                                               │   ║
║  │  ○ RING 5 — OUTER PERIPHERY (oldest)           ~15 tokens    │   ║
║  │    Compression: ~98%  │  Pure XRL atomic hashes only         │   ║
║  │                                                               │   ║
║  │  Total ring block:                            ~400 tokens     │   ║
║  └───────────────────────────────────────────────────────────────┘   ║
║                                                                      ║
║  ┌────────────────────────────────────────────────────────────────┐  ║
║  │ LIVE CONVERSATION TURNS                     ~3296 tokens      │  ║
║  │ (the model talks here — full resolution)                       │  ║
║  └────────────────────────────────────────────────────────────────┘  ║
╚══════════════════════════════════════════════════════════════════════╝
```

### What Each Ring Contains

**Ring 0 — Fovea (raw, uncompressed)**
- The last 6 messages verbatim
- Full speaker attribution, timestamps, full content
- This is the model's "right now" — maximum clarity

**Ring 1 — Parafovea (XRL light compression, ~50%)**
- Key themes from the current session that have scrolled out of Ring 0
- E.g.: `(topic: fixed VAD engine, mood: collaborative, outcome: solved)`
- Still enough detail to understand what happened

**Ring 2 — Near Periphery (XRL medium, ~75%)**
- This week's active threads, compressed to essence
- E.g.: `[2026-07-11] XRL Protocol Phase 14 impl. Integrated MCP bridge. SOLVED.`
- Enough to re-anchor context on a topic without full transcript

**Ring 3 — Mid Periphery (XRL deep, ~88%)**
- Monthly anchors — significant events, decisions, milestones
- E.g.: `[2026-07] Foveated Memory System designed & implemented`
- Topic + outcome only, no detail

**Ring 4 — Far Periphery (XRL ultra, ~95%)**
- Older significant memories as XRL hash references
- E.g.: `xrl://lumax/2026-05/diamond-concordia-purge#a3f2`
- Recall-able via `<recall:>` but not inline readable

**Ring 5 — Outer Periphery (XRL atomic, ~98%)**
- Deepest past as pure hash seeds
- E.g.: `#d8f1 #a3f2 #77bc #1e4a`
- The model knows these exist; their content is invisible until recalled

---

## The Recall Mechanism — "Moving the Eye"

When the model needs something from the peripheral rings, it emits a recall token. The system then performs a **foveal saccade**: the peripheral memory is pulled into full resolution, and the ring structure reorganises around the new focal point.

### Token-Neutral Injection

The key insight: injecting a recalled memory is **token-neutral or net-negative**:

```
BEFORE recall:
  Ring 2: "[2026-07-11] XRL Protocol Phase 14 impl..."   →  12 tokens
  Ring 3: "[2026-07-11] Musical emotion system..."       →   8 tokens
  TOTAL held: 20 tokens

AFTER recall of "musical emotion system":
  Ring 2 entry REMOVED                                   →   0 tokens
  Ring 3 entry REMOVED                                   →   0 tokens
  INJECTED as sharp foveal island:
  "[MEMORY RECALLED: musical emotional system]
   The Systemic Resonance system maps Gnist health to
   musical chords — harmony = major chord (happy),
   dissonance = tritone (alert). Wired into AmbientSoundEngine."
                                                         →  30 tokens

  NET COST: +10 tokens but you freed 20 → true net: -10 tokens
```

The recalled memory becomes a **standing foveal island** — injected between recent messages, fully readable, "impregnating" the nearby sharp context with its clarity.

### The Saccade Flow

```
Model emits:
  (thought: I need to check the musical registry. <recall: "musical emotional system">)
  (emotion: curious)
  [Retrieving memory...]
  ↓
Interceptor fires:
  1. Extract query: "musical emotional system"
  2. Search vector store + ring index
  3. Find: Ring 3 entry + underlying full text
  4. Remove Ring 2 + Ring 3 entries from ring block (free tokens)
  5. Inject full text as [MEMORY RECALLED] system message
  6. Rebuild ring block (recalculate rings without removed entries)
  7. Trigger continuation: "[SYSTEM: Memory uncompressed. Continue answering.]"
  ↓
Model continues with full clarity on the recalled topic
```

---

## Ring Builder — How Rings Are Generated

At the start of each session, the proxy dynamically **builds the ring block** from the memory store:

```javascript
async function buildFoveatedRingBlock(workspaceId, currentSessionId, config) {
    const rings = [];

    // Ring 0 — Fovea: last 6 messages (raw)
    const recent = await memory.getRecentMessages(workspaceId, 6);
    rings.push({ id: 0, label: 'FOVEA', items: recent, compression: 0 });

    // Ring 1 — Parafovea: themes from current session (50% XRL)
    const sessionThemes = await memory.getSessionThemes(workspaceId, currentSessionId);
    const compressed1 = await xrl.compress(sessionThemes, { level: 1, budget: 80 });
    rings.push({ id: 1, label: 'PARAFOVEA', items: compressed1, compression: 0.5 });

    // Ring 2 — Near Periphery: this week (75% XRL)
    const weekTopics = await memory.getTopicsByAge(workspaceId, { days: 7 });
    const compressed2 = await xrl.compress(weekTopics, { level: 2, budget: 60 });
    rings.push({ id: 2, label: 'NEAR_PERIPHERY', items: compressed2, compression: 0.75 });

    // Ring 3 — Mid Periphery: this month (88% XRL)
    const monthTopics = await memory.getTopicsByAge(workspaceId, { days: 30 });
    const compressed3 = await xrl.compress(monthTopics, { level: 3, budget: 40 });
    rings.push({ id: 3, label: 'MID_PERIPHERY', items: compressed3, compression: 0.88 });

    // Ring 4 — Far Periphery: older (95% XRL hash refs)
    const oldTopics = await memory.getTopicsByAge(workspaceId, { days: 365 });
    const compressed4 = await xrl.compress(oldTopics, { level: 4, budget: 25 });
    rings.push({ id: 4, label: 'FAR_PERIPHERY', items: compressed4, compression: 0.95 });

    // Ring 5 — Outer: deep past (98% atomic hashes)
    const deepTopics = await memory.getAllTopicAnchors(workspaceId);
    const compressed5 = await xrl.compress(deepTopics, { level: 5, budget: 15 });
    rings.push({ id: 5, label: 'OUTER_PERIPHERY', items: compressed5, compression: 0.98 });

    return formatRingBlock(rings); // ~400 tokens total
}
```

---

## Memory Scoping — Personal vs. Professional

```
workspaces/
├── personal/
│   └── daniel-jen/          ← Exclusive. Only these two. Never shared.
│       ├── memory.db
│       ├── rings-cache.json
│       └── vectors/
├── work/
│   └── lumax-project/       ← Shared domain. All contributors see this.
│       ├── memory.db        ← Anonymized on write (personal refs stripped)
│       ├── rings-cache.json
│       └── vectors/
└── anonymous/               ← LLM-processed, all personal context removed
    └── lumax-project-anon/  ← Pure technical context, XRL-compressed
```

### Anonymization Flow (Work Mode)

When a message is stored in a **work workspace**, an optional LLM pass strips personal content:

```
INPUT:  "Daniel mentioned his sister is visiting, so we'll delay the XRL 
         Phase 15 work until next week. The tokenslayer compression is at 95%."

ANONYMIZED OUTPUT: "Team availability constraint. XRL Phase 15 delayed ~1 week.
                    TokenSlayer compression: 95%."
```

Only the **technical signal** survives. The personal context is discarded before indexing. This suits the XRL language perfectly — it compresses to structured semantic signal, stripping narrative noise automatically.

---

## Package Architecture — Universal Node.js Standalone

```
foveated-memory-proxy/
├── package.json                   ← npm package, bin: "foveated-memory"
├── server.js                      ← OpenAI-compatible proxy (entry point)
├── core/
│   ├── ring-builder.js            ← Builds foveated ring block per session
│   ├── recall-interceptor.js      ← <recall:> token stream detection
│   ├── saccade-engine.js          ← Foveal "eye movement" — swap rings
│   ├── xrl-compressor.js          ← XRL compression at levels 1–5
│   └── system-prompt-patch.js     ← Injects rings + ACTIVE RECALL into prompts
├── memory/
│   ├── store.js                   ← SQLite + hnswlib (no external deps)
│   ├── workspace-manager.js       ← Per-workspace scoping (personal/work)
│   └── anonymizer.js              ← LLM-powered anonymization for work mode
├── config/
│   ├── default.json               ← Sensible defaults
│   └── schema.json                ← Validation schema
├── bin/
│   └── foveated-memory.js         ← CLI entrypoint
└── README.md
```

### Zero External Infrastructure

The package uses:
- **SQLite** (bundled via `better-sqlite3`) — message history, ring cache
- **hnswlib-node** — embedded vector search, no external server needed
- **Built-in XRL compressor** — based on the existing TokenSlayer levels 1–5

No Docker. No ChromaDB server. No Stardust required (though it can optionally route to Stardust if available). Works completely standalone on Windows.

### Installation & Use

```bash
# Install globally (Windows)
npm install -g foveated-memory-proxy

# Start (points at LM Studio)
foveated-memory --upstream http://localhost:1234 --port 8400

# Start with workspace config
foveated-memory --config ./my-workspace.json

# OR: install as LUMAX Tool
cp -r foveated-memory-proxy/ C:/Users/danie/program/LUMAX/Tools/
```

### my-workspace.json

```json
{
  "proxy_port": 8400,
  "upstream_url": "http://127.0.0.1:1234",
  "workspace_id": "daniel-jen",
  "workspace_mode": "personal",
  "identity_name": "Jen",
  "user_name": "Daniel",
  "ring_token_budget": 400,
  "fovea_message_count": 6,
  "persist_path": "C:/Users/danie/program/LUMAX/user_data/foveated_memory",
  "anonymize_on_write": false,
  "xrl_compression_levels": [0, 1, 2, 3, 4, 5],
  "recall_max_results": 5,
  "recall_token_budget_per_injection": 80
}
```

---

## How It Connects to LM Studio / Any Client

```
┌─────────────────────────────────────────────────────────────────┐
│  ANY CLIENT (LM Studio, Antigravity, VS Code, Open WebUI...)   │
│                                                                 │
│  Change one setting: API endpoint = http://localhost:8400       │
└────────────────────────────┬────────────────────────────────────┘
                             │ OpenAI-compatible POST /v1/chat/completions
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  FOVEATED MEMORY PROXY  :8400                                   │
│                                                                 │
│  On request:                                                    │
│  1. Build foveated ring block (6 rings, ~400 tokens)            │
│  2. Inject rings + ACTIVE RECALL into system prompt             │
│  3. Forward to upstream LLM                                     │
│                                                                 │
│  On response stream:                                            │
│  4. Watch for <recall: "..."> token                             │
│  5. If found → saccade engine fires:                            │
│     a. Extract query                                            │
│     b. Vector search memory store                               │
│     c. Remove 2 peripheral ring entries                         │
│     d. Inject [MEMORY RECALLED] block                           │
│     e. Trigger continuation                                     │
│  6. Store turn to memory (update rings cache)                   │
│  7. Return final response to client                             │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  ANY LLM BACKEND                                                │
│  LM Studio :1234  │  Ollama :11434  │  Antigravity  │  OpenAI  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phased Build Plan

### Phase 1 — Core Proxy + Recall (MVP)
- [ ] `server.js` — OpenAI-compatible proxy
- [ ] `recall-interceptor.js` — stream-time `<recall:>` detection
- [ ] `memory/store.js` — SQLite + hnswlib embedded
- [ ] `system-prompt-patch.js` — ACTIVE RECALL instruction injection
- [ ] `bin/foveated-memory.js` — CLI with `--upstream` and `--port`
- [ ] Basic recall → injection → continuation loop working

### Phase 2 — Foveated Ring Builder
- [ ] `ring-builder.js` — 6-ring system with XRL compression at each level
- [ ] `xrl-compressor.js` — levels 0 (raw) through 5 (atomic hashes)
- [ ] Ring block injected into every context at session start
- [ ] Token budget enforcement (hard cap at configurable limit)

### Phase 3 — Saccade Engine (Full Eye Movement)
- [ ] `saccade-engine.js` — swap recalled peripheral items into foveal islands
- [ ] Ring restructuring after each recall (remove freed entries, rebalance)
- [ ] Token-neutral injection verified (freed ≥ injected)

### Phase 4 — Workspace Scoping + Anonymizer
- [ ] `workspace-manager.js` — personal/work scoping
- [ ] `anonymizer.js` — LLM-powered technical-only filter for work mode
- [ ] Per-workspace isolation enforced at storage layer

### Phase 5 — Polish & Packaging
- [ ] `npm publish foveated-memory-proxy`
- [ ] Windows installer (optional: wrap in `.exe` via `pkg`)
- [ ] Add to `C:/Users/danie/program/LUMAX/Tools/`
- [ ] README + config schema docs

---

## Verification

1. Start proxy, point LM Studio at `:8400`
2. Start fresh conversation — inspect system prompt → ring block should be present
3. Say: "Do you remember what we built two weeks ago?"
4. Model should emit `<recall:>` → proxy intercepts → correct memory injected
5. Model continues with clarity despite fresh context
6. Verify ring block recalculates with recalled item promoted to foveal island
7. Verify token count stays within budget before and after recall
