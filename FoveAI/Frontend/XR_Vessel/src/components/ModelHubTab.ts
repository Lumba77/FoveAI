export class ModelHubTab {
    private static providerData: any = null;
    private static isLoading = false;

    public static render(container: HTMLElement) {
        container.innerHTML = `
            <div class="breadcrumb">MODEL HUB (COGNITIVE ENGINE)</div>
            <div style="background:rgba(0,0,0,0.4); padding:20px; border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                    <h4 style="font-family:'Orbitron'; margin:0; font-size:0.9rem; color:var(--neon-blue); letter-spacing:2px;">INFERENCE ENGINES</h4>
                    <span id="modelhub-status" style="font-size:0.7rem; color:var(--neon-green); font-family:'Share Tech Mono';">LOADING...</span>
                </div>

                <!-- Current Provider / Model Display -->
                <div style="background:rgba(0,243,255,0.08); border:1px solid var(--neon-blue); border-radius:4px; padding:12px; margin-bottom:15px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                        <h5 style="font-family:'Orbitron'; margin:0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">ACTIVE PROVIDER</h5>
                        <button id="btn-refresh-provider" style="background:rgba(0,243,255,0.1); border:1px solid var(--neon-blue); color:var(--neon-blue); padding:2px 8px; border-radius:3px; cursor:pointer; font-family:'Share Tech Mono'; font-size:0.65rem;">⟳ REFRESH</button>
                    </div>
                    <div id="current-provider-display" style="display:flex; align-items:center; gap:10px;">
                        <div style="flex:1;">
                            <div id="provider-name" style="color:var(--neon-blue); font-family:'Share Tech Mono'; font-size:0.95rem; font-weight:bold;">—</div>
                            <div id="provider-model" style="color:#aaa; font-family:'Share Tech Mono'; font-size:0.75rem; margin-top:2px;">loading model info...</div>
                            <div id="provider-url" style="color:#555; font-family:'Share Tech Mono'; font-size:0.6rem; margin-top:2px;"></div>
                        </div>
                    </div>
                </div>

                <!-- Provider Switcher -->
                <div style="margin-bottom:15px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">SWITCH PROVIDER</h5>
                    <div id="provider-switcher" style="display:flex; flex-direction:column; gap:6px;">
                        <div style="color:#666; font-family:'Share Tech Mono'; font-size:0.7rem;">Scanning providers...</div>
                    </div>
                </div>

                <!-- Model Selector (populated per provider) -->
                <div id="model-selector-section" style="margin-bottom:15px; display:none;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">SELECT MODEL</h5>
                    <div style="display:flex; gap:8px;">
                        <select id="model-select" style="flex:1; background:rgba(0,0,0,0.5); border:1px solid var(--border); color:#fff; padding:6px 10px; border-radius:3px; font-family:'Share Tech Mono'; font-size:0.75rem;">
                            <option value="">— Select a model —</option>
                        </select>
                        <button id="btn-apply-model" style="background:rgba(0,243,255,0.15); border:1px solid var(--neon-blue); color:var(--neon-blue); padding:6px 14px; border-radius:3px; cursor:pointer; font-family:'Orbitron'; font-size:0.65rem; letter-spacing:1px;">APPLY</button>
                    </div>
                </div>

                <!-- Available Providers List -->
                <div style="display:flex; gap:20px;">
                    <div style="flex:1;">
                        <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">DETECTED PROVIDERS</h5>
                        <div id="providers-list" style="display:flex; flex-direction:column; gap:4px;">
                            <div style="color:#666; font-family:'Share Tech Mono'; font-size:0.7rem;">Scanning...</div>
                        </div>
                    </div>

                    <div style="flex:1; border-left:1px solid rgba(255,255,255,0.1); padding-left:20px;">
                        <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">INFERENCE PARAMETERS</h5>
                        <div style="display:flex; flex-direction:column; gap:15px;">
                            <div>
                                <div style="display:flex; justify-content:space-between; font-size:0.7rem; font-family:'Share Tech Mono'; margin-bottom:5px;">
                                    <span>Temperature</span><span id="temp-value" style="color:var(--neon-blue);">0.8</span>
                                </div>
                                <input type="range" id="temp-slider" min="0" max="2" step="0.1" value="0.8" style="width:100%; accent-color:var(--neon-blue);">
                            </div>
                            <div>
                                <div style="display:flex; justify-content:space-between; font-size:0.7rem; font-family:'Share Tech Mono'; margin-bottom:5px;">
                                    <span>Max Tokens</span><span id="tokens-value" style="color:var(--neon-blue);">256</span>
                                </div>
                                <input type="range" id="tokens-slider" min="64" max="4096" step="64" value="256" style="width:100%; accent-color:var(--neon-blue);">
                            </div>
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-top:10px;">
                                <span style="font-family:'Share Tech Mono'; font-size:0.75rem; color:#ccc;">Local Vision Senses</span>
                                <label style="position:relative; display:inline-block; width:34px; height:20px;">
                                    <input type="checkbox" id="local-vision-toggle" style="opacity:0; width:0; height:0;">
                                    <span class="slider" style="position:absolute; cursor:pointer; top:0; left:0; right:0; bottom:0; background-color:#333; transition:.4s; border-radius:34px; border:1px solid var(--border);"></span>
                                    <span class="slider-knob" style="position:absolute; content:''; height:14px; width:14px; left:3px; bottom:2px; background-color:var(--neon-blue); transition:.4s; border-radius:50%;"></span>
                                </label>
                            </div>
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-top:8px;">
                                <span style="font-family:'Share Tech Mono'; font-size:0.75rem; color:#ccc;">Structured Output <span style="color:var(--neon-blue); font-size:0.65rem;">[JSON]</span></span>
                                <label style="position:relative; display:inline-block; width:34px; height:20px;">
                                    <input type="checkbox" id="structured-output-toggle" style="opacity:0; width:0; height:0;">
                                    <span class="slider" style="position:absolute; cursor:pointer; top:0; left:0; right:0; bottom:0; background-color:#333; transition:.4s; border-radius:34px; border:1px solid var(--border);"></span>
                                    <span class="slider-knob" style="position:absolute; content:''; height:14px; width:14px; left:3px; bottom:2px; background-color:var(--neon-green); transition:.4s; border-radius:50%;"></span>
                                </label>
                            </div>
                            <button id="btn-purge-cache" class="neon-btn" style="width:100%; padding: 10px; background: rgba(255,0,127,0.1); color: var(--neon-pink); border: 1px solid var(--neon-pink); font-family:'Orbitron'; cursor:pointer; margin-top:10px;">PURGE MODEL CACHE</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Wire up interactions
        this.setupInteractions(container);
        this.fetchProviderInfo();
    }

    private static async fetchProviderInfo() {
        const statusEl = document.getElementById('modelhub-status');
        if (statusEl) statusEl.textContent = 'SCANNING...';
        this.isLoading = true;

        try {
            const resp = await fetch('/api/chat/provider');
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            this.providerData = await resp.json();
            this.updateDisplay();
            if (statusEl) {
                statusEl.textContent = 'ONLINE';
                statusEl.style.color = 'var(--neon-green)';
            }
        } catch (err) {
            console.error('[ModelHub] Failed to fetch provider info:', err);
            if (statusEl) {
                statusEl.textContent = 'OFFLINE';
                statusEl.style.color = 'var(--neon-pink)';
            }
        } finally {
            this.isLoading = false;
        }
    }

    private static updateDisplay() {
        if (!this.providerData) return;
        const data = this.providerData;

        // Update current provider display
        const providerName = document.getElementById('provider-name');
        const providerModel = document.getElementById('provider-model');
        const providerUrl = document.getElementById('provider-url');

        if (providerName) {
            const current = data.current || {};
            const providerId = current.provider || 'unknown';
            // Find friendly name from providers list
            let friendlyName = providerId;
            const providerInfo = (data.providers || []).find((p: any) => p.id === providerId);
            if (providerInfo) friendlyName = providerInfo.name;
            providerName.textContent = friendlyName.toUpperCase();
        }
        if (providerModel) {
            const current = data.current || {};
            providerModel.textContent = current.model || '(default)';
        }
        if (providerUrl) {
            const current = data.current || {};
            providerUrl.textContent = current.base_url || '';
        }

        const visionToggle = document.getElementById('local-vision-toggle') as HTMLInputElement;
        if (visionToggle) {
            visionToggle.checked = data.current?.local_vision ?? true;
        }

        const structuredToggle = document.getElementById('structured-output-toggle') as HTMLInputElement;
        if (structuredToggle) {
            structuredToggle.checked = data.current?.structured_output ?? false;
        }

        // Update provider switcher
        const switcherEl = document.getElementById('provider-switcher');
        if (switcherEl) {
            const providers = data.providers || [];
            if (providers.length === 0) {
                switcherEl.innerHTML = '<div style="color:#666; font-family:\'Share Tech Mono\'; font-size:0.7rem;">No providers detected</div>';
            } else {
                switcherEl.innerHTML = providers.map((p: any) => {
                    const isCurrent = p.id === (data.current?.provider || '');
                    const reachIcon = p.reachable ? '●' : '○';
                    const reachColor = p.reachable ? 'var(--neon-green)' : '#555';
                    const borderColor = isCurrent ? 'var(--neon-blue)' : 'var(--border)';
                    const bgColor = isCurrent ? 'rgba(0,243,255,0.1)' : 'rgba(0,0,0,0.3)';
                    const modelCount = p.models?.length || 0;
                    return `
                        <div class="provider-option" data-provider-id="${p.id}" style="
                            display:flex; align-items:center; gap:10px; padding:8px 12px;
                            background:${bgColor}; border:1px solid ${borderColor}; border-radius:3px;
                            cursor:pointer; transition: all 0.2s;
                        ">
                            <span style="color:${reachColor}; font-size:0.8rem;">${reachIcon}</span>
                            <div style="flex:1;">
                                <div style="color:#fff; font-family:'Share Tech Mono'; font-size:0.8rem;">${p.name}</div>
                                <div style="color:#888; font-family:'Share Tech Mono'; font-size:0.6rem;">${modelCount} model${modelCount !== 1 ? 's' : ''}</div>
                            </div>
                            ${isCurrent ? '<span style="color:var(--neon-blue); font-family:\'Orbitron\'; font-size:0.55rem; letter-spacing:1px;">ACTIVE</span>' : ''}
                        </div>
                    `;
                }).join('');

                // Add click handlers for provider switching
                switcherEl.querySelectorAll('.provider-option').forEach(el => {
                    el.addEventListener('click', async () => {
                        const providerId = (el as HTMLElement).dataset.providerId;
                        if (!providerId) return;
                        await this.switchProvider(providerId, '');
                    });
                    el.addEventListener('mouseenter', () => {
                        (el as HTMLElement).style.background = 'rgba(0,243,255,0.15)';
                        (el as HTMLElement).style.borderColor = 'var(--neon-blue)';
                    });
                    el.addEventListener('mouseleave', () => {
                        const isCurrent = (el as HTMLElement).dataset.providerId === (this.providerData?.current?.provider || '');
                        (el as HTMLElement).style.background = isCurrent ? 'rgba(0,243,255,0.1)' : 'rgba(0,0,0,0.3)';
                        (el as HTMLElement).style.borderColor = isCurrent ? 'var(--neon-blue)' : 'var(--border)';
                    });
                });
            }
        }

        // Update providers list
        const listEl = document.getElementById('providers-list');
        if (listEl) {
            const providers = data.providers || [];
            listEl.innerHTML = providers.map((p: any) => {
                const reachColor = p.reachable ? 'var(--neon-green)' : '#555';
                const reachIcon = p.reachable ? '✓' : '✗';
                return `<div style="display:flex; align-items:center; gap:6px; padding:4px 0;">
                    <span style="color:${reachColor}; font-size:0.75rem;">${reachIcon}</span>
                    <span style="color:#ccc; font-family:'Share Tech Mono'; font-size:0.7rem;">${p.name}</span>
                    <span style="color:#555; font-family:'Share Tech Mono'; font-size:0.6rem;">${p.models?.length || 0} models</span>
                </div>`;
            }).join('');
        }

        // Populate model selector for current provider
        this.updateModelSelector();
    }

    private static updateModelSelector() {
        if (!this.providerData) return;
        const current = this.providerData.current || {};
        const providers = this.providerData.providers || [];
        const currentProvider = providers.find((p: any) => p.id === current.provider);
        const models = currentProvider?.models || [];

        const sectionEl = document.getElementById('model-selector-section');
        const selectEl = document.getElementById('model-select') as HTMLSelectElement;

        if (models.length > 0 && sectionEl && selectEl) {
            sectionEl.style.display = 'block';
            selectEl.innerHTML = '<option value="">— Select a model —</option>';
            models.forEach((m: any) => {
                const modelName = typeof m === 'string' ? m : m.name || m.id;
                const opt = document.createElement('option');
                opt.value = modelName;
                opt.textContent = modelName;
                if (modelName === current.model) opt.selected = true;
                selectEl.appendChild(opt);
            });
        } else if (sectionEl) {
            sectionEl.style.display = 'none';
        }
    }

    private static async switchProvider(providerId: string, model: string) {
        const statusEl = document.getElementById('modelhub-status');
        if (statusEl) {
            statusEl.textContent = 'SWITCHING...';
            statusEl.style.color = '#ff0';
        }

        try {
            const resp = await fetch('/api/chat/provider', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider: providerId, model: model })
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const result = await resp.json();
            console.log('[ModelHub] Provider switched:', result);
            // Refresh display
            await this.fetchProviderInfo();
        } catch (err) {
            console.error('[ModelHub] Failed to switch provider:', err);
            if (statusEl) {
                statusEl.textContent = 'SWITCH FAILED';
                statusEl.style.color = 'var(--neon-pink)';
            }
        }
    }

    private static setupInteractions(container: HTMLElement) {
        // Refresh button
        const btnRefresh = container.querySelector('#btn-refresh-provider');
        btnRefresh?.addEventListener('click', () => this.fetchProviderInfo());

        // Apply model button
        const btnApply = container.querySelector('#btn-apply-model');
        btnApply?.addEventListener('click', async () => {
            const select = container.querySelector('#model-select') as HTMLSelectElement;
            if (!select || !select.value) return;
            const currentProvider = this.providerData?.current?.provider || '';
            await this.switchProvider(currentProvider, select.value);
        });

        // Temperature slider
        const tempSlider = container.querySelector('#temp-slider') as HTMLInputElement;
        const tempValue = container.querySelector('#temp-value');
        tempSlider?.addEventListener('input', () => {
            if (tempValue) tempValue.textContent = tempSlider.value;
        });

        // Max tokens slider
        const tokensSlider = container.querySelector('#tokens-slider') as HTMLInputElement;
        const tokensValue = container.querySelector('#tokens-value');
        tokensSlider?.addEventListener('input', () => {
            if (tokensValue) tokensValue.textContent = tokensSlider.value;
        });

        // Local Vision toggle
        const visionToggle = container.querySelector('#local-vision-toggle') as HTMLInputElement;
        visionToggle?.addEventListener('change', async () => {
            try {
                await fetch('/api/chat/provider', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ local_vision: visionToggle.checked })
                });
                console.log('[ModelHub] Local vision set to:', visionToggle.checked);
            } catch (err) {
                console.error('[ModelHub] Failed to toggle local vision:', err);
            }
        });

        // Structured Output (JSON mode) toggle
        const structuredToggle = container.querySelector('#structured-output-toggle') as HTMLInputElement;
        structuredToggle?.addEventListener('change', async () => {
            try {
                await fetch('/api/chat/provider', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ structured_output: structuredToggle.checked })
                });
                console.log('[ModelHub] Structured output set to:', structuredToggle.checked);
            } catch (err) {
                console.error('[ModelHub] Failed to toggle structured output:', err);
            }
        });

        // Purge cache button
        const btnPurge = container.querySelector('#btn-purge-cache');
        btnPurge?.addEventListener('click', async () => {
            const status = container.querySelector('#modelhub-status') as HTMLElement;
            if (status) { status.innerText = "PURGING..."; status.style.color = "#ff0"; }
            try {
                const cacheNames = await caches.keys();
                for (const name of cacheNames) {
                    if (name.includes('webllm') || name.includes('transformers')) {
                        await caches.delete(name);
                    }
                }
                if (status) { status.innerText = "CACHE PURGED"; status.style.color = "var(--neon-green)"; }
                setTimeout(() => {
                    if (status) { status.innerText = "ONLINE"; status.style.color = "var(--neon-green)"; }
                }, 3000);
            } catch (e) {
                if (status) { status.innerText = "PURGE FAILED"; status.style.color = "var(--neon-pink)"; }
            }
        });
    }
}