import { useEffect, useState } from 'react';

// ── FUI Composer ────────────────────────────────────────────────────────────
// The -fui theme family editor, on the canonical grammar:
//   • Colors = states/identity, readability-ordered (canvas → ink → accent
//     → alarm); under-band untouched, over-band enforced (3/7 contract).
//   • Finish = material/gloss/pattern/cutout/fade — structure serves
//     readability; slack is buffer.
// Preview renders in a SCOPED container (its own CSS vars, never :root)
// so dialing never poisons the live app until Commit.

export interface FuiDraft {
  variant: string;
  fv_accent: string;
  fv_accent_2: string;
  fv_ok: string;
  fv_warn: string;
  fv_danger: string;
  material: 'matte' | 'satin' | 'neon' | 'satin-light';
  gloss: number;          // 0.00–0.30
  pattern: 'none' | 'stripes';
  pattern_strength: number; // 0.00–0.15
  shape_radius: number;   // px
  cutout: number;         // 0–1 → inset depth
  fade: number;           // px
  light_angle: number;    // deg
  ornamentation: 'minimal' | 'cyber-lines' | 'baroque-tech' | 'glowing-edges';
}

const VARIANTS: Record<string, Partial<FuiDraft>> = {
  signum:   { material: 'satin',       gloss: 0.10, pattern: 'stripes', pattern_strength: 0.06, shape_radius: 6,  cutout: 0.45, fade: 24, ornamentation: 'minimal' },
  whisper:  { material: 'matte',       gloss: 0.03, pattern: 'none',    pattern_strength: 0.00, shape_radius: 4,  cutout: 0.25, fade: 12, ornamentation: 'minimal' },
  screamer: { material: 'neon',        gloss: 0.25, pattern: 'stripes', pattern_strength: 0.12, shape_radius: 10, cutout: 0.70, fade: 32, ornamentation: 'cyber-lines' },
  daylight: { material: 'satin-light', gloss: 0.12, pattern: 'none',    pattern_strength: 0.00, shape_radius: 8,  cutout: 0.14, fade: 16, ornamentation: 'minimal' },
};

const DEFAULT_COLORS: Record<string, { accent: string; accent2: string; ok: string; warn: string; danger: string }> = {
  signum: { accent: '#00DCFF', accent2: '#FF9E1F', ok: '#00E664', warn: '#FF9E1F', danger: '#FF3232' },
  whisper: { accent: '#73A8C4', accent2: '#A38A8A', ok: '#3FA05E', warn: '#C4A26E', danger: '#C45C5C' },
  screamer: { accent: '#00E7FF', accent2: '#FF7600', ok: '#00FF70', warn: '#FF7600', danger: '#FF2020' },
  daylight: { accent: '#009FBE', accent2: '#B87000', ok: '#00A647', warn: '#B87000', danger: '#BE2424' },
};

const SLIDER_STYLE: React.CSSProperties = {
  width: '100%', accentColor: 'var(--fv-accent, #00DCFF)', cursor: 'pointer',
};

