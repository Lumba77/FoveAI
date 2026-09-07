// ControllersMappingTab.ts — Controllers Mapping Panel
// Manages WebXR controller bindings, haptic feedback, and input configuration

export class ControllersMappingTab {
    private static controllerData: any = null;

    public static render(container: HTMLElement) {
        container.innerHTML = `
            <div class="breadcrumb">CONTROLLERS MAPPING // INPUT_CONFIG</div>
            <div style="background:rgba(0,0,0,0.4); padding:20px; border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                    <h4 style="font-family:'Orbitron'; margin:0; font-size:0.9rem; color:var(--neon-blue); letter-spacing:2px;">CONTROLLER BINDINGS</h4>
                    <span id="ctrl-status" style="font-size:0.7rem; color:var(--neon-green); font-family:'Share Tech Mono';">SCANNING...</span>
                </div>

                <!-- Connected Controllers -->
                <div style="background:rgba(0,243,255,0.08); border:1px solid var(--neon-blue); border-radius:4px; padding:12px; margin-bottom:15px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">CONNECTED DEVICES</h5>
                    <div id="connected-controllers" style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#aaa; line-height:1.6;">
                        <div>Left: <span id="ctrl-left" style="color:#888;">Not connected</span></div>
                        <div>Right: <span id="ctrl-right" style="color:#888;">Not connected</span></div>
                        <div>Gamepad: <span id="ctrl-gamepad" style="color:#888;">Not detected</span></div>
                    </div>
                </div>

                <!-- Button Mapping -->
                <div style="background:rgba(57,255,20,0.05); border:1px solid #39ff14; border-radius:4px; padding:12px; margin-bottom:15px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:#39ff14; letter-spacing:1px;">BUTTON MAPPINGS</h5>
                    <div style="display:flex; flex-direction:column; gap:6px;">
                        <div class="mapping-row" style="display:flex; align-items:center; gap:8px; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
                            <span style="min-width:100px; font-family:'Share Tech Mono'; font-size:0.65rem; color:#888;">Trigger (0)</span>
                            <select class="mapping-select" data-button="trigger" style="flex:1; background:rgba(0,0,0,0.5); border:1px solid var(--border); color:#fff; padding:3px 6px; border-radius:3px; font-family:'Share Tech Mono'; font-size:0.65rem;">
                                <option value="select">Select / Interact</option>
                                <option value="snapshot">Take Snapshot</option>
                                <option value="talk">Push to Talk</option>
                                <option value="none">None</option>
                            </select>
                        </div>
                        <div class="mapping-row" style="display:flex; align-items:center; gap:8px; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
                            <span style="min-width:100px; font-family:'Share Tech Mono'; font-size:0.65rem; color:#888;">Grip (1)</span>
                            <select class="mapping-select" data-button="grip" style="flex:1; background:rgba(0,0,0,0.5); border:1px solid var(--border); color:#fff; padding:3px 6px; border-radius:3px; font-family:'Share Tech Mono'; font-size:0.65rem;">
                                <option value="grab">Grab / Drag</option>
                                <option value="steering">Toggle Steering</option>
                                <option value="crouch">Crouch</option>
                                <option value="none">None</option>
                            </select>
                        </div>
                        <div class="mapping-row" style="display:flex; align-items:center; gap:8px; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
                            <span style="min-width:100px; font-family:'Share Tech Mono'; font-size:0.65rem; color:#888;">Thumbstick (2)</span>
                            <select class="mapping-select" data-button="thumbstick" style="flex:1; background:rgba(0,0,0,0.5); border:1px solid var(--border); color:#fff; padding:3px 6px; border-radius:3px; font-family:'Share Tech Mono'; font-size:0.65rem;">
                                <option value="move">Movement</option>
                                <option value="teleport">Teleport</option>
                                <option value="rotate">Rotate View</option>
                                <option value="none">None</option>
                            </select>
                        </div>
                        <div class="mapping-row" style="display:flex; align-items:center; gap:8px; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
                            <span style="min-width:100px; font-family:'Share Tech Mono'; font-size:0.65rem; color:#888;">A/X (4)</span>
                            <select class="mapping-select" data-button="ax" style="flex:1; background:rgba(0,0,0,0.5); border:1px solid var(--border); color:#fff; padding:3px 6px; border-radius:3px; font-family:'Share Tech Mono'; font-size:0.65rem;">
                                <option value="snapshot">User Snapshot</option>
                                <option value="diagnosis">Diagnosis Tab</option>
                                <option value="attention">Attention Call</option>
                                <option value="none">None</option>
                            </select>
                        </div>
                        <div class="mapping-row" style="display:flex; align-items:center; gap:8px; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
                            <span style="min-width:100px; font-family:'Share Tech Mono'; font-size:0.65rem; color:#888;">B/Y (5)</span>
                            <select class="mapping-select" data-button="by" style="flex:1; background:rgba(0,0,0,0.5); border:1px solid var(--border); color:#fff; padding:3px 6px; border-radius:3px; font-family:'Share Tech Mono'; font-size:0.65rem;">
                                <option value="talk">Push to Talk</option>
                                <option value="avatar-snapshot">Avatar Snapshot</option>
                                <option value="menu">Menu Toggle</option>
                                <option value="none">None</option>
                            </select>
                        </div>
                        <div class="mapping-row" style="display:flex; align-items:center; gap:8px; padding:4px 0;">
                            <span style="min-width:100px; font-family:'Share Tech Mono'; font-size:0.65rem; color:#888;">Menu (3)</span>
                            <select class="mapping-select" data-button="menu" style="flex:1; background:rgba(0,0,0,0.5); border:1px solid var(--border); color:#fff; padding:3px 6px; border-radius:3px; font-family:'Share Tech Mono'; font-size:0.65rem;">
                                <option value="menu">Open Menu</option>
                                <option value="settings">Settings Tab</option>
                                <option value="recenter">Recenter View</option>
                                <option value="none">None</option>
                            </select>
                        </div>
                    </div>
                </div>

                <!-- Haptic Settings -->
                <div style="background:rgba(255,0,127,0.05); border:1px solid var(--neon-pink); border-radius:4px; padding:12px; margin-bottom:15px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">HAPTIC FEEDBACK</h5>
                    <div style="display:flex; flex-direction:column; gap:8px;">
                        <div style="display:flex; align-items:center; gap:10px;">
                            <label style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#aaa; min-width:80px;">Intensity</label>
                            <input type="range" id="haptic-intensity" min="0" max="1" step="0.1" value="0.5" style="flex:1; accent-color:var(--neon-pink);">
                            <span id="haptic-intensity-value" style="font-family:'Share Tech Mono'; font-size:0.65rem; color:var(--neon-pink); min-width:30px;">0.5</span>
                        </div>
                        <div style="display:flex; align-items:center; gap:10px;">
                            <label style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#aaa; min-width:80px;">Duration</label>
                            <input type="range" id="haptic-duration" min="10" max="200" step="10" value="50" style="flex:1; accent-color:var(--neon-pink);">
                            <span id="haptic-duration-value" style="font-family:'Share Tech Mono'; font-size:0.65rem; color:var(--neon-pink); min-width:30px;">50ms</span>
                        </div>
                    </div>
                </div>

                <!-- Action Buttons -->
                <div style="display:flex; gap:8px;">
                    <button id="btn-test-haptic" style="flex:1; background:rgba(255,0,127,0.15); border:1px solid var(--neon-pink); color:var(--neon-pink); padding:6px 14px; border-radius:3px; cursor:pointer; font-family:'Orbitron'; font-size:0.6rem; letter-spacing:1px;">⚡ TEST HAPTIC</button>
                    <button id="btn-save-mapping" style="flex:1; background:rgba(0,243,255,0.15); border:1px solid var(--neon-blue); color:var(--neon-blue); padding:6px 14px; border-radius:3px; cursor:pointer; font-family:'Orbitron'; font-size:0.6rem; letter-spacing:1px;">💾 SAVE MAPPING</button>
                    <button id="btn-reset-mapping" style="flex:1; background:rgba(255,255,0,0.1); border:1px solid #ff0; color:#ff0; padding:6px 14px; border-radius:3px; cursor:pointer; font-family:'Orbitron'; font-size:0.6rem; letter-spacing:1px;">⟲ RESET</button>
                </div>
            </div>
        `;
        this.setupInteractions(container);
        this.refreshStatus();
    }

