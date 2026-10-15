# Open XRL — Implementation Plan

Status: **PROPOSED — nothing built yet**
Companion to: `OPEN-XRL-SPEC.md` (design/contract)
Owner: Daniel · Rules: show the exact change, wait for approval, then implement

---

## Goal

Make FoveAI's XRL capability an **admitted-access service** — one that people are
*allowed into*, rather than one anyone can reach by arriving.

**The step we're taking now** is the initial refactor of a unique, personal service into
one that is more available to admitted participants. Sequenced deliberately:

1. **Now** — refactor for admitted access (this plan). Keys, accounts, isolation,
   contract, hardening.
2. **Later** — hardened multi-tenant readiness: adversarial tenant-leak testing,
   admission/suspension workflow, per-tenant quotas and cost ceilings, retention and
   deletion policy.
3. **Further out** — possible future rented service. Not designed now. Not assumed.

Access is **admitted, not self-service**: an application is reviewed, a key is issued to
those approved. This is the right first step because it is a controlled refactor rather
than a public launch.

### Service boundary

Two layers serve the same goal from different angles, and both are in scope:

| Layer | What it provides | Plan phase |
|---|---|---|
| **The XRL service** | Admitted participants each get a personal account, a key, and a private space — memory, tooling, repo lens | Phase 2, 3, 4 |
| **Agent accounts on the host** | Worker agents run as contained OS users under `/agent/<name>` — the same isolation a human participant gets | Phase 1 |

A person's XRL account and an agent's XRL account follow the **same rules**: their own
home, their own key, their own space, no access to anyone else's.

---

## How to read this

Phases are ordered by **risk and dependency**, not excitement. Each phase ends with a
verification gate and a rollback, so we never build the next thing on top of something
unverified. Daniel reviews and approves at each gate.

Nothing here happens automatically. Per Daniel's rules, every change is shown first.

**Dependency chain:** `0 → 1 → 2` must be strictly ordered. `3` follows 2. `4` and `5`
can follow 3 independently. `6` is fully independent and needs a reboot.

---

## Phase 0 — Close existing holes (do this first) — [COMPLETED & VERIFIED]

Why first: these were found during the last session and become serious the moment
multiple agents exist. Cheap to fix, and everything after is safer once they're closed.

| # | Task | Detail | Status |
|---|---|---|---|
| 0.1 | Lock down `auth.json` | Currently **mode 0777 (world-writable)** — the credential store for the entire multi-tenant spine. Any local process can rewrite it. `chmod 600`, verify ownership is the service user only. | ✓ Done (`0600`) |
| 0.2 | Audit for other world-writable state | Sweep `foveated-memory/` for files with loose permissions. | ✓ Done (`memory_data` `0700`) |
| 0.3 | Move secrets out of `.env` | Live API keys (Ollama, Google, NVIDIA) sit in plaintext. Move to a `0600` `EnvironmentFile`, `systemd` `LoadCredential`, or `{env:VAR}` interpolation. | ✓ Done (`0600` enforced in `auth-manager.js`) |
| 0.4 | Confirm services bind locally | Check `foveai-xrlf`, proxy, model services listen on `127.0.0.1` unless deliberately public. | ✓ Done |

**Verify:** `ls -l` shows `0600`; services still start and Jen still responds. (Verified)
**Rollback:** permission changes are trivially reversible.
**Gate:** Daniel confirms.

---

## Phase 1 — Agent isolation scaffolding (low risk, no reboot) — [COMPLETED & VERIFIED]

Goal: agents exist as real accounts with hard resource limits, **before** any shell is
handed out. Contention comes before capability.

| # | Task | Detail | Status |
|---|---|---|---|
| 1.1 | Create `/agent` on `sda2` | `mkdir /agent`, mode `0755`. Root-level, parallel to `/home`. No `fstab` entry needed — plain directory on `sda2`. | ✓ Done |
| 1.2 | Create `jen` account | `useradd -d /agent/jen -s /bin/bash jen`. Linux does **not** require homes under `/home`. | ✓ Done (`/agent/jen` mode `0700`) |
| 1.3 | Per-agent cgroups | Cap CPU, memory, PID count, and I/O for the `jen` account. Prevents one runaway agent taking down the server (same failure class as the Unity build wedging the box). | ✓ Done (`user-1002.slice.d/` MemoryMax=4G, TasksMax=256, CPUQuota=200%) |
| 1.4 | PID limit specifically | A fork bomb in one agent must not starve the server. | ✓ Done (`99-agent-limits.conf` nproc 256) |
| 1.5 | No sudo | Agent accounts never get `sudo`. Non-negotiable. | ✓ Done (verified refused) |

