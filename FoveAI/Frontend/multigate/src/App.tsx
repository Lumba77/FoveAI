import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import AvatarOverlay from './AvatarOverlay';
import { CanvasTab } from './components/tabs/CanvasTab';
import { DiagnosticsTab } from './components/tabs/DiagnosticsTab';
import { AgencyTab } from './components/tabs/AgencyTab';
import { MonetizationTab } from './components/tabs/MonetizationTab';
import { PersonaTab } from './components/tabs/PersonaTab';
import { SoundboardTab } from './components/tabs/SoundboardTab';
import { RoleplayTab } from './components/tabs/RoleplayTab';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

interface User {
  username: string;
  role: string;
  apiKey?: string;
  firstName?: string;
  lastName?: string;
  aiName?: string;
}

function App() {
  const [currentUser, setCurrentUser] = useState<User | null>(() => {
    try {
      const saved = localStorage.getItem('foveai_foveai_user');
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.firstName && parsed.aiName) return parsed;
      }
      return null;
    } catch (e) {
      return null;
    }
  });

  const [showSetup, setShowSetup] = useState(() => !currentUser);

  // Persist login state to localStorage
  useEffect(() => {
    if (currentUser) {
      localStorage.setItem('foveai_foveai_user', JSON.stringify(currentUser));
      setShowSetup(false);
    } else {
      localStorage.removeItem('foveai_foveai_user');
    }
  }, [currentUser]);

  // Setup Form State
  const [firstNameInput, setFirstNameInput] = useState('');
  const [lastNameInput, setLastNameInput] = useState('');
  const [aiNameInput, setAiNameInput] = useState('');
  const [setupError, setSetupError] = useState('');

  // Auth Form State
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [usernameInput, setUsernameInput] = useState('');
  const [passwordInput, setPasswordInput] = useState('');
  const [authError, setAuthError] = useState('');
  const [isAuthLoading, setIsAuthLoading] = useState(false);
  
  // Chat State
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: 'Welcome to your private FoveAI Copilot. How can I assist your workflow today?' }
  ]);
  const [activeTab, setActiveTab] = useState('Copilot');
  const [showAvatar, setShowAvatar] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [proxyStatus, setProxyStatus] = useState<'checking' | 'online' | 'offline'>('checking');
  const [activeSimulation, setActiveSimulation] = useState<any | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>('auto');
  const [availableModels, setAvailableModels] = useState<any[]>([]);
  const [chatProvider, setChatProvider] = useState<'xrlf_proxy' | 'lmstudio' | 'cloud'>('xrlf_proxy');

  // Provider-isolated model fleets
  // XRLF Proxy = default (local XRLF runtime on :8402)
  // LM Studio = local GGUF loader on :1234
  // Cloud = opt-in only (requires API key configured in settings)
  const MODEL_FLEETS: Record<string, { id: string; label: string }[]> = {
    xrlf_proxy: [
      { id: 'foveai-pfoveai-omni-router',     label: '🧠 XRLF Omni Router v1 (940MB)' },
      { id: 'foveai-pfoveai-omni-router-v2',  label: '🧠 XRLF Omni Router v2 (1.3GB)' },
      { id: 'no2-foveai-pfoveai-omni-router', label: '🧠 XRLF Omni Router No2 (32K ctx)' },
    ],
    lmstudio: [
      { id: 'qwopus3.5-9b-coder-mtp-moq',           label: '💻 QwOpus 3.5 9B Coder' },
      { id: 'qwen3.5-4b-moq',                       label: '💻 Qwen MoQ 4B (32K ctx)' },
      { id: 'w-ahmad/gemma-4-12b-it-qat-gguf-moq/moq-3.5.gguf', label: '💻 Gemma 4 12B MoQ' },
    ],
    cloud: [
      { id: 'auto',          label: '☁️ Cloud Auto-Route (requires API key)' },
    ],
  };
  const [deepThink, setDeepThink] = useState(false);
  const [contextBudget, setContextBudget] = useState(16000);
  const [compressionLevel, setCompressionLevel] = useState(3);

  // Audio PTT state & refs
  const [isRecording, setIsRecording] = useState(false);
  const [isProcessingAudio, setIsProcessingAudio] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // Open/collapsed state for main category accordions
  const [openCategories, setOpenCategories] = useState<Record<string, boolean>>({
    'AGENCY & INTELLIGENCE': true,
    'DEVELOPMENT SUITE': false,
    'SENSES & REVENUE': false,
    'EDUTAINMENT': false
  });

  const siteName = window.location.hostname.toUpperCase();
  const proxyPort = import.meta.env.VITE_PROXY_PORT || '8400';

  const handleAssimilateDisorder = (disorderRow: any, mode: 'chat' | 'xr') => {
    setActiveSimulation(disorderRow);
    if (mode === 'chat') {
      setActiveTab('Copilot');
    } else {
      const protocol = window.location.protocol;
      const hostname = window.location.hostname;
      window.open(`${protocol}//${hostname}:5176`, '_blank');
    }
  };

  const handleClearSimulation = () => {
    setActiveSimulation(null);
  };
  
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  // Check Foveated Memory Proxy Health
  useEffect(() => {
    if (!currentUser) return;
    
    const checkHealth = async () => {
      try {
        const res = await fetch('/api/foveated/health');
        if (res.ok) {
          setProxyStatus('online');
          const data = await res.json();
          if (data && data.voice_enabled !== undefined) {
            localStorage.setItem('foveai_voice_speech', String(data.voice_enabled));
          }
        } else {
          setProxyStatus('offline');
        }
      } catch (e) {
        setProxyStatus('offline');
      }
    };
    
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, [currentUser]);

  // Fetch available models from the active provider
  useEffect(() => {
    if (!currentUser) return;
    const fetchModels = async () => {
      try {
        if (chatProvider === 'cloud') {
          // Cloud models from proxy
          const res = await fetch('/api/foveated/v1/models', {
            headers: { 'Authorization': `Bearer ${currentUser.apiKey || currentUser.username}` }
          });
          if (res.ok) {
            const data = await res.json();
            if (data && data.data) setAvailableModels(data.data);
          }
        } else if (chatProvider === 'lmstudio') {
          // LM Studio models from :1234
          const res = await fetch('http://127.0.0.1:1234/v1/models');
          if (res.ok) {
            const data = await res.json();
            if (data && data.data) setAvailableModels(data.data);
          }
        } else {
          // XRLF proxy models — static fleet for now
          setAvailableModels(MODEL_FLEETS.xrlf_proxy.map(m => ({ id: m.id, object: 'model', owned_by: 'xrlf' })));
        }
      } catch (e) {
        console.warn('Failed to fetch models', e);
        // Fallback to static fleet
        const fleet = MODEL_FLEETS[chatProvider] || MODEL_FLEETS.xrlf_proxy;
        setAvailableModels(fleet.map(m => ({ id: m.id, object: 'model', owned_by: chatProvider })));
      }
    };
    fetchModels();
  }, [currentUser, chatProvider]);

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!usernameInput.trim() || !passwordInput.trim()) return;
    
    setIsAuthLoading(true);
    setAuthError('');
    
    try {
      const endpoint = authMode === 'register' ? '/api/foveated/v1/auth/register' : '/api/foveated/v1/auth/login';
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: usernameInput.trim(),
          password: passwordInput
        })
      });
      
      const data = await res.json();
      
      if (!res.ok) {
        setAuthError(data.error || 'Authentication failed');
      } else {
        setCurrentUser({
          username: data.username,
          role: usernameInput.trim().toLowerCase() === 'admin' ? 'Admin' : 'Beta Tester',
          apiKey: data.apiKey
        });
        setUsernameInput('');
        setPasswordInput('');
      }
    } catch (err) {
      setAuthError('Failed to connect to authentication server');
    } finally {
      setIsAuthLoading(false);
    }
  };

  const handleLogout = () => {
    setCurrentUser(null);
    setShowSetup(false);
    setMessages([{ role: 'assistant', content: 'Session closed.' }]);
  };

  const handleSetup = (e: React.FormEvent) => {
    e.preventDefault();
    if (!firstNameInput.trim() || !lastNameInput.trim() || !aiNameInput.trim()) {
      setSetupError('Please fill in all fields');
      return;
    }
    const fullName = `${firstNameInput.trim()} ${lastNameInput.trim()}`;
    const newUser: User = {
      username: fullName,
      firstName: firstNameInput.trim(),
      lastName: lastNameInput.trim(),
      aiName: aiNameInput.trim(),
      role: 'Admin',
      apiKey: 'foveai_operator'
    };
    localStorage.setItem('foveai_foveai_user', JSON.stringify(newUser));
    setCurrentUser(newUser);
    setMessages([{ role: 'assistant', content: `Welcome, ${firstNameInput.trim()}. I am ${aiNameInput.trim()}. How can I help you today?` }]);
    setFirstNameInput('');
    setLastNameInput('');
    setAiNameInput('');
    setSetupError('');
    setShowSetup(false);
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim() || !currentUser) return;
    
    const userMsg: Message = { role: 'user', content: inputValue };
    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setIsTyping(true);

    try {
      const recentMessages = messages.slice(-15);
      const payloadMessages = activeSimulation ? [
        { role: 'system', content: `[EPHEMERAL CLINICAL SIMULATION: ${activeSimulation.Disorder} | Cluster: ${activeSimulation.Cluster} | MEMORY SHIELD: ACTIVE - DO NOT SAVE TURNS TO PERMANENT MEMORY]` },
        ...recentMessages,
        userMsg
      ] : [...recentMessages, userMsg];

      const response = await fetch('/api/foveated/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${currentUser.apiKey || currentUser.username}`,
          'X-Memory-Shield': activeSimulation ? 'true' : 'false',
          'X-Deep-Think': deepThink ? 'true' : 'false',
          'X-Context-Budget': String(contextBudget),
          'X-Compression-Level': String(compressionLevel)
        },
        body: JSON.stringify({
          model: selectedModel,
          messages: payloadMessages,
          stream: false
        })
      });

      const data = await response.json();
      const botReply = data.choices?.[0]?.message?.content;
      const fallback = data.error?.message || `Proxy error ${response.status}`;
      
      setMessages(prev => [...prev, { role: 'assistant', content: botReply || fallback }]);
    } catch (err) {
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: `FoveAI Proxy error (Port ${proxyPort}). Details: ${String(err)}` 
      }]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // ----------------------------------------------------
  // RENDER SETUP SCREEN
  // ----------------------------------------------------
  if (showSetup) {
    return (
      <div className="auth-screen">
        <div className="glass-panel auth-card">
          <div className="auth-header">
            <h1>{siteName}</h1>
            <p>Configure your profile and AI companion</p>
          </div>
          <form className="auth-form" onSubmit={handleSetup}>
            {setupError && <div className="auth-error" style={{ color: '#ff6b6b', background: 'rgba(255, 107, 107, 0.1)', padding: '10px', borderRadius: '6px', marginBottom: '15px', fontSize: '0.9rem' }}>{setupError}</div>}
            <h3 style={{ margin: '10px 0 5px', color: 'var(--accent-cyan)', fontFamily: 'Orbitron', fontSize: '0.95rem' }}>Configure User</h3>
            <div className="input-group">
              <label>First Name</label>
              <input
                type="text"
                placeholder="Your first name..."
                value={firstNameInput}
                onChange={e => setFirstNameInput(e.target.value)}
                autoFocus
              />
            </div>
            <div className="input-group">
              <label>Last Name</label>
              <input
                type="text"
                placeholder="Your last name..."
                value={lastNameInput}
                onChange={e => setLastNameInput(e.target.value)}
              />
            </div>
            <h3 style={{ margin: '15px 0 5px', color: 'var(--accent-cyan)', fontFamily: 'Orbitron', fontSize: '0.95rem' }}>Configure AI</h3>
            <div className="input-group">
              <label>AI Name</label>
              <input
                type="text"
                placeholder="e.g. Lumax, Aria..."
                value={aiNameInput}
                onChange={e => setAiNameInput(e.target.value)}
              />
            </div>
            <button type="submit" className="btn-primary">Enter</button>
          </form>
        </div>
      </div>
    );
  }

  // ----------------------------------------------------
  // RENDER AUTH SCREEN
  // ----------------------------------------------------
  if (!currentUser) {
    return (
      <div className="auth-screen">
        <div className="glass-panel auth-card">
          <div className="auth-header">
            <h1>{siteName}</h1>
            <p>Intelligence Nexus Portal</p>
          </div>
          
          <form className="auth-form" onSubmit={handleAuth}>
            {authError && <div className="auth-error" style={{ color: '#ff6b6b', background: 'rgba(255, 107, 107, 0.1)', padding: '10px', borderRadius: '6px', marginBottom: '15px', fontSize: '0.9rem' }}>{authError}</div>}
            <div className="input-group">
              <label>Username</label>
              <input 
                id="username"
                name="username"
                type="text" 
                placeholder="Enter unique ID..."
                value={usernameInput}
                onChange={e => setUsernameInput(e.target.value)}
                autoComplete="username"
                autoFocus
                disabled={isAuthLoading}
              />
            </div>
            
            <div className="input-group">
              <label>Password</label>
              <input 
                id="password"
                name="password"
                type="password" 
                placeholder="••••••••"
                value={passwordInput}
                onChange={e => setPasswordInput(e.target.value)}
                autoComplete="current-password"
                disabled={isAuthLoading}
              />
            </div>
            
            <button type="submit" className="btn-primary" disabled={isAuthLoading}>
              {isAuthLoading ? 'Please wait...' : (authMode === 'login' ? 'Authenticate' : 'Register Beta Account')}
            </button>
          </form>
          
          <div style={{ textAlign: 'center', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
            {authMode === 'login' ? (
              <p>New tester? <span style={{ color: 'var(--accent-cyan)', cursor: 'pointer' }} onClick={() => { setAuthMode('register'); setAuthError(''); }}>Register here</span></p>
            ) : (
              <p>Already registered? <span style={{ color: 'var(--accent-purple)', cursor: 'pointer' }} onClick={() => { setAuthMode('login'); setAuthError(''); }}>Log in</span></p>
            )}
          </div>

          <div style={{ marginTop: '20px', paddingTop: '20px', borderTop: '1px solid rgba(255,255,255,0.1)', textAlign: 'center' }}>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '10px' }}>Other Services</p>
            <a 
              href="intent://xarel.net/enter-xr#Intent;package=com.foveai.alicevr;action=android.intent.action.MAIN;category=android.intent.category.LAUNCHER;end" 
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'inline-block',
                background: 'rgba(0, 243, 255, 0.1)',
                border: '1px solid rgba(0, 243, 255, 0.3)',
                color: 'var(--accent-cyan)',
                textDecoration: 'none',
                padding: '8px 16px',
                borderRadius: '20px',
                fontSize: '0.85rem',
                fontWeight: 'bold',
                transition: 'all 0.2s'
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(0, 243, 255, 0.2)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(0, 243, 255, 0.1)'; }}
            >
              🕶️ Enter XR Portal
            </a>
          </div>
        </div>
      </div>
    );
  }

  // ----------------------------------------------------
  // RENDER FULL-SCREEN Overlays
  // ----------------------------------------------------
  if (activeTab === 'WebVM' || activeTab === 'NativeIDE') {
    const isWebVM = activeTab === 'WebVM';
    const title = isWebVM ? "Linux WebVM (In-Browser OS)" : "FoveAI Terminal IDE (Native Python)";
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    // Use the same protocol and hostname to prevent Mixed Content security warnings
    const srcUrl = isWebVM ? `${protocol}//${hostname}:5176/webvm/` : `${protocol}//${hostname}:8085`;

    return (
      <div style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', zIndex: 9999, background: '#000' }}>
        <button 
          onClick={() => setActiveTab('Copilot')} 
          style={{
            position: 'absolute', top: '15px', right: '20px', zIndex: 10000, 
            background: 'rgba(0,0,0,0.5)', color: '#fff', border: '1px solid rgba(0, 240, 255, 0.5)', 
            padding: '8px 16px', borderRadius: '6px', cursor: 'pointer',
            backdropFilter: 'blur(10px)', fontSize: '14px', fontWeight: 'bold',
            boxShadow: '0 4px 6px rgba(0,0,0,0.3)', transition: 'all 0.2s'
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(0, 240, 255, 0.2)'; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = 'rgba(0,0,0,0.5)'; }}
        >
          ⎋ Exit Fullscreen
        </button>
        <iframe 
          src={srcUrl} 
          style={{ width: '100%', height: '100%', border: 'none' }} 
          sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
          title={title}
        />
      </div>
    );
  }

  const startRecording = async () => {
    if (isTyping || isProcessingAudio) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        setIsProcessingAudio(true);
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        
        // Stop all tracks
        stream.getTracks().forEach(t => t.stop());

        if (audioBlob.size < 2000) {
          setIsProcessingAudio(false);
          return;
        }

        try {
          const reader = new FileReader();
          reader.readAsDataURL(audioBlob);
          reader.onloadend = async () => {
            const base64data = (reader.result as string).split(',')[1];
            const response = await fetch('/api/soul/stt', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                audio_base64: base64data,
                format: 'audio/webm',
                filename: 'recording.webm'
              })
            });

            if (response.ok) {
              const data = await response.json();
              const text = data.text || data.transcription || '';
              if (text.trim()) {
                setInputValue(text);
              }
            }
            setIsProcessingAudio(false);
          };
        } catch (e) {
          console.error('STT error:', e);
          setIsProcessingAudio(false);
        }
      };

      recorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error('Microphone access denied:', err);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const toggleCategory = (title: string) => {
    setOpenCategories(prev => ({ ...prev, [title]: !prev[title] }));
  };

  interface MenuItem {
    id: string;
    label: string;
    icon: string;
    isExternal?: boolean;
    href?: string;
  }
  interface MenuCategory {
    title: string;
    icon: string;
    items: MenuItem[];
  }

  const MENU_CATEGORIES: MenuCategory[] = [
    {
      title: 'AGENCY & INTELLIGENCE',
      icon: '⚡',
      items: [
        { id: 'Agency', label: 'Agency Terminal', icon: '🤖' },
        { id: 'Persona', label: 'Persona & MBTI', icon: '🎭' }
      ]
    },
    {
      title: 'DEVELOPMENT SUITE',
      icon: '🛠️',
      items: [
        { id: 'NativeIDE', label: 'FoveAI Native IDE', icon: '⌨️' },
        { id: 'WebVM', label: 'Linux WebVM (WASM)', icon: '🖥️' }
      ]
    },
    {
      title: 'SENSES & REVENUE',
      icon: '📊',
      items: [
        { id: 'Canvas', label: 'Canvas (Dreamscape)', icon: '🎨' },
        { id: 'Soundboard', label: 'Voice & Soundboard', icon: '🔊' },
        { id: 'Monetization', label: 'Monetization', icon: '💰' }
      ]
    },
    {
      title: 'EDUTAINMENT',
      icon: '🎮',
      items: [
        { id: 'Roleplay', label: 'Roleplay & Scenarios', icon: '🎭' },
        { id: 'Diagnostics', label: 'Diagnostic Matrix', icon: '🔬' },
        { id: 'proxy_stats', label: `Foveated Memory Stats (${proxyPort})`, icon: '📊', isExternal: true, href: '/api/foveated/stats' }
      ]
    }
  ];

  // ----------------------------------------------------
  // RENDER DASHBOARD
  // ----------------------------------------------------
  return (
    <div className="app-container">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="sidebar-brand" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <h2 style={{ margin: 0 }}>{siteName}</h2>
          <div
            className={`dot ${proxyStatus === 'online' ? 'online' : 'offline'}`}
            title={proxyStatus === 'online' ? 'Online' : 'Offline'}
            style={{ width: '10px', height: '10px', borderRadius: '50%' }}
          />
        </div>
        
        <nav className="nav-menu">
          {/* PRIMARY QUICK START BUTTONS */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '10px' }}>
            <button 
              className={`nav-item ${activeTab === 'Copilot' ? 'active' : ''}`}
              onClick={() => setActiveTab('Copilot')}
              style={{ fontWeight: 600 }}
            >
              <span style={{ fontSize: '1.2rem' }}>💬</span> Copilot Chat
            </button>
            <button 
              className={`nav-item ${activeTab === 'Memory' ? 'active' : ''}`}
              onClick={() => setActiveTab('Memory')}
              style={{ fontWeight: 600 }}
            >
              <span style={{ fontSize: '1.2rem' }}>🧠</span> Memory Vault
            </button>
          </div>

          <div style={{ height: '1px', background: 'var(--border-glass)', margin: '4px 0 10px 0' }} />

          {/* 4 MAIN CATEGORIES ACCORDION BUTTONS */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {MENU_CATEGORIES.map((cat) => {
              const isOpen = openCategories[cat.title] ?? true;
              const hasActiveChild = cat.items.some(i => i.id === activeTab);

              return (
                <div key={cat.title} style={{ display: 'flex', flexDirection: 'column' }}>
                  {/* Category Button Header */}
                  <button
                    className={`category-header ${hasActiveChild ? 'has-active' : ''}`}
                    onClick={() => toggleCategory(cat.title)}
                  >
                    <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span>{cat.icon}</span>
                      <span>{cat.title}</span>
                    </span>
                    <span style={{ fontSize: '0.7rem', opacity: 0.7 }}>
                      {isOpen ? '▾' : '▸'}
                    </span>
                  </button>

                  {/* Inline Expanded Items */}
                  {isOpen && (
                    <div className="category-items">
                      {cat.items.map(item => {
                        if (item.isExternal) {
                          return (
                            <a 
                              key={item.id}
                              href={item.href}
                              target="_blank"
                              rel="noreferrer"
                              className="sub-nav-item"
                              style={{ textDecoration: 'none' }}
                            >
                              <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span>{item.icon}</span> {item.label}
                              </span>
                              <span style={{ fontSize: '0.75rem', opacity: 0.5 }}>↗</span>
                            </a>
                          );
                        }
                        const isActive = activeTab === item.id;
                        return (
                          <button 
                            key={item.id}
                            className={`sub-nav-item ${isActive ? 'active' : ''}`} 
                            onClick={() => setActiveTab(item.id)}
                          >
                            <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span>{item.icon}</span> {item.label}
                            </span>
                            {isActive && <span style={{ fontSize: '0.6rem', color: 'var(--accent-cyan)' }}>●</span>}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </nav>
        
        <div className="user-profile">
          <div className="user-info">
            <div className="avatar">
              {currentUser.username.charAt(0).toUpperCase()}
            </div>
            <div>
              <div className="username">{currentUser.username}</div>
              <div className="role">{currentUser.role}</div>
            </div>
          </div>
          <button className="logout-btn" onClick={handleLogout} title="Log Out">
            ⎋
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="main-content">
        {/* Top Bar with Server Metrics & Quick Actions */}
        <header className="chat-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(0, 240, 255, 0.2)', padding: '12px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {/* Quick Action Toolbar */}
            <div className="topbar-actions" style={{ display: 'flex', gap: '10px' }}>
              <button
                className={`icon-btn ${showAvatar ? 'active' : ''}`}
                title="Toggle Video / 3D Avatar"
                onClick={() => setShowAvatar(!showAvatar)}
                style={showAvatar ? { background: 'rgba(255, 0, 127, 0.3)', borderColor: 'var(--neon-pink)' } : {}}
              >
                🎥
              </button>
              <button className={`icon-btn ${activeTab === 'Soundboard' ? 'active' : ''}`} title="Voice & Soundboard" onClick={() => setActiveTab('Soundboard')}>
                🔊
              </button>
              <button className={`icon-btn ${deepThink ? 'active' : ''}`} title="Deep Think" onClick={() => setDeepThink(!deepThink)} style={deepThink ? { background: 'rgba(0, 243, 255, 0.3)', borderColor: 'var(--accent-cyan)' } : {}}>
                🧠
              </button>
              <button className={`icon-btn ${activeTab === 'Canvas' ? 'active' : ''}`} title="Creative / Image Canvas" onClick={() => setActiveTab('Canvas')}>
                🎨
              </button>

              <select
                className="context-select"
                title="Context size & compression"
                value={contextBudget}
                onChange={e => {
                  const v = parseInt(e.target.value, 10);
                  setContextBudget(v);
                  setCompressionLevel(v <= 4000 ? 5 : v <= 8000 ? 4 : v <= 16000 ? 3 : v <= 32000 ? 2 : 1);
                }}
                style={{ background: 'rgba(0,0,0,0.5)', border: '1px solid rgba(0,243,255,0.3)', color: 'var(--text-light)', borderRadius: '4px', padding: '4px 8px', fontSize: '0.7rem', fontFamily: 'Share Tech Mono', cursor: 'pointer' }}
              >
                <option value={4000}>4K Max</option>
                <option value={8000}>8K Small</option>
                <option value={16000}>16K Normal</option>
                <option value={32000}>32K Large</option>
                <option value={64000}>64K Max</option>
              </select>
            </div>

            {/* Active Simulation Pill */}
            {activeSimulation && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(0, 243, 255, 0.1)', border: '1px solid #00f3ff', padding: '4px 10px', borderRadius: '4px', fontSize: '0.72rem', color: '#00f3ff', fontWeight: 'bold' }}>
                <span>🎭 SIMULATION: {activeSimulation.Disorder}</span>
                <span style={{ fontSize: '0.65rem', opacity: 0.8, color: '#a0e0ff' }}>(Memory Shield ON)</span>
                <button 
                  onClick={handleClearSimulation} 
                  style={{ background: 'rgba(255, 0, 80, 0.2)', border: '1px solid #ff4d6d', color: '#ff4d6d', borderRadius: '3px', padding: '1px 6px', fontSize: '0.65rem', cursor: 'pointer' }}
                >
                  ⎋ Revert
                </button>
              </div>
            )}
          </div>

          {/* Top Bar Server Metrics */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '15px', fontFamily: 'Share Tech Mono', fontSize: '0.7rem', color: 'rgba(255,255,255,0.7)', background: 'rgba(0,0,0,0.4)', padding: '6px 12px', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.1)' }}>
            <div>CPU: <span style={{ color: 'var(--neon-green)' }}>14%</span></div>
            <div>RAM: <span style={{ color: 'var(--neon-green)' }}>3.8 GB</span></div>
            <div>STT: <span style={{ color: 'var(--accent-cyan)' }}>Whisper</span></div>
          </div>
        </header>

        {/* Tab Router */}
        {activeTab === 'Memory' ? (
          <div style={{ flex: 1, width: '100%', height: '100%', overflow: 'hidden' }}>
            <iframe 
              src="https://foveai.1um6a.se/memory" 
              style={{ width: '100%', height: '100%', border: 'none', background: '#000' }} 
              title="Memory Vault Dashboard"
            />
          </div>
        ) : activeTab === 'Canvas' ? (
          <CanvasTab />
        ) : activeTab === 'Roleplay' ? (
          <RoleplayTab 
            onApplyRole={(role, mode) => handleAssimilateDisorder({ Disorder: role.title, Cluster: 'Roleplay Scenario', systemPrompt: role.systemPrompt }, mode)}
            activeSimulation={activeSimulation}
            onClearSimulation={handleClearSimulation}
          />
        ) : activeTab === 'Diagnostics' ? (
          <DiagnosticsTab 
            onAssimilateDisorder={handleAssimilateDisorder}
            activeSimulation={activeSimulation}
            onClearSimulation={handleClearSimulation}
          />
        ) : activeTab === 'Agency' ? (
          <AgencyTab />
        ) : activeTab === 'Monetization' ? (
          <MonetizationTab />
        ) : activeTab === 'Soundboard' ? (
          <SoundboardTab />
        ) : activeTab === 'Persona' ? (
          <PersonaTab 
            onNavigateToDiagnostics={() => setActiveTab('Diagnostics')}
            activeSimulation={activeSimulation}
            onClearSimulation={handleClearSimulation}
          />
        ) : (
          <>
            <div className="chat-messages">
              {messages.map((msg, idx) => (
                <div key={idx} className={`message ${msg.role}`}>
                  <div className="message-avatar" title={msg.role === 'user' ? `${currentUser.firstName} ${currentUser.lastName}` : (currentUser.aiName || 'AI')}>
                    {msg.role === 'user' ? currentUser.firstName?.charAt(0).toUpperCase() || 'U' : (currentUser.aiName?.charAt(0).toUpperCase() || 'A')}
                  </div>
                  <div className="message-content">
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '4px' }}>
                      {msg.role === 'user' ? `${currentUser.firstName} ${currentUser.lastName}` : (currentUser.aiName || 'AI')}
                    </div>
                    {msg.content}
                  </div>
                </div>
              ))}
              
              {isTyping && (
                <div className="message assistant">
                  <div className="message-avatar" title={currentUser.aiName || 'AI'}>
                    {currentUser.aiName?.charAt(0).toUpperCase() || 'A'}
                  </div>
                  <div className="message-content" style={{ padding: '20px 24px' }}>
                    <div className="typing-indicator">
                      <div className="typing-dot" />
                      <div className="typing-dot" />
                      <div className="typing-dot" />
                    </div>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            <AvatarOverlay show={showAvatar} talking={isTyping} />

            <div className="input-area">
              <div className="input-wrapper" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                {/* Push To Talk (PTT) Button */}
                <button
                  onMouseDown={startRecording}
                  onMouseUp={stopRecording}
                  onTouchStart={startRecording}
                  onTouchEnd={stopRecording}
                  disabled={isTyping || isProcessingAudio}
                  style={{
                    padding: '10px 16px',
                    background: isRecording ? 'var(--neon-pink)' : 'rgba(0, 240, 255, 0.1)',
                    border: `1px solid ${isRecording ? 'var(--neon-pink)' : 'var(--accent-cyan)'}`,
                    color: isRecording ? '#fff' : 'var(--accent-cyan)',
                    borderRadius: '6px',
                    fontFamily: 'Share Tech Mono',
                    fontSize: '0.75rem',
                    cursor: 'pointer',
                    userSelect: 'none',
                    transition: 'all 0.2s',
                    whiteSpace: 'nowrap'
                  }}
                  title="Hold down to talk via microphone"
                >
                  {isRecording ? '🔴 RECORDING...' : isProcessingAudio ? '⚙️ TRANSCRIBING...' : '🎙️ PTT'}
                </button>

                <select
                  value={chatProvider}
                  onChange={e => {
                    const p = e.target.value as 'xrlf_proxy' | 'lmstudio' | 'cloud';
                    setChatProvider(p);
                    const fleet = MODEL_FLEETS[p] || [];
                    if (fleet.length > 0) setSelectedModel(fleet[0].id);
                  }}
                  disabled={isTyping}
                  style={{
                    padding: '10px 12px',
                    background: 'rgba(0,0,0,0.4)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    color: '#fff',
                    borderRadius: '6px',
                    fontFamily: 'Share Tech Mono',
                    fontSize: '0.75rem',
                    outline: 'none',
                    cursor: 'pointer',
                    maxWidth: '120px'
                  }}
                  title="Chat Provider"
                >
                  <option value="xrlf_proxy">🧠 XRLF Proxy</option>
                  <option value="lmstudio">💻 LM Studio</option>
                  <option value="cloud">☁️ Cloud</option>
                </select>

                <select
                  value={selectedModel}
                  onChange={e => setSelectedModel(e.target.value)}
                  disabled={isTyping}
                  style={{
                    padding: '10px 12px',
                    background: 'rgba(0,0,0,0.4)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    color: '#fff',
                    borderRadius: '6px',
                    fontFamily: 'Share Tech Mono',
                    fontSize: '0.8rem',
                    outline: 'none',
                    cursor: 'pointer',
                    maxWidth: '180px'
                  }}
                  title="Select AI Model"
                >
                  {chatProvider === 'cloud' && <option value="auto">auto (Cloud Auto-Route)</option>}
                  {chatProvider === 'xrlf_proxy' && <option value="auto">auto (Active XRLF Model)</option>}
                  {chatProvider === 'lmstudio' && <option value="auto">auto (Active LM Studio Model)</option>}
                  {(MODEL_FLEETS[chatProvider] || []).map(m => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                  {chatProvider === 'cloud' && availableModels.map((m: any) => (
                    <option key={m.id} value={m.id}>{m.id}</option>
                  ))}
                </select>

                <input 
                  type="text" 
                  className="chat-input"
                  placeholder={`Ask ${currentUser.aiName || 'your AI'} to build something...`}
                  value={inputValue}
                  onChange={e => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={isTyping}
                  style={{ flex: 1 }}
                />
                <button 
                  className="send-btn" 
                  onClick={handleSendMessage}
                  disabled={!inputValue.trim() || isTyping}
                >
                  ↑
                </button>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

export default App;
