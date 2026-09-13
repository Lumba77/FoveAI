/**
 * extension.ts — Jenna Copilot Extension Entry Point
 *
 * Activates on VS Code startup. Wires together:
 * - FoveatedClient (port 8400 proxy)
 * - AudioManager (voice recording)
 * - SessionLogger (bonding layer)
 * - JennaChatViewProvider (sidebar WebView)
 * - JennaStatusBar (status bar HUD)
 * - Commands: newSession, clearMemory, toggleStatus, openSidebar
 */

import * as vscode from 'vscode';
import { FoveatedClient, PERSONAS, PersonaId } from './memory/foveatedClient';
import { SessionLogger } from './bonding/sessionLogger';
import { JennaChatViewProvider } from './JennaChatViewProvider';
import { JennaStatusBar } from './statusBar';
import { ProblemsStatusBar } from './problemsStatusBar';
import { registerInlineProvider } from './inline/inlineProvider';
import { registerSearchMemory } from './commands/searchMemory';
import { registerSwitchModel } from './commands/switchModel';
import { registerSendProblems } from './commands/sendProblems';
import { AudioManager } from './audioManager';
import { ExecutionBuffer } from './executionBuffer';

/** Derive a stable workspace ID from the first workspace folder name */
function resolveWorkspaceId(context: vscode.ExtensionContext): string {
  const config = vscode.workspace.getConfiguration('jenna');
  const override = config.get<string>('workspaceId', '').trim();
  if (override) return override;

  const folders = vscode.workspace.workspaceFolders;
  if (folders && folders.length > 0) {
    // Sanitise: lowercase, replace spaces/special chars with underscore
    return folders[0].name.toLowerCase().replace(/[^a-z0-9]/g, '_');
  }

  // Fallback: use a persisted UUID
  let id = context.globalState.get<string>('jenna.defaultWorkspaceId');
  if (!id) {
    id = `ws_${Date.now().toString(36)}`;
    context.globalState.update('jenna.defaultWorkspaceId', id);
  }
  return id;
}

