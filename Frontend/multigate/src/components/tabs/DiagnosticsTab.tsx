import React, { useState, useEffect } from 'react';

const DIAGNOSTIC_CRITERIA = [
  { id: 'AbnormalBeliefs', label: 'Reality Orientation', question: 'Do you ever find yourself noticing patterns or connections that others seem to miss, or feeling that events have a special significance just for you?' },
  { id: 'SocialDetachment', label: 'Interpersonal Resonance', question: 'In social settings, do you feel like an observer rather than a participant, or find that maintaining close bonds feels more exhausting than rewarding?' },
  { id: 'OddBehavior', label: 'Behavioral Idiosyncrasy', question: 'Have you ever been told that your way of speaking, dressing, or reacting to things is notably different from the norm?' },
  { id: 'Impulsivity', label: 'Action Threshold', question: 'How often do you find yourself committed to a decision or action before you\'ve had a chance to weigh the long-term impact?' },
  { id: 'EmotionalInstability', label: 'Affective Regulation', question: 'Do your emotions ever feel like they have a "mind of their own," shifting rapidly in intensity without a clear external cause?' },
  { id: 'FearAbandonment', label: 'Attachment Security', question: 'In your closest relationships, do you often find yourself hyper-aware of signs that the other person might be pulling away or losing interest?' },
  { id: 'Perfectionism', label: 'Cognitive Rigidity', question: 'Do you feel a significant internal distress if things are not arranged "just right" or if a strictly defined routine is interrupted?' },
  { id: 'Anxiety', label: 'Vigilance Level', question: 'Does your body often feel like it\'s in a state of high alert (racing heart, shallow breathing) even when there is no immediate danger?' },
  { id: 'Depression', label: 'Vitality & Interest', question: 'Have you noticed a persistent "graying out" of the world, where things that once sparked joy now feel heavy or indifferent?' },
  { id: 'Psychosis', label: 'Perceptual Boundary', question: 'Do you ever experience sounds, shadows, or sensations that seem vivid to you but aren\'t perceived by those around you?' },
  { id: 'NegativeSymptoms', label: 'Drive & Volition', question: 'Do you struggle with a sense of "emptiness" in your motivation, finding it difficult to start even simple daily tasks?' },
  { id: 'CognitiveImpairment', label: 'Executive Function', question: 'Do you find it increasingly difficult to filter out distractions, follow complex instructions, or hold multiple pieces of information in your mind?' },
  { id: 'Dissociation', label: 'Consciousness Continuity', question: 'Do you ever lose track of time, feel like you\'re watching yourself from a distance, or find that your surroundings suddenly feel "unreal" or dream-like?' }
];

interface DiagnosticsTabProps {
  onAssimilateDisorder?: (disorderRow: any, mode: 'chat' | 'xr') => void;
  activeSimulation?: any;
  onClearSimulation?: () => void;
}

