# TODO — XRLF Model Routing Fix (Jenna VS Code)

## Goal
Make the Jenna VS Code plugin (via foveated proxy :8200) route XRLF model
requests to the XRLF runtime (:8300) instead of falling back to LM Studio (:7272).

## Steps
- [x] 1. Diagnose root cause (swarm router clobbers 8300 baseUrl; xrlf-spawner not wired in)
- [ ] 2. Wire `xrlf-spawner.js` into `server.js` (import + routing)
- [ ] 3. Skip swarm-router override for XRLF models (keep 8300 baseUrl)
- [ ] 4. Add `/api/xrlf/status` endpoint for plugin visibility
- [ ] 5. Restart proxy (:8200) and verify XRLF request routes to :8300
- [ ] 6. Verify Jenna plugin "Switch Model" -> xrlf-qwen4b-concise talks to XRLF
