#!/usr/bin/env node
/**
 * Foveated Memory — MCP Server (v2)
 *
 * Exposes FoveAI to any MCP-capable IDE (Devin, Cline, Roo, Cursor, Windsurf,
 * Claude Desktop, LM Studio). Proxy-first: when the foveated-memory proxy is
 * live on :8400, tools route through its HTTP API so IDE calls share the same
 * memory store, foveation rings, settings, and model router as everything else.
 * When the proxy is down, memory tools fall back to the on-disk store so the
 * server never hard-fails.
 *
 * Register in any IDE's mcp.json:
 *   "foveated-memory": { "command": "node", "args": ["<abs-path>/mcp-server.js"] }
 *
 * Optional env vars:
 *   FM_PROXY_URL   — proxy base URL (default: http://127.0.0.1:8400)
 *   FM_WORKSPACE   — workspace/namespace (default: "default")
 *   FM_DATA_DIR    — path to memory_data dir (default: ./memory_data next to this file)
 */

'use strict';

const path = require('path');
const { MemoryStore } = require('./memory/store');

// ── Config ────────────────────────────────────────────────────────────────────
const PROXY_URL  = (process.env.FM_PROXY_URL || 'http://127.0.0.1:8400').replace(/\/$/, '');
const WORKSPACE  = process.env.FM_WORKSPACE || 'default';
const DATA_DIR   = process.env.FM_DATA_DIR  || path.join(__dirname, 'memory_data');
const SERVER_NAME    = 'foveated-memory';
const SERVER_VERSION = '2.0.0';

// ── Store (offline fallback) ──────────────────────────────────────────────────
const store = new MemoryStore(DATA_DIR, WORKSPACE);

// ── Proxy reachability (cached 5s) ────────────────────────────────────────────
let _proxyUp = null, _proxyCheckedAt = 0;
async function proxyUp() {
  if (Date.now() - _proxyCheckedAt < 5000 && _proxyUp !== null) return _proxyUp;
  try {
    const r = await fetch(`${PROXY_URL}/api/status`, { signal: AbortSignal.timeout(1200) });
    _proxyUp = r.ok;
  } catch { _proxyUp = false; }
  _proxyCheckedAt = Date.now();
  return _proxyUp;
}

async function api(method, route, body) {
  const r = await fetch(`${PROXY_URL}${route}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${WORKSPACE}`,
    },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(30000),
  });
  if (!r.ok) throw new Error(`proxy ${method} ${route} → ${r.status}`);
  return r.json();
}

// ── MCP Tool Definitions ──────────────────────────────────────────────────────
const TOOLS = [
  {
    name: 'memory_save',
    description: 'Save a message turn to persistent foveated memory. Call this after each assistant response to build long-term recall.',
    inputSchema: {
      type: 'object',
      properties: {
        role:    { type: 'string', enum: ['user', 'assistant', 'system'], description: 'Who sent this message' },
        content: { type: 'string', description: 'The message content to save' },
        session: { type: 'string', description: 'Optional session ID to group related turns (default: today)' }
      },
      required: ['role', 'content']
    }
  },
  {
    name: 'memory_recall',
    description: 'Semantically search persistent memory using TF-IDF. Use this when the user references past conversations, asks "do you remember", or when context seems missing.',
    inputSchema: {
      type: 'object',
      properties: {
        query:  { type: 'string', description: 'Keywords or phrase to search memory for' },
        top_n:  { type: 'number', description: 'Max results to return (default: 5)' }
      },
      required: ['query']
    }
  },
  {
    name: 'memory_recent',
    description: 'Retrieve the N most recent stored messages across all sessions. Useful for resuming context at session start.',
    inputSchema: {
      type: 'object',
      properties: {
        n: { type: 'number', description: 'Number of recent messages to fetch (default: 6, max recommended: 10)' }
      }
    }
  },
  {
    name: 'memory_summary',
    description: 'Get the live foveated ring block: recent turns verbatim + ring-compressed older history, exactly as the proxy injects it into chats. Use ONLY at session start, not on every turn.',
    inputSchema: {
      type: 'object',
      properties: {
        fovea_count: { type: 'number', description: 'How many recent messages to keep verbatim in offline fallback (default: 6)' }
      }
    }
  },
  {
    name: 'memory_stats',
    description: 'Return the total number of stored messages and workspace info.',
    inputSchema: { type: 'object', properties: {} }
  },
  {
    name: 'foveai_status',
    description: 'FoveAI system status: proxy health, upstream runtime, stored memory counts, active session. Use to check whether the local stack is online before calling chat tools.',
    inputSchema: { type: 'object', properties: {} }
  },
  {
    name: 'foveai_chat',
    description: 'Send a chat message through the FoveAI proxy router. Model "auto" (default) routes to the local XRLF model; "nvidia/<id>" routes to an NVIDIA cloud model. Turns are stored into foveated memory automatically.',
    inputSchema: {
      type: 'object',
      properties: {
        message:    { type: 'string', description: 'User message text' },
        model:      { type: 'string', description: 'Model id (default "auto"; prefix "nvidia/" for cloud models)' },
        max_tokens: { type: 'number', description: 'Response cap (default 512)' }
      },
      required: ['message']
    }
  },
  {
    name: 'foveai_models',
    description: 'List model ids currently exposed by the FoveAI proxy (local XRLF + nvidia/* cloud helpers).',
    inputSchema: { type: 'object', properties: {} }
  },
  {
    name: 'foveai_set_aggression',
    description: 'Set the shared compression/aggression level (XRLF_PROXY_AGGRESSION, 0-5) in the live proxy env — the same lever the Commando terminal and Jenna VS Code use.',
    inputSchema: {
      type: 'object',
      properties: {
        level: { type: 'number', description: 'Aggression level 0 (disabled) to 5 (max compression)' }
      },
      required: ['level']
    }
  },
  {
    name: 'foveai_sessions',
    description: 'List stored chat sessions (ids, titles, message counts) from foveated memory.',
    inputSchema: { type: 'object', properties: {} }
  }
];

