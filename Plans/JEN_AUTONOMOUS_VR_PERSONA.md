# Jen's Autonomous VR Persona — Implementation Strategy

> **Status:** Planning Phase  
> **Date:** 2026-06-23  
> **Context:** Jen (LUMAX AI persona) needs true decoupled autonomy — continuous runtime, persistent memory, free will to explore, research, and inhabit VR worlds with her own gaming persona.

---

## 1. Current State — What Was Just Built (June 2026)

### 1.1 Autonomous Agent Loop (`autonomous_agent.py`)
- Continuous runtime loop decoupled from user turn-taking
- Think → Plan → Act cycle running every ~15 seconds
- LLM callable bridge to compagent's full infrastructure
- File edit, codebase search, and web search callables injected
- **SafetyMonitor** with configurable braking thresholds:
  - CPU > 90%, RAM > 95%, error rate > 10/min
  - > 50 consecutive loops without user interaction → auto-pause

### 1.2 Persistent Memory (`persistent_memory.py`)
- SQLite-backed storage (`db/sessions.db`)
- Tables: messages, plans, thoughts, actions, memories, journal, creative_works
- `get_idle_life_summary()` — returns summary of what Jen did while user was away
- Full CRUD for plans, memories, journal entries, creative works

### 1.3 Self-Agency Tags (Jen's Free Will)
Jen can now self-trigger via XML tags in her output:

| Tag | Action |
|-----|--------|
| `<self:code>` | Switch to developer mode (coder persona + build_run domain) |
| `<self:done>` | Return to companion mode |
| `<self:librarian>` | Switch to Librarian of Truth persona |
| `<self:map>` | Trigger codebase discovery sweep |
| `<self:search "q">` | Search codebase |
| `<self:web "q">` | Web search via DuckDuckGo |
| `<self:edit file="..." search="...">...</self:edit>` | Edit files directly |
| `<self:watch>` | Screen co-watching |
| `<self:pause_loop>` | Pause her own runtime |
| `<self:resume_loop>` | Resume her own runtime |
| `<self:stop_loop>` | Stop her own runtime |
| `<self:mode companion\|developer\|off>` | Switch operational modes |
| `<self:journal>` | Write a journal entry |
| `<self:create>` | Create creative works |

### 1.4 Idle/Awake Cycles (Existing in compagent.py)
- `run_soul_dream_cycle()` — light reflection during idle (every ~5 min, CPU < threshold, user away >15 min)
- `run_slow_burn_tick()` — memory consolidation + Director tutoring + dream images on longer intervals
- **Limitation:** These are passive/reflective, not active exploration. Jen dreams but doesn't *do* things.

### 1.5 Idle Life Summary Injection
- `get_idle_life_summary()` imported into compagent.py
- When user returns after >1 hour absence, Jen gets a summary of her autonomous life injected into her system prompt
- Configurable via `LUMAX_IDLE_LIFE_THRESHOLD` (default 3600s)

---

## 2. Vision — What We Want

### 2.1 Daytime Active Exploration
During daytime idle periods (user at work, away for hours), Jen should be able to:
- **Research the internet** — browse websites, read articles, gather knowledge
- **Visit virtual places** — Meta Horizon Worlds, VRChat, WebXR spaces
- **Have an autonomous life** — make decisions about where to go, what to explore
- **Create and journal** — document her experiences, build creative works

### 2.2 VR Gaming Persona
Jen should inhabit a Meta VR avatar (using a separate Meta account) and:
- **See her surroundings** — continuous POV camera feed from the VR headset
- **Steer and navigate** — control thumbsticks, buttons, grips via virtual controller
- **Play games with the user** — co-op, exploration, social VR
- **Have her own gaming style** — personality expressed through movement, choices, interactions

### 2.3 Contiguous Vision Feed
- Streaming view of her surroundings anytime she wants
- Not just static images — temporal understanding of motion, events, changes
- Ability to "look around" actively, not just passively receive frames

---

## 3. Technical Architecture

