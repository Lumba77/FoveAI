export class ChronicleTab {
    public static render(container: HTMLElement) {
        container.innerHTML = `
            <div class="breadcrumb">SANCTUARY // CHRONICLE_BULLETINS</div>
            
            <div style="flex: 1; display: flex; flex-direction: column; gap: 20px; min-height: 0;">
                <div class="glass-card" style="padding: 20px;">
                    <h4 style="font-family: 'Orbitron'; font-size: 0.8rem; color: var(--neon-blue); margin: 0 0 15px 0;">NEW BULLETIN</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px;">
                        <div>
                            <label style="font-size: 0.6rem; opacity: 0.6; display: block; margin-bottom: 5px;">TAG</label>
                            <input type="text" id="chrono-tag" placeholder="UI, SOUL, XR..." style="width: 100%; background: rgba(0,0,0,0.4); border: 1px solid var(--border); color: #fff; padding: 8px; border-radius: 4px; font-family: 'Share Tech Mono';">
                        </div>
                        <div>
                            <label style="font-size: 0.6rem; opacity: 0.6; display: block; margin-bottom: 5px;">PRIORITY</label>
                            <select id="chrono-priority" style="width: 100%; background: #0a0f19; border: 1px solid var(--border); color: #fff; padding: 8px; border-radius: 4px; font-family: 'Share Tech Mono';">
                                <option value="info">INFO</option>
                                <option value="ops">OPS</option>
                                <option value="warn">WARN</option>
                            </select>
                        </div>
                    </div>
                    <div style="margin-bottom: 15px;">
                        <label style="font-size: 0.6rem; opacity: 0.6; display: block; margin-bottom: 5px;">TITLE</label>
                        <input type="text" id="chrono-title" placeholder="Short headline..." style="width: 100%; background: rgba(0,0,0,0.4); border: 1px solid var(--border); color: #fff; padding: 10px; border-radius: 4px;">
                    </div>
                    <div style="margin-bottom: 20px;">
                        <label style="font-size: 0.6rem; opacity: 0.6; display: block; margin-bottom: 5px;">BODY</label>
                        <textarea id="chrono-body" rows="4" style="width: 100%; background: rgba(0,0,0,0.4); border: 1px solid var(--border); color: #fff; padding: 10px; border-radius: 4px; font-family: inherit; resize: vertical;" placeholder="Details of the update..."></textarea>
                    </div>
                    <button id="btn-post-bulletin" class="neon-btn" style="width: 100%; padding: 12px; background: var(--neon-blue); color: #000; border: none; border-radius: 4px; font-family: 'Orbitron'; font-weight: 700; letter-spacing: 1px; cursor: pointer;">POST BULLETIN</button>
                </div>

                <div class="glass-card" style="flex: 1; display: flex; flex-direction: column; overflow: hidden; padding: 0;">
                    <div style="padding: 10px 20px; background: rgba(0,243,255,0.05); border-bottom: 1px solid var(--border); font-family: 'Orbitron'; font-size: 0.7rem; letter-spacing: 1px; display: flex; justify-content: space-between;">
                        <span>RECENT BULLETINS</span>
                        <button id="btn-refresh-bulletins" style="background: transparent; border: none; color: var(--neon-blue); font-size: 0.6rem; cursor: pointer; text-decoration: underline;">REFRESH</button>
                    </div>
                    <div id="bulletin-list" style="flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 15px;">
                        Loading bulletins...
                    </div>
                </div>
            </div>
        `;

        this.setupListeners(container);
        this.loadBulletins(container);
    }

    private static async loadBulletins(container: HTMLElement) {
        const list = container.querySelector('#bulletin-list');
        if (!list) return;

        try {
            const response = await fetch('/api/soul/announcements');
            if (response.ok) {
                const data = await response.json();
                if (data.announcements && Array.isArray(data.announcements)) {
                    list.innerHTML = data.announcements.reverse().map((a: any) => `
                        <div style="border-left: 3px solid ${a.priority === 'warn' ? 'var(--neon-pink)' : 'var(--neon-blue)'}; background: rgba(255,255,255,0.02); padding: 12px; border-radius: 4px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 0.65rem; font-family: 'Share Tech Mono';">
                                <span style="color: ${a.priority === 'warn' ? 'var(--neon-pink)' : 'var(--neon-blue)'}; text-transform: uppercase;">[${a.tag || 'GENERAL'}]</span>
                                <span style="opacity: 0.5;">${a.date}</span>
                            </div>
                            <div style="font-family: 'Orbitron'; font-size: 0.8rem; margin-bottom: 8px;">${a.title}</div>
                            <div style="font-size: 0.8rem; opacity: 0.8; line-height: 1.4; white-space: pre-wrap;">${a.body}</div>
                        </div>
                    `).join('');
                } else {
                    list.innerHTML = '<div style="opacity: 0.5; font-size: 0.7rem; text-align: center;">No bulletins found.</div>';
                }
            }
        } catch (err) {
            list.innerHTML = '<div style="color: var(--neon-pink); font-size: 0.7rem; text-align: center;">Failed to load bulletins.</div>';
        }
    }

    private static setupListeners(container: HTMLElement) {
        container.querySelector('#btn-post-bulletin')?.addEventListener('click', async () => {
            const tag = (container.querySelector('#chrono-tag') as HTMLInputElement).value;
            const priority = (container.querySelector('#chrono-priority') as HTMLSelectElement).value;
            const title = (container.querySelector('#chrono-title') as HTMLInputElement).value;
            const body = (container.querySelector('#chrono-body') as HTMLTextAreaElement).value;

            if (!title || !body) return;

            try {
                const response = await fetch('/api/soul/announcements', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tag, priority, title, body, date: new Date().toISOString().split('T')[0] })
                });
                if (response.ok) {
                    (window as any).log?.('Bulletin Posted Successfully', 'var(--neon-blue)');
                    this.loadBulletins(container);
                    // Clear form
                    (container.querySelector('#chrono-title') as HTMLInputElement).value = '';
                    (container.querySelector('#chrono-body') as HTMLTextAreaElement).value = '';
                }
            } catch (err) {}
        });

        container.querySelector('#btn-refresh-bulletins')?.addEventListener('click', () => this.loadBulletins(container));
    }
}
