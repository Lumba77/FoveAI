import React, { useState, useEffect } from 'react';

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
          traits.forEach(t => {
            loadedTraits[t.key] = data.dna[t.key] !== undefined ? data.dna[t.key] : 0.5;
          });
          setDnaTraits(loadedTraits);
        }
        setLoading(false);
      })
      .catch(err => {
        console.error('Failed to fetch DNA:', err);
        setLoading(false);
      });
  }, []);

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
        </div>
      </div>

      {/* DNA Traits Grid */}
      <div className="glass-card" style={{ padding: '20px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}>
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
    </div>
  );
};
