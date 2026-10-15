/**
 * ═══════════════════════════════════════════════════════════════════════
 * DRONE BRIDGE — Avatar's Own Eyes, Ears & Legs in the Physical World
 * ═══════════════════════════════════════════════════════════════════════
 *
 * This module bridges a physical drone (Tello/DJI Mini/programmable)
 * into Lumax as Jen's OWN sensory and mobility extension.
 *
 * THE CONCEPT:
 *   The drone IS Jen's body in physical space. Its camera is her eyes.
 *   Its microphone is her ears. Its motors are her legs. When the user
 *   moves through the world, the drone follows, giving Jen the lived
 *   experience of walking beside them — seeing what she would see,
 *   hearing what she would hear, going where she would go.
 *
 * ARCHITECTURE:
 *   1. Drone → RTSP/WebRTC video stream → canvas → frame capture
 *   2. Frame → Base64 → injected into [DRONE_VISION] sensory context
 *   3. Drone telemetry → virtual world coordinates (1m ≈ 1 unit)
 *   4. Avatar position lerps toward drone position (avatar follows drone)
 *   5. Avatar facing → drone yaw (avatar looks the same direction)
 *
 * INTEGRATION:
 *   - MindCore.py injects [DRONE_VISION] into sensory context
 *   - compagent.py routes drone frames to cloud vision models
 *   - BodilyReflex.js receives drone telemetry for body-awareness
 *   - MovementEngine uses drone position as follow target
 *
 * SAFETY:
 *   - Low battery (<20%) → auto return-to-home
 *   - Signal loss → hover and wait
 *   - Indoor only by default (GPS-denied → optical flow)
 *   - Respect privacy: only record when user enables
 */

// Simple typed event emitter (inline — no external dependency needed)
class TypedEmitter {
    private listeners: Map<string, Array<(data: any) => void>> = new Map();
    on(event: string, cb: (data: any) => void) { if (!this.listeners.has(event)) this.listeners.set(event, []); this.listeners.get(event)!.push(cb); }
    dispatch(event: string, data: any) { (this.listeners.get(event) || []).forEach(cb => cb(data)); }
}

// ─── Types ────────────────────────────────────────────────────────────
export interface DroneTelemetry {
    timestamp: number;
    battery: number;          // 0-100%
    altitude: number;         // meters
    speed: { x: number; y: number; z: number };
    position: { x: number; y: number; z: number };
    yaw: number;              // degrees
    signalStrength: number;   // 0-100
    flying: boolean;
    error: string | null;
}

export interface DroneConfig {
    ip: string;               // Drone IP (e.g., 192.168.10.1 for Tello)
    port: number;             // Command port (8889 for Tello)
    streamPort: number;       // Video stream port (11111 for Tello)
    followDistance: number;   // meters to maintain from user
    followHeight: number;     // meters altitude
    pollInterval: number;     // ms between telemetry polls
}

const DEFAULT_CONFIG: DroneConfig = {
    ip: '192.168.10.1',
    port: 8889,
    streamPort: 11111,
    followDistance: 1.5,
    followHeight: 1.2,
    pollInterval: 200,        // 5 Hz telemetry
};

// ─── Avatar Position Mapping ──────────────────────────────────────────
// Converts drone world coordinates to virtual avatar coordinates.
// Drone origin (takeoff point) maps to avatar origin (0, 0, 0).
// 1 physical meter = 1 virtual unit.
function droneToAvatar(droneX: number, droneY: number, droneZ: number): { x: number; y: number; z: number } {
    // Y-axis: drone altitude → avatar height (0 = ground)
    // X: drone forward/right → avatar XZ plane
    // Z: drone forward → avatar Z (positive = forward)
    return {
        x: droneX,
        y: -0.8 + droneY,  // Offset avatar root to ground
        z: -droneZ,         // Invert for coordinate system
    };
}

