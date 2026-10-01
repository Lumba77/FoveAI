/**
 * ═══════════════════════════════════════════════════════
 * XRL RECALL INTERCEPTOR
 * ═══════════════════════════════════════════════════════
 *
 * Monitors the LLM's streaming response for <recall: "..."> tokens.
 * When detected, it:
 *   1. Stops collecting the current (incomplete) response
 *   2. Searches the memory store for the query
 *   3. Injects a [MEMORY RECALLED] system message
 *   4. Re-invokes the LLM with a continuation prompt
 *   5. Returns the final (clean) response to the original client
 *
 * This module is stream-aware — it operates on SSE chunks.
 */

'use strict';

const RECALL_REGEX = /<recall:\s*"([^"]+)">/i;

/**
 * Scan a text chunk for the <recall: "..."> token.
 * @param {string} text
 * @returns {string|null} The query string, or null if not found
 */
function detectRecall(text) {
    const m = text.match(RECALL_REGEX);
    return m ? m[1].trim() : null;
}

/**
 * Collect and buffer a full SSE streaming response.
 * Returns { fullText, rawChunks, recallQuery }
 *
 * Stops early if a recall token is detected mid-stream.
 *
 * @param {import('node-fetch').Response} upstreamResponse
 */
async function collectStream(upstreamResponse) {
    let fullText = '';
    const rawChunks = [];
    let buffer = '';

    return new Promise((resolve, reject) => {
        const body = upstreamResponse.body;
        if (!body) return resolve({ fullText: '', rawChunks: [], recallQuery: null });

        // Safety timeout: if stream hangs for >120s, resolve with what we have
        const hangTimer = setTimeout(() => {
            console.warn('[collectStream] ⚠️ Stream timeout (120s) — resolving with partial content');
            body.destroy();
            resolve({ fullText, rawChunks, recallQuery: detectRecall(fullText) });
        }, 120000);

        body.on('data', (chunk) => {
            const chunkStr = chunk.toString();
            rawChunks.push(chunkStr);
            buffer += chunkStr;

            // Process complete SSE lines from buffer
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';  // keep incomplete last line in buffer

            for (const line of lines) {
                if (!line.startsWith('data:')) continue;
                const data = line.slice(5).trim();
                if (data === '[DONE]') continue;
                try {
                    const parsed = JSON.parse(data);
                    const delta = parsed?.choices?.[0]?.delta || {};
                    // Ollama Cloud uses `delta.reasoning`; OpenAI uses `delta.reasoning_content`
                    const text = delta.content || delta.reasoning_content || delta.reasoning || '';
                    fullText += text;
                } catch (_) { /* partial chunk, ignore */ }
            }

            // Check for recall token mid-stream
            const recallQuery = detectRecall(fullText);
            if (recallQuery) {
                clearTimeout(hangTimer);
                body.destroy(); // Stop the upstream stream
                resolve({ fullText, rawChunks, recallQuery });
            }
        });

        body.on('end', () => {
            clearTimeout(hangTimer);
            // Process any remaining buffered content
            if (buffer.startsWith('data:')) {
                const data = buffer.slice(5).trim();
                if (data && data !== '[DONE]') {
                    try {
                        const parsed = JSON.parse(data);
                        const delta = parsed?.choices?.[0]?.delta || {};
                        fullText += delta.content || delta.reasoning_content || delta.reasoning || '';
                    } catch (_) {}
                }
            }
            resolve({ fullText, rawChunks, recallQuery: detectRecall(fullText) });
        });
        body.on('error', reject);
    });
}

/**
 * Collect a non-streaming (JSON) response.
 * @param {import('node-fetch').Response} upstreamResponse
 */
async function collectJson(upstreamResponse) {
    const data = await upstreamResponse.json();
    const message = data?.choices?.[0]?.message || {};
    let fullText = message.content || '';
    // Ollama Cloud uses 'reasoning' instead of 'reasoning_content'.
    // If the model returned no content but has reasoning, surface it as content so the client sees a response.
    if (!fullText && message.reasoning_content) {
        fullText = message.reasoning_content;
    } else if (!fullText && message.reasoning) {
        fullText = message.reasoning;
    }
    if (data.choices?.[0]?.message) {
        data.choices[0].message.content = fullText;
    }
    const recallQuery = detectRecall(fullText);
    return { fullText, data, recallQuery };
}

/**
 * Build the [MEMORY RECALLED] injection block from search results.
 *
 * @param {string} query   - The recall query string
 * @param {Array}  results - Array of search result objects with message and score properties
 * @returns {string} The formatted memory injection block
 */
function buildMemoryInjection(query, results) {
    if (results.length === 0) {
        return `[MEMORY RECALLED for "${query}"]: No matching memories found.`;
    }

    const lines = results.map(r => {
        const ts = r.message.timestamp
            ? new Date(r.message.timestamp).toISOString().slice(0, 10)
            : '?';
        const role = (r.message.role || 'unknown').toUpperCase();
        const rawContent = r.message.content || '';
        const content = (Array.isArray(rawContent)
            ? rawContent.filter(p => p && typeof p.text === 'string').map(p => p.text).join('\n')
            : String(rawContent)
        ).trim();
        const score = (r.score * 100).toFixed(0);
        return `  [${ts}] ${role} (resonance ${score}%): ${content}`;
    });

    return `[MEMORY RECALLED for "${query}"]:\n${lines.join('\n')}`;
}

module.exports = { detectRecall, collectStream, collectJson, buildMemoryInjection };
