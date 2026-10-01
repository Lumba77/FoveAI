# XRL Phase 1: Binary Tokenizer — Implementation Plan

> **Status:** Draft for Review
> **Date:** 2026-07-09
> **Based on:** PoC results (60-95% token reduction confirmed), XRL Language Design, TokenSlayer Language Design, existing XRS tooling

---

## Executive Summary

The PoC proved that XRS skeletonization achieves **67% average token reduction** with **no meaningful information loss**. Phase 1 builds the **XRL Binary Tokenizer (XBT)** — a production-ready binary encoding layer that sits on top of the existing XRS skeletonizer, converting text-based skeletons into compact binary token streams for an additional **15-25% compression** beyond what XRS already achieves.

**Target:** 70-75% total token reduction (XRS text skeleton + XRL binary encoding)

---

## 1. Architecture Overview

### 1.1 Pipeline

```
Source Code (any language)
    │
    ▼
┌─────────────────────────────────────┐
│  XRS Skeletonizer (existing)        │  ← Text-based skeleton (60-65% reduction)
│  tokenslayer.js                     │
└─────────────────────────────────────┘
    │ Text skeleton output
    ▼
┌─────────────────────────────────────┐
│  XRL Binary Tokenizer (NEW)         │  ← Binary encoding (additional 15-25%)
│  xrl-tokenizer.cjs                  │
└─────────────────────────────────────┘
    │ Binary token stream (.xrb)
    ▼
┌─────────────────────────────────────┐
│  Depth-Aware Serializer             │  ← Filter by depth level
│  xrl-serializer.cjs                 │
└─────────────────────────────────────┘
    │ Filtered binary stream
    ▼
┌─────────────────────────────────────┐
│  Token Budget Enforcer              │  ← Trim to fit context window
│  xrl-budget.cjs                     │
└─────────────────────────────────────┘
    │ Final compact representation
    ▼
┌─────────────────────────────────────┐
│  MCP Tools                          │  ← LLM consumption
│  load_xrl / expand_xrl / search_xrl │
└─────────────────────────────────────┘
    │
    ▼
[LLM Context Window]
```

### 1.2 Component Map

| Component | File | Purpose | Depends On |
|-----------|------|---------|------------|
| XRL Tokenizer | `Forge/xrs/xrl-tokenizer.cjs` | Convert text skeleton → binary token stream | XRS skeletonizer |
| XRL Serializer | `Forge/xrs/xrl-serializer.cjs` | Depth-aware filtering + serialization | Tokenizer |
| XRL Budget | `Forge/xrs/xrl-budget.cjs` | Token budget calculation + enforcement | Serializer |
| XRL CLI | `Forge/xrs/xrl.cjs` | Unified CLI for all XRL operations | All above |
| XRL MCP Server | `Forge/xrs/xrl-mcp-server.js` | MCP tools for LLM consumption | All above |
| XRL Benchmark | `Forge/xrs/xrl-benchmark2.cjs` | Enhanced benchmark with binary comparison | All above |
| XRB Format Spec | `Forge/xrs/xrb-format.md` | Binary format specification | — |

---

## 2. Binary Tokenizer Design

### 2.1 Token Types (Extended from Design Doc)

The XRL Binary Tokenizer uses **17 structural token types** with 1-byte opcodes, plus variable-length data payloads:

