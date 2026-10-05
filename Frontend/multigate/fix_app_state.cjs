const fs = require('fs');
let code = fs.readFileSync('src/App.tsx', 'utf8');

const missingCode = `
  const [jenPinned, setJenPinned] = useState(false);
  const [activeMode, setActiveMode] = useState<'TEXT' | 'DICTATE' | 'Vocal PTT' | 'Vocal VAD' | 'Video PTT' | 'Video VAD'>('TEXT');
  const [pendingMode, setPendingMode] = useState<'TEXT' | 'DICTATE' | 'Vocal PTT' | 'Vocal VAD' | 'Video PTT' | 'Video VAD' | null>(null);
  
  const interactionModes: ('TEXT' | 'DICTATE' | 'Vocal PTT' | 'Vocal VAD' | 'Video PTT' | 'Video VAD')[] = [
    'TEXT', 'DICTATE', 'Vocal PTT', 'Vocal VAD', 'Video PTT', 'Video VAD'
  ];

  const getModeExplanation = (m: string | null) => {
    switch (m) {
      case 'TEXT': return "TEXT MODE: Type messages with your keyboard";
      case 'DICTATE': return "DICTATE MODE: Speak and let AI transcribe to text";
      case 'Vocal PTT': return "VOCAL PTT: Hold ball to record audio, release to send";
      case 'Vocal VAD': return "VOCAL VAD: Hands-free continuous audio chat";
      case 'Video PTT': return "VIDEO PTT: Hold ball to record video, release to send";
      case 'Video VAD': return "VIDEO VAD: Hands-free continuous video chat";
      default: return \`Ask \${currentUser?.aiName || 'your AI'} to build something...\`;
    }
  };

  const handleRollStep = (dir: number) => {
    if (inputValue.trim()) return;
    setPendingMode(prev => {
       const current = prev || activeMode;
       let idx = interactionModes.indexOf(current as any) + dir;
       if (idx < 0) idx = interactionModes.length - 1;
       if (idx >= interactionModes.length) idx = 0;
       return interactionModes[idx];
    });
  };

  const handleModeConfirm = () => {
    if (pendingMode) {
      setActiveMode(pendingMode);
      setPendingMode(null);
      if (pendingMode === 'TEXT' || pendingMode === 'DICTATE') setInputMode('TXT');
      else if (pendingMode === 'Vocal PTT' || pendingMode === 'Video PTT') setInputMode('PTT');
      else setInputMode('VAD');
    } else {
      handleSendMessage();
    }
  };
`;

code = code.replace(/const \[isProcessingAudio, setIsProcessingAudio\] = useState\(false\);/, 
  'const [isProcessingAudio, setIsProcessingAudio] = useState(false);\n' + missingCode);

fs.writeFileSync('src/App.tsx', code);
