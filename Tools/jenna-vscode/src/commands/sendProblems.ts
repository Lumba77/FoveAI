/**
 * sendProblems.ts — FoveAI AI Agent Problems Panel Integration
 *
 * Collects active diagnostic errors/warnings from the VS Code Problems Panel
 * and sends them to the AI Agent via escalating delivery strategies:
 *   1. Antigravity native chat API (VS Code 1.90+ workbench.action.chat.open with query)
 *   2. Antigravity panel focus + clipboard with auto-paste instruction
 *   3. Jenna webview direct injection
 *   4. Clipboard fallback with prominent toast
 */

import * as vscode from 'vscode';
import { JennaChatViewProvider } from '../JennaChatViewProvider';
import { setTimeout as delay } from 'node:timers/promises';

/** Build the problem payload string from diagnostics */
function buildPayload(problemItems: { uri: vscode.Uri; diag: vscode.Diagnostic }[]): string {
  let payload = `### 🚨 Active IDE Workspace Problems (Total: ${problemItems.length})\n\n`;
  payload += `Please inspect, diagnose, and resolve the following active errors and warnings from the IDE Problems Panel:\n\n`;

  problemItems.forEach((item, index) => {
    const relPath = vscode.workspace.asRelativePath(item.uri);
    const line = item.diag.range.start.line + 1;
    const col = item.diag.range.start.character + 1;
    const severity = item.diag.severity === vscode.DiagnosticSeverity.Error ? 'ERROR 🔴' : 'WARNING 🟡';
    const source = item.diag.source ? ` [${item.diag.source}]` : '';
    payload += `${index + 1}. **[${severity}]** \`${relPath}:${line}:${col}\`${source}\n`;
    payload += `   - **Message**: ${item.diag.message}\n\n`;
  });

  payload += `\nProvide step-by-step diagnostic fixes and executable code edits to eliminate all listed problems.`;
  return payload;
}

/**
 * Try to send a message directly into the Antigravity / VS Code Copilot chat panel.
 * Returns true if successfully injected, false if all strategies failed.
 */
async function sendToAgentChat(payload: string, provider: JennaChatViewProvider): Promise<boolean> {
  // Strategy 1: Jenna webview injection (our own sidebar)
  try {
    if (!provider.isReady) {
      throw new Error('Webview not ready');
    }
    await provider.handleUserPrompt(payload);
    await vscode.commands.executeCommand('jennaChat.focus');
    return true;
  } catch (_) { /* webview not ready */ }

  // Strategy 2: VS Code 1.90+ Antigravity / GitHub Copilot Chat API
  // workbench.action.chat.open accepts { query, isPartialQuery } in newer builds
  try {
    await vscode.commands.executeCommand('workbench.action.chat.open', {
      query: payload,
      isPartialQuery: false,
    });
    return true;
  } catch (_) { /* not available */ }

  // Strategy 3: antigravity / copilot specific command variants
  const chatCommands = [
    'workbench.panel.chat.view.focus',
    'github.copilot.chat.focus',
    'antigravity.chat.open',
    'workbench.action.openChat',
  ];
  for (const cmd of chatCommands) {
    try {
      await vscode.commands.executeCommand(cmd);
      // Small delay to let the panel open, then try to send
      await delay(300);
      // Try filling the chat input if the API exists
      try {
        await vscode.commands.executeCommand('workbench.action.chat.sendToNewChat', payload);
        return true;
      } catch (_) { /* sendToNewChat not available */ }
      break; // panel opened even if we couldn't auto-send
    } catch (_) { /* command not found */ }
  }

  return false;
}

export function registerSendProblems(
  context: vscode.ExtensionContext,
  provider: JennaChatViewProvider
): void {

  // ── Command 1: Send ALL workspace problems ──────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('jenna.sendAllProblemsToAgent', async () => {
      const allDiagnostics = vscode.languages.getDiagnostics();
      const problemItems: { uri: vscode.Uri; diag: vscode.Diagnostic }[] = [];

      for (const [uri, diagnostics] of allDiagnostics) {
        for (const d of diagnostics) {
          // Only include errors and warnings (skip hints/info)
          if (d.severity <= vscode.DiagnosticSeverity.Warning) {
            problemItems.push({ uri, diag: d });
          }
        }
      }

      if (problemItems.length === 0) {
        vscode.window.showInformationMessage(
          '✅ FoveAI: No errors or warnings in the workspace — everything looks clean!'
        );
        return;
      }

      const payload = buildPayload(problemItems);

      // Always copy to clipboard as a reliable fallback
      await vscode.env.clipboard.writeText(payload);

      // Attempt direct agent delivery
      const delivered = await sendToAgentChat(payload, provider);

      if (delivered) {
        vscode.window.showInformationMessage(
          `🤖 FoveAI: Sent ${problemItems.length} problem(s) to the AI Agent. Also copied to clipboard.`
        );
      } else {
        // Show a prominent toast with an action button
        const action = await vscode.window.showWarningMessage(
          `📋 ${problemItems.length} problem(s) copied to clipboard! Open the Antigravity chat and press Ctrl+V to paste.`,
          'Open Antigravity Chat',
          'Open Jenna Sidebar'
        );
        if (action === 'Open Antigravity Chat') {
          try {
            await vscode.commands.executeCommand('workbench.action.chat.open');
          } catch (_) {}
        } else if (action === 'Open Jenna Sidebar') {
          vscode.commands.executeCommand('jennaChat.focus');
        }
      }
    })
  );

  // ── Command 2: Send problems for the active file only ──────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('jenna.sendProblemToAgent', async () => {
      const activeEditor = vscode.window.activeTextEditor;
      if (!activeEditor) {
        vscode.window.showWarningMessage('FoveAI: No active document is open.');
        return;
      }

      const uri = activeEditor.document.uri;
      const diagnostics = vscode.languages.getDiagnostics(uri).filter(
        d => d.severity <= vscode.DiagnosticSeverity.Warning
      );

      if (diagnostics.length === 0) {
        vscode.window.showInformationMessage(
          `✅ FoveAI: No problems in ${vscode.workspace.asRelativePath(uri)}.`
        );
        return;
      }

      const relPath = vscode.workspace.asRelativePath(uri);
      let payload = `### 🚨 Problems in \`${relPath}\`\n\n`;

      diagnostics.forEach((d, i) => {
        const line = d.range.start.line + 1;
        const severity = d.severity === vscode.DiagnosticSeverity.Error ? 'ERROR 🔴' : 'WARNING 🟡';
        const source = d.source ? ` [${d.source}]` : '';
        payload += `${i + 1}. **[${severity}]**${source} Line ${line}: ${d.message}\n`;
      });

      payload += `\nPlease inspect and fix these issues in \`${relPath}\`.`;

      await vscode.env.clipboard.writeText(payload);

      const delivered = await sendToAgentChat(payload, provider);

      if (delivered) {
        vscode.window.showInformationMessage(
          `🤖 FoveAI: Sent ${diagnostics.length} problem(s) from ${relPath} to the AI Agent.`
        );
      } else {
        vscode.window.showInformationMessage(
          `📋 ${diagnostics.length} problem(s) copied to clipboard! Paste in Antigravity Chat (Ctrl+V).`
        );
      }
    })
  );
}