| Opcode | Token | Size | Description | Depth Filter |
|--------|-------|------|-------------|--------------|
| `0x00` | `NULL` | 1 byte | Null/empty token | Always stripped |
| `0x01` | `KEEP` | 1 byte | @keep annotation marker | Always visible |
| `0x02` | `DETAIL` | 1 byte | @detail annotation marker | Depth ≤ 2 |
| `0x03` | `FLESH` | 1 byte | @flesh annotation marker | Depth ≤ 1 |
| `0x04` | `TEST` | 1 byte | @test annotation marker | Depth 0 only |
| `0x05` | `DOC` | 1 byte | @doc annotation marker | Always visible |
| `0x10` | `FN_SIG` | 1 byte | Function signature start | Always visible |
| `0x11` | `FN_BODY` | 1 byte | Function body start | Depth ≤ 1 |
| `0x12` | `FN_END` | 1 byte | Function end | Always visible |
| `0x20` | `TYPE_DEF` | 1 byte | Type/interface/class definition | Always visible |
| `0x21` | `TYPE_END` | 1 byte | Type definition end | Always visible |
| `0x30` | `IMPORT` | 1 byte | Import/require/include | Always visible |
| `0x31` | `EXPORT` | 1 byte | Export statement | Always visible |
| `0x40` | `BLOCK_OPEN` | 1 byte | Block opening `{` | Always visible |
| `0x41` | `BLOCK_CLOSE` | 1 byte | Block closing `}` | Always visible |
| `0x50` | `STRING` | 2+ bytes | String literal (opcode + length + data) | Varies by context |
| `0x51` | `IDENT` | 2+ bytes | Identifier (opcode + length + data) | Varies by context |
| `0x52` | `NUMBER` | 2+ bytes | Numeric literal (opcode + length + data) | Varies by context |
| `0x60` | `COMMENT` | 1 byte | Comment marker (content stripped) | Depth ≤ 1 |
| `0x70` | `WHITESPACE` | 1 byte | Whitespace marker (content stripped) | Depth ≥ 1 stripped |
| `0x80` | `DECORATOR` | 2+ bytes | Decorator/annotation (opcode + data) | Depth ≤ 2 |
| `0x90` | `MODIFIER` | 2+ bytes | Access modifier (public/private/async) | Always visible |
| `0xA0` | `ASSIGN` | 1 byte | Assignment/equals | Depth ≤ 2 |
| `0xB0` | `SEPARATOR` | 1 byte | Comma/semicolon/pipe | Always visible |
| `0xC0` | `FLESH_MARKER` | 2+ bytes | Collapsed flesh block placeholder | Depth ≥ 1 |
| `0xD0` | `EXPAND_HINT` | 2+ bytes | Hint about what's in a collapsed block | Always visible |

### 2.2 Encoding Scheme

#### Variable-Length String Encoding

```
[Opcode: 1 byte] [Length: 1-2 bytes] [Data: Length bytes]

Length encoding:
- If length < 128: single byte (0x00-0x7F)
- If length ≥ 128: two bytes (0x80 | (len >> 8), len & 0xFF)
```

#### Example: Function Signature Encoding

```xr
@keep
fn add(a: Int, b: Int) -> Int
```

Encoded as binary:
```
0x01                    // KEEP annotation
0x10                    // FN_SIG
0x51 0x03 0x61 0x64 0x64  // IDENT "add" (len=3, a=0x61, d=0x64, d=0x64)
0x51 0x01 0x61          // IDENT "a" (len=1)
0x51 0x03 0x49 0x6E 0x74  // IDENT "Int" (len=3)
0x51 0x01 0x62          // IDENT "b" (len=1)
0x51 0x03 0x49 0x6E 0x74  // IDENT "Int" (len=3)
0x51 0x03 0x49 0x6E 0x74  // IDENT "Int" (return type, len=3)
```

**Total: 20 bytes** vs ~40 bytes of source text → **50% reduction at binary level**

#### Example: Class with Flesh Block

```xr
@keep
class UserService {
    @keep
    fn get_user(id: UserId) -> User { /* ... */ }

    @flesh
    fn _hash_password(password: String) -> String { /* ... */ }
}
```