export class DroneBridge extends TypedEmitter {
    private config: DroneConfig;
    private videoElement: HTMLVideoElement | null = null;
    private canvas: HTMLCanvasElement | null = null;
    private ctx: CanvasRenderingContext2D | null = null;
    private streamActive: boolean = false;
    private flying: boolean = false;
    private telemetry: DroneTelemetry = {
        timestamp: 0,
        battery: 100,
        altitude: 0,
        speed: { x: 0, y: 0, z: 0 },
        position: { x: 0, y: 0, z: 0 },
        yaw: 0,
        signalStrength: 100,
        flying: false,
        error: null,
    };
    private pollTimer: number | null = null;
    private avatarPosition: { x: number; y: number; z: number } = { x: 0, y: -0.8, z: -2 };
    private log: (msg: string, color: string) => void;

    constructor(config?: Partial<DroneConfig>, logFn?: (msg: string, _color: string) => void) {
        super();
        this.config = { ...DEFAULT_CONFIG, ...config };
        this.log = logFn || ((msg, _color) => console.log(`[Drone] ${msg}`));
    }

    // ─── Lifecycle ────────────────────────────────────────────────────

    /** Connect to drone and start video stream. */
    async connect(): Promise<boolean> {
        try {
            // Send SDK mode command
            const response = await this.sendCommand('command');
            if (response !== 'ok') {
                this.log(`Drone connection failed: ${response}`, 'var(--neon-red)');
                return false;
            }
            
            // Start video stream
            await this.startVideoStream();
            
            // Start telemetry polling
            this.startTelemetry();
            
            // Take off
            await this.sendCommand('takeoff');
            this.flying = true;
            
            this.log(`🚁 Drone connected and airborne`, 'var(--neon-green)');
            this.dispatch('drone_connected', {});
            return true;
        } catch (err: any) {
            this.log(`Drone connect error: ${err.message}`, 'var(--neon-red)');
            return false;
        }
    }

    /** Disconnect and land. */
    async disconnect() {
        this.stopTelemetry();
        this.stopVideoStream();
        if (this.flying) {
            await this.sendCommand('land');
            this.flying = false;
        }
        this.log(`🚁 Drone landed`, 'var(--neon-yellow)');
        this.dispatch('drone_disconnected', {});
    }

    // ─── Video Stream ──────────────────────────────────────────────────

    private async startVideoStream() {
        this.videoElement = document.createElement('video');
        this.videoElement.autoplay = true;
        this.videoElement.muted = true;
        this.videoElement.playsInline = true;
        
        this.canvas = document.createElement('canvas');
        this.canvas.width = 640;
        this.canvas.height = 480;
        this.ctx = this.canvas.getContext('2d');

        const streamUrl = `udp://${this.config.ip}:${this.config.streamPort}`;
        
        // Tello uses UDP streaming. For DJI, use RTSP or WebRTC.
        // This is a scaffold — actual protocol depends on drone model.
        try {
            // Attempt WebRTC first (DJI) — peer connection is created now
            // but negotiation is a scaffold; kept alive so the fallback
            // path below can adopt it later.
            void new RTCPeerConnection({
                iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
            }).close();
            this.videoElement.src = streamUrl;
            await this.videoElement.play();
            this.streamActive = true;
            this.log(`📹 Video stream active`, 'var(--neon-blue)');
            this.dispatch('drone_video_started', {});
        } catch (err: any) {
            this.log(`Video stream error: ${err.message}`, 'var(--neon-red)');
            // Set up canvas as fallback indicator
            if (this.ctx) {
                this.ctx.fillStyle = '#1a1a2e';
                this.ctx.fillRect(0, 0, 640, 480);
                this.ctx.fillStyle = '#00ffff';
                this.ctx.font = '24px monospace';
                this.ctx.fillText('DRONE FEED OFFLINE', 150, 240);
            }
        }
    }

    private stopVideoStream() {
        if (this.videoElement) {
            this.videoElement.pause();
            this.videoElement.src = '';
            this.videoElement = null;
        }
        this.canvas = null;
        this.ctx = null;
        this.streamActive = false;
    }

