# XRL Protocol v1.0 — eXpandable Reference Links

## Overview

XRL (eXpandable Reference Links) is a standardized URI format for referencing code locations that can be expanded on-demand via the TokenSlayer Proxy server. It bridges the gap between ultra-compressed level-5 atomic skeletons and full source code, enabling agents to work with ~98-99.5% token reduction while retaining the ability to drill into any specific symbol.

## Core URI Format

```
xrl://{namespace}/{filepath}:{line}:{hash6}
```

### Components

| Component | Description | Example |
|-----------|-------------|---------|
| `namespace` | Project/repo scope identifier | `lumax` |
| `filepath` | Relative path from repo root | `Backend/Cognition/soul_core.py` |
| `line` | Line number of the symbol (1-based) | `97` |
| `hash6` | 6-char MD5 hex prefix of the content | `a3f2b1` |

### Examples

```
xrl://lumax/Backend/Cognition/soul_core.py:97:a3f2b1
xrl://lumax/Backend/Cognition/tokenslayer_proxy_server.py:261:7c4d9e
xrl://lumax/Forge/scratch/TokenSlayer/standalone/tokenslayer.js:42:f1e2d3
```

## Skeleton Block Format (Updated)

Every skeletonized block MUST include an XRL URI in its header:

```markdown
```python
# [TokenSlayer Devourer: Structural Skeleton Only]
# RAW CONTEXT NODE: tag_a3f2b1
# XRL: xrl://lumax/Backend/Cognition/soul_core.py:97:a3f2b1
# Source: Backend/Cognition/soul_core.py
# Compression: regex (level 3)
# The uncompressed raw code was automatically saved at the side to:
# C:\Users\danie\program\LUMAX\.gemini\cache\raw_nodes\tag_a3f2b1.txt
# (To expand, use: curl -X POST http://localhost:8103/api/xrl/expand -H "Content-Type: application/json" -d '{"uri": "xrl://lumax/Backend/Cognition/soul_core.py:97:a3f2b1"}')
```

## Atomic Cache Schema

```json
{
  "xrl://lumax/Backend/Cognition/soul_core.py:97:a3f2b1": {
    "signature": "def process_thought(self, thought: str) -> dict:",
    "filepath": "Backend/Cognition/soul_core.py",
    "line": 97,
    "hash": "a3f2b1",
    "namespace": "lumax",
    "created_at": "2026-07-10T23:42:00.000Z",
    "version": 1,
    "content_hash": "a3f2b1c4d5e6f7a8b9c0d1e2f3a4b5c6",
    "raw_node_path": ".gemini/cache/raw_nodes/tag_a3f2b1.txt"
  }
}
```

## API Endpoints

### `POST /api/xrl/expand`

Expand one or more XRL URIs to their full source context.

**Request:**
```json
{
  "uris": ["xrl://lumax/Backend/Cognition/soul_core.py:97:a3f2b1"],
  "context_lines": 5
}
```

**Response:**
```json
{
  "results": [
    {
      "uri": "xrl://lumax/Backend/Cognition/soul_core.py:97:a3f2b1",
      "expanded": "→ 97: def process_thought(self, thought: str) -> dict:\n  98:     ...",
      "source": "atomic_cache",
      "filepath": "Backend/Cognition/soul_core.py",
      "line": 97
    }
  ],
  "not_found": []
}
```

### `POST /api/xrl/resolve`

Resolve an XRL URI to its file:line location without expanding content.

**Request:**
```json
{
  "uri": "xrl://lumax/Backend/Cognition/soul_core.py:97:a3f2b1"
}
```

**Response:**
```json
{
  "uri": "xrl://lumax/Backend/Cognition/soul_core.py:97:a3f2b1",
  "filepath": "Backend/Cognition/soul_core.py",
  "line": 97,
  "hash": "a3f2b1",
  "namespace": "lumax",
  "resolved": true
}
```

### `GET /api/xrl/status`

Get cache statistics.

**Response:**
```json
{
  "total_entries": 42,
  "namespaces": {"lumax": 42},
  "oldest_entry": "2026-07-10T23:42:00.000Z",
  "newest_entry": "2026-07-10T23:45:00.000Z",
  "cache_file": "Backend/Cognition/atomic_cache.json",
  "raw_nodes_dir": ".gemini/cache/raw_nodes/",
  "raw_node_count": 42
}
```

### `POST /api/xrl/prune`

Remove stale entries from the atomic cache.

**Request:**
```json
{
  "max_age_hours": 24,
  "namespace": "lumax"
}
```

**Response:**
```json
{
  "pruned": 5,
  "remaining": 37
}
```

## MCP Tool Integration

### `expand_node` → Proxy Bridge

The MCP server's `expand_node` tool MUST call the proxy's `/api/xrl/expand` endpoint when the node ID is an XRL URI:

```
MCP Tool: expand_node(node_id="xrl://lumax/Backend/Cognition/soul_core.py:97:a3f2b1")
  → HTTP POST http://localhost:8103/api/xrl/expand
  → Returns expanded source context
