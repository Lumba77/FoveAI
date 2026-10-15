# Gate page — functional reference (frozen 2026-10-08)

The start page. Simple, calm, bulletproof. Replaces the parked vault.

## Contents (top to bottom, centered column)
1. FOVEAI logotype + "CONCORDIA · GATE" subline
2. "welcome back, {firstName}" (from persisted profile — never re-asked)
3. Saved pattern chips (load a preset interference/settings signature) — optional, only if patterns exist
4. Four dropdowns: Cognitive mode / Reasoning / Voice / Microphone
   - values persist to .env via POST /api/setting immediately on change
   - current values loaded from GET /api/setting on mount (last config greets you)
5. Green ENTER button (disabled until settings load; shows ENTERING… on click)
6. Footer hint: "settings persist — the site loads with what you leave here"

## Behavior
- ENTER → sessionStorage foveai_ignited=1 → location.reload() → main page
  boots fresh with the armed settings as its base
- No animations, no hover effects, no images beyond gradients, no webfonts
  beyond Share Tech Mono, no pointer gestures. Nothing that can flicker.
- Works at any viewport ≥360px wide ( Quest browser, TV, desktop )

## Auth flow before the gate
- Login form (username/password) → /api/auth/login → profile merge
  (server persona first, localStorage fallback, displayName last)
- Profile setup only if account has no aiName — after first save it never
  asks again (PUT /api/auth/profile persists firstName/lastName/aiName)
