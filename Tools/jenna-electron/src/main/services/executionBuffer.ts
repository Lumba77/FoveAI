/**
 * executionBuffer.ts — Ported from jenna-vscode (zero VS Code dependency)
 * Pure Node.js path/fs version.
 */

import * as path from 'path';
import * as fs from 'fs';

export type BufferEntryStatus = 'draft' | 'approved' | 'executed' | 'reverted' | 'failed' | 'discarded';

export interface StagedEdit { file: string; originalContent: string; newContent: string; }
export interface BufferEntry {
  id: string; timestamp: number;
  source: 'voice' | 'text' | 'file' | 'scan' | 'intent' | 'plugin' | 'manual';
  summary: string; status: BufferEntryStatus; rawInput: string;
  intentType: string; confidence: number; edits: StagedEdit[];
  planSteps: string[]; userMessage: string; rollbackScript: StagedEdit[];
  result?: string; error?: string;
}

export class ExecutionBuffer {
  private entries: BufferEntry[] = [];
  private entryCounter = 0;
  private _onChange: (() => void) | null = null;
  private _onSendToChat: ((text: string) => Promise<void>) | null = null;

  constructor(private _workspaceRoot: string) {}

  setSendToChat(cb: (text: string) => Promise<void>): void { this._onSendToChat = cb; }
  onChange(cb: () => void): void { this._onChange = cb; }
  getEntries(): BufferEntry[] { return [...this.entries].reverse(); }
  getPending(): BufferEntry[] { return this.entries.filter(e => e.status === 'draft' || e.status === 'approved'); }
  get pendingCount(): number { return this.getPending().length; }

  addEntry(entry: Omit<BufferEntry, 'id' | 'timestamp' | 'status' | 'rollbackScript'>): BufferEntry {
    const id = `buf_${Date.now().toString(36)}_${++this.entryCounter}`;
    const full: BufferEntry = {
      ...entry, id, timestamp: Date.now(), status: 'draft',
      rollbackScript: entry.edits.map(e => ({ file: e.file, originalContent: e.originalContent, newContent: e.originalContent })),
    };
    this.entries.push(full);
    this._notify();
    return full;
  }

  async absorb(input: string, source: 'voice' | 'text' | 'file' | 'scan' | 'intent' | 'plugin' = 'text'): Promise<BufferEntry> {
    let intentType = 'chat', confidence = 0.3;
    try { const { classifyIntent } = await import('./intentEngine.js'); const intent = classifyIntent(input); intentType = intent.type; confidence = intent.confidence; } catch { /* ignore */ }
    const edits: StagedEdit[] = [];
    const fileRefs = input.match(/`([^`]+\.[a-zA-Z]+)`|([a-zA-Z0-9_-]+\.[a-zA-Z]+)/g);
    if (fileRefs) for (const ref of fileRefs) {
      const clean = ref.replace(/`/g, ''); const fp = path.resolve(this._workspaceRoot, clean);
      if (fs.existsSync(fp)) edits.push({ file: clean, originalContent: fs.readFileSync(fp, 'utf8'), newContent: '' });
    }
    return this.addEntry({ source, summary: input.slice(0, 100), rawInput: input, intentType, confidence, edits, planSteps: [`Process: ${intentType}`], userMessage: input });
  }

  approve(id: string): boolean { const e = this.entries.find(x => x.id === id); if (!e || e.status !== 'draft') return false; e.status = 'approved'; this._notify(); return true; }
  approveAll(): number { let c = 0; this.entries.forEach(e => { if (e.status === 'draft') { e.status = 'approved'; c++; } }); if (c) this._notify(); return c; }
  discard(id: string): boolean { const e = this.entries.find(x => x.id === id); if (!e || e.status === 'executed') return false; e.status = 'discarded'; this._notify(); return true; }

  async execute(id: string): Promise<boolean> {
    const e = this.entries.find(x => x.id === id);
    if (!e || e.status !== 'approved') return false;
    e.status = 'executed'; e.result = 'Sent to AI'; this._notify();
    const h = `[Buffer: ${e.intentType} (${Math.round(e.confidence * 100)}%)] Source: ${e.source}\n---\n${e.rawInput}`;
    if (e.edits.length > 0) {
      const ctx = e.edits.map(x => `\`\`\`\n// ${x.file}\n${x.originalContent.slice(0, 2000)}\n\`\`\``).join('\n');
      if (this._onSendToChat) await this._onSendToChat(`${h}\n\nStaged:\n${ctx}\n\n${e.rawInput}`);
    } else if (this._onSendToChat) await this._onSendToChat(`${h}\n\n${e.rawInput}`);
    return true;
  }

  async executeAll(): Promise<number> { let c = 0; for (const e of this.entries.filter(x => x.status === 'approved')) { await this.execute(e.id); c++; await new Promise(r => setTimeout(r, 500)); } return c; }

  async rollback(id: string): Promise<boolean> {
    const e = this.entries.find(x => x.id === id);
    if (!e || e.status !== 'executed') return false;
    let ok = true;
    for (const rev of e.rollbackScript) try { fs.writeFileSync(path.resolve(this._workspaceRoot, rev.file), rev.newContent, 'utf8'); } catch (err) { ok = false; e.error = `Rollback failed: ${err}`; }
    e.status = ok ? 'reverted' : 'failed'; e.result = ok ? 'Rolled back' : 'Failed';
    this._notify(); return ok;
  }

  async rollbackLast(n: number = 1): Promise<number> { let c = 0; for (const e of this.entries.filter(x => x.status === 'executed').reverse().slice(0, n)) { if (await this.rollback(e.id)) c++; } return c; }
  clean(): number { const b = this.entries.length; this.entries = this.entries.filter(e => e.status === 'draft' || e.status === 'approved' || e.status === 'executed'); const c = b - this.entries.length; if (c) this._notify(); return c; }
  clearAll(): void { this.entries = []; this._notify(); }
  getStatusText(): string { const p = this.getPending().length; const ex = this.entries.filter(e => e.status === 'executed').length; const r = this.entries.filter(e => e.status === 'reverted').length; return `📦 ${p} pending | ${ex} done | ${r} reverted`; }
  toDisplayString(): string { if (!this.entries.length) return '**Buffer empty**'; return this.getEntries().map(e => { const ic = e.status === 'draft' ? '📝' : e.status === 'approved' ? '✅' : e.status === 'executed' ? '⚡' : e.status === 'reverted' ? '↩️' : e.status === 'failed' ? '❌' : '🗑️'; return `${ic} **${e.id}** [${e.intentType}] ${e.summary.slice(0, 80)} — _${e.status}_`; }).join('\n'); }
  private _notify(): void { this._onChange?.(); }
  dispose(): void { /* no-op */ }
}
