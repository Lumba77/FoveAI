# Phase 14 Handoff — XRL Protocol Implementation

**Date:** 2026-07-11  
**Author:** AI Agent (TokenSlayer/XRL Pipeline)  
**Status:** Task 1 complete, Tasks 2-6 pending  
**Session Context:** ~40 turns, ~16.8K context window (critical)

---

## 1. What This Document Is

A comprehensive handoff for a fresh AI session to continue Phase 14 (XRL Protocol) implementation without re-reading the entire conversation history. All context, code locations, and pending work are captured here.

---

## 2. Architecture Overview

### Services
| Service | Port | File | Purpose |
|---------|------|------|---------|
| Proxy Server | 8103 | `Backend/Cognition/tokenslayer_proxy_server.py` | FastAPI server: skeletonizes code, manages atomic cache, provides XRL expansion endpoints |
| MCP Server | stdio | `Forge/scratch/TokenSlayer/mcp-server/build/index.js` | Node.js MCP server: 6 tools (analyze_files, expand_node, etc.) |
| Standalone CLI | — | `Forge/scratch/TokenSlayer/standalone/tokenslayer.js` | CLI skeletonizer, levels 0-5, tier shortcuts |

### Data Flow
```
User/Agent → MCP Server (index.js) → expand_node handler
  → Currently: local expandNode() from parser.js (decodes base64url nodeId, reads file directly)
  → Target: HTTP POST to proxy /api/xrl/expand with XRL URI

Proxy Server → _build_skeleton_block() → _extract_symbols_and_register()
  → Registers each symbol in atomic_cache.json with XRL URI
  → XRL URI format: xrl://lumax/{filepath}:{line}:{hash6}
```

### Key Files
| File | Lines | Purpose |
|------|-------|---------|
| `Backend/Cognition/tokenslayer_proxy_server.py` | 1068+ | Main proxy server — all XRL logic |
| `Forge/scratch/TokenSlayer/mcp-server/build/index.js` | ~500 | MCP server — 6 tools, expand_node handler at line 323 |
| `Forge/scratch/TokenSlayer/mcp-server/build/parser.js` | ~800 | Parser — expandNode() at line 715 |
| `test_xrl_workflow.py` | 93 | XRL integration test (all 6 steps passing) |
| `Plans/xrl-protocol.md` | 198 | XRL Protocol v1.0 spec |
| `Tools/lumax-xrl/xrs/` | 16 files | XRS CLI wrapper, XRB binary format, tokenizer, serializer, budget, MCP bridge, benchmarks |

---

## 3. What's Complete (Task 1)

### Task 1: Update `_extract_skeleton()` to register each extracted symbol in atomic cache with XRL URIs

**Status: COMPLETE** — Two new helper functions inserted, `_build_skeleton_block()` modified.

