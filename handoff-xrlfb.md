# Handoff — XRLF/XRLB "Motherboard" (1000-Model TSD Legion)

**Written:** 2026-10-16 · **Source session:** 2026-10-16, 18:18–20:48 (conversation `667b8423-6053-476d-853f-bb9f88f5c2c5`)
**Full archive (English):** `/mnt/foveai/sessions/xrlfb-1000-model-architecture_2026-10-16/` on `sdb2` (`foveai-ssd`)

## One-paragraph summary
One shared nano trunk plus many tiny `.xrlb` "pentahedron" seeds that are folded on demand from disk. About 1,000 virtual specialists cost roughly one core model in VRAM; the rest sit on the SSD. XRLF = model **F**ile, XRL = protocol, XRLB = **B**and of models. The topology is 1 core, 10 dirigents, 4 heads and 16 arms, with the "battery beds" as the bundles.

## State at end of session
**Done / wired**
- Motherboard tree on `sdb2`: `/mnt/foveai/motherboard/` — `00_core_500m`, `01_dirigents_10`, `02_heads_4`, `03_arms_16`, `04_battery_beds` (10 `.xrlb` beds + `epigenetic_crystals`), `motherboard_manifest.json`.
- Runtime/code: `runtime/xrl_swarm.py`, `runtime/xrl_dense_format.py`, `Backend/Creativity/tandem.py` (`--legion` countermodel), `Backend/Creativity/nim_juggle.py`, `runtime/benchmark_tsd_legion.py`, `runtime/repo_youth_engine.py` + skill `.agents/skills/repo-fountain-of-youth/`.
- HTTP/UI: `/api/tsd/{seek-and-destroy,dream-2036,legion,rejuvenate,benchmark}` (`api/server.py`, `foveated-memory/server.js`, Multigate `vite.config.ts` proxy), deck `foveated-memory/public/tsd_blaster.html` (`:5177`, `:8414`), tray submenu in `FoveAI_Taskbar_Linux.py`. Chat modes `juggle`/`tandem`/`legion` route through `tandem.py --legion`.
- Design note: `Docs/XRL_HIVE_MIND.md` (still labelled "concept note").

**Not done / open**
1. **Unverified numbers.** 50x size/power/speed, ~0.48 ms cell wake-up and ~42 ms legion endpoint are the session's own benchmark output. Re-run `runtime/benchmark_tsd_legion.py` before relying on them.
2. **User has not felt it yet.** Daniel has not tried `legion`/`tandem` in Multigate (`:5177`) ("still a legion virgin").
3. **PC micro-wheels, unfinished.** The last request was to make the PC feel fast. Findings so far: a stuck background `git add -A` thrashing the spinning 1 TB HDD (~40 MB/s), and ~6 GB swapped to `/swapfile3` on that HDD while ~11 GB RAM was free. Parent timer/service for `git add -A` was still being traced. Draft: `runtime/pc_micro_wheels.py` (not validated).
4. **Fountain of Youth** (`repo_youth_engine.py`) exists but is not scheduled.

## How to resume
```bash
cd /home/lumba/FoveAI
# 1) re-verify the claims
PYTHONPATH=. .venv/bin/python runtime/benchmark_tsd_legion.py
# 2) try the countermodel
PYTHONPATH=. .venv/bin/python Backend/Creativity/tandem.py --legion "your question"
# 3) UI deck
xdg-open http://127.0.0.1:5177/tsd_blaster.html
# 4) read the story
less /mnt/foveai/sessions/xrlfb-1000-model-architecture_2026-10-16/SESSION.md
```

## Where it is logged
`context.md` (session entry), `uptodate.md` (status), `ARCHITECTURE.md` (architecture section), `Plans.md` ("Next Phase: XRLF/XRLB Motherboard"). Backups of the originals before this edit: `/tmp/log_backup_20261016/` (volatile).

## Caveats
- `context.md` is in `.gitignore`, so its entry is not in `git diff`.
- `code_snapshot/` in the archive is a point-in-time copy; the repo is the source of truth.
- Storage rule: large artifacts go on `sdb2` (`/mnt`) or `sda2` (`/opt`), never `/home/lumba` (~18 GB free).
- In the repo, `handoff.md` is a symlink to `OPEN-XRL-SPEC.md` (a different document). This handoff is saved in the repo as `handoff-xrlfb.md`.