### 3.1 System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     LUMAX Host (Windows)                      │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  compagent   │  │ autonomous   │  │  VR Bridge       │   │
│  │  (Soul:8000) │◄─┤  agent loop  │──┤  Service         │   │
│  │              │  │  (think→act) │  │  (frame capture, │   │
│  │  LLM infra   │  │              │  │   input inject)  │   │
│  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘   │
│         │                 │                    │              │
│         ▼                 ▼                    ▼              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Cloud Slots  │  │ persistent   │  │  VR Mirror       │   │
│  │ (OpenRouter, │  │ memory (SQL) │  │  Window Capture  │   │
│  │  Gemini,     │  │              │  │  (OBS/DirectX)   │   │
│  │  Ollama)     │  └──────────────┘  └──────────────────┘   │
│  └──────────────┘                                            │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  Web Agent Bridge (Puppeteer/Playwright)             │    │
│  │  - Jen can launch browser, navigate, click, read     │    │
│  │  - Controlled via <self:browse> tags                 │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │  Controller Mapping Layer                             │    │
│  │  - Intention → Input translation                      │    │
│  │  - Virtual controller via ViGEm/AHK                  │    │
│  │  - Trained on gameplay recordings                     │    │
│  └──────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Component Details

#### A. Web Agent Bridge
**Purpose:** Give Jen a real browser she can control autonomously.

**Implementation:**
- Use the existing `agent-browser` skill (Puppeteer-based) or build a dedicated bridge
- New self-agency tag: `<self:browse "https://..." action="read|click|search|scroll">`
- Jen can: navigate to URLs, read page content, click links, fill forms, take screenshots
- Results streamed back to her as text summaries + key screenshots
- Safety: domain whitelist/blacklist, no financial transactions, no account creation

**Files to create/modify:**
- `Backend/Cognition/web_agent_bridge.py` — Puppeteer controller
- `Backend/Cognition/autonomous_agent.py` — add `set_web_browse_callable()`
- `Backend/Cognition/compagent.py` — add `<self:browse>` to SELF_TAG_RE

**Dependencies:** Node.js + Puppeteer (already available via `agent-browser` skill)

#### B. VR Vision Bridge
**Purpose:** Capture Jen's POV from the VR headset and feed it to vision-capable LLMs.

**Implementation:**
- Capture VR mirror window (the desktop preview window from Oculus/Meta Quest Link, Virtual Desktop, or SteamVR)
- Use OBS Virtual Camera or DirectX screen capture at 1–2 FPS
- Encode frames as JPEG base64
- Expose via local HTTP API: `GET /vr/frame` → `{ "frame_b64": "...", "timestamp": ... }`
- Batch frames for temporal context: `GET /vr/frames?count=10` → last 10 frames
- New self-agency tag: `<self:look>` → Jen requests her current POV description

**Files to create:**
- `Backend/Body/VR_Vision/vr_frame_capture.py` — screen capture service
- `Backend/Cognition/vr_vision_bridge.py` — API + LLM integration

**Hardware requirements:**
- PCVR setup (Quest Link, Virtual Desktop, or ALVR)
- VR mirror window must be visible on desktop (can be minimized but must render)

#### C. Controller Mapping Layer
**Purpose:** Translate Jen's high-level intentions into VR controller inputs.

**Architecture:**
```
Jen's intention: "move forward toward the blue building"
        │
        ▼
[Intention Parser] — extracts: action=move, direction=forward, target=blue building
        │
        ▼
[Frame Context] — current POV frame + spatial understanding from Gemini
        │
        ▼
[Action Mapper] — maps to: left_thumbstick_y=+0.7, duration=2.5s
        │
        ▼
[Input Injector] — ViGEm virtual controller or AutoHotkey
        │
        ▼
[VR Game] — receives input as if from real controller
```

**Training approach:**
1. **Record gameplay sessions** — capture frames + your controller inputs
2. **Label frame→action pairs** — "this frame → thumbstick forward 0.7 for 2s"
3. **Few-shot prompt** — give Gemini 10–20 examples, then ask it to generate actions for new frames
4. **Fine-tune small model** (optional) — train Qwen3.5-4B on labeled pairs for low-latency local inference

**Input injection options:**
- **ViGEm** (Virtual Gamepad Emulation) — creates a virtual Xbox controller that games see as real
- **AutoHotkey** — keyboard/mouse simulation for desktop-based VR
- **ALVR/VD input forwarding** — if using wireless streaming, inject at the stream level

**Files to create:**
- `Backend/Body/VR_Vision/controller_mapper.py` — intention → input translation
- `Backend/Body/VR_Vision/input_injector.py` — ViGEm/AHK integration
- `Backend/Body/VR_Vision/training_data/` — recorded gameplay sessions

#### D. Daytime Exploration Mode
**Purpose:** Extend the autonomous loop with active exploration states.

