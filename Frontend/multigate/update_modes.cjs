const fs = require('fs');
let code = fs.readFileSync('src/App.tsx', 'utf8');

const oldState = `const [activeMode, setActiveMode] = useState<'Text' | 'Voice' | 'Video'>('Text');
  const [pendingMode, setPendingMode] = useState<'Text' | 'Voice' | 'Video' | null>(null);
  
  const interactionModes: ('Text' | 'Voice' | 'Video')[] = ['Text', 'Voice', 'Video'];`;

const newState = `const [activeMode, setActiveMode] = useState<'TEXT' | 'DICTATE' | 'Vocal PTT' | 'Vocal VAD' | 'Video PTT' | 'Video VAD'>('TEXT');
  const [pendingMode, setPendingMode] = useState<'TEXT' | 'DICTATE' | 'Vocal PTT' | 'Vocal VAD' | 'Video PTT' | 'Video VAD' | null>(null);
  
  const interactionModes: ('TEXT' | 'DICTATE' | 'Vocal PTT' | 'Vocal VAD' | 'Video PTT' | 'Video VAD')[] = [
    'TEXT', 'DICTATE', 'Vocal PTT', 'Vocal VAD', 'Video PTT', 'Video VAD'
  ];`;

code = code.replace(oldState, newState);

// Update icon mapping
const oldIcons = `{interactionModes.map(m => (
                  <span 
                    key={m} 
                    className={\`mode-icon \${activeMode === m && !pendingMode ? 'active' : ''} \${pendingMode === m ? 'active blinking' : ''}\`}
                    onClick={() => { setActiveMode(m); setPendingMode(null); }}
                    title={m}
                  >
                    {m === 'Text' ? '✏️' : m === 'Voice' ? '📞' : '🎥'}
                  </span>
                ))}`;

const newIcons = `{interactionModes.map(m => (
                  <span 
                    key={m} 
                    className={\`mode-icon \${activeMode === m && !pendingMode ? 'active' : ''} \${pendingMode === m ? 'active blinking' : ''}\`}
                    onClick={() => { setActiveMode(m as any); setPendingMode(null); }}
                    title={m}
                    style={{ fontSize: (activeMode === m || pendingMode === m) ? '1.4rem' : '1.1rem', margin: '0 4px', display: (activeMode === m || pendingMode === m) ? 'inline-block' : 'none' }}
                  >
                    {m === 'TEXT' ? '✏️ TEXT' : 
                     m === 'DICTATE' ? '🗣️ DICTATE' : 
                     m === 'Vocal PTT' ? '📞 VOCAL PTT' : 
                     m === 'Vocal VAD' ? '🎙️ VOCAL VAD' : 
                     m === 'Video PTT' ? '🎥 VIDEO PTT' : '📹 VIDEO VAD'}
                  </span>
                ))}`;

code = code.replace(oldIcons, newIcons);

// Update mode sync
const oldSync = `if (pendingMode === 'Text') setInputMode('TXT');
      else if (pendingMode === 'Voice') setInputMode('PTT');
      else if (pendingMode === 'Video') setInputMode('VAD'); // or PTT`;

const newSync = `if (pendingMode === 'TEXT') setInputMode('TXT');
      else if (pendingMode === 'DICTATE') setInputMode('TXT'); // Dictate acts like text input logically here for now
      else if (pendingMode === 'Vocal PTT') setInputMode('PTT');
      else if (pendingMode === 'Vocal VAD') setInputMode('VAD');
      else if (pendingMode === 'Video PTT') setInputMode('PTT');
      else if (pendingMode === 'Video VAD') setInputMode('VAD');`;

code = code.replace(oldSync, newSync);

fs.writeFileSync('src/App.tsx', code);
