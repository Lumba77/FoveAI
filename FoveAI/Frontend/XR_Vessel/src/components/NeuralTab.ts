export class NeuralTab {
    private static traits = {
        intimacy: 0.5,
        curiosity: 0.5,
        nourishment: 0.5
    };

    public static render(container: HTMLElement) {
        container.innerHTML = `
            <div class="breadcrumb">SOUL_CONSTITUTION // NEURAL_TRAITS</div>
            
            <div style="flex: 1; display: flex; flex-direction: column; gap: 20px; min-height: 0; overflow-y: auto; padding-right: 10px;">
                <div class="glass-card" style="padding: 20px;">
                    <h4 style="font-family: 'Orbitron'; font-size: 0.8rem; color: var(--neon-blue); margin: 0 0 20px 0; letter-spacing: 2px;">INTRINSIC TRAITS</h4>
                    
                    <div style="display: flex; flex-direction: column; gap: 25px;">
                        <div class="trait-slider">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                                <span style="font-family: 'Orbitron'; font-size: 0.6rem; color: rgba(255,255,255,0.7);">INTRINSIC_INTIMACY</span>
                                <span id="val-intimacy" style="font-family: 'Share Tech Mono'; font-size: 0.75rem; color: var(--neon-blue);">0.50</span>
                            </div>
                            <input type="range" id="slider-intimacy" min="0" max="1" step="0.01" value="0.5" style="width: 100%;">
                        </div>

                        <div class="trait-slider">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                                <span style="font-family: 'Orbitron'; font-size: 0.6rem; color: rgba(255,255,255,0.7);">NEURAL_CURIOSITY</span>
                                <span id="val-curiosity" style="font-family: 'Share Tech Mono'; font-size: 0.75rem; color: var(--neon-blue);">0.50</span>
                            </div>
                            <input type="range" id="slider-curiosity" min="0" max="1" step="0.01" value="0.5" style="width: 100%;">
                        </div>

                        <div class="trait-slider">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                                <span style="font-family: 'Orbitron'; font-size: 0.6rem; color: rgba(255,255,255,0.7);">SPIRITUAL_NOURISHMENT</span>
                                <span id="val-nourishment" style="font-family: 'Share Tech Mono'; font-size: 0.75rem; color: var(--neon-blue);">0.50</span>
                            </div>
                            <input type="range" id="slider-nourishment" min="0" max="1" step="0.01" value="0.5" style="width: 100%;">
                        </div>
                    </div>

                    <button id="btn-sync-traits" class="neon-btn" style="width: 100%; margin-top: 30px; padding: 12px; background: rgba(0, 243, 255, 0.1); border: 1px solid var(--neon-blue); color: #fff; font-family: 'Orbitron'; font-size: 0.7rem; cursor: pointer;">SYNC TO SOUL</button>
                </div>

                <div class="glass-card" style="padding: 20px;">
                    <h4 style="font-family: 'Orbitron'; font-size: 0.8rem; color: var(--neon-pink); margin: 0 0 20px 0; letter-spacing: 2px;">PERSONA ARCHETYPES</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                        <button class="archetype-btn" data-archetype="HEALER">THE HEALER</button>
                        <button class="archetype-btn" data-archetype="SAGE">THE SAGE</button>
                        <button class="archetype-btn" data-archetype="PIONEER">THE PIONEER</button>
                        <button class="archetype-btn" data-archetype="MUSE">THE MUSE</button>
                    </div>
                    <p style="font-size: 0.7rem; color: rgba(255,255,255,0.5); margin-top: 15px; line-height: 1.5; font-style: italic;">
                        Archetypes shift the core response patterns and engagement philosophy of JEN.
                    </p>
                </div>
            </div>

            <style>
                .archetype-btn {
                    background: rgba(255, 0, 127, 0.05);
                    border: 1px solid rgba(255, 0, 127, 0.2);
                    color: #fff;
                    padding: 12px;
                    font-family: 'Orbitron';
                    font-size: 0.65rem;
                    cursor: pointer;
                    transition: all 0.2s;
                    border-radius: 4px;
                    font-weight: 700;
                    letter-spacing: 1px;
                }
                .archetype-btn:hover {
                    background: rgba(255, 0, 127, 0.15);
                    border-color: var(--neon-pink);
                    box-shadow: 0 0 10px var(--neon-pink);
                }
                .archetype-btn.active {
                    background: var(--neon-pink);
                    color: #000;
                    border-color: var(--neon-pink);
                }
            </style>
        `;

        this.setupListeners(container);
        this.fetchCurrentTraits();
    }

    private static async fetchCurrentTraits() {
        try {
            const response = await fetch('/api/soul/runtime_status');
            if (response.ok) {
                const data = await response.json();
                // Map soul data to our sliders
                if (data.traits) {
                    this.traits = data.traits;
                    this.updateUI();
                }
            }
        } catch (err) {}
    }

    private static updateUI() {
        const sliders = ['intimacy', 'curiosity', 'nourishment'];
        sliders.forEach(s => {
            const slider = document.getElementById(`slider-${s}`) as HTMLInputElement;
            const valLabel = document.getElementById(`val-${s}`);
            if (slider && valLabel) {
                const val = (this.traits as any)[s];
                slider.value = val.toString();
                valLabel.textContent = val.toFixed(2);
            }
        });
    }

    private static setupListeners(container: HTMLElement) {
        const sliders = ['intimacy', 'curiosity', 'nourishment'];
        sliders.forEach(s => {
            const slider = container.querySelector(`#slider-${s}`) as HTMLInputElement;
            const valLabel = container.querySelector(`#val-${s}`);
            slider?.addEventListener('input', (e: any) => {
                const val = parseFloat(e.target.value);
                (this.traits as any)[s] = val;
                if (valLabel) valLabel.textContent = val.toFixed(2);
            });
        });

        container.querySelector('#btn-sync-traits')?.addEventListener('click', async () => {
            try {
                const response = await fetch('/api/soul/update_traits', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.traits)
                });
                if (response.ok) {
                    (window as any).log?.('Neural Traits Synchronized', 'var(--neon-blue)');
                }
            } catch (err) {}
        });

        container.querySelectorAll('.archetype-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const archetype = (e.currentTarget as HTMLElement).getAttribute('data-archetype');
                
                // Remove active from others
                container.querySelectorAll('.archetype-btn').forEach(b => b.classList.remove('active'));
                (e.currentTarget as HTMLElement).classList.add('active');

                try {
                    const response = await fetch('/api/soul/set_archetype', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ archetype })
                    });
                    if (response.ok) {
                        (window as any).log?.(`Archetype shifted to ${archetype}`, 'var(--neon-pink)');
                    }
                } catch (err) {}
            });
        });
    }
}
