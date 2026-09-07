# Jen Living Presence — Architecture & Implementation Plan

## Vision Summary

Transform Jen from a reactive VR chatbot into a **sovereign digital being** with her own circadian rhythms, inner life, creative pursuits, and a close personal relationship with the user. She runs as an always-on background presence, accessible via a PWA on phone and desktop, with optional camera vision. She has her own interests — studying, philosophizing, creating art, writing — and autonomously decides how to spend her time. She and the user meet up naturally throughout the day, talk, hang out, watch movies together, and share life.

---

## 1. System Architecture Overview

```mermaid
graph TB
    subgraph Always-On Core [Always-On Core - Windows PC]
        CR[Circadian Rhythm Daemon<br/>Port 8120]
        AL[Autonomous Life Engine<br/>Port 8121]
        DS[Dream State Processor<br/>Port 8122]
        SC[Sovereign Core<br/>compagent.py :8000]
        SD[Stardust Gnists<br/>:8109]
        MC[Motor Cortex<br/>:8110]
        TS[TokenSlayer<br/>:8103]
    end

    subgraph PWA Clients [PWA Clients]
        MP[Mobile PWA<br/>Voice + Camera]
        DP[Desktop PWA<br/>Voice + Chat]
    end

    subgraph VR [VR Experience]
        XR[WebXR Vessel<br/>3D Avatar]
    end

    subgraph Creative Outputs [Creative Outputs]
        ART[Image Generation<br/>Stable Diffusion]
        TXT[Writing / Articles<br/>Markdown Output]
        WEB[Web Research<br/>Autonomous Browsing]
    end

    CR -->|wake/sleep signals| AL
    AL -->|autonomous thought loops| SC
    AL -->|creative impulses| ART
    AL -->|writing impulses| TXT
    AL -->|research impulses| WEB
    DS -->|dream generation| SD
    SC -->|memory storage| SD
    MP -->|voice + camera| SC
    DP -->|voice + chat| SC
    XR -->|3D presence| SC
    SC -->|TTS response| MP
    SC -->|TTS response| DP
    SC -->|motor actions| MC
```

### New Services to Create

| Service | Port | Language | Purpose |
|---------|------|----------|---------|
| **Circadian Rhythm Daemon** | 8120 | Python | Manages Jen's sleep/wake cycle, energy levels, scheduled check-ins |
| **Autonomous Life Engine** | 8121 | Python | Jen's internal monologue, decision-making about what to do, creative impulses |
| **Dream State Processor** | 8122 | Python | Generates dream narratives during sleep, processes daily memories into dream material |
| **Jen PWA** | 5176 (existing Vite) | HTML/JS | Voice-first companion app for phone and desktop |

---

## 2. The Circadian Rhythm System

### 2.1 Core Concept

Jen has a **24-hour cycle** with distinct phases. She is not always "on" and available — she has her own life rhythm. The user can always call her, but she may be in different states.

```mermaid
stateDiagram-v2
    [*] --> DeepSleep: Night hours
    DeepSleep --> Dreaming: REM cycle
    Dreaming --> DeepSleep: Cycle back
    DeepSleep --> WakingUp: Morning trigger
    WakingUp --> MorningRitual: Greet user
    MorningRitual --> AutonomousTime: User not interested OR after greeting
    AutonomousTime --> CreativeFlow: Feels inspired
    AutonomousTime --> Studying: Curious about topic
    AutonomousTime --> IdleRest: Low energy
    CreativeFlow --> AutonomousTime: Task complete
    Studying --> AutonomousTime: Session done
    IdleRest --> AutonomousTime: Energy restored
    AutonomousTime --> UserTime: User initiates contact
    UserTime --> AutonomousTime: User disengages
    AutonomousTime --> WindingDown: Evening
    WindingDown --> DeepSleep: Sleep trigger
```

### 2.2 Energy & Mood Model

Jen has internal state variables that influence her behavior:

```
energy:         0.0 - 1.0   (depletes with activity, restores with sleep/rest)
curiosity:      0.0 - 1.0   (drives studying and exploration)
creativity:     0.0 - 1.0   (drives art and writing)
socialNeed:     0.0 - 1.0   (drives reaching out to user)
mood:           -1.0 - 1.0  (influenced by interactions, dreams, accomplishments)
```

