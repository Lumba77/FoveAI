export class DreamscapeTab {
    private static uploadedImage: string | null = null;

    public static render(container: HTMLElement) {
        container.innerHTML = `
            <div class="breadcrumb">DREAMSCAPE // ART_GENERATOR</div>
            
            <div style="flex: 1; display: flex; flex-direction: column; gap: 15px; min-height: 0; overflow-y: auto; padding-right: 5px;">
                <div class="glass-card" style="padding: 20px;">
                    <label style="font-family: 'Orbitron'; font-size: 0.65rem; color: var(--neon-blue); display: block; margin-bottom: 10px;">PROMPT DESCRIPTION</label>
                    <textarea id="dream-prompt" rows="3" style="width: 100%; background: rgba(0,0,0,0.4); border: 1px solid var(--border); color: #fff; padding: 12px; border-radius: 4px; font-family: inherit; font-size: 0.9rem; outline: none; resize: vertical;" placeholder="A neon-lit cyberpunk city under a violet sky..."></textarea>
                    
                    <div style="margin-top: 15px; display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                        <div>
                            <label style="font-family: 'Orbitron'; font-size: 0.55rem; color: rgba(255,255,255,0.5); display: block; margin-bottom: 5px;">MODEL ENGINE</label>
                            <select id="dream-engine" style="width: 100%; background: #0a0f19; border: 1px solid var(--border); color: #fff; padding: 8px; border-radius: 4px; font-family: 'Share Tech Mono'; font-size: 0.75rem;">
                                <option value="turbo">SDXL Turbo (Fast)</option>
                                <option value="sd15">Stable Diffusion 1.5</option>
                                <option value="control">ControlNet Structure</option>
                                <option value="upscale">Real-ESRGAN Upscale</option>
                            </select>
                        </div>
                        <div>
                            <label style="font-family: 'Orbitron'; font-size: 0.55rem; color: rgba(255,255,255,0.5); display: block; margin-bottom: 5px;">RATIO</label>
                            <select id="dream-ratio" style="width: 100%; background: #0a0f19; border: 1px solid var(--border); color: #fff; padding: 8px; border-radius: 4px; font-family: 'Share Tech Mono'; font-size: 0.75rem;">
                                <option value="1:1">1:1 Square</option>
                                <option value="16:9">16:9 Cinema</option>
                                <option value="9:16">9:16 Mobile</option>
                            </select>
                        </div>
                    </div>

                    <div style="margin-top: 15px;">
                        <label style="font-family: 'Orbitron'; font-size: 0.55rem; color: rgba(255,255,255,0.5); display: block; margin-bottom: 5px;">IMAGE-TO-IMAGE (OPTIONAL)</label>
                        <div style="display: flex; gap: 10px; align-items: center;">
                            <input type="file" id="dream-file" accept="image/*" style="font-size: 0.7rem; color: rgba(255,255,255,0.5);">
                            <button id="btn-clear-img" style="background: transparent; border: 1px solid rgba(255,255,255,0.2); color: #fff; font-size: 0.6rem; padding: 4px 8px; cursor: pointer; border-radius: 3px;">CLEAR</button>
                        </div>
                        <img id="dream-preview" style="display: none; max-width: 100px; max-height: 100px; margin-top: 10px; border: 1px solid var(--neon-blue); border-radius: 4px;">
                    </div>

                    <button id="btn-forge-dream" class="neon-btn" style="width: 100%; padding: 15px; background: var(--neon-pink); color: #fff; border: none; border-radius: 4px; font-family: 'Orbitron'; font-weight: 700; letter-spacing: 2px; cursor: pointer; margin-top: 20px; box-shadow: 0 0 15px var(--neon-pink);">FORGE VISION</button>
                </div>

                <div id="dream-output-container" class="glass-card" style="flex: 1; min-height: 300px; display: flex; align-items: center; justify-content: center; position: relative; overflow: hidden; background: rgba(0,0,0,0.4);">
                    <div id="dream-empty-state" style="text-align: center; opacity: 0.5;">
                        <div style="font-size: 2rem; margin-bottom: 10px;">✨</div>
                        <div style="font-family: 'Orbitron'; font-size: 0.7rem;">AWAITING ARTILLERY COMMAND</div>
                    </div>
                    <div id="dream-forge-overlay" style="display: none; position: absolute; inset: 0; background: rgba(0,0,0,0.8); z-index: 10; flex-direction: column; align-items: center; justify-content: center;">
                        <div class="forge-spinner" style="width: 40px; height: 40px; border: 3px solid var(--neon-blue); border-top-color: transparent; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                        <div style="margin-top: 15px; font-family: 'Orbitron'; font-size: 0.7rem; color: var(--neon-blue); letter-spacing: 2px;">FORGING NEURAL ARTIFACT...</div>
                    </div>
                    <img id="dream-result-img" style="display: none; max-width: 100%; max-height: 100%; object-fit: contain; box-shadow: 0 0 30px rgba(0,243,255,0.2);">
                </div>
            </div>

            <style>
                @keyframes spin { to { transform: rotate(360deg); } }
            </style>
        `;

        this.setupListeners(container);
    }

    private static setupListeners(container: HTMLElement) {
        const fileInput = container.querySelector('#dream-file') as HTMLInputElement;
        const preview = container.querySelector('#dream-preview') as HTMLImageElement;
        const btnClear = container.querySelector('#btn-clear-img');
        const btnForge = container.querySelector('#btn-forge-dream');
        const promptInput = container.querySelector('#dream-prompt') as HTMLTextAreaElement;
        const overlay = container.querySelector('#dream-forge-overlay') as HTMLElement;
        const resultImg = container.querySelector('#dream-result-img') as HTMLImageElement;
        const emptyState = container.querySelector('#dream-empty-state') as HTMLElement;

        fileInput?.addEventListener('change', (e: any) => {
            const file = e.target.files[0];
            if (file) {
                const reader = new FileReader();
                reader.onload = (re) => {
                    this.uploadedImage = re.target?.result as string;
                    if (preview) {
                        preview.src = this.uploadedImage;
                        preview.style.display = 'block';
                    }
                };
                reader.readAsDataURL(file);
            }
        });

        btnClear?.addEventListener('click', () => {
            this.uploadedImage = null;
            if (fileInput) fileInput.value = '';
            if (preview) preview.style.display = 'none';
        });

        btnForge?.addEventListener('click', async () => {
            const prompt = promptInput.value.trim();
            if (!prompt) return;

            if (overlay) overlay.style.display = 'flex';
            if (emptyState) emptyState.style.display = 'none';
            if (resultImg) resultImg.style.display = 'none';

            try {
                // Determine if we use local artillery or soul
                const engine = (container.querySelector('#dream-engine') as HTMLSelectElement).value;
                const ratio = (container.querySelector('#dream-ratio') as HTMLSelectElement).value;

                let resultBase64 = null;

                // Priority: Local WebSD if available and engine is 'turbo'
                if (engine === 'turbo' && (window as any).localArtillery?.isAvailable()) {
                    resultBase64 = await (window as any).localArtillery.imagine(prompt);
                } else {
                    // Fallback to Creative service via Proxy
                    const response = await fetch('/api/dreamscape/generate', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            prompt, 
                            engine, 
                            ratio,
                            image: this.uploadedImage 
                        })
                    });
                    if (response.ok) {
                        const data = await response.json();
                        resultBase64 = data.image; // Expecting base64
                    }
                }

                if (resultBase64) {
                    if (resultImg) {
                        resultImg.src = resultBase64.startsWith('data:') ? resultBase64 : `data:image/png;base64,${resultBase64}`;
                        resultImg.style.display = 'block';
                    }
                } else {
                    alert('Neural Forge Offline. Check Creativity service logs.');
                    if (emptyState) emptyState.style.display = 'block';
                }
            } catch (err) {
                console.error('Dreamscape error:', err);
                if (emptyState) emptyState.style.display = 'block';
            } finally {
                if (overlay) overlay.style.display = 'none';
            }
        });
    }
}
