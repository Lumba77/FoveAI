/**
 * searchMemory.ts — Jenna Memory Search Panel
 *
 * `Jenna: Search Memory` command — opens a VS Code Quick Pick that queries
 * the foveated store's TF-IDF search endpoint and lets you insert a recalled
 * memory block into the active editor or chat.
 */

import * as vscode from 'vscode';
import { FoveatedClient, MemorySearchResult } from '../memory/foveatedClient';

export function registerSearchMemory(
  context: vscode.ExtensionContext,
  client: FoveatedClient,
  workspaceId: string
): vscode.Disposable {

  const disposable = vscode.commands.registerCommand(
    'jenna.searchMemory',
    async () => {
      // Step 1: Get search query from user
      const query = await vscode.window.showInputBox({
        prompt: '🧠 Jenna Memory Search — what do you want to recall?',
        placeHolder: 'e.g. "how we fixed the auth bug" or "session logger pattern"',
        ignoreFocusOut: true,
      });

      if (!query?.trim()) return;

      // Step 2: Search with progress indicator
      let results: MemorySearchResult[] = [];
      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: 'Jenna: Searching memory…',
          cancellable: false,
        },
        async () => {
          results = await client.searchMemory(query, workspaceId);
        }
      );

      if (results.length === 0) {
        vscode.window.showInformationMessage(
          'Jenna: No memories found for that query. Try different keywords.'
        );
        return;
      }

      // Step 3: Show Quick Pick with results
      const items: (vscode.QuickPickItem & { result: MemorySearchResult })[] = results.map((r, i) => ({
        label: `$(brain) Memory ${i + 1}`,
        description: `Score: ${r.score.toFixed(3)} · ${_relativeAge(r.timestamp)}`,
        detail: r.content.length > 200
          ? r.content.slice(0, 200) + '…'
          : r.content,
        result: r,
      }));

      const picked = await vscode.window.showQuickPick(items, {
        title: `🧠 Jenna recalled ${results.length} memories for: "${query}"`,
        placeHolder: 'Select a memory to insert into the editor or copy',
        matchOnDescription: true,
        matchOnDetail: true,
      });

      if (!picked) return;

      // Step 4: Action — insert into editor or copy to clipboard
      const action = await vscode.window.showQuickPick(
        [
          { label: '$(insert) Insert at cursor', id: 'insert' },
          { label: '$(copy) Copy to clipboard', id: 'copy' },
          { label: '$(comment) Insert as comment', id: 'comment' },
        ],
        { title: 'What do you want to do with this memory?' }
      );

      if (!action) return;

      const content = picked.result.content;

      switch (action.id) {
        case 'insert': {
          const editor = vscode.window.activeTextEditor;
          if (!editor) {
            vscode.window.showWarningMessage('No active editor to insert into.');
            return;
          }
          await editor.edit(eb => {
            eb.insert(editor.selection.active, content);
          });
          break;
        }
        case 'copy':
          await vscode.env.clipboard.writeText(content);
          vscode.window.showInformationMessage('Jenna: Memory copied to clipboard.');
          break;
        case 'comment': {
          const editor = vscode.window.activeTextEditor;
          if (!editor) {
            vscode.window.showWarningMessage('No active editor to insert into.');
            return;
          }
          const commentedLines = content
            .split('\n')
            .map(l => `// ${l}`)
            .join('\n');
          await editor.edit(eb => {
            eb.insert(editor.selection.active, commentedLines + '\n');
          });
          break;
        }
      }
    }
  );

  context.subscriptions.push(disposable);
  return disposable;
}

/** Human-readable relative timestamp */
function _relativeAge(isoTs: string): string {
  try {
    const diff = Date.now() - new Date(isoTs).getTime();
    const mins = Math.floor(diff / 60_000);
    if (mins < 60)   return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24)    return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  } catch {
    return 'unknown';
  }
}
