# TokenSlayer Fork Experiment — Handover Document

**Date:** 2026-07-11  
**Author:** Papillon  
**Status:** Phase 14 (XRL Protocol) — registration bug resolved

---

## 1. What This Project Is

A fork experiment extending the **TokenSlayer** code-compression ecosystem with:
- **XRL Protocol** (eXpandable Reference Links) — standardized URI format for referencing code locations
- **SummarizerCompressor** — learned compression via local GGUF models (Granite-3.3-2B, etc.)
- **Proxy server** (port 8103) — FastAPI server that skeletonizes code, manages atomic cache, provides expansion endpoints

---

## 2. What's Complete (Phases 1-13)

### Core Infrastructure
- ✅ TokenSlayer MCP server (6 tools) wired correctly — registered in `mcp-config.json`
- ✅ Proxy server at `Backend/Cognition/tokenslayer_proxy_server.py` — port 8103, all endpoints confirmed working
- ✅ Standalone CLI at `Forge/scratch/TokenSlayer/standalone/tokenslayer.js` — levels 0-5, tier shortcuts
- ✅ `.tokenslayer-ignore` optimized, `repo-skeleton.md` regenerated

### SummarizerCompressor (Phases 10-13)
- ✅ `Backend/Cognition/summarizer_compressor.py` — 394 lines, `SummarizerCompressor` class
- ✅ 6 fallback model paths (Granite-3.3-2B, Mixture-Summarizer, Qwen3-0.6B, slim-summary, MedGemma, TQL-Coder)
- ✅ `n_ctx=4096` bug fixed (was hardcoded, now auto-detects from model metadata)
- ✅ Integrated into `devour_skeletons()` with `--use-learned` flag
- ✅ Production integration verified — proxy already has full SummarizerCompressor wiring
- ✅ 7 models evaluated: Granite-3.3-2B (best), Mixture-Summarizer (good), MedGemma (❌), TQL-Coder (❌ thinking model, impractical)
- ✅ Full evaluation docs in `Plans/summarizer-model.md`

---

## 3. What Was Resolved — Phase 14: XRL Protocol

### What XRL Protocol Is
A standardized URI format `xrl://lumax/{filepath}:{line}:{hash6}` for referencing code locations that can be expanded on-demand. Defined in [`Plans/xrl-protocol.md`](Plans/xrl-protocol.md).

### What's Been Built
- ✅ [`Plans/xrl-protocol.md`](Plans/xrl-protocol.md) — comprehensive spec (198 lines)
- ✅ XRL functions in proxy server: `generate_xrl()`, `parse_xrl()`, `register_xrl_in_cache()`
- ✅ `_build_skeleton_block()` updated to include XRL URIs in skeleton headers
- ✅ XRL API endpoints: `POST /api/xrl/expand`, `POST /api/xrl/resolve`, `GET /api/xrl/status`, `POST /api/xrl/prune`
- ✅ [`test_xrl_workflow.py`](test_xrl_workflow.py) — comprehensive test script

### The Registration Bug — RESOLVED

**Symptoms (before fix):**
- `/api/skeletonize` works — returns skeleton with 94% reduction
- `/api/xrl/status` always shows `total_cache_entries: 0, xrl_entries: 0`
- XRL entries are never written to `atomic_cache.json`

**Root Cause:**
The fix WAS in the source code at line 570 (`skeletonize_file_content()`) and line 383 (`_build_skeleton_block()`). The code correctly:
1. Reads file content first
2. Tries CLI for skeleton text
3. Always calls `_build_skeleton_block()` with `skeleton_override` parameter

**BUT the running proxy was the OLD version** — started before the fix was applied. The old proxy (PID 12424) was running in Terminal 1 (VS Code foreground), so `taskkill` by window title didn't match it.

**Resolution (2026-07-11):**
1. Old proxy (PID 12424) was already dead when checked — port 8103 was free
2. Started new proxy (PID 26980) with the fixed code
3. Ran `test_xrl_workflow.py` — **ALL 6 STEPS PASSED**
4. Verified: `/api/xrl/status` shows `xrl_entries: 1` after skeletonization
5. Also fixed `datetime.utcnow()` deprecation warnings (6 calls across 2 files)
6. Restarted proxy to pick up `utcnow()` fix — health check confirmed `200 OK` with `atomic_cache_size: 1`