Encoded as binary (depth 2 skeleton):
```
0x01                    // KEEP
0x20                    // TYPE_DEF
0x51 0x0C 0x55 0x73 0x65 0x72 0x53 0x65 0x72 0x76 0x69 0x63 0x65  // IDENT "UserService"
0x40                    // BLOCK_OPEN
0x01                    // KEEP
0x10                    // FN_SIG
0x51 0x08 0x67 0x65 0x74 0x5F 0x75 0x73 0x65 0x72  // IDENT "get_user"
0x51 0x02 0x69 0x64    // IDENT "id"
0x51 0x06 0x55 0x73 0x65 0x72 0x49 0x64  // IDENT "UserId"
0x51 0x04 0x55 0x73 0x65 0x72  // IDENT "User" (return)
0x11                    // FN_BODY
0xC0 0x0A 0x2F 0x2A 0x20 0x2E 0x2E 0x2E 0x20 0x2A 0x2F  // FLESH_MARKER "/* ... */"
0x12                    // FN_END
0x03                    // FLESH
0x10                    // FN_SIG
0x51 0x0F 0x5F 0x68 0x61 0x73 0x68 0x5F 0x70 0x61 0x73 0x73 0x77 0x6F 0x72 0x64  // IDENT "_hash_password"
0x51 0x08 0x70 0x61 0x73 0x73 0x77 0x6F 0x72 0x64  // IDENT "password"
0x51 0x06 0x53 0x74 0x72 0x69 0x6E 0x67  // IDENT "String"
0x51 0x06 0x53 0x74 0x72 0x69 0x6E 0x67  // IDENT "String" (return)
0xC0 0x0A 0x2F 0x2A 0x20 0x2E 0x2E 0x2E 0x20 0x2A 0x2F  // FLESH_MARKER
0x41                    // BLOCK_CLOSE
```

**Total: ~70 bytes** vs ~180 bytes of source → **61% reduction at binary level**

### 2.3 XRB Binary Container Format (GGUF-Inspired)

```
┌─────────────────────────────────────────────┐
│              XRB FILE FORMAT                 │
├─────────────────────────────────────────────┤
│                                              │
│  [Header: 16 bytes]                         │
│  ├─ Magic: "XRB1" (4 bytes)                 │
│  ├─ Version: uint16 (1)                     │
│  ├─ Default Depth: uint8 (2)               │
│  ├─ Token Budget: uint32 (4096)             │
│  └─ Block Count: uint32                     │
│                                              │
│  [Block Table: variable]                    │
│  ├─ Block 1: {name_len, name, annotation,   │
│  │             offset, size, depth_mask}     │
│  ├─ Block 2: {name_len, name, annotation,   │
│  │             offset, size, depth_mask}     │
│  └─ ...                                      │
│                                              │
│  [Token Data: variable]                      │
│  ├─ Full token stream (all depths)          │
│  │  (Each token includes depth visibility   │
│  │   mask for fast filtering)               │
│                                              │
│  [Metadata: variable]                        │
│  ├─ Source language: string                 │
│  ├─ Original file path: string              │
│  ├─ Original file hash: SHA256 (32 bytes)   │
│  ├─ Original token count: uint32            │
│  ├─ Skeleton token count: uint32            │
│  ├─ Reduction percentage: float32           │
│  └─ Expansion hints: [string, ...]          │
│                                              │
└─────────────────────────────────────────────┘
```

### 2.4 Depth Visibility Mask

Each token in the stream carries a **4-bit depth visibility mask** indicating at which depths it should be visible:

| Bit | Depth | Meaning |
|-----|-------|---------|
| 0 | 0 | Visible in full file |
| 1 | 1 | Visible in light skeleton |
| 2 | 2 | Visible in medium skeleton |
| 3 | 3 | Visible in deep skeleton |

Example: `0x0F` = visible at all depths (KEEP), `0x03` = visible at depth 0-1 (FLESH)

This allows O(1) filtering — to serialize at depth N, iterate the token stream and emit tokens where `mask & (1 << N)` is non-zero.

---

## 3. Integration with Existing XRS Skeletonizer

### 3.1 Integration Architecture

The XRL Binary Tokenizer does **not** replace the XRS skeletonizer — it wraps it:

