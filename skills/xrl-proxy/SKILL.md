---
name: xrl-proxy-repo-analyzer
description: Use when analyzing a LUMAX repo through the 8200 XRL proxy. Triggers TokenSlayer skeletonization, semantic recall, and dependency-chain analysis to deliver a compact, high-signal code map in seconds instead of minutes.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [xrl, proxy, analysis, tokenslayer, repo-inspection, lumax]
    related_skills: [xrl-proxy-optimizer, xrl-proxy-debugger, hermes-agent]
---

# XRL Proxy Repo Analyzer

## Overview

The unified proxy on `127.0.0.1:8200` is more than a traffic forwarder — it is a foveated memory + TokenSlayer analysis node. This skill treats the proxy as a repo-analysis coprocessor: instead of reading files one at a time and burning cloud tokens, it asks the proxy for structural skeletons, semantic summaries, and dependency chains, then reasons over the compressed output.

Result: a full repo map in under 30 seconds, using a fraction of the tokens a naive crawl would cost.

## When to Use

- Onboarding to an unfamiliar part of LUMAX
- Planning a change across multiple services
- Refactoring a module and need to know its blast radius
- Searching for where a symbol is defined or consumed
- Wanting a one-page "mind map" of a directory or file tree

## When NOT to Use

- You already know the exact file and line range — just read it directly
- The repo is tiny (< 5 files); overhead is not worth it
- The proxy on `8200` is not running

## Quick Start

### 1. Confirm proxy is alive

```bash
curl -s http://127.0.0.1:8200/health | python -m json.tool
```

Expected:
```json
{
  "status": "ONLINE",
  "service": "FoveatedMemory/TokenSlayer Unified Proxy v3",
  "cloud_cap": "auto",
  "preserve_last": 10
}
```

### 2. Skeletonize a file or directory

```bash
# Level 4 = symbol table only (~95% token reduction)
curl -s -X POST http://127.0.0.1:8200/api/skeletonize \
  -H 'Content-Type: application/json' \
  -d '{"filepath":"Backend/Cognition/soul_core.py","level":4}' | python -m json.tool

# Whole directory at level 3 (imports + signatures)
curl -s -X POST http://127.0.0.1:8200/api/skeletonize \
  -H 'Content-Type: application/json' \
  -d '{"filepath":"Tools/foveated-memory/core","level":3}' | python -m json.tool
```

### 3. Follow a dependency chain

```bash
# Walk imports from a seed file up to depth 3
curl -s -X POST http://127.0.0.1:8200/api/xrl/dependency-chain \
  -H 'Content-Type: application/json' \
  -d '{"seed":"Tools/foveated-memory/server.js","depth":3}' | python -m json.tool
```

### 4. Semantic summary

```bash
curl -s -X POST http://127.0.0.1:8200/api/semantic-summary \
  -H 'Content-Type: application/json' \
  -d '{"filepath":"Tools/foveated-memory/core/ring-builder.js"}' | python -m json.tool
```

## Hermes In-Session Commands

### `/xrl map <path-or-file>`

Produces a compact mind map of the target.

```
/xrl map Backend/Cognition
```

Workflow:
1. Calls `POST /api/skeletonize` at level 3.
2. If result is a directory, collects top-level file skeletons.
3. Summarizes: service boundary, public API surface, key functions, known risks.

### `/xrl chain <seed-file> [depth=3]`

Shows how a module connects to the rest of the codebase.

```
/xrl chain Tools/foveated-memory/server.js 3
```

### `/xrl find <symbol>`

Finds definition and usages by combining proxy skeletonization with a local ripgrep pass.

```
/xrl find enforceCloudBudget
```

## Demo: The 10x Win

**Naive approach:** reading `Tools/foveated-memory/server.js` full file ≈ 1,400 lines ≈ ~18K tokens.

**XRL approach:**
```bash
curl -s -X POST http://127.0.0.1:8200/api/skeletonize \
  -d '{"filepath":"Tools/foveated-memory/server.js","level":4}'
```
Output ≈ 600 tokens.

That is a **97% token reduction** with all function signatures, imports, and decorators preserved. The human/LLM can then `expand_node` or `view_file` the exact body that matters.

## Common Pitfalls

1. **Proxy not running.** Always check `/health` first. If it is down, restart with `taskkill /F /IM node.exe` then `node Tools/foveated-memory/server.js`.

2. **Wrong model in request.** The proxy derives the cloud cap from `body.model`. If you omit it, the cap falls back to the default — still safe, but not capacity-aware.

3. **Passing a directory to `level:4`.** Directory skeletonization applies the level file-by-file, but level 4 may hide too much context for cross-file planning. Use level 3 for directories.

4. **Ignoring the workspace header.** Pass `X-Workspace: lumax` (or set it in `.env`) if you want isolated memory databases per project.

## Verification Checklist

- [ ] `/health` returns `status: ONLINE`
- [ ] `/api/skeletonize` returns a compact structural skeleton
- [ ] `/api/xrl/dependency-chain` follows at least one import link
- [ ] `/api/semantic-summary` returns a human-readable paragraph
- [ ] Token reduction is > 80% vs reading the same files raw

## Templates

`templates/xrl-skeletonize.sh`:
```bash
#!/usr/bin/env bash
FILE=${1:-Backend/Cognition/soul_core.py}
LEVEL=${2:-4}
curl -s -X POST http://127.0.0.1:8200/api/skeletonize \
  -H 'Content-Type: application/json' \
  -d "{\"filepath\":\"$FILE\",\"level\":$LEVEL}" | python -m json.tool
```

`templates/xrl-map-report.md`:
```markdown
# XRL Repo Map: {{TARGET}}

## Boundary
{{BOUNDARY}}

## Public Surface
{{SURFACE}}

## Key Functions / Classes
{{KEY_SYMBOLS}}

## Risks
{{RISKS}}

## Next Steps
{{NEXT_STEPS}}
```
