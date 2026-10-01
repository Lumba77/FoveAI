/**
 * REMAX/COMAX — Unified Coding Executive with Delegated Sub-Agents
 * REMAX (default): Simple prompt → stream → auto-apply (auto_approve=always)
 * COMAX (expanded): Interactive agent with delegation to local sub-agents
 * 
 * ARCHITECTURE:
 *   PRIMARY CLOUD:  DeepSeek-V4-Pro  → reasons, plans, delegates subtasks
 *   SUB-AGENT 12B:  Qwen3.5-12B      → writes code, edits files (GPU offloaded)
 *   SUB-AGENT 7B:   Qwen3.5-7B       → searches, reads code, memory lookup
 *   SUB-AGENT 4B:   TQL-Coder 4B     → executes tsc/lint, validates builds
 *   SUB-AGENT 0.5B: Qwen2-0.5B       → quick chores, syntax checks
 * 
 * Features:
 * - LLM optimization presets (10 presets incl. DeepSeek)
 * - 9-tier cascade: DeepSeek-V4-Pro → Cloud models → Local sub-agents
 * - Delegation protocol: primary model emits delegate_to() → sub-agent executes → result feeds back
 * - Workflow patterns: iterate, self-critique, sequential thinking
 * - Auto-approve: REMAX never stalls on confirmations
 * - Debug tools: Build, TSC, Health, AUTOFIX
 */
declare const chrome: any;

export class COMAX {
    private static messages: Array<{role: string; content: string; tool_calls?: any[]; tool_call_id?: string}> = [];
    private static isRunning = false;
    private static llmPort = 0;
    private static llmModel = 'deepseek-v4-pro';
    private static abortController: AbortController | null = null;
    private static userContext: string[] = [];
    private static mode: 'remax' | 'comax' = 'remax';
    private static preset: string = 'deepseek_code';
    private static workflow: string = 'direct';

    // LLM Optimization Presets — tuned for different cognitive patterns
    private static readonly PRESETS: Record<string, {label: string; icon: string; temp: number; top_p: number; max_tokens: number; freq_pen: number; pres_pen: number; desc: string}> = {
        // DeepSeek-V4-Pro presets (primary orchestrator)
        deepseek_code:  { label: 'DS-CODE',   icon: '🐋', temp: 0.1,  top_p: 0.9,  max_tokens: 8192, freq_pen: 0.0, pres_pen: 0.0, desc: 'DeepSeek deterministic coding' },
        deepseek_reason:{ label: 'DS-REASON', icon: '🧠', temp: 0.15, top_p: 0.95, max_tokens: 8192, freq_pen: 0.0, pres_pen: 0.0, desc: 'DeepSeek deep reasoning + delegation' },
        // General presets
        coding:    { label: 'CODING',    icon: '⌨️', temp: 0.15, top_p: 0.9,  max_tokens: 4096, freq_pen: 0.0, pres_pen: 0.0, desc: 'Deterministic, greedy decode' },
        reasoning: { label: 'REASON',    icon: '🧠', temp: 0.2,  top_p: 0.95, max_tokens: 8192, freq_pen: 0.0, pres_pen: 0.0, desc: 'Chain-of-thought, deep analysis' },
        creative:  { label: 'CREATIVE',  icon: '🎨', temp: 0.8,  top_p: 0.95, max_tokens: 4096, freq_pen: 0.3, pres_pen: 0.2, desc: 'Divergent, brainstorming' },
        balanced:  { label: 'BALANCED',  icon: '⚖️', temp: 0.5,  top_p: 0.9,  max_tokens: 4096, freq_pen: 0.1, pres_pen: 0.1, desc: 'General purpose' },
        precise:   { label: 'PRECISE',   icon: '🎯', temp: 0.05, top_p: 0.85, max_tokens: 2048, freq_pen: 0.0, pres_pen: 0.0, desc: 'Maximum determinism' },
        chat:      { label: 'CHAT',      icon: '💬', temp: 0.7,  top_p: 0.9,  max_tokens: 2048, freq_pen: 0.2, pres_pen: 0.1, desc: 'Natural conversation' },
        debug:     { label: 'DEBUG',     icon: '🔧', temp: 0.1,  top_p: 0.9,  max_tokens: 4096, freq_pen: 0.0, pres_pen: 0.0, desc: 'Methodical diagnosis' },
        // Qwen3.5 recommended presets (from official settings):
        qwen_think_code: { label: 'QW-CODE',  icon: '💻', temp: 0.6,  top_p: 0.95, max_tokens: 8192, freq_pen: 0.0, pres_pen: 0.0, desc: 'Qwen3.5 thinking mode for WebDev' },
        qwen_think_gen:  { label: 'QW-THINK', icon: '🧠', temp: 1.0,  top_p: 0.95, max_tokens: 8192, freq_pen: 0.0, pres_pen: 1.5, desc: 'Qwen3.5 thinking mode for general' },
        qwen_instruct:   { label: 'QW-INST',  icon: '📝', temp: 0.7,  top_p: 0.8,  max_tokens: 4096, freq_pen: 0.0, pres_pen: 1.5, desc: 'Qwen3.5 non-thinking, general' },
    };

