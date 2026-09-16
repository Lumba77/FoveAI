import React, { useState, useEffect, useRef } from 'react';
import './App.css';

// @ts-ignore
const ipcRenderer = window.require ? window.require('electron').ipcRenderer : null;

function App() {
  const [proxyStatus, setProxyStatus] = useState<string>('Checking...');
  const [details, setDetails] = useState<any>(null);
  const [models, setModels] = useState<string[]>([]);
  const [downloadRepo, setDownloadRepo] = useState<string>('');
  const [isDownloading, setIsDownloading] = useState(false);
  
  // Navigation State
  const [activeTab, setActiveTab] = useState<'Copilot' | 'Nursery' | 'Memory'>('Copilot');

  // Chat state
  const [messages, setMessages] = useState<{role: string, content: string}[]>([
    { role: 'assistant', content: 'Welcome to your private Lumax Copilot. How can I assist your workflow today?' }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (activeTab === 'Copilot') {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isTyping, activeTab]);

  useEffect(() => {
    const checkProxy = async () => {
      if (ipcRenderer) {
        try {
          const res = await ipcRenderer.invoke('ping-proxy');
          if (res.error) {
            setProxyStatus('Offline');
          } else {
            setProxyStatus('Online');
            setDetails(res);
          }
        } catch (e) {
          setProxyStatus('Offline');
        }
      } else {
        setProxyStatus('Browser Mode (No IPC)');
      }
    };
    
    checkProxy();
    const interval = setInterval(checkProxy, 5000);
    return () => clearInterval(interval);
  }, []);

  const loadModels = async () => {
    if (ipcRenderer) {
      const list = await ipcRenderer.invoke('list-models');
      setModels(list);
    }
  };

  useEffect(() => {
    if (activeTab === 'Nursery') {
      loadModels();
    }
  }, [activeTab]);

  const handleDownload = async () => {
    if (ipcRenderer && downloadRepo) {
      setIsDownloading(true);
      await ipcRenderer.invoke('download-model', downloadRepo);
      setIsDownloading(false);
      setDownloadRepo('');
      loadModels();
    }
  };

  const handleStartProxy = async () => {
    if (ipcRenderer) {
      setProxyStatus('Starting...');
      await ipcRenderer.invoke('start-proxy');
    }
  };

  const handleStopProxy = async () => {
    if (ipcRenderer) {
      await ipcRenderer.invoke('stop-proxy');
      setProxyStatus('Offline');
      setDetails(null);
    }
  };

  const handleOpenNursery = async () => {
    if (ipcRenderer) {
      await ipcRenderer.invoke('start-nursery');
    }
  };

  const handleSendMessage = async () => {
    if (!inputValue.trim()) return;
    
    const userMsg = { role: 'user', content: inputValue };
    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setIsTyping(true);

    try {
      const response = await fetch('http://127.0.0.1:8200/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${currentUser?.apiKey || 'foveai_desktop_user'}`
        },
        body: JSON.stringify({
          model: 'foveai-vibe',
          messages: [...messages, userMsg],
          stream: false
        })
      });

      const data = await response.json();
      const botReply = data.choices?.[0]?.message?.content || 'Error: No response from swarm.';
      
      setMessages(prev => [...prev, { role: 'assistant', content: botReply }]);
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Connection failed. Is the proxy running?' }]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <div className="app-container" style={{ WebkitAppRegion: 'drag' } as any}>
      {/* Sidebar Navigation */}
      <aside className="sidebar" style={{ WebkitAppRegion: 'no-drag' } as any}>
        <div className="sidebar-brand">
          <h2>FoveAI Center</h2>
        </div>
        
        <nav className="nav-menu">
          <button 
            className={`nav-item ${activeTab === 'Copilot' ? 'active' : ''}`}
            onClick={() => setActiveTab('Copilot')}
          >
            <span>💻</span> Copilot
          </button>
          <button 
            className={`nav-item ${activeTab === 'Memory' ? 'active' : ''}`}
            onClick={() => setActiveTab('Memory')}
          >
            <span>🧠</span> Memory Vault
          </button>
          <button className="nav-item" disabled>
            <span>🎨</span> Canvas (Dreamscape)
          </button>
          <button className="nav-item" disabled>
            <span>⚡</span> Agency Terminal
          </button>
          <button className="nav-item" disabled>
            <span>🖥️</span> Linux VM
          </button>
          <button className="nav-item" disabled>
            <span>💰</span> Monetization
          </button>
          <button className="nav-item" disabled>
            <span>🔊</span> Soundboard
          </button>
          <button className="nav-item" disabled>
            <span>🎭</span> Persona & MBTI
          </button>
          <button 
            className={`nav-item ${activeTab === 'Nursery' ? 'active' : ''}`}
            onClick={() => setActiveTab('Nursery')}
          >
            <span>⚙️</span> Nursery Manager & Diagnostics
          </button>
        </nav>
        
        <div style={{ flex: 1 }} />
        
        <div className="user-profile">
          <div className="user-info">
            <div className="avatar">L</div>
            <div>
              <div className="username">Desktop User</div>
              <div className="role">Local Admin</div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="main-content" style={{ WebkitAppRegion: 'no-drag' } as any}>
        <header className="chat-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
            <h3>{activeTab === 'Copilot' ? 'FoveAI Copilot' : activeTab === 'Memory' ? 'Memory Vault' : 'Nursery & Settings'}</h3>
            <div className="status-indicator">
              <div className={`dot ${proxyStatus === 'Online' ? 'online' : 'offline'}`} />
              {proxyStatus === 'Online' ? 'Proxy Connected' : proxyStatus}
            </div>
          </div>
          
          <div className="topbar-actions" style={{ display: 'flex', gap: '12px' }}>
            <button className="icon-btn" title="Neural Cortex (Personality & Intimacy)" onClick={() => setActiveTab('Memory')}>🧠</button>
            <button className="icon-btn" title="Dreamscape (Canvas)">🎨</button>
            <button className="icon-btn" title="Agency Terminal">⚡</button>
            <button className="icon-btn" title="Voice & Soundboard">🔊</button>
            <button className="icon-btn" title="Avatar Cameras & Expressions">👁️</button>
          </div>
        </header>

        {activeTab === 'Memory' ? (
          <div style={{ flex: 1, width: '100%', height: '100%', overflow: 'hidden' }}>
            <iframe 
              src="https://foveai.1um6a.se/memory" 
              style={{ width: '100%', height: '100%', border: 'none', background: '#000' }} 
              title="Memory Vault Dashboard"
            />
          </div>
        ) : activeTab === 'Copilot' ? (
          <>
            <div className="chat-messages">
              {messages.map((msg, idx) => (
                <div key={idx} className={`message ${msg.role}`}>
                  <div className="message-avatar">
                    {msg.role === 'user' ? 'U' : '🤖'}
                  </div>
                  <div className="message-content">
                    {msg.content}
                  </div>
                </div>
              ))}
              {isTyping && (
                <div className="typing-indicator" style={{ marginLeft: '60px' }}>
                  <div className="typing-dot"></div>
                  <div className="typing-dot"></div>
                  <div className="typing-dot"></div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            <div className="input-area">
              <div className="input-wrapper" style={{ width: '100%' }}>
                <input 
                  type="text" 
                  className="chat-input"
                  placeholder="Ask FoveAI to build something..."
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={isTyping || proxyStatus !== 'Online'}
                />
                <button 
                  className="send-btn" 
                  onClick={handleSendMessage}
                  disabled={isTyping || proxyStatus !== 'Online' || !inputValue.trim()}
                >
                  ➤
                </button>
              </div>
            </div>
          </>
        ) : (
          <div style={{ padding: '32px', display: 'flex', flexDirection: 'column', gap: '24px', overflowY: 'auto' }}>
            <div style={{ background: 'var(--bg-glass)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-glass)' }}>
              <h2 style={{ margin: '0 0 16px 0', fontSize: '1.2rem' }}>Swarm Network Control</h2>
              <div style={{ display: 'flex', gap: '12px', marginBottom: '24px' }}>
                <button className="btn-primary" onClick={handleStartProxy} disabled={proxyStatus === 'Online'}>
                  Start Foveated Proxy
                </button>
                <button className="btn-primary" style={{ background: 'transparent' }} onClick={handleStopProxy} disabled={proxyStatus === 'Offline'}>
                  Stop Proxy
                </button>
                <button className="btn-primary" onClick={handleOpenNursery}>
                  🍼 Open Legacy Nursery
                </button>
              </div>

              {details && (
                <div style={{ display: 'flex', gap: '40px', background: 'rgba(0,0,0,0.2)', padding: '16px', borderRadius: '8px' }}>
                  <div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>MODE</div>
                    <div style={{ fontSize: '1.1rem' }}>{details.mode}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>UPTIME</div>
                    <div style={{ fontSize: '1.1rem' }}>{Math.floor(details.uptime)}s</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>VERSION</div>
                    <div style={{ fontSize: '1.1rem' }}>{details.version}</div>
                  </div>
                </div>
              )}
            </div>

            <div style={{ background: 'var(--bg-glass)', padding: '24px', borderRadius: '12px', border: '1px solid var(--border-glass)' }}>
              <h2 style={{ margin: '0 0 16px 0', fontSize: '1.2rem' }}>Model Downloader</h2>
              <div style={{ display: 'flex', gap: '12px', marginBottom: '24px' }}>
                <input 
                  type="text" 
                  placeholder="HuggingFace Repo ID..." 
                  value={downloadRepo}
                  onChange={e => setDownloadRepo(e.target.value)}
                  disabled={isDownloading}
                  style={{ flex: 1, padding: '12px', background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-glass)', borderRadius: '8px', color: 'white' }}
                />
                <button className="btn-primary" onClick={handleDownload} disabled={isDownloading || !downloadRepo}>
                  {isDownloading ? 'Pulling...' : 'Pull'}
                </button>
              </div>

              <h3 style={{ margin: '0 0 12px 0', fontSize: '1rem', color: 'var(--text-muted)' }}>Installed Micro-Models</h3>
              <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                {models.length > 0 ? (
                  models.map(m => (
                    <li key={m} style={{ padding: '12px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      📦 {m}
                    </li>
                  ))
                ) : (
                  <p style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>No local models found in cache.</p>
                )}
              </ul>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
