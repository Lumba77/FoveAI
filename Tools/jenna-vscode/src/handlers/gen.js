const fs = require('fs');
const path = require('path');
const base = 'src/handlers';
fs.mkdirSync(base, { recursive: true });

// Delete old files
try { fs.readdirSync(base).forEach(f => fs.unlinkSync(path.join(base, f))); } catch {}

// 1. contextAnalyzer.ts
const contextAnalyzer = /**
 * contextAnalyzer.ts — Workspace context collection and analysis.
 */
import * as vscode from 'vscode';
import { FoveatedClient } from '../memory/foveatedClient';

export class ContextAnalyzer {
  constructor(
    private _client: FoveatedClient,
    private _workspaceId: string,
    private _getPersona: () => string,
    private _post: (msg: Record<string, unknown>) => void,
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
    let ctx = '## Workspace Context\\n\\n### Active File: ' + fp + ' (' + lang + ')\\n\\n\\\\\\' + lang + '\\n' + content + '\\n\\\\\\\\n';
    if (probs.length) { ctx += '\\n### Problems (' + probs.length + ')\\n'; probs.forEach(d => { ctx += '- ' + d.message + ' [line ' + (d.range.start.line + 1) + ']\\n'; }); }
    if (diff) ctx += '\\n### Uncommitted Changes\\n\\\\\\diff\\n' + diff + '\\n\\\\\\\\n';
    ctx += '\\nAnalyze this context and suggest specific edits or next actions.';
    await this._onChat(ctx);
  }
  async sendContextToChat(text: string): Promise<void> { await this._onChat(text); }
}
;
fs.writeFileSync(path.join(base, 'contextAnalyzer.ts'), contextAnalyzer.trim());
console.log('contextAnalyzer.ts');
