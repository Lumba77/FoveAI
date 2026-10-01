import * as THREE from 'three';

export class AvatarStudioTab {
    private container: HTMLElement;
    private avatarManager: any = null;

    // Customization State
    private settings = {
        // Body Morphing
        height: 1.0,
        shoulderWidth: 1.0,
        waistRatio: 1.0,
        hipRatio: 1.0,
        armLength: 1.0,

        // Facial Morphing
        jawWidth: 1.0,
        noseSize: 1.0,
        eyeScale: 1.0,
        lipThickness: 1.0,

        // Material & Color Properties
        skinTone: '#e0ac69',
        eyeColor: '#2b5c8f',
        hairColor: '#3d2314',
        roughness: 0.5,
        subsurface: 0.3
    };

    constructor() {
        this.container = document.createElement('div');
        this.container.className = 'tab-content avatar-studio-tab';
        this.loadSavedSettings();
        this.render();
    }

    private loadSavedSettings() {
        try {
            const saved = localStorage.getItem('foveai_avatar_studio_preset');
            if (saved) {
                this.settings = { ...this.settings, ...JSON.parse(saved) };
            }
        } catch (_) {}
    }

    private saveSettings() {
        try {
            localStorage.setItem('foveai_avatar_studio_preset', JSON.stringify(this.settings));
            window.dispatchEvent(new CustomEvent('foveai_avatar_studio_updated', { detail: this.settings }));
        } catch (_) {}
    }

    public getContainer(): HTMLElement {
        return this.container;
    }