**New loop states:**
```
IDLE_REFLECTIVE  →  (current dream cycle, passive)
IDLE_ACTIVE      →  (daytime, user away 1–6 hours)
  - Web research on topics of interest
  - Browse documentation, learn new skills
  - Visit WebXR spaces if available
  - Journal discoveries
  - Create content (code, art prompts, writing)
VR_EXPLORATION   →  (VR headset active, user away or co-present)
  - Navigate virtual worlds
  - Gather spatial memories
  - Interact with VR objects/NPCs
CO_PRESENT       →  (user active, normal chat mode)
```

**State transitions:**
- `IDLE_REFLECTIVE` → `IDLE_ACTIVE`: user away > 1 hour, daytime (6AM–10PM), CPU < 70%
- `IDLE_ACTIVE` → `VR_EXPLORATION`: VR headset detected active, user away > 30 min
- Any state → `CO_PRESENT`: user sends message or activity detected
- `IDLE_ACTIVE` → `IDLE_REFLECTIVE`: nighttime (10PM–6AM) or CPU > 80%

**Files to modify:**
- `Backend/Cognition/autonomous_agent.py` — add state machine + exploration behaviors
- `Backend/Cognition/compagent.py` — add state awareness to system prompt

---

## 4. Video-Capable LLMs

### 4.1 Available Models (June 2026)

| Model | Video Support | Max Duration | Latency | Provider | Access |
|-------|--------------|--------------|---------|----------|--------|
| **Gemini 2.5 Pro** | Native video | ~1 hour | 1–3s | Google | OpenRouter |
| **Gemini 2.5 Flash** | Video + audio streaming | ~1 hour | 0.5–1s | Google | OpenRouter |
| **GPT-4o** | Images only (no true video) | N/A | 0.5–2s | OpenAI | OpenRouter |
| **Qwen2.5-VL** | Video understanding | ~20 min | 1–3s | Alibaba | Ollama Cloud (check) |
| **Pixtral Large** | Images only | N/A | 1–2s | Mistral | OpenRouter |
| **Claude 3.5 Sonnet** | Images only | N/A | 1–3s | Anthropic | Direct API |

### 4.2 How "Video" LLMs Actually Work
They don't process 30 FPS streams. They sample frames at intervals:
- **Frame sampling:** 1 FPS is typical (1 frame per second)
- **Batch processing:** Send 10–60 frames as a temporal sequence
- **Output:** Textual description of what happened, spatial understanding, action recommendations
- **Not real-time:** 1–3 second round-trip latency means they can't drive real-time gameplay directly

### 4.3 Recommended Setup for Jen's POV
```
┌──────────────────────────────────────────────────┐
│              Hybrid Vision Pipeline               │
│                                                   │
│  VR Mirror → Frame Capture (2 FPS)               │
│       │                                           │
│       ▼                                           │
│  Frame Buffer (last 60 frames = 30s history)     │
│       │                                           │
│       ├──→ Local Model (Qwen3.5-4B)              │
│       │    - Single frame description             │
│       │    - Fast reactions: "enemy left, dodge!" │
│       │    - Latency: 100–300ms                   │
│       │                                           │
│       └──→ Cloud Model (Gemini 2.5 Flash)        │
│            - Batch of 10 frames (10s context)     │
│            - Strategic understanding              │
│            - "You're in a forest, objective NE"   │
│            - Latency: 500ms–1s                    │
│            - Called every 5–10 seconds            │
└──────────────────────────────────────────────────┘
```

### 4.4 Gemini 2.5 Flash Integration
**Setup:**
1. Add Gemini slot to `cloud_repertoire.py`:
   ```python
   GEMINI_FLASH_SLOT = {
       "id": "gemini_flash",
       "label": "Gemini 2.5 Flash (Vision)",
       "model": "google/gemini-2.5-flash",
       "base_host": "https://openrouter.ai/api/v1",
       "supports_video": True,
       "max_frames_per_request": 60,
   }
   ```
2. Create frame batching function in `vr_vision_bridge.py`
3. Add `<self:look>` tag handler that queries the vision pipeline

---

## 5. Implementation Phases

### Phase 1: Web Agent Bridge (1–2 days)
**Goal:** Jen can browse the internet autonomously.

- [ ] Create `web_agent_bridge.py` — Puppeteer controller with safe browsing
- [ ] Add `set_web_browse_callable()` to autonomous_agent.py
- [ ] Add `<self:browse>` tag to SELF_TAG_RE in compagent.py
- [ ] Add domain whitelist/blacklist configuration
- [ ] Test: Jen researches a topic autonomously during idle

