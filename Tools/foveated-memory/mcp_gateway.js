const fs = require('fs');
const path = require('path');
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');

class MCPGateway {
    constructor(configPath) {
        this.configPath = configPath;
        this.clients = {}; // serverName -> Client
        this.toolsCache = []; // Flattened list of OpenAI-formatted tools
        this.serverToolMap = {}; // toolName -> serverName mapping
    }

    async init() {
        if (!fs.existsSync(this.configPath)) {
            console.warn(`[MCP Gateway] Config not found at ${this.configPath}. MCP Gateway disabled.`);
            return;
        }

        let config;
        try {
            config = JSON.parse(fs.readFileSync(this.configPath, 'utf8'));
        } catch (e) {
            console.error(`[MCP Gateway] Failed to parse config: ${e.message}`);
            return;
        }

        const servers = config.mcpServers || {};
        for (const [serverName, serverConfig] of Object.entries(servers)) {
            if (serverConfig.disabled) continue;

            console.log(`[MCP Gateway] Starting server: ${serverName}...`);
            try {
                let cmd = serverConfig.command;
                let cwd = path.dirname(this.configPath);
                
                const env = { ...process.env, ...serverConfig.env };
                
                // Hack: stdio transport might not support cwd directly in constructor, but usually it does. Wait, if command is a relative path, we must resolve it.
                if (cmd !== 'node' && cmd !== 'python' && !cmd.startsWith('C:\\')) {
                    cmd = path.resolve(cwd, cmd);
                }
                const resolvedArgs = (serverConfig.args || []).map(arg => arg.startsWith('Tools/') || arg.startsWith('Backend/') || arg.startsWith('Forge/') ? path.resolve(cwd, arg) : arg);
                
                const finalTransport = new StdioClientTransport({
                    command: cmd,
                    args: resolvedArgs,
                    env: env
                });

                const client = new Client(
                    { name: "foveated-mcp-gateway", version: "1.0.0" },
                    { capabilities: {} }
                );

                await client.connect(transport);
                this.clients[serverName] = client;
                console.log(`[MCP Gateway] Connected to ${serverName}`);

                const toolsResp = await client.request({ method: "tools/list" }, z => z);
                if (toolsResp && toolsResp.tools) {
                    for (const tool of toolsResp.tools) {
                        this.toolsCache.push({
                            type: "function",
                            function: {
                                name: tool.name,
                                description: tool.description || "",
                                parameters: tool.inputSchema || {}
                            }
                        });
                        this.serverToolMap[tool.name] = serverName;
                    }
                    console.log(`[MCP Gateway] Cached ${toolsResp.tools.length} tools from ${serverName}`);
                }
            } catch (err) {
                console.error(`[MCP Gateway] Error starting ${serverName}:`, err.message);
            }
        }
    }

    getOpenAITools() {
        return this.toolsCache.length > 0 ? this.toolsCache : undefined;
    }

    async executeTool(toolName, args) {
        const serverName = this.serverToolMap[toolName];
        if (!serverName) {
            throw new Error(`Tool ${toolName} not found in any connected MCP server.`);
        }

        const client = this.clients[serverName];
        if (!client) {
            throw new Error(`Client for ${serverName} is not connected.`);
        }

        console.log(`[MCP Gateway] Executing tool ${toolName} on ${serverName}...`);
        
        try {
            const result = await client.request(
                { method: "tools/call", params: { name: toolName, arguments: args } },
                z => z
            );
            
            if (result && result.content && result.content.length > 0) {
                return result.content.map(c => c.text).join('\n');
            }
            return "Tool executed successfully with no output.";
        } catch (e) {
            console.error(`[MCP Gateway] Tool execution error for ${toolName}:`, e);
            return `Error executing tool: ${e.message}`;
        }
    }
}

module.exports = MCPGateway;
