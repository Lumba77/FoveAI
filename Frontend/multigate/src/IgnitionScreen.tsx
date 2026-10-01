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

interface SessionEntry {
  session_id?: string;
  id?: string;
  title?: string;
  last_updated?: string;
  message_count?: number;
}

interface SettingRow {
  key: string;
  label: string;
  current: string | null;
  previous: string | null;
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

function relTime(iso?: string): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const days = Math.floor(h / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
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

/* ── beta charter: the gift ledger shown to signed-in testers ──
   months accrue from account creation; the rate is the project's
   working estimate of what this service will cost at launch */
const GIFT_MONTHLY_SEK = 200;

interface AccountInfo {
  username: string;
  displayName?: string;
  role?: string;
  created?: string;
}

function betaMonths(created?: string): number {
  if (!created) return 1;
  const from = new Date(created).getTime();
  if (!isFinite(from)) return 1;
  const months = Math.floor((Date.now() - from) / (30.44 * 24 * 3600 * 1000));
  return Math.max(1, months + 1);
}

export default function IgnitionScreen({ userName, token, onEnter }: { userName?: string; token?: string; onEnter: () => void }) {
  const [phase, setPhase] = useState<Phase>('boot');
  const [status, setStatus] = useState<StatusData | null>(null);
  const [account, setAccount] = useState<AccountInfo | null>(null);
  const [sessions, setSessions] = useState<SessionEntry[]>([]);
  const [settings, setSettings] = useState<SettingRow[]>([]);
  const [stackUp, setStackUp] = useState(false);
  const [modelReady, setModelReady] = useState(false);
  const [log, setLog] = useState<Array<{ text: string; ok: boolean | null }>>([]);
  const [editCompression, setEditCompression] = useState<string>('');
  const [editMode, setEditMode] = useState<string>('');
  const [savedFlash, setSavedFlash] = useState(false);
  const [flicker, setFlicker] = useState(0);
  const tb = useTraits(useCallback(() => {
    setSavedFlash(true);
    setTimeout(() => setSavedFlash(false), 1500);
  }, []));
  const logRef = useRef<HTMLDivElement>(null);
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
    try {
      const r = await fetch('/api/sessions', { signal: AbortSignal.timeout(4000) });
      if (r.ok) { const j = await r.json(); setSessions((j.sessions || []).slice(0, 5)); }
    } catch (_) {}
    const rows: SettingRow[] = [];
    let prev: Record<string, string> = {};
    try { prev = JSON.parse(localStorage.getItem(SNAPSHOT_STORE) || '{}'); } catch (_) {}
    const next: Record<string, string> = {};
    for (const { key, label } of SNAPSHOT_KEYS) {
      let cur: string | null = null;
      try {
        const r = await fetch(`/api/setting?key=${encodeURIComponent(key)}`, { signal: AbortSignal.timeout(3000) });
        if (r.ok) cur = (await r.json()).value;
      } catch (_) {}
      next[key] = cur ?? '';
      rows.push({ key, label, current: cur, previous: prev[key] ?? null });
    }
    setSettings(rows);
    localStorage.setItem(SNAPSHOT_STORE, JSON.stringify(next));
    const comp = rows.find(r => r.key === 'XRLF_PROXY_AGGRESSION')?.current;
    if (comp) setEditCompression(comp);
    const mode = rows.find(r => r.key === 'XRLF_COGNITIVE_MODE')?.current;
    if (mode) setEditMode(mode);
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

  /* beta charter — who is boarding, and what their access is worth */
  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        const r = await fetch('/api/auth/me', {
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(4000),
        });
        if (r.ok && aliveRef.current) {
          const j = await r.json();
          if (j.account) setAccount(j.account);
        }
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

  const saveQuick = useCallback(async (key: string, val: string) => {
    try {
      await fetch('/api/setting', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ key, val }), signal: AbortSignal.timeout(5000),
      });
      setSavedFlash(true); setTimeout(() => setSavedFlash(false), 1500);
    } catch (_) {}
  }, []);

  const changed = settings.filter(s => s.previous !== null && s.previous !== s.current);
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

  const Row = ({ k, v, cls }: { k: string; v: React.ReactNode; cls?: string }) => (
    <tr><td className="tk">{k}</td><td className={`tv ${cls || ''}`}>{v}</td></tr>
  );

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

        .ign-body { flex:1; display:flex; min-height:0; }
        .ign-left { flex: 1; padding: 8px 24px 26px 34px; display:flex; flex-direction:column;
          gap: 10px; overflow-y:auto; min-width:0; }
        .ign-right { flex: 1; padding: 8px 34px 26px 24px; display:flex; flex-direction:column;
          gap: 10px; overflow-y:auto; min-width:0; }
        .ign-center { flex: 1.15; display:flex; flex-direction:column; align-items:center;
          justify-content:center; gap:22px; position:relative; padding-bottom:30px;
          min-width:0; overflow:hidden;
          border-left:1px solid rgba(255,200,90,.14);
          border-right:1px solid rgba(255,200,90,.14); }

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

        /* ── reactor emblem ── */
        .reactor-wrap { position:relative; width:560px; height:560px; display:flex;
          align-items:center; justify-content:center; }
        .reactor-plate { position:relative; width:430px; height:430px; display:flex;
          align-items:center; justify-content:center; border-radius:50%; overflow:hidden;
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
        .trait-readout { font-size:14px; letter-spacing:2px; color:#a9b3d4; text-align:center;
          font-family:'Share Tech Mono',monospace; }
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
        /* three columns leave less room for the halo rings — shrink the
           emblem before it crowds the flanking consoles */
        @media (max-width: 1500px) {
          .reactor-wrap { transform:scale(.85); margin:-42px 0; }
        }
        @media (max-width: 920px) {
          .ign-body { flex-direction:column; overflow-y:auto; overflow-x:hidden; }
          .ign-center { order:-1; border-left:none; border-right:none; overflow:visible;
            border-bottom:1px solid rgba(255,200,90,.14); padding-bottom:14px; }
          .reactor-wrap { transform:scale(.72); margin:-60px 0; }
          .ign-logo { font-size:34px; letter-spacing:8px; }
        }
        /* crammed portrait: stack table cells, never let data vanish */
        @media (max-width: 640px) {
          .ign-left { padding: 6px 12px 20px; }
          .ign-right { padding: 6px 12px 20px; }
          .lcd-body { padding:5px 10px 6px; overflow-x:auto; }
          .lcd-tbl, .lcd-tbl tbody { display:block; width:100%; }
          .lcd-tbl tr { display:flex; flex-wrap:wrap; gap:2px 10px; }
          .lcd-tbl td { flex:1 1 45%; min-width:110px; padding:2px 2px;
            overflow-wrap:anywhere; word-break:break-word; }
          .lcd-tbl .tv { text-align:left; }
          .ign-logo { font-size:26px; letter-spacing:5px; }
          .reactor-wrap { transform:scale(.55); margin:-110px 0; }
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

      {/* full-width screwed metal logo plate */}
      <div className="ign-plate">
        <div className="ign-logo">FOVE<span className="ai">AI</span></div>
        <div className="ign-plate-sub">CONCORDIA · INVENTOR'S CONSOLE</div>
      </div>

      <div className="ign-body">
        {/* ── left console stack — machine status & trail ── */}
        <div className="ign-left">
          <div className="lcd">
            <div className="lcd-head">Machine Memory</div>
            <div className="lcd-body"><table className="lcd-tbl"><tbody>
              <Row k="memories" v={status?.total_memories ?? '—'} />
              <Row k="themes" v={status?.total_themes ?? '—'} />
              <Row k="sessions" v={status?.total_sessions ?? '—'} />
              <Row k="core" v={<>{status?.model || '—'}{status?.is_hybrid ? ' ⬡hybrid' : ''}</>} />
              <Row k="state" v={stackUp ? (modelReady ? 'warm — model loaded' : 'warm — model loading') : 'cold — core offline'}
                   cls={stackUp ? 'ok' : 'warn'} />
            </tbody></table></div>
          </div>

          <div className="lcd">
            <div className="lcd-head">Since Last Visit</div>
            <div className="lcd-body"><table className="lcd-tbl"><tbody>
              {changed.length === 0 && <Row k="settings drift" v={<span style={{color:'#7d8a5e'}}>none detected</span>} />}
              {changed.map(s => <Row key={s.key} k={s.label} v={`${s.previous || '∅'} → ${s.current || '∅'}`} cls="chg" />)}
              {settings.filter(s => s.previous === null && s.current !== null)
                       .map(s => <Row key={s.key} k={s.label} v={s.current} />)}
            </tbody></table></div>
          </div>

          <div className="lcd">
            <div className="lcd-head">Trail of Work</div>
            <div className="lcd-body">
              {sessions.length === 0 && <div style={{color:'#7d8a5e', fontSize:14}}>{stackUp ? 'no prior sessions found' : 'awaiting core…'}</div>}
              {sessions.map((s, i) => (
                <div className="sess-item" key={s.session_id || s.id || i}>
                  <div className="sess-t">{s.title || s.session_id || s.id || 'untitled session'}</div>
                  <div className="sess-d">{relTime(s.last_updated)}{s.message_count != null ? ` · ${s.message_count} msgs` : ''}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── center: reactor emblem — trackball flanked by the consoles ── */}
        <div className="ign-center">
          <div className="reactor-name">CONCORDIA THORIUM CORE</div>
          <div className="reactor-wrap">
            {/* 7 halo rings — alluding to the foveated rings; dotted LED borders */}
            {Array.from({ length: 7 }).map((_, i) => {
              const size = 462 + i * 24;
              const isArmedRing = armedIdx % 7 === i;
              return (
                <div key={i} className={`halo ${isArmedRing ? 'armed-ring' : ''}`} style={{
                  width: size, height: size,
                  animation: `ignSpin ${ringPeriod(i)}s linear infinite ${i % 2 ? 'reverse' : ''}`,
                }} />
              );
            })}
            <div className="reactor-plate">
              {/* the trackball instrument — sweep ring to arm, roll to turn,
                  clean press to ignite, flick for momentum */}
              <Trackball store={tb} size={430} ballScale={0.5}
                health={stackUp ? (modelReady ? 'ok' : 'warn') : 'down'}
                onPress={ignite}
                pressHint="press to ignite — roll to turn the armed dial" />
            </div>
          </div>
          <div className="trait-readout">
            <b>{armed.label}</b> = <b>{armedVal}</b>
            <div className="hint">
              {armedBool
                ? `▲ push up = ${fmtVal(armedBool.up)}  ·  ▼ pull down = ${fmtVal(armedBool.down)}`
                : armed.options
                  ? `▲▼ roll through ${armed.options.length} detents`
                  : `▲ +${armed.step}  ·  ▼ −${armed.step}`}
              {' '}· sweep dial to arm · press to board
            </div>
          </div>
          <div className="reactor-label">
            {phase === 'idle' ? (stackUp ? 'core warm — press to board' : 'press to ignite') :
             phase === 'igniting' ? 'reactor spinning up…' : 'containment stable'}
          </div>
          <div className="ign-log" ref={logRef}>
            {log.length === 0 && <div style={{ color: '#5d6b48' }}>reactor log idle…</div>}
            {log.map((l, i) => (
              <div key={i} className={l.ok === false ? 'bad' : l.ok === true ? 'good' : ''}>{l.text}</div>
            ))}
          </div>
        </div>

        {/* ── right console stack — the dial matrix mirrors the ball's ten
            positions live, so every setting stays readable mid-roll ── */}
        <div className="ign-right">
          {account && (
            <div className="lcd">
              <div className="lcd-head">Beta Charter</div>
              <div className="lcd-body"><table className="lcd-tbl"><tbody>
                <Row k="account" v={account.displayName || account.username} />
                <Row k="standing" v={<span className="tv ok">FoveAI Beta Tester</span>} />
                <Row k="since" v={account.created ? new Date(account.created).toLocaleDateString() : '—'} />
                <Row k="provisioned gift"
                     v={`${betaMonths(account.created)} mo access ≈ ${(betaMonths(account.created) * GIFT_MONTHLY_SEK).toLocaleString('sv-SE')} kr`}
                     cls="chg" />
                <Row k="" v={<a href="/beta.html" style={{ color: '#ffd766', textDecoration: 'none' }}>about the beta program →</a>} />
              </tbody></table></div>
            </div>
          )}

          <div className="lcd">
            <div className="lcd-head">Dial Matrix {savedFlash && <span className="saved">· saved</span>}</div>
            <div className="lcd-body"><table className="lcd-tbl"><tbody>
              {TRAITS.map(t => (
                <tr key={t.id}
                    className={`dial-row ${t.id === armed.id ? 'armed' : ''}`}
                    onClick={() => tb.setArmedId(t.id)}
                    title={t.key ? `${t.key} — click to arm` : 'local finish — click to arm'}>
                  <td className="tk">{t.label}</td>
                  <td className="tv">{displayVal(t)}
                    <span className="dial-meter"><i style={{ width: `${Math.round(normTrait(t) * 100)}%` }} /></span>
                  </td>
                </tr>
              ))}
            </tbody></table></div>
          </div>

          <div className="lcd">
            <div className="lcd-head">Quick Dials</div>
            <div className="lcd-body">
              <div className="quick-row">
                <span className="tk">compression</span>
                <select value={editCompression} onChange={e => { setEditCompression(e.target.value); saveQuick('XRLF_PROXY_AGGRESSION', e.target.value); }}>
                  {['1','2','3','4','5'].map(v => <option key={v} value={v}>{v}</option>)}
                </select>
                <span className="tk">mode</span>
                <select value={editMode} onChange={e => { setEditMode(e.target.value); saveQuick('XRLF_COGNITIVE_MODE', e.target.value); }}>
                  <option value="local">local</option>
                  <option value="cloud">cloud</option>
                  <option value="hybrid">hybrid</option>
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
