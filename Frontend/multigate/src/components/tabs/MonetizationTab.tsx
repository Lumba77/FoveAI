import React, { useState, useEffect } from 'react';

export const MonetizationTab: React.FC = () => {
  const [balance, setBalance] = useState('0.00');
  const [sessionProfit] = useState('$0.00');
  const [, setSwarmStatus] = useState('PAUSED');
  const [activeAgents, setActiveAgents] = useState(0);
  const [pendingTasks] = useState(0);
  const [completedTasks] = useState(0);

  const [agents, setAgents] = useState<any[]>([]);
  const [newAgentName, setNewAgentName] = useState('');
  const [newAgentType, setNewAgentType] = useState('crypto_trading');

  useEffect(() => {
    // Initial fetch of state
    fetch('/monetize/state')
      .then(res => res.json())
      .then(data => {
        if (data) {
          setBalance(data.total_cet_earned || '0.00');
          setActiveAgents(data.agents?.length || 0);
        }
      })
      .catch(err => console.error('Error fetching monetize state:', err));
  }, []);

  const handleDeploy = () => {
    if (!newAgentName) return;
    
    fetch('/monetize/forge_agent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newAgentName, type: newAgentType })
    })
      .then(res => res.json())
      .then(data => {
        setAgents([...agents, { id: data.agent_id || Date.now(), name: newAgentName, type: newAgentType, status: 'IDLE' }]);
        setActiveAgents(prev => prev + 1);
        setNewAgentName('');
      })
      .catch(err => console.error('Error deploying agent:', err));
  };

  return (
    <div style={{ padding: '20px', height: '100%', overflowY: 'auto' }}>
      <div className="breadcrumb">FoveAI MONETIZING AGENTS (COINEX / CET GRINDING)</div>
      
      <div className="glass-card" style={{ marginBottom: '20px', padding: '16px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}>
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
          <div style={{ flex: 1 }}>
            <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 8px 0', fontSize: '0.7rem', color: 'var(--neon-green)', letterSpacing: '2px' }}>LIVE BALANCE (CET)</h4>
            <div style={{ fontSize: '1.8rem', fontWeight: 700, color: 'var(--neon-green)' }}>{balance} CET</div>
            <div style={{ marginTop: '8px', fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)' }}>
              <span style={{ fontFamily: 'Share Tech Mono', color: 'var(--neon-blue)' }}>CET Trading Active</span> | 
              Profit: <span style={{ color: 'var(--neon-green)' }}>{sessionProfit}</span>
            </div>
          </div>

          <div style={{ flex: 1 }}>
            <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 8px 0', fontSize: '0.7rem', color: 'var(--neon-pink)', letterSpacing: '2px' }}>RISK STATUS</h4>
            <div style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--neon-green)' }}>OPERATIONAL</div>
            <div style={{ marginTop: '8px', fontSize: '0.7rem', color: 'rgba(255,255,255,0.6)' }}>
              Max daily loss: <span style={{ color: '#ffaa00' }}>$100</span> | 
              Positions remaining: <span style={{ color: 'var(--neon-blue)' }}>3</span>
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '20px', marginBottom: '20px', flexWrap: 'wrap' }}>
        {/* Left: Agent Controls */}
        <div className="glass-card" style={{ flex: 1, minWidth: '300px', padding: '16px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px' }}>
          <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 15px 0', fontSize: '0.9rem', color: 'var(--neon-blue)', letterSpacing: '2px' }}>SWARM CONTROL</h4>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '15px' }}>
            <button 
              onClick={() => setSwarmStatus('RUNNING')}
              style={{ flex: 1, padding: '12px', background: 'rgba(57, 255, 20, 0.2)', border: '1px solid var(--neon-green)', color: 'var(--neon-green)', fontFamily: 'Orbitron', cursor: 'pointer' }}>
              🚀 START
            </button>
            <button 
              onClick={() => setSwarmStatus('PAUSED')}
              style={{ flex: 1, padding: '12px', background: 'rgba(255, 0, 127, 0.2)', border: '1px solid var(--neon-pink)', color: 'var(--neon-pink)', fontFamily: 'Orbitron', cursor: 'pointer' }}>
              ⏸️ PAUSE
            </button>
          </div>

          <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '16px' }}>
            <h5 style={{ fontFamily: 'Orbitron', margin: '0 0 12px 0', fontSize: '0.8rem', color: 'var(--neon-blue)' }}>Forge Agent</h5>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <input 
                type="text" 
                placeholder="Agent Name..." 
                value={newAgentName}
                onChange={e => setNewAgentName(e.target.value)}
                style={{ padding: '10px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--neon-blue)', color: '#fff', fontFamily: 'Share Tech Mono', outline: 'none' }} 
              />
              <select 
                value={newAgentType}
                onChange={e => setNewAgentType(e.target.value)}
                style={{ padding: '10px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--neon-blue)', color: '#fff', fontFamily: 'Share Tech Mono', outline: 'none' }}
              >
                <option value="crypto_trading">Crypto Trading</option>
                <option value="affiliate_marketing">Affiliate Marketing</option>
                <option value="ad_revenue">Ad Revenue</option>
              </select>
              <button 
                onClick={handleDeploy}
                className="neon-btn" 
                style={{ padding: '10px', background: 'var(--neon-blue)', color: '#000', fontFamily: 'Orbitron', cursor: 'pointer', fontWeight: 700 }}
              >
                DEPLOY AGENT
              </button>
            </div>
          </div>
        </div>

        {/* Right: Status */}
        <div className="glass-card" style={{ flex: 1, minWidth: '300px', padding: '16px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px' }}>
          <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 15px 0', fontSize: '0.9rem', color: 'var(--neon-blue)', letterSpacing: '2px' }}>SWARM STATUS</h4>
          <div style={{ background: 'rgba(0,0,0,0.3)', border: '1px solid var(--neon-blue)', padding: '12px', borderRadius: '4px', marginBottom: '15px', fontFamily: 'Share Tech Mono', fontSize: '0.8rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span>Active Agents:</span><span style={{ color: 'var(--neon-green)' }}>{activeAgents}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span>Pending Tasks:</span><span style={{ color: '#ffaa00' }}>{pendingTasks}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span>Completed:</span><span style={{ color: 'var(--neon-blue)' }}>{completedTasks}</span>
            </div>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '150px', overflowY: 'auto' }}>
            {agents.length === 0 ? (
              <div style={{ color: 'rgba(255,255,255,0.4)', textAlign: 'center', fontSize: '0.8rem', padding: '20px' }}>
                No agents deployed.
              </div>
            ) : (
              agents.map(a => (
                <div key={a.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px', background: 'rgba(0,243,255,0.1)', border: '1px solid rgba(0,243,255,0.3)', borderRadius: '4px' }}>
                  <span style={{ fontFamily: 'Orbitron', fontSize: '0.75rem', color: '#fff' }}>{a.name}</span>
                  <span style={{ fontFamily: 'Share Tech Mono', fontSize: '0.75rem', color: 'var(--neon-green)' }}>{a.status}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
