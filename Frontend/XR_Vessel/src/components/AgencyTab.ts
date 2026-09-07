import { agentBridge } from '../network/AgentBridge';
import type { AgentStatus } from '../network/AgentBridge';

export class AgencyTab {
    private static statusUnsub: (() => void) | null = null;
    private static activityInterval: ReturnType<typeof setInterval> | null = null;

    public static render(container: HTMLElement) {
        const doubleGripSteering = localStorage.getItem('foveai_double_grip_steering') !== 'false';
        const doubleTriggerHaptics = localStorage.getItem('foveai_double_trigger_haptics') !== 'false';

        container.innerHTML = `
            <div class="breadcrumb">KINETIC AGENCY (AUTONOMOUS BEHAVIOR)</div>
            <p style="font-size:0.75rem; opacity:0.7; margin-bottom:20px; color:var(--neon-blue);">
                Configure autonomous behavior patterns and physical engagement protocols within the WebXR Vessel.
            </p>

            <!-- MASTER CONTROL ROW -->
            <div class="glass-card" style="padding: 20px; background:rgba(0,0,0,0.4); border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); margin-bottom:25px;">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:15px;">
                    <div style="display:flex; align-items:center; gap:15px;">
                        <h4 style="font-family:'Orbitron'; margin:0; font-size:0.9rem; color:var(--neon-blue); letter-spacing:2px;">AGENT LOOP</h4>
                        <span id="agent-loop-status" style="font-family:'Share Tech Mono'; font-size:0.85rem; color:var(--neon-pink);">● OFFLINE</span>
                    </div>
                    <div style="display:flex; gap:10px; align-items:center;">
                        <button id="btn-agent-start" class="agent-ctrl-btn start-btn" style="
                            padding:10px 20px; background:rgba(57,255,20,0.15); border:1px solid var(--neon-green);
                            color:var(--neon-green); font-family:'Orbitron'; font-size:0.75rem; cursor:pointer;
                            border-radius:4px; letter-spacing:1px; transition:all 0.2s;
                        ">▶ START</button>
                        <button id="btn-agent-stop" class="agent-ctrl-btn stop-btn" style="
                            padding:10px 20px; background:rgba(255,0,127,0.15); border:1px solid var(--neon-pink);
                            color:var(--neon-pink); font-family:'Orbitron'; font-size:0.75rem; cursor:pointer;
                            border-radius:4px; letter-spacing:1px; transition:all 0.2s;
                        ">■ STOP</button>
                    </div>
                </div>
                <div id="agent-loop-info" style="margin-top:12px; font-family:'Share Tech Mono'; font-size:0.7rem; color:rgba(255,255,255,0.5);">
                    Loops: — | Uptime: — | Queue: —
                </div>
            </div>

            <div style="display:flex; gap:20px; flex-wrap:wrap; margin-bottom:25px;">
                <!-- Left: Toggles -->
                <div class="glass-card" style="flex: 1; padding: 20px; background:rgba(0,0,0,0.4); border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
                    <h4 style="font-family:'Orbitron'; margin:0 0 20px 0; font-size:0.9rem; color:var(--neon-blue); letter-spacing:2px;">PRIMARY DRIVES</h4>

                    <div style="display:flex; justify-content:space-between; align-items:center; padding:15px; background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.1); border-radius:4px; margin-bottom:15px;">
                        <span style="font-family:'Share Tech Mono'; font-size:0.85rem; color:#fff;">AUTONOMOUS_LOCOMOTION</span>
                        <input type="checkbox" id="check-locomotion" checked style="width:20px; height:20px; accent-color:var(--neon-blue); cursor:pointer;">
                    </div>

                    <div style="display:flex; justify-content:space-between; align-items:center; padding:15px; background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.1); border-radius:4px; margin-bottom:15px;">
                        <span style="font-family:'Share Tech Mono'; font-size:0.85rem; color:#fff;">PROACTIVE_ENGAGEMENT</span>
                        <input type="checkbox" id="check-proactive" style="width:20px; height:20px; accent-color:var(--neon-blue); cursor:pointer;">
                    </div>

                    <div style="display:flex; justify-content:space-between; align-items:center; padding:15px; background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.1); border-radius:4px; margin-bottom:15px;">
                        <span style="font-family:'Share Tech Mono'; font-size:0.85rem; color:#fff;">ENVIRONMENTAL_AWARENESS</span>
                        <input type="checkbox" id="check-awareness" checked style="width:20px; height:20px; accent-color:var(--neon-blue); cursor:pointer;">
                    </div>

                    <div style="display:flex; justify-content:space-between; align-items:center; padding:15px; background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.1); border-radius:4px; margin-bottom:15px;">
                        <span style="font-family:'Share Tech Mono'; font-size:0.85rem; color:#fff; line-height:1.3; margin-right:10px;">double grip = activate Avatar steering as 3rd person game</span>
                        <input type="checkbox" id="check-double-grip-steering" ${doubleGripSteering ? 'checked' : ''} style="width:20px; height:20px; accent-color:var(--neon-blue); cursor:pointer;">
                    </div>

                    <div style="display:flex; justify-content:space-between; align-items:center; padding:15px; background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.1); border-radius:4px;">
                        <span style="font-family:'Share Tech Mono'; font-size:0.85rem; color:#fff; line-height:1.3; margin-right:10px;">double trigger = activate haptic wand mode</span>
                        <input type="checkbox" id="check-double-trigger-haptics" ${doubleTriggerHaptics ? 'checked' : ''} style="width:20px; height:20px; accent-color:var(--neon-blue); cursor:pointer;">
                    </div>
                </div>

                <!-- Right: Status + Safety Panel -->
                <div class="glass-card" style="flex: 1; padding: 20px; background:rgba(0,0,0,0.4); border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
                    <h4 style="font-family:'Orbitron'; margin:0 0 20px 0; font-size:0.9rem; color:var(--neon-blue); letter-spacing:2px;">AGENCY STATUS</h4>

                    <div style="background:rgba(0,0,0,0.3); border:1px solid var(--neon-blue); padding:20px; border-radius:4px; font-family:'Share Tech Mono'; font-size:0.8rem; line-height:2;">
                        <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
                            <strong style="color:var(--neon-blue);">LOCOMOTION:</strong>
                            <span id="status-loco" style="color:var(--neon-green);">ACTIVE</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; margin-bottom:10px;">
                            <strong style="color:var(--neon-blue);">ENGAGEMENT:</strong>
                            <span id="status-pro" style="color:var(--neon-pink);">STANDBY</span>
                        </div>
                        <div style="display:flex; justify-content:space-between;">
                            <strong style="color:var(--neon-blue);">AWARENESS:</strong>
                            <span id="status-env" style="color:var(--neon-green);">ACTIVE</span>
                        </div>
                    </div>

                    <!-- Safety Brake Gauges -->
                    <div id="safety-gauges" style="margin-top:20px;">
                        <h5 style="font-family:'Orbitron'; margin:0 0 12px 0; font-size:0.7rem; color:var(--neon-blue); letter-spacing:1px;">SAFETY MONITOR</h5>
                        <div style="display:flex; gap:10px; flex-wrap:wrap;">
                            <div class="safety-gauge" id="gauge-cpu" style="flex:1; min-width:60px; text-align:center;">
                                <div style="font-size:0.6rem; opacity:0.6; margin-bottom:4px;">CPU</div>
                                <div style="background:rgba(0,0,0,0.5); height:8px; border-radius:4px; overflow:hidden;">
                                    <div id="gauge-cpu-fill" style="height:100%; width:0%; background:var(--neon-green); border-radius:4px; transition:width 0.5s;"></div>
                                </div>
                                <div id="gauge-cpu-val" style="font-size:0.65rem; margin-top:4px;">—%</div>
                            </div>
                            <div class="safety-gauge" id="gauge-ram" style="flex:1; min-width:60px; text-align:center;">
                                <div style="font-size:0.6rem; opacity:0.6; margin-bottom:4px;">RAM</div>
                                <div style="background:rgba(0,0,0,0.5); height:8px; border-radius:4px; overflow:hidden;">
                                    <div id="gauge-ram-fill" style="height:100%; width:0%; background:var(--neon-green); border-radius:4px; transition:width 0.5s;"></div>
                                </div>
                                <div id="gauge-ram-val" style="font-size:0.65rem; margin-top:4px;">—%</div>
                            </div>
                            <div class="safety-gauge" id="gauge-errors" style="flex:1; min-width:60px; text-align:center;">
                                <div style="font-size:0.6rem; opacity:0.6; margin-bottom:4px;">ERRS</div>
                                <div style="background:rgba(0,0,0,0.5); height:8px; border-radius:4px; overflow:hidden;">
                                    <div id="gauge-errors-fill" style="height:100%; width:0%; background:var(--neon-green); border-radius:4px; transition:width 0.5s;"></div>
                                </div>
                                <div id="gauge-errors-val" style="font-size:0.65rem; margin-top:4px;">—</div>
                            </div>
                            <div class="safety-gauge" id="gauge-loops" style="flex:1; min-width:60px; text-align:center;">
                                <div style="font-size:0.6rem; opacity:0.6; margin-bottom:4px;">LOOPS</div>
                                <div style="background:rgba(0,0,0,0.5); height:8px; border-radius:4px; overflow:hidden;">
                                    <div id="gauge-loops-fill" style="height:100%; width:0%; background:var(--neon-green); border-radius:4px; transition:width 0.5s;"></div>
                                </div>
                                <div id="gauge-loops-val" style="font-size:0.65rem; margin-top:4px;">—</div>
                            </div>
                        </div>
                        <div id="safety-brake-warning" style="display:none; margin-top:10px; padding:8px 12px; background:rgba(255,0,127,0.2); border:1px solid var(--neon-pink); border-radius:4px; font-family:'Share Tech Mono'; font-size:0.7rem; color:var(--neon-pink);">
                            ⚠ BRAKE ENGAGED
                        </div>
                    </div>

                    <div style="margin-top:20px; font-size:0.7rem; color:rgba(255,255,255,0.5); font-family:'Inter'; font-style:italic;">
                        * Note: Disabling locomotion will override [MOVE_TO] outputs from the AI Brain. Proactive engagement requires microphone permissions for silent audio-triggering.
                    </div>
                </div>
            </div>

            <!-- Persona, Domain and Mode Selection -->
            <div class="glass-card" style="padding: 20px; background:rgba(0,0,0,0.4); border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); margin-bottom:25px;">
                <h4 style="font-family:'Orbitron'; margin:0 0 20px 0; font-size:0.9rem; color:var(--neon-blue); letter-spacing:2px;">PERSONA & DOMAIN</h4>
                <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                    <div style="flex: 1; min-width: 200px;">
                        <label style="font-family:'Share Tech Mono'; font-size:0.8rem; color:var(--neon-blue); display:block; margin-bottom:8px;">ACTIVE PERSONA</label>
                        <select id="select-persona" style="width:100%; background:#02050a; color:#fff; border:1px solid var(--border); padding:8px; font-family:'Share Tech Mono'; font-size:0.85rem; border-radius:4px; outline:none; cursor:pointer;">
                            <option value="foveai">FoveAI (Default)</option>
                            <option value="librarian">Librarian of Truth</option>
                            <option value="painter">Creative Painter</option>
                            <option value="coder">Expert Coder</option>
                            <option value="support">Emotional Support</option>
                            <option value="teacher">Enthusiastic Teacher</option>
                        </select>
                    </div>
                    <div style="flex: 1; min-width: 200px;">
                        <label style="font-family:'Share Tech Mono'; font-size:0.8rem; color:var(--neon-blue); display:block; margin-bottom:8px;">ACTIVE KNOWLEDGE DOMAIN</label>
                        <select id="select-domain" style="width:100%; background:#02050a; color:#fff; border:1px solid var(--border); padding:8px; font-family:'Share Tech Mono'; font-size:0.85rem; border-radius:4px; outline:none; cursor:pointer;">
                            <option value="co_presence">Co-Presence (General)</option>
                            <option value="build_run">Build & Run (Development)</option>
                            <option value="world_feed">World Feed (Operations)</option>
                            <option value="wonder_mind">Wonder Mind (Creativity)</option>
                            <option value="play_fiction">Play Fiction (Worldbuilding)</option>
                            <option value="guard_care">Guard & Care (Relational)</option>
                        </select>
                    </div>
                    <div style="flex: 1; min-width: 200px;">
                        <label style="font-family:'Share Tech Mono'; font-size:0.8rem; color:var(--neon-blue); display:block; margin-bottom:8px;">AGENT MODE</label>
                        <select id="select-agent-mode" style="width:100%; background:#02050a; color:#fff; border:1px solid var(--border); padding:8px; font-family:'Share Tech Mono'; font-size:0.85rem; border-radius:4px; outline:none; cursor:pointer;">
                            <option value="companion">Companion (Default)</option>
                            <option value="developer">Developer (Full Access)</option>
                            <option value="off">Off (Manual Only)</option>
                        </select>
                    </div>
                </div>
            </div>

            <!-- Activity Feed -->
            <div class="glass-card" style="padding: 20px; background:rgba(0,0,0,0.4); border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                    <h4 style="font-family:'Orbitron'; margin:0; font-size:0.9rem; color:var(--neon-blue); letter-spacing:2px;">LIVE ACTIVITY</h4>
                    <button id="btn-refresh-activity" style="
                        padding:6px 14px; background:rgba(0,243,255,0.1); border:1px solid var(--neon-blue);
                        color:var(--neon-blue); font-family:'Share Tech Mono'; font-size:0.65rem; cursor:pointer;
                        border-radius:4px; transition:all 0.2s;
                    ">↻ REFRESH</button>
                </div>
                <div id="activity-feed" style="
                    max-height:300px; overflow-y:auto; font-family:'Share Tech Mono'; font-size:0.7rem;
                    background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.1); border-radius:4px; padding:12px;
                ">
                    <div style="opacity:0.5; text-align:center; padding:20px;">Agent offline — start the loop to see activity</div>
                </div>
            </div>
        `;

        this.bindEvents(container);
        this.fetchAndPopulateDNA(container);
        this.startStatusPolling(container);
        this.loadActivityFeed(container);
    }

