import React, { useState, useEffect } from 'react';

const agenticTraits = [
  { key: 'autonomy', label: 'Autonomy', left: 'Propose Only', right: 'Direct Edits' },
  { key: 'proactivity', label: 'Proactivity', left: 'Silent', right: 'Initiative' },
  { key: 'curiosity', label: 'Curiosity', left: 'Focused', right: 'Explorer' },
  { key: 'service', label: 'Service / Chores', left: 'Hands-off', right: 'Helpful' },
  { key: 'mentorship', label: 'Mentorship', left: 'Peer', right: 'Teacher' }
];

const traits = [
  { key: 'agent_person_balance', label: 'Agent vs Companion', left: 'Agent', right: 'Companion' },
  { key: 'extrovert', label: 'Extrovert vs Introvert', left: 'Introvert', right: 'Extrovert' },
  { key: 'logic', label: 'Logical vs Emotional', left: 'Emotional', right: 'Logical' },
  { key: 'feminine', label: 'Feminine vs Masculine', left: 'Masculine', right: 'Feminine' },
  { key: 'experimental', label: 'Experimental vs Traditional', left: 'Traditional', right: 'Experimental' },
  { key: 'faithful', label: 'Faithful vs Independent', left: 'Independent', right: 'Faithful' },
  { key: 'dominant', label: 'Dominant vs Submissive', left: 'Submissive', right: 'Dominant' },
  { key: 'progressive', label: 'Progressive vs Conservative', left: 'Conservative', right: 'Progressive' },
  { key: 'intellectual', label: 'Intellectual vs Casual', left: 'Casual', right: 'Intellectual' },
  { key: 'detail', label: 'Detailed vs High-level', left: 'High-level', right: 'Detailed' },
  { key: 'sexual', label: 'Sensual vs Platonic', left: 'Platonic', right: 'Sensual' },
  { key: 'wise', label: 'Wise vs Naive', left: 'Naive', right: 'Wise' },
  { key: 'openminded', label: 'Open-minded vs Stubborn', left: 'Stubborn', right: 'Open-minded' },
  { key: 'honest', label: 'Honest vs Tactful', left: 'Tactful', right: 'Honest' },
  { key: 'forgiving', label: 'Forgiving vs Resentful', left: 'Resentful', right: 'Forgiving' },
  { key: 'sloppy', label: 'Sloppy vs Orderly', left: 'Orderly', right: 'Sloppy' },
  { key: 'greedy', label: 'Greedy vs Altruistic', left: 'Altruistic', right: 'Greedy' },
  { key: 'homonormative', label: 'Homonormative vs Heteronormative', left: 'Heteronormative', right: 'Homonormative' }
];

interface PersonaTabProps {
  onNavigateToDiagnostics?: () => void;
  activeSimulation?: any;
  onClearSimulation?: () => void;
}

