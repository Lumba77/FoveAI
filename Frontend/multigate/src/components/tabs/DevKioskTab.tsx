import React, { useEffect, useState } from 'react';

// Dev Kiosk — the user-facing creation console (port of the XR Vessel dev kiosk,
// advanced variant). Two forges:
//   APP FORGE   — scaffold a template app, edit with AI assist, compile to a
//                 downloadable binary/zip. Policy-bounded (creative apps only).
//   SOFTLAYER   — JS modules that hot-reload into the XR Vessel sandbox.

const inputStyle: React.CSSProperties = {
  background: '#02050a', color: '#fff', border: '1px solid var(--border)',
  padding: '8px 10px', fontFamily: 'Share Tech Mono', fontSize: '0.8rem',
  borderRadius: '4px', outline: 'none',
};
const btnStyle: React.CSSProperties = {
  padding: '8px 14px', border: 'none', borderRadius: '4px',
  fontFamily: 'Orbitron', fontSize: '0.62rem', cursor: 'pointer', letterSpacing: '1px',
};

// ── SoftLayer templates ─────────────────────────────────────────────────────

const SL_TEMPLATES: Record<string, { label: string; code: (n: string) => string }> = {
  blank: { label: 'Blank module', code: (n) => `// ${n}.js — SoftLayer module
function ${n}_onLoad() { FoveAI.log("${n} loaded"); }
function ${n}_onUpdate(dt) {}
function ${n}_onUnload() {}
` },
  hud_widget: { label: 'HUD widget', code: (n) => `// ${n}.js — HUD corner readout
let t = 0;
function ${n}_onLoad() {
    FoveAI.setHUDLabel('br', '${n.toUpperCase()}');
    FoveAI.setHUDColor('br', 0, 243, 255, 0.9);
}
function ${n}_onUpdate(dt) {
    t += dt;
    if (t >= 1) { t = 0; FoveAI.setHUDValue('br', new Date().toLocaleTimeString()); }
}
` },
  mood: { label: 'Ambient mood', code: (n) => `// ${n}.js — sky + lighting scene
function ${n}_onLoad() {
    FoveAI.sky.setColor(0.02, 0.05, 0.15);
    FoveAI.sky.setHorizon(0.6, 0.2, 0.8);
    FoveAI.lighting.setMood('dusk');
    FoveAI.particles.enable('dust', true);
}
` },
};

const APP_TEMPLATES: Record<string, { label: string; desc: string; icon: string }> = {
  ai_chat:      { icon: '💬', label: 'AI Chat',       desc: 'Chat UI on the local XRLF model' },
  ai_persona:   { icon: '🎭', label: 'AI Persona',    desc: 'Chat with a custom personality' },
  music_app:    { icon: '🎹', label: 'Music Toy',     desc: 'WebAudio synth pads' },
  web_browser:  { icon: '🌐', label: 'Mini Browser',  desc: 'Reader-mode web fetcher' },
  meter_widget: { icon: '📊', label: 'Meter Widget',  desc: 'Live CPU/RAM gauges' },
};

interface KioskApp { owner: string; app: string; files: string[]; artifacts: string[]; }
interface SlModule { name: string; size: number; modified: string; }

