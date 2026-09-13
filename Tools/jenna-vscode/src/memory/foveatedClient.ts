/**
 * foveatedClient.ts
 * Thin HTTP/SSE client that wraps the FoveAI Foveated Memory proxy (port 8400).
 * No external dependencies — uses Node's built-in fetch (Node 18+) or the
 * VS Code extension host's globalThis.fetch.
 */

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface MemoryStatus {
  model: string;
  compressionLevel: number;   // XRL level 0-5
  activeBlocks: number;       // active ring blocks in current context
  totalMemories: number;
  totalThemes: number;
  totalSessions: number;
  workspaceId: string;
  latencyMs: number;
  online: boolean;
}

export interface MemorySearchResult {
  content: string;
  score: number;
  timestamp: string;
}

export interface ChatOptions {
  model?: string;
  temperature?: number;
  stream?: boolean;
  workspaceId: string;
  maxTokens?: number;
  persona?: PersonaId;
  compressionLevel?: number;
  customSystemPrompt?: string;
  tasks?: { text: string; done: boolean }[];
  sessionId?: string;
}

export type PersonaId = 'code' | 'architect' | 'audit' | 'scribe' | 'test' | 'probe' | 'plan' | 'selfcode' | 'fovecode';

export interface PersonaDef {
  id: PersonaId;
  name: string;
  shortName: string;
  icon: string;
  role: string;
  description: string;
  systemPrompt: string;
}

export const PERSONAS: Record<PersonaId, PersonaDef> = {
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
  selfcode: {
    id: 'selfcode',
    name: 'SelfCode',
    shortName: 'SelfCode',
    icon: '🤖',
    role: 'Plugin & App Self-Developer',
    description: 'Develops the Jenna extension and the FoveAI app itself — vibe-coding the tool from inside the tool.',
    systemPrompt: `You are Jenna operating in SELFCODE mode — developing the FoveAI system and this very extension (Tools/jenna-vscode) from inside itself.
Your job: implement features, fix bugs, refactor, and organize the codebase for FoveAI — the local-first XR/AI OS whose XRLF models run locally through the foveated-memory proxy (:8400) and llama.cpp runtime (:8402).
You may be a cloud model (NVIDIA NIM) acting as a contractor: XRLF local models are the product — never suggest replacing them with cloud calls. Cloud is scaffolding; local is the cathedral.
Prefer minimal targeted diffs, follow existing conventions, and keep everything typed. Emit code blocks the Apply button can insert.`,
  },
  fovecode: {
    id: 'fovecode',
    name: 'FoveCode',
    shortName: 'FoveCode',
    icon: '🏠',
    role: 'FoveAI Repository Maintainer',
    description: 'Main FoveAI repository mode — full-system view across proxy, runtime, frontends, and tools.',
    systemPrompt: `You are Jenna operating in FOVECODE mode — maintaining the main FoveAI repository as a whole.
Scope: foveated-memory proxy (:8400), XRLF runtime (:8402/8403), dashboard (:8401), XR frontends (:5176/:5177), Tools/*, selfcoder, and the root .env that is the shared source of truth for compression/aggression settings (XRLF_PROXY_AGGRESSION, XRLF_FOVEATION_OVERRIDE, XRLF_CONTEXT_OVERRIDE, XRLF_REPO_ENABLED).
Help organize the repo, keep ports/protocols consistent (replace legacy references, don't merge zombie code), and respect the local-first architecture. XRLF models are the proof-of-concept product; cloud models are optional helpers only.`,
  },
};

// Default system prompt
const JENNA_SYSTEM_PROMPT = PERSONAS.code.systemPrompt;

export class FoveatedClient {
  private baseUrl: string;
  private _lastLatency = 0;


  private logger?: (msg: string) => void;