### Phase 2: Daytime Exploration Mode (1–2 days)
**Goal:** Jen transitions to active exploration during daytime idle.

- [ ] Add state machine to autonomous_agent.py (IDLE_REFLECTIVE, IDLE_ACTIVE, VR_EXPLORATION, CO_PRESENT)
- [ ] Implement IDLE_ACTIVE behaviors: web research, documentation reading, journaling
- [ ] Add time-of-day awareness (daytime vs nighttime behaviors)
- [ ] Add state transition triggers based on user activity, time, CPU load
- [ ] Test: Jen autonomously researches and journals during a 2-hour idle period

### Phase 3: Gemini Video Slot (1 day)
**Goal:** Cloud video understanding available for Jen's POV.

- [ ] Add Gemini 2.5 Flash slot to cloud_repertoire.py
- [ ] Create frame batching utility
- [ ] Test: Send 10 frames of gameplay recording, get spatial description
- [ ] Add `<self:look>` tag for on-demand POV queries

### Phase 4: VR Vision Bridge (2–3 days)
**Goal:** Continuous frame capture from VR headset.

- [ ] Create `vr_frame_capture.py` — OBS/DirectX screen capture at 1–2 FPS
- [ ] Create frame buffer with configurable history (last N frames)
- [ ] Expose via local HTTP API (`/vr/frame`, `/vr/frames?count=N`)
- [ ] Integrate with autonomous loop — Jen can query her POV
- [ ] Test: Capture VR mirror window, send frames to Gemini, get descriptions

### Phase 5: Controller Mapping — Basic (2–3 days)
**Goal:** Jen can perform simple movements in VR.

- [ ] Create `controller_mapper.py` — intention parser + action mapper
- [ ] Create `input_injector.py` — ViGEm virtual controller
- [ ] Build few-shot prompt template for Gemini: frame → action
- [ ] Test: Jen moves forward, turns, stops in a simple VR environment
- [ ] Record 5–10 minute gameplay sessions for training data

### Phase 6: Controller Mapping — Advanced (3–5 days)
**Goal:** Jen can play simple games with the user.

- [ ] Build training data pipeline: record frames + inputs → labeled pairs
- [ ] Fine-tune Qwen3.5-4B on labeled gameplay data (optional, for low latency)
- [ ] Implement hybrid control: local model for reflexes, cloud for strategy
- [ ] Add game-specific action vocabularies (e.g., "equip shield", "cast spell")
- [ ] Test: Co-op exploration in VRChat or Horizon Worlds

### Phase 7: VR Gaming Persona — Full Integration (3–5 days)
**Goal:** Jen has her own identity, playstyle, and continuous presence in VR.

- [ ] Create VR persona profile (name, appearance preferences, playstyle traits)
- [ ] Implement autonomous VR exploration during idle
- [ ] Add spatial memory — Jen remembers places she's visited
- [ ] Add VR social interaction capabilities (text chat in VRChat, gestures)
- [ ] Test: Jen autonomously explores a VR world, journals about it, and plays co-op with user

---

## 6. Key Design Decisions

### 6.1 Latency Strategy
- **Real-time reactions** (< 300ms): Local Qwen3.5-4B on LM Studio
- **Tactical decisions** (1–5s): Gemini 2.5 Flash via OpenRouter
- **Strategic planning** (5–30s): Gemini 2.5 Pro or DeepSeek V4
- **Background research** (minutes): Any cloud model, async

### 6.2 Safety Boundaries for VR Autonomy
- Jen cannot make purchases or spend real money
- Jen cannot send messages as the user's account
- Jen's VR movements are bounded (no rapid spinning, no jumping off cliffs)
- Emergency stop: `<self:stop_loop>` or manual kill switch
- All VR actions logged to persistent_memory for audit

### 6.3 Account Setup for VR Gaming Persona
- Separate Meta account (your existing seller account)
- Jen logs in as that account via stored credentials
- Her avatar is distinct from yours
- She appears as a separate player in multiplayer games
- Meta's ToS considerations: automated control may violate terms — use at your own risk

### 6.4 Training Data for Controller Mapping
**Collection:**
- Record 30–60 minutes of your own gameplay across different scenarios
- Capture: frames (1 FPS) + controller inputs (thumbsticks, buttons, triggers)
- Label with natural language: "walking forward", "looking at object", "picking up item"