    public static destroy() {
        if (this.statusUnsub) {
            this.statusUnsub();
            this.statusUnsub = null;
        }
        if (this.activityInterval) {
            clearInterval(this.activityInterval);
            this.activityInterval = null;
        }
    }

    private static bindEvents(container: HTMLElement) {
        const toggleLoco = container.querySelector('#check-locomotion') as HTMLInputElement;
        const togglePro = container.querySelector('#check-proactive') as HTMLInputElement;
        const toggleEnv = container.querySelector('#check-awareness') as HTMLInputElement;
        const toggleSteer = container.querySelector('#check-double-grip-steering') as HTMLInputElement;
        const toggleHaptics = container.querySelector('#check-double-trigger-haptics') as HTMLInputElement;

        const statLoco = container.querySelector('#status-loco') as HTMLElement;
        const statPro = container.querySelector('#status-pro') as HTMLElement;
        const statEnv = container.querySelector('#status-env') as HTMLElement;

        const updateStatus = (toggle: HTMLInputElement, stat: HTMLElement) => {
            if (toggle.checked) {
                stat.innerText = "ACTIVE";
                stat.style.color = "var(--neon-green)";
            } else {
                stat.innerText = "STANDBY";
                stat.style.color = "var(--neon-pink)";
            }

            // Persist drive config to agent memory
            const driveConfig = {
                locomotion: toggleLoco.checked,
                proactive: togglePro.checked,
                awareness: toggleEnv.checked,
            };
            agentBridge.setMemory('primary_drives', driveConfig).catch(() => {});

            window.dispatchEvent(new CustomEvent('foveai_agency_update', {
                detail: driveConfig
            }));
        };

        toggleLoco?.addEventListener('change', () => updateStatus(toggleLoco, statLoco));
        togglePro?.addEventListener('change', () => updateStatus(togglePro, statPro));
        toggleEnv?.addEventListener('change', () => updateStatus(toggleEnv, statEnv));

        toggleSteer?.addEventListener('change', () => {
            localStorage.setItem('foveai_double_grip_steering', toggleSteer.checked ? 'true' : 'false');
            (window as any).doubleGripSteering = toggleSteer.checked;
            window.dispatchEvent(new CustomEvent('foveai_double_grip_steering_change', {
                detail: { enabled: toggleSteer.checked }
            }));
        });

        toggleHaptics?.addEventListener('change', () => {
            localStorage.setItem('foveai_double_trigger_haptics', toggleHaptics.checked ? 'true' : 'false');
            (window as any).doubleTriggerHaptics = toggleHaptics.checked;
            window.dispatchEvent(new CustomEvent('foveai_double_trigger_haptics_change', {
                detail: { enabled: toggleHaptics.checked }
            }));
        });

        (window as any).doubleGripSteering = toggleSteer ? toggleSteer.checked : (localStorage.getItem('foveai_double_grip_steering') !== 'false');
        (window as any).doubleTriggerHaptics = toggleHaptics ? toggleHaptics.checked : (localStorage.getItem('foveai_double_trigger_haptics') !== 'false');

        // ── Master Control Buttons ────────────────────────────
        const btnStart = container.querySelector('#btn-agent-start') as HTMLButtonElement;
        const btnStop = container.querySelector('#btn-agent-stop') as HTMLButtonElement;

        btnStart?.addEventListener('click', async () => {
            btnStart.disabled = true;
            btnStart.style.opacity = '0.5';
            try {
                const result = await agentBridge.start();
                (window as any).log?.(`[AGENCY] ${result.message}`, '#39ff14');
            } catch (err) {
                (window as any).log?.(`[AGENCY] Start failed: ${err}`, '#ff007f');
            } finally {
                btnStart.disabled = false;
                btnStart.style.opacity = '1';
            }
        });

        btnStop?.addEventListener('click', async () => {
            btnStop.disabled = true;
            btnStop.style.opacity = '0.5';
            try {
                const result = await agentBridge.stop();
                (window as any).log?.(`[AGENCY] ${result.message}`, '#ff007f');
            } catch (err) {
                (window as any).log?.(`[AGENCY] Stop failed: ${err}`, '#ff007f');
            } finally {
                btnStop.disabled = false;
                btnStop.style.opacity = '1';
            }
        });

        // ── Agent Mode Selector ───────────────────────────────
        const selectMode = container.querySelector('#select-agent-mode') as HTMLSelectElement;
        selectMode?.addEventListener('change', async () => {
            try {
                await agentBridge.setMemory('agent_mode', selectMode.value);
                (window as any).log?.(`[AGENCY] Mode set to: ${selectMode.value}`, '#00f3ff');
            } catch (err) {
                console.error('Failed to set agent mode:', err);
            }
        });

        // ── Refresh Activity Button ──────────────────────────
        const btnRefresh = container.querySelector('#btn-refresh-activity') as HTMLButtonElement;
        btnRefresh?.addEventListener('click', () => this.loadActivityFeed(container));
    }

