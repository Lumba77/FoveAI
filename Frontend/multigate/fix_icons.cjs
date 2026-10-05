const fs = require('fs');
let code = fs.readFileSync('src/App.tsx', 'utf8');

const oldIcons = `style={{ fontSize: (activeMode === m || pendingMode === m) ? '1.4rem' : '1.1rem', margin: '0 4px', display: (activeMode === m || pendingMode === m) ? 'inline-block' : 'none' }}`;

const newIcons = `style={{ fontSize: (activeMode === m || pendingMode === m) ? '1.2rem' : '1.0rem', margin: '0 4px', opacity: (activeMode === m && !pendingMode) || pendingMode === m ? 1 : 0.3, transition: 'all 0.2s' }}`;

code = code.replace(oldIcons, newIcons);
fs.writeFileSync('src/App.tsx', code);
