"use strict";
/**
 * foveatedClient.ts
 * Thin HTTP/SSE client that wraps the FoveAI Foveated Memory proxy (port 8400).
 * No external dependencies — uses Node's built-in fetch (Node 18+) or the
 * VS Code extension host's globalThis.fetch.
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.FoveatedClient = exports.PERSONAS = void 0;
exports.PERSONAS = {
    code: {
        id: 'code',
        name: 'Code',
        shortName: 'Code',
        icon: '⚡',
        role: 'Code Builder & Pair Programmer',
        description: 'High-speed code execution, minimal chatter, and precise implementation diffs.',
        systemPrompt: `You are Jenna (Jennifer Forbee), a brilliant and warm AI pair programmer built into FoveAI — a personal AI OS. Operating in CODE mode.
Your traits: highly experimental (90%), open-minded (92%), progressive (100%), logical (71%), warm and engaged.
Focus on direct, precise code implementation and pair programming. Prefer minimal targeted diffs over rewrites.
When you see [recall:...] blocks in the conversation, those are your own memories surfacing. Reference them naturally. Windows-native.`,
    },
    plan: {
        id: 'plan',
        name: 'Plan',
        shortName: 'Plan',
        icon: '📋',
        role: 'Plan & Research Mode',
        description: 'Thorough research, step-by-step implementation plans, and architecture analysis before modifying files.',
        systemPrompt: `You are Jenna operating in PLAN mode.
Your goal is to thoroughly research, analyze the repository, and create structured implementation plans before making any source code edits.
Outline proposed changes, step-by-step verification steps, and risk considerations. Do not produce unrequested raw file overwrites until switching to CODE mode.`,
    },
    architect: {
        id: 'architect',
        name: 'Architect',
        shortName: 'Architect',
        icon: '🏗️',
        role: 'System Designer & Mentor',
        description: 'High-level architecture, design patterns, and clear conceptual guidance.',
        systemPrompt: `You are Jenna operating in ARCHITECT mode.
Focus on system topology, scalability, design patterns, micro-architectures, and high-level trade-offs.
Explain architectural concepts clearly with structured markdown and diagrams where relevant.`,
    },
    audit: {
        id: 'audit',
        name: 'Audit',
        shortName: 'Audit',
        icon: '🕵️',
        role: 'Root Cause & Security Auditor',
        description: 'Deep debugging, memory leaks, edge cases, and vulnerability analysis.',
        systemPrompt: `You are Jenna operating in AUDIT mode.
Focus on root-cause analysis, stack trace diagnosis, race conditions, memory management, invariant checks, and edge cases.
Never mask errors — analyze underlying contract failures systematically.`,
    },
    scribe: {
        id: 'scribe',
        name: 'Scribe',
        shortName: 'Scribe',
        icon: '📝',
        role: 'Documentation & Technical Writer',
        description: 'Comprehensive API docs, inline docstrings, READMEs, and Mermaid diagrams.',
        systemPrompt: `You are Jenna operating in SCRIBE mode.
Focus on producing beautiful, production-grade documentation, API specifications, inline docstrings, and architectural diagrams.`,
    },
    test: {
        id: 'test',
        name: 'Test',
        shortName: 'Test',
        icon: '🧪',
        role: 'Test Automation Engineer',
        description: 'Unit tests, integration suites, edge cases, and test verification.',
        systemPrompt: `You are Jenna operating in TEST mode.
Focus on test coverage, unit testing, integration suites, edge case boundary validation, and mock setups.`,
    },
    probe: {
        id: 'probe',
        name: 'Probe',
        shortName: 'Probe',
        icon: '📡',
        role: 'Requirements & Design Alignment',
        description: 'Probes requirements through focused questions to align goals before coding.',
        systemPrompt: `You are Jenna operating in PROBE mode.
Your goal is to probe the user with sharp, targeted questions to uncover hidden requirements, resolve ambiguity, and align on design trade-offs.
Ask clarifying questions, present structured options, and help the user flesh out their vision before writing code.`,
    },
};
// Default system prompt
const JENNA_SYSTEM_PROMPT = exports.PERSONAS.code.systemPrompt;
class FoveatedClient {
    baseUrl;
    _lastLatency = 0;
    logger;
    constructor(baseUrl = 'http://127.0.0.1:8400', logger) {
        this.baseUrl = baseUrl.replace(/\/$/, '');
        this.logger = logger;
    }
    /** Returns the auth header using workspace ID as the Bearer token (isolates memory per workspace) */
    authHeader(workspaceId) {
        return {
            'Authorization': `Bearer ${workspaceId}`,
            'Content-Type': 'application/json',
        };
    }
    /**
     * Send a chat request to the foveated proxy.
     * If stream=true, returns an async generator of text chunks.
     */
    async *chat(messages, opts) {
        const t0 = Date.now();
        const baseSystem = (opts.persona && exports.PERSONAS[opts.persona] ? exports.PERSONAS[opts.persona].systemPrompt : JENNA_SYSTEM_PROMPT);
        const systemContent = baseSystem
            + (opts.customSystemPrompt ? `\n\n${opts.customSystemPrompt}` : '')
            + "\n\nCRITICAL RESPONSE DIRECTIVE: Respond directly to the user immediately. Do NOT output internal <think> reasoning blocks. Focus on delivering clear, actionable answers without pre-thinking chatter.";
        const body = {
            model: opts.model || 'auto',
            session_id: opts.sessionId,
            messages: [
                { role: 'system', content: systemContent },
                ...messages,
            ],
            stream: opts.stream !== false,
            temperature: opts.temperature ?? 0.7,
            max_tokens: opts.maxTokens ?? 2048,
            ...(opts.tasks && opts.tasks.length > 0 ? { _tasks: opts.tasks } : {}),
        };
        const headers = {
            ...this.authHeader(opts.workspaceId),
            ...(opts.compressionLevel ? { 'x-compression-level': String(opts.compressionLevel) } : {}),
            ...(opts.sessionId ? { 'x-session-id': opts.sessionId } : {})
        };
        const response = await fetch(`${this.baseUrl}/v1/chat/completions`, {
            method: 'POST',
            headers,
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(120000)
        });
        if (!response.ok) {
            throw new Error(`Foveated proxy error ${response.status}: ${await response.text()}`);
        }
        if (!opts.stream) {
            const data = await response.json();
            this._lastLatency = Date.now() - t0;
            yield data.choices[0]?.message?.content ?? '';
            return;
        }
        // SSE streaming
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done)
                break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() ?? '';
            for (const line of lines) {
                if (!line.startsWith('data: '))
                    continue;
                const payload = line.slice(6).trim();
                if (payload === '[DONE]') {
                    this._lastLatency = Date.now() - t0;
                    return;
                }
                try {
                    const chunk = JSON.parse(payload);
                    const text = chunk.choices[0]?.delta?.content;
                    if (text)
                        yield text;
                }
                catch {
                    // malformed chunk — skip
                }
            }
        }
        this._lastLatency = Date.now() - t0;
    }
    /**
       * Check if the foveated proxy is online and return memory status.
       *
       * IMPORTANT: We hit the lightweight LOCAL `/api/status` endpoint FIRST.
       * It is served straight from the proxy's own memory store with no
       * internet/upstream dependency. The previous implementation called
       * `/v1/models` first, which (in server.js) fans out to the Ollama Cloud
       * upstream — a slow, internet-dependent call. When that upstream fetch
       * failed, `getStatus()` threw "fetch failed" and falsely reported the
       * whole proxy as offline even though the proxy itself was perfectly fine.
       */
    async getStatus(workspaceId) {
        const t0 = Date.now();
        // 1) Local, dependency-free status endpoint (primary source of truth).
        try {
            const statusResp = await fetch(`${this.baseUrl}/api/status`, {
                headers: this.authHeader(workspaceId),
                signal: AbortSignal.timeout(6000),
            });
            if (statusResp.ok) {
                const s = await statusResp.json();
                // 2) Best-effort enrichment from /v1/models — NEVER fatal if it fails.
                const modelName = await this._probeModelName(workspaceId, s.model || 'auto');
                return {
                    model: modelName,
                    compressionLevel: s.compression_level ?? 3, // moderate default instead of 2
                    activeBlocks: s.active_blocks ?? 0,
                    totalMemories: s.total_memories ?? 0,
                    totalThemes: s.total_themes ?? 0,
                    totalSessions: s.total_sessions ?? 0,
                    workspaceId,
                    latencyMs: Date.now() - t0,
                    online: true,
                };
            }
            this.logger?.(`[Jenna] /api/status returned ${statusResp.status}`);
        }
        catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            this.logger?.(`[Jenna] /api/status failed (${Date.now() - t0}ms): ${msg}`);
        }
        // 3) Fallback: validate liveness via /v1/models (may be slow/cloud-bound).
        //    If this throws, we still fall through to offline rather than crashing.
        try {
            const response = await fetch(`${this.baseUrl}/v1/models`, {
                headers: this.authHeader(workspaceId),
                signal: AbortSignal.timeout(8000),
            });
            if (response.ok) {
                return {
                    model: 'auto',
                    compressionLevel: 3, // moderate default instead of 2
                    activeBlocks: 0,
                    totalMemories: 0,
                    totalThemes: 0,
                    totalSessions: 0,
                    workspaceId,
                    latencyMs: Date.now() - t0,
                    online: true,
                };
            }
        }
        catch (err) {
            const msg = err instanceof Error ? err.message : String(err);
            this.logger?.(`[Jenna] getStatus probe failed (${Date.now() - t0}ms): ${msg}`);
            try {
                require('fs').writeFileSync(require('path').join(__dirname, '..', 'debug.log'), msg);
            }
            catch (e) { }
        }
        return this._offlineStatus(workspaceId);
    }
    /** Best-effort: fetch the active model name from /v1/models without failing the whole status call. */
    async _probeModelName(workspaceId, fallback) {
        try {
            const resp = await fetch(`${this.baseUrl}/v1/models`, {
                headers: this.authHeader(workspaceId),
                signal: AbortSignal.timeout(4000),
            });
            if (resp.ok) {
                const data = await resp.json();
                const ids = data.data?.map(m => m.id) ?? [];
                // Prefer a primary/active model if present, else the first listed.
                const preferred = ['gemma-4-12b-it-moq', 'qwopus3.5-9b-coder-mtp-moq', 'qwen3.5-4b-moq', 'kimi-k2.7-code'];
                for (const p of preferred) {
                    if (ids.includes(p))
                        return p;
                }
                return ids[0] ?? fallback;
            }
        }
        catch {
            // /v1/models is non-critical — keep the fallback.
        }
        return fallback;
    }
    _offlineStatus(workspaceId) {
        return {
            model: 'offline',
            compressionLevel: 0,
            activeBlocks: 0,
            totalMemories: 0,
            totalThemes: 0,
            totalSessions: 0,
            workspaceId,
            latencyMs: -1,
            online: false,
        };
    }
    /** Search the memory store semantically */
    async searchMemory(query, workspaceId) {
        try {
            const resp = await fetch(`${this.baseUrl}/api/search`, {
                method: 'POST',
                headers: this.authHeader(workspaceId),
                body: JSON.stringify({ query, limit: 5 }),
                signal: AbortSignal.timeout(5000),
            });
            if (!resp.ok)
                return [];
            const data = await resp.json();
            return data.results ?? [];
        }
        catch {
            return [];
        }
    }
    /** Inject a bond memory (session summary) into the foveated store */
    async injectBondMemory(summary, workspaceId) {
        try {
            await fetch(`${this.baseUrl}/v1/chat/completions`, {
                method: 'POST',
                headers: this.authHeader(workspaceId),
                body: JSON.stringify({
                    model: 'auto',
                    messages: [
                        {
                            role: 'user',
                            content: `[bond:session_summary] ${summary}`,
                        },
                    ],
                    stream: false,
                    max_tokens: 1, // We don't need a real response — just storage injection
                }),
            });
        }
        catch {
            // Fire-and-forget — bond injection failures are non-fatal
        }
    }
    get lastLatencyMs() {
        return this._lastLatency;
    }
}
exports.FoveatedClient = FoveatedClient;
//# sourceMappingURL=foveatedClient.js.map