// 🛸 FOVEAI UNIVERSAL THEME SYNC 🛸
// Inject this script into any FoveAI webpage to magically link it to the global Theme Engine

(function() {
    // Unified WS (XRLF IPC :8403) — same path for every FoveAI surface.
    // Same-origin via the Multigate/dev proxies (/ws/theme) so the tunnel
    // works too; falls back to a direct local socket for tray/dash pages.
    let wsPort = 8403;
    try {
        wsPort = (window.FOVEAI_WS_PORT) || 8403;
    } catch (e) {}
    let wsUrl;
    try {
        if (location.protocol === 'https:' || location.protocol === 'http:') {
            const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            wsUrl = proto + "//" + location.host + "/ws/theme";
        } else {
            wsUrl = "ws://127.0.0.1:" + wsPort + "/ws/theme";
        }
    } catch (e) {
        wsUrl = "ws://127.0.0.1:" + wsPort + "/ws/theme";
    }

    let attempts = 0;

    function connect() {
        // Opt-in: only dial the broker when a surface declares it is running.
        // FOVEAI_WS_PORT is set by the XRLF runtime; without it, stay quiet.
        if (!window.FOVEAI_WS_PORT && !window.FOVEAI_WS_ENABLED) {
            console.log("[FoveAI Theme] Broadcast channel idle (broker not advertised).");
            return;
        }
        // Fast-load from localStorage before WS connects
        try {
            const saved = localStorage.getItem('foveai_fallback_theme');
            if (saved) {
                applyUniversalTheme(JSON.parse(saved), true); // true = isFallback
            }
        } catch (e) {}

        if (attempts > 5) return;
        ws = new WebSocket(wsUrl);
        
        ws.onopen = () => {
            attempts = 0;
            console.log("[FoveAI Theme] Connected to Global Nervous System");
        };

        // A failed socket must stay quiet: an unhandled error event surfaces as
        // an uncaught page error and can take the whole app down with it.
        ws.onerror = () => { /* onclose owns reconnection */ };
        
        ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === "theme_update" && msg.theme) {
                    if (msg.theme.schema_version && msg.theme.schema_version !== "1.0") {
                        console.warn("[FoveAI Theme] Warning: Theme schema version mismatch. Expected 1.0, got " + msg.theme.schema_version);
                    }
                    applyUniversalTheme(msg.theme);
                }
            } catch (e) {
                console.error("[FoveAI Theme] Error parsing theme update", e);
            }
        };

        ws.onclose = () => {
            // The broadcast channel rides the XRLF WS, which is offline during
            // the interactive phase. Reconnect a few times, then stop: an endless
            // retry loop produced a wall of console errors on every page load.
            attempts += 1;
            if (attempts > 5) {
                console.log("[FoveAI Theme] Broadcast channel unavailable — themes still apply on reload.");
                return;
            }
            setTimeout(connect, Math.min(3000 * attempts, 30000));
        };
    }

    function applyUniversalTheme(theme, isFallback = false) {
        if (!isFallback) {
            localStorage.setItem('foveai_fallback_theme', JSON.stringify(theme));
        }

        console.log(`🎨 Applying FoveAI Global Theme: ${theme.theme_name}`);
        const root = document.documentElement;

        // 1. Core Variables
        root.style.setProperty('--fv-bg-dark', theme.fv_bg_dark);
        root.style.setProperty('--fv-bg-panel', theme.fv_bg_panel);
        root.style.setProperty('--fv-text-main', theme.fv_text_main);
        root.style.setProperty('--fv-text-muted', theme.fv_text_muted);
        root.style.setProperty('--fv-accent', theme.fv_accent);
        root.style.setProperty('--fv-accent-2', theme.fv_accent_2);
        root.style.setProperty('--fv-warn', theme.fv_warn);
        root.style.setProperty('--fv-danger', theme.fv_danger);
        root.style.setProperty('--fv-font-sans', theme.fv_font_sans || "'Inter', sans-serif");
        root.style.setProperty('--fv-font-mono', theme.fv_font_mono || "'Fira Code', monospace");

        
        // 1.5 Legacy / Older FoveAI Web Variables (for settings.css and kiosk)
        root.style.setProperty('--bg', theme.fv_bg_dark);
        root.style.setProperty('--panel', theme.fv_bg_panel);
        root.style.setProperty('--text', theme.fv_text_main);
        root.style.setProperty('--muted', theme.fv_text_muted);
        root.style.setProperty('--accent', theme.fv_accent);
        root.style.setProperty('--accent-pink', theme.fv_accent_2);
        root.style.setProperty('--success', theme.fv_warn); // usually a green/warm
        root.style.setProperty('--warning', theme.fv_warn);
        root.style.setProperty('--danger', theme.fv_danger);
        root.style.setProperty('--border', theme.fv_accent + '44');

        // 2. Structural & Glassmorphic Overlays
        const existing = document.getElementById('foveai-universal-glass');
        if (existing) existing.remove();
        
        const s = theme.ui_structure || {};
        const op = s.glass_opacity || 0.5;
        const blur = '8px';
        const accent = theme.fv_accent || '#328879';
        
        const gridCols = s.css_grid_template_columns || '250px 1fr';
        const gridRows = s.css_grid_template_rows || '1fr';
        const gridAreas = s.css_grid_areas || '"sidebar main"';

        const css = `
            :root {
                --glass-bg: rgba(0,0,0,${0.3 + (op * 0.4)});
                --glass-blur: blur(${blur});
                --glass-border: 1px solid ${accent}33;
                --glass-glow: 0 0 20px ${accent}22;
                
                /* Radical CSS Grid Injections */
                --fv-grid-cols: ${gridCols};
                --fv-grid-rows: ${gridRows};
                --fv-grid-areas: ${gridAreas};
            }
            .foveai-themed-panel, .chat-header, .sidebar, .dash-panel {
                background: var(--glass-bg) !important;
                -webkit-backdrop-filter: var(--glass-blur) saturate(180%) !important;
                backdrop-filter: var(--glass-blur) saturate(180%) !important;
                border: var(--glass-border) !important;
                box-shadow: var(--glass-glow) !important;
            }
        `;
        
        const style = document.createElement('style');
        style.id = 'foveai-universal-glass';
        style.textContent = css;
        document.head.appendChild(style);

        // 3. Background Image
        if (theme.background_image_url) {
            document.body.style.backgroundImage = `url('${theme.background_image_url}')`;
            document.body.style.backgroundSize = 'cover';
            document.body.style.backgroundPosition = 'center';
            document.body.style.backgroundAttachment = 'fixed';
        }

        // 4. Dispatch Event for 3D/Canvas Apps (like XR Vessel / Three.js)
        const fvEvent = new CustomEvent('foveai-theme-changed', { detail: theme });
        window.dispatchEvent(fvEvent);
    }

    // Initialize
    connect();
})();
