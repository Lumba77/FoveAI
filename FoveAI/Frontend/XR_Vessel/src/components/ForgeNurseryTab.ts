/**
 * ForgeNurseryTab — XR_Vessel WebUI tab for Forge Nursery
 * Variant management, fine-tuning jobs, and quantization control.
 * Polls the Forge Nursery API (port 8105).
 */
export class ForgeNurseryTab {
    private static pollInterval: any = null;
    private static container: HTMLElement | null = null;

    public static async render(container: HTMLElement): Promise<void> {
        ForgeNurseryTab.destroy();
        ForgeNurseryTab.container = container;
        container.innerHTML = ForgeNurseryTab.buildHTML();
        ForgeNurseryTab.setupInteractions(container);
        await ForgeNurseryTab.fetchStatus();
        ForgeNurseryTab.pollInterval = setInterval(() => ForgeNurseryTab.fetchStatus(), 5000);
    }

    public static destroy(): void {
        if (ForgeNurseryTab.pollInterval) {
            clearInterval(ForgeNurseryTab.pollInterval);
            ForgeNurseryTab.pollInterval = null;
        }
        ForgeNurseryTab.container = null;
    }

    private static buildHTML(): string {
        return `
        <div class="breadcrumb">FORGE NURSERY // GEMMA_4_12B_VARIANT_PIPELINE</div>
        <div style="display:flex; gap:12px; flex:1; min-height:0; overflow:hidden; padding:8px;">
            <!-- LEFT: Variants + Datasets -->
            <div style="flex:1; display:flex; flex-direction:column; gap:8px; min-width:0; overflow-y:auto;">
                <!-- Status Bar -->
                <div class="glass-card" style="padding:10px 14px; display:flex; gap:16px; align-items:center; font-size:0.75rem;">
                    <span>API: <span id="fn-api-status" style="color:var(--neon-pink);">●</span></span>
                    <span>Variants: <span id="fn-variant-count">0</span></span>
                    <span>Training: <span id="fn-training-active">0</span> active</span>
                    <span>LlamaCPP: <span id="fn-llamacpp-status">-</span></span>
                </div>

                <!-- Variant List -->
                <div class="glass-card" style="flex:1; display:flex; flex-direction:column; min-height:0; overflow:hidden;">
                    <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 12px; border-bottom:1px solid var(--border);">
                        <span style="font-family:'Orbitron'; font-size:0.7rem; letter-spacing:1px;">VARIANTS</span>
                        <button id="fn-btn-new-variant" class="foveai-btn" style="font-size:0.65rem; padding:4px 10px;">+ New</button>
                    </div>
                    <div id="fn-variant-list" style="flex:1; overflow-y:auto; padding:8px;">
                        <div style="color:var(--text-dim); font-size:0.7rem; text-align:center; padding:20px;">Loading variants...</div>
                    </div>
                </div>

                <!-- Dataset List -->
                <div class="glass-card" style="max-height:200px; display:flex; flex-direction:column; overflow:hidden;">
                    <div style="padding:8px 12px; border-bottom:1px solid var(--border); font-family:'Orbitron'; font-size:0.7rem; letter-spacing:1px;">
                        LOCAL DATASETS
                    </div>
                    <div id="fn-dataset-list" style="flex:1; overflow-y:auto; padding:8px; font-size:0.65rem;">
                        <div style="color:var(--text-dim); text-align:center; padding:10px;">Loading datasets...</div>
                    </div>
                </div>
            </div>

            <!-- RIGHT: Jobs + Quantized Models -->
            <div style="flex:1; display:flex; flex-direction:column; gap:8px; min-width:0; overflow-y:auto;">
                <!-- Training Jobs -->
                <div class="glass-card" style="flex:1; display:flex; flex-direction:column; min-height:0; overflow:hidden;">
                    <div style="padding:8px 12px; border-bottom:1px solid var(--border); font-family:'Orbitron'; font-size:0.7rem; letter-spacing:1px;">
                        TRAINING JOBS
                    </div>
                    <div id="fn-jobs-list" style="flex:1; overflow-y:auto; padding:8px; font-size:0.7rem;">
                        <div style="color:var(--text-dim); text-align:center; padding:20px;">No active jobs</div>
                    </div>
                </div>

                <!-- Quantized Models -->
                <div class="glass-card" style="max-height:200px; display:flex; flex-direction:column; overflow:hidden;">
                    <div style="padding:8px 12px; border-bottom:1px solid var(--border); font-family:'Orbitron'; font-size:0.7rem; letter-spacing:1px;">
                        QUANTIZED MODELS
                    </div>
                    <div id="fn-quant-list" style="flex:1; overflow-y:auto; padding:8px; font-size:0.65rem;">
                        <div style="color:var(--text-dim); text-align:center; padding:10px;">No quantized models</div>
                    </div>
                </div>

                <!-- Quick Actions -->
                <div class="glass-card" style="padding:10px 14px; display:flex; gap:8px; flex-wrap:wrap;">
                    <button id="fn-btn-forge-companion" class="foveai-btn" style="font-size:0.65rem; padding:6px 12px;">🔨 Forge Companion</button>
                    <button id="fn-btn-forge-coding" class="foveai-btn" style="font-size:0.65rem; padding:6px 12px;">🔨 Forge Coding</button>
                    <button id="fn-btn-refresh" class="foveai-btn" style="font-size:0.65rem; padding:6px 12px;">🔄 Refresh</button>
                </div>
            </div>
        </div>

        <!-- New Variant Modal (hidden) -->
        <div id="fn-modal" style="display:none; position:fixed; top:0; left:0; right:0; bottom:0; background:rgba(0,0,0,0.7); z-index:1000; align-items:center; justify-content:center;">
            <div class="glass-card" style="width:500px; max-height:80vh; overflow-y:auto; padding:20px;">
                <div style="font-family:'Orbitron'; font-size:0.8rem; margin-bottom:16px;">CREATE VARIANT</div>
                <div style="display:flex; flex-direction:column; gap:10px; font-size:0.7rem;">
                    <div>
                        <label style="color:var(--neon-blue);">Variant ID</label>
                        <input id="fn-new-id" class="foveai-input" placeholder="e.g. companion-uncensored" style="width:100%;">
                    </div>
                    <div>
                        <label style="color:var(--neon-blue);">Display Name</label>
                        <input id="fn-new-name" class="foveai-input" placeholder="e.g. Companion Uncensored" style="width:100%;">
                    </div>
                    <div>
                        <label style="color:var(--neon-blue);">Description</label>
                        <textarea id="fn-new-desc" class="foveai-input" rows="2" style="width:100%; resize:vertical;"></textarea>
                    </div>
                    <div>
                        <label style="color:var(--neon-blue);">Quant Type</label>
                        <select id="fn-new-quant" class="foveai-input" style="width:100%;">
                            <option value="moq-3.0">MoQ 3.0 (Companion - 4.5GB)</option>
                            <option value="moq-3.5">MoQ 3.5 (Coding - 5.2GB)</option>
                            <option value="moq-4.0">MoQ 4.0 (Max Quality - 7.8GB)</option>
                            <option value="q4_k_m">Q4_K_M (4-bit K-quant)</option>
                            <option value="q5_k_m">Q5_K_M (5-bit K-quant)</option>
                        </select>
                    </div>
                    <div>
                        <label style="color:var(--neon-blue);">LoRA Rank</label>
                        <input id="fn-new-lora-r" class="foveai-input" value="16" style="width:100%;">
                    </div>
                    <div>
                        <label style="color:var(--neon-blue);">Epochs</label>
                        <input id="fn-new-epochs" class="foveai-input" value="3" style="width:100%;">
                    </div>
                    <div>
                        <label style="color:var(--neon-blue);">Learning Rate</label>
                        <input id="fn-new-lr" class="foveai-input" value="0.0002" style="width:100%;">
                    </div>
                    <div style="display:flex; gap:8px; justify-content:flex-end; margin-top:8px;">
                        <button id="fn-btn-cancel" class="foveai-btn" style="font-size:0.65rem;">Cancel</button>
                        <button id="fn-btn-create" class="foveai-btn" style="font-size:0.65rem; background:var(--neon-blue);">Create</button>
                    </div>
                </div>
            </div>
        </div>
        `;
    }

