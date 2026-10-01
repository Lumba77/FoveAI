/**
 * interceptor.js — XRL Token Stripping Pipeline
 *
 * Reuses the Foveated Memory XRL compressor logic.
 * Strips AI request bodies before they leave the machine.
 */

'use strict';

const path   = require('path');
const crypto = require('crypto');
const fetch  = require('node-fetch');

// ── XRL Compression (inline, no dependency on foveated-memory install) ────────

const THINKING_RE = /<thinking>[\s\S]*?<\/thinking>/gi;

function xrlHash(text) {
    return 'xrl://' + crypto.createHash('md5').update(text).digest('hex').slice(0, 6);
}

function estimateTokens(text) {
    return Math.ceil((text || '').length / 4);
}

function extractContent(msg, isGemini) {
    if (isGemini) {
        if (msg.parts && msg.parts.length > 0 && msg.parts[0].text) {
            return msg.parts[0].text;
        }
        return '';
    }
    return typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content);
}

function repackMessage(msg, newContent, isGemini) {
    if (isGemini) {
        const parts = [...(msg.parts || [])];
        if (parts.length > 0 && parts[0].text !== undefined) {
            parts[0] = { ...parts[0], text: newContent };
        } else if (parts.length === 0) {
            parts.push({ text: newContent });
        }
        return { ...msg, parts };
    }
    return { ...msg, content: newContent };
}

/**
 * Compress a single message at the given level.
 * Level 0 = raw, 1 = light, 2 = medium, 3 = deep, 4 = ultra, 5 = atomic
 */
function compressMessage(msg, level, isGemini = false) {
    if (!msg || level === 0) return msg;
    
    let content = extractContent(msg, isGemini);
    if (!content) return msg;

    // Always strip <thinking> blocks
    content = content.replace(THINKING_RE, '').trim();

    if (level === 1) {
        // Light: keep first + last 300 chars, ellipsis in middle
        if (content.length > 800) {
            content = content.slice(0, 350) + ' … [LCP:L1] … ' + content.slice(-250);
        }
    } else if (level === 2) {
        // Medium: keep first 200 chars only + hash
        if (content.length > 400) {
            const hash = xrlHash(content);
            content = content.slice(0, 200) + ` … [${hash}]`;
        }
    } else if (level === 3) {
        // Deep: first 80 chars + hash
        if (content.length > 120) {
            const hash = xrlHash(content);
            const words = content.split(/\s+/).slice(0, 12).join(' ');
            content = `${words} [${hash}]`;
        }
    } else if (level >= 4) {
        // Ultra/Atomic: just the hash
        content = xrlHash(content);
    }

    return repackMessage(msg, content, isGemini);
}

/**
 * Collapse repeated tool schemas into a single reference.
 * If the same function name appears >1 time, keep first and replace rest with a stub.
 */
function collapseToolSchemas(tools) {
    if (!tools || !Array.isArray(tools)) return tools;
    const seen = new Set();
    return tools.map(tool => {
        const name = tool?.function?.name || tool?.name || '';
        if (seen.has(name)) {
            return { type: 'function', function: { name, description: '[See previous definition]', parameters: {} } };
        }
        seen.add(name);
        return tool;
    });
}

// ── Draft Model Compression (optional) ───────────────────────────────────────

async function draftModelCompress(messages, modelUrl, modelName) {
    try {
        const history = messages.map(m => `${m.role}: ${m.content}`).join('\n');
        const res = await fetch(`${modelUrl}/api/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: modelName,
                prompt: `Compress this conversation history to its essential facts in ≤30% of the original tokens. Keep all decisions, code references, and action items. Output only the compressed text:\n\n${history}`,
                stream: false,
            }),
            signal: AbortSignal.timeout(5000),
        });
        if (res.ok) {
            const data = await res.json();
            return data.response || null;
        }
    } catch (_) {}
    return null;
}

// ── Main Strip Entry Point ────────────────────────────────────────────────────

/**
 * Strip and compress a request body's messages array.
 * @param {object} body - Parsed JSON request body
 * @param {object} cfg  - Compression config from config.json
 * @returns {object} Modified body
 */
async function stripMessages(body, cfg) {
    // Handle both OpenAI format (messages) and Gemini format (contents)
    const isGemini = Array.isArray(body.contents);
    const messages = isGemini ? [...body.contents] : [...(body.messages || [])];
    const window   = cfg.history_window || 4;
    const level    = cfg.default_level  || 2;
    const sysLevel = cfg.system_prompt_level || 3;

    const result = [];
    const total  = messages.length;

    for (let i = 0; i < total; i++) {
        const msg = messages[i];
        const isRecent = i >= total - window;
        const isSystem = msg.role === 'system';

        if (isSystem) {
            // System prompts get their own (usually higher) compression level
            result.push(compressMessage(msg, isRecent ? Math.min(sysLevel, level) : sysLevel, isGemini));
        } else if (isRecent) {
            // Recent messages: strip only thinking blocks
            let content = extractContent(msg, isGemini);
            if (typeof content === 'string') content = content.replace(THINKING_RE, '').trim();
            result.push(repackMessage(msg, content, isGemini));
        } else {
            // Old history: full compression
            result.push(compressMessage(msg, level, isGemini));
        }
    }

    // Collapse tool schemas if enabled
    const tools = cfg.collapse_tool_schemas && body.tools
        ? collapseToolSchemas(body.tools)
        : body.tools;

    // Optional: draft model pass on old context (level 3+)
    if (cfg.draft_model_enabled && level >= 3 && total > window + 2) {
        const oldMessages = result.slice(0, total - window);
        const compressed = await draftModelCompress(oldMessages, cfg.draft_model_url, cfg.draft_model_name);
        if (compressed) {
            // Replace old messages with a single compressed summary
            const summary = {
                role: 'system',
                content: `[LumaxConProxy Context Summary]\n${compressed}`,
            };
            return isGemini 
                ? { ...body, contents: [summary, ...result.slice(total - window)], tools }
                : { ...body, messages: [summary, ...result.slice(total - window)], tools };
        }
    }

    return isGemini ? { ...body, contents: result, tools } : { ...body, messages: result, tools };
}

module.exports = { stripMessages, estimateTokens, compressMessage };
