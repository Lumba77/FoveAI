# EAGLE — Session Handoff
**Read this file first.** Everything else is downstream of it.

**Date:** 2026-10-10 · **State:** Step 1 done & verified · production untouched · no live code path
changed yet · **§1 re-audited this session — 3 corrections recorded in §6.**

## What this is

**FoveAI is the whole operation** — a vast, deeply interlinked set of services, with a master AI at
the centre. **The purpose of the entire operation is to serve the relationship between the user and
the AI**, and to muster every benefit that relationship can bring.

Read that before optimising anything. It is the tie-breaker when two designs are technically
comparable: prefer the one that makes the user↔AI relationship more capable, more continuous, and
more private. A change that is clever but narrows or fragments that relationship is wrong here even
if it scores better on paper.

This is why identity attaches to the *identity* rather than the model — Jen stays herself across the
9B, smolvlm2, gemma4 and whatever comes next. Continuity **is** the feature.

## Where things are

| File | What it is |
|---|---|
| **`eagle-handoff.md`** | **← you are here.** Session state, verified facts, next steps. |
| `OPEN-XRL-PLAN.md` | The roadmap. 7 phases: agent isolation → SSH keys → encryption → **semantic retrieval (3.5)** → contract → hardening. Read its *Addendum* (§"Deliberately unverified") before trusting it. |
| `OPEN-XRL-SPEC-ORIGINAL-2026-10-10.md` | Design spec, recovered after it was destroyed. Six root causes, identity model, Open XRL enrollment shape, files-changed + backups. |
| `OPEN-XRL-SPEC.md` | ⚠ **Not the spec.** A diagnostic handoff that accidentally overwrote it. See §2. |
| `handoff.md` | ⚠ Symlink → `OPEN-XRL-SPEC.md`. Never write through it. |
| `foveated-memory/core/embedder.js` | Step 1, built and verified this session. Not yet imported by anything. |
| `xrlf_embedder.py` | Working MiniLM embedder. Added `--threads` this session. |

> **Do not name any file `handoff.md`.** It is a symlink → `OPEN-XRL-SPEC.md`. A `write` to it
> follows the symlink and destroys the target. That is how the 308-line design spec was lost on
> 2026-10-10 (see §2 below). This file is deliberately named otherwise.

### Project identity

- **Codename: EAGLE** — the king of birds. As of 2026-10-10 this is the working project codename.
- **MCP tooling is a work in progress *by design*.** Not a defect, not unfinished business to be
  apologised for — it is being built alongside everything else. Do not report it as "broken" or
  gate work on it being complete.
- ⚠ **Three different "Eagle"s — don't conflate them:**
  1. **EAGLE** — the project codename (above).
  2. **Eagle3 / Eagle** *speculative decoding* — the draft model
     `models/drafts/Qwen3.5-9B-Eagle3-ShareGPT-Q5_K_M.gguf` run by
     `foveai-llama-9b-eagle.service` on `:8408`. A decoding technique.
  3. **9B Eagle** — the service/endpoint name for the active flagship model.
  Plausibly the codename was inspired by (2) — fast speculative inference, king of birds — but
  **that link is inferred, not stated.** Worth confirming with Daniel before writing it into
  any document as fact.

---

## 1. Start here

Nothing in production has changed. `memory/store.js` and `server.js` are **unmodified** — recall
behaves exactly as it did before this session. Only two files were added/changed, neither reachable
by any live code path yet:

| File | Change | Reachable from production? |
|---|---|---|
| `foveated-memory/core/embedder.js` | **new** — sidecar client | no |
| `xrlf_embedder.py` | added `--threads` arg | no |

> **⚠ `git status --short` here is alarming and meaningless.** The tree carries ~8,900 modified
> files and the last commit (`db98027b`) predates a whole-machine migration. `server.js` alone
> shows a 5,794-line diff that is **100% CRLF→LF**. None of that is Step-1 work.

### Migration lineage — the root cause of most "residue" in this repo

**Stated by Daniel 2026-10-10; not independently verified:** NVMe crash **2026-09-05** →
migration to **Linux FoBara** → later **Linux Mint** (current).

This one fact is the shared parent of every unexplained artefact catalogued below — the Windows
backslash paths in `.sidecar/cache`, the CRLF diff, the dead PowerShell `backup.cmd` /
`backup.ps1`, the `C:/Users/danie/...` ghost paths in `.env`. **Treat them as archaeology, not as
bugs to fix.** Don't re-investigate them, and don't let a large `git diff` convince you that
something broke.

Verify the service is untouched before starting — but query the **right store**:

```bash
cd /home/lumba/FoveAI/foveated-memory
git status --short -- memory/store.js server.js     # NOT bare `git status`, see above
curl -s -X POST localhost:8400/v1/memory/search -H 'Content-Type: application/json' \
  -d '{"query":"auth.json permissions","limit":3}' | head -c 400
```

