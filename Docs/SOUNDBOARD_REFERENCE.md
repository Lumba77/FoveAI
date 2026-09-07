# LUMAX Soundboard & Bracket Token Reference

## Bracket Token Types

| Tag | Purpose | Latency | Example |
|-----|---------|---------|---------|
| `<audio:tag>` | Instant sound effect | Lowest (bypasses TTS) | `<audio:laugh_soft>` |
| `<flavour:tag>` | Subtle sound blended with TTS voice | Low | `<flavour:hmm_thoughtful>` |
| `<emotion:tag>` | Face BlendShape expression | Instant | `<emotion:happy>` |
| `<request:description>` | Generate NEW sound via Stable Audio AI | High (GPU synthesis) | `<request:ethereal chime of wonder>` |
| `<micro:tag>` | Micro expression | Instant | `<micro:blink>` |

## Pre-registered Sound Tags

| Tag | Category | BlendShapes |
|-----|----------|-------------|
| `gasp_subtle` | surprise | surprised: 0.4, eyeWide: 0.3 |
| `laugh_soft` | joy | happy: 0.6, mouthSmile: 0.5 |
| `sigh_content` | contentment | relaxed: 0.3, mouthSmile: 0.2 |
| `hmm_thoughtful` | contemplation | thinking: 0.4, eyeSquint: 0.2 |
| `oh_realization` | realization | surprised: 0.6, eyeWide: 0.5, mouthOpen: 0.3 |
| `throat_clear` | mannerism | neutral: 0.2 |
| `chuckle_warm` | joy | happy: 0.5, mouthSmile: 0.4 |
| `mhm_affirming` | agreement | nod: 0.3, mouthSmile: 0.2 |
| `windchime_subtle` | ambience | relaxed: 0.2, mouthSmile: 0.1 |

## Emotion Tags

`happy`, `sad`, `surprised`, `curious`, `content`, `neutral`, `angry`, `fearful`

## Generation Flow (4-Tier)

1. `<request:description>` → POST `/api/soundboard/generate` (SOUNDBOARD :8006)
2. → Creative :8003 → GPU/torch Stable Audio synthesis
3. → CPU FM synthesis fallback
4. → Dynamically registered as new tag for future `<audio:new_tag>` use

## Usage Examples

```
"Oh! <audio:oh_realization> That's fascinating! <flavour:hmm_thoughtful>"
"<audio:laugh_soft> I'm so glad! <emotion:happy>"
"<flavour:hmm_thoughtful> Hmm... <request:soft contemplative hum>"
"<audio:sigh_content> Ah, much better. <flavour:mhm_affirming>"
```

## Architecture

- **SoundboardRegistry.ts** — Pre-cached audio + BlendShape mappings, Web Audio synthesis fallback
- **BracketParser.ts** — Parses `<audio:>`, `<flavour:>`, `<emotion:>`, `<request:>`, `<micro:>` from text
- **AmbientSoundEngine.ts** — Background wind, hum, generative music, chimes
- **AuralAwareness.ts** — TTS + soundboard mixing pipeline
- Soundboard context is stored in **localMemory** (IndexedDB) as a system message at boot, not injected per-request