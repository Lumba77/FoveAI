/**
 * audioIpc.ts — Voice Recording IPC Bridge
 *
 * Bridges Electron ↔ Python audioRecorder.py subprocess.
 * Same approach as audioManager.ts in jenna-vscode, adapted for ipcMain.
 */

import type { IpcMain, WebContents } from 'electron';
import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';
import * as os from 'os';

// Path to the Python recorder (same as jenna-vscode's, reused)
const RECORDER_SCRIPT = path.join(
  os.homedir(), 'program', 'LUMAX', 'Tools', 'jenna-vscode', 'src', 'audioRecorder.py'
);

// Local copy fallback (will be created alongside this file)
const LOCAL_RECORDER = path.join(__dirname, '..', 'audioRecorder.py');

function getRecorderPath(): string {
  if (fs.existsSync(RECORDER_SCRIPT)) return RECORDER_SCRIPT;
  if (fs.existsSync(LOCAL_RECORDER)) return LOCAL_RECORDER;
  return RECORDER_SCRIPT; // let it fail with a meaningful error
}

let recorderProcess: ChildProcess | null = null;
let recorderSender: WebContents | null = null;

export function registerAudioIpc(ipcMain: IpcMain): void {

  // ── audio:start ─────────────────────────────────────────────────────────────
  ipcMain.handle('audio:start', (event) => {
    if (recorderProcess) return; // already recording

    recorderSender = event.sender;
    const pythonExe = getPythonExecutable();
    const recorderPath = getRecorderPath();

    recorderProcess = spawn(pythonExe, [recorderPath, '--stream'], {
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    recorderProcess.stdout?.on('data', (data: Buffer) => {
      const text = data.toString().trim();
      if (text && recorderSender && !recorderSender.isDestroyed()) {
        recorderSender.send('audio:transcript', text);
      }
    });

    recorderProcess.stderr?.on('data', (data: Buffer) => {
      console.error('[audioIpc] recorder stderr:', data.toString());
    });

    recorderProcess.on('close', (code) => {
      console.log(`[audioIpc] recorder exited with code ${code}`);
      recorderProcess = null;
      recorderSender = null;
    });

    recorderProcess.on('error', (err) => {
      console.error('[audioIpc] recorder error:', err.message);
      recorderProcess = null;
      recorderSender = null;
    });
  });

  // ── audio:stop ──────────────────────────────────────────────────────────────
  ipcMain.handle('audio:stop', () => {
    if (!recorderProcess) return '';
    recorderProcess.kill('SIGTERM');
    recorderProcess = null;
    recorderSender = null;
    return '';
  });

  // ── audio:get-devices ───────────────────────────────────────────────────────
  ipcMain.handle('audio:get-devices', () => {
    // Returns empty — device selection is handled via Web Audio API in renderer
    return [];
  });
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function getPythonExecutable(): string {
  // Try LUMAX venv first
  const lumaxVenv = path.join(os.homedir(), 'program', 'LUMAX', '.venv', 'Scripts', 'python.exe');
  if (fs.existsSync(lumaxVenv)) return lumaxVenv;

  // Try jenna-vscode venv
  const jennaVenv = path.join(os.homedir(), 'program', 'LUMAX', 'Tools', 'jenna-vscode', '.venv', 'Scripts', 'python.exe');
  if (fs.existsSync(jennaVenv)) return jennaVenv;

  // Fall back to system python
  return 'python';
}