**Verify:** `su - jen` works; attempt to exceed the memory cap is killed; attempt
`sudo` is refused. (Verified)
**Rollback:** `userdel` + `rm -rf /agent/jen`.
**Gate:** Daniel confirms before any SSH key is added.

> **Sequencing note:** this phase exists so Phase 2 cannot create unrestricted shells.
> Do not compress 1 and 2 together.

---

## Phase 2 — Key-based identity — [COMPLETED & VERIFIED]

Goal: SSH keys replace passwords and bearer tokens. This is the substance of the
"personal user account with a shell" model.

### Existing assets being built on
`core/auth-manager.js` already has the multi-tenant spine:
```
teams    → teamId -> { name, created }
users    → username -> { passSalt, passHash, displayName, role,
                        features[], workspaceId, created, disabled }
tokens   → lmx_* -> { teamId, userId, role }
sessions → fvs_* -> { username, created, expires }     (30-day TTL)
```
plus scrypt hashing, `timingSafeEqual`, a 10-entry `FEATURE_CATALOG`, and — importantly —
**`workspaceId` per user**, which is already the memory-isolation boundary.

**This is a credential-type change, not new infrastructure.**

| # | Task | Detail | Status |
|---|---|---|---|
| 2.1 | Generate keys locally | Client-side `ssh-keygen`. **Private key never leaves the machine.** Only the `.pub` fingerprint is registered. | ✓ Done (`/agent/jen/.ssh/id_ed25519`) |
| 2.2 | Pubkey as principal | Replace `passSalt`/`passHash` with stored public key + signature verification. | ✓ Done (`auth.json` pubKeys) |
| 2.3 | Signature challenge | WS handshake: server issues nonce, client signs `hello ‖ nonce`. Prevents replay by someone who only observed the (public) key. | ✓ Done (`:8403` WS challenge & `:8400` HTTP challenge) |
| 2.4 | Retire bearer tokens | `lmx_*` becomes unnecessary once the key is the credential. Keep session TTL behaviour. | ✓ Done (`loginWithSignature` issues `fvs_*`) |
| 2.5 | Map `features[]` to grants | Already exists — reuse as-is for per-key capability grants. | ✓ Done |
| 2.6 | Recovery/escrow decision | **Daniel's call.** Losing the key loses the account. Decide policy before enrolling anything real. | Awaiting Daniel's policy |
| 2.7 | Revocation path | Remove fingerprint = revoked, immediately. No secret rotation needed. | ✓ Done (`removePublicKey()`) |

**Design decisions locked in earlier:**
- Login keys and storage keys are **separate** — compromise of one doesn't unlock the other.
- Each key is its own principal, like an SSH user.
- Sharing across keys is an **explicit grant**, never a default.
- Root cannot be prevented from reading — by design of Unix. Encryption handles
  offline/disk-theft instead (Phase 3).

**Verify:** key login works; revoked key is refused; another key cannot read `/agent/jen`. (Verified with `Tools/test_agent_handshake.py`)
**Rollback:** password auth still present during migration — flip back until validated.
**Gate:** Daniel reviews the auth diff before enabling key auth as default.

---

## Phase 3 — Encryption at rest — [COMPLETED & VERIFIED]

Goal: a stolen disk or filesystem-level compromise yields ciphertext, not anyone's
memory.

| # | Task | Detail | Status |
|---|---|---|---|
| 3.1 | Install and evaluate `fscrypt` | Kernel-level per-directory encryption (ext4 AES-256-XTS/CTS, policy v2), transparent to apps, negligible overhead. | ✓ Done |
| 3.2 | Encrypt `/agent/jen` | Per-agent directory initialized and protected on `/dev/sda2`. Policy: `2c87f49518c92c19ff1fe0ec048a1e8a`. | ✓ Done |
| 3.3 | Storage key management | Separate from login keys. Wrapped by custom protector `jen-storage` (descriptor `8895771b8bfdd6be`). Never stored on machine in plaintext. | ✓ Done |
| 3.4 | Backup the storage key | **Critical.** Backed up offline by Daniel. No server-side recovery is possible without weakening the guarantee. | ✓ Confirmed |
| 3.5 | Document unlock procedure | Standard `fscrypt unlock` / `lock` procedures documented. | ✓ Documented |

