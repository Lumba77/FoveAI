/**
 * ═══════════════════════════════════════════════════════
 * CONTEXT CHUNKER — Low-VRAM Chunked Context Processing
 * ═══════════════════════════════════════════════════════
 *
 * Problem: 8GB VRAM / 16GB RAM — large contexts cause OOM crashes.
 * Solution: Split context into small chunks, process sequentially,
 *           carrying forward a condensed summary between chunks.
 *
 * Flow:
 *   [sys+rings] → [Chunk 1] → [Chunk 2] → ... → [Chunk N] → response
 *                    ↓            ↓                  ↓
 *                  summary₁    summary₂          final answer
 *
 * Each chunk is small enough to fit in VRAM. The carry-forward
 * summary preserves context across chunks without the memory cost.
 *
 * Env vars:
 *   LUMAX_CHUNK_SIZE         - max chars per chunk (default 3000)
 *   LUMAX_CHUNK_OVERLAP      - overlap chars between chunks (default 400)
 *   LUMAX_CARRY_TOKENS       - max tokens for carry-forward summary (default 150)
 *   LUMAX_CHUNK_ENABLED      - set to 'false' to disable chunking (default true)
 */

'use strict';

const fetch = require('node-fetch');

// ── Config ──────────────────────────────────────────────────────────────────
const LOW_CTX             = process.env.LUMAX_LOW_CONTEXT_MODE === 'true' || process.env.LUMAX_LOW_CONTEXT_MODE === '1';
const CHUNK_ENABLED       = process.env.LUMAX_CHUNK_ENABLED !== 'false' && process.env.LUMAX_CHUNK_ENABLED !== '0';
const CHUNK_SIZE_CHARS    = parseInt(process.env.LUMAX_CHUNK_SIZE    || (LOW_CTX ? '1500' : '3000'), 10);
const CHUNK_OVERLAP_CHARS = parseInt(process.env.LUMAX_CHUNK_OVERLAP || (LOW_CTX ? '200'  : '400'),  10);
const CARRY_TOKENS        = parseInt(process.env.LUMAX_CARRY_TOKENS  || (LOW_CTX ? '80'   : '150'),  10);

// ── Helpers ─────────────────────────────────────────────────────────────────

function msgChars(msg) {
    if (!msg || !msg.content) return 0;
    return typeof msg.content === 'string' ? msg.content.length : JSON.stringify(msg.content).length;
}

function totalChars(messages) {
    return messages.reduce((n, m) => n + msgChars(m), 0);
}

/**
 * Split messages into chunks that each fit within CHUNK_SIZE_CHARS.
 * System messages are extracted and handled separately (only sent with first chunk).
 * Overlap ensures continuity between chunks.
 */
function splitIntoChunks(messages) {
    const systemMsgs = messages.filter(m => m.role === 'system');
    const convoMsgs  = messages.filter(m => m.role !== 'system');
    
    if (convoMsgs.length === 0) return [{ system: systemMsgs, convo: [] }];
    
    const chunks = [];
    let current = [];
    let currentChars = 0;
    
    for (let i = 0; i < convoMsgs.length; i++) {
        const msg = convoMsgs[i];
        const chars = msgChars(msg);
        
        // If adding this message would exceed chunk size and we already have messages
        if (currentChars + chars > CHUNK_SIZE_CHARS && current.length > 0) {
            chunks.push({ system: [], convo: [...current] });
            
            // Start new chunk with overlap from previous chunk
            const overlapStart = Math.max(0, current.length - Math.ceil(CHUNK_OVERLAP_CHARS / (currentChars / current.length)));
            current = current.slice(overlapStart);
            currentChars = totalChars(current);
        }
        
        current.push(msg);
        currentChars += chars;
    }
    
    // Final chunk
    if (current.length > 0) {
        chunks.push({ system: [], convo: [...current] });
    }
    
    // First chunk gets the system messages
    if (chunks.length > 0 && systemMsgs.length > 0) {
        chunks[0].system = systemMsgs;
    }
    
    return chunks;
}

/**
 * Summarize a response into a compact carry-forward block.
 * Uses the same upstream model with a summarization prompt.
 */
async function summarizeForCarryForward(responseText, upstreamUrl, upstreamHeaders, model) {
    if (!responseText || responseText.trim().length < 50) return '';
    
    const summaryPrompt = {
        role: 'user',
        content: `Condense the following into a very brief carry-forward note (max ${CARRY_TOKENS} tokens). Keep only: key decisions, file changes, current task, and critical facts. Be extremely concise.\n\n${responseText}\n\nCARRY-FORWARD SUMMARY:`
    };
    
    try {
        const res = await fetch(`${upstreamUrl}/v1/chat/completions`, {
            method: 'POST',
            headers: { ...upstreamHeaders, 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: model || 'gpt-oss:20b',
                messages: [
                    { role: 'system', content: 'You are a context compressor. Output ONLY the condensed summary, no preamble.' },
                    summaryPrompt
                ],
                max_tokens: CARRY_TOKENS + 20,
                temperature: 0.1,
                stream: false
            }),
            signal: (() => { const c = new AbortController(); setTimeout(() => c.abort(), 15000); return c.signal; })()
        });
        
        if (!res.ok) return `[chunk summary: ${responseText.slice(0, 200)}...]`;
        const data = await res.json();
        const summary = data.choices?.[0]?.message?.content || '';
        return summary.trim();
    } catch (e) {
        // Fallback: use first 200 chars as summary
        return `[prev: ${responseText.slice(0, 200).replace(/\n/g, ' ')}...]`;
    }
}

