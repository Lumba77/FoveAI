# XRL Swarm — Operations Handbook (captain's edition)

Last updated: 2026-10-18. Everything below is plain language on purpose.
If you read only one paragraph: **you are running a 228.8 MB file that
contains a tiny language model plus a memory ledger of 500 seed entries.
A live chat bridge (port 8400) lets Multigate (port 5177) talk to it.
`verify_memory.py` is your health check; everything else in this file
explains what to touch and what never to touch.**

---

## 1. What is in the swarm

The swarm is "Nova". It has two parts:

- **Pawn** — a miniature language model built by the kqatt project
  (quantization-aware training; 82 MB, `attn8/ffn3/emb6`). Its one talent:
  read a stack of *seed* entries and recite the requested field.
- **Knight** — a slightly larger 6-bit model (137 MB). Its one talent:
  hear the pawn's raw recitation and bind it into the correct answer.
- **Ledger** (`seed_ledger.jsonl`) — the swarm's memory: 500 entries,
  421 members. An entry looks like:

  ```
  name: "onyx quarry"   domain: "shipping"
  goal: "portion scaling"      (asked as: What outcome did ... commit to?)
  dec:  "shorten the sprint"   (asked as: What decision did ... make?)
  gold_seed: "<XRL-SEED d=3><SNP>onyx quarry:shipping:P0</SNP>..." (memory chain)
  ```

  Each seed chains 4 members (`P0`–`P3`), each with its goal+dec. New
  members are **pure data**: add entries in this format and the swarm can
  answer them with zero retraining (proven 2026-10-18 with 20 grown
  members — see §5).

Everything is packed into one **cartridge** file (`.collegium`, a zip).

## 2. Cartridge versions (kept as archive history)

| file | version | what changed |
|---|---|---|
| `nova.collegium` | v1/v2 era | original k6 pawn (287 MB) |
| `nova_kqatt.collegium` | v3 | kqatt champion pawn, raw ledger |
| `nova_kqatt_lz.collegium` | v4 | ledger lz-packed inside (413→18.7 KB) |
| `nova_kqatt_lz_v5.collegium` | **v5 — LIVE** | grown 500-entry ledger, packed (430→20.1 KB) |

**Live setup:** `mg_bridge.py` (chat bridge, port 8400) points at v5 and
is verified end-to-end through the real Multigate proxy (port 5177).
Ask it: *"What outcome did violet channel commit to?"*

## 3. Daily commands

```bash
cd /tmp/opencode
PYTHONPATH=/tmp/opencode  FVPY=/home/lumba/FoveAI/.venv/bin/python

# health check (ledger integrity, live cartridge, packets, bridge):
$FVPY verify_memory.py                                # want: ALL GREEN

# ask the swarm directly (k = how many seeds layered; 1 is most accurate):
$FVPY collegium.py --k 1 "What outcome did lark aquifer commit to?"
$FVPY collegium.py --roster                           # who lives in memory

# inventory the XRLF seed packets:
$FVPY xrlf.py packets                                 # (dir) unpacks + CRCs each
$FVPY xrlf.py make "quiet delta"                      # pack a member's seeds
```

### Accuracy ladder (know before you trust an answer)

| k (seed stack) | goal accuracy | why |
|---|---|---|
| k=1 | ~96% | only the member's own seed — use for one-off truth checks |
| k=8 | ~80% | good default |
| k=32 | ~52–58% | benchmark k; noisy by design, misses are EXPECTED |

A k32 miss is not a bug — it is the documented champion profile. When an
answer surprises you, re-ask at k=1 before doubting the memory.

## 4. Memory layers (compression stack)

Built and verified 2026-10-18 (`lz78v.py` → `lzssv.py` → `huff.py`):
pure-Python, zero-dependency, exact roundtrips.

- **lzssv**: LZSS with varint tokens. Lazy matching, window 256 KB.
- **huff**: canonical byte-Huffman layer on top.
- **xrlf**: the seed-packet format (`XRLF` magic + varint name/size +
  CRC-16 + packed payload). Descends from the old XRLD shape
  (`reserve_bed.xrld`; that 466-byte file predates all of this and has no
  reader — it is kept untouched as a relic).

