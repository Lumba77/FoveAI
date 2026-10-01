export class SwarmTab {
    private static canvas: HTMLCanvasElement | null = null;
    private static ctx: CanvasRenderingContext2D | null = null;
    private static drones: any[] = [];
    private static animationFrame: number | null = null;

    public static render(container: HTMLElement) {
        container.innerHTML = `
            <div class="breadcrumb">SWARM ORCHESTRATOR // DRONE_ARENA</div>
            <div style="flex: 1; display: flex; flex-direction: column; gap: 15px; min-height: 0;">
                <div id="swarm-arena" style="flex: 1; background: rgba(0,0,0,0.6); border: 1px solid var(--border); border-radius: 4px; position: relative; overflow: hidden; min-height: 300px;">
                    <canvas id="swarm-canvas" style="width: 100%; height: 100%; display: block;"></canvas>
                    <div style="position: absolute; top: 15px; left: 15px; pointer-events: none;">
                        <div style="font-family: 'Orbitron'; font-size: 0.7rem; color: var(--neon-blue); letter-spacing: 1px;">LIVE SWARM TELEMETRY</div>
                        <div id="swarm-status-text" style="font-family: 'Share Tech Mono'; font-size: 0.6rem; color: rgba(255,255,255,0.5); margin-top: 4px;">Awaiting Mission...</div>
                    </div>
                </div>

                <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 4px; padding: 15px;">
                    <label style="font-family: 'Orbitron'; font-size: 0.6rem; color: var(--neon-blue); display: block; margin-bottom: 8px;">MISSION OBJECTIVE</label>
                    <div style="display: flex; gap: 10px;">
                        <input type="text" id="swarm-mission-input" placeholder="e.g. Audit security in frontend/XR_Vessel..." style="flex: 1; background: rgba(0,0,0,0.4); border: 1px solid var(--border); color: #fff; padding: 10px; border-radius: 4px; font-family: inherit; font-size: 0.8rem; outline: none;">
                        <button id="btn-launch-swarm" class="neon-btn" style="padding: 0 20px; background: var(--neon-blue); color: #000; border: none; border-radius: 4px; font-family: 'Orbitron'; font-size: 0.7rem; font-weight: 700; cursor: pointer; letter-spacing: 1px;">LAUNCH</button>
                    </div>
                    <div id="swarm-launch-log" style="margin-top: 10px; font-family: 'Share Tech Mono'; font-size: 0.7rem; color: var(--neon-pink); min-height: 1.2em;"></div>
                </div>

                <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 4px; padding: 15px; max-height: 200px; overflow-y: auto;">
                    <h4 style="font-family: 'Orbitron'; font-size: 0.7rem; color: var(--neon-blue); margin: 0 0 10px 0;">SWARM LOGS</h4>
                    <div id="swarm-telemetry-log" style="font-family: 'Share Tech Mono'; font-size: 0.65rem; color: rgba(255,255,255,0.7); line-height: 1.6;">
                        No active mission.
                    </div>
                </div>
            </div>
        `;

        this.initCanvas();
        this.setupListeners(container);
    }

    private static initCanvas() {
        this.canvas = document.getElementById('swarm-canvas') as HTMLCanvasElement;
        if (!this.canvas) return;
        this.ctx = this.canvas.getContext('2d');
        
        const resize = () => {
            if (this.canvas) {
                this.canvas.width = this.canvas.clientWidth;
                this.canvas.height = this.canvas.clientHeight;
                this.initDrones();
            }
        };
        
        window.addEventListener('resize', resize);
        resize();
        this.startAnimation();
    }

    private static initDrones() {
        this.drones = [];
        const droneCount = 8;
        for (let i = 0; i < droneCount; i++) {
            this.drones.push({
                x: Math.random() * (this.canvas?.width || 0),
                y: Math.random() * (this.canvas?.height || 0),
                vx: (Math.random() - 0.5) * 2,
                vy: (Math.random() - 0.5) * 2,
                size: 2 + Math.random() * 3,
                color: i === 0 ? '#ff007f' : '#00f3ff' // First drone is Director
            });
        }
    }

    private static startAnimation() {
        if (this.animationFrame) cancelAnimationFrame(this.animationFrame);
        
        const draw = () => {
            if (!this.ctx || !this.canvas) return;
            
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            
            // Draw grid
            this.ctx.strokeStyle = 'rgba(0, 243, 255, 0.05)';
            this.ctx.lineWidth = 1;
            for (let x = 0; x < this.canvas.width; x += 30) {
                this.ctx.beginPath();
                this.ctx.moveTo(x, 0);
                this.ctx.lineTo(x, this.canvas.height);
                this.ctx.stroke();
            }
            for (let y = 0; y < this.canvas.height; y += 30) {
                this.ctx.beginPath();
                this.ctx.moveTo(0, y);
                this.ctx.lineTo(this.canvas.width, y);
                this.ctx.stroke();
            }

            // Draw drones
            this.drones.forEach((d, i) => {
                d.x += d.vx;
                d.y += d.vy;

                if (d.x < 0 || d.x > this.canvas!.width) d.vx *= -1;
                if (d.y < 0 || d.y > this.canvas!.height) d.vy *= -1;

                this.ctx!.fillStyle = d.color;
                this.ctx!.beginPath();
                this.ctx!.arc(d.x, d.y, d.size, 0, Math.PI * 2);
                this.ctx!.fill();

                // Draw links to director
                if (i > 0) {
                    this.ctx!.strokeStyle = 'rgba(0, 243, 255, 0.1)';
                    this.ctx!.beginPath();
                    this.ctx!.moveTo(d.x, d.y);
                    this.ctx!.lineTo(this.drones[0].x, this.drones[0].y);
                    this.ctx!.stroke();
                }
            });

            this.animationFrame = requestAnimationFrame(draw);
        };
        
        draw();
    }

    private static setupListeners(container: HTMLElement) {
        const btnLaunch = container.querySelector('#btn-launch-swarm');
        const input = container.querySelector('#swarm-mission-input') as HTMLInputElement;
        const log = container.querySelector('#swarm-launch-log');
        const telemetry = container.querySelector('#swarm-telemetry-log');
        const statusText = container.querySelector('#swarm-status-text');

        btnLaunch?.addEventListener('click', async () => {
            const mission = input.value.trim();
            if (!mission) return;

            if (log) log.textContent = 'Launching Swarm Drones...';
            if (statusText) statusText.textContent = 'MISSION ACTIVE: ' + mission.substring(0, 20) + '...';

            try {
                const response = await fetch('/api/soul/api/swarm/launch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mission })
                });

                if (response.ok) {
                    const data = await response.json();
                    if (log) log.textContent = 'Swarm deployed successfully. Mission ID: ' + (data.mission_id || 'OK');
                    if (telemetry) telemetry.innerHTML = `<div>[${new Date().toLocaleTimeString()}] DIRECTOR: Assessing objective...</div>`;
                    this.pollSwarmState(telemetry);
                } else {
                    if (log) log.textContent = 'Launch failed: ' + response.status;
                }
            } catch (err) {
                if (log) log.textContent = 'Network error: ' + err;
            }
        });
    }

    private static async pollSwarmState(telemetry: Element | null) {
        const poll = async () => {
            try {
                const response = await fetch('/api/soul/api/swarm/state');
                if (response.ok) {
                    const data = await response.json();
                    if (telemetry && data.logs) {
                        telemetry.innerHTML = data.logs.map((l: string) => `<div>${l}</div>`).join('');
                    }
                }
            } catch (err) {}
        };
        setInterval(poll, 3000);
    }
}