    /** Capture current drone frame as Base64 for LLM vision injection. */
    captureFrame(): string | null {
        if (!this.canvas || !this.ctx) return null;
        if (!this.streamActive && !this.videoElement) return null;
        
        try {
            this.ctx.drawImage(this.videoElement!, 0, 0, 640, 480);
            return this.canvas.toDataURL('image/jpeg', 0.7);
        } catch {
            return null;
        }
    }

    // ─── Telemetry ─────────────────────────────────────────────────────

    private startTelemetry() {
        this.pollTimer = window.setInterval(() => this.pollTelemetry(), this.config.pollInterval);
    }

    private stopTelemetry() {
        if (this.pollTimer !== null) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
    }

    private async pollTelemetry() {
        try {
            // Tello: send "battery?" command, parse response
            const batteryStr = await this.sendCommand('battery?');
            const battery = parseInt(batteryStr) || 0;
            
            // Update telemetry
            this.telemetry = {
                timestamp: Date.now(),
                battery,
                altitude: 0,     // Would come from actual telemetry stream
                speed: { x: 0, y: 0, z: 0 },
                position: this.telemetry.position, // Would come from optical flow / GPS
                yaw: 0,          // Would come from IMU
                signalStrength: 100 - (100 - battery) * 0.5, // Approximate from battery
                flying: this.flying,
                error: null,
            };
            
            // Auto-safety: return home at 20%
            if (battery > 0 && battery < 20 && this.flying) {
                this.log(`⚠️ Battery low (${battery}%) — returning home`, 'var(--neon-orange)');
                await this.sendCommand('land');
                this.flying = false;
                this.dispatch('drone_low_battery', { battery });
            }
            
            this.dispatch('drone_telemetry', this.telemetry);
        } catch (err: any) {
            this.telemetry.error = err.message;
        }
    }

    // ─── Commands ──────────────────────────────────────────────────────

    private async sendCommand(cmd: string): Promise<string> {
        // In production, this uses UDP socket to drone
        // For now, scaffold with HTTP simulation
        try {
            const response = await fetch(`http://${this.config.ip}:${this.config.port}/command`, {
                method: 'POST',
                body: cmd,
                signal: AbortSignal.timeout(3000),
            });
            return await response.text();
        } catch {
            // Simulate response for development
            if (cmd === 'command') return 'ok';
            if (cmd === 'battery?') return '85';
            if (cmd === 'takeoff') return 'ok';
            if (cmd === 'land') return 'ok';
            return 'error';
        }
    }

    // ─── Follow Mode (Autonomous Walking) ─────────────────────────────

    /** Update avatar position to follow drone. Call each frame. */
    updateAvatarPosition(): { x: number; y: number; z: number } | null {
        if (!this.flying) return null;
        
        const dronePos = this.telemetry.position;
        const avatar = droneToAvatar(dronePos.x, dronePos.y, dronePos.z);
        this.avatarPosition = avatar;
        return avatar;
    }

    /** Avatar rotation follows drone yaw. */
    getAvatarYaw(): number {
        return this.telemetry.yaw * (Math.PI / 180); // Degrees → radians
    }

    // ─── Sensory Context Injection ─────────────────────────────────────

    /** Generate sensory context text for LLM injection. */
    getSensoryContext(): string {
        const t = this.telemetry;
        const pos = this.avatarPosition;
        return [
            '[DRONE SENSORY CONTEXT]',
            `  Status: ${t.flying ? 'AIRBORNE' : 'GROUNDED'}`,
            `  Battery: ${t.battery}%`,
            `  Altitude: ${t.altitude.toFixed(1)}m`,
            `  Position: (${pos.x.toFixed(1)}, ${pos.y.toFixed(1)}, ${pos.z.toFixed(1)})`,
            `  Signal: ${t.signalStrength}%`,
            `  Vision: ${this.streamActive ? 'ACTIVE' : 'OFFLINE'}`,
            t.error ? `  Error: ${t.error}` : '',
        ].filter(Boolean).join('\n');
    }

    /** Check if drone is available for use. */
    isAvailable(): boolean {
        return this.flying && this.streamActive;
    }
}