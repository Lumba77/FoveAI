/**
 * main.ts — LUMAX Vibe Coder Electron App Entry Point
 *
 * Creates the main BrowserWindow with Monaco + Chat two-pane layout.
 * Registers all ipcMain handlers and sets up the system tray.
 */

import {
  app,
  BrowserWindow,
  ipcMain,
  dialog,
  Tray,
  Menu,
  nativeImage,
  shell,
} from 'electron';
import * as path from 'path';
import * as fs from 'fs';
import * as os from 'os';

// IPC handlers
import { registerChatIpc } from './ipc/chatIpc';
import { registerFileIpc } from './ipc/fileIpc';
import { registerAudioIpc } from './ipc/audioIpc';

// DB
import { SessionStore } from './db/sessionStore';

// ── Constants ──────────────────────────────────────────────────────────────────
const FOVEATED_PORT = parseInt(process.env['FOVEATED_PORT'] || '8400', 10);
const FOVEATED_URL = `http://127.0.0.1:${FOVEATED_PORT}`;
const IS_DEV = !app.isPackaged;
const ASSETS_DIR = IS_DEV
  ? path.join(__dirname, '..', '..', 'assets')
  : path.join(process.resourcesPath, 'assets');

// ── Globals ────────────────────────────────────────────────────────────────────
let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let sessionStore: SessionStore | null = null;

// ── App data directory ─────────────────────────────────────────────────────────
function getAppDataDir(): string {
  const dir = path.join(app.getPath('userData'), 'lumax-vibe-coder');
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  return dir;
}

// ── Window creation ────────────────────────────────────────────────────────────
function createWindow(): BrowserWindow {
  const preloadPath = IS_DEV
    ? path.join(__dirname, 'preload.js')
    : path.join(__dirname, 'preload.js');

  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#0f0f17',
    titleBarStyle: 'hidden',
    titleBarOverlay: {
      color: '#0f0f17',
      symbolColor: '#a0a0b0',
      height: 36,
    },
    webPreferences: {
      preload: preloadPath,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,               // needed for preload to use Node APIs
      webSecurity: true,
      allowRunningInsecureContent: false,
    },
    show: false,
    icon: path.join(ASSETS_DIR, 'lumax.png'),
  });

  // Load the renderer shell
  const indexHtml = IS_DEV
    ? path.join(__dirname, '..', '..', 'src', 'renderer', 'index.html')
    : path.join(__dirname, '..', '..', 'src', 'renderer', 'index.html');
  win.loadFile(indexHtml);

  // Dev tools
  if (IS_DEV) win.webContents.openDevTools({ mode: 'detach' });

  win.once('ready-to-show', () => {
    win.show();
    win.focus();
  });

  win.on('closed', () => {
    mainWindow = null;
  });

  // External link guard
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://') || url.startsWith('http://')) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });

  return win;
}

// ── System Tray ────────────────────────────────────────────────────────────────
function createTray(): void {
  const iconPath = path.join(ASSETS_DIR, 'lumax.png');
  const icon = fs.existsSync(iconPath)
    ? nativeImage.createFromPath(iconPath).resize({ width: 16, height: 16 })
    : nativeImage.createEmpty();

  tray = new Tray(icon);
  tray.setToolTip('LUMAX Vibe Coder');
  tray.setContextMenu(
    Menu.buildFromTemplate([
      {
        label: 'Show LUMAX',
        click: () => {
          if (mainWindow) {
            mainWindow.show();
            mainWindow.focus();
          } else {
            mainWindow = createWindow();
          }
        },
      },
      { type: 'separator' },
      {
        label: 'Open Workspace...',
        click: () => {
          mainWindow?.webContents.send('tray:open-workspace');
        },
      },
      { type: 'separator' },
      {
        label: 'Quit',
        click: () => {
          app.quit();
        },
      },
    ])
  );

  tray.on('double-click', () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

// ── App lifecycle ──────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  // Load .env from LUMAX root if it exists
  const lumaxRoot = path.join(os.homedir(), 'program', 'LUMAX');
  const envPath = path.join(lumaxRoot, '.env');
  if (fs.existsSync(envPath)) {
    const lines = fs.readFileSync(envPath, 'utf8').split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed && !trimmed.startsWith('#')) {
        const [key, ...vals] = trimmed.split('=');
        if (key && vals.length > 0) {
          process.env[key.trim()] = vals.join('=').trim().replace(/^["']|["']$/g, '');
        }
      }
    }
  }

  // Init DB
  const dbPath = path.join(getAppDataDir(), 'jenna.db');
  sessionStore = new SessionStore(dbPath);

  // Register IPC channels
  registerChatIpc(ipcMain, FOVEATED_URL);
  registerFileIpc(ipcMain, dialog);
  registerAudioIpc(ipcMain);

  // Session IPC
  ipcMain.handle('sessions:list', () => sessionStore!.listSessions());
  ipcMain.handle('sessions:create', (_evt, title: string) =>
    sessionStore!.createSession(title)
  );
  ipcMain.handle('sessions:delete', (_evt, id: string) =>
    sessionStore!.deleteSession(id)
  );
  ipcMain.handle('sessions:messages', (_evt, sessionId: string) =>
    sessionStore!.getMessages(sessionId)
  );
  ipcMain.handle(
    'sessions:add-message',
    (_evt, sessionId: string, role: string, content: string) =>
      sessionStore!.addMessage(sessionId, role, content)
  );
  ipcMain.handle('sessions:rename', (_evt, id: string, title: string) =>
    sessionStore!.renameSession(id, title)
  );

  // Misc utility IPC
  ipcMain.handle('app:get-version', () => app.getVersion());
  ipcMain.handle('app:get-platform', () => process.platform);
  ipcMain.handle('app:get-workspace-id', () => {
    // Derive a stable workspace ID from the machine + user
    const raw = `lumax_${os.hostname()}_${os.userInfo().username}`;
    return Buffer.from(raw).toString('base64').slice(0, 32);
  });
  ipcMain.handle('app:open-external', (_evt, url: string) =>
    shell.openExternal(url)
  );

  // Window controls for custom title bar
  ipcMain.handle('window:minimize', () => mainWindow?.minimize());
  ipcMain.handle('window:maximize', () => {
    if (mainWindow?.isMaximized()) mainWindow.unmaximize();
    else mainWindow?.maximize();
  });
  ipcMain.handle('window:close', () => mainWindow?.close());
  ipcMain.handle('window:is-maximized', () => mainWindow?.isMaximized() ?? false);

  // Build window + tray
  mainWindow = createWindow();
  createTray();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      mainWindow = createWindow();
    } else {
      mainWindow?.show();
    }
  });
});

app.on('window-all-closed', () => {
  // On Windows/Linux, keep alive in tray rather than quitting
  if (process.platform === 'darwin') app.quit();
});

app.on('before-quit', () => {
  sessionStore?.close();
});
