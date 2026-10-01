// AvatarCamerasTab.ts — Avatar/User Cameras Management Panel
// Controls avatar POV camera, user webcam, passthrough, and snapshot capture

export class AvatarCamerasTab {
    private static streamActive = false;
    private static mediaStream: MediaStream | null = null;

    public static render(container: HTMLElement) {
        container.innerHTML = `
            <div class="breadcrumb">CAMERAS // AVATAR_POV + USER_VIEW</div>
            <div style="background:rgba(0,0,0,0.4); padding:20px; border:1px solid var(--border); border-radius:4px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:15px;">
                    <h4 style="font-family:'Orbitron'; margin:0; font-size:0.9rem; color:var(--neon-blue); letter-spacing:2px;">CAMERA FEEDS</h4>
                    <span id="cameras-status" style="font-size:0.7rem; color:var(--neon-green); font-family:'Share Tech Mono';">STANDBY</span>
                </div>

                <!-- Avatar POV Camera -->
                <div style="background:rgba(0,243,255,0.08); border:1px solid var(--neon-blue); border-radius:4px; padding:12px; margin-bottom:15px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">AVATAR POV</h5>
                    <div style="display:flex; gap:10px; align-items:flex-start;">
                        <div id="avatar-pov-preview" style="width:160px; height:120px; background:rgba(0,0,0,0.5); border:1px solid var(--border); border-radius:3px; display:flex; align-items:center; justify-content:center; font-size:0.6rem; color:#555; font-family:'Share Tech Mono';">
                            NO FEED
                        </div>
                        <div style="flex:1;">
                            <div style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#aaa; line-height:1.6;">
                                <div>Status: <span id="avatar-cam-status" style="color:#888;">Inactive</span></div>
                                <div>Resolution: <span id="avatar-cam-res">—</span></div>
                                <div>FPS: <span id="avatar-cam-fps">—</span></div>
                            </div>
                            <div style="display:flex; gap:6px; margin-top:8px;">
                                <button id="btn-avatar-snapshot" style="background:rgba(0,243,255,0.15); border:1px solid var(--neon-blue); color:var(--neon-blue); padding:4px 10px; border-radius:3px; cursor:pointer; font-family:'Orbitron'; font-size:0.6rem; letter-spacing:1px;">📸 CAPTURE</button>
                                <button id="btn-avatar-toggle-vision" style="background:rgba(57,255,20,0.1); border:1px solid #39ff14; color:#39ff14; padding:4px 10px; border-radius:3px; cursor:pointer; font-family:'Orbitron'; font-size:0.6rem; letter-spacing:1px;">👁️ VISION ON</button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- User Webcam -->
                <div style="background:rgba(57,255,20,0.05); border:1px solid #39ff14; border-radius:4px; padding:12px; margin-bottom:15px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:#39ff14; letter-spacing:1px;">USER WEBCAM</h5>
                    <div style="display:flex; gap:10px; align-items:flex-start;">
                        <div id="user-webcam-preview" style="width:160px; height:120px; background:rgba(0,0,0,0.5); border:1px solid var(--border); border-radius:3px; display:flex; align-items:center; justify-content:center; font-size:0.6rem; color:#555; font-family:'Share Tech Mono';">
                            NO FEED
                        </div>
                        <div style="flex:1;">
                            <div style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#aaa; line-height:1.6;">
                                <div>Status: <span id="user-cam-status" style="color:#888;">Inactive</span></div>
                                <div>Device: <span id="user-cam-device">—</span></div>
                                <div>Resolution: <span id="user-cam-res">—</span></div>
                            </div>
                            <div style="display:flex; gap:6px; margin-top:8px;">
                                <button id="btn-user-snapshot" style="background:rgba(57,255,20,0.15); border:1px solid #39ff14; color:#39ff14; padding:4px 10px; border-radius:3px; cursor:pointer; font-family:'Orbitron'; font-size:0.6rem; letter-spacing:1px;">📸 CAPTURE</button>
                                <button id="btn-toggle-webcam" style="background:rgba(255,255,0,0.1); border:1px solid #ff0; color:#ff0; padding:4px 10px; border-radius:3px; cursor:pointer; font-family:'Orbitron'; font-size:0.6rem; letter-spacing:1px;">📹 START</button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Quest Passthrough -->
                <div style="background:rgba(255,0,127,0.05); border:1px solid var(--neon-pink); border-radius:4px; padding:12px; margin-bottom:15px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">QUEST PASSTHROUGH</h5>
                    <div style="display:flex; gap:10px; align-items:flex-start;">
                        <div id="passthrough-preview" style="width:160px; height:120px; background:rgba(0,0,0,0.5); border:1px solid var(--border); border-radius:3px; display:flex; align-items:center; justify-content:center; font-size:0.6rem; color:#555; font-family:'Share Tech Mono';">
                            NO FEED
                        </div>
                        <div style="flex:1;">
                            <div style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#aaa; line-height:1.6;">
                                <div>Status: <span id="passthrough-status" style="color:#888;">Not in XR</span></div>
                                <div>Mode: <span id="passthrough-mode">—</span></div>
                            </div>
                            <div style="display:flex; gap:6px; margin-top:8px;">
                                <button id="btn-passthrough-snapshot" style="background:rgba(255,0,127,0.15); border:1px solid var(--neon-pink); color:var(--neon-pink); padding:4px 10px; border-radius:3px; cursor:pointer; font-family:'Orbitron'; font-size:0.6rem; letter-spacing:1px;">📸 CAPTURE</button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Composite Vision Status -->
                <div style="background:rgba(0,0,0,0.3); border:1px solid var(--border); border-radius:4px; padding:12px;">
                    <h5 style="font-family:'Orbitron'; margin:0 0 8px 0; font-size:0.7rem; color:var(--neon-pink); letter-spacing:1px;">COMPOSITE VISION</h5>
                    <div id="composite-status" style="font-family:'Share Tech Mono'; font-size:0.7rem; color:#aaa; line-height:1.6;">
                        <div>Layers: <span id="composite-layers">—</span></div>
                        <div>Stencil: <span id="composite-stencil">—</span></div>
                        <div>Last Composite: <span id="composite-last">—</span></div>
                    </div>
                </div>
            </div>
        `;
        this.setupInteractions(container);
        this.refreshStatus();
    }