#### New Function 1: `_extract_symbol_content()` (line 352)
```python
def _extract_symbol_content(lines: list, start_idx: int, language: str = "python") -> str:
```
- Extracts full content of a symbol from its start line to the next top-level definition
- Handles both indentation-based (Python) and brace-based (JS/TS/Rust/C#/Java) languages
- For brace-based: tracks `brace_depth` until it returns to 0
- For indentation-based: checks if a new top-level definition at same or lesser indent is encountered
- Falls back to returning just the start line if end can't be determined

#### New Function 2: `_extract_symbols_and_register()` (line 398)
```python
def _extract_symbols_and_register(code: str, source_hint: str = "") -> list:
```
- Parses code line by line, matches against 11 regex patterns for function/class/interface/type/struct/trait/enum/impl definitions
- For each match, extracts symbol content via `_extract_symbol_content()`
- Registers each in atomic cache via `register_xrl_in_cache()` with:
  - `signature`: The first line of the symbol (e.g., `def my_func(param1, param2):`)
  - `filepath`: The source_hint (filename)
  - `line`: 1-based line number
  - `hash`: First 6 chars of MD5 of content
  - `content`: Full symbol content (stored in raw_nodes cache)
  - `namespace`: "lumax"
  - `version`: 1
- Returns list of XRL URIs (e.g., `["xrl://lumax/myfile.py:42:a1b2c3", ...]`)

#### Modified Function: `_build_skeleton_block()` (line 471)
- **Now calls** `_extract_symbols_and_register(code, source_hint)` at the start to register ALL extracted symbols
- **Includes** all XRL URIs in the header: first URI + symbol count + first 10 URIs
- **Fallback**: If `_extract_symbols_and_register()` returns empty list, registers the first signature line as a single entry
- **Expand hint**: Builds a proper expand hint with the first 5 URIs

#### Exact Code Locations (Proxy Server)
- Line 352: `_extract_symbol_content()` — NEW
- Line 398: `_extract_symbols_and_register()` — NEW
- Line 471: `_build_skeleton_block()` — MODIFIED (now calls `_extract_symbols_and_register()`)
- Line 104: `generate_xrl()` — existing, unchanged
- Line 111: `parse_xrl()` — existing, unchanged
- Line 142: `register_xrl_in_cache()` — existing, unchanged
- Line 326: `_extract_skeleton()` — existing, unchanged (the original regex-based skeletonizer)
- Line 658: `skeletonize_file_content()` — existing, unchanged (calls `_build_skeleton_block()`)

---

## 4. Pending Tasks (2-6)

### Task 2: Wire MCP `expand_node` to proxy `/api/xrl/expand`

**Location:** `Forge/scratch/TokenSlayer/mcp-server/build/index.js` line 323-334

**Current code (lines 323-334):**
```javascript
if (request.params.name === "expand_node") {
    const nodeId = args.nodeId;
    if (!nodeId)
        throw new Error("nodeId is required");
    const result = expandNode(nodeId);
    if (!result) {
        return { content: [{ type: "text", text: "❌ Could not expand node — file may have been modified since analysis." }] };
    }
    return {
        content: [{ type: "text", text: `// ${path.basename(result.filePath)} lines ${result.startLine}–${result.endLine}\n\n${result.content}` }]
    };
}
```

**Current behavior:** Calls `expandNode(nodeId)` from `parser.js` line 715, which decodes base64url-encoded nodeId, parses `filePath:startLine:endLine`, reads the file directly, and returns the slice of lines.

**Target behavior:** Instead of using local `expandNode()`, make an HTTP POST to `http://127.0.0.1:8103/api/xrl/expand` with the XRL URI. The proxy's `/api/xrl/expand` endpoint (line 718) already handles XRL URI expansion.

**Implementation approach:**
1. Import `http` or use `fetch` (Node 18+) in the MCP server
2. In the `expand_node` handler, check if the `nodeId` is an XRL URI (starts with `xrl://`)
3. If XRL URI: POST to `http://127.0.0.1:8103/api/xrl/expand` with `{"xrl": nodeId}`
4. If not XRL URI: fall back to existing `expandNode()` for backward compatibility
5. Parse the proxy response and return the expanded content

**Proxy endpoint reference** (line 718 in proxy server):
```python
@app.post("/api/xrl/expand")
async def xrl_expand(request: XRLExpandRequest):
    """Expand an XRL URI to full context"""
    # Parses XRL URI, looks up in atomic cache, returns content
```

**MCP server imports** (line 15 in index.js):
```javascript
import { expandNode, ... } from './parser.js'
```
The `expandNode` import can remain for the fallback path.

### Task 3: Add `resolve_xrl` MCP tool

**Location:** `Forge/scratch/TokenSlayer/mcp-server/build/index.js` — add new tool handler

