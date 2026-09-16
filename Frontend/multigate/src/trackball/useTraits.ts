import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * useTraits — shared state for the trackball instrument.
 *
 * The dial positions are REAL settings: each Trait with a `key` round-trips
 * through the proxy's /api/setting (same env keys the FoveAI Command console
 * edits). `key: null` traits are local/cosmetic (localStorage).
 * Rolling the ball anywhere — ignition screen or sidebar — turns the same
 * dials, so the ball is one control device for the whole stack.
 */

export interface Trait {
  id: string;
  label: string;
  key: string | null;                          // env key via /api/setting
  min?: number; max?: number; step?: number;   // numeric dial
  options?: string[];                          // discrete dial
  up?: string;                                 // 2-option traits: the value "push up" selects
}

export const FINISHES = ['brass', 'gunmetal', 'copper', 'chrome'];
export const FINISH_TINT: Record<string, string> = {
  brass: '#ffb833', gunmetal: '#9aa4ad', copper: '#e08a4e', chrome: '#cfe3ea',
};

export const TRAITS: Trait[] = [
  { id: 'mode',     label: 'MODE',     key: 'XRLF_COGNITIVE_MODE',       options: ['local', 'cloud'], up: 'cloud' },
  { id: 'think',    label: 'REASON',   key: 'XRLF_MODEL_THINKING',       options: ['false', 'true'], up: 'true' },
  { id: 'compress', label: 'COMPRESS', key: 'XRLF_PROXY_AGGRESSION',     min: 0, max: 5,     step: 1 },
  { id: 'keep',     label: 'KEEP',     key: 'XRLF_CLOUD_PRESERVE_LAST',  min: 0, max: 64,    step: 4 },
  { id: 'cadence',  label: 'CADENCE',  key: 'FOVEA_COMPRESS_EVERY',      min: 2, max: 64,    step: 2 },
  { id: 'tokcap',   label: 'TOK CAP',  key: 'XRLF_CLOUD_MAX_TOKENS_CAP', min: 0, max: 32768, step: 2048 },
  { id: 'ctx',      label: 'CTX',      key: 'XRLF_SPOOF_CONTEXT_WINDOW', options: ['8192', '16384', '32768', '65536', '131072'] },
  { id: 'voice',    label: 'VOICE',    key: 'XRLF_VOICE_ENABLED',        options: ['true', 'false'], up: 'true' },
  { id: 'mic',      label: 'MIC',      key: 'XRLF_MIC_ENABLED',          options: ['false', 'true'], up: 'true' },
  { id: 'finish',   label: 'FINISH',   key: null,                        options: FINISHES },
];

export const dialAngle = (i: number) => -90 + i * (360 / TRAITS.length);

/** hemisphere split for 2-option traits — push up = `up`, pull down = the other */
export const boolDirs = (t: Trait): { up: string; down: string } | null => {
  if (t.options?.length !== 2) return null;
  const up = t.up ?? t.options[1];
  return { up, down: t.options.find(o => o !== up)! };
};

/** value → human label (true/false → ON/OFF, rest uppercased) */
export const fmtVal = (v: string): string =>
  v === 'true' ? 'ON' : v === 'false' ? 'OFF' : v.toUpperCase();

export interface TraitStore {
  values: Record<string, string>;
  armedId: string;
  setArmedId: (id: string) => void;
  armed: Trait;
  armedIdx: number;
  finishTint: string;
  normTrait: (t: Trait) => number;
  bumpTrait: (t: Trait, dir: number) => void;
  setTrait: (t: Trait, v: string) => void;
  displayVal: (t: Trait) => string;
  reload: () => Promise<void>;
}

export function useTraits(onSaved?: () => void): TraitStore {
  const [values, setValues] = useState<Record<string, string>>({});
  const [armedId, setArmedId] = useState<string>('compress');
  const alive = useRef(true);

  const saveTrait = useCallback((t: Trait, v: string) => {
    if (t.key) {
      fetch('/api/setting', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: t.key, val: v }),
        signal: AbortSignal.timeout(5000),
      }).then(() => onSaved?.()).catch(() => {});
    } else {
      localStorage.setItem('foveai_ignition_finish', v);
      onSaved?.();
    }
  }, [onSaved]);

  const setTrait = useCallback((t: Trait, v: string) => {
    setValues(p => ({ ...p, [t.id]: v }));
    saveTrait(t, v);
  }, [saveTrait]);

  const bumpTrait = useCallback((t: Trait, dir: number) => {
    let nv: string;
    if (t.options) {
      const i = Math.max(0, t.options.indexOf(String(values[t.id])));
      nv = t.options[(i + dir + t.options.length) % t.options.length];
    } else {
      const cur = parseFloat(String(values[t.id] ?? t.min));
      const v = Number.isFinite(cur) ? cur : t.min!;
      nv = String(Math.min(t.max!, Math.max(t.min!, v + dir * t.step!)));
    }
    setTrait(t, nv);
  }, [values, setTrait]);

  const normTrait = useCallback((t: Trait): number => {
    const raw = String(values[t.id]);
    if (t.options) {
      const bd = boolDirs(t);
      if (bd) return raw === bd.up ? 1 : 0;      // hemisphere: lit = "up" value
      const i = t.options.indexOf(raw);
      return t.options.length < 2 ? 1 : Math.max(0, i) / (t.options.length - 1);
    }
    const v = parseFloat(raw);
    return Number.isFinite(v) ? Math.min(1, Math.max(0, (v - t.min!) / (t.max! - t.min!))) : 0;
  }, [values]);

  const displayVal = useCallback((t: Trait): string => {
    const raw = String(values[t.id] ?? '');
    if (raw === '') return '—';
    if (raw === 'true') return 'ON';
    if (raw === 'false') return 'OFF';
    return raw;
  }, [values]);

  const reload = useCallback(async () => {
    const tv: Record<string, string> = {};
    for (const t of TRAITS) {
      const fallback = t.options ? t.options[0] : String(t.min);
      if (!t.key) { tv[t.id] = localStorage.getItem('foveai_ignition_finish') || fallback; continue; }
      try {
        const r = await fetch(`/api/setting?key=${encodeURIComponent(t.key)}`, { signal: AbortSignal.timeout(3000) });
        if (r.ok) {
          const v = String((await r.json()).value ?? '');
          tv[t.id] = v !== '' && v !== 'null' ? v : fallback;
        } else tv[t.id] = fallback;
      } catch (_) { tv[t.id] = fallback; }
    }
    if (alive.current) setValues(tv);
  }, []);

  useEffect(() => {
    alive.current = true;
    reload();
    return () => { alive.current = false; };
  }, [reload]);

  const armed = TRAITS.find(t => t.id === armedId) ?? TRAITS[0];
  const armedIdx = TRAITS.indexOf(armed);
  const finishName = FINISHES.includes(values['finish']) ? values['finish'] : FINISHES[0];
  const finishTint = FINISH_TINT[finishName];

  return { values, armedId, setArmedId, armed, armedIdx, finishTint, normTrait, bumpTrait, setTrait, displayVal, reload };
}