export function activate(context: vscode.ExtensionContext): void {
  console.log('[jenna] activating…');

  // ── Configuration ──────────────────────────────────────────────────────
  const config     = vscode.workspace.getConfiguration('jenna');
  const baseUrl    = config.get<string>('foveatedMemoryUrl', 'http://127.0.0.1:8400');
  const workspaceId = resolveWorkspaceId(context);

  console.log(`[jenna] workspace id: ${workspaceId} | proxy: ${baseUrl}`);

  // ── Output channel (for diagnostics) ───────────────────────────────────
  const out = vscode.window.createOutputChannel('Jenna');
  context.subscriptions.push(out);
  out.appendLine(`[Jenna] Activating — proxy: ${baseUrl} | workspace: ${workspaceId}`);

  // ── Core services ───────────────────────────────────────────────────────
  const client    = new FoveatedClient(baseUrl, (msg) => out.appendLine(msg));
  const statusBar = new JennaStatusBar(client, workspaceId);

  const workspaceFolder = vscode.workspace.workspaceFolders?.[0]?.name ?? 'unknown';
  const logger    = new SessionLogger(workspaceId, workspaceFolder, client);

  // ── Audio Manager ────────────────────────────────────────────────────────
  const audioManager = new AudioManager(context.extensionUri.fsPath, workspaceId);
  context.subscriptions.push(audioManager);

  // ── Execution Buffer ──────────────────────────────────────────────────────
  const wsRootPath = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? '';
  const executionBuffer = new ExecutionBuffer(wsRootPath);

  // ── WebView provider ────────────────────────────────────────────────────
  const provider = new JennaChatViewProvider(
    context.extensionUri,
    context.globalStorageUri,
    client,
    logger,
    statusBar,
    workspaceId,
    executionBuffer,
    audioManager,
  );
  context.subscriptions.push(executionBuffer);

  // Wire buffer's send-to-chat after provider exists (breaks circular dep)
  executionBuffer.setSendToChat((text) => provider.handleExternalChat(text));

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      JennaChatViewProvider.viewType,
      provider,
      { webviewOptions: { retainContextWhenHidden: true } }
    )
  );

  // ── Commands ────────────────────────────────────────────────────────────

  // Switch Persona command
  context.subscriptions.push(
    vscode.commands.registerCommand('jenna.switchPersona', async () => {
      const items = Object.keys(PERSONAS).map((id) => {
        const p = PERSONAS[id as PersonaId];
        return {
          label: `${p.icon} ${p.name}`,
          description: p.role,
          detail: p.description,
          id: id as PersonaId,
        };
      });

      const selected = await vscode.window.showQuickPick(items, {
        placeHolder: 'Select active FoveAI persona',
      });

      if (selected) {
        provider.setPersona(selected.id);
        vscode.workspace.getConfiguration('FoveAI').update('persona', selected.id, true);
        vscode.window.showInformationMessage(`FoveAI: Switched persona to ${selected.label}`);
      }
    })
  );

  // New session: flush current bond, clear chat history, reset session start
  context.subscriptions.push(
    vscode.commands.registerCommand('jenna.newSession', async () => {
      out.appendLine('[Jenna] Starting new session — flushing bond...');
      await logger.flush();
      provider.clearHistory();
      vscode.window.showInformationMessage('FoveAI: Session bond saved. Starting fresh!');
    })
  );

  // Reload / Update Webview Frame
  context.subscriptions.push(
    vscode.commands.registerCommand('jenna.reloadWebview', () => {
      provider.reload();
      vscode.window.showInformationMessage('FoveAI: Plugin frame reloaded.');
    })
  );

  // 1-Click Reload IDE Window (reloads current window instantly)
  context.subscriptions.push(
    vscode.commands.registerCommand('jenna.reloadWindow', () => {
      vscode.commands.executeCommand('workbench.action.reloadWindow');
    })
  );

  // Clear workspace memory (asks for confirmation)
  context.subscriptions.push(
    vscode.commands.registerCommand('jenna.clearMemory', async () => {
      const choice = await vscode.window.showWarningMessage(
        `Clear all of Jenna's memory for workspace "${workspaceId}"? This cannot be undone.`,
        { modal: true },
        'Clear Memory'
      );
      if (choice === 'Clear Memory') {
        // Fire a special clear request to the proxy
        try {
          await fetch(`${baseUrl}/api/clear`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${workspaceId}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({ workspace_id: workspaceId }),
          });
          vscode.window.showInformationMessage('Jenna: Memory cleared.');
        } catch {
          vscode.window.showErrorMessage('Jenna: Could not reach Foveated Memory proxy (port 8400).');
        }
        provider.clearHistory();
      }
    })
  );

  // Show status in info message
  context.subscriptions.push(
    vscode.commands.registerCommand('jenna.toggleStatus', async () => {
      const status = await client.getStatus(workspaceId);
      if (!status.online) {
        vscode.window.showWarningMessage(
          'Jenna: Foveated Memory proxy (port 8400) is offline. Start it with: node Tools/foveated-memory/server.js'
        );
      } else {
        vscode.window.showInformationMessage(
          `Jenna online | Model: ${status.model} | XRL: ${status.compressionLevel} | Blocks: ${status.activeBlocks} | Memories: ${status.totalMemories} | Latency: ${status.latencyMs}ms`
        );
      }
    })
  );

  // Open sidebar
  context.subscriptions.push(
    vscode.commands.registerCommand('jenna.openSidebar', () => {
      vscode.commands.executeCommand('jennaChat.focus');
    })
  );

  // ── Phase 2: Inline completions, memory search, model switcher ──────────

  registerInlineProvider(context, client, workspaceId);
  registerSearchMemory(context, client, workspaceId);
  registerSwitchModel(context, client, workspaceId);
  registerSendProblems(context, provider);

  // ── Problems Status Bar (always-visible ⚠️ → Agent button) ─────────────
  new ProblemsStatusBar(context);

  // ── Config change listener ───────────────────────────────────────────────
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('jenna')) {
        vscode.window.showInformationMessage(
          'Jenna: Configuration updated. Reload the window to apply changes.',
          'Reload'
        ).then(action => {
          if (action === 'Reload') {
            vscode.commands.executeCommand('workbench.action.reloadWindow');
          }
        });
      }
    })
  );

  // Register disposables
  context.subscriptions.push(statusBar, logger);

  console.log(`[jenna] activated ✓ | workspace: ${workspaceId}`);
}

export async function deactivate(): Promise<void> {
  // SessionLogger.flush() is called via the dispose() path registered above.
  // The extension host calls dispose() on all subscriptions on deactivation.
  console.log('[jenna] deactivated — session bond flushed.');
}

