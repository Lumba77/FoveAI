import { useEffect, useRef, useState } from 'react';

/**
 * useLipsync — amplitude mouth-movement for still-image "talking" frames.
 *
 * Listens to (window event 'foveai_tts_energy') amplitude values published
 * by AuralAwareness playback (WebAudio analyser / mic input) and exposes a
 * 0..1 mouth-open factor + speaking flag. The frame component uses it to
 * bounce the still image (scaleY squash + brightness) — the lipsynced-still
 * mode of the call frames, no VRM needed.
 */
export function useLipsync(): { mouth: number; speaking: boolean } {
  const [mouth, setMouth] = useState(0);
  const [speaking, setSpeaking] = useState(false);
  const decayRef = useRef(0);

  useEffect(() => {
    let raf = 0;
    let lastTs = 0;
    const onEnergy = (e: Event) => {
      const v = (e as CustomEvent).detail?.energy;
      if (typeof v === 'number' && v >= 0 && v <= 1) {
        setMouth((prev) => {
          // attack fast, decay slow — reads as jaw movement
          const next = v > prev ? v : prev * 0.86 + v * 0.14;
          decayRef.current = next;
          return next;
        });
      }
    };
    const tick = (ts: number) => {
      if (lastTs && ts - lastTs > 90 && decayRef.current > 0.01) {
        setMouth((prev) => Math.max(0, prev * 0.9));
      }
      lastTs = ts;
      raf = requestAnimationFrame(tick);
    };
    window.addEventListener('foveai_tts_energy', onEnergy);
    raf = requestAnimationFrame(tick);
    const spkTimer = setInterval(() => {
      setSpeaking(decayRef.current > 0.06);
    }, 200);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('foveai_tts_energy', onEnergy);
      clearInterval(spkTimer);
    };
  }, []);

  return { mouth, speaking };
}
