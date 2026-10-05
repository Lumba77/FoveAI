const fs = require('fs');
let code = fs.readFileSync('src/App.tsx', 'utf8');

const explanationMap = `
  const getModeExplanation = (m: string | null) => {
    switch (m) {
      case 'TEXT': return "TEXT MODE: Type messages with your keyboard";
      case 'DICTATE': return "DICTATE MODE: Speak and let AI transcribe to text";
      case 'Vocal PTT': return "VOCAL PTT: Hold ball to record audio, release to send";
      case 'Vocal VAD': return "VOCAL VAD: Hands-free continuous audio chat";
      case 'Video PTT': return "VIDEO PTT: Hold ball to record video, release to send";
      case 'Video VAD': return "VIDEO VAD: Hands-free continuous video chat";
      default: return \`Ask \${currentUser.aiName || 'your AI'} to build something...\`;
    }
  };
`;

if (!code.includes('getModeExplanation')) {
  code = code.replace(/const interactionModes:/, explanationMap + '\n  const interactionModes:');
}

const inputAreaRegex = /<div className="chat-input-area">[\s\S]*?<div\s+className={`send-socket [^>]+>\s*<SendBall onSend=\{inputValue\.trim\(\) \? backend\.state === 'down' \? backend\.ignite : handleSendMessage : handleModeConfirm\}([\s\S]*?) \/>/m;

const newInputArea = `<div className="chat-input-area">
              <div className="chat-mode-selector" style={{ opacity: pendingMode ? 1 : 0, transition: 'opacity 0.3s', pointerEvents: pendingMode ? 'auto' : 'none', position: 'absolute', right: '100px', bottom: '80px', background: 'rgba(11,15,26,0.9)', padding: '10px 20px', borderRadius: '12px', border: '1px solid var(--accent-cyan)', display: 'flex', gap: '16px', boxShadow: '0 0 20px rgba(0, 243, 255, 0.2)' }}>
                {interactionModes.map(m => (
                  <span 
                    key={m} 
                    className={\`mode-icon \${pendingMode === m ? 'active blinking' : ''}\`}
                    onClick={() => { setActiveMode(m as any); setPendingMode(null); }}
                    title={m}
                    style={{ fontSize: pendingMode === m ? '1.5rem' : '1.2rem', opacity: pendingMode === m ? 1 : 0.4, transition: 'all 0.2s', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}
                  >
                    <span style={{ fontSize: '1.8rem' }}>
                      {m === 'TEXT' ? '✏️' : 
                       m === 'DICTATE' ? '🗣️' : 
                       m.includes('Vocal') ? '📞' : '🎥'}
                    </span>
                    {pendingMode === m && (
                      <span style={{ fontSize: '0.6rem', color: 'var(--accent-cyan)', fontFamily: 'Share Tech Mono' }}>{m}</span>
                    )}
                  </span>
                ))}
              </div>
              <div className="input-wrapper" style={{ display: 'flex', gap: '8px', alignItems: 'center', flex: 1, position: 'relative' }}>
                {isProcessingAudio && (
                  <span style={{ fontFamily: 'Share Tech Mono', fontSize: '0.7rem', color: 'var(--accent-cyan)', whiteSpace: 'nowrap' }}>
                    ⚙️ TRANSCRIBING...
                  </span>
                )}
                
                <input 
                  type="text" 
                  className="chat-input"
                  placeholder={pendingMode ? "" : getModeExplanation(activeMode)}
                  value={pendingMode ? "" : inputValue}
                  onChange={e => { setInputValue(e.target.value); setPendingMode(null); }}
                  onKeyDown={handleKeyDown}
                  disabled={isTyping || !!pendingMode}
                  style={{ 
                    flex: 1, 
                    transition: 'all 0.3s',
                    borderColor: pendingMode ? 'var(--accent-cyan)' : undefined,
                    boxShadow: pendingMode ? '0 0 15px rgba(0, 243, 255, 0.3) inset' : undefined,
                    background: pendingMode ? 'rgba(0, 243, 255, 0.05)' : undefined
                  }}
                />
                
                {pendingMode && (
                  <div style={{ position: 'absolute', left: '20px', pointerEvents: 'none', color: 'var(--accent-cyan)', fontFamily: 'Share Tech Mono', fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span className="blinking">▶</span>
                    {getModeExplanation(pendingMode)}
                    <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.75rem', marginLeft: '10px' }}>(press ball to lock)</span>
                  </div>
                )}

                <div
                  className={\`send-socket \${backendDown ? 'down' : ''} \${!inputValue.trim() || isTyping ? 'idle' : ''} \${isRecording ? 'rec' : ''}\`}
                  title={backendDown ? 'backend is down — press to ignite' : 'spin to select mode · press to lock/send'}
                  style={{ zIndex: 100 }}
                >
                  <SendBall onSend={inputValue.trim() ? backend.state === 'down' ? backend.ignite : handleSendMessage : handleModeConfirm}$1 />`;

code = code.replace(inputAreaRegex, newInputArea);
fs.writeFileSync('src/App.tsx', code);
