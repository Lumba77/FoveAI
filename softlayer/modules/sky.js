// ── sky.js — Dynamic sky, time of day, horizon colors ───────────────────────
// Control the sky appearance and simulate time progression.
//
// API:
//   FoveAI.sky.setColor(r, g, b)         — zenith color
//   FoveAI.sky.setHorizon(r, g, b)       — horizon color
//   FoveAI.sky.setTimeOfDay(hour)        — 0-24

// ── Time-of-day presets ──
FoveAI.setParam("sky.timePresets", {
    dawn:      { hour: 6,  zenith: [0.3, 0.4, 0.6], horizon: [0.9, 0.6, 0.4] },
    morning:   { hour: 9,  zenith: [0.4, 0.6, 0.9], horizon: [0.7, 0.8, 1.0] },
    noon:      { hour: 12, zenith: [0.3, 0.5, 0.9], horizon: [0.6, 0.7, 0.9] },
    afternoon: { hour: 15, zenith: [0.4, 0.5, 0.85], horizon: [0.8, 0.7, 0.6] },
    sunset:    { hour: 18, zenith: [0.2, 0.2, 0.4], horizon: [1.0, 0.5, 0.3] },
    dusk:      { hour: 20, zenith: [0.1, 0.1, 0.2], horizon: [0.4, 0.2, 0.3] },
    night:     { hour: 0,  zenith: [0.02, 0.02, 0.05], horizon: [0.05, 0.05, 0.1] },
});

function sky_onLoad() {
    // Start at afternoon
    sky_setTime("afternoon");
    FoveAI.log("sky module loaded — afternoon light");
}

function sky_setTime(presetName) {
    var presets = FoveAI.getParam("sky.timePresets");
    if (!presets || !presets[presetName]) return;
    var p = presets[presetName];
    FoveAI.sky.setColor(p.zenith[0], p.zenith[1], p.zenith[2]);
    FoveAI.sky.setHorizon(p.horizon[0], p.horizon[1], p.horizon[2]);
    FoveAI.sky.setTimeOfDay(p.hour);
    FoveAI.log("sky → " + presetName);
}

// ── Auto time progression ──
var sky_autoProgress = false;
var sky_currentHour = 15;
var sky_progressSpeed = 0.01; // hours per second (24h in ~40min)

function sky_onUpdate(dt) {
    if (!sky_autoProgress) return;
    sky_currentHour = (sky_currentHour + sky_progressSpeed * dt) % 24;

    // Interpolate sky colors based on time
    var h = sky_currentHour;
    if (h < 6)       { FoveAI.sky.setColor(0.02, 0.02, 0.05); FoveAI.sky.setHorizon(0.05, 0.05, 0.1); }
    else if (h < 9)  { FoveAI.sky.setColor(0.3, 0.4, 0.6);    FoveAI.sky.setHorizon(0.9, 0.6, 0.4); }
    else if (h < 15) { FoveAI.sky.setColor(0.3, 0.5, 0.9);    FoveAI.sky.setHorizon(0.6, 0.7, 0.9); }
    else if (h < 18) { FoveAI.sky.setColor(0.4, 0.5, 0.85);   FoveAI.sky.setHorizon(0.8, 0.7, 0.6); }
    else if (h < 20) { FoveAI.sky.setColor(0.2, 0.2, 0.4);    FoveAI.sky.setHorizon(1.0, 0.5, 0.3); }
    else             { FoveAI.sky.setColor(0.02, 0.02, 0.05); FoveAI.sky.setHorizon(0.05, 0.05, 0.1); }

    FoveAI.sky.setTimeOfDay(h);
}

function sky_onUnload() {
    FoveAI.sky.setColor(0.3, 0.5, 0.9);
    FoveAI.sky.setHorizon(0.6, 0.7, 0.9);
}
