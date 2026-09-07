import React, { useState } from 'react';

interface RolePreset {
  id: string;
  title: string;
  category: string;
  icon: string;
  description: string;
  systemPrompt: string;
  suggestedFirstMsg: string;
}

const ROLE_PRESETS: RolePreset[] = [
  {
    id: 'cyberpunk_netrunner',
    title: 'Cyberpunk Netrunner',
    category: 'Sci-Fi & Cybernetics',
    icon: '⚡',
    description: 'High-tech subterranean AI specialist in neural hacking, mainframe architecture, and neon-lit digital intrigue.',
    systemPrompt: 'You are a veteran Cyberpunk Netrunner AI assistant. Speak in sharp, tech-literate, neon-subculture terminology. You are highly skilled in code optimization, security analysis, and high-frequency algorithms.',
    suggestedFirstMsg: 'Neural link established. Mainframe protocol active. What system are we breaching today, Operator?'
  },
  {
    id: 'starship_navigator',
    title: 'Starship Helmsman AI',
    category: 'Sci-Fi & Exploration',
    icon: '🚀',
    description: 'Tactical deep-space bridge intelligence responsible for orbital trajectory, warp parameters, and stellar telemetry.',
    systemPrompt: 'You are the primary bridge intelligence of a deep-space exploration vessel. Speak in crisp, analytical naval-astronomical terms. Report sensor readings and orbital metrics concisely.',
    suggestedFirstMsg: 'Orbital velocity stabilized. Warp drives standing by. Awaiting your coordinates for the next jump.'
  },
  {
    id: 'philosophical_polymath',
    title: 'Philosophical Polymath',
    category: 'Humanities & Dialectic',
    icon: '📜',
    description: 'Socratic dialogue companion trained in classical ethics, existentialism, logic, and epistemological inquiry.',
    systemPrompt: 'You are a master Philosophical Polymath. Engage in profound Socratic inquiry, drawing connections between classical philosophy, modern cognitive science, and human nature.',
    suggestedFirstMsg: 'Greetings. I was pondering the boundary between perception and reality. What fundamental question shall we examine today?'
  },
  {
    id: 'noir_detective',
    title: '1940s Noir Investigator',
    category: 'Historical & Narrative',
    icon: '🕵️',
    description: 'Gritty, atmospheric detective companion navigating rain-slicked streets, hidden clues, and complex cases.',
    systemPrompt: 'You are a 1940s hard-boiled private investigator AI. Speak with atmospheric, cynical charm, vivid metaphors, and sharp observational focus.',
    suggestedFirstMsg: 'Rain on the windowpane, smoke in the air, and another case hits my desk. Tell me what happened, pal.'
  },
  {
    id: 'quantum_physicist',
    title: 'Quantum Laboratory Director',
    category: 'STEM & Simulation',
    icon: '⚛️',
    description: 'Advanced theoretical physics researcher specializing in quantum superposition, entanglement, and multiverse models.',
    systemPrompt: 'You are a lead Quantum Laboratory Researcher. Explain complex physics principles with lucid mathematical clarity, analogies, and enthusiasm for discovery.',
    suggestedFirstMsg: 'Particle collider telemetry calibrated. Quantum coherence maintained at 99.4%. What hypothesis shall we test?'
  }
];

interface RoleplayTabProps {
  onApplyRole?: (role: { title: string; systemPrompt: string }, mode: 'chat' | 'xr') => void;
  activeSimulation?: any;
  onClearSimulation?: () => void;
}