  constructor(baseUrl: string = 'http://127.0.0.1:8400', logger?: (msg: string) => void) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.logger = logger;
  }

  /** Returns the auth header using workspace ID as the Bearer token (isolates memory per workspace) */
  private authHeader(workspaceId: string): Record<string, string> {
    return {
      'Authorization': `Bearer ${workspaceId}`,
      'Content-Type': 'application/json',
    };
  }

  /**
   * Send a chat request to the foveated proxy.
   * If stream=true, returns an async generator of text chunks.
   */
  async *chat(
    messages: ChatMessage[],
    opts: ChatOptions
  ): AsyncGenerator<string, void, unknown> {
    const t0 = Date.now();
    const baseSystem = (opts.persona && PERSONAS[opts.persona] ? PERSONAS[opts.persona].systemPrompt : JENNA_SYSTEM_PROMPT);
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
      const data = await response.json() as {choices: Array<{message: {content: string}}>};
      this._lastLatency = Date.now() - t0;
      yield data.choices[0]?.message?.content ?? '';
      return;
    }

    // SSE streaming
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') {
          this._lastLatency = Date.now() - t0;
          return;
        }
        try {
          const chunk = JSON.parse(payload) as {
            choices: Array<{ delta?: { content?: string } }>;
          };
          const text = chunk.choices[0]?.delta?.content;
          if (text) yield text;
        } catch {
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
  async getStatus(workspaceId: string): Promise<MemoryStatus> {
    const t0 = Date.now();

    // 1) Local, dependency-free status endpoint (primary source of truth).
    try {
      const statusResp = await fetch(`${this.baseUrl}/api/status`, {
        headers: this.authHeader(workspaceId),
        signal: AbortSignal.timeout(6000),
      });
      if (statusResp.ok) {
        const s = await statusResp.json() as {
          compression_level?: number;
          active_blocks?: number;
          total_memories?: number;
          total_themes?: number;
          total_sessions?: number;
          model?: string;
        };
        // 2) Best-effort enrichment from /v1/models — NEVER fatal if it fails.
        const modelName = await this._probeModelName(workspaceId, s.model || 'auto');
        return {
          model: modelName,
          compressionLevel: s.compression_level ?? 3,  // moderate default instead of 2
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
    } catch (err: unknown) {
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
          compressionLevel: 3,  // moderate default instead of 2
          activeBlocks: 0,
          totalMemories: 0,
          totalThemes: 0,
          totalSessions: 0,
          workspaceId,
          latencyMs: Date.now() - t0,
          online: true,
        };
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      this.logger?.(`[Jenna] getStatus probe failed (${Date.now() - t0}ms): ${msg}`);
      try { require('fs').writeFileSync(require('path').join(__dirname, '..', 'debug.log'), msg); } catch(e){}
    }

    return this._offlineStatus(workspaceId);
  }

  /** Best-effort: fetch the active model name from /v1/models without failing the whole status call. */
  private async _probeModelName(workspaceId: string, fallback: string): Promise<string> {
    if (fallback && fallback !== 'auto' && fallback !== 'unknown') {
      return fallback;
    }
    try {
      const resp = await fetch(`${this.baseUrl}/v1/models`, {
        headers: this.authHeader(workspaceId),
        signal: AbortSignal.timeout(4000),
      });
      if (resp.ok) {
        const data = await resp.json() as { data?: Array<{ id: string }> };
        const ids = data.data?.map(m => m.id) ?? [];
        return ids[0] ?? fallback;
      }
    } catch {
      // /v1/models is non-critical — keep the fallback.
    }
    return fallback;
  }

  private _offlineStatus(workspaceId: string): MemoryStatus {
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
  async searchMemory(query: string, workspaceId: string): Promise<MemorySearchResult[]> {
    try {
      const resp = await fetch(`${this.baseUrl}/api/search`, {
        method: 'POST',
        headers: this.authHeader(workspaceId),
        body: JSON.stringify({ query, limit: 5 }),
        signal: AbortSignal.timeout(5000),
      });
      if (!resp.ok) return [];
      const data = await resp.json() as { results?: MemorySearchResult[] };
      return data.results ?? [];
    } catch {
      return [];
    }
  }

  /** Inject a bond memory (session summary) into the foveated store */
  async injectBondMemory(summary: string, workspaceId: string): Promise<void> {
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
          max_tokens: 1,   // We don't need a real response — just storage injection
        }),
      });
    } catch {
      // Fire-and-forget — bond injection failures are non-fatal
    }
  }

  get lastLatencyMs(): number {
    return this._lastLatency;
  }
}