```
tokenslayer.js (existing)
    │ Produces text skeleton
    ▼
xrl-tokenizer.cjs (NEW)
    │ Parses text skeleton into structured AST
    │ Encodes AST into binary token stream
    │ Writes .xrb binary file
    ▼
xrl-serializer.cjs (NEW)
    │ Reads .xrb file
    │ Filters by depth mask
    │ Outputs compact representation
```

### 3.2 Text Skeleton → Binary Token Mapping

The tokenizer parses the text skeleton output from `tokenslayer.js` and maps each line to binary tokens:

| Text Skeleton Pattern | Binary Token(s) |
|----------------------|------------------|
| `@keep` | `0x01 KEEP` |
| `@detail` | `0x02 DETAIL` |
| `@flesh` | `0x03 FLESH` |
| `fn name(params) -> Ret` | `0x10 FN_SIG + 0x51 IDENT ...` |
| `class Name {` | `0x20 TYPE_DEF + 0x51 IDENT + 0x40 BLOCK_OPEN` |
| `import X from 'y'` | `0x30 IMPORT + 0x51 IDENT ...` |
| `export function name` | `0x31 EXPORT + 0x10 FN_SIG ...` |
| `{` | `0x40 BLOCK_OPEN` |
| `}` | `0x41 BLOCK_CLOSE` |
| `/* ... */ }` | `0xC0 FLESH_MARKER + 0x12 FN_END` |
| `// comment` | `0x60 COMMENT` |

### 3.3 Backward Compatibility

The existing XRS tooling continues to work unchanged:

```bash
# Existing workflow (unchanged)
node xrs.cjs service.py --depth 2

# New XRL workflow (adds binary encoding)
node xrl.cjs service.py --depth 2 --format binary
node xrl.cjs service.py --depth 2 --format text     # Same as xrs.cjs
node xrl.cjs service.py --depth 2 --format json      # JSON AST for tooling
```

### 3.4 File Extension Convention

| Extension | Format | Description |
|-----------|--------|-------------|
| `.xr` | Text | Human-readable XRL skeleton (same as current XRS output) |
| `.xrb` | Binary | XRL Binary format (compact, machine-optimized) |
| `.xrj` | JSON | XRL JSON AST (for tooling and debugging) |

---

## 4. MCP Tool Integration for LLM Consumption

### 4.1 MCP Tool Definitions

Three MCP tools that make XRL skeletons directly consumable by LLMs:

#### Tool 1: `load_xrl`

```json
{
    "name": "load_xrl",
    "description": "Load a source file as an XRL skeleton at specified depth. Returns compact binary or text representation.",
    "parameters": {
        "path": {
            "type": "string",
            "description": "Path to source file (.py, .js, .ts, .html, .md, etc.)"
        },
        "depth": {
            "type": "integer",
            "enum": [0, 1, 2, 3],
            "description": "0=full, 1=light, 2=medium, 3=deep"
        },
        "format": {
            "type": "string",
            "enum": ["text", "binary", "json"],
            "default": "text",
            "description": "Output format"
        },
        "budget": {
            "type": "integer",
            "optional": true,
            "description": "Maximum token budget. If exceeded, auto-deepens depth."
        }
    }
}
```

**Response:**
```json
{
    "file": "service.py",
    "language": "python",
    "depth": 2,
    "format": "text",
    "content": "@keep\nclass UserService {\n    @keep\n    fn get_user(id: UserId) -> User /* ... */ }\n    @flesh\n    fn _hash_password(password: String) -> String /* ... */ }\n}",
    "stats": {
        "originalTokens": 10000,
        "skeletonTokens": 3200,
        "reduction": "68%",
        "blocks": 12,
        "fleshBlocks": 3
    }
}
```

#### Tool 2: `expand_xrl`

