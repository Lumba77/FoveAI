const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const isDev = process.env.NODE_ENV === 'development';

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    show: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false // For ease of porting internal IPC, but should be true in production
    },
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#1e1e1e'
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    mainWindow.focus();
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, 'dist', 'index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

const { spawn } = require('child_process');

let proxyProcess = null;

// Basic IPC to test connection to the local proxy
ipcMain.handle('ping-proxy', async () => {
  try {
    const res = await fetch('http://127.0.0.1:8400/health');
    return await res.json();
  } catch (err) {
    return { error: 'Foveated Proxy not reachable' };
  }
});

ipcMain.handle('start-proxy', () => {
  if (proxyProcess) return { status: 'already running' };
  
  // Point to the server.js in the foveated-memory directory
  const serverPath = path.join(__dirname, '..', '..', 'Tools', 'foveated-memory', 'server.js');
  proxyProcess = spawn('node', [serverPath], { cwd: path.dirname(serverPath) });
  
  return { status: 'started' };
});

ipcMain.handle('stop-proxy', () => {
  if (proxyProcess) {
    proxyProcess.kill();
    proxyProcess = null;
    return { status: 'stopped' };
  }
  return { status: 'not running' };
});

ipcMain.handle('start-nursery', () => {
  // Point to the sleipnir_nursery_launcher.js in the repo root
  const nurseryPath = path.join(__dirname, '..', '..', 'sleipnir_nursery_launcher.js');
  spawn('node', [nurseryPath], { cwd: path.dirname(nurseryPath), detached: true });
  return { status: 'launched' };
});

const fs = require('fs');

ipcMain.handle('list-models', () => {
  const modelsDir = path.join(__dirname, '..', '..', 'Training', 'unsloth_compiled_cache');
  if (!fs.existsSync(modelsDir)) return [];
  try {
    return fs.readdirSync(modelsDir).filter(f => f.endsWith('.gguf') || f.endsWith('.bin'));
  } catch (err) {
    return [];
  }
});

ipcMain.handle('download-model', async (event, repoId) => {
  return new Promise((resolve) => {
    // Assuming python is in path or in .venv
    const venvPython = path.join(__dirname, '..', '..', '.venv', 'Scripts', 'python.exe');
    const pythonExec = fs.existsSync(venvPython) ? venvPython : 'python';
    
    // Using huggingface-cli download
    const modelsDir = path.join(__dirname, '..', '..', 'Training', 'unsloth_compiled_cache');
    const dlProcess = spawn(pythonExec, ['-m', 'huggingface_hub.cli', 'download', repoId, '--local-dir', modelsDir], {
      cwd: path.join(__dirname, '..', '..')
    });
    
    dlProcess.on('close', (code) => {
      resolve({ success: code === 0, code });
    });
  });
});

// Soul DNA & Command Center Settings IPC
ipcMain.handle('get-soul-dna', async () => {
  try {
    const res = await fetch('http://127.0.0.1:8405/api/soul/soul_dna');
    return await res.json();
  } catch (_) {
    const soulPath = path.join(__dirname, '..', '..', 'Backend', 'Cognition', 'jen_soul.json');
    if (fs.existsSync(soulPath)) {
      return { dna: JSON.parse(fs.readFileSync(soulPath, 'utf8')) };
    }
    return { error: 'Could not load soul DNA' };
  }
});

ipcMain.handle('update-soul', async (event, patch) => {
  try {
    const res = await fetch('http://127.0.0.1:8405/api/soul/update_soul', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch)
    });
    return await res.json();
  } catch (err) {
    return { error: err.message };
  }
});

ipcMain.handle('open-settings', async () => {
  const { shell } = require('electron');
  await shell.openExternal('http://127.0.0.1:8414/settings.html#sec-persona');
  return { status: 'opened' };
});