```

### New MCP Tool: `resolve_xrl`

Resolve an XRL URI to its file:line location.

```
MCP Tool: resolve_xrl(uri="xrl://lumax/Backend/Cognition/soul_core.py:97:a3f2b1")
  → HTTP POST http://localhost:8103/api/xrl/resolve
  → Returns {filepath, line, hash, namespace}
```

## Hash Generation Algorithm

```python
import hashlib

def generate_xrl(filepath: str, line: int, content: str, namespace: str = "lumax") -> str:
    """Generate an XRL URI for a code location."""
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
    hash6 = content_hash[:6]
    return f"xrl://{namespace}/{filepath}:{line}:{hash6}"

def parse_xrl(uri: str) -> dict:
    """Parse an XRL URI into its components."""
    # xrl://namespace/filepath:line:hash6
    parts = uri.replace("xrl://", "").split("/", 1)
    namespace = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    # filepath:line:hash6
    last_colon = rest.rfind(":")
    second_last_colon = rest.rfind(":", 0, last_colon)
    filepath = rest[:second_last_colon]
    line = int(rest[second_last_colon+1:last_colon])
    hash6 = rest[last_colon+1:]
    return {
        "namespace": namespace,
        "filepath": filepath,
        "line": line,
        "hash": hash6
    }
```

## Cache Invalidation Strategy

1. **TTL-based**: Entries older than 24 hours are candidates for pruning
2. **File-based**: If the source file's modification time is newer than the cache entry, the entry is stale
3. **Manual**: `POST /api/xrl/prune` for explicit cleanup
4. **Startup**: Auto-prune entries >7 days old on proxy startup

## Versioning

- **Cache entry version**: Incremented when the same hash is re-generated with different content
- **Protocol version**: `xrl://v1/` — bump when URI format changes
- **Backward compatibility**: Old `tag_` format still supported via `expand_hash()`

## Security Considerations

- XRL URIs are content-addressed (hash-based) — tampering changes the hash
- Filepath traversal is prevented by `expand_file_line()` path resolution
- No authentication required for local proxy (port 8103 is localhost-only)
- Rate limiting recommended for batch expansion (>100 URIs)

## Migration Path

1. **Phase 1**: Add XRL URI generation to `_build_skeleton_block()` and `_extract_skeleton()`
2. **Phase 2**: Add XRL endpoints to proxy server
3. **Phase 3**: Update atomic cache schema to include XRL metadata
4. **Phase 4**: Wire MCP `expand_node` to proxy `/api/xrl/expand`
5. **Phase 5**: Add `resolve_xrl` MCP tool
6. **Phase 6**: Deprecate old `tag_` format (keep backward compat for 30 days)

---

## Implementation Status (Phase 14 — 2026-07-11)

| Component | Status | Location |
|-----------|--------|----------|
| XRL URI format (`xrl://lumax/{filepath}:{line}:{hash6}`) | ✅ Implemented | `tokenslayer_proxy_server.py:104` |
| `generate_xrl()` | ✅ Implemented | `tokenslayer_proxy_server.py:104` |
| `parse_xrl()` | ✅ Implemented | `tokenslayer_proxy_server.py:111` |
| `register_xrl_in_cache()` | ✅ Implemented | `tokenslayer_proxy_server.py:142` |
| Per-symbol registration in atomic cache (Task 1) | ✅ Implemented | `tokenslayer_proxy_server.py:352,398,471` |
| `POST /api/xrl/expand` | ✅ Implemented | `tokenslayer_proxy_server.py:829` |
| `POST /api/xrl/resolve` | ✅ Implemented | `tokenslayer_proxy_server.py:~870` |
| `GET /api/xrl/status` | ✅ Implemented | `tokenslayer_proxy_server.py:~900` |
| `POST /api/xrl/prune` | ✅ Implemented | `tokenslayer_proxy_server.py:~948` |
| MCP `expand_node` → proxy `/api/xrl/expand` wiring (Task 2) | ✅ Implemented | `mcp-server/build/index.js:327` |
| MCP `resolve_xrl` tool (Task 3) | ✅ Implemented | `mcp-server/build/index.js:201,373` |
| Startup auto-prune >7 days (Task 4) | ✅ Implemented | `tokenslayer_proxy_server.py:1177` |
| XRS/XRB integration (Task 6) | ✅ Implemented | [xrs.cjs](file:///c:/Users/danie/program/LUMAX/Tools/lumax-xrl/xrs/xrs.cjs), [xrl-mcp-bridge.py](file:///c:/Users/danie/program/LUMAX/Tools/lumax-xrl/xrs/xrl-mcp-bridge.py) |

## Related Specifications & Templates

- **Binary Token Layout Specification**: See [xrb-format.md](file:///c:/Users/danie/program/LUMAX/Tools/lumax-xrl/xrs/xrb-format.md) for X-Ray Language Binary format (XRB v1.0).
- **Prompt Template**: See [xrl-prompt.md](file:///c:/Users/danie/program/LUMAX/Tools/lumax-xrl/xrs/xrl-prompt.md) for configuring LLM system prompts for XRL-aware code analysis.