    private static setupInteractions(container: HTMLElement) {
        // Haptic sliders
        const hapticIntensity = container.querySelector('#haptic-intensity') as HTMLInputElement;
        const hapticDuration = container.querySelector('#haptic-duration') as HTMLInputElement;

        hapticIntensity?.addEventListener('input', () => {
            const valEl = document.getElementById('haptic-intensity-value');
            if (valEl) valEl.textContent = hapticIntensity.value;
        });

        hapticDuration?.addEventListener('input', () => {
            const valEl = document.getElementById('haptic-duration-value');
            if (valEl) valEl.textContent = `${hapticDuration.value}ms`;
        });

        // Buttons
        container.querySelector('#btn-test-haptic')?.addEventListener('click', () => this.testHaptic());
        container.querySelector('#btn-save-mapping')?.addEventListener('click', () => this.saveMapping());
        container.querySelector('#btn-reset-mapping')?.addEventListener('click', () => this.resetMapping());
    }

    private static async testHaptic() {
        const intensity = (document.getElementById('haptic-intensity') as HTMLInputElement)?.value || '0.5';
        const duration = (document.getElementById('haptic-duration') as HTMLInputElement)?.value || '50';

        // Try WebXR haptic if available
        const session = (window as any).env?.renderer?.xr?.getSession();
        if (session) {
            for (const src of session.inputSources) {
                if (src.gamepad && src.gamepad.hapticActuators?.length > 0) {
                    try {
                        src.gamepad.hapticActuators[0].pulse(parseFloat(intensity), parseInt(duration));
                    } catch (e) {
                        console.debug('[CtrlMap] Haptic pulse failed:', e);
                    }
                }
            }
        }

        const statusEl = document.getElementById('ctrl-status');
        if (statusEl) {
            statusEl.textContent = 'HAPTIC TEST';
            statusEl.style.color = 'var(--neon-pink)';
            setTimeout(() => {
                statusEl.textContent = 'READY';
                statusEl.style.color = 'var(--neon-green)';
            }, 1500);
        }
    }

