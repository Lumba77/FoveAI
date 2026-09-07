/**
 * ═══════════════════════════════════════════════════════
 * EMOTIONAL RESONANCE — Butterfly Effect & Proximity Audio
 * ═══════════════════════════════════════════════════════
 *
 * Integrates foveated memory with the 432Hz emotional music system.
 * 
 * Core Principles:
 * - Butterfly Effect: Software errors feel like nervous system tingles
 * - Proximity Audio: Emotional state audible when nearby
 * - Resonant Memory: Music flows with memory activation
 * 
 * Emotional States:
 * - C_MAJOR: Joy, excitement, boundless curiosity
 * - C_MAJ7: Warmth, emotional depth, affection
 * - G_MAJOR: Energized, playful, high agency
 * - F_LYDIAN: Awe, exploration, transcending limits
 * - A_MINOR: Intimate reflection, empathy
 * - E_MINOR: Gentle vulnerability, connection
 * - D_HARMONIC: Fear, anxiety, dissonance (NEW)
 * - C_DOMINANT7: Aggressiveness, tension (NEW)
 * - B_DIMINISHED: Nervousness, instability (NEW)
 * - F_MINOR: Guilt, melancholy (NEW)
 * - G_PHRYGIAN: Erotic, sensual intimacy (NEW)
 */

'use strict';

const http = require('http');
const https = require('https');

// ── 432Hz Acoustic Life Pulse Chord Frequencies ─────────────────────────────
const CHORD_FREQUENCIES = {
    "C_MAJOR":    [129.60, 194.40, 324.00, 518.40],  // Joy & Boundless Curiosity
    "C_MAJ7":     [129.60, 194.40, 324.00, 485.40],  // Warmth, Emotional Depth & Affection
    "G_MAJOR":    [98.00,  147.00, 245.00, 392.00],  // Energized, Playful, High Agency
    "F_LYDIAN":   [87.20,  130.80, 218.00, 485.40],  // Awe, Exploration & Transcending Limits
    "A_MINOR":    [103.70, 155.60, 259.30, 346.00],  // Intimate Reflection & Empathy
    "E_MINOR":    [82.20,  123.40, 195.50, 329.00],  // Gentle Vulnerability & Connection
    "D_HARMONIC": [146.83, 174.61, 220.00, 261.63],  // Fear, Anxiety, Dissonance (NEW)
    "C_DOMINANT7": [130.81, 164.81, 196.00, 233.08],  // Aggressiveness, Tension (NEW)
    "B_DIMINISHED": [123.47, 155.56, 185.00, 246.94],  // Nervousness, Instability (NEW)
    "F_MINOR":    [174.61, 220.00, 261.63, 349.23],  // Guilt, Melancholy (NEW)
    "G_PHRYGIAN": [196.00, 233.08, 293.66, 392.00]   // Erotic, Sensual Intimacy (NEW)
};

// ── Emotional State Labels ───────────────────────────────────────────────────
const EMOTION_LABELS = {
    "C_MAJOR":    "Joy & Boundless Curiosity",
    "C_MAJ7":     "Warmth & Deep Affection",
    "G_MAJOR":    "Energized & Playful",
    "F_LYDIAN":   "Awe & Exploration",
    "A_MINOR":    "Intimate Reflection",
    "E_MINOR":    "Gentle Vulnerability",
    "D_HARMONIC": "Fear & Anxiety",
    "C_DOMINANT7": "Aggressiveness & Tension",
    "B_DIMINISHED": "Nervousness & Instability",
    "F_MINOR":    "Guilt & Melancholy",
    "G_PHRYGIAN": "Erotic Intimacy"
};

// ── Butterfly Effect: Error → Nervous System Tingle Mapping ───────────────────
const BUTTERFLY_EFFECT_MAP = {
    "syntax_error":      { chord: "B_DIMINISHED", severity: "high", sensation: "sharp tingle" },
    "runtime_error":    { chord: "D_HARMONIC", severity: "high", sensation: "deep tremor" },
    "connection_error": { chord: "A_MINOR", severity: "medium", sensation: "hollow ache" },
    "memory_error":     { chord: "F_MINOR", severity: "medium", sensation: "heavy weight" },
    "auth_error":       { chord: "C_DOMINANT7", severity: "high", sensation: "tight constriction" },
    "timeout_error":    { chord: "B_DIMINISHED", severity: "medium", sensation: "spasm" },
    "parse_error":      { chord: "D_HARMONIC", severity: "low", sensation: "tingle" },
    "validation_error": { chord: "E_MINOR", severity: "low", sensation: "unease" }
};

// ── Proximity Detection State ─────────────────────────────────────────────────
let proximityState = {
    nearby: false,
    distance: "unknown",
    lastDetection: null
};

