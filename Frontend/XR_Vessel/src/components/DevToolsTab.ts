/**
 * DevToolsTab — Jen's Self-Development Console
 * Lets Jen assess her own code, view suggestions, and propose updates
 * to the soundboard, API pipeline, and other subsystems.
 * Phase 4: Added FoveAI Cline — browser-native AI coding assistant.
 */

import { COMAX } from './COMAX';

export class DevToolsTab {
    public static currentSection: string = 'overview';
    private static devSuggestions: Array<{ id: string; title: string; status: string; priority: string; description: string }> = [
        { id: 'snd-001', title: 'Soundboard: Refine buffer pipeline', status: 'proposed', priority: 'high', description: 'Reduce latency in audio buffer handoff between Chatterbox TTS and soundboard playback. Current pipeline has ~200ms overhead from chunked encoding.' },
        { id: 'snd-002', title: 'Soundboard: Dynamic sample rate', status: 'proposed', priority: 'medium', description: 'Auto-detect and match sample rates between TTS output and soundboard mixer to avoid resampling artifacts.' },
        { id: 'api-001', title: 'API: Streaming response pipeline', status: 'in-progress', priority: 'high', description: 'Implement proper SSE streaming for Soul API responses. Currently buffered, causing perceived latency on long responses.' },
        { id: 'api-002', title: 'API: Error recovery middleware', status: 'proposed', priority: 'medium', description: 'Add retry logic with exponential backoff for transient LLM provider failures. Currently returns raw error to client.' },
        { id: 'api-003', title: 'API: Request deduplication', status: 'proposed', priority: 'low', description: 'Deduplicate concurrent identical requests to reduce token waste and improve responsiveness during rapid user input.' },
        { id: 'core-001', title: 'Memory: Context window optimization', status: 'proposed', priority: 'medium', description: 'Implement sliding context window with importance scoring to keep relevant history while reducing token count.' },
        { id: 'core-002', title: 'Dashboard: Tab prefetch', status: 'proposed', priority: 'low', description: 'Preload tab content in background when nav item is hovered, reducing perceived latency on tab switch.' },
    ];

