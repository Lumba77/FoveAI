import React, { useState } from 'react';

export const CanvasTab: React.FC = () => {
  const [prompt, setPrompt] = useState('');
  const [engine, setEngine] = useState('turbo');
  const [ratio, setRatio] = useState('1:1');
  const [uploadedImage, setUploadedImage] = useState<string | null>(null);
  const [isForging, setIsForging] = useState(false);
  const [resultImage, setResultImage] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (re) => {
        setUploadedImage(re.target?.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleClearImage = () => {
    setUploadedImage(null);
    const fileInput = document.getElementById('dream-file') as HTMLInputElement;
    if (fileInput) fileInput.value = '';
  };

  const handleForge = () => {
    if (!prompt.trim()) return;
    setIsForging(true);
    // Placeholder logic for API call
    setTimeout(() => {
      setIsForging(false);
      // We don't have a real image to show yet, but this proves the UI state works
      setResultImage('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400"><rect width="400" height="400" fill="%230a0f19"/><text x="200" y="200" font-family="Orbitron" font-size="20" fill="%2300f3ff" text-anchor="middle" dominant-baseline="middle">API NOT CONNECTED</text></svg>');
    }, 2000);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%' }}>
      <style>
        {`
          @keyframes spin { to { transform: rotate(360deg); } }
        `}
      </style>
      <div className="breadcrumb" style={{ padding: '15px 20px', borderBottom: '1px solid var(--border)' }}>
        DREAMSCAPE // ART_GENERATOR
      </div>
      
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '15px', minHeight: 0, overflowY: 'auto', padding: '20px' }}>
        <div className="glass-card" style={{ padding: '20px', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '8px' }}>
          <label style={{ fontFamily: 'Orbitron', fontSize: '0.65rem', color: 'var(--neon-blue)', display: 'block', marginBottom: '10px' }}>PROMPT DESCRIPTION</label>
          <textarea 
            rows={3} 
            style={{ width: '100%', background: 'rgba(0,0,0,0.4)', border: '1px solid var(--border)', color: '#fff', padding: '12px', borderRadius: '4px', fontFamily: 'inherit', fontSize: '0.9rem', outline: 'none', resize: 'vertical' }} 
            placeholder="A neon-lit cyberpunk city under a violet sky..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          
          <div style={{ marginTop: '15px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
            <div>
              <label style={{ fontFamily: 'Orbitron', fontSize: '0.55rem', color: 'rgba(255,255,255,0.5)', display: 'block', marginBottom: '5px' }}>MODEL ENGINE</label>
              <select value={engine} onChange={(e) => setEngine(e.target.value)} style={{ width: '100%', background: '#0a0f19', border: '1px solid var(--border)', color: '#fff', padding: '8px', borderRadius: '4px', fontFamily: 'Share Tech Mono', fontSize: '0.75rem' }}>
                <option value="turbo">SDXL Turbo (Fast)</option>
                <option value="sd15">Stable Diffusion 1.5</option>
                <option value="control">ControlNet Structure</option>
                <option value="upscale">Real-ESRGAN Upscale</option>
              </select>
            </div>
            <div>
              <label style={{ fontFamily: 'Orbitron', fontSize: '0.55rem', color: 'rgba(255,255,255,0.5)', display: 'block', marginBottom: '5px' }}>RATIO</label>
              <select value={ratio} onChange={(e) => setRatio(e.target.value)} style={{ width: '100%', background: '#0a0f19', border: '1px solid var(--border)', color: '#fff', padding: '8px', borderRadius: '4px', fontFamily: 'Share Tech Mono', fontSize: '0.75rem' }}>
                <option value="1:1">1:1 Square</option>
                <option value="16:9">16:9 Cinema</option>
                <option value="9:16">9:16 Mobile</option>
              </select>
            </div>
          </div>

          <div style={{ marginTop: '15px' }}>
            <label style={{ fontFamily: 'Orbitron', fontSize: '0.55rem', color: 'rgba(255,255,255,0.5)', display: 'block', marginBottom: '5px' }}>IMAGE-TO-IMAGE (OPTIONAL)</label>
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              <input type="file" id="dream-file" accept="image/*" onChange={handleFileChange} style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.5)' }} />
              {uploadedImage && (
                <button onClick={handleClearImage} style={{ background: 'transparent', border: '1px solid rgba(255,255,255,0.2)', color: '#fff', fontSize: '0.6rem', padding: '4px 8px', cursor: 'pointer', borderRadius: '3px' }}>CLEAR</button>
              )}
            </div>
            {uploadedImage && (
              <img src={uploadedImage} style={{ maxWidth: '100px', maxHeight: '100px', marginTop: '10px', border: '1px solid var(--neon-blue)', borderRadius: '4px' }} alt="Upload preview" />
            )}
          </div>

          <button 
            className="neon-btn" 
            onClick={handleForge}
            disabled={isForging || !prompt.trim()}
            style={{ width: '100%', padding: '15px', background: 'var(--neon-pink)', color: '#fff', border: 'none', borderRadius: '4px', fontFamily: 'Orbitron', fontWeight: 700, letterSpacing: '2px', cursor: (isForging || !prompt.trim()) ? 'not-allowed' : 'pointer', marginTop: '20px', boxShadow: '0 0 15px var(--neon-pink)', opacity: (isForging || !prompt.trim()) ? 0.5 : 1 }}
          >
            {isForging ? 'FORGING...' : 'FORGE VISION'}
          </button>
        </div>

        <div className="glass-card" style={{ flex: 1, minHeight: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative', overflow: 'hidden', background: 'rgba(0,0,0,0.4)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
          {!isForging && !resultImage && (
            <div style={{ textAlign: 'center', opacity: 0.5 }}>
              <div style={{ fontSize: '2rem', marginBottom: '10px' }}>✨</div>
              <div style={{ fontFamily: 'Orbitron', fontSize: '0.7rem' }}>AWAITING ARTILLERY COMMAND</div>
            </div>
          )}
          
          {isForging && (
            <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 10, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{ width: '40px', height: '40px', border: '3px solid var(--neon-blue)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
              <div style={{ marginTop: '15px', fontFamily: 'Orbitron', fontSize: '0.7rem', color: 'var(--neon-blue)', letterSpacing: '2px' }}>FORGING NEURAL ARTIFACT...</div>
            </div>
          )}
          
          {resultImage && !isForging && (
            <img src={resultImage} style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', boxShadow: '0 0 30px rgba(0,243,255,0.2)' }} alt="Result" />
          )}
        </div>
      </div>
    </div>
  );
};
