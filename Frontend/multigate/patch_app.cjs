const fs = require('fs');
let code = fs.readFileSync('src/App.tsx', 'utf8');

// 1. Update SendBall definition
code = code.replace(
  /function SendBall\(\{ onSend, onHoldStart, onHoldEnd, health, pressHint \}: \{ onSend: \(\) => void; onHoldStart\?: \(\) => void; onHoldEnd\?: \(\) => void; health\?: 'ok' \| 'warn' \| 'down' \| 'off' \| null; pressHint\?: string \}\) \{/,
  `function SendBall({ onSend, onHoldStart, onHoldEnd, health, pressHint, onRollStep }: { onSend: () => void; onHoldStart?: () => void; onHoldEnd?: () => void; onRollStep?: (dir: number) => void; health?: 'ok' | 'warn' | 'down' | 'off' | null; pressHint?: string }) {`
);
code = code.replace(
  /return <Trackball store=\{tb\} size=\{56\} bare health=\{health\} onPress=\{onSend\} onHoldStart=\{onHoldStart\} onHoldEnd=\{onHoldEnd\} pressHint=\{pressHint \|\| 'press to send · hold to talk'\} \/>;/,
  `return <Trackball store={tb} size={56} bare health={health} onPress={onSend} onHoldStart={onHoldStart} onHoldEnd={onHoldEnd} onRollStep={onRollStep} pressHint={pressHint || 'press to send · hold to talk'} />;`
);

fs.writeFileSync('src/App.tsx', code);