**Implementation:**
1. Add a new tool definition in the `ListToolsRequestSchema` handler (around line 100-200)
2. Add a new handler in the `SetToolsRequestSchema` handler (after the `expand_node` handler at line 334)
3. The tool should accept an XRL URI and return metadata (filepath, line, hash, signature, created_at)
4. Call proxy's `POST /api/xrl/resolve` endpoint (line 803)

**Proxy endpoint reference** (line 803):
```python
@app.post("/api/xrl/resolve")
async def xrl_resolve(request: XRLResolveRequest):
    """Resolve XRL URI metadata"""
```

### Task 4: Add startup auto-prune for entries >7 days old

**Location:** `Backend/Cognition/tokenslayer_proxy_server.py` — in the startup section (around line 1050-1070)

**Implementation:**
1. Add a function `_auto_prune_cache()` that:
   - Iterates through `_ATOMIC_CACHE`
   - Removes entries where `created_at` is >7 days old
   - Saves the pruned cache to `atomic_cache.json`
2. Call it at startup, before `uvicorn.run()`

**Proxy endpoint reference** (line 837):
```python
@app.post("/api/xrl/prune")
async def xrl_prune(request: XRLPruneRequest):
    """Prune stale entries from atomic cache"""
```
This endpoint already exists — the auto-prune should call similar logic at startup.

### Task 5: Update `Plans/xrl-protocol.md` with implementation status

**Location:** `Plans/xrl-protocol.md`

**What to update:**
- Mark XRL URI format as implemented
- Mark `generate_xrl()`, `parse_xrl()`, `register_xrl_in_cache()` as implemented
- Mark `/api/xrl/expand`, `/api/xrl/resolve`, `/api/xrl/status`, `/api/xrl/prune` endpoints as implemented
- Mark per-symbol registration in atomic cache as implemented (Task 1)
- Mark MCP `expand_node` → proxy wiring as pending (Task 2)
- Mark `resolve_xrl` MCP tool as pending (Task 3)
- Mark startup auto-prune as pending (Task 4)
- Mark XRS/XRB integration as pending (Task 6)

### Task 6: Integrate new XRS/XRB work from `Tools/lumax-xrl/xrs/`

**Location:** Multiple files in `Tools/lumax-xrl/xrs/` (16 files)

**What to integrate:**
- **`xrs.cjs`** (329 lines): XRS CLI wrapper — wraps TokenSlayer skeletonizer with depth control (0-3), `--expand`, `--json`, `--stats`. Currently standalone. Should be callable from the proxy server as an alternative to the existing CLI path.
- **`xrl.cjs`** (471 lines): Unified CLI — complete pipeline: read source → XRS skeletonize → tokenize → apply budget → serialize → output. Currently standalone.
- **`xrl-tokenizer.cjs`** (834 lines): Core tokenizer — 25 token types with depth masks. Could be used by the proxy for binary token stream generation.
- **`xrl-serializer.cjs`** (900 lines): XRB binary serializer/deserializer — implements XRB format v1.0. Could be used by the proxy for binary output.
- **`xrl-budget.cjs`** (459 lines): Token budget enforcement — progressive stripping by depth. Could be used by the proxy for budget-aware skeletonization.
- **`xrl-mcp-bridge.py`** (439 lines): Python interface for XRL pipeline — calls `xrl.cjs` as subprocess. Could be imported by the proxy server.
- **`xrl-mcp-server.cjs`** (516 lines): Standalone MCP server for XRL tools (load_xrl, expand_xrl, search_xrl). Could be registered alongside the TokenSlayer MCP server.
- **`xrl-prompt.md`** (175 lines): LLM prompt template for XRL-aware code assistants.
- **`xrb-format.md`** (292 lines): XRB binary format specification v1.0.
- **`xrl-poc-results.md`** (188 lines): PoC results — 67% average token reduction.
- **Benchmark scripts**: `xrl-benchmark.cjs` (385 lines), `xrl-benchmark2.cjs` (501 lines), `xrl-benchmark-local.cjs` (808 lines), `xrs-tokens.cjs` (159 lines), `xrl-infer.cjs` (776 lines)