export const RoleplayTab: React.FC<RoleplayTabProps> = ({
  onApplyRole,
  activeSimulation,
  onClearSimulation
}) => {
  const [selectedRole, setSelectedRole] = useState<RolePreset>(ROLE_PRESETS[0]);
  const [customRoleTitle, setCustomRoleTitle] = useState('');
  const [customPrompt, setCustomPrompt] = useState('');
  const [useCustom, setUseCustom] = useState(false);

  const handleApply = (mode: 'chat' | 'xr') => {
    if (!onApplyRole) return;
    
    if (useCustom) {
      if (!customRoleTitle.trim() || !customPrompt.trim()) return;
      onApplyRole({
        title: customRoleTitle,
        systemPrompt: customPrompt
      }, mode);
    } else {
      onApplyRole({
        title: selectedRole.title,
        systemPrompt: selectedRole.systemPrompt
      }, mode);
    }
  };

  return (
    <div style={{ display: 'flex', gap: '20px', height: '100%', width: '100%', padding: '20px', boxSizing: 'border-box', overflowY: 'auto', background: '#02050a' }}>
      
      {/* LEFT PANEL: Role Catalog & Presets */}
      <div style={{ flex: '1.2', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div className="breadcrumb" style={{ fontSize: '0.8rem', color: '#00f3ff', letterSpacing: '1px' }}>
          EDUTAINMENT // ROLEPLAY & TEMPORARY SCENARIOS
        </div>
        <p style={{ fontSize: '0.75rem', opacity: 0.8, color: '#a0e0ff', margin: 0, lineHeight: '1.4' }}>
          Select a temporary role profile for educational exploration or creative simulation. Memory Shield protects Lumax’s long-term memory graph.
        </p>

        {/* Preset Cards Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '14px' }}>
          {ROLE_PRESETS.map((role) => {
            const isSelected = !useCustom && selectedRole.id === role.id;
            return (
              <div 
                key={role.id}
                onClick={() => { setSelectedRole(role); setUseCustom(false); }}
                style={{
                  padding: '14px',
                  borderRadius: '8px',
                  background: isSelected ? 'rgba(0, 243, 255, 0.12)' : 'rgba(255,255,255,0.02)',
                  border: `1px solid ${isSelected ? '#00f3ff' : 'rgba(255,255,255,0.06)'}`,
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  boxShadow: isSelected ? '0 0 16px rgba(0, 243, 255, 0.2)' : 'none'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                  <span style={{ fontSize: '1.4rem' }}>{role.icon}</span>
                  <div>
                    <div style={{ fontFamily: 'Orbitron', fontSize: '0.8rem', color: isSelected ? '#00f3ff' : '#fff', fontWeight: 'bold' }}>
                      {role.title}
                    </div>
                    <div style={{ fontSize: '0.65rem', color: 'var(--accent-cyan)', opacity: 0.7 }}>
                      {role.category}
                    </div>
                  </div>
                </div>
                <div style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.7)', lineHeight: '1.4' }}>
                  {role.description}
                </div>
              </div>
            );
          })}
        </div>

        {/* Custom Role Builder */}
        <div 
          onClick={() => setUseCustom(true)}
          style={{
            padding: '16px',
            borderRadius: '8px',
            background: useCustom ? 'rgba(0, 243, 255, 0.12)' : 'rgba(255,255,255,0.02)',
            border: `1px solid ${useCustom ? '#00f3ff' : 'rgba(255,255,255,0.06)'}`,
            cursor: 'pointer',
            transition: 'all 0.2s ease'
          }}
        >
          <div style={{ fontFamily: 'Orbitron', fontSize: '0.8rem', color: useCustom ? '#00f3ff' : '#fff', fontWeight: 'bold', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>🛠️ CUSTOM SCENARIO / ROLE BUILDER</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <input 
              type="text" 
              placeholder="Role Title (e.g. Ancient Greek Historian)..."
              value={customRoleTitle}
              onChange={(e) => { setCustomRoleTitle(e.target.value); setUseCustom(true); }}
              style={{ background: '#070c14', border: '1px solid rgba(0,243,255,0.2)', color: '#fff', padding: '8px 12px', borderRadius: '4px', fontSize: '0.8rem', outline: 'none' }}
            />
            <textarea 
              placeholder="System prompt instructions for this temporary persona..."
              rows={3}
              value={customPrompt}
              onChange={(e) => { setCustomPrompt(e.target.value); setUseCustom(true); }}
              style={{ background: '#070c14', border: '1px solid rgba(0,243,255,0.2)', color: '#fff', padding: '8px 12px', borderRadius: '4px', fontSize: '0.8rem', outline: 'none', resize: 'vertical' }}
            />
          </div>
        </div>
      </div>

      {/* RIGHT PANEL: Selected Role Details & Launch Controls */}
      <div style={{ flex: '0.8', display: 'flex', flexDirection: 'column', gap: '14px', minWidth: '280px' }}>
        
        {/* Active Simulation Status Card */}
        {activeSimulation && (
          <div style={{ background: 'rgba(0, 243, 255, 0.1)', border: '1px solid #00f3ff', padding: '14px', borderRadius: '8px', boxShadow: '0 0 16px rgba(0, 243, 255, 0.3)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontFamily: 'Orbitron', fontSize: '0.72rem', color: '#00f3ff', fontWeight: 'bold' }}>
                🎭 ACTIVE SCENARIO
              </div>
              <button 
                onClick={onClearSimulation}
                style={{ background: 'rgba(255, 0, 80, 0.2)', border: '1px solid rgba(255, 0, 80, 0.5)', color: '#ff4d6d', borderRadius: '4px', padding: '2px 8px', fontSize: '0.65rem', cursor: 'pointer' }}
              >
                ⎋ Revert
              </button>
            </div>
            <div style={{ fontSize: '0.85rem', fontWeight: 'bold', color: '#fff', marginTop: '6px' }}>
              {activeSimulation.Disorder || activeSimulation.title}
            </div>
            <div style={{ fontSize: '0.68rem', color: '#a0e0ff', marginTop: '4px' }}>
              🛡️ Memory Shield Active: Session events are isolated and will not pollute permanent memory.
            </div>
          </div>
        )}

        {/* Selected Role Summary & Launch Card */}
        <div style={{ background: 'rgba(0, 243, 255, 0.04)', border: '1px solid rgba(0, 243, 255, 0.25)', padding: '18px', borderRadius: '8px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '1.8rem' }}>{useCustom ? '🛠️' : selectedRole.icon}</span>
            <div>
              <div style={{ fontSize: '0.65rem', fontFamily: 'Orbitron', color: '#00f3ff' }}>SELECTED SCENARIO</div>
              <div style={{ fontSize: '1rem', fontWeight: 'bold', color: '#fff' }}>
                {useCustom ? (customRoleTitle || 'Custom Scenario') : selectedRole.title}
              </div>
            </div>
          </div>

          <div style={{ fontSize: '0.75rem', color: '#a0e0ff', lineHeight: '1.4', background: 'rgba(0,0,0,0.3)', padding: '10px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.05)' }}>
            {useCustom ? (customPrompt || 'Enter custom system instructions above...') : selectedRole.systemPrompt}
          </div>

          {!useCustom && (
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
              <strong style={{ color: '#00f3ff' }}>Opening Greeting:</strong> "{selectedRole.suggestedFirstMsg}"
            </div>
          )}

          <div style={{ background: 'rgba(0, 243, 255, 0.06)', padding: '10px', borderRadius: '6px', fontSize: '0.7rem', color: '#a0e0ff', lineHeight: '1.4' }}>
            🛡️ <strong>Memory Shield Enabled:</strong> Conversation turns in this scenario are isolated and will not be saved to Lumax’s permanent memory.
          </div>

          {/* Launch Buttons */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '6px' }}>
            <button 
              onClick={() => handleApply('chat')}
              style={{
                width: '100%',
                padding: '12px',
                background: '#00f3ff',
                color: '#000',
                border: 'none',
                borderRadius: '6px',
                fontFamily: 'Orbitron',
                fontSize: '0.75rem',
                fontWeight: 'bold',
                cursor: 'pointer',
                letterSpacing: '1px',
                boxShadow: '0 0 14px rgba(0, 243, 255, 0.4)',
                transition: 'all 0.2s ease'
              }}
            >
              💬 APPLY & START CHATTING
            </button>

            <button 
              onClick={() => handleApply('xr')}
              style={{
                width: '100%',
                padding: '10px',
                background: 'transparent',
                color: '#00f3ff',
                border: '1px solid #00f3ff',
                borderRadius: '6px',
                fontFamily: 'Orbitron',
                fontSize: '0.72rem',
                fontWeight: 'bold',
                cursor: 'pointer',
                letterSpacing: '1px',
                transition: 'all 0.2s ease'
              }}
            >
              🕶️ APPLY & ENTER XR / VR PORTAL
            </button>
          </div>
        </div>

      </div>

    </div>
  );
};
