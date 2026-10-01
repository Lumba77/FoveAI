/**
 * fileIpc.ts — File system IPC handlers
 *
 * Replaces vscode.workspace.fs with native Node fs + dialog APIs.
 * Includes file watching via chokidar.
 */

import type { IpcMain, Dialog } from 'electron';
import * as fs from 'fs';
import * as path from 'path';
import chokidar from 'chokidar';
import type { FSWatcher } from 'chokidar';

const watchers = new Map<string, FSWatcher>();

export function registerFileIpc(ipcMain: IpcMain, dialog: Dialog): void {

  // ── file:open-dialog ────────────────────────────────────────────────────────
  ipcMain.handle('file:open-dialog', async (_event, options?: {
    filters?: { name: string; extensions: string[] }[];
    properties?: string[];
  }) => {
    const result = await dialog.showOpenDialog({
      properties: (options?.properties as any) ?? ['openFile', 'multiSelections'],
      filters: options?.filters ?? [
        { name: 'Source Files', extensions: ['ts', 'tsx', 'js', 'jsx', 'py', 'json', 'md', 'css', 'html', 'yaml', 'toml'] },
        { name: 'All Files', extensions: ['*'] },
      ],
    });
    return result.canceled ? [] : result.filePaths;
  });

  // ── file:save-path ──────────────────────────────────────────────────────────
  ipcMain.handle('file:save-path', async (_event, options?: {
    defaultPath?: string;
    filters?: { name: string; extensions: string[] }[];
  }) => {
    const result = await dialog.showSaveDialog({
      defaultPath: options?.defaultPath,
      filters: options?.filters ?? [{ name: 'All Files', extensions: ['*'] }],
    });
    return result.canceled ? null : result.filePath;
  });

  // ── file:open-folder-dialog ─────────────────────────────────────────────────
  ipcMain.handle('file:open-folder-dialog', async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openDirectory'],
    });
    return result.canceled ? null : result.filePaths[0];
  });

  // ── file:read ───────────────────────────────────────────────────────────────
  ipcMain.handle('file:read', async (_event, filePath: string) => {
    try {
      const stat = fs.statSync(filePath);
      // Guard against reading huge files
      if (stat.size > 2 * 1024 * 1024) {
        const partial = fs.readFileSync(filePath, 'utf8').slice(0, 500_000);
        return partial + '\n\n[... file truncated at 500KB ...]';
      }
      return fs.readFileSync(filePath, 'utf8');
    } catch (err: unknown) {
      throw new Error(`Cannot read ${filePath}: ${err instanceof Error ? err.message : String(err)}`);
    }
  });

  // ── file:write ──────────────────────────────────────────────────────────────
  ipcMain.handle('file:write', async (_event, filePath: string, content: string) => {
    const dir = path.dirname(filePath);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(filePath, content, 'utf8');
  });

  // ── file:exists ─────────────────────────────────────────────────────────────
  ipcMain.handle('file:exists', async (_event, filePath: string) => {
    return fs.existsSync(filePath);
  });

  // ── file:read-dir ───────────────────────────────────────────────────────────
  ipcMain.handle('file:read-dir', async (_event, dirPath: string) => {
    try {
      const entries = fs.readdirSync(dirPath, { withFileTypes: true });
      return entries
        .filter(e => !e.name.startsWith('.') && e.name !== 'node_modules')
        .map(e => ({
          name: e.name,
          isDir: e.isDirectory(),
          size: e.isFile() ? fs.statSync(path.join(dirPath, e.name)).size : undefined,
        }))
        .sort((a, b) => {
          if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
          return a.name.localeCompare(b.name);
        });
    } catch {
      return [];
    }
  });

  // ── repo:scan ───────────────────────────────────────────────────────────────
  ipcMain.handle('repo:scan', async (_event, rootPath: string, workspaceId: string) => {
    try {
      const { scanRepo } = await import('../memory/repoScanner');
      const { FoveatedClient } = await import('../memory/foveatedClient');
      const foveatedUrl = process.env['FOVEATED_URL'] ?? 'http://127.0.0.1:8400';
      const client = new FoveatedClient(foveatedUrl);
      const result = await scanRepo(rootPath, client, workspaceId);
      return { digest: result.digest, fileCount: result.fileCount };
    } catch (err: unknown) {
      return { digest: `Scan failed: ${err instanceof Error ? err.message : String(err)}`, fileCount: 0 };
    }
  });

  // ── file:watch ──────────────────────────────────────────────────────────────
  ipcMain.handle('file:watch', (event, dirPath: string, watchId: string) => {
    if (watchers.has(watchId)) return;
    const watcher = chokidar.watch(dirPath, {
      ignored: /(^|[/\\])(\.|node_modules|dist|__pycache__|\.venv)/,
      persistent: true,
      ignoreInitial: true,
      depth: 6,
    });
    ['add', 'change', 'unlink', 'addDir', 'unlinkDir'].forEach((type) => {
      watcher.on(type, (filePath) => {
        if (!event.sender.isDestroyed()) {
          event.sender.send('file:watch-event', { id: watchId, type, path: filePath });
        }
      });
    });
    watchers.set(watchId, watcher);
  });

  // ── file:unwatch ────────────────────────────────────────────────────────────
  ipcMain.handle('file:unwatch', async (_event, watchId: string) => {
    const watcher = watchers.get(watchId);
    if (watcher) {
      await watcher.close();
      watchers.delete(watchId);
    }
  });
}