    private static setupInteractions(container: HTMLElement): void {
        // New variant modal
        container.querySelector('#fn-btn-new-variant')?.addEventListener('click', () => {
            const modal = container.querySelector('#fn-modal') as HTMLElement;
            if (modal) modal.style.display = 'flex';
        });

        container.querySelector('#fn-btn-cancel')?.addEventListener('click', () => {
            const modal = container.querySelector('#fn-modal') as HTMLElement;
            if (modal) modal.style.display = 'none';
        });

        container.querySelector('#fn-btn-create')?.addEventListener('click', async () => {
            await ForgeNurseryTab.createVariant(container);
        });

        // Forge buttons
        container.querySelector('#fn-btn-forge-companion')?.addEventListener('click', () => {
            ForgeNurseryTab.forgeVariant('companion-uncensored', 'moq-3.0');
        });

        container.querySelector('#fn-btn-forge-coding')?.addEventListener('click', () => {
            ForgeNurseryTab.forgeVariant('coding-sharp', 'moq-3.5');
        });

        container.querySelector('#fn-btn-refresh')?.addEventListener('click', () => {
            ForgeNurseryTab.fetchStatus();
        });
    }

    private static async fetchStatus(): Promise<void> {
        try {
            const [statusRes, variantsRes, datasetsRes, jobsRes] = await Promise.all([
                fetch('http://localhost:8105/api/status').catch(() => null),
                fetch('http://localhost:8105/api/variants').catch(() => null),
                fetch('http://localhost:8105/api/datasets').catch(() => null),
                fetch('http://localhost:8105/api/training/jobs').catch(() => null),
            ]);

            // API status
            const apiEl = document.getElementById('fn-api-status');
            if (apiEl) {
                if (statusRes && statusRes.ok) {
                    const status = await statusRes.json();
                    apiEl.style.color = 'var(--neon-green)';
                    apiEl.textContent = '● ONLINE';
                    ForgeNurseryTab.setText('fn-variant-count', String(status.variants || 0));
                    ForgeNurseryTab.setText('fn-training-active', String(status.active_training_jobs || 0));
                    ForgeNurseryTab.setText('fn-llamacpp-status', status.llama_cpp_available ? '✓' : '✗');
                } else {
                    apiEl.style.color = 'var(--neon-pink)';
                    apiEl.textContent = '● OFFLINE';
                }
            }

            // Variants
            if (variantsRes && variantsRes.ok) {
                const variants = await variantsRes.json();
                ForgeNurseryTab.renderVariants(variants);
            }

            // Datasets
            if (datasetsRes && datasetsRes.ok) {
                const datasets = await datasetsRes.json();
                ForgeNurseryTab.renderDatasets(datasets);
            }

            // Jobs
            if (jobsRes && jobsRes.ok) {
                const jobs = await jobsRes.json();
                ForgeNurseryTab.renderJobs(jobs);
            }

            // Quantized models (fetch per variant)
            await ForgeNurseryTab.fetchQuantizedModels();

        } catch (err) {
            console.warn('[ForgeNursery] fetch error:', err);
        }
    }

