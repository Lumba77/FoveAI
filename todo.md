# XRLF Restore + Proxy Integration — Task List

## Goal
Restore the XRLF runtime as a working dev directory and upgrade the main 8200 proxy to natively spin up + route to the XRLF model when selected in the Jenna plugin.

## Status Legend
- [ ] Pending
- [x] In progress / Done
- [~] Blocked / needs decision

---

## Phase 1 — Restore XRLF dev working directory
- [x] Create dev directory `Tools/XRLF 1.0 dev`
- [x] Copy clean published repo base from `Tools/XRLF-1.0-source`
- [x] Copy latest + missing runtime assets from `Archive/xrlf-workdir-aug8` (venv, xrl_encoded, .xrlf models, GGUF, memory_data, outputs, modified source)
- [x] Verify dev dir has complete structure (venv, xrl_encoded, .xrlf, GGUF)
- [x] Verify `.venv` has required deps (llama_cpp, fastapi, uvicorn, tiktoken)
- [x] **Confirm XRLF server boots from dev dir** (manual launch + /health check) — HEALTH OK on 8300

## Phase 2 — Upgrade 8200 proxy for XRLF auto-spin-up
- [x] XRLF server confirmed working (chat completion returns "4")
- [x] Create `Tools/foveated-memory/core/xrlf-spawner.js` (spawn + health-wait + cleanup)
- [x] Modify `Tools/foveated-memory/core/swarm-router.js` to respect explicitly-resolved dedicated providers
- [x] Modify `Tools/foveated-memory/server.js` to detect XRLF model, ensure server running, route to 8402, skip swarm override
- [x] Update `Tools/foveated-memory/memory_data/providers.json` (XRLF → llama_server @ 8402, distinct from lm_studio)

## Phase 3 — Verify
- [x] Start XRLF server, confirm /health + /v1/models respond
- [x] Confirm proxy routes XRLF selection to 8402 (not 7272)
- [x] Test a chat request through the proxy targeting the XRLF model
- [x] **XRLF MODEL RESPONDED "Hello." — end-to-end pipeline confirmed working**
