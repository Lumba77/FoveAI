/**
 * codeActionProvider.ts — Lightbulb & QuickFix provider for Jenna (LUMAX Agent)
 *
 * Registers QuickFix actions on errors/warnings so users can click the lightbulb
 * or "Send to Agent" menu item and immediately forward problem tracebacks & context to Jenna.
 */

import * as vscode from 'vscode';
import { JennaChatViewProvider } from '../JennaChatViewProvider';

export class JennaCodeActionProvider implements vscode.CodeActionProvider {
  public static readonly providedCodeActionKinds = [
    vscode.CodeActionKind.QuickFix
  ];

  public provideCodeActions(
    document: vscode.TextDocument,
    range: vscode.Range | vscode.Selection,
    context: vscode.CodeActionContext,
    _token: vscode.CancellationToken
  ): vscode.ProviderResult<(vscode.Command | vscode.CodeAction)[]> {
    if (!context.diagnostics || context.diagnostics.length === 0) {
      return [];
    }

    const actions: vscode.CodeAction[] = [];

    // 1. Action for specific diagnostic under cursor
    for (const diagnostic of context.diagnostics) {
      const title = `🤖 Send to Jenna AI: "${diagnostic.message.slice(0, 45)}..."`;
      const action = new vscode.CodeAction(title, vscode.CodeActionKind.QuickFix);
      action.command = {
        command: 'jenna.sendProblemToAgent',
        title: title,
        arguments: [document, range, [diagnostic]]
      };
      action.isPreferred = true;
      actions.push(action);
    }

    // 2. Action to send all diagnostics in file to Jenna
    if (context.diagnostics.length > 1) {
      const allTitle = `🤖 Send all ${context.diagnostics.length} problems in file to Jenna AI`;
      const allAction = new vscode.CodeAction(allTitle, vscode.CodeActionKind.QuickFix);
      allAction.command = {
        command: 'jenna.sendAllProblemsToAgent',
        title: allTitle,
        arguments: [document, context.diagnostics]
      };
      actions.push(allAction);
    }

    return actions;
  }
}

export function registerCodeActionProvider(
  context: vscode.ExtensionContext,
  chatProvider: JennaChatViewProvider
): void {
  // Register CodeAction provider for all languages
  context.subscriptions.push(
    vscode.languages.registerCodeActionsProvider('*', new JennaCodeActionProvider(), {
      providedCodeActionKinds: JennaCodeActionProvider.providedCodeActionKinds
    })
  );

  // Command 1: Send single problem to Jenna
  context.subscriptions.push(
    vscode.commands.registerCommand(
      'jenna.sendProblemToAgent',
      async (document?: vscode.TextDocument, _range?: vscode.Range, diagnostics?: vscode.Diagnostic[]) => {
        // Focus Jenna sidebar view
        await vscode.commands.executeCommand('jennaChat.focus');

        const activeDoc = document || vscode.window.activeTextEditor?.document;
        if (!activeDoc) {
          vscode.window.showWarningMessage('No active document found to inspect problem.');
          return;
        }

        const diags = diagnostics || vscode.languages.getDiagnostics(activeDoc.uri);
        if (!diags || diags.length === 0) {
          vscode.window.showInformationMessage('No active diagnostics found in document.');
          return;
        }

        const firstDiag = diags[0];
        const lineText = activeDoc.lineAt(firstDiag.range.start.line).text.trim();
        const relativePath = vscode.workspace.asRelativePath(activeDoc.uri);

        const prompt = `Please help fix this code problem in \`${relativePath}:${firstDiag.range.start.line + 1}\`:\n` +
          `**Diagnostic Error:** \`${firstDiag.message}\` (Code: ${firstDiag.code || 'N/A'})\n` +
          `**Source Line:** \`${lineText}\`\n\n` +
          `Could you investigate and provide the corrected code?`;

        chatProvider.handleUserPrompt(prompt);
      }
    )
  );

  // Command 2: Send all problems in workspace to Jenna
  context.subscriptions.push(
    vscode.commands.registerCommand(
      'jenna.sendAllProblemsToAgent',
      async (_document?: vscode.TextDocument, _diagnostics?: vscode.Diagnostic[]) => {
        await vscode.commands.executeCommand('jennaChat.focus');

        const allDiagnostics = vscode.languages.getDiagnostics();
        let totalCount = 0;
        const problemSummaryLines: string[] = [];

        for (const [uri, diags] of allDiagnostics) {
          if (diags.length === 0) continue;
          const relPath = vscode.workspace.asRelativePath(uri);
          for (const d of diags.slice(0, 10)) { // limit to top 10 to fit prompt nicely
            totalCount++;
            problemSummaryLines.push(`- \`${relPath}:${d.range.start.line + 1}\`: ${d.message}`);
          }
        }

        if (totalCount === 0) {
          vscode.window.showInformationMessage('No active problems found in workspace!');
          return;
        }

        const prompt = `Please inspect and fix the following ${totalCount} problem(s) in the workspace:\n\n` +
          problemSummaryLines.join('\n') +
          `\n\nPlease systematically resolve these issues to bring the Problems Panel to 0 errors.`;

        chatProvider.handleUserPrompt(prompt);
      }
    )
  );
}