```json
{
    "name": "expand_xrl",
    "description": "Expand a specific @flesh block in an XRL skeleton to see its full implementation.",
    "parameters": {
        "path": {
            "type": "string",
            "description": "Path to source file"
        },
        "block": {
            "type": "string",
            "description": "Block name to expand (e.g., 'fn hash_password' or 'class UserService')"
        },
        "depth": {
            "type": "integer",
            "default": 0,
            "description": "Depth to expand to (0 = full implementation)"
        }
    }
}
```

**Response:**
```json
{
    "expanded": "fn _hash_password(password: String) -> String {\n    let salt = generate_salt()\n    return pbkdf2(password, salt, iterations: 100000)\n}",
    "tokensAdded": 45,
    "newTotal": 3245,
    "blockType": "flesh"
}
```

#### Tool 3: `search_xrl`

```json
{
    "name": "search_xrl",
    "description": "Search across multiple XRL skeletons for specific patterns (functions, classes, imports).",
    "parameters": {
        "paths": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of file paths to search"
        },
        "pattern": {
            "type": "string",
            "description": "Search pattern (function name, class name, import path)"
        },
        "searchType": {
            "type": "string",
            "enum": ["function", "class", "import", "all"],
            "default": "all"
        },
        "depth": {
            "type": "integer",
            "default": 2
        }
    }
}
```

**Response:**
```json
{
    "results": [
        {
            "file": "service.py",
            "matches": [
                {"type": "function", "name": "get_user", "annotation": "keep"},
                {"type": "function", "name": "_hash_password", "annotation": "flesh"}
            ]
        }
    ],
    "totalMatches": 2,
    "filesScanned": 1
}
```

### 4.2 MCP Server Implementation

The MCP server will be a Node.js process that:

1. **Starts as a sidecar** alongside the existing MCP server
2. **Exposes 3 tools** (load_xrl, expand_xrl, search_xrl)
3. **Caches .xrb files** in memory for fast repeated access
4. **Auto-detects file language** and selects appropriate skeletonizer
5. **Reports token statistics** with every response

```bash
# Start the XRL MCP server
node Forge/xrs/xrl-mcp-server.js

# It registers with the MCP host:
# - name: "xrl-mcp-server"
# - tools: load_xrl, expand_xrl, search_xrl
```

### 4.3 Integration with Existing TokenSlayer Proxy

The existing [`tokenslayer_proxy_server.py`](Backend/Cognition/tokenslayer_proxy_server.py) at port 8106 already does text-level skeletonization. The XRL MCP server adds binary encoding on top:

```
LLM Request → TokenSlayer Proxy (:8106) → Text skeleton → XRL MCP → Binary .xrb
```

The proxy can be extended to optionally return binary XRL format when the LLM client supports it.

---

## 5. Benchmarking Framework

### 5.1 Enhanced Benchmark Suite

Building on the existing [`xrl-benchmark.cjs`](Forge/xrs/xrl-benchmark.cjs), the Phase 1 benchmark adds binary-specific metrics:

| Metric | Current (PoC) | Phase 1 Target |
|--------|---------------|----------------|
| Text skeleton reduction | 62-65% (JS/TS) | 62-65% (baseline) |
| Binary encoding reduction | — | 70-75% (text + binary) |
| Encoding speed | — | <100ms per file |
| Decoding speed | — | <50ms per file |
| File size (text skeleton) | ~40% of original | ~40% of original |
| File size (.xrb binary) | — | ~25% of original |

### 5.2 Benchmark Test Suite

| Test ID | Name | Category | What It Measures |
|---------|------|----------|-----------------|
| B1 | Token Reduction | Compression | Original vs text skeleton vs binary tokens |
| B2 | Encoding Speed | Performance | Time to tokenize + serialize |
| B3 | Decoding Speed | Performance | Time to deserialize + expand |
| B4 | Depth Filtering | Correctness | Correct filtering at each depth level |
| B5 | Budget Enforcement | Correctness | Correct trimming when budget exceeded |
| B6 | Round-Trip Fidelity | Correctness | Binary → text → binary equivalence |
| B7 | Multi-File Batch | Performance | Throughput for 10+ files |
| B8 | MCP Latency | Performance | End-to-end MCP tool response time |

