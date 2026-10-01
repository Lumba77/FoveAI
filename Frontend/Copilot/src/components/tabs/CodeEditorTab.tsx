import React, { useState, useEffect, useRef } from 'react';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
}

interface ModelOption {
  id: string;
  label: string;
}

const NVIDIA_MODELS: ModelOption[] = [
  { id: 'moonshotai/kimi-k3', label: 'Kimi K3 (Reasoning + Vision)' },
  { id: 'deepseek-ai/deepseek-r1', label: 'DeepSeek R1 (Reasoning)' },
  { id: 'meta/llama-3.3-70b-instruct', label: 'Llama 3.3 70B' },
  { id: 'nvidia/llama-3.1-nemotron-70b-instruct', label: 'Nemotron 70B' },
  { id: 'qwen/qwen2.5-coder-32b-instruct', label: 'Qwen 2.5 Coder 32B' },
];

const REASONING_LEVELS = ['low', 'medium', 'max'] as const;

export const CodeEditorTab: React.FC = () => {
  const [code, setCode] = useState<string>(() => {
    return localStorage.getItem('lumax_ide_code') || `# Welcome to LUMAX IDE\n# Powered by NVIDIA build.nvidia.com\n\ndef hello():\n    print("Hello from LUMAX IDE!")\n    return "success"\n\nhello()\n`;
  });
  const [chat, setChat] = useState<ChatMessage[]>([
    { role: 'assistant', content: 'Hi! I\'m your AI coding assistant powered by NVIDIA. Ask me to write, explain, or debug code.' }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState<string>(() => localStorage.getItem('lumax_ide_model') || 'moonshotai/kimi-k3');
  const [reasoningEffort, setReasoningEffort] = useState<typeof REASONING_LEVELS[number]>(() => localStorage.getItem('lumax_ide_reasoning') as any || 'medium');
  const [apiKey, setApiKey] = useState<string>(() => localStorage.getItem('lumax_nvidia_key') || '');
  const [showSettings, setShowSettings] = useState(false);
  const [fileName, setFileName] = useState<string>(() => localStorage.getItem('lumax_ide_filename') || 'main.py');
  const [output, setOutput] = useState<string>('');
  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Persist state
  useEffect(() => { localStorage.setItem('lumax_ide_code', code); }, [code]);
  useEffect(() => { localStorage.setItem('lumax_ide_model', selectedModel); }, [selectedModel]);
  useEffect(() => { localStorage.setItem('lumax_ide_reasoning', reasoningEffort); }, [reasoningEffort]);
  useEffect(() => { localStorage.setItem('lumax_nvidia_key', apiKey); }, [apiKey]);
  useEffect(() => { localStorage.setItem('lumax_ide_filename', fileName); }, [fileName]);

  // Auto-scroll chat
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [chat]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  }, [input]);

  // Try to load API key from .env via backend proxy
  useEffect(() => {
    if (!apiKey) {
      fetch('/api/nvidia-key')
        .then(r => r.json())
        .then(data => { if (data.key) setApiKey(data.key); })
        .catch(() => {});
    }
  }, []);

  const sendToNvidia = async (userMessage: string, includeCode: boolean = false) => {
    if (!apiKey) {
      setChat(prev => [...prev, { role: 'assistant', content: '⚠️ No API key set. Click the ⚙️ button to add your NVIDIA API key (nvapi-...).' }]);
      return;
    }

    setIsLoading(true);

    const prompt = includeCode
      ? `${userMessage}\n\n\`\`\`\n${code}\n\`\`\``
      : userMessage;

    try {
      const resp = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: selectedModel,
          messages: [
            ...chat.filter(m => m.role === 'user' || m.role === 'assistant').map(m => ({
              role: m.role,
              content: m.content,
            })),
            { role: 'user', content: prompt },
          ],
          max_tokens: 16384,
          temperature: 1,
          stream: false,
          reasoning_effort: reasoningEffort,
        }),
      });

      if (!resp.ok) {
        const errText = await resp.text();
        setChat(prev => [...prev, { role: 'assistant', content: `❌ Error ${resp.status}: ${errText.substring(0, 200)}` }]);
        return;
      }

      const data = await resp.json();
      const msg = data.choices[0].message;
      const reasoning = msg.reasoning_content || '';
      const content = msg.content || '';

      setChat(prev => [...prev, {
        role: 'assistant',
        content,
        reasoning: reasoning ? reasoning.substring(0, 500) + (reasoning.length > 500 ? '...' : '') : undefined,
      }]);
    } catch (e: any) {
      setChat(prev => [...prev, { role: 'assistant', content: `❌ Network error: ${e.message}` }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSend = () => {
    if (!input.trim() || isLoading) return;
    const userMsg = input.trim();
    setChat(prev => [...prev, { role: 'user', content: userMsg }]);
    setInput('');
    sendToNvidia(userMsg, false);
  };

  const handleSendWithCode = () => {
    if (!input.trim() || isLoading) return;
    const userMsg = input.trim();
    setChat(prev => [...prev, { role: 'user', content: userMsg + ' (with code context)' }]);
    setInput('');
    sendToNvidia(userMsg, true);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewFile = () => {
    setCode('');
    setFileName('untitled.py');
    setOutput('');
  };

  const handleSave = () => {
    const blob = new Blob([code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleLoadFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (ev) => setCode(ev.target?.result as string || '');
    reader.readAsText(file);
  };

  const insertCodeBlock = (codeStr: string) => {
    setCode(prev => prev + '\n' + codeStr.replace(/```[a-z]*\n?/g, '').replace(/```$/g, ''));
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#0a0a0f', color: '#e0e0e0' }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px',
        background: 'rgba(0, 0, 0, 0.3)', borderBottom: '1px solid rgba(0, 243, 255, 0.1)',
        flexShrink: 0,
      }}>
        <span style={{ fontSize: '1.2rem' }}>⌨️</span>
        <input
          value={fileName}
          onChange={(e) => setFileName(e.target.value)}
          style={{
            background: 'transparent', border: '1px solid rgba(255,255,255,0.1)',
            color: '#00eaff', padding: '4px 8px', borderRadius: '4px', fontSize: '0.85rem',
            width: '180px', fontFamily: 'monospace',
          }}
        />
        <button onClick={handleNewFile} style={btnStyle}>New</button>
        <button onClick={handleSave} style={btnStyle}>Save</button>
        <label style={{ ...btnStyle, cursor: 'pointer' }}>
          Load
          <input type="file" onChange={handleLoadFile} style={{ display: 'none' }} accept=".py,.js,.ts,.txt,.json,.md" />
        </label>
        <div style={{ flex: 1 }} />
        <select
          value={selectedModel}
          onChange={(e) => setSelectedModel(e.target.value)}
          style={{ ...btnStyle, background: 'rgba(0, 243, 255, 0.05)' }}
        >
          {NVIDIA_MODELS.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
        </select>
        <select
          value={reasoningEffort}
          onChange={(e) => setReasoningEffort(e.target.value as any)}
          style={{ ...btnStyle, background: 'rgba(0, 243, 255, 0.05)' }}
        >
          {REASONING_LEVELS.map(r => <option key={r} value={r}>Think: {r}</option>)}
        </select>
        <button onClick={() => setShowSettings(!showSettings)} style={{ ...btnStyle, background: showSettings ? 'rgba(0, 243, 255, 0.2)' : 'rgba(0,0,0,0.3)' }}>⚙️</button>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div style={{
          padding: '12px', background: 'rgba(0, 243, 255, 0.03)',
          borderBottom: '1px solid rgba(0, 243, 255, 0.1)', display: 'flex', gap: '12px', alignItems: 'center',
        }}>
          <label style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>NVIDIA API Key:</label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="nvapi-..."
            style={{
              flex: 1, background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)',
              color: '#fff', padding: '6px 10px', borderRadius: '4px', fontFamily: 'monospace', fontSize: '0.85rem',
            }}
          />
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Get a free key at <a href="https://build.nvidia.com" target="_blank" style={{ color: 'var(--accent-cyan)' }}>build.nvidia.com</a>
          </span>
        </div>
      )}

      {/* Main split: editor + chat */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Editor pane */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', borderRight: '1px solid rgba(255,255,255,0.05)' }}>
          <textarea
            value={code}
            onChange={(e) => setCode(e.target.value)}
            spellCheck={false}
            style={{
              flex: 1, background: '#0d0d14', color: '#c8c8c8', border: 'none',
              padding: '16px', fontFamily: "'Fira Code', 'Consolas', monospace", fontSize: '14px',
              lineHeight: '1.6', resize: 'none', outline: 'none', tabSize: 4,
            }}
            placeholder="Write your code here..."
          />
          {output && (
            <div style={{
              height: '150px', overflow: 'auto', padding: '10px',
              background: '#000', color: '#0f0', fontFamily: 'monospace', fontSize: '12px',
              borderTop: '1px solid rgba(0, 243, 255, 0.2)',
            }}>
              <div style={{ color: '#888', marginBottom: '4px' }}>--- Output ---</div>
              <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{output}</pre>
            </div>
          )}
        </div>

        {/* Chat pane */}
        <div style={{ width: '420px', display: 'flex', flexDirection: 'column', background: 'rgba(0,0,0,0.2)' }}>
          {/* Chat messages */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
            {chat.map((msg, i) => (
              <div key={i} style={{
                marginBottom: '12px',
                marginLeft: msg.role === 'user' ? '40px' : '0',
                marginRight: msg.role === 'assistant' ? '40px' : '0',
              }}>
                <div style={{
                  fontSize: '0.7rem', color: msg.role === 'user' ? '#00eaff' : '#a020f0',
                  marginBottom: '4px', fontWeight: 'bold',
                }}>
                  {msg.role === 'user' ? 'YOU' : 'AI'}
                </div>
                {msg.reasoning && (
                  <div style={{
                    fontSize: '0.75rem', color: '#888', fontStyle: 'italic',
                    background: 'rgba(255,255,255,0.03)', padding: '6px 8px', borderRadius: '4px',
                    marginBottom: '4px', borderLeft: '2px solid #555',
                  }}>
                    💭 {msg.reasoning}
                  </div>
                )}
                <div style={{
                  background: msg.role === 'user' ? 'rgba(0, 234, 255, 0.08)' : 'rgba(160, 32, 240, 0.08)',
                  border: `1px solid ${msg.role === 'user' ? 'rgba(0, 234, 255, 0.15)' : 'rgba(160, 32, 240, 0.15)'}`,
                  borderRadius: '8px', padding: '10px 12px', fontSize: '0.85rem', lineHeight: '1.5',
                  whiteSpace: 'pre-wrap',
                }}>
                  {msg.content}
                </div>
                {msg.role === 'assistant' && msg.content.includes('```') && (
                  <button
                    onClick={() => {
                      const match = msg.content.match(/```[\s\S]*?```/);
                      if (match) insertCodeBlock(match[0]);
                    }}
                    style={{
                      marginTop: '4px', fontSize: '0.7rem', color: '#00eaff',
                      background: 'transparent', border: '1px solid rgba(0, 234, 255, 0.2)',
                      padding: '2px 8px', borderRadius: '4px', cursor: 'pointer',
                    }}
                  >
                    📋 Insert code
                  </button>
                )}
              </div>
            ))}
            {isLoading && (
              <div style={{ color: '#888', fontSize: '0.85rem', padding: '8px' }}>
                <span style={{ animation: 'pulse 1s infinite' }}>●</span> AI is thinking...
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Input area */}
          <div style={{ padding: '10px', borderTop: '1px solid rgba(255,255,255,0.05)', flexShrink: 0 }}>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask AI to write, explain, or debug code... (Enter to send, Shift+Enter for newline)"
              disabled={isLoading}
              style={{
                width: '100%', background: 'rgba(0,0,0,0.3)', color: '#fff', border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '8px', padding: '10px', fontSize: '0.85rem', resize: 'none',
                minHeight: '44px', maxHeight: '120px', outline: 'none', fontFamily: 'inherit',
              }}
            />
            <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
              <button
                onClick={handleSend}
                disabled={isLoading || !input.trim()}
                style={{
                  ...btnStyle, flex: 1,
                  background: isLoading ? 'rgba(100,100,100,0.2)' : 'rgba(0, 234, 255, 0.15)',
                  borderColor: 'rgba(0, 234, 255, 0.3)',
                }}
              >
                Send
              </button>
              <button
                onClick={handleSendWithCode}
                disabled={isLoading || !input.trim()}
                title="Send with current code as context"
                style={{
                  ...btnStyle,
                  background: isLoading ? 'rgba(100,100,100,0.2)' : 'rgba(160, 32, 240, 0.15)',
                  borderColor: 'rgba(160, 32, 240, 0.3)',
                }}
              >
                Send + Code
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const btnStyle: React.CSSProperties = {
  background: 'rgba(0,0,0,0.3)', color: '#ccc', border: '1px solid rgba(255,255,255,0.1)',
  padding: '5px 12px', borderRadius: '4px', fontSize: '0.8rem', cursor: 'pointer',
  fontFamily: 'inherit', transition: 'all 0.2s',
};
