/**
 * chatIpc.ts — Chat IPC handlers
 *
 * Handles chat:send from renderer, streams tokens back via chat:token events.
 * Mirrors JennaChatViewProvider's streaming logic without any VS Code dependency.
 */

import type { IpcMain } from 'electron';
import { FoveatedClient } from '../memory/foveatedClient';
import type { ChatMessage, ChatOptions, PersonaId } from '../memory/foveatedClient';

// Single global client instance (per app lifetime)
let client: FoveatedClient | null = null;
let currentController: AbortController | null = null;

export function registerChatIpc(ipcMain: IpcMain, foveatedUrl: string): void {
  client = new FoveatedClient(foveatedUrl, (msg) => console.log('[Jenna]', msg));

  // ── chat:send ───────────────────────────────────────────────────────────────
  ipcMain.handle('chat:send', async (event, payload: {
    messages: ChatMessage[];
    model?: string;
    persona?: PersonaId;
    workspaceId: string;
    sessionId?: string;
    tasks?: { text: string; done: boolean }[];
    customSystemPrompt?: string;
    compressionLevel?: number;
    temperature?: number;
  }) => {
    // Abort any previous stream
    if (currentController) {
      currentController.abort();
      currentController = null;
    }
    currentController = new AbortController();
    const sender = event.sender;

    const opts: ChatOptions = {
      model: payload.model || 'auto',
      persona: payload.persona,
      workspaceId: payload.workspaceId,
      sessionId: payload.sessionId,
      stream: true,
      temperature: payload.temperature ?? 0.7,
      maxTokens: 2048,
      tasks: payload.tasks,
      customSystemPrompt: payload.customSystemPrompt,
      compressionLevel: payload.compressionLevel,
    };

    try {
      for await (const token of client!.chat(payload.messages, opts)) {
        if (currentController?.signal.aborted) break;
        if (!sender.isDestroyed()) {
          sender.send('chat:token', token);
        }
      }
      if (!sender.isDestroyed()) {
        sender.send('chat:done');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error('[chatIpc] stream error:', msg);
      if (!sender.isDestroyed()) {
        sender.send('chat:error', msg);
      }
    } finally {
      currentController = null;
    }
  });

  // ── chat:abort ──────────────────────────────────────────────────────────────
  ipcMain.handle('chat:abort', () => {
    if (currentController) {
      currentController.abort();
      currentController = null;
    }
  });

  // ── chat:get-status ─────────────────────────────────────────────────────────
  ipcMain.handle('chat:get-status', async (_event, workspaceId: string) => {
    try {
      return await client!.getStatus(workspaceId);
    } catch {
      return {
        model: 'offline', compressionLevel: 0, activeBlocks: 0,
        totalMemories: 0, totalThemes: 0, totalSessions: 0, latencyMs: -1, online: false,
      };
    }
  });

  // ── chat:search-memory ──────────────────────────────────────────────────────
  ipcMain.handle('chat:search-memory', async (_event, { query, workspaceId }: { query: string; workspaceId: string }) => {
    return client!.searchMemory(query, workspaceId);
  });

  // ── chat:get-models ─────────────────────────────────────────────────────────
  ipcMain.handle('chat:get-models', async (_event, workspaceId: string) => {
    try {
      const resp = await fetch(`${foveatedUrl}/v1/models`, {
        headers: { 'Authorization': `Bearer ${workspaceId}`, 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(5000),
      });
      if (!resp.ok) return [];
      const data = await resp.json() as { data?: { id: string }[] };
      return data.data?.map((m) => m.id) ?? [];
    } catch {
      return [];
    }
  });

  // ── chat:switch-model ───────────────────────────────────────────────────────
  ipcMain.handle('chat:switch-model', async (_event, { model, workspaceId }: { model: string; workspaceId: string }) => {
    try {
      await fetch(`${foveatedUrl}/api/model`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${workspaceId}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ model }),
        signal: AbortSignal.timeout(5000),
      });
      return true;
    } catch {
      return false;
    }
  });
}
