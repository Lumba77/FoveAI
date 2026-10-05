import { useCallback, useEffect, useRef, useState } from 'react';
import { boolDirs, dialAngle, TRAITS } from './useTraits';
import type { Trait, TraitStore } from './useTraits';
import './trackball.css';

/**
 * Trackball — the FoveAI control instrument.
 *
 * A heavy glossy-red planet ball seated in a dark socket, ringed by an
 * astrolabe dial of bearing-pips. Sweep the ring (or tap a pip) to arm a
 * setting, then roll the ball to turn it — each detent ticks the value.
 * Flick it and it keeps spinning: momentum decays and detents keep
 * stepping until the ball settles. A clean press fires onPress.
 *
 * All ten positions are real settings via the TraitStore (useTraits) —
 * /api/setting round-trips — so this one device drives the same dials
 * the FoveAI Command console edits.
 */

interface Props {
  store: TraitStore;
  size?: number;        // dial plate diameter, px (360 = ignition size)
  sizeParentRef?: React.RefObject<HTMLDivElement | null>;  // when set, size tracks this container's square diameter
  ballScale?: number;   // ball diameter as fraction of `size` (default 0.596)
  compact?: boolean;    // sidebar mode — tighter pips, no pip values
  bare?: boolean;       // socketed ball only — no dial, no pips (the clicker)
  health?: 'ok' | 'warn' | 'down' | 'off' | null;  // lamp doubles as a health beacon; 'off' = control plane dead (grey, unlit)
  onPress?: () => void; // clean press on the ball
  onHoldStart?: () => void; // press-and-hold begins (after holdMs, without rolling)
  onHoldEnd?: () => void;   // held ball released — replaces onPress for that gesture
  onRollStep?: (dir: number) => void; // ball rolled a step (1 or -1)
  holdMs?: number;      // press duration that counts as a hold (default 280ms)
  pressHint?: string;   // tooltip for the press action
}

/* ── synthesized mechanics — tiny WebAudio, no assets ── */
let actx: AudioContext | null = null;
function audio(): AudioContext | null {
  try {
    if (!actx) actx = new (window.AudioContext || (window as any).webkitAudioContext)();
    if (actx.state === 'suspended') actx.resume().catch(() => {});
    return actx;
  } catch { return null; }
}
function noiseBurst(c: AudioContext, t: number, ms: number, freq: number, gain: number, dest: AudioNode) {
  const len = Math.floor(c.sampleRate * ms / 1000);
  const buf = c.createBuffer(1, len, c.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2);
  const src = c.createBufferSource(); src.buffer = buf;
  const bp = c.createBiquadFilter(); bp.type = 'bandpass'; bp.frequency.value = freq; bp.Q.value = 0.9;
  const g = c.createGain(); g.gain.value = gain;
  src.connect(bp); bp.connect(g); g.connect(dest); src.start(t);
}
/** detent click — ball rolling over a notch */
function rollTick(strength = 1) {
  const c = audio(); if (!c) return;
  const t = c.currentTime;
  noiseBurst(c, t, 14, 2400, 0.09 * strength, c.destination);
  const o = c.createOscillator(), g = c.createGain();
  o.type = 'sine';
  o.frequency.setValueAtTime(150, t);
  o.frequency.exponentialRampToValueAtTime(92, t + 0.05);
  g.gain.setValueAtTime(0.10 * strength, t);
  g.gain.exponentialRampToValueAtTime(0.001, t + 0.07);
  o.connect(g); g.connect(c.destination); o.start(t); o.stop(t + 0.08);
}
/** pip armed — solid brass thunk */
function armThunk() {
  const c = audio(); if (!c) return;
  const t = c.currentTime;
  const o = c.createOscillator(), g = c.createGain();
  o.type = 'sine';
  o.frequency.setValueAtTime(105, t);
  o.frequency.exponentialRampToValueAtTime(58, t + 0.11);
  g.gain.setValueAtTime(0.17, t);
  g.gain.exponentialRampToValueAtTime(0.001, t + 0.14);
  o.connect(g); g.connect(c.destination); o.start(t); o.stop(t + 0.15);
  noiseBurst(c, t, 20, 900, 0.07, c.destination);
}
/** clean press — the ball seats deep into the socket */
function pressThunk() {
  const c = audio(); if (!c) return;
  const t = c.currentTime;
  const o = c.createOscillator(), g = c.createGain();
  o.type = 'sine';
  o.frequency.setValueAtTime(72, t);
  o.frequency.exponentialRampToValueAtTime(38, t + 0.18);
  g.gain.setValueAtTime(0.24, t);
  g.gain.exponentialRampToValueAtTime(0.001, t + 0.24);
  o.connect(g); g.connect(c.destination); o.start(t); o.stop(t + 0.26);
  noiseBurst(c, t, 30, 500, 0.10, c.destination);
}

