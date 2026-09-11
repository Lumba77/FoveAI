// ── hud_config.js — HUD colors, labels, and layout (hot-reloadable) ──────────
// Edit this file and save — the Quest HUD updates instantly. No APK rebuild.
//
// FoveAI API:
//   FoveAI.setHUDColor(corner, r, g, b, a)   — corner: "TL"|"TR"|"BL"|"BR"
//   FoveAI.setHUDValue(corner, text)          — set the metric text
//   FoveAI.setHUDLabel(corner, label)         — set the label under the metric
//   FoveAI.setHUDAlpha(alpha)                 — global HUD transparency
//   FoveAI.setParam(path, value)              — set a soft param
//   FoveAI.getParam(path)                     — get a soft param
//   FoveAI.log(msg)                           — log to Unity console
//   FoveAI.triggerGesture(name)               — trigger avatar animation
//   FoveAI.setEmotion(emotion, intensity)     — set avatar emotion

// ── Corner colors (cyan/magenta/amber/green palette) ──
// Change these and the HUD corners recolor instantly
FoveAI.setHUDColor("TL", 0.0, 0.94, 1.0, 0.28);   // cyan — LINK
FoveAI.setHUDColor("TR", 0.85, 0.15, 0.85, 0.28); // magenta — FPS
FoveAI.setHUDColor("BL", 1.0, 0.78, 0.10, 0.28);  // amber — MOOD
FoveAI.setHUDColor("BR", 0.30, 0.95, 0.45, 0.28); // green — FLOW

// ── Corner labels ──
FoveAI.setHUDLabel("TL", "LINK");
FoveAI.setHUDLabel("TR", "FPS");
FoveAI.setHUDLabel("BL", "MOOD");
FoveAI.setHUDLabel("BR", "FLOW");

// ── HUD transparency ──
FoveAI.setHUDAlpha(0.28);  // 28% — subtle, peripheral

// ── Pipeline bar config ──
FoveAI.setParam("hud.bar.segments", ["STT", "ROUTER", "AI", "TTS", "VRAM", "MEM"]);
FoveAI.setParam("hud.bar.pulseSpeed", 2.0);
FoveAI.setParam("hud.breathRing.enabled", true);

// ── Initial values ──
FoveAI.setHUDValue("TL", "ON");
FoveAI.setHUDValue("TR", "72");
FoveAI.setHUDValue("BL", "IDLE");
FoveAI.setHUDValue("BR", "0%");

FoveAI.log("hud_config loaded — corners colored, labels set");
