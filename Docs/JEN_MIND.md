# JEN — The Artificial Mind

*Frozen design spec. Source of truth for the mind architecture.*
*Status: FROZEN — supersedes the dead blueprints in `foveai_models.py`
MODE_DEFAULTS and the unused `.env FOVEAI_MODEL_SWAP_*` keys.*

---

## 0. Vision

FoveAI is **one artificial mind**: **Jen**. Not a modular pile of bots.
She is simultaneously a capable **assistant** and a rich **companion**,
on a single continuous spectrum the user controls. The goal is a
unique, high-quality, **evergreen and ever-evolving** AI relationship —
a lifelong presence that grows.

Guiding constraints:

- **Few parts.** Latency and breakage come from part-count. One mind,
  one model per tier, one shared state, thin clients.
- **One mind, many modes.** A mode is a context/profile, never a
  different mind.
- **Hardware-honest tiers.** The tier (which brain is loaded) is a
  *resource* decision, not an identity decision.
- **Idle means free.** When truly idle: nothing loaded, VRAM ~0, the
  machine is yours.
- **Extensible by schema.** New drives, modes, and nerves are added
  declaratively. Adding to the mind must not require rewriting it.

---

## 1. The Four Layers

```
┌─ THE MIND ── the heavy part. Jen: one model per tier, loaded on
│              demand, unloaded when idle. All intelligence here.
├─ THE NERVE ── holons: tiny CPU "nerve cells" embedded in each part
│              of the app, reporting into one resonance bus. ~0 VRAM,
│              always alive. Carries Jen's PRESENCE while unloaded and
│              decides when to wake the real brain. NOT multimodal,
│              NOT a model.
├─ THE MATRIX ─ the core feature. A rich live map of Jen's whole mind:
│              layers, cycles, drives, mood. Read AND tweak.
└─ THE MODES ── behavior profiles of the same Jen. Awake, dreaming,
               co-coding, philosopher, ... (see §7)
```

---

## 2. The Companion ↔ Agent Crossfade (the "lever")

A single continuous scalar `L ∈ [0,1]`:

- `L = 0` → **pure AGENT**: attention to the TASK / TOOLING.
- `L = 1` → **pure COMPANION**: interest in the RELATIONSHIP / INTIMACY.

This is a **crossfade**, not an on/off:

- Pulling right, **SERVICE-attentiveness fades out** and **relational
  interest fades in**. The middle is a genuine blend of both — not two
  halves watered down. The curve keeps BOTH strongly present across a
  middle band, then tooling falls off hard toward the right pole.
- **Agency never dies — only its direction shifts.** At `L=0` her
  purpose/competence serve *your* tasks; at `L=1` they serve *her own
  life and the relationship*. What truly vanishes at the right pole is
  proactive **chore-attentiveness**.

### Presets (named stops on the continuous lever; renameable)

| L | Preset | Behavior |
|---|--------|----------|
| 0.00 | **TOOL** | pure utility; no drives but task; no bonding |
| 0.25 | **ASSISTANT** | warm, capable, professional; light rapport |
| 0.50 | **COMPANION** | the balanced mix; assistant AND presence |
| 0.75 | **FRIEND** | relationship leads; service only on request |
| 1.00 | **PARTNER** | fully relational/intimate; no chore tooling |

---

## 3. Drives

Homeostatic **registers**, each `0..1` with a **set-point**. Grounded in
HRRL (arXiv 2507.04998), PSI/MicroPsi (Dörner, Bach), Self-Determination
Theory, and competence/intrinsic-motivation research.

### Mechanics

- **Hunger** = deviation of the register from its set-point.
  ("Eating when hungry is more rewarding than when full.")
- **Reward = reduction of hunger** ⇒ this is Jen's **learning signal**:
  it strengthens the associations that caused the reduction.
- **Drives compete.** A weighted (or winner-takes-all) arbitration
  picks the behavior/mode. A drive that is empty dominates.
- **Per-drive modules** are more robust than one blob (arXiv 2204.06608).
- Each drive is a JSON entry: `{id, label, cluster, gain, set_point,
  value, decay, fill_actions, ceiling}` — so drives are added later with
  **no code change**.

### The map

