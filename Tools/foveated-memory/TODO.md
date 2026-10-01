# Foveated Memory — Context Loss Fix (Completed)

## Root Cause
The `context-compressor.js` used its own **inverted** 1-5 aggression map
(1 = max compression, 5 = almost raw) and **ignored** the unified resolution
level passed from `server.js`. Meanwhile `server.js` used the new unified 0-6
scale where level 0 = 65% baseline floor and 6 = max compression. This
contradiction caused inconsistent compression → models lost connective tissue
and became confused.

Additionally, the foveal window (recent verbatim turns) had **no token cap**,
so a single unguarded huge message could flood the entire context window.

## Fixes Applied

### 1. Unified Resolution Scale (`core/context-compressor.js`)
- Imports `./resolution` (single source of truth)
- `compressContext(messages, sessionId, level)` clamps via `resolution.clampResolution(level)`
- Pulls `{ keepRecent, compressEvery }` from `resolution.COMPRESSOR_PARAMS[lvl]`
  (replaces old inverted `dynamicWindow`/`dynamicCompress` ternaries)
- Default level changed from 3 → 0 (65% baseline floor)

### 2. Server Wiring (`server.js`)
- Requires `./core/resolution`
- `scaleConfigForModel` uses `resolution.RING_MULTIPLIER` / `resolution.LABELS`
  (level 0 still applies baseline ring multiplier 1.0)
- Compression call site resolves `activeResolution` from `LUMAX_PROXY_AGGRESSION`
  + `x-resolution` / `x-compression-level` header override
- `LUMAX_FOVEA0..6_CLOUD_BUDGET` env overrides all supported

### 3. Foveal Window Token Cap + LLM Refinement (`core/context-compressor.js`)
- **NEW** `refineFovealWindow(toKeep)`:
  - Hard-caps verbatim fovea at `FOVEA_MAX_TOKENS` (default 6000)
  - Messages > `FOVEA_REFINE_THRESHOLD_CHARS` (default 400) are routed through
    LM Studio `refineMessageAsync()` — strips "air between words" filler while
    preserving tone, decisions, file refs, facts
  - Always keeps the final message (model sees latest turn)
  - Falls back to verbatim if LLM unreachable

## Verification
- `node --check` passes on context-compressor.js, resolution.js, server.js
- Module loads cleanly (no circular deps)
- `RING_MULTIPLIER`: {0:1, 1:0.85, 2:0.7, 3:0.55, 4:0.4, 5:0.25, 6:0.15}

## Workspace Isolation (confirmed intact)
API-key word → `authManager.resolveToken(token)` → `teamId` → `workspaceId`.
Everyone using the same Bearer token shares the same memory context.
