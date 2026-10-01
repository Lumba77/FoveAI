// EnvironmentManagementTab.ts — Environment Management Panel
// Controls 3D scene environment: lighting, skybox, fog, room presets

export class EnvironmentManagementTab {
    private static currentPreset = 'default';

    public static render(container: HTMLElement) {
        container.innerHTML = `
            <div class="breadcrumb">ENVIRONMENT MANAGEMENT // SCENE_CONTROL</div>
            <div style="background:rgba(0,0,0,0.4); padding:20px; border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                    <h4 style="font-family:'Orbitron'; margin:0; font-size:0.9rem; color:var(--neon-blue); letter-spacing:2px;">SCENE ENVIRONMENT</h4>
                    <span id="envmgt-status" style="font-size:0.7rem; color:var(--neon-green); font-family:'Share Tech Mono';">READY</span>
                </div>

                <!-- Room Presets -->
                <div style="background:rgba(0,243,255,0.08); border:1px solid var(--neon-blue); border-radius:4px; padding:12px; margin-bottom:15px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">ROOM PRESETS</h5>
                    <div id="preset-grid" style="display:grid; grid-template-columns:1fr 1fr; gap:6px;">
                        <div class="preset-card" data-preset="default" style="background:rgba(0,243,255,0.1); border:1px solid var(--neon-blue); border-radius:3px; padding:8px; cursor:pointer; text-align:center;">
                            <div style="font-size:1.2rem; margin-bottom:4px;">🏠</div>
                            <div style="font-family:'Share Tech Mono'; font-size:0.6rem; color:var(--neon-blue);">DEFAULT</div>
                        </div>
                        <div class="preset-card" data-preset="night" style="background:rgba(0,0,0,0.3); border:1px solid var(--border); border-radius:3px; padding:8px; cursor:pointer; text-align:center;">
                            <div style="font-size:1.2rem; margin-bottom:4px;">🌙</div>
                            <div style="font-family:'Share Tech Mono'; font-size:0.6rem; color:#888;">NIGHT</div>
                        </div>
                        <div class="preset-card" data-preset="studio" style="background:rgba(0,0,0,0.3); border:1px solid var(--border); border-radius:3px; padding:8px; cursor:pointer; text-align:center;">
                            <div style="font-size:1.2rem; margin-bottom:4px;">🎬</div>
                            <div style="font-family:'Share Tech Mono'; font-size:0.6rem; color:#888;">STUDIO</div>
                        </div>
                        <div class="preset-card" data-preset="outdoor" style="background:rgba(0,0,0,0.3); border:1px solid var(--border); border-radius:3px; padding:8px; cursor:pointer; text-align:center;">
                            <div style="font-size:1.2rem; margin-bottom:4px;">🌳</div>
                            <div style="font-family:'Share Tech Mono'; font-size:0.6rem; color:#888;">OUTDOOR</div>
                        </div>
                    </div>
                </div>

                <!-- Lighting Controls -->
                <div style="background:rgba(57,255,20,0.05); border:1px solid #39ff14; border-radius:4px; padding:12px; margin-bottom:15px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:#39ff14; letter-spacing:1px;">LIGHTING</h5>
                    <div style="display:flex; flex-direction:column; gap:8px;">
                        <div style="display:flex; align-items:center; gap:10px;">
                            <label style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#aaa; min-width:80px;">Intensity</label>
                            <input type="range" id="light-intensity" min="0" max="2" step="0.1" value="1.0" style="flex:1; accent-color:var(--neon-blue);">
                            <span id="light-intensity-value" style="font-family:'Share Tech Mono'; font-size:0.65rem; color:var(--neon-blue); min-width:30px;">1.0</span>
                        </div>
                        <div style="display:flex; align-items:center; gap:10px;">
                            <label style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#aaa; min-width:80px;">Color Temp</label>
                            <input type="range" id="light-color-temp" min="2000" max="8000" step="100" value="5500" style="flex:1; accent-color:#ff0;">
                            <span id="light-color-value" style="font-family:'Share Tech Mono'; font-size:0.65rem; color:#ff0; min-width:40px;">5500K</span>
                        </div>
                        <div style="display:flex; align-items:center; gap:10px;">
                            <label style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#aaa; min-width:80px;">Shadows</label>
                            <label style="display:flex; align-items:center; gap:6px; cursor:pointer;">
                                <input type="checkbox" id="shadows-toggle" checked>
                                <span style="font-family:'Share Tech Mono'; font-size:0.65rem; color:#888;">Enabled</span>
                            </label>
                        </div>
                    </div>
                </div>

                <!-- Skybox & Fog -->
                <div style="background:rgba(255,0,127,0.05); border:1px solid var(--neon-pink); border-radius:4px; padding:12px; margin-bottom:15px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">SKYBOX & FOG</h5>
                    <div style="display:flex; flex-direction:column; gap:8px;">
                        <div style="display:flex; align-items:center; gap:10px;">
                            <label style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#aaa; min-width:80px;">Skybox</label>
                            <select id="skybox-select" style="flex:1; background:rgba(0,0,0,0.5); border:1px solid var(--border); color:#fff; padding:4px 8px; border-radius:3px; font-family:'Share Tech Mono'; font-size:0.7rem;">
                                <option value="none">None</option>
                                <option value="stars" selected>Stars</option>
                                <option value="grid">Grid</option>
                                <option value="cyberpunk">Cyberpunk</option>
                                <option value="sunset">Sunset</option>
                            </select>
                        </div>
                        <div style="display:flex; align-items:center; gap:10px;">
                            <label style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#aaa; min-width:80px;">Fog</label>
                            <input type="range" id="fog-density" min="0" max="0.1" step="0.005" value="0" style="flex:1; accent-color:var(--neon-pink);">
                            <span id="fog-density-value" style="font-family:'Share Tech Mono'; font-size:0.65rem; color:var(--neon-pink); min-width:30px;">0</span>
                        </div>
                    </div>
                </div>

                <!-- Scene Objects -->
                <div style="background:rgba(0,0,0,0.3); border:1px solid var(--border); border-radius:4px; padding:12px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">SCENE OBJECTS</h5>
                    <div id="scene-objects" style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#aaa; line-height:1.6;">
                        <div>Meshes: <span id="scene-mesh-count">—</span></div>
                        <div>Lights: <span id="scene-light-count">—</span></div>
                        <div>Cameras: <span id="scene-camera-count">—</span></div>
                    </div>
                    <div style="display:flex; gap:6px; margin-top:8px;">
                        <button id="btn-reset-env" style="background:rgba(255,0,127,0.1); border:1px solid var(--neon-pink); color:var(--neon-pink); padding:4px 10px; border-radius:3px; cursor:pointer; font-family:'Orbitron'; font-size:0.6rem; letter-spacing:1px;">⟲ RESET ENV</button>
                        <button id="btn-apply-env" style="background:rgba(0,243,255,0.15); border:1px solid var(--neon-blue); color:var(--neon-blue); padding:4px 10px; border-radius:3px; cursor:pointer; font-family:'Orbitron'; font-size:0.6rem; letter-spacing:1px;">✓ APPLY</button>
                    </div>
                </div>
            </div>
        `;
        this.setupInteractions(container);
        this.refreshStatus();
    }

