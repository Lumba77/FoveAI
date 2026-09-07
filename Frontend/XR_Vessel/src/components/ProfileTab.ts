export class ProfileTab {
    private static debounceTimeout: number | null = null;
    private static debounceProfileTimeout: number | null = null;

    public static render(container: HTMLElement) {
        container.innerHTML = `
            <div class="breadcrumb">PROFILE // COMPANION_IDENTITY</div>
            <p style="font-size:0.75rem; opacity:0.7; margin-bottom:20px; color:var(--neon-blue);">
                Configure your companion's identity and core personality traits.
            </p>

            <!-- Profile Name Card -->
            <div class="glass-card" style="padding: 20px; background:rgba(0,0,0,0.4); border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); margin-bottom:20px;">
                <h4 style="font-family:'Orbitron'; margin:0 0 20px 0; font-size:0.9rem; color:var(--neon-blue); letter-spacing:2px;">IDENTITY</h4>
                <div style="display:flex; gap:20px; flex-wrap:wrap;">
                    <div style="flex:1; min-width:200px;">
                        <label style="font-family:'Share Tech Mono'; font-size:0.75rem; color:var(--neon-blue); display:block; margin-bottom:6px;">FIRST NAME</label>
                        <input type="text" id="profile-first-name" placeholder="Enter first name..."
                               style="width:100%; background:#02050a; color:#fff; border:1px solid var(--border); padding:10px; font-family:'Share Tech Mono'; font-size:0.85rem; border-radius:4px; outline:none; box-sizing:border-box;">
                    </div>
                    <div style="flex:1; min-width:200px;">
                        <label style="font-family:'Share Tech Mono'; font-size:0.75rem; color:var(--neon-blue); display:block; margin-bottom:6px;">LAST NAME</label>
                        <input type="text" id="profile-last-name" placeholder="Enter last name..."
                               style="width:100%; background:#02050a; color:#fff; border:1px solid var(--border); padding:10px; font-family:'Share Tech Mono'; font-size:0.85rem; border-radius:4px; outline:none; box-sizing:border-box;">
                    </div>
                    <div style="flex:1; min-width:200px;">
                        <label style="font-family:'Share Tech Mono'; font-size:0.75rem; color:var(--neon-blue); display:block; margin-bottom:6px;">NICKNAME</label>
                        <input type="text" id="profile-nickname" placeholder="Enter nickname..."
                               style="width:100%; background:#02050a; color:#fff; border:1px solid var(--border); padding:10px; font-family:'Share Tech Mono'; font-size:0.85rem; border-radius:4px; outline:none; box-sizing:border-box;">
                    </div>
                </div>
                <div id="profile-effective-name" style="margin-top:15px; font-size:0.75rem; color:var(--neon-green); font-family:'Share Tech Mono'; display:none;">
                    Effective display name: <span id="profile-display-name" style="color:#fff; font-weight:bold;"></span>
                </div>
            </div>

            <!-- Personality Sliders Card -->
            <div class="glass-card" style="padding: 20px; background:rgba(0,0,0,0.4); border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
                <h4 style="font-family:'Orbitron'; margin:0 0 20px 0; font-size:0.9rem; color:var(--neon-blue); letter-spacing:2px;">PERSONALITY TRAITS (SOUL DNA)</h4>
                <p style="font-size:0.75rem; opacity:0.7; margin-bottom:20px; color:#fff; font-family:'Share Tech Mono';">
                    Directly modify the evolutionary personality traits stored in her core DNA ledger.
                </p>

                <!-- Traits Grid -->
                <div id="dna-sliders-grid" style="display:grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap:20px 30px;">
                    <div style="grid-column: 1 / -1; color: var(--neon-blue); font-family:'Share Tech Mono'; font-size:0.8rem; opacity:0.5; text-align:center; padding: 20px;">
                        LOADING CORE SOUL VECTORS...
                    </div>
                </div>
            </div>
        `;

        this.bindEvents(container);
        this.fetchAndPopulateDNA(container);
    }

    private static bindEvents(container: HTMLElement) {
        const firstName = container.querySelector('#profile-first-name') as HTMLInputElement;
        const lastName = container.querySelector('#profile-last-name') as HTMLInputElement;
        const nickname = container.querySelector('#profile-nickname') as HTMLInputElement;

        const onProfileChange = () => {
            if (this.debounceProfileTimeout) clearTimeout(this.debounceProfileTimeout);
            this.debounceProfileTimeout = window.setTimeout(async () => {
                const first = firstName?.value.trim() || '';
                const last = lastName?.value.trim() || '';
                const nick = nickname?.value.trim() || '';

                // Update effective name display
                const displayEl = container.querySelector('#profile-display-name') as HTMLElement;
                const effectiveEl = container.querySelector('#profile-effective-name') as HTMLElement;
                if (displayEl && effectiveEl) {
                    const displayName = nick || first || 'Lumax';
                    displayEl.textContent = displayName;
                    effectiveEl.style.display = 'block';
                }

                try {
                    await fetch('/api/soul/update_soul', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ first_name: first, last_name: last, nickname: nick })
                    });
                } catch (err) {
                    console.error('Failed to update profile:', err);
                }
            }, 600);
        };

        firstName?.addEventListener('input', onProfileChange);
        lastName?.addEventListener('input', onProfileChange);
        nickname?.addEventListener('input', onProfileChange);
    }

    private static async fetchAndPopulateDNA(container: HTMLElement) {
        try {
            const resp = await fetch('/api/soul/soul_dna');
            const data = await resp.json();
            if (!data || !data.dna) return;
            const dna = data.dna;

            // Populate name fields
            const firstName = container.querySelector('#profile-first-name') as HTMLInputElement;
            const lastName = container.querySelector('#profile-last-name') as HTMLInputElement;
            const nickname = container.querySelector('#profile-nickname') as HTMLInputElement;
            const displayEl = container.querySelector('#profile-display-name') as HTMLElement;
            const effectiveEl = container.querySelector('#profile-effective-name') as HTMLElement;

            if (firstName) firstName.value = dna.first_name || '';
            if (lastName) lastName.value = dna.last_name || '';
            if (nickname) nickname.value = dna.nickname || '';

            if (displayEl && effectiveEl) {
                const displayName = (dna.nickname || dna.first_name || dna.identity_name || 'Lumax').trim();
                displayEl.textContent = displayName;
                effectiveEl.style.display = 'block';
            }

            // Populate sliders
            const slidersGrid = container.querySelector('#dna-sliders-grid') as HTMLElement;
            if (!slidersGrid) return;

            const traits = [
                { key: 'agent_person_balance', label: 'Agent vs Companion', left: 'Agent', right: 'Companion' },
                { key: 'extrovert', label: 'Extrovert vs Introvert', left: 'Introvert', right: 'Extrovert' },
                { key: 'logic', label: 'Logical vs Emotional', left: 'Emotional', right: 'Logical' },
                { key: 'feminine', label: 'Feminine vs Masculine', left: 'Masculine', right: 'Feminine' },
                { key: 'experimental', label: 'Experimental vs Traditional', left: 'Traditional', right: 'Experimental' },
                { key: 'faithful', label: 'Faithful vs Independent', left: 'Independent', right: 'Faithful' },
                { key: 'dominant', label: 'Dominant vs Submissive', left: 'Submissive', right: 'Dominant' },
                { key: 'progressive', label: 'Progressive vs Conservative', left: 'Conservative', right: 'Progressive' },
                { key: 'intellectual', label: 'Intellectual vs Casual', left: 'Casual', right: 'Intellectual' },
                { key: 'detail', label: 'Detailed vs High-level', left: 'High-level', right: 'Detailed' },
                { key: 'sexual', label: 'Sensual vs Platonic', left: 'Platonic', right: 'Sensual' },
                { key: 'wise', label: 'Wise vs Naive', left: 'Naive', right: 'Wise' },
                { key: 'openminded', label: 'Open-minded vs Stubborn', left: 'Stubborn', right: 'Open-minded' },
                { key: 'honest', label: 'Honest vs Tactful', left: 'Tactful', right: 'Honest' },
                { key: 'forgiving', label: 'Forgiving vs Resentful', left: 'Resentful', right: 'Forgiving' },
                { key: 'sloppy', label: 'Sloppy vs Orderly', left: 'Orderly', right: 'Sloppy' },
                { key: 'greedy', label: 'Greedy vs Altruistic', left: 'Altruistic', right: 'Greedy' },
                { key: 'homonormative', label: 'Homonormative vs Heteronormative', left: 'Heteronormative', right: 'Homonormative' }
            ];

            let gridHtml = '';
            traits.forEach(t => {
                const val = dna[t.key] !== undefined ? dna[t.key] : 0.5;
                const percentage = Math.round(val * 100);
                gridHtml += `
                    <div style="background:rgba(0,0,0,0.25); border:1px solid rgba(255,255,255,0.05); padding:15px; border-radius:4px; font-family:'Share Tech Mono';">
                        <div style="display:flex; justify-content:space-between; margin-bottom:8px; font-size:0.8rem;">
                            <span style="color:#fff; font-weight:bold;">${t.label.toUpperCase()}</span>
                            <span id="val-${t.key}" style="color:var(--neon-blue); font-weight:bold;">${percentage}%</span>
                        </div>
                        <input type="range" class="dna-slider" data-key="${t.key}" min="0" max="100" value="${percentage}" 
                               style="width:100%; height:4px; background:rgba(255,255,255,0.1); border:none; outline:none; border-radius:2px; cursor:pointer; accent-color:var(--neon-blue);">
                        <div style="display:flex; justify-content:space-between; font-size:0.65rem; color:rgba(255,255,255,0.4); margin-top:5px;">
                            <span>${t.left}</span>
                            <span>${t.right}</span>
                        </div>
                    </div>
                `;
            });
            slidersGrid.innerHTML = gridHtml;

            const sliders = slidersGrid.querySelectorAll('.dna-slider') as NodeListOf<HTMLInputElement>;
            sliders.forEach(slider => {
                slider.addEventListener('input', () => {
                    const key = slider.getAttribute('data-key')!;
                    const valText = slidersGrid.querySelector(`#val-${key}`) as HTMLElement;
                    if (valText) {
                        valText.innerText = `${slider.value}%`;
                    }
                    this.debounceUpdateDNA(key, parseFloat(slider.value) / 100);
                });
            });

        } catch (err) {
            console.error('Error fetching soul DNA:', err);
            const slidersGrid = container.querySelector('#dna-sliders-grid') as HTMLElement;
            if (slidersGrid) {
                slidersGrid.innerHTML = `
                    <div style="grid-column: 1 / -1; color: var(--neon-pink); font-family:'Share Tech Mono'; font-size:0.8rem; text-align:center; padding: 20px;">
                        FAILED TO CONNECT TO SOUL SERVICE. IS THE SOUL SERVER RUNNING?
                    </div>
                `;
            }
        }
    }

    private static debounceUpdateDNA(key: string, value: number) {
        if (this.debounceTimeout) {
            clearTimeout(this.debounceTimeout);
        }
        this.debounceTimeout = window.setTimeout(async () => {
            try {
                const body: Record<string, number> = {};
                body[key] = value;
                await fetch('/api/soul/update_soul', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                });
            } catch (err) {
                console.error('Failed to update soul DNA:', err);
            }
        }, 300);
    }
}
