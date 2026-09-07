import React, { useState } from 'react';

const presetSounds = [
  { id: 'gasp_subtle', label: 'Subtle Gasp', icon: '😮' },
  { id: 'laugh_soft', label: 'Soft Laugh', icon: '🤭' },
  { id: 'sigh_content', label: 'Content Sigh', icon: '😌' },
  { id: 'hmm_thoughtful', label: 'Thoughtful Hmm', icon: '🤔' },
  { id: 'oh_realization', label: 'Realization Oh', icon: '😲' },
  { id: 'throat_clear', label: 'Throat Clear', icon: '🤨' },
  { id: 'chuckle_warm', label: 'Warm Chuckle', icon: '😊' },
  { id: 'mhm_affirming', label: 'Affirming Mhm', icon: '👍' },
  { id: 'windchime_subtle', label: 'Windchime', icon: '🎐' }
];

export const SoundboardTab: React.FC = () => {
  const [playing, setPlaying] = useState<string | null>(null);
  const [generatePrompt, setGeneratePrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [generatedSounds, setGeneratedSounds] = useState<any[]>([]);

  const playSound = (id: string, urlPath: string) => {
    setPlaying(id);
    const audio = new Audio(urlPath);
    audio.onended = () => setPlaying(null);
    audio.play().catch(err => {
      console.warn('Failed to play audio:', err);
      setPlaying(null);
    });
  };

  const handleGenerate = () => {
    if (!generatePrompt) return;
    setIsGenerating(true);

    fetch('/api/soundboard/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description: generatePrompt })
    })
      .then(res => res.json())
      .then(data => {
        setIsGenerating(false);
        if (data && (data.url || data.tag)) {
          setGeneratedSounds([...generatedSounds, { 
            id: data.tag || `gen_${Date.now()}`, 
            label: generatePrompt.substring(0, 20) + '...', 
            url: data.url || `/soundboard/${data.tag}.wav` 
          }]);
        }
        setGeneratePrompt('');
      })
      .catch(err => {
        console.error('Generation failed:', err);
        setIsGenerating(false);
      });
  };

  return (
    <div style={{ padding: '20px', height: '100%', overflowY: 'auto' }}>
      <div className="breadcrumb">VOICE & SOUNDBOARD (STABLE AUDIO)</div>
      <p style={{ fontSize: '0.75rem', opacity: 0.7, marginBottom: '20px', color: 'var(--neon-blue)' }}>
        Trigger emotive non-verbal expressions or synthesize brand new acoustic responses.
      </p>

      {/* Generation Panel */}
      <div className="glass-card" style={{ padding: '20px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)', marginBottom: '25px' }}>
        <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 15px 0', fontSize: '0.9rem', color: 'var(--neon-pink)', letterSpacing: '2px' }}>FORGE SOUND (AI SYNTHESIS)</h4>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <input 
            type="text" 
            placeholder="Describe the sound (e.g. 'A robotic purr', 'Soft digital wind')..." 
            value={generatePrompt}
            onChange={e => setGeneratePrompt(e.target.value)}
            disabled={isGenerating}
            style={{ flex: 1, padding: '12px', background: 'rgba(0,0,0,0.3)', border: '1px solid var(--neon-pink)', color: '#fff', fontFamily: 'Share Tech Mono', outline: 'none', borderRadius: '4px' }}
          />
          <button 
            onClick={handleGenerate}
            disabled={isGenerating || !generatePrompt.trim()}
            className="neon-btn"
            style={{ padding: '12px 24px', background: isGenerating ? 'rgba(255,0,127,0.2)' : 'var(--neon-pink)', color: isGenerating ? 'var(--neon-pink)' : '#fff', border: 'none', cursor: isGenerating ? 'default' : 'pointer', fontFamily: 'Orbitron', fontWeight: 700, borderRadius: '4px' }}
          >
            {isGenerating ? 'SYNTHESIZING...' : 'GENERATE'}
          </button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
        {/* Core Expressions */}
        <div className="glass-card" style={{ flex: 2, minWidth: '350px', padding: '20px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}>
          <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 20px 0', fontSize: '0.9rem', color: 'var(--neon-blue)', letterSpacing: '2px' }}>CORE EXPRESSIONS</h4>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: '15px' }}>
            {presetSounds.map(s => (
              <button 
                key={s.id}
                onClick={() => playSound(s.id, `/soundboard/${s.id}.wav`)}
                style={{
                  display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '8px',
                  padding: '15px 10px', background: playing === s.id ? 'var(--neon-blue)' : 'rgba(0,243,255,0.05)',
                  border: `1px solid ${playing === s.id ? '#fff' : 'rgba(0,243,255,0.3)'}`,
                  color: playing === s.id ? '#000' : 'var(--neon-blue)',
                  borderRadius: '6px', cursor: 'pointer', transition: 'all 0.2s'
                }}
              >
                <span style={{ fontSize: '1.8rem' }}>{s.icon}</span>
                <span style={{ fontFamily: 'Share Tech Mono', fontSize: '0.7rem', textAlign: 'center', fontWeight: playing === s.id ? 700 : 'normal' }}>
                  {s.label.toUpperCase()}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Dynamic & Generated */}
        <div className="glass-card" style={{ flex: 1, minWidth: '250px', padding: '20px', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', borderRadius: '4px', boxShadow: '0 10px 30px rgba(0,0,0,0.5)' }}>
          <h4 style={{ fontFamily: 'Orbitron', margin: '0 0 20px 0', fontSize: '0.9rem', color: 'var(--neon-green)', letterSpacing: '2px' }}>SYNTHESIZED</h4>
          
          {generatedSounds.length === 0 ? (
            <div style={{ color: 'rgba(255,255,255,0.4)', fontFamily: 'Share Tech Mono', fontSize: '0.8rem', textAlign: 'center', padding: '20px' }}>
              No dynamic sounds generated yet.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {generatedSounds.map(s => (
                <button 
                  key={s.id}
                  onClick={() => playSound(s.id, s.url)}
                  style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '12px 15px', background: playing === s.id ? 'var(--neon-green)' : 'rgba(57,255,20,0.05)',
                    border: `1px solid ${playing === s.id ? '#fff' : 'rgba(57,255,20,0.3)'}`,
                    color: playing === s.id ? '#000' : 'var(--neon-green)',
                    borderRadius: '4px', cursor: 'pointer', fontFamily: 'Share Tech Mono', transition: 'all 0.2s'
                  }}
                >
                  <span style={{ fontSize: '0.75rem', fontWeight: playing === s.id ? 700 : 'normal' }}>{s.label}</span>
                  <span>▶</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