    private static setupInteractions(container: HTMLElement) {
        // Preset cards
        container.querySelectorAll('.preset-card').forEach(el => {
            el.addEventListener('click', () => this.applyPreset((el as HTMLElement).dataset.preset || 'default'));
        });

        // Sliders
        const intensitySlider = container.querySelector('#light-intensity') as HTMLInputElement;
        const tempSlider = container.querySelector('#light-color-temp') as HTMLInputElement;
        const fogSlider = container.querySelector('#fog-density') as HTMLInputElement;

        intensitySlider?.addEventListener('input', () => {
            const valEl = document.getElementById('light-intensity-value');
            if (valEl) valEl.textContent = intensitySlider.value;
        });

        tempSlider?.addEventListener('input', () => {
            const valEl = document.getElementById('light-color-value');
            if (valEl) valEl.textContent = `${tempSlider.value}K`;
        });

        fogSlider?.addEventListener('input', () => {
            const valEl = document.getElementById('fog-density-value');
            if (valEl) valEl.textContent = fogSlider.value;
        });

        // Buttons
        container.querySelector('#btn-reset-env')?.addEventListener('click', () => this.resetEnvironment());
        container.querySelector('#btn-apply-env')?.addEventListener('click', () => this.applySettings());
    }

    private static async applyPreset(preset: string) {
        const statusEl = document.getElementById('envmgt-status');
        if (statusEl) {
            statusEl.textContent = `APPLYING ${preset.toUpperCase()}...`;
            statusEl.style.color = '#ff0';
        }

        // Update visual selection
        document.querySelectorAll('.preset-card').forEach(el => {
            const card = el as HTMLElement;
            if (card.dataset.preset === preset) {
                card.style.background = 'rgba(0,243,255,0.1)';
                card.style.borderColor = 'var(--neon-blue)';
                card.querySelector('div:last-child')!.textContent = preset.toUpperCase();
                (card.querySelector('div:last-child') as HTMLElement).style.color = 'var(--neon-blue)';
            } else {
                card.style.background = 'rgba(0,0,0,0.3)';
                card.style.borderColor = 'var(--border)';
                (card.querySelector('div:last-child') as HTMLElement).style.color = '#888';
            }
        });

        this.currentPreset = preset;

        try {
            const resp = await fetch('/api/environment/preset', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ preset })
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const result = await resp.json();
            console.log('[EnvMgt] Preset applied:', result);
            if (statusEl) {
                statusEl.textContent = `${preset.toUpperCase()} ACTIVE`;
                statusEl.style.color = 'var(--neon-green)';
            }
        } catch (err) {
            console.error('[EnvMgt] Failed to apply preset:', err);
            // Apply locally via Three.js if available
            this.applyPresetLocal(preset);
            if (statusEl) {
                statusEl.textContent = 'LOCAL ONLY';
                statusEl.style.color = '#ff0';
            }
        }
    }

    private static applyPresetLocal(preset: string) {
        const env = (window as any).env;
        if (!env || !env.scene) return;

        switch (preset) {
            case 'night':
                env.scene.background = new (window as any).THREE.Color(0x0a0a1a);
                if (env.scene.fog) env.scene.fog.density = 0.02;
                break;
            case 'studio':
                env.scene.background = new (window as any).THREE.Color(0x222222);
                if (env.scene.fog) env.scene.fog.density = 0;
                break;
            case 'outdoor':
                env.scene.background = new (window as any).THREE.Color(0x87CEEB);
                if (env.scene.fog) env.scene.fog.density = 0.005;
                break;
            default: // default
                env.scene.background = new (window as any).THREE.Color(0x111111);
                if (env.scene.fog) env.scene.fog.density = 0;
                break;
        }
    }

    private static async resetEnvironment() {
        const statusEl = document.getElementById('envmgt-status');
        if (statusEl) {
            statusEl.textContent = 'RESETTING...';
            statusEl.style.color = '#ff0';
        }

        try {
            const resp = await fetch('/api/environment/reset', { method: 'POST' });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const result = await resp.json();
            console.log('[EnvMgt] Environment reset:', result);
            if (statusEl) {
                statusEl.textContent = 'RESET';
                statusEl.style.color = 'var(--neon-green)';
            }
        } catch (err) {
            console.error('[EnvMgt] Reset failed:', err);
            if (statusEl) {
                statusEl.textContent = 'ERROR';
                statusEl.style.color = 'var(--neon-pink)';
            }
        }
    }

    private static async applySettings() {
        const statusEl = document.getElementById('envmgt-status');
        if (statusEl) {
            statusEl.textContent = 'APPLYING...';
            statusEl.style.color = '#ff0';
        }

        const intensity = (document.getElementById('light-intensity') as HTMLInputElement)?.value || '1.0';
        const colorTemp = (document.getElementById('light-color-temp') as HTMLInputElement)?.value || '5500';
        const shadows = (document.getElementById('shadows-toggle') as HTMLInputElement)?.checked || false;
        const skybox = (document.getElementById('skybox-select') as HTMLSelectElement)?.value || 'none';
        const fog = (document.getElementById('fog-density') as HTMLInputElement)?.value || '0';

        try {
            const resp = await fetch('/api/environment/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ intensity, colorTemp, shadows, skybox, fog })
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const result = await resp.json();
            console.log('[EnvMgt] Settings applied:', result);
            if (statusEl) {
                statusEl.textContent = 'APPLIED';
                statusEl.style.color = 'var(--neon-green)';
            }
        } catch (err) {
            console.error('[EnvMgt] Apply failed:', err);
            if (statusEl) {
                statusEl.textContent = 'ERROR';
                statusEl.style.color = 'var(--neon-pink)';
            }
        }
    }

    private static async refreshStatus() {
        try {
            const resp = await fetch('/api/environment/status');
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();

            const setText = (id: string, val: string) => {
                const el = document.getElementById(id);
                if (el) el.textContent = val;
            };

            setText('scene-mesh-count', String(data.meshes || '—'));
            setText('scene-light-count', String(data.lights || '—'));
            setText('scene-camera-count', String(data.cameras || '—'));
        } catch (err) {
            // Try local Three.js scene
            const env = (window as any).env;
            if (env && env.scene) {
                const meshes: any[] = [];
                const lights: any[] = [];
                const cameras: any[] = [];
                env.scene.traverse((obj: any) => {
                    if (obj.isMesh) meshes.push(obj);
                    if (obj.isLight) lights.push(obj);
                    if (obj.isCamera) cameras.push(obj);
                });
                const setText = (id: string, val: string) => {
                    const el = document.getElementById(id);
                    if (el) el.textContent = val;
                };
                setText('scene-mesh-count', String(meshes.length));
                setText('scene-light-count', String(lights.length));
                setText('scene-camera-count', String(cameras.length));
            }
        }
    }
}