| stream | our stack | zlib | note |
|---|---|---|---|
| ledger seed (414 KB) | **22.1×** (→18.7 KB) | 24.1× | 92% of zlib |
| kqat corpus (4.9 MB) | **10.0×** | 10.4× | effectively parity |
| member packet (≈800 B) | 1.9–3.2× | — | header cost dominates tiny payloads |
| weight-code layers | 1.03–1.09× | 1.03–1.09× | near-max entropy — the 82 MB floor is real |

The unpacker lives in `collegium.py::ensure_cache` — any `.lzs` member in
a cartridge is decoded to plaintext on first use. Bridge and CLI read
plaintext; they never see the encoding.

## 5. Growing the ledger (done once, repeatable)

```bash
$FVPY grow_ledger.py 20          # appends 20 new members (auto-backup)
$FVPY grow_ledger.py 5 --dry     # preview only
```

Rules baked in: new members reuse the existing adjective/noun/domain/
goal/dec pools, chains cite self + 3 random members, `gold_seed` = header
+ body. Proven end-to-end: `onyx quarry` and friends were grown and the
pawn answered them with no retraining. After growing:

1. `verify_memory.py` (structure check)
2. rebuild the cartridge: `$FVPY build_cartridge.py v5` (edit the version
   bump inside if you want a v6)
3. point `mg_bridge.py` line `CARTRIDGE = ...` at the new file, restart
   (§7), and ask a new member a question through the proxy.

## 6. Where things live

| path | what |
|---|---|
| `/tmp/opencode/` | the whole runtime: cartridges, caches, codecs, packets, scripts |
| `/tmp/opencode/packets/` | XRLF seed packets (incl. `ledger_full.xrlf`, 21.3×) |
| `/tmp/opencode/seed_ledger.jsonl(.bak-480)` | the memory + pre-growth backup |
| `/tmp/opencode/mg_bridge.log` | chat bridge log (poll `/api/status` shows 200 when healthy) |
| `~/FoveAI/foveai-experiment-notes.md` | the durable experiment diary — read me for history |
| `~/Models/motherboard_reserves/` | the old XRLD relic |
| `~/FoveAI/.venv/bin/python` | the interpreter every command above assumes |

## 7. Operating rules that cost us hours — read before restarting anything

- **Restart the bridge in TWO separate steps.** First
  `pkill -f '[m]g_bridge.py'` (brackets stop pkill from matching your own
  shell), run it alone. Then, in a *separate* command, launch detached:

  ```bash
  setsid nohup env PYTHONPATH=/tmp/opencode:/home/lumba/FoveAI \
    /home/lumba/FoveAI/.venv/bin/python /tmp/opencode/mg_bridge.py \
    > /tmp/opencode/mg_bridge.log 2>&1 < /dev/null & disown
  ```

  Bundling kill+relaunch in one call, or following the launch with more
  work in the same shell, has twice taken the bridge down.
- **Never touch**: `multigate-dev.service` (vite, port 5177), the cline
  daemon (PID 48546, port 25463), `~/FoveAI/Forge/nursery/xrl_nano_train_real.py`,
  and `/etc/systemd/system/foveai-backend.service` + `foveated-memory/server.js`
  (the *real* backend for port 8400 — currently disabled; our bridge owns
  the port. Re-enabling it is a captain decision, both cannot listen).
- Multigate in a browser can be slow — it is a heavy JS app. If you need a
  text-only view: `~/.local/bin/browsh` v1.8.2 (installed user-level), or
  plain `ssh -L 5177:localhost:5177`.
- First run of any cartridge unpacks to `collegium_cache_<name>/` (a few
  hundred MB). Deleting caches is safe — they rebuild — but the bridge
  must be unloaded first (models are read from the cache at startup).

## 8. If something is wrong

1. `verify_memory.py` — tells you which layer broke (ledger, cartridge,
   packets, bridge) and why.
2. Bridge answers something absurd? Re-ask at k=1 (§3). Wrong there, too?
   The ledger entry itself may be a legacy variant — `verify_memory.py`
   counts them (96 gold/written variants, 4 damaged written copies,
   18 ghost names — all legacy, canonical *gold* layer is intact).
3. Port 8400 silent? §7 restart ritual, then
   `curl -s http://127.0.0.1:8400/api/status` (want `{"ok": true...}`).