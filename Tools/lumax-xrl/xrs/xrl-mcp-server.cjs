#!/usr/bin/env node
/**
 * XRL MCP Server — X-Ray Language Binary Tokenizer for LLM Consumption
 * 
 * Provides 3 MCP tools:
 *   1. load_xrl — Load a file as XRL skeleton at specified depth
 *   2. expand_xrl — Expand a specific block (function/class) to full detail
 *   3. search_xrl — Search across XRL-skeletonized files
 * 
 * Protocol: JSON-RPC 2.0 over stdio (standard MCP transport)
 * 
 * Usage:
 *   node xrl-mcp-server.js
 * 
 * Integration with LUMAX MCP ecosystem:
 *   - Registers as "xrl" tool namespace
 *   - Can be launched alongside lumax_mcp_server.py
 *   - Uses XRL binary format for token-efficient responses
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const XRL_CLI = path.join(__dirname, 'xrl.cjs');
const XRS_PATH = path.join(__dirname, 'xrs.cjs');
const TOKENSLAYER_PATH = path.join(__dirname, '..', 'scratch', 'TokenSlayer', 'standalone', 'tokenslayer.js');

// ─── Configuration ──────────────────────────────────────────────

const CONFIG = {
    defaultDepth: 2,
    maxFileSize: 1024 * 1024,  // 1MB max
    cacheSize: 50,              // Max cached skeletons
    searchLimit: 20             // Max search results
};

// ─── Skeleton Cache ─────────────────────────────────────────────

class SkeletonCache {
    constructor(maxSize = CONFIG.cacheSize) {
        this.cache = new Map();
        this.maxSize = maxSize;
    }

    get(filePath, depth) {
        const key = `${filePath}@${depth}`;
        const entry = this.cache.get(key);
        if (entry && Date.now() - entry.timestamp < 60000) { // 1 min TTL
            return entry.data;
        }
        return null;
    }

    set(filePath, depth, data) {
        if (this.cache.size >= this.maxSize) {
            const oldest = this.cache.keys().next().value;
            this.cache.delete(oldest);
        }
        const key = `${filePath}@${depth}`;
        this.cache.set(key, { data, timestamp: Date.now() });
    }
}

const cache = new SkeletonCache();

// ─── XRL Engine ─────────────────────────────────────────────────

class XRLEngine {
    /**
     * Load a file as XRL skeleton
     */
    loadFile(filePath, depth = CONFIG.defaultDepth) {
        // Resolve relative to LUMAX root
        const resolved = path.resolve(filePath);
        
        if (!fs.existsSync(resolved)) {
            return { error: `File not found: ${filePath}` };
        }

        const stat = fs.statSync(resolved);
        if (stat.size > CONFIG.maxFileSize) {
            return { error: `File too large: ${(stat.size / 1024 / 1024).toFixed(1)}MB (max 1MB)` };
        }

        // Check cache
        const cached = cache.get(resolved, depth);
        if (cached) return cached;

        try {
            const result = execSync(
                `node "${XRL_CLI}" "${resolved}" --depth ${depth} --json --stats`,
                { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }
            );
            const data = JSON.parse(result.trim());
            
            // Get the skeleton text for the response
            const skeletonResult = execSync(
                `node "${XRS_PATH}" "${resolved}" --depth ${depth} --json`,
                { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }
            );
            const skeletonData = JSON.parse(skeletonResult.trim());
            
            const response = {
                file: path.basename(resolved),
                language: data.language,
                depth: data.depth,
                originalTokens: data.originalTokens,
                skeletonTokens: data.skeletonTokens,
                binaryTokens: data.binaryTokens,
                textReduction: data.textReduction,
                totalReduction: data.totalReduction,
                skeleton: skeletonData.skeleton.content,
                blocks: this._extractBlocks(skeletonData.skeleton.content)
            };

            cache.set(resolved, depth, response);
            return response;
        } catch (err) {
            return { error: `Skeletonization failed: ${err.message}` };
        }
    }

    /**
     * Expand a specific block to full detail
     */
    expandBlock(filePath, blockName, depth = 0) {
        const resolved = path.resolve(filePath);
        
        if (!fs.existsSync(resolved)) {
            return { error: `File not found: ${filePath}` };
        }

        try {
            const result = execSync(
                `node "${XRL_CLI}" "${resolved}" --depth ${depth} --expand "${blockName}" --json`,
                { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }
            );
            return JSON.parse(result.trim());
        } catch (err) {
            return { error: `Expansion failed: ${err.message}` };
        }
    }

    /**
     * Search across XRL-skeletonized files in a directory
     */
    searchDirectory(dirPath, query, depth = CONFIG.defaultDepth, limit = CONFIG.searchLimit) {
        const resolved = path.resolve(dirPath);
        
        if (!fs.existsSync(resolved) || !fs.statSync(resolved).isDirectory()) {
            return { error: `Directory not found: ${dirPath}` };
        }

        const results = [];
        const files = this._findSourceFiles(resolved);

        for (const file of files.slice(0, limit * 3)) { // Scan more, return top
            try {
                const skeletonResult = execSync(
                    `node "${XRS_PATH}" "${file}" --depth ${depth} --json`,
                    { encoding: 'utf8', maxBuffer: 5 * 1024 * 1024 }
                );
                const data = JSON.parse(skeletonResult.trim());
                const skeleton = data.skeleton.content;
                
                if (skeleton.toLowerCase().includes(query.toLowerCase())) {
                    // Find matching lines with context
                    const lines = skeleton.split('\n');
                    const matches = [];
                    for (let i = 0; i < lines.length; i++) {
                        if (lines[i].toLowerCase().includes(query.toLowerCase())) {
                            const start = Math.max(0, i - 2);
                            const end = Math.min(lines.length, i + 3);
                            matches.push({
                                line: i + 1,
                                context: lines.slice(start, end).join('\n'),
                                match: lines[i].trim()
                            });
                        }
                    }

                    results.push({
                        file: path.relative(resolved, file),
                        language: data.language,
                        matches: matches.length,
                        skeletonTokens: data.skeleton.tokens,
                        reduction: data.skeleton.reduction,
                        lines: matches
                    });
                }
            } catch {
                // Skip files that fail skeletonization
                continue;
            }

            if (results.length >= limit) break;
        }

        return {
            query,
            directory: dirPath,
            depth,
            totalResults: results.length,
            results
        };
    }

    /**
     * Extract block names from skeleton text
     */
    _extractBlocks(skeleton) {
        const blocks = [];
        const lines = skeleton.split('\n');
        
        for (const line of lines) {
            const fnMatch = line.match(/^(\s*)(?:async\s+)?function\s+(\w+)/);
            const clsMatch = line.match(/^(\s*)class\s+(\w+)/);
            const methodMatch = line.match(/^\s*(?:async\s+)?(\w+)\s*\(/);
            const arrowMatch = line.match(/^\s*(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(/);
            
            if (fnMatch) {
                blocks.push({ type: 'function', name: fnMatch[2], indent: fnMatch[1].length });
            } else if (clsMatch) {
                blocks.push({ type: 'class', name: clsMatch[2], indent: clsMatch[1].length });
            } else if (methodMatch && !methodMatch[1].startsWith('if') && !methodMatch[1].startsWith('for') && !methodMatch[1].startsWith('while')) {
                blocks.push({ type: 'method', name: methodMatch[1], indent: 0 });
            } else if (arrowMatch) {
                blocks.push({ type: 'arrow', name: arrowMatch[1], indent: 0 });
            }
        }
        
        return blocks;
    }

    /**
     * Find source files in a directory (recursive, respecting .gitignore patterns)
     */
    _findSourceFiles(dirPath) {
        const sourceExtensions = new Set([
            '.py', '.js', '.ts', '.jsx', '.tsx', '.cjs', '.mjs',
            '.go', '.rs', '.java', '.cs', '.kt', '.swift',
            '.html', '.css', '.scss', '.md', '.json', '.yaml', '.yml',
            '.rb', '.php', '.lua', '.sh', '.bat', '.ps1'
        ]);
        
        const skipDirs = new Set([
            'node_modules', '.venv', 'venv', '__pycache__', '.git',
            '.idea', '.vscode', 'dist', 'build', '.logs', 'archive',
            'chroma_db', 'kuzu_db', 'Data', 'storage', 'models'
        ]);

        const files = [];
        
        const walk = (dir) => {
            try {
                const entries = fs.readdirSync(dir, { withFileTypes: true });
                for (const entry of entries) {
                    const fullPath = path.join(dir, entry.name);
                    if (entry.isDirectory()) {
                        if (!skipDirs.has(entry.name) && !entry.name.startsWith('.')) {
                            walk(fullPath);
                        }
                    } else if (entry.isFile() && sourceExtensions.has(path.extname(entry.name).toLowerCase())) {
                        files.push(fullPath);
                    }
                }
            } catch {
                // Skip inaccessible directories
            }
        };
        
        walk(dirPath);
        return files;
    }
}

const engine = new XRLEngine();

// ─── MCP Protocol ───────────────────────────────────────────────

/**
 * Send a JSON-RPC response to stdout
 */
function sendResponse(id, result) {
    const response = {
        jsonrpc: '2.0',
        id,
        result
    };
    const message = JSON.stringify(response);
    process.stdout.write(`Content-Length: ${Buffer.byteLength(message, 'utf8')}\r\n\r\n${message}`);
}

/**
 * Send a JSON-RPC error response
 */
function sendError(id, code, message, data = null) {
    const response = {
        jsonrpc: '2.0',
        id,
        error: { code, message, data }
    };
    const msg = JSON.stringify(response);
    process.stdout.write(`Content-Length: ${Buffer.byteLength(msg, 'utf8')}\r\n\r\n${msg}`);
}

/**
 * Handle incoming JSON-RPC request
 */
function handleRequest(request) {
    const { id, method, params } = request;

    switch (method) {
        // ─── MCP Initialization ────────────────────────────────
        case 'initialize':
            sendResponse(id, {
                protocolVersion: '2024-11-05',
                capabilities: {
                    tools: {
                        load_xrl: {
                            description: 'Load a source file as XRL skeleton at specified depth. Returns skeleton text, token counts, and block list.',
                            inputSchema: {
                                type: 'object',
                                properties: {
                                    filePath: { type: 'string', description: 'Path to source file' },
                                    depth: { type: 'number', enum: [0, 1, 2, 3], default: 2, description: 'Skeletonization depth (0=full, 1=light, 2=medium, 3=deep)' }
                                },
                                required: ['filePath']
                            }
                        },
                        expand_xrl: {
                            description: 'Expand a specific block (function/class) to full detail. Returns expanded source code.',
                            inputSchema: {
                                type: 'object',
                                properties: {
                                    filePath: { type: 'string', description: 'Path to source file' },
                                    blockName: { type: 'string', description: 'Name of function/class to expand' },
                                    depth: { type: 'number', enum: [0, 1, 2, 3], default: 0, description: 'Expansion depth (0=full source)' }
                                },
                                required: ['filePath', 'blockName']
                            }
                        },
                        search_xrl: {
                            description: 'Search across XRL-skeletonized files in a directory. Returns matching files with context lines.',
                            inputSchema: {
                                type: 'object',
                                properties: {
                                    directory: { type: 'string', description: 'Directory to search' },
                                    query: { type: 'string', description: 'Search query' },
                                    depth: { type: 'number', enum: [0, 1, 2, 3], default: 2, description: 'Skeletonization depth for search' },
                                    limit: { type: 'number', default: 20, description: 'Max results' }
                                },
                                required: ['directory', 'query']
                            }
                        }
                    }
                }
            });
            break;

        case 'tools/list':
            sendResponse(id, {
                tools: [
                    {
                        name: 'load_xrl',
                        description: 'Load a source file as XRL skeleton at specified depth. Returns skeleton text, token counts, and block list.',
                        inputSchema: {
                            type: 'object',
                            properties: {
                                filePath: { type: 'string', description: 'Path to source file' },
                                depth: { type: 'number', enum: [0, 1, 2, 3], default: 2, description: 'Skeletonization depth (0=full, 1=light, 2=medium, 3=deep)' }
                            },
                            required: ['filePath']
                        }
                    },
                    {
                        name: 'expand_xrl',
                        description: 'Expand a specific block (function/class) to full detail. Returns expanded source code.',
                        inputSchema: {
                            type: 'object',
                            properties: {
                                filePath: { type: 'string', description: 'Path to source file' },
                                blockName: { type: 'string', description: 'Name of function/class to expand' },
                                depth: { type: 'number', enum: [0, 1, 2, 3], default: 0, description: 'Expansion depth (0=full source)' }
                            },
                            required: ['filePath', 'blockName']
                        }
                    },
                    {
                        name: 'search_xrl',
                        description: 'Search across XRL-skeletonized files in a directory. Returns matching files with context lines.',
                        inputSchema: {
                            type: 'object',
                            properties: {
                                directory: { type: 'string', description: 'Directory to search' },
                                query: { type: 'string', description: 'Search query' },
                                depth: { type: 'number', enum: [0, 1, 2, 3], default: 2, description: 'Skeletonization depth for search' },
                                limit: { type: 'number', default: 20, description: 'Max results' }
                            },
                            required: ['directory', 'query']
                        }
                    }
                ]
            });
            break;

        case 'tools/call':
            const toolName = params.name;
            const toolArgs = params.arguments || {};

            switch (toolName) {
                case 'load_xrl': {
                    const result = engine.loadFile(toolArgs.filePath, toolArgs.depth || CONFIG.defaultDepth);
                    if (result.error) {
                        sendError(id, -32000, result.error);
                    } else {
                        sendResponse(id, {
                            content: [{
                                type: 'text',
                                text: JSON.stringify(result, null, 2)
                            }]
                        });
                    }
                    break;
                }

                case 'expand_xrl': {
                    const result = engine.expandBlock(toolArgs.filePath, toolArgs.blockName, toolArgs.depth || 0);
                    if (result.error) {
                        sendError(id, -32000, result.error);
                    } else {
                        sendResponse(id, {
                            content: [{
                                type: 'text',
                                text: JSON.stringify(result, null, 2)
                            }]
                        });
                    }
                    break;
                }

                case 'search_xrl': {
                    const result = engine.searchDirectory(
                        toolArgs.directory,
                        toolArgs.query,
                        toolArgs.depth || CONFIG.defaultDepth,
                        toolArgs.limit || CONFIG.searchLimit
                    );
                    if (result.error) {
                        sendError(id, -32000, result.error);
                    } else {
                        sendResponse(id, {
                            content: [{
                                type: 'text',
                                text: JSON.stringify(result, null, 2)
                            }]
                        });
                    }
                    break;
                }

                default:
                    sendError(id, -32601, `Tool not found: ${toolName}`);
            }
            break;

        case 'notifications/initialized':
            // No response needed for notifications
            break;

        default:
            sendError(id, -32601, `Method not found: ${method}`);
    }
}

// ─── Main Loop ───────────────────────────────────────────────────

let buffer = '';

process.stdin.on('data', (chunk) => {
    buffer += chunk.toString('utf8');
    
    // Process complete messages
    while (true) {
        const headerMatch = buffer.match(/^Content-Length: (\d+)\r\n\r\n/);
        if (!headerMatch) break;

        const contentLength = parseInt(headerMatch[1], 10);
        const headerEnd = headerMatch[0].length;
        const totalLength = headerEnd + contentLength;

        if (buffer.length < totalLength) break;

        const content = buffer.slice(headerEnd, totalLength);
        buffer = buffer.slice(totalLength);

        try {
            const request = JSON.parse(content);
            handleRequest(request);
        } catch (err) {
            console.error(`[XRL-MCP] Parse error: ${err.message}`, file=process.stderr);
            sendError(null, -32700, `Parse error: ${err.message}`);
        }
    }
});

process.stdin.on('end', () => {
    process.exit(0);
});

// Log startup
console.error('[XRL-MCP] XRL MCP Server v1.0 started');
console.error(`[XRL-MCP] Default depth: ${CONFIG.defaultDepth}`);
console.error(`[XRL-MCP] Cache size: ${CONFIG.cacheSize}`);
console.error(`[XRL-MCP] XRL CLI: ${XRL_CLI}`);