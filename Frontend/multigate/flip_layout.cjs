const fs = require('fs');
let css = fs.readFileSync('src/components/ChatLayout.css', 'utf8');

// 1. Flip AI Window
css = css.replace(/(\.ai-avatar-window\s*\{[\s\S]*?)left:\s*20px;/, '$1right: 20px;\n  left: auto;');

// 2. Flip User Window
css = css.replace(/(\.user-avatar-window\s*\{[\s\S]*?)right:\s*20px;/, '$1left: 20px;\n  right: auto;');
// Fix text-align for user name
css = css.replace(/(\.user-avatar-name\s*\{[\s\S]*?)text-align:\s*right;/, '$1text-align: left;');
// Fix text-align for AI name (if we want it right aligned now?)
// Actually AI name is left by default, let's make it right aligned
css = css.replace(/(\.ai-avatar-name\s*\{[\s\S]*?)left:\s*0;/, '$1left: 0;\n  text-align: right;');

// 3. Flip Chat Bubbles
const oldBubbles = `.chat-bubble-row.ai {
  justify-content: flex-start;
}

.chat-bubble-row.user {
  justify-content: flex-flex-end;
}

.chat-bubble {
  max-width: 70%;
  padding: 16px 20px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(11, 15, 26, 0.6);
  position: relative;
  font-size: 0.95rem;
  line-height: 1.5;
}

.chat-bubble.ai {
  border-color: rgba(0, 243, 255, 0.4);
  border-top-left-radius: 0;
  margin-left: 20px;
}

.chat-bubble.ai::before {
  content: '';
  position: absolute;
  top: -1px;
  left: -20px;
  border-width: 10px 20px 0 0;
  border-style: solid;
  border-color: rgba(0, 243, 255, 0.4) transparent transparent transparent;
}

.chat-bubble.user {
  border-color: rgba(255, 106, 0, 0.4);
  border-bottom-right-radius: 0;
  margin-right: 20px;
  margin-left: auto;
}

.chat-bubble.user::after {
  content: '';
  position: absolute;
  bottom: -1px;
  right: -20px;
  border-width: 0 0 10px 20px;
  border-style: solid;
  border-color: transparent transparent rgba(255, 106, 0, 0.4) transparent;
}`;

const newBubbles = `.chat-bubble-row.ai {
  justify-content: flex-end;
}

.chat-bubble-row.user {
  justify-content: flex-start;
}

.chat-bubble {
  max-width: 70%;
  padding: 16px 20px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(11, 15, 26, 0.6);
  position: relative;
  font-size: 0.95rem;
  line-height: 1.5;
}

.chat-bubble.ai {
  border-color: rgba(0, 243, 255, 0.4);
  border-top-right-radius: 0;
  margin-right: 20px;
  margin-left: auto;
}

.chat-bubble.ai::after {
  content: '';
  position: absolute;
  top: -1px;
  right: -20px;
  border-width: 10px 0 0 20px;
  border-style: solid;
  border-color: rgba(0, 243, 255, 0.4) transparent transparent transparent;
}

.chat-bubble.user {
  border-color: rgba(255, 106, 0, 0.4);
  border-bottom-left-radius: 0;
  margin-left: 20px;
  margin-right: auto;
}

.chat-bubble.user::before {
  content: '';
  position: absolute;
  bottom: -1px;
  left: -20px;
  border-width: 0 20px 10px 0;
  border-style: solid;
  border-color: transparent rgba(255, 106, 0, 0.4) transparent transparent;
}`;

css = css.replace(oldBubbles, newBubbles);

fs.writeFileSync('src/components/ChatLayout.css', css);
