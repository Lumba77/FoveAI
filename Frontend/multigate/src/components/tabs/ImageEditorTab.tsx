import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useTraits, TRAITS } from '../../trackball/useTraits';

// ─── ImageEditorTab ──────────────────────────────────────────────────
// First FoveAI Tool. Personal gallery + web-based editor.
//
// Layout: gallery grid → select → editor canvas wrapped in draggable
// white frame lines ("the measured desk"): pulling any border resizes
// the viewer; pulling the top line resizes with proportions locked.
// In editor mode a ruler strip shows pixel measurements along the top
// and left edges of the image.
//
// Backend: /api/tools/images (gallery, live on proxy :8400). AI ops
// (outpaint / enhance) POST to the LOCAL FoveAI creative engine
// (/api/dream on :8412 — SD1.5 img2img for outpaint, upscaler chain
// for enhance). No web readymades: every generated pixel stays local.
//
// The desk is decoupled: the white frame is a viewport window onto the
// image. The image has its own deskZoom (0.05x..5x, css px per image
// px) and imgPan offset, so it can be scaled BIGGER than the frame
// (pan + crop to frame) or SMALLER (empty margins to outpaint into).

const API = '/api/tools/images';

interface GalleryItem {
  id: string;
  file: string;
  bytes: number;
  added: string | null;
  url: string;
}

type Tool =
  | 'pan' | 'select' | 'crop' | 'resize' | 'rotate'
  | 'light' | 'sharpen' | 'undo'
  | 'save' | 'saveAs' | 'share' | 'copy' | 'export';

const TOOLS: { id: Tool; label: string; icon: string; hint: string }[] = [
  { id: 'pan', label: 'Pan', icon: '✋', hint: 'drag the image on the desk · wheel = zoom · image may overflow the frame' },
  { id: 'select', label: 'Select', icon: '▯', hint: 'marquee-select a region' },
  { id: 'crop', label: 'Crop', icon: '⌗', hint: 'crop to current selection' },
  { id: 'resize', label: 'Resize', icon: '⤢', hint: 'width/height in px — proportions locked unless unlocked' },
  { id: 'rotate', label: 'Rotate', icon: '↻', hint: 'rotate 90° CW' },
  { id: 'light', label: 'Light', icon: '☀', hint: 'brightness / contrast' },
  { id: 'sharpen', label: 'Sharpen', icon: '▽', hint: 'unsharp mask via convolution' },
  { id: 'undo', label: 'Undo', icon: '↺', hint: 'step back one edit' },
  { id: 'save', label: 'Save', icon: '⤓', hint: 'save · save as · share · copy · export' },
];

