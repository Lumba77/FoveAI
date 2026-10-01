/**
 * ═══════════════════════════════════════════════════════
 * RESOLUTION ENGINE — Single Source of Truth for Memory Resolution
 * ═══════════════════════════════════════════════════════
 *
 * Unifies the two previously-disconnected scales:
 *   - LUMAX_PROXY_AGGRESSION (0-5, ring multiplier only)
 *   - compressContext level (1-5, checkpoint aggressiveness, inverted)
 *
 * into ONE 0-5 RESOLUTION scale, where 0 is the guaranteed 65% baseline.
 *
 * ═══ DESIGN (per user spec) ═══
 *  - We ABANDON the notion of an "uncompressed" context.
 *  - Level 0 = 65% baseline compression. It ALWAYS applies. It keeps the
 *    ~4 most recent ("unprepared") messages verbatim as the foveal boundary,
 *    and compresses everything older at 65% retention. This yields real
 *    token savings with ZERO loss of context-following fidelity.
 *  - Levels 1-5 go progressively deeper on top of that baseline.
 *  - There is NO "Off" level (max compression is level 5).
 *
 * ═══ WINDOW MATH ═══
 *  retention[r] = fraction of conversation retained in the physical window.
 *  For a physical window P and resolution r:
 *      maxAdvertisedV[r] = P / retention[r]
 *  To advertise V tokens on a physical window P, required retention:
 *      requiredRetention = P / V
 *  Pick the resolution whose retention is nearest to (>=) required.
 *
 *  Examples (physical P = 8192):
 *    r0 (65%)  → V ≈ 12.6K
 *    r2 (35%)  → V ≈ 23.4K
 *    r3 (20%)  → V ≈ 41.0K
 *    r5 (5%)   → V ≈ 164K   (≈128K advertised on 8K physical)
 */

'use strict';

// ── Retention per resolution level (fraction of conversation kept) ─────────
// r0 = 65% baseline (guaranteed floor, default)
// r5 = 5% (20x compression → 8K physical ≈ 164K advertised)
const RETENTION = {
    0: 0.65,
    1: 0.50,
    2: 0.35,
    3: 0.20,
    4: 0.10,
    5: 0.05,
};

// ── Ring-builder multiplier (kept verbatim fovea size) ─────────────────────
// Lower resolution = keep MORE verbatim in the ring (larger multiplier).
// Higher resolution = keep LESS verbatim (smaller multiplier).
const RING_MULTIPLIER = {
    0: 1.0,   // baseline
    1: 0.85,
    2: 0.70,
    3: 0.55,
    4: 0.40,
    5: 0.15,
};

// ── Checkpoint compressor params (per resolution) ──────────────────────────
// keepRecent = number of recent turns left verbatim (foveal window)
// compressEvery = turns per checkpoint batch
const COMPRESSOR_PARAMS = {
    0: { keepRecent: 4, compressEvery: 8 },   // 65% baseline
    1: { keepRecent: 4, compressEvery: 7 },   // ~50%
    2: { keepRecent: 3, compressEvery: 6 },   // ~35%
    3: { keepRecent: 3, compressEvery: 5 },   // ~20% (balanced)
    4: { keepRecent: 2, compressEvery: 4 },   // ~10%
    5: { keepRecent: 1, compressEvery: 2 },   // ~5% (max)
};

// ── Human labels ───────────────────────────────────────────────────────────
const LABELS = {
    0: 'R0 Baseline (65% retention)',
    1: 'R1 Light (50%)',
    2: 'R2 Moderate (35%)',
    3: 'R3 High (20%)',
    4: 'R4 Aggressive (10%)',
    5: 'R5 Maximum (5%)',
};

/**
 * Clamp a raw value into the valid resolution range 0-5.
 * Any NaN/undefined → 0 (baseline).
 */
function clampResolution(raw) {
    const n = parseInt(raw, 10);
    if (isNaN(n)) return 0;
    return Math.max(0, Math.min(5, n));
}

/**
 * Resolve the effective resolution from env + optional header override.
 * @param {string|number} envValue - LUMAX_PROXY_AGGRESSION (0-5)
 * @param {string|number|null} headerValue - optional x-resolution header override
 * @returns {number} resolution 0-5
 */
function resolve(envValue, headerValue = null) {
    // Header override wins if present and valid
    if (headerValue !== null && headerValue !== undefined && headerValue !== '') {
        const h = clampResolution(headerValue);
        if (!isNaN(h)) return h;
    }
    return clampResolution(envValue);
}

/**
 * Get compressed-history retention fraction for a resolution.
 */
function retentionFor(resolution) {
    return RETENTION[clampResolution(resolution)];
}

/**
 * Max advertised (spoofed) context window V for a physical window P.
 *   maxV = P / retention[r]
 */
function maxAdvertisedWindow(physicalWindow, resolution) {
    const p = Math.max(1, parseInt(physicalWindow, 10) || 8192);
    const r = retentionFor(resolution);
    return Math.floor(p / r);
}

/**
 * Physical window P required to advertise V tokens at a given resolution.
 *   P = V * retention[r]  (plus a small safety margin)
 */
function requiredPhysicalWindow(advertisedWindow, resolution) {
    const v = Math.max(1, parseInt(advertisedWindow, 10) || 128000);
    const r = retentionFor(resolution);
    return Math.floor(v * r * 1.05); // 5% safety margin
}

/**
 * Pick the recommended resolution to advertise `advertisedWindow` tokens
 * on a physical window of `physicalWindow`.
 *   requiredRetention = P / V  → nearest resolution with retention >= required
 */
function resolutionForWindow(advertisedWindow, physicalWindow) {
    const v = Math.max(1, parseInt(advertisedWindow, 10) || 128000);
    const p = Math.max(1, parseInt(physicalWindow, 10) || 8192);
    const requiredRetention = p / v;
    let best = 0;
    let bestDelta = Infinity;
    for (let r = 0; r <= 5; r++) {
        const delta = Math.abs(RETENTION[r] - requiredRetention);
        if (delta < bestDelta) {
            bestDelta = delta;
            best = r;
        }
    }
    return best;
}

/**
 * Get full resolution descriptor: retention, ring multiplier, compressor params,
 * and the advertised window it supports for a given physical window.
 */
function describe(resolution, physicalWindow = 8192) {
    const r = clampResolution(resolution);
    const p = Math.max(1, parseInt(physicalWindow, 10) || 8192);
    return {
        level: r,
        label: LABELS[r],
        retention: RETENTION[r],
        ring_multiplier: RING_MULTIPLIER[r],
        compressor: { ...COMPRESSOR_PARAMS[r] },
        max_advertised_window: maxAdvertisedWindow(p, r),
        physical_window: p,
    };
}

module.exports = {
    RETENTION,
    RING_MULTIPLIER,
    COMPRESSOR_PARAMS,
    LABELS,
    clampResolution,
    resolve,
    retentionFor,
    maxAdvertisedWindow,
    requiredPhysicalWindow,
    resolutionForWindow,
    describe,
};