**Key insight:** This was **never a code bug** — the fix was already in the source file. The issue was that the running process was the pre-fix version. The proxy runs as a foreground process in VS Code's Terminal 1, not as a background system process, so it doesn't appear in Task Manager.

### What's Still Left for Phase 14
- [ ] Update `_extract_skeleton()` to register each extracted symbol in atomic cache with XRL URIs
- [ ] Wire MCP `expand_node` to proxy `/api/xrl/expand`
- [ ] Add `resolve_xrl` MCP tool
- [ ] Add startup auto-prune for entries >7 days old
- [ ] Update [`Plans/xrl-protocol.md`](Plans/xrl-protocol.md) with implementation status
- [ ] Integrate new XRS/XRB work from [`Tools/lumax-xrl/xrs/`](Tools/lumax-xrl/xrs/) (XRS CLI wrapper, XRB binary format spec, XRL prompt template)

---

## 4. Key Files Reference

| File | Purpose | Key Lines |
|------|---------|-----------|
| `Backend/Cognition/tokenslayer_proxy_server.py` | Main proxy server (1068+ lines) | L383: `_build_skeleton_block()`, L570: `skeletonize_file_content()`, L104-161: XRL functions |
| `Backend/Cognition/summarizer_compressor.py` | Learned compression via GGUF (394 lines) | `SummarizerCompressor.compress()`, 6 fallback paths |
| `Plans/xrl-protocol.md` | XRL Protocol v1.0 spec (198 lines) | URI format, API endpoints, migration path |
| `Plans/summarizer-model.md` | Model evaluation docs | All 7 model results, benchmarks, n_ctx=4096 bug fix |
| `test_xrl_workflow.py` | XRL integration test (93 lines) | Tests skeletonize → XRL status → expand → resolve |
| `Forge/scratch/TokenSlayer/standalone/tokenslayer.js` | Standalone CLI | Levels 0-5, tier shortcuts |

---

## 5. What's Left (Phases 14-15)

### Phase 14: XRL Protocol (registration bug resolved)
- [x] Fix: kill old proxy, restart with new code, verify XRL entries register — **DONE (2026-07-11)**
- [ ] Update `_extract_skeleton()` to register each extracted symbol in atomic cache with XRL URIs
- [ ] Wire MCP `expand_node` to proxy `/api/xrl/expand`
- [ ] Add `resolve_xrl` MCP tool
- [ ] Add startup auto-prune for entries >7 days old
- [ ] Update [`Plans/xrl-protocol.md`](Plans/xrl-protocol.md) with implementation status
- [ ] Integrate new XRS/XRB work from [`Tools/lumax-xrl/xrs/`](Tools/lumax-xrl/xrs/) (XRS CLI wrapper, XRB binary format spec, XRL prompt template)

### Phase 15: Fine-Tuning (not started)
- [ ] LoRA fine-tune Granite-3.3-2B on full→skeleton pairs
- [ ] Only if prompt-only approach plateaus

---

## 6. Quick Start Commands

```bash
# Start proxy (runs in VS Code Terminal 1 — foreground process)
python Backend/Cognition/tokenslayer_proxy_server.py

# Test XRL workflow
python test_xrl_workflow.py

# Check proxy health
curl http://127.0.0.1:8103/health

# Skeletonize a file
curl -X POST http://127.0.0.1:8103/api/skeletonize -H "Content-Type: application/json" -d "{\"filepath\": \"Backend/Cognition/soul_core.py\", \"level\": 3}"

# Check XRL status
curl http://127.0.0.1:8103/api/xrl/status

# Standalone CLI demo
node Forge/scratch/TokenSlayer/standalone/tokenslayer.js Backend/Cognition/soul_core.py --level 4
node Forge/scratch/TokenSlayer/standalone/tokenslayer.js Backend/Cognition/soul_core.py --level 5
```

---

## 7. Architecture Notes

- **Windows-Native** (no Docker, no WSL2)
- **Proxy port:** 8103
- **Atomic cache:** `atomic_cache.json` (in-memory + JSON file)
- **Raw nodes:** `.gemini/cache/raw_nodes/`
- **MCP server:** Node.js at `Forge/scratch/TokenSlayer/mcp-server/build/index.js`
- **Python venv:** `.venv/` in project root
- **Key models:** DeepSeek V4 (cloud), Qwen3.5-4B (local middleman via LM Studio)