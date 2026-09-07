const { spawn } = require('child_process');

const server = spawn('node', ['C:\\Users\\danie\\program\\LUMAX\\Forge\\scratch\\TokenSlayer\\mcp-server\\build\\index.js']);

let out = "";
server.stdout.on('data', (data) => {
  out += data.toString();
  if (out.includes("result")) {
      console.log(out.substring(0, 1500) + "...");
  }
});

const req = {
  jsonrpc: "2.0",
  id: 1,
  method: "tools/call",
  params: {
    name: "analyze_workspace",
    arguments: {
      directoryPath: "C:\\Users\\danie\\program\\LUMAX",
      maxTokens: 8192,
      format: "json"
    }
  }
};

const initReq = {
  jsonrpc: "2.0",
  id: 0,
  method: "initialize",
  params: { protocolVersion: "2024-11-05", capabilities: {}, clientInfo: { name: "test", version: "1.0.0" } }
};
server.stdin.write(JSON.stringify(initReq) + '\n');

setTimeout(() => {
  server.stdin.write(JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized", params: {} }) + '\n');
  server.stdin.write(JSON.stringify(req) + '\n');
}, 500);

setTimeout(() => {
  server.kill();
}, 10000);
