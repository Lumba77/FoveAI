import { useState, useEffect, useCallback, useRef } from 'react';
import { useTraits } from './trackball/useTraits';

/**
 * IgnitionScreen — the gate. Simple and stable by design (2026-10-08):
 * after days of the animated vault fighting the Quest WebView (flicker,
 * image re-decode storms, hover/zoom thrash), the start page is now a
 * calm, bulletproof surface:
 *   1. pick a saved pattern (or leave the last one)
 *   2. optional: tweak individual settings in a plain list
 *   3. Enter — the site loads with those settings as its base.
 * The trackball instrument remains available via /vault.html for the
 * day it gets a proper, device-tested revival.
 */

const SLOTS = [
  { id: 'mode',   label: 'Cognitive mode', opts: ['local', 'cloud', 'juggle', 'tandem', 'triune'], key: 'XRLF_COGNITIVE_MODE' },
  { id: 'think',  label: 'Reasoning',      opts: ['off', 'on'], key: 'XRLF_MODEL_THINKING' },
  { id: 'voice',  label: 'Voice',          opts: ['off', 'on'], key: 'XRLF_VOICE_ENABLED' },
  { id: 'mic',    label: 'Microphone',     opts: ['off', 'on'], key: 'XRLF_MIC_ENABLED' },
] as const;

export default function IgnitionScreen({ userName, onEnter }: { userName?: string; onEnter: () => void }) {
  const tb = useTraits();
  const [values, setValues] = useState<Record<string, string>>({});
  const [ready, setReady] = useState(false);
  const [entering, setEntering] = useState(false);
  const alive = useRef(true);

  /* load current settings once — they persist in .env, so the gate always
     greets you with your last configuration */
  useEffect(() => {
    alive.current = true;
    (async () => {
      const out: Record<string, string> = {};
      for (const s of SLOTS) {
        let v = '';
        try {
          const r = await fetch(`/api/setting?key=${encodeURIComponent(s.key)}`, { signal: AbortSignal.timeout(3000) });
          if (r.ok) v = String((await r.json()).value ?? '');
        } catch { /* offline: leave default */ }
        out[s.id] = v || (s.opts[0] === 'off' ? (s as any).opts[1] : (s as any).opts[0]);
      }
      // dials (ring settings) too — reuse the trait store's reload
      await tb.reload();
      if (alive.current) { setValues(out); setReady(true); }
    })();
    return () => { alive.current = false; };
  }, []);

  const setSlot = useCallback((id: string, key: string, val: string) => {
    setValues(p => ({ ...p, [id]: val }));
    fetch('/api/setting', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, val }),
      signal: AbortSignal.timeout(4000),
    }).catch(() => {});
  }, []);

  const enter = useCallback(() => {
    if (entering) return;
    setEntering(true);
    onEnter();
  }, [entering, onEnter]);

  const names = Object.keys(tb.listPatterns());

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 100000,
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      gap: '18px', padding: '24px', overflowY: 'auto',
      fontFamily: "'Share Tech Mono', monospace", color: '#dfe7ff',
      background:
        "radial-gradient(1px 1px at 12% 22%, rgba(255,255,255,.8), transparent 60%)," +
        "radial-gradient(1px 1px at 68% 8%, rgba(255,255,255,.6), transparent 60%)," +
        "radial-gradient(1.5px 1.5px at 84% 44%, rgba(200,220,255,.7), transparent 60%)," +
        "radial-gradient(1px 1px at 34% 66%, rgba(255,255,255,.5), transparent 60%)," +
        "radial-gradient(1px 1px at 52% 88%, rgba(255,240,210,.6), transparent 60%)," +
        "radial-gradient(900px 500px at 78% -10%, rgba(167,139,250,.14), transparent 60%)," +
        "radial-gradient(1100px 600px at 15% 110%, rgba(94,234,212,.08), transparent 60%)," +
        "linear-gradient(165deg, #0c1028 0%, #090b1c 40%, #050712 100%)",
    }}>
      <img src="/foveai-logo-light.png" alt="FoveAI"
        style={{ height: '56px', display: 'block',
                 filter: 'drop-shadow(0 0 18px rgba(94,234,212,.28)) drop-shadow(0 2px 2px rgba(0,0,0,.7))' }} />
      <div style={{ fontSize: '13px', letterSpacing: '4px', color: '#9a8757' }}>
        CONCORDIA · GATE
      </div>

      {userName && (
        <div style={{ fontSize: '14px', color: '#8a94b8' }}>welcome back, <span style={{ color: '#eaffd0' }}>{userName}</span></div>
      )}

      {names.length > 0 && (
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', justifyContent: 'center', maxWidth: '520px' }}>
          {names.map(n => (
            <button key={n} onClick={() => tb.loadPattern(n)}
              style={{
                fontSize: '12px', color: '#c9f0ae', background: 'rgba(10,12,8,.5)',
                border: '1px solid rgba(255,200,90,.3)', borderRadius: '7px', padding: '6px 12px', cursor: 'pointer',
              }}>
              {n}
            </button>
          ))}
        </div>
      )}

      <div style={{
        display: 'flex', flexDirection: 'column', gap: '10px', minWidth: '320px', maxWidth: '420px', width: '100%',
        padding: '24px 28px',
        background: 'rgba(20, 26, 52, 0.45)',
        border: '1px solid rgba(148, 168, 220, 0.16)',
        borderRadius: '18px',
        backdropFilter: 'blur(12px)',
        boxShadow: 'inset 0 1px 1px rgba(255,255,255,.06), 0 24px 60px rgba(0,0,0,.45)',
      }}>
        {SLOTS.map(s => (
          <label key={s.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', fontSize: '14px' }}>
            <span style={{ color: '#8a94b8' }}>{s.label}</span>
            <select value={values[s.id] ?? ''} onChange={e => setSlot(s.id, s.key, e.target.value)}
              style={{
                fontSize: '14px', color: '#eaffd0', background: '#0d1108',
                border: '1px solid rgba(255,200,90,.35)', borderRadius: '6px', padding: '6px 10px',
              }}>
              {s.opts.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
        ))}
      </div>

      <button onClick={enter} disabled={!ready || entering}
        style={{
          marginTop: '6px', fontSize: '16px', letterSpacing: '3px', padding: '12px 42px', cursor: 'pointer',
          color: entering ? '#8a94b8' : '#052208', fontWeight: 700,
          background: entering ? 'rgba(45,255,106,.15)' : '#2dff6a',
          border: 'none', borderRadius: '10px',
          boxShadow: entering ? 'none' : '0 0 22px rgba(45,255,106,.35)',
          transition: 'background .2s',
        }}>
        {entering ? 'ENTERING…' : 'ENTER'}
      </button>

      <div style={{ fontSize: '11px', color: '#64748b' }}>
        settings persist — the site loads with what you leave here
      </div>
    </div>
  );
}