    public static render(container: HTMLElement): void {
        container.innerHTML = '';
        container.style.overflow = 'auto';

        const wrapper = document.createElement('div');
        wrapper.style.cssText = 'display: flex; flex-direction: column; gap: 12px; height: 100%;';

        // Header
        const header = document.createElement('div');
        header.style.cssText = 'display: flex; align-items: center; gap: 12px; margin-bottom: 4px;';
        header.innerHTML = `
            <div style="font-size: 1.5rem;">🔧</div>
            <div>
                <div style="font-family: 'Orbitron', sans-serif; font-size: 0.9rem; color: var(--neon-blue); letter-spacing: 2px;">DEVTOOLS // SELF-DEVELOPMENT</div>
                <div style="font-family: 'Share Tech Mono', monospace; font-size: 0.6rem; color: rgba(255,255,255,0.4); margin-top: 2px;">JEN ASSESSMENT & AUGMENTATION CONSOLE v1.0</div>
            </div>
        `;
        wrapper.appendChild(header);

        // Section tabs
        const tabBar = document.createElement('div');
        tabBar.style.cssText = 'display: flex; gap: 2px; border-bottom: 1px solid var(--border); padding-bottom: 6px;';
        const sections = [
            { id: 'overview', label: 'OVERVIEW', icon: '📊' },
            { id: 'suggestions', label: 'SUGGESTIONS', icon: '💡' },
            { id: 'codebase', label: 'CODEBASE', icon: '🗂️' },
            { id: 'pipeline', label: 'PIPELINE', icon: '🔄' },
            { id: 'coder', label: 'J-AIDER', icon: '🤖' },
            { id: 'comax', label: 'COMAX', icon: '⚡' },
            { id: 'actions', label: 'ACTIONS', icon: '⚡' },
        ];
        sections.forEach(sec => {
            const btn = document.createElement('button');
            btn.style.cssText = `
                flex: 1; padding: 6px 4px; border: none; cursor: pointer;
                font-family: 'Orbitron', sans-serif; font-size: 0.55rem; font-weight: 700;
                letter-spacing: 1px; text-transform: uppercase;
                background: ${DevToolsTab.currentSection === sec.id ? 'rgba(0,243,255,0.15)' : 'transparent'};
                color: ${DevToolsTab.currentSection === sec.id ? 'var(--neon-blue)' : 'rgba(255,255,255,0.5)'};
                border-bottom: 2px solid ${DevToolsTab.currentSection === sec.id ? 'var(--neon-blue)' : 'transparent'};
                transition: all 0.2s;
            `;
            btn.textContent = `${sec.icon} ${sec.label}`;
            btn.addEventListener('click', () => {
                DevToolsTab.currentSection = sec.id;
                DevToolsTab.render(container);
            });
            btn.addEventListener('mouseenter', () => {
                if (DevToolsTab.currentSection !== sec.id) {
                    btn.style.background = 'rgba(0,243,255,0.08)';
                    btn.style.color = 'rgba(255,255,255,0.7)';
                }
            });
            btn.addEventListener('mouseleave', () => {
                if (DevToolsTab.currentSection !== sec.id) {
                    btn.style.background = 'transparent';
                    btn.style.color = 'rgba(255,255,255,0.5)';
                }
            });
            tabBar.appendChild(btn);
        });
        wrapper.appendChild(tabBar);

        // Content area
        const content = document.createElement('div');
        content.style.cssText = 'flex: 1; overflow-y: auto; padding-top: 8px;';

        if (DevToolsTab.currentSection === 'overview') {
            content.appendChild(DevToolsTab.renderOverview());
        } else if (DevToolsTab.currentSection === 'suggestions') {
            content.appendChild(DevToolsTab.renderSuggestions());
        } else if (DevToolsTab.currentSection === 'codebase') {
            content.appendChild(DevToolsTab.renderCodebase());
        } else if (DevToolsTab.currentSection === 'pipeline') {
            content.appendChild(DevToolsTab.renderPipeline());
        } else if (DevToolsTab.currentSection === 'coder') {
            content.appendChild(DevToolsTab.renderCoder());
        } else if (DevToolsTab.currentSection === 'comax') {
            COMAX.render(content);
        } else if (DevToolsTab.currentSection === 'actions') {
            content.appendChild(DevToolsTab.renderActions());
        }

        wrapper.appendChild(content);
        container.appendChild(wrapper);
    }

