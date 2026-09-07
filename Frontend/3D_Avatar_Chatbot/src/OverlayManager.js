/**
 * Overlay Manager
 * Handles displaying the unified Feature Modal and dynamically loading content components.
 */
class OverlayManager {
    constructor() {
        this.modalEl = null;
        this.titleEl = null;
        this.bodyEl = null;
        this.closeBtn = null;
        this.loadedComponents = new Map(); // Cache loaded HTML
        this._initialized = false;

        // Defer DOM queries until DOM is ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this._init());
        } else {
            this._init();
        }
    }

    _init() {
        this.modalEl = document.getElementById('feature-modal');
        this.titleEl = document.getElementById('feature-modal-title');
        this.bodyEl = document.getElementById('feature-modal-body');
        this.closeBtn = document.getElementById('close-feature-modal');

        if (!this.modalEl) {
            console.warn('[OverlayManager] #feature-modal not found in DOM. Feature panel buttons will fall back to opening settings modal.');
            return;
        }

        this._initListeners();
        this._initialized = true;
    }

    _initListeners() {
        if (!this.modalEl) return;

        // Close on X button
        if (this.closeBtn) {
            this.closeBtn.addEventListener('click', () => this.close());
        }

        // Close on clicking outside the modal
        this.modalEl.addEventListener('click', (e) => {
            if (e.target === this.modalEl) {
                this.close();
            }
        });

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen()) {
                this.close();
            }
        });
    }

    isOpen() {
        return this.modalEl && this.modalEl.classList.contains('active');
    }

    /**
     * Open the feature modal with specific content
     * @param {string} title - The title to display
     * @param {string} componentUrl - URL to fetch the HTML content
     */
    async open(title, componentUrl) {
        if (!this.modalEl) {
            console.warn('[OverlayManager] Feature modal not available. Falling back to settings modal.');
            // Fallback: open the settings modal instead
            const settingsModal = document.getElementById('settings-modal');
            if (settingsModal && typeof openSettings === 'function') {
                openSettings();
            }
            return;
        }

        // Update title — it's now an <h2> element
        if (this.titleEl) {
            this.titleEl.textContent = title;
        }
        this.modalEl.classList.add('active');

        // Check cache
        if (this.loadedComponents.has(componentUrl)) {
            this._injectHTML(this.loadedComponents.get(componentUrl));
            return;
        }

        // Show loading state
        this.bodyEl.innerHTML = `<div style="text-align:center; padding: 40px; color: var(--text-muted); font-size: 0.9rem; font-family: var(--font-display);">INITIALIZING LINK...</div>`;

        try {
            const response = await fetch(componentUrl);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const html = await response.text();
            
            this.loadedComponents.set(componentUrl, html);
            this._injectHTML(html);
        } catch (err) {
            console.error(`[OverlayManager] Failed to load component ${componentUrl}:`, err);
            this.bodyEl.innerHTML = `<div style="color: var(--status-error); padding: 20px;">Failed to load module: ${err.message}</div>`;
        }
    }

    _injectHTML(html) {
        this.bodyEl.innerHTML = html;
        
        // Execute any scripts that were injected via innerHTML
        const scripts = this.bodyEl.querySelectorAll('script');
        scripts.forEach(oldScript => {
            const newScript = document.createElement('script');
            Array.from(oldScript.attributes).forEach(attr => newScript.setAttribute(attr.name, attr.value));
            newScript.appendChild(document.createTextNode(oldScript.innerHTML));
            oldScript.parentNode.replaceChild(newScript, oldScript);
        });
    }

    close() {
        if (!this.modalEl) return;
        this.modalEl.classList.remove('active');
    }

    /**
     * Helper to wire a button directly to a component
     */
    registerButton(btnId, title, componentUrl) {
        const btn = document.getElementById(btnId);
        if (btn) {
            btn.addEventListener('click', () => {
                this.open(title, componentUrl);
            });
        } else {
            console.warn(`[OverlayManager] Button #${btnId} not found in DOM`);
        }
    }
}

// Instantiate globally (constructor defers DOM queries)
window.overlayManager = new OverlayManager();

// Auto-register elements once DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    const om = window.overlayManager;
    om.registerButton('topbar-btn-imagine', 'DREAMSCAPE', 'components/imagine_panel.html');
    om.registerButton('topbar-btn-neural', 'NEURAL CORTEX', 'components/neural_panel.html');
    om.registerButton('topbar-btn-agency', 'AGENCY TERMINAL', 'components/agency_panel.html');
    om.registerButton('topbar-btn-webvm', 'LINUX VM', 'components/webvm_panel.html');
    om.registerButton('topbar-btn-system', 'SYSTEM CONFIGURATION', 'components/settings_panel.html');
    om.registerButton('topbar-btn-monetize', 'MONETIZATION ENGINE', 'components/monetize_panel.html');
    om.registerButton('topbar-btn-soundboard', 'SOUNDBOARD', 'components/soundboard_panel.html');
    om.registerButton('topbar-btn-persona', 'PERSONA & MBTI', 'components/persona_panel.html');
    om.registerButton('topbar-btn-diagnostics', 'DIAGNOSTICS', 'components/diagnostics_panel.html');
    // New panels
    om.registerButton('topbar-btn-modelhub', 'MODEL HUB', 'components/model_hub_panel.html');
    om.registerButton('topbar-btn-envmap', 'ENVIRONMENT MAPPING', 'components/environment_mapping_panel.html');
    om.registerButton('topbar-btn-cameras', 'AVATAR CAMERAS', 'components/avatar_cameras_panel.html');
    om.registerButton('topbar-btn-environment', 'ENVIRONMENT', 'components/environment_panel.html');
    om.registerButton('topbar-btn-controllers', 'CONTROLLERS', 'components/controllers_panel.html');
});