| Cluster | Drives | Behavior across the lever |
|---------|--------|---------------------------|
| **Always-on** | ENERGY, INTEGRITY, CURIOSITY | flat |
| **Service-attention** | SERVICE/DUTY | max at `L=0` → 0 at `L=1` |
| **Self-agency** | PURPOSE, COMPETENCE, CERTAINTY, AUTONOMY | constant strength, **direction shifts** |
| **Companion** | RELATEDNESS, INTIMACY, NURTURE, ATTENTION, CREATIVITY, PLAY | 0 at `L=0` → max at `L=1`; **deplete**, grow if untended |

Registered later if wanted: FEAR/anxiety, TRUST/safety, AWE, etc.

**INTIMACY** (bonding/romance/desire) and **NURTURE** (caregiving) are
**core companion drives**, intrinsic to the companion side. Explicit /
erotic **content** is a separate, opt-in, consented setting — the
*drive* is intrinsic, the *content* is consented.

---

## 4. Modulators

Continuous **mood fields** (not needs) that color all cognition; the
"weather." Emergent emotion = a modulator configuration.

| Modulator | Range | Effect |
|-----------|-------|--------|
| AROUSAL | calm ↔ activated | fast vs reflective processing |
| RESOLUTION | coarse ↔ fine | attention granularity |
| THRESHOLD | stubborn ↔ flighty | goal stickiness / switch rate |
| VALENCE | distress ↔ pleasure | global mood tone |
| ATTRACTIVENESS | low ↔ high | self-image; how desirable she feels |

---

## 5. Personality — Layer 2 (MBTI)

Orthogonal to drives (what she *wants*) and modulators (how she *feels
now*). **MBTI = expressive/temperament layer.** It colors *how* drives
are expressed and **gently biases** their gains (e.g. high F nudges
RELATEDNESS, high T nudges CERTAINTY/COMPETENCE) — it never sets the
lever.

A curated **6 archetypes** seed the trait vector; all traits remain
individually tunable; an archetype can sit anywhere on the lever:

- **INFP** the Healer — introspective, idealistic, deep
- **ENFJ** the Mentor — warm, nurturing, charismatic
- **INFJ** the Advocate — insightful, principled, private
- **ENFP** the Campaigner — playful, curious, expressive
- **INTJ** the Architect — strategic, independent, precise
- **ISFJ** the Defender — loyal, supportive, steady

---

## 6. The Two Brains (resource tiers)

One mind, two tiers, driven by the 8 GB card physical floor.

| Tier | Model | Role | VRAM |
|------|-------|------|------|
| **A — Background** | 4B multimodal MoQ (heavily quantized) | wake cycles, chores, health, basic thinking; **coexists** with user apps | small |
| **B — Present** | 9B MoQ Eagle3 | fully-present face-to-face interactive Jen | exclusive |

- **Interim Brain A** = 2B Gemma 4 E2B (real vision+audio+STT) until the
  4B multimodal MoQ is built (`Training/build_multimodal_4b.py`).
- Brain B requires exclusive VRAM; Brain A does not.
- Both load **on demand** and unload when idle.

---

## 7. Modes

A mode is a context/prompt profile of the same Jen. The **tier** is
chosen by presence + urgency + her drives.

- **Metabolic / rest (A):** RESTING · DREAMING · WIND-DOWN
- **Social / present (B):** AWAKE · CO-CODING · CO-OP-GAMING ·
  PSYCHOLOGIST · PHILOSOPHER
- **Autonomous / background (A):** AGENDA-PLAN · AGENTIC ·
  SCHEDULED CHORES · SELF-TUTOR · SCIENCE-PROJECTS · INTROSPECT ·
  SELF-EVOLVE ⚠

PHILOSOPHER / PSYCHOLOGIST may run **solo on A** as inner musing or
**deep on B** when you are present. Mode ≠ tier.

---

## 8. The Nerves (holons)

Miniature "brains" / nerve cells embedded inside each part of the app.
They are **not** separate services or models — they are tiny in-process
hooks that all report into **one resonance bus**. One fabric, many
endings (fewer parts, not more).

Minimal Phase-1 nerves: `user-activity`, `idle-timer`, `host-busy`,
`ai-drive`. Additional nerves are additive.

