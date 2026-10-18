import React, { useCallback, useEffect, useRef, useState } from 'react';
import './AudioFxTab.css';
import {
  fetchAudioFxState,
  applyAudioFxPreset,
  setAudioFxBypass,
  fmtDb,
  fmtPct,
  fmtSemi,
  fmtHz,
  type AudioFxState,
} from '../../services/audioFx';

// ── Audio FX (PipeWire EQ + mic FX) ──────────────────────────────────────────
// The first cut is deliberately not a DAW: it shows what the audio-variator-eq
// engine currently holds (output lane = EQ bands + pitch, input lane = the six
// mic FX knobs), lets a scene preset be applied, and carries an explicit master
// bypass. Colour never decorates here — every colour is a FUI role bound in
// AudioFxTab.css, and each role is used for its state (see the header comment
// in that file). The backend is frequently DOWN; the offline state is a first
// class state, not an error path.

type LoadStatus = 'loading' | 'ready' | 'offline';

/** EQ bands — the three output-lane gains the PipeWire EQ filter owns. */
const EQ_BANDS = [
  { key: 'bass',   label: 'BASS',   max: 12 },
  { key: 'mid',    label: 'MID',    max: 12 },
  { key: 'treble', label: 'TREBLE', max: 12 },
] as const;

/** Mic FX lane — input-lane knobs, all 0–100 % (set-mic-fx). */
const MIC_KNOBS = [
  { key: 'noise',    label: 'noise' },
  { key: 'clarity',  label: 'clarity' },
  { key: 'voxpress', label: 'voxpress' },
  { key: 'drive',    label: 'drive' },
  { key: 'echo',     label: 'echo' },
  { key: 'voxrev',   label: 'voxrev' },
] as const;

const POLL_MS = 15000;