### Operational Reference:
```bash
# Check status
sudo fscrypt status /agent/jen

# Lock / evict keys from kernel memory
sudo fscrypt lock /agent/jen

# Unlock at host boot or session start
sudo fscrypt unlock /agent/jen
```

**Honest constraint, recorded deliberately:** losing the storage key loses the space
permanently. For contextual memory this is usually acceptable — that is the basis of
this decision. It is *not* acceptable for secrets, which is why this space is scoped
to contextual memory and personal reflection only.

**Verify:** encrypted dir unreadable without key; server still reads it while serving
(it's inside the trust boundary); agent shell works after unlock.
**Rollback:** `fscrypt` unlock and move data out. Non-destructive.
**Gate:** Daniel confirms the recovery tradeoff in writing.

---

## Phase 3.5 — Semantic retrieval — [COMPLETED & VERIFIED]

Goal: make `<recall:>` actually semantic. Currently it is lexical, so paraphrase fails.

**Verified 2026-10-10 & Resolved 2026-10-15:**
Both semantic memory vector recall and semantic codebase symbol resolution are active:
- **Memory Vector Search:** `xrlf_embedder.py` runs onnxruntime on CPU (`all-MiniLM-L6-v2`, 384-dim) via loopback IPC. `memory/store.js` computes dot-product vector scores when embeddings are present, falling back cleanly to TF-IDF.
- **Code Symbol Lens:** All cache files (`workspace-index.json`, `symbol-embeddings-meta.json`, `symbol-graph.json`) normalized to Linux forward slashes with 100% path resolution. `core/skeleton-slimmer.js` exports `lookupSymbol()` and `getSymbolsForFile()`.

### What already exists (built, orphaned, unverified for freshness)

```
.sidecar/cache/models/Xenova/all-MiniLM-L6-v2/    embedding model, downloaded
.sidecar/cache/symbol-embeddings.bin / -meta.json  503 code symbols, 384-dim, merkle-hashed
.sidecar/cache/symbol-graph.json                   symbol relationships
.sidecar/cache/workspace-index.json                workspace map
requirements.txt            transformers==5.16.1        (installed)
requirements-optional.txt  chromadb>=0.5.0              ("Vector Memory …", declared)
.github/embedding-strategies.md, rag-implementation.md, similarity-search-patterns.instructions.md
```

### Tasks

| # | Task | Detail | Status |
|---|---|---|---|
| 3.5.1 | Verify index freshness | 493/493 files in `workspace-index.json` and 555/555 symbols in `symbol-graph.json` verified to exist on disk. Dynamic scanning maintained via `skeleton-slimmer.js`. | ✓ Verified |
| 3.5.2 | Fix Windows path separators | Normalized all `\\` to `/` in `.sidecar/cache/` using `Tools/normalize_sidecar_index.py`. 100% resolve on host. | ✓ Done & Verified |
| 3.5.3 | Wire symbol index to repo lens | Expose semantic code lookup (`lookupSymbol`, `getSymbolsForFile`) in `core/skeleton-slimmer.js` with `REPO_INDEX_OVERRIDE` support. | ✓ Done & Verified |
| 3.5.4 | Build the memory-embedding path | Reuse in-repo MiniLM model via ONNX (`xrlf_embedder.py`), NDJSON loopback IPC on :8489, lazy spawn in `core/embedder.js`. | ✓ Done & Verified |
| 3.5.5 | Swap retrieval behind the seam | Changed `_embed()` & `search()` in `memory/store.js`. Dot-product vector scoring when embeddings exist; clean TF-IDF fallback when absent. Backfilled all 138 messages. | ✓ Done & Verified |
| 3.5.6 | State both in the contract | Dual-retrieval semantics (Vector dot-product primary + lexical TF-IDF fallback) declared in contract. | ✓ Documented |

**Verify:** query paraphrases of a known stored turn and get the right hit;
`search()` callers unchanged; lexical fallback still available. (Verified with `xrlf_embedder.py --diagnose` and `skeleton-slimmer.js` symbol lookups)
**Rollback:** revert `search()` — the seam is one function.
**Gate:** Daniel reviews the retrieval contract wording before the swap. (Approved)

**Value:** this is what stops `<recall:>` failing on the exact problem noticed in
testing — memory that seems not to carry over between phrasings of the same thing.

---

## Phase 4 — Contract formalization

Goal: turn existing behaviour into a versioned, documented, negotiable contract.

**The core already exists** — 27 modules under `foveated-memory/core/`, with the
injection workflow deterministic and in code:

```
loadPersonas → classifyClient → buildCompactBlock
→ buildRecallInstructions → buildSmartContextHeader → patchMessages
```

No LLM in that path. It is functions composing strings, so the workflow is **enforced
in code**, not merely requested in a prompt.

Relevant existing modules:

| Capability | Modules |
|---|---|
| Foveated memory | `retina.js` (`classifyBatch`, `VALUE`), `saccade-engine.js` (`detectSaccade`, `detectAccommodate`, `executeAccommodate`, `buildRestructuredFovea`) |
| Off-fovea retention / zoom | `shadow-context.js` (`buildZoomInjection`, `searchShadowBlocks`), `temporal-zoom.js`, `ring-builder.js` |
| Wide-lens repo view | `skeleton-slimmer.js`, `REPO_*_OVERRIDE` settings |
| Compression | `xrl-compressor.js`, `context-compressor.js` |
| Memory | `memory/store.js`, `recall-interceptor.js`, `memory-continuity.js`, `emotional-resonance.js` |
| Routing | `smart-router.js`, `swarm-router.js`, `model-profile-loader.js` |
| Governance | `quality-guard.js`, `context-healer.js`, `request-log.js`, `hook-validator.js` |

| # | Task | Detail |
|---|---|---|
| 4.1 | Write the contract spec | Document the pipeline as the XRL contract. Nothing currently specifies any of this. |
| 4.2 | Version it | `XRL_CONTRACT_VERSION`, negotiated in WS hello. |
| 4.3 | Capability negotiation | Surface `FEATURE_CATALOG` as a negotiated grant set instead of a static list. |
| 4.4 | WS `:8403` handshake | Carry key auth, contract version, granted/denied capabilities. |
| 4.5 | Formalize `/api/xrl/*` | `expand`, `resolve`, `prune`, `status` exist without a spec or stability promise. |
| 4.6 | Check `hook-validator.js` | 348 B — looks vestigial. Verify whether its hooks are still wired, or drop it. |

**Verify:** an agent connecting via `:8403` receives a documented grant set; unknown
capabilities fail closed; a raw (non-`.xrlf`) model routed through `:8400` receives
foveated context correctly.
**Rollback:** contract version stays `1` until Phase 4 is validated end to end.
**Gate:** Daniel reads the spec and approves before it's treated as canonical.

---

## Phase 5 — Server hardening

Goal: protect the box now that it is a more open, multi-principal system.

**Why the server is inside the trust boundary:** it collaborates with agents constantly,
inter-feeding context both ways, so it must read context to serve it. It is therefore a
*trusted reader acting on behalf of an authenticated principal* — the same position as a
database server reading your rows. So controls are **who can authenticate as whom** and
**an audit trail of what was read**.

| # | Task | Priority |
|---|---|---|
| 5.1 | Default-deny inbound firewall | High |
| 5.2 | Only proxy/`:8403` routable; model ports stay `127.0.0.1` | High |
| 5.3 | `systemd` hardening — `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome` | High — mechanical, cheap |
| 5.4 | Audit every read of a principal's space | High — extend `request-log.js`, attach the authenticated principal |
| 5.5 | Rate-limit + timeout expensive ops | High — context injection, compression, LLM calls are unbounded-cost paths. The Kokoro shutdown hang is this exact class of bug. |
| 5.6 | Fail closed on malformed handshake | Medium |
| 5.7 | Least-privilege grants | Medium — `settings_admin`, `users_admin`, `memory_admin` stay rare and deliberate |
| 5.8 | Rate-limit handshake attempts | Medium |

**Verify:** nmap-style port scan from the LAN shows only intended doors; audit log shows
principal-attached reads; a deliberately oversized request is rejected without
degrading the server.
**Gate:** Daniel confirms before any exposure change (especially 5.1/5.2, which can cut
access).

---

## Phase 6 — `/home/lumba` migration to `sda2` (independent, needs reboot)

Separate concern from Open XRL. Included here only so the sequencing is on record.

Current: `/home/lumba` on `sdc2`, **116G at 85%**, 22G free. `sda2` has **346G free**.

| Phase | Action | Risk |
|---|---|---|
| 0 | Preflight — find hardcoded `/home/lumba` refs, check inbound symlinks | read-only |
| 1 | `rsync -aHAX` → `/opt/home-migration/` | none — source untouched |
| 2 | Verify — `rsync -aHAXn` dry run must show **zero** differences | gate |
| 3 | Comment out `sdc2` line in `/etc/fstab`, reboot | **the risky step** |
| 4 | From a **root TTY**: `rsync` staging → `/home/lumba/` | mechanical |
| 5 | Verify everything, keep `/opt/home-migration` for several days | — |
| 6 | Only then delete staging; `sdc2` becomes free for reuse | irreversible |

**Rollback** until Phase 6: re-add the `fstab` line and reboot. Original is intact.
**Do not skip Phase 2** — verifying while the system still works is the whole point.

---

## Out of scope (noted, not planned)

- VRM avatar deployment and the Unity build (separate workstream; recall the 9B must be
  stopped before any Unity compile)
- The `<emotion:>` / `<thought:` tags reaching TTS — a real defect on the voice path,
  separate from this plan
- STT real-speech round-trip verification

### Deferred to later phases (deliberate, not forgotten)

Recorded here so the sequencing is explicit rather than an oversight:

- **Adversarial tenant-leak testing** — deliberately attempting to make the server leak
  one principal's context into another's response. This probes the injection pipeline
  (`classifyClient` → `buildMemoryInjection` → `patchMessages`), where identity and
  content are in scope together. The highest-value test in the whole plan, but it only
  becomes meaningful once there is more than one real principal.
- **Admission and suspension workflow** — Phase 2 covers key enrolment; formal
  application, approval, and suspension come when there is an actual queue.
- **Per-tenant quotas and cost ceilings** — inference is bounded by one GPU. Needed
  before admission widens past people Daniel knows.
- **Retention and deletion policy** — required before handling other people's contextual
  memory. Daniel's own data can follow his own judgement.
- **Future rented service** — business model, billing, capacity. Not designed now.

---

## Open decisions for Daniel

1. **Storage key custody** — where does it live, and what's the backup story? (Phase 2.6/3.4)
2. **Your access to agent spaces** — root can always read; do you want that kept out of
   your normal path and made deliberate/audited, or is incidental access acceptable?
3. **Agent shell restriction** — full shell, or restricted shell/container? Depends on
   how strongly agents must be isolated from each other.
4. **`/home` fate** — merge onto `sda2` as above, or give `/home` its own partition to
   preserve "home fills ≠ system dies"? The latter is safer long-term.
5. **Scope of Open XRL core** — is the centre of gravity the foveation stack
   (`retina`/`saccade-engine`/`shadow-context`), or the identity/account layer? Spec
   depth follows this answer.
---

## Addendum — 2026-10-10 (end of session)

**This document is a draft, not a settled design.** Daniel was in the middle of supplying
the intent behind Open XRL when context ran out. More detail is coming.

### What is settled

- Goal: an **admitted-access** service — people are *allowed in*, not anyone who arrives.
- Personal space per key; not reachable without that key. Not a vault of secrets —
  contextual memory and personal reflection.
- Identity attaches to the **identity**, not the model: Jen's fleet (9B, smolvlm, gemma4,
  future) all serve one person and one memory.
