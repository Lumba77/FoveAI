import { useState, useEffect } from 'react';
import './SettingsOverlay.css';

interface Persona {
  id: string;
  name: string;
  baseline_emotion: string;
  response_style: string;
}

interface SettingsOverlayProps {
  isVisible: boolean;
  onClose: () => void;
}

export function SettingsOverlay({ isVisible, onClose }: SettingsOverlayProps) {
  const [status, setStatus] = useState<'Connecting…' | 'Online' | 'Offline' | 'Error'>('Connecting…');
  const [wsUrl, setWsUrl] = useState('ws://127.0.0.1:8000');
  const [xrlfVersion, setXrlfVersion] = useState('—');
  
  const [autoloadAvatar, setAutoloadAvatar] = useState(true);
  const [emotionDriver, setEmotionDriver] = useState(true);
  const [fts5Memory, setFts5Memory] = useState(true);
  const [xrMode, setXrMode] = useState('passthrough');
  
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [activePersona, setActivePersona] = useState('');
  
  const [ws, setWs] = useState<WebSocket | null>(null);

  // Load from localStorage on mount
  useEffect(() => {
    const savedUrl = localStorage.getItem('xrlf_ws_url');
    if (savedUrl) setWsUrl(savedUrl);
    const savedMode = localStorage.getItem('xrlf_xr_mode');
    if (savedMode) setXrMode(savedMode);
    
    const savedAvatar = localStorage.getItem('xrlf_avatar_autoload');
    if (savedAvatar !== null) setAutoloadAvatar(savedAvatar === 'true');
    const savedEmotion = localStorage.getItem('xrlf_emotion_driver');
    if (savedEmotion !== null) setEmotionDriver(savedEmotion === 'true');
    const savedMemory = localStorage.getItem('xrlf_memory_fts5');
    if (savedMemory !== null) setFts5Memory(savedMemory === 'true');
  }, []);

  // Connect WebSocket when visible
  useEffect(() => {
    if (!isVisible) return;
    
    let socket: WebSocket | null = null;
    try {
      setStatus('Connecting…');
      socket = new WebSocket(wsUrl);
      
      socket.onopen = () => {
        setStatus('Online');
        socket?.send(JSON.stringify({ xrlf_version: '3.0', event: 'health', payload: {} }));
        socket?.send(JSON.stringify({ xrlf_version: '3.0', event: 'persona.list', payload: {} }));
      };
      
      socket.onclose = () => setStatus('Offline');
      socket.onerror = () => setStatus('Error');
      
      socket.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.xrlf_version) setXrlfVersion(msg.xrlf_version);
          if (msg.event === 'health' && msg.payload) {
            setXrlfVersion(msg.payload.xrlf_version || '3.0');
          }
          if (msg.event === 'persona.list' && msg.payload) {
            setPersonas(msg.payload.personas || []);
          }
          if (msg.event === 'persona.switched' && msg.payload) {
            setActivePersona(msg.payload.persona_id);
          }
        } catch (e) {
          console.warn('Parse error', e);
        }
      };
      
      setWs(socket);
    } catch (e) {
      setStatus('Error');
    }
    
    return () => {
      if (socket) socket.close();
    };
  }, [isVisible, wsUrl]);

  const sendEvent = (event: string, payload: any) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ xrlf_version: '3.0', event, payload }));
    }
  };

  const handlePersonaSwitch = (id: string) => {
    setActivePersona(id);
    sendEvent('persona.switch', { persona_id: id });
  };

  const handleApply = () => {
    localStorage.setItem('xrlf_ws_url', wsUrl);
    localStorage.setItem('xrlf_xr_mode', xrMode);
    localStorage.setItem('xrlf_avatar_autoload', String(autoloadAvatar));
    localStorage.setItem('xrlf_emotion_driver', String(emotionDriver));
    localStorage.setItem('xrlf_memory_fts5', String(fts5Memory));
    
    // Dispatch a storage event manually if other parts of the app need to react to these changes
    window.dispatchEvent(new Event('storage'));
    
    onClose();
  };

  if (!isVisible) return null;

  return (
    <div className="settings-overlay-backdrop">
      <div className="settings-panel">
        <h1>🦋 XRLF 3.0 Spatial Machine</h1>
        <div className="subtitle">Unified Cognitive Engine — Settings Overlay</div>

        <div className="section">
          <h2>Connection</h2>
          <div className="row">
            <label>
              <span className={`status-dot ${status === 'Online' ? 'online' : status === 'Connecting…' ? 'connecting' : 'offline'}`}></span>
              Backend Status
            </label>
            <span className="value">{status}</span>
          </div>
          <div className="row">
            <label>WebSocket URL</label>
            <input type="text" value={wsUrl} onChange={(e) => setWsUrl(e.target.value)} />
          </div>
          <div className="row">
            <label>XRLF Version</label>
            <span className="value">{xrlfVersion}</span>
          </div>
        </div>

        <div className="section">
          <h2>Avatar</h2>
          <div className="row">
            <label>Companion Model</label>
            <span className="value">Alicechan.vrm</span>
          </div>
          <div className="row">
            <label>Auto-Load Avatar on Boot</label>
            <div className={`toggle ${autoloadAvatar ? 'on' : ''}`} onClick={() => setAutoloadAvatar(!autoloadAvatar)}></div>
          </div>
          <div className="row">
            <label>Blendshape Emotion Driver</label>
            <div className={`toggle ${emotionDriver ? 'on' : ''}`} onClick={() => setEmotionDriver(!emotionDriver)}></div>
          </div>
        </div>

        <div className="section">
          <h2>Persona</h2>
          <div className="persona-grid">
            {personas.length === 0 && <span className="value">Loading…</span>}
            {personas.map(p => (
              <div 
                key={p.id} 
                className={`persona-card ${p.id === activePersona ? 'active' : ''}`}
                onClick={() => handlePersonaSwitch(p.id)}
              >
                <div className="name">{p.name}</div>
                <div className="emotion">{p.baseline_emotion} · {p.response_style}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="section">
          <h2>XR Mode</h2>
          <div className="row">
            <label>Default Runtime</label>
            <select value={xrMode} onChange={(e) => setXrMode(e.target.value)}>
              <option value="passthrough">Meta Quest 3 Passthrough (WebXR)</option>
              <option value="desktop">Desktop WebApp Fallback</option>
            </select>
          </div>
          <div className="row">
            <label>Foveated Memory (FTS5)</label>
            <div className={`toggle ${fts5Memory ? 'on' : ''}`} onClick={() => setFts5Memory(!fts5Memory)}></div>
          </div>
        </div>

        <div className="footer">
          <button className="btn danger" onClick={onClose}>Close</button>
          <button className="btn" onClick={handleApply}>Apply</button>
        </div>
        <div className="hint">Summon this panel via Quest 3 controller menu button or desktop keyboard shortcut (Shift+M).</div>
      </div>
    </div>
  );
}
