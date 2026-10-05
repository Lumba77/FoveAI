import fs from 'fs';

let code = fs.readFileSync('src/App.tsx', 'utf8');

// 1. Remove the global AvatarView and import
code = code.replace(/<AvatarView \/>\n/g, '');

// 2. Add mode states
const stateInsert = `
  const [activeMode, setActiveMode] = useState<'Text' | 'Voice' | 'Video'>('Text');
  const [pendingMode, setPendingMode] = useState<'Text' | 'Voice' | 'Video' | null>(null);
  
  const interactionModes: ('Text' | 'Voice' | 'Video')[] = ['Text', 'Voice', 'Video'];
  
  const handleRollStep = (dir: number) => {
    if (inputValue.trim()) return; // Lock if typing
    setPendingMode(prev => {
       const current = prev || activeMode;
       let idx = interactionModes.indexOf(current) + dir;
       if (idx < 0) idx = interactionModes.length - 1;
       if (idx >= interactionModes.length) idx = 0;
       return interactionModes[idx];
    });
  };

  const handleModeConfirm = () => {
    if (pendingMode) {
      setActiveMode(pendingMode);
      setPendingMode(null);
      // Synchronize with internal inputMode if needed
      if (pendingMode === 'Text') setInputMode('TXT');
      else if (pendingMode === 'Voice') setInputMode('PTT');
      else if (pendingMode === 'Video') setInputMode('VAD'); // or PTT
    } else {
      handleSendMessage();
    }
  };
`;

code = code.replace(/(const \[inputMode, setInputMode\] = useState<[^>]+>\([^)]+\);)/, `$1${stateInsert}`);

// 3. Replace the chat layout classes
// The Copilot section starts with <div className="chat-messages">
// Actually, let's just replace the SendBall render and the mode selector.

let inputAreaRegex = /<div className="input-area">[\s\S]*?<div\s+className={`send-socket [^>]+>\s*<SendBall onSend=\{([^}]+)\}([\s\S]*?)\/>/m;

code = code.replace(inputAreaRegex, (match, onSendOrig, restProps) => {
  return `<div className="chat-input-area">
              <div className="chat-mode-selector">
                {interactionModes.map(m => (
                  <span 
                    key={m} 
                    className={\`mode-icon \${activeMode === m && !pendingMode ? 'active' : ''} \${pendingMode === m ? 'active blinking' : ''}\`}
                    onClick={() => { setActiveMode(m); setPendingMode(null); }}
                    title={m}
                  >
                    {m === 'Text' ? '✏️' : m === 'Voice' ? '📞' : '🎥'}
                  </span>
                ))}
              </div>
              <div className="input-wrapper" style={{ display: 'flex', gap: '8px', alignItems: 'center', flex: 1 }}>
                {isProcessingAudio && (
                  <span style={{ fontFamily: 'Share Tech Mono', fontSize: '0.7rem', color: 'var(--accent-cyan)', whiteSpace: 'nowrap' }}>
                    ⚙️ TRANSCRIBING...
                  </span>
                )}
                <input 
                  type="text" 
                  className="chat-input"
                  placeholder={\`Ask \${currentUser.aiName || 'your AI'} to build something...\`}
                  value={inputValue}
                  onChange={e => { setInputValue(e.target.value); setPendingMode(null); }}
                  onKeyDown={handleKeyDown}
                  disabled={isTyping}
                  style={{ flex: 1 }}
                />
                <div
                  className={\`send-socket \${backendDown ? 'down' : ''} \${!inputValue.trim() || isTyping ? 'idle' : ''} \${isRecording ? 'rec' : ''}\`}
                  title={backendDown ? 'backend is down — press to ignite' : 'spin to select mode · press to lock/send'}
                >
                  <SendBall onSend={inputValue.trim() ? ${onSendOrig} : handleModeConfirm} ${restProps} onRollStep={handleRollStep} />`;
});

// Replace <div className="chat-messages"> with <div className="chat-messages-container">
code = code.replace(/<div className="chat-messages">/, `<div className="chat-messages-container">`);

// Replace <div key={idx} className={`message ${msg.role}`}> with <div key={idx} className={`chat-bubble-row ${msg.role}`}>
code = code.replace(/<div key=\{idx\} className=\{`message \$\{msg\.role\}`\}>/g, `<div key={idx} className={\`chat-bubble-row \${msg.role}\`}>`);

// Replace <div className="message-avatar"... to be removed because avatars are fixed
// Actually, let's keep it simple: replace the whole message rendering if possible, but regex might be brittle.
// I'll just change the message classes.
code = code.replace(/<div className="message-content">/g, `<div className="chat-bubble ${"${msg.role}"}">`);

fs.writeFileSync('src/App.tsx', code);