### 5.3 Test Files

The benchmark uses the existing XRS tooling files plus additional LUMAX codebase files:

| File | Language | Lines | Expected Reduction |
|------|----------|-------|-------------------|
| `xrs.cjs` | TypeScript | 329 | 65% |
| `xrs-tokens.cjs` | TypeScript | 159 | 64% |
| `xrl-benchmark.cjs` | TypeScript | 385 | 62% |
| `tokenslayer.js` | TypeScript | 523 | 95% |
| `xrl-prompt.md` | Markdown | 176 | 1% (baseline) |
| `main.js` | TypeScript | 5,233 | 65% |
| `LumaxIntegrationLayer.js` | TypeScript | 1,399 | 65% |
| `compagent.py` | Python | ~2,000 | 68% |
| `index.html` | HTML | ~1,500 | 55% |
| `ARCHITECTURE.md` | Markdown | ~500 | 30% (improved) |

### 5.4 Benchmark Script

```bash
# Run all benchmarks
node xrl-benchmark2.cjs --all

# Run specific benchmark
node xrl-benchmark2.cjs --test B1 --file service.py

# Compare text vs binary
node xrl-benchmark2.cjs --compare --format text,binary

# Output as JSON for analysis
node xrl-benchmark2.cjs --all --json > benchmark-results.json
```

### 5.5 Success Criteria

| Criterion | Target | How Measured |
|-----------|--------|-------------|
| Binary token reduction | ≥70% (text + binary) | Compare original tokens vs binary stream size |
| Encoding speed | <100ms per file | `console.time()` around tokenize+serialize |
| Decoding speed | <50ms per file | `console.time()` around deserialize |
| Depth filtering accuracy | 100% | Unit tests for each depth level |
| Budget enforcement | Correct trimming | Test with budgets of 500, 1000, 2000, 4096 |
| Round-trip fidelity | 100% | Binary → text → binary produces identical output |
| MCP response time | <200ms | End-to-end timing of MCP tool calls |

---

## 6. Implementation Details

### 6.1 File: `xrl-tokenizer.cjs`

**Purpose:** Parse text skeleton output from `tokenslayer.js` and produce a structured AST with binary encoding.

**Key functions:**
- `parseSkeleton(text)` → `ASTNode[]` — Parse text skeleton into AST nodes
- `encodeAST(ast)` → `Buffer` — Encode AST into binary token stream
- `decodeTokens(buffer)` → `ASTNode[]` — Decode binary stream back to AST
- `writeXRB(ast, metadata)` → `Buffer` — Write complete .xrb file
- `readXRB(buffer)` → `{ast, metadata}` — Read .xrb file

**AST Node structure:**
```javascript
{
    type: 'KEEP' | 'DETAIL' | 'FLESH' | 'FN_SIG' | 'TYPE_DEF' | ...,
    annotation: 'keep' | 'detail' | 'flesh' | null,
    name: string | null,
    children: ASTNode[],
    depthMask: number,  // 4-bit visibility mask
    data: Buffer | null  // Raw binary data
}
```

### 6.2 File: `xrl-serializer.cjs`

**Purpose:** Filter AST by depth and serialize to requested output format.

**Key functions:**
- `filterByDepth(ast, depth)` → `ASTNode[]` — Filter AST nodes by depth mask
- `serializeToText(ast)` → `string` — Output human-readable XRL
- `serializeToBinary(ast)` → `Buffer` — Output binary token stream
- `serializeToJSON(ast)` → `string` — Output JSON AST
- `expandBlock(ast, blockName, depth)` → `string` — Expand specific block

### 6.3 File: `xrl-budget.cjs`

**Purpose:** Calculate token counts and enforce budget constraints.