export const DiagnosticsTab: React.FC<DiagnosticsTabProps> = ({
  onAssimilateDisorder,
  activeSimulation,
  onClearSimulation
}) => {
  const [hoveredDef, setHoveredDef] = useState('Hover over or click any row to inspect & assimilate clinical disorder profiles...');
  const [hoveredCrit, setHoveredCrit] = useState('Hover over any column header or cell to inspect dimension criteria...');
  const [selectedDisorder, setSelectedDisorder] = useState<any | null>(null);
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);

  useEffect(() => {
    fetch('/diagnostic_data.json')
      .then(res => res.json())
      .then(json => {
        setData(json);
        setLoading(false);
      })
      .catch(err => {
        console.error('Failed to load diagnostic_data.json', err);
        setLoading(false);
      });
  }, []);

  const handleRowClick = (row: any) => {
    setSelectedDisorder(row);
    setShowModal(true);
  };

  return (
    <div style={{ display: 'flex', gap: '16px', height: '100%', width: '100%', padding: '16px', boxSizing: 'border-box', overflow: 'hidden', background: '#02050a' }}>
      
      {/* LEFT SIDE: Compact Matrix Table Container */}
      <div style={{ flex: '1.4', minWidth: 0, display: 'flex', flexDirection: 'column', height: '100%', background: 'rgba(5, 12, 22, 0.7)', border: '1px solid rgba(0, 229, 255, 0.15)', borderRadius: '8px', boxShadow: '0 8px 32px rgba(0, 0, 0, 0.6)', overflow: 'hidden' }}>
        
        {loading ? (
          <div style={{ padding: '60px', textAlign: 'center', color: 'var(--accent-cyan)', fontFamily: 'Share Tech Mono' }}>
            LOADING CLINICAL MATRIX FROM DISC...
          </div>
        ) : (
          <div style={{ flex: 1, overflowY: 'auto', overflowX: 'auto', position: 'relative' }}>
            <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: 0, fontSize: '0.68rem', color: '#fff' }}>
              <thead style={{ position: 'sticky', top: 0, zIndex: 100, background: 'var(--bg-panel)' }}>
                <tr style={{ background: '#0a1322', borderBottom: '2px solid var(--accent-cyan)' }}>
                  <th style={{ textAlign: 'left', padding: '8px 10px', fontFamily: 'Orbitron', fontSize: '0.62rem', letterSpacing: '1px', whiteSpace: 'nowrap', width: '22%', background: 'var(--bg-panel)', borderBottom: '2px solid var(--accent-cyan)', borderRight: '1px solid rgba(0, 229, 255, 0.2)', color: 'var(--accent-cyan)' }}>
                    Disorder Profile (Click to Assimilate)
                  </th>
                  {DIAGNOSTIC_CRITERIA.map((c, idx) => (
                    <th 
                      key={idx} 
                      style={{ padding: '6px 2px', borderLeft: '1px solid rgba(255,255,255,0.06)', textAlign: 'center', width: '5.5%', cursor: 'help', background: 'var(--bg-panel)', borderBottom: '2px solid var(--accent-cyan)' }}
                      onMouseEnter={() => {
                        setHoveredCrit(`${c.label} (${c.id})\n\nClinical Criterion:\n${c.question}`);
                      }}
                      onMouseLeave={() => {
                        setHoveredCrit('Hover over any column header or cell to inspect dimension criteria...');
                      }}
                    >
                      <div style={{ writingMode: 'vertical-lr', transform: 'rotate(180deg)', height: '85px', whiteSpace: 'nowrap', margin: '0 auto', fontSize: '0.6rem', padding: '2px 0', color: 'var(--accent-cyan)', fontWeight: 600 }}>
                        {c.label}
                      </div>
                    </th>
                  ))}
                  <th style={{ padding: '6px 2px', borderLeft: '1px solid rgba(255,255,255,0.06)', width: '5.5%', cursor: 'help', background: 'var(--bg-panel)', borderBottom: '2px solid var(--accent-cyan)' }}>
                    <div style={{ writingMode: 'vertical-lr', transform: 'rotate(180deg)', height: '85px', whiteSpace: 'nowrap', margin: '0 auto', fontSize: '0.6rem', padding: '2px 0', color: '#70e0ff', fontWeight: 600 }}>
                      Genetic
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.map((row, idx) => {
                  const isSelected = selectedDisorder?.Disorder === row.Disorder;
                  const isSimulated = activeSimulation?.Disorder === row.Disorder;

                  return (
                    <tr 
                      key={idx} 
                      onClick={() => handleRowClick(row)}
                      style={{ 
                        borderBottom: '1px solid rgba(255,255,255,0.04)', 
                        transition: 'all 0.15s ease',
                        cursor: 'pointer',
                        background: isSimulated ? 'rgba(0, 229, 255, 0.12)' : isSelected ? 'rgba(0, 229, 255, 0.08)' : 'transparent'
                      }}
                      onMouseEnter={() => {
                        setHoveredDef(`[${row.Disorder}] Cluster: ${row.Cluster}\n\nClick row to assimilate this clinical profile into Lumax Persona.\n\nResonance Pattern:\nAbnormal Beliefs: ${row.AbnormalBeliefs || 0} | Social Detachment: ${row.SocialDetachment || 0} | Psychosis: ${row.Psychosis || 0}`);
                      }}
                      onMouseLeave={() => {
                        setHoveredDef('Hover over or click any row to inspect & assimilate clinical disorder profiles...');
                      }}
                    >
                      <td style={{ textAlign: 'left', padding: '6px 10px', fontFamily: 'Orbitron', fontSize: '0.62rem', whiteSpace: 'nowrap', background: isSimulated ? 'rgba(0, 229, 255, 0.25)' : '#070c14', borderRight: '1px solid rgba(0, 229, 255, 0.15)', color: isSimulated ? 'var(--accent-cyan)' : '#e0f8ff', fontWeight: isSimulated ? 'bold' : 'normal' }}>
                        {isSimulated && '🎭 '}
                        {row.Disorder}
                      </td>
                      {DIAGNOSTIC_CRITERIA.map((c, colIdx) => {
                        const val = row[c.id] || 0;
                        let cellStyle: React.CSSProperties = { border: '1px solid rgba(0, 229, 255, 0.06)', textAlign: 'center', fontWeight: 'bold' };
                        if (val === 1) {
                          cellStyle.background = 'rgba(0, 140, 180, 0.35)';
                          cellStyle.color = 'var(--accent-purple)';
                          cellStyle.border = '1px solid rgba(0, 200, 240, 0.3)';
                        } else if (val === 2) {
                          cellStyle.background = 'rgba(0, 229, 255, 0.85)';
                          cellStyle.color = '#002030';
                          cellStyle.boxShadow = '0 0 10px rgba(0, 229, 255, 0.8)';
                          cellStyle.border = '1px solid var(--accent-cyan)';
                          cellStyle.fontWeight = 800;
                        }

                        return (
                          <td 
                            key={colIdx} 
                            style={cellStyle}
                            onMouseEnter={() => {
                              setHoveredCrit(`Dimension: ${c.label} (${c.id}) = Score ${val}\n\nClinical Criterion:\n${c.question}`);
                            }}
                          >
                            {val > 0 && <span style={{ fontSize: '0.62rem' }}>{val}</span>}
                          </td>
                        );
                      })}
                      <td style={{ 
                        border: '1px solid rgba(0, 229, 255, 0.06)', 
                        background: row.Genetic === 2 ? 'rgba(0, 229, 255, 0.85)' : (row.Genetic === 1 ? 'rgba(0, 140, 180, 0.35)' : 'transparent'),
                        boxShadow: row.Genetic === 2 ? '0 0 10px rgba(0, 229, 255, 0.8)' : 'none',
                        textAlign: 'center' 
                      }}>
                        {row.Genetic > 0 ? <div style={{ fontSize: '9px', color: row.Genetic === 2 ? '#002030' : 'var(--accent-purple)', fontWeight: 'bold' }}>{row.Genetic === 2 ? '🧬🧬' : '🧬'}</div> : ''}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* RIGHT SIDE: Header, Active Simulation Controls & Dynamic Definitions */}
      <div style={{ flex: '0.8', display: 'flex', flexDirection: 'column', gap: '12px', overflowY: 'auto', minWidth: '300px' }}>
        
        {/* Active Simulation Status Card */}
        {activeSimulation && (
          <div style={{ background: 'rgba(0, 229, 255, 0.1)', border: '1px solid var(--accent-cyan)', padding: '14px', borderRadius: '8px', boxShadow: '0 0 16px rgba(0, 229, 255, 0.3)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontFamily: 'Orbitron', fontSize: '0.72rem', color: 'var(--accent-cyan)', fontWeight: 'bold' }}>
                🎭 ACTIVE SIMULATION
              </div>
              <button 
                onClick={onClearSimulation}
                style={{ background: 'rgba(255, 0, 80, 0.2)', border: '1px solid rgba(255, 0, 80, 0.5)', color: '#ff4d6d', borderRadius: '4px', padding: '2px 8px', fontSize: '0.65rem', cursor: 'pointer' }}
              >
                ⎋ Revert
              </button>
            </div>
            <div style={{ fontSize: '0.85rem', fontWeight: 'bold', color: '#fff', marginTop: '6px' }}>
              {activeSimulation.Disorder}
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: '4px' }}>
              🛡️ Memory Shield Active: Turn events are isolated and will not pollute permanent memory.
            </div>
          </div>
        )}

        {/* Title & Action Box */}
        <div style={{ background: 'rgba(0, 229, 255, 0.03)', border: '1px solid rgba(0, 229, 255, 0.2)', padding: '16px', borderRadius: '8px' }}>
          <div className="breadcrumb" style={{ fontSize: '0.75rem', color: 'var(--accent-cyan)', letterSpacing: '1px' }}>
            DIAGNOSTIC COMPARISON MATRIX
          </div>
          <div style={{ fontSize: '0.72rem', opacity: 0.8, color: 'var(--text-muted)', marginTop: '6px', lineHeight: '1.4' }}>
            Click any disorder profile row to temporarily assimilate the clinical traits into Lumax Persona for educational exploration.
          </div>
          
          {/* Legend */}
          <div style={{ display: 'flex', gap: '12px', marginTop: '12px', padding: '8px 10px', background: 'rgba(0,0,0,0.4)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.05)', fontSize: '0.65rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '12px', height: '12px', background: 'rgba(0, 140, 180, 0.45)', border: '1px solid var(--accent-purple)', borderRadius: '2px' }}></div>
              <span style={{ color: '#70e0ff' }}>1 = Moderate</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '12px', height: '12px', background: 'rgba(0, 229, 255, 0.85)', boxShadow: '0 0 8px var(--accent-cyan)', borderRadius: '2px' }}></div>
              <span style={{ color: 'var(--accent-cyan)', fontWeight: 'bold' }}>2 = Severe Flare</span>
            </div>
          </div>
        </div>

        {/* Selected Disorder Card */}
        {selectedDisorder && (
          <div style={{ background: 'rgba(0, 229, 255, 0.03)', backdropFilter: 'blur(12px)', border: '1px solid rgba(0, 229, 255, 0.3)', padding: '14px', borderRadius: '8px' }}>
            <div style={{ fontSize: '0.68rem', fontFamily: 'Orbitron', color: 'var(--accent-cyan)' }}>SELECTED PROFILE FOR ASSIMILATION</div>
            <div style={{ fontSize: '0.95rem', fontWeight: 'bold', color: '#fff', margin: '4px 0' }}>{selectedDisorder.Disorder}</div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '10px' }}>Cluster: {selectedDisorder.Cluster}</div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <button 
                onClick={() => onAssimilateDisorder && onAssimilateDisorder(selectedDisorder, 'chat')}
                style={{ flex: 1, padding: '8px 10px', background: 'var(--accent-cyan)', color: '#000', border: 'none', borderRadius: '4px', fontWeight: 'bold', fontSize: '0.68rem', cursor: 'pointer' }}
              >
                💬 Chat Simulation
              </button>
              <button 
                onClick={() => onAssimilateDisorder && onAssimilateDisorder(selectedDisorder, 'xr')}
                style={{ flex: 1, padding: '8px 10px', background: 'rgba(0,0,0,0.5)', color: 'var(--accent-cyan)', border: '1px solid var(--accent-cyan)', borderRadius: '4px', fontWeight: 'bold', fontSize: '0.68rem', cursor: 'pointer' }}
              >
                🕶️ WebXR Experience
              </button>
            </div>
          </div>
        )}

        {/* Dynamic Criteria Definition Panel */}
        <div style={{ background: 'rgba(0, 229, 255, 0.02)', backdropFilter: 'blur(12px)', padding: '14px', borderRadius: '8px', border: '1px solid rgba(0, 229, 255, 0.2)', fontSize: '0.75rem', flex: 1, display: 'flex', flexDirection: 'column' }}>
          <div style={{ color: 'var(--accent-cyan)', fontFamily: 'Orbitron', fontWeight: 700, fontSize: '0.7rem', letterSpacing: '1px', marginBottom: '8px' }}>
            🔬 CRITERIA DIMENSION
          </div>
          <div style={{ opacity: 0.9, fontFamily: 'Share Tech Mono', color: 'var(--text-main)', whiteSpace: 'pre-wrap', lineHeight: '1.5', flex: 1, overflowY: 'auto' }}>
            {hoveredCrit}
          </div>
        </div>

        {/* Dynamic Clinical Detail Panel */}
        <div style={{ background: 'rgba(157, 78, 221, 0.02)', backdropFilter: 'blur(12px)', padding: '14px', borderRadius: '8px', border: '1px solid rgba(157, 78, 221, 0.2)', fontSize: '0.75rem', flex: 1, display: 'flex', flexDirection: 'column' }}>
          <div style={{ color: 'var(--accent-purple)', fontFamily: 'Orbitron', fontWeight: 700, fontSize: '0.7rem', letterSpacing: '1px', marginBottom: '8px' }}>
            📋 CLINICAL DISORDER DETAIL
          </div>
          <div style={{ opacity: 0.9, fontFamily: 'Share Tech Mono', color: 'var(--text-main)', whiteSpace: 'pre-wrap', lineHeight: '1.5', flex: 1, overflowY: 'auto' }}>
            {hoveredDef}
          </div>
        </div>

      </div>

      {/* ASSIMILATION CONFIRMATION MODAL */}
      {showModal && selectedDisorder && (
        <div style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', zIndex: 10000, background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ width: '440px', background: 'var(--bg-panel)', border: '1px solid var(--accent-cyan)', borderRadius: '12px', padding: '24px', boxShadow: '0 0 30px rgba(0, 229, 255, 0.4)', display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ fontFamily: 'Orbitron', fontSize: '0.9rem', color: 'var(--accent-cyan)', fontWeight: 'bold' }}>
              🎭 ASSIMILATE CLINICAL SIMULATION
            </div>
            
            <div style={{ fontSize: '0.85rem', color: '#fff', lineHeight: '1.5' }}>
              Apply <strong>{selectedDisorder.Disorder}</strong> traits to Lumax Persona for an educational simulation session?
            </div>

            <div style={{ background: 'rgba(0, 229, 255, 0.08)', border: '1px solid rgba(0, 229, 255, 0.2)', padding: '12px', borderRadius: '6px', fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: '1.4' }}>
              🛡️ <strong>Memory Shield Enabled:</strong> Conversation turns during this simulation will be isolated and will NOT be saved to Lumax's permanent memory.
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '10px' }}>
              <button 
                onClick={() => {
                  setShowModal(false);
                  if (onAssimilateDisorder) onAssimilateDisorder(selectedDisorder, 'chat');
                }}
                style={{ padding: '12px', background: 'var(--accent-cyan)', color: '#000', border: 'none', borderRadius: '6px', fontWeight: 'bold', fontSize: '0.8rem', cursor: 'pointer', fontFamily: 'Orbitron', letterSpacing: '1px' }}
              >
                💬 START CHAT SIMULATION
              </button>

              <button 
                onClick={() => {
                  setShowModal(false);
                  if (onAssimilateDisorder) onAssimilateDisorder(selectedDisorder, 'xr');
                }}
                style={{ padding: '12px', background: 'transparent', color: 'var(--accent-cyan)', border: '1px solid var(--accent-cyan)', borderRadius: '6px', fontWeight: 'bold', fontSize: '0.8rem', cursor: 'pointer', fontFamily: 'Orbitron', letterSpacing: '1px' }}
              >
                🕶️ EXPERIENCE IN WEBXR PORTAL
              </button>

              <button 
                onClick={() => setShowModal(false)}
                style={{ padding: '8px', background: 'transparent', color: 'var(--text-muted)', border: 'none', borderRadius: '6px', fontSize: '0.75rem', cursor: 'pointer', marginTop: '4px' }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};