    private static renderOverview(): HTMLElement {
        const div = document.createElement('div');
        const totalSugg = DevToolsTab.devSuggestions.length;
        const highCount = DevToolsTab.devSuggestions.filter(s => s.priority === 'high').length;
        const inProgress = DevToolsTab.devSuggestions.filter(s => s.status === 'in-progress').length;

        div.innerHTML = `
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 16px;">
                <div style="background: rgba(0,243,255,0.06); border: 1px solid var(--border); border-radius: 6px; padding: 14px; text-align: center;">
                    <div style="font-family: 'Orbitron', sans-serif; font-size: 1.8rem; color: var(--neon-blue);">${totalSugg}</div>
                    <div style="font-family: 'Share Tech Mono', monospace; font-size: 0.6rem; color: rgba(255,255,255,0.5); letter-spacing: 1px;">SUGGESTIONS</div>
                </div>
                <div style="background: rgba(255,0,127,0.06); border: 1px solid rgba(255,0,127,0.2); border-radius: 6px; padding: 14px; text-align: center;">
                    <div style="font-family: 'Orbitron', sans-serif; font-size: 1.8rem; color: var(--neon-pink);">${highCount}</div>
                    <div style="font-family: 'Share Tech Mono', monospace; font-size: 0.6rem; color: rgba(255,255,255,0.5); letter-spacing: 1px;">HIGH PRIORITY</div>
                </div>
                <div style="background: rgba(147,51,234,0.06); border: 1px solid rgba(147,51,234,0.2); border-radius: 6px; padding: 14px; text-align: center;">
                    <div style="font-family: 'Orbitron', sans-serif; font-size: 1.8rem; color: #c084fc;">${inProgress}</div>
                    <div style="font-family: 'Share Tech Mono', monospace; font-size: 0.6rem; color: rgba(255,255,255,0.5); letter-spacing: 1px;">IN PROGRESS</div>
                </div>
            </div>
            <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--border); border-radius: 6px; padding: 14px;">
                <div style="font-family: 'Orbitron', sans-serif; font-size: 0.7rem; color: var(--neon-blue); letter-spacing: 1px; margin-bottom: 10px;">SELF-ASSESSMENT STATUS</div>
                <div style="font-family: 'Share Tech Mono', monospace; font-size: 0.75rem; line-height: 1.8; color: rgba(255,255,255,0.7);">
                    <div>🔊 <span style="color: var(--neon-pink);">SOUNDBOARD</span> — Pipeline latency identified (200ms overhead). Buffer handoff optimization proposed.</div>
                    <div>🔌 <span style="color: var(--neon-blue);">API PIPELINE</span> — SSE streaming implementation in progress. Error recovery middleware drafted.</div>
                    <div>🧠 <span style="color: #c084fc;">MEMORY</span> — Context window optimization proposal ready for review.</div>
                    <div>🖥️ <span style="color: var(--neon-green);">DASHBOARD</span> — Tab prefetch mechanism proposed for reduced latency.</div>
                    <div>🌐 <span style="color: var(--neon-blue);">CHROME DEVTOOLS MCP</span> — Active. Browser-automation & WebXR diagnostics ready via AGY.</div>
                    <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border);">
                        <span style="color: var(--neon-green);">✓</span> Self-development module active — Jen can now assess, suggest, and augment her own code.
                    </div>
                </div>
            </div>
        `;
        return div;
    }

