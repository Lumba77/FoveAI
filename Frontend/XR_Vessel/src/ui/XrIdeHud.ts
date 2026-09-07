import * as THREE from 'three';

export interface DevEditsPayload {
    status: string;
    timestamp?: string;
    git_status?: string[];
    files_changed?: { file: string; changes: number; sign: string }[];
    commands?: string[];
    code_preview?: string;
    diff_head?: string;
}

const CYAN = '#00f3ff';
const PINK = '#ff007f';
const GREEN = '#39ff14';
const ORANGE = '#ffaa00';
const BG = 'rgba(4, 8, 16, 0.62)';
const FONT = "'Orbitron', 'Segoe UI', monospace";

function fitText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string {
    if (ctx.measureText(text).width <= maxWidth) return text;
    let low = 1, high = text.length, best = text.slice(0, 1);
    while (low <= high) {
        const mid = Math.floor((low + high) / 2);
        const slice = text.slice(0, mid) + '…';
        if (ctx.measureText(slice).width <= maxWidth) {
            best = slice;
            low = mid + 1;
        } else {
            high = mid - 1;
        }
    }
    return best;
}

function wordWrap(ctx: CanvasRenderingContext2D, text: string, maxWidth: number, maxLines: number): string[] {
    const out: string[] = [];
    const lines = text.split('\n');
    for (const raw of lines) {
        if (out.length >= maxLines) break;
        const words = raw.split(' ');
        let line = '';
        for (const w of words) {
            const test = line ? line + ' ' + w : w;
            if (ctx.measureText(test).width <= maxWidth) {
                line = test;
            } else {
                if (line) out.push(line);
                line = w;
                if (out.length >= maxLines) break;
            }
        }
        if (line && out.length < maxLines) out.push(line);
    }
    return out.slice(0, maxLines);
}

function rinseCommands(cmds: string[]): string[] {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const c of cmds) {
        const key = c.replace(/\d+/g, '#').toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        out.push(c);
        if (out.length >= 7) break;
    }
    return out.length ? out : ['No recent commands'];
}

export class XrIdeHud {
    public group = new THREE.Group();
    public backdrop: THREE.Mesh | null = null;
    public hudCards: THREE.Mesh[] = [];
    private backdropCanvas: HTMLCanvasElement;
    private backdropCtx: CanvasRenderingContext2D;
    private backdropTex: THREE.CanvasTexture;
    private cardCanvases: { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D; tex: THREE.CanvasTexture; mesh: THREE.Mesh }[] = [];
    private data: DevEditsPayload = { status: 'idle' };
    private visible = false;
    private targetOpacity = 0;
    private rayTargets: THREE.Object3D[] = [];
    private hoverTarget: THREE.Object3D | null = null;
    private clickPending = false;
    private lastDevModeActive = false;
    private lastListeningActive = false;
    private bgImage: HTMLImageElement | null = null;
    private videoElement: HTMLVideoElement | null = null;

