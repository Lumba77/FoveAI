// ── lighting.js — Dynamic lighting moods and transitions ────────────────────
// Controls ambient light, key light, and mood presets.
//
// API:
//   FoveAI.lighting.setAmbient(r, g, b, intensity)
//   FoveAI.lighting.setKeyLight(r, g, b, intensity)
//   FoveAI.lighting.setMood(mood) — "warm"|"cool"|"dramatic"|"dreamy"|"energetic"|"cozy"

// ── Default mood ──
function lighting_onLoad() {
    FoveAI.lighting.setMood("cozy");
    FoveAI.log("lighting module loaded — mood: cozy");
}

// ── Mood cycling (subtle, over minutes) ──
var lighting_moodCycle = ["cozy", "warm", "dreamy", "cool", "cozy"];
var lighting_moodIndex = 0;
var lighting_moodTimer = 0;
var lighting_moodInterval = 120; // 2 minutes per mood

function lighting_onUpdate(dt) {
    lighting_moodTimer += dt;
    if (lighting_moodTimer >= lighting_moodInterval) {
        lighting_moodTimer = 0;
        lighting_moodIndex = (lighting_moodIndex + 1) % lighting_moodCycle.length;
        var nextMood = lighting_moodCycle[lighting_moodIndex];
        FoveAI.lighting.setMood(nextMood);
        FoveAI.log("lighting mood → " + nextMood);
    }
}

function lighting_onUnload() {
    FoveAI.lighting.setMood("warm");
}