export const ImageEditorTab: React.FC = () => {
  // ── gallery ──
  const [gallery, setGallery] = useState<GalleryItem[]>([]);
  const [activeItem, setActiveItem] = useState<GalleryItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  // ── editor state ──
  const [editing, setEditing] = useState(false);
  const [tool] = useState<Tool>('select');
  const [brightness, setBrightness] = useState(100);   // %
  const [contrast, setContrast] = useState(100);       // %
  const [sharpenAmt, setSharpenAmt] = useState(0);     // 0..100
  const [resizeW, setResizeW] = useState(0);
  const [resizeH, setResizeH] = useState(0);
  const [lockRatio, setLockRatio] = useState(true);
  const [frameW, setFrameW] = useState(0);             // desk frame (css px)
  const [frameH, setFrameH] = useState(0);
  // desk composition: the image has its OWN scale and position, wholly
  // decoupled from the white frame. deskZoom = css px per image px;
  // imgPan = image top-left offset relative to the frame top-left.
  // deskZoom > frame fit → image bigger than frame (crop by framing);
  // deskZoom < fit → empty margins inside the frame (outpaint territory).
  const [deskZoom, setDeskZoom] = useState(1);
  const [imgPan, setImgPan] = useState({ x: 0, y: 0 });

  // worktable: physical-unit measuring, checked surface, touch gestures
  const PPI = 96;                                    // display px per (nominal) inch
  type Unit = 'px' | 'in' | 'cm';
  const [unit, setUnit] = useState<Unit>('px');      // measurement display
  const [refUnits, setRefUnits] = useState(21);      // desk width in chosen real unit
  const [checked, setChecked] = useState(true);      // worktable surface
  const [spin, setSpin] = useState(0);               // desk rotation deg

  // ── The Image Dial Matrix — THE REAL INSTRUMENT, reused ─────────
  // Same useTraits store the ignition screen and sidebar ball drive
  // (repo rule: extend what exists — one ball, one dial set, whole stack).
  // LOCAL dial values ride the same XRLF_* env keys; image-gen specific
  // guidance composes client-side into the steerage envelope so the
  // quantized model gets maximal signal per token.
  const [dialMenu, setDialMenu] = useState(false);
  const tb = useTraits();
  const [imageDialId, setImageDialId] = useState<string | null>(null);
  
  const dials = tb.values;                      // live values of REAL dials
  const turnImageDial = (dir: 1 | -1) => { tb.bumpTrait(tb.armed, dir); playTick(); };

  // ── composed prompt (background composition) ──
  // REAL dial states (compress/aggression, mode, ctx…) + image-gen
  // steerage envelope → the "optimal prompt" preview shown live.
  const composeImagePrompt = () => {
    const steer: string[] = [];
    const agg = dials.compress;                          // XRLF_PROXY_AGGRESSION
    if (agg && +agg >= 3) steer.push('clean edges, coherent local detail');
    if (agg && +agg >= 4) steer.push('high perceived sharpness');
    if (dials.mode === 'cloud') steer.push('max quality, cloud pipeline');
    if (dials.ctx && +dials.ctx >= 32768) steer.push('rich semantic context');
    const envelope = `[xrlf steers: steer_strength ${dials.think === 'true' ? 'high' : 'std'}${steer.length ? ', ' + steer.join(', ') : ''}]`;
    return `${envelope} ${aiText.trim() || 'highly detailed'}`.trim();
  };

  // green ball: dial collaboration band — high aggression + high context
  // + think ON = the sweet spot; extremes without support = warn
  const ballState = (() => {
    const agg = +(dials.compress || 0);
    const ctx = +(dials.ctx || 0);
    if (agg >= 4 && ctx < 16000) return 'warn';   // pushed past what ctx supports
    if (agg >= 2 && (dials.think === 'true' || ctx >= 16000)) return 'green';
    if (agg >= 0) return 'ok';
    return 'warn';
  })();

  // ── the plasma core — luminous gas in a transparent ball ─────
  // Dropping the red/green indicator ball as a rule. The core is a
  // transparent vessel with living gas: idle = a solar corona radiating
  // tentacle-arms of electricity in all directions; touched = the
  // electricity CONVERGES to the finger as a pulsating stream; rolled =
  // colour shifts + pulse frequency climbs with the dial ensemble's
  // quality, until the gas lightning-illuminates green — release now.
  // Haptics ride the pulse so the frequency is felt, not seen.
  const [coreTouched, setCoreTouched] = useState(false);
  const [corePulse, setCorePulse] = useState(0);
  useEffect(() => {
    // pulse period: far-from-optimal slow & dim; optimal fast & electric
    const period = ballState === 'green' ? 90 : ballState === 'ok' ? 420 : 1100;
    const t = setInterval(() => setCorePulse(p => (p + 1) % 1000), period);
    return () => clearInterval(t);
  }, [ballState]);
  const CORE_COLOR = ballState === 'green' ? '#5dff8f'
    : ballState === 'ok' ? '#8fd4ff'
    : '#c9a0ff';
  const CORE_HOT = ballState === 'green';

  // haptic stream: continuous while touched, frequency ∝ quality;
  // an accelerating burst right at the optimal zone.
  useEffect(() => {
    if (!coreTouched) return;
    if (CORE_HOT) {
      const iv = setInterval(() => navigator.vibrate?.(30), 90);
      return () => clearInterval(iv);
    }
    const iv = setInterval(() => navigator.vibrate?.(18), 600);
    return () => clearInterval(iv);
  }, [coreTouched, CORE_HOT]);

  // ── the sonic identity (WebAudio, synthesized, no assets) ───────
  //  · tick     — when a dial turns: tiny wooden clock tick, LOW level;
  //               so quiet you lean forward. The sound of adjusting.
  //  · swoosh   — when the pass fires: a wind sweep through the room.
  //  · boom     — 2s after fire: a LARGE broom/thunder, faint and far,
  //               swelling very loud at the tail but "outside" — low-pass
  //               filtered so it never sounds in the room. 12s of decay.
  const audioCtxRef = useRef<AudioContext | null>(null);
  const ensureAudio = () => {
    if (!audioCtxRef.current) {
      try { audioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)(); } catch (_) {}
    }
    return audioCtxRef.current;
  };

  // pentatonic ladder — dial turns walk a musical scale instead of one tone
  const tickStepRef = useRef(0);
  const PENTA = [523.25, 587.33, 659.25, 783.99, 880.00]; // C5 D5 E5 G5 A5
  const playTick = () => {
    const ctx = ensureAudio(); if (!ctx) return;
    const t = ctx.currentTime;
    const f0 = PENTA[tickStepRef.current % PENTA.length];
    tickStepRef.current += 1;
    // softer, rounder: triangle wave, quick decay, hushed
    const o = ctx.createOscillator(); o.type = 'triangle'; o.frequency.value = f0;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.018, t + 0.006);  // quieter than v1
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.09);  // longer, softer tail
    const bp = ctx.createBiquadFilter(); bp.type = 'lowpass'; bp.frequency.value = 1800;
    o.connect(bp).connect(g).connect(ctx.destination);
    o.start(t); o.stop(t + 0.1);
  };

  const playFireSequence = () => {
    const ctx = ensureAudio(); if (!ctx) return;
    const t = ctx.currentTime;
    // 1. wind swoosh through the room (white noise, wide band, 1.2s swell)
    const len = Math.floor(ctx.sampleRate * 1.4);
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) {
      const p = i / len;
      // bandpass sweep feel: amplitude rises mid, falls at end
      d[i] = (Math.random() * 2 - 1) * Math.sin(p * Math.PI) * 0.5;
    }
    const src = ctx.createBufferSource(); src.buffer = buf;
    const f = ctx.createBiquadFilter(); f.type = 'bandpass';
    f.frequency.setValueAtTime(300, t);
    f.frequency.exponentialRampToValueAtTime(2400, t + 0.9);   // the "wind rise"
    f.frequency.exponentialRampToValueAtTime(500, t + 1.3);
    const g = ctx.createGain(); g.gain.value = 0.22;
    src.connect(f).connect(g).connect(ctx.destination);
    src.start(t);
    // 2. distant boom at +2s: faint thunder, low-passed "outside",
    //    swells very loud in its tail over ~12s decay
    const boomAt = t + 2;
    const blen = Math.floor(ctx.sampleRate * 12);
    const bbuf = ctx.createBuffer(1, blen, ctx.sampleRate);
    const bd = bbuf.getChannelData(0);
    for (let i = 0; i < blen; i++) {
      const p = i / blen;
      // distant ~1 km rumble: barely hearable approach, escalating
      // closeness (never a slam), receding far-echo tail
      bd[i] = (Math.random() * 2 - 1) * Math.pow(p, 1.8) * 0.8 * (1 - Math.max(0, p - 0.75) * 3.2);
    }
    const bsrc = ctx.createBufferSource(); bsrc.buffer = bbuf;
    const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 160;  // outside the room
    const bg = ctx.createGain();
    bg.gain.setValueAtTime(0.02, boomAt);         // barely hearable...
    bg.gain.exponentialRampToValueAtTime(0.13, boomAt + 4.0); // ...distressing closeness (half-volume)...
    bg.gain.exponentialRampToValueAtTime(0.05, boomAt + 8.0); // ...recedes to the far echo...
    bg.gain.exponentialRampToValueAtTime(0.001, boomAt + 11.9); // ...the 1 km rumble fades out
    bsrc.connect(lp).connect(bg).connect(ctx.destination);
    bsrc.start(boomAt);
  };

  // the doorbell — "your image is finished": two-tone chime, bright and
  // present (in the room, unlike the distant thunder), then a soft
  // spoken-style shimmer. The AI having fun with you.
  const playDoorbell = () => {
    const ctx = ensureAudio(); if (!ctx) return;
    const t = ctx.currentTime;
    const ring = (freq: number, at: number, dur: number) => {
      const o = ctx.createOscillator(); o.type = 'sine'; o.frequency.value = freq;
      const o2 = ctx.createOscillator(); o2.type = 'sine'; o2.frequency.value = freq * 2;  // bell overtone
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.0001, at);
      g.gain.exponentialRampToValueAtTime(0.12, at + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, at + dur);
      const g2 = ctx.createGain(); g2.gain.value = 0.25;  // overtone quieter
      o.connect(g).connect(ctx.destination);
      o2.connect(g2).connect(g);
      o.start(at); o.stop(at + dur + 0.05);
      o2.start(at); o2.stop(at + dur + 0.05);
    };
    ring(659.25, t, 0.5);        // E5
    ring(880.00, t + 0.55, 0.9); // A5 — ding-dong
  };

  // ── the AI's voice: typewriter cheek, then the reveal ───────────
  // When the print is fixed: a retro typewriter line pops up —
  // "Look what I did…" / "I brought you a gift." — then the image
  // blooms into view right behind it. Waiting made exciting.
  const CHEEKS = ['Look what I did…', 'I brought you a gift.', 'Knock knock. It\'s done.', 'Fixed it in the bath…'];
  const [typewriter, setTypewriter] = useState<{ text: string; shown: number } | null>(null);

  const typeCheek = () => {
    const text = CHEEKS[Math.floor(Math.random() * CHEEKS.length)];
    setTypewriter({ text, shown: 0 });
    let i = 0;
    const t = setInterval(() => {
      i += 1;
      setTypewriter({ text, shown: i });
      if (i >= text.length) clearInterval(t);
    }, 55);
    // fade out after 5s
    setTimeout(() => setTypewriter(null), 5200);
  };





  // pinch gesture state (two active pointers on the desk)
  const pinchRef = useRef<Map<number, { x: number; y: number }>>(new Map());
  const pinchStart = useRef<{ dist: number; zoom: number; angle: number; spin: number } | null>(null);
  const pinchBase = useRef<{ x: number; y: number } | null>(null);

  // desk centre for pinch anchor & spin
  const deskCentre = () => {
    const el = frameRef.current;
    if (!el) return { x: 0, y: 0 };
    const r = el.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  };

  const imgRef = useRef<HTMLImageElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const frameRef = useRef<HTMLDivElement | null>(null);

  // AI ops: outpaint and enhance. Provider: the LOCAL FoveAI creative
  // engine /api/dream (:8412). No web readymades — every generated
  // pixel comes from the local SD pipeline. The text the user types
  // steers the pass ("toenail" → detailed toenail).
  const [aiBusy, setAiBusy] = useState(false);
  // magical tour: when the pass fires, a FLASH (lightning)...
  // ...and ~1.8s later the THUNDER arrives — a soft room shake that
  // swells then decays over ~4s. Multi-sensory echo: see flash, feel boom.
  const [flashOn, setFlashOn] = useState(false);
  const [shakeOn, setShakeOn] = useState(false);
  const [aiText, setAiText] = useState('');
  const [aiPromptOpen, setAiPromptOpen] = useState<null | 'paint' | 'outpaint' | 'detail'>(null);
  // generation engine: turbo = LOCAL SD1.5 img2img/txt2img (~2.5G fp16,
  // always fits the shared card next to the resident LLM). zimage_gguf =
  // LOCAL Z-Image-Turbo (12G quantized trio) — opt-in; the service
  // preflights RAM and refuses fast when the LLM is resident.
  const [aiEngine, setAiEngine] = useState<'turbo' | 'zimage_gguf'>('turbo');

  // POST to the local creative engine; returns a data URL of the result.
  const dream = async (payload: Record<string, unknown>) => {
    const res = await fetch('/api/dream', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const j = await res.json().catch(() => ({}));
    if (!res.ok || j.status !== 'success' || !j.image_b64) {
      throw new Error(j.detail || `HTTP ${res.status}`);
    }
    return `data:image/png;base64,${j.image_b64}`;
  };

  // feather-blend: paste src at (x,y,w,h) over ctx with soft alpha edges
  // (f px) so restored pixels melt into generated margins, no hard seam.
  const featherPaste = (ctx: CanvasRenderingContext2D, src: CanvasImageSource, x: number, y: number, w: number, h: number, f = 14) => {
    const mw = Math.max(1, Math.round(w)), mh = Math.max(1, Math.round(h));
    const mm = Math.min(f, Math.floor(Math.min(mw, mh) / 3));
    const mask = document.createElement('canvas');
    mask.width = mw; mask.height = mh;
    const m = mask.getContext('2d')!;
    m.drawImage(src, x, y, w, h);
    m.globalCompositeOperation = 'destination-out';
    const featherEdge = (gx: number | null, gy: number | null) => {
      const grad = gx !== null
        ? m.createLinearGradient(gx === 0 ? 0 : mw, 0, gx === 0 ? mm : mw - mm, 0)
        : m.createLinearGradient(0, gy === 0 ? 0 : mh, 0, gy === 0 ? mm : mh - mm);
      grad.addColorStop(0, 'rgba(0,0,0,1)');
      grad.addColorStop(1, 'rgba(0,0,0,0)');
      m.fillStyle = grad;
      if (gx === 0) m.fillRect(0, 0, mm, mh);
      else if (gx !== null) m.fillRect(mw - mm, 0, mm, mh);
      else if (gy === 0) m.fillRect(0, 0, mw, mm);
      else m.fillRect(0, mh - mm, mw, mm);
    };
    featherEdge(0, null);   featherEdge(mw, null);   // left, right
    featherEdge(null, 0);   featherEdge(null, mh);   // top, bottom
    ctx.drawImage(mask, Math.round(x), Math.round(y));
  };

  const runAI = async (kind: 'paint' | 'outpaint' | 'detail') => {
    const canvas = canvasRef.current;
    if (!canvas || aiBusy) return;
    setAiPromptOpen(null);
    setAiBusy(true);
    playFireSequence();
    // the tour: FLASH...
    setFlashOn(true);
    setTimeout(() => setFlashOn(false), 240);
    // ...then the thunder arrives late and swells.
    setTimeout(() => setShakeOn(true), 1400);
    setTimeout(() => setShakeOn(false), 3800);
    setNotice(`${kind} running…`);
    const div8 = (v: number) => Math.max(64, Math.round(v / 8) * 8);
    try {
      if (kind === 'paint') {
        // fresh LOCAL generation — the frame's proportions are the
        // composition; engine switchable: Z-Image-Turbo (4 steps) or SD1.5
        const cap = Math.min(1, 1024 / Math.max(frameW, frameH));
        const w = div8(frameW * cap), h = div8(frameH * cap);
        const z = aiEngine === 'zimage_gguf';
        const url = await dream({
          prompt: aiText.trim() || 'highly detailed',
          model_type: aiEngine,
          num_inference_steps: z ? 4 : 14,
          guidance_scale: z ? 0.0 : 7.5,
          width: w, height: h,
        });
        playDoorbell();   // someone rings the doorbell — your image is finished
        typeCheek();      // …and the AI teases: "Look what I did…"
        const out = new Image();
        out.onload = () => {
          const bmp = createImageBitmap(canvas);
          undoStack.current.push(bmp as unknown as ImageBitmap);
          // the painted sheet becomes the working image, fit into frame
          canvas.width = out.width; canvas.height = out.height;
          canvas.getContext('2d')!.drawImage(out, 0, 0);
          setResizeW(out.width); setResizeH(out.height);
          const fz = Math.min(frameW / out.width, frameH / out.height);
          setDeskZoom(fz);
          setImgPan({ x: (frameW - out.width * fz) / 2, y: (frameH - out.height * fz) / 2 });
          const cloned = new Image();
          cloned.src = canvas.toDataURL();
          cloned.onload = () => { imgRef.current = cloned; drawImage(); setAiBusy(false); };
        };
        out.onerror = () => { setNotice('paint failed: bad model output'); setAiBusy(false); };
        out.src = url;
      } else if (kind === 'outpaint') {
        // composition = exactly what the frame shows: the image at
        // deskZoom/imgPan, with empty margins out to the frame rim.
        // Target resolution: cap the long edge at 1024 for the model.
        const compWc = frameW, compHc = frameH;
        const cap = Math.min(1, 1024 / Math.max(compWc, compHc));
        const compW = div8(compWc * cap), compH = div8(compHc * cap);
        const comp = document.createElement('canvas');
        comp.width = compW; comp.height = compH;
        const cc = comp.getContext('2d')!;
        cc.fillStyle = '#808080';
        cc.fillRect(0, 0, compW, compH);
        cc.drawImage(imgRef.current!,
          0, 0, imgRef.current!.width, imgRef.current!.height,
          imgPan.x * cap, imgPan.y * cap,
          (resizeW || imgRef.current!.width) * deskZoom * cap,
          (resizeH || imgRef.current!.height) * deskZoom * cap);
        const b64 = comp.toDataURL('image/png').split(',')[1];
        const url = await dream({
          prompt: `${aiText.trim() || 'natural continuation of the scene'} — seamless outpainting, extend beyond the edges naturally, coherent lighting and perspective`,
          model_type: 'turbo',
          reference_image_b64: b64,   // legacy img2img path in creative_service
          strength: 0.72,
          num_inference_steps: 24,
          guidance_scale: 6.5,
          width: compW, height: compH,
        });
        playDoorbell();   // someone rings the doorbell — your image is finished
        typeCheek();      // …and the AI teases: "Look what I did…"
        const out = new Image();
        out.onload = () => {
          const bmp = createImageBitmap(canvas);
          undoStack.current.push(bmp as unknown as ImageBitmap);
          // keep the interior honest: re-paste the original pixels over
          // the generated sheet with feathered edges (only true margins
          // stay generative).
          const fin = document.createElement('canvas');
          fin.width = compW; fin.height = compH;
          const fc = fin.getContext('2d')!;
          const px = imgPan.x * cap, py = imgPan.y * cap;
          const pw = (resizeW || imgRef.current!.width) * deskZoom * cap;
          const ph = (resizeH || imgRef.current!.height) * deskZoom * cap;
          // AI everywhere first (margins + interior), then the original
          // interior (pixel-fidelity), then the AI's interior melted on
          // top with feathered edges — only the true margins stay
          // fully generative
          fc.drawImage(out, 0, 0, compW, compH);
          fc.drawImage(imgRef.current!, 0, 0, imgRef.current!.width, imgRef.current!.height, px, py, pw, ph);
          featherPaste(fc, out, px, py, pw, ph);
          canvas.width = compW; canvas.height = compH;
          canvas.getContext('2d')!.drawImage(fin, 0, 0);
          setResizeW(compW); setResizeH(compH);
          // the composition is now frame-exact: recentre to fit
          setDeskZoom(Math.min(frameW / compW, frameH / compH));
          setImgPan({ x: (frameW - compW * Math.min(frameW / compW, frameH / compH)) / 2, y: (frameH - compH * Math.min(frameW / compW, frameH / compH)) / 2 });
          const cloned = new Image();
          cloned.src = canvas.toDataURL();
          cloned.onload = () => { imgRef.current = cloned; drawImage(); setAiBusy(false); };
        };
        out.onerror = () => { setNotice('outpaint failed: bad model output'); setAiBusy(false); };
        out.src = url;
      } else {
        // detail: upscale the selection crop with the local enhancer
        let srcCanvas = canvas;
        if (!selRect || selRect.w < 8 || selRect.h < 8) throw new Error('drag a selection first');
        const off = document.createElement('canvas');
        off.width = Math.round(selRect.w);
        off.height = Math.round(selRect.h);
        off.getContext('2d')!.drawImage(
          canvas,
          selRect.x, selRect.y, selRect.w, selRect.h,
          0, 0, off.width, off.height
        );
        srcCanvas = off;
        const b64 = srcCanvas.toDataURL('image/png').split(',')[1];
        const url = await dream({
          prompt: aiText.trim() || 'highly detailed, sharp focus',
          model_type: 'enhance',
          control_image_b64: b64,
        });
        playDoorbell();   // someone rings the doorbell — your image is finished
        typeCheek();      // …and the AI teases: "Look what I did…"
        const out = new Image();
        out.onload = () => {
          const bmp = createImageBitmap(canvas);
          undoStack.current.push(bmp as unknown as ImageBitmap);
          const ctx = canvas.getContext('2d')!;
          // paste the enhanced detail back, scaled to the selection
          ctx.drawImage(out, selRect.x, selRect.y, selRect.w, selRect.h);
          const cloned = new Image();
          cloned.src = canvas.toDataURL();
          cloned.onload = () => { imgRef.current = cloned; drawImage(); setAiBusy(false); };
        };
        out.onerror = () => { setNotice('detail failed: bad model output'); setAiBusy(false); };
        out.src = url;
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      // full-GPU policy: an OOM while loading means the resident LLM holds
      // the card — surface it as a switchable, honest error (no silent CPU crawl)
      const friendly = /out of memory|CUDA|allocat/i.test(msg)
        ? 'GPU card is busy (LLM resident) — switch to SD1.5 or free the card first'
        : msg;
      setNotice(`${kind} failed: ${friendly}`);
      setAiBusy(false);
    }
  };

  // save menu: a spawn-menu on the save icon — save / save as / share /
  // copy / export. 'save' is idempotent overwrite; 'save as' prompts a
  // name; 'export' downloads locally; 'copy' → clipboard; 'share' uses
  // the Web Share API when present (Quest share sheet).
  const [saveMenu, setSaveMenu] = useState(false);
  const [saveAsName, setSaveAsName] = useState('');

  // edit stack for undo
  const undoStack = useRef<ImageBitmap[]>([]);

  // selRect in image coords; null = no selection
  const [selRect, setSelRect] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const dragState = useRef<{ startX: number; startY: number; mode: null | 'marquee' } | null>(null);

  // gallery scope: 'mine' (personal folder) | 'community' (public across users)
  const [scope, setScope] = useState<'mine' | 'community'>('mine');
  const [community, setCommunity] = useState<GalleryItem[]>([]);

  const refreshCommunity = useCallback(async () => {
    try {
      const res = await fetch(`${API}/community`);
      const d = await res.json();
      setCommunity(d.community || []);
    } catch (_) {}
  }, []);
  useEffect(() => { if (scope === 'community') refreshCommunity(); }, [scope, refreshCommunity]);

  // ── long-press: tactile card handling ──────────────────────────
  // long-press a gallery card → a small spawn-menu appears:
  //   ♥ Lead    — like it (community weight)
  //   ✕ Rinse   — delete it (rinse duplicates out of the gallery)
  const [pressMenu, setPressMenu] = useState<{ id: string; x: number; y: number } | null>(null);
  const pressTimer = useRef<number | null>(null);

  const startPress = (id: string) => (e: React.PointerEvent) => {
    if (pressTimer.current) window.clearTimeout(pressTimer.current);
    pressTimer.current = window.setTimeout(() => {
      setPressMenu({ id, x: e.clientX, y: e.clientY });
    }, 550);
  };
  const cancelPress = () => {
    if (pressTimer.current) { window.clearTimeout(pressTimer.current); pressTimer.current = null; }
  };

  // selection: long-press marks a card selected; further taps on
  // selected cards toggle membership; the Rinse button sweeps them all.
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const toggleSelect = (id: string) => setSelected(prev => {
    const n = new Set(prev);
    if (n.has(id)) n.delete(id); else n.add(id);
    return n;
  });

  const rinseSelection = async () => {
    const list = scope === 'community' ? community : gallery;
    const targets = list.filter(i => selected.has(i.id));
    if (targets.length === 0) return;
    let ok = 0;
    for (const it of targets) {
      try {
        const res = await fetch(`${API}/file/${encodeURIComponent(it.file)}`, { method: 'DELETE' });
        if (res.ok) ok += 1;
      } catch (_) {}
    }
    await refreshGallery();
    setSelected(new Set());
    setNotice(`rinsed ${ok}/${targets.length} images`);
  };

  const rinseImage = async (item: GalleryItem) => {
    setPressMenu(null);
    try {
      const res = await fetch(`${API}/file/${encodeURIComponent(item.file)}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await refreshGallery();
      setNotice(`rinsed ${item.file}`);
    } catch (err) { setNotice(`rinse failed: ${err instanceof Error ? err.message : err}`); }
  };

  const leadImage = async (item: GalleryItem) => {
    setPressMenu(null);
    try {
      const res = await fetch(`${API}/like/${encodeURIComponent((item as any).owner || 'shared')}/${encodeURIComponent(item.file)}`, { method: 'POST' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await refreshCommunity();
      setNotice(`lead ${item.file}`);
    } catch (err) { setNotice(`lead failed: ${err instanceof Error ? err.message : err}`); }
  };

  // ── gallery fetch ──
  const refreshGallery = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(API);
      const data = await res.json();
      setGallery(data.gallery || []);
    } catch (e) {
      setNotice(`gallery fetch failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refreshGallery(); }, [refreshGallery]);

  // ── upload ──
  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async (re) => {
      const dataUrl = re.target?.result as string;
      try {
        const res = await fetch(`${API}/upload`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ data: dataUrl, name: file.name.replace(/\.[^.]+$/, '') }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        await refreshGallery();
        setNotice(`uploaded ${file.name}`);
      } catch (err) {
        setNotice(`upload failed: ${err instanceof Error ? err.message : err}`);
      }
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  // ── open image into editor ──
  const openEditor = (item: GalleryItem) => {
    const img = new Image();
    img.onload = () => {
      imgRef.current = img;
      setActiveItem(item);
      setEditing(true);
      setBrightness(100);
      setContrast(100);
      setSharpenAmt(0);
      setSelRect(null);
      // start from the image's native ratio: the frame is sized to the
      // window, the image fits inside its current desk zoom, centred
      const availW = Math.max(320, window.innerWidth - 480);
      const availH = Math.max(240, window.innerHeight - 300);
      const fit = Math.min(1, availW / img.width, availH / img.height);
      const fw = Math.round(img.width * fit);
      const fh = Math.round(img.height * fit);
      setFrameW(fw); setFrameH(fh);
      const dz = Math.min(fw / img.width, fh / img.height);
      setDeskZoom(dz);
      setImgPan({ x: (fw - img.width * dz) / 2, y: (fh - img.height * dz) / 2 });
      setResizeW(img.width);
      setResizeH(img.height);
      undoStack.current = [];
      drawImage();
    };
    img.src = item.url;
  };

  // desk view helpers — fit / fill / 1:1, all centred in the frame
  const fitImage = (mode: 'fit' | 'fill' | '1:1') => {
    const img = imgRef.current;
    if (!img || !frameW || !frameH) return;
    const w = resizeW || img.width, h = resizeH || img.height;
    const z = mode === 'fit' ? Math.min(frameW / w, frameH / h)
      : mode === 'fill' ? Math.max(frameW / w, frameH / h)
      : 1;
    setDeskZoom(z);
    setImgPan({ x: (frameW - w * z) / 2, y: (frameH - h * z) / 2 });
  };

  // crop to frame: cut exactly the image region the frame currently
  // shows (image bigger than frame → the framing decides the crop).
  const cropToFrame = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const z = deskZoom || 1;
    const rx0 = -imgPan.x / z, ry0 = -imgPan.y / z;
    const x0 = Math.max(0, rx0), y0 = Math.max(0, ry0);
    const x1 = Math.min(canvas.width, rx0 + frameW / z);
    const y1 = Math.min(canvas.height, ry0 + frameH / z);
    const nw = Math.round(x1 - x0), nh = Math.round(y1 - y0);
    if (nw < 8 || nh < 8) { setNotice('frame is outside the image — pan or fit first'); return; }
    (async () => {
      const ctx = canvas.getContext('2d')!;
      const bmp = await createImageBitmap(canvas);
      undoStack.current.push(bmp);
      const region = ctx.getImageData(x0, y0, nw, nh);
      canvas.width = nw; canvas.height = nh;
      canvas.getContext('2d')!.putImageData(region, 0, 0);
      setResizeW(nw); setResizeH(nh);
      const cloned = new Image();
      cloned.src = canvas.toDataURL();
      cloned.onload = () => { imgRef.current = cloned; drawImage(); };
      setNotice(`cropped to frame: ${nw}×${nh}`);
    })();
  };

  // px→unit formatting: 1in nominal = PPI css px; measured at the CURRENT
// zoom (what you actually see on the desk)
const fmt = (imagePx: number) => {
  const cssPerPx = deskZoom || 1;
  const vPx = imagePx * cssPerPx;
  if (unit === 'px') return `${Math.round(imagePx)}px`;
  if (unit === 'in') return `${(vPx / PPI).toFixed(1)}″`;
  if (unit === 'cm') return `${(vPx / PPI * 2.54).toFixed(1)}cm`;
  return `${Math.round(imagePx)}px`;
};
// ruler scale: total desk width reads as refUnits of the active real unit
const rulerLabel = () => {
  if (unit === 'px') return `${frameW}px`;
  const inches = frameW / PPI;
  if (unit === 'in') return `${inches.toFixed(1)}″ of ${refUnits}″`;
  return `${(inches * 2.54).toFixed(1)}cm`;
};
const rulerMid = () => {
  if (unit === 'px') return `${Math.round(frameW / 2)}px`;
  const inches = frameW / PPI / 2;
  if (unit === 'in') return `${inches.toFixed(1)}″`;
  return `${(inches * 2.54).toFixed(1)}cm`;
};

// ── canvas draw with adjustments ──
  const drawImage = useCallback(() => {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!img || !canvas) return;
    const w = resizeW || img.width;
    const h = resizeH || img.height;
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // scale step if a resize is staged
    ctx.clearRect(0, 0, w, h);
    ctx.drawImage(img, 0, 0, w, h);

    // pixel-level adjustments via ImageData
    const id = ctx.getImageData(0, 0, w, h);
    const d = id.data;
    const bAmt = brightness / 100;
    const cAmt = contrast / 100;
    if (bAmt !== 1 || cAmt !== 1) {
      for (let i = 0; i < d.length; i += 4) {
        for (let c = 0; c < 3; c++) {
          let v = d[i + c];
          v = (v - 128) * cAmt + 128;   // contrast around mid
          v *= bAmt;                     // brightness
          d[i + c] = Math.max(0, Math.min(255, v));
        }
      }
    }
    // sharpen: unsharp mask approximation (1 centre, -α neighbours)
    if (sharpenAmt > 0) {
      const a = sharpenAmt / 100;
      const copy = new Uint8ClampedArray(d);
      for (let y = 1; y < h - 1; y++) {
        for (let x = 1; x < w - 1; x++) {
          const i = (y * w + x) * 4;
          for (let c = 0; c < 3; c++) {
            const centre = copy[i + c];
            const neighbours =
              copy[i - 4 + c] + copy[i + 4 + c] +
              copy[i - w * 4 + c] + copy[i + w * 4 + c];
            d[i + c] = Math.max(0, Math.min(255, centre + a * (centre * 4 - neighbours) / 4));
          }
        }
      }
    }
    ctx.putImageData(id, 0, 0);
  }, [brightness, contrast, sharpenAmt, resizeW, resizeH]);

  useEffect(() => { if (editing) drawImage(); }, [drawImage, editing]);

  // ── frame drag (the white lines) ──
  type DragMode = 'constrain' | 'distort';
  const startFrameDrag = (edge: 'left' | 'right' | 'top' | 'bottom' | 'corner', mode: DragMode = 'constrain') => (e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const startX = e.clientX, startY = e.clientY;
    const fw = frameW, fh = frameH;
    const ratio = imgRef.current ? imgRef.current.width / imgRef.current.height : 1;

    const onMove = (ev: PointerEvent) => {
      // pinch-style zoom on the checkboard (two-pointer gesture)
      if (ev.pointerType === 'touch' && pinchRef.current.size >= 2) return;  // pinch handles this
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;
      if (mode === 'distort') {
        // free resize: dx → width, dy → height independently
        const dir = edge === 'left' ? -1 : 1;
        const nw = Math.max(160, Math.min(2400, fw + (edge === 'top' || edge === 'bottom' ? 0 : dir * dx)));
        const vh = edge === 'top' ? -1 : 1;
        const nh = Math.max(120, Math.min(2000, fh + (edge === 'left' || edge === 'right' ? 0 : vh * dy)));
        setFrameW(nw); setFrameH(nh);
        return;
      }
      if (edge === 'top' || edge === 'bottom' || edge === 'corner') {
        // proportion-constrained: one axis drives, the other follows
        const drive = edge === 'top' || edge === 'corner' ? -dy : dy;
        const nh = Math.max(120, Math.min(2000, fh + drive));
        const nw = Math.round(nh * ratio);
        setFrameW(nw); setFrameH(nh);
      } else {
        const dir = edge === 'left' ? -1 : 1;
        const nw = Math.max(160, Math.min(2400, fw + dir * dx));
        const nh = Math.round(nw / ratio);
        setFrameW(nw); setFrameH(nh);
      }
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  // ── worktable gestures: pinch-zoom (anchored), two-finger spin ──
  const deskPointer = (e: React.PointerEvent<HTMLDivElement>) => {
    const pinch = pinchRef.current;
    if (pinch.size === 0 && e.buttons === 0 && e.pointerType !== 'touch') return;  // ignore hover
    if (e.type === 'pointerdown' && e.pointerType === 'touch') {
      pinch.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pinch.size === 2) {
        const [a, b] = [...pinch.values()];
        pinchBase.current = deskCentre();
        pinchStart.current = {
          dist: Math.hypot(b.x - a.x, b.y - a.y),
          zoom: deskZoom,
          angle: Math.atan2(b.y - a.y, b.x - a.x),
          spin,
        };
      }
    } else if (e.type === 'pointermove' && pinch.size >= 2 && pinchStart.current) {
      if (pinch.has(e.pointerId)) pinch.set(e.pointerId, { x: e.clientX, y: e.clientY });
      const [a, b] = [...pinch.values()];
      const now = Math.hypot(b.x - a.x, b.y - a.y);
      const ang = Math.atan2(b.y - a.y, b.x - a.x);
      const st = pinchStart.current;
      const nz = Math.max(0.05, Math.min(5, st.zoom * (now / st.dist)));
      // anchored: the desk centre point stays put while zooming
      const frame = frameRef.current;
      if (frame && pinchBase.current) {
        const r = frame.getBoundingClientRect();
        const bx = pinchBase.current.x - r.left, by = pinchBase.current.y - r.top;
        const k = nz / deskZoom;
        setDeskZoom(nz);
        setImgPan({ x: bx - (bx - imgPan.x) * k, y: by - (by - imgPan.y) * k });
      } else {
        setDeskZoom(nz);
      }
      let deltaSpin = ((ang - st.angle) * 180) / Math.PI;
      setSpin(st.spin + deltaSpin);
    } else if (e.type === 'pointerup' || e.type === 'pointercancel') {
      pinch.delete(e.pointerId);
      if (pinch.size < 2) pinchStart.current = null;
    }
  };

  // wheel zoom — anchored at the cursor, 5%..500%
  const frameWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    e.preventDefault();
    const frame = frameRef.current;
    if (!frame) return;
    const r = frame.getBoundingClientRect();
    const cx = e.clientX - r.left, cy = e.clientY - r.top;
    const nz = Math.max(0.05, Math.min(5, deskZoom * Math.exp(-e.deltaY * 0.0016)));
    const k = nz / deskZoom;
    setDeskZoom(nz);
    setImgPan({ x: cx - (cx - imgPan.x) * k, y: cy - (cy - imgPan.y) * k });
  };

  // ── pan / marquee on the canvas ──
  // Pan tool (✋) or middle mouse drags the image around the desk
  // (independent of the frame); Select/Crop drag a marquee.
  const panDrag = useRef<{ sx: number; sy: number; px: number; py: number } | null>(null);
  const canvasPointer = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (e.type === 'pointerdown') {
      const wantPan = tool === 'pan' || e.button === 1;
      if (wantPan) {
        e.preventDefault();
        panDrag.current = { sx: e.clientX, sy: e.clientY, px: imgPan.x, py: imgPan.y };
      } else if (tool === 'select' || tool === 'crop') {
        const canvas = canvasRef.current!;
        const rect = canvas.getBoundingClientRect();
        const sx = (e.clientX - rect.left) * (canvas.width / rect.width);
        const sy = (e.clientY - rect.top) * (canvas.height / rect.height);
        dragState.current = { startX: sx, startY: sy, mode: 'marquee' };
      }
      return;
    }
    if (panDrag.current && e.type === 'pointermove') {
      setImgPan({
        x: panDrag.current.px + (e.clientX - panDrag.current.sx),
        y: panDrag.current.py + (e.clientY - panDrag.current.sy),
      });
      return;
    }
    if (panDrag.current && (e.type === 'pointerup' || e.type === 'pointercancel')) {
      panDrag.current = null;
      return;
    }
    if (!dragState.current) return;
    const canvas = canvasRef.current!;
    const rect = canvas.getBoundingClientRect();
    const sx = (e.clientX - rect.left) * (canvas.width / rect.width);
    const sy = (e.clientY - rect.top) * (canvas.height / rect.height);
    if (e.type === 'pointermove' && dragState.current.mode === 'marquee') {
      setSelRect({
        x: Math.min(sx, dragState.current.startX),
        y: Math.min(sy, dragState.current.startY),
        w: Math.abs(sx - dragState.current.startX),
        h: Math.abs(sy - dragState.current.startY),
      });
    } else if (e.type === 'pointerup') {
      dragState.current = null;
    }
  };

  // ── apply active tool ──
  const applyTool = async (t: Tool) => {
    const img = imgRef.current;
    const canvas = canvasRef.current;
    if (!img || !canvas) return;

    if (t === 'undo') {
      const prev = undoStack.current.pop();
      if (!prev) { setNotice('nothing to undo'); return; }
      // restore canvas from bitmap
      canvas.width = prev.width; canvas.height = prev.height;
      canvas.getContext('2d')!.drawImage(prev, 0, 0);
      setResizeW(prev.width); setResizeH(prev.height);
      // reflect into imgRef for future draws
      const cloned = new Image();
      cloned.src = canvas.toDataURL();
      cloned.onload = () => { imgRef.current = cloned; drawImage(); };
      setNotice('undone');
      return;
    }

    if (t === 'save' || t === 'saveAs') {
      const dataUrl = canvas.toDataURL('image/png');
      const base = t === 'saveAs' && saveAsName.trim() ? saveAsName.trim().replace(/\.(png|jpg|jpeg|webp)$/i, '') : `${activeItem?.id || 'edit'}_edited`;
      try {
        const res = await fetch(`${API}/upload`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ data: dataUrl, name: base }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        await refreshGallery();
        setSaveMenu(false);
        setNotice(`saved as ${base}`);
      } catch (err) { setNotice(`save failed: ${err instanceof Error ? err.message : err}`); }
      return;
    }

    if (t === 'copy') {
      try {
        const blob = await new Promise<Blob>((ok, err) => canvas.toBlob(b => b ? ok(b) : err('toBlob failed'), 'image/png'));
        await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
        setNotice('image copied to clipboard');
      } catch (err) { setNotice(`copy failed: ${err instanceof Error ? err.message : err}`); }
      return;
    }

    if (t === 'export') {
      const a = document.createElement('a');
      a.href = canvas.toDataURL('image/png');
      a.download = `${activeItem?.id || 'edit'}_${resizeW}x${resizeH}.png`;
      a.click();
      setNotice('exported locally');
      return;
    }

    if (t === 'share') {
      // Web Share API — Quest/Android surfaces the OS share sheet
      try {
        const blob = await new Promise<Blob>((ok, err) => canvas.toBlob(b => b ? ok(b) : err('toBlob failed'), 'image/png'));
        const file = new File([blob], `${activeItem?.id || 'edit'}.png`, { type: 'image/png' });
        if (navigator.canShare && navigator.canShare({ files: [file] })) {
          await navigator.share({ files: [file], title: 'FoveAI edit' });
        } else {
          setNotice('share target unavailable');
        }
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;  // user cancelled the sheet
        setNotice(`share failed: ${err instanceof Error ? err.message : err}`);
      }
      return;
    }

    // stage a bitmap for undo first
    const bmp = await createImageBitmap(canvas);
    undoStack.current.push(bmp);

    if (t === 'resize') { drawImage(); return; }        // live from inputs
    if (t === 'light') { drawImage(); return; }          // live from inputs
    if (t === 'sharpen') { drawImage(); return; }        // live from inputs

    if (t === 'crop' &&
        (!selRect || selRect.w < 8 || selRect.h < 8)) {
      setNotice('drag a selection first, then Crop');
      undoStack.current.pop();
      return;
    }
    if (t === 'crop' && selRect) {
      const ctx = canvas.getContext('2d')!;
      const region = ctx.getImageData(selRect.x, selRect.y, selRect.w, selRect.h);
      const nw = selRect.w, nh = selRect.h;
      canvas.width = nw; canvas.height = nh;
      const nctx = canvas.getContext('2d')!;
      nctx.putImageData(region, 0, 0);
      setSelRect(null); setResizeW(nw); setResizeH(nh);
      const cloned = new Image();
      cloned.src = canvas.toDataURL();
      cloned.onload = () => { imgRef.current = cloned; drawImage(); };
      return;
    }

    if (t === 'rotate') {
      const ctx = canvas.getContext('2d')!;
      const src = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const nw = canvas.height, nh = canvas.width;
      canvas.width = nw; canvas.height = nh;
      const out = ctx.createImageData(nw, nh);
      for (let y = 0; y < src.height; y++) {
        for (let x = 0; x < src.width; x++) {
          const si = (y * src.width + x) * 4;
          const x2 = src.height - 1 - y;
          const y2 = x;
          const di = (y2 * nw + x2) * 4;
          for (let c = 0; c < 4; c++) out.data[di + c] = src.data[si + c];
        }
      }
      ctx.putImageData(out, 0, 0);
      setResizeW(nw); setResizeH(nh);
      const cloned = new Image();
      cloned.src = canvas.toDataURL();
      cloned.onload = () => { imgRef.current = cloned; drawImage(); };
      return;
    }
  };

  // ── rulers ──
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100%', width: '100%',
      transform: shakeOn ? `translate${corePulse % 2 ? 'X' : 'Y'}(${(Math.sin(corePulse * 2.1) * 2.2).toFixed(1)}px)` : undefined,
      transition: 'transform 120ms linear',
    }}>
      {/* the lightning flash overlay — brief white bloom at fire */}
      <div style={{
        position: 'fixed', inset: 0, zIndex: 300, pointerEvents: 'none',
        background: 'radial-gradient(circle at 50% 45%, rgba(255,255,255,0.95), rgba(255,255,255,0.25) 55%, transparent 80%)',
        opacity: flashOn ? 1 : 0,
        transition: 'opacity 200ms ease-out',
      }} />
      <div className="breadcrumb" style={{ padding: '15px 20px', borderBottom: '1px solid var(--border)' }}>
        TOOLS // IMAGE_EDITOR {activeItem ? `· ${activeItem.file}` : ''}
      </div>

      {!editing ? (
        // ── gallery view ──
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
          {/* gallery scope: mine | community — the magic of glimpsing others' work */}
          <div style={{ display: 'flex', gap: '6px', marginBottom: '12px', fontFamily: 'Orbitron', fontSize: '0.58rem' }}>
            {(['mine', 'community'] as const).map(s => (
              <button key={s}
                onClick={() => setScope(s)}
                style={{
                  padding: '7px 16px', borderRadius: '4px', cursor: 'pointer',
                  fontFamily: 'Orbitron', letterSpacing: '1px',
                  background: scope === s ? 'rgba(0,243,255,0.15)' : 'transparent',
                  border: '1px solid ' + (scope === s ? 'var(--neon-blue)' : 'var(--border)'),
                  color: scope === s ? 'var(--neon-blue)' : 'var(--text-muted)',
                }}>{s === 'mine' ? '▦ mine' : '🌐 community'}</button>
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <label style={{
              padding: '8px 18px', background: 'rgba(0,243,255,0.1)', border: '1px solid var(--neon-blue)',
              borderRadius: '4px', color: 'var(--neon-blue)', fontFamily: 'Orbitron', fontSize: '0.65rem',
              cursor: 'pointer', whiteSpace: 'nowrap'
            }}>
              ⤒ UPLOAD IMAGE
              <input type="file" accept="image/*" style={{ display: 'none' }} onChange={handleUpload} />
            </label>
            {selected.size > 0 && (
              <button onClick={rinseSelection} title="rinse every selected image out of the gallery" style={{
                padding: '8px 16px', background: 'rgba(255,80,60,0.15)', border: '1px solid #ff6a5d',
                color: '#ff6a5d', borderRadius: '4px', cursor: 'pointer', fontFamily: 'Orbitron', fontSize: '0.6rem', whiteSpace: 'nowrap'
              }}>✕ RINSE ({selected.size})</button>
            )}
            <button onClick={refreshGallery} style={{
              padding: '8px 14px', background: 'transparent', border: '1px solid var(--border)',
              color: 'var(--text-muted)', borderRadius: '4px', cursor: 'pointer', fontFamily: 'Orbitron', fontSize: '0.6rem'
            }}>↺ REFRESH</button>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.7rem', fontFamily: 'Share Tech Mono' }}>
              {loading ? 'loading…' : `${gallery.length} in gallery`}
            </span>
          </div>

          {notice && (
            <div style={{
              padding: '8px 12px', marginBottom: '12px', background: 'rgba(0,243,255,0.08)',
              border: '1px solid rgba(0,243,255,0.3)', color: 'var(--neon-blue)', fontSize: '0.75rem', borderRadius: '4px'
            }}>{notice}</div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: '14px' }}>
            {(scope === 'community' ? community : gallery).map(item => (
              <div key={item.id}
                onClick={() => selected.has(item.id) ? toggleSelect(item.id) : openEditor(item)}
                onPointerDown={startPress(item.id)}
                onPointerUp={cancelPress}
                onPointerLeave={cancelPress}
                style={{
                  cursor: 'pointer',
                  border: selected.has(item.id) ? '2px solid var(--neon-pink)'
                    : activeItem?.id === item.id ? '1px solid var(--neon-blue)' : '1px solid var(--border)',
                  borderRadius: '6px', overflow: 'hidden', background: 'rgba(0,0,0,0.25)',
                }}>
                <img src={item.url} alt={item.file} style={{
                  width: '100%', height: '120px', objectFit: 'cover', display: 'block'
                }} />
                <div style={{ padding: '8px' }}>
                  <div style={{ color: '#fff', fontSize: '0.7rem', fontFamily: 'Share Tech Mono', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.file}
                  </div>
                  {scope === 'community' && (
                    <button
                      onClick={async (e) => {
                        e.stopPropagation();
                        try {
                          await fetch(`${API}/like/${(item as any).owner}/${item.file}`, { method: 'POST' });
                          await refreshCommunity();
                        } catch (_) {}
                      }}
                      title="like this image"
                      style={{
                        marginTop: '4px', padding: '2px 8px', cursor: 'pointer',
                        background: 'rgba(255,0,127,0.12)', border: '1px solid var(--neon-pink)',
                        color: 'var(--neon-pink)', borderRadius: '3px', fontSize: '0.6rem', fontFamily: 'Share Tech Mono'
                      }}>
                      ♥ {((item as any).likes ?? 0)} · {(item as any).owner}
                    </button>
                  )}
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.6rem', fontFamily: 'Share Tech Mono' }}>
                    {item.bytes > 1024 * 1024 ? `${(item.bytes / 1048576).toFixed(1)}M` : `${Math.max(1, Math.round(item.bytes / 1024))}k`}
                    {item.added ? ` · ${item.added.slice(0, 10)}` : ''}
                  </div>
                </div>
              </div>
            ))}
          </div>
          {!loading && (scope === 'community' ? community.length === 0 : gallery.length === 0) && (
            <div style={{ color: 'var(--text-muted)', fontFamily: 'Share Tech Mono', marginTop: '40px', textAlign: 'center' }}>
              gallery empty — upload an image to start editing
            </div>
          )}
        </div>
      ) : (
        // ── editor view ──
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {/* top menu inside the editor */}
          <div style={{ display: 'flex', gap: '4px', padding: '8px 16px', borderBottom: '1px solid var(--border)', flexWrap: 'wrap', alignItems: 'center' }}>
            {/* dial matrix: REAL dials + pulsing LED */}
            <div style={{ position: 'relative' }}>
              <button onClick={() => setDialMenu(!dialMenu)} title="Dial Matrix — image generation settings" style={{
                padding: '6px 12px',
                background: dialMenu ? 'rgba(0,243,255,0.15)' : 'transparent',
                border: '1px solid var(--border)', borderRadius: '4px', color: '#fff',
                cursor: 'pointer', fontSize: '0.7rem', fontFamily: 'Share Tech Mono', whiteSpace: 'nowrap'
              }}>◉ Dials ◃</button>
            </div>
            {TOOLS.filter(t => !['save'].includes(t.id)).map(t => (
              <button key={t.id} onClick={() => applyTool(t.id)} title={t.hint} style={{
                padding: '6px 12px',
                background: (tool === t.id && t.id !== 'undo') ? 'rgba(0,243,255,0.15)' : 'transparent',
                border: '1px solid var(--border)', borderRadius: '4px', color: '#fff',
                cursor: 'pointer', fontSize: '0.7rem', fontFamily: 'Share Tech Mono', whiteSpace: 'nowrap'
              }}>{t.icon} {t.label}</button>
            ))}

            {/* save spawn-menu — outermost right of the top bar */}
            <div style={{ position: 'relative', marginLeft: 'auto', display: 'flex', gap: '4px' }}>
              <button onClick={() => { setSaveAsName(''); setSaveMenu(!saveMenu); }} style={{
                padding: '6px 12px',
                background: 'rgba(0,243,255,0.15)',
                border: '1px solid var(--neon-blue)', borderRadius: '4px', color: '#fff',
                cursor: 'pointer', fontSize: '0.7rem', fontFamily: 'Share Tech Mono', whiteSpace: 'nowrap'
              }}>⤓ Save ▾</button>
              {saveMenu && (
                <div style={{
                  position: 'absolute', top: '110%', right: 0, zIndex: 50, minWidth: 170,
                  background: 'rgba(8,12,20,0.97)', border: '1px solid var(--neon-blue)', borderRadius: '6px',
                  boxShadow: '0 8px 30px rgba(0,0,0,0.6)', padding: '4px', display: 'flex', flexDirection: 'column'
                }}>
                  {([
                    ['save', '⤓ Save', 'overwrite in gallery'],
                    ['saveAs', '⤓ Save As…', 'new name in gallery'],
                    ['share', '⇪ Share', 'OS share sheet'],
                    ['copy', '⧉ Copy', 'clipboard'],
                    ['export', '⬒ Export', 'download file'],
                  ] as [Tool, string, string][]).map(([id, label, hint]) => (
                    <button key={id} title={hint} onClick={() => id === 'saveAs' ? undefined : applyTool(id)} style={{
                      padding: '8px 12px', background: 'transparent', border: 'none',
                      borderBottom: '1px solid rgba(255,255,255,0.06)', color: '#fff', textAlign: 'left',
                      cursor: 'pointer', fontSize: '0.72rem', fontFamily: 'Share Tech Mono', whiteSpace: 'nowrap'
                    }}>{label}</button>
                  ))}
                  {/* save-as inline name input */}
                  <div style={{ padding: '8px 12px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                    <input
                      value={saveAsName}
                      placeholder="name for Save As…"
                      onChange={e => setSaveAsName(e.target.value)}
                      onPointerDown={e => e.stopPropagation()}
                      style={{
                        width: '100%', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)',
                        color: '#fff', padding: '6px', borderRadius: '4px', fontFamily: 'Share Tech Mono', fontSize: '0.7rem'
                      }}
                    />
                    <button onClick={() => applyTool('saveAs')} style={{
                      width: '100%', marginTop: '6px', padding: '6px',
                      background: 'rgba(0,243,255,0.12)', border: '1px solid var(--neon-blue)',
                      color: '#fff', borderRadius: '4px', cursor: 'pointer', fontSize: '0.7rem', fontFamily: 'Share Tech Mono'
                    }}>⤓ Save As</button>
                  </div>
                </div>
              )}
            </div>
            <button onClick={() => setChecked(!checked)} title="toggle checkboard worktable" style={{
              padding: '6px 12px', background: checked ? 'rgba(0,243,255,0.15)' : 'transparent',
              border: '1px solid var(--border)', borderRadius: '4px', color: '#fff',
              cursor: 'pointer', fontSize: '0.7rem', fontFamily: 'Share Tech Mono', whiteSpace: 'nowrap'
            }}>▦ desk</button>
            <button onClick={() => { setSpin(0); fitImage('fit'); }} title="reset desk spin + fit image in frame" style={{
              padding: '6px 12px', background: 'transparent',
              border: '1px solid var(--border)', borderRadius: '4px', color: '#fff',
              cursor: 'pointer', fontSize: '0.7rem', fontFamily: 'Share Tech Mono', whiteSpace: 'nowrap'
            }}>⊙ reset</button>
            <div style={{ flex: 1 }} />
            <button onClick={() => setEditing(false)} style={{
              padding: '6px 14px', background: 'transparent', border: '1px solid var(--border)',
              color: 'var(--text-muted)', borderRadius: '4px', cursor: 'pointer', fontFamily: 'Share Tech Mono', fontSize: '0.7rem'
            }}>← gallery</button>
          </div>

          {/* tool parameter strips */}
          {(tool === 'light' || tool === 'sharpen' || tool === 'resize') && (
            <div style={{ display: 'flex', gap: '18px', padding: '10px 16px', borderBottom: '1px solid var(--border)', alignItems: 'center', flexWrap: 'wrap', fontFamily: 'Share Tech Mono', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
              {tool === 'light' && (<>
                <label>☀ brightness <input type="range" min={20} max={200} value={brightness} onChange={e => setBrightness(+e.target.value)} /></label>
                <label>◐ contrast <input type="range" min={20} max={200} value={contrast} onChange={e => setContrast(+e.target.value)} /></label>
              </>)}
              {tool === 'sharpen' && (
                <label>▽ sharpen <input type="range" min={0} max={100} value={sharpenAmt} onChange={e => setSharpenAmt(+e.target.value)} /></label>
              )}
              {(
          /* units UI — tools share the worktable units */
          true) && (<>
                <select value={unit} onChange={e => setUnit(e.target.value as Unit)} style={{
                  background: '#0a0f19', border: '1px solid var(--border)', color: '#fff',
                  fontFamily: 'Share Tech Mono', fontSize: '0.7rem', padding: '4px 8px', borderRadius: '4px'
                }}>
                  <option value="px">px</option>
                  <option value="in">inch (real)</option>
                  <option value="cm">cm (real)</option>
                </select>
                {unit !== 'px' && (
                  <label>desk = <input type="number" min={5} max={100} value={refUnits}
                    onChange={e => setRefUnits(+e.target.value)} style={{ width: '46px' }} />
                    {unit === 'in' ? '″ wide' : 'cm wide'}</label>
                )}
              </>)}
              {tool === 'resize' && (<>
                <label>w <input type="number" value={resizeW} onChange={e => {
                  const w = +e.target.value;
                  setResizeW(w);
                  if (lockRatio) setResizeH(Math.round(w / (imgRef.current ? imgRef.current.width / imgRef.current.height : 1)));
                }} style={{ width: '70px' }} /></label>
                <label>h <input type="number" value={resizeH} onChange={e => {
                  const h = +e.target.value;
                  setResizeH(h);
                  if (lockRatio) setResizeW(Math.round(h * (imgRef.current ? imgRef.current.width / imgRef.current.height : 1)));
                }} style={{ width: '70px' }} /></label>
                <label><input type="checkbox" checked={lockRatio} onChange={e => setLockRatio(e.target.checked)} /> lock proportions</label>
              </>)}
            </div>
          )}

          <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
            {/* ── the measured desk ── */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {/* checkboard worktable surface: CSS chess pattern; pinch/spin live here */}
          <div
            onPointerDown={deskPointer}
            onPointerMove={deskPointer}
            onPointerUp={deskPointer}
            onPointerCancel={deskPointer}
            style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
              overflow: 'hidden', padding: '24px', minHeight: 0, touchAction: 'none',
              background: checked
                ? 'repeating-conic-gradient(rgba(255,255,255,0.045) 0% 25%, transparent 0% 50%) 0 0/40px 40px'
                : 'transparent',
              transform: `rotate(${spin}deg)`,
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', width: frameW, minWidth: 'fit-content' }}>
              {/* top ruler */}
              {tool !== 'select' && (
                <div style={{ height: '20px', display: 'flex', alignItems: 'flex-end', color: 'var(--text-muted)', fontFamily: 'Share Tech Mono', fontSize: '0.55rem', justifyContent: 'space-between', padding: '0 6px' }}>
                  <span>0</span>
                  <span>{rulerMid()}</span>
                  <span>{rulerLabel()}</span>
                </div>
              )}
              {/* top drag line */}
              <div
                onPointerDown={startFrameDrag('top')}
                style={{ height: '6px', background: '#fff', cursor: 'ns-resize', borderRadius: '2px', opacity: 0.9 }}
                title="pull to resize the frame — the image keeps its own zoom & placement"
              />
              <div style={{ display: 'flex', alignItems: 'stretch' }}>
                {/* left ruler */}
                {tool !== 'select' && (
                  <div style={{ width: '20px', color: 'var(--text-muted)', fontFamily: 'Share Tech Mono', fontSize: '0.55rem', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', alignItems: 'flex-end', padding: '6px 4px' }}>
                    <span>0</span>
                    <span>{Math.round(frameH / 2)}</span>
                    <span>{frameH}</span>
                  </div>
                )}
                {/* left drag line */}
                <div
                  onPointerDown={startFrameDrag('left')}
                  style={{ width: '6px', background: '#fff', cursor: 'ew-resize', borderRadius: '2px', opacity: 0.9 }}
                  title="pull to resize"
                />
                {/* the frame is a WINDOW onto the image: the canvas is
                    absolutely placed at imgPan, scaled to deskZoom —
                    bigger, smaller, or offset at will */}
                <div ref={frameRef} onWheel={frameWheel} style={{
                  width: frameW - 24, height: frameH,
                  position: 'relative', overflow: 'hidden',
                  background: 'rgba(255,255,255,0.02)', margin: '6px 0'
                }}>
                  <canvas
                    ref={canvasRef}
                    onPointerDown={canvasPointer}
                    onPointerMove={canvasPointer}
                    onPointerUp={canvasPointer}
                    onPointerCancel={canvasPointer}
                    style={{
                      position: 'absolute', left: imgPan.x, top: imgPan.y,
                      width: (resizeW || 1) * deskZoom, height: (resizeH || 1) * deskZoom,
                      cursor: (tool === 'pan') ? 'grab'
                        : (tool === 'select' || tool === 'crop') ? 'crosshair' : 'default'
                    }}
                  />
                </div>
                {/* right drag line */}
                <div
                  onPointerDown={startFrameDrag('right')}
                  style={{ width: '6px', background: '#fff', cursor: 'ew-resize', borderRadius: '2px', opacity: 0.9 }}
                  title="pull to resize"
                />
              </div>
              {/* bottom drag line */}
              <div
                onPointerDown={startFrameDrag('bottom')}
                style={{ height: '6px', background: '#fff', cursor: 'ns-resize', borderRadius: '2px', opacity: 0.9 }}
                title="pull to resize"
              />
              {/* contextual AI chips — appear when they make sense */}
              {(selRect || true) && (
                <div style={{ display: 'flex', gap: '8px', padding: '8px', justifyContent: 'center', flexWrap: 'wrap' }}>
                  <button
                    onClick={() => fitImage('fit')}
                    title="fit the whole image inside the frame"
                    style={{
                      padding: '7px 14px', background: 'transparent',
                      border: '1px solid var(--border)', borderRadius: '14px', color: '#fff',
                      cursor: 'pointer', fontSize: '0.68rem', fontFamily: 'Share Tech Mono', whiteSpace: 'nowrap',
                    }}>⤡ fit</button>
                  <button
                    onClick={() => fitImage('fill')}
                    title="fill the frame — image overflows, crop by framing"
                    style={{
                      padding: '7px 14px', background: 'transparent',
                      border: '1px solid var(--border)', borderRadius: '14px', color: '#fff',
                      cursor: 'pointer', fontSize: '0.68rem', fontFamily: 'Share Tech Mono', whiteSpace: 'nowrap',
                    }}>⊞ fill</button>
                  <button
                    onClick={() => fitImage('1:1')}
                    title="zoom to 100% — one image pixel per desk pixel"
                    style={{
                      padding: '7px 14px', background: 'transparent',
                      border: '1px solid var(--border)', borderRadius: '14px', color: '#fff',
                      cursor: 'pointer', fontSize: '0.68rem', fontFamily: 'Share Tech Mono', whiteSpace: 'nowrap',
                    }}>1:1</button>
                  <button
                    onClick={cropToFrame}
                    title="cut exactly what the frame shows — image may be bigger than the frame"
                    style={{
                      padding: '7px 14px', background: 'transparent',
                      border: '1px solid var(--border)', borderRadius: '14px', color: '#fff',
                      cursor: 'pointer', fontSize: '0.68rem', fontFamily: 'Share Tech Mono', whiteSpace: 'nowrap',
                    }}>⛶ crop to frame</button>
                  <button
                    onClick={() => { setAiText(''); setAiPromptOpen('paint'); }}
                    disabled={aiBusy}
                    title="paint a fresh image with the local engine (Z-Image-Turbo / SD1.5)"
                    style={{
                      padding: '7px 14px',
                      background: aiPromptOpen === 'paint' ? 'rgba(160,90,255,0.25)' : 'rgba(160,90,255,0.12)',
                      border: '1px solid #a05aff', borderRadius: '14px', color: '#fff',
                      cursor: aiBusy ? 'wait' : 'pointer', fontSize: '0.68rem', fontFamily: 'Share Tech Mono', whiteSpace: 'nowrap',
                      opacity: aiBusy ? 0.5 : 1,
                    }}>✦ AI Paint</button>
                  <button
                    onClick={() => { setAiText(''); setAiPromptOpen('outpaint'); }}
                    disabled={aiBusy}
                    title="fill in everything around the image out to the frame"
                    style={{
                      padding: '7px 14px',
                      background: aiPromptOpen === 'outpaint' ? 'rgba(255,0,127,0.25)' : 'rgba(0,243,255,0.1)',
                      border: '1px solid var(--neon-pink)', borderRadius: '14px', color: '#fff',
                      cursor: aiBusy ? 'wait' : 'pointer', fontSize: '0.68rem', fontFamily: 'Share Tech Mono', whiteSpace: 'nowrap',
                      opacity: aiBusy ? 0.5 : 1,
                    }}>✨ outpaint to frame</button>
                  <button
                    onClick={() => { setAiText(''); setAiPromptOpen('detail'); }}
                    disabled={aiBusy || !selRect}
                    title={selRect ? 'high-res AI detail of your selection' : 'drag a selection first'}
                    style={{
                      padding: '7px 14px',
                      background: selRect ? 'rgba(0,243,255,0.1)' : 'transparent',
                      border: '1px solid rgba(0,243,255,0.5)', borderRadius: '14px', color: selRect ? '#fff' : 'var(--text-muted)',
                      cursor: !selRect || aiBusy ? 'not-allowed' : 'pointer', fontSize: '0.68rem', fontFamily: 'Share Tech Mono', whiteSpace: 'nowrap',
                      opacity: aiBusy ? 0.5 : selRect ? 1 : 0.5,
                    }}>◈ AI detail{selRect ? '' : ' (select first)'}</button>
                </div>
              )}

              {/* what does it depict? — text popup after framing a pass */}
              {aiPromptOpen && (
                <div style={{
                  position: 'fixed', top: '20%', left: '50%', transform: 'translateX(-50%)',
                  zIndex: 200, width: 'min(90%, 460px)',
                  background: 'rgba(8,12,20,0.98)', border: '1px solid var(--neon-pink)',
                  borderRadius: '10px', padding: '18px', boxShadow: '0 12px 60px rgba(0,0,0,0.7)'
                }}>
                  <div style={{ fontFamily: 'Orbitron', fontSize: '0.7rem', color: 'var(--neon-pink)', marginBottom: '10px', letterSpacing: '1px' }}>
                    {aiPromptOpen === 'paint' ? 'PAINT THE SCENE' : aiPromptOpen === 'outpaint' ? 'EXTEND THE SCENE' : 'WHAT DEPICTS THIS DETAIL?'}
                  </div>
                  {aiPromptOpen === 'paint' && (
                    <div style={{ display: 'flex', gap: '6px', marginBottom: '10px', alignItems: 'center' }}>
                      {([['turbo', '◈ SD1.5 (edge, always fits)'], ['zimage_gguf', '⚡ Z-Turbo (4 steps — needs free card)']] as const).map(([id, label]) => (
                        <button key={id} onClick={() => setAiEngine(id)} style={{
                          padding: '5px 10px', borderRadius: '12px', cursor: 'pointer', fontSize: '0.65rem', fontFamily: 'Share Tech Mono',
                          background: aiEngine === id ? 'rgba(160,90,255,0.25)' : 'transparent',
                          border: '1px solid ' + (aiEngine === id ? '#a05aff' : 'var(--border)'), color: '#fff',
                        }}>{label}</button>
                      ))}
                    </div>
                  )}
                  <textarea
                    autoFocus
                    rows={2}
                    value={aiText}
                    onChange={e => setAiText(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); runAI(aiPromptOpen); } }}
                    placeholder={aiPromptOpen === 'outpaint'
                      ? 'a queen in a ballroom, candlelight continues…'
                      : aiPromptOpen === 'paint'
                      ? 'a greenhouse at dawn, glass panes breathing gold…'
                      : 'a detailed toenail, painterly like an oil portrait…'}
                    style={{
                      width: '100%', background: 'rgba(0,0,0,0.5)', border: '1px solid var(--border)',
                      color: '#fff', padding: '10px', borderRadius: '4px', fontSize: '0.85rem', outline: 'none', resize: 'vertical'
                    }}
                  />
                  <div style={{ display: 'flex', gap: '8px', marginTop: '10px', justifyContent: 'flex-end' }}>
                    <button onClick={() => setAiPromptOpen(null)} style={{
                      padding: '7px 14px', background: 'transparent', border: '1px solid var(--border)',
                      color: 'var(--text-muted)', borderRadius: '4px', cursor: 'pointer', fontFamily: 'Share Tech Mono', fontSize: '0.7rem'
                    }}>cancel</button>
                    <button onClick={() => runAI(aiPromptOpen)} disabled={aiBusy} style={{
                      padding: '7px 16px', background: 'rgba(255,0,127,0.2)', border: '1px solid var(--neon-pink)',
                      color: '#fff', borderRadius: '4px', cursor: aiBusy ? 'wait' : 'pointer', fontFamily: 'Share Tech Mono', fontSize: '0.7rem'
                    }}>{aiBusy ? '…' : 'paint it'}</button>
                  </div>
                </div>
              )}

              {/* status footer: live pixel info */}
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px', color: 'var(--text-muted)', fontFamily: 'Share Tech Mono', fontSize: '0.6rem' }}>
                <span>{fmt(resizeW)} × {fmt(resizeH)}</span>
                {selRect && <span>sel: {fmt(selRect.w)} × {fmt(selRect.h)} @ {Math.round(selRect.x)},{Math.round(selRect.y)}</span>}
                <span>zoom {Math.round(deskZoom * 100)}% · desk: {rulerLabel()}</span>
              </div>
            </div>
          </div>
          </div>

            {/* ── Dial Matrix column (right, beside the desk) ──
                toggled by the ◉ Dials button → frees the whole desk
                width when you want room to work */}
            {dialMenu && (
            <div style={{
              width: '340px', minWidth: '300px', borderLeft: '1px solid var(--border)',
              padding: '14px', overflowY: 'auto', background: 'rgba(0,0,0,0.15)',
              display: 'flex', flexDirection: 'column', gap: '14px'
            }}>
              {/* the plasma core — transparent ball, luminous gas */}
              <div
                onPointerDown={() => setCoreTouched(true)}
                onPointerUp={() => setCoreTouched(false)}
                onPointerLeave={() => setCoreTouched(false)}
                style={{ display: 'flex', alignItems: 'center', gap: '12px', userSelect: 'none', touchAction: 'none' }}
              >
                <div style={{
                  width: 44, height: 44, borderRadius: '50%', position: 'relative',
                  background: 'radial-gradient(circle at 50% 50%, transparent 30%, rgba(255,255,255,0.05) 75%, rgba(255,255,255,0.12) 92%, transparent 100%)',
                  border: '1px solid rgba(255,255,255,0.15)',
                  overflow: 'hidden', cursor: 'pointer', flexShrink: 0,
                }}>
                  {/* electric corona: idle = arms radiating; touched = converging to finger */}
                  <i style={{
                    position: 'absolute', inset: 2, borderRadius: '50%',
                    background: coreTouched
                      ? `radial-gradient(circle at ${50 + (corePulse % 2 ? 8 : -8)}% ${50 + (corePulse % 3 ? 6 : -6)}%, ${CORE_COLOR} 12%, transparent 34%)`
                      : `radial-gradient(circle at 50% 50%, ${CORE_COLOR}${CORE_HOT ? 'f0' : '70'} 8%, ${CORE_COLOR}34 26%, transparent 62%)`,
                    filter: `blur(${CORE_HOT ? 0.5 : 1.5}px)`,
                    opacity: coreTouched ? 1 : CORE_HOT ? (corePulse % 2 ? 0.9 : 1) : 0.75,
                    transition: 'background 90ms linear',
                  }} />
                  {/* corona arms / tentacles — idle only */}
                  {!coreTouched && (
                    <i style={{
                      position: 'absolute', inset: -6, borderRadius: '50%',
                      background: `conic-gradient(from ${corePulse * 3}deg, ${CORE_COLOR}25 0 6deg, transparent 6deg 34deg, ${CORE_COLOR}18 34deg 38deg, transparent 38deg 90deg, ${CORE_COLOR}25 90deg 94deg, transparent 94deg 150deg, ${CORE_COLOR}18 150deg 156deg, transparent 156deg 240deg, ${CORE_COLOR}25 240deg 245deg, transparent 245deg 360deg)`,
                      filter: 'blur(2.5px)', opacity: 0.85,
                      transition: 'background 120ms linear',
                    }} />
                  )}
                  {/* lightning flash rim at optimal */}
                  {CORE_HOT && (
                    <i style={{
                      position: 'absolute', inset: 0, borderRadius: '50%',
                      border: `2px solid ${CORE_COLOR}`,
                      boxShadow: `0 0 18px ${CORE_COLOR}, inset 0 0 12px ${CORE_COLOR}88`,
                      opacity: corePulse % 2 ? 0.65 : 1,
                    }} />
                  )}
                </div>
                <div style={{
                  fontFamily: 'Orbitron', fontSize: '0.62rem', letterSpacing: '2px',
                  color: CORE_COLOR, lineHeight: 1.5,
                }}>
                  {CORE_HOT ? '⚡ GAS ILLUMINATED — RELEASE NOW'
                    : ballState === 'ok' ? 'gas stirring — roll toward the band'
                    : 'corona idle — dial ensemble out of band'}
                </div>
              </div>

              {/* composed optimal prompt — updates live in the background */}
              <div>
                <div style={{ fontFamily: 'Orbitron', fontSize: '0.55rem', color: 'var(--text-muted)', letterSpacing: '2px', marginBottom: '6px' }}>
                  COMPOSED PROMPT (BACKGROUND)
                </div>
                <div style={{
                  fontFamily: 'Share Tech Mono', fontSize: '0.68rem', color: '#c9f0ae',
                  background: 'rgba(9,13,6,.8)', border: '1px solid rgba(120,220,130,.2)',
                  borderRadius: '6px', padding: '8px 10px', lineHeight: 1.5, maxHeight: 96, overflowY: 'auto'
                }}>
                  {composeImagePrompt()}
                </div>
              </div>

              {/* dial matrix — same rows as the ignition console LCD */}
              <div style={{
                background: 'linear-gradient(180deg, rgba(24,30,16,.85), rgba(13,16,8,.88))',
                border: '1px solid rgba(255,200,90,.26)', borderRadius: '8px', overflow: 'hidden'
              }}>
                <div style={{ padding: '4px 12px', fontSize: '0.6rem', letterSpacing: '2px',
                  color: '#ffd766', fontFamily: 'Orbitron', fontWeight: 700,
                  background: 'linear-gradient(180deg, #4d4636, #2e2918 60%, #221d10)',
                  borderBottom: '2px solid rgba(255,200,90,.35)' }}>
                  IMAGE DIAL MATRIX
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.72rem' }}>
                  <tbody>
                    {TRAITS.map((t) => {
                      
                      return (
                        <tr key={t.id}
                            onClick={() => { tb.setArmedId(t.id); setImageDialId(t.id); }}
                            title={t.key ? `${t.key} — sweep the ball to turn` : 'local — click to arm'}
                            style={{ cursor: 'pointer' }}>
                          <td style={{
                            padding: '3px 6px', borderBottom: '1px dashed rgba(140,255,150,.12)',
                            color: tb.armed.id === t.id ? CORE_COLOR : '#8f9a6a',
                            width: '38%', letterSpacing: 1,
                            textShadow: tb.armed.id === t.id ? `0 0 8px ${CORE_COLOR}66` : undefined,
                          }}>{tb.armed.id === t.id && '◈ '}{t.label}</td>
                          <td style={{
                            padding: '3px 6px', borderBottom: '1px dashed rgba(140,255,150,.12)',
                            color: '#c9f0ae', textAlign: 'right'
                          }}>
                            {tb.displayVal(t)}
                            {t.id === imageDialId && (
                              <span style={{ marginLeft: 8, display: 'inline-flex', gap: 4 }}>
                                <button onClick={(e) => { e.stopPropagation(); turnImageDial(-1); }}
                                  style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', borderRadius: 3, cursor: 'pointer', padding: '0 5px', fontSize: '0.6rem' }}>−</button>
                                <button onClick={(e) => { e.stopPropagation(); turnImageDial(1); }}
                                  style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', borderRadius: 3, cursor: 'pointer', padding: '0 5px', fontSize: '0.6rem' }}>+</button>
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <div style={{ padding: '5px 10px', fontFamily: 'Share Tech Mono', fontSize: '0.6rem', color: '#8a94b8' }}>
                  click a row to arm · roll the ball (anywhere) to turn · −/+ nudge
                </div>
              </div>

              {/* guidance: dial-zone warnings */}
              <div style={{
                fontFamily: 'Share Tech Mono', fontSize: '0.62rem', color: 'var(--text-muted)',
                lineHeight: 1.6, background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.06)',
                borderRadius: '6px', padding: '8px 10px'
              }}>
                {ballState === 'warn' && +(dials.compress || 0) >= 4 && + (dials.ctx || 8000) < 16000 && (
                  <span style={{ color: '#ff9a6a' }}>⚠ compression {dials.compress} with {dials.ctx} context — raise CTX or ease COMPRESS for a coherent result.</span>
                )}
                {ballState !== 'warn' && (
                  <span>dials cooperate in the band — the light pulses while acceptable and flickers fast when the composition predicts the optimal envelope.</span>
                )}
              </div>
            </div>
            )}
          </div>
        </div>
      )}

      {/* long-press spawn-menu — Lead / Rinse */}
      {pressMenu && (() => {
        const list = scope === 'community' ? community : gallery;
        const item = list.find(i => i.id === pressMenu.id);
        if (!item) return null;
        return (
          <div style={{
            position: 'fixed', left: Math.min(pressMenu.x, window.innerWidth - 190), top: Math.min(pressMenu.y, window.innerHeight - 120),
            zIndex: 500, width: 180,
            background: 'rgba(8,12,20,0.98)', border: '1px solid var(--neon-blue)', borderRadius: '8px',
            boxShadow: '0 10px 50px rgba(0,0,0,0.6)', padding: '4px', display: 'flex', flexDirection: 'column'
          }} onPointerDown={e => e.stopPropagation()}>
            <button onClick={() => leadImage(item)} style={{
              padding: '9px 12px', background: 'transparent', border: 'none', borderBottom: '1px solid rgba(255,255,255,0.06)',
              color: 'var(--neon-pink)', textAlign: 'left', cursor: 'pointer', fontSize: '0.75rem', fontFamily: 'Share Tech Mono'
            }}>♥ Lead</button>
            <button onClick={() => rinseImage(item)} style={{
              padding: '9px 12px', background: 'transparent', border: 'none',
              color: '#ff6a5d', textAlign: 'left', cursor: 'pointer', fontSize: '0.75rem', fontFamily: 'Share Tech Mono'
            }}>✕ Rinse</button>
          </div>
        );
      })()}

      {/* typewriter tease — "Look what I did…" blooms, fades after 5s */}
      {typewriter && (
        <div style={{
          position: 'fixed', bottom: '34px', left: '50%', transform: 'translateX(-50%)',
          zIndex: 400, pointerEvents: 'none',
          fontFamily: "'Share Tech Mono', monospace", fontSize: '0.95rem',
          color: '#eaffd0', textShadow: '0 0 18px rgba(90,255,140,0.55)',
          background: 'rgba(9,13,6,0.82)', border: '1px solid rgba(120,220,130,0.3)',
          borderRadius: '10px', padding: '12px 22px',
        }}>
          {typewriter.text.slice(0, typewriter.shown)}
          <span style={{ opacity: (typewriter.shown % 2) ? 0 : 1 }}>▌</span>
        </div>
      )}
    </div>
  );
};