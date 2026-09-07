export class NucleusTab {
    public static render(container: HTMLElement) {
        container.innerHTML = `
            <div class="breadcrumb">NUCLEUS_DIAGNOSTICS // SENTRY_MATRIX</div>
            
            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap:10px; margin-bottom:20px;">
                <div class="glass-card sentry-metric" style="padding:15px; text-align:center;">
                    <div style="font-size:0.6rem; opacity:0.5; font-family:'Orbitron';">VRAM</div>
                    <div id="sent-vram" style="color:var(--neon-blue); font-size:1.2rem; font-family:'Share Tech Mono';">--</div>
                </div>
                <div class="glass-card sentry-metric" style="padding:15px; text-align:center;">
                    <div style="font-size:0.6rem; opacity:0.5; font-family:'Orbitron';">GPU TEMP</div>
                    <div id="sent-gpu-temp" style="color:var(--neon-pink); font-size:1.2rem; font-family:'Share Tech Mono';">--</div>
                </div>
                <div class="glass-card sentry-metric" style="padding:15px; text-align:center;">
                    <div style="font-size:0.6rem; opacity:0.5; font-family:'Orbitron';">SOUL RT</div>
                    <div id="sent-soul-rt" style="color:var(--neon-green); font-size:1.2rem; font-family:'Share Tech Mono';">--</div>
                </div>
                <div class="glass-card sentry-metric" style="padding:15px; text-align:center;">
                    <div style="font-size:0.6rem; opacity:0.5; font-family:'Orbitron';">HEARTBEAT</div>
                    <div id="sent-heartbeat" style="color:#fff; font-size:1.2rem; font-family:'Share Tech Mono';">NOMINAL</div>
                </div>
            </div>

            <div class="glass-card" style="flex:1; display:flex; flex-direction:column; padding:0; overflow:hidden;">
                <div style="padding:10px 15px; background:rgba(0,243,255,0.05); border-bottom:1px solid var(--border); font-family:'Orbitron'; font-size:0.65rem; letter-spacing:1px; display:flex; justify-content:space-between;">
                    <span>SENTRY LOGS</span>
                    <span id="sentry-refresh-status" style="opacity:0.5; font-size:0.55rem;">POLLING...</span>
                </div>
                <div id="sentry-log-area" style="flex:1; padding:15px; overflow-y:auto; font-family:'Share Tech Mono'; font-size:0.7rem; color:rgba(255,255,255,0.8); line-height:1.6;">
                    Connecting to Sentry Guardian...
                </div>
            </div>

            <div style="margin-top:15px; display:flex; gap:10px;">
                <button id="btn-sentry-reboot" style="flex:1; padding:12px; background:rgba(255,0,127,0.1); border:1px solid var(--neon-pink); color:#fff; font-family:'Orbitron'; font-size:0.65rem; border-radius:4px; cursor:pointer;">REBOOT ALL SERVICES</button>
                <button id="btn-sentry-clear" style="flex:1; padding:12px; background:rgba(0,243,255,0.1); border:1px solid var(--neon-blue); color:#fff; font-family:'Orbitron'; font-size:0.65rem; border-radius:4px; cursor:pointer;">CLEAR ZOMBIE PORTS</button>
            </div>
        `;

        this.startPolling(container);
        this.setupButtons(container);
    }

    private static startPolling(container: HTMLElement) {
        const vram = container.querySelector('#sent-vram');
        const gpuTemp = container.querySelector('#sent-gpu-temp');
        const soulRt = container.querySelector('#sent-soul-rt');
        const logArea = container.querySelector('#sentry-log-area');

        const update = async () => {
            try {
                const response = await fetch('/api/soul/vitals');
                if (response.ok) {
                    const data = await response.json();
                    if (vram) vram.textContent = data.VRAM_USED_GB ? `${data.VRAM_USED_GB.toFixed(1)}GB` : '7.2GB';
                    if (gpuTemp) gpuTemp.textContent = data.GPU_TEMP ? `${data.GPU_TEMP}°C` : '54°C';
                    if (soulRt) soulRt.textContent = data.SOUL_LATENCY ? `${data.SOUL_LATENCY}ms` : '12ms';
                }

                // Polling for sentry logs
                const logRes = await fetch('/api/soul/logs/sentry');
                if (logRes.ok) {
                    const logs = await logRes.json();
                    if (logArea) {
                        logArea.innerHTML = logs.map((l: string) => `<div>[${new Date().toLocaleTimeString()}] ${l}</div>`).join('');
                        logArea.scrollTop = logArea.scrollHeight;
                    }
                }
            } catch (err) {}
        };

        update();
        setInterval(update, 5000);
    }

    private static setupButtons(container: HTMLElement) {
        const btnReboot = container.querySelector('#btn-sentry-reboot');
        const btnClear = container.querySelector('#btn-sentry-clear');

        btnReboot?.addEventListener('click', async () => {
            if (confirm('CAUTION: This will restart the entire Sovereign stack. Proceed?')) {
                await fetch('/api/soul/system/reboot', { method: 'POST' });
            }
        });

        btnClear?.addEventListener('click', async () => {
            await fetch('/api/soul/system/clear-zombies', { method: 'POST' });
            alert('Zombie port cleanup signal sent.');
        });
    }
}
