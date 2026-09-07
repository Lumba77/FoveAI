"use strict";
/**
 * executionBuffer.ts — The Buffer Zone
 *
 * Continuous listening buffer between user input and code execution.
 * All intents, edits, and actions land here first. Nothing executes
 * until approved. Every action has a revert path. The buffer is
 * visible, editable, and rollback-capable.
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
exports.ExecutionBuffer = void 0;
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
class ExecutionBuffer {
    _workspaceRoot;
    entries = [];
    entryCounter = 0;
    _onChange = null;
    _onSendToChat = null;
    constructor(_workspaceRoot) {
        this._workspaceRoot = _workspaceRoot;
    }
    setSendToChat(cb) { this._onSendToChat = cb; }
    onChange(cb) { this._onChange = cb; }
    getEntries() { return [...this.entries].reverse(); }
    getPending() { return this.entries.filter(e => e.status === 'draft' || e.status === 'approved'); }
    get pendingCount() { return this.getPending().length; }
    addEntry(entry) {
        const id = `buf_${Date.now().toString(36)}_${++this.entryCounter}`;
        const full = {
            ...entry, id, timestamp: Date.now(), status: 'draft',
            rollbackScript: entry.edits.map(e => ({
                file: e.file,
                originalContent: e.originalContent,
                newContent: e.originalContent,
            })),
        };
        this.entries.push(full);
        this._notify();
        return full;
    }
    async absorb(input, source = 'text') {
        let intentType = 'chat', confidence = 0.3;
        try {
            const { classifyIntent } = await import('./intentEngine.js');
            const intent = classifyIntent(input);
            intentType = intent.type;
            confidence = intent.confidence;
        }
        catch { }
        const edits = [];
        const fileRefs = input.match(/`([^`]+\.[a-zA-Z]+)`|([a-zA-Z0-9_-]+\.[a-zA-Z]+)/g);
        if (fileRefs)
            for (const ref of fileRefs) {
                const clean = ref.replace(/`/g, '');
                const fp = path.resolve(this._workspaceRoot, clean);
                if (fs.existsSync(fp))
                    edits.push({ file: clean, originalContent: fs.readFileSync(fp, 'utf8'), newContent: '' });
            }
        return this.addEntry({ source, summary: input.slice(0, 100), rawInput: input, intentType, confidence, edits, planSteps: [`Process: ${intentType}`], userMessage: input });
    }
    approve(id) { const e = this.entries.find(x => x.id === id); if (!e || e.status !== 'draft')
        return false; e.status = 'approved'; this._notify(); return true; }
    approveAll() { let c = 0; this.entries.forEach(e => { if (e.status === 'draft') {
        e.status = 'approved';
        c++;
    } }); if (c)
        this._notify(); return c; }
    discard(id) { const e = this.entries.find(x => x.id === id); if (!e || e.status === 'executed')
        return false; e.status = 'discarded'; this._notify(); return true; }
    async execute(id) {
        const e = this.entries.find(x => x.id === id);
        if (!e || e.status !== 'approved')
            return false;
        e.status = 'executed';
        e.result = 'Sent to AI';
        this._notify();
        const h = `[Buffer: ${e.intentType} (${Math.round(e.confidence * 100)}%)] Source: ${e.source}\n---\n${e.rawInput}`;
        if (e.edits.length > 0) {
            const ctx = e.edits.map(x => `\`\`\`\n// ${x.file}\n${x.originalContent.slice(0, 2000)}\n\`\`\``).join('\n');
            if (this._onSendToChat)
                await this._onSendToChat(`${h}\n\nStaged:\n${ctx}\n\n${e.rawInput}`);
        }
        else if (this._onSendToChat)
            await this._onSendToChat(`${h}\n\n${e.rawInput}`);
        return true;
    }
    async executeAll() { let c = 0; for (const e of this.entries.filter(x => x.status === 'approved')) {
        await this.execute(e.id);
        c++;
        await new Promise(r => setTimeout(r, 500));
    } return c; }
    async rollback(id) {
        const e = this.entries.find(x => x.id === id);
        if (!e || e.status !== 'executed')
            return false;
        let ok = true;
        for (const rev of e.rollbackScript)
            try {
                fs.writeFileSync(path.resolve(this._workspaceRoot, rev.file), rev.newContent, 'utf8');
            }
            catch (err) {
                ok = false;
                e.error = `Rollback failed: ${err}`;
            }
        e.status = ok ? 'reverted' : 'failed';
        e.result = ok ? 'Rolled back' : 'Failed';
        this._notify();
        return ok;
    }
    async rollbackLast(n = 1) { let c = 0; for (const e of this.entries.filter(x => x.status === 'executed').reverse().slice(0, n)) {
        if (await this.rollback(e.id))
            c++;
    } return c; }
    clean() { const b = this.entries.length; this.entries = this.entries.filter(e => e.status === 'draft' || e.status === 'approved' || e.status === 'executed'); const c = b - this.entries.length; if (c)
        this._notify(); return c; }
    clearAll() { this.entries = []; this._notify(); }
    getStatusText() { const p = this.getPending().length; const ex = this.entries.filter(e => e.status === 'executed').length; const r = this.entries.filter(e => e.status === 'reverted').length; return `📦 ${p} pending | ${ex} done | ${r} reverted`; }
    toDisplayString() { if (!this.entries.length)
        return '**Buffer empty**'; return this.getEntries().map(e => { const i = e.status === 'draft' ? '📝' : e.status === 'approved' ? '✅' : e.status === 'executed' ? '⚡' : e.status === 'reverted' ? '↩️' : e.status === 'failed' ? '❌' : '🗑️'; return `${i} **${e.id}** [${e.intentType}] ${e.summary.slice(0, 80)} — _${e.status}_`; }).join('\n'); }
    _notify() { this._onChange?.(); }
    dispose() { }
}
exports.ExecutionBuffer = ExecutionBuffer;
//# sourceMappingURL=executionBuffer.js.map