// EnvironmentMappingTab.ts — User Environment Mapping Panel
// Controls room scanning, spatial plaster, and environment awareness

export class EnvironmentMappingTab {
    private static scanActive = false;
    private static scanInterval: number | null = null;

    public static render(container: HTMLElement) {
        container.innerHTML = `
            <div class="breadcrumb">ENVIRONMENT MAPPING // SPATIAL_AWARENESS</div>
            <div style="background:rgba(0,0,0,0.4); padding:20px; border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                    <h4 style="font-family:'Orbitron'; margin:0; font-size:0.9rem; color:var(--neon-blue); letter-spacing:2px;">ROOM SCANNER</h4>
                    <span id="envmap-status" style="font-size:0.7rem; color:var(--neon-green); font-family:'Share Tech Mono';">IDLE</span>
                </div>

                <!-- Scan Controls -->
                <div style="background:rgba(0,243,255,0.08); border:1px solid var(--neon-blue); border-radius:4px; padding:12px; margin-bottom:15px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">SCAN CONTROLS</h5>
                    <div style="display:flex; gap:8px; flex-wrap:wrap;">
                        <button id="btn-start-scan" style="background:rgba(0,243,255,0.15); border:1px solid var(--neon-blue); color:var(--neon-blue); padding:6px 14px; border-radius:3px; cursor:pointer; font-family:'Orbitron'; font-size:0.65rem; letter-spacing:1px;">▶ START SCAN</button>
                        <button id="btn-stop-scan" style="background:rgba(255,0,127,0.1); border:1px solid var(--neon-pink); color:var(--neon-pink); padding:6px 14px; border-radius:3px; cursor:pointer; font-family:'Orbitron'; font-size:0.65rem; letter-spacing:1px;">■ STOP SCAN</button>
                        <button id="btn-reset-map" style="background:rgba(255,255,0,0.1); border:1px solid #ff0; color:#ff0; padding:6px 14px; border-radius:3px; cursor:pointer; font-family:'Orbitron'; font-size:0.65rem; letter-spacing:1px;">⟲ RESET MAP</button>
                    </div>
                </div>

                <!-- Scan Progress -->
                <div style="background:rgba(0,0,0,0.3); border:1px solid var(--border); border-radius:4px; padding:12px; margin-bottom:15px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">SCAN PROGRESS</h5>
                    <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">
                        <div style="flex:1; height:8px; background:rgba(0,0,0,0.5); border-radius:4px; overflow:hidden;">
                            <div id="scan-progress-bar" style="width:0%; height:100%; background:linear-gradient(90deg, var(--neon-blue), var(--neon-green)); transition:width 0.5s;"></div>
                        </div>
                        <span id="scan-progress-text" style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#aaa;">0%</span>
                    </div>
                    <div id="scan-coverage" style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#888;">
                        <div>Walls: <span id="scan-walls">—</span></div>
                        <div>Floor: <span id="scan-floor">—</span></div>
                        <div>Ceiling: <span id="scan-ceiling">—</span></div>
                        <div>Objects: <span id="scan-objects">—</span></div>
                    </div>
                </div>

                <!-- Spatial Status -->
                <div style="background:rgba(57,255,20,0.05); border:1px solid #39ff14; border-radius:4px; padding:12px; margin-bottom:15px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:#39ff14; letter-spacing:1px;">SPATIAL AWARENESS</h5>
                    <div id="spatial-status" style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#aaa; line-height:1.6;">
                        <div>Room: <span id="spatial-room">Not detected</span></div>
                        <div>Meshes: <span id="spatial-meshes">0</span></div>
                        <div>Last Update: <span id="spatial-update">—</span></div>
                        <div>Plaster Quality: <span id="spatial-plaster">—</span></div>
                    </div>
                </div>

                <!-- Coaching Log -->
                <div style="background:rgba(0,0,0,0.3); border:1px solid var(--border); border-radius:4px; padding:12px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">COACHING LOG</h5>
                    <div id="coaching-log" style="font-family:'Share Tech Mono'; font-size:0.65rem; color:#666; max-height:120px; overflow-y:auto; line-height:1.5;">
                        <div>— Awaiting scan —</div>
                    </div>
                </div>
            </div>
        `;
        this.setupInteractions(container);
        this.refreshStatus();
    }

