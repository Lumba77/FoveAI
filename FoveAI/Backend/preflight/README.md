# Backend Preflight (Sentry-coupled)

This module provides lightweight preflight checks that run inside `lumax_ops` (via `autonomous_sentry.py`) before each sentry pulse.

## Why

- Catch cross-service regressions early.
- Keep checks close to backend runtime reality (container network).
- Enable escalation levels with low token/tool overhead.

## Levels

- `light`: project path sanity only (critical baseline).
- `standard`: adds service health checks (`lumax_soul`, `lumax_body`, `lumax_turbochat`).
- `deep`: adds optional loopback bridge probe.

## Playbook JSON (JSON5)

`watchdog_policy.json` and `unstable_features.json` are loaded via `preflight/json_util.py`: with **`json5`** installed you can use **`//` comments**, **`/* */`**, and **trailing commas**. Plain JSON still works. The Docker image installs `json5` with `lumax_unified`.

## Configuration (docker-compose env)

- `LUMAX_PREFLIGHT_LEVEL=light|standard|deep`
- `LUMAX_PREFLIGHT_AUTOHEAL=true|false`
- `LUMAX_PREFLIGHT_BRIDGE_URL` (optional, deep mode)
- `LUMAX_SENTRY_AGENTIC=true|false` (enable model-guided heal decisions)
- `LUMAX_SENTRY_SOLVER_MODE=command|ollama` (`command` recommended for ONNX/TensorRT local runner; default in code is `command` when unset)
- Ollama base URL resolution (in `ollama` mode): `LUMAX_SENTRY_OLLAMA_HOST` (optional, scheme://host:port) → else `LUMAX_SENTRY_SOLVER_URL` with any `/api/...` path stripped (legacy) → else `OLLAMA_HOST` (compose passes the same default as `lumax_soul`).
- `LUMAX_SENTRY_SOLVER_HTTP_MODE=auto|generate|chat` — `auto` tries `/api/generate` then `/api/chat`; failures log without throwing (no noisy 404 spam from `raise_for_status`).
- `LUMAX_SENTRY_SOLVER_URL` — optional legacy override when it includes a full path; prefer base-only env vars above.
- `LUMAX_SENTRY_AGENTIC_PAUSED=true|false` (hard pause during deployment)
- `LUMAX_SENTRY_DEPLOY_LOCK_PATH` (pause when lock file exists)
- `LUMAX_SENTRY_PAUSE_UNTIL_EPOCH` (pause until unix epoch seconds)

## Integration

`Backend/autonomous_sentry.py` runs:
1. `run_preflight(...)`
2. service pulse checks
3. ADB reverse bridge maintenance

This keeps preflight and sentry in one communicative cycle.

## Runtime behavior

- The sentry loop runs continuously while app services are running, so self-heal is realtime by design.
- Safety is enforced by action whitelist in `agentic_solver.py`; unknown actions are ignored.
- During deployment, pause model actions with `LUMAX_SENTRY_AGENTIC_PAUSED=true` or by creating the lock file path.

## Shepherd roaming + Q&A

- Roaming inspection runs periodically and writes inside-view reports to outbox (`container_watchdog_report_latest.json`).
- Roam policy:
  - `LUMAX_SENTRY_ROAM_WHEN_NOT_IN_SERVICE=true`: roam aggressively when unhealthy.
  - `LUMAX_SENTRY_ROAM_WHEN_IN_SERVICE=true`: roam only if loop overhead is under `LUMAX_SENTRY_ROAM_LOOP_BUDGET_MS`.
  - `LUMAX_SENTRY_ROAM_MIN_INTERVAL_SEC`: minimum cadence.
- Ask runtime questions by writing JSON to inbox:
  - path: `${LUMAX_SENTRY_INBOX_DIR}/question_latest.json`
  - payload example: `{ "question": "Why is animation player breaking on startup?" }`
- Answers are written to outbox:
  - `question_answer_latest.json`
  - includes question + investigation response based on internal container/log context.