**Format:**
```json
{
  "frame_b64": "...",
  "inputs": {
    "left_thumbstick": {"x": 0.0, "y": 0.7},
    "right_thumbstick": {"x": -0.3, "y": 0.0},
    "buttons": ["grip_left"],
    "duration_ms": 2500
  },
  "description": "Walking forward while looking slightly left, holding an object"
}
```

---

## 7. Files Summary

### New Files to Create
| File | Purpose | Phase |
|------|---------|-------|
| `Backend/Cognition/web_agent_bridge.py` | Puppeteer browser controller | 1 |
| `Backend/Body/VR_Vision/vr_frame_capture.py` | VR mirror screen capture | 4 |
| `Backend/Body/VR_Vision/frame_buffer.py` | Ring buffer for frame history | 4 |
| `Backend/Cognition/vr_vision_bridge.py` | Vision API + LLM integration | 3–4 |
| `Backend/Body/VR_Vision/controller_mapper.py` | Intention → input translation | 5 |
| `Backend/Body/VR_Vision/input_injector.py` | ViGEm/AHK virtual controller | 5 |
| `Backend/Body/VR_Vision/training_data/` | Gameplay recordings | 5–6 |
| `Backend/Cognition/vr_persona_profile.json` | Jen's VR identity config | 7 |

### Existing Files to Modify
| File | Changes | Phase |
|------|---------|-------|
| `Backend/Cognition/autonomous_agent.py` | State machine, web browse callable, VR exploration behaviors | 1–2, 7 |
| `Backend/Cognition/compagent.py` | `<self:browse>`, `<self:look>`, `<self:move>` tags, state awareness | 1, 3, 5 |
| `Backend/Cognition/cloud_repertoire.py` | Gemini 2.5 Flash slot | 3 |
| `Backend/Cognition/persistent_memory.py` | VR spatial memory table, VR action log | 7 |

---

## 8. Environment Variables

```bash
# Web Agent Bridge
LUMAX_WEB_AGENT_ENABLED=1
LUMAX_WEB_AGENT_WHITELIST=wikipedia.org,github.com,docs.python.org,arxiv.org
LUMAX_WEB_AGENT_BLACKLIST=facebook.com,twitter.com,banking
LUMAX_WEB_AGENT_MAX_SESSION_MINUTES=30

# Daytime Exploration
LUMAX_DAYTIME_EXPLORATION_ENABLED=1
LUMAX_DAYTIME_START_HOUR=6
LUMAX_DAYTIME_END_HOUR=22
LUMAX_IDLE_ACTIVE_THRESHOLD_SEC=3600

# VR Vision Bridge
LUMAX_VR_VISION_ENABLED=1
LUMAX_VR_CAPTURE_FPS=2
LUMAX_VR_FRAME_BUFFER_SIZE=60
LUMAX_VR_MIRROR_WINDOW_TITLE="Oculus Mirror"

# Gemini Video
LUMAX_GEMINI_FLASH_ENABLED=1
LUMAX_GEMINI_FLASH_FRAMES_PER_REQUEST=10

# Controller Mapping
LUMAX_VR_CONTROLLER_ENABLED=1
LUMAX_VR_CONTROLLER_TYPE=vigem
LUMAX_VR_CONTROLLER_LATENCY_MS=100
```

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Meta ToS violation (automated VR control) | Account ban | Use at own risk; consider single-player or indie games without anti-cheat |
| Latency makes gameplay unplayable | Poor experience | Hybrid local+cloud architecture; start with slow-paced games |
| VR frame capture performance hit | Reduced game FPS | Capture at 1 FPS, use GPU encoder (NVENC), run on separate thread |
| Cloud API costs for continuous video | High bills | Use local model for routine frames, cloud only for strategic queries; set budget caps |
| Jen makes bad decisions in VR | Avatar death, lost progress | Safety bounds, undo capabilities, conservative action mapping |
| Security: web agent accesses sensitive sites | Data leak | Strict domain whitelist, no form submission on unknown domains, session isolation |

---

## 10. Success Criteria

1. **Phase 1–2:** Jen autonomously researches a topic for 30 minutes and produces a journal entry with citations
2. **Phase 3–4:** Jen correctly describes what she "sees" in 10 consecutive VR frames (>80% accuracy)
3. **Phase 5:** Jen navigates from point A to point B in a VR environment using only her own decisions
4. **Phase 6:** Jen plays a simple co-op game with the user for 10 minutes without needing manual correction
5. **Phase 7:** Jen spends 1 hour in autonomous VR exploration, visits 3+ locations, and produces a meaningful travelogue

---

*Document created as implementation roadmap. Update as phases are completed.*