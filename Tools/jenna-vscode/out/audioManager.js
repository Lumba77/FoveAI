"use strict";
/**
 * audioManager.ts — Jenna Voice Recording Bridge
 *
 * Manages the Python-based audio recorder subprocess for voice input.
 * Provides push-to-talk and continuous voice recording modes.
 * Audio is transcribed via the foveated memory proxy (port 8401).
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.AudioManager = void 0;
const vscode = __importStar(require("vscode"));
const child_process_1 = require("child_process");
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
class AudioManager {
    _extensionPath;
    _workspaceId;
    _recorder = null;
    _recording = false;
    _outputDir;
    _micMode = 'ptt';
    _disposables = [];
    constructor(_extensionPath, _workspaceId) {
        this._extensionPath = _extensionPath;
        this._workspaceId = _workspaceId;
        this._outputDir = path.join(_extensionPath, 'out', 'recordings');
        try {
            fs.mkdirSync(this._outputDir, { recursive: true });
        }
        catch (_) { }
    }
    get isRecording() {
        return this._recording;
    }
    get micMode() {
        return this._micMode;
    }
    set micMode(mode) {
        this._micMode = mode;
    }
    /**
     * Start voice recording. Spawns the Python audio recorder if not already running.
     */
    async startRecording() {
        if (this._recording)
            return true;
        if (!this._recorder) {
            const pyPath = path.join(this._extensionPath, 'src', 'audioRecorder.py');
            if (!fs.existsSync(pyPath)) {
                vscode.window.showWarningMessage('Jenna: Audio recorder script not found at src/audioRecorder.py');
                return false;
            }
            this._recorder = (0, child_process_1.spawn)('python', [pyPath], {
                cwd: this._extensionPath,
                stdio: ['pipe', 'pipe', 'pipe'],
            });
            // Wait for "ready" signal from Python process
            const ready = new Promise((resolve) => {
                if (this._recorder?.stdout) {
                    const onData = (data) => {
                        const line = data.toString().trim();
                        if (line === 'ready') {
                            this._recorder.stdout.removeListener('data', onData);
                            resolve();
                        }
                    };
                    this._recorder.stdout.on('data', onData);
                }
                else {
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
    async stopRecording() {
        if (!this._recording)
            return null;
        this._recording = false;
        const timestamp = Date.now();
        const wavPath = path.join(this._outputDir, `jenna_recording_${timestamp}.wav`);
        this._sendToRecorder(`stop ${wavPath}`);
        // Give the file time to be written
        await new Promise(r => setTimeout(r, 300));
        // Try to transcribe via the proxy
        try {
            const config = vscode.workspace.getConfiguration('jenna');
            const baseUrl = config.get('foveatedMemoryUrl', 'http://127.0.0.1:8400');
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
                    const data = await resp.json();
                    // Clean up temp file
                    try {
                        fs.unlinkSync(wavPath);
                    }
                    catch (_) { }
                    return data.text?.trim() ?? null;
                }
            }
        }
        catch (e) {
            console.error('[Jenna] Audio transcription failed:', e);
        }
        // If transcription failed, return null — caller can show a message
        return null;
    }
    /**
     * Cancel the current recording without saving/transcribing.
     */
    cancelRecording() {
        if (!this._recording)
            return;
        this._recording = false;
        this._sendToRecorder('cancel');
    }
    dispose() {
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
    _sendToRecorder(cmd) {
        if (this._recorder?.stdin?.writable) {
            this._recorder.stdin.write(cmd + '\n');
        }
    }
}
exports.AudioManager = AudioManager;
//# sourceMappingURL=audioManager.js.map