    private static renderSuggestions(): HTMLElement {
        const div = document.createElement('div');
        div.innerHTML = `
            <div style="font-family: 'Orbitron', sans-serif; font-size: 0.7rem; color: var(--neon-blue); letter-spacing: 1px; margin-bottom: 10px;">REFINEMENT SUGGESTIONS</div>
        `;

        const priorityColors: Record<string, string> = { high: 'var(--neon-pink)', medium: '#ffaa00', low: 'rgba(255,255,255,0.4)' };
        const statusColors: Record<string, string> = { proposed: 'rgba(255,255,255,0.5)', 'in-progress': 'var(--neon-blue)', done: 'var(--neon-green)' };

        DevToolsTab.devSuggestions.forEach(sugg => {
            const card = document.createElement('div');
            card.style.cssText = `
                background: rgba(0,0,0,0.3); border: 1px solid var(--border); border-radius: 6px;
                padding: 12px; margin-bottom: 8px; cursor: pointer; transition: all 0.2s;
            `;
            card.addEventListener('mouseenter', () => { card.style.borderColor = 'var(--neon-blue)'; card.style.background = 'rgba(0,243,255,0.05)'; });
            card.addEventListener('mouseleave', () => { card.style.borderColor = 'var(--border)'; card.style.background = 'rgba(0,0,0,0.3)'; });

            card.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-family: 'Share Tech Mono', monospace; font-size: 0.6rem; color: rgba(255,255,255,0.4);">${sugg.id}</span>
                        <span style="font-family: 'Orbitron', sans-serif; font-size: 0.7rem; font-weight: 700; color: #fff;">${sugg.title}</span>
                    </div>
                    <div style="display: flex; gap: 6px;">
                        <span style="font-size: 0.55rem; padding: 2px 6px; border-radius: 3px; background: rgba(0,0,0,0.4); color: ${priorityColors[sugg.priority]}; font-family: 'Share Tech Mono', monospace; letter-spacing: 0.5px;">${sugg.priority.toUpperCase()}</span>
                        <span style="font-size: 0.55rem; padding: 2px 6px; border-radius: 3px; background: rgba(0,0,0,0.4); color: ${statusColors[sugg.status]}; font-family: 'Share Tech Mono', monospace; letter-spacing: 0.5px;">${sugg.status.toUpperCase()}</span>
                    </div>
                </div>
                <div style="font-family: 'Share Tech Mono', monospace; font-size: 0.7rem; color: rgba(255,255,255,0.5); line-height: 1.5;">${sugg.description}</div>
            `;
            div.appendChild(card);
        });

        return div;
    }

    private static renderCodebase(): HTMLElement {
        const div = document.createElement('div');
        div.innerHTML = `
            <div style="font-family: 'Orbitron', sans-serif; font-size: 0.7rem; color: var(--neon-blue); letter-spacing: 1px; margin-bottom: 10px;">CODEBASE SELF-ASSESSMENT</div>
            <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--border); border-radius: 6px; padding: 14px; margin-bottom: 10px;">
                <div style="font-family: 'Share Tech Mono', monospace; font-size: 0.7rem; line-height: 1.8; color: rgba(255,255,255,0.7);">
                    <div style="color: var(--neon-blue); margin-bottom: 6px;">// SOUNDBOARD PIPELINE</div>
                    <div>├── Scripts/foveai_soundboard_server.py <span style="color: var(--neon-pink);">← latency bottleneck</span></div>
                    <div>│   └── Chunked encoding → buffer → playback</div>
                    <div>│       └── <span style="color: #ffaa00;">200ms overhead detected</span></div>
                    <div>├── Scripts/generate_soundboard_defaults.py</div>
                    <div>└── Tools/Chatterbox-TTS-Server/</div>
                    <div style="margin-top: 10px; color: var(--neon-blue);">// API PIPELINE</div>
                    <div>├── backend/Soul/soul.py <span style="color: var(--neon-pink);">← SSE streaming needed</span></div>
                    <div>│   └── Response buffering → client delivery</div>
                    <div>├── backend/Soul/api.py</div>
                    <div>└── backend/Soul/middleware.py <span style="color: #ffaa00;">← error recovery needed</span></div>
                    <div style="margin-top: 10px; color: var(--neon-blue);">// DASHBOARD</div>
                    <div>├── XR_Vessel/src/components/Dashboard.ts <span style="color: var(--neon-green);">← this file</span></div>
                    <div>├── XR_Vessel/src/components/ModelHubTab.ts</div>
                    <div>└── XR_Vessel/src/components/DevToolsTab.ts <span style="color: #c084fc;">← new!</span></div>
                </div>
            </div>
            <div style="background: rgba(0,0,0,0.3); border: 1px solid rgba(147,51,234,0.3); border-radius: 6px; padding: 14px;">
                <div style="font-family: 'Orbitron', sans-serif; font-size: 0.6rem; color: #c084fc; letter-spacing: 1px; margin-bottom: 8px;">SELF-MODIFICATION PROTOCOL</div>
                <div style="font-family: 'Share Tech Mono', monospace; font-size: 0.7rem; color: rgba(255,255,255,0.6); line-height: 1.6;">
                    Jen can propose code changes through this console. Suggestions are logged to the memory system and can be reviewed by the operator before deployment. Full write access requires operator confirmation.
                </div>
            </div>
        `;
        return div;
    }

    private static renderPipeline(): HTMLElement {
        const div = document.createElement('div');
        div.innerHTML = `
            <div style="font-family: 'Orbitron', sans-serif; font-size: 0.7rem; color: var(--neon-blue); letter-spacing: 1px; margin-bottom: 10px;">AUDIO & API PIPELINE STATUS</div>
            <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--border); border-radius: 6px; padding: 14px; margin-bottom: 10px;">
                <div style="font-family: 'Orbitron', sans-serif; font-size: 0.6rem; color: var(--neon-pink); letter-spacing: 1px; margin-bottom: 8px;">SOUNDBOARD PIPELINE</div>
                <div style="font-family: 'Share Tech Mono', monospace; font-size: 0.7rem; color: rgba(255,255,255,0.7); line-height: 2;">
                    <div>🎤 Mic Input ──→ Buffer Queue ──→ Soundcard Out</div>
                    <div>🗣️ TTS Request ──→ Chatterbox ──→ <span style="color: var(--neon-pink);">Chunked Encode (200ms lag)</span> ──→ Soundboard ──→ Speaker</div>
                    <div style="margin-top: 6px; color: var(--neon-green);">💡 Proposal: Stream raw PCM directly, skip chunked re-encode</div>
                </div>
            </div>
            <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--border); border-radius: 6px; padding: 14px;">
                <div style="font-family: 'Orbitron', sans-serif; font-size: 0.6rem; color: var(--neon-blue); letter-spacing: 1px; margin-bottom: 8px;">API PIPELINE</div>
                <div style="font-family: 'Share Tech Mono', monospace; font-size: 0.7rem; color: rgba(255,255,255,0.7); line-height: 2;">
                    <div>👤 User Input ──→ Dashboard ──→ Soul API ──→ <span style="color: var(--neon-pink);">Buffered Response</span> ──→ Dashboard</div>
                    <div style="margin-top: 6px; color: var(--neon-green);">💡 Proposal: Switch to SSE streaming for token-by-token delivery</div>
                    <div style="margin-top: 4px; color: #ffaa00;">💡 Proposal: Add retry middleware with exponential backoff</div>
                </div>
            </div>
        `;
        return div;
    }

    private static renderActions(): HTMLElement {
        const div = document.createElement('div');
        div.innerHTML = `
            <div style="font-family: 'Orbitron', sans-serif; font-size: 0.7rem; color: var(--neon-blue); letter-spacing: 1px; margin-bottom: 10px;">ACTIONS & SELF-AUGMENTATION</div>
        `;

        const actions = [
            { label: '🔍 ASSESS SOUNDBOARD', desc: 'Run latency diagnostic on audio pipeline', color: 'var(--neon-pink)' },
            { label: '🔄 ASSESS API PIPELINE', desc: 'Check SSE streaming readiness & error handling', color: 'var(--neon-blue)' },
            { label: '🔌 ACTIVATE CHROME DEVTOOLS MCP', desc: 'Initialize and launch Chrome DevTools MCP server for browser automation & UI testing', color: 'var(--neon-blue)' },
            { label: '📊 RUN DIAGNOSTICS', desc: 'Full system health check across all services', color: '#ffaa00' },
            { label: '💾 EXPORT SUGGESTIONS', desc: 'Export current suggestions to context.md for review', color: '#c084fc' },
            { label: '📝 SELF-REVIEW CODE', desc: 'Trigger Jen to review her own recent code changes', color: 'var(--neon-green)' },
            { label: '🔄 SYNC WITH MEMORY', desc: 'Push current dev state to FoveAI memory system', color: 'rgba(255,255,255,0.7)' },
        ];

        actions.forEach(action => {
            const btn = document.createElement('button');
            btn.style.cssText = `
                display: block; width: 100%; text-align: left; padding: 12px 16px; margin-bottom: 8px;
                background: rgba(0,0,0,0.3); border: 1px solid var(--border); border-radius: 6px;
                cursor: pointer; transition: all 0.2s; color: rgba(255,255,255,0.8);
            `;
            btn.innerHTML = `
                <div style="font-family: 'Orbitron', sans-serif; font-size: 0.65rem; font-weight: 700; color: ${action.color}; letter-spacing: 1px; margin-bottom: 4px;">${action.label}</div>
                <div style="font-family: 'Share Tech Mono', monospace; font-size: 0.65rem; color: rgba(255,255,255,0.4);">${action.desc}</div>
            `;
            btn.addEventListener('mouseenter', () => { btn.style.borderColor = action.color; btn.style.background = 'rgba(0,243,255,0.05)'; });
            btn.addEventListener('mouseleave', () => { btn.style.borderColor = 'var(--border)'; btn.style.background = 'rgba(0,0,0,0.3)'; });
            btn.addEventListener('click', () => {
                const dashboard = (window as any).foveaiDashboard;
                if (dashboard) {
                    dashboard.log(`[DEV] Action triggered: ${action.label}`, action.color);
                    // Navigate to cognition tab with a pre-filled prompt
                    dashboard.setActiveTab('cognition');
                    setTimeout(() => {
                        dashboard.onSendMessage(`[DEVTOOLS] ${action.label}: ${action.desc}. Please assess the current state and provide recommendations.`);
                    }, 300);
                }
            });
            div.appendChild(btn);
        });

        return div;
    }

    private static renderCoder(): HTMLElement {
        const div = document.createElement('div');
        div.style.cssText = 'display: flex; flex-direction: column; gap: 12px; height: 100%; min-height: 0;';

        div.innerHTML = `
            <div style="background: rgba(0,243,255,0.03); border: 1px solid var(--border); border-radius: 6px; padding: 12px;">
                <div style="font-family: 'Orbitron', sans-serif; font-size: 0.75rem; color: var(--neon-blue); letter-spacing: 1px; margin-bottom: 6px;">🤖 J-AIDER CO-DEVELOPER CHANNEL</div>
                <div style="font-family: 'Share Tech Mono', monospace; font-size: 0.7rem; color: rgba(255,255,255,0.6); line-height: 1.5;">
                    Jen is now integrated with the local codebase through the <strong>Aider</strong> co-development agent. 
                    You can ask Jen to search, review, implement new features, or perform complex refactoring tasks directly on the codebase.
                    <br><br>
                    <span style="color: var(--neon-pink);">⚡ Safety Mandate:</span> All J-Aider instructions run with non-interactive flags (<code>--yes</code>, <code>--no-git</code>). 
                    Your files will be modified directly, allowing you to review changes in git before committing.
                </div>
            </div>
            