export const DevKioskTab: React.FC<{ currentUser?: string }> = ({ currentUser }) => {
  const owner = (currentUser || 'guest').toLowerCase().replace(/[^a-z0-9_]/g, '') || 'guest';
  const [section, setSection] = useState<'apps' | 'softlayer'>('apps');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  // ── App forge state ──
  const [apps, setApps] = useState<KioskApp[]>([]);
  const [newAppName, setNewAppName] = useState('');
  const [appName, setAppName] = useState('');
  const [appFile, setAppFile] = useState('main.py');
  const [appSource, setAppSource] = useState('');
  const [assistPrompt, setAssistPrompt] = useState('');
  const [policy, setPolicy] = useState('');
  const [target, setTarget] = useState('binary');
  const [targets, setTargets] = useState<Record<string, { available: boolean; note: string }>>({});

  // ── SoftLayer state ──
  const [slModules, setSlModules] = useState<SlModule[]>([]);
  const [slName, setSlName] = useState('my_module');
  const [slSource, setSlSource] = useState(SL_TEMPLATES.blank.code('my_module'));
  const [slTemplate, setSlTemplate] = useState('blank');

  const loadApps = () => {
    fetch(`/api/soul/kiosk/apps?owner=${owner}`)
      .then(r => r.json()).then(d => { if (d.apps) setApps(d.apps); }).catch(() => {});
  };
  const loadSlModules = () => {
    fetch('/api/soul/softlayer/modules')
      .then(r => r.json()).then(d => { if (d.modules) setSlModules(d.modules); }).catch(() => {});
  };
  useEffect(() => {
    loadApps(); loadSlModules();
    fetch('/api/soul/kiosk/templates').then(r => r.json())
      .then(d => { if (d.policy) setPolicy(d.policy); }).catch(() => {});
    fetch('/api/soul/kiosk/targets').then(r => r.json())
      .then(d => { if (d.targets) setTargets(d.targets); }).catch(() => {});
  }, []);

  // ── App forge actions ──

  const createApp = (template: string) => {
    const name = newAppName.trim().toLowerCase().replace(/[^a-z0-9_]/g, '');
    if (!name) { setNotice('name the app first'); return; }
    setBusy(true);
    fetch('/api/soul/kiosk/apps', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ owner, app: name, template }),
    }).then(r => r.json()).then(d => {
      if (d.ok) { setAppName(name); setNewAppName(''); openFile(name, 'main.py'); setNotice(`created ${name}`); loadApps(); }
      else setNotice(`error: ${d.detail || 'failed'}`);
    }).catch(e => setNotice(`${e}`)).finally(() => setBusy(false));
  };

  const openFile = (app: string, path: string) => {
    fetch(`/api/soul/kiosk/apps/${owner}/${app}/file?path=${encodeURIComponent(path)}`)
      .then(r => r.json()).then(d => {
        if (d.content !== undefined) { setAppName(app); setAppFile(path); setAppSource(d.content); }
      }).catch(() => {});
  };

  const saveFile = () => {
    if (!appName) return;
    fetch(`/api/soul/kiosk/apps/${owner}/${appName}/file`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: appFile, content: appSource }),
    }).then(r => r.json()).then(d => setNotice(d.ok ? `saved ${appFile}` : `error: ${d.detail}`))
      .catch(e => setNotice(`${e}`));
  };

  const assist = () => {
    const p = assistPrompt.trim();
    if (!p || !appName) return;
    setBusy(true); setNotice('asking Jen…');
    fetch('/api/soul/kiosk/assist', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: p, owner, app: appName, path: appFile, source: appSource }),
    }).then(r => r.json()).then(d => {
      if (d.refused) setNotice(d.message);
      else if (d.source) { setAppSource(d.source); setNotice('AI edit applied — review, then save'); }
      else setNotice(`assist error: ${d.detail || 'no code'}`);
    }).catch(e => setNotice(`${e}`)).finally(() => setBusy(false));
  };

  const build = () => {
    if (!appName) return;
    setBusy(true); setNotice('compiling… (binary builds take a minute)');
    fetch('/api/soul/kiosk/build', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ owner, app: appName, target }),
    }).then(r => r.json()).then(d => {
      const got = [d.binary, d.flatpak, d.zip, d.winexe].filter(Boolean);
      setNotice((got.length ? `built: ${got.join(' + ')}` : 'nothing produced')
        + (d.build_log ? ' — ' + d.build_log.slice(0, 120) : ''));
      loadApps();
    }).catch(e => setNotice(`${e}`)).finally(() => setBusy(false));
  };

  // ── SoftLayer actions ──

  const slSave = () => {
    setBusy(true);
    fetch(`/api/soul/softlayer/modules/${slName}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: slSource }),
    }).then(r => r.json()).then(d => {
      setNotice(d.ok ? 'saved — hot-reloads into the XR Vessel' : `error: ${d.detail}`);
      loadSlModules();
    }).catch(e => setNotice(`${e}`)).finally(() => setBusy(false));
  };

  const slOpen = (n: string) => {
    fetch(`/api/soul/softlayer/modules/${n}`).then(r => r.json())
      .then(d => { if (d.source !== undefined) { setSlName(n); setSlSource(d.source); } }).catch(() => {});
  };

  const currentApp = apps.find(a => a.app === appName);

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
      <div>
        <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 4px 0', fontSize: '0.9rem', color: 'var(--accent-cyan)', letterSpacing: '2px' }}>DEV KIOSK</h4>
        <p style={{ fontSize: '0.72rem', opacity: 0.7, color: '#a0e0ff', margin: 0 }}>
          Build your own apps with Jen's help — pick a template, edit or ask AI, compile to a downloadable binary. Or forge SoftLayer modules that live inside the XR Vessel.
        </p>
      </div>

      {/* Section switch */}
      <div style={{ display: 'flex', gap: '4px' }}>
        {([['apps', '📦 APP FORGE'], ['softlayer', '⚡ SOFTLAYER MODULES']] as const).map(([id, label]) => (
          <button key={id} onClick={() => setSection(id)} style={{
            ...btnStyle, padding: '6px 14px',
            background: section === id ? 'rgba(0,243,255,0.15)' : 'transparent',
            color: section === id ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.5)',
            border: `1px solid ${section === id ? 'var(--accent-cyan)' : 'var(--border)'}`,
          }}>{label}</button>
        ))}
      </div>

      {section === 'apps' && (
        <>
          {/* Create from template */}
          <div className="glass-card" style={{ padding: '14px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px' }}>
            <div style={{ fontFamily: 'Orbitron', fontSize: '0.65rem', color: 'var(--accent-cyan)', letterSpacing: '1px', marginBottom: '10px' }}>NEW APP FROM TEMPLATE</div>
            <div style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
              <input value={newAppName} onChange={e => setNewAppName(e.target.value)} placeholder="app_name" style={{ ...inputStyle, width: '200px' }} />
            </div>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {Object.entries(APP_TEMPLATES).map(([id, t]) => (
                <button key={id} onClick={() => createApp(id)} disabled={busy} style={{
                  ...btnStyle, textAlign: 'left', padding: '10px 14px',
                  background: 'rgba(77,255,160,0.06)', border: '1px solid rgba(77,255,160,0.3)', color: '#fff',
                }}>
                  <div style={{ fontSize: '0.72rem' }}>{t.icon} {t.label}</div>
                  <div style={{ fontSize: '0.58rem', opacity: 0.6, fontFamily: 'Share Tech Mono', marginTop: '3px' }}>{t.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* My apps */}
          {apps.length > 0 && (
            <div className="glass-card" style={{ padding: '14px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px' }}>
              <div style={{ fontFamily: 'Orbitron', fontSize: '0.65rem', color: 'var(--accent-cyan)', letterSpacing: '1px', marginBottom: '8px' }}>YOUR APPS</div>
              {apps.map(a => (
                <div key={a.app} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '6px 8px', fontFamily: 'Share Tech Mono', fontSize: '0.75rem', flexWrap: 'wrap' }}>
                  <span onClick={() => openFile(a.app, 'main.py')} style={{ color: a.app === appName ? 'var(--neon-green)' : '#fff', cursor: 'pointer' }}>📦 {a.app}</span>
                  {a.artifacts.map(ar => (
                    <a key={ar} href={`/api/soul/kiosk/download/${owner}/${a.app}/${ar}`}
                      style={{ color: 'var(--accent-cyan)', fontSize: '0.65rem', textDecoration: 'none' }}>⬇ {ar}</a>
                  ))}
                </div>
              ))}
            </div>
          )}

          {/* Editor */}
          {appName && (
            <div className="glass-card" style={{ padding: '12px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontFamily: 'Orbitron', fontSize: '0.65rem', color: 'var(--neon-green)' }}>📦 {appName}</span>
                {currentApp?.files.map(f => (
                  <span key={f} onClick={() => openFile(appName, f)}
                    style={{ fontSize: '0.68rem', fontFamily: 'Share Tech Mono', cursor: 'pointer', color: f === appFile ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.5)' }}>{f}</span>
                ))}
                <span style={{ flex: 1 }} />
                <button onClick={saveFile} style={{ ...btnStyle, background: 'var(--neon-green)', color: '#000' }}>SAVE</button>
                <select value={target} onChange={e => setTarget(e.target.value)}
                  title={targets[target]?.note || ''}
                  style={{ ...inputStyle, cursor: 'pointer', padding: '6px 8px' }}>
                  {[['binary', '⬇ Linux binary'], ['zip', '🗜 source .zip'],
                    ['flatpak', '📦 Flatpak'], ['winexe', '🪟 Windows .exe']].map(([v, l]) => (
                    <option key={v} value={v}>{l}{targets[v] && !targets[v].available ? ' (toolchain missing)' : ''}</option>
                  ))}
                </select>
                <button onClick={build} disabled={busy} style={{ ...btnStyle, background: 'rgba(255,179,71,0.2)', color: '#ffb347', border: '1px solid #ffb347' }}>⚙ COMPILE</button>
              </div>
              {targets[target] && !targets[target].available && (
                <div style={{ fontSize: '0.62rem', color: '#ffb347', fontFamily: 'Share Tech Mono', opacity: 0.8 }}>
                  {targets[target].note}
                </div>
              )}
              <textarea value={appSource} onChange={e => setAppSource(e.target.value)} spellCheck={false}
                style={{ ...inputStyle, minHeight: '300px', resize: 'vertical', lineHeight: 1.5, whiteSpace: 'pre' }} />
              <div style={{ display: 'flex', gap: '8px' }}>
                <input value={assistPrompt} onChange={e => setAssistPrompt(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') assist(); }}
                  placeholder="Ask Jen: 'add a dark mode toggle' / 'make it use the persona API'…"
                  style={{ ...inputStyle, flex: 1 }} />
                <button onClick={assist} disabled={busy} style={{ ...btnStyle, background: 'rgba(0,243,255,0.15)', color: 'var(--accent-cyan)', border: '1px solid var(--accent-cyan)' }}>✨ AI ASSIST</button>
              </div>
            </div>
          )}

          {/* Policy */}
          {policy && (
            <div style={{ padding: '12px', border: '1px dashed rgba(255,179,71,0.4)', borderRadius: '4px', fontSize: '0.65rem', fontFamily: 'Share Tech Mono', color: 'rgba(255,255,255,0.55)', whiteSpace: 'pre-wrap' }}>
              {policy}
            </div>
          )}
        </>
      )}

      {section === 'softlayer' && (
        <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap' }}>
          <div className="glass-card" style={{ width: '220px', padding: '12px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px' }}>
            <div style={{ fontFamily: 'Orbitron', fontSize: '0.65rem', color: 'var(--accent-cyan)', letterSpacing: '1px', marginBottom: '8px' }}>MODULES</div>
            {slModules.map(m => (
              <div key={m.name} onClick={() => slOpen(m.name)}
                style={{ padding: '6px 8px', cursor: 'pointer', fontFamily: 'Share Tech Mono', fontSize: '0.72rem', color: m.name === slName ? 'var(--neon-green)' : 'rgba(255,255,255,0.7)' }}>
                {m.name}.js <span style={{ opacity: 0.4, fontSize: '0.6rem' }}>{m.size}b</span>
              </div>
            ))}
          </div>
          <div className="glass-card" style={{ flex: 1, minWidth: '380px', padding: '12px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
              <input value={slName} onChange={e => setSlName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
                placeholder="module_name" style={{ ...inputStyle, width: '180px' }} />
              <select value={slTemplate} onChange={e => { setSlTemplate(e.target.value); setSlSource(SL_TEMPLATES[e.target.value].code(slName)); }}
                style={{ ...inputStyle, cursor: 'pointer' }}>
                {Object.entries(SL_TEMPLATES).map(([k, t]) => <option key={k} value={k}>{t.label}</option>)}
              </select>
              <button onClick={slSave} disabled={busy} style={{ ...btnStyle, background: 'var(--neon-green)', color: '#000' }}>DEPLOY</button>
            </div>
            <textarea value={slSource} onChange={e => setSlSource(e.target.value)} spellCheck={false}
              style={{ ...inputStyle, minHeight: '300px', resize: 'vertical', lineHeight: 1.5, whiteSpace: 'pre' }} />
          </div>
        </div>
      )}

      {notice && <div style={{ fontSize: '0.7rem', color: 'var(--neon-green)', fontFamily: 'Share Tech Mono' }}>{notice}</div>}
    </div>
  );
};
