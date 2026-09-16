// ── particles.js — Dynamic particle effects (snow, rain, leaves, etc.) ──────
// Control particle systems from JS — enable/disable, set density.
//
// API:
//   FoveAI.particles.enable(type, true/false)
//   FoveAI.particles.setDensity(type, 0.0-1.0)
//
// Types: "snow", "rain", "leaves", "petals", "fireflies", "dust", "bubbles", "sparkles"

function particles_onLoad() {
    // Sterile default: nothing enabled. Seasons/presets are opt-in via
    // particles_setSeason() or FoveAI.particles.enable() — never on by default.
    FoveAI.log("particles module loaded — dormant (no default particles)");
}

// ── Seasonal presets ──
FoveAI.setParam("particles.seasonal", {
    spring: {
        petals: { enabled: true, density: 0.5 },
        leaves: { enabled: false, density: 0 },
        dust:   { enabled: true, density: 0.1 },
    },
    summer: {
        fireflies: { enabled: true, density: 0.3 },
        leaves:    { enabled: false, density: 0 },
        dust:      { enabled: true, density: 0.15 },
    },
    autumn: {
        leaves: { enabled: true, density: 0.4 },
        dust:   { enabled: true, density: 0.1 },
    },
    winter: {
        snow:   { enabled: true, density: 0.6 },
        leaves: { enabled: false, density: 0 },
    },
});

function particles_setSeason(season) {
    var presets = FoveAI.getParam("particles.seasonal");
    if (!presets || !presets[season]) return;
    var p = presets[season];
    for (var type in p) {
        FoveAI.particles.enable(type, p[type].enabled);
        FoveAI.particles.setDensity(type, p[type].density);
    }
    FoveAI.log("particles season → " + season);
}

function particles_onUpdate(dt) {
    // Could add wind variation, gust effects, etc.
}

function particles_onUnload() {
    FoveAI.particles.enable("leaves", false);
    FoveAI.particles.enable("dust", false);
}