// ── Tool Handlers ─────────────────────────────────────────────────────────────
async function handleTool(name, args) {
  const live = await proxyUp();
  switch (name) {

    case 'memory_save': {
      if (live) {
        return await api('POST', '/v1/memory/store', {
          role: args.role, content: args.content, session: args.session,
        });
      }
      const sessionId = args.session || new Date().toISOString().slice(0, 10);
      await store.store(sessionId, args.role, args.content, Date.now());
      const total = await store.count();
      return { saved: true, workspace: WORKSPACE, total_messages: total, via: 'disk (proxy offline)' };
    }

    case 'memory_recall': {
      const topN = args.top_n || 5;
      if (live) {
        const d = await api('POST', '/v1/memory/search', { query: args.query, limit: topN });
        return { results: (d.results || []).map(r => ({
          score: Math.round((r.score ?? 0) * 1000) / 1000,
          role: r.role || r.message?.role,
          content: _contentText(r.content ?? r.message?.content),
        })), mode: d.mode || 'tfidf', via: 'proxy' };
      }
      const results = await store.search(args.query, topN);
      if (!results.length) return { results: [], message: 'No matching memories found.' };
      return {
        results: results.map(r => ({
          score:   Math.round(r.score * 1000) / 1000,
          role:    r.message.role,
          content: _contentText(r.message.content),
          age:     _relativeAge(r.message.timestamp)
        })),
        via: 'disk (proxy offline)'
      };
    }

    case 'memory_recent': {
      const n = Math.min(args.n || 6, 10); // hard cap at 10 to protect context window
      const msgs = await store.getRecent(n);
      return {
        count: msgs.length,
        messages: msgs.map(m => ({
          role:    m.role,
          content: m.content,
          age:     _relativeAge(m.timestamp)
        }))
      };
    }

    case 'memory_summary': {
      if (live) {
        const d = await api('GET', '/memory/rings');
        return {
          workspace: WORKSPACE,
          stored_messages: d.stored_messages,
          ring_tokens_est: d.ring_tokens_est,
          summary: d.ring_block,
          via: 'proxy'
        };
      }
      const foveaCount = Math.min(args.fovea_count || 4, 6);
      const all = await store.getRecent(20);
      if (!all.length) return { summary: '[No memory stored yet]' };
      const fovea = all.slice(0, foveaCount);
      const older = all.slice(foveaCount);
      const rings = older.slice(0, 10).map((m, i) => {
        const budget  = Math.max(20, 100 - i * 10);
        const content = String(m.content || '');
        const excerpt = content.length > budget ? content.slice(0, budget) + '…' : content;
        return `[${_relativeAge(m.timestamp)} | ${m.role}] ${excerpt}`;
      });
      const verbatim = fovea.map(m => `[${m.role}]: ${m.content}`).join('\n');
      const compressed = rings.length ? '\n\n--- Compressed History ---\n' + rings.join('\n') : '';
      return { workspace: WORKSPACE, summary: verbatim + compressed, via: 'disk (proxy offline)' };
    }

    case 'memory_stats': {
      if (live) return { ...(await api('GET', '/memory/stats')), via: 'proxy' };
      const total = await store.count();
      return { workspace: WORKSPACE, data_dir: DATA_DIR, total_messages: total, via: 'disk (proxy offline)' };
    }

    case 'foveai_status': {
      if (!live) return { online: false, proxy: PROXY_URL, note: 'proxy unreachable — memory tools are in disk fallback' };
      const [health, stats] = await Promise.all([
        api('GET', '/health').catch(() => null),
        api('GET', '/memory/stats').catch(() => null),
      ]);
      return { online: true, proxy: PROXY_URL, health, memory: stats };
    }

    case 'foveai_chat': {
      if (!live) throw new Error('FoveAI proxy offline — chat requires the proxy on ' + PROXY_URL);
      const d = await api('POST', '/v1/chat/completions', {
        model: args.model || 'auto',
        messages: [{ role: 'user', content: args.message }],
        max_tokens: args.max_tokens || 512,
        stream: false,
      });
      const choice = d.choices && d.choices[0];
      return {
        model: d.model || args.model || 'auto',
        content: choice?.message?.content ?? '',
        usage: d.usage,
      };
    }

    case 'foveai_models': {
      if (!live) throw new Error('FoveAI proxy offline — model list requires the proxy on ' + PROXY_URL);
      const d = await api('GET', '/v1/models');
      return { models: (d.data || []).map(m => m.id) };
    }

    case 'foveai_set_aggression': {
      if (!live) throw new Error('FoveAI proxy offline — settings require the proxy on ' + PROXY_URL);
      const level = Math.max(0, Math.min(5, Number(args.level)));
      await api('POST', '/api/setting', { key: 'XRLF_PROXY_AGGRESSION', val: String(level) });
      return { set: 'XRLF_PROXY_AGGRESSION', level };
    }

    case 'foveai_sessions': {
      if (!live) throw new Error('FoveAI proxy offline — sessions require the proxy on ' + PROXY_URL);
      return await api('GET', '/api/sessions');
    }

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function _contentText(raw) {
  if (Array.isArray(raw)) {
    return raw.filter(p => p && typeof p.text === 'string').map(p => p.text).join('\n');
  }
  return String(raw || '');
}

function _relativeAge(ts) {
  if (!ts) return 'unknown';
  const t = typeof ts === 'number' ? ts : new Date(ts).getTime();
  const diffMs  = Date.now() - t;
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1)   return 'just now';
  if (diffMin < 60)  return `${diffMin}m ago`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24)    return `${diffH}h ago`;
  return `${Math.floor(diffH / 24)}d ago`;
}

