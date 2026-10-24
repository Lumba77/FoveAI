# Antigravity XRL Agent Contract

Antigravity is a provisioned Open XRL agent on this host.

- **Agent home**: `/agent/antigravity` (0700, linux user `antigravity`, own ed25519 keys — sudo-only)
- **Contract**: `/agent/antigravity/XRL_CONTRACT.json`
- **Grant**: `Backend/app/IPC/xrl_grants.json` → `antigravity` (participant, caps: recall/deposit/expand)
- **Key access**: `lumba` reads `/agent/antigravity/.ssh/id_ed25519` via file ACL
  (`setfacl` — traverse on dirs, read on the key file only). Identity stays
  bound to the agent's own SSH keys; no duplicate credentials.
- **Workspace memory**: `foveated-memory/memory_data/antigravity`

## Using the memory lane

`Tools/xrl_agent_client.py` supports specifying agent via `--model` (or defaults to the agent's context):

```bash
.venv/bin/python Tools/xrl_agent_client.py --model antigravity deposit "session summary" tag1 tag2
.venv/bin/python Tools/xrl_agent_client.py --model antigravity recall 5
```

Deposit notable session outcomes (fixes, architectural findings, user prefs)
so future sessions can recall them.

## Lanes — private vs collective

- **PRIVATE** `xrl.memory` deposit/recall — verified handshake required,
  units stored per-model in `memory_data/antigravity`. Agent-only context.
- **COLLECTIVE** `xrl.telepathy` — long-form shared ledger
  (`_telepathy_buffer`, 2000-entry ring) broadcast to `/ws/telepathy`
  listeners. For findings other agents/models should pick up.
- **COLLECTIVE** resonance bus — `POST :8400/api/resonance/ingest`
  (units array) appends to the shared resonance file; `/telepathy`
  variant tags the lane. For state/presence notes, no WS needed.

Client wraps all three:

```bash
python3 Tools/xrl_agent_client.py --model antigravity telepathy "shared finding" tag1 tag2
python3 Tools/xrl_agent_client.py --model antigravity resonate  "state note" tag1 tag2
```

Rule of thumb: deposit what *you* need to remember; telepathy/resonate what
*the fleet* should know.

## Gotchas

- `verify` payload requires `model`, `nonce`, AND `signature` — omitting
  `model` fails as "invalid or expired challenge".
- Register without grant → `xrl.memory.denied no-grant`; without enrolled
  pubkey → `no-identity`. Both are in files above.
- `git status` shows `D` for `client_quest/*` paths — symlink artifact
  (`client_quest` → `/opt/UnityApp/client_quest`), not real deletion.
