/**
 * ═══════════════════════════════════════════════════════
 * SMART ROUTER — Middleman-Based Message Routing
 * ═══════════════════════════════════════════════════════
 *
 * Routes messages through a middleman model for intelligent
 * compression and context management before sending to upstream.
 *
 * This module was missing, causing crashes when XRLF_REPO_ENABLED=true.
 */

'use strict';

const fetch = require('node-fetch');

/**
 * Route messages through the smart router for compression.
 *
 * @param {Array} messages - The messages array to route
 * @param {string} middleman - The middleman model name
 * @param {string} upstream - The upstream URL
 * @returns {Promise<Array>} - The routed/compressed messages
 */
async function smartRouteMessages(messages, middleman = null, upstream = null) {
    // Skip routing if no messages or too few messages
    if (!messages || messages.length < 3) {
        return messages;
    }

    const primaryModel = middleman 
        || process.env.FOVEAI_OMNI_ROUTER_MODEL 
        || 'foveai-omni-router-v2';
    const failoverModel = process.env.FOVEAI_NO2_ROUTER_MODEL 
        || 'no2-foveai-omni-router';
    const targetUpstream = upstream 
        || process.env.XRLF_RUNTIME_URL 
        || 'http://127.0.0.1:8400';

    const baseUrl = targetUpstream.replace(/\/v1\/?$/, '');
    const routingPrompt = buildRoutingPrompt(messages);

    // ── Attempt 1: Primary Omni-Router ──
    try {
        console.log(`[SmartRouter] Attempting Primary Omni-Router: ${primaryModel}`);
        const result = await callRouterModel(baseUrl, primaryModel, routingPrompt, messages);
        if (result) return result;
    } catch (primaryErr) {
        console.warn(`[SmartRouter] ⚠️ Primary router failed (${primaryErr.message}). Engaging No. 2 Omni-Router failover...`);
    }

    // ── Attempt 2: No. 2 Failover Omni-Router ──
    try {
        console.log(`[SmartRouter] Attempting Failover Omni-Router: ${failoverModel}`);
        const result = await callRouterModel(baseUrl, failoverModel, routingPrompt, messages);
        if (result) {
            console.log('[SmartRouter] ✅ No. 2 Omni-Router recovered message routing.');
            return result;
        }
    } catch (failoverErr) {
        console.warn(`[SmartRouter] ⚠️ Both routers unavailable (${failoverErr.message}). Falling back to uncompressed context.`);
    }

    return messages; // Fallback to original messages
}

/**
 * Call a specific router model endpoint and apply decision.
 */
async function callRouterModel(baseUrl, modelName, routingPrompt, originalMessages) {
    const response = await fetch(`${baseUrl}/v1/chat/completions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            model: modelName,
            messages: [
                { role: 'system', content: 'You are a message routing assistant. Analyze the conversation and output a JSON array of message indices to keep or compress.' },
                { role: 'user', content: routingPrompt }
            ],
            max_tokens: 500,
            temperature: 0.1,
            stream: false
        }),
        signal: AbortSignal.timeout(15000)
    });

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();
    const routingDecision = data.choices?.[0]?.message?.content;
    const routed = applyRoutingDecision(originalMessages, routingDecision);
    console.log(`[SmartRouter] Successfully routed ${originalMessages.length} → ${routed.length} messages`);
    return routed;
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
        // Try to parse JSON decision
        const parsed = JSON.parse(decision);

        if (parsed.keep && Array.isArray(parsed.keep)) {
            // Filter to only kept messages, preserving order
            const keepSet = new Set(parsed.keep);
            return messages.filter((_, i) => keepSet.has(i));
        }

        return messages;
    } catch {
        // If parsing fails, return original messages
        return messages;
    }
}

/**
 * Get router statistics.
 */
function getRouterStats() {
    return {
        enabled: true,
        module: 'smart-router',
        version: '1.0.0'
    };
}

module.exports = {
    smartRouteMessages,
    getRouterStats
};