/**
 * chatHandler.ts — Handles AI chat, dictation, context farming, auto-edit, and task extraction.
 * This is the core execution layer after the message router dispatches.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { FoveatedClient, ChatMessage, PersonaId } from '../memory/foveatedClient';
import { SessionLogger } from '../bonding/sessionLogger';
import { FarmedContext, farmContext } from '../memory/contextFarmer';
import { processUserIntent, classifyIntent } from '../intentEngine';
import { ExecutionBuffer } from '../executionBuffer';
import { AgentTools, AGENT_TOOLS_PROMPT, parseToolCalls } from '../agentTools';

export class ChatHandler {
  private _history: ChatMessage[] = [];

  constructor(
    private _client: FoveatedClient,
    private _logger: SessionLogger,
    private _workspaceId: string,
    private _getPersona: () => PersonaId,
    private _getXrl: () => number,
    private _getSessionStart: () => string,
    private _post: (msg: Record<string, unknown>) => void,
    private _buffer: ExecutionBuffer,
  ) {}

  get history(): ChatMessage[] { return this._history; }
  set history(h: ChatMessage[]) { this._history = h; }

  async handleChat(text: string, tasks?: { text: string; done: boolean }[]): Promise<void> {
    if (!text) return;

    // Intent engine for agent mode — superseded by the agentic tool loop
    // (agentTools), which lets the model drive tools itself instead of a
    // client-side keyword classifier pre-empting the conversation.
    const config = vscode.workspace.getConfiguration('jenna');
    const agentMode = config.get<boolean>('agentMode', false) && !config.get<boolean>('agentTools', true);
    if (agentMode && text.length < 2000) {
      try {
        const intent = classifyIntent(text);
        if (intent.confidence > 0.5 && intent.type !== 'chat') {
          this._post({ type: 'status_update', status: { online: true, loading: true, message: 'Intent: ' + intent.type + ' (' + Math.round(intent.confidence * 100) + '%)' } });
          await processUserIntent(text, this._client, this._workspaceId, { handleExternalChat: (t) => this._handleChat(t) });
          this._post({ type: 'status_update', status: { online: true, loading: false, message: 'Intent complete' } });
          return;
        }
      } catch {}
    }

    // Buffer absorb
    await this._buffer.absorb(text, 'text');
    await this._handleChat(text, tasks);
  }

  async handleDictation(rawText: string): Promise<void> {
    try {
      const config = vscode.workspace.getConfiguration('jenna');
      const baseUrl = config.get<string>('foveatedMemoryUrl', 'http://127.0.0.1:8400');
      const prompt = 'You are an expert transcription editor. Fix any stutters, add correct punctuation, capitalization, and make this spoken dictation perfectly clear and professional. Do not add any conversational filler. ONLY output the corrected text.\n\nDictation:\n' + rawText;
      const res = await fetch(baseUrl + '/v1/chat/completions', {
        method: 'POST', headers: { 'Authorization': 'Bearer ' + this._workspaceId, 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: 'auto', messages: [{ role: 'user', content: prompt }], temperature: 0.2, max_tokens: 1000 })
      });
      if (res.ok) {
        const data = await res.json() as any;
        let formatted = data.choices?.[0]?.message?.content || rawText;
        formatted = formatted.replace(/ thinking[\s\S]*?<\/think>/gi, '').trim();
        await this._handleChat(formatted);
      } else { await this._handleChat(rawText); }
    } catch { await this._handleChat(rawText); }
  }

  private async _handleChat(userText: string, tasks?: { text: string; done: boolean }[]): Promise<void> {
    if (!this._post) return;

    const config = vscode.workspace.getConfiguration('jenna');
    const model = config.get<string>('model', 'auto');

    // Farm large inputs
    let finalText = userText;
    let farmed: FarmedContext | null = null;
    if (userText.length > 4000) {
      this._post({ type: 'status_update', status: { online: true, loading: true, message: 'Farming large context...' } });
      try {
        farmed = await farmContext(userText, this._client, this._workspaceId, this._getPersona());
        finalText = farmed.digest;
        if (farmed.tasks.length > 0) { tasks = [...(tasks || []), ...farmed.tasks]; this._post({ type: 'tasks_update', tasks: farmed.tasks }); }
        this._post({ type: 'status_update', status: { online: true, loading: false, message: 'Farmed: ' + userText.length + '->' + farmed.farmedLength + ' chars' } });
      } catch {}
    }

    this._history.push({ role: 'user', content: finalText });
    this._post({ type: 'stream_start' });

    const toolsEnabled = config.get<boolean>('agentTools', true);
    const tools = toolsEnabled ? new AgentTools(this._client, this._workspaceId) : null;
    const MAX_TOOL_ROUNDS = 6;

    let fullResponse = '';
    try {
      const activeSid = this._workspaceId + '_' + this._getSessionStart();
      const chatOpts = {
        model, workspaceId: this._workspaceId,
        stream: config.get<boolean>('streamingEnabled', true),
        persona: this._getPersona(),
        compressionLevel: this._getXrl(),
        sessionId: activeSid,
        customSystemPrompt: toolsEnabled ? AGENT_TOOLS_PROMPT : undefined,
        ...(tasks && tasks.length > 0 ? { tasks } : {}),
      };
      const stream = this._client.chat(this._history, chatOpts);
      for await (const chunk of stream) { fullResponse += chunk; this._post({ type: 'stream_chunk', chunk }); }

      this._history.push({ role: 'assistant', content: fullResponse });

      // ── Agentic tool loop ──
      // If the model emitted <tool> calls, execute them and feed the results
      // back as a user message, then let it continue. Repeats until she stops
      // calling tools, emits <done/>, or hits the round cap.
      if (tools) {
        for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
          const calls = parseToolCalls(fullResponse);
          if (calls.length === 0) break;

          const names = calls.map(c => c.name + (c.args.path || c.args.query || c.args.cmd ? ':' + (c.args.path || c.args.query || c.args.cmd) : '')).join(' · ');
          this._post({ type: 'status_update', status: { online: true, loading: true, message: '⚙ tools: ' + names } });
          const { feedback, isDone } = await tools.executeAll(calls);
          if (isDone) break;
          if (!feedback) break;

          this._history.push({ role: 'user', content: feedback });
          this._post({ type: 'stream_start' });
          fullResponse = '';
          const cont = this._client.chat(this._history, chatOpts);
          for await (const chunk of cont) { fullResponse += chunk; this._post({ type: 'stream_chunk', chunk }); }
          this._history.push({ role: 'assistant', content: fullResponse });
          this._post({ type: 'stream_end' });
        }
        this._post({ type: 'status_update', status: { online: true, loading: false } });
      }

      this._logger.recordTurn(userText, fullResponse);
      this._saveSessionLocally(userText);

      // Auto-apply code blocks
      const blocks = fullResponse.match(/`(?:\w+)?\n[\s\S]*?`/g);
      if (blocks && blocks.length > 0 && vscode.window.activeTextEditor) {
        const lastBlock = blocks[blocks.length - 1];
        const code = lastBlock.replace(/`(?:\w+)?\n/, '').replace(/`$/, '').trim();
        if (code.length > 10) {
          const editor = vscode.window.activeTextEditor;
          editor.edit(eb => {
            if (!editor.selection.isEmpty) eb.replace(editor.selection, code);
            else eb.insert(editor.selection.active, code);
          }).then(s => {
            if (s && editor.document.isDirty) { editor.document.save(); this._post({ type: 'status_update', status: { online: true, loading: false, message: 'Code auto-applied & saved' } }); }
          });
        }
      }

      // Extract tasks
      const tr = /[-*]\s+\[([ xX])\]\s+(.+)/g;
      const nt: { text: string; done: boolean }[] = [];
      let tm: RegExpExecArray | null;
      while ((tm = tr.exec(fullResponse)) !== null) nt.push({ text: tm[2].trim(), done: tm[1].toLowerCase() === 'x' });
      if (nt.length > 0) this._post({ type: 'tasks_update', tasks: nt });

      this._post({ type: 'turn_complete', applied: !!(blocks && blocks.length > 0) });
      this._post({ type: 'stream_end' });

      // Trigger session list refresh
      try {
        const baseUrl = config.get<string>('foveatedMemoryUrl', 'http://127.0.0.1:8400');
        fetch(baseUrl + '/api/session/generate-title', { method: 'POST', headers: { 'Authorization': 'Bearer ' + this._workspaceId, 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: activeSid }), signal: AbortSignal.timeout(10000) }).catch(() => {});
      } catch {}
    } catch (err) {
      this._post({ type: 'stream_error', error: err instanceof Error ? err.message : String(err) });
    }
  }

  private _saveSessionLocally(preview: string): void {
    try {
      const lp = path.join(__dirname, '..', 'sessions.json');
      let s: any[] = [];
      try { if (fs.existsSync(lp)) s = JSON.parse(fs.readFileSync(lp, 'utf8')) || []; } catch {}
      s.unshift({ session_id: this._workspaceId + '_' + Date.now(), workspace_id: this._workspaceId, count: this._history.length, last_updated: new Date().toISOString(), preview: preview.slice(0, 120) });
      fs.writeFileSync(lp, JSON.stringify(s.slice(0, 50), null, 2), 'utf8');
    } catch {}
  }
}
