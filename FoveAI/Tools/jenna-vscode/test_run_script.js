const fs = require('fs');
const html = fs.readFileSync('c:/Users/danie/program/LUMAX/Tools/jenna-vscode/src/webview/chat.html', 'utf8');

// Replace $historyBtn with a dummy or declaration in html to test what else fails
let code = html.match(/<script nonce="{{NONCE}}">([\s\S]*?)<\/script>/)[1];
code = 'const $historyBtn = document.getElementById("btn-list-sessions");\n' + code;

const window = {
    addEventListener: () => {},
    removeEventListener: () => {},
    innerHeight: 800,
    innerWidth: 600,
    localStorage: { getItem: () => null, setItem: () => {} },
    location: { reload: () => {} }
};
const localStorage = { getItem: () => null, setItem: () => {} };
const document = {
    getElementById: (id) => ({
        id,
        style: {},
        classList: { add: () => {}, remove: () => {}, contains: () => false, toggle: () => false },
        addEventListener: () => {},
        querySelectorAll: () => [],
        querySelector: () => null,
        appendChild: () => {}
    }),
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: (tag) => ({
        style: {},
        classList: { add: () => {}, remove: () => {}, contains: () => false, toggle: () => false },
        addEventListener: () => {},
        querySelectorAll: () => [],
        querySelector: () => null,
        appendChild: () => {}
    }),
    body: { appendChild: () => {}, style: {} },
    addEventListener: () => {}
};
const acquireVsCodeApi = () => ({ postMessage: (msg) => console.log('postMessage:', msg.type) });

try {
    const fn = new Function('window', 'document', 'acquireVsCodeApi', 'localStorage', code);
    fn(window, document, acquireVsCodeApi, localStorage);
    console.log('SUCCESS: Script evaluated completely with 0 errors!');
} catch (err) {
    console.error('ERROR during script evaluation:\n', err);
}
