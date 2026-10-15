/**
    * GAME CONTROLLER - Virtual controller emulation for co - op gaming.
 *
 * Enables the avatar to play co - op games with the user by:
 * 1. Simulating a Meta Quest ghost account for VR co - op
    * 2. Emulating gamepad / keyboard input via virtual drivers
         * 3. Screen - reading + frame capture for 2D / 3D game play
            *
 * VR: Creates a "ghost" Meta account session using WebXR emulation
 * that the avatar controls.The avatar sees the same VR gorld
    * and can interact alongside the user(tennis, golf, racing, etc).
 *
 * Desktop: Uses virtual gamepad driver(ViGEm / vJoy) or keyboard
    * emulation to control games on the user's screen.
        *
 * Architecture:
 * Browser → WebSocket → Backend → ViGEm / vJoy driver → OS input layer
    * Browser → WebXR emulation → VR game
        */

export interface GamepadState {
    buttons: boolean[];  // 16 buttons (A, B, X, Y, LB, RB, triggers, sticks, d-pad)
    leftStick: [number, number];  // -1 to 1
    rightStick: [number, number]; // -1 to 1
    leftTrigger: number;  // 0 to 1
    rightTrigger: number; // 0 to 1
}

export interface KeyboardState {
    keysDown: string[];  // Current keys being pressed
}

const WS = 'ws://localhost:8410/controller'; // hands/motor — virtual gamepad service
const VIGEM = '/api/controller/vigem';

export class GameController {
    private ws: WebSocket | null = null;
    private connected = false;
    private gamepad: GamepadState;
    private log: (m: string, c: string) => void;

    constructor(logFn?: (m: string, c: string) => void) {
        this.log = logFn || ((m, c) => console.log('[GameCtrl] ' + m));
        this.gamepad = {
            buttons: new Array(16).fill(false),
            leftStick: [0, 0], rightStick: [0, 0],
            leftTrigger: 0, rightTrigger: 0,
        };
    }

    /** Connect to the backend controller driver. */
    async connect(): Promise<boolean> {
        try {
            this.ws = new WebSocket(WS);
            return new Promise(resolve => {
                if (!this.ws) { resolve(false); return; }
                this.ws.onopen = () => { this.connected = true; this.log('Controller connected', '#0f0'); resolve(true); };
                this.ws.onerror = () => { this.connected = false; resolve(false); };
                setTimeout(() => { if (!this.connected) resolve(false); }, 5000);
            });
        } catch { return false; }
    }

    disconnect(): void {
        if (this.ws) { this.ws.close(); this.ws = null; this.connected = false; }
    }

    /** Send full gamepad state to the system. */
    private send(): void {
        if (!this.connected || !this.ws || this.ws.readyState !== 1) return;
        try {
            this.ws.send(JSON.stringify({ type: 'gamepad', state: this.gamepad }));
        } catch (_) {}
    }

    // ── High-level game actions ──
    moveLeftStick(x: number, y: number): void { this.gamepad.leftStick = [x, y]; this.send(); }
    moveRightStick(x: number, y: number): void { this.gamepad.rightStick = [x, y]; this.send(); }

    press(buttonIndex: number): void { this.gamepad.buttons[buttonIndex] = true; this.send(); }
    release(buttonIndex: number): void { this.gamepad.buttons[buttonIndex] = false; this.send(); }
    tap(buttonIndex: number): void { this.press(buttonIndex); setTimeout(() => this.release(buttonIndex), 100); }

    // Convenience
    pressA(): void { this.tap(0); }
    pressB(): void { this.tap(1); }
    pressX(): void { this.tap(2); }
    pressY(): void { this.tap(3); }
    pressDpad(dir: 'up' | 'down' | 'left' | 'right'): void {
        const idx = { up: 12, down: 13, left: 14, right: 15 }[dir];
        this.tap(idx);
    }

    /** Emulate a keyboard key press. */
    async keyTap(key: string): Promise<boolean> {
        try {
            const r = await fetch(VIGEM, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type: 'keyboard', keys: [key], duration: 100 }),
            });
            return r.ok;
        } catch { return false; }
    }

    /** Emulate keyboard typing (for text input in games). */
    async typeText(text: string): Promise<void> {
        for (const char of text) {
            await this.keyTap(char);
            await new Promise(r => setTimeout(r, 50));
        }
    }

    // ── VR Ghost Account ──
    /** Initiate a WebXR ghost session for VR co-op. */
    async startVRSession(): Promise<boolean> {
        try {
            // Uses navigator.xr to launch parallel VR session
            const r = await fetch('/api/vr/ghost/start', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
            });
            if (r.ok) {
                this.log('VR Ghost session started', '#0f0');
                return true;
            }
            return false;
        } catch { return false; }
    }

    async stopVRSession(): Promise<void> {
        await fetch('/api/vr/ghost/stop', { method: 'POST' });
    }

    getContext(): string {
        const status = this.connected ? 'CONNECTED' : 'disconnected';
        return `[GAME CONTROLLER] Virtual gamepad ${status}. Keyboard emulation, VR ghost account available. Co-op ready.`;
    }

    isConnected(): boolean { return this.connected; }
    dispose(): void { this.disconnect(); }
}
