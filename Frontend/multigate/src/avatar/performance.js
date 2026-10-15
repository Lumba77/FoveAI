/**
 * Avatar performance math — pure, deterministic, testable.
 *
 * Every number here is a function of (time, energy) only, so the same input
 * always yields the same pose. That makes the performance verifiable headless
 * (node --test) instead of only observable by staring at a browser.
 *
 * The rig is a VRM 1.0 humanoid (52 bones) with preset expressions, so we can
 * perform entirely procedurally: no animation clips, no bracket parsing, no
 * puppeteering — just bones and mouth shapes driven by audio amplitude.
 */

/** Mouth shapes available on a standard VRM 1.0 preset rig. */
export const VISEMES = ['aa', 'ih', 'ou', 'ee', 'oh'];

/** Smooth 0..1 with fast attack and slower release — reads as a jaw. */
export function envelope(prev, energy, attack = 0.55, release = 0.14) {
  if (!Number.isFinite(prev)) prev = 0;
  const v = Number.isFinite(energy) ? Math.min(1, Math.max(0, energy)) : 0;
  return v > prev ? prev + (v - prev) * attack : prev + (v - prev) * release;
}

/**
 * Pick a viseme for the current moment. Speech is syllable-paced, not
 * amplitude-paced, so gate on a syllable clock and let energy decide openness.
 */
export function visemeAt(tSec, energy, seed = 0) {
  const e = Math.min(1, Math.max(0, Number.isFinite(energy) ? energy : 0));
  if (e < 0.04) return null;
  // ~5.5 syllables/second while speaking
  const syl = Math.floor(tSec * 5.5 + seed);
  const jitter = Math.abs(Math.sin(syl * 12.9898 + seed * 78.233)) % 1;
  const idx = Math.floor(jitter * VISEMES.length) % VISEMES.length;
  // openness follows loudness; quiet syllables are smaller shapes
  const openness = 0.35 + 0.65 * e;
  return { name: VISEMES[idx], value: openness };
}

/** Breathing: slow sine on the chest, always alive even when silent. */
export function breathing(tSec, rate = 0.28) {
  return Math.sin(tSec * Math.PI * 2 * rate);
}

/** Weight shift: slow lateral hip sway so idle never looks frozen. */
export function weightShift(tSec) {
  const a = Math.sin(tSec * 0.31);
  const b = Math.sin(tSec * 0.17 + 1.1);
  return { x: a * 0.035 + b * 0.012, roll: a * 0.02 };
}

/** Micro head motion — never perfectly still. */
export function headIdle(tSec) {
  return {
    yaw: Math.sin(tSec * 0.23) * 0.05 + Math.sin(tSec * 0.61) * 0.015,
    pitch: Math.sin(tSec * 0.19 + 0.7) * 0.035,
    roll: Math.sin(tSec * 0.13 + 2.2) * 0.03,
  };
}

/** Speaking emphasis: nods and small torso pushes, scaled by loudness. */
export function talkBody(tSec, energy) {
  const e = Math.min(1, Math.max(0, Number.isFinite(energy) ? energy : 0));
  if (e < 0.05) return { nod: 0, pitch: 0, torso: 0, hand: 0 };
  const beat = Math.sin(tSec * Math.PI * 2 * 1.7);
  const beat2 = Math.sin(tSec * Math.PI * 2 * 0.9 + 1.4);
  return {
    nod: beat * 0.09 * e,
    pitch: beat2 * 0.05 * e,
    torso: beat2 * 0.03 * e,
    hand: Math.max(0, beat) * 0.22 * e,
  };
}

/**
 * Blinks: mostly closed-open pattern with natural irregular gaps. Returns a
 * 0..1 lid value (1 = fully shut).
 */
export function blinkAt(tSec, seed = 0) {
  const period = 3.4 + (Math.sin(tSec * 0.7 + seed) * 0.5 + 0.5) * 2.6;
  const phase = tSec % period;
  const close = 0.11;
  if (phase < close) return Math.sin((phase / close) * Math.PI);
  return 0;
}

/** Whether we are "speaking" from an envelope value. */
export function isSpeaking(env, threshold = 0.06) {
  return Number.isFinite(env) && env > threshold;
}
/**
 * Aliases for mouth/blink targets across naming conventions.
 * Covers VRM 1.0 presets (aa/ih/ou/ee/oh), VRM 0.0 (A/I/U/E/O), ARKit
 * (jawOpen/mouthFunnel…) and prefixed exports such as Fcl_MTH_A / Fcl_EYE_Close.
 */
export const MORPH_ALIASES = {
  aa: ['aa', 'jawopen', 'mouthopen', 'a', 'fcl_mth_a', 'mth_a'],
  ih: ['ih', 'mouthstretch', 'mouthsmile', 'i', 'fcl_mth_i', 'mth_i'],
  ou: ['ou', 'mouthpucker', 'mouthfunnel', 'u', 'fcl_mth_u', 'mth_u'],
  ee: ['ee', 'mouthwide', 'e', 'fcl_mth_e', 'mth_e'],
  oh: ['oh', 'mouthround', 'mouthlowerdown', 'o', 'fcl_mth_o', 'mth_o'],
  blink: ['blink', 'eyeblink', 'fcl_eye_close', 'eyeclose'],
  blinkLeft: ['blinkleft', 'eyeblinkleft', 'fcl_eye_close_l', 'fcl_eye_close'],
  blinkRight: ['blinkright', 'eyeblinkright', 'fcl_eye_close_r', 'fcl_eye_close'],
};

/**
 * Collect { mesh, index } bindings for a target by alias matching.
 * Returns an empty array when the rig simply lacks the shape.
 */
export function resolveMorphBindings(root, target) {
  const aliases = MORPH_ALIASES[target] || [target];
  const out = [];
  const seen = new Set();
  root.traverse((obj) => {
    const mesh = obj;
    const dict = mesh && mesh.morphTargetDictionary;
    if (!dict) return;
    for (const name of Object.keys(dict)) {
      const key = String(name).toLowerCase().replace(/[\s\-_.]/g, '');
      if (aliases.includes(key) && !seen.has(mesh.uuid + name)) {
        seen.add(mesh.uuid + name);
        out.push({ mesh, index: dict[name] });
      }
    }
  });
  return out;
}

/** Write one morph value everywhere it exists on the rig. */
export function applyMorph(root, target, value) {
  const bindings = resolveMorphBindings(root, target);
  for (const b of bindings) {
    if (b.mesh.morphTargetInfluences) b.mesh.morphTargetInfluences[b.index] = value;
  }
  return bindings.length;
}
