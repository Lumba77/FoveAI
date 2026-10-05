import { useState, useEffect, useRef, useCallback } from 'react';
import Trackball from './trackball/Trackball';
import { boolDirs, fmtVal } from './trackball/useTraits';
import { useTraits, TRAITS } from './trackball/useTraits';

/**
 * IgnitionScreen — the FoveAI boot ritual, garage edition.
 *
 * Design language: inventor's workshop. A full-width sprayed-metal logo
 * plate screwed to the wall, brass-bezel LCD consoles with two-column
 * data tables (Jenna-plugin style) flanking left AND right, diode
 * work-lights shining down from the top edge, dust in the beams — and in
 * the center the Concordia Thorium Core, a car-emblem-sized red button on
 * a bolted metal ring, so every dial value stays in view while you roll.
 *
 * Press it: heavy reverbed clack, mains hum, crackle, a sawtooth riser
 * swelling under garage reverb — all synthesized WebAudio, no assets.
 * Then real health checks gate the handoff into the Multigate.
 */

type Phase = 'boot' | 'idle' | 'igniting' | 'ready' | 'entering';

interface StatusData {
  status?: string;
  total_memories?: number;
  total_themes?: number;
  total_sessions?: number;
  model?: string;
  is_hybrid?: boolean;
  loaded?: boolean;
  load_state?: string;
  load_error?: string | null;
}

const SNAPSHOT_KEYS: Array<{ key: string; label: string }> = [
  { key: 'XRLF_MODEL_LOCAL_ID', label: 'Local model' },
  { key: 'XRLF_COGNITIVE_MODE', label: 'Cognitive mode' },
  { key: 'XRLF_PROXY_AGGRESSION', label: 'Compression' },
  { key: 'FOVEAI_FRONTEND_UI', label: 'Frontend' },
];

const SNAPSHOT_STORE = 'foveai_ignition_snapshot';
const IGNITION_URL = '/ignition';

/* ── rotary dial: 10 persona-critical positions around the core ──
   sweep the ring to arm a position · roll the ball to turn its value
   (instrument lives in ./trackball — same device also sits in the app
   sidebar, so the ball controls the whole console) */

/* ══ Audio engine — garage-grade synthesized sound ═══════════════════ */

function garageIR(ctx: AudioContext, seconds = 2.8, decay = 2.4): AudioBuffer {
  // synthetic garage impulse: big concrete space, long dark tail
  const len = Math.floor(ctx.sampleRate * seconds);
  const buf = ctx.createBuffer(2, len, ctx.sampleRate);
  for (let ch = 0; ch < 2; ch++) {
    const d = buf.getChannelData(ch);
    for (let i = 0; i < len; i++) {
      const t = i / len;
      d[i] = (Math.random() * 2 - 1) * Math.pow(1 - t, decay) *
             (t < 0.02 ? t / 0.02 : 1); // soft attack = walls, not a drum
    }
  }
  return buf;
}

function makeReverb(ctx: AudioContext): ConvolverNode {
  const conv = ctx.createConvolver();
  conv.buffer = garageIR(ctx);
  return conv;
}