// ── JSON-RPC / MCP stdio transport ────────────────────────────────────────────
let buffer = '';

process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  buffer += chunk;
  const lines = buffer.split('\n');
  buffer = lines.pop(); // keep incomplete last line
  lines.forEach(line => {
    line = line.trim();
    if (line) handleMessage(line);
  });
});

async function handleMessage(raw) {
  let msg;
  try { msg = JSON.parse(raw); }
  catch { return; }

  const { id, method, params } = msg;

  // Notifications (no id) — ignore
  if (id === undefined && !method) return;

  try {
    const result = await dispatch(method, params || {});
    if (id !== undefined) send({ jsonrpc: '2.0', id, result });
  } catch (err) {
    if (id !== undefined) {
      send({ jsonrpc: '2.0', id, error: { code: -32603, message: err.message } });
    }
  }
}

async function dispatch(method, params) {
  switch (method) {

    case 'initialize':
      return {
        protocolVersion: '2024-11-05',
        capabilities: { tools: {} },
        serverInfo: { name: SERVER_NAME, version: SERVER_VERSION }
      };

    case 'notifications/initialized':
    case 'initialized':
      return {};

    case 'tools/list':
      return { tools: TOOLS };

    case 'tools/call': {
      const { name, arguments: args } = params;
      const content = await handleTool(name, args || {});
      return { content: [{ type: 'text', text: JSON.stringify(content, null, 2) }] };
    }

    case 'ping':
      return {};

    default:
      throw Object.assign(new Error(`Method not found: ${method}`), { code: -32601 });
  }
}

function send(obj) {
  process.stdout.write(JSON.stringify(obj) + '\n');
}

// ── Boot ──────────────────────────────────────────────────────────────────────
process.stderr.write(`[foveated-memory MCP] v${SERVER_VERSION} started | workspace="${WORKSPACE}" | proxy="${PROXY_URL}" | data="${DATA_DIR}"\n`);