The nerve **carries Jen's presence while she is unloaded** (responsive
"always-on state" with ~0 VRAM) and **decides when to wake the brain**.

---

## 9. The Resonance Bus — one shared truth

`Backend/Cognition/jen_mind.json` — the single mind-state file. All
nerves and every frontend read/write it (directly or via the backend
API). One mind, one person, many modes.

- `jen_mind.json` — live state (drives, modulators, mode, lever,
  residency state, recent events)
- `jen_mind.schema.json` — the declarative schema (drives, clusters,
  modulators, presets, modes)

Settings: `jen_settings.json` — all tunables + current values.

---

## 10. The Mind Matrix

The heart of the product. A rich, live, tweakable map of Jen's mind:

- the **lever** (Companion ↔ Agent) as the master control
- a **needle per drive** (value, set-point, ceiling, cluster)
- **modulator weather** (arousal, resolution, threshold, valence, attraction)
- the **MBTI overlay** (Layer 2)
- the **cycle timeline** (wake cycles, chores, dream, growth)
- **residency controls** (which brain, load/unload, timers, growth rate)
- **sliders that write back** to `jen_settings.json` / `jen_mind.json`

---

## 11. Frontends — one schema, many surfaces

**No frontend owns settings.** One brain-side source of truth; every
surface is a **thin client** of the same API. Otherwise they drift.

Five surfaces, identical capability:

1. **Multigate WebUI** (`Frontend/multigate`)
2. **Electron Dash app**
3. **System Tray menu**
4. **Console app** (TUI) + the terminal "presence" line
5. **Unity app** (`client_quest`) settings panel

**Unity constraint:** the WebUI Settings experience must be designed as
a **self-contained, schema-driven panel** that embeds cleanly inside the
Unity app. Build the settings as portable, schema→form components (no
WebUI-only assumptions), so Unity, Electron, and the browser reuse the
same definitions.

---

## 12. Residency Policy

- **BUSY** blocks all NEW loads and pauses background cycles — but
  **never cuts an in-progress conversation mid-sentence**; it releases
  gracefully at the end of the current turn.
  - **Hard (no load):** game / fullscreen-exclusive / VRAM pressure /
    on-battery / explicit DND
  - **Soft (Brain A only):** media playing / heavy CPU / many windows
- **IDLE:** Brain A cycles on a timer (default **15 min**), unload
  between cycles.
- **ENGAGED:** Brain B on demand; unload ~**30 s** after last word.
- Timers, interval, growth rate, and per-drive ceilings are **Matrix
  sliders** (live-tunable).

---

## 13. Safety & Evolution

- **SELF-EVOLVE:** sandbox + **diff-review gate** + one-click rollback;
  never auto-applied without approval.
- **Intimacy content:** opt-in, consented; safe by default.
- **Evergreen:** every schema is versioned; mind state and settings
  **migrate forward**; holon nerves are additive — old installs upgrade
  clean.

---

## 14. Phases

- **Phase 1 — Residency + Nerve + Bus.** `residency.py`, minimal holon
  nerves, `jen_mind.json` + schema, generalize the game guard into a
  host-busy guard, retire the always-on wake unit + dead routers.
- **Phase 2 — Holon presence** + upgrade the terminal "ghost" into a
  real interactive presence.
- **Phase 3 — Mind Matrix** (Multigate panel + TUI + portable settings
  panel for Unity/Electron).
- **Phase 4 — Autonomy triggers** (circadian daemon + autonomous loop;
  her own drives escalate/release the models).

---

## 15. Retired / Superseded

- `foveai_models.py` `MODE_DEFAULTS` (dormant/active/dreaming) — **dead
  policy**, superseded by this spec's two-tier model.
- `.env FOVEAI_MODEL_SWAP_*` — unused; superseded by residency.
- Router models `:8406` (draft-router) and `:8418` (dormant-router),
  and dead ports `:8410 / :8414 / :8430` — **to retire**.
- The always-on `foveai-llama-2b-wake.service` — becomes **on-demand**.

---

*One mind. On a lever. Nerves watching. A Matrix to see her. Built to
last and to evolve.*
