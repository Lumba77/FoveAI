/**
 * switchModel.ts — Jenna Model Switcher
 *
 * `Jenna: Switch Model` command — fetches available models from port 8400
 * (which proxies to Ollama/LM Studio) and lets you pick one via Quick Pick.
 * The selection is persisted to workspace settings.
 */

import * as vscode from 'vscode';
import { FoveatedClient } from '../memory/foveatedClient';

interface OllamaModel {
  id: string;
  object: string;
  created?: number;
}

export function registerSwitchModel(
  context: vscode.ExtensionContext,
  _client: FoveatedClient,
  workspaceId: string
): vscode.Disposable {

  const disposable = vscode.commands.registerCommand(
    'jenna.switchModel',
    async () => {
      const config  = vscode.workspace.getConfiguration('jenna');
      const baseUrl = config.get<string>('foveatedMemoryUrl', 'http://127.0.0.1:8400');
      const current = config.get<string>('model', 'auto');

      // Fetch available models from proxy
      let models: OllamaModel[] = [];
      try {
        const resp = await fetch(`${baseUrl}/v1/models`, {
          headers: {
            'Authorization': `Bearer ${workspaceId}`,
          },
          signal: AbortSignal.timeout(4000),
        });

        if (resp.ok) {
          const data = await resp.json() as { data?: OllamaModel[] };
          models = data.data ?? [];
        }
      } catch {
        // Fall through to manual entry
      }

      // Build Quick Pick items
      const items: vscode.QuickPickItem[] = [
        {
          label: '$(symbol-keyword) auto',
          description: 'Let the proxy decide (recommended)',
          detail: current === 'auto' ? '✓ Currently active' : undefined,
        },
                { label: '$(server) Gemma-4-12b-XRLF', description: 'Gemma-4-12b-XRLF' },
        { label: '$(server) Quwtpus-9B-XRLF', description: 'Quwtpus-9B-XRLF' },
        { label: '$(server) 4B-Super-Coder-XRLF', description: '4B-Super-Coder-XRLF' },
        ...models.map(m => ({
          label: `$(server) ${m.id}`,
          description: m.id,
          detail: current === m.id ? '✓ Currently active' : undefined,
        })),
        {
          label: '$(edit) Enter model name manually…',
          description: 'Type a model ID not listed above',
        },
      ];

      const picked = await vscode.window.showQuickPick(items, {
        title: '🧠 Jenna — Select Model',
        placeHolder: `Current: ${current}`,
      });

      if (!picked) return;

      let selectedModel: string;

      if (picked.label.includes('Enter model name manually')) {
        const manual = await vscode.window.showInputBox({
          prompt: 'Enter the exact model ID (e.g. qwen2.5-coder:7b)',
          value: current,
        });
        if (!manual?.trim()) return;
        selectedModel = manual.trim();
      } else if (picked.label.includes('auto')) {
        selectedModel = 'auto';
      } else {
        selectedModel = picked.description ?? 'auto';
      }

      // Persist to workspace settings
      await config.update('model', selectedModel, vscode.ConfigurationTarget.Workspace);
      vscode.window.showInformationMessage(`Jenna: Model switched to → ${selectedModel}`);
    }
  );

  context.subscriptions.push(disposable);
  return disposable;
}

