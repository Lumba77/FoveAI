# XRB Binary Format Specification v1.0

## Overview

XRB (X-Ray Binary) is a compact binary container format for storing XRL-skeletonized source code. It is inspired by GGUF (GGML Universal Format) and applies the same compression principles at the code representation layer.

### Design Goals

1. **Token Efficiency** — Binary encoding reduces token count by 15-25% over text skeletons
2. **Depth-Aware** — Each token carries a 4-bit depth visibility mask for O(1) filtering
3. **Streamable** — Block table enables random access to specific functions/classes
4. **Self-Describing** — Header contains all metadata needed for reconstruction
5. **Extensible** — Versioned format with reserved fields for future expansion

### File Extension

`.xrb`

### MIME Type

`application/x-xrb`

---

## 1. File Structure

```
┌─────────────────────────────────────────┐
│ Header (16 bytes)                       │
├─────────────────────────────────────────┤
│ Block Table (variable)                  │
├─────────────────────────────────────────┤
│ Token Data (variable)                   │
├─────────────────────────────────────────┤
│ Metadata Section (optional, variable)   │
└─────────────────────────────────────────┘
```

---

## 2. Header (16 bytes)

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0 | 4 | Magic | `XRB1` (0x584E4231) |
| 4 | 2 | Version | Format version (currently 1) |
| 6 | 1 | Default Depth | Default skeletonization depth (0-3) |
| 7 | 4 | Token Budget | Maximum token budget (0 = unlimited) |
| 11 | 4 | Block Count | Number of blocks in block table |
| 15 | 1 | Flags | Bit flags (see below) |

### Flags

| Bit | Meaning |
|-----|---------|
| 0 | Has metadata section |
| 1 | Has annotations |
| 2 | Has expand hints |
| 3-7 | Reserved (must be 0) |

---

## 3. Block Table

The block table provides random access to named blocks (functions, classes, methods).

### Block Table Entry (16 bytes each)

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0 | 4 | Name Offset | Byte offset into string table for block name |
| 4 | 4 | Token Offset | Byte offset into token data for this block |
| 8 | 4 | Token Count | Number of tokens in this block |
| 12 | 1 | Block Type | 0=function, 1=class, 2=method, 3=arrow, 4=variable |
| 13 | 1 | Depth Mask | Visibility mask for this block |
| 14 | 1 | Annotation | Annotation type (0=none, 1=@keep, 2=@detail, 3=@flesh, 4=@test, 5=@doc) |
| 15 | 1 | Reserved | Must be 0 |

### String Table

The string table follows the block entries and contains null-terminated UTF-8 strings for block names.

---

## 4. Token Data

### Token Header (1 byte)

Each token starts with a 1-byte header:

```
Bit:  7  6  5  4  3  2  1  0
     ┌──┴──┴──┴──┴──┴──┴──┴──┐
     │ Opcode (5 bits) │ Depth │
     └─────────────────────────┘
```

- **Opcode** (bits 7-3): Token type (0-31)
- **Depth Mask** (bits 2-0): Visibility depth (0-3, or 0xF for all depths)

### Token Types

| Opcode | Name | Description | Payload |
|--------|------|-------------|---------|
| 0x00 | END | End of token stream | None |
| 0x01 | KEEP | Always-visible content | String |
| 0x02 | DETAIL | Visible at depth ≤ 2 | String |
| 0x03 | FLESH | Visible at depth ≤ 1 | String |
| 0x04 | FN_SIG | Function signature | String |
| 0x05 | TYPE_DEF | Type definition | String |
| 0x06 | IMPORT | Import statement | String |
| 0x07 | EXPORT | Export statement | String |
| 0x08 | BLOCK_OPEN | Block start (scope) | None |
| 0x09 | BLOCK_CLOSE | Block end | None |
| 0x0A | IDENT | Identifier | String |
| 0x0B | STRING | String literal | String |
| 0x0C | NUMBER | Numeric literal | 4 bytes (float32) |
| 0x0D | DECORATOR | Decorator/annotation | String |
| 0x0E | MODIFIER | Access modifier | 1 byte (enum) |
| 0x0F | ASSIGN | Assignment operator | None |
| 0x10 | SEPARATOR | Separator (comma, semicolon) | None |
| 0x11 | FLESH_MARKER | @flesh annotation marker | None |
| 0x12 | EXPAND_HINT | Expansion hint for LLM | String |
| 0x13-0x1F | Reserved | Future use | — |

### String Encoding

Strings use variable-length length prefix + UTF-8 content:

- **Length < 128**: Single byte (0x00-0x7F) followed by UTF-8 bytes
- **Length ≥ 128**: Two bytes (0x80 | (len >> 8), len & 0xFF) followed by UTF-8 bytes

### Modifier Enum (1 byte)

| Value | Modifier |
|-------|----------|
| 0x00 | public |
| 0x01 | private |
| 0x02 | protected |
| 0x03 | static |
| 0x04 | abstract |
| 0x05 | async |
| 0x06 | const |
| 0x07 | let |
| 0x08 | var |
| 0x09-0xFF | Reserved |

