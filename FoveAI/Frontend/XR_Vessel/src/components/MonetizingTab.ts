export class MonetizingTab {
    private static swarmState = {
        agents: [] as any[],
        opportunities: [] as any[],
        creds: {
            apiKey: '',
            apiSecret: '',
            wallet: '',
            maxLoss: 100,
            maxPositions: 3
        }
    };

    private static ideas: any[] = [];
    private static activePlan: any = null;
    private static isScanning = false;
    private static isCertifying: { [key: string]: boolean } = {};
    private static isPlanning: { [key: string]: boolean } = {};

    public static render(container: HTMLElement) {
        container.innerHTML = `
            <div class="breadcrumb">FoveAI MONETIZING AGENTS (COINEX / CET GRINDING)</div>
            <div class="glass-card" style="margin-bottom: 20px; padding: 16px; background:rgba(0,0,0,0.4); border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
                <div style="display: flex; gap: 16px; align-items: center;">
                    <div style="flex: 1;">
                        <h4 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-green); letter-spacing:2px;">LIVE BALANCE (CET)</h4>
                        <div id="monetizing-total-earnings" style="font-size: 1.8rem; font-weight: 700; color: var(--neon-green);">0.00 CET</div>
                        <div style="margin-top: 8px; font-size: 0.8rem; color: rgba(255,255,255,0.6);">        
                            <span id="monetizing-solana-address" style="font-family:'Share Tech Mono'; color: var(--neon-blue);">CET Trading Active</span> | 
                            Profit: <span id="monetizing-session-profit" style="color: var(--neon-green);">$0.00</span>
                        </div>
                    </div>

                    <div style="flex: 1;">
                        <h4 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:2px;">RISK STATUS</h4>
                        <div id="monetizing-risk-status" style="font-size: 1.2rem; font-weight: 700; color: var(--neon-green);">OPERATIONAL</div>
                        <div style="margin-top: 8px; font-size: 0.7rem; color: rgba(255,255,255,0.6);">
                            Max daily loss: <span id="monetizing-max-loss" style="color: #ffaa00;">$100</span> | 
                            Positions remaining: <span id="monetizing-positions-remaining" style="color: var(--neon-blue);">3</span>
                        </div>
                    </div>
                </div>
            </div>

            <div style="display:flex; gap:20px; margin-bottom:20px;">
                <!-- Left: Agent Controls -->
                <div class="glass-card" style="flex: 1; padding: 16px; background:rgba(0,0,0,0.4); border:1px solid var(--border); border-radius:4px;">
                    <h4 style="font-family:'Orbitron'; margin:0 0 15px 0; font-size:0.9rem; color:var(--neon-blue); letter-spacing:2px;">SWARM CONTROL</h4>
                    <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom:15px;">
                        <button id="btn-start-swarm" style="flex: 1; padding: 12px; background: rgba(57, 255, 20, 0.2); border: 1px solid var(--neon-green); color: var(--neon-green); font-family:'Orbitron'; cursor:pointer;">🚀 START</button>
                        <button id="btn-pause-swarm" style="flex: 1; padding: 12px; background: rgba(255, 0, 127, 0.2); border: 1px solid var(--neon-pink); color: var(--neon-pink); font-family:'Orbitron'; cursor:pointer;">⏸️ PAUSE</button>
                    </div>

                    <div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 16px;">
                        <h5 style="font-family:'Orbitron'; margin:0 0 12px 0; font-size:0.8rem; color:var(--neon-blue);">Forge Agent</h5>
                        <div style="display: flex; flex-direction: column; gap: 8px;">
                            <input type="text" id="agent-name-input" placeholder="Agent Name..." style="padding: 10px; background: rgba(0,0,0,0.3); border: 1px solid var(--neon-blue); color: #fff; font-family:'Share Tech Mono'; outline:none;">
                            <select id="agent-type-input" style="padding: 10px; background: rgba(0,0,0,0.3); border: 1px solid var(--neon-blue); color: #fff; font-family:'Share Tech Mono'; outline:none;">
                                <option value="crypto_trading">Crypto Trading</option>
                                <option value="affiliate_marketing">Affiliate Marketing</option>
                                <option value="ad_revenue">Ad Revenue</option>
                            </select>
                            <button id="btn-add-agent" class="neon-btn" style="padding: 10px; background: var(--neon-blue); color: #000; font-family:'Orbitron'; cursor:pointer; font-weight:700;">DEPLOY AGENT</button>
                        </div>
                    </div>
                </div>

                <!-- Right: Status -->
                <div class="glass-card" style="flex: 1; padding: 16px; background:rgba(0,0,0,0.4); border:1px solid var(--border); border-radius:4px;">
                    <h4 style="font-family:'Orbitron'; margin:0 0 15px 0; font-size:0.9rem; color:var(--neon-blue); letter-spacing:2px;">SWARM STATUS</h4>
                    <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--neon-blue); padding: 12px; border-radius: 4px; margin-bottom:15px; font-family:'Share Tech Mono'; font-size:0.8rem;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                            <span>Active Agents:</span><span id="swarm-active-agents" style="color: var(--neon-green);">0</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                            <span>Pending Tasks:</span><span id="swarm-pending-tasks" style="color: #ffaa00;">0</span>
                        </div>
                        <div style="display: flex; justify-content: space-between;">
                            <span>Completed:</span><span id="swarm-completed-tasks" style="color: var(--neon-blue);">0</span>
                        </div>
                    </div>
                    <div id="monetizing-agents-list" style="display: flex; flex-direction: column; gap: 8px; max-height:150px; overflow-y:auto;">
                        <div style="color: rgba(255,255,255,0.4); text-align: center; font-size:0.8rem; padding:20px;">No agents deployed.</div>
                    </div>
                    
                    <!-- Agent Detail HUD Monitor -->
                    <div id="agent-monitor-container" style="display:none; margin-top:15px; padding: 12px; background: rgba(0,0,0,0.5); border: 1px solid var(--neon-blue); border-radius: 4px; font-family:'Share Tech Mono'; font-size:0.75rem;">
                        <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.2); padding-bottom:6px; margin-bottom:10px;">
                            <h4 style="font-family:'Orbitron'; margin:0; font-size:0.8rem; color:var(--neon-blue); letter-spacing:1px; display:flex; align-items:center; gap:6px;">
                                <span>📺 REALTIME MONITOR:</span> <span id="monitor-agent-name" style="color:var(--neon-green);">None</span>
                            </h4>
                            <button id="btn-close-monitor" style="background:none; border:none; color:rgba(255,255,255,0.6); font-size:1.1rem; cursor:pointer;">✖</button>
                        </div>
                        <div style="display:flex; gap:16px; margin-bottom:10px;">
                            <div style="flex:1;">
                                <div>ID: <span id="monitor-agent-id" style="color:var(--neon-blue);">None</span></div>
                                <div>Status: <span id="monitor-agent-status" style="color:var(--neon-green);">None</span></div>
                            </div>
                            <div style="flex:1;">
                                <div>Tasks Completed: <span id="monitor-agent-tasks" style="color:#ffaa00;">0</span></div>
                                <div>Earnings Generated: <span id="monitor-agent-earnings" style="color:var(--neon-green); font-weight:700;">$0.00</span></div>
                            </div>
                        </div>
                        <div style="background:rgba(0,0,0,0.4); border:1px solid rgba(255,255,255,0.1); padding:8px; border-radius:2px; font-size:0.65rem;">
                            <div style="font-weight:700; color:var(--neon-blue); margin-bottom:4px;">CURRENT ACTIVE TASK:</div>
                            <div id="monitor-active-task" style="color:rgba(255,255,255,0.8); line-height:1.3;">Awaiting task allocation from Swarm Orchestrator...</div>
                            <div style="font-weight:700; color:var(--neon-blue); margin-top:8px; margin-bottom:4px;">LAST TELEMETRY SEARCH:</div>
                            <div id="monitor-last-search" style="color:rgba(255,255,255,0.6);">None recorded.</div>
                        </div>
                    </div>
                </div>
            </div>

            <style>
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
                .badge {
                    display: inline-block;
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-size: 0.65rem;
                    font-weight: 700;
                    text-transform: uppercase;
                }
                .badge-cryptotrading { background: rgba(0, 191, 255, 0.2); border: 1px solid #00bfff; color: #00bfff; }
                .badge-affiliatemarketing { background: rgba(255, 0, 127, 0.2); border: 1px solid #ff007f; color: #ff007f; }
                .badge-adrevenue { background: rgba(57, 255, 20, 0.2); border: 1px solid #39ff14; color: #39ff14; }
                .badge-saas { background: rgba(186, 85, 211, 0.2); border: 1px solid #ba55d3; color: #ba55d3; }
                .badge-contentcreation { background: rgba(255, 165, 0, 0.2); border: 1px solid #ffa500; color: #ffa500; }
                .badge-freelancing { background: rgba(0, 255, 255, 0.2); border: 1px solid #00ffff; color: #00ffff; }
                .badge-ecommerce { background: rgba(238, 130, 238, 0.2); border: 1px solid #ee82ee; color: #ee82ee; }
                .badge-dropshipping { background: rgba(127, 255, 212, 0.2); border: 1px solid #7fffd4; color: #7fffd4; }
                .badge-licensing { background: rgba(245, 222, 179, 0.2); border: 1px solid #f5deb3; color: #f5deb3; }
                .badge-consulting { background: rgba(211, 211, 211, 0.2); border: 1px solid #d3d3d3; color: #d3d3d3; }
                
                .idea-row:hover {
                    background: rgba(255, 255, 255, 0.03);
                }
            </style>

            <div class="glass-card" style="margin-bottom: 20px; padding: 16px; background:rgba(0,0,0,0.4); border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:10px;">
                    <h4 style="font-family:'Orbitron'; margin:0; font-size:0.9rem; color:var(--neon-green); letter-spacing:2px; display:flex; align-items:center; gap:8px;">
                        <span>💡 IDEA LAB & STRATEGY ENGINE</span>
                    </h4>
                    <button id="btn-scan-ideas" class="neon-btn" style="padding: 6px 16px; background: rgba(57, 255, 20, 0.2); border: 1px solid var(--neon-green); color: var(--neon-green); font-family:'Orbitron'; font-size:0.7rem; cursor:pointer; font-weight:700; display:flex; align-items:center; gap:6px;">
                        <span id="scan-spinner" style="display:none; width:12px; height:12px; border:2px solid var(--neon-green); border-top-color:transparent; border-radius:50%; animation:spin 1s linear infinite;"></span>
                        <span id="scan-text">SCAN FOR STRATEGIES</span>
                    </button>
                </div>
                
                <div id="ideas-table-container" style="max-height: 350px; overflow-y: auto; font-family:'Share Tech Mono'; font-size:0.8rem;">
                    <div style="color: rgba(255,255,255,0.4); text-align: center; padding: 30px 20px;">
                        Loading monetizing ideas...
                    </div>
                </div>
                
                <div id="ideas-plan-container" style="display:none; margin-top:15px; padding: 12px; background: rgba(0,0,0,0.5); border: 1px solid var(--neon-blue); border-radius: 4px; font-family:'Share Tech Mono'; font-size:0.8rem;">
                </div>
            </div>

            <div class="glass-card" style="margin-bottom: 20px; padding: 16px; background:rgba(0,0,0,0.4); border:1px solid var(--border); border-radius:4px;">
                <h4 style="font-family:'Orbitron'; margin:0 0 15px 0; font-size:0.9rem; color:var(--neon-pink); letter-spacing:2px;">API CONFIGURATION</h4>
                <div style="display:flex; gap:20px;">
                    <div style="flex:1;">
                        <input type="password" id="coinex-api-key" placeholder="CoinEx Access ID" style="width:100%; padding: 10px; background: rgba(0,0,0,0.3); border: 1px solid var(--neon-pink); color: #fff; font-family:'Share Tech Mono'; margin-bottom:10px; outline:none; box-sizing:border-box;">
                        <input type="password" id="coinex-api-secret" placeholder="CoinEx Secret Key" style="width:100%; padding: 10px; background: rgba(0,0,0,0.3); border: 1px solid var(--neon-pink); color: #fff; font-family:'Share Tech Mono'; margin-bottom:10px; outline:none; box-sizing:border-box;">
                        <input type="text" id="solana-wallet-address" placeholder="Solana Wallet Address" style="width:100%; padding: 10px; background: rgba(0,0,0,0.3); border: 1px solid var(--neon-green); color: #fff; font-family:'Share Tech Mono'; margin-bottom:10px; outline:none; box-sizing:border-box;">
                        <button id="btn-save-creds" class="neon-btn" style="width:100%; padding: 10px; background: var(--neon-pink); color: #fff; border:none; font-family:'Orbitron'; cursor:pointer; font-weight:700;">SAVE CREDENTIALS</button>
                    </div>
                    <div style="flex:1; display:flex; flex-direction:column; gap:10px;">
                        <div>
                            <label style="font-family:'Share Tech Mono'; font-size:0.7rem; opacity:0.7;">Daily Loss Limit ($)</label>
                            <input type="number" id="risk-daily-loss" value="100" style="width:100%; padding: 8px; background: rgba(0,0,0,0.3); border: 1px solid var(--neon-pink); color: #fff; box-sizing:border-box;">
                        </div>
                        <div>
                            <label style="font-family:'Share Tech Mono'; font-size:0.7rem; opacity:0.7;">Max Positions</label>
                            <input type="number" id="risk-max-positions" value="3" style="width:100%; padding: 8px; background: rgba(0,0,0,0.3); border: 1px solid var(--neon-pink); color: #fff; box-sizing:border-box;">
                        </div>
                    </div>
                </div>
            </div>

            <div id="monetizing-audit-log" style="background: rgba(0,0,0,0.5); border: 1px solid var(--neon-blue); padding: 16px; border-radius: 4px; max-height: 150px; overflow-y: auto; font-family:'Share Tech Mono'; font-size: 0.7rem;">
                <h4 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-blue);">AUDIT LOG</h4>
                <div id="audit-log-content">
                    <div style="color: var(--neon-blue); opacity: 0.5;">[System] Initialized. Awaiting configuration...</div>
                </div>
            </div>
        `;

        this.bindEvents(container);
        this.loadState(container);
    }

    private static async fetchStatus(container: HTMLElement) {
        try {
            const resp = await fetch('/monetize/status');
            const data = await resp.json();
            
            if (data.error) {
                this.log(container, `System Status: ${data.error}`, 'var(--neon-pink)');
                return;
            }

            // Update Vitals
            const earnings = container.querySelector('#monetizing-total-earnings') as HTMLElement;
            const walletDisplay = container.querySelector('#monetizing-solana-address') as HTMLElement;
            const riskStatus = container.querySelector('#monetizing-risk-status') as HTMLElement;
            const maxLoss = container.querySelector('#monetizing-max-loss') as HTMLElement;
            const positions = container.querySelector('#monetizing-positions-remaining') as HTMLElement;

            if (data.wallet) {
                walletDisplay.innerText = data.wallet.substring(0, 8) + '...' + data.wallet.substring(data.wallet.length - 4);
                walletDisplay.style.color = 'var(--neon-blue)';
            } else {
                walletDisplay.innerText = 'Not connected';
                walletDisplay.style.color = 'rgba(255,255,255,0.4)';
            }
            
            // Show ACTUAL balance in the big green area
            // Prioritize CET if available, else SOL
            if (data.cet_balance > 0) {
                earnings.innerText = `${data.cet_balance.toFixed(2)} CET`;
            } else {
                earnings.innerText = `${(data.balance || 0).toFixed(4)} SOL`;
            }
            earnings.style.color = 'var(--neon-green)';

            // Show simulated/tracked profit below
            const profitDisplay = container.querySelector('#monetizing-session-profit') as HTMLElement;
            if (profitDisplay) {
                profitDisplay.innerText = `${(data.earnings || 0).toFixed(4)} SOL`;
            }

            // Repopulate input fields if they are empty (avoids clearing user typing)
            const solInput = container.querySelector('#solana-wallet-address') as HTMLInputElement;
            if (solInput && !solInput.value && data.wallet) {
                solInput.value = data.wallet;
            }
            
            // Visual feedback for persisted keys
            const keyInput = container.querySelector('#coinex-api-key') as HTMLInputElement;
            const secretInput = container.querySelector('#coinex-api-secret') as HTMLInputElement;
            if (data.has_coinex_keys) {
                if (keyInput && !keyInput.value) keyInput.value = "********";
                if (secretInput && !secretInput.value) secretInput.value = "********";
            }

            riskStatus.innerText = data.risk.current_positions > 0 ? 'OPERATIONAL' : 'STANDBY';
            riskStatus.style.color = data.risk.current_positions > 0 ? 'var(--neon-green)' : 'var(--neon-blue)';
            
            if (maxLoss) maxLoss.innerText = `$${data.risk.daily_loss_limit}`;
            if (positions) positions.innerText = data.risk.positions_remaining.toString();

            // Sync input fields if they aren't being edited
            const lossInput = container.querySelector('#risk-daily-loss') as HTMLInputElement;
            const posInput = container.querySelector('#risk-max-positions') as HTMLInputElement;
            if (lossInput && document.activeElement !== lossInput) lossInput.value = data.risk.daily_loss_limit.toString();
            if (posInput && document.activeElement !== posInput) posInput.value = data.risk.max_concurrent_positions.toString();

            // Update Agents List
            const list = container.querySelector('#monetizing-agents-list') as HTMLElement;
            const activeCount = container.querySelector('#swarm-active-agents') as HTMLElement;
            
            let html = '';
            let active = 0;
            if (data.agents && Array.isArray(data.agents) && data.agents.length > 0) {
                data.agents.forEach((agent: any) => {
                    const status = agent.status || 'idle';
                    if (['executing', 'searching', 'analyzing'].includes(status)) active++;
                    const color = status === 'executing' ? 'var(--neon-green)' 
                                : status === 'searching' ? '#ffaa00'
                                : status === 'analyzing' ? '#00bfff'
                                : status === 'paused' ? 'rgba(255,255,255,0.3)'
                                : status === 'error' ? 'var(--neon-pink)'
                                : 'rgba(255,255,255,0.6)';
                    
                    const statusIcon = status === 'executing' ? '⚡' 
                                    : status === 'searching' ? '🔍'
                                    : status === 'analyzing' ? '🧠'
                                    : status === 'paused' ? '⏸'
                                    : status === 'idle' ? '💤'
                                    : status === 'error' ? '❌' : '•';
                    
                    const lastSearch = agent.last_search || 'None';
                    const currentTask = agent.current_task;
                    const activeTask = currentTask 
                        ? `[${currentTask.task_id}] ${currentTask.opportunity?.name || currentTask.type} — ${currentTask.notes || 'running...'} (${Math.round(currentTask.progress || 0)}%)`
                        : 'Awaiting task allocation from Swarm Orchestrator...';
                    
                    const isLive = agent.is_live === true;
                    const hasCredentials = agent.has_credentials !== false;
                    const liveBadge = isLive
                        ? (hasCredentials 
                            ? `<span style="background:rgba(57,255,20,0.15); border:1px solid var(--neon-green); color:var(--neon-green); font-size:0.5rem; padding:1px 5px; border-radius:2px; font-family:'Orbitron'; font-weight:700;">🟢 LIVE</span>`
                            : `<span style="background:rgba(255,170,0,0.15); border:1px solid #ffaa00; color:#ffaa00; font-size:0.5rem; padding:1px 5px; border-radius:2px; font-family:'Orbitron'; font-weight:700;">🟢 LIVE ⚠️ NO KEYS</span>`)
                        : `<span style="background:rgba(255,0,127,0.1); border:1px solid rgba(255,0,127,0.4); color:rgba(255,0,127,0.8); font-size:0.5rem; padding:1px 5px; border-radius:2px; font-family:'Orbitron'; font-weight:700;">🔴 SIM</span>`;

                    html += `
                    <div class="agent-card" data-id="${agent.agent_id}" data-name="${agent.name}" data-status="${status}" data-tasks="${agent.total_tasks_completed}" data-earnings="${(agent.total_earnings || 0).toFixed(4)}" data-last-search="${lastSearch}" data-active-task="${activeTask}" style="background: rgba(0,0,0,0.3); border: 1px solid ${isLive ? 'rgba(57,255,20,0.3)' : 'var(--border)'}; padding: 10px; border-radius: 4px; margin-bottom:5px; position:relative; cursor:pointer; transition: background 0.2s;">
                        <button class="btn-delete-agent" data-id="${agent.agent_id}" style="position:absolute; right:8px; top:8px; background:none; border:none; color:var(--neon-pink); cursor:pointer; font-size:0.85rem; font-weight:700; z-index: 10;" title="Terminate Agent">✖</button>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-right: 18px;">
                            <div style="display:flex; align-items:center; gap:6px;">
                                <strong style="font-family:'Orbitron'; color:var(--neon-blue);">${agent.name}</strong>
                                ${liveBadge}
                            </div>
                            <span style="font-family:'Share Tech Mono'; color:${color}; font-size:0.7rem;">${statusIcon} ${status.toUpperCase()}</span>
                        </div>
                        <div style="font-size: 0.6rem; margin-top:5px; opacity:0.8;">Earned: $${(agent.total_earnings || 0).toFixed(2)} USD | Tasks: ${agent.total_tasks_completed} <span style="opacity:0.5; font-size:0.55rem;">${agent.agent_id}</span></div>
                        ${currentTask ? `<div style="font-size:0.58rem; margin-top:3px; color:${color}; opacity:0.9;">↳ ${currentTask.notes || currentTask.type}</div>` : ''}
                    </div>`;
                });
            }
            
            if (list) {
                list.innerHTML = html || '<div style="color: rgba(255,255,255,0.4); text-align: center; font-size:0.8rem; padding:20px;">No agents deployed.</div>';
            }
            if (activeCount) activeCount.innerText = active.toString();

            // Update swarm-level task counters
            const pendingEl = container.querySelector('#swarm-pending-tasks') as HTMLElement;
            const completedEl = container.querySelector('#swarm-completed-tasks') as HTMLElement;
            if (data.swarm) {
                if (pendingEl) pendingEl.innerText = (data.swarm.approved_tasks || 0).toString();
                if (completedEl) completedEl.innerText = (data.swarm.completed_tasks || 0).toString();
            }

            // Bind actions for agents list (clicks and delete)
            if (data.agents && Array.isArray(data.agents) && data.agents.length > 0) {
                const cards = container.querySelectorAll('.agent-card');
                cards.forEach(card => {
                    card.addEventListener('click', (e) => {
                        const target = e.target as HTMLElement;
                        if (target.classList.contains('btn-delete-agent') || target.parentElement?.classList.contains('btn-delete-agent')) {
                            return;
                        }
                        
                        const id = card.getAttribute('data-id') || 'None';
                        const name = card.getAttribute('data-name') || 'None';
                        const status = card.getAttribute('data-status') || 'None';
                        const tasks = card.getAttribute('data-tasks') || '0';
                        const earnings = card.getAttribute('data-earnings') || '0.00';
                        const lastSearch = card.getAttribute('data-last-search') || 'None';
                        const activeTask = card.getAttribute('data-active-task') || 'None';
                        
                        const monitor = container.querySelector('#agent-monitor-container') as HTMLElement;
                        if (monitor) {
                            monitor.style.display = 'block';
                            (monitor.querySelector('#monitor-agent-name') as HTMLElement).innerText = name;
                            (monitor.querySelector('#monitor-agent-id') as HTMLElement).innerText = id;
                            (monitor.querySelector('#monitor-agent-status') as HTMLElement).innerText = status.toUpperCase();
                            (monitor.querySelector('#monitor-agent-tasks') as HTMLElement).innerText = tasks;
                            (monitor.querySelector('#monitor-agent-earnings') as HTMLElement).innerText = `$${earnings}`;
                            (monitor.querySelector('#monitor-active-task') as HTMLElement).innerText = activeTask;
                            (monitor.querySelector('#monitor-last-search') as HTMLElement).innerText = lastSearch;
                        }
                    });
                });
                
                const deleteBtns = container.querySelectorAll('.btn-delete-agent');
                deleteBtns.forEach(btn => {
                    btn.addEventListener('click', async (e) => {
                        e.stopPropagation();
                        const id = btn.getAttribute('data-id');
                        if (!id) return;
                        
                        if (confirm(`Are you sure you want to terminate and delete Swarm Agent ${id}?`)) {
                            this.log(container, `Terminating and removing agent ${id}...`, 'var(--neon-pink)');
                            try {
                                const formData = new FormData();
                                formData.append('agent_id', id);
                                
                                const resp = await fetch('/monetize/remove_agent', {
                                    method: 'POST',
                                    body: formData
                                });
                                const res = await resp.json();
                                if (res.status === 'removed') {
                                    this.log(container, `Agent ${id} terminated successfully.`, 'var(--neon-green)');
                                    
                                    const monitor = container.querySelector('#agent-monitor-container') as HTMLElement;
                                    const monitorId = monitor?.querySelector('#monitor-agent-id') as HTMLElement;
                                    if (monitor && monitorId && monitorId.innerText === id) {
                                        monitor.style.display = 'none';
                                    }
                                }
                            } catch (err) {
                                console.error('Failed to remove agent', err);
                                this.log(container, `Failed to terminate agent ${id}`, 'var(--neon-pink)');
                            } finally {
                                this.fetchStatus(container);
                            }
                        }
                    });
                });
            }

            // Update Audit Log from Server
            const logArea = container.querySelector('#audit-log-content') as HTMLElement;
            if (logArea && data.audit) {
                logArea.innerHTML = data.audit.map((e: any) => `<div><span style="color:var(--neon-blue);">[${new Date(e.timestamp).toLocaleTimeString()}]</span> ${e.action}</div>`).join('');
            }

        } catch (e) {
            console.error('Failed to fetch monetizing status', e);
        }
    }

    private static bindEvents(container: HTMLElement) {
        const btnAdd = container.querySelector('#btn-add-agent');
        const btnStart = container.querySelector('#btn-start-swarm');
        const btnPause = container.querySelector('#btn-pause-swarm');
        const btnSave = container.querySelector('#btn-save-creds');

        btnAdd?.addEventListener('click', async () => {
            const nameInput = container.querySelector('#agent-name-input') as HTMLInputElement;
            const typeInput = container.querySelector('#agent-type-input') as HTMLSelectElement;
            const name = nameInput.value.trim();
            if (!name) return;

            const formData = new FormData();
            formData.append('name', name);
            formData.append('type', typeInput.value);

            await fetch('/monetize/add_agent', { method: 'POST', body: formData });
            nameInput.value = '';
            this.fetchStatus(container);
        });

        btnStart?.addEventListener('click', async () => {
            await fetch('/monetize/control', { 
                method: 'POST', 
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'start' }) 
            });
            this.fetchStatus(container);
        });

        btnPause?.addEventListener('click', async () => {
            await fetch('/monetize/control', { 
                method: 'POST', 
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'pause' }) 
            });
            this.fetchStatus(container);
        });

        btnSave?.addEventListener('click', async () => {
            const key = (container.querySelector('#coinex-api-key') as HTMLInputElement).value.trim();
            const secret = (container.querySelector('#coinex-api-secret') as HTMLInputElement).value.trim();
            const sol = (container.querySelector('#solana-wallet-address') as HTMLInputElement).value.trim();
            const loss = (container.querySelector('#risk-daily-loss') as HTMLInputElement).value;
            const pos = (container.querySelector('#risk-max-positions') as HTMLInputElement).value;

            await fetch('/monetize/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    apiKey: key,
                    apiSecret: secret,
                    wallet: sol,
                    maxLoss: parseInt(loss) || 100,
                    maxPositions: parseInt(pos) || 3
                })
            });
            
            this.fetchStatus(container);
            this.log(container, 'Configuration synchronized with server.', 'var(--neon-green)');
        });

        const closeMonitor = container.querySelector('#btn-close-monitor');
        closeMonitor?.addEventListener('click', () => {
            const monitor = container.querySelector('#agent-monitor-container') as HTMLElement;
            if (monitor) monitor.style.display = 'none';
        });

        const btnScan = container.querySelector('#btn-scan-ideas');
        btnScan?.addEventListener('click', async () => {
            if (this.isScanning) return;
            
            this.isScanning = true;
            const spinner = container.querySelector('#scan-spinner') as HTMLElement;
            const btnText = container.querySelector('#scan-text') as HTMLElement;
            if (spinner) spinner.style.display = 'inline-block';
            if (btnText) btnText.innerText = 'SCANNING...';
            
            this.log(container, 'Launching Monetizing Idea Lab Scanner...', '#ffaa00');
            
            try {
                const resp = await fetch('/monetize/ideas/scan', { method: 'POST' });
                const result = await resp.json();
                
                this.log(container, `Scanning successfully complete! Discovered ${result.discovered_count} strategies.`, 'var(--neon-green)');
                await this.fetchIdeas(container);
            } catch (err) {
                console.error('Idea scanning failed', err);
                this.log(container, 'Idea scanning failed', 'var(--neon-pink)');
            } finally {
                this.isScanning = false;
                if (spinner) spinner.style.display = 'none';
                if (btnText) btnText.innerText = 'SCAN FOR STRATEGIES';
            }
        });

        // Start Auto-Refresh Loop
        const refreshInterval = setInterval(() => {
            if (document.contains(container)) {
                this.fetchStatus(container);
            } else {
                clearInterval(refreshInterval);
            }
        }, 5000);
    }

    private static async fetchIdeas(container: HTMLElement) {
        try {
            const resp = await fetch('/monetize/ideas');
            const data = await resp.json();
            if (data.ideas) {
                this.ideas = data.ideas;
                this.renderIdeasTable(container);
            }
        } catch (e) {
            console.error('Failed to fetch ideas list', e);
        }
    }

    private static renderIdeasTable(container: HTMLElement) {
        const tableContainer = container.querySelector('#ideas-table-container') as HTMLElement;
        if (!tableContainer) return;
        
        let html = `
        <table style="width: 100%; border-collapse: collapse; text-align: left; table-layout: fixed;">
            <thead>
                <tr style="border-bottom: 1px solid rgba(255,255,255,0.2); opacity: 0.8; font-size: 0.7rem; letter-spacing: 1px;">
                    <th style="padding: 8px 6px; width: 65%;">STRATEGY DETAILS</th>
                    <th style="padding: 8px 6px; text-align: right; width: 35%;">ACTIONS</th>
                </tr>
            </thead>
            <tbody>
        `;

        if (this.ideas.length === 0) {
            html += `
                <tr>
                    <td colspan="2" style="text-align: center; padding: 30px; color: rgba(255,255,255,0.4);">
                        No strategies discovered. Click "SCAN FOR STRATEGIES" to search online databases.
                    </td>
                </tr>
            `;
        } else {
            this.ideas.forEach(idea => {
                const catClass = `badge-${idea.category.toLowerCase().replace('_', '')}`;
                
                const complexityVal = String(idea.complexity || '0');
                const complexityLower = complexityVal.toLowerCase();
                const complexityColor = (complexityLower === 'high' || complexityLower === '5') ? 'var(--neon-pink)' : (complexityLower === 'medium' || complexityLower === '3' || complexityLower === '4') ? '#ffaa00' : 'var(--neon-green)';
                
                const isCertifying = this.isCertifying[idea.id];
                const isPlanning = this.isPlanning[idea.id];
                
                let certText = 'UNTESTED';
                let certColor = 'rgba(255,255,255,0.4)';
                let certBg = 'rgba(255,255,255,0.05)';
                let certBorder = 'rgba(255,255,255,0.2)';
                
                if (idea.certified) {
                    certText = `CERTIFIED (${idea.cert_status.toUpperCase()})`;
                    certColor = idea.cert_status === 'failed' ? 'var(--neon-pink)' : 'var(--neon-green)';
                    certBg = idea.cert_status === 'failed' ? 'rgba(255, 0, 127, 0.1)' : 'rgba(57, 255, 20, 0.1)';
                    certBorder = idea.cert_status === 'failed' ? 'var(--neon-pink)' : 'var(--neon-green)';
                }
                
                html += `
                <tr class="idea-row" style="border-bottom: 1px solid rgba(255,255,255,0.05); font-size:0.75rem;">
                    <td style="padding: 8px 6px; overflow: hidden; text-overflow: ellipsis;">
                        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 4px;">
                            <span class="badge ${catClass}" style="font-size: 0.55rem; padding: 1px 4px;">${idea.category.replace('_', ' ')}</span>
                            <strong style="color: var(--neon-blue); font-size: 0.8rem;">${idea.title}</strong>
                        </div>
                        <div style="font-size: 0.65rem; opacity: 0.7; margin-bottom: 4px; line-height: 1.2;">${idea.description}</div>
                        <div style="display: flex; gap: 10px; font-size: 0.65rem; opacity: 0.9; color: rgba(255,255,255,0.6); font-family: 'Share Tech Mono'; flex-wrap: wrap;">
                            <span>Est: <strong style="color: var(--neon-green); font-weight:700;">$${(Number(idea.estimated_revenue_month) || 0).toFixed(0)}/mo</strong></span>
                            <span>Complexity: <strong style="color: ${complexityColor};">${complexityVal}</strong></span>
                            <span>Score: <strong style="color: var(--neon-blue);">${(Number(idea.score) || 0).toFixed(1)}</strong></span>
                        </div>
                    </td>
                    <td style="padding: 8px 6px; text-align: right; vertical-align: middle; white-space: nowrap;">
                        <div style="display: flex; gap: 4px; justify-content: flex-end; align-items: center;">
                            <button class="btn-certify-idea" data-id="${idea.id}" style="padding: 3px 6px; background: ${certBg}; border: 1px solid ${certBorder}; color: ${certColor}; font-family:'Orbitron'; font-size: 0.55rem; cursor:pointer;" ${isCertifying ? 'disabled' : ''}>
                                ${isCertifying ? 'CERTIFYING...' : certText}
                            </button>
                            <button class="btn-plan-idea" data-id="${idea.id}" style="padding: 3px 6px; background: rgba(0, 191, 255, 0.1); border: 1px solid var(--neon-blue); color: var(--neon-blue); font-family:'Orbitron'; font-size: 0.55rem; cursor:pointer;" ${isPlanning ? 'disabled' : ''}>
                                ${isPlanning ? 'PLAN' : 'PLAN'}
                            </button>
                            <button class="btn-deploy-idea" data-id="${idea.id}" data-title="${idea.title}" data-category="${idea.category}" style="padding: 3px 6px; background: var(--neon-green); border: none; color: #000; font-family:'Orbitron'; font-size: 0.55rem; cursor:pointer; font-weight:700;">
                                DEPLOY
                            </button>
                        </div>
                    </td>
                </tr>
                `;
            });
        }

        html += `
            </tbody>
        </table>
        `;
        
        tableContainer.innerHTML = html;
        this.bindIdeasActions(container);
    }

    private static bindIdeasActions(container: HTMLElement) {
        // Certify
        const certBtns = container.querySelectorAll('.btn-certify-idea');
        certBtns.forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const target = e.currentTarget as HTMLButtonElement;
                const id = target.getAttribute('data-id');
                if (!id) return;
                
                this.isCertifying[id] = true;
                this.renderIdeasTable(container);
                this.log(container, `Triggered local AI simulation for strategy ${id}...`, '#ffaa00');
                
                try {
                    const resp = await fetch('/monetize/ideas/certify', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ idea_id: id })
                    });
                    const certResult = await resp.json();
                    
                    this.log(container, `Strategy ${id} certification complete! Score: ${certResult.score}/100. Status: ${certResult.status.toUpperCase()}`, 'var(--neon-green)');
                    if (certResult.summary) {
                        this.log(container, `Summary: ${certResult.summary}`, 'rgba(255,255,255,0.7)');
                    }
                } catch (err) {
                    console.error('Certification failed', err);
                    this.log(container, `Certification failed for strategy ${id}`, 'var(--neon-pink)');
                } finally {
                    this.isCertifying[id] = false;
                    this.fetchIdeas(container);
                }
            });
        });

        // Plan
        const planBtns = container.querySelectorAll('.btn-plan-idea');
        planBtns.forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const target = e.currentTarget as HTMLButtonElement;
                const id = target.getAttribute('data-id');
                if (!id) return;
                
                this.isPlanning[id] = true;
                this.renderIdeasTable(container);
                
                try {
                    const resp = await fetch(`/monetize/ideas/plan?idea_id=${id}`);
                    const plan = await resp.json();
                    
                    const planContainer = container.querySelector('#ideas-plan-container') as HTMLElement;
                    if (planContainer) {
                        planContainer.style.display = 'block';
                        planContainer.innerHTML = `
                            <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.2); padding-bottom:8px; margin-bottom:12px;">
                                <h4 style="font-family:'Orbitron'; margin:0; font-size:0.85rem; color:var(--neon-blue); letter-spacing:1px;">📋 STRATEGY PLAN: ${plan.idea_title}</h4>
                                <button id="btn-close-plan" style="background:none; border:none; color:rgba(255,255,255,0.6); font-size:1.2rem; cursor:pointer;">✖</button>
                            </div>
                            <div style="display:flex; gap:16px; margin-bottom:12px;">
                                <div style="flex:1; background:rgba(0,0,0,0.3); padding:8px; border:1px solid rgba(255,255,255,0.1); border-radius:2px;">
                                    <div style="font-size:0.6rem; opacity:0.6; text-transform:uppercase;">Timeline</div>
                                    <div style="font-size:1rem; font-weight:700; color:var(--neon-green);">${plan.timeline_days} Days</div>
                                </div>
                                <div style="flex:1; background:rgba(0,0,0,0.3); padding:8px; border:1px solid rgba(255,255,255,0.1); border-radius:2px;">
                                    <div style="font-size:0.6rem; opacity:0.6; text-transform:uppercase;">Est. Cost</div>
                                    <div style="font-size:1rem; font-weight:700; color:var(--neon-pink);">$${plan.estimated_cost}</div>
                                </div>
                                <div style="flex:1; background:rgba(0,0,0,0.3); padding:8px; border:1px solid rgba(255,255,255,0.1); border-radius:2px;">
                                    <div style="font-size:0.6rem; opacity:0.6; text-transform:uppercase;">Est. Monthly Rev</div>
                                    <div style="font-size:1rem; font-weight:700; color:var(--neon-blue);">$${plan.estimated_revenue}</div>
                                </div>
                            </div>
                            
                            <div style="margin-bottom:12px;">
                                <div style="font-size:0.7rem; font-weight:700; color:var(--neon-blue); margin-bottom:6px;">PHASES & MILESTONES:</div>
                                <div style="display:flex; flex-direction:column; gap:6px; max-height: 180px; overflow-y:auto; padding-right:4px;">
                                    ${plan.phases.map((phase: any, index: number) => `
                                        <div style="background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05); padding:8px; border-radius:2px;">
                                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                                                <span style="font-weight:700; color:#ffaa00; font-size:0.7rem;">Phase ${index + 1}: ${phase.name}</span>
                                                <span style="font-size:0.6rem; opacity:0.7;">(${phase.duration_days} Days)</span>
                                            </div>
                                            <div style="font-size:0.65rem; opacity:0.8; margin-bottom:4px;">Tasks: ${phase.tasks.join(', ')}</div>
                                            ${phase.milestone ? `<div style="font-size:0.6rem; color:var(--neon-green);">★ Milestone: ${phase.milestone}</div>` : ''}
                                        </div>
                                    `).join('')}
                                </div>
                            </div>
                            
                            <div style="display:flex; gap:16px;">
                                <div style="flex:1;">
                                    <div style="font-size:0.7rem; font-weight:700; color:var(--neon-blue); margin-bottom:4px;">RESOURCES:</div>
                                    <ul style="margin:0; padding-left:14px; font-size:0.65rem; opacity:0.8;">
                                        ${plan.resources_needed.map((r: string) => `<li>${r}</li>`).join('')}
                                    </ul>
                                </div>
                                <div style="flex:1;">
                                    <div style="font-size:0.7rem; font-weight:700; color:var(--neon-blue); margin-bottom:4px;">SUCCESS CRITERIA:</div>
                                    <ul style="margin:0; padding-left:14px; font-size:0.65rem; opacity:0.8;">
                                        ${plan.success_criteria.map((c: string) => `<li>${c}</li>`).join('')}
                                    </ul>
                                </div>
                            </div>
                        `;
                        
                        // Close button inside plan container
                        const closeBtn = planContainer.querySelector('#btn-close-plan');
                        closeBtn?.addEventListener('click', () => {
                            planContainer.style.display = 'none';
                        });
                    }
                } catch (err) {
                    console.error('Plan load failed', err);
                    this.log(container, `Plan load failed for strategy ${id}`, 'var(--neon-pink)');
                } finally {
                    this.isPlanning[id] = false;
                    this.renderIdeasTable(container);
                }
            });
        });

        // Deploy
        const deployBtns = container.querySelectorAll('.btn-deploy-idea');
        deployBtns.forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const target = e.currentTarget as HTMLButtonElement;
                const id = target.getAttribute('data-id');
                const title = target.getAttribute('data-title') || '';
                const category = target.getAttribute('data-category') || '';
                if (!id) return;
                
                const agentNameInput = container.querySelector('#agent-name-input') as HTMLInputElement;
                const agentTypeInput = container.querySelector('#agent-type-input') as HTMLSelectElement;
                
                if (agentNameInput && agentTypeInput) {
                    agentNameInput.value = `${title.substring(0, 15)} Agent`;
                    
                    const mapCategoryToIncomeType = (cat: string): string => {
                        const val = cat.toLowerCase();
                        if (val.includes('crypto')) return 'crypto_trading';
                        if (val.includes('affiliate')) return 'affiliate_marketing';
                        if (val.includes('ad_revenue') || val.includes('ad')) return 'ad_revenue';
                        if (val.includes('freelance') || val.includes('freelancing')) return 'freelancing';
                        return 'crypto_trading'; 
                    };
                    
                    agentTypeInput.value = mapCategoryToIncomeType(category);
                    
                    // Smoothly scroll to the Forge Agent section
                    agentNameInput.scrollIntoView({ behavior: 'smooth' });
                    agentNameInput.focus();
                    
                    this.log(container, `Selected strategy "${title}" pre-filled inside Forge Agent. Click "DEPLOY AGENT" to execute.`, 'var(--neon-green)');
                }
            });
        });
    }

    private static log(container: HTMLElement, message: string, color: string = 'var(--neon-blue)') {
        const logArea = container.querySelector('#audit-log-content') as HTMLElement;
        if (!logArea) return;
        const time = new Date().toLocaleTimeString();
        const entry = document.createElement('div');
        entry.innerHTML = `<span style="color:${color};">[${time}]</span> ${message}`;
        logArea.prepend(entry);
    }

    private static loadState(container: HTMLElement) {
        // Now handled by fetchStatus on initial load and loop
        this.fetchStatus(container);
        this.fetchIdeas(container);
    }
}