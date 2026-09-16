# LUMAX-lite: Token-Efficient Workflow Guide

**Purpose:** Maximize efficiency by leveraging Cognee-indexed documentation and session history instead of full repo indexing. Designed to work alongside TokenLayr for optimal token usage.

**Generated:** May 5, 2026  
**Status:** OPERATIONAL

---

## Quick Reference

| Task | Command / MCP Tool | Tokens Saved |
|------|-------------------|--------------|
| Get current status | `search_lumax_memory(query="current status uptodate")` | ~5000 |
| Find architecture info | `search_lumax_memory(query="service architecture ports")` | ~3000 |
| Load session context | `get_session_injection` | ~2000 |
| Index new docs | `python Scripts/index_docs_cognee.py` | N/A |
| Check Cognee status | `get_cognee_status` | ~500 |

---

## Starting a New Session (Token-Efficient)

### Step 1: Get Session Context (Optional)

If you want previous session context:

```
Use get_session_injection to get previous session context
```

This returns recent conversation turns for continuity.

### Step 2: Get Current Status

Instead of reading files, search Cognee:

```
Use search_lumax_memory with query="current status services running"
```

Returns: Latest status from `uptodate.md` and session history.

### Step 3: Get Architecture Info (If Needed)

```
Use search_lumax_memory with query="service ports architecture"
```

Returns: Relevant architecture chunks without reading full `ARCHITECTURE.md`.

### Step 4: Task-Specific Search

For any task, search first:

```
Use search_lumax_memory with query="your task topic"
```

Examples:
- `"Godot VR scene structure"`
- `"MCP server configuration"`
- `"TTS service setup"`
- `"memory service ChromaDB Kuzu"`

---

## Routine Maintenance Workflow

### Daily: Quick Status Check

```bash
# Check Cognee has latest docs
curl http://localhost:8009/api/v1/stats
```

Or via MCP:
```
Use get_cognee_status
```

### Weekly: Update Documentation Index

After adding new features or docs:

```bash
cd /home/lumba/LUMAX-lite
.venv/memory/bin/python Scripts/index_docs_cognee.py
```

This scans and indexes:
- `Docs/` directory
- `godot_docs/` directory  
- Source code docstrings
- Root documentation files

### After Major Changes: Update Authoritative Files

1. **Update `uptodate.md`**:
   ```
   Use add_to_lumax_memory with role="system" and content="DOCUMENTATION UPDATE: [summary of changes]"
   ```
   Then manually edit `uptodate.md` with new section.

2. **Update `context.md`**:
   Add session entry following existing format:
   ```markdown
   - Session update [YYYY-MM-DD]
   - Task N start [YYYY-MM-DD]
     - [Task description]
       - Investigation 1, [description], [files]
   --> !        * Tried solution 1 [description], [files]
       * User confirmation: solved [YYYY-MM-DD]
   ```

3. **Re-index**:
   ```bash
   .venv/memory/bin/python Scripts/index_docs_cognee.py
   ```

---

## Token-Saving Patterns

### Pattern 1: Search Before Reading

**Instead of:**
```
Read uptodate.md, ARCHITECTURE.md, LUMAX.md
```

**Do:**
```
Use search_lumax_memory with query="current architecture status"
```

**Saves:** ~10,000 tokens per session

### Pattern 2: Incremental Context Loading

**Instead of:**
```
Load entire session history
```

**Do:**
```
Use get_lumax_memory with limit=10
```

**Saves:** ~5,000-20,000 tokens

### Pattern 3: Targeted File Reading

**Instead of:**
```
Read all files in directory
```

**Do:**
```
Use search_lumax_memory with query="specific feature"
Then read only the 1-2 most relevant files returned
```

**Saves:** ~3,000-15,000 tokens

### Pattern 4: Use Cognee for Code Search

**Instead of:**
```
search_files for pattern across repo
```

**Do:**
```
Use search_lumax_memory with query="code pattern description"
```

**Saves:** ~2,000-10,000 tokens (plus Cognee has semantic understanding)

---

## Authoritative Files Checklist

These files should be checked/updated routinely:

| File | When to Check | Update Trigger |
|------|---------------|----------------|
| `uptodate.md` | Every session start | After any feature change |
| `context.md` | Every task completion | After each task |
| `ARCHITECTURE.md` | Weekly | When services change |
| `LUMAX.md` | Weekly | When operational rules change |
| `.clinerules` | Monthly | When workflow changes |
| `gemini.md` | Monthly | When workflow changes |
| `WORKFLOW.md` | Monthly | When new patterns discovered |

---

## MCP Tools Quick Reference

### For Context Loading

