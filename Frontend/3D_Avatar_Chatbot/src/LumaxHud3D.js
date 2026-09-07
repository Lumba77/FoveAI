/**
 * ═══════════════════════════════════════════════════════════════════════
 * FoveAI 3D HUD — Ported from XR_Vessel XrIdeHud.ts
 * ═══════════════════════════════════════════════════════════════════════
 *
 * A 3D Canvas-based in-game HUD that provides:
 *   - Developer IDE overlay (code editing wall)
 *   - Media wall (video streaming, images)
 *   - Status cards (system vitals, telemetry)
 *   - Interactive buttons and panels
 *
 * PORTED FROM: Frontend/XR_Vessel/src/ui/XrIdeHud.ts
 * The original was a TypeScript Three.js class with canvas-based rendering.
 * This JavaScript version adapts it for the 3D_Avatar_Chatbot's ViewerEngine.
 *
 * ═══════════════════════════════════════════════════════════════════════
 */

(function () {
    'use strict';

    const CYAN = '#00f3ff';
    const PINK = '#ff007f';
    const GREEN = '#39ff14';
    const ORANGE = '#ffaa00';
    const BG = 'rgba(4, 8, 16, 0.62)';
    const FONT = "'Orbitron', 'Segoe UI', monospace";

    /**
     * Fit text to a maximum width by reducing font size.
     */
    function fitText(ctx, text, maxWidth) {
        let low = 1, high = text.length, best = text.slice(0, 1);
        while (low <= high) {
            const mid = Math.floor((low + high) / 2);
            const candidate = text.slice(0, mid);
            const w = ctx.measureText(candidate).width;
            if (w <= maxWidth) {
                best = candidate;
                low = mid + 1;
            } else {
                high = mid - 1;
            }
        }
        return best;
    }

    /**
     * Word-wrap text to fit within a maximum width.
     */
    function wordWrap(ctx, text, maxWidth, maxLines) {
        const out = [];
        const lines = text.split('\n');
        for (const raw of lines) {
            let words = raw.split(' ');
            let line = '';
            for (const word of words) {
                const test = line ? line + ' ' + word : word;
                if (ctx.measureText(test).width > maxWidth && line) {
                    out.push(line);
                    if (maxLines && out.length >= maxLines) return out;
                    line = word;
                } else {
                    line = test;
                }
            }
            if (line) {
                out.push(line);
                if (maxLines && out.length >= maxLines) return out;
            }
        }
        return out;
    }

    /**
     * Draw a rounded rectangle on a canvas context.
     */
    function roundRect(ctx, x, y, w, h, r) {
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

    /**
     * LumaxHud3D — 3D Canvas-based HUD for the 3D_Avatar_Chatbot.
     */
    class LumaxHud3D {
        constructor() {
            this.visible = false;
            this.scene = null;
            this.camera = null;
            this.cardCanvases = [];
            this.backdropMesh = null;
            this.backdropCanvas = null;
            this.backdropCtx = null;
            this.backdropTexture = null;
            this.videoElement = null;
            this.videoTexture = null;
            this.data = {
                status: 'idle',
                files_changed: [],
                recent_commands: [],
                system_vitals: { cpu: 0, gpu: 0, ram: 0, fps: 0 },
                motor_state: 'idle',
                emotion: 'neutral',
                behavior: 'calm_idle'
            };
            this.interactables = [];
            this._hoveredIndex = -1;
            this._animTime = 0;

            // Expose globally
            window.FoveAI_HUD_3D = this;
            console.log('[LumaxHud3D] Created');
        }

        /**
         * Build the 3D HUD in the given scene.
         * @param {THREE.Scene} scene
         * @param {THREE.Camera} camera
         */
        build(scene, camera) {
            this.scene = scene;
            this.camera = camera;
            this._animTime = 0;

            // Create backdrop wall
            this._createBackdrop();

            // Create status cards
            this._createCards();

            // Listen for data updates
            this._setupEventListeners();

            console.log('[LumaxHud3D] Built in scene');
        }

        /**
         * Create the main backdrop wall (code editor / media wall).
         */
        _createBackdrop() {
            const canvas = document.createElement('canvas');
            canvas.width = 1024;
            canvas.height = 768;
            this.backdropCanvas = canvas;
            this.backdropCtx = canvas.getContext('2d');

            this.backdropTexture = new THREE.CanvasTexture(canvas);
            this.backdropTexture.minFilter = THREE.LinearFilter;
            this.backdropTexture.magFilter = THREE.LinearFilter;

            const geometry = new THREE.PlaneGeometry(4, 3);
            const material = new THREE.MeshBasicMaterial({
                map: this.backdropTexture,
                transparent: true,
                opacity: 0.85,
                side: THREE.DoubleSide
            });
            this.backdropMesh = new THREE.Mesh(geometry, material);
            this.backdropMesh.position.set(0, 1.4, -4.5);
            this.backdropMesh.visible = this.visible;

            this.scene.add(this.backdropMesh);
            this._drawBackdrop();
        }

        /**
         * Create the status cards (small HUD cards).
         */
        _createCards() {
            const cardDefs = [
                { label: 'STATUS', width: 240, height: 80, color: CYAN },
                { label: 'MOTOR', width: 240, height: 80, color: GREEN },
                { label: 'EMOTION', width: 240, height: 80, color: PINK },
                { label: 'VITALS', width: 240, height: 80, color: ORANGE }
            ];

            const startX = -3.6;
            const startY = 2.6;
            const spacing = 0.3;

            this.cardCanvases = cardDefs.map((def, i) => {
                const canvas = document.createElement('canvas');
                canvas.width = def.width;
                canvas.height = def.height;
                const ctx = canvas.getContext('2d');

                const texture = new THREE.CanvasTexture(canvas);
                texture.minFilter = THREE.LinearFilter;
                texture.magFilter = THREE.LinearFilter;

                const aspect = def.width / def.height;
                const geo = new THREE.PlaneGeometry(0.8 * aspect, 0.8);
                const mat = new THREE.MeshBasicMaterial({
                    map: texture,
                    transparent: true,
                    opacity: 0.9,
                    side: THREE.DoubleSide
                });
                const mesh = new THREE.Mesh(geo, mat);
                mesh.position.set(
                    startX + i * (0.8 * aspect + spacing),
                    startY,
                    -4.0
                );
                mesh.userData.cardIndex = i;
                mesh.userData.isHudCard = true;
                mesh.visible = this.visible;

                this.scene.add(mesh);
                this.interactables.push(mesh);

                // Draw initial content
                this._drawCard(canvas, ctx, def.label, def.color, '');

                return { canvas, ctx, texture, mesh, def };
            });
        }

        /**
         * Draw a single status card.
         */
        _drawCard(canvas, ctx, label, color, value) {
            const w = canvas.width;
            const h = canvas.height;

            // Background
            ctx.clearRect(0, 0, w, h);
            roundRect(ctx, 0, 0, w, h, 12);
            ctx.fillStyle = BG;
            ctx.fill();

            // Border
            roundRect(ctx, 0, 0, w, h, 12);
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.stroke();

            // Label
            ctx.fillStyle = color;
            ctx.font = 'bold 14px ' + FONT;
            ctx.textAlign = 'left';
            ctx.textBaseline = 'top';
            ctx.fillText(label, 12, 10);

            // Value
            ctx.fillStyle = '#ffffff';
            ctx.font = '12px ' + FONT;
            ctx.textAlign = 'left';
            ctx.textBaseline = 'bottom';
            const lines = wordWrap(ctx, value || '--', w - 24, 2);
            lines.forEach((line, i) => {
                ctx.fillText(line, 12, h - 10 - i * 16);
            });

            // Update texture
            if (canvas.__texture) {
                canvas.__texture.needsUpdate = true;
            }
        }

        /**
         * Draw the main backdrop content.
         */
        _drawBackdrop() {
            const ctx = this.backdropCtx;
            const w = this.backdropCanvas.width;
            const h = this.backdropCanvas.height;

            // Background
            ctx.clearRect(0, 0, w, h);
            const gradient = ctx.createLinearGradient(0, 0, 0, h);
            gradient.addColorStop(0, 'rgba(4, 8, 16, 0.85)');
            gradient.addColorStop(1, 'rgba(4, 8, 16, 0.95)');
            ctx.fillStyle = gradient;
            roundRect(ctx, 0, 0, w, h, 20);
            ctx.fill();

            // Border
            ctx.strokeStyle = CYAN;
            ctx.lineWidth = 2;
            roundRect(ctx, 0, 0, w, h, 20);
            ctx.stroke();

            // Title
            ctx.fillStyle = CYAN;
            ctx.font = 'bold 24px ' + FONT;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            ctx.fillText('FoveAI IDE', w / 2, 20);

            // Status
            const status = this.data.status || 'idle';
            ctx.fillStyle = status === 'active' ? GREEN : '#888';
            ctx.font = '14px ' + FONT;
            ctx.fillText(`Status: ${status.toUpperCase()}`, w / 2, 60);

            // Recent commands
            const commands = this.data.recent_commands || [];
            ctx.fillStyle = '#aaa';
            ctx.font = '12px ' + FONT;
            ctx.textAlign = 'left';
            ctx.fillText('Recent Commands:', 20, 100);
            commands.slice(-5).forEach((cmd, i) => {
                ctx.fillStyle = CYAN;
                ctx.fillText(`> ${cmd}`, 20, 125 + i * 20);
            });

            // System vitals
            const vitals = this.data.system_vitals || {};
            ctx.textAlign = 'right';
            ctx.fillStyle = ORANGE;
            ctx.font = '12px ' + FONT;
            ctx.fillText(`CPU: ${(vitals.cpu || 0).toFixed(1)}%`, w - 20, 100);
            ctx.fillStyle = PINK;
            ctx.fillText(`GPU: ${(vitals.gpu || 0).toFixed(1)}%`, w - 20, 120);
            ctx.fillStyle = CYAN;
            ctx.fillText(`RAM: ${(vitals.ram || 0).toFixed(1)}%`, w - 20, 140);
            ctx.fillStyle = GREEN;
            ctx.fillText(`FPS: ${(vitals.fps || 0).toFixed(0)}`, w - 20, 160);

            // Motor state
            ctx.textAlign = 'left';
            ctx.fillStyle = GREEN;
            ctx.font = '12px ' + FONT;
            ctx.fillText(`Motor: ${this.data.motor_state || 'idle'}`, 20, h - 40);

            // Emotion
            ctx.fillStyle = PINK;
            ctx.fillText(`Emotion: ${this.data.emotion || 'neutral'}`, 20, h - 20);

            // Behavior
            ctx.textAlign = 'right';
            ctx.fillStyle = CYAN;
            ctx.fillText(`Behavior: ${this.data.behavior || 'calm_idle'}`, w - 20, h - 20);

            if (this.backdropTexture) {
                this.backdropTexture.needsUpdate = true;
            }
        }

        /**
         * Set up event listeners for data updates.
         */
        _setupEventListeners() {
            // Listen for integration layer state changes
            window.addEventListener('foveai_state_changed', (e) => {
                this.data.behavior = e.detail?.to || 'calm_idle';
                this._updateDisplay();
            });

            window.addEventListener('foveai_emotion_changed', (e) => {
                this.data.emotion = e.detail?.emotion || 'neutral';
                this._updateDisplay();
            });

            window.addEventListener('foveai_body_feedback', (e) => {
                const type = e.detail?.type || 'unknown';
                this.data.recent_commands.push(type);
                if (this.data.recent_commands.length > 20) {
                    this.data.recent_commands.shift();
                }
                this._updateDisplay();
            });

            // Listen for motor state from bridge
            window.addEventListener('motor_state_update', (e) => {
                this.data.motor_state = e.detail?.state || 'idle';
                this._updateDisplay();
            });

            // Listen for system vitals
            window.addEventListener('foveai_vitals_update', (e) => {
                if (e.detail) {
                    Object.assign(this.data.system_vitals, e.detail);
                }
                this._updateDisplay();
            });
        }

        /**
         * Update the HUD display.
         */
        _updateDisplay() {
            if (!this.visible) return;

            // Update backdrop
            this._drawBackdrop();

            // Update cards
            const cardValues = [
                `State: ${this.data.status}\nCmds: ${(this.data.recent_commands || []).length}`,
                `State: ${this.data.motor_state}\nMoving: ${window.FoveAI_INTEGRATION?.isMoving() ? 'YES' : 'NO'}`,
                `${this.data.emotion}\nIntensity: ${window.FoveAI_INTEGRATION?.emotionIntensity?.toFixed(1) || '0.5'}`,
                `CPU: ${(this.data.system_vitals.cpu || 0).toFixed(0)}%\nFPS: ${(this.data.system_vitals.fps || 0).toFixed(0)}`
            ];

            this.cardCanvases.forEach((card, i) => {
                this._drawCard(
                    card.canvas, card.ctx,
                    card.def.label, card.def.color,
                    cardValues[i] || '--'
                );
                card.texture.needsUpdate = true;
            });
        }

        /**
         * Set the HUD visibility.
         * @param {boolean} visible
         */
        setVisible(visible) {
            this.visible = visible;
            if (this.backdropMesh) {
                this.backdropMesh.visible = visible;
            }
            this.cardCanvases.forEach(c => {
                c.mesh.visible = visible;
            });
            if (visible) {
                this._updateDisplay();
            }
        }

        /**
         * Toggle HUD visibility.
         */
        toggle() {
            this.setVisible(!this.visible);
        }

        /**
         * Check if HUD is visible.
         * @returns {boolean}
         */
        isVisible() {
            return this.visible;
        }

        /**
         * Set the data payload for the HUD.
         * @param {Object} data
         */
        setData(data) {
            if (data.status) this.data.status = data.status;
            if (data.files_changed) this.data.files_changed = data.files_changed;
            if (data.recent_commands) this.data.recent_commands = data.recent_commands;
            if (data.system_vitals) Object.assign(this.data.system_vitals, data.system_vitals);
            if (data.motor_state) this.data.motor_state = data.motor_state;
            if (data.emotion) this.data.emotion = data.emotion;
            if (data.behavior) this.data.behavior = data.behavior;
            this._updateDisplay();
        }

        /**
         * Play a video on the backdrop wall.
         * @param {string} url - Video URL
         */
        playVideo(url) {
            if (!this.backdropMesh) return;

            // Stop existing video
            this.stopVideo();

            const video = document.createElement('video');
            video.src = url;
            video.crossOrigin = 'anonymous';
            video.loop = true;
            video.muted = true;
            video.playsInline = true;
            video.play().catch(() => {});

            this.videoElement = video;
            this.videoTexture = new THREE.VideoTexture(video);
            this.videoTexture.minFilter = THREE.LinearFilter;
            this.videoTexture.magFilter = THREE.LinearFilter;

            this.backdropMesh.material.map = this.videoTexture;
            this.backdropMesh.material.needsUpdate = true;

            console.log('[LumaxHud3D] Playing video:', url);
        }

        /**
         * Stop video playback on the backdrop wall.
         */
        stopVideo() {
            if (this.videoElement) {
                this.videoElement.pause();
                this.videoElement.src = '';
                this.videoElement.load();
                this.videoElement = null;
            }
            if (this.videoTexture) {
                this.videoTexture.dispose();
                this.videoTexture = null;
            }
            // Restore canvas texture
            if (this.backdropMesh && this.backdropTexture) {
                this.backdropMesh.material.map = this.backdropTexture;
                this.backdropMesh.material.needsUpdate = true;
                this._drawBackdrop();
            }
        }

        /**
         * Update the HUD (called from animation loop).
         * @param {number} delta - Time delta in seconds
         * @param {THREE.Camera} camera - Active camera
         */
        update(delta, camera) {
            if (!this.visible) return;
            this._animTime += delta;

            // Update video texture if playing
            if (this.videoTexture && this.videoElement) {
                this.videoTexture.needsUpdate = true;
            }

            // Update card positions to face camera (gaze-locked)
            if (camera) {
                this.cardCanvases.forEach(c => {
                    c.mesh.lookAt(camera.position);
                });
            }

            // Subtle pulse animation on backdrop border
            if (this.backdropMesh && this.backdropMesh.material) {
                const pulse = 0.85 + Math.sin(this._animTime * 0.5) * 0.1;
                this.backdropMesh.material.opacity = pulse;
            }
        }

        /**
         * Get interactable meshes for raycasting.
         * @returns {THREE.Mesh[]}
         */
        getInteractables() {
            return this.interactables;
        }

        /**
         * Handle pointer move on HUD.
         * @param {THREE.Intersection|null} hit
         */
        onPointerMove(hit) {
            if (!hit) {
                if (this._hoveredIndex >= 0) {
                    const prev = this.interactables[this._hoveredIndex];
                    if (prev) prev.material.color.setHex(0xffffff);
                    this._hoveredIndex = -1;
                }
                return;
            }
            const idx = this.interactables.indexOf(hit.object);
            if (idx >= 0 && idx !== this._hoveredIndex) {
                if (this._hoveredIndex >= 0) {
                    const prev = this.interactables[this._hoveredIndex];
                    if (prev) prev.material.color.setHex(0xffffff);
                }
                hit.object.material.color.setHex(0x00f3ff);
                this._hoveredIndex = idx;
            }
        }

        /**
         * Handle pointer select on HUD.
         * @param {THREE.Intersection} hit
         */
        onPointerSelect(hit) {
            const idx = this.interactables.indexOf(hit.object);
            if (idx >= 0) {
                const card = this.cardCanvases[idx];
                if (card) {
                    console.log(`[LumaxHud3D] Card selected: ${card.def.label}`);
                    // Toggle HUD visibility on card click
                    this.toggle();
                }
            }
        }

        /**
         * Clean up and dispose.
         */
        dispose() {
            this.stopVideo();
            if (this.backdropMesh) {
                this.scene.remove(this.backdropMesh);
                this.backdropMesh.material.dispose();
                this.backdropMesh.geometry.dispose();
            }
            this.cardCanvases.forEach(c => {
                this.scene.remove(c.mesh);
                c.mesh.material.dispose();
                c.mesh.geometry.dispose();
            });
            this.cardCanvases = [];
            this.interactables = [];
            console.log('[LumaxHud3D] Disposed');
        }
    }

    // ─── Export ──────────────────────────────────────────────────────
    window.LumaxHud3D = LumaxHud3D;
})();