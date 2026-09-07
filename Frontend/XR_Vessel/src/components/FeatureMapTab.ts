export class FeatureMapTab {
    private static featureData: any = null;
    private static isLoading = false;
    private static searchFilter = '';
    private static tierFilter = 'ALL';

    public static async render(container: HTMLElement) {
        container.innerHTML = `
            <div class="breadcrumb">FEATURE INVENTORY & MAP</div>
            <div class="glass-card" style="padding: 20px; background:rgba(0,0,0,0.4); border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); display: flex; flex-direction: column; gap: 20px; min-height: 0; flex: 1;">
                
                <!-- Swarm Self-Augmentation Status Banner -->
                <div style="background: rgba(0, 243, 255, 0.05); border: 1px solid var(--neon-blue); border-radius: 4px; padding: 12px; font-family: 'Share Tech Mono', monospace; font-size: 0.7rem; line-height: 1.4;">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                        <span style="color: var(--neon-blue); font-weight: 700; letter-spacing: 1px;">🤖 SWARM SELF-AUGMENTATION ENGINE (ONLINE)</span>
                        <span style="color: var(--neon-green); animation: pulse 1.5s infinite;">● STANDBY // AUDITING CODEBASE</span>
                    </div>
                    <span style="color: #aaa;">Swarm drones can be tasked to run continuous autonomous chore queues. Select a Tier B/C blueprint module below to assign swarm self-augmentation priorities for automated code development and verification.</span>
                </div>

                <!-- Controls & Stats Bar -->
                <div style="display: flex; flex-wrap: wrap; gap: 15px; align-items: center; justify-content: space-between; background: rgba(0,0,0,0.3); padding: 12px 15px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.05);">
                    <div style="display: flex; gap: 10px; flex: 1; min-width: 250px;">
                        <input type="text" id="fmap-search" placeholder="Search features, paths, or keywords..." style="flex: 1; background: rgba(0,0,0,0.5); border: 1px solid var(--border); color: #fff; padding: 6px 12px; border-radius: 3px; font-family: 'Share Tech Mono', monospace; font-size: 0.75rem;">
                        <select id="fmap-tier-select" style="background: rgba(0,0,0,0.5); border: 1px solid var(--border); color: #fff; padding: 6px; border-radius: 3px; font-family: 'Share Tech Mono', monospace; font-size: 0.75rem;">
                            <option value="ALL">All Tiers</option>
                            <option value="A">Tier A (Completed)</option>
                            <option value="B">Tier B (In Progress)</option>
                            <option value="C">Tier C (Planned)</option>
                            <option value="D">Tier D (Conceptual)</option>
                        </select>
                    </div>
                    <div id="fmap-stats" style="display: flex; gap: 15px; font-family: 'Share Tech Mono', monospace; font-size: 0.7rem;">
                        <!-- Populate via JS -->
                        <span style="color: #666;">Scanning stats...</span>
                    </div>
                </div>

                <!-- Live Feature Table -->
                <div style="flex: 1; overflow-y: auto; border: 1px solid var(--border); border-radius: 4px; background: rgba(0,0,0,0.25);">
                    <table style="width: 100%; border-collapse: collapse; text-align: left; font-family: 'Share Tech Mono', monospace; font-size: 0.72rem;">
                        <thead>
                            <tr style="background: rgba(0, 243, 255, 0.08); border-bottom: 1px solid var(--border); color: var(--neon-blue); letter-spacing: 1px;">
                                <th style="padding: 10px; width: 30%;">FEATURE / CAPABILITY</th>
                                <th style="padding: 10px; width: 10%; text-align: center;">TIER</th>
                                <th style="padding: 10px; width: 45%;">NOTES / CAPABILITY MAPPING</th>
                                <th style="padding: 10px; width: 15%;">CATEGORY</th>
                            </tr>
                        </thead>
                        <tbody id="fmap-table-body">
                            <!-- Populate via JS -->
                            <tr>
                                <td colspan="4" style="padding: 30px; text-align: center; color: #888;">LOADING FEATURE INVENTORY DATA...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>

            </div>
        `;

        this.setupInteractions(container);
        await this.fetchFeatureMap();
    }

    private static async fetchFeatureMap() {
        if (this.isLoading) return;
        this.isLoading = true;

        try {
            const resp = await fetch('/api/fmap');
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            this.featureData = await resp.json();
            this.renderList();
        } catch (err) {
            console.error('[FeatureMap] Failed to load features:', err);
            const tbody = document.getElementById('fmap-table-body');
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="4" style="padding: 30px; text-align: center; color: var(--neon-pink);">
                            ⚠️ FAIL: Could not fetch feature inventory API. Ensure xr_app.py serves /api/fmap successfully.
                        </td>
                    </tr>
                `;
            }
        } finally {
            this.isLoading = false;
        }
    }

    private static renderList() {
        if (!this.featureData || !this.featureData.flat_rows) return;

        const tbody = document.getElementById('fmap-table-body');
        const statsEl = document.getElementById('fmap-stats');
        if (!tbody) return;

        const rows = this.featureData.flat_rows;
        
        // Filter rows
        const query = this.searchFilter.toLowerCase().trim();
        const filtered = rows.filter((r: any) => {
            const matchesSearch = !query || 
                r.label?.toLowerCase().includes(query) || 
                r.notes?.toLowerCase().includes(query) || 
                r.h2_title?.toLowerCase().includes(query) ||
                r.category?.toLowerCase().includes(query);
            
            const matchesTier = this.tierFilter === 'ALL' || r.tier === this.tierFilter;
            
            return matchesSearch && matchesTier;
        });

        // Compute dynamic stats
        const total = rows.length;
        const tierA = rows.filter((r: any) => r.tier === 'A').length;
        const tierB = rows.filter((r: any) => r.tier === 'B').length;
        const tierC = rows.filter((r: any) => r.tier === 'C').length;
        const tierD = rows.filter((r: any) => r.tier === 'D').length;

        if (statsEl) {
            statsEl.innerHTML = `
                <span style="color: #aaa;">TOTAL: <strong style="color: var(--neon-blue);">${total}</strong></span>
                <span style="color: var(--neon-green);">TIER A (DONE): <strong>${tierA}</strong></span>
                <span style="color: #ffaa00;">TIER B (WORK): <strong>${tierB}</strong></span>
                <span style="color: #00f3ff;">TIER C (PLAN): <strong>${tierC}</strong></span>
                <span style="color: var(--neon-pink);">TIER D (CONCEPT): <strong>${tierD}</strong></span>
            `;
        }

        if (filtered.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="4" style="padding: 30px; text-align: center; color: #666;">
                        No features matched filter options.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = filtered.map((r: any) => {
            const badgeStyle = this.getTierBadgeStyle(r.tier);
            const categoryLabel = this.featureData.categories?.find((c: any) => c.id === r.category)?.label || r.category;
            
            return `
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.15s; cursor: default;">
                    <td style="padding: 10px 12px; color: #fff; font-weight: bold; border-right: 1px solid rgba(255,255,255,0.03);">
                        <div style="font-size: 0.74rem;">${r.label}</div>
                        <div style="font-size: 0.6rem; color: #555; margin-top: 2px; text-transform: uppercase;">${r.h2_title} ${r.h3_title ? `// ${r.h3_title}` : ''}</div>
                    </td>
                    <td style="padding: 10px; text-align: center; border-right: 1px solid rgba(255,255,255,0.03);">
                        <span style="${badgeStyle}">${r.tier || '—'}</span>
                    </td>
                    <td style="padding: 10px 12px; color: #aaa; border-right: 1px solid rgba(255,255,255,0.03); line-height: 1.35;">
                        ${r.notes || '—'}
                    </td>
                    <td style="padding: 10px 12px; color: var(--neon-blue); opacity: 0.85;">
                        ${categoryLabel}
                    </td>
                </tr>
            `;
        }).join('');

        // Wire hover visual effect
        tbody.querySelectorAll('tr').forEach(tr => {
            tr.addEventListener('mouseenter', () => {
                tr.style.background = 'rgba(0, 243, 255, 0.04)';
            });
            tr.addEventListener('mouseleave', () => {
                tr.style.background = 'transparent';
            });
        });
    }

    private static getTierBadgeStyle(tier: string): string {
        const base = "display: inline-block; padding: 2px 8px; font-size: 0.58rem; border-radius: 2px; font-weight: 700; letter-spacing: 0.5px;";
        if (tier === 'A') return base + "background: rgba(57,255,20,0.15); border: 1px solid var(--neon-green); color: var(--neon-green); text-shadow: 0 0 4px var(--neon-green);";
        if (tier === 'B') return base + "background: rgba(255,170,0,0.15); border: 1px solid #ffaa00; color: #ffaa00; text-shadow: 0 0 4px #ffaa00;";
        if (tier === 'C') return base + "background: rgba(0,243,255,0.15); border: 1px solid var(--neon-blue); color: var(--neon-blue); text-shadow: 0 0 4px var(--neon-blue);";
        if (tier === 'D') return base + "background: rgba(255,0,127,0.15); border: 1px solid var(--neon-pink); color: var(--neon-pink); text-shadow: 0 0 4px var(--neon-pink);";
        return base + "background: rgba(255,255,255,0.05); border: 1px solid #555; color: #888;";
    }

    private static setupInteractions(container: HTMLElement) {
        const searchInput = container.querySelector('#fmap-search') as HTMLInputElement;
        const tierSelect = container.querySelector('#fmap-tier-select') as HTMLSelectElement;

        searchInput?.addEventListener('input', () => {
            this.searchFilter = searchInput.value;
            this.renderList();
        });

        tierSelect?.addEventListener('change', () => {
            this.tierFilter = tierSelect.value;
            this.renderList();
        });
    }
}
