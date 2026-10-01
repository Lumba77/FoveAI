import React, { useState, useEffect } from 'react';

export const AgencyTab: React.FC = () => {
  const [agentStatus, setAgentStatus] = useState('OFFLINE');
  const [cpuVal, setCpuVal] = useState(0);
  const [ramVal, setRamVal] = useState(0);
  
  const [persona, setPersona] = useState('foveai');
  const [domain, setDomain] = useState('co_presence');

  // Fetch DNA config
  useEffect(() => {
    fetch('/api/soul/soul_dna')
      .then(res => res.json())
      .then(data => {
        if (data && data.dna) {
          if (data.dna.active_persona_id) setPersona(data.dna.active_persona_id);
          if (data.dna.domain) setDomain(data.dna.domain);
        }
      })
      .catch(err => console.error('Failed to fetch DNA:', err));
  }, []);

  const updateDNA = (key: string, value: string) => {
    fetch('/api/soul/update_soul', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [key]: value })
    }).catch(err => console.error('Failed to update DNA:', err));
  };

  // Mocking agent status poll for visual flair
  useEffect(() => {
    let interval: any;
    if (agentStatus === 'ONLINE') {
      interval = setInterval(() => {
        setCpuVal(Math.floor(Math.random() * 40) + 10);
        setRamVal(Math.floor(Math.random() * 20) + 30);
      }, 2000);
    } else {
      setCpuVal(0);
      setRamVal(0);
    }
    return () => clearInterval(interval);
  }, [agentStatus]);

  return (
    <div style={{ padding: '20px', height: '100%', overflowY: 'auto' }}>
      <div className="breadcrumb">KINETIC AGENCY (AUTONOMOUS BEHAVIOR)</div>
      <p style={{ fontSize: '0.75rem', opacity: 0.7, marginBottom: '20px', color: 'var(--neon-blue)' }}>
        Configure autonomous behavior patterns and physical engagement protocols within the WebXR Vessel.
      </p>

      {/* MASTER CONTROL ROW */}
      <div className="glass-card" style={{ padding: '20px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)', marginBottom: '25px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '15px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
            <h4 style={{ fontFamily: 'Orbitron', margin: 0, fontSize: '0.9rem', color: 'var(--neon-blue)', letterSpacing: '2px' }}>AGENT LOOP</h4>
            <span style={{ fontFamily: 'Share Tech Mono', fontSize: '0.85rem', color: agentStatus === 'ONLINE' ? 'var(--neon-green)' : 'var(--neon-pink)' }}>
              ● {agentStatus}
            </span>
          </div>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <button 
              onClick={() => setAgentStatus('ONLINE')}
              style={{ padding: '10px 20px', background: 'rgba(57,255,20,0.15)', border: '1px solid var(--neon-green)', color: 'var(--neon-green)', fontFamily: 'Orbitron', fontSize: '0.75rem', cursor: 'pointer', borderRadius: '4px', letterSpacing: '1px' }}>
              ▶ START
            </button>
            <button 
              onClick={() => setAgentStatus('OFFLINE')}
              style={{ padding: '10px 20px', background: 'rgba(255,0,127,0.15)', border: '1px solid var(--neon-pink)', color: 'var(--neon-pink)', fontFamily: 'Orbitron', fontSize: '0.75rem', cursor: 'pointer', borderRadius: '4px', letterSpacing: '1px' }}>
              ■ STOP
            </button>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', marginBottom: '25px' }}>
        {/* Left: Toggles */}
        <div className="glass-card" style={{ flex: 1, padding: '20px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}>
          <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 20px 0', fontSize: '0.9rem', color: 'var(--neon-blue)', letterSpacing: '2px' }}>PRIMARY DRIVES</h4>
          
          {['AUTONOMOUS_LOCOMOTION', 'PROACTIVE_ENGAGEMENT', 'ENVIRONMENTAL_AWARENESS'].map(drive => (
            <div key={drive} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '15px', background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '4px', marginBottom: '15px' }}>
              <span style={{ fontFamily: 'Share Tech Mono', fontSize: '0.85rem', color: '#fff' }}>{drive}</span>
              <input type="checkbox" defaultChecked style={{ width: '20px', height: '20px', accentColor: 'var(--neon-blue)', cursor: 'pointer' }} />
            </div>
          ))}
        </div>

        {/* Right: Status + Safety Panel */}
        <div className="glass-card" style={{ flex: 1, padding: '20px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}>
          <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 20px 0', fontSize: '0.9rem', color: 'var(--neon-blue)', letterSpacing: '2px' }}>AGENCY STATUS</h4>
          
          <div style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid var(--neon-blue)', padding: '20px', borderRadius: '4px', fontFamily: 'Share Tech Mono', fontSize: '0.8rem', lineHeight: 2 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
              <strong style={{ color: 'var(--neon-blue)' }}>LOCOMOTION:</strong>
              <span style={{ color: agentStatus === 'ONLINE' ? 'var(--neon-green)' : 'var(--neon-pink)' }}>{agentStatus === 'ONLINE' ? 'ACTIVE' : 'STANDBY'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
              <strong style={{ color: 'var(--neon-blue)' }}>ENGAGEMENT:</strong>
              <span style={{ color: 'var(--neon-pink)' }}>STANDBY</span>
            </div>
          </div>

          <div style={{ marginTop: '20px' }}>
            <h5 style={{ fontFamily: 'Orbitron', margin: '0 0 12px 0', fontSize: '0.7rem', color: 'var(--neon-blue)', letterSpacing: '1px' }}>SAFETY MONITOR</h5>
            <div style={{ display: 'flex', gap: '10px' }}>
              <div style={{ flex: 1, textAlign: 'center' }}>
                <div style={{ fontSize: '0.6rem', opacity: 0.6, marginBottom: '4px' }}>CPU</div>
                <div style={{ background: 'rgba(0,0,0,0.5)', height: '8px', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${cpuVal}%`, background: 'var(--neon-green)', transition: 'width 0.5s' }} />
                </div>
                <div style={{ fontSize: '0.65rem', marginTop: '4px' }}>{cpuVal}%</div>
              </div>
              <div style={{ flex: 1, textAlign: 'center' }}>
                <div style={{ fontSize: '0.6rem', opacity: 0.6, marginBottom: '4px' }}>RAM</div>
                <div style={{ background: 'rgba(0,0,0,0.5)', height: '8px', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${ramVal}%`, background: 'var(--neon-green)', transition: 'width 0.5s' }} />
                </div>
                <div style={{ fontSize: '0.65rem', marginTop: '4px' }}>{ramVal}%</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Persona, Domain and Mode Selection */}
      <div className="glass-card" style={{ padding: '20px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)', marginBottom: '25px' }}>
        <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 20px 0', fontSize: '0.9rem', color: 'var(--neon-blue)', letterSpacing: '2px' }}>PERSONA & DOMAIN</h4>
        <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
          
          <div style={{ flex: 1, minWidth: '200px' }}>
            <label style={{ fontFamily: 'Share Tech Mono', fontSize: '0.8rem', color: 'var(--neon-blue)', display: 'block', marginBottom: '8px' }}>ACTIVE PERSONA</label>
            <select value={persona} onChange={e => { setPersona(e.target.value); updateDNA('active_persona_id', e.target.value); }} style={{ width: '100%', background: '#02050a', color: '#fff', border: '1px solid var(--border)', padding: '8px', fontFamily: 'Share Tech Mono', fontSize: '0.85rem', borderRadius: '4px', outline: 'none', cursor: 'pointer' }}>
              <option value="foveai">FoveAI (Default)</option>
              <option value="librarian">Librarian of Truth</option>
              <option value="painter">Creative Painter</option>
              <option value="coder">Expert Coder</option>
            </select>
          </div>

          <div style={{ flex: 1, minWidth: '200px' }}>
            <label style={{ fontFamily: 'Share Tech Mono', fontSize: '0.8rem', color: 'var(--neon-blue)', display: 'block', marginBottom: '8px' }}>KNOWLEDGE DOMAIN</label>
            <select value={domain} onChange={e => { setDomain(e.target.value); updateDNA('domain', e.target.value); }} style={{ width: '100%', background: '#02050a', color: '#fff', border: '1px solid var(--border)', padding: '8px', fontFamily: 'Share Tech Mono', fontSize: '0.85rem', borderRadius: '4px', outline: 'none', cursor: 'pointer' }}>
              <option value="co_presence">Co-Presence (General)</option>
              <option value="build_run">Build & Run (Development)</option>
              <option value="wonder_mind">Wonder Mind (Creativity)</option>
            </select>
          </div>

        </div>
      </div>
    </div>
  );
};