    constructor() {
        // Backdrop canvas
        this.backdropCanvas = document.createElement('canvas');
        this.backdropCanvas.width = 1536;
        this.backdropCanvas.height = 768;
        this.backdropCtx = this.backdropCanvas.getContext('2d')!;
        this.backdropTex = new THREE.CanvasTexture(this.backdropCanvas);
        this.backdropTex.colorSpace = THREE.SRGBColorSpace;
        this.backdropTex.minFilter = THREE.LinearFilter;
        this.backdropTex.magFilter = THREE.LinearFilter;

        // HUD card canvases
        for (let i = 0; i < 4; i++) {
            const c = document.createElement('canvas');
            c.width = 512;
            c.height = 128;
            const ctx = c.getContext('2d')!;
            const tex = new THREE.CanvasTexture(c);
            tex.colorSpace = THREE.SRGBColorSpace;
            tex.minFilter = THREE.LinearFilter;
            tex.magFilter = THREE.LinearFilter;
            const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide });
            const mesh = new THREE.Mesh(new THREE.PlaneGeometry(0.4, 0.1), mat);
            mesh.name = `ide_hud_card_${i}`;
            this.cardCanvases.push({ canvas: c, ctx, tex, mesh });
            this.hudCards.push(mesh);
            this.group.add(mesh);
        }
    }

    public build(scene: THREE.Scene, camera: THREE.Camera) {
        // Backdrop: large semi-transparent plane in front of user
        const geo = new THREE.PlaneGeometry(5.5, 2.8);
        const mat = new THREE.MeshBasicMaterial({
            map: this.backdropTex,
            transparent: true,
            opacity: 0,
            depthWrite: false,
            side: THREE.DoubleSide
        });
        this.backdrop = new THREE.Mesh(geo, mat);
        this.backdrop.name = 'ide_backdrop';
        this.backdrop.position.set(0, 1.4, -4.5); // Static position behind Jen in the middle back-end of room
        this.backdrop.lookAt(0, 1.4, 0);
        this.group.add(this.backdrop);
        this.rayTargets.push(this.backdrop);

        // Cards arranged across top
        const cardY = 0.35;
        const cardZ = -0.6;
        const cardW = 0.42;
        this.hudCards[0].position.set(-cardW * 1.55, cardY, cardZ);
        this.hudCards[1].position.set(-cardW * 0.52, cardY, cardZ);
        this.hudCards[2].position.set(cardW * 0.52, cardY, cardZ);
        this.hudCards[3].position.set(cardW * 1.55, cardY, cardZ);
        this.hudCards.forEach((m, i) => {
            m.lookAt(0, cardY, -2);
            m.userData.index = i;
            this.rayTargets.push(m);
        });

        // Also make each HUD card an interactive ray target for direct pointer selection
        this.hudCards.forEach((m) => {
            m.userData.isIdeTarget = true;
        });
        if (this.backdrop) {
            this.backdrop.userData.isIdeTarget = true;
        }

        scene.add(this.group);
        this.drawBackdrop();
        this.drawCards();
    }

    public setVisible(v: boolean) {
        this.visible = v;
        this.targetOpacity = v ? 1 : 0;
    }

    public toggle() {
        this.setVisible(!this.visible);
        return this.visible;
    }

    public isVisible() { return this.visible; }

    public playVideo(url: string) {
        this.stopVideo();
        const isVideo = url.match(/\.(mp4|webm|ogg|m3u8|mov|m4v)/i) || url.startsWith('blob:') || url.includes('stream') || url.includes('video');
        if (isVideo) {
            if (!this.videoElement) {
                this.videoElement = document.createElement('video');
                this.videoElement.crossOrigin = 'anonymous';
                this.videoElement.loop = true;
                this.videoElement.muted = true;
                this.videoElement.playsInline = true;
            }
            this.videoElement.src = url;
            this.videoElement.play().catch(e => console.warn('[XR-IDE] Video play failed:', e));
        } else {
            if (!this.bgImage) {
                this.bgImage = new Image();
                this.bgImage.crossOrigin = 'anonymous';
                this.bgImage.onload = () => this.drawBackdrop();
            }
            this.bgImage.src = url;
        }
    }

    public stopVideo() {
        if (this.videoElement) {
            this.videoElement.pause();
            this.videoElement.src = '';
        }
        if (this.bgImage) {
            this.bgImage.src = '';
        }
        this.drawBackdrop();
    }

    public setData(d: DevEditsPayload) {
        this.data = d;
        this.drawBackdrop();
    }

    private drawCards() {
        const isDev = !!(window as any).isDevModeActive;
        const isListening = !!(window as any).dashboard?.isListening;
        const labels = [
            { icon: '👩', text: 'JEN COMPANION', color: PINK },
            { icon: '🛠️', text: isDev ? 'DEV: ACTIVE' : 'DEV: OFFLINE', color: isDev ? GREEN : '#ff5500' },
            { icon: '🎙️', text: isListening ? 'VAD: LISTENING' : 'VAD: STANDBY', color: isListening ? GREEN : CYAN },
            { icon: '🖥️', text: 'SYS VITAL', color: GREEN },
        ];
        this.cardCanvases.forEach(({ canvas, ctx, tex, mesh }, i) => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            const { icon, text, color } = labels[i];
            ctx.fillStyle = 'rgba(4,8,16,0.85)';
            ctx.strokeStyle = color;
            ctx.lineWidth = 3;
            roundRect(ctx, 8, 8, canvas.width - 16, canvas.height - 16, 12);
            ctx.fill();
            ctx.stroke();
            ctx.font = `bold 28px ${FONT}`;
            ctx.fillStyle = '#ffffff';
            ctx.textBaseline = 'middle';
            ctx.fillText(icon, 26, canvas.height / 2);
            ctx.font = `24px ${FONT}`;
            ctx.fillStyle = color;
            ctx.fillText(fitText(ctx, text, canvas.width - 80), 70, canvas.height / 2);
            tex.needsUpdate = true;
        });
    }

    private drawBackdrop() {
        const c = this.backdropCanvas;
        const ctx = this.backdropCtx;
        const W = c.width;
        const H = c.height;

        ctx.clearRect(0, 0, W, H);

        // Draw background media (video frame or static image)
        let mediaDrawn = false;
        if (this.videoElement && !this.videoElement.paused) {
            try {
                ctx.drawImage(this.videoElement, 0, 0, W, H);
                mediaDrawn = true;
            } catch (e) { }
        } else if (this.bgImage && this.bgImage.complete && this.bgImage.naturalWidth > 0) {
            try {
                ctx.drawImage(this.bgImage, 0, 0, W, H);
                mediaDrawn = true;
            } catch (e) { }
        }

        if (mediaDrawn) {
            // Draw a subtle dark overlay so code text remains legible on top
            ctx.fillStyle = 'rgba(4, 12, 20, 0.45)';
            ctx.fillRect(0, 0, W, H);
        } else {
            // Dark frosted base
            const grad = ctx.createLinearGradient(0, 0, 0, H);
            grad.addColorStop(0, 'rgba(4, 12, 20, 0.55)');
            grad.addColorStop(1, 'rgba(2, 6, 12, 0.78)');
            ctx.fillStyle = grad;
            ctx.fillRect(0, 0, W, H);
        }

        // Border glow
        ctx.strokeStyle = 'rgba(0, 243, 255, 0.35)';
        ctx.lineWidth = 4;
        roundRect(ctx, 12, 12, W - 24, H - 24, 24);
        ctx.stroke();

        // Scanlines
        ctx.fillStyle = 'rgba(0, 243, 255, 0.04)';
        for (let y = 0; y < H; y += 4) {
            ctx.fillRect(0, y, W, 1);
        }

        // Headline
        const files = this.data.files_changed || [];
        const fileCount = files.length;
        const totalChanges = files.reduce((s, f) => s + f.changes, 0);
        const headline = fileCount
            ? `XR-IDE // ${fileCount} FILE${fileCount > 1 ? 'S' : ''} CHANGED · ${totalChanges} Δ`
            : 'XR-IDE // AWAITING INSTRUCTIONS';

        ctx.font = `bold 44px ${FONT}`;
        ctx.fillStyle = CYAN;
        ctx.textBaseline = 'top';
        ctx.shadowColor = CYAN;
        ctx.shadowBlur = 16;
        ctx.fillText(headline, 50, 38);
        ctx.shadowBlur = 0;

        // Helper / status line
        ctx.font = `italic 24px ${FONT}`;
        ctx.fillStyle = GREEN;
        const sub = this.data.git_status?.length
            ? `WORKING TREE: ${this.data.git_status.length} MODIFIED`
            : 'WORKING TREE: CLEAN';
        ctx.fillText(sub, 50, 92);

        // Divider
        ctx.strokeStyle = 'rgba(0, 243, 255, 0.25)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(50, 132);
        ctx.lineTo(W - 50, 132);
        ctx.stroke();

        // Left: flowing code preview
        ctx.font = `bold 26px ${FONT}`;
        ctx.fillStyle = CYAN;
        ctx.fillText('LATEST CODE', 50, 158);

        const preview = (this.data.code_preview || '// no active diff').trim();
        ctx.font = `22px 'Fira Code', 'Consolas', monospace`;
        ctx.fillStyle = GREEN;
        const codeLines = preview.split('\n').slice(0, 14);
        let y = 196;
        for (const line of codeLines) {
            const safe = line.replace(/[\x00-\x08\x0b-\x1f]/g, '').slice(0, 70);
            ctx.fillText(safe, 62, y);
            y += 30;
        }

        // Right: recent commands
        const cmdX = W * 0.62;
        ctx.font = `bold 26px ${FONT}`;
        ctx.fillStyle = CYAN;
        ctx.fillText('RECENT VOICE COMMANDS', cmdX, 158);

        const cmds = rinseCommands(this.data.commands || []);
        ctx.font = `24px ${FONT}`;
        y = 196;
        for (const cmd of cmds) {
            ctx.fillStyle = '#ffffff';
            ctx.fillText('›', cmdX, y);
            ctx.fillStyle = GREEN;
            const wrapped = wordWrap(ctx, cmd, W - cmdX - 80, 1);
            ctx.fillText(wrapped[0] || cmd, cmdX + 28, y);
            y += 38;
        }

        // Footer hint
        ctx.font = `20px ${FONT}`;
        ctx.fillStyle = 'rgba(255,255,255,0.5)';
        ctx.fillText('TRIGGER on code to edit · Y to rollback', 50, H - 44);

        this.backdropTex.needsUpdate = true;
    }

    public update(delta: number, camera: THREE.Camera) {
        // If a video is playing, redraw the video frame onto the canvas texture on every frame
        if (this.videoElement && !this.videoElement.paused) {
            this.drawBackdrop();
        }

        // Dynamic Card updates based on live window/dashboard states
        const isDev = !!(window as any).isDevModeActive;
        const isListening = !!(window as any).dashboard?.isListening;
        if (isDev !== this.lastDevModeActive || isListening !== this.lastListeningActive) {
            this.lastDevModeActive = isDev;
            this.lastListeningActive = isListening;
            this.drawCards();
        }

        // Smooth fade
        const mat = this.backdrop?.material as THREE.MeshBasicMaterial;
        if (mat) {
            const diff = this.targetOpacity - mat.opacity;
            if (Math.abs(diff) > 0.01) {
                mat.opacity += diff * Math.min(1, delta * 8);
            } else {
                mat.opacity = this.targetOpacity;
            }
        }
        this.group.visible = mat ? mat.opacity > 0.01 : this.visible;

        if (!this.group.visible) return;

        // Cards fade
        const targetCard = this.visible ? 0.82 : 0;
        for (const { mesh } of this.cardCanvases) {
            const m = mesh.material as THREE.MeshBasicMaterial;
            m.opacity += (targetCard - m.opacity) * Math.min(1, delta * 8);
        }

        // Keep backdrop in front of the user (camera), facing toward the user
        const camPos = new THREE.Vector3();
        const camQuat = new THREE.Quaternion();
        
        try {
            // Extract world position/quaternion directly from matrixWorld to prevent
            // updateWorldMatrix() from overwriting it with stale local matrix values.
            if (camera.matrixWorld) {
                camPos.setFromMatrixPosition(camera.matrixWorld);
                camQuat.setFromRotationMatrix(camera.matrixWorld);
            } else {
                camera.getWorldPosition(camPos);
                camera.getWorldQuaternion(camQuat);
            }
        } catch (err) {
            console.error('[XR-IDE] Error extracting camera position/rotation from matrixWorld in update:', err);
            try {
                camera.getWorldPosition(camPos);
                camera.getWorldQuaternion(camQuat);
            } catch (err2) {
                console.error('[XR-IDE] Fallback getWorldPosition in update failed:', err2);
            }
        }

        // Static positioning for the giant code editor wall, cutting the room back end in the middle
        const staticPos = new THREE.Vector3(0, 1.4, -4.5);
        this.backdrop!.position.copy(staticPos);
        this.backdrop!.lookAt(0, 1.4, 0);

        // Cards follow top of view
        const right = new THREE.Vector3(1, 0, 0).applyQuaternion(camQuat);
        const up = new THREE.Vector3(0, 1, 0);
        const cardCenter = camPos.clone()
            .add(new THREE.Vector3(0, 0, -1).applyQuaternion(camQuat).multiplyScalar(1.2))
            .add(up.clone().multiplyScalar(0.42));
        this.hudCards.forEach((m, i) => {
            const offset = (i - 1.5) * 0.48;
            const target = cardCenter.clone().add(right.clone().multiplyScalar(offset));
            m.position.lerp(target, 0.15);
            m.lookAt(camPos);
            // Hover scale pulse
            const targetScale = (this.hoverTarget === m) ? 1.15 : 1.0;
            const s = m.scale.x + (targetScale - m.scale.x) * Math.min(1, delta * 10);
            m.scale.set(s, s, s);
        });
    }

    public getInteractables(): THREE.Object3D[] {
        return this.rayTargets.filter(o => o.visible !== false);
    }

    public onPointerMove(hit: THREE.Intersection | null) {
        if (!hit) {
            this.hoverTarget = null;
            return;
        }
        this.hoverTarget = hit.object;
    }

    public onPointerSelect(hit: THREE.Intersection) {
        this.hoverTarget = hit.object;
        const target = hit.object;
        if (target.name === 'ide_backdrop') {
            // Click on backdrop opens holographic panel with full code + rollback option
            this.openCodePanel();
        } else if (target.name.startsWith('ide_hud_card_')) {
            const idx = target.userData.index as number;
            if (idx === 1) {
                // Dev mode card
                this.openCodePanel();
            }
        }
    }

    private openCodePanel() {
        // Expose details to the dashboard/holographic panel as a transient event
        (window as any).foveaiIdeOpenEdit = {
            code: this.data.code_preview || '// no diff',
            commands: rinseCommands(this.data.commands || []),
            files: this.data.files_changed || [],
            timestamp: Date.now()
        };
        // Also open the holographic panel and switch to cognition tab if available
        const w = window as any;
        if (typeof w.toggleHolographicPanel === 'function') {
            w.toggleHolographicPanel(true);
        }
        if (w.dashboard?.setActiveTab) {
            w.dashboard.setActiveTab('cognition');
        }
        if (w.dashboard?.log) {
            w.dashboard.log('[XR-IDE] Opened edit panel', 'var(--neon-cyan)');
        }
        const ev = new CustomEvent('xr-ide-open-edit', { detail: (window as any).foveaiIdeOpenEdit });
        window.dispatchEvent(ev);
    }

    public interact(raycaster: THREE.Raycaster, triggerClicked: boolean): boolean {
        if (!this.visible || !this.backdrop) return false;
        const hits = raycaster.intersectObjects(this.rayTargets, false);
        if (hits.length === 0) {
            this.hoverTarget = null;
            return false;
        }
        const hit = hits[0];
        this.hoverTarget = hit.object;
        if (triggerClicked) {
            this.onPointerSelect(hit);
            return true;
        }
        return true;
    }
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
    const rr = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + rr, y);
    ctx.lineTo(x + w - rr, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + rr);
    ctx.lineTo(x + w, y + h - rr);
    ctx.quadraticCurveTo(x + w, y + h, x + w - rr, y + h);
    ctx.lineTo(x + rr, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - rr);
    ctx.lineTo(x, y + rr);
    ctx.quadraticCurveTo(x, y, x + rr, y);
    ctx.closePath();
}
