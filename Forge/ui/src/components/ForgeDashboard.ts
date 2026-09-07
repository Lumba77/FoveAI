/**
 * The Forge Dashboard — Main IDE UI for Cline CLI agent streaming.
 */
import { ForgeCore, type ForgeEvent, type SessionInfo } from '../ForgeCore';

interface DashboardElements {
  root: HTMLElement;
  statusBadge: HTMLElement;
  statusText: HTMLElement;
  sessionCount: HTMLElement;
  eventCount: HTMLElement;
  sessionList: HTMLElement;
  eventFeed: HTMLElement;
  promptInput: HTMLTextAreaElement;
  sendBtn: HTMLButtonElement;
  spawnBtn: HTMLButtonElement;
  modelSelect: HTMLSelectElement;
  tabBar: HTMLElement;
}

export class ForgeDashboard {
  private core: ForgeCore;
  private el!: DashboardElements;
  private activeSessionId: string | null = null;
  private sessions: Map<string, SessionInfo> = new Map();
  private autoScroll: boolean = true;
  private eventCounts: Record<string, number> = {};

  constructor(core: ForgeCore) {
    this.core = core;
    this.buildDOM();
    this.bindEvents();
    this.bindForgeEvents();
    this.refreshSessions();
  }

  /* ── DOM Construction ────────────────────────────── */

  private buildDOM(): void {
    const root = document.getElementById('forge-root');
    if (!root) throw new Error('Missing #forge-root');
    this.injectStyles();
    root.innerHTML = this.getShellHTML();
    this.el = {
      root,
      statusBadge: root.querySelector('#forge-status-badge')!,
      statusText: root.querySelector('#forge-status-text')!,
      sessionCount: root.querySelector('#forge-session-count')!,
      eventCount: root.querySelector('#forge-event-count')!,
      sessionList: root.querySelector('#forge-session-list')!,
      eventFeed: root.querySelector('#forge-event-feed')!,
      promptInput: root.querySelector('#forge-prompt-input')!,
      sendBtn: root.querySelector('#forge-send-btn')!,
      spawnBtn: root.querySelector('#forge-spawn-btn')!,
      modelSelect: root.querySelector('#forge-model-select')!,
      tabBar: root.querySelector('#forge-tab-bar')!,
    };
    this.setConnected(false);
  }

  private getShellHTML(): string {
    const html = `
<div class="forge-shell">
<header class="forge-topbar">
<div class="forge-brand"><span class="forge-icon">⚙</span><span class="forge-title">The Forge</span><span class="forge-version">v1.0.0</span></div>
<div class="forge-status"><span class="forge-badge" id="forge-status-badge">●</span><span id="forge-status-text">Connecting...</span></div>
<div class="forge-metrics"><span>Sessions: <strong id="forge-session-count">0</strong></span><span>Events: <strong id="forge-event-count">0</strong></span></div>
</header>
<div class="forge-body">
<aside class="forge-sidebar"><div class="forge-panel-header"><h3>Sessions</h3>
<div class="forge-spawn-controls"><select id="forge-model-select">
<option value="deepseek-v4-pro">DeepSeek V4 Pro</option>
<option value="glm-5.1-cloud">GLM-5.1 Cloud</option>
<option value="qwen3.5-cloud">Qwen 3.5 Cloud</option>
<option value="gemma3:27b-cloud">Gemma 3 27B</option>
</select><button id="forge-spawn-btn" class="forge-btn forge-btn-primary">+ Spawn</button></div></div>
<div id="forge-session-list" class="forge-session-list"><div class="forge-empty-state">No active sessions</div></div></aside>
<main class="forge-main">
<nav class="forge-tabs" id="forge-tab-bar">
<button class="forge-tab active" data-tab="stream">Stream</button>
<button class="forge-tab" data-tab="files">Files</button>
<button class="forge-tab" data-tab="tools">Tools</button></nav>
<div class="forge-event-feed" id="forge-event-feed"><div class="forge-welcome">
<div class="forge-welcome-icon">⚔</div><h2>The Forge is Ready</h2>
<p>Spawn a session to begin.</p>
<p class="forge-welcome-hint">DeepSeek V4, GLM-5.1, Qwen 3.5, Gemma 3</p></div></div>
<div class="forge-prompt-bar"><textarea id="forge-prompt-input" class="forge-prompt-input"
placeholder="Send a prompt... (Enter to send)" rows="2" disabled></textarea>
<button id="forge-send-btn" class="forge-btn forge-btn-send" disabled>Send</button></div></main>
<aside class="forge-metrics-panel" id="forge-metrics-panel"><div class="forge-panel-header"><h3>Session Info</h3></div>
<div class="forge-metrics-content">
<div class="forge-metric-card"><label>Model</label><span id="metric-model">—</span></div>
<div class="forge-metric-card"><label>Uptime</label><span id="metric-uptime">—</span></div>
<div class="forge-metric-card"><label>Events</label><span id="metric-events">—</span></div>
<div class="forge-metric-card"><label>Tool Calls</label><span id="metric-tool-calls">0</span></div>
<div class="forge-metric-card"><label>File Edits</label><span id="metric-file-edits">0</span></div>
<div class="forge-metric-card"><label>Responses</label><span id="metric-responses">0</span></div>
<div class="forge-metric-card"><label>Errors</label><span id="metric-errors">0</span></div>
</div></aside></div></div>`;
    return html;
  }