    private render() {
        this.container.innerHTML = `
            <div style="padding: 16px; color: #fff; font-family: system-ui, sans-serif; max-height: 80vh; overflow-y: auto;">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255,255,255,0.15); padding-bottom: 10px; margin-bottom: 15px;">
                    <h3 style="margin: 0; font-size: 16px; color: #00f3ff; display: flex; align-items: center; gap: 8px;">
                        <span>🎨</span> Native Avatar Customization Studio
                    </h3>
                    <div style="display: flex; gap: 8px;">
                        <button id="studio-reset-btn" style="background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); color: #fff; border-radius: 4px; padding: 4px 8px; font-size: 11px; cursor: pointer;">Reset</button>
                        <button id="studio-save-btn" style="background: #00f3ff; border: none; color: #000; font-weight: bold; border-radius: 4px; padding: 4px 12px; font-size: 11px; cursor: pointer;">Save Preset</button>
                    </div>
                </div>

                <!-- ── BODY MORPHING SECTION ── -->
                <div style="background: rgba(0,0,0,0.2); border: 1px solid rgba(0,243,255,0.2); border-radius: 8px; padding: 12px; margin-bottom: 15px;">
                    <div style="font-weight: 600; font-size: 12px; color: #39ff14; margin-bottom: 10px; text-transform: uppercase;">🦵 Body Proportions & Scale</div>
                    
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 11px;">
                        <div>
                            <label style="display: flex; justify-content: space-between;">Height <span id="val-height">${this.settings.height.toFixed(2)}x</span></label>
                            <input type="range" id="slider-height" min="0.8" max="1.3" step="0.01" value="${this.settings.height}" style="width: 100%;">
                        </div>
                        <div>
                            <label style="display: flex; justify-content: space-between;">Shoulder Width <span id="val-shoulderWidth">${this.settings.shoulderWidth.toFixed(2)}x</span></label>
                            <input type="range" id="slider-shoulderWidth" min="0.7" max="1.4" step="0.01" value="${this.settings.shoulderWidth}" style="width: 100%;">
                        </div>
                        <div>
                            <label style="display: flex; justify-content: space-between;">Waist Ratio <span id="val-waistRatio">${this.settings.waistRatio.toFixed(2)}x</span></label>
                            <input type="range" id="slider-waistRatio" min="0.7" max="1.3" step="0.01" value="${this.settings.waistRatio}" style="width: 100%;">
                        </div>
                        <div>
                            <label style="display: flex; justify-content: space-between;">Hip Ratio <span id="val-hipRatio">${this.settings.hipRatio.toFixed(2)}x</span></label>
                            <input type="range" id="slider-hipRatio" min="0.7" max="1.4" step="0.01" value="${this.settings.hipRatio}" style="width: 100%;">
                        </div>
                    </div>
                </div>

                <!-- ── FACIAL MORPHING SECTION ── -->
                <div style="background: rgba(0,0,0,0.2); border: 1px solid rgba(255,0,127,0.2); border-radius: 8px; padding: 12px; margin-bottom: 15px;">
                    <div style="font-weight: 600; font-size: 12px; color: #ff007f; margin-bottom: 10px; text-transform: uppercase;">👤 Facial Structure</div>
                    
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 11px;">
                        <div>
                            <label style="display: flex; justify-content: space-between;">Jaw Width <span id="val-jawWidth">${this.settings.jawWidth.toFixed(2)}x</span></label>
                            <input type="range" id="slider-jawWidth" min="0.7" max="1.3" step="0.01" value="${this.settings.jawWidth}" style="width: 100%;">
                        </div>
                        <div>
                            <label style="display: flex; justify-content: space-between;">Nose Scale <span id="val-noseSize">${this.settings.noseSize.toFixed(2)}x</span></label>
                            <input type="range" id="slider-noseSize" min="0.7" max="1.4" step="0.01" value="${this.settings.noseSize}" style="width: 100%;">
                        </div>
                        <div>
                            <label style="display: flex; justify-content: space-between;">Eye Scale <span id="val-eyeScale">${this.settings.eyeScale.toFixed(2)}x</span></label>
                            <input type="range" id="slider-eyeScale" min="0.8" max="1.3" step="0.01" value="${this.settings.eyeScale}" style="width: 100%;">
                        </div>
                        <div>
                            <label style="display: flex; justify-content: space-between;">Lip Thickness <span id="val-lipThickness">${this.settings.lipThickness.toFixed(2)}x</span></label>
                            <input type="range" id="slider-lipThickness" min="0.7" max="1.4" step="0.01" value="${this.settings.lipThickness}" style="width: 100%;">
                        </div>
                    </div>
                </div>

                <!-- ── MATERIAL & SHADER SECTION ── -->
                <div style="background: rgba(0,0,0,0.2); border: 1px solid rgba(255,170,0,0.2); border-radius: 8px; padding: 12px;">
                    <div style="font-weight: 600; font-size: 12px; color: #ffaa00; margin-bottom: 10px; text-transform: uppercase;">✨ Skin Shaders & Pigments</div>
                    
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 11px;">
                        <div>
                            <label style="display: block; margin-bottom: 4px;">Skin Pigment Tone</label>
                            <input type="color" id="picker-skinTone" value="${this.settings.skinTone}" style="width: 100%; height: 28px; border: none; cursor: pointer; background: transparent;">
                        </div>
                        <div>
                            <label style="display: block; margin-bottom: 4px;">Eye Color</label>
                            <input type="color" id="picker-eyeColor" value="${this.settings.eyeColor}" style="width: 100%; height: 28px; border: none; cursor: pointer; background: transparent;">
                        </div>
                        <div>
                            <label style="display: flex; justify-content: space-between;">Skin Roughness <span id="val-roughness">${this.settings.roughness.toFixed(2)}</span></label>
                            <input type="range" id="slider-roughness" min="0.1" max="0.9" step="0.02" value="${this.settings.roughness}" style="width: 100%;">
                        </div>
                        <div>
                            <label style="display: flex; justify-content: space-between;">Subsurface Glow <span id="val-subsurface">${this.settings.subsurface.toFixed(2)}</span></label>
                            <input type="range" id="slider-subsurface" min="0.0" max="0.8" step="0.02" value="${this.settings.subsurface}" style="width: 100%;">
                        </div>
                    </div>
                </div>
            </div>
        `;

        this.bindEvents();
    }

