import React, { useCallback, useEffect, useRef, useState } from 'react';
import { auralAwareness } from '../senses/AuralAwareness';

/**
 * Makes the microphone legible. Every failure mode that used to be invisible —
 * wrong input device, suspended audio context, a level too low to trip VAD —
 * shows up here as a number or a label instead of silence.
 */
export const MicDiagnostics: React.FC = () => {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [chosen, setChosen] = useState('');
  const [active, setActive] = useState('(not capturing)');
  const [level, setLevel] = useState(0);
  const [peak, setPeak] = useState(0);
  const [ctxState, setCtxState] = useState('none');
  const raf = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    setDevices(await auralAwareness.listInputs());
    setActive(auralAwareness.getActiveInputLabel());
    setCtxState(auralAwareness.getContextState());
  }, []);

  useEffect(() => {
    refresh();
    const tick = () => {
      const v = auralAwareness.getInputLevel();
      setLevel(v);
      setPeak((p) => Math.max(p * 0.985, v));
      setCtxState(auralAwareness.getContextState());
      setActive(auralAwareness.getActiveInputLabel());
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    // Labels only populate once a capture has been granted.
    const onDevices = () => { refresh(); };
    navigator.mediaDevices?.addEventListener?.('devicechange', onDevices);
    return () => {
      if (raf.current) cancelAnimationFrame(raf.current);
      navigator.mediaDevices?.removeEventListener?.('devicechange', onDevices);
    };
  }, [refresh]);

  const pct = Math.min(100, Math.round(level * 200));
  const peakPct = Math.min(100, Math.round(peak * 200));

  return (
    <div className="mic-diag" role="group" aria-label="Microphone diagnostics">
      <label className="mic-diag-field">
        <span>input</span>
        <select
          value={chosen}
          onChange={async (e) => {
            setChosen(e.target.value);
            await auralAwareness.selectInput(e.target.value);
            setActive(auralAwareness.getActiveInputLabel());
          }}
        >
          <option value="">system default</option>
          {devices.map((d, i) => (
            <option key={d.deviceId || i} value={d.deviceId}>
              {d.label || `input ${i + 1}`}
            </option>
          ))}
        </select>
      </label>
      <div className="mic-diag-meter" aria-hidden>
        <div className="mic-diag-fill" style={{ width: `${pct}%` }} />
        <div className="mic-diag-peak" style={{ left: `${peakPct}%` }} />
      </div>
      <div className="mic-diag-readout">
        <span>level {(level * 100).toFixed(1)}%</span>
        <span>peak {(peak * 100).toFixed(1)}%</span>
        <span>audio {ctxState}</span>
        <span className="mic-diag-active" title={active}>{active}</span>
      </div>
      {peak < 0.02 && (
        <p className="mic-diag-warn">
          No signal. Either you are speaking into a different mic than the one
          above, or the level is too low to trip voice detection — check the OS
          input meter for the selected device.
        </p>
      )}
    </div>
  );
};

export default MicDiagnostics;
