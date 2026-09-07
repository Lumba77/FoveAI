/**
 * ═══════════════════════════════════════════════════════
 * FoveAI Custom LLM Provider — XLR Skeleton Usage Example
 * ═══════════════════════════════════════════════════════
 *
 * Demonstrates how the custom OpenAI-compatible provider works
 * with the XRL foveated memory ring compressor.
 *
 * Related:
 *   - .xrlf/prompts/llm-provider-custom.xrlf (prompt skeleton)
 *   - .xrlf/prompts/llm-provider-custom.schema.json (schema)
 *   - Tools/foveated-memory/core/xrl-compressor.js (compressor)
 *   - .env:365-366 (FoveAI_LLM_PROVIDER=custom)
 */

'use strict';

// ── 1. Load XRL Compressor ────────────────────────────────────────
// The compressor applies foveated ring compression to conversation
// history before sending it to the LLM endpoint.
const { compress, compressAsync } = require('../../Tools/foveated-memory/core/xrl-compressor.js');

// ── 2. Provider Configuration (from .env) ─────────────────────────
const PROVIDER_CONFIG = {
    provider: process.env.FoveAI_LLM_PROVIDER || 'custom',
    baseUrl: process.env.FoveAI_BASE_URL || 'https://ollama.com/v1',
    modelId: process.env.FoveAI_MODEL_ID || 'default-model',
    apiKey: process.env.FoveAI_API_KEY || '',
    cloudModel: process.env.FoveAI_CLOUD_MODEL || 'kimi-2.7-code',
    summarizerModel: process.env.FoveAI_SUMMARIZER_MODEL || 'reasoning-summarizer-800m-pre',
    lmStudioUrl: process.env.LM_STUDIO_URL || 'http://127.0.0.1:7272',
    llmSummarize: process.env.FoveAI_LLM_SUMMARIZE !== 'false',
};

// ── 3. Build OpenAI-Compatible Request ────────────────────────────
/**
 * Constructs a chat completion request in OpenAI format.
 * @param {string} systemPrompt - System role content
 * @param {string} userMessage - User role content
 * @param {Array} conversationHistory - Prior messages (will be XRL-compressed)
 * @param {number} compressionLevel - Ring level 0-5 (default: 3 = Deep)
 * @returns {object} OpenAI-compatible request body
 */
function buildRequest(systemPrompt, userMessage, conversationHistory = [], compressionLevel = 3) {
    // Compress conversation history using XRL foveated rings
    const compressedHistory = compress(conversationHistory, compressionLevel, 999);

    const messages = [
        { role: 'system', content: systemPrompt },
    ];

    // If we have compressed history, inject it as a system context block
    if (compressedHistory) {
        messages.push({
            role: 'system',
            content: `[XRL Compressed Context — Ring ${compressionLevel}]\n${compressedHistory}`,
        });
    }

    messages.push({ role: 'user', content: userMessage });

    return {
        model: PROVIDER_CONFIG.modelId,
        messages,
        stream: true,
        temperature: 0.7,
    };
}

// ── 4. Send Request to Custom Provider ────────────────────────────
/**
 * Sends a chat completion request to the custom OpenAI-compatible endpoint.
 * Falls back to cloud model if the primary endpoint fails.
 * @param {object} requestBody - Request body from buildRequest()
 * @returns {Promise<Response>} Fetch response
 */
async function sendRequest(requestBody) {
    const url = `${PROVIDER_CONFIG.baseUrl}/chat/completions`;
    const headers = {
        'Authorization': `Bearer ${PROVIDER_CONFIG.apiKey}`,
        'Content-Type': 'application/json',
    };

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers,
            body: JSON.stringify(requestBody),
        });

        if (!response.ok) {
            throw new Error(`Provider returned ${response.status}: ${response.statusText}`);
        }

        return response;
    } catch (error) {
        console.error(`[FoveAI Custom Provider] Primary endpoint failed: ${error.message}`);
        console.log(`[FoveAI Custom Provider] Falling back to cloud model: ${PROVIDER_CONFIG.cloudModel}`);

        // Fallback: switch to cloud model
        const fallbackBody = { ...requestBody, model: PROVIDER_CONFIG.cloudModel };
        return fetch(url, {
            method: 'POST',
            headers,
            body: JSON.stringify(fallbackBody),
        });
    }
}

// ── 5. Async Compression with LLM Summarizer ──────────────────────
/**
 * Uses the async compressor which leverages the local LLM summarizer
 * (reasoning-summarizer-800m-pre) for higher-quality ring 1-3 compression.
 * Falls back to extractive summarization if the summarizer is unreachable.
 * @param {Array} messages - Conversation messages
 * @param {number} level - Compression ring level (0-5)
 * @returns {Promise<string>} Compressed context string
 */
async function compressWithContext(messages, level = 3) {
    if (!PROVIDER_CONFIG.llmSummarize) {
        // LLM summarization disabled — use extractive only
        return compress(messages, level, 999);
    }
    return compressAsync(messages, level, 999);
}

// ── 6. Full Pipeline Example ──────────────────────────────────────
/**
 * Complete example: compress history → build request → send to provider.
 */
async function customProviderChat(systemPrompt, userMessage, conversationHistory) {
    // Step 1: Compress conversation history (Ring 3 = Deep ~88%)
    const compressedContext = await compressWithContext(conversationHistory, 3);
    console.log('[XRL] Compressed context:', compressedContext.slice(0, 100) + '...');

    // Step 2: Build OpenAI-compatible request
    const requestBody = buildRequest(systemPrompt, userMessage, conversationHistory, 3);

    // Step 3: Send to custom provider
    const response = await sendRequest(requestBody);

    // Step 4: Parse streaming response
    if (response.body) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullResponse = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value);
            fullResponse += chunk;
            process.stdout.write(chunk);
        }

        return fullResponse;
    }

    return await response.text();
}

// ── 7. XRL Ring Level Reference ────────────────────────────────────
const XRL_RINGS = {
    0: { name: 'Fovea',       compression: '0%',  method: 'Tone-classified refinement' },
    1: { name: 'Parafovea',   compression: '~50%', method: 'Extractive: top sentences + headline' },
    2: { name: 'Near-Periphery', compression: '~75%', method: 'Key sentences + topic + headline' },
    3: { name: 'Mid-Periphery', compression: '~88%', method: 'Headline + topic + first meaningful sentence' },
    4: { name: 'Far-Periphery', compression: '~95%', method: 'Headline + topic label + xrl:// hash' },
    5: { name: 'Outer-Periphery', compression: '~98%', method: 'Headline + xrl:// hash only' },
};

// ── Exports ────────────────────────────────────────────────────────
module.exports = {
    PROVIDER_CONFIG,
    buildRequest,
    sendRequest,
    compressWithContext,
    customProviderChat,
    XRL_RINGS,
};