/* ── sphere-surface marker math ── */
type Vec3 = [number, number, number];
const rotY = (v: Vec3, th: number): Vec3 => {
  const c = Math.cos(th), s = Math.sin(th);
  return [v[0] * c + v[2] * s, v[1], -v[0] * s + v[2] * c];
};
const rotX = (v: Vec3, th: number): Vec3 => {
  const c = Math.cos(th), s = Math.sin(th);
  return [v[0], v[1] * c - v[2] * s, v[1] * s + v[2] * c];
};

interface Drag {
  x: number; y: number; x0: number; y0: number; t0: number;
  moved: number; acc: number;
  vx: number; vy: number; lastT: number; latch: number;
}

export default function Trackball({ store, size: sizeProp = 360, sizeParentRef, ballScale = 0.596, compact = false, bare = false, health = null, onPress, onHoldStart, onHoldEnd, onRollStep, holdMs = 280, pressHint }: Props) {
  const [parentSize, setParentSize] = useState<number | null>(null);
  useEffect(() => {
    if (!sizeParentRef?.current) return;
    const el = sizeParentRef.current;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      setParentSize(Math.min(r.width, r.height));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [sizeParentRef]);
  const size = sizeParentRef ? (parentSize ?? 0) || sizeProp : sizeProp;

  /* browser zoom (or CSS zoom on an ancestor) scales rect widths but not the
     px values we compute, so mixing getBoundingClientRect-derived sizes with
     unzoomed px math misaligns the circular geometry. Normalise by the
     document's effective zoom so all radius math uses real screen px. */
  const zoomRef = useRef(1);
  useEffect(() => {
    const measure = () => {
      // rect of a 1px probe: its width = effective zoom (browser × CSS zoom)
      const probe = document.createElement('div');
      probe.style.cssText = 'position:absolute;visibility:hidden;width:1px;';
      document.body.appendChild(probe);
      const z = probe.getBoundingClientRect().width || 1;
      probe.remove();
      zoomRef.current = z;
      // re-derive size in *real* px from the zoomed rect
      if (sizeParentRef?.current) {
        const r = sizeParentRef.current.getBoundingClientRect();
        setParentSize(Math.min(r.width, r.height) / z);
      }
    };
    measure();
    const ro = new ResizeObserver(measure);
    if (sizeParentRef?.current) ro.observe(sizeParentRef.current);
    window.addEventListener('resize', measure);
    return () => { ro.disconnect(); window.removeEventListener('resize', measure); };
  }, [sizeParentRef]);
  const s = size / 360;
  const em = bare ? size / 15.4 : 16 * s;     // root font scale — ring/pip/label size
  const ballDia = bare ? size * 0.87 : size * ballScale;    // ball px — independent of plate
  const socketDia = bare ? size : ballDia * 15.4 / 13.4;
  const ballR = ballDia / 2;
  const pipR = 132 * s;                       // pip orbit radius — inside the ring so pips never clip
  const detent = bare ? Math.max(8, size * 0.16) : 34 * s;  // px of roll per step — faceted, not slippery
  /* press tolerance — physical trackballs drift a few px while the ball is
     pressed; net displacement (not travelled path) decides press vs roll,
     and a quick tap forgives twice the slop. Scales with the ball. */
  const pressSlop = Math.max(14, ballDia * 0.12);
  const tapMs = 450;

  const ringRef = useRef<HTMLDivElement>(null);
  const ballRef = useRef<HTMLDivElement>(null);
  const dotRef = useRef<HTMLDivElement>(null);
  const speckRef = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);
  const coast = useRef(0);
  const dialDrag = useRef(false);
  const holdTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const holding = useRef(false);
  const { armedIdx, armedId, setArmedId, bumpTrait, setTrait, normTrait, displayVal, finishTint, values } = store;
  const armedTrait = TRAITS.find(t => t.id === armedId);
  const bd = armedTrait ? boolDirs(armedTrait) : null;   // hemisphere split when 2-option

  /* two markers on the ball surface: an ivory dot + a darker speck,
     so rotation is unmistakable while it rolls. Plus a seam — a great
     circle splitting the ball into hemispheres; edge-on it reads as a
     diameter line and sweeps visibly as the ball turns. */
  const dotV = useRef<Vec3>([0.34, -0.52, 0.79]);
  const speckV = useRef<Vec3>([-0.58, 0.28, 0.76]);
  const seamRef = useRef<HTMLDivElement>(null);
  const seamN = useRef<Vec3>([0.94, 0.1, 0.33]);   // seam-plane normal, slightly tilted
  const locked = useRef(false);                   // pole plunger — freezes the ball
  const lockRef = useRef<HTMLDivElement>(null);

  /* imperative px offsets (dots/seam/drag deltas) are computed from real
     screen px; under browser/CSS zoom multiply by the measured zoom so the
     DOM px they land in render at the same physical scale. */
  const px = useCallback((n: number) => n * zoomRef.current, []);

  const paintDots = useCallback(() => {
    const paint = (v: Vec3, el: HTMLDivElement | null, rad: number) => {
      if (!el) return;
      const z = v[2];
      const vis = Math.min(1, Math.max(0, (z - 0.02) / 0.3));
      el.style.transform = `translate(-50%,-50%) translate(${px(v[0] * rad).toFixed(1)}px, ${px(v[1] * rad).toFixed(1)}px) scale(${(0.65 + 0.35 * Math.max(0, z)).toFixed(2)})`;
      el.style.opacity = vis.toFixed(2);
    };
    paint(dotV.current, dotRef.current, ballR * 0.72);
    paint(speckV.current, speckRef.current, ballR * 0.72);
    const n = seamN.current;
    if (seamRef.current) {
      // great circle ⊥ n → ellipse: minor/major = |n.z|, long axis ⊥ n.xy
      const squash = Math.abs(n[2]);
      const angle = Math.atan2(n[1], n[0]) + Math.PI / 2;
      seamRef.current.style.transform =
        `translate(-50%,-50%) rotate(${angle.toFixed(3)}rad) scaleY(${Math.max(squash, 0.04).toFixed(3)})`;
      seamRef.current.style.opacity = (0.25 + 0.75 * (1 - squash)).toFixed(2);
    }
  }, [ballR, px]);

  const rotateBall = useCallback((dx: number, dy: number) => {
    const k = 1 / ballR;                        // arc length → radians
    dotV.current   = rotX(rotY(dotV.current,   dx * k), -dy * k);
    speckV.current = rotX(rotY(speckV.current, dx * k), -dy * k);
    seamN.current  = rotX(rotY(seamN.current,  dx * k), -dy * k);
    paintDots();
  }, [ballR, paintDots]);

  /* ── the faceted net under the ball ──────────────────────────────
     Vertical roll feeds `acc` through a well/crest grip: resistance is
     highest right after a detent (leaving a well) and lowest at the
     crest between wells — the geometry pulls the setting into place
     instead of letting it free-spin.
     2-option traits get a hemisphere divider instead: push up past the
     threshold = the `up` value, pull down = the other. A deadzone and
     latch make it impossible to flicker yes/no by accident. */
  const feedRoll = useCallback((st: { acc: number; latch: number }, dy: number) => {
    const frac = (((st.acc % detent) + detent) % detent) / detent;
    const grip = 1 - 0.55 * Math.cos(2 * Math.PI * frac);   // 0.45 in wells, 1.55 on crests
    st.acc -= dy * grip;
    
    if (bare) {
      while (Math.abs(st.acc) >= detent) {
        const dir = Math.sign(st.acc);
        st.acc -= dir * detent;
        if (onRollStep) onRollStep(dir);
        rollTick();
      }
      return;
    }
    if (!armedTrait) return;
    
    if (bd) {
      const TH = detent * 1.15;
      // acc grows positive on upward roll — up = the "up" value
      if (st.acc >= TH && st.latch !== 1) { setTrait(armedTrait, bd.up); st.latch = 1; rollTick(1.3); }
      else if (st.acc <= -TH && st.latch !== -1) { setTrait(armedTrait, bd.down); st.latch = -1; rollTick(1.3); }
      else if (Math.abs(st.acc) < TH * 0.4) st.latch = 0;   // rolled back to centre — re-arm
    } else {
      while (Math.abs(st.acc) >= detent) {
        const dir = Math.sign(st.acc);
        st.acc -= dir * detent;
        bumpTrait(armedTrait, dir);
        rollTick();
      }
    }
  }, [bare, detent, armedTrait, bd, setTrait, bumpTrait, onRollStep]);

  /* flick momentum — the ball keeps rolling, but the net grips it:
     faster spin-down, and once slow it snaps into the nearest well */
  const startCoast = useCallback((vx0: number, vy0: number) => {
    cancelAnimationFrame(coast.current);
    const st = { acc: 0, latch: 0 };
    let vx = vx0, vy = vy0, last = performance.now(), t0 = last;
    const step = (now: number) => {
      const dt = Math.min(50, now - last); last = now;
      const decay = Math.pow(0.90, dt / 16.7);   // faceted friction — settles sooner
      vx *= decay; vy *= decay;
      const dx = vx * dt, dy = vy * dt;
      rotateBall(dx, dy);
      feedRoll(st, dy);
      if (Math.hypot(vx, vy) > 0.05 && now - t0 < 2200) {
        coast.current = requestAnimationFrame(step);
        return;
      }
      // settle: the net pulls acc into the nearest well
      const well = Math.round(st.acc / detent) * detent;
      const pull = (well - st.acc) * 0.22;
      if (Math.abs(pull) > 0.3) {
        st.acc += pull;
        rotateBall(0, -pull);
        coast.current = requestAnimationFrame(step);
      }
    };
    coast.current = requestAnimationFrame(step);
  }, [detent, rotateBall, feedRoll]);

  /* ── ball gestures ── */
  const cancelHold = useCallback(() => {
    if (holdTimer.current) { clearTimeout(holdTimer.current); holdTimer.current = null; }
  }, []);

  const onBallDown = useCallback((e: React.PointerEvent) => {
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    cancelAnimationFrame(coast.current);          // catch a spinning ball
    const now = performance.now();
    drag.current = { x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY, t0: now, moved: 0, acc: 0, vx: 0, vy: 0, lastT: now, latch: 0 };
    holding.current = false;
    if (onHoldStart) {
      holdTimer.current = setTimeout(() => {
        const d = drag.current;
        if (d && d.moved < pressSlop) {          // still a clean press → it's a hold
          holding.current = true;
          onHoldStart();
        }
      }, holdMs);
    }
  }, [onHoldStart, holdMs, pressSlop]);

  /* pole plunger — locks the ball: roll input is ignored so the press
     can't jitter into a roll. Press still works — that's the point. */
  const toggleLock = useCallback((e: React.PointerEvent) => {
    e.stopPropagation();                           // don't start a ball drag
    locked.current = !locked.current;
    lockRef.current?.classList.toggle('tb-on', locked.current);
    ballRef.current?.classList.toggle('tb-locked', locked.current);
    rollTick(1.3);
  }, []);

  const onBallMove = useCallback((e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y;
    d.x = e.clientX; d.y = e.clientY;
    d.moved += Math.abs(dx) + Math.abs(dy);
    const now = performance.now();
    const dt = Math.max(1, now - d.lastT); d.lastT = now;
    d.vx = d.vx * 0.65 + (dx / dt) * 0.35;         // smoothed flick velocity
    d.vy = d.vy * 0.65 + (dy / dt) * 0.35;
    if (d.moved >= pressSlop) cancelHold();        // became a roll — not a hold
    if (locked.current) return;                    // frozen — plunger is in
    rotateBall(dx, dy);                            // ball follows the finger in both axes…
    feedRoll(d, dy);                               // …but only the vertical feed turns dials
  }, [rotateBall, feedRoll, cancelHold, pressSlop]);

  const onBallUp = useCallback(() => {
    cancelHold();
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (holding.current) {                        // held ball released — end hold, not a press
      holding.current = false;
      onHoldEnd?.();
      return;
    }
    const disp = Math.hypot(d.x - d.x0, d.y - d.y0);   // net travel — press wiggle cancels out
    const heldMs = performance.now() - d.t0;
    if (disp < pressSlop || (heldMs < tapMs && disp < pressSlop * 2)) {
      pressThunk();                                   // clean press, not a roll
      onPress?.();
    } else if (!locked.current && Math.hypot(d.vx, d.vy) > 0.12) {   // released with a flick
      startCoast(d.vx, d.vy);
    }
  }, [onPress, onHoldEnd, startCoast, cancelHold, pressSlop, tapMs]);

  const onBallCancel = useCallback(() => {
    cancelHold();
    if (holding.current) { holding.current = false; onHoldEnd?.(); }
    drag.current = null;
  }, [onHoldEnd, cancelHold]);

  /* ── ring: sweep or tap arms the pip under your finger ── */
  const armAtPointer = useCallback((e: React.PointerEvent) => {
    const el = ringRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const deg = Math.atan2(e.clientY - (r.top + r.height / 2), e.clientX - (r.left + r.width / 2)) * 180 / Math.PI;
    const idx = ((Math.round((deg + 90) / (360 / TRAITS.length)) % TRAITS.length) + TRAITS.length) % TRAITS.length;
    if (TRAITS[idx].id !== armedId) { setArmedId(TRAITS[idx].id); armThunk(); }
  }, [armedId, setArmedId]);

  const onRingDown = useCallback((e: React.PointerEvent) => {
    dialDrag.current = true;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    armAtPointer(e);
  }, [armAtPointer]);
  const onRingMove = useCallback((e: React.PointerEvent) => {
    if (dialDrag.current) armAtPointer(e);
  }, [armAtPointer]);
  const onRingUp = useCallback(() => { dialDrag.current = false; }, []);

  return (
    <div
      className={`tb-root ${compact ? 'tb-compact' : ''} ${bare ? 'tb-bare' : ''} ${health ? `tb-health-${health}` : ''}`}
      style={{ width: size, height: size, fontSize: `${em}px`, ['--tb-finish' as any]: finishTint }}
    >
      {!bare && (
        <>
          {/* astrolabe ring — ticked brass, sweep to arm */}
          <div
            className="tb-ring" ref={ringRef}
            onPointerDown={onRingDown} onPointerMove={onRingMove}
            onPointerUp={onRingUp} onPointerCancel={onRingUp}
          />
          {/* needle snaps to the armed position */}
          <div className="tb-needle" style={{ transform: `rotate(${dialAngle(armedIdx) + 90}deg)` }} />

          {/* bearing-pips — one per setting, glowing with its value */}
          {TRAITS.map((t: Trait, i: number) => {
            const a = dialAngle(i);
            const isArmed = t.id === armedId;
            return (
              <div
                key={t.id}
                className={`tb-pip ${isArmed ? 'armed' : ''}`}
                onPointerDown={(e) => { e.stopPropagation(); setArmedId(t.id); armThunk(); }}
                style={{ transform: `rotate(${a + 90}deg) translateY(-${pipR}px) rotate(${-a - 90}deg)`,
                         ['--pv' as any]: normTrait(t) }}
              >
                <span className="tb-pip-ball" />
                <span className="tb-pip-label">{t.label}</span>
                {!compact && <span className="tb-pip-val">{displayVal(t)}</span>}
              </div>
            );
          })}
        </>
      )}

      {/* socket + planet ball — sized in px so the ball can stay fixed
          while the dial matrix around it grows */}
      <div
        className="tb-socket"
        style={{ width: socketDia, height: socketDia, fontSize: `${socketDia / 15.4}px` }}
      >
        <div
          className="tb-ball" ref={ballRef}
          style={{ width: ballDia, height: ballDia, fontSize: `${ballDia / 13.4}px` }}
          onPointerDown={onBallDown} onPointerMove={onBallMove}
          onPointerUp={onBallUp} onPointerCancel={onBallCancel}
          title={pressHint || 'press — roll to turn the armed dial'}
        >
          <div className="tb-seam" ref={seamRef} />
          <div className="tb-dot" ref={dotRef} />
          <div className="tb-speck" ref={speckRef} />
          {size >= 140 && (
            <div
              className="tb-lock" ref={lockRef}
              onPointerDown={toggleLock}
              title="lock ball — rolling disabled, press still clicks"
            />
          )}
        </div>
      </div>

      {/* hemisphere divider — etched midline + ▲▼ rim glyphs when a
          two-option setting is armed; the lit glyph marks the live side */}
      {!bare && bd && armedTrait && (
        <div
          className="tb-divider"
          style={{ width: socketDia, height: socketDia, fontSize: `${socketDia / 15.4}px` }}
          aria-hidden
        >
          <span className={`tb-div-glyph up ${String(values[armedTrait.id]) === bd.up ? 'lit' : ''}`}>▲</span>
          <span className="tb-div-edge" />
          <span className={`tb-div-glyph down ${String(values[armedTrait.id]) === bd.down ? 'lit' : ''}`}>▼</span>
        </div>
      )}
    </div>
  );
}