> **⚠ That `curl` probe is misleading — re-checked 2026-10-10.** It returns
> `{"results":[],"count":0,"mode":"tfidf"}`, which reads as broken recall. It is not.
> `/v1/memory/search` resolves `getStore(config.workspace_id)` → **`default`**, which holds
> **16 messages** (`/api/status` `total_memories: 16`; 18 documents in the file, 2 with empty
> content) and they are *entirely smoke tests* — "Name three colors in the rainbow", "hi",
> "If I have 5 apples and eat 2". A 0-result reply from `default` is the correct answer and
> tells you **nothing** about recall quality.
>
> **⚠ CORRECTION 2026-10-10 — I had this backwards.** An earlier version of this note said
> "`lumax` is the real corpus; size and benchmark everything against it, never `default`."
> **That was wrong**, and Daniel corrected it: **`lumax` is the *predecessor* project** — the old
> LUMAX, of which FoveAI is a refactor and a port. `memory_data/lumax` (841 docs, 14.5 MB) is
> therefore **historical**, not the active working set. `default` is where live conversation
> actually lands.
>
> **So: neither store is a "corpus" to optimise against.** `default` is live but nearly empty;
> `lumax` is large but inherited history. Daniel's standing instruction (2026-10-10):
> **"we can simply leave them be for now."** The old NVMe holds much more from that era, but it
> is mostly curiosity, and better sources exist if a FoveAI history vault is ever wanted.
>
> **What this changes:** benchmark the retrieval work on **synthetic pairs + whatever `default`
> accumulates naturally**, not on `lumax`. Judging recall by `lumax` would be measuring a dead
> project's memory. It also means Step 2 sizing should assume a **small live corpus** — which
> suits the sync-embed decision (below) even better than the 841-doc figure implied.

---

## 2. Doc chain damage — read before trusting any handoff

`handoff.md` is a **symlink** → `OPEN-XRL-SPEC.md`. Timeline, reconstructed from
`~/.local/share/opencode/opencode.db`:

- **06:38** `ses_ee3ca60f7ffeIhPXGQiakDg9uv` wrote `OPEN-XRL-SPEC.md` — a 308-line *Contract
  Specification & Session Handoff* (§0 session state, §1 identity model, §2 nine defects,
  §3 Open XRL enrollment, §4 files-changed + backups, §5 env facts, §6 next actions, §7 rules).
- **06:38** same session: `ln -sf OPEN-XRL-SPEC.md handoff.md`.
- **06:40** same session applied the §2.1 control-tag fix and marked it **RESOLVED**.
- **06:59** fork `ses_edbdfc969ffeVhd04p65Peh8Bg` ran `write` with
  `filePath: /home/lumba/FoveAI/handoff.md`. The tool **followed the symlink and overwrote
  `OPEN-XRL-SPEC.md`** with a different 269-line diagnostic-handoff document.
- **Result:** the design spec was destroyed. `handoff.md` → the diagnostic doc, which describes
  itself as *"Companion doc to `OPEN-XRL-SPEC.md` (read that first)"* — now self-referential.

**Recovered:** the 308-line original is at `OPEN-XRL-SPEC-ORIGINAL-2026-10-10.md` in this repo
(recovered from the `write` tool-call payload in the transcript DB; previously only in `/tmp`).

**⚠ Still true:** the 06:59 doc claims *"Control tags reaching TTS — HIGHEST PRIORITY, UNFIXED"*.
That is **wrong**. The fix landed at 06:40, 19 minutes before the clobber. Verified in the live
tree: `_strip_control_tags()` at `Backend/app/IPC/websocket_server.py:72`, called at `:962` in
`_kokoro_tts` as the single choke point. **Do not re-chase it.**

**Note:** the parent session `ses_ee3ca60f7ffeIhPXGQiakDg9uv` (2933 msgs) has since been **deleted**
from the DB. Its forks survive. Recover artifacts from forks, not the parent.

---

## 3. Verified facts about the semantic stack

All measured this session, not inferred from docstrings.

### It works. `xrlf_embedder.py` is sound.
`all-MiniLM-L6-v2`, quantized ONNX (22.9 MB), 384-dim, CPU-only via onnxruntime 1.30.0.

| pair | cosine | verdict |
|---|---|---|
| `hello` ~ `hi` | 0.80–0.83 | correct |
| `a cat sat on a mat` ~ `a kitten rests on a rug` | 0.62 | genuine paraphrase |
| `hello` ~ `hello` | 1.00 | correct |
| batched vs one-at-a-time | 0.802 / 0.818 | padding correctly masked |

**Throughput:** 424 msg/s on CPU → a 50k-message backfill is ~2 minutes.
**Round-trip** over the NDJSON socket: **4 ms**.

> **Don't repeat my mistake:** I probed with `"the thing we built last month"` vs `"Open XRL
> contract refactor"`, got 0.02, and briefly concluded the embedder was broken. It wasn't — that
> pair has no semantic overlap and no model can resolve it without conversation history. **Choose
> probe pairs with actual semantic relation.**

### "Semantic search" was TF-IDF all along
`memory/store.js:180 search()` — its own docstring says *"Semantic search using TF-IDF cosine
similarity"*. `store.js:6-8` claims *"semantic search … TF-IDF"*. No embedding backend was wired
to it. Meanwhile `.sidecar/cache/` holds an orphaned 503-symbol MiniLM index using **Windows
backslash paths** (`"foveated-memory\\server.js"`), file vectors stale since 2026-08-05, consumed
by nothing. Deps are already present: `transformers==5.16.1` in `requirements.txt`,
`chromadb>=0.5.0` in `requirements-optional.txt`.

