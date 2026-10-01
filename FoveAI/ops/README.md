# Ops (operations)

Deployment and **operational** assets for the Lumax stack (not application “Mind/Body” code).

- **`playbooks/`** — watchdog policy, unstable-features registry, preflight level hints, transplant progress notes, and related JSON/env examples consumed by `lumax_ops` / sentry (`LUMAX_SENTRY_*_PATH` in `docker-compose.yml`).

Default container paths use `/app/ops/playbooks/...` (repo root bind-mount is `.` → `/app`).
