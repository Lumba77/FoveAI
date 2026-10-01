/**
 * contextAnalyzer.ts — Workspace context collection and analysis.
 * Gathers active file content, diagnostics, and git diff. Feeds to AI.
 */

import * as vscode from 'vscode';


export class ContextAnalyzer {
  constructor(
    private _onChat: (text: string) => Promise<void>,
  ) {}

  async analyzeContext(): Promise<void> {
    const editor = vscode.window.activeTextEditor;
    const ws = vscode.workspace.workspaceFolders;
    if (!editor || !ws) { vscode.window.showWarningMessage('Open a file and workspace first'); return; }
    const doc = editor.document;
    const fp = vscode.workspace.asRelativePath(doc.uri);
    const content = doc.getText().slice(0, 8000);
    const lang = doc.languageId;
    const probs = vscode.languages.getDiagnostics(doc.uri).filter(d => d.severity <= vscode.DiagnosticSeverity.Warning).slice(0, 10);
    let diff = '';
    try { const cp = require('child_process'); diff = cp.execSync('git diff --unified=3 HEAD', { cwd: ws[0].uri.fsPath, timeout: 3000, windowsHide: true, maxBuffer: 8192 }).toString().slice(0, 4000); } catch {}
    let ctx = '## Workspace Context\n\n### Active File: ' + fp + ' (' + lang + ')\n\n`' + lang + '\n' + content + '\n`\n';
    if (probs.length) { ctx += '\n### Problems (' + probs.length + ')\n'; probs.forEach(d => { ctx += '- ' + d.message + ' [line ' + (d.range.start.line + 1) + ']\n'; }); }
    if (diff) ctx += '\n### Uncommitted Changes\n`diff\n' + diff + '\n`\n';
    ctx += '\nAnalyze this context and suggest specific edits or next actions.';
    await this._onChat(ctx);
  }
  async sendContextToChat(text: string): Promise<void> { await this._onChat(text); }
}