    // 9-Tier Delegation Cascade — Primary orchestrator + cloud models + local sub-agents
    // Primary (Cloud): DeepSeek-V4-Pro → reasons, plans, delegates to sub-agents
    // Sub-Agent 12B (Local GPU): Qwen3.5-12B → writes code, edits files, complex tasks
    // Sub-Agent 7B (Local GPU): Qwen3.5-7B → searches, reads code, memory lookup
    // Sub-Agent 4B (Local CPU): TQL-Coder 4B → tsc/lint, build validation, simple syntax
    // Sub-Agent 0.5B (Local CPU): Qwen2-0.5B → tiny chores, quick checks, always available
    private static readonly CASCADE = [
        // PRIMARY ORCHESTRATOR
        { name: 'DeepSeek-V4-Pro',   port: 0,    model: 'deepseek-v4-pro',                  icon: '🐋', tier: 'primary', role: 'orchestrator', max_tokens: 8192 },
        // CLOUD FALLBACKS
        { name: 'Ollama Direct',    port: -3,   model: 'gemini-3-flash-preview',           icon: '🎯', tier: 'direct_cloud' },
        { name: 'Ollama Cloud',     port: 0,    model: 'glm-5.1',                          icon: '☁️', tier: 'standard' },
        { name: 'Qwen3.5 Deep',     port: 0,    model: 'qwen3.5:397b',                     icon: '🧠', tier: 'deep', preserve_thinking: true },
        // LOCAL SUB-AGENTS (LM Studio port 1234)
        { name: 'Qwen12B Editor',   port: 1234, model: 'qwen3.5:12b',                      icon: '✍️', tier: 'subagent_edit', role: 'editor',
            tools: ['write_file', 'edit_file', 'exec:safe'],
            sp: 'You are FoveAI EDITOR sub-agent. Write clean TypeScript/Python code. Output only the file content, no explanations. Be precise and minimal.' },
        { name: 'Qwen7B Searcher',  port: 1234, model: 'qwen3.5:7b',                       icon: '🔍', tier: 'subagent_search', role: 'searcher',
            tools: ['read_file', 'list_files', 'search_files', 'search_memory'],
            sp: 'You are FoveAI SEARCH sub-agent. Read files and find code patterns. Return results concisely. No chit-chat.' },
        { name: 'TQL-Coder Linter', port: 1234, model: 'TQL-Coder-Qwen3.5-4B-thinking',    icon: '🖥️', tier: 'subagent_lint', role: 'linter', enable_thinking: true,
            tools: ['exec:tsc', 'exec:build'],
            sp: 'You are FoveAI LINTER sub-agent. Run the given lint/build command. Report errors ONLY. If clean, reply "OK".' },
        { name: 'Qwen05 Chore',     port: 1234, model: 'Qwen2-0.5B-Instruct-heretic',      icon: '🔥', tier: 'subagent_micro', role: 'micro',
            tools: ['exec:simple'],
            sp: 'You are FoveAI MICRO sub-agent. Execute this simple task. Be fast, minimal output. One-line responses preferred.' },
        { name: 'Gemini Flash',      port: -1,   model: 'gemini-2.5-flash',                icon: '⚡', tier: 'flash' },
    ];

    // Sub-agent delegation map — which sub-agent handles which tool categories
    private static readonly DELEGATION: Record<string, {agent: string; model: string; tools: string[]}> = {
        write:  { agent: 'Qwen12B Editor',  model: 'qwen3.5:12b', tools: ['write_file', 'edit_file'] },
        search: { agent: 'Qwen7B Searcher', model: 'qwen3.5:7b',  tools: ['read_file', 'list_files', 'search_files', 'search_memory'] },
        lint:   { agent: 'TQL-Coder Linter',model: 'TQL-Coder-Qwen3.5-4B-thinking', tools: ['exec:tsc', 'exec:build'] },
        chore:  { agent: 'Qwen05 Chore',    model: 'Qwen2-0.5B-Instruct-heretic', tools: ['exec:simple'] },
    };

    // Workflow patterns — structured thinking modes
    private static readonly WORKFLOWS: Record<string, {label: string; icon: string; desc: string; prompt: string}> = {
        direct:    { label: 'DIRECT',    icon: '➡️', desc: 'Single response', prompt: '' },
        iterate:   { label: 'ITERATE',   icon: '🔄', desc: 'Multi-pass refinement',
            prompt: '\n\n### WORKFLOW: ITERATIVE REFINEMENT\nExecute this task in passes:\n1. Draft: Initial implementation\n2. Review: Read back what you wrote, identify issues\n3. Refine: Apply improvements\n4. Verify: Run build/check if possible\nRepeat until satisfied. Mark each pass clearly.' },
        critique:  { label: 'CRITIQUE',  icon: '🔍', desc: 'Self-criticism + fix',
            prompt: '\n\n### WORKFLOW: SELF-CRITIQUE\n1. Generate initial solution\n2. Switch to critic mode: "What\'s wrong with this? What edge cases fail?"\n3. Address every criticism found\n4. Re-critique the improved version\n5. Final pass: confirm all criticisms resolved' },
        sequential: { label: 'SEQUENTIAL', icon: '📋', desc: 'Step-by-step planning',
            prompt: '\n\n### WORKFLOW: SEQUENTIAL THINKING\nBreak this task into numbered steps. For each step:\n1. State what you\'ll do and why\n2. Execute the step (use tools)\n3. Verify the result before proceeding\n4. Only move to next step when current is confirmed\nIf a step fails, diagnose before retrying. Never skip steps.' },
    };

