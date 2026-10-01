# Generative AI Suite — UI, Graphics & Audio Development

## Vision
AI-driven construction of UI layouts, components, graphics, and audio effects that precisely accommodates the user's visual and sonic wishes through calculated, measured generation.

## Architecture (Future)

### 1. Design Token System
- Extract LUMAX's existing design system into computable tokens
- Colors (--neon-blue, --neon-pink, --neon-green), fonts (Orbitron, Share Tech Mono), spacing, borders
- AI references tokens by name → outputs pixel-perfect matching styles

### 2. Component Templates Library
- Pre-built LUMAX-styled component patterns (cards, panels, tabs, grids, modals)
- AI assembles from templates → guarantees visual consistency
- Templates stored as JSON specs: `{type: "card", variant: "neon", slots: ["title", "body"]}`

### 3. Generative UI Pipeline
```
User Wish → COMAX Intent Parser → Design Spec → Template Assembly → CSS/TS Output → Preview
```
- User describes visual intent in natural language
- AI translates to structured design specification (layout grid, component choices, color assignments)
- Spec validated against design tokens → guarantees consistency
- Output: ready-to-use TypeScript component code

### 4. Generative Graphics Pipeline
- Icon generation via image AI (DALL-E/Stable Diffusion API)
- Style-aware: generates in LUMAX's neon/cyberpunk aesthetic
- Output: SVG or PNG assets placed in frontend/assets/
- 3D asset generation for WebXR scenes (VRM poses, environment objects)

### 5. Generative Audio Pipeline (Stable Audio Integration)
LUMAX already has Stable Audio available. Extend it for UI sound effects:
- UI interaction sounds: clicks, hovers, transitions, notifications
- Ambient soundscapes: loading states, background atmospheres
- Audio token system (like design tokens): `--sound-click`, `--sound-hover`, `--sound-error`
- AI generates audio to match visual mood (neon=crisp electronic, warm=soft ambient)
- Prompt-driven: "cyberpunk menu open sound, short, metallic" → Stable Audio → .wav
- Auto-encodes to web-playable format, registers in soundboard
- User can preview, adjust duration, apply effects (reverb, filter)
- Integration with Chatterbox TTS pipeline for voice+sound layering

```
User Wish → Audio Intent → Stable Audio Prompt → Generation → Encode → Soundboard Slot
```

### 6. Live Preview & Diff
- Side-by-side preview: current UI vs proposed changes
- Audio preview: play generated sounds in context with UI actions
- Rendered in an iframe sandbox within COMAX
- One-click apply or reject per change

### 7. Smart Accommodation Engine
- Measures user's existing UI patterns (spacing ratios, color usage, density)
- Measures existing audio patterns (sound length, frequency, style)
- New generations match established patterns by default
- User can override with "make it more spacious", "use warmer tones", "softer sounds"
- Learning: tracks accepted/rejected designs and sounds to refine future suggestions

## Integration Points
- COMAX tab gets "🎨 Design" mode + "🔊 Audio" mode toggles
- REMAX can batch-generate component sets and sound packs non-interactively
- Chrome Extension captures screenshots for "make it look like this" requests
- Soul service provides aesthetic personality guidance
- Soundboard server auto-registers generated audio clips
- Stable Audio API for generation, Chatterbox TTS for voice layering

## Dependencies
- Design token extraction from existing CSS
- Audio token system design
- Image generation API (Ollama_Cloud SD3, DALL-E, or local Stable Diffusion)
- Stable Audio API (already available in LUMAX)
- Component template JSON library
- Preview sandbox iframe

### 8. Reference Works System
Like image gen AI, but for apps/websites/GUIs/code — provide references of things you want to "make something similar":
- **URL references**: Drop a website URL → AI analyzes layout, styling, component structure
- **GitHub references**: Paste a repo → AI reads component structure, patterns, architecture
- **Screenshot references**: Capture or upload screenshots → AI extracts layout grid, color palette, typography
- **Video references**: Timestamped video clips → AI extracts motion patterns, transition styles
- **Code references**: Paste code snippets → AI matches patterns and style

Reference workflow:
```
User: "Make a dashboard like https://linear.app"
→ COMAX fetches page structure, extracts design tokens
→ Generates LUMAX-styled component matching the reference layout
→ Preserves LUMAX neon aesthetic while adopting Linear's information density and spacing
```

- Reference board: Collect multiple references → AI blends patterns
- Style strength slider: "Match reference 70%, keep LUMAX style 30%"
- Chrome Extension captures live page DOM + screenshot for richest reference data
- References stored in Lumax MCP memory for reuse across sessions

## 9. Self-Augmentation Architecture
LUMAX improves itself through AI-driven coding:
- **Chief Coder** (COMAX in REMAX mode): Persistent memory, long-distance planning, approves/rejects augmentative initiatives
- **Self-coding loop**: COMAX reads codebase → identifies improvements → proposes change → Chief Coder reviews → applies if approved
- **Suggestion engine**: Soul monitors usage patterns, suggests UX/performance improvements
- **Copilot mode**: User works in COMAX, AI anticipates next steps, pre-reads relevant files
- **Auto-patch**: Debug tools detect errors → AUTOFIX routes to COMAX with error context → self-repair cycle

### Chief Coder Hierarchy
```
User Request → Chief Coder (REMAX/COMAX)
                ├── Evaluate: Is this safe? Does it fit the architecture?
                ├── Plan: Break into sequential steps
                ├── Execute: Apply changes with workflow (iterate/critique/sequential)
                ├── Verify: Build + test
                └── Remember: Save decision to MCP memory for future reference
```

### LLM Optimization Presets (Implemented)
| Preset | Temp | Top_P | Max_Tokens | Use Case |
|--------|------|-------|------------|----------|
| CODING | 0.15 | 0.9 | 4096 | Deterministic code gen |
| REASONING | 0.2 | 0.95 | 8192 | Chain-of-thought |
| CREATIVE | 0.8 | 0.95 | 4096 | Brainstorming |
| BALANCED | 0.5 | 0.9 | 4096 | General |
| PRECISE | 0.05 | 0.85 | 2048 | Factual lookup |
| CHAT | 0.7 | 0.9 | 2048 | Voice pipeline |
| DEBUG | 0.1 | 0.9 | 4096 | Error diagnosis |

### 4-Layer Cascade (Implemented)
1. LM Studio (local, port 1234) → fastest when available
2. Ollama_Cloud (remote GLM-5.1) → high quality default
3. Gemini API → low-quota backup
4. OpenRouter/OpenAI → paid fallback

### Workflow Patterns (Implemented)
- **Direct**: Single response (default)
- **Iterate**: Draft → Review → Refine → Verify loop
- **Self-Critique**: Generate → Criticize → Fix → Re-criticize cycle
- **Sequential Thinking**: Numbered steps, verify each before proceeding

## Priority: Phase 6+ (generative suite); Core features (presets/cascade/workflows) already implemented