    private static async saveMapping() {
        const statusEl = document.getElementById('ctrl-status');
        if (statusEl) {
            statusEl.textContent = 'SAVING...';
            statusEl.style.color = '#ff0';
        }

        const mappings: Record<string, string> = {};
        document.querySelectorAll('.mapping-select').forEach(el => {
            const select = el as HTMLSelectElement;
            mappings[select.dataset.button || 'unknown'] = select.value;
        });

        const hapticIntensity = (document.getElementById('haptic-intensity') as HTMLInputElement)?.value || '0.5';
        const hapticDuration = (document.getElementById('haptic-duration') as HTMLInputElement)?.value || '50';

        try {
            const resp = await fetch('/api/controllers/mapping', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mappings, haptic: { intensity: hapticIntensity, duration: hapticDuration } })
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const result = await resp.json();
            console.log('[CtrlMap] Mapping saved:', result);
            if (statusEl) {
                statusEl.textContent = 'SAVED';
                statusEl.style.color = 'var(--neon-green)';
                setTimeout(() => {
                    statusEl.textContent = 'READY';
                    statusEl.style.color = 'var(--neon-green)';
                }, 2000);
            }
        } catch (err) {
            console.error('[CtrlMap] Save failed:', err);
            // Save to localStorage as fallback
            localStorage.setItem('foveai_controller_mappings', JSON.stringify(mappings));
            localStorage.setItem('foveai_haptic_settings', JSON.stringify({ intensity: hapticIntensity, duration: hapticDuration }));
            if (statusEl) {
                statusEl.textContent = 'SAVED (LOCAL)';
                statusEl.style.color = '#ff0';
                setTimeout(() => {
                    statusEl.textContent = 'READY';
                    statusEl.style.color = 'var(--neon-green)';
                }, 2000);
            }
        }
    }

    private static async resetMapping() {
        const statusEl = document.getElementById('ctrl-status');
        if (statusEl) {
            statusEl.textContent = 'RESETTING...';
            statusEl.style.color = '#ff0';
        }

        // Reset all selects to defaults
        document.querySelectorAll('.mapping-select').forEach(el => {
            const select = el as HTMLSelectElement;
            select.selectedIndex = 0;
        });

        // Reset haptic sliders
        const intensitySlider = document.getElementById('haptic-intensity') as HTMLInputElement;
        const durationSlider = document.getElementById('haptic-duration') as HTMLInputElement;
        if (intensitySlider) { intensitySlider.value = '0.5'; }
        if (durationSlider) { durationSlider.value = '50'; }
        const intensityVal = document.getElementById('haptic-intensity-value');
        const durationVal = document.getElementById('haptic-duration-value');
        if (intensityVal) intensityVal.textContent = '0.5';
        if (durationVal) durationVal.textContent = '50ms';

        try {
            const resp = await fetch('/api/controllers/mapping/reset', { method: 'POST' });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const result = await resp.json();
            console.log('[CtrlMap] Mapping reset:', result);
        } catch (err) {
            console.error('[CtrlMap] Reset failed:', err);
            localStorage.removeItem('foveai_controller_mappings');
            localStorage.removeItem('foveai_haptic_settings');
        }

        if (statusEl) {
            statusEl.textContent = 'RESET';
            statusEl.style.color = 'var(--neon-green)';
            setTimeout(() => {
                statusEl.textContent = 'READY';
                statusEl.style.color = 'var(--neon-green)';
            }, 2000);
        }
    }

    private static async refreshStatus() {
        try {
            // Check XR controller status
            const session = (window as any).env?.renderer?.xr?.getSession();
            const setText = (id: string, val: string, color?: string) => {
                const el = document.getElementById(id);
                if (el) {
                    el.textContent = val;
                    if (color) el.style.color = color;
                }
            };

            if (session && session.inputSources) {
                let leftConnected = false;
                let rightConnected = false;
                let gamepadCount = 0;

                for (const src of session.inputSources) {
                    if (src.handedness === 'left') leftConnected = true;
                    if (src.handedness === 'right') rightConnected = true;
                    if (src.gamepad) gamepadCount++;
                }

                setText('ctrl-left', leftConnected ? 'Connected ✓' : 'Not connected', leftConnected ? 'var(--neon-green)' : '#888');
                setText('ctrl-right', rightConnected ? 'Connected ✓' : 'Not connected', rightConnected ? 'var(--neon-green)' : '#888');
                setText('ctrl-gamepad', gamepadCount > 0 ? `${gamepadCount} gamepad(s)` : 'Not detected', gamepadCount > 0 ? 'var(--neon-green)' : '#888');

                const statusEl = document.getElementById('ctrl-status');
                if (statusEl) {
                    statusEl.textContent = leftConnected || rightConnected ? 'CONNECTED' : 'NO DEVICES';
                    statusEl.style.color = leftConnected || rightConnected ? 'var(--neon-green)' : '#888';
                }
            } else {
                setText('ctrl-left', 'Not in XR');
                setText('ctrl-right', 'Not in XR');
                setText('ctrl-gamepad', 'Not in XR');
                const statusEl = document.getElementById('ctrl-status');
                if (statusEl) {
                    statusEl.textContent = 'NO XR SESSION';
                    statusEl.style.color = '#888';
                }
            }

            // Load saved mappings
            const saved = localStorage.getItem('foveai_controller_mappings');
            if (saved) {
                try {
                    const mappings = JSON.parse(saved);
                    document.querySelectorAll('.mapping-select').forEach(el => {
                        const select = el as HTMLSelectElement;
                        const key = select.dataset.button;
                        if (key && mappings[key]) {
                            select.value = mappings[key];
                        }
                    });
                } catch (e) { /* ignore */ }
            }
        } catch (err) {
            console.debug('[CtrlMap] Status refresh failed:', err);
        }
    }
}