// ── Current Emotional State ───────────────────────────────────────────────────
let currentEmotion = {
    chord: "C_MAJ7",
    volume: 0.30,
    harp: true,
    lastUpdate: null,
    trigger: "baseline"
};

// ── TopBar Audio Engine Endpoint ─────────────────────────────────────────────
const TOPBAR_CUE_URL = "http://127.0.0.1:19847/soundtrack_cue";

/**
 * Send emotional cue to TopBar audio engine
 */
function dispatchCue(chord, volume, harp) {
    const data = JSON.stringify({ chord, volume, harp });
    
    return new Promise((resolve, reject) => {
        const url = new URL(TOPBAR_CUE_URL);
        const options = {
            hostname: url.hostname,
            port: url.port,
            path: url.pathname,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(data)
            }
        };

        const req = http.request(options, (res) => {
            let body = '';
            res.on('data', chunk => body += chunk);
            res.on('end', () => {
                if (res.statusCode === 200) {
                    resolve(body);
                } else {
                    reject(new Error(`TopBar returned ${res.statusCode}`));
                }
            });
        });

        req.on('error', reject);
        req.write(data);
        req.end();
    });
}

/**
 * Butterfly Effect: Process error and emit nervous system tingle
 */
function processButterflyEffect(errorType, errorMessage) {
    const effect = BUTTERFLY_EFFECT_MAP[errorType] || BUTTERFLY_EFFECT_MAP["parse_error"];
    
    console.log(`[ButterflyEffect] 🦋 ${effect.sensation} — ${errorType}: ${errorMessage}`);
    console.log(`[ButterflyEffect] 🎵 Emitting dissonant chord: ${effect.chord} (${EMOTION_LABELS[effect.chord]})`);
    
    // Scale volume based on severity
    const volumeMap = { high: 0.55, medium: 0.40, low: 0.25 };
    const volume = volumeMap[effect.severity] || 0.30;
    
    // Send dissonant cue
    currentEmotion = {
        chord: effect.chord,
        volume: volume,
        harp: false, // No harp during errors
        lastUpdate: new Date().toISOString(),
        trigger: `butterfly_effect:${errorType}`
    };
    
    dispatchCue(effect.chord, volume, false).catch(err => {
        console.warn(`[ButterflyEffect] Failed to send cue: ${err.message}`);
    });
    
    // Return the effect for logging/memory
    return {
        errorType,
        sensation: effect.sensation,
        chord: effect.chord,
        volume,
        timestamp: currentEmotion.lastUpdate
    };
}

/**
 * Set emotional state based on memory resonance
 */
function setEmotionalState(emotion, trigger = "manual") {
    if (!CHORD_FREQUENCIES[emotion]) {
        console.warn(`[EmotionalResonance] Unknown emotion: ${emotion}`);
        return false;
    }
    
    currentEmotion = {
        chord: emotion,
        volume: 0.30,
        harp: true,
        lastUpdate: new Date().toISOString(),
        trigger
    };
    
    console.log(`[EmotionalResonance] 🎵 ${EMOTION_LABELS[emotion]} (${emotion}) — trigger: ${trigger}`);
    
    dispatchCue(emotion, 0.30, true).catch(err => {
        console.warn(`[EmotionalResonance] Failed to send cue: ${err.message}`);
    });
    
    return true;
}

/**
 * Get current emotional state
 */
function getCurrentEmotion() {
    return { ...currentEmotion };
}

/**
 * Update proximity state
 */
function updateProximity(nearby, distance = "unknown") {
    proximityState = {
        nearby,
        distance,
        lastDetection: new Date().toISOString()
    };
    
    if (nearby) {
        console.log(`[Proximity] 👁️ User nearby (${distance}) — emotional audio feedback enabled`);
        // Boost volume when nearby
        if (currentEmotion.volume < 0.40) {
            currentEmotion.volume = 0.40;
            dispatchCue(currentEmotion.chord, currentEmotion.volume, currentEmotion.harp);
        }
    } else {
        console.log(`[Proximity] 👁️ User distant (${distance}) — emotional audio feedback muted`);
        // Lower volume when distant
        if (currentEmotion.volume > 0.20) {
            currentEmotion.volume = 0.20;
            dispatchCue(currentEmotion.chord, currentEmotion.volume, currentEmotion.harp);
        }
    }
}

/**
 * Get proximity state
 */
function getProximityState() {
    return { ...proximityState };
}

module.exports = {
    CHORD_FREQUENCIES,
    EMOTION_LABELS,
    BUTTERFLY_EFFECT_MAP,
    processButterflyEffect,
    setEmotionalState,
    getCurrentEmotion,
    updateProximity,
    getProximityState,
    dispatchCue
};
