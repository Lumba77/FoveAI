"use strict";
/**
 * sessionManager.ts — Session persistence, retrieval, title generation.
 * HTTP-first with NeDB disk fallback for offline operation.
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
exports.SessionManager = void 0;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
class SessionManager {
    _workspaceId;
    _storageUri;
    _post;
    _getHistory;
    constructor(_workspaceId, _storageUri, _post, _getHistory) {
        this._workspaceId = _workspaceId;
        this._storageUri = _storageUri;
        this._post = _post;
        this._getHistory = _getHistory;
    }
    async fetchAndSend() {
        try {
            const b = vscode.workspace.getConfiguration('jenna').get('foveatedMemoryUrl', 'http://127.0.0.1:8400');
            const r = await fetch(b + '/api/sessions', { headers: { 'Authorization': 'Bearer ' + this._workspaceId }, signal: AbortSignal.timeout(3000) });
            if (r.ok) {
                const d = await r.json();
                const s = d.sessions || [];
                if (s.length > 0)
                    this._writeLocal(s.slice(0, 50));
                this._post({ type: 'sessions_list', sessions: s });
                setTimeout(() => this._genTitles(s, b), 2000);
                return;
            }
        }
        catch { }
        const n = this._readNedb();
        if (n.length > 0) {
            this._post({ type: 'sessions_list', sessions: n });
            return;
        }
        const l = this._readLocal();
        if (l.length > 0) {
            this._post({ type: 'sessions_list', sessions: l });
            return;
        }
        this._post({ type: 'sessions_offline' });
    }
    async loadLatest() {
        try {
            const b = vscode.workspace.getConfiguration('jenna').get('foveatedMemoryUrl', 'http://127.0.0.1:8400');
            const r = await fetch(b + '/api/sessions', { headers: { 'Authorization': 'Bearer ' + this._workspaceId }, signal: AbortSignal.timeout(3000) });
            if (r.ok) {
                const d = await r.json();
                const s = d.sessions || [];
                if (s.length > 0) {
                    s.sort((a, b) => (b.last_updated || '').localeCompare(a.last_updated || ''));
                    const id = s[0].session_id || s[0].id;
                    if (id) {
                        await this.getMessages(id);
                        return;
                    }
                }
            }
        }
        catch { }
        let s = this._readNedb();
        if (s.length === 0)
            s = this._readLocal();
        if (s.length > 0) {
            s.sort((a, b) => (b.last_updated || '').localeCompare(a.last_updated || ''));
            const id = s[0].session_id || s[0].id;
            if (id)
                await this.getMessages(id);
        }
    }
    async getMessages(sid) {
        const id = sid || this._workspaceId;
        let m = [];
        try {
            const b = vscode.workspace.getConfiguration('jenna').get('foveatedMemoryUrl', 'http://127.0.0.1:8400');
            const r = await fetch(b + '/api/session/messages?session_id=' + encodeURIComponent(id), { headers: { 'Authorization': 'Bearer ' + this._workspaceId }, signal: AbortSignal.timeout(3000) });
            if (r.ok) {
                const d = await r.json();
                m = d.messages || [];
            }
        }
        catch { }
        if (m.length === 0)
            m = this._readNedbMsgs(id);
        const h = this._getHistory();
        h.length = 0;
        m.forEach((x) => h.push({ role: x.role, content: x.content }));
        this._post({ type: 'session_messages', sessionId: id, messages: m });
    }
    saveLocal(p) { this._saveLocalPreview(p); }
    _lp() { return path.join(this._storageUri.fsPath, 'sessions.json'); }
    _readLocal() { try {
        const p = this._lp();
        if (fs.existsSync(p))
            return JSON.parse(fs.readFileSync(p, 'utf8')) || [];
    }
    catch { } return []; }
    _writeLocal(s) { try {
        fs.writeFileSync(this._lp(), JSON.stringify(s, null, 2), 'utf8');
    }
    catch { } }
    _saveLocalPreview(p) {
        try {
            const s = this._readLocal();
            s.unshift({ session_id: this._workspaceId + '_' + Date.now(), workspace_id: this._workspaceId, count: 1, last_updated: new Date().toISOString(), preview: p.slice(0, 120) });
            this._writeLocal(s.slice(0, 50));
        }
        catch { }
    }
    _readNedb() {
        try {
            const d = path.join(this._storageUri.fsPath, 'memory');
            if (!fs.existsSync(d))
                return [];
            let ss = [];
            try {
                ss = fs.readdirSync(d).filter(n => { try {
                    return fs.statSync(path.join(d, n)).isDirectory();
                }
                catch {
                    return false;
                } });
            }
            catch { }
            for (const db of Array.from(new Set([this._workspaceId, 'default', 'FoveAI', ...ss]))) {
                const p = path.join(d, db, 'memory.db');
                if (fs.existsSync(p))
                    return this._parseNedb(p);
            }
        }
        catch { }
        return [];
    }
    _readNedbMsgs(sid) {
        try {
            const d = path.join(this._storageUri.fsPath, 'memory');
            if (!fs.existsSync(d))
                return [];
            let ss = [];
            try {
                ss = fs.readdirSync(d).filter(n => { try {
                    return fs.statSync(path.join(d, n)).isDirectory();
                }
                catch {
                    return false;
                } });
            }
            catch { }
            for (const db of Array.from(new Set([this._workspaceId, 'default', 'FoveAI', ...ss]))) {
                const p = path.join(d, db, 'memory.db');
                if (fs.existsSync(p)) {
                    const ms = [];
                    for (const l of fs.readFileSync(p, 'utf8').split('\n')) {
                        const t = l.trim();
                        if (!t)
                            continue;
                        try {
                            const o = JSON.parse(t);
                            if (o.session_id === sid && o.role && o.content)
                                ms.push({ role: o.role, content: o.content, timestamp: o.timestamp || '' });
                        }
                        catch { }
                    }
                    if (ms.length > 0)
                        return ms;
                }
            }
        }
        catch { }
        return [];
    }
    _parseNedb(p) {
        const m = new Map();
        for (const l of fs.readFileSync(p, 'utf8').split('\n')) {
            const t = l.trim();
            if (!t)
                continue;
            try {
                const o = JSON.parse(t);
                if (o.deleted || o.theme_name)
                    continue;
                const id = o.session_id || 'default';
                if (!m.has(id))
                    m.set(id, { session_id: id, workspace_id: this._workspaceId, count: 0, last_updated: o.timestamp || '', preview: (o.content || '').slice(0, 120) });
                const e = m.get(id);
                e.count++;
                const ts = o.timestamp || '';
                if (ts && ts > (e.last_updated || ''))
                    e.last_updated = ts;
                if (o.role === 'user' && o.content)
                    e.preview = o.content.slice(0, 120);
            }
            catch { }
        }
        return Array.from(m.values()).sort((a, b) => (b.last_updated || '').localeCompare(a.last_updated || '')).slice(0, 50);
    }
    async _genTitles(s, b) {
        let g = false, a = 0;
        for (const x of s) {
            if (a >= 2)
                break;
            const c = (x.title || '').trim();
            if ((!c || c.length <= 4) && (x.count || 0) >= 3) {
                a++;
                try {
                    const r = await fetch(b + '/api/session/generate-title', { method: 'POST', headers: { 'Authorization': 'Bearer ' + this._workspaceId, 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: x.session_id }), signal: AbortSignal.timeout(10000) });
                    if (r.ok) {
                        const d = await r.json();
                        if (d.title) {
                            x.title = d.title;
                            if (d.keywords)
                                x.keywords = d.keywords;
                            g = true;
                        }
                    }
                }
                catch { }
            }
        }
        if (g)
            this._post({ type: 'sessions_list', sessions: s });
    }
}
exports.SessionManager = SessionManager;
//# sourceMappingURL=sessionManager.js.map