**Integration approach:**
1. **Proxy integration**: Import `xrl_mcp_bridge.py` functions into the proxy server for XRL pipeline operations
2. **MCP integration**: Register `xrl-mcp-server.cjs` as an additional MCP server in `mcp-config.json`
3. **CLI integration**: Ensure `xrs.cjs` and `xrl.cjs` are discoverable from the proxy's CLI execution path
4. **Documentation**: Update `Plans/xrl-protocol.md` to reference the XRB format spec and XRL prompt template

---

## 5. Key Architecture Decisions

### XRL URI Format
```
xrl://lumax/{filepath}:{line}:{hash6}
```
- `namespace`: "lumax" (hardcoded in `generate_xrl()`)
- `filepath`: Relative path from project root
- `line`: 1-based line number of the symbol definition
- `hash6`: First 6 characters of MD5 hex digest of the symbol content

### Atomic Cache Structure
```python
_ATOMIC_CACHE = {
    "xrl://lumax/myfile.py:42:a1b2c3": {
        "signature": "def my_func(param1, param2):",
        "filepath": "myfile.py",
        "line": 42,
        "hash": "a1b2c3",
        "namespace": "lumax",
        "version": 1,
        "content_hash": "full_md5_hash",
        "raw_node_path": ".gemini/cache/raw_nodes/a1b2c3_full_md5_hash.txt",
        "created_at": "2026-07-11T12:00:00",
    }
}
```

### Cache Persistence
- In-memory: `_ATOMIC_CACHE` dict (global)
- File: `atomic_cache.json` (loaded at startup via `load_cache()`, saved on each `register_xrl_in_cache()` call)
- Raw nodes: `.gemini/cache/raw_nodes/` directory (full content stored as text files)

### Proxy Startup
```python
# Line 1050-1070 in proxy server
if __name__ == "__main__":
    load_cache()  # Load atomic_cache.json into _ATOMIC_CACHE
    uvicorn.run(app, host="127.0.0.1", port=8103)
```

### MCP Server Registration
In `mcp-config.json`:
```json
{
  "mcpServers": {
    "tokenslayer": {
      "command": "node",
      "args": ["Forge/scratch/TokenSlayer/mcp-server/build/index.js"],
      "env": {}
    }
  }
}
```

---

## 6. Test Results

### `test_xrl_workflow.py` — All 6 steps PASSING (2026-07-11)
1. ✅ Skeletonize a file → returns skeleton with XRL URIs
2. ✅ Check XRL status → shows cache entries
3. ✅ Expand XRL URI → returns full content
4. ✅ Resolve XRL URI → returns metadata
5. ✅ Prune cache → removes entries
6. ✅ Verify prune → status shows 0 entries

### How to Run Tests
```bash
# Start proxy (in Terminal 1)
python Backend/Cognition/tokenslayer_proxy_server.py

# Run XRL workflow test (in Terminal 2)
python test_xrl_workflow.py

# Check proxy health
curl http://127.0.0.1:8103/health

# Skeletonize a file
curl -X POST http://127.0.0.1:8103/api/skeletonize \
  -H "Content-Type: application/json" \
  -d "{\"filepath\": \"Backend/Cognition/soul_core.py\", \"level\": 3}"

# Check XRL status
curl http://127.0.0.1:8103/api/xrl/status
```

---

## 7. Known Issues & Gotchas

### Proxy Config in `.env` (Lines 41-51)
- All `LUMAX_PROXY_*` variables are **already commented out** with `#`
- These are dead config from Proxy v2 that never worked
- The current proxy hardcodes port 8103 and doesn't read these variables
- **No action needed** — already handled

### Context Window Constraint
- The model has a **16.8K context window** (very tight)
- Each turn's `environment_details` section adds ~5-8K tokens of instructions
- **Strategy**: Keep responses minimal, use targeted diffs, avoid full file rewrites
- **Proactive reset**: After ~15 turns, suggest starting a fresh session with this handoff