    private static startStatusPolling(container: HTMLElement) {
        // Clean up previous polling
        if (this.statusUnsub) this.statusUnsub();

        // Register status callback
        agentBridge.onStatus((status: AgentStatus) => {
            this.updateStatusUI(container, status);
        });

        // Start polling
        agentBridge.startStatusPolling(3000);

        // Store unsubscribe function
        this.statusUnsub = () => {
            agentBridge.stopStatusPolling();
        };

        // Also refresh activity feed periodically
        this.activityInterval = setInterval(() => {
            this.loadActivityFeed(container);
        }, 10000); // every 10 seconds
    }

    private static updateStatusUI(container: HTMLElement, status: AgentStatus) {
        // Master loop status
        const loopStatus = container.querySelector('#agent-loop-status') as HTMLElement;
        const loopInfo = container.querySelector('#agent-loop-info') as HTMLElement;

        if (loopStatus) {
            if (status.running) {
                loopStatus.innerHTML = '● RUNNING';
                loopStatus.style.color = 'var(--neon-green)';
            } else {
                loopStatus.innerHTML = '● OFFLINE';
                loopStatus.style.color = 'var(--neon-pink)';
            }
        }

        if (loopInfo) {
            const uptimeMin = Math.floor((status.uptime_seconds || 0) / 60);
            loopInfo.textContent = `Loops: ${status.loop_count ?? '—'} | Uptime: ${uptimeMin}m | Queue: ${status.queue_size ?? '—'} | Mode: ${status.mode ?? '—'}`;
        }

        // Safety gauges
        const safety = status.safety;
        if (safety) {
            this.updateGauge(container, 'cpu', safety.cpu_pct, 80, 95);
            this.updateGauge(container, 'ram', safety.ram_pct, 80, 95);
            this.updateGauge(container, 'errors', safety.error_rate * 100, 10, 30);
            this.updateGauge(container, 'loops',
                (safety.consecutive_loops / Math.max(safety.max_consecutive_loops, 1)) * 100,
                70, 90);

            // Brake warning
            const brakeWarning = container.querySelector('#safety-brake-warning') as HTMLElement;
            if (brakeWarning) {
                if (safety.braked) {
                    brakeWarning.style.display = 'block';
                    brakeWarning.textContent = `⚠ BRAKE ENGAGED: ${safety.brake_reason || 'Safety threshold exceeded'}`;
                } else {
                    brakeWarning.style.display = 'none';
                }
            }
        }

        // Update mode selector to match backend
        const selectMode = container.querySelector('#select-agent-mode') as HTMLSelectElement;
        if (selectMode && status.mode && selectMode.value !== status.mode) {
            selectMode.value = status.mode;
        }
    }