    private static setupInteractions(container: HTMLElement) {
        container.querySelector('#btn-avatar-snapshot')?.addEventListener('click', () => this.captureAvatarSnapshot());
        container.querySelector('#btn-avatar-toggle-vision')?.addEventListener('click', () => this.toggleAvatarVision());
        container.querySelector('#btn-user-snapshot')?.addEventListener('click', () => this.captureUserSnapshot());
        container.querySelector('#btn-toggle-webcam')?.addEventListener('click', () => this.toggleWebcam());
        container.querySelector('#btn-passthrough-snapshot')?.addEventListener('click', () => this.capturePassthroughSnapshot());
    }

    private static async captureAvatarSnapshot() {
        try {
            window.dispatchEvent(new CustomEvent('foveai_voice_snapshot', { detail: { text: 'avatar' } }));
            const statusEl = document.getElementById('cameras-status');
            if (statusEl) {
                statusEl.textContent = 'SNAPSHOT SENT';
                statusEl.style.color = 'var(--neon-green)';
                setTimeout(() => {
                    statusEl.textContent = 'STANDBY';
                    statusEl.style.color = '#888';
                }, 2000);
            }
        } catch (err) {
            console.error('[Cameras] Avatar snapshot failed:', err);
        }
    }

    private static async captureUserSnapshot() {
        try {
            window.dispatchEvent(new CustomEvent('foveai_voice_snapshot', { detail: { text: 'user snapshot' } }));
            const statusEl = document.getElementById('cameras-status');
            if (statusEl) {
                statusEl.textContent = 'USER SNAPSHOT SENT';
                statusEl.style.color = '#39ff14';
                setTimeout(() => {
                    statusEl.textContent = 'STANDBY';
                    statusEl.style.color = '#888';
                }, 2000);
            }
        } catch (err) {
            console.error('[Cameras] User snapshot failed:', err);
        }
    }

