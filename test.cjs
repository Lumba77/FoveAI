const fs = require('fs');
const content = fs.readFileSync('c:/Users/danie/program/LUMAX/Tools/jenna-vscode/src/webview/chat.html', 'utf8');
const scriptMatch = content.match(/<script nonce="\{\{NONCE\}\}">([\s\S]*?)<\/script>/);
if (scriptMatch) {
  try {
    new Function(scriptMatch[1]);
    console.log('Syntax OK');
  } catch (e) {
    console.error('Syntax Error:', e.message);
  }
} else {
  console.log('no script found');
}