function playIgnitionAudio() {
  try {
    const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
    const t = ctx.currentTime;
    const verb = makeReverb(ctx);
    const wet = ctx.createGain(); wet.gain.value = 0.55;
    const dry = ctx.createGain(); dry.gain.value = 0.8;
    verb.connect(wet).connect(ctx.destination);
    dry.connect(ctx.destination);

    /* heavy mechanical clack — metal contact + body thunk */
    const clack = ctx.createOscillator();
    const clackG = ctx.createGain();
    clack.type = 'square';
    clack.frequency.setValueAtTime(220, t);
    clack.frequency.exponentialRampToValueAtTime(48, t + 0.11);
    clackG.gain.setValueAtTime(0.5, t);
    clackG.gain.exponentialRampToValueAtTime(0.001, t + 0.16);
    clack.connect(clackG); clackG.connect(dry); clackG.connect(verb);
    clack.start(t); clack.stop(t + 0.17);

    /* contact noise burst */
    const nb = ctx.createBufferSource();
    const nbuf = ctx.createBuffer(1, 4410, ctx.sampleRate);
    const nd = nbuf.getChannelData(0);
    for (let i = 0; i < nd.length; i++) nd[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / nd.length, 2);
    nb.buffer = nbuf;
    const nbp = ctx.createBiquadFilter(); nbp.type = 'bandpass'; nbp.frequency.value = 2600; nbp.Q.value = 0.8;
    const ng = ctx.createGain(); ng.gain.setValueAtTime(0.35, t);
    ng.gain.exponentialRampToValueAtTime(0.001, t + 0.08);
    nb.connect(nbp); nbp.connect(ng); ng.connect(dry); ng.connect(verb);
    nb.start(t);

    /* mains hum — 50Hz + 3rd harmonic, wobbling like old wiring */
    const hum = ctx.createOscillator(); hum.type = 'sine'; hum.frequency.value = 50;
    const hum3 = ctx.createOscillator(); hum3.type = 'sine'; hum3.frequency.value = 150;
    const humG = ctx.createGain(); humG.gain.setValueAtTime(0.0001, t + 0.05);
    humG.gain.exponentialRampToValueAtTime(0.07, t + 0.7);
    humG.gain.exponentialRampToValueAtTime(0.001, t + 6);
    const hum3G = ctx.createGain(); hum3G.gain.value = 0.3;
    const wob = ctx.createOscillator(); wob.frequency.value = 6.7;
    const wobG = ctx.createGain(); wobG.gain.value = 0.02;
    wob.connect(wobG); wobG.connect(humG.gain);
    hum.connect(humG); hum3.connect(hum3G); hum3G.connect(humG);
    humG.connect(dry); humG.connect(verb);
    hum.start(t); hum3.start(t); wob.start(t);
    hum.stop(t + 6.2); hum3.stop(t + 6.2); wob.stop(t + 6.2);

    /* reactor riser — sawtooth through a slowly opening lowpass, drenched */
    const riser = ctx.createOscillator(); riser.type = 'sawtooth';
    riser.frequency.setValueAtTime(36, t + 0.2);
    riser.frequency.linearRampToValueAtTime(96, t + 3.4);
    const rlp = ctx.createBiquadFilter(); rlp.type = 'lowpass';
    rlp.frequency.setValueAtTime(140, t + 0.2);
    rlp.frequency.exponentialRampToValueAtTime(900, t + 3.4);
    const rg = ctx.createGain(); rg.gain.setValueAtTime(0.0001, t + 0.2);
    rg.gain.exponentialRampToValueAtTime(0.16, t + 2.6);
    rg.gain.exponentialRampToValueAtTime(0.001, t + 5.2);
    riser.connect(rlp); rlp.connect(rg); rg.connect(dry); rg.connect(verb);
    riser.start(t + 0.2); riser.stop(t + 5.4);

    /* faint wind — brown noise wandering through a bandpass */
    const wind = ctx.createBufferSource();
    const wlen = ctx.sampleRate * 6;
    const wbuf = ctx.createBuffer(1, wlen, ctx.sampleRate);
    const wd = wbuf.getChannelData(0);
    let last = 0;
    for (let i = 0; i < wlen; i++) {
      last = (last + 0.02 * (Math.random() * 2 - 1)) / 1.02;
      wd[i] = last * 3;
    }
    wind.buffer = wbuf;
    const wbp = ctx.createBiquadFilter(); wbp.type = 'bandpass'; wbp.frequency.value = 320; wbp.Q.value = 2.5;
    const wg = ctx.createGain(); wg.gain.setValueAtTime(0.0001, t + 0.4);
    wg.gain.linearRampToValueAtTime(0.028, t + 2.5);
    wg.gain.linearRampToValueAtTime(0.0001, t + 6.2);
    wind.connect(wbp); wbp.connect(wg); wg.connect(verb); wg.connect(dry);
    wind.start(t + 0.4);

    /* electric crackle — sparse glitchy ticks during spin-up */
    for (let k = 0; k < 14; k++) {
      const tt = t + 0.3 + Math.random() * 3.4;
      const c = ctx.createBufferSource();
      const cb = ctx.createBuffer(1, 700, ctx.sampleRate);
      const cd = cb.getChannelData(0);
      for (let i = 0; i < cd.length; i++) cd[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / cd.length, 3);
      c.buffer = cb;
      const hp = ctx.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 2400 + Math.random() * 3000;
      const cg = ctx.createGain(); cg.gain.setValueAtTime(0.05 + Math.random() * 0.1, tt);
      c.connect(hp); hp.connect(cg); cg.connect(verb); cg.connect(dry);
      c.start(tt);
    }
  } catch (_) { /* audio is garnish */ }
}

/* corner screws for metal plates (4-corner, for the big logo plate) */
const SCREW_BG = [
  'radial-gradient(circle 5px at 14px 14px, #1a1a1a 0 2px, #666 3px, #3a3a3a 4px, #777 5px, transparent 5px)',
  'radial-gradient(circle 5px at calc(100% - 14px) 14px, #1a1a1a 0 2px, #666 3px, #3a3a3a 4px, #777 5px, transparent 5px)',
  'radial-gradient(circle 5px at 14px calc(100% - 14px), #1a1a1a 0 2px, #666 3px, #3a3a3a 4px, #777 5px, transparent 5px)',
  'radial-gradient(circle 5px at calc(100% - 14px) calc(100% - 14px), #1a1a1a 0 2px, #666 3px, #3a3a3a 4px, #777 5px, transparent 5px)',
].join(',');

