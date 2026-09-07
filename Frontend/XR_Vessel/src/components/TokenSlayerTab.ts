/**
 * Foveated Memory & TokenSlayer Tab — WebUI Operations tab for Port 8200 Foveated Memory & XRL Context.
 * Embedded live Graph Test & active memory status dashboard.
 */
export class TokenSlayerTab {
    private static pollInterval: ReturnType<typeof setInterval> | null = null;
    private static container: HTMLElement | null = null;

    public static async render(container: HTMLElement): Promise<void> {
        TokenSlayerTab.container = container;
        container.innerHTML = TokenSlayerTab.buildHTML();
        TokenSlayerTab.setupInteractions(container);
        await TokenSlayerTab.fetchStats();
        // Poll every 10s
        if (TokenSlayerTab.pollInterval) clearInterval(TokenSlayerTab.pollInterval);
        TokenSlayerTab.pollInterval = setInterval(() => TokenSlayerTab.fetchStats(), 10000);
    }

    public static destroy(): void {
        if (TokenSlayerTab.pollInterval) {
            clearInterval(TokenSlayerTab.pollInterval);
            TokenSlayerTab.pollInterval = null;
        }
        TokenSlayerTab.container = null;
    }

    private static buildHTML(): string {
        const host = window.location.hostname || '127.0.0.1';
        return `
            <div class="ts-tab" style="display:flex; flex-direction:column; height:100%; padding:12px; gap:12px; box-sizing:border-box;">
                <div class="breadcrumb" style="font-family:'Share Tech Mono',monospace; font-size:0.65rem; color:var(--neon-blue); letter-spacing:1px; flex-shrink:0;">
                    FOVEATED MEMORY & TOKENSLAYER // CENTRAL_PROXY_PORT_8200
                </div>

                <!-- Live Proxy Status Strip -->
                <div class="glass-card" style="padding:10px 14px; display:flex; justify-content:space-between; align-items:center; flex-shrink:0; font-family:'Share Tech Mono',monospace; font-size:0.7rem;">
                    <div>
                        <span style="color:#8b949e;">PROXY STATUS:</span>
                        <span id="fm-status-badge" style="color:#3fb950; font-weight:700; margin-left:6px;">Checking…</span>
                    </div>
                    <div>
                        <span style="color:#8b949e;">MEMORIES STORED:</span>
                        <span id="fm-stored-count" style="color:#00f3ff; font-weight:700; margin-left:6px;">—</span>
                    </div>
                    <div>
                        <button id="fm-btn-open-settings" class="btn btn-dev" style="padding:4px 10px; font-size:0.6rem; background:rgba(0,243,255,0.15); border:1px solid #00f3ff; color:#00f3ff; border-radius:3px; cursor:pointer;">
                            ⚙️ OPEN SETTINGS PANEL
                        </button>
                    </div>
                </div>

                <!-- Embedded XRL Memory Graph & Dashboard -->
                <div style="flex:1; min-height:0; display:flex; flex-direction:column; border:1px solid var(--border); border-radius:6px; overflow:hidden;">
                    <iframe src="http://${host}:8401/graphtest.html" style="width:100%; height:100%; border:none; background:#0d1117;" sandbox="allow-scripts allow-same-origin allow-popups allow-forms"></iframe>
                </div>
            </div>
        `;
    }

    private static setupInteractions(container: HTMLElement): void {
        const host = window.location.hostname || '127.0.0.1';
        container.querySelector('#fm-btn-open-settings')?.addEventListener('click', () => {
            window.open(`http://${host}:8401/memory/settings.html`, '_blank');
        });
    }

    private static async fetchStats(): Promise<void> {
        const host = window.location.hostname || '127.0.0.1';
        try {
            const resp = await fetch(`http://${host}:8400/health`, { signal: AbortSignal.timeout(3000) });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            
            const badge = TokenSlayerTab.container?.querySelector('#fm-status-badge');
            const count = TokenSlayerTab.container?.querySelector('#fm-status-badge');
            const countEl = TokenSlayerTab.container?.querySelector('#fm-stored-count');
            
            if (badge) {
                badge.textContent = `🟢 ONLINE (${data.mode || 'Active'})`;
                (badge as HTMLElement).style.color = '#3fb950';
            }
            if (countEl) {
                countEl.textContent = String(data.stored_messages ?? data.memories ?? 'Active');
            }
        } catch {
            const badge = TokenSlayerTab.container?.querySelector('#fm-status-badge');
            if (badge) {
                badge.textContent = '🔴 PROXY OFFLINE (Port 8200)';
                (badge as HTMLElement).style.color = '#ff007f';
            }
        }
    }
}