### Proxy Process Management
- The proxy runs as a **foreground process** in VS Code's Terminal 1
- It does NOT appear in Task Manager as a background process
- To restart: Ctrl+C in Terminal 1, then `python Backend/Cognition/tokenslayer_proxy_server.py`
- To verify: `curl http://127.0.0.1:8103/health`

### MCP Server Build
- The MCP server is compiled to `build/index.js` from TypeScript source
- Source is in `Forge/scratch/TokenSlayer/mcp-server/src/`
- To rebuild: `cd Forge/scratch/TokenSlayer/mcp-server && npm run build`
- **Important**: Edit the `build/index.js` directly for quick changes, or edit source and rebuild

---

## 8. Quick Start for Fresh Session

```bash
# 1. Read this handoff
cat Plans/handover-phase14.md

# 2. Read the proxy server skeleton (use TokenSlayer MCP)
#    (Don't read full file — use analyze_files or targeted ranges)

# 3. Start proxy if not running
python Backend/Cognition/tokenslayer_proxy_server.py

# 4. Verify proxy is healthy
curl http://127.0.0.1:8103/health

# 5. Run XRL workflow test to verify Task 1
python test_xrl_workflow.py

# 6. Proceed to Task 2: Wire MCP expand_node to proxy
#    Edit: Forge/scratch/TokenSlayer/mcp-server/build/index.js line 323-334

# 7. Task 3: Add resolve_xrl MCP tool
#    Edit: Forge/scratch/TokenSlayer/mcp-server/build/index.js

# 8. Task 4: Add startup auto-prune
#    Edit: Backend/Cognition/tokenslayer_proxy_server.py (startup section)

# 9. Task 5: Update Plans/xrl-protocol.md

# 10. Task 6: Integrate XRS/XRB work
```

---

## 9. File Change Log

| File | Change | Status |
|------|--------|--------|
| `Backend/Cognition/tokenslayer_proxy_server.py` | Inserted `_extract_symbol_content()` | ✅ Done |
| `Backend/Cognition/tokenslayer_proxy_server.py` | Inserted `_extract_symbols_and_register()` | ✅ Done |
| `Backend/Cognition/tokenslayer_proxy_server.py` | Modified `_build_skeleton_block()` to call `_extract_symbols_and_register()` | ✅ Done |
| `Forge/scratch/TokenSlayer/mcp-server/build/index.js` | Modify `expand_node` handler to call proxy | ✅ Done |
| `Forge/scratch/TokenSlayer/mcp-server/build/index.js` | Add `resolve_xrl` tool handler | ✅ Done |
| `Backend/Cognition/tokenslayer_proxy_server.py` | Add startup auto-prune | ✅ Done |
| `Backend/Cognition/tokenslayer_proxy_server.py` | Integrate `xrl_mcp_bridge` (using `importlib` for dash support) | ✅ Done |
| `Plans/xrl-protocol.md` | Update implementation status and specifications links | ✅ Done |
| `mcp-config.json` | Register XRL MCP server | ✅ Done |
| `context.md` | Log completed tasks | ✅ Done |

---

## 10. Todo List (for new session)

- [x] Task 2: Wire MCP `expand_node` to proxy `/api/xrl/expand` — modify `index.js`
- [x] Task 3: Add `resolve_xrl` MCP tool — add new handler in `index.js`
- [x] Task 4: Add startup auto-prune for entries >7 days old — modify proxy startup
- [x] Task 5: Update `Plans/xrl-protocol.md` with implementation status
- [x] Task 6: Integrate new XRS/XRB work from `Tools/lumax-xrl/xrs/`
- [x] Test: Restart proxy and run `test_xrl_workflow.py` to verify all tasks
- [x] Log: Update `context.md` with completed tasks