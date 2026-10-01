/**
 * ═══════════════════════════════════════════════════════
 * SMART ROUTER — Middleman-Based Message Routing
 * ═══════════════════════════════════════════════════════
 *
 * Routes large messages through a fast local middleman model
 * for intelligent compression before sending to upstream.
 *
 * Fixed: Added AbortSignal.timeout on fetch to prevent infinite hangs
 * when LM Studio is unresponsive. Ported from XRLF 1.0 dev.
 */

'use strict';

const fetch = require('node-fetch');

const SMART_ROUTER_TIMEOUT_MS = parseInt(process.env.LUMAX_SMART_ROUTER_TIMEOUT_MS || '25000', 10);

/**
 * Route messages through the smart router for compression.
 *
 * @param {Array}  messages  - The messages array to route
 * @param {string} middleman - The middleman model name
 * @param {string} upstream  - The upstream URL (LM Studio base)
 * @returns {Promise<Array>} - The routed/compressed messages
 */
async function smartRouteMessages(
    messages,
    middleman = 'qwen2.5-0.5b-instruct',
    upstream  = 'http://127.0.0.1:7272'
) {
    // Resolve model from env if not explicitly provided
    if (!middleman) {
        middleman = process.env.LUMAX_SMART_ROUTER_MODEL
            || process.env.LUMAX_MIDDLEMAN_MODEL
            || process.env.LOCAL_LLM_MODEL
            || process.env.LUMAX_MODEL_LOCAL_ID
            || 'qwen2.5-0.5b-instruct';
    }

    // Skip routing for very short conversations — not worth the round-trip
    if (!messages || messages.length < 3) {
        return messages;
    }

    try {
        const baseUrl = upstream.replace(/\/v1\/?$/, '');

        // Build routing prompt
        const routingPrompt = buildRoutingPrompt(messages);

        // ── Call the middleman model ──────────────────────────────────────
        // IMPORTANT: always pass a signal so we never hang indefinitely if
        // LM Studio is loaded but stalled (TCP half-open on Windows).
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), SMART_ROUTER_TIMEOUT_MS);

        let response;
        try {
            response = await fetch(`${baseUrl}/v1/chat/completions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model: middleman,
                    messages: [
                        {
                            role: 'system',
                            content: 'You are a message routing assistant. Analyze the conversation and output a JSON object with which messages to keep or compress.'
                        },
                        { role: 'user', content: routingPrompt }
                    ],
                    max_tokens: 500,
                    temperature: 0.1,
                    stream: false
                }),
                signal: controller.signal
            });
        } finally {
            clearTimeout(timer);
        }

        if (!response.ok) {
            console.warn(`[SmartRouter] Middleman call failed: ${response.status} — bypassing`);
            return messages;
        }

        const data = await response.json();
        const routingDecision = data.choices?.[0]?.message?.content;

        const routedMessages = applyRoutingDecision(messages, routingDecision);
        console.log(`[SmartRouter] Routed ${messages.length} → ${routedMessages.length} messages`);
        return routedMessages;

    } catch (error) {
        if (error.name === 'AbortError') {
            console.warn(`[SmartRouter] Timed out after ${SMART_ROUTER_TIMEOUT_MS}ms — bypassing`);
        } else {
            console.warn('[SmartRouter] Routing failed:', error.message, '— bypassing');
        }
        return messages; // Always fall back safely
    }
}

/**
 * Build a prompt for the middleman to decide which messages to keep.
 */
function buildRoutingPrompt(messages) {
    const summary = messages.map((m, i) => {
        const preview = typeof m.content === 'string'
            ? m.content.slice(0, 100).replace(/\n/g, ' ')
            : JSON.stringify(m.content).slice(0, 100);
        return `[${i}] ${m.role}: ${preview}...`;
    }).join('\n');

    return `Analyze this conversation and decide which messages are essential:\n\n${summary}\n\nRespond with JSON: {"keep": [indices], "compress": [indices]}`;
}

/**
 * Apply the routing decision to filter/compress messages.
 */
function applyRoutingDecision(messages, decision) {
    try {
        const parsed = JSON.parse(decision);
        if (parsed.keep && Array.isArray(parsed.keep) && parsed.keep.length > 0) {
            const keepSet = new Set(parsed.keep);
            return messages.filter((_, i) => keepSet.has(i));
        }
        return messages;
    } catch {
        return messages; // Parse failure → return original safely
    }
}

/**
 * Get router statistics.
 */
function getRouterStats() {
    return {
        enabled: true,
        module: 'smart-router',
        version: '1.1.0',
        timeoutMs: SMART_ROUTER_TIMEOUT_MS
    };
}

module.exports = {
    smartRouteMessages,
    getRouterStats
};