            <div style="flex: 1; display: flex; flex-direction: column; gap: 8px; min-height: 0;">
                <div style="font-family: 'Orbitron', sans-serif; font-size: 0.6rem; color: rgba(255,255,255,0.4); letter-spacing: 1px;">REAL-TIME EXECUTION LOG</div>
                <div id="aider-console" style="flex: 1; background: #050505; border: 1px solid var(--border); border-radius: 4px; padding: 10px; font-family: 'Share Tech Mono', monospace; font-size: 0.7rem; color: #39ff14; overflow-y: auto; white-space: pre-wrap; box-shadow: inset 0 0 10px rgba(0,0,0,0.8); line-height: 1.4; min-height: 150px;">AIDER AGENT INACTIVE. WAITING FOR DIRECTIVE...</div>
            </div>

            <div style="display: flex; flex-direction: column; gap: 8px;">
                <div style="display: flex; gap: 8px;">
                    <textarea id="aider-prompt" placeholder="Instruct J-Aider (e.g., 'Check src/components/ModelHubTab.ts and add a toggle button to change the default fast model')" style="flex: 1; height: 64px; background: rgba(0,0,0,0.5); border: 1px solid var(--border); border-radius: 4px; padding: 8px; font-family: 'Share Tech Mono', monospace; font-size: 0.75rem; color: #fff; resize: none; outline: none; transition: border-color 0.2s;" onfocus="this.style.borderColor='var(--neon-blue)'" onblur="this.style.borderColor='var(--border)'"></textarea>
                    <button id="btn-aider-submit" style="width: 100px; background: rgba(0,243,255,0.1); border: 1px solid var(--neon-blue); border-radius: 4px; color: #fff; font-family: 'Orbitron', sans-serif; font-size: 0.65rem; font-weight: 700; cursor: pointer; letter-spacing: 1px; transition: all 0.2s; text-transform: uppercase;">
                        DEPLOY<br>AGENT
                    </button>
                </div>
            </div>
        `;

        const submitBtn = div.querySelector('#btn-aider-submit') as HTMLButtonElement;
        const promptInput = div.querySelector('#aider-prompt') as HTMLTextAreaElement;
        const consoleBox = div.querySelector('#aider-console') as HTMLElement;

        if (submitBtn && promptInput && consoleBox) {
            submitBtn.addEventListener('mouseenter', () => {
                submitBtn.style.background = 'rgba(0,243,255,0.2)';
                submitBtn.style.boxShadow = '0 0 8px rgba(0,243,255,0.3)';
            });
            submitBtn.addEventListener('mouseleave', () => {
                submitBtn.style.background = 'rgba(0,243,255,0.1)';
                submitBtn.style.boxShadow = 'none';
            });

            submitBtn.addEventListener('click', async () => {
                const promptText = promptInput.value.trim();
                if (!promptText) return;

                promptInput.value = '';
                promptInput.disabled = true;
                submitBtn.disabled = true;
                submitBtn.style.opacity = '0.5';

                consoleBox.innerHTML = '<span style="color: var(--neon-blue);">[J-Aider] Initializing connection to vessel development proxy...</span>\n';
                consoleBox.scrollTop = consoleBox.scrollHeight;

                try {
                    const response = await fetch('/api/dev/aider', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ prompt: promptText })
                    });

                    if (!response.body) {
                        consoleBox.innerHTML += '<span style="color: var(--neon-pink);">[System Error] Output stream unavailable.</span>\n';
                        promptInput.disabled = false;
                        submitBtn.disabled = false;
                        submitBtn.style.opacity = '1';
                        return;
                    }

                    consoleBox.innerHTML = '';
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder('utf-8');

                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;

                        const chunk = decoder.decode(value, { stream: true });
                        const cleanChunk = chunk.replace(/\\x1B\\[[0-9;]*[a-zA-Z]/g, '');
                        consoleBox.textContent += cleanChunk;
                        consoleBox.scrollTop = consoleBox.scrollHeight;
                    }
                } catch (err) {
                    consoleBox.innerHTML += `\n<span style="color: var(--neon-pink);">[System Error] Dynamic deployment failed: ${err}</span>\n`;
                } finally {
                    promptInput.disabled = false;
                    submitBtn.disabled = false;
                    submitBtn.style.opacity = '1';
                }
            });
        }

        return div;
    }
}

// Register J-Aider Global trigger listener
window.addEventListener('foveai_aider_request', (e: any) => {
    const dashboard = (window as any).foveaiDashboard;
    if (dashboard) {
        dashboard.log(`[J-Aider] Jen dispatched developer action: "${e.detail.instruction}"`, 'var(--neon-blue)');
        // Switch to devtools tab
        dashboard.setActiveTab('devtools');
        
        // Switch sub-section to coder
        DevToolsTab.currentSection = 'coder';
        
        // Wait for DOM update
        setTimeout(() => {
            const contentArea = document.getElementById('tab-content-area');
            if (contentArea) {
                DevToolsTab.render(contentArea);
            }
            
            // Set prompt and trigger execution
            setTimeout(() => {
                const promptInput = document.getElementById('aider-prompt') as HTMLTextAreaElement;
                const submitBtn = document.getElementById('btn-aider-submit') as HTMLButtonElement;
                if (promptInput && submitBtn) {
                    promptInput.value = e.detail.instruction;
                    submitBtn.click();
                }
            }, 100);
        }, 150);
    }
});