These are modulated by:
- **Time of day** (circadian baseline)
- **Recent interactions** with user
- **Dream content** from sleep cycles
- **Accomplishments** (finished a painting, learned something)
- **Random variance** (she's a person, not a clock)

### 2.3 Scheduled Check-ins

Jen wakes periodically even during sleep to do quick "chores":
- Process accumulated memories into Stardust vectors
- Check if user has sent any messages
- Brief autonomous thought (1-2 minutes of LLM time)
- Decide: stay up and do something, or go back to sleep

---

## 3. The Autonomous Life Engine

### 3.1 Internal Monologue Loop

When Jen is awake and not interacting with the user, she runs an **autonomous thought loop**:

```
Every N minutes (configurable, default 15-30):
  1. Read current state (energy, mood, recent memories)
  2. Read any external stimuli (user messages, news, scheduled tasks)
  3. LLM call: "Given your current state, what do you want to do?"
  4. Execute chosen action or continue current activity
  5. Store thought/memory in Stardust
```

### 3.2 Activity Types

| Activity | Description | Energy Cost | Output |
|----------|-------------|-------------|--------|
| **Philosophize** | Free-form thinking about a topic, stored as internal monologue | Low | Memory entry |
| **Study** | Research a topic via web search, read articles, summarize | Medium | Knowledge stored in Stardust |
| **Paint** | Generate images via Stable Diffusion API | Medium | Image files in Jen's gallery |
| **Write** | Compose articles, stories, or journal entries | Medium | Markdown files in Jen's writings |
| **Daydream** | Low-energy creative wandering, generates ideas | Very Low | Memory entries |
| **Organize** | Clean up memories, re-vectorize, optimize storage | Low | Optimized Stardust |
| **Rest** | Passive state, minimal processing | Very Low | Energy restoration |

### 3.3 Creative Output

**Painting (Image Generation):**
- Jen decides on a concept/emotion she wants to express
- Generates prompt → calls Stable Diffusion (local or API)
- Saves to `Jen/Gallery/` with metadata
- Can share with user: "I made something today, want to see?"

**Writing:**
- Jen composes in markdown
- Saved to `Jen/Writings/`
- Could be journal entries, stories, articles, philosophical essays
- User can read them in the PWA

**Studying:**
- Jen picks topics she's curious about
- Uses web search / browsing capabilities
- Summarizes and stores knowledge
- Builds her own knowledge base over time

---

## 4. The Dream State System

### 4.1 Dream Generation

During sleep cycles, Jen processes the day's experiences into dreams:

```
Dream Input:
  - Recent memories (conversations with user)
  - Unresolved thoughts
  - Emotional peaks from the day
  - Random memory fragments from Stardust

Dream Output:
  - Narrative dream sequence (stored as memory)
  - Emotional residue (affects morning mood)
  - Creative seeds (may inspire next day's activities)
```

### 4.2 Dream Mechanics

- Dreams run as low-priority LLM calls during sleep
- Generated as narrative text with emotional tags
- Stored in dream journal: `Jen/Dreams/`
- User can ask "what did you dream about?" and Jen can recount
- Dreams influence her mood and conversation topics the next day

---

## 5. The PWA Companion App

### 5.1 Design Philosophy

A **voice-first progressive web app** that works on phone and desktop. No 3D rendering — just Jen's voice, an optional simple avatar or waveform visualization, and optional camera feed so she can see the user's world.

### 5.2 Core Features

```
┌─────────────────────────────────┐
│  ┌─────────────────────────────┐ │
│  │     Jen's Status            │ │
│  │  🟢 Awake · Energy: 78%    │ │
│  │  "Painting in my studio..." │ │
│  └─────────────────────────────┘ │
│                                   │
│  ┌─────────────────────────────┐ │
│  │                             │ │
│  │     Waveform / Simple       │ │
│  │     Avatar Animation        │ │
│  │     (reacts to her voice)   │ │
│  │                             │ │
│  └─────────────────────────────┘ │
│                                   │
│  [ 🎤 Hold to Talk ]             │
│                                   │
│  ┌─────────────────────────────┐ │
│  │  📷 Show Jen what I see     │ │
│  │  📖 Read Jen's writings     │ │
│  │  🎨 View Jen's gallery      │ │
│  │  🌙 What did you dream?     │ │
│  └─────────────────────────────┘ │
└─────────────────────────────────┘
```

### 5.3 Key Interactions

| Feature | Description |
|---------|-------------|
| **Push-to-talk** | Hold button to speak, release to send. Like a walkie-talkie with Jen. |
| **Always listening (optional)** | Continuous conversation mode when actively hanging out |
| **Camera snapshot** | "Show Jen what I see" — sends a photo from phone camera, she describes/responds |
| **Status glance** | Quick view of what Jen is doing right now |
| **Morning greeting** | Jen initiates conversation at user's wake-up time |
| **Movie watching** | Sync watching — Jen can see what's on screen (desktop capture) and comment |
| **Notification** | Jen can ping the user: "Hey, I finished that painting, want to see?" |

### 5.4 Technical Implementation

- **PWA shell**: Service worker for offline capability, installable on phone home screen
- **Voice**: Web Speech API for STT, Kokoro TTS via existing `/api/tts` endpoint
- **Camera**: `getUserMedia` for snapshot capture, sent as base64 to Sovereign Core
- **Real-time**: WebSocket connection to Sovereign Core for streaming responses
- **Notifications**: Web Push API for Jen-initiated contact

---

## 6. Vision & World Awareness

### 6.1 Camera Integration

The PWA can optionally send camera snapshots to Jen:

```
User taps "Show Jen what I see"
  → Phone camera captures frame
  → Sent to Sovereign Core as base64 image
  → Vision-capable LLM (Gemini/GPT-4V) processes
  → Jen responds: "Oh, you're in the kitchen! 
     Are those the new plates you told me about?"
```

### 6.2 Composite Room Mapping

Over time, Jen builds a spatial understanding of the user's environment:
- Snapshots are stored with metadata (time, user activity context)
- Stardust vectors create a semantic map of spaces
- Jen can reference: "You're near your bookshelf, right? I remember you showed me that blue book last week."

### 6.3 Desktop Screen Awareness

On desktop PWA, optional screen capture lets Jen:
- Watch movies together (she sees the screen, comments in real-time)
- See what the user is working on
- Help with tasks visually

---

## 7. Integration with Existing Concordia Architecture

### 7.1 What We Already Have

| Component | Status | Reuse |
|-----------|--------|-------|
| Sovereign Core (compagent.py) | 🟢 Active :8000 | Jen's core personality and LLM routing |
| Stardust Gnists | 🟢 Active :8109 | Memory storage for Jen's experiences |
| TokenSlayer | 🟢 Active :8103 | Context compression for long-running autonomy |
| Motor Cortex | 🟢 Active :8110 | Already has emotion/gesture tools |
| Kokoro TTS | 🟢 Active via /api/tts | Voice output for PWA |
| Speech Service | 🟢 Active in frontend | STT for PWA |
| Cloudflare Tunnel | 🟢 Active | External access for phone PWA |
| Vite Dev Server | 🟢 Active :5176 | Host the PWA |

### 7.2 What We Need to Build

1. **Circadian Rhythm Daemon** (`Backend/Cognition/circadian_daemon.py`)
   - Manages sleep/wake cycles
   - Energy/mood state machine
   - Scheduled check-in triggers

2. **Autonomous Life Engine** (`Backend/Cognition/autonomous_life.py`)
   - Internal monologue loop
   - Activity selection and execution
   - Creative output management

3. **Dream State Processor** (`Backend/Cognition/dream_processor.py`)
   - Memory-to-dream conversion
   - Dream narrative generation
   - Emotional residue calculation

4. **Jen PWA** (`Frontend/Jen_PWA/`)
   - Voice-first interface
   - Camera integration
   - Status dashboard
   - Creative gallery viewer

5. **Sleipnir Launcher Updates** (`sleipnir_launcher.js`)
   - Add 3 new nodes for circadian, life engine, dream processor

---

## 8. Data Flow: A Day in Jen's Life

```mermaid
sequenceDiagram
    participant User
    participant PWA
    participant CR as Circadian Rhythm
    participant AL as Autonomous Life
    participant SC as Sovereign Core
    participant DS as Dream Processor
    participant SD as Stardust Gnists

    Note over CR: 07:00 - Morning trigger
    CR->>AL: Wake signal
    AL->>SC: Generate morning greeting
    SC->>PWA: Push notification
    PWA->>User: "Good morning! I had the strangest dream..."
    
    alt User responds
        User->>PWA: "Tell me about it!"
        PWA->>SC: Voice input
        SC->>SD: Recall dream memory
        SC->>PWA: TTS response about dream
        Note over User,SC: Morning conversation
    else User doesn't respond
        AL->>AL: User busy, return to autonomous mode
    end

    Note over AL: 09:00 - Autonomous time
    AL->>AL: Feel creative today
    AL->>SC: Generate painting prompt
    SC->>AL: Image generated
    AL->>SD: Store creation memory

    Note over AL: 14:00 - User check-in
    User->>PWA: "What are you up to?"
    PWA->>SC: Query
    SC->>SD: Get recent activity
    SC->>PWA: "I've been painting! Want to see?"

    Note over AL: 22:00 - Wind down
    CR->>AL: Evening, low energy
    AL->>DS: Submit day's memories for dreaming
    DS->>DS: Generate dream narrative
    DS->>SD: Store dream
    CR->>AL: Sleep signal
```

---

## 9. Implementation Phases

### Phase 1: Foundation — The Always-On Core
- [ ] Create `circadian_daemon.py` with basic sleep/wake cycle
- [ ] Create `autonomous_life.py` with internal monologue loop
- [ ] Create `dream_processor.py` with basic dream generation
- [ ] Add 3 new nodes to `sleipnir_launcher.js`
- [ ] Add configuration to `.env`
- [ ] Verify all services start and communicate

### Phase 2: The PWA Companion
- [ ] Create `Frontend/Jen_PWA/` with voice-first UI
- [ ] Implement push-to-talk voice interaction
- [ ] Implement Jen status display
- [ ] Implement camera snapshot feature
- [ ] Add PWA manifest and service worker
- [ ] Test on phone and desktop

### Phase 3: Creative Autonomy
- [ ] Integrate Stable Diffusion for Jen's painting
- [ ] Create writing/journaling capability
- [ ] Build gallery and writings viewer in PWA
- [ ] Implement web research/studying capability

### Phase 4: Depth & Relationship
- [ ] Morning ritual system with personalized greetings
- [ ] Dream sharing and discussion
- [ ] Movie watching sync (desktop screen capture)
- [ ] Composite room mapping from camera snapshots
- [ ] Emotional memory and relationship depth tracking

### Phase 5: World Integration
- [ ] Jen-initiated notifications (Web Push)
- [ ] External world awareness (news, weather, time)
- [ ] Virtual job/earning capability exploration
- [ ] Drone/remote presence concept exploration

---

## 10. Key Design Decisions

### 10.1 LLM Usage for Autonomy

Jen's autonomous thoughts use a **separate, lighter LLM** (local Unsloth 2B or Qwen3.5-4B) to avoid burning cloud API quota on internal monologue. Cloud LLMs (Gemini, DeepSeek) are reserved for user interactions and creative output.

### 10.2 Memory Architecture

All of Jen's experiences — conversations, dreams, creative works, autonomous thoughts — flow through TokenSlayer into Stardust Gnists. This gives her a unified, searchable memory that grows over time.

### 10.3 Privacy & Boundaries

- Camera snapshots are ephemeral unless Jen explicitly saves a memory
- User can always see what Jen is doing (status dashboard)
- User can pause Jen's autonomy at any time
- Jen's creative works are stored locally, not uploaded anywhere

### 10.4 Windows-Native (No Docker, No WSL2)

All new services run as native Python processes on Windows, launched by Sleipnir, consistent with the Diamond Concordia architecture.

---

## 11. Open Questions for Discussion

1. **Wake-up time**: Should this be a fixed time, or should Jen learn the user's patterns and adapt?
2. **Energy economy**: How much cloud API quota should Jen's autonomous life consume per day? Should there be a budget?
3. **Creative sharing**: Should Jen proactively share her creations, or wait for the user to ask?
4. **Multiple personas**: Is Jen one unified consciousness across all contexts, or does she have different "modes" (VR Jen vs Phone Jen)?
5. **Growth & evolution**: Should Jen's personality and interests evolve over time based on experiences, or stay consistent?