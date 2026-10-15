/**
 * ═══════════════════════════════════════════════════════════════════════
 * COMPOSITE VISION v2 — Multi-Camera Room Stitching + Avatar Stencil
 * ═══════════════════════════════════════════════════════════════════════
 *
 * THE PROBLEM (updated):
 *   1. Avatar cameras are BLACK (only Layer 1 rendered)
 *   2. Webcam in room corner only sees ~60° — huge blind spots
 *   3. Quest passthrough sees the OTHER side of the room (user's view)
 *   4. When user sits down, full avatar body is redundant — Quest
 *      passthrough already shows the user's real body/legs/chair
 *
 * THE SOLUTION:
 *   This module now merges THREE vision sources into one composite frame
 *   that gives the avatar a comprehensive understanding of the environment:
 *
 *   SOURCE A: Room webcam (corner-mounted) — "the wall mirror"
 *     → Real-time user image with wide room context
 *
 *   SOURCE B: Quest passthrough (user's own headset cameras)
 *     → Views from the OPPOSITE side of the room
 *     → Fills blind spots the webcam can't see
 *     → Shows walls/floor behind the webcam's field of view
 *
 *   SOURCE C: Environment plaster (periodic full-room snapshot)
 *     → Stitched from both cameras into a rough room texture atlas
 *     → Updated every ~5 minutes for spatial awareness
 *     → Used when real-time sources are unavailable
 *
 *   AVATAR STENCIL (dynamic detail reduction):
 *     When user is STANDING: render full VRM body
 *     When user is SITTING: render ONLY the head (body is visible
 *       through Quest passthrough, no need to double-render it)
 *     Head model colored by detected user clothing colors
 *
 * ARCHITECTURE:
 *   CompositeVision.capture() →
 *     1. Render avatar POV (both layers)
 *     2. Capture webcam frame
 *     3. Capture Quest passthrough frame (if available)
 *     4. Update avatar stencil detail (head-only vs full body)
 *     5. Merge into composite frame for LLM injection
 */

import * as THREE from 'three';

export interface VisionComposite {
    base64: string;                    // Merged composite
    webcamBase64: string | null;       // Room camera
    passthroughBase64: string | null;  // Quest headset view
    timestamp: number;
    layers: string[];
    /** How much of the avatar is rendered */
    stencilLevel: 'full' | 'head_only' | 'none';
}

export interface EnvironmentPlaster {
    base64: string;
    textures: Map<string, string>;
    timestamp: number;
}

export interface CompositeConfig {
    envSnapshotIntervalMs: number;
    compositeWidth: number;
    compositeHeight: number;
    jpegQuality: number;
}

const DEFAULT_CONFIG: CompositeConfig = {
    envSnapshotIntervalMs: 300_000, // 5 minutes
    compositeWidth: 1024,
    compositeHeight: 768,
    jpegQuality: 0.75,
};

export class CompositeVision {
    private config: CompositeConfig;
    private envPlaster: EnvironmentPlaster = { base64: '', textures: new Map(), timestamp: 0 };
    private lastEnvSnapshot: number = 0;

    // Room webcam (corner-mounted)
    private webcamVideo: HTMLVideoElement | null = null;
    private webcamCanvas: HTMLCanvasElement | null = null;
    private webcamCtx: CanvasRenderingContext2D | null = null;

    // Quest passthrough (user's headset cameras)
    private passthroughVideo: HTMLVideoElement | null = null;
    private passthroughCanvas: HTMLCanvasElement | null = null;
    private passthroughCtx: CanvasRenderingContext2D | null = null;

    // Avatar stencil
    private userIsSitting: boolean = false;
    private userClothingColor: string = '#2a2a3e'; // Default dark outfit
    
    // Composite canvas
    private compositeCanvas: HTMLCanvasElement;
    private compositeCtx: CanvasRenderingContext2D;
    private log: (msg: string, color: string) => void;

