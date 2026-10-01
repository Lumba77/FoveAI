var fs = require('fs');
var f;

// 1. contextAnalyzer.ts - remove unused params
f = fs.readFileSync('src/handlers/contextAnalyzer.ts', 'utf8');
f = f.replace(/private _client: FoveatedClient;[\s\S]*?private _onChat:/, 'private _onChat:');
fs.writeFileSync('src/handlers/contextAnalyzer.ts', f);
console.log('1/3 contextAnalyzer fixed');

// 2. messageRouter.ts - add _buffer field, remove extensionUri, fix refs
f = fs.readFileSync('src/handlers/messageRouter.ts', 'utf8');
f = f.replace('export class MessageRouter {', 'export class MessageRouter {\n  private _buffer: ExecutionBuffer;');
f = f.replace(/\bbuffer\./g, 'this._buffer.');
f = f.replace(/, extensionUri: vscode\.Uri,/, ',');
var idx = f.indexOf('this._chat = new ChatHandler');
f = f.slice(0, idx) + 'this._buffer = buffer;\n    ' + f.slice(idx);
fs.writeFileSync('src/handlers/messageRouter.ts', f);
console.log('2/3 messageRouter fixed');

// 3. sessionManager.ts - remove unused param
f = fs.readFileSync('src/handlers/sessionManager.ts', 'utf8');
f = f.replace(/,\n    private _getSessionStart: \(\) => string,/, ',');
fs.writeFileSync('src/handlers/sessionManager.ts', f);
console.log('3/3 sessionManager fixed');
