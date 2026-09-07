const { spawn } = require('child_process');

const server = spawn('node', ['C:\\Users\\danie\\program\\FoveAI\\Forge\\scratch\\TokenSlayer\\mcp-server\\build\\index.js']);

server.stdout.on('data', (data) => {
  console.log(data.toString());
});

server.stderr.on('data', (data) => {
  console.error(data.toString());
});

const req = {
  jsonrpc: "2.0",
  id: 1,
  method: "tools/call",
  params: {
    name: "analyze_workspace",
    arguments: {
      directoryPath: "C:\\Users\\danie\\program\\FoveAI",
      maxTokens: 8192,
      format: "json"
    }
  }
};

// Send init
const initReq = {
  jsonrpc: "2.0",
  id: 0,
  method: "initialize",
  params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "test", version: "1.0.0" } }
};
server.stdin.write(JSON.stringify(initReq) + '\n');

// Wait and send actual request
setTimeout(() => {
  server.stdin.write(JSON.stringify(req) + '\n');
}, 500);

setTimeout(() => {
  server.kill();
}, 8000);
