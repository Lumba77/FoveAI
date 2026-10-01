/**
 * problemsStatusBar.ts — "Send Problems → Agent" Status Bar Button
 *
 * Creates a persistent left-aligned status bar item that:
 * - Shows live problem count (errors + warnings) updated in real-time
 * - Clicking it sends ALL problems directly to the Antigravity agent chat
 * - Falls back to Jenna sidebar + clipboard if Antigravity is unavailable
 */

import * as vscode from 'vscode';

export class ProblemsStatusBar {
  private item: vscode.StatusBarItem;
  private disposables: vscode.Disposable[] = [];

  constructor(context: vscode.ExtensionContext) {
    // Left-aligned, high priority so it appears near the left side of the status bar
    // The ID ensures VS Code remembers the item's visibility and doesn't hide it
    this.item = vscode.window.createStatusBarItem(
      'FoveAI.sendProblems',
      vscode.StatusBarAlignment.Left,
      950
    );
    this.item.command = 'jenna.sendAllProblemsToAgent';
    this.item.name = 'FoveAI: Send Problems to Agent';

    // Initial render
    this._updateCount();

    // Listen for diagnostic changes and re-render
    const diagListener = vscode.languages.onDidChangeDiagnostics(() => {
      this._updateCount();
    });

    this.disposables.push(diagListener);
    context.subscriptions.push(this.item, diagListener);

    this.item.show();
  }

  private _updateCount(): void {
    const all = vscode.languages.getDiagnostics();
    let errors = 0;
    let warnings = 0;

    for (const [, diags] of all) {
      for (const d of diags) {
        if (d.severity === vscode.DiagnosticSeverity.Error) errors++;
        else if (d.severity === vscode.DiagnosticSeverity.Warning) warnings++;
      }
    }

    const total = errors + warnings;

    if (total === 0) {
      // Always visible — show a clean/ready state
      this.item.text = '$(check) 0 Problems';
      this.item.tooltip = 'FoveAI: No errors — click to send problems to Agent';
      this.item.backgroundColor = undefined;
      this.item.color = undefined;
    } else {
      const parts: string[] = [];
      if (errors > 0) parts.push(`$(error) ${errors}`);
      if (warnings > 0) parts.push(`$(warning) ${warnings}`);
      this.item.text = `${parts.join('  ')} → Agent`;
      this.item.tooltip = `FoveAI: ${total} problem(s) — click to send ALL to AI Agent for diagnosis`;
      this.item.backgroundColor = errors > 0
        ? new vscode.ThemeColor('statusBarItem.errorBackground')
        : new vscode.ThemeColor('statusBarItem.warningBackground');
      this.item.color = undefined;
    }
  }

  dispose(): void {
    this.item.dispose();
    this.disposables.forEach(d => d.dispose());
  }
}