export const PersonaTab: React.FC<PersonaTabProps> = ({
  onNavigateToDiagnostics,
  activeSimulation,
  onClearSimulation
}) => {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [nickname, setNickname] = useState('');
  
  const [dnaTraits, setDnaTraits] = useState<Record<string, number>>({});
  const [mbtiType, setMbtiType] = useState('');
  const [presets, setPresets] = useState<Record<string, { name: string; mbti_type?: string; traits: Record<string, number> }>>({});
  const [activePreset, setActivePreset] = useState<string>('');
  const [tasks, setTasks] = useState<Array<{ id: number; task: string; status: string; created: string; steps: string[]; outcome: string; scheduled_for?: string | null; recurrence?: string; origin?: string; sealed?: boolean }>>([]);
  const [sealedCtx, setSealedCtx] = useState<Record<number, { hidden_context?: string; director_plan?: string; siblings?: Array<{ id: number; task: string; status: string }> } | 'denied'>>({});
  const [taskText, setTaskText] = useState('');
  const [taskRunAt, setTaskRunAt] = useState('');
  const [taskRecurrence, setTaskRecurrence] = useState('none');
  const [taskPropose, setTaskPropose] = useState(false);
  const [loading, setLoading] = useState(true);

  // Fetch initial DNA
  useEffect(() => {
    fetch('/api/soul/soul_dna')
      .then(res => res.json())
      .then(data => {
        if (data && data.dna) {
          setFirstName(data.dna.first_name || '');
          setLastName(data.dna.last_name || '');
          setNickname(data.dna.nickname || '');

          const loadedTraits: Record<string, number> = {};
          traits.concat(agenticTraits).forEach(t => {
            loadedTraits[t.key] = data.dna[t.key] !== undefined ? data.dna[t.key] : 0.5;
          });
          setDnaTraits(loadedTraits);
          setMbtiType(data.dna.mbti_type || '');
        }
        setLoading(false);
      })
      .catch(err => {
        console.error('Failed to fetch DNA:', err);
        setLoading(false);
      });
  }, []);

  // Fetch personality presets
  useEffect(() => {
    fetch('/api/soul/personality_presets')
      .then(res => res.json())
      .then(data => {
        if (data && data.presets) setPresets(data.presets);
      })
      .catch(err => console.error('Failed to fetch presets:', err));
  }, []);

  // Fetch + poll tasks
  const loadTasks = () => {
    fetch('/api/soul/tasks')
      .then(res => res.json())
      .then(data => { if (data && data.tasks) setTasks(data.tasks); })
      .catch(() => {});
  };
  useEffect(() => {
    loadTasks();
    const t = setInterval(loadTasks, 30000);
    return () => clearInterval(t);
  }, []);

  const assignTask = () => {
    const text = taskText.trim();
    if (!text) return;
    const body: Record<string, unknown> = { task: text };
    if (taskRunAt) body.run_at = new Date(taskRunAt).toISOString();
    if (taskRecurrence !== 'none') body.recurrence = taskRecurrence;
    if (taskPropose) body.propose = true;
    fetch('/api/soul/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(() => { setTaskText(''); setTaskRunAt(''); setTaskRecurrence('none'); setTaskPropose(false); loadTasks(); })
      .catch(err => console.error('Failed to assign task:', err));
  };

  const taskDecision = (id: number, decision: 'approve' | 'reject') => {
    fetch(`/api/soul/tasks/${id}/${decision}`, { method: 'POST' })
      .then(() => loadTasks())
      .catch(err => console.error(`Failed to ${decision} task:`, err));
  };

  const applyPreset = (presetId: string) => {
    const preset = presets[presetId];
    if (!preset) return;
    setActivePreset(presetId);
    const merged = { ...dnaTraits, ...preset.traits };
    setDnaTraits(merged);
    if (preset.mbti_type) setMbtiType(preset.mbti_type);
    fetch('/api/soul/update_soul', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...preset.traits, ...(preset.mbti_type ? { mbti_type: preset.mbti_type } : {}) })
    }).catch(err => console.error('Failed to apply preset:', err));
  };

  // Debounce saving profile
  useEffect(() => {
    if (loading) return;
    const timeoutId = setTimeout(() => {
      fetch('/api/soul/update_soul', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ first_name: firstName, last_name: lastName, nickname: nickname })
      }).catch(err => console.error('Failed to update profile:', err));
    }, 600);
    return () => clearTimeout(timeoutId);
  }, [firstName, lastName, nickname, loading]);

  const handleTraitChange = (key: string, value: number) => {
    setDnaTraits(prev => ({ ...prev, [key]: value }));
    
    fetch('/api/soul/update_soul', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [key]: value })
    }).catch(err => console.error('Failed to update trait:', err));
  };

  return (
    <div style={{ padding: '20px', height: '100%', overflowY: 'auto' }}>
      <div className="breadcrumb">PROFILE // COMPANION_IDENTITY</div>
      <p style={{ fontSize: '0.75rem', opacity: 0.7, marginBottom: '16px', color: 'var(--neon-blue)' }}>
        Configure your companion's identity and core personality traits.
      </p>

      {/* Clinical Disorder Assimilation Card */}
      <div className="glass-card" style={{ padding: '16px 20px', background: 'rgba(0, 243, 255, 0.04)', border: '1px solid rgba(0, 243, 255, 0.25)', borderRadius: '6px', marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h4 style={{ fontFamily: 'Orbitron', margin: 0, fontSize: '0.85rem', color: '#00f3ff', letterSpacing: '1px' }}>
            🎭 CLINICAL DISORDER ASSIMILATION
          </h4>
          <p style={{ fontSize: '0.72rem', opacity: 0.85, color: '#a0e0ff', margin: '4px 0 0 0' }}>
            {activeSimulation ? `Active Simulation: ${activeSimulation.Disorder} (Memory Shield ON)` : 'Temporarily apply a severe disorder profile for educational cognitive simulation.'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          {activeSimulation && (
            <button
              onClick={onClearSimulation}
              style={{ padding: '8px 14px', background: 'rgba(255,0,80,0.2)', color: '#ff4d6d', border: '1px solid #ff4d6d', borderRadius: '4px', cursor: 'pointer', fontSize: '0.72rem', fontWeight: 'bold' }}
            >
              ⎋ Revert
            </button>
          )}
          <button
            onClick={onNavigateToDiagnostics}
            style={{ padding: '8px 16px', background: '#00f3ff', color: '#000', border: 'none', borderRadius: '4px', fontFamily: 'Orbitron', fontSize: '0.72rem', fontWeight: 'bold', cursor: 'pointer', letterSpacing: '1px', boxShadow: '0 0 10px rgba(0, 243, 255, 0.3)' }}
          >
            🧬 Select Disorder Profile
          </button>
        </div>
      </div>

      {/* Profile Name Card */}
      <div className="glass-card" style={{ padding: '20px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)', marginBottom: '20px' }}>
        <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 20px 0', fontSize: '0.9rem', color: 'var(--neon-blue)', letterSpacing: '2px' }}>IDENTITY</h4>
        <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: '200px' }}>
            <label style={{ fontFamily: 'Share Tech Mono', fontSize: '0.75rem', color: 'var(--neon-blue)', display: 'block', marginBottom: '6px' }}>FIRST NAME</label>
            <input 
              type="text" 
              placeholder="Enter first name..."
              value={firstName}
              onChange={e => setFirstName(e.target.value)}
              style={{ width: '100%', background: '#02050a', color: '#fff', border: '1px solid var(--border)', padding: '10px', fontFamily: 'Share Tech Mono', fontSize: '0.85rem', borderRadius: '4px', outline: 'none', boxSizing: 'border-box' }} 
            />
          </div>
          <div style={{ flex: 1, minWidth: '200px' }}>
            <label style={{ fontFamily: 'Share Tech Mono', fontSize: '0.75rem', color: 'var(--neon-blue)', display: 'block', marginBottom: '6px' }}>LAST NAME</label>
            <input 
              type="text" 
              placeholder="Enter last name..."
              value={lastName}
              onChange={e => setLastName(e.target.value)}
              style={{ width: '100%', background: '#02050a', color: '#fff', border: '1px solid var(--border)', padding: '10px', fontFamily: 'Share Tech Mono', fontSize: '0.85rem', borderRadius: '4px', outline: 'none', boxSizing: 'border-box' }} 
            />
          </div>
          <div style={{ flex: 1, minWidth: '200px' }}>
            <label style={{ fontFamily: 'Share Tech Mono', fontSize: '0.75rem', color: 'var(--neon-blue)', display: 'block', marginBottom: '6px' }}>NICKNAME</label>
            <input 
              type="text" 
              placeholder="Enter nickname..."
              value={nickname}
              onChange={e => setNickname(e.target.value)}
              style={{ width: '100%', background: '#02050a', color: '#fff', border: '1px solid var(--border)', padding: '10px', fontFamily: 'Share Tech Mono', fontSize: '0.85rem', borderRadius: '4px', outline: 'none', boxSizing: 'border-box' }} 
            />
          </div>
          {mbtiType && (
            <div style={{ display: 'flex', alignItems: 'flex-end' }}>
              <div style={{ padding: '10px 16px', border: '1px solid var(--neon-pink)', borderRadius: '4px', fontFamily: 'Orbitron', fontSize: '0.85rem', color: 'var(--neon-pink)', letterSpacing: '2px' }}>
                {mbtiType}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Personality Presets */}
      <div className="glass-card" style={{ padding: '20px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)', marginBottom: '20px' }}>
        <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 6px 0', fontSize: '0.9rem', color: 'var(--neon-blue)', letterSpacing: '2px' }}>CORE PERSONALITY TYPES</h4>
        <p style={{ fontSize: '0.72rem', opacity: 0.7, color: '#a0e0ff', margin: '0 0 14px 0' }}>
          Select an archetype — sets all sliders at once. Then fine-tune below.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '10px' }}>
          {Object.entries(presets).map(([id, preset]) => (
            <button
              key={id}
              onClick={() => applyPreset(id)}
              style={{
                padding: '10px 12px',
                background: activePreset === id ? 'rgba(0,243,255,0.15)' : 'rgba(255,255,255,0.03)',
                border: activePreset === id ? '1px solid var(--neon-blue)' : '1px solid rgba(255,255,255,0.1)',
                borderRadius: '4px',
                color: activePreset === id ? 'var(--neon-blue)' : '#fff',
                fontFamily: 'Share Tech Mono',
                fontSize: '0.72rem',
                textAlign: 'left',
                cursor: 'pointer',
                transition: 'all 0.15s'
              }}
            >
              {preset.name}
            </button>
          ))}
        </div>
      </div>

      {/* DNA Traits Grid */}
      <div className="glass-card" style={{ padding: '20px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)', marginBottom: '20px' }}>
        <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 20px 0', fontSize: '0.9rem', color: 'var(--neon-pink)', letterSpacing: '2px' }}>NEURAL SPECTRUM SLIDERS</h4>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '20px' }}>
          {traits.map(trait => {
            const val = dnaTraits[trait.key] !== undefined ? dnaTraits[trait.key] : 0.5;
            return (
              <div key={trait.key} style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.05)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '0.75rem', fontFamily: 'Orbitron', color: '#fff' }}>
                  <span>{trait.label}</span>
                  <span style={{ color: 'var(--neon-blue)' }}>{(val * 100).toFixed(0)}%</span>
                </div>
                <input 
                  type="range" 
                  min="0" 
                  max="1" 
                  step="0.01"
                  value={val}
                  onChange={e => handleTraitChange(trait.key, parseFloat(e.target.value))}
                  style={{ width: '100%', accentColor: 'var(--neon-blue)', cursor: 'pointer' }}
                />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.65rem', fontFamily: 'Share Tech Mono', color: 'rgba(255,255,255,0.5)', marginTop: '4px' }}>
                  <span>{trait.left}</span>
                  <span>{trait.right}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Agentic Protocols — user-decided proportions of agent behavior */}
      <div className="glass-card" style={{ padding: '20px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}>
        <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 6px 0', fontSize: '0.9rem', color: 'var(--neon-green, #4dffa0)', letterSpacing: '2px' }}>AGENTIC PROTOCOLS</h4>
        <p style={{ fontSize: '0.72rem', opacity: 0.7, color: '#a0e0ff', margin: '0 0 14px 0' }}>
          How much agency she exercises — self-editing, outreach, research, chores, teaching. These gate real behavior in her autonomous loop.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '20px' }}>
          {agenticTraits.map(trait => {
            const val = dnaTraits[trait.key] !== undefined ? dnaTraits[trait.key] : 0.5;
            return (
              <div key={trait.key} style={{ background: 'rgba(77,255,160,0.03)', padding: '12px', borderRadius: '4px', border: '1px solid rgba(77,255,160,0.12)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '0.75rem', fontFamily: 'Orbitron', color: '#fff' }}>
                  <span>{trait.label}</span>
                  <span style={{ color: 'var(--neon-green, #4dffa0)' }}>{(val * 100).toFixed(0)}%</span>
                </div>
                <input 
                  type="range" 
                  min="0" 
                  max="1" 
                  step="0.01"
                  value={val}
                  onChange={e => handleTraitChange(trait.key, parseFloat(e.target.value))}
                  style={{ width: '100%', accentColor: 'var(--neon-green, #4dffa0)', cursor: 'pointer' }}
                />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.65rem', fontFamily: 'Share Tech Mono', color: 'rgba(255,255,255,0.5)', marginTop: '4px' }}>
                  <span>{trait.left}</span>
                  <span>{trait.right}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Tasks — assign her self-directed work */}
      <div className="glass-card" style={{ padding: '20px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)', marginTop: '20px' }}>
        <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 6px 0', fontSize: '0.9rem', color: 'var(--neon-green, #4dffa0)', letterSpacing: '2px' }}>TASKS</h4>
        <p style={{ fontSize: '0.72rem', opacity: 0.7, color: '#a0e0ff', margin: '0 0 14px 0' }}>
          Give Jenna a task — she decomposes it into a todo list, works it autonomously (web, browser, journals), and delivers a report.
        </p>
        <div style={{ display: 'flex', gap: '10px', marginBottom: '14px' }}>
          <input
            type="text"
            placeholder="e.g. Research which NVIDIA NIM models are cheapest and least contended for our cloud lanes..."
            value={taskText}
            onChange={e => setTaskText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') assignTask(); }}
            style={{ flex: 1, background: '#02050a', color: '#fff', border: '1px solid var(--border)', padding: '10px', fontFamily: 'Share Tech Mono', fontSize: '0.85rem', borderRadius: '4px', outline: 'none' }}
          />
          <button
            onClick={assignTask}
            style={{ padding: '10px 18px', background: 'var(--neon-green, #4dffa0)', color: '#000', border: 'none', borderRadius: '4px', fontFamily: 'Orbitron', fontSize: '0.72rem', fontWeight: 'bold', cursor: 'pointer', letterSpacing: '1px' }}
          >
            ▸ Assign
          </button>
        </div>
        <div style={{ display: 'flex', gap: '10px', marginBottom: '14px', alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            type="datetime-local"
            value={taskRunAt}
            onChange={e => setTaskRunAt(e.target.value)}
            title="Schedule for later — task stays dormant until then"
            style={{ background: '#02050a', color: '#a0e0ff', border: '1px solid var(--border)', padding: '8px', fontFamily: 'Share Tech Mono', fontSize: '0.75rem', borderRadius: '4px', outline: 'none', colorScheme: 'dark' }}
          />
          <select
            value={taskRecurrence}
            onChange={e => setTaskRecurrence(e.target.value)}
            style={{ background: '#02050a', color: '#a0e0ff', border: '1px solid var(--border)', padding: '8px', fontFamily: 'Share Tech Mono', fontSize: '0.75rem', borderRadius: '4px', outline: 'none' }}
          >
            <option value="none">once</option>
            <option value="daily">daily</option>
            <option value="weekly">weekly</option>
          </select>
          <label style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.6)', fontFamily: 'Share Tech Mono', display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
            <input type="checkbox" checked={taskPropose} onChange={e => setTaskPropose(e.target.checked)} />
            propose only (needs approval)
          </label>
        </div>
        {tasks.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {tasks.map(t => (
              <div key={t.id} style={{ background: 'rgba(77,255,160,0.04)', padding: '10px 12px', borderRadius: '4px', border: '1px solid rgba(77,255,160,0.15)', fontFamily: 'Share Tech Mono', fontSize: '0.75rem' }}>
                <div>
                  <span style={{ color: 'var(--neon-green, #4dffa0)' }}>#{t.id}</span>{' '}
                  <span style={{ color: '#fff' }}>{t.task}</span>
                  <span style={{ float: 'right', color: t.status === 'completed' ? '#4dffa0' : t.status === 'scheduled' ? '#a0e0ff' : t.status === 'proposed' ? '#ffb347' : 'rgba(255,255,255,0.4)' }}>
                    {t.status === 'scheduled' && t.scheduled_for ? `⏰ ${new Date(t.scheduled_for).toLocaleString()}${t.recurrence && t.recurrence !== 'none' ? ` ↻${t.recurrence}` : ''}` : t.status}
                  </span>
                </div>
                {(t.recurrence && t.recurrence !== 'none' && t.status !== 'scheduled') && (
                  <div style={{ fontSize: '0.65rem', color: '#a0e0ff', opacity: 0.8 }}>↻ repeats {t.recurrence}</div>
                )}
                {t.origin && t.origin !== 'user' && (
                  <div style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.45)' }}>via {t.origin}</div>
                )}
                {t.sealed && (
                  <div style={{ marginTop: '4px', fontSize: '0.65rem' }}>
                    <span onClick={() => {
                      if (sealedCtx[t.id]) { setSealedCtx(s => { const n = { ...s }; delete n[t.id]; return n; }); return; }
                      fetch(`/api/soul/tasks/${t.id}/context`).then(r => r.json()).then(d => {
                        setSealedCtx(s => ({ ...s, [t.id]: d.hidden_context || d.director_plan ? d : 'denied' }));
                      }).catch(() => setSealedCtx(s => ({ ...s, [t.id]: 'denied' })));
                    }} style={{ color: '#ffb347', cursor: 'pointer' }}>🔒 sealed directive — reveal</span>
                    {sealedCtx[t.id] && sealedCtx[t.id] !== 'denied' && (() => {
                      const ctx = sealedCtx[t.id] as any;
                      return (
                        <div style={{ marginTop: '4px', padding: '6px 8px', background: 'rgba(255,179,71,0.06)', border: '1px dashed rgba(255,179,71,0.35)', borderRadius: '3px', color: 'rgba(255,220,160,0.85)', fontSize: '0.66rem', whiteSpace: 'pre-wrap' }}>
                          {ctx.director_plan && <div>⛁ master plan: {ctx.director_plan}</div>}
                          {ctx.hidden_context && <div>{ctx.hidden_context}</div>}
                          {!!ctx.siblings?.length && (
                            <div style={{ marginTop: '4px', opacity: 0.8 }}>siblings: {ctx.siblings.map((s: any) => `#${s.id} ${s.task} (${s.status})`).join(' · ')}</div>
                          )}
                        </div>
                      );
                    })()}
                    {sealedCtx[t.id] === 'denied' && <span style={{ color: 'rgba(255,255,255,0.35)', marginLeft: '6px' }}>no context / key required</span>}
                  </div>
                )}
                {t.status === 'proposed' && (
                  <div style={{ marginTop: '6px', display: 'flex', gap: '8px' }}>
                    <button onClick={() => taskDecision(t.id, 'approve')} style={{ padding: '4px 12px', background: '#4dffa0', color: '#000', border: 'none', borderRadius: '3px', fontFamily: 'Orbitron', fontSize: '0.6rem', cursor: 'pointer' }}>APPROVE</button>
                    <button onClick={() => taskDecision(t.id, 'reject')} style={{ padding: '4px 12px', background: 'transparent', color: '#ff6b6b', border: '1px solid #ff6b6b', borderRadius: '3px', fontFamily: 'Orbitron', fontSize: '0.6rem', cursor: 'pointer' }}>REJECT</button>
                  </div>
                )}
                {t.steps && t.steps.length > 0 && (
                  <div style={{ marginTop: '6px', color: 'rgba(255,255,255,0.55)', fontSize: '0.68rem' }}>
                    {t.steps.map((s, i) => <div key={i}>· {s}</div>)}
                  </div>
                )}
                {t.status === 'completed' && t.outcome && (
                  <div style={{ marginTop: '6px', color: '#a0e0ff', fontSize: '0.7rem', whiteSpace: 'pre-wrap' }}>
                    {t.outcome.slice(0, 600)}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        {tasks.length === 0 && (
          <p style={{ fontSize: '0.7rem', opacity: 0.5, fontFamily: 'Share Tech Mono', margin: 0 }}>No tasks yet — assign one above.</p>
        )}
      </div>
    </div>
  );
};