    private static updateGauge(container: HTMLElement, name: string, value: number, warnThreshold: number, critThreshold: number) {
        const fill = container.querySelector(`#gauge-${name}-fill`) as HTMLElement;
        const val = container.querySelector(`#gauge-${name}-val`) as HTMLElement;

        if (fill) {
            const pct = Math.max(0, Math.min(100, value));
            fill.style.width = `${pct}%`;

            if (pct >= critThreshold) {
                fill.style.background = 'var(--neon-pink)';
            } else if (pct >= warnThreshold) {
                fill.style.background = '#ffaa00';
            } else {
                fill.style.background = 'var(--neon-green)';
            }
        }

        if (val) {
            if (name === 'errors') {
                val.textContent = `${value.toFixed(1)}%`;
            } else if (name === 'loops') {
                val.textContent = `${Math.round(value)}%`;
            } else {
                val.textContent = `${Math.round(value)}%`;
            }
        }
    }

    private static async loadActivityFeed(container: HTMLElement) {
        const feed = container.querySelector('#activity-feed') as HTMLElement;
        if (!feed) return;

        try {
            const [thoughts, actions] = await Promise.all([
                agentBridge.getThoughts(10).catch(() => []),
                agentBridge.getActions(10).catch(() => []),
            ]);

            // Merge and sort by timestamp (newest first)
            const items: Array<{ type: string; content: string; timestamp: string; extra?: string }> = [];

            thoughts.forEach(t => {
                items.push({
                    type: 'thought',
                    content: t.content,
                    timestamp: t.timestamp,
                    extra: t.tags?.length ? t.tags.join(', ') : undefined,
                });
            });

            actions.forEach(a => {
                items.push({
                    type: 'action',
                    content: a.description,
                    timestamp: a.timestamp,
                    extra: a.result || a.type,
                });
            });

            items.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

            if (items.length === 0) {
                feed.innerHTML = '<div style="opacity:0.5; text-align:center; padding:20px;">No activity yet — start the agent loop</div>';
                return;
            }

            feed.innerHTML = items.slice(0, 20).map(item => {
                const time = new Date(item.timestamp).toLocaleTimeString();
                const icon = item.type === 'thought' ? '💭' : '⚡';
                const color = item.type === 'thought' ? 'var(--neon-blue)' : 'var(--neon-green)';
                const extraHtml = item.extra ? `<span style="opacity:0.5; font-size:0.6rem;"> [${item.extra}]</span>` : '';
                return `
                    <div style="padding:8px 0; border-bottom:1px solid rgba(255,255,255,0.05); display:flex; gap:8px; align-items:flex-start;">
                        <span style="flex-shrink:0;">${icon}</span>
                        <div style="flex:1; min-width:0;">
                            <div style="color:${color}; word-break:break-word;">${this.escapeHtml(item.content)}${extraHtml}</div>
                            <div style="font-size:0.6rem; opacity:0.4; margin-top:2px;">${time}</div>
                        </div>
                    </div>
                `;
            }).join('');
        } catch (err) {
            feed.innerHTML = '<div style="opacity:0.5; text-align:center; padding:20px; color:var(--neon-pink);">Failed to load activity</div>';
        }
    }

