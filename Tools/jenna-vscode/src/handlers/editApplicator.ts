/**
 * editApplicator.ts — Applies AI code blocks to active editor.
 * Extracts code from markdown code fences, writes to cursor or selection.
 */

import * as vscode from 'vscode';

export class EditApplicator {
  constructor(private _post: (msg: Record<string, unknown>) => void) {}

  applyEdit(text: string): void {
    const editor = vscode.window.activeTextEditor;
    if (!editor || !text) { vscode.window.showWarningMessage('No active editor'); return; }
    let code = text;
    const m = text.match(/`(?:\w+)?\n([\s\S]*?)`/);
    if (m) code = m[1];
    editor.edit(eb => {
      if (!editor.selection.isEmpty) eb.replace(editor.selection, code);
      else eb.insert(editor.selection.active, code);
    }).then(s => { if (s) this._post({ type: 'status_update', status: { online: true, loading: false, message: 'Edit applied' } }); });
  }
}
