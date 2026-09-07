const fs = require('fs');
const content = fs.readFileSync('src/webview/chat.html', 'utf8');
const tag = '<script nonce="{{NONCE}}">';
const start = content.indexOf(tag);
const end = content.lastIndexOf('</script>');
if (start === -1 || end === -1) {
  console.log('Script tag not found');
  process.exit(1);
}
const script = content.substring(start + tag.length, end);
try {
  new Function('acquireVsCodeApi', script);
  console.log('SCRIPT OK');
} catch (e) {
  console.error('SCRIPT ERROR:', e);
}
