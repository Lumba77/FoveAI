/**
 * inlineProvider.ts — Jenna Inline Ghost-Text Completions
 *
 * Registers an InlineCompletionItemProvider that sends the current file
 * context (prefix + suffix) to the Foveated Memory proxy and streams
 * back a code completion as ghost text.
 *
 * Debounced at 600ms to avoid hammering the proxy on every keystroke.
 */

import * as vscode from 'vscode';
import { FoveatedClient } from '../memory/foveatedClient';

const DEBOUNCE_MS = 600;
const MAX_PREFIX_LINES = 40;   // lines before cursor
const MAX_SUFFIX_LINES = 10;   // lines after cursor
const MAX_COMPLETION_TOKENS = 120;

// Supported languages for inline completions
const ENABLED_LANGUAGES = new Set([
  'python', 'typescript', 'javascript', 'typescriptreact', 'javascriptreact',
  'go', 'rust', 'java', 'csharp', 'cpp', 'c', 'powershell', 'shellscript',
]);

export function registerInlineProvider(
  context: vscode.ExtensionContext,
  client: FoveatedClient,
  workspaceId: string
): vscode.Disposable {
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;

  const provider: vscode.InlineCompletionItemProvider = {
    async provideInlineCompletionItems(
      document: vscode.TextDocument,
      position: vscode.Position,
      _context: vscode.InlineCompletionContext,
      token: vscode.CancellationToken
    ): Promise<vscode.InlineCompletionList | null> {

      // Only trigger for enabled languages
      if (!ENABLED_LANGUAGES.has(document.languageId)) return null;

      // Check config — user can disable inline completions
      const config = vscode.workspace.getConfiguration('jenna');
      if (!config.get<boolean>('inlineCompletions', true)) return null;

      // Debounce
      if (debounceTimer) clearTimeout(debounceTimer);
      await new Promise<void>((resolve) => {
        debounceTimer = setTimeout(resolve, DEBOUNCE_MS);
      });

      if (token.isCancellationRequested) return null;

      // Build prefix (lines before cursor)
      const prefixStart = Math.max(0, position.line - MAX_PREFIX_LINES);
      const prefix = document.getText(
        new vscode.Range(prefixStart, 0, position.line, position.character)
      );

      // Build suffix (lines after cursor)
      const suffixEnd = Math.min(document.lineCount - 1, position.line + MAX_SUFFIX_LINES);
      const suffix = document.getText(
        new vscode.Range(position.line, position.character, suffixEnd, 0)
      );

      const fileName = document.fileName.split(/[\\/]/).pop() ?? '';
      const lang = document.languageId;

      const prompt = [
        `Complete the following ${lang} code in file \`${fileName}\`.`,
        `Return ONLY the completion text — no explanation, no markdown fences.`,
        `Prefix:\n${prefix}`,
        suffix ? `Suffix (what comes after):\n${suffix}` : '',
      ].filter(Boolean).join('\n\n');

      try {
        let completion = '';
        const stream = client.chat(
          [{ role: 'user', content: prompt }],
          {
            workspaceId,
            model: vscode.workspace.getConfiguration('jenna').get<string>('model', 'auto'),
            stream: true,
            maxTokens: MAX_COMPLETION_TOKENS,
            temperature: 0.1,   // low temp for completions
          }
        );

        for await (const chunk of stream) {
          if (token.isCancellationRequested) return null;
          completion += chunk;
        }

        completion = completion.trim();
        if (!completion) return null;

        return {
          items: [
            new vscode.InlineCompletionItem(
              completion,
              new vscode.Range(position, position)
            ),
          ],
        };

      } catch {
        // Silently fail — don't show error toasts for inline completions
        return null;
      }
    },
  };

  const disposable = vscode.languages.registerInlineCompletionItemProvider(
    { pattern: '**' },   // all files — filtered by ENABLED_LANGUAGES above
    provider
  );

  context.subscriptions.push(disposable);
  return disposable;
}