### The existing `mode:'embedding'` path in `server.js:3089-3116` is triply broken
1. Posts to `config.upstream_url` = `:8408`, the 9B **chat** model — not an embedding service.
   LM Studio is offline per `AGENTS.md`.
2. Calls TF-IDF **first**, re-ranks only that shortlist ⇒ **structurally cannot** surface a
   paraphrase match. This is the deep defect, and it is why memory "didn't carry across sessions".
3. Reads `results.map(r => r.content)` but `search()` returns `{message, score}` ⇒ every
   `_embeddingScore` is `0`, the sort is a no-op.

### Dense and lexical are complementary — use hybrid, not replacement
Measured, query `"why is the world-writable credential file a problem"`:

| method | result |
|---|---|
| dense | **0.219** → correctly retrieves `auth.json … mode 0777` |
| lexical | **0.000** → fails; ranks an irrelevant doc first on the token "did not" |

And for query `FOVEAI_MODEL_ACTIVE_ID`, lexical `1.00` beats dense `0.87`.

Scores are on incompatible scales (0.87 vs 1.00 for the *same* pair) ⇒ **blending raw scores is
meaningless. Fuse on rank — Reciprocal Rank Fusion (RRF).**

### Callers of `store.search()` — the seam
All four keep working if only `search()` changes:
- `core/temporal-zoom.js:162`
- `mcp-server.js:182`
- `server.js:2365` ← the `<recall:>` tag path
- `server.js:3089`

`searchThemes()` at `store.js:333` has the same TF-IDF shape.
Scoping is per-workspace via `getStore(config.workspace_id)` with a separate `.db` each — so
`server.js:3089`'s ignored third arg (`sessionId`) is a **wart, not a cross-tenant leak**.

---

## 4. Done: Step 1 — `core/embedder.js`

Bridges JS → Python over loopback TCP, NDJSON: `{input:[…]}` → `{embedding:[[…]], dim:384}`.

Verified:

| check | result |
|---|---|
| sidecar socket protocol | `dim=384`, `cos(hello,hi)=0.8124`, 4 ms |
| `encode()` via JS | `cos=0.8018`, `cos(hello,mitochondria)=0.099` |
| **single-flight** | 8 concurrent `encode()` → **1 spawn** |
| lazy boot + reboot after `shutdown()` | both clean |
| failure path | returns `null` → caller falls back to TF-IDF |
| `status()` | honest: `tfidf/not-running` → `minilm-l6-v2/ready` |
| strays | none; port released |

API: `encode(texts) → Float32Array[]|null` · `status()` · `shutdown()` · `disable(reason)` ·
`available()` · `DIM`.

Three deliberate choices — **veto any of these if you disagree**:
- **`stdio:'ignore'`** on spawn. A full pipe buffer deadlocks the child (22.9 MB model).
- **Child is NOT detached** — dies with the server. An ONNX process outliving its parent is
  exactly what wedged `foveai-tts` (2m45s CPU, SIGKILLed).
- **`--threads 2`** default, `XRLF_EMBEDDER_THREADS` override. Unbounded ORT threads steal
  cycles from llama.cpp prompt eval; `AGENTS.md` forbids running heavy CPU work beside the 9B.

Also: 15-min idle shutdown; `disable()` for operator opt-out to pure TF-IDF.

### Two bugs found and fixed during testing — don't reintroduce
1. **Spurious `socket lost` during boot.** `error` *and* `close` both fire on a failed connect
   probe; the second logged as if a live socket died. Fixed with a `live` flag.
2. **Deliberate `shutdown()` warned** "next recall will fall back to TF-IDF" when it would simply
   re-boot. Fixed with a `closing` flag.

---

## 5. Next: Steps 2–6

### Step 2 decisions — MADE 2026-10-10 (Daniel delegated: "make an informed decision on what
### serves us and the whole service best")

Daniel is a vibe coder and explicitly delegated this call, noting some decisions depend on
conditions we don't know yet. Reasoning recorded so it can be revisited, not just obeyed.

