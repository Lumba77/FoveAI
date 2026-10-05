const fs = require('fs');
let css = fs.readFileSync('src/components/ChatLayout.css', 'utf8');

const newAiWindow = `.ai-avatar-window {
  position: absolute;
  top: 20px;
  left: 20px;
  width: 180px;
  height: 220px;
  background: rgba(22, 28, 36, 0.6);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(0, 210, 255, 0.3);
  box-shadow: inset 0 0 20px rgba(0,0,0,0.5), 0 8px 32px rgba(0,210,255,0.15);
  border-radius: 16px;
  overflow: hidden;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ai-avatar-name {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding: 8px 12px;
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.75rem;
  color: #00d2ff;
  background: linear-gradient(180deg, rgba(0,0,0,0.85) 0%, transparent 100%);
  z-index: 20;
  border-bottom: 1px solid rgba(0, 210, 255, 0.1);
  letter-spacing: 1px;
}`;

const newUserWindow = `.user-avatar-window {
  position: absolute;
  bottom: 80px;
  right: 20px;
  width: 140px;
  height: 180px;
  background: rgba(22, 28, 36, 0.6);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 184, 0, 0.3);
  box-shadow: inset 0 0 20px rgba(0,0,0,0.5), 0 8px 32px rgba(255, 184, 0, 0.1);
  border-radius: 16px;
  overflow: hidden;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
}

.user-avatar-name {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 8px 12px;
  text-align: right;
  font-family: 'Share Tech Mono', monospace;
  font-size: 0.7rem;
  color: #ffb800;
  background: linear-gradient(0deg, rgba(0,0,0,0.85) 0%, transparent 100%);
  z-index: 20;
  border-top: 1px solid rgba(255, 184, 0, 0.1);
  letter-spacing: 1px;
}`;

// Replace AI window css
css = css.replace(/\.ai-avatar-window\s*\{[\s\S]*?\}\s*\.ai-avatar-name\s*\{[\s\S]*?\}/, newAiWindow);
css = css.replace(/\.user-avatar-window\s*\{[\s\S]*?\}\s*\.user-avatar-name\s*\{[\s\S]*?\}/, newUserWindow);

fs.writeFileSync('src/components/ChatLayout.css', css);