    private static renderVariants(variants: any[]): void {
        const el = document.getElementById('fn-variant-list');
        if (!el) return;

        if (!variants || variants.length === 0) {
            el.innerHTML = '<div style="color:var(--text-dim); font-size:0.7rem; text-align:center; padding:20px;">No variants defined. Click "+ New" to create one.</div>';
            return;
        }

        el.innerHTML = variants.map((v: any) => {
            const statusColor = v.status === 'active' ? 'var(--neon-green)' :
                               v.status === 'training' ? 'var(--neon-yellow)' :
                               v.status === 'trained' ? 'var(--neon-blue)' :
                               'var(--text-dim)';
            return `
            <div class="glass-card" style="padding:8px 10px; margin-bottom:6px; font-size:0.7rem;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-weight:bold;">${ForgeNurseryTab.escapeHtml(v.name || v.id)}</span>
                    <span style="color:${statusColor}; font-size:0.6rem;">● ${v.status || 'defined'}</span>
                </div>
                <div style="color:var(--text-dim); font-size:0.6rem; margin-top:2px;">
                    ${ForgeNurseryTab.escapeHtml(v.description || '')}
                </div>
                <div style="display:flex; gap:4px; margin-top:4px; font-size:0.55rem; color:var(--text-dim);">
                    <span>Base: ${ForgeNurseryTab.escapeHtml(v.base_model || 'gemma-4-12b-it')}</span>
                    <span>|</span>
                    <span>Datasets: ${(v.datasets || []).length}</span>
                    <span>|</span>
                    <span>Quant: ${ForgeNurseryTab.escapeHtml(v.quant_type || 'moq-3.0')}</span>
                </div>
                <div style="display:flex; gap:4px; margin-top:6px;">
                    <button class="foveai-btn fn-forge-btn" data-variant="${ForgeNurseryTab.escapeHtml(v.id)}" data-quant="${ForgeNurseryTab.escapeHtml(v.quant_type || 'moq-3.0')}" style="font-size:0.55rem; padding:2px 8px;">🔨 Forge</button>
                    <button class="foveai-btn fn-delete-btn" data-variant="${ForgeNurseryTab.escapeHtml(v.id)}" style="font-size:0.55rem; padding:2px 8px; color:var(--neon-pink);">✕</button>
                </div>
            </div>`;
        }).join('');

        // Bind forge buttons
        el.querySelectorAll('.fn-forge-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const variantId = (e.target as HTMLElement).dataset.variant;
                const quantType = (e.target as HTMLElement).dataset.quant;
                if (variantId) ForgeNurseryTab.forgeVariant(variantId, quantType || 'moq-3.0');
            });
        });

        // Bind delete buttons
        el.querySelectorAll('.fn-delete-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const variantId = (e.target as HTMLElement).dataset.variant;
                if (variantId && confirm(`Delete variant "${variantId}"?`)) {
                    await fetch(`http://localhost:8105/api/variants/${variantId}`, { method: 'DELETE' });
                    ForgeNurseryTab.fetchStatus();
                }
            });
        });
    }

    private static renderDatasets(datasets: any[]): void {
        const el = document.getElementById('fn-dataset-list');
        if (!el) return;

        if (!datasets || datasets.length === 0) {
            el.innerHTML = '<div style="color:var(--text-dim); text-align:center; padding:10px;">No local datasets found</div>';
            return;
        }

        el.innerHTML = datasets.map((ds: any) => `
            <div style="display:flex; justify-content:space-between; padding:3px 0; border-bottom:1px solid rgba(255,255,255,0.03);">
                <span style="color:var(--neon-blue);">${ForgeNurseryTab.escapeHtml(ds.id)}</span>
                <span style="color:var(--text-dim);">${ds.sample_count || '?'} samples · ${ds.size_mb || 0}MB · ${ForgeNurseryTab.escapeHtml(ds.format || '?')}</span>
            </div>
        `).join('');
    }

    private static renderJobs(jobs: any[]): void {
        const el = document.getElementById('fn-jobs-list');
        if (!el) return;

        if (!jobs || jobs.length === 0) {
            el.innerHTML = '<div style="color:var(--text-dim); text-align:center; padding:20px;">No training jobs</div>';
            return;
        }

        el.innerHTML = jobs.map((j: any) => {
            const statusColor = j.status === 'completed' ? 'var(--neon-green)' :
                               j.status === 'failed' ? 'var(--neon-pink)' :
                               j.status === 'training' ? 'var(--neon-yellow)' :
                               j.status === 'cancelled' ? 'var(--text-dim)' :
                               'var(--neon-blue)';
            const progressBar = j.status === 'training'
                ? `<div style="background:var(--border); height:4px; border-radius:2px; margin-top:4px;"><div style="background:var(--neon-yellow); height:100%; width:${(j.progress || 0) * 100}%; border-radius:2px; transition:width 0.3s;"></div></div>`
                : '';

            return `
            <div class="glass-card" style="padding:8px 10px; margin-bottom:6px; font-size:0.65rem;">
                <div style="display:flex; justify-content:space-between;">
                    <span>${ForgeNurseryTab.escapeHtml(j.variant_id)}</span>
                    <span style="color:${statusColor};">● ${j.status}</span>
                </div>
                ${progressBar}
                <div style="color:var(--text-dim); font-size:0.55rem; margin-top:2px;">
                    Step ${j.current_step || 0}/${j.total_steps || '?'} · Loss: ${j.loss || 0} · Progress: ${Math.round((j.progress || 0) * 100)}%
                </div>
                ${j.error ? `<div style="color:var(--neon-pink); font-size:0.55rem; margin-top:2px;">Error: ${ForgeNurseryTab.escapeHtml(j.error)}</div>` : ''}
            </div>`;
        }).join('');
    }

    private static async fetchQuantizedModels(): Promise<void> {
        const el = document.getElementById('fn-quant-list');
        if (!el) return;

        try {
            // Try fetching for known variants
            const variants = ['companion-uncensored', 'coding-sharp'];
            let allModels: any[] = [];

            for (const vid of variants) {
                const res = await fetch(`http://localhost:8105/api/quantize/models/${vid}`).catch(() => null);
                if (res && res.ok) {
                    const models = await res.json();
                    allModels = allModels.concat(models.map((m: any) => ({ ...m, variant_id: vid })));
                }
            }

            if (allModels.length === 0) {
                el.innerHTML = '<div style="color:var(--text-dim); text-align:center; padding:10px;">No quantized models yet</div>';
                return;
            }

            el.innerHTML = allModels.map((m: any) => `
                <div style="display:flex; justify-content:space-between; padding:3px 0; border-bottom:1px solid rgba(255,255,255,0.03);">
                    <span style="color:var(--neon-green);">${ForgeNurseryTab.escapeHtml(m.variant_id)}</span>
                    <span style="color:var(--text-dim);">${ForgeNurseryTab.escapeHtml(m.quant_type || '?')} · ${(m.files || []).length} file(s)</span>
                </div>
            `).join('');

        } catch (err) {
            console.warn('[ForgeNursery] quant fetch error:', err);
        }
    }

    private static async createVariant(container: HTMLElement): Promise<void> {
        const id = (container.querySelector('#fn-new-id') as HTMLInputElement)?.value?.trim();
        const name = (container.querySelector('#fn-new-name') as HTMLInputElement)?.value?.trim();
        const desc = (container.querySelector('#fn-new-desc') as HTMLTextAreaElement)?.value?.trim();
        const quant = (container.querySelector('#fn-new-quant') as HTMLSelectElement)?.value;
        const loraR = parseInt((container.querySelector('#fn-new-lora-r') as HTMLInputElement)?.value || '16');
        const epochs = parseInt((container.querySelector('#fn-new-epochs') as HTMLInputElement)?.value || '3');
        const lr = parseFloat((container.querySelector('#fn-new-lr') as HTMLInputElement)?.value || '0.0002');

        if (!id || !name) {
            alert('Variant ID and Name are required.');
            return;
        }

        try {
            const res = await fetch('http://localhost:8105/api/variants', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    variant_id: id,
                    name: name,
                    description: desc,
                    quant_type: quant,
                    lora_r: loraR,
                    lora_alpha: loraR * 2,
                    epochs: epochs,
                    learning_rate: lr,
                }),
            });

            if (res.ok) {
                const modal = container.querySelector('#fn-modal') as HTMLElement;
                if (modal) modal.style.display = 'none';
                ForgeNurseryTab.fetchStatus();
            } else {
                const err = await res.json();
                alert(`Failed to create variant: ${err.detail || res.statusText}`);
            }
        } catch (err) {
            alert(`Error: ${err}`);
        }
    }

    private static async forgeVariant(variantId: string, quantType: string): Promise<void> {
        try {
            const res = await fetch('http://localhost:8105/api/forge', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    variant_id: variantId,
                    max_samples: 5000,
                    quant_type: quantType,
                    auto_quantize: true,
                }),
            });

            if (res.ok) {
                const data = await res.json();
                ForgeNurseryTab.setMsg(`Forge started: ${data.job_id}`, 'var(--neon-green)');
                ForgeNurseryTab.fetchStatus();
            } else {
                const err = await res.json();
                ForgeNurseryTab.setMsg(`Forge failed: ${err.detail || res.statusText}`, 'var(--neon-pink)');
            }
        } catch (err) {
            ForgeNurseryTab.setMsg(`Error: ${err}`, 'var(--neon-pink)');
        }
    }

    private static setText(id: string, text: string): void {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    private static setMsg(msg: string, color: string): void {
        // Use thought toast if available
        if ((window as any).thoughtToast?.show) {
            (window as any).thoughtToast.show(msg, color);
        }
    }

    private static escapeHtml(text: string): string {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}