| Tool | Use Case | Example |
|------|----------|---------|
| `get_lumax_memory` | Get recent conversations | `{"limit": 10}` |
| `get_session_injection` | Get context for new session | `{}` |
| `search_lumax_memory` | Search by keyword | `{"query": "service ports"}` |

### For Documentation Management

| Tool | Use Case | Example |
|------|----------|---------|
| `add_to_lumax_memory` | Log important info | `{"role": "system", "content": "New feature: X"}` |
| `get_cognee_status` | Check indexed content | `{}` |
| `import_sessions` | Import new sessions | `{"source": "all"}` |

---

## Integration with TokenLayr

TokenLayr compresses context window. This workflow complements it by:

1. **Pre-session:** Use Cognee search to identify relevant docs
2. **During session:** TokenLayr manages what's in context
3. **Post-session:** Export to Cognee for future search

### Recommended TokenLayr Settings

```json
{
  "tokenLayr": {
    "compression": "aggressive",
    "keepInContext": ["current task", "recent turns"],
    "offloadToCognee": ["completed tasks", "reference docs"]
  }
}
```

---

## Example Session Flow

### Session Start
```
1. Use get_session_injection → Get previous context
2. Use search_lumax_memory with query="current status" → Get uptodate info
3. Review returned chunks (typically 3-5, ~500 tokens)
4. Plan task based on current state
```

### During Task
```
1. Need info? Use search_lumax_memory first
2. Only read files if search doesn't have answer
3. Use get_lumax_memory for recent conversation context
```

### Task Completion & Recapitulation
```
1. Update context.md manually with a task log summary detailing the investigation, changes, and solutions.
2. Update uptodate.md to keep the active Spotlight (Section 4) and status report aligned with reality.
```

### Session End (Big Picture Recapitulation)
```
1. Trigger a session Checkpoint (either via CLI `/checkpoint` or automatically when stopping a session). This logs the session's summary to the memory_vault.
2. **Librarian Codebase Mapping Sweep**: The creation of a checkpoint automatically triggers the background Librarian mapping sweep (use_director=True). The Director LLM parses the session summary alongside code changes to:
   - Identify what features were developed/completed.
   - Detect what features were retired or marked [OBSOLETE].
   - Update FEATURE_INVENTORY.md to keep the project's big-picture mapping 100% in sync with development.
3. This recapitulation ensures the next session starts with perfect context and clear roadmap alignment.
```

---

## Emergency: Full Repo Context

If Cognee search isn't enough and you need full context:

```bash
# Read all authoritative files
cat uptodate.md ARCHITECTURE.md LUMAX.md context.md | head -500
```

**Token cost:** ~2,000-5,000 tokens  
**Use sparingly:** Only when search fails

---

## Best Practices

### Do ✅
- Search Cognee before reading files
- Use `get_lumax_memory` with small limits (5-20)
- Index docs after adding new features
- Update `context.md` after each task
- Use `add_to_lumax_memory` for important findings

### Don't ❌
- Read entire files without searching first
- Load full session history unless necessary
- Skip updating `context.md`
- Forget to re-index after doc changes
- Use bulk file reading (max 3 files per turn)

---

## Troubleshooting

### Search Not Returning Results

1. Check Cognee is running:
   ```bash
   curl http://localhost:8009/health
   ```

2. Re-index docs:
   ```bash
   .venv/memory/bin/python Scripts/index_docs_cognee.py
   ```

3. Try different query terms

### Cognee Not Available

Fallback to direct file reading:
```bash
cat uptodate.md | head -100
```

### Memory Not Persisting

Check MCP server is running:
```bash
ps aux | grep cline_mcp
```

Restart if needed:
```bash
.venv/sentry/bin/python backend/Memory/cline_mcp_server.py &
```

---

## Metrics

### Typical Token Savings Per Session

| Activity | Without This Workflow | With This Workflow | Savings |
|----------|----------------------|-------------------|---------|
| Status check | Read 5 files (~10k) | Cognee search (~500) | 9,500 |
| Architecture lookup | Read ARCHITECTURE.md (~5k) | Cognee search (~300) | 4,700 |
| Session context | Full history (~20k) | Recent 10 (~2k) | 18,000 |
| Code search | search_files + reads (~5k) | Cognee search (~500) | 4,500 |

**Total per session:** ~35,000 tokens saved  
**Per day (10 sessions):** ~350,000 tokens saved  
**Per month:** ~10 million tokens saved

---

## See Also

- `Docs/ONBOARDING.md` - New worker guide
- `Docs/QUICK_START.md` - 5-minute setup
- `uptodate.md` - Current status report
- `.clinerules` - Cline operational rules
- `gemini.md` - Gemini AI assistant rules

---

*This workflow document is itself indexed in Cognee for self-referential search.*
*Last updated: May 5, 2026*