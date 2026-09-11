// ── wall.js — Dynamic wall emergence with XR occlusion ──────────────────────
// A wall erupts from the floor — shaking, squeaking, concrete dust clouding.
// Uses XR occlusion so it respects real room geometry.
//
// API:
//   FoveAI.wall.emerge(dirX, dirZ, height, speed)  — spawn wall in direction
//   FoveAI.wall.dissolve()                         — remove wall
//   FoveAI.wall.setColor(r, g, b)                  — wall material color
//   FoveAI.wall.setShake(intensity)                — shake strength
//
// Phases: RUMBLE → CRACK → RISE → SETTLE → STANDING → (dissolve)

// ── Wall presets ──
FoveAI.setParam("wall.presets", {
    concrete: { color: [0.5, 0.48, 0.45], shake: 0.02, speed: 1.2 },
    brick:    { color: [0.6, 0.3, 0.25],  shake: 0.03, speed: 1.0 },
    ice:      { color: [0.7, 0.85, 0.95], shake: 0.01, speed: 1.5 },
    stone:    { color: [0.4, 0.38, 0.35], shake: 0.04, speed: 0.8 },
    metal:    { color: [0.3, 0.3, 0.35],  shake: 0.02, speed: 1.0 },
    wood:     { color: [0.45, 0.35, 0.25], shake: 0.025, speed: 1.1 },
});

function wall_onLoad() {
    FoveAI.log("wall module loaded — ready to close off the room");
}

// ── Emerge in a direction ──
function wall_emerge(direction, presetName) {
    var presets = FoveAI.getParam("wall.presets");
    var p = presets && presets[presetName] ? presets[presetName] : presets.concrete;

    FoveAI.wall.setColor(p.color[0], p.color[1], p.color[2]);
    FoveAI.wall.setShake(p.shake);

    var dir = { forward: [0, 1], back: [0, -1], left: [-1, 0], right: [1, 0] };
    var d = dir[direction] || [0, 1];

    FoveAI.wall.emerge(d[0], d[1], 2.5, p.speed);
    FoveAI.log("Wall emerging: " + direction + " (" + (presetName || "concrete") + ")");
}

// ── Close off the room (all 4 walls) ──
function wall_closeOffRoom() {
    var directions = ["forward", "back", "left", "right"];
    for (var i = 0; i < directions.length; i++) {
        (function(dir, delay) {
            setTimeout(function() {
                wall_emerge(dir, "concrete");
            }, delay);
        })(directions[i], i * 800); // stagger each wall by 0.8s
    }
    FoveAI.log("Closing off the room — 4 walls emerging");
}

// ── Open the room back up ──
function wall_openRoom() {
    FoveAI.wall.dissolve();
    FoveAI.log("Opening the room — walls dissolving");
}

// ── Per-frame: could add ambient effects to standing walls ──
function wall_onUpdate(dt) {
    // e.g. subtle dust drift from standing walls
}

function wall_onUnload() {
    FoveAI.wall.dissolve();
}