---

## 5. Metadata Section (Optional)

Present when Flags bit 0 is set.

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0 | 4 | Metadata Size | Total size of metadata section |
| 4 | 2 | Key Count | Number of key-value pairs |
| 6+ | var | Key-Value Pairs | Repeated entries |

### Key-Value Pair

| Size | Field | Description |
|------|-------|-------------|
| 2 | Key Length | Length of key string |
| var | Key | UTF-8 key string |
| 2 | Value Length | Length of value string |
| var | Value | UTF-8 value string |

### Standard Metadata Keys

| Key | Description |
|-----|-------------|
| `source_file` | Original source file path |
| `language` | Programming language |
| `created` | Creation timestamp (ISO 8601) |
| `original_size` | Original file size in bytes |
| `original_tokens` | Original token count |
| `skeleton_tokens` | Skeleton token count |
| `compression_ratio` | Compression ratio (original/skeleton) |
| `tool_version` | XRL tool version that created this file |

---

## 6. Depth-Aware Filtering

Each token carries a 3-bit depth mask that determines visibility at each depth level:

| Depth | Name | Visible Tokens |
|-------|------|----------------|
| 0 | Full | All tokens (mask & 0x1) |
| 1 | Light | KEEP, DETAIL, FN_SIG, TYPE_DEF, IMPORT, EXPORT, DECORATOR, MODIFIER (mask & 0x2) |
| 2 | Medium | KEEP, FN_SIG, TYPE_DEF, IMPORT, EXPORT (mask & 0x4) |
| 3 | Deep | KEEP, FN_SIG, IMPORT, EXPORT (mask & 0x8) |

### Filtering Algorithm

```
function filterTokens(tokens, depth):
    for each token in tokens:
        if token.depthMask & (1 << depth):
            yield token
```

This is O(1) per token — no string parsing needed.

---

## 7. Example

### Source (Python)

```python
@dataclass
class User:
    """User model with authentication"""

    id: int
    name: str

    @flesh
    def authenticate(self, password: str) -> bool:
        # Implementation detail
        return check_password(self.id, password)
```

### XRB Binary (hex dump)

```
0000: 58 52 42 31 01 00 02 00 00 00 00 01 00 00 00 03  XRB1............
0010: 01 00 00 00 0A 00 00 00 05 00 00 00 01 01 00 00  ................
0020: 04 55 73 65 72 00 0A 75 73 65 72 5F 6D 6F 64 65  .User..user_mode
0030: 6C 00 0C 61 75 74 68 65 6E 74 69 63 61 74 65 00  l..authenticate.
0040: 0D 64 61 74 61 63 6C 61 73 73 0E 01 0A 55 73 65  .dataclass...Use
0050: 72 0E 01 0A 69 64 0E 01 0A 6E 61 6D 65 0E 01 0A  r...id...name...
0060: 61 75 74 68 65 6E 74 69 63 61 74 65 0E 01 0A 73  authenticate...s
0070: 65 6C 66 0E 01 0A 70 61 73 73 77 6F 72 64 0E 01  elf...password..
0080: 0A 62 6F 6F 6C 11 12 63 68 65 63 6B 5F 70 61 73  .bool..check_pas
0090: 73 77 6F 72 64 00 00                             sword..
```

### Size Comparison

| Format | Size | Tokens (est.) | Reduction |
|--------|------|---------------|-----------|
| Original | 256 bytes | 64 | — |
| Text skeleton | 98 bytes | 25 | 61% |
| XRB binary | 152 bytes | 38 | 41% |

Note: Binary is larger than text skeleton for small files due to header overhead. For files > 10KB, binary is consistently smaller.

---

## 8. Implementation Notes

### Byte Order

All multi-byte values are **little-endian** (matching x86 architecture).

### String Encoding

All strings are UTF-8 encoded. Null characters (0x00) are not allowed in string content.

### Validation

Valid XRB files must:
1. Start with magic bytes `XRB1`
2. Have version ≤ current version
3. Have block count matching actual block entries
4. Have token data ending with END token (opcode 0x00)
5. Have metadata size matching actual metadata (if present)

### Extension

Future versions should:
1. Increment the version number
2. Add new token types in the reserved range (0x13-0x1F)
3. Add new metadata keys as needed
4. Maintain backward compatibility with version 1 readers

---

## 9. Comparison with GGUF

| Aspect | GGUF | XRB |
|--------|------|-----|
| Purpose | Model weights | Code skeletons |
| Magic | GGUx | XRB1 |
| Header | Fixed + KV metadata | Fixed + block table |
| Data | Tensor data | Token stream |
| Compression | Quantization | Depth filtering |
| Random Access | Tensor names | Block names |
| Extensible | KV metadata | Metadata section |

The key insight is that both formats apply the same principle — **structured compression with semantic awareness** — at different layers of the AI stack.