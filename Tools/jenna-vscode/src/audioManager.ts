/**
 * audioManager.ts — Jenna Voice Recording Bridge
 *
 * Manages the Python-based audio recorder subprocess for voice input.
 * Provides push-to-talk and continuous voice recording modes.
 * Audio is transcribed via the foveated memory proxy (port 8401, /api/soul/stt).
 */

import * as vscode from 'vscode';
import { spawn, ChildProcess } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

export class AudioManager {
  private _recorder: ChildProcess | null = null;
  private _recording = false;
  private _outputDir: string;
  private _micMode: 'ptt' | 'continuous' = 'ptt';
  private _disposables: vscode.Disposable[] = [];
  private _wavPath: string | null = null;
  private _stdoutLines: ((line: string) => void)[] = [];

  constructor(private _extensionPath: string, private _workspaceId: string) {
    this._outputDir = path.join(_extensionPath, 'out', 'recordings');
    try { fs.mkdirSync(this._outputDir, { recursive: true }); } catch (_) {}
  }

  get isRecording(): boolean {
    return this._recording;
  }

  get micMode(): string {
    return this._micMode;
  }

  set micMode(mode: 'ptt' | 'continuous') {
    this._micMode = mode;
  }

  private _pythonBin(): string {
    return process.platform === 'win32' ? 'python' : 'python3';
  }

  /** Wait for a specific line on the recorder's stdout (with timeout). */
  private _waitForLine(prefix: string, timeoutMs = 4000): Promise<string | null> {
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        this._stdoutLines = this._stdoutLines.filter(l => l !== handler);
        resolve(null);
      }, timeoutMs);
      const handler = (line: string) => {
        if (line.startsWith(prefix)) {
          clearTimeout(timer);
          this._stdoutLines = this._stdoutLines.filter(l => l !== handler);
          resolve(line);
        }
      };
      this._stdoutLines.push(handler);
    });
  }

  /**
   * Start voice recording. Spawns the Python audio recorder if not already running.
   */
  async startRecording(): Promise<boolean> {
    if (this._recording) return true;

    if (!this._recorder) {
      const pyPath = path.join(this._extensionPath, 'src', 'audioRecorder.py');
      if (!fs.existsSync(pyPath)) {
        vscode.window.showWarningMessage('Jenna: Audio recorder script not found at src/audioRecorder.py');
        return false;
      }
      this._recorder = spawn(this._pythonBin(), [pyPath], {
        cwd: this._extensionPath,
        stdio: ['pipe', 'pipe', 'pipe'],
      });

      // Fan stdout lines out to any pending waiters
      let buf = '';
      this._recorder.stdout?.on('data', (data: Buffer) => {
        buf += data.toString();
        let idx;
        while ((idx = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, idx).trim();
          buf = buf.slice(idx + 1);
          for (const fn of [...this._stdoutLines]) fn(line);
        }
      });

      this._recorder.stderr?.on('data', (data: Buffer) => {
        console.error('[Jenna] recorder stderr:', data.toString().trim());
      });

      this._recorder.on('exit', (code) => {
        console.log(`[Jenna] Audio recorder exited with code ${code}`);
        this._recorder = null;
        this._recording = false;
      });

      const ready = await this._waitForLine('ready', 3000);
      if (!ready) {
        console.warn('[Jenna] recorder did not signal ready');
      }
    }

    const timestamp = Date.now();
    this._wavPath = path.join(this._outputDir, `jenna_recording_${timestamp}.wav`);
    this._sendToRecorder(`start ${this._wavPath}`);
    this._recording = true;
    return true;
  }

  /**
   * Stop recording and transcribe the captured audio via the proxy's STT route.
   * Returns the transcribed text, or null if transcription failed.
   */
  async stopRecording(): Promise<string | null> {
    if (!this._recording) return null;
    this._recording = false;

    const wavPath = this._wavPath;
    this._wavPath = null;
    const saved = this._waitForLine('saved', 6000);
    this._sendToRecorder('stop');
    await saved;

    // Try to transcribe via the proxy
    try {
      const config = vscode.workspace.getConfiguration('jenna');
      const baseUrl = config.get<string>('foveatedMemoryUrl', 'http://127.0.0.1:8400');

      if (wavPath && fs.existsSync(wavPath)) {
        const audioBuffer = fs.readFileSync(wavPath);
        const base64Audio = audioBuffer.toString('base64');

        const resp = await fetch(`${baseUrl}/api/soul/stt`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${this._workspaceId}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            audio_base64: base64Audio,
            format: 'audio/wav',
            filename: path.basename(wavPath),
          }),
          signal: AbortSignal.timeout(20000),
        });

        if (resp.ok) {
          const data = await resp.json() as { text?: string };
          // Clean up temp file
          try { fs.unlinkSync(wavPath); } catch (_) {}
          return data.text?.trim() ?? null;
        }
        console.warn('[Jenna] STT returned', resp.status);
      }
    } catch (e) {
      console.error('[Jenna] Audio transcription failed:', e);
    }

    // If transcription failed, return null — caller can show a message
    return null;
  }

  /**
   * Cancel the current recording without saving/transcribing.
   */
  cancelRecording(): void {
    if (!this._recording) return;
    this._recording = false;
    this._wavPath = null;
    this._sendToRecorder('cancel');
  }

  dispose(): void {
    if (this._recorder) {
      this._sendToRecorder('quit');
      setTimeout(() => {
        if (this._recorder) {
          this._recorder.kill();
          this._recorder = null;
        }
      }, 500);
    }
    this._disposables.forEach(d => d.dispose());
  }

  private _sendToRecorder(cmd: string): void {
    if (this._recorder?.stdin?.writable) {
      this._recorder.stdin.write(cmd + '\n');
    }
  }
}
