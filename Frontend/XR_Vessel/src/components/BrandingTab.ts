export class BrandingTab {
    private static config: any = null;

    public static async render(container: HTMLElement) {
        container.innerHTML = `
            <div class="breadcrumb">LABORATORY // BRANDING_CONFIG</div>
            
            <div style="flex: 1; display: flex; flex-direction: column; gap: 20px; min-height: 0; overflow-y: auto; padding-right: 10px;">
                <div class="glass-card" style="padding: 20px;">
                    <h4 style="font-family: 'Orbitron'; font-size: 0.8rem; color: var(--neon-blue); margin: 0 0 15px 0;">UI CONFIGURATION</h4>
                    <p style="font-size: 0.7rem; opacity: 0.6; margin-bottom: 20px; line-height: 1.4;">
                        Customize labels and branding for different surfaces. Changes are saved to <span style="font-family: 'Share Tech Mono'; color: var(--neon-blue);">foveai_ui_config.json</span>.
                    </p>

                    <div style="display: flex; gap: 10px; margin-bottom: 20px;">
                        <button class="surface-btn active" data-surface="global">GLOBAL</button>
                        <button class="surface-btn" data-surface="web">WEB</button>
                        <button class="surface-btn" data-surface="godot_vr">VR</button>
                        <button class="surface-btn" data-surface="mobile">MOBILE</button>
                    </div>

                    <div id="brand-fields" style="display: grid; grid-template-columns: 1fr; gap: 15px;">
                        Loading configuration...
                    </div>

                    <button id="btn-save-branding" class="neon-btn" style="width: 100%; margin-top: 25px; padding: 12px; background: var(--neon-blue); color: #000; border: none; border-radius: 4px; font-family: 'Orbitron'; font-weight: 700; letter-spacing: 1px; cursor: pointer;">SAVE CONFIGURATION</button>
                </div>
            </div>

            <style>
                .surface-btn {
                    flex: 1;
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    color: rgba(255, 255, 255, 0.6);
                    padding: 8px;
                    font-family: 'Orbitron';
                    font-size: 0.6rem;
                    cursor: pointer;
                    border-radius: 4px;
                    transition: all 0.2s;
                }
                .surface-btn:hover {
                    background: rgba(0, 243, 255, 0.1);
                    color: var(--neon-blue);
                }
                .surface-btn.active {
                    background: rgba(0, 243, 255, 0.2);
                    border-color: var(--neon-blue);
                    color: var(--neon-blue);
                }
                .brand-field {
                    display: flex;
                    flex-direction: column;
                    gap: 5px;
                }
                .brand-field label {
                    font-size: 0.65rem;
                    opacity: 0.7;
                    text-transform: uppercase;
                    font-family: 'Orbitron';
                    letter-spacing: 1px;
                }
                .brand-field input, .brand-field textarea {
                    background: rgba(0,0,0,0.4);
                    border: 1px solid var(--border);
                    color: #fff;
                    padding: 10px;
                    border-radius: 4px;
                    font-family: inherit;
                    font-size: 0.85rem;
                }
            </style>
        `;

        await this.fetchConfig();
        this.renderFields(container, 'global');
        this.setupListeners(container);
    }

    private static async fetchConfig() {
        try {
            const response = await fetch('/api/soul/ui_config');
            if (response.ok) {
                this.config = await response.json();
            }
        } catch (err) {}
    }

    private static renderFields(container: HTMLElement, surface: string) {
        const fieldsArea = container.querySelector('#brand-fields');
        if (!fieldsArea || !this.config) return;

        const data = this.config[surface] || {};
        let html = '';

        Object.entries(data).forEach(([key, val]: [string, any]) => {
            if (typeof val === 'string') {
                if (val.length > 60 || key.includes('body') || key.includes('blurb')) {
                    html += `
                        <div class="brand-field">
                            <label>${key.replace(/_/g, ' ')}</label>
                            <textarea data-key="${key}" data-surface="${surface}" rows="3">${val}</textarea>
                        </div>
                    `;
                } else {
                    html += `
                        <div class="brand-field">
                            <label>${key.replace(/_/g, ' ')}</label>
                            <input type="text" data-key="${key}" data-surface="${surface}" value="${val}">
                        </div>
                    `;
                }
            }
        });

        fieldsArea.innerHTML = html || `<div style="opacity: 0.5; font-size: 0.7rem; text-align: center;">No fields found for ${surface}.</div>`;
    }

    private static setupListeners(container: HTMLElement) {
        container.querySelectorAll('.surface-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const surface = (e.currentTarget as HTMLElement).getAttribute('data-surface') || 'global';
                container.querySelectorAll('.surface-btn').forEach(b => b.classList.remove('active'));
                (e.currentTarget as HTMLElement).classList.add('active');
                this.renderFields(container, surface);
            });
        });

        container.querySelector('#btn-save-branding')?.addEventListener('click', async () => {
            // Collect all current field values
            container.querySelectorAll('[data-key]').forEach((el: any) => {
                const surface = el.getAttribute('data-surface');
                const key = el.getAttribute('data-key');
                const val = el.value;
                if (this.config[surface]) {
                    this.config[surface][key] = val;
                }
            });

            try {
                const response = await fetch('/api/soul/ui_config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.config)
                });
                if (response.ok) {
                    (window as any).log?.('UI Configuration Saved', 'var(--neon-blue)');
                }
            } catch (err) {}
        });
    }
}
