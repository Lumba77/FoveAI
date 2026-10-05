const fs = require('fs');
let code = fs.readFileSync('src/App.tsx', 'utf8');

// 1. Add state for jenPinned
if (!code.includes('const [jenPinned')) {
  code = code.replace(/const \[activeMode, setActiveMode\] = useState/, "const [jenPinned, setJenPinned] = useState(false);\n  const [activeMode, setActiveMode] = useState");
}

// 2. Replace the AI avatar window in chat-content-wrapper
const oldAiWindowRegex = /<div className="ai-avatar-window">[\s\S]*?<AvatarView mode=\{activeMode\.startsWith\('Video'\) \? 'video' : 'still'\} \/>\s*<\/div>/;

const newChatAiWindow = `{!jenPinned && (
              <div className="ai-avatar-window">
                <span className="ai-avatar-name">
                  {currentUser.aiName || 'JEN'}
                  <span style={{ float: 'right', cursor: 'pointer', opacity: 0.6 }} onClick={() => setJenPinned(true)} title="Pin Jen to all screens">📌</span>
                </span>
                <AvatarView mode={activeMode.startsWith('Video') ? 'video' : 'still'} />
              </div>
            )}`;

code = code.replace(oldAiWindowRegex, newChatAiWindow);

// 3. Add the pinned window at the very end of the App container
const oldEnd = `      <SettingsOverlay isVisible={showSettings} onClose={() => setShowSettings(false)} />
    </div>`;

const newEnd = `      <SettingsOverlay isVisible={showSettings} onClose={() => setShowSettings(false)} />
      
      {jenPinned && (
        <div className="ai-avatar-window pinned">
          <span className="ai-avatar-name">
            {currentUser.aiName || 'JEN'}
            <span style={{ float: 'right', cursor: 'pointer', opacity: 1 }} onClick={() => setJenPinned(false)} title="Unpin Jen">📌</span>
          </span>
          <AvatarView mode={activeMode.startsWith('Video') ? 'video' : 'still'} />
        </div>
      )}
    </div>`;

code = code.replace(oldEnd, newEnd);

fs.writeFileSync('src/App.tsx', code);

// 4. Update CSS
let css = fs.readFileSync('src/components/ChatLayout.css', 'utf8');
const pinnedCss = `
.ai-avatar-window.pinned {
  position: fixed;
  top: 20px;
  right: 20px;
  left: auto;
  z-index: 9999;
  width: 150px;
  height: 200px;
  box-shadow: 0 10px 40px rgba(0,210,255,0.4), inset 0 0 20px rgba(0,0,0,0.5);
  border: 1px solid rgba(0, 210, 255, 0.6);
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
`;
if (!css.includes('.ai-avatar-window.pinned')) {
  css += pinnedCss;
  fs.writeFileSync('src/components/ChatLayout.css', css);
}
