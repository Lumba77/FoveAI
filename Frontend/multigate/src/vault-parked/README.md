# Vault (parked 2026-10-08)

The animated ignition instrument — 12 warmth-driven concentric rings, silver
pip dial, glass ball with planetary system, 3-stage arm ritual, countdown
fire — is PARKED. It fought the Quest WebView for two days (compositing
layer invalidation → image re-decode flicker; hover-latch zoom thrash;
pointer-jitter accidental fires) and the user called it: simple gate first.

Recovery sources for the revival:
- Full compiled CSS template: extracted to `style_template.css` here
  (extracted from dist/assets/index-*.js of the last good build 20:41).
- Geometry truths learned the hard way (see AGENTS.md lessons):
  * halos: whole-transform animation, transform-box border-box, no filters,
    duration floor (negative period = invalid anim = displaced ring)
  * pips: 0x0 anchors at 50%/50%, children center themselves — never
    3.5em/-1.75em margins (ellipse orbit bug)
  * measuring: offsetWidth/offsetHeight (transform-immune), debounced
  * zoom: latched button only — NEVER hover/distance gates (thrash/eat clicks)
  * plate: own layer translateZ(0) + contain:paint (no bg re-decode)
Revival plan: rebuild on a plain canvas/WebGL layer where the whole
instrument composites in ONE draw call — immune to DOM layer invalidation.