/**
 * Process messages in chunks, carrying forward context between chunks.
 * 
 * @param {Array} messages - Full messages array
 * @param {string} upstreamUrl - Upstream LLM URL
 * @param {object} upstreamHeaders - Headers for upstream requests
 * @param {string} model - Model name
 * @param {object} opts - Options
 * @param {boolean} opts.stream - Whether to stream the final response
 * @param {Function} opts.onChunkComplete - Called after each chunk with { index, total, summary }
 * @returns {object} { finalResponse, chunks, carryForward }
 */
async function processChunked(messages, upstreamUrl, upstreamHeaders, model, opts = {}) {
    if (!CHUNK_ENABLED) {
        return { finalResponse: null, chunks: 0, carryForward: '', skipped: true };
    }
    
    const fullChars = totalChars(messages);
    if (fullChars <= CHUNK_SIZE_CHARS) {
        return { finalResponse: null, chunks: 0, carryForward: '', skipped: true, reason: 'under threshold' };
    }
    
    const chunks = splitIntoChunks(messages);
    if (chunks.length <= 1) {
        return { finalResponse: null, chunks: 1, carryForward: '', skipped: true, reason: 'single chunk' };
    }
    
    console.log(`[Chunker] 📦 Splitting ${fullChars} chars into ${chunks.length} chunks (max ${CHUNK_SIZE_CHARS}/chunk)`);
    
    let carryForward = '';
    const chunkResults = [];
    
    for (let i = 0; i < chunks.length; i++) {
        const chunk = chunks[i];
        const isLastChunk = (i === chunks.length - 1);
        
        // Build chunk messages
        let chunkMessages = [];
        
        // System messages only on first chunk
        if (i === 0 && chunk.system.length > 0) {
            chunkMessages.push(...chunk.system);
        }
        
        // Carry-forward from previous chunks
        if (carryForward && i > 0) {
            chunkMessages.push({
                role: 'system',
                content: `[CARRY-FORWARD FROM PREVIOUS CHUNKS]\n${carryForward}\n[/CARRY-FORWARD]`
            });
        }
        
        // Current chunk's conversation messages
        chunkMessages.push(...chunk.convo);
        
        const chunkChars = totalChars(chunkMessages);
        console.log(`[Chunker] ▶️ Chunk ${i + 1}/${chunks.length}: ${chunkMessages.length} msgs, ${chunkChars} chars${isLastChunk ? ' (FINAL)' : ''}`);
        
        if (isLastChunk) {
            // Last chunk: return the messages for normal processing
            return {
                finalResponse: null,
                chunks: chunks.length,
                carryForward,
                chunkedMessages: chunkMessages,
                skipped: false,
                isLastChunk: true
            };
        }
        
        // Intermediate chunk: process and summarize
        try {
            const res = await fetch(`${upstreamUrl}/v1/chat/completions`, {
                method: 'POST',
                headers: { ...upstreamHeaders, 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model: model || 'gpt-oss:20b',
                    messages: chunkMessages,
                    max_tokens: CARRY_TOKENS + 100,
                    temperature: 0.3,
                    stream: false
                }),
                signal: (() => { const c = new AbortController(); setTimeout(() => c.abort(), 30000); return c.signal; })()
            });
            
            if (res.ok) {
                const data = await res.json();
                const responseText = data.choices?.[0]?.message?.content || '';
                
                // Summarize for carry-forward
                const summary = await summarizeForCarryForward(responseText, upstreamUrl, upstreamHeaders, model);
                carryForward = carryForward 
                    ? `${carryForward}\n---\n${summary}`
                    : summary;
                
                chunkResults.push({ index: i, response: responseText, summary });
                
                if (opts.onChunkComplete) {
                    opts.onChunkComplete({ index: i, total: chunks.length, summary });
                }
            } else {
                const errText = await res.text();
                console.warn(`[Chunker] ⚠️ Chunk ${i + 1} failed (${res.status}): ${errText.slice(0, 200)}`);
                // Continue with partial carry-forward
                carryForward = carryForward 
                    ? `${carryForward}\n---\n[chunk ${i + 1} failed: ${res.status}]`
                    : `[chunk ${i + 1} failed: ${res.status}]`;
            }
        } catch (e) {
            console.warn(`[Chunker] ⚠️ Chunk ${i + 1} error: ${e.message}`);
            carryForward = carryForward 
                ? `${carryForward}\n---\n[chunk ${i + 1} error: ${e.message}]`
                : `[chunk ${i + 1} error: ${e.message}]`;
        }
    }
    
    return {
        finalResponse: null,
        chunks: chunks.length,
        carryForward,
        chunkResults,
        skipped: false
    };
}

/**
 * Quick check: would chunking help for this message set?
 */
function shouldChunk(messages) {
    if (!CHUNK_ENABLED) return false;
    return totalChars(messages) > CHUNK_SIZE_CHARS;
}

/**
 * Get chunker config for health endpoints.
 */
function getChunkerState() {
    return {
        enabled: CHUNK_ENABLED,
        chunkSize: CHUNK_SIZE_CHARS,
        overlap: CHUNK_OVERLAP_CHARS,
        carryTokens: CARRY_TOKENS,
    };
}

module.exports = {
    processChunked,
    shouldChunk,
    splitIntoChunks,
    totalChars,
    getChunkerState,
    CHUNK_SIZE_CHARS,
    CHUNK_ENABLED,
};
