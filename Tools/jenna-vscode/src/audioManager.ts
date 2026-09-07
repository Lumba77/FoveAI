/**
 * audioManager.ts — Jenna Voice Recording Bridge
 *
 * Manages the Python-based audio recorder subprocess for voice input.
 * Provides push-to-talk and continuous voice recording modes.
 * Audio is transcribed via the foveated memory proxy (port 8400).
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
      this._recorder = spawn('python', [pyPath], {
        cwd: this._extensionPath,
        stdio: ['pipe', 'pipe', 'pipe'],
      });

      // Wait for "ready" signal from Python process
      const ready = new Promise<void>((resolve) => {
        if (this._recorder?.stdout) {
          const onData = (data: Buffer) => {
            const line = data.toString().trim();
            if (line === 'ready') {
              this._recorder!.stdout!.removeListener('data', onData);
              resolve();
            }
          };
          this._recorder.stdout.on('data', onData);
        } else {
          resolve();
        }
      });

      this._recorder.on('exit', (code) => {
        console.log(`[Jenna] Audio recorder exited with code ${code}`);
        this._recorder = null;
        this._recording = false;
      });

      // Give it time to start (max 2 seconds)
      await Promise.race([ready, new Promise(r => setTimeout(r, 2000))]);
    }

    this._sendToRecorder('start');
    this._recording = true;
    return true;
  }

  /**
   * Stop recording and optionally transcribe the captured audio.
   * Returns the transcribed text, or null if transcription failed.
   */
  async stopRecording(): Promise<string | null> {
    if (!this._recording) return null;
    this._recording = false;

    const timestamp = Date.now();
    const wavPath = path.join(this._outputDir, `jenna_recording_${timestamp}.wav`);
    this._sendToRecorder(`stop ${wavPath}`);

    // Give the file time to be written
    await new Promise(r => setTimeout(r, 300));

    // Try to transcribe via the proxy
    try {
      const config = vscode.workspace.getConfiguration('jenna');
      const baseUrl = config.get<string>('foveatedMemoryUrl', 'http://127.0.0.1:8400');
      
      if (fs.existsSync(wavPath)) {
        const audioBuffer = fs.readFileSync(wavPath);
        const base64Audio = audioBuffer.toString('base64');

        const resp = await fetch(`${baseUrl}/v1/audio/transcriptions`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${this._workspaceId}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            audio: base64Audio,
            model: 'whisper-1',
          }),
          signal: AbortSignal.timeout(10000),
        });

        if (resp.ok) {
          const data = await resp.json() as { text?: string };
          // Clean up temp file
          try { fs.unlinkSync(wavPath); } catch (_) {}
          return data.text?.trim() ?? null;
        }
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