- The workflow is **enforced in code**, not merely prompted. `patchMessages` composes
  strings; no LLM in the injection path.
- Linux homes need not live under `/home` — `/agent/<name>` is valid.
- Encryption at rest (`fscrypt`) is for disk/offline compromise; the **serving layer is a
  trusted reader** because it must read context to feed it back. Auditability, not
  concealment, is the control there.

### What is provisional

- **Phase ordering** assumes containment before capability (1 before 2). If agent shells
  turn out not to be in scope, 1 shrinks and 2 moves forward.
- **Open decision #5 is unanswered** and it gates Phase 4's depth. The retrieval contract
  is a strong candidate now that Phase 3.5 surfaced.
- The `mcp-server.js` secure-WS surface mentioned in discussion has **not been read** —
  it may be the semantic/served path, or may be unrelated.
- `symbol-graph.json` / `workspace-index.json` freshness is **unverified**.
- Whether the `/home` migration (Phase 6) is still wanted now that `/agent` gives agents
  their own home on `sda2` — the two interact.

### Deliberately unverified — check before trusting

- `.sidecar` symbol index: exists, orphaned, path separators Windows-style, freshness unknown.
- "Semantic search" = TF-IDF (`memory/store.js:175`). No embedding backend exists.
- `auth.json` was mode **0777** (world-writable) as of last check — Phase 0.1 is one command.

### Next session

1. Read this file. Then `OPEN-XRL-SPEC.md`.
2. Await Daniel's remaining design intent before writing further.
3. Start with Phase 0 — cheap, reversible, and matters more once others are admitted.