    private static async capturePassthroughSnapshot() {
        try {
            window.dispatchEvent(new CustomEvent('foveai_voice_snapshot', { detail: { text: 'passthrough' } }));
            const statusEl = document.getElementById('cameras-status');
            if (statusEl) {
                statusEl.textContent = 'PASSTHROUGH SENT';
                statusEl.style.color = 'var(--neon-pink)';
                setTimeout(() => {
                    statusEl.textContent = 'STANDBY';
                    statusEl.style.color = '#888';
                }, 2000);
            }
        } catch (err) {
            console.error('[Cameras] Passthrough snapshot failed:', err);
        }
    }

    private static async toggleAvatarVision() {
        const btn = document.getElementById('btn-avatar-toggle-vision');
        const statusEl = document.getElementById('avatar-cam-status');
        if (!btn || !statusEl) return;

        const isActive = btn.textContent?.includes('ON');
        if (isActive) {
            // Disable vision
            btn.textContent = '👁️ VISION ON';
            btn.style.borderColor = '#39ff14';
            btn.style.color = '#39ff14';
            statusEl.textContent = 'Inactive';
            statusEl.style.color = '#888';
        } else {
            // Enable vision
            btn.textContent = '👁️ VISION OFF';
            btn.style.borderColor = 'var(--neon-pink)';
            btn.style.color = 'var(--neon-pink)';
            statusEl.textContent = 'Active';
            statusEl.style.color = 'var(--neon-green)';
        }
    }

    private static async toggleWebcam() {
        const btn = document.getElementById('btn-toggle-webcam');
        const preview = document.getElementById('user-webcam-preview');
        const statusEl = document.getElementById('user-cam-status');
        if (!btn || !preview || !statusEl) return;

        if (this.streamActive) {
            // Stop webcam
            if (this.mediaStream) {
                this.mediaStream.getTracks().forEach(t => t.stop());
                this.mediaStream = null;
            }
            this.streamActive = false;
            btn.textContent = '📹 START';
            btn.style.borderColor = '#ff0';
            btn.style.color = '#ff0';
            preview.innerHTML = 'NO FEED';
            statusEl.textContent = 'Inactive';
            statusEl.style.color = '#888';
        } else {
            // Start webcam
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ video: true });
                this.mediaStream = stream;
                this.streamActive = true;

                const video = document.createElement('video');
                video.srcObject = stream;
                video.autoplay = true;
                video.muted = true;
                video.style.width = '100%';
                video.style.height = '100%';
                video.style.objectFit = 'cover';
                preview.innerHTML = '';
                preview.appendChild(video);

                btn.textContent = '📹 STOP';
                btn.style.borderColor = 'var(--neon-pink)';
                btn.style.color = 'var(--neon-pink)';
                statusEl.textContent = 'Active';
                statusEl.style.color = '#39ff14';

                const track = stream.getVideoTracks()[0];
                const settings = track.getSettings();
                const devEl = document.getElementById('user-cam-device');
                const resEl = document.getElementById('user-cam-res');
                if (devEl) devEl.textContent = track.label || 'Unknown';
                if (resEl) resEl.textContent = `${settings.width || '?'}×${settings.height || '?'}`;
            } catch (err) {
                console.error('[Cameras] Webcam start failed:', err);
                statusEl.textContent = 'Error';
                statusEl.style.color = 'var(--neon-pink)';
            }
        }
    }

    private static async refreshStatus() {
        try {
            const resp = await fetch('/api/vision/status');
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();

            const setText = (id: string, val: string) => {
                const el = document.getElementById(id);
                if (el) el.textContent = val;
            };

            setText('avatar-cam-res', data.avatarResolution || '—');
            setText('avatar-cam-fps', String(data.avatarFps || '—'));
            setText('composite-layers', (data.layers || []).join(', ') || '—');
            setText('composite-stencil', data.stencilLevel || '—');
            setText('composite-last', data.lastComposite || '—');

            const passthroughEl = document.getElementById('passthrough-status');
            if (passthroughEl) {
                const xrActive = !!(window as any).env?.renderer?.xr?.isPresenting;
                passthroughEl.textContent = xrActive ? 'Active (XR)' : 'Not in XR';
                passthroughEl.style.color = xrActive ? 'var(--neon-green)' : '#888';
            }
        } catch (err) {
            console.debug('[Cameras] Status refresh failed:', err);
        }
    }
}