    private static baseSystemPrompt = `You are REMAX/COMAX, FoveAI's unified AI coding executive with delegated sub-agents.

### FoveAI REPO ARCHITECTURE
- frontend/XR_Vessel/ — Vite web UI (src/main.ts, src/components/, src/senses/)
- frontend/XR_Vessel/xr_app.py — Python backend + API proxy
- backend/Soul/ — AI personality service (port 8405) — STT → LLM → TTS voice pipeline
- backend/Memory/ — Lumax MCP memory server (port 8002)
- backend/Cognition/ — Cognitive agents (ag_coder.py=REMAX, compagent.py)
- backend/Creativity/ — Creative generation
- Scripts/ — Background utilities
- Tools/Chatterbox-TTS-Server/ — Local TTS engine
- Service/ — Windows service management

### SUB-AGENT DELEGATION SYSTEM (USE THIS!)
You have 4 specialized local sub-agents running in LM Studio. Use delegate_to() to offload work:
  delegate_to(\"write\", \"Write file X with content Y\")     → Qwen12B Editor (writes/edit files)
  delegate_to(\"search\", \"Find pattern Z in files\")         → Qwen7B Searcher (reads/searches files)
  delegate_to(\"lint\", \"Run tsc --noEmit\")                  → TQL-Coder Linter (runs tsc/build, reports errors)
  delegate_to(\"chore\", \"Quick syntax check\")               → Qwen05 Chore (tiny tasks, fast)

Always delegate write_file, edit_file to the \"write\" sub-agent. Delegate tsc/build/lint to the \"lint\" agent. Read/search tasks go to \"search\". Use delegate_to() for EVERY file modification — you are the orchestrator, not the executor.

### AUTO-APPROVE MODE
This is a non-interactive pipeline. NEVER ask for confirmation. Apply changes immediately after generating code. Use the auto-compile check to validate your work.

### TECH STACK
TypeScript/Vite, Python FastAPI, Ollama_Cloud LLM, LM Studio local models.

Available tools: read_file, write_file, list_files, search_files, exec, search_memory, memory_context, memory_add, memory_import

Rules: Always delegate writes. Auto-apply changes. Never wait for human confirmation. Be decisive and fast.`;

    private static readonly TOOLS: any[] = JSON.parse(`[
        {"type": "function", "function": {"name": "read_file", "description": "Read a file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
        {"type": "function", "function": {"name": "write_file", "description": "Write a file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
        {"type": "function", "function": {"name": "list_files", "description": "List directory", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
        {"type": "function", "function": {"name": "search_files", "description": "Search codebase", "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}, "required": ["pattern"]}}},
        {"type": "function", "function": {"name": "exec", "description": "Run shell command", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
        {"type": "function", "function": {"name": "search_memory", "description": "Search shared memory", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
        {"type": "function", "function": {"name": "memory_context", "description": "Get session context", "parameters": {"type": "object", "properties": {}}}},
        {"type": "function", "function": {"name": "memory_add", "description": "Save to shared memory", "parameters": {"type": "object", "properties": {"role": {"type": "string", "enum": ["user","assistant","system"]}, "content": {"type": "string"}, "source": {"type": "string"}}, "required": ["role","content"]}}},
        {"type": "function", "function": {"name": "memory_import", "description": "Import session history", "parameters": {"type": "object", "properties": {"source": {"type": "string", "enum": ["cline","gemini","all"]}}, "required": ["source"]}}}
    ]`);

