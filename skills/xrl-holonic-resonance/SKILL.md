---
name: xrl-holonic-resonance
description: Use when demonstrating or applying the foveated-memory + XRL proxy advantage. Captures the 'Holonic resonance' idea — local compression echoes into cloud context, expensive turns are recalled exactly, and the system gets cheaper as it learns the repo.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [xrl, proxy, holonic, foveated-memory, resonance, demo, lumax]
    related_skills: [xrl-proxy-repo-analyzer, xrl-proxy-optimizer, xrl-proxy-debugger]
---

# XRL Holonic Resonance

## Overview

This skill documents the compounding advantage of running LUMAX through the 8200 XRL proxy. The name is intentionally dramatic because the effect is real:

- **Local compression** (LM Studio on 7272) chews old turns into dense checkpoints.
- **Cloud context** (Ollama Cloud) keeps only the high-signal verbatim window.
- **TokenSlayer skeletonization** maps the repo once and reuses the map.
- **Recall** surfaces prior decisions when the same symbol or question reappears.
- **Result:** the more you work in the repo, the less you pay per insight. The system resonates.

## When to Use

- You want to justify or demonstrate the proxy setup to yourself or others
- You are onboarding a new module and want the fastest path to fluency
- You want a repeatable benchmark showing token/cost/time savings
- You want to design a new feature that leverages foveated memory

## When NOT to Use

- The task is a one-off, throwaway query with no repo context to reuse
- You need raw, un-summarized full session history for legal/audit reasons
- The proxy is offline or you are not allowed to route through 8200

## The Five Resonance Principles

1. **Holons are self-similar.** Every conversation turn is a whole (it contains meaning) and a part (it feeds the memory index). The proxy treats it as both.

2. **Memory is active, not archival.** Checkpoints are not cold storage — they are TF-IDF recall targets. Old decisions resurface when a new question vibrates at the same frequency.

3. **Compression is a tax on redundancy, not signal.** The last N verbatim turns and all first-turn system instructions are protected. Only redundant middle history is summarized.

4. **Skeletons are reusable mirrors.** A TokenSlayer level-4 skeleton of a 1,400-line file costs ~600 tokens. Once generated, it can be reused across many analysis queries.

5. **Local work funds cloud work.** LM Studio does the summarization for free. That leaves the cloud budget for reasoning, not bookkeeping.

## Demo Script: The 10x-100x Win

Run this benchmark script to make the resonance concrete.

`scripts/xrl-resonance-benchmark.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
URL=${XRL_PROXY_URL:-http://127.0.0.1:8200}
FILE=${1:-Tools/foveated-memory/server.js}

echo "=== Target: $FILE ==="
RAW_LINES=$(wc -l < "$FILE")
RAW_CHARS=$(wc -c < "$FILE")
echo "Raw file: $RAW_LINES lines, $RAW_CHARS chars"

echo "=== Level 4 skeleton ==="
SKEL=$(curl -s -X POST "$URL/api/skeletonize" \
  -H 'Content-Type: application/json' \
  -d "{\"filepath\":\"$FILE\",\"level\":4}")
SKEL_CHARS=$(echo "$SKEL" | wc -c)
echo "Skeleton chars: $SKEL_CHARS"

echo "=== Reduction ==="
python3 -c "raw=$RAW_CHARS; skel=$SKEL_CHARS; print(f'Saved {(1-skel/raw)*100:.1f}% of tokens ({raw} → {skel})')"

echo "=== Semantic summary ==="
curl -s -X POST "$URL/api/semantic-summary" \
  -H 'Content-Type: application/json' \
  -d "{\"filepath\":\"$FILE\"}" | python -m json.tool
```

Example run:
```bash
bash skills/xrl-proxy/scripts/xrl-resonance-benchmark.sh Tools/foveated-memory/server.js
```

Expected output shape:
```
Raw file: 1420 lines, 48234 chars
Skeleton chars: 1376
Saved 97.1% of tokens (48234 → 1376)
```

## In-Session Commands

### `/xrl resonance`

Prints a one-paragraph manifesto plus current proxy stats.

### `/xrl benchmark <file>`

Runs the benchmark above and returns the reduction percentage.

### `/xrl demo`

A guided, three-step demo:
1. Show raw file size.
2. Show skeleton size.
3. Show recall of a prior related question.

## Application: Code Review with Resonance

When reviewing a PR:
1. Skeletonize every changed file with `/xrl map <file>`.
2. Ask `/xrl recall <feature-name>` to surface prior decisions.
3. Combine the two for a review that costs ~2K tokens instead of ~30K.

This is the practical proof: **the agent remembers the codebase so you don't have to re-feed it every time.**

## Common Pitfalls

1. **Treating the proxy as a black box.** The resonance depends on visible, inspectable endpoints. Use them.
2. **Forgetting workspace scoping.** Each project should pass `X-Workspace: lumax` so recall does not mix unrelated repos.
3. **Over-summarizing.** If recall starts returning garbage, raise `LUMAX_CLOUD_PRESERVE_LAST` or lower the compression ratio.
4. **Measuring only once.** Resonance compounds. Benchmark on day 1, day 7, and day 30 to see the curve.

## Verification Checklist

- [ ] Benchmark script returns > 80% reduction on a real LUMAX file
- [ ] `/api/semantic-summary` returns a coherent paragraph
- [ ] `/api/xrl/recall` returns a relevant prior turn on a second query about the same topic
- [ ] Cloud token spend per meaningful insight trends down across sessions

## Templates

`templates/xrl-resonance-report.md`:
```markdown
# Holonic Resonance Report

## Session
{{SESSION}}

## Benchmarks
{{BENCHMARKS}}

## Observed Resonance
{{RESONANCE}}

## Suggested Rituals
{{RITUALS}}
```