export const AudioFxTab: React.FC = () => {
  const [status, setStatus] = useState<LoadStatus>('loading');
  const [detail, setDetail] = useState<string | null>(null);
  const [state, setState] = useState<AudioFxState | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [applied, setApplied] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [failedKey, setFailedKey] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: 'ok' | 'crit'; text: string } | null>(null);
  const alive = useRef(true);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setStatus('loading');
    try {
      const res = await fetchAudioFxState();
      if (!alive.current) return;
      if (res.ok) {
        setState(res);
        setStatus('ready');
        setDetail(null);
      } else {
        setStatus('offline');
        setDetail(res.error);
      }
    } catch (e) {
      // safeFetch is built not to throw; if it ever does, the surface still
      // degrades to the deliberate offline state instead of blanking.
      if (!alive.current) return;
      setStatus('offline');
      setDetail(String((e as Error)?.message || e).slice(0, 160));
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    load();
    const t = window.setInterval(() => load(true), POLL_MS);
    return () => { alive.current = false; window.clearInterval(t); };
  }, [load]);

  const output = state?.output ?? null;
  const input = state?.input ?? null;
  const offline = status === 'offline' || !output || !input;

  const onToggleBypass = async () => {
    if (!output || busyKey) return;
    setBusyKey('bypass');
    setFailedKey(null);
    setNotice(null);
    try {
      const res = await setAudioFxBypass(!output.bypass);
      if (!alive.current) return;
      if (res.ok) {
        // Only the engine's own answer updates the readout — never optimism.
        setState(s => (s ? { ...s, output: res.output } : s));
        setNotice({ tone: 'ok', text: res.bypass ? 'Bypass ON — the graph is passing dry.' : 'Bypass OFF — the FX graph is live.' });
      } else {
        setFailedKey('bypass');
        setNotice({ tone: 'crit', text: `bypass refused: ${res.error}` });
      }
    } catch (e) {
      if (!alive.current) return;
      setFailedKey('bypass');
      setNotice({ tone: 'crit', text: `bypass failed: ${String((e as Error)?.message || e).slice(0, 120)}` });
    } finally {
      if (alive.current) setBusyKey(null);
    }
  };

  const onApplyPreset = async (name: string) => {
    if (busyKey) return;
    setSelected(name);
    setBusyKey(name);
    setFailedKey(null);
    setNotice(null);
    try {
      const res = await applyAudioFxPreset(name);
      if (!alive.current) return;
      if (res.ok) {
        setState(s => (s ? { ...s, output: res.output } : s));
        setApplied(name);
        setNotice({ tone: 'ok', text: `applied "${res.applied}" — the engine confirmed the new state.` });
      } else {
        setApplied(null);
        setFailedKey(name);
        setNotice({ tone: 'crit', text: `"${name}" was not applied: ${res.error}` });
      }
    } catch (e) {
      if (!alive.current) return;
      setApplied(null);
      setFailedKey(name);
      setNotice({ tone: 'crit', text: `"${name}" failed: ${String((e as Error)?.message || e).slice(0, 120)}` });
    } finally {
      if (alive.current) setBusyKey(null);
    }
  };

  const statusChip = () => {
    if (status === 'loading') return <span className="afx-chip afx-chip--busy">◐ PROBING</span>;
    if (status === 'ready') return <span className="afx-chip afx-chip--ok">● LIVE</span>;
    return <span className="afx-chip afx-chip--warn">⚠ OFFLINE</span>;
  };

  const bypassClass = failedKey === 'bypass'
    ? 'afx-btn afx-btn--crit'
    : busyKey === 'bypass'
      ? 'afx-btn afx-btn--busy'
      : 'afx-btn afx-btn--wide';

  return (
    <div className="afx-root">
      <div className="afx-band" />
      <div className="afx-head">
        <h2 className="afx-title">AUDIO FX — PIPEWIRE</h2>
        {statusChip()}
      </div>
      <p className="afx-sub">
        Read-out of the audio-variator-eq engine (PipeWire EQ, studio pitch and the mic FX chain).
        Presets apply to the live graph; the bypass is the master FX switch. Values are shown as the
        engine reports them — this surface never guesses.
      </p>

      {status === 'offline' && (
        <div className="afx-offline">
          <span>⚠</span>
          <div className="afx-offline-body">
            <div className="afx-offline-head">OFFLINE — AUDIO FX BACKEND UNREACHABLE</div>
            <div>
              The audio FX API did not answer, so nothing on this page is live: the lanes below are
              blank, controls are disabled and no preset has been applied. Presets stay untouched —
              your PipeWire graph is exactly as the engine last left it.
            </div>
            {detail && <div className="afx-offline-detail">backend said: {detail}</div>}
          </div>
          <button className="afx-btn" onClick={() => load()} disabled={status === 'loading'}>
            {status === 'loading' ? 'RETRYING…' : 'RETRY'}
          </button>
        </div>
      )}

      <div className="afx-grid">
        {/* OUTPUT LANE — EQ bands, pitch, bypass */}
        <section className="afx-panel">
          <div className="afx-panel-head">
            <span>OUTPUT LANE · EQ</span>
            <button
              className={bypassClass}
              onClick={onToggleBypass}
              disabled={offline || !!busyKey}
              title={offline ? 'backend offline' : 'master FX bypass'}
            >
              {busyKey === 'bypass' ? '◐ …' : failedKey === 'bypass' ? '✖ BYPASS FAILED' : output?.bypass ? 'BYPASS ON' : 'BYPASS OFF'}
            </button>
          </div>
          <div className="afx-panel-body">
            {offline ? (
              <div className="afx-empty">no readout — backend offline</div>
            ) : (
              <>
                {EQ_BANDS.map(band => {
                  const v = output[band.key];
                  const moved = Math.abs(v) > 0.01;
                  return (
                    <div className="afx-row" key={band.key}>
                      <span className="afx-row-label">{band.label}</span>
                      <span className="afx-meter-track">
                        <span className="afx-meter">
                          <span
                            className={`afx-meter-fill${moved ? ' afx-meter-fill--live' : ''}`}
                            style={{ width: `${Math.min(100, (Math.abs(v) / band.max) * 100)}%` }}
                          />
                        </span>
                        <span className={`afx-row-value${moved ? '' : ' afx-row-value--idle'}`}>
                          {fmtDb(v)}
                        </span>
                      </span>
                    </div>
                  );
                })}
                <div className="afx-row">
                  <span className="afx-row-label">CENTRE FREQ</span>
                  <span className="afx-row-value">
                    {fmtHz(output.bass_freq)} / {fmtHz(output.mid_freq)} / {fmtHz(output.treble_freq)}
                  </span>
                </div>
                <div className="afx-row">
                  <span className="afx-row-label">PITCH</span>
                  <span className={`afx-row-value${output.pitch === 0 ? ' afx-row-value--idle' : ''}`}>
                    {fmtSemi(output.pitch)}
                    <span className="afx-row-note">warp {Math.round(output.warp)} ct</span>
                  </span>
                </div>
                <div className="afx-row">
                  <span className="afx-row-label">BYPASS</span>
                  <span className={`afx-chip ${output.bypass ? 'afx-chip--idle' : 'afx-chip--ok'}`}>
                    {output.bypass ? '○ BYPASSED (dry)' : '● FX ENGAGED'}
                  </span>
                </div>
              </>
            )}
          </div>
        </section>

        {/* INPUT LANE — mic FX knobs */}
        <section className="afx-panel">
          <div className="afx-panel-head">
            <span>INPUT LANE · MIC FX</span>
            <span className="afx-preset-cat">{input?.aux ? 'AUX ON' : 'AUX OFF'}</span>
          </div>
          <div className="afx-panel-body">
            {offline ? (
              <div className="afx-empty">no readout — backend offline</div>
            ) : (
              <div className="afx-knobs">
                {MIC_KNOBS.map(knob => {
                  const v = input[knob.key];
                  return (
                    <div className="afx-knob" key={knob.key}>
                      <div className="afx-knob-label">{knob.label}</div>
                      <div className={`afx-knob-value${v === 0 ? ' afx-knob-value--idle' : ''}`}>
                        {fmtPct(v)}
                      </div>
                      <span className="afx-meter">
                        <span
                          className={`afx-meter-fill${v > 0 ? ' afx-meter-fill--live' : ''}`}
                          style={{ width: `${Math.min(100, Math.max(0, v))}%` }}
                        />
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </section>

        {/* PRESETS */}
        <section className="afx-panel afx-panel--preset">
          <div className="afx-panel-head">
            <span>SCENE PRESETS</span>
            <button className="afx-btn" onClick={() => load(true)} disabled={offline || status === 'loading'}>
              REFRESH
            </button>
          </div>
          <div className="afx-panel-body">
            {offline ? (
              <div className="afx-empty">preset list unavailable — backend offline</div>
            ) : state!.presets.length === 0 ? (
              <div className="afx-empty">the engine reported no presets</div>
            ) : (
              <div className="afx-preset-list">
                {state!.presets.map(p => {
                  const isBusy = busyKey === p.name;
                  const isFailed = failedKey === p.name;
                  const isApplied = applied === p.name;
                  const rowClass = [
                    'afx-preset',
                    selected === p.name ? 'afx-preset--selected' : '',
                    isApplied ? 'afx-preset--applied' : '',
                    isFailed ? 'afx-preset--failed' : '',
                  ].filter(Boolean).join(' ');
                  return (
                    <div className={rowClass} key={p.name}>
                      <span className="afx-preset-mark">
                        {isBusy ? '◐' : isFailed ? '✖' : isApplied ? '●' : '○'}
                      </span>
                      <span className="afx-preset-name">{p.name}</span>
                      {p.cat && <span className="afx-preset-cat">{p.cat}</span>}
                      <button
                        className={`afx-btn${isBusy ? ' afx-btn--busy' : ''}${isFailed ? ' afx-btn--crit' : ''}`}
                        onClick={() => onApplyPreset(p.name)}
                        disabled={!!busyKey}
                      >
                        {isBusy ? 'APPLYING' : isFailed ? 'RETRY' : 'APPLY'}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
            {notice && (
              <div className={`afx-row-note afx-chip ${notice.tone === 'ok' ? 'afx-chip--ok' : 'afx-chip--crit'}`}>
                {notice.tone === 'ok' ? '●' : '✖'} {notice.text}
              </div>
            )}
          </div>
        </section>
      </div>

      <div className="afx-foot">
        Presets are applied by the engine itself — this page only reports what came back.
        Offline means unreachable, not broken: the PipeWire graph is untouched until a preset is
        applied from here.
      </div>
    </div>
  );
};

export default AudioFxTab;