/* 2 screws only — left/right mid-height, for slim header bars */
const SCREW_BG_2 = [
  'radial-gradient(circle 4px at 13px 50%, #141414 0 1.5px, #5a5a5a 2.5px, #333 3.5px, transparent 4px)',
  'radial-gradient(circle 4px at calc(100% - 13px) 50%, #141414 0 1.5px, #5a5a5a 2.5px, #333 3.5px, transparent 4px)',
].join(',');

/* ── settings snapshot ("Since Last Visit" drift log — kept in localStorage) ── */

export default function IgnitionScreen({ userName, token, onEnter }: { userName?: string; token?: string; onEnter: () => void }) {
  const [phase, setPhase] = useState<Phase>('boot');
  const [status, setStatus] = useState<StatusData | null>(null);
  const [stackUp, setStackUp] = useState(false);
  const [modelReady, setModelReady] = useState(false);
  const [log, setLog] = useState<Array<{ text: string; ok: boolean | null }>>([]);
  const [savedFlash, setSavedFlash] = useState(false);
  const [flicker, setFlicker] = useState(0);
  const tb = useTraits(useCallback(() => {
    setSavedFlash(true);
    setTimeout(() => setSavedFlash(false), 1500);
  }, []));
  const logRef = useRef<HTMLDivElement>(null);
  const plateWrapRef = useRef<HTMLDivElement>(null);
  const aliveRef = useRef(true);

  const pushLog = useCallback((text: string, ok: boolean | null = null) => {
    setLog((prev) => [...prev.slice(-9), { text, ok }]);
  }, []);

  /* fluorescent flicker — old electrics breathing */
  useEffect(() => {
    let to: ReturnType<typeof setTimeout>;
    const loop = () => {
      setFlicker(Math.random() < 0.12 ? 0.75 + Math.random() * 0.25 : 1);
      to = setTimeout(loop, 120 + Math.random() * 900);
    };
    loop();
    return () => clearTimeout(to);
  }, []);

  const probe = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch('/api/status', { signal: AbortSignal.timeout(3500) });
      if (!res.ok) throw new Error(String(res.status));
      const data: StatusData = await res.json();
      setStatus(data); setStackUp(true);
      // Model readiness is merged into /api/status server-side — no separate
      // (session-shielded) /xrlf/health round-trip needed from the browser.
      setModelReady(data.loaded === true || data.load_state === 'ready');
      return true;
    } catch {
      setStackUp(false); setModelReady(false);
      return false;
    }
  }, []);

  const loadPanelData = useCallback(async () => {
    const next: Record<string, string> = {};
    for (const { key } of SNAPSHOT_KEYS) {
      let cur: string | null = null;
      try {
        const r = await fetch(`/api/setting?key=${encodeURIComponent(key)}`, { signal: AbortSignal.timeout(3000) });
        if (r.ok) cur = (await r.json()).value;
      } catch (_) {}
      next[key] = cur ?? '';
    }
    localStorage.setItem(SNAPSHOT_STORE, JSON.stringify(next));
  }, []);

  useEffect(() => {
    aliveRef.current = true;
    (async () => {
      const up = await probe();
      await loadPanelData();
      if (aliveRef.current) setPhase('idle');
      if (!up) pushLog('proxy silent — reactor cold', false);
    })();
    const iv = setInterval(probe, 5000);
    return () => { aliveRef.current = false; clearInterval(iv); };
  }, [probe, loadPanelData, pushLog]);

  /* beta charter — who is boarding (kept: auth readiness check only) */
  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        await fetch('/api/auth/me', {
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(4000),
        });
      } catch (_) {}
    })();
  }, [token]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [log]);

  const ignite = useCallback(async () => {
    if (phase === 'igniting' || phase === 'entering') return;
    playIgnitionAudio();
    setPhase('igniting');
    setLog([]);
    (async () => {
      pushLog('◈ THORIUM LATTICE ENERGIZED');
      if (!stackUp) {
        pushLog('◈ cold core — sending ignition pulse…');
        try { await fetch(IGNITION_URL, { method: 'POST', signal: AbortSignal.timeout(8000) }); } catch (_) {}
      }
      let up = false;
      for (let i = 0; i < 30 && aliveRef.current; i++) {
        if (await probe()) { up = true; break; }
        await new Promise(r => setTimeout(r, 2000));
      }
      pushLog(up ? '◈ HELIUM CIRCULATORS ONLINE — proxy :8400' : '◈ circulators stalled (proxy :8400)', up);
      if (!up) { setPhase('idle'); return; }
      pushLog('◈ NEUTRON FLUX RISING — model check…');
      let ready = false;
      for (let i = 0; i < 60 && aliveRef.current; i++) {
        try {
          const h = await fetch('/api/status', { signal: AbortSignal.timeout(2500) });
          if (h.ok) {
            const hj: StatusData = await h.json();
            if (hj.loaded === true || hj.load_state === 'ready') { ready = true; break; }
            if (hj.load_state === 'error') { pushLog(`◈ core fault: ${hj.load_error || 'unknown'}`, false); setPhase('idle'); return; }
          }
        } catch (_) {}
        await new Promise(r => setTimeout(r, 2000));
      }
      pushLog(ready ? '◈ MEMORY BANKS SYNCHRONIZED' : '◈ model not ready yet — entering anyway', ready ? true : null);
      pushLog(`◈ CORE NOMINAL — welcome back${userName ? ', ' + userName : ''}`, true);
      setPhase('ready');
      setTimeout(() => { if (aliveRef.current) { setPhase('entering'); setTimeout(onEnter, 700); } }, 900);
    })();
  }, [phase, stackUp, probe, pushLog, userName, onEnter]);

  const { armed, armedIdx, finishTint, normTrait, displayVal } = tb;
  const coreColor = phase === 'idle' || phase === 'boot' ? '#ff3524' : '#39ff70';
  const spinning = phase === 'igniting' || phase === 'ready' || phase === 'entering';
  const armedVal = displayVal(armed);
  const armedBool = boolDirs(armed);

  // each halo ring belongs to dial position i%10 — spin rate follows its
  // value, so the seven foveated rings literally balance against each other
  const ringPeriod = (i: number) => {
    const norm = normTrait(TRAITS[i % TRAITS.length]);
    const base = 26 - i * 2.4;
    return spinning ? base / (1.6 + i * 0.35) : base / (0.5 + norm * 2.2);
  };

  return (
    <div className={`ign-screen ${phase === 'entering' ? 'ign-exit' : ''}`} style={{ ['--flick' as any]: flicker }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Share+Tech+Mono&display=swap');

        .ign-screen { position: fixed; inset: 0; z-index: 100000; display: flex; flex-direction: column;
          overflow-y: auto; overflow-x: hidden;
          font-family: 'Share Tech Mono', monospace; color: #dfe7ff; font-size: 15px;
          background:
            radial-gradient(1px 1px at 12% 22%, rgba(255,255,255,.85), transparent 60%),
            radial-gradient(1px 1px at 68% 8%, rgba(255,255,255,.65), transparent 60%),
            radial-gradient(1.5px 1.5px at 84% 44%, rgba(200,220,255,.75), transparent 60%),
            radial-gradient(1px 1px at 34% 66%, rgba(255,255,255,.55), transparent 60%),
            radial-gradient(1px 1px at 52% 88%, rgba(255,240,210,.65), transparent 60%),
            radial-gradient(1.5px 1.5px at 8% 78%, rgba(255,255,255,.5), transparent 60%),
            radial-gradient(1px 1px at 91% 81%, rgba(255,255,255,.65), transparent 60%),
            radial-gradient(1px 1px at 44% 34%, rgba(180,200,255,.45), transparent 60%),
            radial-gradient(900px 500px at 78% -10%, rgba(167,139,250,.14), transparent 60%),
            radial-gradient(1100px 600px at 15% 110%, rgba(94,234,212,.08), transparent 60%),
            radial-gradient(1400px 500px at 50% -15%, rgba(255,190,70,.08), transparent 60%),
            linear-gradient(165deg, rgba(12,16,40,.86) 0%, rgba(9,11,28,.90) 40%, rgba(5,7,18,.95) 100%),
            url('/garage/backdrop.png') center / cover no-repeat,
            linear-gradient(165deg, #0c1028 0%, #090b1c 40%, #050712 100%);
          transition: opacity .7s ease, transform .7s ease; }
        .ign-exit { opacity: 0; transform: scale(1.05); pointer-events: none; }
        .ign-screen::before { content:''; position:absolute; inset:0; pointer-events:none;
          background: repeating-linear-gradient(0deg, transparent 0 3px, rgba(0,0,0,.10) 3px 4px); }
        .ign-screen::after { content:''; position:absolute; inset:0; pointer-events:none;
          box-shadow: inset 0 0 200px rgba(0,0,0,.8); }

        /* diode work-lights: cone beams directed down from the top edge */
        .ign-lights { position:absolute; top:0; left:0; right:0; height:60vh; pointer-events:none;
          background:
            conic-gradient(from 168deg at 22% 0%, transparent 0, rgba(255,205,90,.10) 6deg, rgba(255,205,90,.02) 11deg, transparent 13deg),
            conic-gradient(from 168deg at 50% 0%, transparent 0, rgba(255,205,90,.09) 6deg, rgba(255,205,90,.02) 11deg, transparent 13deg),
            conic-gradient(from 168deg at 78% 0%, transparent 0, rgba(140,255,160,.08) 6deg, rgba(140,255,160,.02) 11deg, transparent 13deg),
            radial-gradient(240px 200px at 22% -30px, rgba(255,215,110,.28), transparent 70%),
            radial-gradient(240px 200px at 50% -30px, rgba(255,215,110,.22), transparent 70%),
            radial-gradient(240px 200px at 78% -30px, rgba(140,255,160,.18), transparent 70%);
          opacity: var(--flick, 1); }
        .ign-diodes { position:absolute; top:0; left:0; right:0; height:8px; pointer-events:none;
          background:
            radial-gradient(circle 4px at 22% 4px, #ffe9a8 0 2px, rgba(255,205,90,.9) 3px, transparent 4px),
            radial-gradient(circle 4px at 50% 4px, #ffe9a8 0 2px, rgba(255,205,90,.9) 3px, transparent 4px),
            radial-gradient(circle 4px at 78% 4px, #b8ffc0 0 2px, rgba(140,255,160,.9) 3px, transparent 4px); }
        .ign-dust { position:absolute; inset:0; pointer-events:none; overflow:hidden; }
        .mote { position:absolute; width:2px; height:2px; border-radius:50%;
          background: rgba(255,220,140,.35); animation: mote-drift linear infinite; }
        @keyframes mote-drift {
          from { transform: translateY(-10px); opacity:0; }
          15% { opacity:.8; } 85% { opacity:.6; }
          to { transform: translateY(105vh); opacity:0; } }

        /* ── full-width screwed metal logo plate ── */
        .ign-plate { position:relative; flex-shrink:0; margin: 22px 26px 18px;
          padding: 20px 30px; text-align:center;
          border-radius: 14px;
          background:
            ${SCREW_BG},
            linear-gradient(90deg, transparent 0, rgba(255,255,255,.06) 8%, transparent 16%, rgba(255,255,255,.05) 55%, transparent 70%),
            linear-gradient(180deg, rgba(74,68,56,.55) 0%, rgba(51,45,34,.6) 12%, rgba(36,31,22,.72) 55%, rgba(25,21,16,.85) 100%),
            url('/garage/plate.png') center / cover no-repeat;
          box-shadow:
            inset 0 2px 0 rgba(255,235,180,.18), inset 0 -3px 8px rgba(0,0,0,.7),
            0 6px 24px rgba(0,0,0,.6);
          border: 1px solid rgba(255,210,110,.28);
          opacity: var(--flick, 1); }
        .ign-plate::after { content:''; position:absolute; left:30px; right:30px; bottom:6px; height:2px;
          background: linear-gradient(90deg, transparent, rgba(255,200,90,.5), transparent); }
        .ign-logo { font-family:'Orbitron',monospace; font-weight:900; font-size:52px;
          letter-spacing:14px; color:#ffcf3f;
          text-shadow:
            0 0 2px #ffcf3f, 0 0 18px rgba(255,190,60,.55),
            0 2px 0 rgba(0,0,0,.6), 2px 0 1px rgba(255,150,30,.35), -2px 0 1px rgba(255,150,30,.35);
          font-variant: small-caps; transform: rotate(-.4deg); }
        .ign-logo .ai { color:#5dff8f; text-shadow: 0 0 2px #5dff8f, 0 0 20px rgba(90,255,140,.6), 0 2px 0 rgba(0,0,0,.6); }
        .ign-plate-sub { font-size:13px; letter-spacing:5px; color:#9a8757; margin-top:6px; }

        .ign-body { flex:1; display:flex; flex-direction:column; min-height:0; align-items:center; justify-content:center; }
        /* assembled stage — rail tucked under the logo, dial big and overlapping */
        .ign-stage { position:relative; display:flex; align-items:center; justify-content:center;
          gap:2vw; min-height:0; flex:0 0 auto; width:100%; padding:0 2vw;
          max-width:1200px; margin:0 auto; }
        /* between-panel readout — floats in the gap between dial and table */
        .ign-between { position:relative; z-index:20; align-self:center; order:1.5;
          text-align:center; margin-left:-4vw; margin-right:-4vw; }
        .ign-between .trait-readout { font-size:12px; letter-spacing:1.6px; color:#a9b3d4;
          text-align:center; font-family:'Share Tech Mono',monospace;
          background:rgba(10,12,8,.30); backdrop-filter:blur(8px);
          -webkit-backdrop-filter:blur(8px); border:1px solid rgba(255,200,90,.16);
          border-radius:10px; padding:8px 14px; }
        .ign-between .trait-readout b { color:${finishTint}; font-weight:normal; text-shadow:0 0 8px ${finishTint}66; }
        .ign-between .trait-readout .hint { color:#8a94b8; font-size:11px; }
        /* caption — the phase label + log, under the whole group */
        .ign-caption { flex:1 1 100%; display:flex; flex-direction:column; align-items:center;
          gap:6px; margin-top:0; }
        /* dial and rail heights — dial full to its rings, rail matches its content */
        .ign-center { display:flex; flex-direction:column; align-items:center;
          justify-content:center; gap:10px; position:relative; flex:0 0 auto; order:1;
          overflow:visible; padding:.2em 0; }
        .ign-rail { flex:0 0 257px; display:flex; align-items:center; justify-content:flex-start;
          min-width:0; max-width:257px; order:2; margin-left:-1vw; z-index:10;
          height:auto; max-height:min(calc(100vh - 160px), 60vh); margin-top:0; }
        .ign-rail .ign-info { align-self:center; margin-top:0; position:relative;
          min-width:0; max-width:257px; zoom:0.79; transform-origin:left center; }
        .ign-rail .ign-info, .ign-info { background:rgba(10,12,8,.30); }  /* ~70% see-through glass */

        /* ── LCD consoles: brass bezel, metal header rail, 2-col tables ── */
        .lcd { position:relative; border-radius:10px; padding:0; overflow:hidden;
          background: linear-gradient(180deg, rgba(24,30,16,.85), rgba(13,16,8,.88));
          border:1px solid rgba(255,200,90,.26);
          box-shadow: inset 0 0 0 3px #0a0c06, inset 0 0 0 4px rgba(195,155,60,.4),
                      inset 0 2px 18px rgba(0,0,0,.6), 0 4px 14px rgba(0,0,0,.5); }
        .lcd::before { content:''; position:absolute; inset:4px; border-radius:6px; pointer-events:none;
          background: repeating-linear-gradient(0deg, transparent 0 2px, rgba(130,255,140,.025) 2px 3px); }
        .lcd-head { position:relative; padding:4px 30px; font-size:11px; letter-spacing:2.5px;
          color:#ffd766; text-transform:uppercase; font-family:'Orbitron',monospace; font-weight:700;
          background:
            ${SCREW_BG_2},
            linear-gradient(180deg, #4d4636, #2e2918 60%, #221d10);
          border-bottom:2px solid rgba(255,200,90,.35);
          box-shadow: inset 0 1px 0 rgba(255,235,180,.15), 0 2px 6px rgba(0,0,0,.5);
          text-shadow:0 0 12px rgba(255,200,90,.45); }
        .lcd-body { padding:7px 14px 9px; overflow:hidden; }
        table.lcd-tbl { width:100%; border-collapse:collapse; font-size:14px; table-layout:fixed; }
        .lcd-tbl td { padding:3px 5px; border-bottom:1px dashed rgba(140,255,150,.12);
          overflow-wrap:anywhere; word-break:break-word; }
        .lcd-tbl tr:last-child td { border-bottom:none; }
        .tk { color:#8f9a6a; letter-spacing:1px; width:38%; }
        .tv { color:#c9f0ae; text-align:right; }
        .tv.warn { color:#ff9a6a; } .tv.ok { color:#5dff8f; } .tv.chg { color:#ffd766; }

        .sess-item { padding:4px 4px; border-bottom:1px dashed rgba(140,255,150,.12); font-size:14px; }
        .sess-item:last-child { border-bottom:none; }
        .sess-t { color:#d4efb2; overflow-wrap:anywhere; word-break:break-word; }
        .sess-d { color:#7d8a5e; font-size:12px; margin-top:2px; }
        .quick-row { display:flex; align-items:center; gap:12px; padding:4px 2px; font-size:14px; flex-wrap:wrap; }
        .quick-row select { background:#0d1108; color:#c9f0ae; border:1px solid rgba(255,200,90,.35);
          font-family:inherit; font-size:14px; padding:5px 10px; border-radius:5px; }
        .saved { color:#5dff8f; font-size:12px; letter-spacing:1px; }

        /* dial matrix rows — live mirror of the ball's ten positions;
           click a row to arm that dial on the instrument */
        .dial-row { cursor:pointer; }
        .dial-row td { transition:color .15s, text-shadow .15s; }
        .dial-row:hover .tk, .dial-row:hover .tv { color:#eaffd0; }
        .dial-row.armed .tk, .dial-row.armed .tv { color:${finishTint};
          text-shadow:0 0 8px ${finishTint}66; }
        .dial-row.armed .tk::before { content:'◈ '; }
        .dial-meter { display:block; height:3px; margin-top:2px; border-radius:2px;
          background:rgba(140,255,150,.10); overflow:hidden; }
        .dial-meter i { display:block; height:100%; border-radius:2px;
          background:linear-gradient(90deg, rgba(140,255,150,.35), #c9f0ae);
          transition:width .2s; }
        .dial-row.armed .dial-meter i { background:linear-gradient(90deg, ${finishTint}66, ${finishTint}); }

        /* ── hover infopanels — translucent glass sheets floating over the dial ── */
        .ign-info { position:absolute; z-index:50; min-width:230px; max-width:270px;
          border-radius:10px; padding:10px 14px;
          background:rgba(10,12,8,.30);
          backdrop-filter:blur(8px) saturate(1.15);
          -webkit-backdrop-filter:blur(8px) saturate(1.15);
          border:1px solid rgba(255,200,90,.16);
          box-shadow:0 8px 32px rgba(0,0,0,.30), inset 0 0 40px rgba(120,180,255,.03);
          color:#c9f0ae; font-size:11.5px; line-height:1.4;
          pointer-events:none; opacity:0; transform:translateY(6px);
          transition:opacity .22s ease, transform .22s ease; }
        .ign-info.on { opacity:1; transform:translateY(0); }
        .ign-info b { color:#ffd766; letter-spacing:1.2px; font-size:10px;
          text-transform:uppercase; display:block; margin-bottom:4px;
          font-family:'Orbitron',monospace; }
        .ign-info .iv { color:#eaffd0; }
        .ign-info .im { display:block; height:3px; margin-top:6px; border-radius:2px;
          background:rgba(140,255,150,.12); overflow:hidden; }
        .ign-info .im i { display:block; height:100%; border-radius:2px;
          background:linear-gradient(90deg, ${finishTint}66, ${finishTint}); }

        /* panel anchor zones — invisible hit areas flanking the dial */
        .ign-hot { position:absolute; cursor:pointer; z-index:40; }
        .ign-hot:hover ~ .ign-info { opacity:0; }  /* default off until matched */

        /* ── reactor emblem — big hero; outer rings slip behind the rail ── */
        .reactor-wrap { position:relative;
          width:min(calc(100vh - 200px), 46vw);
          height:min(calc(100vh - 200px), 46vw);
          min-width:320px; min-height:320px;
          display:flex; align-items:center; justify-content:center; }
        .reactor-plate { position:relative; width:81%; height:81%; display:flex;
          align-items:center; justify-content:center; border-radius:50%;
          overflow:visible;
          background:
            ${SCREW_BG},
            radial-gradient(circle at 50% 32%, rgba(77,70,54,.5), rgba(42,36,21,.65) 55%, rgba(21,17,10,.9) 100%),
            url('/garage/emblem.png') center / cover no-repeat,
            radial-gradient(circle at 50% 32%, #4d4636, #2a2415 55%, #15110a 100%);
          border:3px solid rgba(200,160,70,.5);
          box-shadow: inset 0 3px 2px rgba(255,235,180,.15), inset 0 -10px 30px rgba(0,0,0,.75),
                      0 14px 44px rgba(0,0,0,.65); }
        .halo { position:absolute; border-radius:50%; pointer-events:none;
          border:2px dotted ${coreColor}55;
          filter: drop-shadow(0 0 4px ${coreColor}44); }
        .halo.armed-ring { border-color:${finishTint}cc;
          filter: drop-shadow(0 0 8px ${finishTint}88); }

        /* the trackball instrument itself lives in trackball/trackball.css */
        .trait-readout { font-size:12px; letter-spacing:1.6px; color:#a9b3d4; text-align:center;
          font-family:'Share Tech Mono',monospace; max-width:520px; margin:0 auto; }
        .trait-readout b { color:${finishTint}; font-weight:normal; text-shadow:0 0 8px ${finishTint}66; }
        .trait-readout .hint { color:#8a94b8; font-size:12px; }
        .reactor-name { font-family:'Orbitron',monospace; font-size:16px; letter-spacing:4px;
          color:${coreColor}; text-shadow:0 0 14px ${coreColor}99; }
        .reactor-label { font-size:13px; letter-spacing:4px; color:#8a94b8; text-transform:uppercase; }

        .ign-log { width:90%; max-width:440px; height:140px; overflow-y:auto;
          font-size:13px; line-height:1.75; color:#a8d68f;
          background:rgba(9,13,6,.8); border:1px solid rgba(120,220,130,.2);
          border-radius:8px; padding:10px 16px;
          box-shadow: inset 0 2px 10px rgba(0,0,0,.6); }
        .ign-log .bad { color:#ff9a6a; } .ign-log .good { color:#5dff8f; }

        @keyframes ignSpin { to { transform: rotate(360deg); } }
        @keyframes ignBreathe {
          0%,100% { box-shadow:0 0 40px #ff352455, inset 0 0 30px #ff352433; }
          50% { box-shadow:0 0 90px #ff352499, inset 0 0 52px #ff352455; } }
        @media (max-width: 1100px) {
          .ign-stage { flex-direction:column; overflow-y:auto; justify-content:center; }
          .ign-center { order:1; overflow:visible; }
          .ign-rail { order:2; max-width:480px; width:90%; justify-content:center; margin-left:0; }
          .reactor-wrap { width:min(64vh, 80vw); height:min(64vh, 80vw); }
        }
      `}</style>

      <div className="ign-lights" />
      <div className="ign-diodes" />
      <div className="ign-dust">
        {Array.from({ length: 26 }).map((_, i) => (
          <div key={i} className="mote" style={{
            left: `${(i * 37.3) % 100}%`,
            animationDuration: `${9 + (i % 7) * 3}s`,
            animationDelay: `${(i * 1.7) % 12}s`,
            opacity: 0.2 + (i % 4) * 0.12,
          }} />
        ))}
      </div>

      {/* brand top-center-left — the rail aligns beneath it */}
      <div className="ign-brand" style={{ position:'absolute', left:'50%', top:'14px', transform:'translateX(-50%)', textAlign:'center', zIndex:60 }}>
        <div className="ign-logo" style={{ fontSize:'26px', letterSpacing:'7px' }}>FOVE<span className="ai">AI</span></div>
        <div className="ign-plate-sub" style={{ fontSize:'8px', letterSpacing:'3px', marginTop:'1px' }}>CONCORDIA · INVENTOR'S CONSOLE</div>
      </div>

      <div className="ign-body">
        {/* ── split stage: info column left (under the brand), dial right ── */}
        <div className="ign-stage">

          {/* the reactor emblem — left half, fills viewport height */}
          <div className="ign-center">
            <div className="reactor-wrap">
              {/* 7 halo rings — alluding to the foveated rings; dotted LED borders */}
              {Array.from({ length: 7 }).map((_, i) => {
                const size = 80 + i * 3;   /* percent of the wrap — top ring tips stay clear of the logo */
                const isArmedRing = armedIdx % 7 === i;
                return (
                  <div key={i} className={`halo ${isArmedRing ? 'armed-ring' : ''}`} style={{
                    width: `${size}%`, height: `${size}%`,
                    animation: `ignSpin ${ringPeriod(i)}s linear infinite ${i % 2 ? 'reverse' : ''}`,
                  }} />
                );
              })}
              <div className="reactor-plate" ref={plateWrapRef}>
                {/* the trackball instrument — sweep ring to arm, roll to turn,
                    clean press to ignite, flick for momentum */}
                <Trackball store={tb} sizeParentRef={plateWrapRef} ballScale={0.5}
                  health={stackUp ? (modelReady ? 'ok' : 'warn') : 'down'}
                  onPress={ignite}
                  pressHint="press to ignite — roll to turn the armed dial" />
              </div>
            </div>
          </div>
          {/* ── between-panel readout — the armed dial value, floating in the gap ── */}
          <div className="ign-between">
            <div className="trait-readout">
              <b>{armed.label}</b> = <b>{armedVal}</b>
              <div className="hint">
                {armedBool
                  ? `▲ ${fmtVal(armedBool.up)} · ▼ ${fmtVal(armedBool.down)}`
                  : armed.options
                    ? `▲▼ ${armed.options.length} detents`
                    : `▲ +${armed.step} · ▼ −${armed.step}`}
              </div>
            </div>
          </div>

          {/* ── shared caption — phase label + log, centered under the whole group ── */}
          <div className="ign-caption">
            <div className="reactor-label">
              {armed.label} = {armedVal} · {phase === 'idle' ? (stackUp ? 'core warm — press to board' : 'press to ignite') :
               phase === 'igniting' ? 'reactor spinning up…' : 'containment stable'}
            </div>
          </div>

          {/* ── right rail: the standing info table, vertically centered
              against the dial ── */}
          <div className="ign-rail">
            <div className="ign-info on" style={{ position:'relative', pointerEvents:'auto' }}>
              <b>Machine Memory</b>
              <div className="iv">memories <span style={{float:'right'}}>{status?.total_memories ?? '—'}</span></div>
              <div className="iv">themes <span style={{float:'right'}}>{status?.total_themes ?? '—'}</span></div>
              <div className="iv">sessions <span style={{float:'right'}}>{status?.total_sessions ?? '—'}</span></div>
              <div className="iv">core <span style={{float:'right'}}>{status?.model || '—'}{status?.is_hybrid ? ' ⬡hybrid' : ''}</span></div>
              <div className="iv">state <span style={{float:'right', color: stackUp ? (modelReady ? '#5dff8f' : '#ff9a6a') : '#ff9a6a'}}>
                {stackUp ? (modelReady ? 'warm — loaded' : 'warm — loading') : 'cold — offline'}</span></div>
              <div style={{height:12}} />
              <b>Dial Matrix {savedFlash && <span style={{color:'#5dff8f', letterSpacing:1}}>· saved</span>}</b>
              {TRAITS.map(t => (
                <div key={t.id} style={{marginBottom:4, cursor:'default'}}
                     className={t.id === armed.id ? 'iv' : ''}
                     onClick={() => tb.setArmedId(t.id)}>
                  {t.label} <span style={{float:'right'}}>{displayVal(t)}</span>
                  <span className="im"><i style={{ width: `${Math.round(normTrait(t) * 100)}%` }} /></span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