**Key functions:**
- `countTokens(ast)` → `number` — Count tokens in AST
- `countBinaryTokens(buffer)` → `number` — Count tokens in binary stream
- `enforceBudget(ast, budget)` → `ASTNode[]` — Trim AST to fit budget
- `estimateDepthForBudget(ast, budget)` → `number` — Find optimal depth for budget

**Budget enforcement strategy:**
```
1. If current tokens ≤ budget → return as-is
2. Try depth 2 (medium skeleton) → if fits, return
3. Try depth 3 (deep skeleton) → if fits, return
4. Extract minimal (imports + public signatures only)
5. If still over budget → return with warning
```

### 6.4 File: `xrl.cjs`

**Purpose:** Unified CLI for all XRL operations.

```bash
# Basic usage
node xrl.cjs <filepath> [options]

# Options:
#   --depth <0-3>     Skeletonization depth (default: 2)
#   --format <type>   Output format: text, binary, json (default: text)
#   --output <path>   Output file path
#   --expand <name>   Expand a specific block
#   --budget <num>    Token budget for auto-depth selection
#   --stats           Show token statistics only
#   --json            Machine-readable JSON output

# Examples:
node xrl.cjs service.py --depth 2
node xrl.cjs service.py --format binary --output service.xrb
node xrl.cjs service.py --depth 2 --expand "fn authenticate"
node xrl.cjs service.py --budget 2048 --format json
```

### 6.5 File: `xrl-mcp-server.js`

**Purpose:** MCP server exposing XRL tools for LLM consumption.

**Key implementation:**
```javascript
// MCP tool handlers
server.tool('load_xrl', async ({ path, depth, format, budget }) => {
    const ast = await loadAndTokenize(path, depth);
    if (budget) enforceBudget(ast, budget);
    const content = serialize(ast, format);
    return { content, stats: getStats(ast) };
});

server.tool('expand_xrl', async ({ path, block, depth }) => {
    const fullAst = await loadFullAST(path);
    const expanded = expandBlock(fullAst, block, depth);
    return { expanded, tokensAdded: countTokens(expanded) };
});

server.tool('search_xrl', async ({ paths, pattern, searchType, depth }) => {
    const results = [];
    for (const p of paths) {
        const ast = await loadAndTokenize(p, depth);
        results.push(searchAST(ast, pattern, searchType));
    }
    return { results, totalMatches: results.length };
});
```

---

## 7. Timeline and Dependencies

### 7.1 Timeline (2 Weeks)

| Day | Task | Deliverable | Dependencies |
|-----|------|-------------|--------------|
| **1** | Build `xrl-tokenizer.cjs` — text skeleton parser + AST builder | Working parser that converts XRS output to structured AST | XRS skeletonizer (existing) |
| **2** | Build binary encoder/decoder — all 25 token types | Working binary encode/decode with round-trip tests | Day 1 |
| **3** | Build XRB file format — header, block table, metadata | Working .xrb file read/write | Day 2 |
| **4** | Build `xrl-serializer.cjs` — depth filtering + 3 output formats | Working depth-aware serialization (text/binary/json) | Day 3 |
| **5** | Build `xrl-budget.cjs` — token counting + budget enforcement | Working budget enforcement with auto-depth selection | Day 4 |
| **6** | Build `xrl.cjs` — unified CLI | Working CLI with all options | Days 1-5 |
| **7** | Build `xrl-mcp-server.js` — 3 MCP tools | Working MCP server registered with host | Day 6 |
| **8** | Build `xrl-benchmark2.cjs` — enhanced benchmark suite | Working benchmark with 8 test cases | Days 1-5 |
| **9** | Run benchmarks on 10+ LUMAX files | Benchmark results document | Day 8 |
| **10** | Integration testing with existing TokenSlayer proxy | Verified end-to-end pipeline | Days 7, 9 |

### 7.2 Dependencies

