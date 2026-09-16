/**
 * messageRouter.ts — Central brain. Routes all 24 message types from webview to focused handlers.
 * Each handler owns a single concern: context, edits, status, sessions, or chat.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import * as cp from 'child_process';
import { FoveatedClient, PersonaId, PERSONAS } from '../memory/foveatedClient';
import { SessionLogger } from '../bonding/sessionLogger';
import { JennaStatusBar } from '../statusBar';
import { ExecutionBuffer } from '../executionBuffer';
import { AudioManager } from '../audioManager';
import { ContextAnalyzer } from './contextAnalyzer';
import { EditApplicator } from './editApplicator';
import { StatusPusher } from './statusPusher';
import { SessionManager } from './sessionManager';
import { ChatHandler } from './chatHandler';

export class MessageRouter {
  private _buffer: ExecutionBuffer;
  private _history = { value: [] as any[] };
  private _activePersona: PersonaId = 'code';
  private _xrlLevel = 5;
  private _sessionStart = new Date().toISOString();

  private _analyzer: ContextAnalyzer;
  private _editor: EditApplicator;
  private _status: StatusPusher;
  private _sessions: SessionManager;
  private _chat: ChatHandler;

  constructor(
    client: FoveatedClient,
    logger: SessionLogger,
    statusBar: JennaStatusBar,
    workspaceId: string,
    buffer: ExecutionBuffer,
    storageUri: vscode.Uri,
    private _post: (msg: Record<string, unknown>) => void,
    private _audio?: AudioManager,
  ) {
    const onChat = (text: string, tasks?: any[]) => this._chat.handleChat(text, tasks);
    
    this._analyzer = new ContextAnalyzer((t) => onChat(t));
    this._editor = new EditApplicator(this._post);
    this._status = new StatusPusher(client, statusBar, workspaceId, () => this._xrlLevel, this._post);
    this._sessions = new SessionManager(workspaceId, storageUri, this._post, () => this._history.value);
    this._buffer = buffer;
    this._chat = new ChatHandler(client, logger, workspaceId, () => this._activePersona, () => this._xrlLevel, () => this._sessionStart, this._post, buffer);
  }

  get chat(): ChatHandler { return this._chat; }
  get sessions(): SessionManager { return this._sessions; }

  /** Pull the live aggression level from the proxy's shared env — the same
   *  source of truth Commando/Commander write via POST /api/setting. */
  private async _syncXrlFromProxy(): Promise<void> {
    try {
      const baseUrl = vscode.workspace.getConfiguration('jenna').get<string>('foveatedMemoryUrl', 'http://127.0.0.1:8400');
      const r = await fetch(`${baseUrl}/api/setting?key=XRLF_PROXY_AGGRESSION`, { signal: AbortSignal.timeout(3000) });
      if (r.ok) {
        const d = await r.json() as { value?: string | null };
        const lvl = Number(d.value);
        if (!Number.isNaN(lvl) && d.value != null) {
          this._xrlLevel = Math.max(0, Math.min(5, lvl));
          this._post({ type: 'xrl_update', level: this._xrlLevel });
        }
      }
    } catch {}
  }

  async handle(msg: any): Promise<void> {
    switch (msg.type) {
      case 'format_dictation': await this._chat.handleDictation(msg.text); break;
      case 'chat': await this._chat.handleChat(msg.text, msg.tasks); break;

      case 'send_all_problems':
      case 'get_problems': {
        const all = vscode.languages.getDiagnostics();
        const items: { uri: vscode.Uri; diag: vscode.Diagnostic }[] = [];
        for (const [uri, diags] of all) for (const d of diags) if (d.severity <= vscode.DiagnosticSeverity.Warning) items.push({ uri, diag: d });
        if (items.length === 0) { vscode.window.showInformationMessage('No errors or warnings'); break; }
        let p = '### Active IDE Problems (' + items.length + ' total)\n\n';
        items.forEach(({ uri, diag }, i) => { p += (i+1) + '. [' + (diag.severity === vscode.DiagnosticSeverity.Error ? 'ERROR' : 'WARN') + '] ' + vscode.workspace.asRelativePath(uri) + ':' + (diag.range.start.line + 1) + ' - ' + diag.message + '\n'; });
        this._chat.handleChat(p);
        break;
      }

      case 'message_delete': if (typeof msg.index === 'number' && msg.index >= 0) this._history.value.splice(msg.index, 1); break;
      case 'message_edit': if (typeof msg.index === 'number' && msg.index >= 0 && msg.text) this._history.value[msg.index].content = msg.text; break;

      case 'rollback_session':
        this._post({ type: 'status_update', status: { online: true, loading: true } });
        try {
          const baseUrl = vscode.workspace.getConfiguration('jenna').get<string>('foveatedMemoryUrl', 'http://127.0.0.1:8400');
          const r = await fetch(baseUrl + '/api/session/rollback', { method: 'POST', headers: { 'Authorization': 'Bearer ' + this._chat['_workspaceId'], 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: this._chat['_workspaceId'] + '_' + this._sessionStart }), signal: AbortSignal.timeout(3000) });
          if (r.ok) { const d = await r.json() as { messages?: any[] }; const f = (d.messages || []).filter((m: any) => m.role !== 'system'); this._history.value = f; this._post({ type: 'session_messages', messages: f }); }
        } catch {}
        this._post({ type: 'status_update', status: { online: true, loading: false } });
        break;

      case 'new_session':
        this._history.value = [];
        this._chat.history = [];
        this._sessionStart = new Date().toISOString();
        this._post({ type: 'clear' });
        this._sessions.fetchAndSend();
        break;
      case 'toggle_online': {
        const online = !!msg.online;
        if (!online) {
          vscode.window.showInformationMessage('FoveAI is now Offline (Models Unloaded)');
          try {
            const baseUrl = vscode.workspace.getConfiguration('jenna').get<string>('foveatedMemoryUrl', 'http://127.0.0.1:8400');
            fetch(baseUrl + '/api/unload', { method: 'POST', signal: AbortSignal.timeout(2000) }).catch(() => {});
          } catch {}
          this._post({ type: 'status_update', status: { online: false, message: 'Offline (Unloaded)' } });
        } else {
          vscode.window.showInformationMessage('FoveAI is now Online');
          await this._status.push();
        }
        break;
      }

      case 'get_status': await this._status.push(); this._post({ type: 'persona_update', activePersona: this._activePersona, personas: PERSONAS }); break;

      case 'refresh_plugin':
        try { const baseUrl = vscode.workspace.getConfiguration('jenna').get<string>('foveatedMemoryUrl', 'http://127.0.0.1:8400'); await fetch(baseUrl + '/api/consolidate', { method: 'POST', headers: { 'Authorization': 'Bearer ' + this._chat['_workspaceId'] }, signal: AbortSignal.timeout(3000) }); } catch {}
        await this._status.push(); this._post({ type: 'persona_update', activePersona: this._activePersona, personas: PERSONAS });
        break;

      case 'set_persona':
        if (msg.personaId && PERSONAS[msg.personaId as PersonaId]) { this._activePersona = msg.personaId as PersonaId; vscode.workspace.getConfiguration('FoveAI').update('persona', msg.personaId, true); this._post({ type: 'persona_update', activePersona: this._activePersona, personas: PERSONAS }); }
        break;

      case 'set_model':
        if (typeof msg.model === 'string') {
          vscode.workspace.getConfiguration('jenna').update('model', msg.model, true);
          this._post({ type: 'model_updated', model: msg.model });
          await this._status.push();
        }
        break;

      case 'set_xrl':
      case 'set_fovea_level':
        if (typeof msg.level === 'number') {
          this._xrlLevel = Math.max(0, Math.min(5, msg.level));
          vscode.workspace.getConfiguration('foveai').update('xrlLevel', this._xrlLevel, true);
          // Push to the shared env via the proxy — same lever Commando/Commander use.
          try {
            const baseUrl = vscode.workspace.getConfiguration('jenna').get<string>('foveatedMemoryUrl', 'http://127.0.0.1:8400');
            fetch(`${baseUrl}/api/setting`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ key: 'XRLF_PROXY_AGGRESSION', val: String(this._xrlLevel) }),
              signal: AbortSignal.timeout(3000),
            }).catch(() => {});
          } catch {}
          await this._status.push();
        }
        break;

      case 'get_xrl':
        await this._syncXrlFromProxy();
        break;

      case 'attach_file':
        try {
          const files = await vscode.window.showOpenDialog({ canSelectMany: true, openLabel: 'Attach', filters: { 'All': ['*'] } });
          if (files) for (const f of files) {
            const ext = require('path').extname(f.fsPath).toLowerCase();
            const name = require('path').basename(f.fsPath);
            const isImage = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg'].includes(ext);
            if (isImage) { const buf = require('fs').readFileSync(f.fsPath); this._post({ type: 'file_attached', file: { name, path: f.fsPath, content: 'data:image/' + ext.replace('.','') + ';base64,' + buf.toString('base64'), isImage: true } }); }
            else { this._post({ type: 'file_attached', file: { name, path: f.fsPath, content: require('fs').readFileSync(f.fsPath, 'utf8').slice(0, 15000), isImage: false } }); }
          }
        } catch {}
        break;

      case 'get_sessions': await this._sessions.fetchAndSend(); break;
      case 'load_latest_session': await this._sessions.loadLatest(); break;
      case 'get_session_messages': await this._sessions.getMessages(msg.sessionId); break;
      case 'select_session_window': {
        if (msg.sessionId) {
          await this._sessions.getMessages(msg.sessionId);
          this._post({ type: 'hide_sessions_drawer' });
        }
        break;
      }
      case 'open_settings': vscode.commands.executeCommand('workbench.action.openSettings', 'FoveAI'); break;
      case 'toggle_speaker': vscode.workspace.getConfiguration('jenna').update('speakerEnabled', msg.enabled, true); break;
      case 'get_compression_stats': {
        try {
          const baseUrl = vscode.workspace.getConfiguration('jenna').get<string>('foveatedMemoryUrl', 'http://127.0.0.1:8400');
          const r = await fetch(`${baseUrl}/api/compression/stats?workspace_id=${encodeURIComponent(this._chat['_workspaceId'])}`, { signal: AbortSignal.timeout(3000) });
          if (r.ok) {
            const data = await r.json() as any;
            this._post({ type: 'compression_stats', data: { ...data, level: this._xrlLevel } });
          } else {
            this._post({ type: 'compression_stats', data: { level: this._xrlLevel, rawTokens: 0, foveatedTokens: 0, messageCount: 0, moneySaved: 0 } });
          }
        } catch {
          this._post({ type: 'compression_stats', data: { level: this._xrlLevel, rawTokens: 0, foveatedTokens: 0, messageCount: 0, moneySaved: 0 } });
        }
        break;
      }
      case 'start_recording': {
        if (!this._audio) break;
        const ok = await this._audio.startRecording();
        this._post({ type: 'recording_state', recording: ok });
        break;
      }
      case 'stop_recording': {
        if (!this._audio) break;
        const text = await this._audio.stopRecording();
        this._post({ type: 'recording_state', recording: false });
        if (text) this._post({ type: 'dictation_result', text });
        break;
      }
      case 'cancel_recording': this._audio?.cancelRecording(); this._post({ type: 'recording_state', recording: false }); break;
      case 'set_input_mode':
        if (this._audio) this._audio.micMode = msg.mode === 'ptt' ? 'ptt' : 'continuous';
        break;
      case 'webview_ready':
        this._post({ type: 'persona_update', activePersona: this._activePersona, personas: PERSONAS });
        // Push saved speaker config so webview stays in sync with extension settings
        this._post({ type: 'speaker_state', enabled: vscode.workspace.getConfiguration('jenna').get<boolean>('speakerEnabled', true) });
        await this._syncXrlFromProxy();
        await this._status.push();
        await this._pushDiffStats();
        if (this._history.value.length === 0) {
          await this._sessions.loadLatest();
        }
        break;
      case 'analyze_context': await this._analyzer.analyzeContext(); break;
      case 'apply_edit': this._editor.applyEdit(msg.text); break;
      case 'buffer_status': this._post({ type: 'user_message', text: '**Buffer**\\n' + this._buffer.getStatusText() + '\\n\\n' + this._buffer.toDisplayString() }); break;
      case 'buffer_approve': if (typeof msg.id === 'string' && this._buffer.approve(msg.id)) { this._post({ type: 'status_update', status: { online: true, loading: false, message: 'Approved ' + msg.id } }); this._buffer.execute(msg.id); } break;
      case 'buffer_execute_all': const n = await this._buffer.executeAll(); this._post({ type: 'status_update', status: { online: true, loading: false, message: 'Executed ' + n + ' entries' } }); break;
      case 'buffer_discard': if (typeof msg.id === 'string') this._buffer.discard(msg.id); break;
      case 'open_url':
      case 'open_external_url':
        if (typeof msg.url === 'string' && msg.url) {
          vscode.env.openExternal(vscode.Uri.parse(msg.url));
        }
        break;
      case 'open_file':
      case 'open_workspace_file':
        if (typeof msg.file === 'string' && msg.file) {
          const wsFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
          const targetPath = path.isAbsolute(msg.file) ? msg.file : (wsFolder ? path.join(wsFolder, msg.file) : msg.file);
          if (fs.existsSync(targetPath)) {
            vscode.workspace.openTextDocument(targetPath).then(doc => vscode.window.showTextDocument(doc));
          } else {
            vscode.window.showWarningMessage(`File not found: ${msg.file}`);
          }
        }
        break;
      case 'open_explorer':
      case 'reveal_workspace':
        vscode.commands.executeCommand('workbench.view.explorer');
        break;
      case 'list_workspaces': {
        const folders = (vscode.workspace.workspaceFolders || []).map(f => ({ name: f.name, path: f.uri.fsPath }));
        const wsFile = vscode.workspace.workspaceFile?.fsPath;
        const seen = new Set<string>(folders.map(f => f.path));
        const files: { name: string; path: string }[] = [];
        const scanDirs = new Set<string>();
        for (const f of vscode.workspace.workspaceFolders || []) scanDirs.add(path.dirname(f.uri.fsPath));
        if (wsFile) scanDirs.add(path.dirname(wsFile));
        scanDirs.add(require('os').homedir());
        for (const dir of scanDirs) {
          try {
            for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
              if (e.isFile() && e.name.endsWith('.code-workspace')) {
                const p = path.join(dir, e.name);
                if (!seen.has(p)) { seen.add(p); files.push({ name: e.name, path: p }); }
              }
            }
          } catch {}
        }
        this._post({ type: 'workspace_list', folders, workspaceFile: wsFile || null, files });
        break;
      }
      case 'browse_workspace': {
        const picked = await vscode.window.showOpenDialog({
          canSelectFolders: true,
          canSelectFiles: true,
          canSelectMany: false,
          openLabel: 'Open Workspace',
          filters: { 'Workspace / Folder': ['code-workspace', '*'] },
        });
        if (picked && picked[0]) vscode.commands.executeCommand('vscode.openFolder', picked[0]);
        break;
      }
      case 'open_workspace':
        if (typeof msg.path === 'string' && msg.path) {
          vscode.commands.executeCommand('vscode.openFolder', vscode.Uri.file(msg.path));
        }
        break;
      case 'list_projects': {
        const projects: { name: string; path: string }[] = [];
        for (const f of vscode.workspace.workspaceFolders || []) {
          try {
            for (const e of fs.readdirSync(f.uri.fsPath, { withFileTypes: true })) {
              if (e.isDirectory() && !e.name.startsWith('.') && e.name !== 'node_modules') {
                projects.push({ name: `${f.name}/${e.name}`, path: path.join(f.uri.fsPath, e.name) });
              }
            }
          } catch {}
        }
        this._post({ type: 'project_list', projects });
        break;
      }
      case 'reveal_path':
        if (typeof msg.path === 'string' && msg.path) {
          vscode.commands.executeCommand('revealInExplorer', vscode.Uri.file(msg.path));
        }
        break;
      case 'reveal_problems':
        vscode.commands.executeCommand('workbench.actions.view.problems');
        break;
      case 'open_model_dashboard':
        vscode.env.openExternal(vscode.Uri.parse('http://127.0.0.1:8401'));
        break;
      case 'buffer_rollback': const m = await this._buffer.rollbackLast(typeof msg.count === 'number' ? msg.count : 1); this._post({ type: 'status_update', status: { online: true, loading: false, message: 'Rolled back ' + m + ' entries' } }); break;
      case 'clear_memory': await vscode.commands.executeCommand('jenna.clearMemory'); break;
      case 'search_memory': await vscode.commands.executeCommand('jenna.searchMemory'); break;
      case 'switch_model': await vscode.commands.executeCommand('jenna.switchModel'); break;
      case 'reload_webview': await vscode.commands.executeCommand('jenna.reloadWebview'); break;
      case 'toggle_status': await vscode.commands.executeCommand('jenna.toggleStatus'); break;
      case 'alarm_fired': vscode.window.showInformationMessage(`⏰ Jenna alarm — ${typeof msg.time === 'string' ? msg.time : ''}`); break;

      case 'get_diff_stats': await this._pushDiffStats(); break;
      case 'accept_changes': {
        await this._git(['add', '-A']);
        this._post({ type: 'status_update', status: { online: true, loading: false, message: 'Changes accepted — all staged' } });
        await this._pushDiffStats();
        break;
      }
      case 'reject_changes': {
        const pick = await vscode.window.showWarningMessage(
          'Discard ALL uncommitted changes in this workspace? This cannot be undone.',
          { modal: true }, 'Discard Changes');
        if (pick === 'Discard Changes') {
          await this._git(['restore', '--staged', '.']);
          await this._git(['restore', '.']);
          this._post({ type: 'status_update', status: { online: true, loading: false, message: 'Changes discarded' } });
          await this._pushDiffStats();
        }
        break;
      }

      case 'list_mcp_servers': {
        const home = require('os').homedir();
        const wsFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
        const files = [
          { scope: 'devin-user', file: path.join(home, '.config', 'devin', 'mcp_config.json') },
          { scope: 'devin-project', file: path.join(wsFolder, '.devin', 'mcp_config.json') },
          { scope: 'devin-local', file: path.join(wsFolder, '.devin', 'mcp_config.local.json') },
          { scope: 'agents', file: path.join(wsFolder, '.agents', 'mcp_config.json') },
          { scope: 'kilocode', file: path.join(wsFolder, '.kilocode', 'mcp.json') },
          { scope: 'roo', file: path.join(wsFolder, '.roo', 'mcp.json') },
        ];
        const servers: { name: string; scope: string; command: string; disabled: boolean }[] = [];
        for (const f of files) {
          try {
            if (!fs.existsSync(f.file)) continue;
            const cfg = JSON.parse(fs.readFileSync(f.file, 'utf8'));
            const mcp = cfg.mcpServers || {};
            for (const [name, s] of Object.entries<any>(mcp)) {
              servers.push({
                name,
                scope: f.scope,
                command: s.command ? `${s.command} ${(s.args || []).join(' ')}`.trim() : (s.url || ''),
                disabled: !!s.disabled,
              });
            }
          } catch { /* unreadable config — skip */ }
        }
        this._post({ type: 'mcp_servers', servers });
        break;
      }
    }
  }

  private _git(args: string[]): Promise<string> {
    return new Promise((resolve) => {
      const cwd = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (!cwd) return resolve('');
      cp.execFile('git', args, { cwd }, (err, stdout) => resolve(err ? '' : stdout));
    });
  }

  private async _pushDiffStats(): Promise<void> {
    let files = 0, added = 0, removed = 0;
    const numstat = await this._git(['diff', '--numstat', 'HEAD']);
    for (const line of numstat.split('\n')) {
      const m = line.match(/^(\d+|-)\t(\d+|-)\t/);
      if (m) {
        files++;
        if (m[1] !== '-') added += parseInt(m[1], 10);
        if (m[2] !== '-') removed += parseInt(m[2], 10);
      }
    }
    // Untracked files (and all changes when repo has no HEAD yet)
    const status = await this._git(['status', '--porcelain']);
    for (const line of status.split('\n')) {
      if (line.startsWith('??')) files++;
      else if (line.trim() && !numstat.trim()) files++;
    }
    this._post({ type: 'diff_stats', files, added, removed });
  }
}

