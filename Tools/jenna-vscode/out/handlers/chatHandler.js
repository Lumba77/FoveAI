"use strict";
/**
 * chatHandler.ts — Handles AI chat, dictation, context farming, auto-edit, and task extraction.
 * This is the core execution layer after the message router dispatches.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.ChatHandler = void 0;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const contextFarmer_1 = require("../memory/contextFarmer");
const intentEngine_1 = require("../intentEngine");
class ChatHandler {
    _client;
    _logger;
    _workspaceId;
    _getPersona;
    _getXrl;
    _getSessionStart;
    _post;
    _buffer;
    _history = [];
    constructor(_client, _logger, _workspaceId, _getPersona, _getXrl, _getSessionStart, _post, _buffer) {
        this._client = _client;
        this._logger = _logger;
        this._workspaceId = _workspaceId;
        this._getPersona = _getPersona;
        this._getXrl = _getXrl;
        this._getSessionStart = _getSessionStart;
        this._post = _post;
        this._buffer = _buffer;
    }
    get history() { return this._history; }
    set history(h) { this._history = h; }
    async handleChat(text, tasks) {
        if (!text)
            return;
        // Intent engine for agent mode
        const config = vscode.workspace.getConfiguration('jenna');
        const agentMode = config.get('agentMode', false);
        if (agentMode && text.length < 2000) {
            try {
                const intent = (0, intentEngine_1.classifyIntent)(text);
                if (intent.confidence > 0.5 && intent.type !== 'chat') {
                    this._post({ type: 'status_update', status: { online: true, loading: true, message: 'Intent: ' + intent.type + ' (' + Math.round(intent.confidence * 100) + '%)' } });
                    await (0, intentEngine_1.processUserIntent)(text, this._client, this._workspaceId, { handleExternalChat: (t) => this._handleChat(t) });
                    this._post({ type: 'status_update', status: { online: true, loading: false, message: 'Intent complete' } });
                    return;
                }
            }
            catch { }
        }
        // Buffer absorb
        await this._buffer.absorb(text, 'text');
        await this._handleChat(text, tasks);
    }
    async handleDictation(rawText) {
        try {
            const config = vscode.workspace.getConfiguration('jenna');
            const baseUrl = config.get('foveatedMemoryUrl', 'http://127.0.0.1:8400');
            const prompt = 'You are an expert transcription editor. Fix any stutters, add correct punctuation, capitalization, and make this spoken dictation perfectly clear and professional. Do not add any conversational filler. ONLY output the corrected text.\n\nDictation:\n' + rawText;
            const res = await fetch(baseUrl + '/v1/chat/completions', {
                method: 'POST', headers: { 'Authorization': 'Bearer ' + this._workspaceId, 'Content-Type': 'application/json' },
                body: JSON.stringify({ model: 'auto', messages: [{ role: 'user', content: prompt }], temperature: 0.2, max_tokens: 1000 })
            });
            if (res.ok) {
                const data = await res.json();
                let formatted = data.choices?.[0]?.message?.content || rawText;
                formatted = formatted.replace(/ thinking[\s\S]*?<\/think>/gi, '').trim();
                await this._handleChat(formatted);
            }
            else {
                await this._handleChat(rawText);
            }
        }
        catch {
            await this._handleChat(rawText);
        }
    }
    async _handleChat(userText, tasks) {
        if (!this._post)
            return;
        const config = vscode.workspace.getConfiguration('jenna');
        const model = config.get('model', 'auto');
        // Farm large inputs
        let finalText = userText;
        let farmed = null;
        if (userText.length > 4000) {
            this._post({ type: 'status_update', status: { online: true, loading: true, message: 'Farming large context...' } });
            try {
                farmed = await (0, contextFarmer_1.farmContext)(userText, this._client, this._workspaceId, this._getPersona());
                finalText = farmed.digest;
                if (farmed.tasks.length > 0) {
                    tasks = [...(tasks || []), ...farmed.tasks];
                    this._post({ type: 'tasks_update', tasks: farmed.tasks });
                }
                this._post({ type: 'status_update', status: { online: true, loading: false, message: 'Farmed: ' + userText.length + '->' + farmed.farmedLength + ' chars' } });
            }
            catch { }
        }
        this._history.push({ role: 'user', content: finalText });
        this._post({ type: 'stream_start' });
        let fullResponse = '';
        try {
            const activeSid = this._workspaceId + '_' + this._getSessionStart();
            const stream = this._client.chat(this._history, {
                model, workspaceId: this._workspaceId,
                stream: config.get('streamingEnabled', true),
                persona: this._getPersona(),
                compressionLevel: this._getXrl(),
                sessionId: activeSid,
                ...(tasks && tasks.length > 0 ? { tasks } : {}),
            });
            for await (const chunk of stream) {
                fullResponse += chunk;
                this._post({ type: 'stream_chunk', chunk });
            }
            this._history.push({ role: 'assistant', content: fullResponse });
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
                        if (!editor.selection.isEmpty)
                            eb.replace(editor.selection, code);
                        else
                            eb.insert(editor.selection.active, code);
                    }).then(s => {
                        if (s && editor.document.isDirty) {
                            editor.document.save();
                            this._post({ type: 'status_update', status: { online: true, loading: false, message: 'Code auto-applied & saved' } });
                        }
                    });
                }
            }
            // Extract tasks
            const tr = /[-*]\s+\[([ xX])\]\s+(.+)/g;
            const nt = [];
            let tm;
            while ((tm = tr.exec(fullResponse)) !== null)
                nt.push({ text: tm[2].trim(), done: tm[1].toLowerCase() === 'x' });
            if (nt.length > 0)
                this._post({ type: 'tasks_update', tasks: nt });
            this._post({ type: 'turn_complete', applied: !!(blocks && blocks.length > 0) });
            this._post({ type: 'stream_end' });
            // Trigger session list refresh
            try {
                const baseUrl = config.get('foveatedMemoryUrl', 'http://127.0.0.1:8400');
                fetch(baseUrl + '/api/session/generate-title', { method: 'POST', headers: { 'Authorization': 'Bearer ' + this._workspaceId, 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: activeSid }), signal: AbortSignal.timeout(10000) }).catch(() => { });
            }
            catch { }
        }
        catch (err) {
            this._post({ type: 'stream_error', error: err instanceof Error ? err.message : String(err) });
        }
    }
    _saveSessionLocally(preview) {
        try {
            const lp = path.join(__dirname, '..', 'sessions.json');
            let s = [];
            try {
                if (fs.existsSync(lp))
                    s = JSON.parse(fs.readFileSync(lp, 'utf8')) || [];
            }
            catch { }
            s.unshift({ session_id: this._workspaceId + '_' + Date.now(), workspace_id: this._workspaceId, count: this._history.length, last_updated: new Date().toISOString(), preview: preview.slice(0, 120) });
            fs.writeFileSync(lp, JSON.stringify(s.slice(0, 50), null, 2), 'utf8');
        }
        catch { }
    }
}
exports.ChatHandler = ChatHandler;
//# sourceMappingURL=chatHandler.js.map