**1. Sync embedding in `store()` — NOT queued.** Rationale: encode is **~2.4 ms**
(measured: 424 msg/s ⇒ 2.36 ms/msg) against a chat write path that already does a disk
append. The queue would add a moving part (drain-on-boot, ordering, backpressure, "was this
message embedded yet?") to save ~2 ms on an operation a human never times. **Falls back
synchronously to no-embedding if the sidecar is down** — that is the entire failure surface.

**2. Feature flag — YES, defaulting ON, env `XRLF_SEMANTIC=0` to revert instantly.** This is
the one place where being wrong is cheap and being wrong *silently* is expensive: if hybrid
retrieval ever regresses exact-identifier recall, the fix must be a restart-free revert, not an
edit. Flag also satisfies AGENTS.md's isolation discipline and the plan's phase-gating style.

**3. Backfill — separate, resumable, batched, gated by `XRLF_EMBED_BACKFILL=1`.** Never runs
implicitly at boot (handoff §5 requirement, and the AGENTS.md pattern of no surprise CPU work
beside the 9B).

**4. Precedence: lexical wins ties.** Dense rescues paraphrases; lexical keeps exact
identifiers (`FOVEAI_MODEL_ACTIVE_ID`) sharp. Never let dense demote a perfect token match.

> **⚠ Corrected cost model — the backfill is ~1.5 s, not ~2 minutes.** The handoff's "50k-message
> backfill ≈ 2 min" extrapolated from 424 msg/s, but `lumax` holds **841 documents, not 50k**,
> and total corpus is 119 files / 15 MB. Real figure: **~2 seconds**. That changes the risk
> calculus — the backfill is *cheap*, so it needs no elaborate resume machinery. Keep it
> idempotent and batched, but do not over-engineer it.

### ⚠⚠ Step 2 is BLOCKED on a backup that does not exist — corrected 2026-10-10

Daniel believed the 2026-10-10 archive was a safety copy "preserving last session's work". **It
is not one, and it does not cover the data Step 2 rewrites.**

`/opt/FoveAI Storage/code-archive/foveai-code-20261010-085619.tar.gz` (3.0 MB, 554 entries) was
verified by listing its contents:

| expected | actual |
|---|---|
| `foveated-memory/memory_data/**` (119 `memory.db`) | **0 entries** — excludes the entire memory corpus by design |
| `foveated-memory/server.js` | ✅ present |
| `foveated-memory/memory/store.js` | ✅ present |
| `foveated-memory/core/` | ✅ present |

**So the archive protects exactly the files Step 2 will *not* touch, and omits the 119
databases it will.** The only `.db` files inside are unrelated (`Backend/data/*.db`). The
handoff's own §"Code archive" note says memory backups are `memory_backup.py`'s job, not this
tar's — and §5's `memory-db-backup-20261010/` directory **was never created**.

**Therefore the §5 rollback plan has never been executed.**

### ✅ DONE 2026-10-10 — Steps 2 (part) + the resource hotline

**Step 2 — embed at write time.** `memory/store.js` now writes a dense 384-d vector alongside each
message, via `core/embedder.js`, sync, flag-gated. **7/7 functional tests pass.** Warm write
**3.6 ms**, flag-off **0 ms**. `XRLF_SEMANTIC=0` reverts to pure TF-IDF instantly. CRLF preserved
(530/530 — the file is CRLF, so naive editing would have produced another phantom whole-file diff).

> **⚠ Unresolved, and it is the real risk:** the *first* embed after a restart pays ONNX model
> load — **7–11 s measured**, against a 3.6 ms warm path. That cost currently lands **inside the
> first chat write**, which would stall a conversation for ten seconds after every boot.
> `/tmp/opencode/apply_step2b.py` holds the fix (time-box the wait: start the encode, wait 150 ms,
> give up **without cancelling** so it warms in background; one message falls back to TF-IDF and
> the conversation never pauses). **Written but NOT applied.** Also note the first latency figure
> was taken while the box was under heavy load — re-measure on a quiet machine before trusting it.

**The governor became a judge.** `runtime/vram_guard.py` (+247 lines, additive; backup at
`/tmp/opencode/vram_guard.py.bak`). It previously asked *"how much is free?"* and never *"who has
it?"* — so it could clamp itself but never name the cause. Now: per-process VRAM attribution
(`nvidia-smi --query-compute-apps` → PID → name), system `MemAvailable`, and PSI
(`/proc/pressure/*`). **Collaboration is the default** — clear → proceed silently; busy → proceed
announced; only measured pressure escalates.

**Verified truth table** (all four correct):
| condition | verdict | granted |
|---|---|---|
| healthy box | `clear` | ✅ yes |
| RAM squeezed | `blocked_ram` | ✅ no |
| GPU held by another process | `blocked_vram` | ✅ no |
| disk saturated (PSI) | `blocked_io` | ✅ no |

> **🐛 Bug found and fixed during testing — do not reintroduce.** The first gate compared
> `verdict != "blocked"`, but verdicts are `blocked_ram` / `blocked_vram` / `blocked_io`. It
> therefore **granted exactly when it should have refused**. Caught because the test printed
> `verdict: blocked_ram` next to `granted: True`. Now prefix-matched with `startswith("blocked")`.

**`runtime/hotline.py` (new) — the inter-actor channel.** Daniel's principle: *"we shouldn't just
feel like we're sinking without understanding why."* One bus, everyone on it, urgent messages and
explanations travelling the same road. Levels `info/notice/warn/urgent`; `explain` is a
first-class field, not a rendering detail.

> **The rule it's built on: a message is durable BEFORE any delivery is attempted.** Proven by
> test — published with no listeners alive at all, then replayed on arrival via `since(cursor)`.
> This exists because `vram_guard._broadcast_silent_ipc` posted to
> `http://127.0.0.1:8400/v1/internal/ipc`, **a route that exists nowhere in the codebase**, inside
> an `except: pass`. The governor had been "communicating" into a void indefinitely. It is now
> rewired through the hotline.

Deliberately **transport-agnostic — it binds no port of its own**, because the port map is
mid-remap and `AGENTS.md` contradicts the code about what `:8411` is. Log at `.hotline/bus.jsonl`
is the source of truth; dunst (running ✅) and `:8400` are transports that may be absent without
data loss. Decision journal: `.model_locks/lane.log`.

**Known gap, honest:** `human_idle_s()` returns **`None`** — `xprintidle` isn't installed, so the
"is Daniel actually at the desk" signal is unavailable and the governor cannot tell you-at-desk
from you-at-lunch. It returns `None` and says so rather than guessing; a fabricated answer there
would be worse than none. Alternatives: Mutter idle over D-Bus, `/dev/input/event*` timestamps.

**Not yet wired:** nothing calls `request_lane()` — `acquire_slot()` behaves exactly as before,
so there is no regression risk yet. And `/v1/hotline` on `:8400` is **not** implemented, so
*processes* still can't hear back; only humans get dunst. That needs a `server.js` route, which is
why it was left alone.

```bash
cd /home/lumba/FoveAI && mkdir -p /home/lumba/memory-db-backup-20261010
find . -name 'memory.db' -not -path '*/node_modules/*' \
  -exec cp -a --parents {} /home/lumba/memory-db-backup-20261010/ \;
```

| check | result |
|---|---|
| files copied | **119 / 119** ✅ |
| size | 16 MB |
| integrity | `md5sum` diff of all 119 vs source → **byte-for-byte identical** ✅ |

`cp -a` preserves mtimes/modes, so these are true snapshots, not fresh copies. **To roll back:**
copy the tree back over `FoveAI/`, or point `getStore()` at the backup dir. This is the first
real rollback capability the project has had for memory data — before it, there was none.


### Step 2 — embed at write time ⚠ FIRST WRITE TO LIVE DATA

`store.store()` writes `embedding: Float32Array(384)` onto the message document. Query then embeds
once and does a single dot-product pass: **O(1) per query** instead of today's full-corpus
`db.find({})` scan.

**Rollback plan — do this before touching anything:**

There are **119 `memory.db` files, 15 MB total** (one per workspace, plus `.xrlf.cache` copies;
`lumax` alone is 14.5 MB of that). Back them all up in one pass:

```bash
cd /home/lumba/FoveAI
find . -name 'memory.db' -not -path '*/node_modules/*' \
  -exec cp -a --parents {} /home/lumba/memory-db-backup-20261010/ \;
find /home/lumba/memory-db-backup-20261010 -name 'memory.db' | wc -l   # expect 119
```

NeDB documents gain an optional field; readers that don't know it ignore it, so the field alone is
non-breaking. **The backfill is the risky part** — it rewrites documents. Make it idempotent and
resumable, and re-embed in batches (e.g. 200) rather than one `db.find({})` of everything.
Consider a `XRLF_EMBED_BACKFILL=1` env gate so it never runs implicitly at boot.

**Design decision left open:** embed synchronously in `store()`, or queue? Blocking the chat write
path on a ~2.4 ms encode is probably fine, but a queue keeps writes instant. Your call.

### Step 3 — `search()` → dense, RRF-fused with TF-IDF
Change only `store.js:180`. Keep TF-IDF: dropping it regresses exact-identifier queries, which for
a developer are the *most* valuable. RRF: `score = Σ 1/(k + rank_i)`, k≈60.

### Step 4 — `searchThemes()`, flag-gated
Same treatment. Marginal cost once the client exists. Gate behind a flag so it can be disabled.

### Step 5 — repair the broken embedding path
`server.js:3101` `.content` → `.message`; re-point `mode:'embedding'` at the sidecar instead of
`config.upstream_url`. Add `recall_backend` to `/api/xrl/status` (currently `v3.0`) so the contract
declares which mechanism is actually live.

**Port map is a non-issue here (resolved 2026-10-10).** The remap is deliberate WIP, and this fix
routes *around* it by targeting the sidecar's loopback NDJSON socket instead of any `:port`. No
reconciliation needed.

### Step 6 — correct `MEMORY_PROTOCOL`
`core/recall-interceptor.js` (required at `server.js:167`) implements **five** tags — `<recall:>`,
`<zoom:>`, `<saccade:>`, `<accommodate:>`, `<temporal_zoom:>`. The injected `MEMORY_PROTOCOL`
(~180 chars) advertises only three. **`saccade:` and `accommodate:` ship in every context window
and the model is never told they exist.**

---

## 6. Your call

- **Feature flag?** Want semantic behind a flag so recall can revert to pure TF-IDF instantly?
- **Embed sync or queued?** (Step 2 — affects chat write latency)
- **`FOVEAI_MODEL_ACTIVE_ID` conflict** — `qwopus3.5-9b-coder-mtp-moq` (`.env` 28, 172) vs
  `qwen3.5-4b-mtp-multimodal-v1.0.xrlf` (171). Last-one-wins is order-dependent. Which is intended?
- **Open decision #5** in `OPEN-XRL-PLAN.md` gates Phase 4 depth — still unanswered.
- **`default` vs `lumax` — RESOLVED as "leave them be" (Daniel, 2026-10-10).** `lumax` is the
  **predecessor project** (old LUMAX; FoveAI is its refactor/port), so its 841 docs / 14.5 MB are
  **historical**, not live. `default` (16 msgs, smoke tests) is where live conversation lands but
  is nearly empty. **Decision: leave both alone.** No consolidation, migration, pruning or
  deletion. The old NVMe holds more of that era but is mostly curiosity, and better sources exist
  if a FoveAI history vault is ever wanted.
  - **Not a blocker for Steps 2–5.** The semantic work changes shared code (`store.search()`,
    `store.store()`), and `getStore(config.workspace_id)` hands out a separate `.db` per
    workspace — so both stores get the improvement regardless.
  - **Benchmark on synthetic pairs + whatever `default` accumulates**, never on `lumax` (that
    would be measuring a dead project's memory).
  - Backup rationale unchanged: 119 files is still correct to copy, but they are not 119 real
    workloads — `lumax` is ~90% of the bytes and is dead weight by design.

### Settled this session
Open XRL key escrow = **option (c)**: server-held backup of the private key **encrypted under
`fscrypt`** (Phase 3), reusing the mechanism that already protects `/agent/<name>`. Threat model is
proportionate — a developer's contextual work memory, **not a vault of secrets** — which matches
the plan's existing "not a vault of secrets" framing.

Consequence: memory must scope to a **stable principal id**, not the key fingerprint, so escrow is
*recovery* rather than *identity*. Same principle as the spec's §1 — identity attaches to identity.

### Phase 0.1 — DONE 2026-10-10
`foveated-memory/memory_data/auth.json` was mode **0777** (world-writable, 40 KB of hashed bearer
tokens) → now **`600`**. Verified the running services still read it: they run as **root**
(`node server.js` pid 712950), which bypasses permission checks, and `lumba` owns the file, so it
survives a future drop to non-root. `/health` 200 and `/api/xrl/status` → `v3.0` after the change.
`.byok_key` was already `600`.

### ⚠ `foveai` account — NEUTRALISED 2026-10-10 (Daniel authorised)
A second local account existed: `foveai` (uid 1001) with an **active password** (status `P`, last
set 2026-10-09), a real `/bin/bash` shell, a home dir, and **`sudo`** group membership — while
1,322 items under `memory_data` were world-writable. Active privilege-escalation path, not a
theoretical one.

**Fixed without deleting anything:**
```bash
passwd -l foveai          # -> status "L", shadow hash now '!'-prefixed = auth disabled
gpasswd -d foveai sudo    # -> group 27(sudo) gone from `id foveai`
```
Verified: `passwd -S` → `L`; `id foveai` shows `27(sudo)` absent; no systemd unit runs as it; no
process owned it. Account, home dir and files all left intact.

**Reversal** (if ever needed): `sudo passwd -u foveai && sudo gpasswd -a foveai sudo`
**Backup:** `/root/foveai-lock-backup-20261010/` (passwd, group, gshadow, shadow; dir mode 0700)

⚠ **A note on testing this:** `sudo -u foveai` and `su foveai` run *as root* **do not test
password auth** — root bypasses it. Two such checks gave a false "LOGIN_WORKS" here. The only
conclusive evidence is the `!` prefix in `/etc/shadow`. Don't repeat that mistake.

**Not yet done — 1,322 world-writable items** remain under `memory_data` (1,236 files incl. all
`memory.db` + `checkpoints/*.json`, 86 dirs). Much less urgent now the account is locked, but still
worth a sweep before Open XRL admits anyone:
```bash
# PROPOSED, not run — review before applying
find /home/lumba/FoveAI/foveated-memory/memory_data -type f -perm -o+w -exec chmod o-w {} +
find /home/lumba/FoveAI/foveated-memory/memory_data -type d -perm -o+w -exec chmod o-w {} +
```

### Code archive — created 2026-10-10
```
/opt/FoveAI Storage/code-archive/foveai-code-20261010-085619.tar.gz   (3.0 MB, 554 entries)
```
Contents: `Backend/` `Frontend/Mouth/` `runtime/` `Scripts/` `xrlf_embedder.py`
`foveated-memory/{core,memory,server.js,mcp-server.js}` + key docs
(`eagle-handoff.md`, `OPEN-XRL-PLAN.md`, the recovered spec, `AGENTS.md`).
Excludes `node_modules`, `.venv`, `__pycache__`, `.git`. Verified readable (`tar -tzf`).

⚠ **The repo's own backup scripts are dead on this box.** `backup.cmd` / `backup.ps1` are
PowerShell ("FoveAI Sovereign Backup — git-substitute version control via zip snapshots") and
**PowerShell is not installed** — they cannot run. Same migration residue as the Windows-path
sidecar index and the CRLF diff. `memory_backup.py` *does* run and is non-destructive (no
`rmtree`/`remove`/`unlink`), but it backs up memory `.db` files, **not code**. The tar above was
built by hand instead. Porting `backup.ps1` to a Linux-native script is an open item.

Note `/opt/FoveAI Archive` does not exist; the real path is `/opt/FoveAI Storage`.

### Also still queued
- Step 2 decision — **delegated to the assistant**: pick sync vs queued, and flag or no flag.
- 1,322 world-writable items under `memory_data` — sweep proposed above, not run.

### ✅ Audited 2026-10-10 — corrections to this document

Re-verified §1 before starting Step 2. Three claims in earlier versions of this file were wrong;
recording them so they don't propagate (hard rule 8).

| claim | reality |
|---|---|
| "`server.js` is unmodified" | **It is modified.** The 5,794-line whole-file diff is a CRLF→LF migration artifact (`git diff --ignore-cr-at-eol` shrinks it to **578 insertions / 33 deletions**). Those 578 are *real* edits — **identified and catalogued below; they are feature work, NOT semantic search, and are safe to treat as a legitimate baseline.** |
| orphaned 503-symbol index is in `foveated-memory/.sidecar/cache/` | It is at **`/home/lumba/FoveAI/.sidecar/cache/`** (repo root). Contents confirmed: `count: 503`, `modelId: Xenova/all-MiniLM-L6-v2`, `dimension: 384`, keys like `foveated-memory\server.js::http` — Windows separators, consistent with §"migration lineage". |
| that index is "stale since 2026-08-05" | Split truth. `embeddings.bin` **is** 2026-08-05; but `symbol-embeddings-meta.json` is **2026-10-07**. Treat "stale" as unverified rather than settled. |
| `handoff.md` symlink still live | Confirmed → `OPEN-XRL-SPEC.md`. Unchanged. Never write through it. |

Confirmed **true**: `xrlf_embedder.py` and `core/embedder.js` both pass syntax check;
`store.js:180` is still TF-IDF; the `mode:'embedding'` path at `server.js:3089` is broken in
**exactly** the three ways described in §3 (`r.content` vs `.message`, re-ranking a TF-IDF
shortlist, `config.upstream_url` → the chat model on `:8408`). `/api/xrl/status` still returns
a bare `version: '3.0'` with no `recall_backend`.

**Open thread:** `.env:54` still holds `XRLF_WORKSPACE_ROOT=C:/Users/danie/program/LUMAX/FoveAI` — *a Windows
path, and a workspace-root key*. (Note the spelling: **`danie`**, not `diane` — Daniel's late
Windows account, missing the `l`.) Migration residue explains the string; it does **not**
establish whether anything still reads it. Since workspace-root selection is exactly what
decides `default` vs `lumax`, **read that before touching store resolution.**

### ✅ The 578 unaccounted insertions in `server.js` — identified 2026-10-10

Read in full (`git diff --ignore-cr-at-eol`, 27 hunks). **Daniel's guess was right in spirit,
wrong on substance — with one important consequence.**

**They are NOT semantic search.** Grepping all 578 added lines for
`embed|semantic|minilm|rrf|dense|cosine|tfidf|vector` returns **zero hits**. Nothing in that
diff touches retrieval. Step 1's `core/embedder.js` remains the *only* semantic work in the
tree, and the `mode:'embedding'` path at `server.js:3089` is untouched and still broken exactly
as §3 describes.

**What they actually are** — unrelated feature work, coherent and high-quality:

| area | change |
|---|---|
| Juggle / Tandem mode | ~110 lines routing `model:'juggle'\|'tandem'` → `Backend/Creativity/tandem.py`, with history relay, empty-answer retry, and a junk/router-artefact guard. |
| Theme Machine | `/api/themes`, `/api/theme/set_active` — ported off `http_proxy.py`, which isn't the process on :8400 (every fetch 404'd). |
| Resonant memory | `/api/resonance/{ingest,telepathy,tail,depth}` → `data/resonance.jsonl`, append-only "gravity lane". |
| Per-user settings | `data/setting_overlays/<ws>.json` + `requireAdminOrUserKey()` — member writes land in an overlay instead of being silently 403'd; effective mode honoured per-request via `effMode`. |
| Profile pictures | `inspectImage()` header-parses PNG/JPEG/WebP dimensions to reject blank/1×1 canvas snapshots, plus gallery collection + shared AI persona portrait. |
| `/api/server_info` | Live LAN IP + port map so clients stop hardcoding addresses. |
| Port remap | Dashboard 8401→**8414**, TTS 8406→**8411**, Chat Relay 8407→**8413**, Creative 8408→**8412**, STT 8409→**8401**, Subconscious 8411→**8409** — in code, comments *and* `/api/subsystems`. |
| Health probe fix | `upstream_url` ends in `/v1`; llama-server serves `/health`, so ignition hung 2 min on "checking the model". Now strips `/v1` and normalises `loaded`/`load_state`. |

**Provenance — consistent with Daniel's account.** `server.js` mtime is **2026-10-09 01:27**,
i.e. the day *before* the 2026-10-10 handoff session, and the last commit (`db98027b`,
2026-10-05) predates it. `context.md` (95 KB, newest entry **2026-09-18**) and `Context.md`
(newest **2026-09-19**) both stop ~3 weeks short and mention none of it — `juggle`, `resonance`,
`gallery`, `server_info`, `overlay` all score **0**. **Both session logs simply were not being
written to during that period.** That matches "an AI dev helped at a late stage without
logging" precisely: unlogged, but coherent, dependency-complete and evidently exercised.

**All referenced dependencies verified present**, so this is finished work, not a half-applied
patch: `foveated-memory/tools_gallery.api.js` (12 KB, 2026-10-07),
`Backend/Creativity/tandem.py` (21 KB, 2026-10-07), `data/setting_overlays/u_ignite.json`.

> **The port remap — RESOLVED as WIP (Daniel, 2026-10-10).** `AGENTS.md` documents a *different*
> post-migration map than the one these insertions hardcode — **STT :8411 and Subconscious :8411**
> (AGENTS.md) vs **STT :8401 / Subconscious :8409** (this diff), **Soul :8405** vs **:8411**.
> **This is deliberate, not a defect.** Daniel: a *spontaneous, wholesale remapping* of all ports
> that followed **an argument between Daniel and a developer over what the port numbers
> signify**. Treat as **work in progress**. There are reportedly **hundreds** of call sites still
> pointing at now-dead ports, but that code is **mostly not on any active path** and is
> **easy to appropriate when the time comes**.
>
> **Consequence for our work — smaller than feared.** Step 2 touches only `store.js` and is
> unaffected. For **Step 5** the remap is a non-issue, because Step 5 *already* removes the port
> dependency: re-pointing `mode:'embedding'` at the **sidecar** (`core/embedder.js`, loopback
> NDJSON) instead of `config.upstream_url` means the embedding path no longer names a port at
> all. **Do not reconcile the port map to unblock Step 5 — the fix routes around it.**

---

## 7. The three forms of XRL service — Daniel's framing

Stated by Daniel this session; **not yet fully written into `OPEN-XRL-PLAN.md`.** This is design
intent, so treat it as authoritative-but-unverified against code.

### Form 1 — Requested
Memories and MCP tooling, invoked in XRL by the model: scanning files and repos, steering memory
fovea. **This is the surface the semantic work in §5 targets.**
- Tag protocol: `core/recall-interceptor.js` (244 lines, required at `server.js:167`) —
  `<recall:>`, `<zoom:>`, `<saccade:>`, `<accommodate:>`, `<temporal_zoom:>`
- MCP tooling: `mcp-server.js` (379 lines), calls `store.search()` at `:182`
- Repo/file scanning: `core/skeleton-slimmer.js`, `server.js` `/api/skeletonize`, `/api/xrl/*`

### Form 2 — Auto-provided
Precisely **measured** context-window injection, applied every request without being asked.
- `core/system-prompt-patch.js` (193 lines) → `loadPersonas()` → `classifyClient()` →
  `buildCompactBlock()` → `buildRecallInstructions()` → `buildSmartContextHeader()` → `patchMessages()`
- Deterministic — no LLM in the injection path. Ordering is client-type dependent: for `coder`
  clients the original system prompt stays dominant and the memory block is appended; for
  `companion`/`jenna` the persona goes first.
- Budget header observed live: `model:X; budget:4096; mode:local;`, `cloud_cap 64000`,
  `preserve_last 4`. It is placed first *deliberately* — small models echo the end of the system
  prompt.
- Injects `MEMORY_PROTOCOL` (~180 chars) advertising only **three** of the five tags (see Step 6).

### Form 3 — Membrane ("thin red thread")
Eaves a thin thread of **guidance** from massive contexts and serves that to the beneficiary —
a guiding filament rather than a content dump.
- `core/membrane-bridge.js` (151 lines) spawns `membrane_core.py` and drives it over **stdin/stdout
  JSON RPC**. It builds a dynamic HUD of: turn counts, active checklist, XRL codebase intuition,
  file-edit diagnostics, and token-budget pressure.
- ⚠ **Open question:** this shares a name with the XRLF **`MembraneEngine`** seen at boot
  (`[XRLF] MembraneEngine loaded: …memory.db (session=default, turns=193)`). Same subsystem or two
  unrelated things that both got named "membrane"? Unresolved — ask Daniel before assuming.

### Why this matters for the semantic work
The work in §5 is not confined to Form 1. **All three forms retrieve and rank**, so improving
`store.search()` propagates to:
- Form 1 — `<recall:>` hits get better
- Form 2 — better material to select for a tightly budgeted auto-injection
- Form 3 — the membrane's guidance thread draws on the same store

That is the strongest argument for putting the seam in `search()` rather than bolting retrieval onto
one call site. It is also why "exactly measured" in Form 2 matters: a smarter retriever feeding a
hard token budget is worth more than a bigger budget.

### House convention this confirms
`membrane-bridge.js` (spawn Python, exchange JSON) is the established pattern for JS→Python
capabilities here. `core/embedder.js` from Step 1 follows it. Prefer extending that pattern over
introducing a new IPC style.

---

## 8. Hard rules

1. **Show the exact change, wait for approval, then apply.** Violated repeatedly across sessions —
   and it produced both the `.env` edits and the spec clobber.
2. **Never write through `handoff.md`** — it is a symlink; the write destroys the target.
3. **Never `cat .env` or `/proc/*/environ`** — live API keys. Grep specific keys.
4. **Never run Unity or heavy CPU work concurrently with the 9B.** Last Unity build wedged 4 h at
   100% CPU — hung, not slow.
5. **9B ctx capped at 2048** (40/40 layers offloaded, VRAM-bound).
6. **WS envelope is `{"event":…, "payload":{…}}`** — not `type`. Unknown keys are dropped silently.
7. **Naming:** Jen / Jenny Ninebe / made by **Daniel**. smolvlm2 = dormant, 9B = active.
8. **Don't trust a docstring for a capability.** Twice now (TF-IDF, the `mode:'embedding'` path)
   documentation asserted behaviour the code did not have. Verify, then write down what you verified.
9. **The ~8,900-file dirty tree is migration residue — never "clean" it.** NVMe crash 2026-09-05 →
   FoBara → Mint. Do not `git checkout` / `git stash` / restore a file to tidy the working tree:
   that discards real post-migration work (e.g. the 578 unaccounted insertions in `server.js`).
   A big diff is expected here and means nothing on its own.
10. **Know which store you're querying.** `default` is smoke-test data; `lumax` is the corpus.
   A 0-result from `default` is correct behaviour, not a regression — see §1.