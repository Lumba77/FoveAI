---
name: xrl-proxy-debugger
description: Use when debugging LUMAX runtime issues through the 8200 XRL proxy. Combines proxy health checks, expand-node inspection, and holonic memory recall to zero in on root causes faster than grepping logs.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [xrl, proxy, debugging, troubleshooting, holonic, lumax]
    related_skills: [xrl-proxy-repo-analyzer, xrl-proxy-optimizer]
---

# XRL Proxy Debugger

## Overview

When something breaks in the LUMAX pipeline — proxy returning weird caps, context disappearing, model routing to the wrong endpoint — this skill routes the diagnostic work through the XRL proxy first. The proxy exposes its own state (`/health`), its compression decisions (`/api/expand`, `/api/compress`), and its memory checkpoints (`/api/xrl/recall`), so you can debug the system with the system.

## When to Use

- Proxy `/health` reports unexpected `cloud_cap` or `mode`
- Context feels "too short" or "too long" in chat
- A request is hitting the wrong upstream
- You need to inspect what the proxy actually sent upstream
- You suspect a checkpoint swallowed important history

## When NOT to Use

- The issue is clearly in the LUMAX application code and unrelated to routing/proxying
- You have a clean stack trace pointing to one line
- The proxy is not part of the failing call path

## Quick Start

### 1. Read proxy state

```bash
curl -s http://127.0.0.1:8200/health | python -m json.tool
```

### 2. Inspect a compressed checkpoint

```bash
curl -s -X POST http://127.0.0.1:8200/api/expand \
  -H 'Content-Type: application/json' \
  -d '{"filepath":"Tools/foveated-memory/server.js","line":97,"context":3}' | python -m json.tool
```

### 3. Recall recent memory

```bash
curl -s -X POST http://127.0.0.1:8200/api/xrl/recall \
  -H 'Content-Type: application/json' \
  -d '{"workspace":"default","query":"proxy cloud cap","limit":5}' | python -m json.tool
```

## Hermes In-Session Commands

### `/xrl why [symptom]`

Runs a structured diagnostic:
1. `/health`
2. `.env` overrides for `LUMAX_CLOUD_*`
3. Check active listeners (`netstat -ano | grep -E '8200|8103|7272'`)
4. Return a concise diagnosis

### `/xrl expand <file:line> [context=3]`

Expand a pruned `/* EXPAND:nodeId */` tag or a raw file:line reference back to full source.

```
/xrl expand Tools/foveated-memory/server.js:97
```

### `/xrl recall <query>`

Query the foveated memory workspace for relevant prior turns.

```
/xrl recall why did context drop to zero
```

## Demo: Holonic Resonance in Action

**Symptom:** Chat context suddenly collapsed to almost nothing.

**Classic debug:** manually scroll through 50 turns of JSON logs.

**XRL debug:**
```bash
curl -s http://127.0.0.1:8200/health
# cloud_cap looks OK, preserve_last=10

curl -s -X POST http://127.0.0.1:8200/api/xrl/recall \
  -d '{"workspace":"default","query":"context compressor summary max_tokens","limit":5}'
# surfaces the recent change to summary max_tokens 60→280
```

**Result:** root cause found in two calls instead of twenty.

## Common Pitfalls

1. **Forgetting workspace isolation.** Recall queries are scoped to `X-Workspace`. The default is `default`; use `lumax` if you started the proxy with that workspace.
2. **Trusting stale PIDs.** Windows `node.exe` processes can linger. Use `taskkill /F /IM node.exe` then relaunch if the proxy behaves oddly.
3. **Not checking `.env` overrides.** `LUMAX_CLOUD_MAX_TOKENS_CAP` disables auto-capacity logic. `LUMAX_COGNITIVE_MODE` switches cloud/local routing.
4. **Confusing 8103 and 8200.** 8103 is the legacy Python proxy; 8200 is the unified Node proxy. Verify which one is actually listening.

## Verification Checklist

- [ ] `/health` returns expected mode, cap, preserve count
- [ ] Active ports match intended routing
- [ ] `.env` overrides inspected
- [ ] Recall/expand endpoints surface the relevant facts
- [ ] Diagnosis links a symptom to a specific file:line or config value

## Templates

`templates/xrl-debug-report.md`:
```markdown
# XRL Debug Report

## Symptom
{{SYMPTOM}}

## Proxy State
{{HEALTH_JSON}}

## Active Listeners
{{PORT_STATUS}}

## Relevant Recall
{{RECALL_SNIPPETS}}

## Root Cause
{{ROOT_CAUSE}}

## Fix
{{FIX}}

## Verification Command
{{VERIFY}}
```