export default function FuiComposer({ onCommit }: {
  onCommit?: (draft: FuiDraft) => Promise<void>;
}) {
  const [variant, setVariant] = useState('signum');
  const [draft, setDraft] = useState<FuiDraft>({
    variant: 'signum',
    ...DEFAULT_COLORS.signum,
    ...VARIANTS.signum,
  } as FuiDraft);
  const [committing, setCommitting] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const set = <K extends keyof FuiDraft>(k: K, v: FuiDraft[K]) =>
    setDraft(d => ({ ...d, [k]: v }));

  // variant presets swap colors + finish; dials stay user-modifiable after
  const pickVariant = (v: string) => {
    setVariant(v);
    setDraft(d => ({
      ...d,
      variant: v,
      ...DEFAULT_COLORS[v],
      ...VARIANTS[v],
    }));
  };

  // scoped preview vars — NEVER document :root
  const pv: Record<string, string> = {
    '--pv-canvas': variant === 'daylight' ? '#ECEFF3' : '#1E1E1E',
    '--pv-panel': variant === 'daylight' ? '#FFFFFF' : '#2D2D2D',
    '--pv-fg': variant === 'daylight' ? '#17202A' : '#E0E0E0',
    '--pv-fg-dim': variant === 'daylight' ? '#5A6B7B' : '#888888',
    '--pv-accent': draft.fv_accent,
    '--pv-fg-warn': draft.fv_warn,
    '--pv-ok': draft.fv_ok,
    '--pv-crit': draft.fv_danger,
    '--pv-accent2': draft.fv_accent_2,
    '--pv-shape': `${draft.shape_radius}px`,
    '--pv-cutout': `inset 0 2px 6px rgba(0,0,0,${draft.cutout})`,
    '--pv-pattern': draft.pattern === 'stripes'
      ? `repeating-linear-gradient(135deg, rgba(127,127,127,${draft.pattern_strength}) 0 1px, transparent 1px 7px)`
      : 'none',
    '--pv-highlight': `inset 0 1px 0 rgba(255,255,255,${Math.min(0.3, draft.gloss).toFixed(3)})`,
    '--pv-fade': `${draft.fade}px`,
  };

  const commit = async () => {
    if (!onCommit) return;
    setCommitting(true);
    setNote(null);
    try {
      await onCommit(draft);
      setNote('✅ committed live + persisted');
    } catch (e: any) {
      setNote(`❌ ${e.message}`);
    } finally {
      setCommitting(false);
    }
  };

  return (
    <div style={panel}>
      <div style={head}>
        <span style={{ fontWeight: 700 }}>🎨 FUI Composer</span>
        <select value={variant} onChange={e => pickVariant(e.target.value)} style={select}>
          <option value="signum">Signum — dark, balanced (authoritative)</option>
          <option value="whisper">Whisper — dark, discreet</option>
          <option value="screamer">Screamer — dark, loud</option>
          <option value="daylight">Daylight — light canvas</option>
        </select>
      </div>

      {/* Live preview — scoped, table-shape graphic language */}
      <div style={{ ...previewBox, ...pv } as React.CSSProperties}>
        <div style={{ background: 'var(--pv-panel)', border: '1px solid color-mix(in srgb, var(--pv-accent) 25%, transparent)', borderRadius: 'var(--pv-shape)', padding: 10, backgroundImage: 'var(--pv-pattern)', boxShadow: 'var(--pv-highlight)' }}>
          <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, background: 'var(--pv-panel)', border: '1px solid color-mix(in srgb, var(--pv-accent) 25%, transparent)', borderRadius: 'var(--pv-shape)', overflow: 'hidden' }}>
            <thead>
              <tr>
                {['Service', 'State'] .map(h => (
                  <th key={h} style={{ background: 'color-mix(in srgb, var(--pv-accent) 14%, transparent)', color: 'var(--pv-fg)', borderBottom: '1px solid var(--pv-accent)', textAlign: 'left', padding: '6px 10px' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[['ok', '● up'], ['busy', '◐ loading'], ['crit', '✖ down']].map(([st, w], i) => (
                <tr key={st} style={i % 2 ? { background: 'color-mix(in srgb, var(--pv-fg-dim) 8%, transparent)' } : undefined}>
                  <td style={{ color: 'var(--pv-fg)', padding: '5px 10px' }}>{st}</td>
                  <td style={{ color: st === 'ok' ? 'var(--pv-ok)' : st === 'busy' ? 'var(--pv-fg-warn)' : 'var(--pv-crit)', padding: '5px 10px' }}>{w}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ ...cutoutBox, marginTop: 8, boxShadow: 'var(--pv-cutout)', borderRadius: 'var(--pv-shape)' }}>
            cutout well
          </div>
        </div>
      </div>

      {/* Dials */}
      <div style={dialGrid}>
        <ColorDial label="accent" value={draft.fv_accent} onChange={v => set('fv_accent', v)} />
        <ColorDial label="accent-2" value={draft.fv_accent_2} onChange={v => set('fv_accent_2', v)} />
        <ColorDial label="ok" value={draft.fv_ok} onChange={v => set('fv_ok', v)} />
        <ColorDial label="warn" value={draft.fv_warn} onChange={v => set('fv_warn', v)} />
        <ColorDial label="danger" value={draft.fv_danger} onChange={v => set('fv_danger', v)} />
        <Dial label={`material: ${draft.material}`}>
          <select
            value={draft.material}
            onChange={e => { const v = e.target.value as FuiDraft['material']; set('material', v); }}
            style={selectSmall}
          >
            <option value="matte">matte</option>
            <option value="satin">satin</option>
            <option value="neon">neon</option>
            <option value="satin-light">satin-light</option>
          </select>
        </Dial>
        <Dial label={`gloss: ${(draft.gloss * 100).toFixed(0)}%`} >
          <input type="range" min={0} max={0.3} step={0.01} value={draft.gloss}
                 onChange={e => set('gloss', parseFloat(e.target.value))} style={SLIDER_STYLE} />
        </Dial>
        <Dial label={`pattern: ${draft.pattern}`}>
          <select value={draft.pattern}
                  onChange={e => set('pattern', e.target.value as FuiDraft['pattern'])} style={selectSmall}>
            <option value="none">none</option>
            <option value="stripes">stripes (lollipop)</option>
          </select>
        </Dial>
        <Dial label={`pattern strength: ${(draft.pattern_strength * 100).toFixed(0)}%`}>
          <input type="range" min={0} max={0.15} step={0.01} value={draft.pattern_strength}
                 disabled={draft.pattern !== 'stripes'}
                 onChange={e => set('pattern_strength', parseFloat(e.target.value))} style={SLIDER_STYLE} />
        </Dial>
        <Dial label={`corner shape: ${draft.shape_radius}px`}>
          <input type="range" min={2} max={24} step={1} value={draft.shape_radius}
                 onChange={e => set('shape_radius', parseInt(e.target.value, 10))} style={SLIDER_STYLE} />
        </Dial>
        <Dial label={`cutout depth: ${draft.cutout.toFixed(2)}`}>
          <input type="range" min={0} max={1} step={0.05} value={draft.cutout}
                 onChange={e => set('cutout', parseFloat(e.target.value))} style={SLIDER_STYLE} />
        </Dial>
        <Dial label={`edge fade: ${draft.fade}px`}>
          <input type="range" min={0} max={48} step={2} value={draft.fade}
                 onChange={e => set('fade', parseInt(e.target.value, 10))} style={SLIDER_STYLE} />
        </Dial>
        <Dial label={`light angle: ${draft.light_angle}°`}>
          <input type="range" min={0} max={360} step={15} value={draft.light_angle}
                 onChange={e => set('light_angle', parseInt(e.target.value, 10))} style={SLIDER_STYLE} />
        </Dial>
        <Dial label={`ornamentation: ${draft.ornamentation}`}>
          <select value={draft.ornamentation}
                  onChange={e => set('ornamentation', e.target.value as FuiDraft['ornamentation'])} style={selectSmall}>
            <option value="minimal">minimal</option>
            <option value="cyber-lines">cyber-lines</option>
            <option value="baroque-tech">baroque-tech</option>
            <option value="glowing-edges">glowing-edges</option>
          </select>
        </Dial>
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
        <button onClick={commit} disabled={committing} style={commitBtn}>{committing ? '⏳ …' : '⬆ Commit live'}</button>
      </div>
      {note && <div style={{ marginTop: 6, fontSize: '0.8rem', opacity: 0.8 }}>{note}</div>}
    </div>
  );
}

// ── atoms ──────────────────────────────────────────────────────────────────
const panel: React.CSSProperties = {
  background: 'rgba(0,0,0,0.35)', border: '1px solid var(--fv-border, rgba(255,255,255,0.12))',
  borderRadius: 10, padding: 14,
};
const head: React.CSSProperties = { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, gap: 8 };
const select: React.CSSProperties = {
  padding: '8px 12px', background: 'var(--fv-surface, rgba(255,255,255,0.08))',
  color: 'var(--fv-text, #fff)', border: '1px solid var(--fv-border, rgba(255,255,255,0.12))', borderRadius: 8,
};
const selectSmall: React.CSSProperties = {
  width: '100%', padding: '4px 8px', background: 'rgba(0,0,0,0.4)', color: 'var(--fv-text, #fff)',
  border: '1px solid var(--fv-border, rgba(255,255,255,0.12))', borderRadius: 6, fontSize: '0.75rem',
};
const previewBox: React.CSSProperties = {
  padding: 12, borderRadius: 10, margin: '10px 0',
  background: 'linear-gradient(180deg, var(--pv-canvas), var(--pv-panel))',
  border: '1px solid var(--fv-border, rgba(255,255,255,0.12))',
};
const cutoutBox: React.CSSProperties = {
  padding: '8px 10px', fontSize: '0.75rem', color: 'var(--pv-fg-dim)', textAlign: 'center',
  background: 'color-mix(in srgb, var(--pv-canvas) 70%, var(--pv-panel))',
};
const dialGrid: React.CSSProperties = {
  display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 10,
};
const dial: React.CSSProperties = { minWidth: 0 };
const dialLabel: React.CSSProperties = { fontSize: '0.68rem', opacity: 0.7, marginBottom: 4, display: 'block' };
const commitBtn: React.CSSProperties = {
  flex: 1, padding: '10px 16px', fontWeight: 700, borderRadius: 8, border: 'none', cursor: 'pointer',
  background: 'var(--fv-accent, #00DCFF)', color: '#000',
};

function Dial({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={dial}>
      <span style={dialLabel}>{label}</span>
      {children}
    </div>
  );
}

function ColorDial({ label, value, onChange }: {
  label: string; value: string; onChange: (v: string) => void;
}) {
  return (
    <Dial label={`${label}: ${value}`}>
      <input type="color" value={value} onChange={e => onChange(e.target.value)}
             style={{ width: '100%', height: 28, border: 'none', borderRadius: 6, background: 'transparent', cursor: 'pointer' }} />
    </Dial>
  );
}