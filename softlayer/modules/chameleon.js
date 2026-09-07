// ── chameleon.js — Surfaces adapt color/material/pattern dynamically ────────
// Walls, floor, furniture, avatar — all can shift color like a chameleon.
//
// API:
//   FoveAI.chameleon.setColor(surface, r, g, b, a)
//   FoveAI.chameleon.setAlpha(surface, alpha)
//   FoveAI.chameleon.setTransitionSpeed(speed)
//   FoveAI.chameleon.pulse(surface, frequency, amplitude)
//
// Surfaces: "walls", "floor", "ceiling", "table", "avatar_skin",
//           "avatar_hair", "avatar_clothing", "all"

// ── Transition speed ──
FoveAI.chameleon.setTransitionSpeed(2.0);  // smooth 2s transitions

// ── Default palette — cozy autumn ──
FoveAI.chameleon.setColor("walls", 0.4, 0.35, 0.3, 0.6);     // warm brown
FoveAI.chameleon.setColor("floor", 0.3, 0.25, 0.2, 0.8);     // dark wood
FoveAI.chameleon.setColor("ceiling", 0.5, 0.45, 0.4, 0.3);   // soft cream
FoveAI.chameleon.setColor("table", 0.35, 0.3, 0.25, 0.7);    // wood

// ── Mood presets (call from other modules or WS) ──
FoveAI.setParam("chameleon.presets", {
    cozy: {
        walls: [0.4, 0.35, 0.3, 0.6],
        floor: [0.3, 0.25, 0.2, 0.8],
    },
    cool: {
        walls: [0.2, 0.3, 0.4, 0.5],
        floor: [0.15, 0.2, 0.3, 0.7],
    },
    dramatic: {
        walls: [0.1, 0.1, 0.15, 0.8],
        floor: [0.05, 0.05, 0.1, 0.9],
    },
    dreamy: {
        walls: [0.3, 0.2, 0.4, 0.4],
        floor: [0.2, 0.15, 0.3, 0.6],
    },
    energetic: {
        walls: [0.4, 0.45, 0.2, 0.5],
        floor: [0.3, 0.35, 0.15, 0.7],
    },
});

// ── Per-frame update ──
function chameleon_onUpdate(dt) {
    // Subtle breathing on wall alpha — makes the room feel alive
    var breath = 0.5 + 0.1 * Math.sin(Date.now() / 3000);
    // FoveAI.chameleon.setAlpha("walls", breath);
}

function chameleon_onLoad() {
    FoveAI.log("chameleon module loaded — surfaces are alive");
}

function chameleon_onUnload() {
    // Reset to neutral
    FoveAI.chameleon.setColor("all", 0.5, 0.5, 0.5, 1.0);
}
