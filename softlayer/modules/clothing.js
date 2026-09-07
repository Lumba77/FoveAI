// ── clothing.js — Avatar outfits, colors, materials (hot-reloadable) ────────
// Change Alice's clothes, colors, metallic, smoothness, emission — instantly.
//
// API:
//   FoveAI.clothing.setOutfit(name)         — "default"|"casual"|"formal"|"cozy"|"cyber"
//   FoveAI.clothing.setColor(part, r, g, b) — part: "shirt"|"skirt"|"hair"|"skin"|"shoes"
//   FoveAI.clothing.setMetallic(m)          — 0=matte, 1=metal
//   FoveAI.clothing.setSmoothness(s)        — 0=rough, 1=smooth
//   FoveAI.clothing.setEmission(r, g, b, i) — glow effect

// ── Outfit presets ──
FoveAI.setParam("clothing.outfits", {
    default: {
        shirt: [0.5, 0.6, 0.9],
        skirt: [0.3, 0.3, 0.5],
        metallic: 0.0,
        smoothness: 0.5,
    },
    casual: {
        shirt: [0.7, 0.5, 0.4],
        skirt: [0.4, 0.35, 0.3],
        metallic: 0.0,
        smoothness: 0.4,
    },
    formal: {
        shirt: [0.1, 0.1, 0.15],
        skirt: [0.05, 0.05, 0.1],
        metallic: 0.1,
        smoothness: 0.7,
    },
    cozy: {
        shirt: [0.8, 0.6, 0.5],
        skirt: [0.5, 0.4, 0.35],
        metallic: 0.0,
        smoothness: 0.3,
    },
    cyber: {
        shirt: [0.1, 0.05, 0.2],
        skirt: [0.05, 0.02, 0.1],
        metallic: 0.6,
        smoothness: 0.9,
        emission: [0.3, 0.1, 0.8, 0.5],
    },
    festive: {
        shirt: [0.8, 0.2, 0.2],
        skirt: [0.2, 0.6, 0.3],
        metallic: 0.2,
        smoothness: 0.6,
    },
});

// ── Apply default outfit ──
function clothing_onLoad() {
    FoveAI.clothing.setOutfit("default");
    FoveAI.log("clothing module loaded — Alice is dressed");
}

// ── Outfit switching ──
// Called by: FoveAI.clothing.setOutfit("cyber")
// The C# side calls this function name, but we also expose it via param
function clothing_setOutfit(name) {
    var outfits = FoveAI.getParam("clothing.outfits");
    if (!outfits || !outfits[name]) {
        FoveAI.log("Unknown outfit: " + name);
        return;
    }
    var o = outfits[name];
    if (o.shirt) FoveAI.clothing.setColor("shirt", o.shirt[0], o.shirt[1], o.shirt[2]);
    if (o.skirt) FoveAI.clothing.setColor("skirt", o.skirt[0], o.skirt[1], o.skirt[2]);
    if (o.metallic !== undefined) FoveAI.clothing.setMetallic(o.metallic);
    if (o.smoothness !== undefined) FoveAI.clothing.setSmoothness(o.smoothness);
    if (o.emission) FoveAI.clothing.setEmission(o.emission[0], o.emission[1], o.emission[2], o.emission[3]);
    FoveAI.log("Outfit changed: " + name);
}

function clothing_onUpdate(dt) {
    // Could add dynamic effects here — e.g. shimmer, color cycling
}

function clothing_onUnload() {
    FoveAI.clothing.setOutfit("default");
}