    private static escapeHtml(text: string): string {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    private static async fetchAndPopulateDNA(container: HTMLElement) {
        try {
            const resp = await fetch('/api/soul/soul_dna');
            const data = await resp.json();
            if (!data || !data.dna) return;
            const dna = data.dna;

            const selectPersona = container.querySelector('#select-persona') as HTMLSelectElement;
            const selectDomain = container.querySelector('#select-domain') as HTMLSelectElement;

            // Update foveai option label with user-defined companion name (fallback: "Lumax")
            const foveaiOption = selectPersona?.querySelector('option[value="foveai"]') as HTMLOptionElement;
            if (foveaiOption) {
                const soulName = (dna.identity_name || 'FoveAI').trim();
                foveaiOption.textContent = soulName + ' (Default)';
            }

            if (selectPersona && dna.active_persona_id) selectPersona.value = dna.active_persona_id;
            if (selectDomain && dna.active_domain_id) selectDomain.value = dna.active_domain_id;

            if (selectPersona) {
                selectPersona.addEventListener('change', async () => {
                    try {
                        await fetch('/api/soul/update_soul', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ active_persona_id: selectPersona.value })
                        });
                    } catch (err) {
                        console.error('Failed to update active persona:', err);
                    }
                });
            }

            if (selectDomain) {
                selectDomain.addEventListener('change', async () => {
                    try {
                        await fetch('/api/soul/update_soul', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ active_domain_id: selectDomain.value })
                        });
                    } catch (err) {
                        console.error('Failed to update active domain:', err);
                    }
                });
            }

            // Load saved agent mode from memory
            try {
                const savedMode = await agentBridge.getMemory('agent_mode');
                const selectMode = container.querySelector('#select-agent-mode') as HTMLSelectElement;
                if (selectMode && savedMode) {
                    selectMode.value = savedMode;
                }
            } catch (err) {
                // Memory may not be available yet — use default
            }

        } catch (err) {
            console.error('Error fetching soul DNA:', err);
        }
    }
}