  /* ── CSS Injection ──────────────────────────────── */

  private injectStyles(): void {
    if (document.getElementById('forge-dashboard-styles')) return;
    const s = document.createElement('style');
    s.id = 'forge-dashboard-styles';
    s.textContent = `
:root{--fbg:#02050a;--fsurf:#0a1119;--fsurf2:#111d2b;--fbor:#1a2a3a;--faccent:#00f3ff;--faccent2:#7c3aed;--ftxt:#d0d5dd;--fdim:#6b7280;--fgreen:#10b981;--fwarn:#f59e0b;--ferr:#ef4444;--ffont:system-ui,sans-serif;--fmono:'Cascadia Code','Fira Code',monospace}
.forge-shell{display:flex;flex-direction:column;width:100%;height:100%;font-family:var(--ffont);color:var(--ftxt);background:var(--fbg)}
.forge-topbar{display:flex;align-items:center;gap:16px;padding:8px 16px;background:var(--fsurf);border-bottom:1px solid var(--fbor);min-height:44px;flex-shrink:0}
.forge-brand{display:flex;align-items:center;gap:8px;font-weight:600}
.forge-icon{font-size:18px;color:var(--faccent)}
.forge-title{font-size:15px;letter-spacing:.5px}
.forge-version{font-size:11px;color:var(--fdim)}
.forge-status{display:flex;align-items:center;gap:6px;margin-left:auto}
.forge-badge{font-size:10px}.forge-badge.connected{color:var(--fgreen)}.forge-badge.disconnected{color:var(--ferr)}
.forge-metrics{display:flex;gap:16px;font-size:12px;color:var(--fdim)}
.forge-metrics strong{color:var(--ftxt);font-family:var(--fmono)}
.forge-body{display:flex;flex:1;overflow:hidden}
.forge-sidebar{width:260px;flex-shrink:0;display:flex;flex-direction:column;background:var(--fsurf);border-right:1px solid var(--fbor)}
.forge-panel-header{padding:12px;border-bottom:1px solid var(--fbor)}
.forge-panel-header h3{font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:var(--fdim);margin:0 0 8px}
.forge-spawn-controls{display:flex;gap:6px}
.forge-spawn-controls select{flex:1;padding:6px 8px;font-size:12px;background:var(--fsurf2);color:var(--ftxt);border:1px solid var(--fbor);border-radius:6px;cursor:pointer;font-family:var(--fmono)}
.forge-btn{padding:6px 12px;font-size:12px;font-weight:600;border:none;border-radius:6px;cursor:pointer;font-family:var(--ffont);transition:all .15s}
.forge-btn-primary{background:var(--faccent);color:#000}.forge-btn-primary:hover{filter:brightness(1.2)}.forge-btn-primary:disabled{opacity:.4;cursor:not-allowed;filter:none}
.forge-btn-send{background:var(--faccent2);color:#fff;padding:8px 20px;font-size:13px}.forge-btn-send:hover{filter:brightness(1.2)}.forge-btn-send:disabled{opacity:.4;cursor:not-allowed;filter:none}
.forge-btn-danger{background:transparent;color:var(--ferr);border:1px solid var(--ferr);padding:3px 8px;font-size:10px;margin-top:4px}.forge-btn-danger:hover{background:var(--ferr);color:#fff}
.forge-session-list{flex:1;overflow-y:auto;padding:8px}
.forge-session-card{padding:10px;margin-bottom:6px;background:var(--fsurf2);border-radius:8px;border:1px solid var(--fbor);cursor:pointer;transition:border-color .15s}
.forge-session-card:hover{border-color:var(--faccent2)}
.forge-session-card.active{border-color:var(--faccent);background:rgba(0,243,255,.05)}
.forge-session-card .sid{font-size:11px;font-family:var(--fmono);color:var(--faccent);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-bottom:4px}
.forge-session-card .smeta{font-size:11px;color:var(--fdim);display:flex;justify-content:space-between;align-items:center}
.forge-session-card .smodel{font-family:var(--fmono);font-size:10px}
.forge-session-card .suptime{font-family:var(--fmono);font-size:10px}
.forge-session-card .sbadge{display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--fgreen);margin-right:4px}
.forge-session-card .sbadge.stopped{background:var(--fdim)}
.forge-empty-state{text-align:center;padding:32px 16px;color:var(--fdim);font-size:13px;font-style:italic}
.forge-main{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}
.forge-tabs{display:flex;gap:0;background:var(--fsurf);border-bottom:1px solid var(--fbor);padding:0 12px;flex-shrink:0}
.forge-tab{padding:10px 16px;font-size:12px;font-weight:600;background:none;border:none;color:var(--fdim);cursor:pointer;font-family:var(--ffont);border-bottom:2px solid transparent;transition:all .15s}
.forge-tab:hover{color:var(--ftxt)}.forge-tab.active{color:var(--faccent);border-bottom-color:var(--faccent)}
.forge-event-feed{flex:1;overflow-y:auto;padding:12px 16px;display:flex;flex-direction:column;gap:6px}
.forge-event-feed::-webkit-scrollbar{width:6px}.forge-event-feed::-webkit-scrollbar-track{background:transparent}.forge-event-feed::-webkit-scrollbar-thumb{background:var(--fbor);border-radius:3px}
.forge-welcome{text-align:center;padding:64px 24px;margin:auto}
.forge-welcome-icon{font-size:48px;color:var(--faccent);margin-bottom:16px}
.forge-welcome h2{font-size:22px;font-weight:600;margin:0 0 8px}.forge-welcome p{color:var(--fdim);font-size:14px;margin:4px 0}
.forge-welcome-hint{font-size:12px!important;font-family:var(--fmono)}
.forge-event{padding:8px 12px;border-radius:6px;font-size:12px;font-family:var(--fmono);border-left:3px solid var(--fbor);background:var(--fsurf2);animation:ffadein .2s ease-out}
@keyframes ffadein{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:translateY(0)}}
.forge-event .evtime{font-size:10px;color:var(--fdim);margin-bottom:4px}
.forge-event .evtype{display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600;margin-right:6px;text-transform:uppercase}
.forge-event .evcontent{color:var(--ftxt);white-space:pre-wrap;word-break:break-word;line-height:1.5;margin-top:4px}
.forge-event.et-tool_call{border-left-color:var(--fwarn)}.forge-event.et-tool_call .evtype{background:rgba(245,158,11,.15);color:var(--fwarn)}
.forge-event.et-tool_result{border-left-color:var(--faccent2)}.forge-event.et-tool_result .evtype{background:rgba(124,58,237,.15);color:var(--faccent2)}
.forge-event.et-response{border-left-color:var(--faccent)}.forge-event.et-response .evtype{background:rgba(0,243,255,.15);color:var(--faccent)}
.forge-event.et-thought{border-left-color:#9333ea}.forge-event.et-thought .evtype{background:rgba(147,51,234,.15);color:#9333ea}
.forge-event.et-file_edit{border-left-color:var(--fgreen)}.forge-event.et-file_edit .evtype{background:rgba(16,185,129,.15);color:var(--fgreen)}
.forge-event.et-error{border-left-color:var(--ferr)}.forge-event.et-error .evtype{background:rgba(239,68,68,.15);color:var(--ferr)}
.forge-event.et-session_start{border-left-color:var(--faccent)}.forge-event.et-session_end{border-left-color:var(--fdim)}
.forge-event .evpath{font-family:var(--fmono);color:var(--faccent2);font-size:11px}
.forge-event .evtool{font-family:var(--fmono);color:var(--fwarn);font-weight:600}
.forge-event .evmeta{font-size:10px;color:var(--fdim);margin-top:4px}
.forge-prompt-bar{display:flex;gap:8px;padding:10px 16px;background:var(--fsurf);border-top:1px solid var(--fbor);flex-shrink:0}
.forge-prompt-input{flex:1;padding:8px 12px;font-size:13px;background:var(--fsurf2);color:var(--ftxt);border:1px solid var(--fbor);border-radius:8px;resize:none;font-family:var(--fmono);outline:none;transition:border-color .2s}
.forge-prompt-input:focus{border-color:var(--faccent2)}.forge-prompt-input:disabled{opacity:.4;cursor:not-allowed}.forge-prompt-input::placeholder{color:var(--fdim)}
.forge-metrics-panel{width:220px;flex-shrink:0;background:var(--fsurf);border-left:1px solid var(--fbor);display:flex;flex-direction:column}
.forge-metrics-content{padding:8px 12px;display:flex;flex-direction:column;gap:6px}
.forge-metric-card{padding:8px;background:var(--fsurf2);border-radius:6px;display:flex;justify-content:space-between;align-items:center}
.forge-metric-card label{font-size:11px;color:var(--fdim);font-weight:500}
.forge-metric-card span{font-family:var(--fmono);font-size:12px;font-weight:600}
`;document.head.appendChild(s);
  }


