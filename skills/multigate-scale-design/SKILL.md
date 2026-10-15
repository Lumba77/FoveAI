---
name: multigate-scale-design
description: Multigate UI scale system — from real browser-zoom comfort testing (200–250% comfortable, content text overshoots). Rule: ALL UI sizes ×2 (dimensions, padding, radii, gaps, scrollbars, images, form controls) but content font-size ×1.5 only (chat bubbles, menus, body text). Use when restyling, generating new tabs/components, or reviewing Multigate CSS.
version: 1.0.0
metadata:
  tags: [multigate, ui-scale, typography, frontend-design, foveai]
  related_skills: [frontend-design-skill]
---

# Multigate Scale Design Tokens

## The Scale Law (verified by zoom-comfort testing 2026-10-07)

User comfort ≈ browser zoom 200–250% for structure, but content text at that
zoom is too large. So structure and text scale differently:

| Category | Factor | Applies to |
|---|:---:|---|
| **UI structure** | ×2 | width/height/padding/margin/gap/border-radius, scrollbar, images, windows, form controls, icon buttons, letter-spacing of chrome |
| **Content text** | ×1.5 | font-size everywhere: chat bubbles, nav/menu items, subtitles, labels, chip/caption text |

Rules:
1. NEVER scale `vh`/`vw` values, `1px` hairlines, or `calc(100vh - …)` full-viewport rules.
2. Chat bubble text baseline: `0.85rem → 1.275rem`. Nav item text: `0.85rem → 1.275rem`.
3. Chrome (avatar windows, rails, toolbars) scales geometrically — labels ride along at ×1.5.
4. Write literals, not `zoom:` — CSS `zoom` broke the trackball's px math and
   double-transformed rect geometry (fixed by zoom normalizer in Trackball.tsx,
   but literals are the durable pattern).

## Files carrying the scale (reference state)

- `Frontend/multigate/src/index.css` — base palette, scrollbars, `.glass-panel`
- `Frontend/multigate/src/App.css` — sidebar/nav/auth/chrome
- `Frontend/multigate/src/components/ChatLayout.css` — chat layout, bubbles, pips
- `Frontend/multigate/src/App.tsx` — inline `style={{…}}` objects (same law)

## Interaction spec (fits frontend-design-skill State Engine)

- Every UI-scaled control keeps distinct `:hover / :focus-within / :active / :disabled`.
- Example (ignition reactor-plate): hover-brass → `transition: transform .45s cubic-bezier(.3,1.3,.5,1)` zoom-out so all bearing-pips become visible/clickable; leave → ease back to close-up.
## Verification protocol (mandatory since 2026-10-08)

NEVER claim a visual change is stable without seeing it. Setup lives in
`FoveAI/Tools/pw-verify/` (scripts) — node_modules for playwright at
`/tmp/opencode` (recreate with `npm i playwright --no-save` if lost;
run scripts with cwd=/tmp/opencode or adjust import).

```bash
export PATH="$HOME/.local/node24/bin:$PATH" && cd /tmp/opencode
npm i playwright --no-save           # if node_modules empty
node vault.mjs                       # screenshots vault1/2_core/3_armed.png
```

`vault.mjs` seeds `localStorage.foveai_foveai_user` (needs firstName+aiName
or App shows the profile-setup screen instead of the vault), reloads, walks
the 3 arm stages, screenshots each. Read the PNGs with the read tool.

Rules:
1. Verify EVERY stage after geometry/overlay changes — stage2 zoom and LCD
   pane overlap are the historical failure spots.
2. Quest WebView serves stale builds — tell the user to long-press refresh
   or use a private window; note a BUILD marker comment in IgnitionScreen.
3. Desktop screenshots ≠ Quest rendering (timewarp ghosting, raycast
   pointer) — motion smoothness and touch still need the user's eyes.
