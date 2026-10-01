/**
 * preload.ts — Electron Context Bridge
 *
 * Exposes a typed `window.electronAPI` object to the renderer.
 * All communication between renderer and main process goes through here.
 * contextIsolation=true, so Node APIs are never directly exposed.
 */

import { contextBridge, ipcRenderer } from 'electron';

export type ElectronAPI = typeof api;

const api = {
  // ── Window controls ──────────────────────────────────────────────────────────
  window: {
    minimize: () => ipcRenderer.invoke('window:minimize'),
    maximize: () => ipcRenderer.invoke('window:maximize'),
    close: () => ipcRenderer.invoke('window:close'),
    isMaximized: (): Promise<boolean> => ipcRenderer.invoke('window:is-maximized'),
  },

  // ── App info ─────────────────────────────────────────────────────────────────
  app: {
    getVersion: (): Promise<string> => ipcRenderer.invoke('app:get-version'),
    getPlatform: (): Promise<string> => ipcRenderer.invoke('app:get-platform'),
    getWorkspaceId: (): Promise<string> => ipcRenderer.invoke('app:get-workspace-id'),
    openExternal: (url: string) => ipcRenderer.invoke('app:open-external', url),
  },

  // ── Chat / AI streaming ───────────────────────────────────────────────────────
  chat: {
    send: (payload: {
      messages: { role: string; content: string }[];
      model?: string;
      persona?: string;
      workspaceId: string;
      sessionId?: string;
      tasks?: { text: string; done: boolean }[];
    }): Promise<void> => ipcRenderer.invoke('chat:send', payload),

    abort: () => ipcRenderer.invoke('chat:abort'),

    // Subscribe to streaming tokens
    onToken: (cb: (token: string) => void) => {
      const handler = (_evt: Electron.IpcRendererEvent, token: string) => cb(token);
      ipcRenderer.on('chat:token', handler);
      return () => ipcRenderer.removeListener('chat:token', handler);
    },
    onDone: (cb: () => void) => {
      const handler = () => cb();
      ipcRenderer.once('chat:done', handler);
      return () => ipcRenderer.removeListener('chat:done', handler);
    },
    onError: (cb: (err: string) => void) => {
      const handler = (_evt: Electron.IpcRendererEvent, err: string) => cb(err);
      ipcRenderer.once('chat:error', handler);
      return () => ipcRenderer.removeListener('chat:error', handler);
    },

    getStatus: (workspaceId: string): Promise<{
      model: string;
      compressionLevel: number;
      activeBlocks: number;
      totalMemories: number;
      totalThemes: number;
      totalSessions: number;
      latencyMs: number;
      online: boolean;
    }> => ipcRenderer.invoke('chat:get-status', workspaceId),

    searchMemory: (query: string, workspaceId: string) =>
      ipcRenderer.invoke('chat:search-memory', { query, workspaceId }),

    getModels: (workspaceId: string): Promise<string[]> =>
      ipcRenderer.invoke('chat:get-models', workspaceId),

    switchModel: (model: string, workspaceId: string) =>
      ipcRenderer.invoke('chat:switch-model', { model, workspaceId }),
  },

  // ── Sessions (SQLite) ─────────────────────────────────────────────────────────
  sessions: {
    list: (): Promise<{ id: string; title: string; created_at: number; updated_at: number; message_count: number }[]> =>
      ipcRenderer.invoke('sessions:list'),
    create: (title: string): Promise<{ id: string; title: string; created_at: number; updated_at: number }> =>
      ipcRenderer.invoke('sessions:create', title),
    delete: (id: string): Promise<void> =>
      ipcRenderer.invoke('sessions:delete', id),
    messages: (sessionId: string): Promise<{ id: string; role: string; content: string; ts: number }[]> =>
      ipcRenderer.invoke('sessions:messages', sessionId),
    addMessage: (sessionId: string, role: string, content: string): Promise<string> =>
      ipcRenderer.invoke('sessions:add-message', sessionId, role, content),
    rename: (id: string, title: string): Promise<void> =>
      ipcRenderer.invoke('sessions:rename', id, title),
  },

  // ── File system ───────────────────────────────────────────────────────────────
  files: {
    openDialog: (options?: { filters?: { name: string; extensions: string[] }[] }) =>
      ipcRenderer.invoke('file:open-dialog', options),
    savePath: (options?: { defaultPath?: string; filters?: { name: string; extensions: string[] }[] }) =>
      ipcRenderer.invoke('file:save-path', options),
    read: (filePath: string): Promise<string> =>
      ipcRenderer.invoke('file:read', filePath),
    write: (filePath: string, content: string): Promise<void> =>
      ipcRenderer.invoke('file:write', filePath, content),
    exists: (filePath: string): Promise<boolean> =>
      ipcRenderer.invoke('file:exists', filePath),
    readDir: (dirPath: string): Promise<{ name: string; isDir: boolean; size?: number }[]> =>
      ipcRenderer.invoke('file:read-dir', dirPath),
    scanRepo: (rootPath: string, workspaceId: string): Promise<{ digest: string; fileCount: number }> =>
      ipcRenderer.invoke('repo:scan', rootPath, workspaceId),
    watchDir: (dirPath: string, id: string) =>
      ipcRenderer.invoke('file:watch', dirPath, id),
    unwatchDir: (id: string) =>
      ipcRenderer.invoke('file:unwatch', id),
    onWatchEvent: (cb: (event: { id: string; type: string; path: string }) => void) => {
      const handler = (_evt: Electron.IpcRendererEvent, data: { id: string; type: string; path: string }) => cb(data);
      ipcRenderer.on('file:watch-event', handler);
      return () => ipcRenderer.removeListener('file:watch-event', handler);
    },
  },

  // ── Audio / Voice ─────────────────────────────────────────────────────────────
  audio: {
    start: (): Promise<void> => ipcRenderer.invoke('audio:start'),
    stop: (): Promise<string> => ipcRenderer.invoke('audio:stop'),
    getDevices: (): Promise<{ id: string; label: string }[]> =>
      ipcRenderer.invoke('audio:get-devices'),
    onTranscript: (cb: (text: string) => void) => {
      const handler = (_evt: Electron.IpcRendererEvent, text: string) => cb(text);
      ipcRenderer.on('audio:transcript', handler);
      return () => ipcRenderer.removeListener('audio:transcript', handler);
    },
  },

  // ── Tray events ───────────────────────────────────────────────────────────────
  tray: {
    onOpenWorkspace: (cb: () => void) => {
      ipcRenderer.on('tray:open-workspace', cb);
      return () => ipcRenderer.removeListener('tray:open-workspace', cb);
    },
  },
};

contextBridge.exposeInMainWorld('electronAPI', api);
