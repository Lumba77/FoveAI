---
name: xrl-proxy-optimizer
description: Use when suggesting code optimizations, refactors, or performance fixes in the LUMAX codebase. Leverages the 8200 XRL proxy to skeletonize hot paths, measure token cost of context windows, and propose Holonic, low-blast-radius changes.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [xrl, proxy, optimization, refactoring, performance, lumax]
    related_skills: [xrl-proxy-repo-analyzer, xrl-proxy-debugger]
---

# XRL Proxy Optimizer

## Overview

This skill turns the XRL proxy into an optimization coprocessor. Instead of guessing where the fat is, it:
1. Skeletonizes the candidate file(s) to find hot loops, heavy functions, and duplicated patterns.
2. Uses the proxy's tier-info endpoint to pick the right compression level for the target model.
3. Generates a ranked list of optimizations with token-cost and blast-radius annotations.

Best applied to: cloud token budgets, response latency, memory pressure, and context-window hygiene.

## When to Use

- A module feels "too heavy" (slow responses, large diffs, high token burn)
- You want to reduce cloud context usage without losing signal
- Refactoring a service and need the smallest change that yields the biggest win
- Comparing two implementations for token/performance tradeoffs

## When NOT to Use

- The code is already skeletonized and you know the exact line to edit
- The bottleneck is external (network, GPU, database) — profile those first
- You have not run the existing tests; optimization without regression guardrails is gambling

## Quick Start

### 1. Snapshot current token profile

```bash
# Get model-specific tier recommendation
curl -s "http://127.0.0.1:8200/api/tier-info?model=gemini-1.5-pro&mode=cloud"

# Compress a sample conversation context
curl -s -X POST http://127.0.0.1:8200/api/compress \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Hello"},{"role":"assistant","content":"Hi"}]}' | python -m json.tool
```

### 2. Skeletonize the hot file

```bash
curl -s -X POST http://127.0.0.1:8200/api/skeletonize \
  -H 'Content-Type: application/json' \
  -d '{"filepath":"Tools/foveated-memory/server.js","level":2}' | python -m json.tool
```

### 3. Rank optimizations

Use the template at `templates/xrl-optimization-report.md`.

## Hermes In-Session Commands

### `/xrl optimize <file-or-dir>`

```
/xrl optimize Tools/foveated-memory/core
```

Returns:
- Estimated current token cost of the target
- Top 3-5 low-blast-radius wins
- Suggested compression level for the model in use
- Diff sketch (pseudocode) for each proposal

### `/xrl smell <file>`

Detects common anti-patterns:
- duplicated string literals
- oversized functions with no early returns
- nested loops over message arrays
- JSON.parse/stringify hot paths
- unbounded `Array.prototype.filter` in loops

### `/xrl compare <fileA> <fileB>`

Compare two implementations for token/perf characteristics.

## Demo: Token-Budget Optimization

**Scenario:** `Tools/foveated-memory/server.js` sends full context upstream because the cap logic was not model-aware.

**XRL move:**
```bash
curl -s "http://127.0.0.1:8200/api/tier-info?model=gemini-1.5-pro&mode=cloud"
# → recommended_tier: micro (level 4/5)

# Apply micro skeletonization to system-prompt history
# Cap derived from context_window (1M → 32768, 150K → 16384)
```

**Result:** upstream context drops from ~70K to 16-32K for large-context models while preserving decision-critical turns via `LUMAX_CLOUD_PRESERVE_LAST=10`.

## Common Pitfalls

1. **Optimizing without measuring.** Always get the tier-info / skeletonize baseline first.
2. **Over-compressing human-readable logs.** Summaries can strip stack traces and exact error messages. Keep raw output for the last N turns.
3. **Changing multiple variables at once.** Tune either cap or compression level, not both, so you know what helped.
4. **Forgetting `.env` override.** An explicit `LUMAX_CLOUD_MAX_TOKENS_CAP` disables the capacity-based auto logic.

## Verification Checklist

- [ ] Baseline token cost captured via tier-info or compress endpoint
- [ ] Skeletonization reveals the actual hot symbols
- [ ] Each proposal includes blast-radius estimate
- [ ] Tests or lint passes after applying the chosen change
- [ ] `/health` shows expected `cloud_cap` after restart

## Templates

`templates/xrl-optimization-report.md`:
```markdown
# XRL Optimization Report: {{TARGET}}

## Baseline
- File(s): {{TARGET}}
- Model: {{MODEL}}
- Recommended tier: {{TIER}}
- Estimated token cost: {{TOKENS}}

## Findings
{{FINDINGS}}

## Proposed Wins
| # | Change | Blast Radius | Token Save | Confidence |
|---|--------|--------------|------------|------------|
{{WINS_TABLE}}

## Diff Sketches
{{DIFF_SKETCHES}}

## Next Step
{{RECOMMENDATION}}
```