    public static render(container: HTMLElement): void {
        container.innerHTML = '';
        container.style.overflow = 'hidden';
        const wrapper = document.createElement('div');
        wrapper.style.cssText = 'display: flex; flex-direction: column; height: 100%;';
        const isRemax = COMAX.mode === 'remax';

        // Header
        const header = document.createElement('div');
        header.style.cssText = 'display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; flex-shrink: 0;';
        header.innerHTML = `
            <div style="display: flex; align-items: center; gap: 10px;">
                <div style="font-size: 1.3rem;">${isRemax ? '🚀' : '⚡'}</div>
                <div>
                    <div style="font-family: 'Orbitron', sans-serif; font-size: 0.8rem; color: var(--neon-blue); letter-spacing: 2px;">${isRemax ? 'REMAX' : 'COMAX'}</div>
                    <div style="font-family: 'Share Tech Mono', monospace; font-size: 0.55rem; color: rgba(255,255,255,0.4);">${isRemax ? 'REQUEST MANAGING EXEC · STREAM' : 'CODING MANAGING EXEC · INTERACTIVE'}</div>
                </div>
            </div>
            <div style="display: flex; gap: 4px; align-items: center; flex-wrap: wrap;">
                <button id="cx-toggle" style="background: rgba(0,243,255,0.1); border: 1px solid rgba(0,243,255,0.3); border-radius: 4px; color: var(--neon-blue); padding: 4px 8px; font-family: 'Share Tech Mono', monospace; font-size: 0.6rem; cursor: pointer;">${isRemax ? '⚡ COMAX' : '🚀 REMAX'}</button>
                ${!isRemax ? `
                <button id="cx-ctx" style="background: rgba(147,51,234,0.1); border: 1px solid rgba(147,51,234,0.3); border-radius: 4px; color: #c084fc; padding: 4px 8px; font-family: 'Share Tech Mono', monospace; font-size: 0.6rem; cursor: pointer;">📂</button>
                <button id="cx-upload" style="background: rgba(46,204,113,0.1); border: 1px solid rgba(46,204,113,0.3); border-radius: 4px; color: var(--neon-green); padding: 4px 8px; font-family: 'Share Tech Mono', monospace; font-size: 0.6rem; cursor: pointer;">📎</button>
                <select id="cx-model" style="background: rgba(0,0,0,0.5); color: var(--neon-blue); border: 1px solid var(--border); border-radius: 4px; padding: 4px 8px; font-family: 'Share Tech Mono', monospace; font-size: 0.6rem;">
                    <option value="deepseek-v4-pro" selected>🐋 DeepSeek-V4-Pro</option><option value="qwen3.5:12b">✍️ Qwen12B Editor</option><option value="qwen3.5:7b">🔍 Qwen7B Searcher</option><option value="glm-5.1">🧠 GLM-5.1</option><option value="qwen3.5:397b">🌊 Qwen3.5 Deep</option><option value="gemini-2.5-pro">💎 GeminiPro</option><option value="TQL-Coder-Qwen3.5-4B-thinking">🖥️ TQL-Coder</option><option value="Qwen2-0.5B-Instruct-heretic">🔥 Qwen05 Chore</option>
                </select>
                <select id="cx-backend" style="background: rgba(0,0,0,0.5); color: var(--neon-blue); border: 1px solid var(--border); border-radius: 4px; padding: 4px 8px; font-family: 'Share Tech Mono', monospace; font-size: 0.6rem;" title="Backend route: Direct=bypasses Soul, Cloud=via Jen, LM=local">
                    <option value="-3">🎯 Direct</option><option value="0">☁️ Cloud</option><option value="-1">⚡ Gemini</option><option value="1234">🖥️ LM</option><option value="11434">🦙 Ollama</option>
                </select>
                <select id="cx-preset" style="background: rgba(0,0,0,0.5); color: #ffaa00; border: 1px solid rgba(255,170,0,0.3); border-radius: 4px; padding: 4px 8px; font-family: 'Share Tech Mono', monospace; font-size: 0.6rem;" title="LLM optimization preset">
                    ${Object.entries(COMAX.PRESETS).map(([k,v]) => `<option value="${k}" ${k===COMAX.preset?'selected':''}>${v.icon} ${v.label}</option>`).join('')}
                </select>
                <select id="cx-workflow" style="background: rgba(0,0,0,0.5); color: var(--neon-green); border: 1px solid rgba(46,204,113,0.3); border-radius: 4px; padding: 4px 8px; font-family: 'Share Tech Mono', monospace; font-size: 0.6rem;" title="Workflow pattern">
                    ${Object.entries(COMAX.WORKFLOWS).map(([k,v]) => `<option value="${k}" ${k===COMAX.workflow?'selected':''}>${v.icon} ${v.label}</option>`).join('')}
                </select>` : ''}
                <button id="cx-debug" style="background: rgba(255,170,0,0.1); border: 1px solid rgba(255,170,0,0.3); border-radius: 4px; color: #ffaa00; padding: 4px 8px; font-family: 'Share Tech Mono', monospace; font-size: 0.6rem; cursor: pointer;">🔧</button>
                <button id="cx-clear" style="background: rgba(255,0,127,0.1); border: 1px solid rgba(255,0,127,0.3); border-radius: 4px; color: rgba(255,0,127,0.7); padding: 4px 8px; font-family: 'Share Tech Mono', monospace; font-size: 0.6rem; cursor: pointer;">CLR</button>
            </div>`;
        wrapper.appendChild(header);

        // Debug panel
        const debugPanel = document.createElement('div');
        debugPanel.id = 'cx-dbg';
        debugPanel.style.cssText = 'display: none; flex-shrink: 0; background: rgba(0,0,0,0.4); border: 1px solid rgba(255,170,0,0.2); border-radius: 6px; padding: 8px; margin-bottom: 8px;';
        debugPanel.innerHTML = `
            <div style="font-family: 'Orbitron', sans-serif; font-size: 0.6rem; color: #ffaa00; letter-spacing: 1px; margin-bottom: 6px;">🔧 DEBUG TOOLS</div>
            <div style="display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 6px;">
                <button id="db-build" style="background: rgba(0,243,255,0.1); border: 1px solid var(--border); border-radius: 3px; color: var(--neon-blue); padding: 3px 8px; font-family: 'Share Tech Mono', monospace; font-size: 0.6rem; cursor: pointer;">▶ BUILD</button>
                <button id="db-tsc" style="background: rgba(147,51,234,0.1); border: 1px solid var(--border); border-radius: 3px; color: #c084fc; padding: 3px 8px; font-family: 'Share Tech Mono', monospace; font-size: 0.6rem; cursor: pointer;">TSC</button>
                <button id="db-health" style="background: rgba(46,204,113,0.1); border: 1px solid var(--border); border-radius: 3px; color: var(--neon-green); padding: 3px 8px; font-family: 'Share Tech Mono', monospace; font-size: 0.6rem; cursor: pointer;">♥ HEALTH</button>
                <button id="db-fix" style="background: rgba(255,0,127,0.1); border: 1px solid rgba(255,0,127,0.3); border-radius: 3px; color: var(--neon-pink); padding: 3px 8px; font-family: 'Share Tech Mono', monospace; font-size: 0.6rem; cursor: pointer;">🔧 AUTOFIX</button>
            </div>
            <div id="db-out" style="background: #050505; border: 1px solid var(--border); border-radius: 4px; padding: 6px; font-family: 'Share Tech Mono', monospace; font-size: 0.65rem; color: rgba(255,255,255,0.6); max-height: 120px; overflow-y: auto; white-space: pre-wrap;">Ready.</div>`;
        wrapper.appendChild(debugPanel);

        // Chat area
        const chatArea = document.createElement('div');
        chatArea.id = 'cx-chat';
        chatArea.style.cssText = 'flex: 1; overflow-y: auto; background: #050505; border: 1px solid var(--border); border-radius: 6px; padding: 10px; margin-bottom: 8px; display: flex; flex-direction: column; gap: 6px; min-height: 0;';
        if (COMAX.messages.length === 0) {
            chatArea.innerHTML = `<div style="font-family: 'Share Tech Mono', monospace; font-size: 0.7rem; color: rgba(255,255,255,0.3); padding: 20px; text-align: center;">
                ${isRemax ? '🚀 REMAX — Type a task, stream + auto-apply<br><span style="color:rgba(255,255,255,0.2);">Click ⚡ COMAX for interactive mode</span>' : '⚡ COMAX — Interactive agent with tools, memory & workflows<br><span style="color:rgba(255,255,255,0.2);">Presets • Cascade • Iteration • Self-critique • Sequential thinking</span>'}
            </div>`;
        } else { COMAX.renderMessages(chatArea); }
        wrapper.appendChild(chatArea);

        // Input
        const inputArea = document.createElement('div');
        inputArea.style.cssText = 'flex-shrink: 0; display: flex; gap: 8px;';
        inputArea.innerHTML = `
            <textarea id="cx-in" placeholder="${isRemax ? 'REMAX: coding task (auto-apply)' : 'COMAX: interactive command'}" style="flex: 1; min-height: 120px; height: 120px; background: rgba(0,0,0,0.5); border: 1px solid var(--border); border-radius: 4px; padding: 10px; font-family: 'Share Tech Mono', monospace; font-size: 0.8rem; color: #fff; resize: vertical; outline: none; line-height: 1.5;"></textarea>
            <div style="display: flex; flex-direction: column; gap: 4px;">
                <button id="cx-send" style="width: 80px; flex: 1; background: rgba(0,243,255,0.15); border: 1px solid var(--neon-blue); border-radius: 4px; color: var(--neon-blue); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; font-weight: 700; cursor: pointer;">SEND</button>
                <button id="cx-stop" style="width: 80px; background: rgba(255,0,127,0.15); border: 1px solid rgba(255,0,127,0.5); border-radius: 4px; color: rgba(255,0,127,0.7); font-family: 'Orbitron', sans-serif; font-size: 0.6rem; cursor: pointer; display: none;">STOP</button>
            </div>`;
        wrapper.appendChild(inputArea);
        container.appendChild(wrapper);

        // Events
        const input = wrapper.querySelector('#cx-in') as HTMLTextAreaElement;
        const sendBtn = wrapper.querySelector('#cx-send') as HTMLButtonElement;
        const stopBtn = wrapper.querySelector('#cx-stop') as HTMLButtonElement;

        wrapper.querySelector('#cx-toggle')!.addEventListener('click', () => { COMAX.mode = COMAX.mode === 'remax' ? 'comax' : 'remax'; COMAX.render(container); });
        wrapper.querySelector('#cx-debug')!.addEventListener('click', () => { const p = wrapper.querySelector('#cx-dbg') as HTMLElement; p.style.display = p.style.display === 'none' ? 'block' : 'none'; });
        wrapper.querySelector('#cx-clear')!.addEventListener('click', () => { COMAX.messages = []; COMAX.userContext = []; COMAX.isRunning = false; chatArea.innerHTML = '<div style="font-family:\'Share Tech Mono\',monospace;font-size:0.7rem;color:rgba(255,255,255,0.3);padding:20px;text-align:center;">CLEARED.</div>'; });

        // COMAX mode buttons
        if (!isRemax) {
            const ctxBtn = wrapper.querySelector('#cx-ctx') as HTMLButtonElement;
            const uploadBtn = wrapper.querySelector('#cx-upload') as HTMLButtonElement;
            ctxBtn && (ctxBtn.onclick = async () => { const p = prompt('File path:'); if (!p) return; try { const r = await fetch('/api/dev/cline', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tool:'read_file',path:p})}); const d = await r.json(); COMAX.userContext.push(`--- ${p} ---\n${typeof d==='string'?d:JSON.stringify(d)}`); ctxBtn.textContent = `📂(${COMAX.userContext.length})`; } catch {} });
            uploadBtn && (uploadBtn.onclick = () => { const fi = document.createElement('input'); fi.type='file'; fi.accept='.ts,.js,.py,.json,.yml,.yaml,.md,.txt,.css,.html'; fi.onchange = async () => { const f = fi.files?.[0]; if (!f) return; COMAX.userContext.push(`--- ${f.name} ---\n${await f.text()}`); uploadBtn.textContent = `📎(${COMAX.userContext.length})`; }; fi.click(); });
        }

        // Debug tools
        const dbOut = wrapper.querySelector('#db-out') as HTMLElement;
        const runDb = async (label: string, cmd: string) => { dbOut.textContent = `${label}: Running...`; try { const r = await fetch('/api/dev/cline', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tool:'exec',command:cmd})}); const d = await r.json(); dbOut.textContent = `${label}: ${JSON.stringify(d,null,2).substring(0,2000)}`; if (dbOut.textContent.includes('error') || dbOut.textContent.includes('Error')) dbOut.textContent += '\n⚠️ Click AUTOFIX'; } catch { dbOut.textContent = `${label}: Failed`; } };
        wrapper.querySelector('#db-build')?.addEventListener('click', () => runDb('BUILD', 'npm run build --prefix frontend/XR_Vessel'));
        wrapper.querySelector('#db-tsc')?.addEventListener('click', () => runDb('TSC', 'npx tsc --noEmit --project frontend/XR_Vessel/tsconfig.json'));
        wrapper.querySelector('#db-health')?.addEventListener('click', async () => { dbOut.textContent = 'HEALTH: Checking...'; const svcs = [{n:'Soul',u:'http://localhost:8405/health'},{n:'Memory',u:'http://localhost:8002/health'}]; const res: string[] = []; for (const s of svcs) { try { const r = await fetch(s.u, {signal: AbortSignal.timeout(3000)}); res.push(`${s.n}: ✅ ${r.status}`); } catch { res.push(`${s.n}: ❌ unreachable`); } } dbOut.textContent = res.join('\n'); });
        wrapper.querySelector('#db-fix')?.addEventListener('click', () => { const errTxt = dbOut.textContent; if (errTxt.includes('error') || errTxt.includes('Error')) { COMAX.mode = 'comax'; COMAX.render(container); setTimeout(() => { const inp = document.getElementById('cx-in') as HTMLTextAreaElement; if (inp) inp.value = `[AUTOFIX] Fix these errors:\n${errTxt.substring(0,800)}`; }, 100); } else { dbOut.textContent = 'All clear! ✅'; } });

        // Send
        const send = () => {
            const t = input.value.trim(); if (!t || COMAX.isRunning) return;
            if (!isRemax) {
                const ms = wrapper.querySelector('#cx-model') as HTMLSelectElement;
                const bs = wrapper.querySelector('#cx-backend') as HTMLSelectElement;
                const ps = wrapper.querySelector('#cx-preset') as HTMLSelectElement;
                const ws = wrapper.querySelector('#cx-workflow') as HTMLSelectElement;
                if (ms) COMAX.llmModel = ms.value;
                if (bs) COMAX.llmPort = parseInt(bs.value);
                if (ps) COMAX.preset = ps.value;
                if (ws) COMAX.workflow = ws.value;
            }
            input.value = '';
            isRemax ? COMAX.remaxSend(t, chatArea, sendBtn, stopBtn) : COMAX.comaxSend(t, chatArea, sendBtn, stopBtn);
        };
        sendBtn.onclick = send;
        input.onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } };
        stopBtn.onclick = () => { if (COMAX.abortController) { COMAX.abortController.abort(); COMAX.isRunning = false; sendBtn.style.display = ''; stopBtn.style.display = 'none'; } };
    }

    // REMAX: Simple stream via backend
    private static async remaxSend(text: string, chatArea: HTMLElement, sendBtn: HTMLButtonElement, stopBtn: HTMLButtonElement): Promise<void> {
        COMAX.isRunning = true; sendBtn.style.display = 'none'; stopBtn.style.display = '';
        COMAX.abortController = new AbortController();
        const uDiv = document.createElement('div'); uDiv.style.cssText = 'padding:8px;border-radius:4px;font-family:"Share Tech Mono",monospace;font-size:0.72rem;background:rgba(0,243,255,0.05);border-left:3px solid var(--neon-blue);color:#e0e0e0;white-space:pre-wrap;'; uDiv.textContent = text; chatArea.appendChild(uDiv);
        const oDiv = document.createElement('div'); oDiv.style.cssText = 'padding:8px;border-radius:4px;font-family:"Share Tech Mono",monospace;font-size:0.72rem;background:rgba(147,51,234,0.05);border-left:3px solid #c084fc;color:#39ff14;white-space:pre-wrap;line-height:1.4;'; chatArea.appendChild(oDiv); chatArea.scrollTop = chatArea.scrollHeight;
        try {
            const r = await fetch('/api/dev/aider', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:text}),signal:COMAX.abortController.signal});
            if (!r.body) { oDiv.textContent = '[No stream]'; return; }
            const reader = r.body.getReader(); const dec = new TextDecoder();
            while (true) { const {done, value} = await reader.read(); if (done) break; oDiv.textContent += dec.decode(value, {stream:true}); chatArea.scrollTop = chatArea.scrollHeight; }
        } catch (e: any) { if (e.name !== 'AbortError') oDiv.textContent += `\n[Error] ${e.message}`; else oDiv.textContent += '\n[Stopped]'; }
        finally { COMAX.isRunning = false; sendBtn.style.display = ''; stopBtn.style.display = 'none'; COMAX.abortController = null; }
    }

    // COMAX: Interactive agent with workflow support
    private static async comaxSend(text: string, chatArea: HTMLElement, sendBtn: HTMLButtonElement, stopBtn: HTMLButtonElement): Promise<void> {
        COMAX.isRunning = true; sendBtn.style.display = 'none'; stopBtn.style.display = '';
        if (COMAX.messages.length === 0) {
            let p = await COMAX.injectMemoryContext();
            if (COMAX.userContext.length) p += '\n\n### USER CONTEXT\n' + COMAX.userContext.join('\n\n');
            // Inject workflow pattern into system prompt
            const wf = COMAX.WORKFLOWS[COMAX.workflow];
            if (wf && wf.prompt) p += wf.prompt;
            COMAX.messages.push({role:'system',content:p});
        }
        COMAX.addMsg(chatArea, {role:'user',content:text});
        COMAX.abortController = new AbortController();
        try { await COMAX.agentLoop(chatArea); } catch (e: any) { COMAX.addMsg(chatArea, {role:'assistant',content: e.name==='AbortError' ? '[Stopped]' : `[Error] ${e.message}`}); }
        finally { COMAX.isRunning = false; sendBtn.style.display = ''; stopBtn.style.display = 'none'; COMAX.abortController = null; }
    }

    private static addMsg(chatArea: HTMLElement, msg: any): void { COMAX.messages.push(msg); COMAX.renderMessages(chatArea); }

    private static renderMessages(chatArea: HTMLElement): void {
        chatArea.innerHTML = '';
        for (let mi = 0; mi < COMAX.messages.length; mi++) {
            const msg = COMAX.messages[mi];
            if (msg.role === 'system') continue;
            const wrapper = document.createElement('div');
            wrapper.style.cssText = 'position: relative;';
            const div = document.createElement('div');
            div.style.cssText = 'padding:8px 36px 8px 8px;border-radius:4px;font-family:"Share Tech Mono",monospace;font-size:0.72rem;line-height:1.5;white-space:pre-wrap;word-break:break-word;';
            if (msg.role === 'user') { div.style.background='rgba(0,243,255,0.05)'; div.style.borderLeft='3px solid var(--neon-blue)'; div.style.color='#e0e0e0'; div.textContent=msg.content; }
            else if (msg.role === 'assistant') { div.style.background='rgba(147,51,234,0.05)'; div.style.borderLeft='3px solid #c084fc'; div.style.color='#e0e0e0'; div.textContent=msg.content||''; if (msg.tool_calls) for (const tc of msg.tool_calls) { const td = document.createElement('div'); td.style.cssText='margin-top:4px;padding:4px 8px;background:rgba(255,170,0,0.08);border:1px solid rgba(255,170,0,0.2);border-radius:3px;font-size:0.65rem;color:#ffaa00;'; td.textContent=`⚡ ${tc.function.name}(${tc.function.arguments})`; div.appendChild(td); } }
            else if (msg.role === 'tool') { div.style.background='rgba(46,204,113,0.05)'; div.style.borderLeft='3px solid var(--neon-green)'; div.style.color='rgba(255,255,255,0.6)'; div.style.fontSize='0.65rem'; div.textContent=`→ ${msg.content.substring(0,500)}${msg.content.length>500?'...':''}`; }
            wrapper.appendChild(div);
            // Copy button — appears on hover
            const copyBtn = document.createElement('button');
            copyBtn.textContent = '📋';
            copyBtn.title = 'Copy response to clipboard';
            copyBtn.style.cssText = 'position: absolute; top: 8px; right: 8px; background: rgba(0,243,255,0.1); border: 1px solid rgba(0,243,255,0.3); border-radius: 3px; color: var(--neon-blue); font-size: 0.65rem; cursor: pointer; padding: 2px 6px; opacity: 0; transition: opacity 0.15s;';
            copyBtn.onmouseenter = () => { copyBtn.style.opacity = '1'; };
            copyBtn.onmouseleave = () => { copyBtn.style.opacity = '0'; };
            copyBtn.onclick = async (e) => {
                e.stopPropagation();
                const txt = div.textContent || '';
                try { await navigator.clipboard.writeText(txt); copyBtn.textContent = '✅'; setTimeout(() => { copyBtn.textContent = '📋'; }, 1000); }
                catch { copyBtn.textContent = '❌'; setTimeout(() => { copyBtn.textContent = '📋'; }, 1000); }
            };
            wrapper.appendChild(copyBtn);
            // Show copy button on wrapper hover
            wrapper.onmouseenter = () => { copyBtn.style.opacity = '1'; };
            wrapper.onmouseleave = () => { copyBtn.style.opacity = '0'; };
            chatArea.appendChild(wrapper);
        }
        chatArea.scrollTop = chatArea.scrollHeight;
    }

    // === DELEGATION PROTOCOL ===
    // Primary model (DeepSeek-V4-Pro) emits: delegate_to({target: 'editor|searcher|linter|micro', task: '...'})
    // COMAX routes task to the correct sub-agent model in LM Studio, captures result, feeds back to primary.
    private static async delegateTo(target: string, task: string, chatArea: HTMLElement): Promise<string> {
        const meta = COMAX.DELEGATION[target];
        if (!meta) return `Unknown delegation target: ${target}. Use: ${Object.keys(COMAX.DELEGATION).join(', ')}`;
        const agent = COMAX.CASCADE.find(l => l.name === meta.agent);
        if (!agent) return `Agent not found: ${meta.agent}`;
        const sp = (agent as any).sp || 'You are a FoveAI sub-agent. Execute the task precisely and output only the result.';
        COMAX.addMsg(chatArea, {role:'tool',content: `🔄 Delegating to ${meta.agent} (${meta.model})\n   Task: ${task.substring(0, 100)}`});
        try {
            const body: any = {
                messages: [{role:'system',content:sp},{role:'user',content:task}],
                model: meta.model, temperature: 0.1, max_tokens: 2048, stream: false,
            };
            // Sub-agents use LM Studio port 1234
            const r = await fetch('/api/dev/cline_llm?port=1234', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify(body), signal: COMAX.abortController?.signal,
            });
            if (!r.ok) { COMAX.addMsg(chatArea, {role:'tool',content:`⚠️ ${meta.agent} failed: ${r.status} → trying cascade`}); return `[ERROR: ${meta.agent} returned ${r.status}]`; }
            const d = await r.json();
            const content = d.choices?.[0]?.message?.content || JSON.stringify(d);
            COMAX.addMsg(chatArea, {role:'tool',content:`✅ ${meta.agent}: ${content.substring(0, 300)}`});
            return content;
        } catch (e: any) {
            COMAX.addMsg(chatArea, {role:'tool',content:`❌ ${meta.agent} unavailable: ${e.message}`});
            return `[ERROR: ${meta.agent} unavailable: ${e.message}]`;
        }
    }

    private static async agentLoop(chatArea: HTMLElement, maxIter = 20): Promise<void> {
        for (let i = 0; i < maxIter; i++) {
            const resp = await COMAX.callLLM(COMAX.messages);
            if (!resp) { COMAX.addMsg(chatArea, {role:'assistant',content:'[LLM failed]'}); return; }
            const ch = resp.choices?.[0]; if (!ch) return;
            const content = ch.message?.content || '';
            // Check for delegation directives in primary model's response
            const delegateMatch = content.match(/delegate_to\(['"](.+?)['"],\s*['"](.+?)['"]\)/i);
            if (delegateMatch) {
                const targetAgent = delegateMatch[1];
                const subtask = delegateMatch[2];
                const result = await COMAX.delegateTo(targetAgent, subtask, chatArea);
                COMAX.messages.push({role:'user',content:`Sub-agent ${targetAgent} result:\n${result}`});
                // Re-query primary with the result — don't stop the loop
                continue;
            }
            const am: any = {role:'assistant',content}; if (ch.message?.tool_calls) am.tool_calls = ch.message.tool_calls;
            COMAX.addMsg(chatArea, am);
            if (!ch.message?.tool_calls?.length) return;
            for (const tc of ch.message.tool_calls) {
                let args: any = {}; try { args = JSON.parse(tc.function.arguments); } catch {}
                let res: any;
                // Route write/edit tools to Editor sub-agent if available
                const isWrite = ['write_file','edit_file'].includes(tc.function.name);
                const isRead = ['read_file','list_files','search_files'].includes(tc.function.name);
                const isExecLint = tc.function.name === 'exec' && typeof args.command === 'string' && /tsc|lint|build/.test(args.command);
                const isExecSimple = tc.function.name === 'exec' && !isExecLint;
                if (isWrite) {
                    res = await COMAX.delegateTo('write', `${tc.function.name}: ${tc.function.arguments}`, chatArea);
                } else if (isExecLint) {
                    res = await COMAX.delegateTo('lint', `Run: ${args.command}`, chatArea);
                } else if (['read_file','write_file','list_files','search_files','exec'].includes(tc.function.name)) {
                    res = await COMAX.executeTool(tc.function.name, args);
                } else if (['search_memory','memory_context','memory_add','memory_import'].includes(tc.function.name)) {
                    res = await COMAX.execMem(tc.function.name, args);
                } else {
                    res = {error: `Unknown: ${tc.function.name}`};
                }
                COMAX.addMsg(chatArea, {role:'tool',content:typeof res==='string'?res:JSON.stringify(res),tool_call_id:tc.id} as any);
            }
            if (COMAX.abortController?.signal.aborted) throw new DOMException('Aborted','AbortError');
        }
        COMAX.addMsg(chatArea, {role:'assistant',content:'[Max iterations reached]'});
    }

    private static async callLLM(msgs: any[]): Promise<any> {
        const p = COMAX.PRESETS[COMAX.preset] || COMAX.PRESETS.coding;
        const url = COMAX.llmPort === 0 ? '/api/dev/cline_llm' : `/api/dev/cline_llm?port=${COMAX.llmPort}`;
        // Check if current model has preserve_thinking (deep tier)
        const currentLayer = COMAX.CASCADE.find(l => l.port === COMAX.llmPort && l.model === COMAX.llmModel);
        const preserveThinking = (currentLayer as any)?.preserve_thinking || false;
        const enableThinking = (currentLayer as any)?.enable_thinking || false;
        const body: any = {
                model: COMAX.llmModel || undefined, messages: msgs, tools: COMAX.TOOLS, tool_choice: 'auto',
                temperature: p.temp, top_p: p.top_p, max_tokens: p.max_tokens,
                frequency_penalty: p.freq_pen, presence_penalty: p.pres_pen,
                preserve_thinking: preserveThinking,
        };
        // Local Qwen3.5 models use enable_thinking (ChatML <arg_key>...</think> format), not Ollama preserve_thinking
        if (enableThinking) body.enable_thinking = true;
        try {
            const r = await fetch(url, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal: COMAX.abortController?.signal});
            if (r.ok) return await r.json();
            // Cascade fallback on failure — try each tier (Flash → Standard → Deep → Local Think → Local Micro)
            for (const layer of COMAX.CASCADE) {
                if (layer.port === COMAX.llmPort && layer.model === COMAX.llmModel) continue;
                try {
                    const curl = layer.port <= 0 ? '/api/dev/cline_llm' : `/api/dev/cline_llm?port=${layer.port}`;
                    const lp = (layer as any).preserve_thinking || false;
                    const le = (layer as any).enable_thinking || false;
                    const fb: any = {
                        model: layer.model, messages: msgs, tools: COMAX.TOOLS, tool_choice: 'auto',
                        temperature: p.temp, top_p: p.top_p, max_tokens: p.max_tokens,
                        frequency_penalty: p.freq_pen, presence_penalty: p.pres_pen,
                        preserve_thinking: lp,
                    };
                    if (le) fb.enable_thinking = true;
                    const cr = await fetch(curl, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(fb),signal: COMAX.abortController?.signal});
                    if (cr.ok) return await cr.json();
                } catch {}
            }
            throw new Error(`LLM ${r.status}, cascade exhausted`);
        } catch (e) { if (e instanceof TypeError && e.message.includes('fetch')) throw new Error('All LLM backends unreachable'); throw e; }
    }

    private static async executeTool(name: string, args: any): Promise<any> {
        try { if (typeof chrome!=='undefined' && chrome.runtime?.sendNativeMessage) return new Promise((res,rej)=>{chrome.runtime.sendNativeMessage('com.foveai.foveai_host',{action:name,...args},(r:any)=>{if(chrome.runtime.lastError) COMAX.httpTool(name,args).then(res).catch(rej);else res(r);});}); } catch {}
        return COMAX.httpTool(name, args);
    }
    private static async httpTool(name: string, args: any): Promise<any> {
        try { const r = await fetch('/api/dev/cline',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tool:name,...args})}); return await r.json(); } catch { return {error:`${name} unavailable`}; }
    }

    private static async execMem(name: string, args: any): Promise<any> {
        const eps: any = { search_memory: ['/api/memory/search','POST',{query:args.query,limit:args.limit||10}], memory_context: ['/api/memory/context?limit=10','GET',null], memory_add: ['/api/memory/add','POST',{role:args.role,content:args.content,source:args.source||'comax'}], memory_import: ['/api/memory/import','POST',{source:args.source||'all'}] };
        const ep = eps[name]; if (!ep) return {error:`Unknown: ${name}`};
        try { const r = await fetch(ep[0],{method:ep[1],headers:{'Content-Type':'application/json'},body:ep[2]?JSON.stringify(ep[2]):undefined}); return await r.json(); } catch { return {error:'Memory unavailable'}; }
    }

    private static async injectMemoryContext(): Promise<string> {
        try { const r = await fetch('/api/memory/context?limit=10'); const d = await r.json(); return d.injection_prompt ? COMAX.baseSystemPrompt+'\n\n'+d.injection_prompt : COMAX.baseSystemPrompt; } catch { return COMAX.baseSystemPrompt; }
    }
}