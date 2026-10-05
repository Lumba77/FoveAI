const fs = require('fs');
let code = fs.readFileSync('src/App.tsx', 'utf8');

const avatarWindows = `
            <div className="chat-content-wrapper">
              <div className="ai-avatar-window">
                <span className="ai-avatar-name">{currentUser.aiName || 'JEN'}</span>
                <AvatarView mode={activeMode === 'Video' ? 'video' : 'still'} />
              </div>
              <div className="user-avatar-window">
                <span className="user-avatar-name">{currentUser.firstName?.toUpperCase() || 'USER'}</span>
                <img src="/avatars/user_fallback.png" alt="User" className="user-avatar-image" onError={(e) => (e.currentTarget.src = '/avatars/fallback.png')} />
              </div>
              <div className="chat-messages-container">
`;

code = code.replace(/<div className="chat-messages-container">/, avatarWindows);

// And close the wrapper right after the <div ref={chatEndRef} /></div>
code = code.replace(/<div ref=\{chatEndRef\} \/>\s*<\/div>/, `<div ref={chatEndRef} />\n            </div>\n            </div>`);

// I also need to make sure AvatarView is imported
if (!code.includes('import { AvatarView }')) {
  code = code.replace(/import .* from 'react';/, `$& \nimport { AvatarView } from './components/AvatarView';`);
}

fs.writeFileSync('src/App.tsx', code);