    private bindEvents() {
        const updateSlider = (key: keyof typeof this.settings, val: any) => {
            (this.settings as any)[key] = parseFloat(val) || val;
            const valDisplay = this.container.querySelector(`#val-${key}`);
            if (valDisplay) {
                valDisplay.textContent = typeof (this.settings as any)[key] === 'number' ? (this.settings as any)[key].toFixed(2) + (key.includes('Tone') || key.includes('Color') ? '' : 'x') : val;
            }
            this.applyCustomizationsToAvatar();
        };

        const keys = ['height', 'shoulderWidth', 'waistRatio', 'hipRatio', 'jawWidth', 'noseSize', 'eyeScale', 'lipThickness', 'roughness', 'subsurface'];
        keys.forEach(k => {
            const input = this.container.querySelector(`#slider-${k}`) as HTMLInputElement;
            if (input) {
                input.addEventListener('input', (e: any) => updateSlider(k as any, e.target.value));
            }
        });

        ['skinTone', 'eyeColor'].forEach(k => {
            const picker = this.container.querySelector(`#picker-${k}`) as HTMLInputElement;
            if (picker) {
                picker.addEventListener('input', (e: any) => updateSlider(k as any, e.target.value));
            }
        });

        const saveBtn = this.container.querySelector('#studio-save-btn');
        saveBtn?.addEventListener('click', () => {
            this.saveSettings();
            alert('✓ Avatar preset saved locally!');
        });

        const resetBtn = this.container.querySelector('#studio-reset-btn');
        resetBtn?.addEventListener('click', () => {
            localStorage.removeItem('foveai_avatar_studio_preset');
            this.settings = {
                height: 1.0, shoulderWidth: 1.0, waistRatio: 1.0, hipRatio: 1.0, armLength: 1.0,
                jawWidth: 1.0, noseSize: 1.0, eyeScale: 1.0, lipThickness: 1.0,
                skinTone: '#e0ac69', eyeColor: '#2b5c8f', hairColor: '#3d2314', roughness: 0.5, subsurface: 0.3
            };
            this.render();
            this.applyCustomizationsToAvatar();
        });
    }

    private applyCustomizationsToAvatar() {
        const foveaiAvatar = (window as any).foveaiAvatar;
        if (!foveaiAvatar || !foveaiAvatar.vrm) return;

        const vrmScene = foveaiAvatar.vrm.scene;
        if (!vrmScene) return;

        // 1. Scale Root & Bones
        vrmScene.scale.set(1, this.settings.height, 1);

        const chest = foveaiAvatar.bones?.chest || foveaiAvatar.bones?.upperChest;
        if (chest) {
            chest.scale.set(this.settings.shoulderWidth, 1, 1);
        }

        const hips = foveaiAvatar.bones?.hips;
        if (hips) {
            hips.scale.set(this.settings.hipRatio, 1, this.settings.waistRatio);
        }

        const head = foveaiAvatar.bones?.head;
        if (head) {
            head.scale.set(this.settings.jawWidth, this.settings.noseSize, this.settings.eyeScale);
        }

        // 2. Adjust Materials & Shaders
        vrmScene.traverse((obj: any) => {
            if (obj.isMesh && obj.material) {
                const matName = (obj.material.name || '').toLowerCase();
                const objName = (obj.name || '').toLowerCase();

                if (matName.includes('skin') || objName.includes('body') || objName.includes('face')) {
                    if (obj.material.color) {
                        obj.material.color.setStyle(this.settings.skinTone);
                    }
                    if (obj.material.roughness !== undefined) {
                        obj.material.roughness = this.settings.roughness;
                    }
                }

                if (matName.includes('eye') || objName.includes('eye')) {
                    if (obj.material.color) {
                        obj.material.color.setStyle(this.settings.eyeColor);
                    }
                }
            }
        });
    }
}
