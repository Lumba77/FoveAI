# Main page — functional reference (frozen 2026-10-08)

The chat page after login. This is what "working" means. Screens taken
from the user's description + the last known-good layout (molded-C, Oct 5).

## Layout (molded C)
- Left sidebar: logo top, nav menu (Copilot/Memory/News + category accordion),
  user card bottom. Width ~200-300px depending on viewport tier.
- Center: chat column — header bar (clock, quick-action icons), messages
  area (bubbles, AI right-aligned / user left), composer pinned at bottom.
- Right: optional avatar window / todo rail, overlay-style.

## Composer — THE critical surface
- Full-width input box, always fully visible on screen, sticky bottom.
- **Send-ball** (the small trackball at the right end of the input bar):
  - press = send message
  - press-and-hold = push-to-talk (voice)
  - rolling it does NOTHING functional (feel only)
  - it must NEVER: capture drags (no "image move" cursor), float away,
    hijack clicks meant for the menu, or trigger page-level gestures.
- **Mode menu** (text / voice / video): opens from a control ON/NEAR the
  input bar. The selected-mode indicator renders INSIDE the input area
  (left edge of the box or the button face) — never a floating banner
  above the composer.
- Selection persists (localStorage) until changed.

## Chat round-trip (the point of the page)
1. type text → press send-ball → message appears as user bubble
2. streaming reply renders as AI bubble (may include motor/avatar tags —
   stripped for display, consumed by TTS/motor/XR layers)
3. errors show inline in the chat, never as page-level toasts that
   vanish or move layout

## Scale system (user comfort law)
- UI structure ×2, content text ×1.5 (literals, no CSS `zoom`)
- Viewport tiers: ≥1600px and ≥2200px walk spacing back (App.css SCALE TIERS)
- Composer sticky at every tier — this is a hard invariant.

## Forbidden on this page
- Hover-driven zoom of any element
- Animations that invalidate compositing layers over the chat area
- Any element that captures pointer events outside its visual footprint
