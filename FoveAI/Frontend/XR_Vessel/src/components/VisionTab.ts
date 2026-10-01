export class VisionTab {
    public static render(container: HTMLElement) {
        container.innerHTML = `
            <div class="breadcrumb">VESSEL_SENSES // SPECTRAL_VIEW</div>
            
            <div style="flex: 1; display: flex; flex-direction: column; gap: 20px; min-height: 0; overflow-y: auto; padding-right: 10px;">
                <div class="glass-card" style="padding: 20px;">
                    <h4 style="font-family: 'Orbitron'; font-size: 0.8rem; color: var(--neon-blue); margin: 0 0 15px 0;">MULTIMODAL SENSORS</h4>
                    <p style="font-size: 0.7rem; opacity: 0.6; margin-bottom: 20px; line-height: 1.4;">
                        Status of multimodal vision (GGUF mmproj) and real-time environment parsing.
                    </p>

                    <div id="vision-status-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 15px;">
                        <div class="vision-metric">
                            <span class="v-label">VISION_ACTIVE</span>
                            <span id="v-active" class="v-value">OFFLINE</span>
                        </div>
                        <div class="vision-metric">
                            <span class="v-label">MMPROJ_LOADED</span>
                            <span id="v-mmproj" class="v-value">NO</span>
                        </div>
                        <div class="vision-metric">
                            <span class="v-label">LAST_GAZE_EVENT</span>
                            <span id="v-gaze" class="v-value">--</span>
                        </div>
                    </div>
                <div class="glass-card" style="padding: 20px;">
                    <h4 style="font-family: 'Orbitron'; font-size: 0.8rem; color: var(--neon-blue); margin: 0 0 15px 0;">SPATIAL ROOM SCANNER</h4>
                    <p style="font-size: 0.7rem; opacity: 0.6; margin-bottom: 20px; line-height: 1.4;">
                        Guides environmental mapping to plaster the virtual space with camera textures.
                    </p>
                    
                    <div style="display: flex; gap: 15px; align-items: center; margin-bottom: 15px;">
                        <div style="flex: 1;">
                            <div style="font-size: 0.6rem; opacity: 0.5; font-family: 'Orbitron'; margin-bottom: 5px;">MAPPING_COVERAGE</div>
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <div style="flex: 1; height: 8px; background: rgba(255,255,255,0.05); border: 1px solid var(--border); border-radius: 4px; overflow: hidden;">
                                    <div id="scan-progress-bar" style="width: 0%; height: 100%; background: var(--neon-green); transition: width 0.3s ease;"></div>
                                </div>
                                <span id="scan-coverage-text" style="font-family: 'Share Tech Mono'; font-size: 0.8rem; color: var(--neon-green);">0%</span>
                            </div>
                        </div>
                    </div>

                    <div id="scan-hint-box" style="padding: 10px; background: rgba(0,243,255,0.02); border: 1px solid var(--border); font-family: 'Share Tech Mono'; font-size: 0.75rem; color: rgba(255,255,255,0.85); margin-bottom: 15px;">
                        Scanner Offline
                    </div>

                    <div style="display: flex; gap: 10px;">
                        <button id="btn-start-scan" style="flex: 1; padding: 8px; font-family: 'Orbitron'; font-size: 0.65rem; border: 1px solid var(--neon-green); background: rgba(57,255,20,0.1); color: var(--neon-green); border-radius: 4px; cursor: pointer; text-shadow: 0 0 3px var(--neon-green);">🔍 START SCAN</button>
                        <button id="btn-stop-scan" style="flex: 1; padding: 8px; font-family: 'Orbitron'; font-size: 0.65rem; border: 1px solid var(--neon-pink); background: rgba(255,0,136,0.1); color: var(--neon-pink); border-radius: 4px; cursor: pointer; text-shadow: 0 0 3px var(--neon-pink);">⏹️ STOP SCAN</button>
                        <button id="btn-reset-scan" style="padding: 8px; font-family: 'Orbitron'; font-size: 0.65rem; border: 1px solid var(--neon-orange); background: rgba(255,170,0,0.1); color: var(--neon-orange); border-radius: 4px; cursor: pointer;">🗑️ RESET</button>
                    </div>
                </div>

                <div class="glass-card" style="flex: 1; display: flex; flex-direction: column; padding: 0; overflow: hidden;">
                    <div style="padding: 10px 20px; background: rgba(0,243,255,0.05); border: 1px solid var(--border); font-family: 'Orbitron'; font-size: 0.7rem; letter-spacing: 1px;">
                        ENVIRONMENT_DESCRIPTION
                    </div>
                    <div id="v-description" style="flex: 1; padding: 20px; font-family: 'Share Tech Mono'; font-size: 0.8rem; color: rgba(255,255,255,0.8); line-height: 1.6;">
                        Awaiting visual prompt or gaze trigger...
                    </div>
                </div>
            </div>

            <style>
                .vision-metric {
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid var(--border);
                    padding: 12px;
                    border-radius: 4px;
                    display: flex;
                    flex-direction: column;
                    gap: 5px;
                }
                .v-label {
                    font-size: 0.55rem;
                    opacity: 0.5;
                    font-family: 'Orbitron';
                }
                .v-value {
                    font-size: 0.9rem;
                    font-family: 'Share Tech Mono';
                    color: var(--neon-blue);
                }
                .v-value.active {
                    color: var(--neon-green);
                    text-shadow: 0 0 5px var(--neon-green);
                }
            </style>
        `;

        this.startPolling(container);
    }

    private static startPolling(container: HTMLElement) {
        const vActive = container.querySelector('#v-active');
        const vMmproj = container.querySelector('#v-mmproj');
        const vGaze = container.querySelector('#v-gaze');
        const vDesc = container.querySelector('#v-description');

        const updateScannerUI = () => {
            const scanner = (window as any).roomScanner;
            const btnStart = container.querySelector('#btn-start-scan') as HTMLElement;
            const btnStop = container.querySelector('#btn-stop-scan') as HTMLElement;
            const btnReset = container.querySelector('#btn-reset-scan') as HTMLElement;
            const progressBar = container.querySelector('#scan-progress-bar') as HTMLElement;
            const coverageText = container.querySelector('#scan-coverage-text') as HTMLElement;
            const hintBox = container.querySelector('#scan-hint-box') as HTMLElement;

            if (scanner) {
                const session = scanner.getSession();
                if (progressBar) progressBar.style.width = `${session.overallCoverage}%`;
                if (coverageText) coverageText.textContent = `${session.overallCoverage}%`;
                if (hintBox) {
                    hintBox.textContent = scanner.isScanning() ? session.coachingText : 'Scanner Offline';
                }

                if (btnStart && !btnStart.dataset.wired) {
                    btnStart.dataset.wired = 'true';
                    btnStart.onclick = () => {
                        scanner.start();
                        updateScannerUI();
                    };
                }
                if (btnStop && !btnStop.dataset.wired) {
                    btnStop.dataset.wired = 'true';
                    btnStop.onclick = () => {
                        scanner.stop();
                        updateScannerUI();
                    };
                }
                if (btnReset && !btnReset.dataset.wired) {
                    btnReset.dataset.wired = 'true';
                    btnReset.onclick = () => {
                        scanner.reset();
                        const spatialEnv = (window as any).spatialEnvironment;
                        if (spatialEnv) spatialEnv.reset();
                        updateScannerUI();
                    };
                }
            }
        };

        const update = async () => {
            try {
                const response = await fetch('/api/soul/runtime_status');
                if (response.ok) {
                    const data = await response.json();
                    if (vActive) {
                        vActive.textContent = data.vision_active ? 'ACTIVE' : 'OFFLINE';
                        vActive.className = data.vision_active ? 'v-value active' : 'v-value';
                    }
                    if (vMmproj) vMmproj.textContent = data.mmproj_loaded ? 'YES' : 'NO';
                    if (vGaze) vGaze.textContent = data.last_gaze_time || '--';
                    if (vDesc && data.last_vision_description) vDesc.textContent = data.last_vision_description;
                }
            } catch (err) {}
            updateScannerUI();
        };

        update();
        setInterval(update, 3000);
    }
}