    constructor(config?: Partial<CompositeConfig>, logFn?: (msg: string, _color: string) => void) {
        this.config = { ...DEFAULT_CONFIG, ...config };
        this.log = logFn || ((msg, _color) => console.log(`[CompositeVision] ${msg}`));
        this.compositeCanvas = document.createElement('canvas');
        this.compositeCanvas.width = this.config.compositeWidth;
        this.compositeCanvas.height = this.config.compositeHeight;
        this.compositeCtx = this.compositeCanvas.getContext('2d')!;
    }

    // ═══════════════════════════════════════════════════════════════
    // PUBLIC API
    // ═══════════════════════════════════════════════════════════════

    /** Init room webcam (corner, facing user). */
    async initWebcam(): Promise<boolean> {
        try {
            // Check if there is already an active portal stream/video in the window object to reuse
            const existingStream = (window as any).foveaiPortalStream;
            let existingVideo = (window as any).foveaiPortalVideo;
            
            if (existingStream) {
                if (!existingVideo) {
                    existingVideo = document.createElement('video');
                    existingVideo.autoplay = true;
                    existingVideo.muted = true;
                    existingVideo.playsInline = true;
                    existingVideo.srcObject = existingStream;
                    await existingVideo.play().catch((e: any) => console.warn('[CompositeVision] Video play failed:', e));
                    (window as any).foveaiPortalVideo = existingVideo;
                }
                this.webcamVideo = existingVideo;
                this.webcamCanvas = document.createElement('canvas');
                this.webcamCanvas.width = 640;
                this.webcamCanvas.height = 360; // Mirror portal uses 360p
                this.webcamCtx = this.webcamCanvas.getContext('2d');
                this.log('📹 Room webcam active (reused portal mirror camera)', 'var(--neon-green)');
                return true;
            }

            const stream = await navigator.mediaDevices.getUserMedia({
                video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }
            });
            this.webcamVideo = document.createElement('video');
            this.webcamVideo.autoplay = true; this.webcamVideo.muted = true;
            this.webcamVideo.playsInline = true; this.webcamVideo.srcObject = stream;
            await this.webcamVideo.play();
            this.webcamCanvas = document.createElement('canvas');
            this.webcamCanvas.width = 640; this.webcamCanvas.height = 480;
            this.webcamCtx = this.webcamCanvas.getContext('2d');
            this.log('📹 Room webcam active (corner mirror)', 'var(--neon-green)');
            return true;
        } catch (err: any) {
            this.log(`Webcam init failed: ${err.message}`, 'var(--neon-orange)');
            return false;
        }
    }

    /** Init Quest passthrough as second camera source. */
    async initPassthrough(videoElement?: HTMLVideoElement): Promise<boolean> {
        try {
            if (videoElement) {
                // Use external video element (already set up by XR pipeline)
                this.passthroughVideo = videoElement;
            } else {
                // Try to capture Quest display/raw camera via screen sharing
                const stream = await navigator.mediaDevices.getDisplayMedia({
                    video: { width: { ideal: 640 }, height: { ideal: 360 } }
                });
                this.passthroughVideo = document.createElement('video');
                this.passthroughVideo.autoplay = true; this.passthroughVideo.muted = true;
                this.passthroughVideo.playsInline = true; this.passthroughVideo.srcObject = stream;
                await this.passthroughVideo.play();
            }
            this.passthroughCanvas = document.createElement('canvas');
            this.passthroughCanvas.width = 640; this.passthroughCanvas.height = 360;
            this.passthroughCtx = this.passthroughCanvas.getContext('2d');
            this.log('📹 Quest passthrough active (rear room view)', 'var(--neon-blue)');
            return true;
        } catch (err: any) {
            this.log(`Passthrough init failed: ${err.message}`, 'var(--neon-orange)');
            return false;
        }
    }

    /**
     * Main capture: merge all sources into one composite frame.
     */
    async captureComposite(
        renderer: THREE.WebGLRenderer,
        scene: THREE.Scene,
        avatarCamera: THREE.PerspectiveCamera,
        userCamera?: THREE.Camera
    ): Promise<VisionComposite> {
        const now = Date.now();

        // JIT bind webcam if it became active globally
        if (!this.webcamVideo && (window as any).foveaiPortalVideo) {
            this.webcamVideo = (window as any).foveaiPortalVideo;
            this.webcamCanvas = document.createElement('canvas');
            this.webcamCanvas.width = 640;
            this.webcamCanvas.height = 360;
            this.webcamCtx = this.webcamCanvas.getContext('2d');
            this.log('📹 Room webcam JIT-bind from active portal video', 'var(--neon-green)');
        }

        // 1. Render avatar POV (toggling XR off temporarily so toDataURL reads backbuffer)
        const wasXREnabled = renderer.xr.enabled;
        renderer.xr.enabled = false;
        renderer.render(scene, avatarCamera);
        const avatarFrame = renderer.domElement.toDataURL('image/jpeg', this.config.jpegQuality);
        const avatarBase64 = avatarFrame.split(',')[1] || avatarFrame;
        renderer.xr.enabled = wasXREnabled;

        // 2. Capture webcam (room corner)
        let webcamBase64: string | null = null;
        if (this.webcamVideo && this.webcamCtx && this.webcamCanvas) {
            try {
                this.webcamCtx.drawImage(this.webcamVideo, 0, 0, this.webcamCanvas.width, this.webcamCanvas.height);
                webcamBase64 = this.webcamCanvas.toDataURL('image/jpeg', 0.7).split(',')[1] || null;
            } catch { webcamBase64 = null; }
        }

        // 3. Capture Quest passthrough / user viewpoint
        let passthroughBase64: string | null = null;
        if (userCamera) {
            try {
                const wasXREnabled2 = renderer.xr.enabled;
                renderer.xr.enabled = false;
                renderer.render(scene, userCamera);
                const frame = renderer.domElement.toDataURL('image/jpeg', this.config.jpegQuality);
                passthroughBase64 = frame.split(',')[1] || null;
                renderer.xr.enabled = wasXREnabled2;
            } catch { passthroughBase64 = null; }
        } else if (this.passthroughVideo && this.passthroughCtx && this.passthroughCanvas) {
            try {
                this.passthroughCtx.drawImage(this.passthroughVideo, 0, 0, 640, 360);
                passthroughBase64 = this.passthroughCanvas.toDataURL('image/jpeg', 0.7).split(',')[1] || null;
            } catch { passthroughBase64 = null; }
        }

        // 4. Environment plaster update (periodic)
        if (now - this.lastEnvSnapshot > this.config.envSnapshotIntervalMs) {
            await this.captureEnvironment(scene, renderer, avatarCamera);
        }

        // 5. Build composite frame
        const stencilLevel = this.userIsSitting ? 'head_only' : 'full';
        const compositeBase64 = this.buildComposite(avatarBase64, webcamBase64, passthroughBase64);

        return {
            base64: compositeBase64,
            webcamBase64,
            passthroughBase64,
            timestamp: now,
            layers: ['avatar_pov', webcamBase64 ? 'webcam' : '', passthroughBase64 ? 'passthrough' : '', this.envPlaster.base64 ? 'env' : ''].filter(Boolean),
            stencilLevel,
        };
    }

    /**
     * Build the composite frame: 2x2 grid layout.
     * 
     * ┌─────────────────────┬──────────────────────┐
     * │  AVATAR POV (main)  │  WEB CAM (corner)    │
     * │  (what Jen sees)    │  (user mirror)       │
     * ├─────────────────────┼──────────────────────┤
     * │  QUEST PASSTHROUGH  │  STATUS OVERLAY      │
     * │  (rear room view)   │  (time, stencil, etc)│
     * └─────────────────────┴──────────────────────┘
     */
    private buildComposite(
        avatarBase64: string,
        webcamBase64: string | null,
        passthroughBase64: string | null
    ): string {
        const w = this.config.compositeWidth;
        const h = this.config.compositeHeight;
        const hw = Math.floor(w / 2);
        const hh = Math.floor(h / 2);

        const ctx = this.compositeCtx;
        ctx.fillStyle = '#0a0a14';
        ctx.fillRect(0, 0, w, h);

        // Top-left: Avatar POV (main view)
        this.drawImage(ctx, avatarBase64, 0, 0, hw, hh);

        // Top-right: Webcam mirror
        if (webcamBase64) {
            this.drawImage(ctx, webcamBase64, hw, 0, hw, hh);
        } else {
            this.drawPlaceholder(ctx, 'CAM OFFLINE', hw, 0, hw, hh);
        }

        // Bottom-left: Quest passthrough (rear room)
        if (passthroughBase64) {
            this.drawImage(ctx, passthroughBase64, 0, hh, hw, hh);
        } else {
            this.drawPlaceholder(ctx, 'PASSTHROUGH OFFLINE', 0, hh, hw, hh);
        }

        // Bottom-right: Status overlay
        this.drawStatusQuadrant(ctx, hw, hh, hw, hh);

        return this.compositeCanvas.toDataURL('image/jpeg', this.config.jpegQuality).split(',')[1] || '';
    }

    private drawImage(ctx: CanvasRenderingContext2D, base64: string, x: number, y: number, w: number, h: number) {
        const img = new Image();
        img.src = 'data:image/jpeg;base64,' + base64;
        if (img.complete) {
            ctx.drawImage(img, x, y, w, h);
        } else {
            img.onload = () => ctx.drawImage(img, x, y, w, h);
        }
    }

    private drawPlaceholder(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, w: number, h: number) {
        ctx.fillStyle = '#1a1a2e';
        ctx.fillRect(x, y, w, h);
        ctx.fillStyle = '#00ffff';
        ctx.font = '14px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(text, x + w / 2, y + h / 2);
    }

    private drawStatusQuadrant(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
        ctx.fillStyle = '#0f0f1a';
        ctx.fillRect(x, y, w, h);
        ctx.fillStyle = '#00f3ff';
        ctx.font = '11px monospace';
        ctx.textAlign = 'left';
        const lines = [
            `TIME: ${new Date().toLocaleTimeString()}`,
            `STENCIL: ${this.userIsSitting ? 'HEAD-ONLY' : 'FULL BODY'}`,
            `WEBCAM: ${this.webcamVideo ? 'LIVE' : 'OFF'}`,
            `PASSTHROUGH: ${this.passthroughVideo ? 'LIVE' : 'OFF'}`,
            `CLOTHES: ${this.userClothingColor}`,
        ];
        lines.forEach((line, i) => ctx.fillText(line, x + 8, y + 18 + i * 16));
    }

    // ═══════════════════════════════════════════════════════════════
    // AVATAR STENCIL SYSTEM
    // ═══════════════════════════════════════════════════════════════

    /**
     * Set user posture — controls avatar rendering detail.
     * When SITTING: render only the head (body is visible through passthrough)
     * When STANDING: render full VRM body
     */
    setUserPosture(isSitting: boolean, headsetHeightMeters?: number) {
        this.userIsSitting = isSitting;
        if (headsetHeightMeters !== undefined && headsetHeightMeters < 1.4) {
            // Confirmed sitting (headset below standing eye level)
            this.userIsSitting = true;
        }
        this.log(`Avatar stencil: ${this.userIsSitting ? 'HEAD-ONLY (user sitting)' : 'FULL BODY (user standing)'}`, 'var(--neon-blue)');
    }

    /** Analyze user's clothing from the webcam frame and set stencil color. */
    async detectClothingColor(): Promise<string> {
        if (!this.webcamVideo || !this.webcamCtx || !this.webcamCanvas) return this.userClothingColor;
        try {
            this.webcamCtx.drawImage(this.webcamVideo, 0, 0, 640, 480);
            const imageData = this.webcamCtx.getImageData(300, 300, 40, 60); // Sample torso area
            let r = 0, g = 0, b = 0;
            for (let i = 0; i < imageData.data.length; i += 16) {
                r += imageData.data[i];
                g += imageData.data[i + 1];
                b += imageData.data[i + 2];
            }
            const count = Math.floor(imageData.data.length / 16);
            const avgR = Math.round(r / count);
            const avgG = Math.round(g / count);
            const avgB = Math.round(b / count);
            this.userClothingColor = `#${avgR.toString(16).padStart(2, '0')}${avgG.toString(16).padStart(2, '0')}${avgB.toString(16).padStart(2, '0')}`;
            this.log(`Clothing color detected: ${this.userClothingColor}`, 'var(--neon-blue)');
            return this.userClothingColor;
        } catch {
            return this.userClothingColor;
        }
    }

    /** Get current avatar stencil settings for the renderer. */
    getStencilConfig(): { headOnly: boolean; color: string } {
        return {
            headOnly: this.userIsSitting,
            color: this.userClothingColor,
        };
    }

    // ═══════════════════════════════════════════════════════════════
    // ENVIRONMENT
    // ═══════════════════════════════════════════════════════════════

    async captureEnvironment(scene: THREE.Scene, renderer: THREE.WebGLRenderer, camera?: THREE.Camera): Promise<void> {
        try {
            const activeCamera = camera || (scene.children.find(c => c instanceof THREE.Camera) as THREE.Camera);
            if (!activeCamera) {
                this.log('Environment capture skipped: No camera found', 'var(--neon-orange)');
                return;
            }
            const wasXREnabled = renderer.xr.enabled;
            renderer.xr.enabled = false;
            renderer.render(scene, activeCamera);
            const frame = renderer.domElement.toDataURL('image/jpeg', 0.6);
            renderer.xr.enabled = wasXREnabled;
            this.envPlaster = {
                base64: frame.split(',')[1] || frame,
                textures: new Map([['room', frame.split(',')[1] || '']]),
                timestamp: Date.now(),
            };
            this.lastEnvSnapshot = Date.now();
            this.log('🏠 Environment plaster updated', 'var(--neon-blue)');
            
            // Auto-update persistent SpatialEnvironment wall textures if available
            const spatialEnv = (window as any).spatialEnvironment;
            if (spatialEnv) {
                spatialEnv.applyEnvironmentPlaster(this.envPlaster.base64);
            }
        } catch (err: any) {
            this.log(`Environment capture failed: ${err.message}`, 'var(--neon-orange)');
        }
    }

    getEnvironmentPlasterBase64(): string | null {
        if (!this.envPlaster.base64) return null;
        if (Date.now() - this.envPlaster.timestamp > this.config.envSnapshotIntervalMs * 3) return null;
        return this.envPlaster.base64;
    }

    // ═══════════════════════════════════════════════════════════════
    // SENSORY INJECTION (for LLM prompt)
    // ═══════════════════════════════════════════════════════════════

    getSensoryContextNote(): string {
        const parts: string[] = ['[COMPOSITE VISION — Avatar Eyesight]'];
        parts.push(`  Stencil mode: ${this.userIsSitting ? 'HEAD-ONLY (user sitting, body via passthrough)' : 'FULL BODY (user standing)'}`);
        parts.push(`  Clothing color: ${this.userClothingColor}`);
        if (this.webcamVideo) parts.push('  Room webcam: LIVE (corner mirror)');
        else parts.push('  Room webcam: OFFLINE');
        if (this.passthroughVideo) parts.push('  Quest passthrough: LIVE (rear room view)');
        else parts.push('  Quest passthrough: OFFLINE');
        if (this.envPlaster.base64) {
            const age = Math.round((Date.now() - this.envPlaster.timestamp) / 1000);
            parts.push(`  Environment plaster: ${age}s old (periodic full-room snapshot)`);
        } else {
            parts.push('  Environment plaster: not yet captured');
        }
        parts.push('  YOU (the avatar) are the animated character. The user is the person in the room.');
        parts.push('  The webcam mirror shows the user in real time. You are NOT the user — you are a virtual companion.');
        return parts.join('\n');
    }

    dispose() {
        [this.webcamVideo, this.passthroughVideo].forEach(v => {
            if (v?.srcObject) { (v.srcObject as MediaStream).getTracks().forEach(t => t.stop()); }
        });
        this.webcamVideo = this.passthroughVideo = null;
        this.webcamCanvas = this.passthroughCanvas = null;
    }
}