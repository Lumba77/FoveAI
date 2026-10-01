---
name: ui-machine
description: Generative UI pipeline — a glossy/branded reference image + a sitemap go in the top, a coherent stitched UI comes out the bottom. Orchestrates tandem (NVIDIA free tier) for bulk generation, a VLM pass for style extraction, and deterministic verification. Use when building a new UI/theme/skin from a visual reference, restyling an app from an image, or mass-producing screens in one brand language.
---

# UI Machine

Input: **reference image** (any glossy/branded visual) + **sitemap** (list of screens/routes + their roles) + **target stack** (default: the repo's vite/React + vanilla CSS, unless told otherwise).

Output: a complete, coherent UI — design tokens + one component per screen + a stitched shell — verified, not just generated.

## The contract

- **Design tokens are the single source of truth.** Every screen consumes `tokens.css`; nothing hard-codes colors. This is what makes per-screen outputs stitch instead of drift.
- **Pointers, not truth.** The draft model produces candidates; the operator (Devin) verifies every artifact that ships.
- **Cheapest tool first.** Extract what you can deterministically (palette, luminance, aspect) before spending model calls.

## Pipeline

### Phase 0 — Read the reference (`extract`)
1. Deterministic pass (no model): dominant-color palette via PIL quantization, luminance map, aspect ratio, and `spatial_grid_6x4` (luminance+saturation per cell) — the image's compositional weight, translated into layout hints for screen generation. Writes `style/raw-stats.json`.
2. VLM pass (NIM vision model, e.g. `meta/llama-3.2-90b-vision-instruct`): image + prompt → `style/spec.json`:
   `{palette_hex[], surface_type (brushed-metal|glass|matte|neon), shape_language (radius, borders), glow/emissive treatment, typography_mood, brand_marks, color_coding_semantics (what each hue means), mood_keywords[]}`
3. Fallback if VLM unavailable/flaky: derive spec from raw-stats + `foveai-brushed-steel-ui` defaults.

### Phase 1 — Tokens (`forge`)
Turn `spec.json` into `tokens.css` (custom properties: colors, surfaces, radii, glow shadows, spacing scale, font stack — Syndra first-party where available). One file, versioned per run. **Gate: Devin reviews tokens before any screen is generated** — 30 seconds here prevents 30 minutes of drift.

### Phase 2 — Screens (`stamp`)
`sitemap.json` → `tandem bg` fan-out, one job per node. Each job receives: skill text + `spec.json` + `tokens.css` + the node's role/contents contract. Output: `screens/<name>.jsx|html` + co-located CSS that only references tokens. Cap: 4 concurrent (free-tier rate limits); retry ladder on null content (kimi collapses ~1-in-4).

### Phase 3 — Stitch (`duel`)
1. Mechanical check: every screen parses, imports tokens, uses no hard-coded hexes outside tokens.
2. Duel pass: `tandem opine` on the stitch — "what's inconsistent across these screens" — Devin resolves the dissent. Two eyes; coverage eye wins breadth, operator owns correctness.

### Phase 4 — Verify (`gate`)
- Structural: build/typecheck passes (`vite build`, `tsc --noEmit`, or per-file parse for plain HTML).
- Visual (when a browser is available): screenshot each screen at the reference aspect; compare palette histograms vs `raw-stats.json` — drift beyond tolerance → regen that screen only.

### Phase 5 — Wire
Devin integrates: routes, assets, fonts (syndra zips already in `~/Hämtningar`), real data. Generated UI is a candidate until it passes the project's own gates.

## Failure modes (learned, keep list growing)
- kimi-k3 returns null content + `!!!!` reasoning ~25% — retry ladder required, vary effort/temp.
- Per-screen generation drifts without tokens-first gating.
- VLM hallucinates brand marks — keep palette extraction deterministic as ground truth.
- Sync tandem calls stall the operator — always `bg` + collect.
- Screens that "look right" can still fail on semantics (missing roles/aria) — the duel prompt must ask for that explicitly.

## Usage
```
tandem ui extract  <image>            # phase 0+1 → tokens.css (Devin gates)
tandem ui stamp    sitemap.json       # phase 2 fan-out
tandem ui stitch                     # phase 3+4 duel + verify
```
