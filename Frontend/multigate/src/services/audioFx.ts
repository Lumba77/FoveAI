/**
 * audioFx — typed data layer for the PipeWire Audio FX surface.
 *
 * The backend (foveated-memory server.js :8400) shells to
 * Tools/audio-variator-eq and answers:
 *   GET  /api/audio-fx/state   → { ok, output, input, presets }
 *   POST /api/audio-fx/preset  → { ok, applied, output, log }
 *   POST /api/audio-fx/bypass  → { ok, bypass, output }
 *
 * House rules honoured here (see src/services/registry.ts):
 *   1. no component ever names a URL — the route lives in SERVICES;
 *   2. nothing throws into the void — every call is a discriminated result
 *      with a timeout, a retry budget and a circuit breaker, so a backend
 *      that is down degrades this surface instead of blanking the page;
 *   3. absence is a value — the caller branches on `ok`, never on a throw.
 *
 * The field names below mirror the CLI output of `set-eq --json` and
 * `set-mic-fx --json` exactly. Unknown extra keys are tolerated (the CLI
 * grows), missing ones are not assumed.
 */

import { safeFetch } from './registry';

/** Output lane — PipeWire EQ + studio pitch/effects (set-eq --json). */
export interface AudioFxOutput {
  bypass: boolean;
  bass: number;
  mid: number;
  treble: number;
  bass_freq: number;
  mid_freq: number;
  treble_freq: number;
  bass_q: number;
  mid_q: number;
  treble_q: number;
  bal_low: string;
  bal_high: string;
  pitch: number;
  warp: number;
  loudness: number;
  compressor: number;
  reverb: number;
  reverb_type: string;
  delay: number;
  delay_type: string;
  chorus: number;
  chorus_type: string;
  modulator: number;
  width: number;
}

/** Input lane — mic FX (set-mic-fx --json); all values are 0–100 %. */
export interface AudioFxInput {
  noise: number;
  clarity: number;
  voxpress: number;
  drive: number;
  echo: number;
  voxrev: number;
  aux: boolean;
}

export interface AudioFxPreset {
  name: string;
  cat: string | null;
}

export interface AudioFxState {
  ok: true;
  output: AudioFxOutput;
  input: AudioFxInput;
  presets: AudioFxPreset[];
}

export interface AudioFxPresetResult {
  ok: true;
  applied: string;
  output: AudioFxOutput;
  log: string;
}

export interface AudioFxBypassResult {
  ok: true;
  bypass: boolean;
  output: AudioFxOutput;
}

export type AudioFxResult<T> =
  | T
  | { ok: false; status: number; error: string };

const fail = (status: number, error: string): { ok: false; status: number; error: string } =>
  ({ ok: false, status, error });

/** Preset names are user input; the UI trims before we ever send one. */
export function isValidPresetName(name: string): boolean {
  return /^[A-Za-z0-9 _-]{1,64}$/.test(name);
}

/** Read-only snapshot of both lanes + the preset list. Never mutates audio. */
export async function fetchAudioFxState(timeoutMs = 6000): Promise<AudioFxResult<AudioFxState>> {
  const res = await safeFetch('audiofx', {
    method: 'GET',
    suffix: '/state',
    retries: 0,
    timeoutMs,
  });
  if (!res.ok) return fail(res.status, res.error || `backend answered ${res.status}`);
  const d = res.data;
  if (!d || typeof d !== 'object' || !d.output || !d.input) {
    return fail(res.status || 200, 'malformed state payload');
  }
  return {
    ok: true,
    output: d.output as AudioFxOutput,
    input: d.input as AudioFxInput,
    presets: Array.isArray(d.presets) ? (d.presets as AudioFxPreset[]) : [],
  };
}

/** Apply a scene preset by name. Mutates the live PipeWire graph. */
export async function applyAudioFxPreset(
  name: string,
  timeoutMs = 10000,
): Promise<AudioFxResult<AudioFxPresetResult>> {
  const preset = name.trim();
  if (!isValidPresetName(preset)) {
    return fail(400, 'preset name rejected locally (1-64 chars of A–Z, 0–9, space, _ or -)');
  }
  const res = await safeFetch('audiofx', {
    method: 'POST',
    suffix: '/preset',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preset }),
    retries: 0,
    timeoutMs,
  });
  if (!res.ok) return fail(res.status, res.error || `backend answered ${res.status}`);
  const d = res.data;
  if (!d || d.ok !== true || !d.output) return fail(res.status || 200, 'malformed preset payload');
  return { ok: true, applied: d.applied ?? preset, output: d.output as AudioFxOutput, log: String(d.log || '') };
}

/** Master FX bypass. Mutates the live PipeWire graph. */
export async function setAudioFxBypass(
  bypass: boolean,
  timeoutMs = 10000,
): Promise<AudioFxResult<AudioFxBypassResult>> {
  const res = await safeFetch('audiofx', {
    method: 'POST',
    suffix: '/bypass',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bypass }),
    retries: 0,
    timeoutMs,
  });
  if (!res.ok) return fail(res.status, res.error || `backend answered ${res.status}`);
  const d = res.data;
  if (!d || d.ok !== true || !d.output) return fail(res.status || 200, 'malformed bypass payload');
  return { ok: true, bypass: !!d.bypass, output: d.output as AudioFxOutput };
}

/** Display helpers — one place decides how a raw number is worded. */
export const fmtDb = (v: number): string => `${v > 0 ? '+' : ''}${Number(v ?? 0).toFixed(1)} dB`;
export const fmtPct = (v: number): string => `${Math.round(Number(v ?? 0))}%`;
export const fmtSemi = (v: number): string => `${Number(v ?? 0) > 0 ? '+' : ''}${Math.round(Number(v ?? 0))} st`;
export const fmtHz = (v: number): string => `${Math.round(Number(v ?? 0)).toLocaleString()} Hz`;