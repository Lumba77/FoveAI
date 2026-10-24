# Repo Reality-Check Audit — 2026-10-24

Sweep by Devin across logs, ports, service state, memory lanes, and the bench rig.
Severity: 🔴 breaks things · 🟡 degrades/lies · 🟢 worth finishing.

## Service failures (journal)

| unit | failure | notes |
|---|---|---|
| `foveai-creative.service` | 🔴 `oom-kill` | killed by OOM — needs memory cap or smaller model |
| `foveai-residency.service` | 🟡 `timeout` | failed on timeout — check its start budget |
| `foveai-chorus.service` (:8419) | 🟡 inactive/dead | Nova chorus — port collides with ad-hoc bench servers (see below) |
| `foveai-nova.service` (:8416) | 🟡 inactive/dead | Nova Collective bridge — was up earlier, down after unload |
| `foveai-theme.service` (:8415) | 🟡 inactive/dead | Theme API — theme propagation path needs it up |
| `foveai-wake.service` | 🟡 inactive/dead | bouncer — esse tier won't warm-freeze/wake without it |

## Port mismatches

- 🔴 **Dead port references** (referenced in code, nothing listening): `8000, 8002, 8004, 8005, 8006, 8010, 8080, 8106, 8109, 8110, 8113, 8406, 8407, 8415, 8416, 8790–8794, 8888` — matches the ~94 dead refs found in the plumbing audit. SettingsTab health panel likely reports ghosts.
- 🔴 **:8419 collision** — `foveai-chorus` is assigned :8419, but ad-hoc llama-servers get launched there (this session's 1.5B bench). Reserved-port registry needed; bench/test servers should live in a dedicated range (e.g. 8480–8489 except :8489 embedder).
- 🟡 **:8408 chat-template returns empty completions** — `/v1/chat/completions` yields `content:''` while raw `/completion` works. The OpenAI shim (or GGUF chat template) is broken; API clients will see silent empty answers.
- 🟡 **:8489 embedder is the only sidecar port** — fine, but `xrlf_embedder` startup is lazy; first-call latency ~450ms documented, acceptable.

## Model/export defects

- 🔴 **GGUF "Merged" export defect (systemic):** `qwen3.5-4b-core.gguf` and `xrlf_coder_mtp_q5_k_m.gguf` both declare `block_count=33` + `nextn_predict_layers=1` but ship only 32 block tensors and zero nextn tensors — llama.cpp refuses to load. **Fixed in-place this session** (metadata patch 33→32, nextn→0; backup `.bak-meta`). The *exporter* needs the fix — every future Merged export inherits this.
- 🟡 **4B MTP coder**: MTP speculative layer physically absent — runs as plain 4B; fine for capability, loses MTP decode speed.

## Memory / XRL layer

- 🟢 `POST /v1/memory/reindex` — built & verified (~1,300 docs backfilled to MiniLM vectors). All workspaces `remaining: 0`.
- 🟢 Curator v2 — `Tools/memory_curator.py` (LLM distill + extractive fallback + Certifier gate + domains + Google-CSE/DDG). Wired as MCP tools `curate_memory`, `ingest_url`, `web_research`.
- 🟡 **`web_research` DDG parser is regex-fragile** — works, but brittle; swap to CSE when `GOOGLE_CSE_ID`/`GOOGLE_API_KEY` set.
- 🟢 HUD v2 — timestamp/CTX gauge/FOCUS/prior-history(semantic, 0.35-gated)/job-spec/skills slots live in `membrane-bridge.js` + `server.js`.
- 🟢 `foveai_mcp_server.py` — 49 tools; XRL lanes + curator + spawn_agent + run_harden verified. Registered `foveai-memory-xrl` in `mcp-config.json` (repo `mcp-config.json` still has stale Windows lumax entry — worth refreshing).
- 🟢 `foveai --esse` patched to self-provision `foveai-esse.target`.

## Guardian (Taskbar)

- 🟢 FIXED: `kill_zombie_unity_workers` now refuses to run while a live Unity editor/build exists (was the plausible mid-build killer — pkill on `UnityShaderCompiler`).
- 🟢 FIXED: `kill_runaway_git_processes` bar raised 250MB → 750MB.
- 🟡 `audit_and_alert` is notify-only (correct); `free RAM` menu kills `llama-server` by name — will kill ad-hoc/bench servers too; consider narrowing to unit-owned pids.

## Benchmark findings (xrl_bench.py — raw + gated + bearer sets)

| model | memory base→aug | repo | generic | bearer (synthesis) |
|---|---|---|---|---|
| Qwen3.5-9B :8408 | .29→1.00 | .33→.42 | 1.0→.89 | not run |
| Qwen3.5-4B :8418 | .29→**1.00** | .33→.58 | 1.0→1.0 (gated) | **1.0/1.0/1.0/.75** — rejects injected lies |
| XRLF router 1.5B :8419 | .07→.46 | 0→.25 | .89→.89 | 1.0/0/.17/.5 — **parrots wrong member facts** |
| Nova Collective :8416 | ~0 (idiom mismatch) | .17 | .22 | n/a — needs judge pass |

- 🔑 **Production fix landed:** unconditional memory injection measurably derails small models (4B generic 1.0→0.44) — HUD prior-history injection now gated at vector score ≥0.35.
- 🔑 **Bearer conclusion:** router-class 1.5B is NOT spokespipe material (parrots falsehoods); 4B filters injected lies nearly perfectly. Bearer should be ≥4B-class or a purpose-trained ~2B.

## Unfinished worth finishing

1. 🔴 Fix the GGUF Merged exporter (root cause of the 4B load failure) — wherever `Xrlf_Coder_Mtp_Merged` was produced.
2. 🔴 Port-registry/consistency pass — dead refs make the health panel lie; reserve a bench range.
3. 🟡 `:8408` chat-template shim repair (OpenAI-compat clients get empty answers).
4. 🟡 `foveai-creative` OOM — bound its VRAM/RAM or downsize.
5. 🟡 Skills index → HUD `skillHints` slot (wired, empty).
6. 🟡 `foveai-curate.timer` — scheduled curator sweeps of docs/logs.
7. 🟡 Repo `mcp-config.json` — stale Windows lumax entry; refresh for Linux clients.
8. 🟡 Judge calibration for bench — different-family grader (cloud/Devin) not Qwen-on-Qwen.
9. 🟢 Alice + Jen two-character avatars — `SchoolGirl.vrm` imported; second container + singleton-binding separation in `AutoSceneBuilder`/`AdoptAvatar` remains.
10. 🟢 XRL `expand` cap — exists in grants, not exposed in the client.

## Fixed this session

semantic backfill · curator v2 + Certifier · HUD v2 + 0.35 injection gate · MCP 49 tools + registration · `foveai --esse` self-provision · guardian zombie-kill guard + git bar · 4B GGUF metadata surgery · bearer eval built into `xrl_bench.py`
