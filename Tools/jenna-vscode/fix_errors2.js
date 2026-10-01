var fs = require('fs');
var f;

// contextAnalyzer.ts - remove unused FoveatedClient import
f = fs.readFileSync('src/handlers/contextAnalyzer.ts', 'utf8');
f = f.replace("import { FoveatedClient } from '../memory/foveatedClient';", '');
fs.writeFileSync('src/handlers/contextAnalyzer.ts', f);
console.log('contextAnalyzer fixed');

// messageRouter.ts - complex fixes
f = fs.readFileSync('src/handlers/messageRouter.ts', 'utf8');
// Remove extensionUri from constructor
f = f.replace(/extensionUri: vscode\.Uri,\n    /, '');
// Remove unused onStatus
f = f.replace(/const onStatus = .*?\n/, '');
// Fix SessionManager constructor call - remove _getSessionStart
f = f.replace(/new SessionManager\(workspaceId, storageUri, this._post, \(\) => this._history\.value, \(\) => this._sessionStart\)/, 'new SessionManager(workspaceId, storageUri, this._post, () => this._history.value)');
// Fix ContextAnalyzer constructor call - remove extra params
f = f.replace(/new ContextAnalyzer\(client, workspaceId, \(\) => this\._activePersona, this\._post, \(t\) => onChat\(t\)\)/, 'new ContextAnalyzer((t) => onChat(t))');
// Fix messageRouter.ts sessionManager import to remove unused
f = f.replace("private _getHistory: () => ChatMessage[],\n    private _getSessionStart: () => string", 'private _getHistory: () => ChatMessage[]');
fs.writeFileSync('src/handlers/messageRouter.ts', f);
console.log('messageRouter fixed');

// sessionManager.ts - fix constructor to remove _getSessionStart
f = fs.readFileSync('src/handlers/sessionManager.ts', 'utf8');
f = f.replace("private _getHistory: () => ChatMessage[],\n  ) {", 'private _getHistory: () => ChatMessage[],');
f = f.replace(/private _getHistory: \(\) => ChatMessage\[\],\n  \) {/g, 'private _getHistory: () => ChatMessage[],');
// Add closing ) { after the last param
var idx = f.indexOf('private _getHistory: () => ChatMessage[],');
var after = f.indexOf('\n', idx + 40);
f = f.slice(0, after) + ') {' + f.slice(after);
// Remove orphaned constructor body if any
f = f.replace(') {: ) {', ') {');
fs.writeFileSync('src/handlers/sessionManager.ts', f);
console.log('sessionManager fixed');