  /* ── Event Binding ──────────────────────────────── */

  private bindEvents(): void {
    this.el.spawnBtn.addEventListener('click', () => this.spawnSession());
    this.el.sendBtn.addEventListener('click', () => this.sendPrompt());
    this.el.promptInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.sendPrompt(); }
    });
    this.el.tabBar.addEventListener('click', (e) => {
      const tab = (e.target as HTMLElement).closest('.forge-tab') as HTMLButtonElement;
      if (!tab) return;
      this.el.tabBar.querySelectorAll('.forge-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      this.filterEvents(tab.dataset.tab || 'stream');
    });
    this.el.eventFeed.addEventListener('scroll', () => {
      const feed = this.el.eventFeed;
      this.autoScroll = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 40;
    });
  }

  private bindForgeEvents(): void {
    this.core.on('forge_connected', () => this.setConnected(true));
    this.core.on('forge_disconnected', () => this.setConnected(false));
    this.core.on('session_start', (e) => { this.addEvent(e); this.refreshSessions(); });
    this.core.on('session_end', (e) => { this.addEvent(e); this.refreshSessions(); });
    const types = ['tool_call','tool_result','response','thought','file_edit','error'];
    for (const t of types) this.core.on(t, (e) => this.addEvent(e));
    this.core.on('*', (e) => {
      if (!types.includes(e.type) && e.type.startsWith('forge_') === false
          && e.type !== 'session_start' && e.type !== 'session_end') {
        this.addEvent(e);
      }
    });
  }

  /* ── Session Management ──────────────────────────── */

  private async spawnSession(): Promise<void> {
    const model = this.el.modelSelect.value;
    this.el.spawnBtn.disabled = true;
    this.el.spawnBtn.textContent = '...';
    try {
      const sid = await this.core.spawnSession(model);
      this.activeSessionId = sid;
      this.el.promptInput.disabled = false;
      this.el.sendBtn.disabled = false;
      this.addSystem('Session spawned: ' + sid.substring(0, 20) + '... (' + model + ')');
      await this.refreshSessions();
    } catch (err: any) {
      this.addSystem('Failed: ' + err.message, true);
    } finally {
      this.el.spawnBtn.disabled = false;
      this.el.spawnBtn.textContent = '+ Spawn';
    }
  }

  private async stopSession(sid: string): Promise<void> {
    try {
      await this.core.stopSession(sid);
      if (this.activeSessionId === sid) {
        this.activeSessionId = null;
        this.el.promptInput.disabled = true;
        this.el.sendBtn.disabled = true;
      }
      await this.refreshSessions();
    } catch (err: any) {
      this.addSystem('Failed to stop: ' + err.message, true);
    }
  }

  private async sendPrompt(): Promise<void> {
    const text = this.el.promptInput.value.trim();
    if (!text || !this.activeSessionId) return;
    this.el.promptInput.value = '';
    this.el.sendBtn.disabled = true;
    try {
      this.addSystem('> ' + text);
      await this.core.sendPrompt(this.activeSessionId, text);
    } catch (err: any) {
      this.addSystem('Send failed: ' + err.message, true);
    } finally {
      this.el.sendBtn.disabled = false;
      this.el.promptInput.focus();
    }
  }

  private async refreshSessions(): Promise<void> {
    try {
      const sessions = await this.core.listSessions();
      this.sessions.clear();
      for (const s of sessions) this.sessions.set(s.session_id, s);
      this.renderSessions();
    } catch { /* API may not be running */ }
  }


  /* ── Rendering ──────────────────────────────────── */

  private renderSessions(): void {
    const list = this.el.sessionList;
    if (this.sessions.size === 0) {
      list.innerHTML = '<div class="forge-empty-state">No active sessions</div>';
      return;
    }
    let html = '';
    for (const [id, info] of this.sessions) {
      const active = id === this.activeSessionId ? ' active' : '';
      const running = info.is_running ? '' : ' stopped';
      html += `<div class="forge-session-card${active}" data-sid="${id}">
<div class="sid" title="${id}">${id.substring(0, 28)}...</div>
<div class="smeta"><span class="smodel"><span class="sbadge${running}"></span>${info.model}</span>
<span class="suptime">${this.fmtUptime(info.uptime_s)}</span></div>
<button class="forge-btn forge-btn-danger sid-stop" data-sid="${id}">Stop</button></div>`;
    }
    list.innerHTML = html;
    list.querySelectorAll('.forge-session-card').forEach(card => {
      card.addEventListener('click', (e) => {
        if ((e.target as HTMLElement).closest('.sid-stop')) return;
        this.selectSession((card as HTMLElement).dataset.sid!);
      });
    });
    list.querySelectorAll('.sid-stop').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.stopSession((btn as HTMLElement).dataset.sid!);
      });
    });
  }

  private selectSession(sid: string): void {
    this.activeSessionId = sid;
    this.el.promptInput.disabled = false;
    this.el.sendBtn.disabled = false;
    this.renderSessions();
    this.addSystem('Switched to: ' + sid.substring(0, 20) + '...');
    this.updateMetrics();
    this.el.promptInput.focus();
  }

  /* ── Event Feed ─────────────────────────────────── */

  private addEvent(event: ForgeEvent): void {
    if (this.activeSessionId && event.session_id && event.session_id !== this.activeSessionId) return;
    const feed = this.el.eventFeed;
    const w = feed.querySelector('.forge-welcome');
    if (w) w.remove();

    const time = event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
    const typeLabel = event.type.replace(/_/g, ' ');
    let content = '';

    switch (event.type) {
      case 'tool_call':
        content = `<span class="evtype">${typeLabel}</span><span class="evtool">${event.tool || '?'}</span>`;
        if (event.args) content += `<div class="evcontent">${this.trunc(JSON.stringify(event.args, null, 2), 400)}</div>`;
        break;
      case 'tool_result':
        content = `<span class="evtype">${typeLabel}</span><span class="evtool">${event.tool || '?'}</span>`;
        if (event.duration_ms) content += `<span class="evmeta">${event.duration_ms}ms</span>`;
        if (event.result) content += `<div class="evcontent">${this.trunc(typeof event.result==='string'?event.result:JSON.stringify(event.result), 300)}</div>`;
        break;
      case 'response':
        content = `<span class="evtype">${typeLabel}</span>`;
        if (event.content) content += `<div class="evcontent">${event.content}</div>`;
        if (event.tokens) content += `<div class="evmeta">Tokens: ${event.tokens} | Model: ${event.model||'?'}</div>`;
        break;
      case 'thought':
        content = `<span class="evtype">${typeLabel}</span>`;
        if (event.content) content += `<div class="evcontent">${this.trunc(event.content, 500)}</div>`;
        break;
      case 'file_edit':
        content = `<span class="evtype">${typeLabel}</span>`;
        if (event.path) content += `<span class="evpath">${event.path}</span>`;
        if (event.diff) content += `<div class="evcontent">${this.trunc(event.diff, 300)}</div>`;
        break;
      case 'session_start':
        content = `<span class="evtype">${typeLabel}</span> Model: ${event.model||'?'} | Workspace: ${event.workspace||'?'}`;
        break;
      case 'session_end':
        content = `<span class="evtype">${typeLabel}</span> ${event.reason||'?'}`;
        if (event.duration_s) content += `<span class="evmeta">Duration: ${event.duration_s}s</span>`;
        break;
      case 'error':
        content = `<span class="evtype">${typeLabel}</span>`;
        if (event.message) content += `<div class="evcontent">${event.message}</div>`;
        break;
      default:
        content = `<span class="evtype">${typeLabel}</span>`;
        if (event.content) content += `<div class="evcontent">${this.trunc(event.content, 300)}</div>`;
    }


    const entry = document.createElement('div');
    entry.className = `forge-event et-${event.type}`;
    entry.dataset.eventType = event.type;
    entry.innerHTML = `<div class="evtime">${time}</div>${content}`;
    if (event.session_id) {
      entry.innerHTML += `<div class="evtime" style="margin-top:4px">sid: ${event.session_id.substring(0,16)}...</div>`;
    }
    feed.appendChild(entry);
    if (this.autoScroll) feed.scrollTop = feed.scrollHeight;
    this.eventCounts[event.type] = (this.eventCounts[event.type] || 0) + 1;
    this.updateMetrics();
  }

  private addSystem(msg: string, isErr: boolean = false): void {
    const feed = this.el.eventFeed;
    const w = feed.querySelector('.forge-welcome');
    if (w) w.remove();
    const entry = document.createElement('div');
    entry.className = `forge-event${isErr ? ' et-error' : ''}`;
    entry.innerHTML = `<div class="evtime">${new Date().toLocaleTimeString()}</div>
<span class="evtype" style="background:rgba(107,114,128,.15);color:var(--fdim)">SYS</span>
<span class="evcontent" style="color:${isErr ? 'var(--ferr)' : 'var(--fdim)'}">${msg}</span>`;
    feed.appendChild(entry);
    if (this.autoScroll) feed.scrollTop = feed.scrollHeight;
  }

  private filterEvents(tab: string): void {
    this.el.eventFeed.querySelectorAll('.forge-event').forEach((el: any) => {
      const et = el.dataset.eventType;
      if (tab === 'files') el.style.display = (et === 'file_edit') ? '' : 'none';
      else if (tab === 'tools') el.style.display = (et === 'tool_call' || et === 'tool_result') ? '' : 'none';
      else el.style.display = '';
    });
  }


  /* ── Status & Metrics ───────────────────────────── */

  private setConnected(ok: boolean): void {
    this.el.statusBadge.textContent = '●';
    this.el.statusBadge.className = 'forge-badge ' + (ok ? 'connected' : 'disconnected');
    this.el.statusText.textContent = ok ? 'Connected' : 'Disconnected';
    this.el.spawnBtn.disabled = !ok;
    if (ok) this.refreshSessions();
  }

  private updateMetrics(): void {
    const set = (id: string, v: string) => {
      const el = document.getElementById(id); if (el) el.textContent = v;
    };
    const active = this.activeSessionId ? this.sessions.get(this.activeSessionId) : null;
    if (active) {
      set('metric-model', active.model);
      set('metric-uptime', this.fmtUptime(active.uptime_s));
      const total = Object.values(active.event_summary || {}).reduce((a:number,b:number)=>a+b, 0);
      set('metric-events', String(total));
      set('metric-tool-calls', String(active.event_summary?.['tool_call'] || 0));
      set('metric-file-edits', String(active.event_summary?.['file_edit'] || 0));
      set('metric-responses', String(active.event_summary?.['response'] || 0));
      set('metric-errors', String(active.event_summary?.['error'] || 0));
    } else {
      set('metric-model', '—');
      set('metric-uptime', '—');
      set('metric-events', '—');
      set('metric-tool-calls', '0');
      set('metric-file-edits', '0');
      set('metric-responses', '0');
      set('metric-errors', '0');
    }
  }

  /* ── Helpers ────────────────────────────────────── */

  private fmtUptime(s: number): string {
    if (s < 60) return Math.round(s) + 's';
    if (s < 3600) return Math.floor(s/60) + 'm ' + Math.round(s%60) + 's';
    return Math.floor(s/3600) + 'h ' + Math.floor((s%3600)/60) + 'm';
  }

  private trunc(text: string, max: number): string {
    if (text.length <= max) return text;
    return text.substring(0, max) + '...';
  }
}