| Dependency | Type | Status | Notes |
|------------|------|--------|-------|
| XRS skeletonizer (`tokenslayer.js`) | Runtime | ✅ Existing | Core skeletonization engine |
| XRS CLI wrapper (`xrs.cjs`) | Runtime | ✅ Existing | Used as reference for CLI design |
| Node.js ≥ 18 | Runtime | ✅ Existing | All LUMAX tooling uses Node |
| MCP SDK | Runtime | ⚠️ Need to verify | `@modelcontextprotocol/sdk` for MCP server |
| Existing benchmark (`xrl-benchmark.cjs`) | Reference | ✅ Existing | Used as template for enhanced version |

### 7.3 Risk Assessment

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Binary format incompatible with future XRL versions | High | Medium | Use versioned header (uint16), document format spec |
| MCP SDK not available for Node.js | Medium | Low | Fall back to stdio-based MCP protocol |
| Performance degradation for large files | Medium | Low | Stream processing, avoid loading entire file into memory |
| Round-trip fidelity issues | High | Low | Comprehensive unit tests for all token types |
| LLM doesn't understand binary format | High | Low | Always provide text fallback; binary is for storage/transmission only |

---

## 8. Open Questions for Discussion

1. **Binary vs text for LLM consumption?** The binary format is primarily for storage and transmission. LLMs will likely always receive text skeletons. Should we invest in making LLMs understand binary tokens directly, or keep binary as an internal format?

2. **MCP server integration model?** Should the XRL MCP server be:
   - A standalone process (separate from existing MCP server)?
   - Integrated into the existing MCP server as additional tools?
   - A plugin loaded by the existing MCP server?

3. **Caching strategy?** Should .xrb files be cached on disk (like `.gemini/cache/raw_nodes`) or kept in memory only? Disk caching enables reuse across sessions but adds complexity.

4. **Markdown skeletonization improvement?** The PoC showed only 1% reduction for markdown. Should Phase 1 include an improved markdown skeletonizer, or defer to a later phase?

5. **Precision levels (MoQ-inspired)?** The design doc mentions `@precision(16/8/4/2/0)` annotations. Should these be implemented in Phase 1 or deferred to Phase 2?

---

## 9. Success Criteria

- [ ] **Binary tokenizer** correctly encodes all 25 token types with round-trip fidelity
- [ ] **XRB format** passes read/write tests with metadata preservation
- [ ] **Depth-aware serializer** correctly filters at all 4 depth levels
- [ ] **Budget enforcer** correctly trims AST to fit specified token budgets
- [ ] **MCP tools** (load_xrl, expand_xrl, search_xrl) respond within 200ms
- [ ] **Benchmark suite** measures all 8 metrics and produces JSON output
- [ ] **Total token reduction** ≥70% (text skeleton + binary encoding)
- [ ] **All existing XRS tooling** continues to work unchanged
- [ ] **Documentation** updated: XRB format spec, MCP tool docs, benchmark results

---

## 10. Appendix: File Inventory After Phase 1

```
Forge/xrs/
├── tokenslayer.js           # Existing — core skeletonizer engine
├── xrs.cjs                  # Existing — CLI wrapper (unchanged)
├── xrs-tokens.cjs           # Existing — token counter (unchanged)
├── xrl-prompt.md            # Existing — LLM prompt template (unchanged)
├── xrl-benchmark.cjs        # Existing — PoC benchmark (unchanged)
├── xrl-poc-results.md       # Existing — PoC results report
├── xrl-tokenizer.cjs        # NEW — binary tokenizer
├── xrl-serializer.cjs       # NEW — depth-aware serializer
├── xrl-budget.cjs           # NEW — token budget enforcer
├── xrl.cjs                  # NEW — unified CLI
├── xrl-mcp-server.js        # NEW — MCP server
├── xrl-benchmark2.cjs       # NEW — enhanced benchmark
├── xrb-format.md            # NEW — XRB binary format specification
└── benchmark-output/        # Existing — benchmark prompt files