    private static setupInteractions(container: HTMLElement) {
        const btnStart = container.querySelector('#btn-start-scan');
        const btnStop = container.querySelector('#btn-stop-scan');
        const btnReset = container.querySelector('#btn-reset-map');

        btnStart?.addEventListener('click', () => this.startScan());
        btnStop?.addEventListener('click', () => this.stopScan());
        btnReset?.addEventListener('click', () => this.resetMap());
    }

    private static async startScan() {
        const statusEl = document.getElementById('envmap-status');
        if (statusEl) {
            statusEl.textContent = 'SCANNING...';
            statusEl.style.color = '#ff0';
        }
        this.scanActive = true;

        try {
            const resp = await fetch('/api/spatial/scan/start', { method: 'POST' });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const result = await resp.json();
            console.log('[EnvMap] Scan started:', result);
            if (statusEl) {
                statusEl.textContent = 'ACTIVE';
                statusEl.style.color = 'var(--neon-green)';
            }
            // Start polling progress
            this.startProgressPolling();
        } catch (err) {
            console.error('[EnvMap] Failed to start scan:', err);
            if (statusEl) {
                statusEl.textContent = 'FAILED';
                statusEl.style.color = 'var(--neon-pink)';
            }
            this.scanActive = false;
        }
    }

    private static async stopScan() {
        const statusEl = document.getElementById('envmap-status');
        if (statusEl) {
            statusEl.textContent = 'STOPPING...';
            statusEl.style.color = '#ff0';
        }
        this.scanActive = false;

        if (this.scanInterval) {
            clearInterval(this.scanInterval);
            this.scanInterval = null;
        }

        try {
            const resp = await fetch('/api/spatial/scan/stop', { method: 'POST' });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const result = await resp.json();
            console.log('[EnvMap] Scan stopped:', result);
            if (statusEl) {
                statusEl.textContent = 'IDLE';
                statusEl.style.color = '#888';
            }
        } catch (err) {
            console.error('[EnvMap] Failed to stop scan:', err);
            if (statusEl) {
                statusEl.textContent = 'ERROR';
                statusEl.style.color = 'var(--neon-pink)';
            }
        }
    }

    private static async resetMap() {
        const statusEl = document.getElementById('envmap-status');
        if (statusEl) {
            statusEl.textContent = 'RESETTING...';
            statusEl.style.color = '#ff0';
        }

        try {
            const resp = await fetch('/api/spatial/map/reset', { method: 'POST' });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const result = await resp.json();
            console.log('[EnvMap] Map reset:', result);
            if (statusEl) {
                statusEl.textContent = 'RESET';
                statusEl.style.color = '#ff0';
            }
            this.refreshStatus();
        } catch (err) {
            console.error('[EnvMap] Failed to reset map:', err);
            if (statusEl) {
                statusEl.textContent = 'ERROR';
                statusEl.style.color = 'var(--neon-pink)';
            }
        }
    }

    private static startProgressPolling() {
        if (this.scanInterval) clearInterval(this.scanInterval);
        this.scanInterval = window.setInterval(() => this.refreshStatus(), 2000);
    }

    private static async refreshStatus() {
        try {
            const resp = await fetch('/api/spatial/status');
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();

            // Update progress bar
            const progressBar = document.getElementById('scan-progress-bar');
            const progressText = document.getElementById('scan-progress-text');
            const pct = data.progress || 0;
            if (progressBar) progressBar.style.width = `${pct}%`;
            if (progressText) progressText.textContent = `${pct}%`;

            // Update coverage
            const setText = (id: string, val: string) => {
                const el = document.getElementById(id);
                if (el) el.textContent = val;
            };
            setText('scan-walls', data.walls ? `${data.walls}%` : '—');
            setText('scan-floor', data.floor ? `${data.floor}%` : '—');
            setText('scan-ceiling', data.ceiling ? `${data.ceiling}%` : '—');
            setText('scan-objects', data.objects || '—');

            // Update spatial status
            setText('spatial-room', data.room || 'Not detected');
            setText('spatial-meshes', String(data.meshes || 0));
            setText('spatial-update', data.lastUpdate || '—');
            setText('spatial-plaster', data.plasterQuality || '—');

            // Update coaching log
            const logEl = document.getElementById('coaching-log');
            if (logEl && data.coaching) {
                logEl.innerHTML = data.coaching.map((msg: string) => `<div>${msg}</div>`).join('');
            }
        } catch (err) {
            // Silently fail — backend may not be available
            console.debug('[EnvMap] Status refresh failed (expected if backend offline):', err);
        }
    }
}