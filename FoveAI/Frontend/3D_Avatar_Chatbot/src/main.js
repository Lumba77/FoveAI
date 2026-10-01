/**
 * Nexus Avatar - Main Application Controller (PROD, GLOBAL build) — UPDATED (LANG + VOICE PREFS)
 *
 * Key additions in this version:
 * ✅ Speech Settings persisted (language, voice, preference, rate, pitch)
 * ✅ "Any / Male / Female" preference filter (heuristic based)
 * ✅ Voice dropdown filters by selected Language
 * ✅ "Auto (best match)" logic in speakText
 * ✅ "TEST VOICE" button support
 * ✅ Preserves ViewerEngine + Proxy + Test Connection patch logic
 */

'use strict';

/* =========================================================
   Device Detection — early, before any DOM mutation
   Adds classes to <html> so CSS can adapt immediately.
   ========================================================= */
(function applyDeviceMode() {
    const isMobile = window.matchMedia('(max-width: 767px)').matches;
    const isTablet = window.matchMedia('(min-width: 768px) and (max-width: 1024px)').matches;
    const ua = navigator.userAgent || '';
    const isAndroid = /Android/i.test(ua);
    const isIOS = /iPad|iPhone|iPod/.test(ua);
    const isHeadset = /OculusBrowser|Quest|Vive|Pico|Wolvic/i.test(ua);

    const cl = document.documentElement.classList;
    cl.toggle('is-mobile', isMobile);
    cl.toggle('is-tablet', isTablet);
    cl.toggle('is-desktop', !isMobile && !isTablet);
    cl.toggle('is-android-phone', isAndroid && !isHeadset);
    cl.toggle('is-ios', isIOS);
    cl.toggle('is-headset', isHeadset);

    // Re-evaluate on resize (orientation changes)
    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
            const mob = window.matchMedia('(max-width: 767px)').matches;
            const tab = window.matchMedia('(min-width: 768px) and (max-width: 1024px)').matches;
            cl.toggle('is-mobile', mob);
            cl.toggle('is-tablet', tab);
            cl.toggle('is-desktop', !mob && !tab);
        }, 150);
    });
})();

/* =========================================================
   Speech Settings (persisted)
   ========================================================= */
const SpeechSettings = {
    lang: localStorage.getItem('speech_lang') || 'en-US',
    voiceURI: localStorage.getItem('speech_voice_uri') || '',
    voicePref: localStorage.getItem('speech_voice_pref') || 'female', // any|female|male
    rate: parseFloat(localStorage.getItem('speech_rate') || '0.9'),
    pitch: parseFloat(localStorage.getItem('speech_pitch') || '1.0'),
    autoSend: localStorage.getItem('stt_auto_send') === 'true',
    showConfidence: localStorage.getItem('stt_show_confidence') === 'true',
};

/* =========================================================
   Strict Global Aliases (GLOBAL build)
   ========================================================= */
const THREE = window.THREE;
const OrbitControls = window.OrbitControls || (THREE && THREE.OrbitControls) || null;
const GLTFLoader = window.GLTFLoader || (THREE && THREE.GLTFLoader) || null;

/* =========================================================
   Config: Avatar Manifest
   ========================================================= */
const AVATAR_MANIFEST_URL = '/vendor/avatars/avatars.json';

/* ============================
   Application State
   ============================ */
let scene, camera, renderer, controls, clock;
let currentAvatar = null;
let mixer = null;
let animations = {};
let currentAnimationAction = null;

let recognition = null;
let isListening = false;
let isVadPinned = false; // [NEXUS OVERHAUL] Continuous listening mode

let currentObjectURL = null;
let loaderWatchdogTimer = null;

/** Dynamic avatar list loaded from manifest */
let avatarItems = []; // [{name,file,url}]
let avatarBasePath = '/vendor/avatars';

/** Framing state — on mobile use tight fit so full character is visible */
let lastFrameFitOffset = window.matchMedia('(max-width: 767px)').matches ? 0.9 : 1.35;

/** Scene helpers */
let floorMesh = null;
let dirLight = null;

/* ============================
   Configuration (Providers)
   ============================ */

/**
 * Load config from unified LLMManager settings or fall back to legacy keys.
 * This ensures desktop and VR share the same settings (nexus_llm_settings).
 */
function loadConfig() {
    const defaults = {
        provider: 'none',
        apiKey: '',
        model: '',
        systemPrompt: 'You are a helpful AI assistant named Nexus. You are friendly, professional, and knowledgeable.',
        watsonxProjectId: '',
        baseUrl: '',
    };

    try {
        // 1) Try loading from unified LLMManager key (shared with VR)
        const unified = localStorage.getItem('nexus_llm_settings');
        if (unified) {
            const settings = JSON.parse(unified);
            console.log('[Main] Loading config from unified settings (nexus_llm_settings):', settings.provider);

            // Extract provider-specific settings
            let apiKey = '';
            let model = '';
            let baseUrl = '';
            let watsonxProjectId = '';

            if (settings.provider === 'openai' && settings.openai) {
                apiKey = settings.openai.api_key || '';
                model = settings.openai.model || 'gpt-4o';
                baseUrl = settings.openai.base_url || '';
            } else if (settings.provider === 'claude' && settings.claude) {
                apiKey = settings.claude.api_key || '';
                model = settings.claude.model || 'claude-3-5-sonnet-20240620';
                baseUrl = settings.claude.base_url || '';
            } else if (settings.provider === 'watsonx' && settings.watsonx) {
                apiKey = settings.watsonx.api_key || '';
                model = settings.watsonx.model_id || 'ibm/granite-13b-chat-v2';
                baseUrl = settings.watsonx.base_url || 'https://us-south.ml.cloud.ibm.com';
                watsonxProjectId = settings.watsonx.project_id || '';
            } else if (settings.provider === 'ollama' && settings.ollama) {
                model = settings.ollama.model || 'llama3';
                baseUrl = settings.ollama.base_url || 'http://localhost:11434';
            } else if (settings.provider === 'ollabridge' && settings.ollabridge) {
                apiKey = settings.ollabridge.api_key || '';
                model = settings.ollabridge.model || 'default';
                baseUrl = settings.ollabridge.base_url || '';
            }

            return {
                provider: settings.provider || defaults.provider,
                apiKey: apiKey,
                model: model,
                systemPrompt: settings.system_prompt || defaults.systemPrompt,
                watsonxProjectId: watsonxProjectId,
                baseUrl: baseUrl,
            };
        }
    } catch (e) {
        console.warn('[Main] Failed to load unified settings, falling back to legacy keys:', e);
    }

    // 2) Fall back to legacy localStorage keys (backward compatible)
    const legacyProvider = localStorage.getItem('ai_provider');
    if (legacyProvider && legacyProvider !== 'none') {
        console.log('[Main] Loading config from legacy localStorage keys');
        return {
            provider: legacyProvider || defaults.provider,
            apiKey: localStorage.getItem('ai_api_key') || defaults.apiKey,
            model: localStorage.getItem('ai_model') || defaults.model,
            systemPrompt: localStorage.getItem('system_prompt') || defaults.systemPrompt,
            watsonxProjectId: localStorage.getItem('watsonx_project_id') || defaults.watsonxProjectId,
            baseUrl: localStorage.getItem('base_url') || defaults.baseUrl,
        };
    }

    // 3) No localStorage config — fetch from backend .env via /api/soul/env
    // This is the default path when the user hasn't configured anything in the UI.
    // The .env file has FoveAI_CHAT_PROVIDER, API keys, model IDs, etc.
    console.log('[Main] No localStorage config found, fetching from backend /api/soul/env');
    // Return defaults immediately; the async fetch will populate localStorage and
    // the LLMManager will re-initialize when the response arrives.
    // Return a promise that resolves when config is ready
    const promise = _fetchEnvConfig();
    window.__NEXUS_CONFIG_READY__ = promise;
    return { ...defaults };
}

// Make config mutable so _fetchEnvConfig can update it
let config = loadConfig();

/** Async fetch .env config from backend and populate localStorage + LLMManager.
 *  Falls back to reading .env directly if backend is not running. */
async function _fetchEnvConfig(retries = 5) {
    let env = null;
    
    // Retry loop with exponential backoff — backend may still be starting up
    for (let attempt = 0; attempt <= retries; attempt++) {
        if (attempt > 0) {
            const delay = Math.min(1000 * Math.pow(2, attempt - 1), 8000);
            console.log(`[Main] Retrying backend config fetch in ${delay}ms (attempt ${attempt}/${retries})...`);
            await new Promise(r => setTimeout(r, delay));
        }
        
        // Try backend first
        try {
            const resp = await fetch('/api/soul/env', { signal: AbortSignal.timeout(3000) });
            if (resp.ok) {
                const data = await resp.json();
                if (data.status === 'ok' && data.env) {
                    env = data.env;
                    console.log('[Main] Loaded config from backend /api/soul/env');
                    break;
                }
            }
        } catch (e) {
            console.warn(`[Main] Backend /api/soul/env not reachable (attempt ${attempt}):`, e.message);
        }
        
        // Fallback: try to read .env directly via the proxy server
        if (!env) {
            try {
                const resp = await fetch('/api/proxy/8402/api/soul/env', { signal: AbortSignal.timeout(3000) });
                if (resp.ok) {
                    const data = await resp.json();
                    if (data.status === 'ok' && data.env) {
                        env = data.env;
                        console.log('[Main] Loaded config via proxy fallback');
                        break;
                    }
                }
            } catch (e) {
                console.warn(`[Main] Proxy fallback also failed (attempt ${attempt}):`, e.message);
            }
        }
    }
    
    // If we still have no env, check if there's a cached config from a previous session
    if (!env) {
        const cachedProvider = localStorage.getItem('ai_provider');
        if (cachedProvider && cachedProvider !== 'none') {
            console.log('[Main] Using cached localStorage config (backend unavailable)');
            // Config is already loaded from localStorage in loadConfig(), nothing more to do
            return;
        }
        console.log('[Main] No backend, no cache — showing setup guide. Provider will be "none".');
        return;
    }

    // Map .env vars to frontend config
    const provider = (env.FoveAI_CHAT_PROVIDER || 'unsloth').toLowerCase();
    const localBaseUrl = env.FoveAI_LOCAL_BASE_URL || 'http://127.0.0.1:8888/v1';
    const cloudBaseUrl = env.FoveAI_CLOUD_BASE_URL || 'https://ollama.com';
    const cloudModel = env.FoveAI_MODEL_CLOUD_ID || 'gemma4:31b-cloud';
    const localModel = env.FoveAI_MODEL_LOCAL_ID || 'MoQ-3.5';
    const ollamaApiKey = env.OLLAMA_API_KEY || '';
    const geminiApiKey = env.FoveAI_REPERTOIRE_GEMINI_API_KEY || '';
    const openrouterApiKey = env.FoveAI_CLOUD_OPENROUTER_API || '';

    // Determine which provider config to use
    let apiKey = '';
    let model = '';
    let baseUrl = '';

    if (provider === 'unsloth' || provider === 'local') {
        apiKey = '';  // local LLM doesn't need API key
        model = localModel;
        baseUrl = localBaseUrl;
    } else if (provider === 'ollama') {
        apiKey = ollamaApiKey;
        model = cloudModel;
        baseUrl = env.FoveAI_CLOUD_BASE_URL || 'https://ollama.com';
    } else if (provider === 'openai') {
        apiKey = env.OPENAI_API_KEY || '';
        model = env.FoveAI_MODEL_OPENAI_ID || 'gpt-4o';
        baseUrl = env.OPENAI_BASE_URL || '';
    } else if (provider === 'gemini') {
        apiKey = geminiApiKey;
        model = env.FoveAI_MODEL_GEMINI_ID || 'gemini-1.5-pro';
        baseUrl = env.FoveAI_REPERTOIRE_GEMINI_BASE_URL || 'https://generativelanguage.googleapis.com/v1beta/openai/';
    } else if (provider === 'openrouter') {
        apiKey = openrouterApiKey;
        model = env.FoveAI_MODEL_OPENROUTER_ID || 'llama-70b-instruct:free';
        baseUrl = env.FoveAI_CLOUD_OPENROUTER_BASEURL || 'https://openrouter.ai/api/v1/';
    }

    // Persist to localStorage so subsequent loads use the fast path
    // Map 'unsloth'/'local' to 'ollabridge' so LLMManager.sendMessage() routes correctly.
    // LLMManager only knows about: openai, claude, watsonx, ollama, ollabridge.
    // 'unsloth' would fall through to _streamLumax() which sends to a non-existent
    // /compagent/stream endpoint on soul_core.py (404 error).
    const effectiveProvider = (provider === 'unsloth' || provider === 'local' || provider === 'lm_studio') ? 'ollabridge' : provider;
    localStorage.setItem('ai_provider', effectiveProvider);
    localStorage.setItem('ai_api_key', apiKey);
    localStorage.setItem('ai_model', model);
    localStorage.setItem('base_url', baseUrl);
    if (env.FoveAI_COGNITIVE_MODE) {
        localStorage.setItem('cognitive_mode', env.FoveAI_COGNITIVE_MODE);
    }

    // Store feature flags from .env
    if (env.FoveAI_HUD_ENABLED !== undefined) {
        localStorage.setItem('foveai_hud_enabled', env.FoveAI_HUD_ENABLED);
        console.log('[Main] Feature flag FoveAI_HUD_ENABLED:', env.FoveAI_HUD_ENABLED);
    }
    if (env.FoveAI_CLOUD_MAX_TOKENS !== undefined) {
        localStorage.setItem('foveai_cloud_max_tokens', env.FoveAI_CLOUD_MAX_TOKENS);
    }
    if (env.FoveAI_AUDIO_ONLY_PROXY !== undefined) {
        localStorage.setItem('foveai_audio_only', env.FoveAI_AUDIO_ONLY_PROXY);
    }
    if (env.FoveAI_LIBRARIAN_ENABLED !== undefined) {
        localStorage.setItem('foveai_librarian_enabled', env.FoveAI_LIBRARIAN_ENABLED);
    }
    if (env.FoveAI_AUTONOMOUS_MOVEMENT !== undefined) {
        localStorage.setItem('foveai_autonomous_movement', env.FoveAI_AUTONOMOUS_MOVEMENT);
    }
    if (env.FoveAI_3D_HUD_ENABLED !== undefined) {
        localStorage.setItem('foveai_3d_hud_enabled', env.FoveAI_3D_HUD_ENABLED);
    }

    // Store 3D Avatar Frontend settings from .env
    if (env.FoveAI_TTS_ENABLED !== undefined) {
        localStorage.setItem('foveai_tts_enabled', env.FoveAI_TTS_ENABLED);
    }
    if (env.FoveAI_KOKORO_VOICE !== undefined) {
        localStorage.setItem('foveai_kokoro_voice', env.FoveAI_KOKORO_VOICE);
    }
    if (env.FoveAI_KOKORO_SPEED !== undefined) {
        localStorage.setItem('foveai_kokoro_speed', env.FoveAI_KOKORO_SPEED);
    }
    if (env.FoveAI_MEMORY_BACKUP_ENABLED !== undefined) {
        localStorage.setItem('foveai_memory_backup_enabled', env.FoveAI_MEMORY_BACKUP_ENABLED);
    }
    if (env.FoveAI_GREETING_ENABLED !== undefined) {
        localStorage.setItem('foveai_greeting_enabled', env.FoveAI_GREETING_ENABLED);
    }
    if (env.FoveAI_USER_NAME !== undefined) {
        localStorage.setItem('foveai_user_name', env.FoveAI_USER_NAME);
    }

    console.log('[Main] Loaded config from .env:', { provider, model, baseUrl });

    // Update the global config object AND the module-level config variable
    config.provider = effectiveProvider;
    config.apiKey = apiKey;
    config.model = model;
    config.baseUrl = baseUrl;
    config.systemPrompt = env.FoveAI_SYSTEM_PROMPT || 'You are a helpful AI assistant named Jen. You are friendly, professional, and knowledgeable.';

    window._nexusConfig = {
        provider: effectiveProvider,
        apiKey: apiKey,
        model: model,
        systemPrompt: env.FoveAI_SYSTEM_PROMPT || 'You are a helpful AI assistant named Jen. You are friendly, professional, and knowledgeable.',
        watsonxProjectId: '',
        baseUrl: baseUrl,
    };

    // Re-initialize LLMManager with the new config
    if (typeof window.LLMManager === 'function') {
        // Build the provider-specific settings
        const providerSettings = {
            [provider]: {
                api_key: apiKey,
                model: model,
                base_url: baseUrl,
            },
        };

        // Also populate ollabridge section with local LLM endpoint when using unsloth/local
        // so the Settings UI shows the correct base URL and auth mode for model fetching.
        // IMPORTANT: Strip trailing /v1 from localBaseUrl because ollabridge methods
        // append /v1/models and /v1/chat/completions themselves — double /v1 would break.
        if (effectiveProvider === 'ollabridge') {
            const ollaBaseUrl = (localBaseUrl || 'http://127.0.0.1:8888/v1').replace(/\/v1\/?$/, '');
            providerSettings.ollabridge = {
                api_key: '',
                pair_token: '',
                auth_mode: 'local-trust',
                base_url: ollaBaseUrl,
                model: localModel || 'MoQ-3.5',
            };
            // Enable proxy to avoid CORS issues — browser blocks direct fetch from
            // port 8080 to port 8888 (different origin). The proxy routes through
            // the same origin (port 8080) via /api/proxy.
            providerSettings.proxy = {
                enable_proxy: true,
                proxy_url: '/api/proxy',
            };
        }

        window._nexusLLM = new window.LLMManager();
        window._nexusLLM.updateSettings({
            provider: effectiveProvider,
            system_prompt: window._nexusConfig.systemPrompt,
            ...providerSettings,
        });
    }

    // Dispatch event so other components know config is ready
    window.dispatchEvent(new CustomEvent('nexus-config-ready', { detail: window._nexusConfig }));
}

/* ============================
   One-Time Migration: Legacy → Unified Settings
   ============================ */
// Automatically migrate existing settings to unified format for VR compatibility
(function migrateLegacySettings() {
    try {
        // Check if unified settings already exist
        if (localStorage.getItem('nexus_llm_settings')) {
            console.log('[Main] Unified settings already exist, skipping migration');
            return;
        }

        // Check if legacy settings exist
        const legacyProvider = localStorage.getItem('ai_provider');
        if (!legacyProvider || legacyProvider === 'none') {
            console.log('[Main] No legacy settings to migrate');
            return;
        }

        // Create LLMManager and save current config to unified format
        if (typeof window.LLMManager === 'function') {
            console.log('[Main] 🔄 Migrating legacy settings to unified format...');
            window._nexusLLM = new window.LLMManager();

            const patch = {
                provider: config.provider,
                system_prompt: config.systemPrompt,
                proxy: {
                    enable_proxy: true,
                    proxy_url: '/api/proxy',
                },
            };

            if (config.provider === 'openai') {
                patch.openai = {
                    api_key: config.apiKey,
                    model: config.model || 'gpt-4o',
                    base_url: config.baseUrl || '',
                };
            } else if (config.provider === 'claude') {
                patch.claude = {
                    api_key: config.apiKey,
                    model: config.model || 'claude-3-5-sonnet-20240620',
                    base_url: config.baseUrl || '',
                };
            } else if (config.provider === 'watsonx') {
                patch.watsonx = {
                    api_key: config.apiKey,
                    project_id: config.watsonxProjectId || '',
                    model_id: config.model || 'ibm/granite-13b-chat-v2',
                    base_url: config.baseUrl || 'https://us-south.ml.cloud.ibm.com',
                };
            } else if (config.provider === 'ollama') {
                patch.ollama = {
                    base_url: config.baseUrl || 'http://localhost:11434',
                    model: config.model || 'llama3',
                };
            } else if (config.provider === 'ollabridge') {
                patch.ollabridge = {
                    api_key: config.apiKey,
                    base_url: config.baseUrl || '',
                    model: config.model || 'default',
                };
            }

            window._nexusLLM.updateSettings(patch);
            console.log('[Main] ✅ Migration complete! VR will now use:', config.provider);
        } else {
            console.warn('[Main] LLMManager not loaded yet, migration will retry on settings save');
        }
    } catch (e) {
        console.warn('[Main] Migration failed (non-fatal):', e);
    }
})();

/* ============================
   One-Time Migration: Legacy TTS Settings → Unified Settings
   ============================ */
// Migrate existing TTS settings from individual keys to nexus_settings_v1
(function migrateLegacyTTSSettings() {
    try {
        // Check if unified settings already have TTS config
        const unifiedRaw = localStorage.getItem('nexus_settings_v1');
        if (unifiedRaw) {
            try {
                const settings = JSON.parse(unifiedRaw);
                // If speechVoice or speechRate exists, assume migration already done
                if (settings.speechVoice !== undefined || settings.speechRate !== undefined) {
                    console.log('[Main] TTS settings already in unified format, skipping migration');
                    return;
                }
            } catch (e) {
                // Invalid JSON, will recreate below
            }
        }

        // Check if legacy TTS settings exist
        const legacyVoiceURI = localStorage.getItem('speech_voice_uri');
        const legacyRate = localStorage.getItem('speech_rate');
        const legacyPitch = localStorage.getItem('speech_pitch');
        const legacyLang = localStorage.getItem('speech_lang');

        if (!legacyVoiceURI && !legacyRate && !legacyPitch && !legacyLang) {
            console.log('[Main] No legacy TTS settings to migrate');
            return;
        }

        console.log('[Main] 🔄 Migrating legacy TTS settings to unified format...');

        // Resolve the voice object from URI
        const voices = window.speechSynthesis?.getVoices?.() || [];
        const resolvedVoice = legacyVoiceURI ? voices.find((v) => v.voiceURI === legacyVoiceURI) : null;

        // Build unified TTS config from legacy settings
        const ttsConfig = {
            // ✅ Name goes here
            speechVoice: resolvedVoice?.name || '',

            // ✅ URI goes here
            speechVoiceURI: legacyVoiceURI || '',

            speechRate: legacyRate ? parseFloat(legacyRate) : 0.9,
            speechPitch: legacyPitch ? parseFloat(legacyPitch) : 1.0,
            speechVolume: 1.0, // Default (not stored in legacy)
            speechLang: legacyLang || 'en-US',
            ttsEnabled: true, // Default (not stored in legacy)
        };

        // Save to unified format
        if (window.SpeechService) {
            window.SpeechService.saveTTSConfig(ttsConfig);
            console.log('[Main] ✅ TTS migration complete! VR will now use desktop voice settings');
        } else {
            // Fallback: save directly if SpeechService not loaded yet
            let settings = {};
            if (unifiedRaw) {
                try {
                    settings = JSON.parse(unifiedRaw);
                } catch (e) {
                    // Ignore parse error
                }
            }
            localStorage.setItem('nexus_settings_v1', JSON.stringify({ ...settings, ...ttsConfig }));
            console.log('[Main] ✅ TTS migration complete (direct save)');
        }
    } catch (e) {
        console.warn('[Main] TTS migration failed (non-fatal):', e);
    }
})();

/* ============================
   Helpers
   ============================ */
function $(id) {
    return document.getElementById(id);
}

function safeClass(el, action, cls) {
    if (!el) return;
    if (action === 'add') el.classList.add(cls);
    if (action === 'remove') el.classList.remove(cls);
}

function logWarn(msg, extra) {
    console.warn(`[Nexus] ${msg}`, extra || '');
}

function logError(msg, extra) {
    console.error(`[Nexus] ${msg}`, extra || '');
}

/* ============================
   Loading Overlay
   ============================ */
function showLoading(message = 'Loading 3D Avatar...') {
    const overlay = $('loading-overlay');
    const text = $('loading-text') || document.querySelector('.loading-text');
    if (text) text.textContent = message;
    if (overlay) safeClass(overlay, 'remove', 'hidden');
}

function hideLoading() {
    const overlay = $('loading-overlay');
    if (overlay) safeClass(overlay, 'add', 'hidden');
}

function startLoaderWatchdog(ms = 20000) {
    stopLoaderWatchdog();
    loaderWatchdogTimer = setTimeout(() => {
        showLoading('Avatar load timed out. Try another avatar.');
        setStatus('idle', 'TIMEOUT');
    }, ms);
}

function stopLoaderWatchdog() {
    if (loaderWatchdogTimer) {
        clearTimeout(loaderWatchdogTimer);
        loaderWatchdogTimer = null;
    }
}

/* ============================
   Status Indicator
   ============================ */
function setStatus(mode, text) {
    const indicator = $('status-indicator');
    const statusText = $('status-text');
    if (statusText) statusText.textContent = text || '';

    const sessionSubtitle = $('session-subtitle');
    if (sessionSubtitle) sessionSubtitle.textContent = text || '';

    const aiStatus = $('ai-response-status');
    if (aiStatus)
        aiStatus.textContent =
            mode === 'speaking' ? 'Speaking…' : mode === 'listening' ? 'Listening…' : 'Awaiting input…';

    if (indicator) {
        indicator.classList.remove('speaking', 'listening');
        if (mode === 'speaking') indicator.classList.add('speaking');
        if (mode === 'listening') indicator.classList.add('listening');
    }
}

/* =========================================================
   Vendor Guard
   ========================================================= */
function vendorAssertOrAbort() {
    const missing = [];
    if (!THREE) missing.push('THREE');
    if (!GLTFLoader) missing.push('GLTFLoader');
    if (!OrbitControls) missing.push('OrbitControls');

    if (missing.length === 0) return true;

    const el = $('loading-text');
    if (el) el.textContent = `Initialization failed: ${missing.join(', ')} missing. Open DevTools console.`;
    console.error('[Nexus] Missing vendor globals:', missing);
    return false;
}

/* =========================================================
   VRM Manager IndexedDB Blob Restore
   ========================================================= */
function loadBlobFromVRMCache(fileKey) {
    return new Promise((resolve) => {
        try {
            const req = indexedDB.open('vrm_avatar_cache', 1);
            req.onerror = () => resolve(null);
            req.onsuccess = () => {
                try {
                    const db = req.result;
                    const tx = db.transaction('avatars', 'readonly');
                    const get = tx.objectStore('avatars').get(fileKey);
                    get.onsuccess = () => {
                        if (get.result && get.result.blob) {
                            const url = URL.createObjectURL(get.result.blob);
                            resolve(url);
                        } else {
                            resolve(null);
                        }
                    };
                    get.onerror = () => resolve(null);
                } catch (_) {
                    resolve(null);
                }
            };
            req.onupgradeneeded = (e) => {
                // DB doesn't exist yet — nothing cached
                e.target.transaction.abort();
                resolve(null);
            };
        } catch (_) {
            resolve(null);
        }
    });
}

/* =========================================================
   Installed Avatar Sync — merge VRM Manager installs into manifest
   ========================================================= */

/**
 * Merge user-installed avatars (from VRM Manager catalog) into the base
 * manifest items. Also removes entries whose source file is no longer
 * installed (uninstalled via VRM Manager).
 *
 * Non-destructive: legacy/bundled avatars in avatars.json are never removed.
 * Only catalog-installed entries are added or pruned.
 *
 * @param {Array} baseItems - Items from avatars.json or manifest override
 * @returns {Array} Merged items array
 */
function _mergeInstalledAvatars(baseItems) {
    let installedRaw;
    try {
        installedRaw = JSON.parse(localStorage.getItem('vrm_manager_installed') || '{}');
    } catch (_) {
        return baseItems;
    }

    // Build a Set of files already in the base manifest (for dedup)
    const existingFiles = new Set(baseItems.map((x) => x.file));

    // Entries to add: installed but not in manifest
    const additions = [];
    for (const [id, entry] of Object.entries(installedRaw)) {
        if (!entry || !entry.localFile) continue;
        const file = entry.localFile;
        if (existingFiles.has(file)) continue; // already in manifest

        additions.push({
            name: entry.name || file.replace(/\.\w+$/, ''),
            file: file,
            format: entry.format || (file.endsWith('.vrm') ? 'vrm' : 'glb'),
            source: entry.source || 'VRM Manager',
            features: entry.features || [],
            _installedId: id, // marker for installed avatars
        });
    }

    // Entries to remove: previously added by VRM Manager but now uninstalled.
    // Only prune items that have a blob: or vroid-hub: URL and whose file
    // is NOT in the installed list and NOT a bundled avatar (no _installedId).
    const installedFiles = new Set(
        Object.values(installedRaw)
            .filter((e) => e && e.localFile)
            .map((e) => e.localFile)
    );

    const merged = baseItems.filter((item) => {
        // Keep all bundled/legacy avatars unconditionally
        if (!item._installedId) return true;
        // Keep installed entries that are still in vrm_manager_installed
        return installedFiles.has(item.file);
    });

    if (additions.length > 0) {
        merged.push(...additions);
        console.log(
            '[Main] Merged',
            additions.length,
            'installed avatar(s) into manifest:',
            additions.map((a) => a.name).join(', ')
        );
    }

    return merged;
}

/* =========================================================
   Avatar Manifest Loader
   ========================================================= */
async function loadAvatarManifest() {
    try {
        // Check for VRM Manager manifest override (includes downloaded VRM avatars)
        const override = localStorage.getItem('vrm_manager_manifest_override');
        let data;

        if (override) {
            try {
                data = JSON.parse(override);
                console.log('[Main] Using VRM Manager manifest override with', (data.items || []).length, 'avatars');
            } catch (_) {
                data = null;
            }
        }

        if (!data) {
            const res = await fetch(AVATAR_MANIFEST_URL, { cache: 'no-store' });
            if (!res.ok) throw new Error(`Manifest fetch failed: ${res.status} ${res.statusText}`);
            data = await res.json();
        }

        const basePath = (data && data.basePath) || '/vendor/avatars';
        let items = (data && data.items) || [];

        if (!Array.isArray(items)) throw new Error('Manifest format invalid: items must be an array');

        // ── Merge user-installed avatars from VRM Manager ──
        // This ensures avatars installed via Browse Catalog always appear,
        // even if autoInstall was off or the manifest override is stale.
        items = _mergeInstalledAvatars(items);

        // Collect blob URLs from VRM Manager downloads
        const blobMap = JSON.parse(localStorage.getItem('vrm_manager_blob_urls') || '{}');

        avatarBasePath = basePath.replace(/\/$/, '');
        avatarItems = items
            .filter((x) => x && x.file)
            .map((x) => ({
                name: x.name || x.file,
                file: x.file,
                url: blobMap[x.file] || `${avatarBasePath}/${x.file}`,
                format: x.format || (x.file.endsWith('.vrm') ? 'vrm' : 'glb'),
                vroidModelId: x.vroidModelId || null,
                _installedId: x._installedId || null, // preserve merge marker
            }));

        // Restore stale blob: URLs from IndexedDB.
        // blob: URLs expire when the page is unloaded, so on a fresh page load
        // any VRM Manager downloads will have dead blob URLs.  Re-create them
        // from the cached binary stored in IndexedDB during install.
        // Also restore URLs for merged installed avatars (their files only exist in IndexedDB).
        const refreshedBlobMap = {};
        for (const item of avatarItems) {
            const needsRestore = (item.url && item.url.startsWith('blob:')) || item._installedId;
            if (needsRestore) {
                const fileKey = 'file:' + item.file;
                let cached = await loadBlobFromVRMCache(fileKey);
                // Also try VRoid Hub cache key if this is a VRoid Hub model
                if (!cached && item.vroidModelId) {
                    cached = await loadBlobFromVRMCache('vroid-hub-' + item.vroidModelId);
                }
                if (cached) {
                    item.url = cached;
                    refreshedBlobMap[item.file] = cached;
                } else {
                    // Blob gone from IndexedDB — fall back to server path so
                    // it doesn't 404 on a dead blob: URL
                    item.url = `${avatarBasePath}/${item.file}`;
                }
            }
        }
        // Update blobMap in localStorage with fresh URLs so the rest of the
        // session doesn't hit dead blob: references
        if (Object.keys(refreshedBlobMap).length > 0) {
            const updated = { ...blobMap, ...refreshedBlobMap };
            try {
                localStorage.setItem('vrm_manager_blob_urls', JSON.stringify(updated));
            } catch (_) { }
        }

        populateAvatarSelect(avatarItems);
        window.__AVATAR_ITEMS__ = avatarItems; // expose to module bridge

        // Check if VRM Manager directed us to load a specific avatar
        const useAvatar = localStorage.getItem('vrm_manager_use_avatar');
        if (useAvatar) {
            try {
                const selection = JSON.parse(useAvatar);
                localStorage.removeItem('vrm_manager_use_avatar');

                // Try to find in manifest items by file or name
                let idx = avatarItems.findIndex((x) => x.file === selection.file || x.name === selection.name);

                // If not found in manifest, add it dynamically (e.g. downloaded via VRM Manager)
                if (idx < 0 && selection.url) {
                    // For downloaded avatars, blob URLs expire on page reload
                    // and vroid-hub: scheme URLs can't be loaded directly.
                    // Restore from VRM Manager's IndexedDB cache.
                    let resolvedUrl = selection.url;
                    if (resolvedUrl.startsWith('blob:') || resolvedUrl.startsWith('vroid-hub:')) {
                        const fileKey = 'file:' + (selection.file || selection.id);
                        const cached = await loadBlobFromVRMCache(fileKey);
                        if (cached) {
                            resolvedUrl = cached;
                        } else if (resolvedUrl.startsWith('vroid-hub:')) {
                            // No cache — try the catalog item cache key
                            const modelId = resolvedUrl.replace('vroid-hub:', '');
                            const cacheId = 'vroid-hub-' + modelId;
                            const cached2 = await loadBlobFromVRMCache(cacheId);
                            if (cached2) resolvedUrl = cached2;
                        }
                    }

                    avatarItems.push({
                        name: selection.name || selection.file || 'VRM Avatar',
                        file: selection.file || selection.id,
                        url: resolvedUrl,
                        format: selection.format || 'vrm',
                    });
                    idx = avatarItems.length - 1;
                    populateAvatarSelect(avatarItems);
                    window.__AVATAR_ITEMS__ = avatarItems;
                }

                if (idx >= 0) {
                    // For existing manifest items with stale blob/vroid-hub URLs, try IndexedDB restore
                    const item = avatarItems[idx];
                    if (item.url && (item.url.startsWith('blob:') || item.url.startsWith('vroid-hub:'))) {
                        const fileKey = 'file:' + item.file;
                        let cached = await loadBlobFromVRMCache(fileKey);
                        if (!cached && item.url.startsWith('vroid-hub:')) {
                            const modelId = item.url.replace('vroid-hub:', '');
                            cached = await loadBlobFromVRMCache('vroid-hub-' + modelId);
                        }
                        if (cached) item.url = cached;
                    }

                    const select = $('avatar-select');
                    if (select) select.value = String(idx);
                    // Store the index so loadDefaultAvatarFromManifest loads it
                    window.__vrm_manager_avatar_idx = idx;
                    console.log('[Main] VRM Manager selected avatar:', selection.name, 'at index', idx);
                }
            } catch (e) {
                console.warn('[Main] VRM Manager avatar selection error:', e);
            }
        }

        return avatarItems;
    } catch (e) {
        logError('Avatar manifest load failed', e);
        showLoading('Failed to load avatar list (vendor/avatars/avatars.json missing?)');
        setStatus('idle', 'ERROR');
        populateAvatarSelect([]);
        return [];
    }
}

function populateAvatarSelect(items) {
    const select = $('avatar-select');
    if (!select) return;

    select.innerHTML = '';

    if (!items || items.length === 0) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'No avatars found (check avatars.json)';
        select.appendChild(opt);
        return;
    }

    items.forEach((it, idx) => {
        const opt = document.createElement('option');
        opt.value = String(idx);
        opt.textContent = it.name;
        select.appendChild(opt);
    });

    // Expose manifest to module engine (ViewerEngine)
    window.__AVATAR_ITEMS__ = avatarItems;
    window.__AVATAR_BASE_PATH__ = avatarBasePath;
}

/* =========================================================
   Avatar positioning helpers
   ========================================================= */
function placeAvatarOnFloor(avatarRoot, floorY = 0) {
    const box = new THREE.Box3().setFromObject(avatarRoot);
    const size = box.getSize(new THREE.Vector3());
    const minY = box.min.y;

    avatarRoot.position.y += floorY - minY;
    return { box, size };
}

/* =========================================================
   Camera framing
   ========================================================= */
function frameObjectToCamera(object, fitOffset = 1.35) {
    if (!object || !camera) return;

    const box = new THREE.Box3().setFromObject(object);
    if (!isFinite(box.min.x) || !isFinite(box.max.x)) return;

    const center = box.getCenter(new THREE.Vector3());

    // Recenter model to origin
    object.position.sub(center);

    const box2 = new THREE.Box3().setFromObject(object);
    const size2 = box2.getSize(new THREE.Vector3());
    const center2 = box2.getCenter(new THREE.Vector3());
    // [NEXUS OVERHAUL] Shift target Y up by 25% of height to focus on face instead of chest
    const height = box2.max.y - box2.min.y;
    center2.y += height * 0.25;

    const maxSize = Math.max(size2.x, size2.y, size2.z);
    const fitHeightDistance = maxSize / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov * 0.5)));
    const fitWidthDistance = fitHeightDistance / camera.aspect;
    const distance = fitOffset * Math.max(fitHeightDistance, fitWidthDistance);

    const isMobileView = window.matchMedia('(max-width: 767px)').matches;
    // On mobile: lower camera angle (0.15) shows full body head-to-toe
    // On desktop: slightly elevated (0.5) for upper-body focus
    const direction = new THREE.Vector3(0, isMobileView ? 0.15 : 0.5, 1).normalize();
    camera.position.copy(direction.multiplyScalar(distance));

    camera.near = Math.max(0.01, distance / 100);
    camera.far = distance * 100;
    camera.updateProjectionMatrix();

    if (controls) {
        controls.target.copy(center2);
        controls.update();
    } else {
        camera.lookAt(center2);
    }

    if (floorMesh) {
        const worldBox = new THREE.Box3().setFromObject(object);
        const yMin = worldBox.min.y;
        floorMesh.position.y = yMin - 0.02;
    }

    lastFrameFitOffset = fitOffset;
}

function resetView() {
    // Prefer ViewerEngine camera reset (handles avatar framing automatically)
    if (window.NEXUS_VIEWER?.resetCamera) {
        window.NEXUS_VIEWER.resetCamera();
        return;
    }
    if (!camera || !controls) return;
    const mob = window.matchMedia('(max-width: 767px)').matches;
    camera.position.set(0, mob ? 0.9 : 1.5, mob ? 2.5 : 3);
    controls.target.set(0, mob ? 0.8 : 1, 0);
    controls.update();

    if (currentAvatar) frameObjectToCamera(currentAvatar, lastFrameFitOffset);
}

/* ============================
   Three.js Setup (GLOBAL)
   ============================ */
function setupThreeJS() {
    const viewport = $('avatar-viewport');
    if (!viewport) {
        showLoading('UI error: #avatar-viewport not found');
        throw new Error('#avatar-viewport not found');
    }

    const w = viewport.clientWidth || 640;
    const h = viewport.clientHeight || 480;

    scene = new THREE.Scene();
    scene.background = null;

    const isMobileInit = window.matchMedia('(max-width: 767px)').matches;
    // Narrower FOV on mobile (45°) frames the character tighter within tall viewport
    camera = new THREE.PerspectiveCamera(isMobileInit ? 45 : 55, w / h, 0.1, 1000);
    // Lower camera Y on mobile to center full-body view
    camera.position.set(0, isMobileInit ? 0.9 : 1.5, isMobileInit ? 2.5 : 3);

    let canvas = viewport.querySelector('canvas');
    if (!canvas) {
        canvas = document.createElement('canvas');
        viewport.appendChild(canvas);
    }

    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setSize(w, h, false);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    // WebXR initialization
    renderer.xr.enabled = true;

    scene.add(new THREE.AmbientLight(0xffffff, 0.55));

    dirLight = new THREE.DirectionalLight(0xffffff, 0.95);
    dirLight.position.set(5, 10, 7);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 2048;
    dirLight.shadow.mapSize.height = 2048;
    scene.add(dirLight);

    const pointLight = new THREE.PointLight(0xffffff, 0.35, 100);
    pointLight.position.set(-5, 5, 5);
    scene.add(pointLight);

    floorMesh = new THREE.Mesh(
        new THREE.PlaneGeometry(50, 50),
        new THREE.MeshStandardMaterial({ color: 0x0b1f2b, roughness: 1, metalness: 0 })
    );
    floorMesh.rotation.x = -Math.PI / 2;
    floorMesh.position.y = -1;
    floorMesh.receiveShadow = true;
    floorMesh.material.depthWrite = false;
    floorMesh.material.depthTest = true;
    floorMesh.renderOrder = 0;
    scene.add(floorMesh);

    controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.minDistance = 0.5;
    controls.maxDistance = 25;
    controls.enablePan = true;
    controls.maxPolarAngle = Math.PI * 0.49;
    // Target center-of-body on mobile (lower) vs upper-body on desktop
    controls.target.set(0, isMobileInit ? 0.8 : 1, 0);

    clock = new THREE.Clock();

    window.addEventListener('resize', onWindowResize);

    if (window.ResizeObserver) {
        const ro = new ResizeObserver(() => onWindowResize());
        ro.observe(viewport);
    }

    animate();
}

function animate() {
    renderer.setAnimationLoop(function (time, frame) {
        const delta = clock ? clock.getDelta() : 0;
        if (mixer) mixer.update(delta);

        /* NEXUS_PATCH_LIFE_ENGINE_UPDATE_LOOP */
        try {
            // clock exists only in legacy ThreeJS path; guard it.
            const t = typeof clock !== 'undefined' && clock ? clock.getElapsedTime() : performance.now() * 0.001;
            window.NEXUS_PROCEDURAL_ANIMATOR?.update?.(t, delta);
        } catch (_) { }
        if (controls) controls.update();
        if (renderer && scene && camera) renderer.render(scene, camera);
    });
}

function onWindowResize() {
    const viewport = $('avatar-viewport');
    if (!viewport || !camera || !renderer) return;

    const w = viewport.clientWidth || 640;
    const h = viewport.clientHeight || 480;

    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, false);
}

/* ============================
   Disposal
   ============================ */
function disposeObject3D(obj) {
    if (!obj) return;
    obj.traverse((child) => {
        if (!child.isMesh) return;

        if (child.geometry && child.geometry.dispose) child.geometry.dispose();

        const mats = Array.isArray(child.material) ? child.material : [child.material];
        mats.forEach((mat) => {
            if (!mat) return;
            for (const k in mat) {
                const v = mat[k];
                if (v && v.isTexture && v.dispose) v.dispose();
            }
            if (mat.dispose) mat.dispose();
        });
    });
}

/* ============================
   Avatar Loading
   ============================ */
function waitForViewerEngineReady(timeoutMs = 30000) {
    // If already ready, resolve immediately
    if (window.NEXUS_VIEWER && typeof window.NEXUS_VIEWER.loadAvatar === 'function') {
        console.log('[Main] ViewerEngine already ready');
        return Promise.resolve(true);
    }

    console.log('[Main] Waiting for ViewerEngine...', {
        hasReadyPromise: !!window.__NEXUS_VIEWER_READY__,
        hasNexusViewer: !!window.NEXUS_VIEWER,
    });

    // Hybrid: poll for NEXUS_VIEWER (handles any load path) with timeout
    const start = Date.now();
    return new Promise((resolve, reject) => {
        // Also listen to the ready promise if available
        if (window.__NEXUS_VIEWER_READY__) {
            window.__NEXUS_VIEWER_READY__.then(() => {
                console.log('[Main] ViewerEngine ready via promise');
                resolve(true);
            });
        }

        (function tick() {
            if (window.NEXUS_VIEWER && typeof window.NEXUS_VIEWER.loadAvatar === 'function') {
                console.log('[Main] ViewerEngine ready via polling after', Date.now() - start, 'ms');
                return resolve(true);
            }
            if (Date.now() - start > timeoutMs) {
                console.error('[Main] ViewerEngine not ready after', timeoutMs, 'ms', {
                    hasNexusViewer: !!window.NEXUS_VIEWER,
                    docReadyState: document.readyState,
                });
                return reject(new Error('ViewerEngine not ready (timeout)'));
            }
            setTimeout(tick, 100);
        })();
    });
}

function loadAvatar(url, source, avatarName) {
    // ViewerEngine path
    if (window.__USE_GLTF_VIEWER_ENGINE__) {
        showLoading('Loading 3D Avatar...');
        setStatus('idle', 'LOADING...');
        startLoaderWatchdog(20000);

        (async () => {
            try {
                await waitForViewerEngineReady(15000);

                // Resolve vroid-hub: custom scheme to a real blob URL.
                // Downloaded VRoid Hub models are cached in IndexedDB; fall
                // back to the download-license API if no cache entry exists.
                let resolvedUrl = url;
                if (typeof url === 'string' && url.startsWith('vroid-hub:')) {
                    const modelId = url.replace('vroid-hub:', '');
                    let blobUrl = null;

                    // 1. Try IndexedDB cache (model was already downloaded)
                    if (typeof VRMManager !== 'undefined' && VRMManager.getCachedBlob) {
                        // The cache key is the catalog item id, not the raw URL.
                        // Installed avatars use id "vroid-hub-<modelId>".
                        const cacheId = `vroid-hub-${modelId}`;
                        try {
                            const cached = await VRMManager.getCachedBlob(cacheId);
                            if (cached && cached.blob) {
                                blobUrl = URL.createObjectURL(cached.blob);
                            }
                        } catch (_) {
                            /* cache miss */
                        }
                    }

                    // 2. Fall back to download license API
                    if (!blobUrl && typeof VRMManager !== 'undefined' && VRMManager.getVroidHubDownloadUrl) {
                        try {
                            const realUrl = await VRMManager.getVroidHubDownloadUrl(modelId);
                            if (realUrl) {
                                const res = await fetch(`/api/avatar-proxy?url=${encodeURIComponent(realUrl)}`);
                                if (res.ok) {
                                    const blob = await res.blob();
                                    blobUrl = URL.createObjectURL(blob);
                                    // Cache the blob so future reloads don't need another download license
                                    if (VRMManager.cacheBlob) {
                                        const cacheId = `vroid-hub-${modelId}`;
                                        VRMManager.cacheBlob(cacheId, blob, { format: 'vrm' }).catch(() => { });
                                    }
                                }
                            }
                        } catch (e) {
                            console.warn('[Main] VRoid Hub download-license fallback failed:', e.message);
                        }
                    }

                    if (blobUrl) {
                        resolvedUrl = blobUrl;
                    } else {
                        throw new Error('Could not resolve VRoid Hub model. Try re-installing it from the catalog.');
                    }
                }

                // Pass avatarName so ViewerEngine/AvatarManager can detect VRM files
                // even when the URL is a blob: (e.g. uploaded .vrm files)
                await window.NEXUS_VIEWER.loadAvatar(resolvedUrl, avatarName || '');

                // Sync saved pose settings to the live viewport immediately.
                // Without this, localStorage settings only take effect on "Save".
                applyPoseSettingsLive();

                /* NEXUS_PATCH_LIFE_ENGINE_REGISTER_VIEWER */
                // Note: ProceduralAnimator registration now handled inside AvatarManager.setAvatarByUrl()
                // Auto-blink also starts automatically via AvatarManager._buildVRMLoaderBridge()
                console.log('[Main] Avatar loaded via ViewerEngine', {
                    root: !!window.NEXUS_VIEWER?.avatarManager?.currentRoot,
                    vrmLoader: !!window.NEXUS_VIEWER?.avatarManager?.vrmLoader,
                    clips: window.NEXUS_VIEWER?.avatarManager?.currentClips?.length || 0,
                    proceduralAnimator: !!window.NEXUS_PROCEDURAL_ANIMATOR,
                });
                stopLoaderWatchdog();
                hideLoading();
                setStatus('idle', 'READY');
                const hint = document.getElementById('viewport-hint');
                if (hint) hint.classList.add('hidden');
                console.log(`[Nexus] Avatar loaded (viewer-engine):`, url);
            } catch (e) {
                stopLoaderWatchdog();
                console.error('[Main] loadAvatar failed:', e.message, {
                    url,
                    source,
                    hasNexusViewer: !!window.NEXUS_VIEWER,
                    hasLoadAvatar: typeof window.NEXUS_VIEWER?.loadAvatar,
                    useGltfEngine: !!window.__USE_GLTF_VIEWER_ENGINE__,
                    hasReadyPromise: !!window.__NEXUS_VIEWER_READY__,
                    docReadyState: document.readyState,
                    containerExists: !!(
                        document.getElementById('avatar-viewport') || document.getElementById('avatar-container')
                    ),
                });
                const detail = e.message || String(e);
                showLoading(`Failed to load avatar: ${detail}`);
                setStatus('idle', 'ERROR');
            }
        })();

        return;
    }

    // Legacy path
    showLoading('Loading 3D Avatar...');
    setStatus('idle', 'LOADING...');
    startLoaderWatchdog(20000);

    if (!scene) {
        stopLoaderWatchdog();
        showLoading('Initialization failed: scene not ready');
        setStatus('idle', 'ERROR');
        return;
    }

    if (currentAvatar) {
        scene.remove(currentAvatar);
        disposeObject3D(currentAvatar);
        currentAvatar = null;
    }

    if (mixer) {
        mixer.stopAllAction();
        mixer = null;
    }
    animations = {};
    currentAnimationAction = null;

    if (currentObjectURL && currentObjectURL !== url) {
        URL.revokeObjectURL(currentObjectURL);
        currentObjectURL = null;
    }

    if (url && url.startsWith('blob:')) {
        currentObjectURL = url;
    }

    const loader = new GLTFLoader();

    loader.load(
        url,
        (gltf) => {
            stopLoaderWatchdog();

            currentAvatar = gltf.scene;
            scene.add(currentAvatar);

            /* NEXUS_PATCH_LIFE_ENGINE_REGISTER_LEGACY */
            try {
                window.NEXUS_PROCEDURAL_ANIMATOR?.registerAvatar?.(
                    currentAvatar,
                    Array.isArray(gltf.animations) && gltf.animations.length > 0
                );
                // Set natural standing pose (replaces T-pose) and default talk style
                window.NEXUS_PROCEDURAL_ANIMATOR?.setBasePose?.('lecturerNeutral');
                window.NEXUS_PROCEDURAL_ANIMATOR?.setTalkStyle?.('explainCalm');
            } catch (_) { }

            // Sync saved pose settings to the live viewport immediately.
            applyPoseSettingsLive();
            currentAvatar.traverse((child) => {
                if (child.isMesh) {
                    child.castShadow = true;
                    child.receiveShadow = true;
                    child.renderOrder = 1;
                }
            });

            placeAvatarOnFloor(currentAvatar, 0);

            onWindowResize();
            frameObjectToCamera(currentAvatar, lastFrameFitOffset);

            if (Array.isArray(gltf.animations) && gltf.animations.length > 0) {
                mixer = new THREE.AnimationMixer(currentAvatar);
                gltf.animations.forEach((clip) => {
                    const key = (clip.name || 'clip').toLowerCase();
                    animations[key] = clip;
                });

                // Register clips in central AnimationManager
                try {
                    window.NEXUS_ANIMATION_MANAGER?.registerClips?.(gltf.animations);
                } catch (_) { }

                const idleKey = findIdleAnimation();
                if (idleKey) playAnimation(idleKey, true);
            }

            hideLoading();
            setStatus('idle', 'READY');

            const hint = $('viewport-hint');
            if (hint) safeClass(hint, 'add', 'hidden');

            console.log(`[Nexus] Avatar loaded (${source}):`, url);
            console.log('[Nexus] Animations:', Object.keys(animations));
        },
        (progress) => {
            const loaded = progress && typeof progress.loaded === 'number' ? progress.loaded : 0;
            const total = progress && typeof progress.total === 'number' ? progress.total : 0;

            if (total > 0) {
                const percent = Math.round((loaded / total) * 100);
                showLoading(`Loading 3D Avatar... ${percent}%`);
            } else {
                showLoading('Loading 3D Avatar...');
            }
        },
        (error) => {
            stopLoaderWatchdog();
            logError('Error loading avatar', error);
            showLoading('Failed to load avatar. Try another preset.');
            setStatus('idle', 'ERROR');
            showMessage('Failed to load avatar. Please try another one.', 'error');

            if (currentObjectURL && currentObjectURL.startsWith('blob:')) {
                URL.revokeObjectURL(currentObjectURL);
                currentObjectURL = null;
            }
        }
    );
}

function loadDefaultAvatarFromManifest() {
    if (!avatarItems || avatarItems.length === 0) {
        showLoading('No avatars found in manifest. Upload a .glb/.gltf to test.');
        setStatus('idle', 'READY');
        return;
    }

    // If VRM Manager selected a specific avatar, load that one
    const vmIdx = window.__vrm_manager_avatar_idx;
    if (vmIdx != null && avatarItems[vmIdx]) {
        delete window.__vrm_manager_avatar_idx;
        loadAvatar(avatarItems[vmIdx].url, 'vrm-manager', avatarItems[vmIdx].name);
        return;
    }

    // Restore previously chosen avatar from localStorage (persists across navigation)
    try {
        const savedFile = localStorage.getItem('nexus_selected_avatar_file');
        const savedIdx = parseInt(localStorage.getItem('nexus_selected_avatar_idx') || '', 10);
        if (savedFile) {
            // Check if this is an uploaded avatar (starts with "upload:" prefix)
            if (savedFile.startsWith('upload:')) {
                // Attempt to restore the blob from IndexedDB cache
                (async () => {
                    const blobUrl = await loadBlobFromVRMCache(savedFile);
                    if (blobUrl) {
                        // Check if this uploaded avatar is already in avatarItems
                        let fileIdx = avatarItems.findIndex((x) => x.file === savedFile);
                        if (fileIdx < 0) {
                            // Not in the list — add it back
                            const displayName = savedFile.replace('upload:', '').replace(/\.\w+$/, '');
                            avatarItems.push({
                                name: displayName,
                                file: savedFile,
                                url: blobUrl,
                                format: savedFile.endsWith('.vrm') ? 'vrm' : 'glb',
                                _uploaded: true,
                            });
                            fileIdx = avatarItems.length - 1;
                            populateAvatarSelect(avatarItems);
                        } else {
                            // Update the stale blob URL
                            avatarItems[fileIdx].url = blobUrl;
                        }
                        const select = $('avatar-select');
                        if (select) select.value = String(fileIdx);
                        loadAvatar(blobUrl, 'upload(persisted)', displayName);
                        console.log('[Main] Restored uploaded avatar from IndexedDB:', displayName);
                        return;
                    } else {
                        // Blob not found in cache — fall through to manifest match
                        console.warn('[Main] Uploaded avatar not found in IndexedDB cache, falling back to manifest');
                    }
                })();
                // Don't return here — the async callback will handle it.
                // Fall through to manifest match or default if cache miss.
            } else {
                // Match by filename first (more reliable across manifest changes)
                const fileIdx = avatarItems.findIndex((x) => x.file === savedFile);
                if (fileIdx >= 0) {
                    const select = $('avatar-select');
                    if (select) select.value = String(fileIdx);
                    loadAvatar(avatarItems[fileIdx].url, 'manifest(persisted)', avatarItems[fileIdx].name);
                    console.log('[Main] Restored persisted avatar:', avatarItems[fileIdx].name, 'at index', fileIdx);
                    return;
                }
            }
        }
        if (Number.isFinite(savedIdx) && avatarItems[savedIdx]) {
            const select = $('avatar-select');
            if (select) select.value = String(savedIdx);
            loadAvatar(avatarItems[savedIdx].url, 'manifest(persisted)', avatarItems[savedIdx].name);
            console.log('[Main] Restored persisted avatar by index:', savedIdx);
            return;
        }
    } catch (_) { }

    loadAvatar(avatarItems[0].url, 'manifest(default)', avatarItems[0].name);
}

/* ============================
   Animation Control
   ============================ */
function findIdleAnimation() {
    const keys = Object.keys(animations);
    return keys.find((k) => k.includes('idle')) || keys[0] || null;
}

function playAnimation(name, loop) {
    if (
        window.__USE_GLTF_VIEWER_ENGINE__ &&
        window.NEXUS_VIEWER &&
        typeof window.NEXUS_VIEWER.playAnimationByName === 'function'
    ) {
        window.NEXUS_VIEWER.playAnimationByName(name);
        return;
    }

    const key = (name || '').toLowerCase();
    if (!mixer || !animations[key]) {
        logWarn(`Animation "${key}" not found; falling back to idle/first.`);
        const fallback = findIdleAnimation();
        if (!fallback || !mixer || !animations[fallback]) return;
        name = fallback;
    } else {
        name = key;
    }

    if (currentAnimationAction) currentAnimationAction.fadeOut(0.2);

    const clip = animations[name];
    const action = mixer.clipAction(clip);

    action.reset();
    action.fadeIn(0.2);
    action.setLoop(loop ? THREE.LoopRepeat : THREE.LoopOnce);
    action.clampWhenFinished = true;
    action.play();

    currentAnimationAction = action;

    if (!loop) {
        setTimeout(
            () => {
                const idleKey = findIdleAnimation();
                if (idleKey) playAnimation(idleKey, true);
            },
            Math.max(0, (clip.duration - 0.2) * 1000)
        );
    }
}

/* =========================================================
   Speech Settings UI & Logic
   ========================================================= */

// Heuristic to guess gender from voice name
function guessGender(voice) {
    const s = `${voice.name} ${voice.voiceURI}`.toLowerCase();
    // Common patterns across OS/browsers (not perfect, but helpful)
    if (
        /(female|woman|zira|susan|samantha|victoria|tessa|karen|serena|monica|lucia|alice|emma|olivia|google us english)/i.test(
            s
        )
    )
        return 'female';
    if (/(male|man|david|mark|daniel|george|alex|fred|tom|diego|luca|paul|joel)/i.test(s)) return 'male';
    return 'unknown';
}

function pickBestVoice() {
    const voices = window.speechSynthesis?.getVoices?.() || [];
    if (!voices.length) return null;

    const targetLang = (SpeechSettings.lang || 'en-US').toLowerCase();
    const base = targetLang.split('-')[0];
    const pref = (SpeechSettings.voicePref || 'any').toLowerCase();

    // 1) exact voiceURI preference
    if (SpeechSettings.voiceURI) {
        const exact = voices.find((v) => v.voiceURI === SpeechSettings.voiceURI);
        if (exact) return exact;
    }

    // 2) Exact language match
    let candidates = voices.filter((v) => (v.lang || '').toLowerCase() === targetLang);
    if (!candidates.length) {
        // 3) Base language match
        candidates = voices.filter((v) => (v.lang || '').toLowerCase().startsWith(base));
    }
    // Fallback: all voices if no lang match (rare, but possible)
    if (!candidates.length) candidates = voices;

    // 4) Apply Gender Preference
    if (pref === 'female' || pref === 'male') {
        const preferred = candidates.filter((v) => guessGender(v) === pref);
        if (preferred.length) return preferred[0];
    }

    // 5) Default best match
    return candidates[0] || null;
}

function refreshVoiceList() {
    const voiceEl = document.getElementById('speech-voice');
    if (!voiceEl || !('speechSynthesis' in window)) return;

    const voices = window.speechSynthesis.getVoices() || [];
    const lang = (SpeechSettings.lang || 'en-US').toLowerCase();
    const base = lang.split('-')[0];
    const genderPref = (SpeechSettings.voicePref || 'any').toLowerCase();

    // Filter by language base to keep list relevant
    let filtered = voices.filter((v) => (v.lang || '').toLowerCase().startsWith(base));
    const list = filtered.length ? filtered : voices;

    // ✅ Filter by gender preference
    let genderFiltered = list;
    if (genderPref === 'female' || genderPref === 'male') {
        const byGender = list.filter((v) => guessGender(v) === genderPref);
        if (byGender.length) {
            genderFiltered = byGender;
        }
    }

    voiceEl.innerHTML = `<option value="">Auto (best match)</option>`;
    for (const v of genderFiltered) {
        const opt = document.createElement('option');
        opt.value = v.voiceURI;
        const gender = guessGender(v);
        const genderLabel = gender !== 'unknown' ? ` [${gender}]` : '';
        opt.textContent = `${v.name}${genderLabel} — ${v.lang}`;
        voiceEl.appendChild(opt);
    }

    // restore selection
    voiceEl.value = SpeechSettings.voiceURI || '';
}

function saveSpeechSettingsFromUI() {
    const langEl = document.getElementById('speech-lang');
    const voiceEl = document.getElementById('speech-voice');
    const prefEl = document.getElementById('speech-voice-pref');
    const rateEl = document.getElementById('speech-rate');
    const pitchEl = document.getElementById('speech-pitch');

    if (langEl) {
        SpeechSettings.lang = langEl.value || 'en-US';
        localStorage.setItem('speech_lang', SpeechSettings.lang);
    }
    if (voiceEl) {
        SpeechSettings.voiceURI = voiceEl.value || '';
        localStorage.setItem('speech_voice_uri', SpeechSettings.voiceURI);
    }
    if (prefEl) {
        SpeechSettings.voicePref = prefEl.value || 'any';
        localStorage.setItem('speech_voice_pref', SpeechSettings.voicePref);
    }
    if (rateEl) {
        const v = parseFloat(rateEl.value || '0.9');
        SpeechSettings.rate = Number.isFinite(v) ? v : 0.9;
        localStorage.setItem('speech_rate', String(SpeechSettings.rate));
    }
    if (pitchEl) {
        const v = parseFloat(pitchEl.value || '1.0');
        SpeechSettings.pitch = Number.isFinite(v) ? v : 1.0;
        localStorage.setItem('speech_pitch', String(SpeechSettings.pitch));
    }

    // Save TTS engine + Piper voice settings
    const engineEl = document.getElementById('tts-engine');
    const piperVoiceEl = document.getElementById('piper-voice');
    if (engineEl && window.TTSProvider) {
        window.TTSProvider.setEngine(engineEl.value);
        _togglePiperVoiceUI(engineEl.value);
    }
    if (piperVoiceEl && window.PiperWasmTTSProvider) {
        window.PiperWasmTTSProvider.setSelectedVoice(piperVoiceEl.value);
    }

    // Apply to recognition immediately if running
    if (recognition) recognition.lang = SpeechSettings.lang;

    // Also save to unified nexus_settings_v1 for VR compatibility
    if (window.SpeechService) {
        // Resolve the selected voice object so we can store BOTH name and URI
        const voices = window.speechSynthesis?.getVoices?.() || [];
        const selectedVoiceObj = SpeechSettings.voiceURI
            ? voices.find((v) => v.voiceURI === SpeechSettings.voiceURI)
            : null;

        window.SpeechService.saveTTSConfig({
            // ✅ Store NAME here (what legacy VR logic expects)
            speechVoice: selectedVoiceObj?.name || '',

            // ✅ Store URI explicitly (best identifier)
            speechVoiceURI: SpeechSettings.voiceURI || '',

            // ✅ Store voice preference (gender filter)
            speechVoicePref: SpeechSettings.voicePref || 'any',

            speechRate: SpeechSettings.rate,
            speechPitch: SpeechSettings.pitch,
            speechVolume: 1.0, // Default volume (not exposed in UI yet)
            speechLang: SpeechSettings.lang,
            ttsEnabled: true, // Default enabled (not exposed in UI yet)
        });
    }
}

function loadSpeechSettingsIntoUI() {
    const langEl = document.getElementById('speech-lang');
    const voiceEl = document.getElementById('speech-voice');
    const prefEl = document.getElementById('speech-voice-pref');
    const rateEl = document.getElementById('speech-rate');
    const pitchEl = document.getElementById('speech-pitch');

    if (langEl) langEl.value = SpeechSettings.lang;
    if (prefEl) prefEl.value = SpeechSettings.voicePref || 'any';
    if (rateEl) rateEl.value = String(SpeechSettings.rate);
    if (pitchEl) pitchEl.value = String(SpeechSettings.pitch);

    if (voiceEl) voiceEl.value = SpeechSettings.voiceURI || '';

    // Restore TTS engine + Piper voice
    const engineEl = document.getElementById('tts-engine');
    const piperVoiceEl = document.getElementById('piper-voice');
    const savedEngine = localStorage.getItem('tts_engine') || 'web-speech-api';
    if (engineEl) engineEl.value = savedEngine;
    if (piperVoiceEl) piperVoiceEl.value = localStorage.getItem('piper_voice') || 'en_US-lessac-medium';
    _togglePiperVoiceUI(savedEngine);
}

/** Show/hide Piper vs Web Speech API voice controls, and populate Piper voices for current language. */
function _togglePiperVoiceUI(engine) {
    const isPiper = engine === 'piper-wasm';
    const piperGroup = document.getElementById('piper-voice-group');
    if (piperGroup) piperGroup.style.display = isPiper ? '' : 'none';

    // Hide Web Speech API VOICE dropdown when Piper is active (not needed)
    // Keep VOICE PREFERENCE visible — it filters Piper voices by gender too
    const webVoiceEl = document.getElementById('speech-voice');
    if (webVoiceEl && webVoiceEl.closest('.input-group')) {
        webVoiceEl.closest('.input-group').style.display = isPiper ? 'none' : '';
    }

    if (isPiper) _refreshPiperVoiceList();
}

/** Populate the Piper voice dropdown filtered by the current language. */
function _refreshPiperVoiceList() {
    const piperVoiceEl = document.getElementById('piper-voice');
    if (!piperVoiceEl || !window.PiperWasmTTSProvider) return;

    const langEl = document.getElementById('speech-lang');
    const lang = (langEl ? langEl.value : SpeechSettings.lang) || 'en-US';
    const base = lang.split('-')[0].toLowerCase(); // "en", "es", "fr", etc.

    const allVoices = window.PiperWasmTTSProvider.getVoices();

    // Filter: exact lang match first, then base match (e.g. es-ES also shows es-MX)
    let filtered = allVoices.filter((v) => v.lang.toLowerCase() === lang.toLowerCase());
    if (!filtered.length) {
        filtered = allVoices.filter((v) => v.lang.toLowerCase().startsWith(base));
    }

    // Fallback: show all English if no voices match the language (e.g. ja-JP, ko-KR)
    const noVoicesForLang = !filtered.length;
    if (noVoicesForLang) {
        filtered = allVoices.filter((v) => v.lang.startsWith('en-'));
    }

    // Apply gender preference filter
    const prefEl = document.getElementById('speech-voice-pref');
    const genderPref = (prefEl ? prefEl.value : SpeechSettings.voicePref || 'any').toLowerCase();
    if (genderPref === 'female' || genderPref === 'male') {
        const byGender = filtered.filter((v) => v.gender === genderPref);
        if (byGender.length) {
            filtered = byGender;
        }
        // If no voices match the gender, keep all (don't empty the list)
    }

    // Build options
    const saved = localStorage.getItem('piper_voice') || '';
    piperVoiceEl.innerHTML = '';

    if (noVoicesForLang) {
        const warn = document.createElement('option');
        warn.value = '';
        warn.textContent = '⚠ No Piper voices for ' + lang + ' — showing English';
        warn.disabled = true;
        piperVoiceEl.appendChild(warn);
    }

    let hasSelected = false;
    for (const v of filtered) {
        const opt = document.createElement('option');
        opt.value = v.id;
        const gLabel = v.gender !== 'unknown' ? ' [' + v.gender + ']' : '';
        const qLabel = v.quality === 'low' ? ' ⚡' : v.quality === 'high' ? ' ★' : '';
        opt.textContent = v.name + gLabel + qLabel;
        if (v.id === saved) {
            opt.selected = true;
            hasSelected = true;
        }
        piperVoiceEl.appendChild(opt);
    }

    // If saved voice not in filtered list, select first
    if (!hasSelected && piperVoiceEl.options.length) {
        const firstValid = [...piperVoiceEl.options].find((o) => !o.disabled);
        if (firstValid) {
            firstValid.selected = true;
            window.PiperWasmTTSProvider.setSelectedVoice(firstValid.value);
        }
    }

    console.log(
        '[PiperVoiceList] lang:',
        lang,
        '| gender:',
        genderPref,
        '| voices:',
        filtered.length,
        '| selected:',
        piperVoiceEl.value
    );
}

/* ============================
   STT Settings Helpers
   ============================ */
function loadSTTSettingsIntoUI() {
    if (!window.SpeechService) return;

    const sttConfig = window.SpeechService.getSTTConfig();

    const sttProvider = $('stt-provider');
    const wasmModelSize = $('wasm-model-size');
    const openaiWhisperModel = $('openai-whisper-model');
    const openaiSTTKey = $('openai-stt-key');
    const googleSTTKey = $('google-stt-key');
    const googleSTTModel = $('google-stt-model');
    const sttLanguage = $('stt-language');
    const sttInterimResults = $('stt-interim-results');
    const sttMicrophone = $('stt-microphone');

    if (sttProvider) sttProvider.value = sttConfig.provider;
    if (wasmModelSize) wasmModelSize.value = sttConfig.wasm.modelSize;
    if (openaiWhisperModel) openaiWhisperModel.value = sttConfig.openai.model;
    if (openaiSTTKey) openaiSTTKey.value = sttConfig.openai.apiKey;
    if (googleSTTKey) googleSTTKey.value = sttConfig.google.apiKey;
    if (googleSTTModel) googleSTTModel.value = sttConfig.google.model;
    if (sttLanguage) sttLanguage.value = sttConfig.language;
    if (sttInterimResults) sttInterimResults.checked = sttConfig.interimResults;
    if (sttMicrophone && sttConfig.microphoneDeviceId) sttMicrophone.value = sttConfig.microphoneDeviceId;

    // Load speaker device setting
    const ttsSpeaker = $('tts-speaker');
    if (ttsSpeaker) {
        ttsSpeaker.value = localStorage.getItem('foveai_speaker_device_id') || '';
    }

    // Auto-send setting
    const sttAutoSend = $('stt-auto-send');
    if (sttAutoSend) {
        sttAutoSend.checked = SpeechSettings.autoSend;
        sttAutoSend.addEventListener('change', () => {
            SpeechSettings.autoSend = sttAutoSend.checked;
            localStorage.setItem('stt_auto_send', sttAutoSend.checked ? 'true' : 'false');
            console.log('[Main] Auto-send', sttAutoSend.checked ? 'enabled' : 'disabled');
        });
    }

    // Show confidence notifications setting
    const sttShowConfidence = $('stt-show-confidence');
    if (sttShowConfidence) {
        sttShowConfidence.checked = SpeechSettings.showConfidence;
        sttShowConfidence.addEventListener('change', () => {
            SpeechSettings.showConfidence = sttShowConfidence.checked;
            localStorage.setItem('stt_show_confidence', sttShowConfidence.checked ? 'true' : 'false');
            console.log('[Main] Confidence notifications', sttShowConfidence.checked ? 'enabled' : 'disabled');
        });
    }

    // Update provider-specific UI
    updateSTTProviderUI(sttConfig.provider);
}

function saveSTTSettingsFromUI() {
    if (!window.SpeechService) return;

    const sttProvider = $('stt-provider');
    const wasmModelSize = $('wasm-model-size');
    const openaiWhisperModel = $('openai-whisper-model');
    const openaiSTTKey = $('openai-stt-key');
    const googleSTTKey = $('google-stt-key');
    const googleSTTModel = $('google-stt-model');
    const sttLanguage = $('stt-language');
    const sttInterimResults = $('stt-interim-results');
    const sttMicrophone = $('stt-microphone');
    const ttsSpeaker = $('tts-speaker');

    // Save and apply speaker output routing
    if (ttsSpeaker) {
        const storedSpeaker = ttsSpeaker.value || '';
        localStorage.setItem('foveai_speaker_device_id', storedSpeaker);
        if (typeof window.applyAudioOutputDevice === 'function') {
            window.applyAudioOutputDevice(storedSpeaker);
        }
    }

    window.SpeechService.saveSTTConfig({
        provider: sttProvider ? sttProvider.value : 'webspeech',
        language: sttLanguage ? sttLanguage.value : 'en-US',
        interimResults: sttInterimResults ? sttInterimResults.checked : true,
        microphoneDeviceId: sttMicrophone ? sttMicrophone.value : '',
        wasm: {
            modelSize: wasmModelSize ? wasmModelSize.value : 'base',
        },
        openai: {
            apiKey: openaiSTTKey ? openaiSTTKey.value.trim() : '',
            model: openaiWhisperModel ? openaiWhisperModel.value : 'whisper-1',
        },
        google: {
            apiKey: googleSTTKey ? googleSTTKey.value.trim() : '',
            model: googleSTTModel ? googleSTTModel.value : 'default',
        },
    });

    // Update recognition options
    window.SpeechService.setRecognitionOptions({
        lang: sttLanguage ? sttLanguage.value : 'en-US',
        interimResults: sttInterimResults ? sttInterimResults.checked : true,
    });
}

function updateSTTProviderUI(provider) {
    const wasmSTTSettings = $('wasm-stt-settings');
    const openaiSTTSettings = $('openai-stt-settings');
    const googleSTTSettings = $('google-stt-settings');

    // Hide all provider-specific settings
    if (wasmSTTSettings) wasmSTTSettings.style.display = 'none';
    if (openaiSTTSettings) openaiSTTSettings.style.display = 'none';
    if (googleSTTSettings) googleSTTSettings.style.display = 'none';

    // Show relevant provider settings
    switch (provider) {
        case 'wasm':
            if (wasmSTTSettings) wasmSTTSettings.style.display = 'block';
            break;
        case 'openai':
            if (openaiSTTSettings) openaiSTTSettings.style.display = 'block';
            break;
        case 'google':
            if (googleSTTSettings) googleSTTSettings.style.display = 'block';
            break;
    }
}

async function testSTT() {
    if (!window.SpeechService) {
        showMessage('Speech service not available', 'error');
        return;
    }

    const statusElement = $('test-stt-status');

    try {
        if (statusElement) {
            statusElement.textContent = 'Starting STT test...';
            statusElement.style.color = '#3b82f6';
        }

        // Start STT with test callbacks
        const started = await window.SpeechService.startSTT({
            onStart: () => {
                if (statusElement) {
                    statusElement.textContent = '🎤 Listening... (speak now)';
                    statusElement.style.color = '#10b981';
                }
            },
            onInterim: (interimText) => {
                if (statusElement) {
                    statusElement.textContent = `📝 Interim: "${interimText}"`;
                    statusElement.style.color = '#f59e0b';
                }
            },
            onResult: (transcript, confidence) => {
                const confidencePercent = Math.round(confidence * 100);
                if (statusElement) {
                    statusElement.textContent = `✅ Transcribed: "${transcript}" (${confidencePercent}% confidence)`;
                    statusElement.style.color = '#10b981';
                }
                console.log('[STT Test] Result:', transcript);

                // Show success message
                setTimeout(() => {
                    if (statusElement) {
                        statusElement.textContent = 'Test completed successfully!';
                    }
                }, 2000);
            },
            onError: (error, context) => {
                const errorMsg = context ? `${error}: ${context}` : error;
                if (statusElement) {
                    statusElement.textContent = `❌ Error: ${errorMsg}`;
                    statusElement.style.color = '#ef4444';
                }
                console.error('[STT Test] Error:', error, context);
            },
            onEnd: () => {
                console.log('[STT Test] Recognition ended');
            },
        });

        if (!started) {
            throw new Error('Failed to start STT');
        }

        // Auto-stop after 10 seconds
        setTimeout(() => {
            if (window.SpeechService.isRecognizing) {
                window.SpeechService.stopSTT();
                if (statusElement) {
                    statusElement.textContent = 'Test timeout (10s limit)';
                    statusElement.style.color = '#f59e0b';
                }
            }
        }, 10000);
    } catch (error) {
        console.error('[STT Test] Failed:', error);
        if (statusElement) {
            statusElement.textContent = `❌ Failed: ${error.message}`;
            statusElement.style.color = '#ef4444';
        }
    }
}

/**
 * Load available microphones into the selector
 */
async function loadAvailableMicrophones() {
    const microphoneSelect = $('stt-microphone');
    if (!microphoneSelect) return;

    try {
        console.log('[Main] Loading available microphones...');

        // Request microphone permission first (required for device labels)
        await navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
            // Stop the stream immediately, we just needed permission
            stream.getTracks().forEach((track) => track.stop());
        });

        // Enumerate devices
        const devices = await navigator.mediaDevices.enumerateDevices();
        const audioInputs = devices.filter((device) => device.kind === 'audioinput');

        console.log(`[Main] Found ${audioInputs.length} microphones`);

        // Clear existing options (except default)
        microphoneSelect.innerHTML = '<option value="">Default (System Default)</option>';

        // Add microphone options
        audioInputs.forEach((device, index) => {
            const option = document.createElement('option');
            option.value = device.deviceId;
            option.textContent = device.label || `Microphone ${index + 1}`;
            microphoneSelect.appendChild(option);
        });

        // Load selected microphone from config
        if (window.SpeechService) {
            const sttConfig = window.SpeechService.getSTTConfig();
            if (sttConfig.microphoneDeviceId) {
                microphoneSelect.value = sttConfig.microphoneDeviceId;
            }
        }

        console.log('[Main] Microphones loaded successfully');
    } catch (error) {
        console.error('[Main] Failed to load microphones:', error);
        // If permission denied, show a helpful message
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'Permission denied - click to allow microphone access';
        microphoneSelect.innerHTML = '';
        microphoneSelect.appendChild(option);
    }

    // Chain loading available speakers (output devices)
    try {
        await loadAvailableSpeakers();
    } catch (e) {
        console.warn('[Main] Failed to auto-load speakers:', e);
    }
}

/**
 * Load available audio output devices (speakers/headphones)
 */
async function loadAvailableSpeakers() {
    const speakerSelect = $('tts-speaker');
    if (!speakerSelect) return;

    try {
        console.log('[Main] Loading available audio output devices (speakers)...');

        // Enumerate devices
        const devices = await navigator.mediaDevices.enumerateDevices();
        const audioOutputs = devices.filter((device) => device.kind === 'audiooutput');

        console.log(`[Main] Found ${audioOutputs.length} audio output devices`);

        // Clear existing options
        speakerSelect.innerHTML = '<option value="">Default (System Default)</option>';

        audioOutputs.forEach((device, index) => {
            const option = document.createElement('option');
            option.value = device.deviceId;
            option.textContent = device.label || `Speaker/Headphones ${index + 1}`;
            speakerSelect.appendChild(option);
        });

        // Load selected speaker from localStorage
        const storedSpeaker = localStorage.getItem('foveai_speaker_device_id');
        if (storedSpeaker) {
            speakerSelect.value = storedSpeaker;
            window.applyAudioOutputDevice(storedSpeaker);
        }

        console.log('[Main] Speakers loaded successfully');
    } catch (error) {
        console.error('[Main] Failed to load speakers:', error);
    }
}

/**
 * Apply selected audio output device to AudioContext and persistent TTS Audio element
 */
window.applyAudioOutputDevice = function(deviceId) {
    localStorage.setItem('foveai_speaker_device_id', deviceId || '');

    // Apply to persistent TTS element
    const ttsAudio = window.NEXUS_TTS_AUDIO;
    if (ttsAudio && typeof ttsAudio.setSinkId === 'function') {
        ttsAudio.setSinkId(deviceId || '')
            .then(() => console.log('[AudioOutput] Routed TTS to device:', deviceId || 'Default'))
            .catch(err => console.error('[AudioOutput] Failed to route TTS:', err));
    }

    // Apply to Web Audio Context
    const audioCtx = window.foveaiAudioContext;
    if (audioCtx && typeof audioCtx.setSinkId === 'function') {
        audioCtx.setSinkId(deviceId || '')
            .then(() => console.log('[AudioOutput] Routed Web Audio Context to device:', deviceId || 'Default'))
            .catch(err => console.error('[AudioOutput] Failed to route Web Audio Context:', err));
    }
};

/* ============================
   UI / Events
   ============================ */
function setEmotionPressed(btn) {
    document.querySelectorAll('.emotion-btn').forEach((b) => b.setAttribute('aria-pressed', 'false'));
    if (btn) btn.setAttribute('aria-pressed', 'true');
}

function setupEventListeners() {
    // Clear chat input on load (prevents browser autocomplete filling stale text)
    const chatInput = $('speech-text');
    if (chatInput) {
        chatInput.value = '';
        // Mobile browsers (Chrome Android, Safari iOS) ignore autocomplete="off"
        // on standard text inputs. Setting a non-standard value forces them to
        // skip their built-in autofill (address, email, name suggestions).
        chatInput.setAttribute('autocomplete', 'one-time-code');
    }

    const avatarSelect = $('avatar-select');
    if (avatarSelect) {
        avatarSelect.addEventListener('change', (e) => {
            const idx = parseInt(e.target.value, 10);
            if (!Number.isFinite(idx)) return;
            if (!avatarItems[idx]) return;
            // Persist chosen avatar so it survives navigation to settings/manager
            try {
                localStorage.setItem('nexus_selected_avatar_idx', String(idx));
                localStorage.setItem('nexus_selected_avatar_file', avatarItems[idx].file || '');
            } catch (_) { }
            loadAvatar(avatarItems[idx].url, 'manifest', avatarItems[idx].name);
        });
    }

    const avatarUpload = $('avatar-upload');
    if (avatarUpload) {
        avatarUpload.addEventListener('change', async (e) => {
            const file = e.target.files && e.target.files[0];
            if (!file) return;

            const fileName = file.name.toLowerCase();
            const ext = fileName.split('.').pop();

            if (ext !== 'glb' && ext !== 'gltf' && ext !== 'vrm') {
                showMessage('Please upload a .glb, .gltf, or .vrm file', 'error');
                e.target.value = '';
                return;
            }

            if (ext === 'gltf') {
                showMessage(
                    'Warning: .gltf files with external assets may not load correctly. .glb is recommended.',
                    'warning'
                );
            }

            if (ext === 'vrm') {
                console.log('[Main] VRM file detected — loading via VRMLoader path');
            }

            // Store the uploaded blob in IndexedDB for persistence across page reloads
            const uploadKey = 'upload:' + file.name;
            try {
                const dbReq = indexedDB.open('vrm_avatar_cache', 1);
                dbReq.onupgradeneeded = (evt) => {
                    const db = evt.target.result;
                    if (!db.objectStoreNames.contains('avatars')) {
                        db.createObjectStore('avatars');
                    }
                };
                dbReq.onsuccess = () => {
                    const db = dbReq.result;
                    const tx = db.transaction('avatars', 'readwrite');
                    tx.objectStore('avatars').put({ blob: file, format: ext }, uploadKey);
                    tx.oncomplete = () => {
                        console.log('[Main] Uploaded avatar cached in IndexedDB:', uploadKey);
                    };
                };
            } catch (_) {
                console.warn('[Main] Failed to cache uploaded avatar in IndexedDB');
            }

            const blobURL = URL.createObjectURL(file);

            // Add to avatarItems so it appears in the dropdown selector
            const displayName = file.name.replace(/\.\w+$/, '');
            const newIdx = avatarItems.length;
            avatarItems.push({
                name: displayName,
                file: uploadKey,
                url: blobURL,
                format: ext,
                _uploaded: true,
            });

            // Update the dropdown selector
            populateAvatarSelect(avatarItems);
            const select = $('avatar-select');
            if (select) select.value = String(newIdx);

            // Persist selection so it survives page reload
            try {
                localStorage.setItem('nexus_selected_avatar_idx', String(newIdx));
                localStorage.setItem('nexus_selected_avatar_file', uploadKey);
            } catch (_) { }

            loadAvatar(blobURL, 'upload', displayName);
        });
    }

    const speechText = $('speech-text');
    const speakBtn = $('speak-btn');
    if (speakBtn && speechText) {
        speakBtn.addEventListener('click', () => {
            const text = speechText.value.trim();
            if (!text) return;
            handleUserMessage(text);
            speechText.value = '';
        });

        speechText.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                const text = speechText.value.trim();
                if (!text) return;
                handleUserMessage(text);
                speechText.value = '';
            }
        });
    }

    const listenBtn = $('listen-btn');
    if (listenBtn) listenBtn.addEventListener('click', toggleVoiceInput);

    document.querySelectorAll('.emotion-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
            const emotion = (btn.dataset.emotion || '').toLowerCase();

            /* Route through AnimationManager for proper durations */
            if (window.NEXUS_ANIMATION_MANAGER?.applyEmotion) {
                window.NEXUS_ANIMATION_MANAGER.applyEmotion(emotion);
            } else {
                try {
                    window.NEXUS_PROCEDURAL_ANIMATOR?.setMode?.(emotion, 5000);
                } catch (_) { }
            }
            const mapped = Object.keys(animations).find((k) => k.includes(emotion)) || findIdleAnimation();
            if (mapped) playAnimation(mapped, false);

            const emotionActive = $('emotion-active');
            if (emotionActive) emotionActive.textContent = emotion.toUpperCase();

            setEmotionPressed(btn);
            setStatus('idle', `FEELING ${emotion.toUpperCase()}`);
            setTimeout(() => setStatus('idle', 'READY'), 1500);
        });
    });

    // Emotion dropdown menu items in avatar footer
    document.querySelectorAll('.emotion-menu-item').forEach((btn) => {
        btn.addEventListener('click', () => {
            const emotion = (btn.dataset.emotion || '').toLowerCase();
            /* Route through AnimationManager for proper durations */
            if (window.NEXUS_ANIMATION_MANAGER?.applyEmotion) {
                window.NEXUS_ANIMATION_MANAGER.applyEmotion(emotion);
            } else {
                try {
                    window.NEXUS_PROCEDURAL_ANIMATOR?.setMode?.(emotion, 5000);
                } catch (_) { }
            }
            const mapped = Object.keys(animations).find((k) => k.includes(emotion)) || findIdleAnimation();
            if (mapped) playAnimation(mapped, false);
            if (window.setEmotionIcon) window.setEmotionIcon(emotion);
            setStatus('idle', `FEELING ${emotion.toUpperCase()}`);
            setTimeout(() => setStatus('idle', 'READY'), 1500);
        });
    });

    const clearBtn = $('clear-history');
    if (clearBtn) clearBtn.addEventListener('click', clearHistory);

    const settingsBtn = $('settings-btn');
    if (settingsBtn) settingsBtn.addEventListener('click', openSettings);

    const infoBtn = $('info-btn');
    if (infoBtn) infoBtn.addEventListener('click', openInfo);

    const resetBtn = $('reset-view-btn');
    if (resetBtn) resetBtn.addEventListener('click', () => resetView());

    const frameBtn = $('frame-avatar-btn');
    if (frameBtn)
        frameBtn.addEventListener(
            'click',
            () => currentAvatar && frameObjectToCamera(currentAvatar, lastFrameFitOffset)
        );

    // ── Face Tracking toggle ──
    const faceTrackBtn = $('face-track-btn');
    if (faceTrackBtn) {
        faceTrackBtn.addEventListener('click', () => {
            if (window.NEXUS_FACE_TRACKER) {
                if (window.NEXUS_FACE_TRACKER.isActive) {
                    window.NEXUS_FACE_TRACKER.stop();
                    faceTrackBtn.classList.remove('active');
                    faceTrackBtn.setAttribute('aria-pressed', 'false');
                } else {
                    window.NEXUS_FACE_TRACKER.start();
                    faceTrackBtn.classList.add('active');
                    faceTrackBtn.setAttribute('aria-pressed', 'true');
                }
            }
        });
    }

    // ── Tracking Settings panel toggle ──
    const trackingSettingsBtn = $('tracking-settings-btn');
    if (trackingSettingsBtn) {
        trackingSettingsBtn.addEventListener('click', () => {
            if (window.NEXUS_TRACKING_PANEL) {
                window.NEXUS_TRACKING_PANEL.toggle();
            }
        });
    }

    const readyBtn = $('ready-btn');
    if (readyBtn) {
        readyBtn.addEventListener('click', () => {
            setStatus('idle', 'READY');
            showMessage('Session started.', 'success');
        });
    }

    // --- SPEECH SETTINGS UI WIRING ---
    const langEl = document.getElementById('speech-lang');
    if (langEl) {
        langEl.addEventListener('change', () => {
            SpeechSettings.lang = langEl.value || 'en-US';
            localStorage.setItem('speech_lang', SpeechSettings.lang);

            // Changing language implies resetting voice specific URI to Auto (so we don't keep an English voice for Italian text)
            SpeechSettings.voiceURI = '';
            localStorage.setItem('speech_voice_uri', '');

            if (recognition) recognition.lang = SpeechSettings.lang;

            refreshVoiceList();
            _refreshPiperVoiceList(); // sync Piper voices to new language
            loadSpeechSettingsIntoUI();
        });
    }

    // Piper voice dropdown — apply selection immediately
    const piperVoiceDropdown = document.getElementById('piper-voice');
    if (piperVoiceDropdown) {
        piperVoiceDropdown.addEventListener('change', () => {
            if (window.PiperWasmTTSProvider) {
                window.PiperWasmTTSProvider.setSelectedVoice(piperVoiceDropdown.value);
            }
        });
    }

    const prefEl = document.getElementById('speech-voice-pref');
    if (prefEl) {
        prefEl.addEventListener('change', () => {
            SpeechSettings.voicePref = prefEl.value || 'any';
            localStorage.setItem('speech_voice_pref', SpeechSettings.voicePref);

            // ✅ Refresh voice list to show only matching gender
            refreshVoiceList();
            _refreshPiperVoiceList(); // sync Piper voices to gender preference
        });
    }

    const voiceEl = document.getElementById('speech-voice');
    if (voiceEl) {
        voiceEl.addEventListener('change', (e) => {
            SpeechSettings.voiceURI = e.target.value || '';
            localStorage.setItem('speech_voice_uri', SpeechSettings.voiceURI);
        });
    }

    document.getElementById('speech-rate')?.addEventListener('input', (e) => {
        const v = parseFloat(e.target.value || '0.9');
        SpeechSettings.rate = Number.isFinite(v) ? v : 0.9;
        localStorage.setItem('speech_rate', String(SpeechSettings.rate));
    });

    document.getElementById('speech-pitch')?.addEventListener('input', (e) => {
        const v = parseFloat(e.target.value || '1.0');
        SpeechSettings.pitch = Number.isFinite(v) ? v : 1.0;
        localStorage.setItem('speech_pitch', String(SpeechSettings.pitch));
    });

    // TEST VOICE BUTTON
    document.getElementById('test-tts')?.addEventListener('click', async () => {
        // Apply current TTS engine selection before testing (user may not have saved yet)
        const engineEl = document.getElementById('tts-engine');
        const piperVoiceEl = document.getElementById('piper-voice');
        if (engineEl && window.TTSProvider) {
            await window.TTSProvider.setEngine(engineEl.value);
        }
        if (piperVoiceEl && window.PiperWasmTTSProvider) {
            window.PiperWasmTTSProvider.setSelectedVoice(piperVoiceEl.value);
        }

        const sampleByLang = {
            'en-US': 'Hello! This is Nexus. Your voice settings are working.',
            'en-GB': 'Hello! This is Nexus. Voice test complete.',
            'it-IT': 'Ciao! Sono Nexus. Le impostazioni della voce funzionano.',
            'es-ES': '¡Hola! Soy Nexus. La configuración de voz funciona.',
            'fr-FR': 'Bonjour ! Je suis Nexus. Les paramètres de voix fonctionnent.',
            'de-DE': 'Hallo! Ich bin Nexus. Deine Spracheinstellungen funktionieren.',
            'pt-BR': 'Olá! Eu sou Nexus. O teste de voz funcionou.',
            'ja-JP': 'こんにちは、Nexusです。音声テストは成功しました。',
            'ko-KR': '안녕하세요, 넥서스입니다. 음성 설정이 작동 중입니다.',
        };
        // Apply rate/pitch/lang from UI fields (not yet saved)
        const rateEl = document.getElementById('speech-rate');
        const pitchEl = document.getElementById('speech-pitch');
        const langTestEl = document.getElementById('speech-lang');
        if (rateEl) SpeechSettings.rate = parseFloat(rateEl.value) || 0.9;
        if (pitchEl) SpeechSettings.pitch = parseFloat(pitchEl.value) || 1.0;
        if (langTestEl) SpeechSettings.lang = langTestEl.value || 'en-US';

        const sample = sampleByLang[SpeechSettings.lang] || 'Voice test successful.';
        console.log(
            '[TestVoice] engine:',
            engineEl?.value,
            '| piperVoice:',
            piperVoiceEl?.value,
            '| activeVoice:',
            window.PiperWasmTTSProvider?.getSelectedVoice?.(),
            '| lang:',
            SpeechSettings.lang,
            '| rate:',
            SpeechSettings.rate
        );
        speakText(sample);
    });

    // --- STT SETTINGS UI WIRING ---
    const sttProvider = document.getElementById('stt-provider');
    if (sttProvider) {
        sttProvider.addEventListener('change', (e) => {
            updateSTTProviderUI(e.target.value);
        });
    }

    const testSTTBtn = document.getElementById('test-stt');
    if (testSTTBtn) {
        testSTTBtn.addEventListener('click', () => {
            testSTT();
        });
    }

    const ttsSpeaker = document.getElementById('tts-speaker');
    if (ttsSpeaker) {
        ttsSpeaker.addEventListener('change', (e) => {
            if (typeof window.applyAudioOutputDevice === 'function') {
                window.applyAudioOutputDevice(e.target.value);
            }
        });
    }

    const refreshMicrophonesBtn = document.getElementById('refresh-microphones');
    if (refreshMicrophonesBtn) {
        refreshMicrophonesBtn.addEventListener('click', () => {
            loadAvailableMicrophones();
        });
    }

    // Load microphones on page load
    loadAvailableMicrophones();
}

/* ============================
   Modals
   ============================ */
function setupModals() {
    const settingsModal = $('settings-modal');
    const infoModal = $('info-modal');

    const closeSettings = $('close-settings');
    const closeInfo = $('close-info');
    const cancelSettings = $('cancel-settings');
    const saveSettingsBtn = $('save-settings');

    function hideModal(modal) {
        if (!modal) return;
        modal.classList.remove('active');
        modal.hidden = true;
    }

    if (closeSettings && settingsModal) closeSettings.addEventListener('click', () => hideModal(settingsModal));
    if (cancelSettings && settingsModal) cancelSettings.addEventListener('click', () => hideModal(settingsModal));
    if (saveSettingsBtn) saveSettingsBtn.addEventListener('click', saveSettings);

    if (closeInfo && infoModal) closeInfo.addEventListener('click', () => hideModal(infoModal));

    document.querySelectorAll('input[name="provider"]').forEach((radio) => {
        radio.addEventListener('change', updateProviderFields);
    });

    // Live preview: change desktop background immediately when radio is selected
    document.querySelectorAll('input[name="desktop-bg"]').forEach((radio) => {
        radio.addEventListener('change', () => {
            window.NEXUS_VIEWER?.setDesktopBackground(radio.value);
        });
    });

    // Live preview: toggle shadows immediately when radio is selected
    document.querySelectorAll('input[name="desktop-shadow"]').forEach((radio) => {
        radio.addEventListener('change', () => {
            window.NEXUS_VIEWER?.setShadows(radio.value === 'on');
        });
    });

    // Visual effects toggles — live preview (additive, non-destructive)
    const fxEnvMap = document.getElementById('fx-envmap');
    if (fxEnvMap) {
        fxEnvMap.addEventListener('change', () => {
            window.NEXUS_VIEWER?.setEnvironmentMap(fxEnvMap.checked);
        });
    }
    const fxBloom = document.getElementById('fx-bloom');
    if (fxBloom) {
        fxBloom.addEventListener('change', () => {
            window.NEXUS_VIEWER?.postProcessing?.setBloom(fxBloom.checked);
        });
    }
    const fxSsao = document.getElementById('fx-ssao');
    if (fxSsao) {
        fxSsao.addEventListener('change', () => {
            window.NEXUS_VIEWER?.postProcessing?.setSSAO(fxSsao.checked);
        });
    }
    const fxToneMapping = document.getElementById('fx-tonemapping');
    if (fxToneMapping) {
        fxToneMapping.addEventListener('change', () => {
            window.NEXUS_VIEWER?.setToneMapping(fxToneMapping.checked);
        });
    }

    if (settingsModal) {
        settingsModal.addEventListener('click', (e) => {
            if (e.target === settingsModal) hideModal(settingsModal);
        });
    }
    if (infoModal) {
        infoModal.addEventListener('click', (e) => {
            if (e.target === infoModal) hideModal(infoModal);
        });
    }
}

// =========================================================================
// Pose Normalizer Settings UI
// =========================================================================
function setupPoseNormalizerUI() {
    const pn = window.NEXUS_POSE_NORMALIZER;
    if (!pn) return;

    const s = pn.getSettings();

    // Global intensity slider — apply live as user drags
    const intensitySlider = document.getElementById('pose-intensity');
    const intensityVal = document.getElementById('pose-intensity-val');
    if (intensitySlider) {
        intensitySlider.value = s.intensity;
        if (intensityVal) intensityVal.textContent = s.intensity.toFixed(2);
        intensitySlider.addEventListener('input', () => {
            const v = parseFloat(intensitySlider.value);
            if (intensityVal) intensityVal.textContent = v.toFixed(2);
            // Apply intensity change live without requiring "Apply" button
            applyPoseSettingsLive();
        });
    }

    // Preset selector
    const presetSelect = document.getElementById('pose-preset');
    if (presetSelect) presetSelect.value = s.preset || 'naturalIdle';

    // Per-bone sliders
    document.querySelectorAll('.pose-bone-slider').forEach((slider) => {
        const bone = slider.dataset.bone;
        if (bone && s.bones[bone] != null) {
            slider.value = s.bones[bone];
        }
        const valSpan = document.getElementById('pose-bone-' + bone + '-val');
        if (valSpan) valSpan.textContent = parseFloat(slider.value).toFixed(2);
        slider.addEventListener('input', () => {
            if (valSpan) valSpan.textContent = parseFloat(slider.value).toFixed(2);
        });
    });

    // Apply Live button
    const applyBtn = document.getElementById('pose-apply-btn');
    if (applyBtn) {
        applyBtn.addEventListener('click', () => {
            applyPoseSettingsLive();
        });
    }

    // Reset Defaults button
    const resetBtn = document.getElementById('pose-reset-btn');
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            const defaults = pn.resetSettings();
            // Update UI to defaults
            if (intensitySlider) {
                intensitySlider.value = defaults.intensity;
                if (intensityVal) intensityVal.textContent = defaults.intensity.toFixed(2);
            }
            if (presetSelect) presetSelect.value = defaults.preset;
            document.querySelectorAll('.pose-bone-slider').forEach((sl) => {
                const bone = sl.dataset.bone;
                if (bone && defaults.bones[bone] != null) {
                    sl.value = defaults.bones[bone];
                    const vs = document.getElementById('pose-bone-' + bone + '-val');
                    if (vs) vs.textContent = defaults.bones[bone].toFixed(2);
                }
            });
            applyPoseSettingsLive();
        });
    }

    // Cross-sync: when Pose Studio or other systems change settings, update this UI
    window.addEventListener('pose-settings-changed', () => {
        loadPoseSettingsIntoUI();
    });

    // VR Pose Preset dropdown — uses VRPoseSystem (same as VR chat panel)
    // Requires pose mode coordination: stop clips, yield ProceduralAnimator,
    // enable autoUpdateHumanBones so normalized→raw bone sync works.
    const vrPoseSelect = document.getElementById('vr-pose-preset');
    if (vrPoseSelect) {
        vrPoseSelect.addEventListener('change', () => {
            const vps = window.vrPoseSystem;
            if (!vps || !vps.enabled) {
                console.warn('[Desktop] VRPoseSystem not available — load an avatar first');
                return;
            }

            // Enter pose mode: stop clips, yield ProceduralAnimator, enable bone sync
            try {
                window.NEXUS_CLIP_LOADER?.stopClip?.({ fadeOut: 0.25 });
            } catch (_) { }
            try {
                window.NEXUS_ANIMATION_RESOLVER?.stop?.();
            } catch (_) { }
            try {
                window.NEXUS_PROCEDURAL_ANIMATOR?.setPoseMode?.(true);
            } catch (_) { }
            try {
                const vrm = window.NEXUS_VIEWER?.avatarManager?._currentVRM;
                if (vrm && vrm.humanoid && 'autoUpdateHumanBones' in vrm.humanoid) {
                    vrm.humanoid.autoUpdateHumanBones = true;
                }
            } catch (_) { }

            vps.applyPreset(vrPoseSelect.value, 0.6);
            console.log(`[Desktop] VR pose preset → ${vrPoseSelect.value}`);
        });

        // Listen for VR-side pose changes to sync dropdown back
        window.addEventListener('vr-pose-changed', (e) => {
            if (e.detail && e.detail.preset) {
                vrPoseSelect.value = e.detail.preset;
            }
        });
    }
}

function collectPoseSettingsFromUI() {
    const patch = { bones: {} };
    const intensitySlider = document.getElementById('pose-intensity');
    if (intensitySlider) patch.intensity = parseFloat(intensitySlider.value);

    const presetSelect = document.getElementById('pose-preset');
    if (presetSelect) patch.preset = presetSelect.value;

    document.querySelectorAll('.pose-bone-slider').forEach((slider) => {
        const bone = slider.dataset.bone;
        if (bone) patch.bones[bone] = parseFloat(slider.value);
    });
    return patch;
}

function applyPoseSettingsLive() {
    const pn = window.NEXUS_POSE_NORMALIZER;
    if (!pn) return;

    const patch = collectPoseSettingsFromUI();
    pn.updateSettings(patch);

    // Re-apply pose to current avatar if loaded
    const vrm = window.vrmLoader?.currentVRM || window.NEXUS_VIEWER?.getCurrentVRM?.();
    if (vrm) {
        const root = vrm.scene || vrm;
        const np = window.NEXUS_NATURAL_POSE;
        const humanoid = vrm.humanoid || root.userData?.vrmHumanoid || null;

        // ── VRM path: use NaturalPosePlugin (industry-standard normalized bones)
        // This matches how VRoid Hub displays models in natural poses.
        if (np && humanoid && typeof humanoid.getNormalizedBoneNode === 'function') {
            np.reset();
            np.setPreset(patch.preset || 'naturalIdle');
            np.apply(root, { humanoid, preset: patch.preset });
        } else {
            // ── GLB fallback: world-space alignment via PoseNormalizer
            pn.restoreNeutralPose(root);
            pn.normalizeAvatarPose(root, {
                rig: humanoid,
            });
        }

        // Re-capture rest pose for ProceduralAnimator
        if (window.NEXUS_PROCEDURAL_ANIMATOR) {
            window.NEXUS_PROCEDURAL_ANIMATOR.registerAvatar(root, false);
        }
    }
}

function loadPoseSettingsIntoUI() {
    const pn = window.NEXUS_POSE_NORMALIZER;
    if (!pn) return;

    const s = pn.getSettings();
    const intensitySlider = document.getElementById('pose-intensity');
    const intensityVal = document.getElementById('pose-intensity-val');
    if (intensitySlider) {
        intensitySlider.value = s.intensity;
        if (intensityVal) intensityVal.textContent = s.intensity.toFixed(2);
    }

    const presetSelect = document.getElementById('pose-preset');
    if (presetSelect) presetSelect.value = s.preset || 'naturalIdle';

    document.querySelectorAll('.pose-bone-slider').forEach((slider) => {
        const bone = slider.dataset.bone;
        if (bone && s.bones[bone] != null) {
            slider.value = s.bones[bone];
            const valSpan = document.getElementById('pose-bone-' + bone + '-val');
            if (valSpan) valSpan.textContent = s.bones[bone].toFixed(2);
        }
    });
}

function openSettings() {
    const modal = $('settings-modal');
    if (!modal) {
        console.warn('[Main] #settings-modal not found in DOM');
        return;
    }

    console.log('[Main] Opening settings modal');

    try {
        // Load config + speech settings into UI whenever settings opens
        loadConfigIntoUI();
        loadSpeechSettingsIntoUI();
    } catch (e) {
        console.warn('[Main] Error loading config/speech into UI:', e);
    }

    // Wire TTS engine selector to toggle Piper voice controls live
    const ttsEngineEl = document.getElementById('tts-engine');
    if (ttsEngineEl && !ttsEngineEl._wired) {
        ttsEngineEl._wired = true;
        ttsEngineEl.addEventListener('change', () => _togglePiperVoiceUI(ttsEngineEl.value));
    }

    // Pre-select saved desktop background
    const savedBg = localStorage.getItem('desktop_bg') || 'black';
    const bgRadio = document.querySelector(`input[name="desktop-bg"][value="${savedBg}"]`);
    if (bgRadio) bgRadio.checked = true;

    // Pre-select saved shadow setting
    const savedShadow = localStorage.getItem('desktop_shadow') || 'off';
    const shadowRadio = document.querySelector(`input[name="desktop-shadow"][value="${savedShadow}"]`);
    if (shadowRadio) shadowRadio.checked = true;

    // Restore visual effects toggles from localStorage
    const fxFields = [
        { id: 'fx-envmap', key: 'fx_envmap' },
        { id: 'fx-bloom', key: 'fx_bloom' },
        { id: 'fx-ssao', key: 'fx_ssao' },
        { id: 'fx-tonemapping', key: 'fx_tonemapping' },
    ];
    for (const { id, key } of fxFields) {
        const el = document.getElementById(id);
        const saved = localStorage.getItem(key);
        if (el && saved !== null) el.checked = saved === 'true';
    }

    // Restore face tracking settings
    const ftModeSaved = localStorage.getItem('ft_mode') || 'imitate';
    const ftModeRadio = document.querySelector(`input[name="ft-mode"][value="${ftModeSaved}"]`);
    if (ftModeRadio) ftModeRadio.checked = true;

    // Show/hide imitate-only options based on mode
    const ftImitateOpts = document.getElementById('ft-imitate-options');
    if (ftImitateOpts) ftImitateOpts.style.display = ftModeSaved === 'imitate' ? '' : 'none';

    // Wire mode radio to show/hide imitate options live
    document.querySelectorAll('input[name="ft-mode"]').forEach((radio) => {
        radio.addEventListener('change', () => {
            if (ftImitateOpts) ftImitateOpts.style.display = radio.value === 'imitate' ? '' : 'none';
        });
    });

    const ftIndepEyes = document.getElementById('ft-independent-eyes');
    if (ftIndepEyes) {
        const saved = localStorage.getItem('ft_independent_eyes');
        ftIndepEyes.checked = saved === 'true';
    }

    try {
        loadSTTSettingsIntoUI();
    } catch (e) {
        console.warn('[Main] Error loading STT settings into UI:', e);
    }

    refreshVoiceList();

    // Load pose normalizer settings into UI
    try {
        loadPoseSettingsIntoUI();
    } catch (e) {
        console.warn('[Main] Error loading pose settings into UI:', e);
    }

    // Auto-refresh model list if stale (e.g. persona was unpublished)
    if (window._nexusLLM && window._nexusLLM.modelsStale) {
        const fetchBtn = document.getElementById('fetch-models-btn');
        if (fetchBtn) setTimeout(() => fetchBtn.click(), 300);
    }

    // Show the modal
    modal.classList.add('active');
    modal.hidden = false;
    console.log('[Main] Settings modal opened successfully');
}

function openInfo() {
    const modal = $('info-modal');
    if (!modal) return;
    modal.classList.add('active');
    modal.hidden = false;
}

/* ============================
   Provider UI + Storage
   ============================ */

/**
 * Fetch available models from LLMManager and populate dropdown
 * @param {string} provider - Provider name (openai, claude, etc.)
 * @param {HTMLSelectElement} selectElement - The select element to populate
 */
async function fetchAndPopulateModels(provider, selectElement) {
    if (!selectElement) {
        console.warn('[Main] Cannot fetch models: missing selectElement');
        return;
    }

    // Ensure LLMManager instance exists
    if (!window._nexusLLM) {
        if (typeof window.LLMManager !== 'function') {
            console.error('[Main] LLMManager not loaded');
            selectElement.innerHTML = '<option value="">LLMManager not loaded</option>';
            return;
        }
        console.log('[Main] Creating LLMManager instance for model fetching');
        window._nexusLLM = new window.LLMManager();
    }

    // Add loading option
    selectElement.innerHTML = '<option value="">Loading models...</option>';

    try {
        // Temporarily patch the LLMManager with UI values to fetch models
        // (User may have typed new values but not saved yet)
        const currentSettings = window._nexusLLM.getSettings();
        const originalSettings = JSON.parse(JSON.stringify(currentSettings)); // deep copy

        const apiKey = document.getElementById('api-key')?.value?.trim() || '';
        const baseUrl = document.getElementById('base-url')?.value?.trim() || '';

        const tempPatch = { provider: provider };
        if (provider === 'openai') {
            tempPatch.openai = { api_key: apiKey, base_url: baseUrl };
        } else if (provider === 'claude') {
            tempPatch.claude = { api_key: apiKey, base_url: baseUrl };
        } else if (provider === 'watsonx') {
            tempPatch.watsonx = { api_key: apiKey, base_url: baseUrl };
        } else if (provider === 'ollabridge') {
            tempPatch.ollabridge = { api_key: apiKey, base_url: baseUrl, auth_mode: 'local-trust' };
            // Enable proxy for local LLM — browser blocks direct fetch from port 8080 to port 8888
            tempPatch.proxy = { enable_proxy: true, proxy_url: '/api/proxy' };
        }

        window._nexusLLM.updateSettings(tempPatch);

        const result = await window._nexusLLM.fetchAvailableModels();

        // Restore original settings
        window._nexusLLM.updateSettings(originalSettings);

        if (result.error) {
            console.warn(`[Main] Model fetch warning: ${result.error}`);

            // Show error prominently if it's an authentication issue
            if (
                result.error.includes('401') ||
                result.error.includes('Authentication') ||
                result.error.includes('invalid')
            ) {
                alert(
                    `⚠️ ${provider.toUpperCase()} Authentication Error\n\n${result.error}\n\nPlease check your API key in Settings and try again.`
                );
            }
        }

        selectElement.innerHTML = '<option value="">Select a model...</option>';

        if (result.models && result.models.length > 0) {
            const nameMap = result.modelNames || {};

            // Deduplicate display names — add numeric suffix when the same
            // persona name appears more than once (e.g. "Lina (1)", "Lina (2)")
            const displayNames = result.models.map((m) => nameMap[m] || m.toUpperCase().replace(/-/g, ' '));
            const nameFreq = {};
            displayNames.forEach((n) => {
                nameFreq[n] = (nameFreq[n] || 0) + 1;
            });
            const nameCounter = {};

            result.models.forEach((m, i) => {
                const baseName = displayNames[i];
                let label = baseName;
                if (nameFreq[baseName] > 1) {
                    nameCounter[baseName] = (nameCounter[baseName] || 0) + 1;
                    label = `${baseName} (${nameCounter[baseName]})`;
                }
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = label;
                selectElement.appendChild(opt);
            });

            const statusMsg = result.error
                ? `⚠️ Loaded ${result.models.length} ${provider} models (using defaults due to error)`
                : `✅ Loaded ${result.models.length} ${provider} models`;
            console.log(`[Main] ${statusMsg}`);
        } else {
            selectElement.innerHTML = '<option value="">No models available</option>';
        }

        // Restore current selection if it exists
        if (config.model && result.models.includes(config.model)) {
            selectElement.value = config.model;
        }
    } catch (e) {
        console.error('[Main] Failed to fetch models:', e);
        selectElement.innerHTML = '<option value="">Error loading models</option>';
    }
}

function updateProviderFields() {
    const selected = document.querySelector('input[name="provider"]:checked');
    const provider = selected ? selected.value : 'none';

    const modelSelect = $('model-select');
    const apiKeyInput = $('api-key');
    const baseUrlInput = $('base-url');
    const watsonxRow = $('watsonx-project-row');
    const baseurlRow = $('baseurl-row');

    if (!modelSelect) return;
    modelSelect.innerHTML = '<option value="">Select a model...</option>';

    // Load provider-specific API key from unified settings
    try {
        const unified = localStorage.getItem('nexus_llm_settings');
        if (unified && apiKeyInput) {
            const settings = JSON.parse(unified);

            // Update API key field to show the correct provider's key
            if (provider === 'openai' && settings.openai?.api_key) {
                apiKeyInput.value = settings.openai.api_key;
                if (baseUrlInput) baseUrlInput.value = settings.openai.base_url || '';
            } else if (provider === 'claude' && settings.claude?.api_key) {
                apiKeyInput.value = settings.claude.api_key;
                if (baseUrlInput) baseUrlInput.value = settings.claude.base_url || '';
            } else if (provider === 'watsonx' && settings.watsonx?.api_key) {
                apiKeyInput.value = settings.watsonx.api_key;
                if (baseUrlInput) baseUrlInput.value = settings.watsonx.base_url || 'https://us-south.ml.cloud.ibm.com';
            } else if (provider === 'ollama') {
                apiKeyInput.value = ''; // Ollama doesn't need API key
                if (baseUrlInput) baseUrlInput.value = settings.ollama?.base_url || 'http://localhost:11434';
            } else if (provider === 'ollabridge' && settings.ollabridge) {
                apiKeyInput.value = settings.ollabridge.api_key || '';
                if (baseUrlInput) {
                    baseUrlInput.value = settings.ollabridge?.base_url || '';
                }
            } else {
                // No key saved for this provider, clear the field
                apiKeyInput.value = '';
                if (baseUrlInput) baseUrlInput.value = '';
            }
        } else if (apiKeyInput && !unified) {
            // No unified settings, check if current config matches this provider
            if (config.provider === provider) {
                apiKeyInput.value = config.apiKey || '';
                if (baseUrlInput) baseUrlInput.value = config.baseUrl || '';
            } else {
                // Different provider, clear the field
                apiKeyInput.value = '';
                if (baseUrlInput) baseUrlInput.value = '';
            }
        }
    } catch (e) {
        console.warn('[Main] Failed to load provider-specific API key:', e);
    }

    if (provider === 'watsonx') {
        if (watsonxRow) watsonxRow.style.display = 'block';
        if (baseurlRow) baseurlRow.style.display = 'block';

        // Updated Watsonx models (latest versions as of 2025/2026)
        [
            'ibm/granite-3-1-8b-instruct', // Updated from granite-3-8b-instruct
            'meta-llama/llama-3-3-70b-instruct', // Updated from llama-3-70b (3.3 offers 405B performance)
            'meta-llama/llama-3-1-8b-instruct', // Updated from llama-3-8b (3.1 has 128k context)
            'mistralai/mistral-large-2407', // Updated from mixtral-8x7b (Mistral Large 2 flagship)
            'mistralai/mistral-nemo', // New mid-sized model (12B)
        ].forEach((m) => {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m;
            modelSelect.appendChild(opt);
        });
        return;
    }

    if (watsonxRow) watsonxRow.style.display = 'none';
    if (baseurlRow) baseurlRow.style.display = provider === 'none' ? 'none' : 'block';
    const pairRowHide = $('ollabridge-pair-row');
    if (pairRowHide) pairRowHide.style.display = 'none';
    const authRowHide = $('ollabridge-auth-row');
    if (authRowHide) authRowHide.style.display = 'none';
    const remotePromptRow = $('ollabridge-remote-prompt-row');
    if (remotePromptRow) remotePromptRow.style.display = 'none';

    // Only fetch models if valid API key is present
    const currentKey = apiKeyInput ? apiKeyInput.value.trim() : '';
    const hasValidKey = currentKey && currentKey.length > 10;

    if (provider === 'openai' && hasValidKey) {
        // Only fetch if key looks valid (starts with sk-)
        if (currentKey.startsWith('sk-') && !currentKey.startsWith('sk-ant-')) {
            fetchAndPopulateModels('openai', modelSelect);
        } else {
            modelSelect.innerHTML =
                '<option value="">⚠️ Please enter a valid OpenAI API key (starts with "sk-") and save settings first</option>';
        }
    } else if (provider === 'claude' && hasValidKey) {
        // Only fetch if key looks valid (starts with sk-ant-)
        if (currentKey.startsWith('sk-ant-')) {
            fetchAndPopulateModels('claude', modelSelect);
        } else {
            modelSelect.innerHTML =
                '<option value="">⚠️ Please enter a valid Claude API key (starts with "sk-ant-") and save settings first</option>';
        }
    } else if (provider === 'ollabridge') {
        if (baseurlRow) baseurlRow.style.display = 'block';
        // Show auth mode dropdown for OllaBridge
        const authRow = $('ollabridge-auth-row');
        if (authRow) authRow.style.display = 'block';

        // Show remote prompt checkbox
        if (remotePromptRow) {
            remotePromptRow.style.display = 'block';
            // Load saved value
            try {
                const unified = JSON.parse(localStorage.getItem('nexus_llm_settings') || '{}');
                const cb = $('ollabridge-use-remote-prompt');
                if (cb) cb.checked = unified.ollabridge?.use_remote_prompt !== false;
            } catch (_) { }
        }

        // Show/hide correct fields based on current auth mode selection
        _updateOllaBridgeAuthUI();

        // Fetch models from OllaBridge gateway (includes HomePilot personas)
        const ollaKey = apiKeyInput ? apiKeyInput.value.trim() : '';
        // Also check for stored pair token or local-trust auth mode
        let hasPairToken = false;
        let isLocalTrust = false;
        try {
            const unified = JSON.parse(localStorage.getItem('nexus_llm_settings') || '{}');
            hasPairToken = !!(unified.ollabridge && unified.ollabridge.pair_token);
            isLocalTrust = unified.ollabridge?.auth_mode === 'local-trust';
        } catch (_) { }
        if (ollaKey || hasPairToken || isLocalTrust) {
            fetchAndPopulateModels('ollabridge', modelSelect);
        } else {
            modelSelect.innerHTML = '<option value="default">default</option>';
        }
    } else if (provider === 'openai' || provider === 'claude') {
        // No API key configured yet
        modelSelect.innerHTML = '<option value="">⚠️ Please enter your API key above and save settings first</option>';
    }
}

/**
 * Update the OllaBridge settings UI based on the selected auth mode dropdown.
 * Shows/hides fields dynamically: pairing code, API key, or just base URL.
 */
function _updateOllaBridgeAuthUI() {
    const authModeSelect = $('ollabridge-auth-mode');
    const authHint = $('ollabridge-auth-hint');
    const pairRow = $('ollabridge-pair-row');
    const apiKeyInput = $('api-key');
    const apiKeyRow = apiKeyInput ? apiKeyInput.closest('.input-group') : null;

    if (!authModeSelect) return;

    // Restore saved auth mode from settings
    try {
        const unified = JSON.parse(localStorage.getItem('nexus_llm_settings') || '{}');
        if (unified.ollabridge?.auth_mode) {
            authModeSelect.value = unified.ollabridge.auth_mode;
        }
    } catch (_) { }

    function applyAuthMode() {
        const mode = authModeSelect.value;

        if (mode === 'pairing') {
            // Device Pairing: show pair code row, hide API key
            if (pairRow) pairRow.style.display = 'block';
            if (apiKeyRow) apiKeyRow.style.display = 'none';
            if (authHint) {
                authHint.textContent = 'Enter the OllaBridge pairing code and click Pair.';
                authHint.style.color = '#888';
            }
        } else if (mode === 'apikey') {
            // API Key: show API key field, hide pair code
            if (pairRow) pairRow.style.display = 'none';
            if (apiKeyRow) apiKeyRow.style.display = 'block';
            if (authHint) {
                authHint.textContent = 'Enter your OllaBridge API key.';
                authHint.style.color = '#888';
            }
        } else if (mode === 'local-trust') {
            // Local Trust: hide both API key and pair code
            if (pairRow) pairRow.style.display = 'none';
            if (apiKeyRow) apiKeyRow.style.display = 'none';
            if (authHint) {
                authHint.textContent = 'No credentials needed — requests from localhost are trusted.';
                authHint.style.color = '#22c55e';
            }
        }
    }

    // Apply immediately
    applyAuthMode();

    // Re-apply on dropdown change
    authModeSelect.removeEventListener('change', applyAuthMode);
    authModeSelect.addEventListener('change', applyAuthMode);
}

function loadConfigIntoUI() {
    const providerRadio = document.querySelector(`input[name="provider"][value="${config.provider}"]`);
    if (providerRadio) {
        providerRadio.checked = true;
        updateProviderFields();
    }

    if ($('api-key')) $('api-key').value = config.apiKey;
    if ($('model-select')) $('model-select').value = config.model;
    if ($('system-prompt')) $('system-prompt').value = config.systemPrompt;
    if ($('watsonx-project-id')) $('watsonx-project-id').value = config.watsonxProjectId;
    if ($('base-url')) $('base-url').value = config.baseUrl;
}

function saveSettings() {
    const selected = document.querySelector('input[name="provider"]:checked');
    const provider = selected ? selected.value : 'none';

    const apiKey = ($('api-key') && $('api-key').value.trim()) || '';
    const model = ($('model-select') && $('model-select').value) || '';
    const systemPrompt = ($('system-prompt') && $('system-prompt').value) || config.systemPrompt;
    const watsonxProjectId = ($('watsonx-project-id') && $('watsonx-project-id').value) || '';
    const baseUrl = ($('base-url') && $('base-url').value) || '';

    if (provider !== 'none' && provider !== 'foveai_native' && provider !== 'ollama' && provider !== 'ollabridge' && !apiKey) {
        return showMessage('Please enter an API key', 'error');
    }
    if (provider !== 'none' && provider !== 'foveai_native' && !model) {
        return showMessage('Please select a model', 'error');
    }

    // Validate API key format matches provider
    if (apiKey) {
        if (provider === 'claude' && !apiKey.startsWith('sk-ant-')) {
            return showMessage(
                '❌ Invalid Claude API Key!\n\nClaude keys must start with "sk-ant-"\n\nYou entered a key starting with: ' +
                apiKey.substring(0, 7) +
                '\n\nThis looks like an OpenAI key. Please check your API key.',
                'error'
            );
        }
        if (provider === 'openai' && (!apiKey.startsWith('sk-') || apiKey.startsWith('sk-ant-'))) {
            return showMessage(
                '❌ Invalid OpenAI API Key!\n\nOpenAI keys must start with "sk-" (NOT "sk-ant-")\n\nYou entered a key starting with: ' +
                apiKey.substring(0, 10) +
                '\n\nThis looks like a Claude key. Please check your API key.',
                'error'
            );
        }
    }

    // Persist viewport background
    const bgRadio = document.querySelector('input[name="desktop-bg"]:checked');
    const desktopBg = bgRadio ? bgRadio.value : 'black';
    localStorage.setItem('desktop_bg', desktopBg);
    window.NEXUS_VIEWER?.setDesktopBackground(desktopBg);

    // Persist shadow setting
    const shadowRadio = document.querySelector('input[name="desktop-shadow"]:checked');
    const desktopShadow = shadowRadio ? shadowRadio.value : 'off';
    localStorage.setItem('desktop_shadow', desktopShadow);
    window.NEXUS_VIEWER?.setShadows(desktopShadow === 'on');

    // Persist visual effects toggles
    const fxSaveFields = [
        { id: 'fx-envmap', key: 'fx_envmap', apply: (v) => window.NEXUS_VIEWER?.setEnvironmentMap(v) },
        {
            id: 'fx-bloom',
            key: 'fx_bloom',
            apply: (v) => window.NEXUS_VIEWER?.postProcessing?.setBloom(v),
        },
        {
            id: 'fx-ssao',
            key: 'fx_ssao',
            apply: (v) => window.NEXUS_VIEWER?.postProcessing?.setSSAO(v),
        },
        { id: 'fx-tonemapping', key: 'fx_tonemapping', apply: (v) => window.NEXUS_VIEWER?.setToneMapping(v) },
    ];
    for (const { id, key, apply } of fxSaveFields) {
        const el = document.getElementById(id);
        if (el) {
            localStorage.setItem(key, String(el.checked));
            apply(el.checked);
        }
    }

    // Persist face tracking settings and apply live
    const ftModeRadioSave = document.querySelector('input[name="ft-mode"]:checked');
    if (ftModeRadioSave) {
        const mode = ftModeRadioSave.value;
        localStorage.setItem('ft_mode', mode);
        if (window.NEXUS_FACE_TRACKER?.setMode) {
            window.NEXUS_FACE_TRACKER.setMode(mode);
        }
    }

    const ftIndepEyesSave = document.getElementById('ft-independent-eyes');
    if (ftIndepEyesSave) {
        const val = ftIndepEyesSave.checked;
        localStorage.setItem('ft_independent_eyes', String(val));
        if (window.NEXUS_FACE_TRACKER?.setIndependentEyes) {
            window.NEXUS_FACE_TRACKER.setIndependentEyes(val);
        }
    }

    // Persist pose normalizer settings and apply live
    if (window.NEXUS_POSE_NORMALIZER) {
        const posePatch = collectPoseSettingsFromUI();
        window.NEXUS_POSE_NORMALIZER.updateSettings(posePatch);
        applyPoseSettingsLive();
    }

    // ✅ Persist provider settings
    localStorage.setItem('ai_provider', provider);
    localStorage.setItem('ai_api_key', apiKey);
    localStorage.setItem('ai_model', model);
    localStorage.setItem('system_prompt', systemPrompt);
    localStorage.setItem('watsonx_project_id', watsonxProjectId);
    localStorage.setItem('base_url', baseUrl);

    config.provider = provider;
    config.apiKey = apiKey;
    config.model = model;
    config.systemPrompt = systemPrompt;
    config.watsonxProjectId = watsonxProjectId;
    config.baseUrl = baseUrl;

    // ✅ ALSO persist to unified LLMManager storage (for VR)
    // Production-safe: desktop keeps legacy keys; VR gets nexus_llm_settings.
    try {
        if (typeof window.LLMManager === 'function') {
            window._nexusLLM = window._nexusLLM || new window.LLMManager();

            // Build the unified settings object that matches LLMManager defaults structure.
            const patch = {
                provider: provider,
                system_prompt: systemPrompt,

                // Enable proxy for production to avoid CORS (VR browsers need this)
                proxy: {
                    enable_proxy: true,
                    proxy_url: '/api/proxy',
                },
            };

            if (provider === 'openai') {
                patch.openai = {
                    api_key: apiKey,
                    model: model || 'gpt-4o',
                    base_url: baseUrl || '',
                };
            } else if (provider === 'claude') {
                patch.claude = {
                    api_key: apiKey,
                    model: model || 'claude-3-5-sonnet-20240620',
                    base_url: baseUrl || '',
                };
            } else if (provider === 'watsonx') {
                patch.watsonx = {
                    api_key: apiKey,
                    project_id: watsonxProjectId || '',
                    model_id: model || 'ibm/granite-13b-chat-v2',
                    base_url: baseUrl || 'https://us-south.ml.cloud.ibm.com',
                };
            } else if (provider === 'ollama') {
                patch.ollama = {
                    base_url: baseUrl || 'http://localhost:11434',
                    model: model || 'llama3',
                };
            } else if (provider === 'ollabridge') {
                const authModeSelect = $('ollabridge-auth-mode');
                // Default to 'local-trust' when no API key is provided (e.g. Unsloth local LLM)
                const authMode = authModeSelect ? authModeSelect.value : (apiKey ? 'apikey' : 'local-trust');
                const remotePromptCb = $('ollabridge-use-remote-prompt');
                // Strip trailing /v1 from base URL to prevent double /v1 in LLMManager methods
                const cleanBaseUrl = (baseUrl || '').trim().replace(/\/v1\/?$/, '');
                patch.ollabridge = {
                    api_key: authMode === 'apikey' ? apiKey : '',
                    base_url: cleanBaseUrl,
                    model: model || 'default',
                    auth_mode: authMode,
                    use_remote_prompt: remotePromptCb ? remotePromptCb.checked : true,
                };
            }

            window._nexusLLM.updateSettings(patch);
            console.log('[Main] ✅ Unified LLM settings saved to nexus_llm_settings for VR:', provider);
        } else {
            console.warn('[Main] LLMManager not loaded; VR will not inherit unified settings.');
        }
    } catch (e) {
        console.warn('[Main] Failed to save unified LLM settings:', e);
    }

    // ✅ Persist speech settings
    saveSpeechSettingsFromUI();

    // ✅ Persist STT settings
    saveSTTSettingsFromUI();

    const modal = $('settings-modal');
    if (modal) {
        modal.classList.remove('active');
        modal.hidden = true;
    }

    showMessage('Settings saved successfully', 'success');
}

/* ============================
   Chat + LLM
   ============================ */
window.isGenerating = false;

async function handleUserMessage(text) {
    if (window.isGenerating) {
        console.warn('[Main] Already generating a response. Ignoring extra input.');
        return;
    }
    window.isGenerating = true;

    try {
        addMessageToHistory('user', text);

    // Add user message to chat session history
    chatHistory.addMessage('user', text);

    // Persist chat
    _persistChat();

    setStatus('listening', 'THINKING...');

    // Wait for async config fetch to complete (backend .env may still be loading)
    if (window.__NEXUS_CONFIG_READY__) {
        try {
            await window.__NEXUS_CONFIG_READY__;
            console.log('[Main] Config ready after await, provider:', config.provider);
        } catch (e) {
            console.warn('[Main] Config fetch failed, using fallback:', e.message);
        }
    }

    const effectiveProvider = config.provider || (window._nexusConfig && window._nexusConfig.provider) || 'none';

    // ✅ Ensure LLMManager is initialized early so streaming works
    if (!window._nexusLLM && typeof window.LLMManager === 'function') {
        window._nexusLLM = new window.LLMManager();
        window._nexusLLM.updateSettings({
            provider: effectiveProvider,
            system_prompt: config.systemPrompt || (window._nexusConfig && window._nexusConfig.systemPrompt) || '',
            proxy: { enable_proxy: true, proxy_url: '/api/proxy' }
        });
    }

    // Try streaming first, fallback to non-streaming
    const canStream =
        window._nexusLLM &&
        typeof window._nexusLLM.sendMessageStream === 'function' &&
        effectiveProvider !== 'ollabridge' &&
        effectiveProvider !== 'watsonx';

    if (canStream) {
        await _handleStreamingResponse(text);
    } else {
        await _handleNonStreamingResponse(text);
    }
    } finally {
        window.isGenerating = false;
    }
}

// Streaming response: tokens appear word-by-word in the chat
async function _handleStreamingResponse(text) {
    // Create an empty bot message element that we'll fill progressively
    const { textDiv, row } = _createStreamingBotMessage();

    if (window.setTypingIndicator) window.setTypingIndicator(true);

    try {
        // Limit history to last 6 messages to prevent context window overflow on large models like Gemma 12B
        const fullHistory = window.chatHistory.getHistory();
        const history = fullHistory.length > 6 ? fullHistory.slice(-6) : fullHistory;
        let systemPrompt = config.systemPrompt || 'You are a helpful AI assistant named Nexus.';
        // Inject bracket token context for soundboard/flavour non-verbal expressions
        if (window.FoveAI_INTEGRATION?.injectBracketTokens) {
            systemPrompt = window.FoveAI_INTEGRATION.injectBracketTokens(systemPrompt);
        }
        let accumulated = '';

        const fullText = await window._nexusLLM.sendMessageStream(text, systemPrompt, history, (token) => {
            // Hide typing indicator on first token and show the bubble
            if (!accumulated) {
                if (window.setTypingIndicator) window.setTypingIndicator(false);
                if (row) row.style.display = 'flex'; // Show message bubble
            }
            accumulated += token;
            textDiv.textContent = accumulated;
            // Scroll chat
            const chatEl = $('chat-history');
            if (chatEl) chatEl.scrollTop = chatEl.scrollHeight;
        });

        if (window.setTypingIndicator) window.setTypingIndicator(false);

        const displayText = fullText || accumulated || 'No response';
        textDiv.textContent = displayText;
        if (row && row.style.display === 'none') row.style.display = 'flex'; // Ensure visible even if no onToken was fired

        chatHistory.addMessage('assistant', displayText);
        _persistChat();

        // 🌟 XRL ACTIVE RECALL INTERCEPTOR 🌟
        const recallMatch = displayText.match(/<recall:\s*"([^"]+)">/i);
        if (recallMatch) {
            const query = recallMatch[1];
            console.log(`[XRL] Memory recall triggered for: "${query}"`);
            if (window.setTypingIndicator) window.setTypingIndicator(true);
            setStatus('listening', 'SEARCHING MEMORY...');
            
            try {
                // Build corpus from entire Dexie/Session history + Long-Term memory
                const allHistory = window.chatHistory.getHistory();
                const corpus = {};
                
                // Add current session (higher priority context)
                allHistory.forEach((msg, i) => {
                    if (msg.role === 'user' || msg.role === 'assistant') {
                        corpus[`current_session_turn_${i}`] = `[${msg.timestamp || 'Recent'}] ${msg.role.toUpperCase()}: ${msg.content}`;
                    }
                });

                // Fetch long-term memory history
                try {
                    const histRes = await fetch('/api/memory/history');
                    if (histRes.ok) {
                        const histData = await histRes.json();
                        if (histData && histData.conversations) {
                            histData.conversations.forEach((msg, i) => {
                                if (msg.role === 'user' || msg.role === 'assistant') {
                                    corpus[`past_session_${msg.session_id}_turn_${i}`] = `[${msg.timestamp || 'Past'}] ${msg.role.toUpperCase()}: ${msg.content}`;
                                }
                            });
                        }
                    }
                } catch (err) {
                    console.warn('[XRL] Could not fetch long-term history:', err);
                }

                // Send to Stardust Encoder on port 8109 via our proxy
                const res = await fetch('/api/memory/stardust/swarm_match', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query: query, corpus: corpus })
                });

                if (res.ok) {
                    const data = await res.json();
                    if (data.matches && data.matches.length > 0) {
                        let injectedText = `[MEMORY UNCOMPRESSED for "${query}"]:\n`;
                        data.matches.forEach(m => {
                            if (corpus[m.filePath]) {
                                injectedText += `* ${corpus[m.filePath]}\n`;
                            }
                        });
                        
                        console.log("[XRL] Uncompressed memory:", injectedText);
                        // Inject into rolling history
                        chatHistory.addMessage('system', injectedText);
                        _persistChat();
                        
                        // Show in UI as a system notification
                        addMessageToHistory('system', `Memory uncompressed for: "${query}"`);
                        
                        // Automatically unlock and trigger continuation
                        window.isGenerating = false;
                        setTimeout(() => handleUserMessage("[SYSTEM: Memory uncompressed. Please continue answering the user.]"), 500);
                        return; // Exit early, do NOT speak the intermediate thought
                    } else {
                        addMessageToHistory('system', `Memory search found nothing for: "${query}"`);
                    }
                } else {
                    console.error("[XRL] Stardust API error:", res.statusText);
                }
            } catch (err) {
                console.error("[XRL] Failed to search memory", err);
            }
        }

        // Mirror to AR overlay (only if no recall)
        if (window._arAppendBubble) window._arAppendBubble('bot', displayText);

        // Forward to VR (only if no recall)
        if (window.sendBotResponseToVR) {
            window.sendBotResponseToVR({
                text: displayText,
                attachments: [],
                avatar_directives: {},
                persona_context: null,
            });
        }

        _applyEmotionFromText(displayText);
        speakText(displayText);
        setStatus('idle', 'READY');
    } catch (error) {
        if (window.setTypingIndicator) window.setTypingIndicator(false);
        logError('Streaming error, falling back', error);

        // Remove the empty streaming message
        if (row.parentElement) row.parentElement.removeChild(row);

        // Fallback to non-streaming
        await _handleNonStreamingResponse(text);
    }
}

// Non-streaming response (original behavior + retry button)
async function _handleNonStreamingResponse(text) {
    if (window.setTypingIndicator) window.setTypingIndicator(true);

    try {
        const effectiveProvider = config.provider || (window._nexusConfig && window._nexusConfig.provider) || 'none';
        const response = await callLLM(text);

        if (window.setTypingIndicator) window.setTypingIndicator(false);

        let displayText;
        let attachments = [];
        if (response && typeof response === 'object' && typeof response.text === 'string') {
            displayText = response.text;
            attachments = response.attachments || [];
        } else {
            displayText = String(response);
        }

        addMessageToHistory('avatar', displayText, attachments);

        if (window.sendBotResponseToVR) {
            window.sendBotResponseToVR({
                text: displayText,
                attachments: attachments,
                avatar_directives: response?.avatar_directives || {},
                persona_context: response?.persona_context || null,
            });
        }

        chatHistory.addMessage('assistant', displayText);
        _persistChat();

        // 🌟 XRL ACTIVE RECALL INTERCEPTOR (Non-Streaming) 🌟
        const recallMatch = displayText.match(/<recall:\s*"([^"]+)">/i);
        if (recallMatch) {
            const query = recallMatch[1];
            console.log(`[XRL] Memory recall triggered for: "${query}"`);
            if (window.setTypingIndicator) window.setTypingIndicator(true);
            setStatus('listening', 'SEARCHING MEMORY...');
            
            try {
                const allHistory = window.chatHistory.getHistory();
                const corpus = {};
                allHistory.forEach((msg, i) => {
                    if (msg.role === 'user' || msg.role === 'assistant') {
                        corpus[`turn_${i}`] = `[${msg.timestamp || 'Past'}] ${msg.role.toUpperCase()}: ${msg.content}`;
                    }
                });

                const res = await fetch('/api/memory/stardust/swarm_match', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query: query, corpus: corpus })
                });

                if (res.ok) {
                    const data = await res.json();
                    if (data.matches && data.matches.length > 0) {
                        let injectedText = `[MEMORY UNCOMPRESSED for "${query}"]:\n`;
                        data.matches.forEach(m => {
                            if (corpus[m.filePath]) injectedText += `* ${corpus[m.filePath]}\n`;
                        });
                        
                        console.log("[XRL] Uncompressed memory:", injectedText);
                        chatHistory.addMessage('system', injectedText);
                        _persistChat();
                        
                        addMessageToHistory('system', `Memory uncompressed for: "${query}"`);
                        
                        window.isGenerating = false;
                        setTimeout(() => handleUserMessage("[SYSTEM: Memory uncompressed. Please continue answering the user.]"), 500);
                        return; // Exit early
                    } else {
                        addMessageToHistory('system', `Memory search found nothing for: "${query}"`);
                    }
                }
            } catch (err) {
                console.error("[XRL] Failed to search memory", err);
            }
        }

        // Use inline tags if available, otherwise fallback to text-based regex heuristics
        if (response?.avatar_directives?.emotion && window.NEXUS_ANIMATION_MANAGER?.applyEmotion) {
            window.NEXUS_ANIMATION_MANAGER.applyEmotion(response.avatar_directives.emotion);
            setStatus('idle', `FEELING ${response.avatar_directives.emotion.toUpperCase()}`);
        } else {
            _applyEmotionFromText(displayText);
        }
        speakText(displayText);
        setStatus('idle', 'READY');
    } catch (error) {
        if (window.setTypingIndicator) window.setTypingIndicator(false);
        logError('Error processing message', error);

        if (error.name === 'PersonaUnavailableError') {
            const friendlyMsg =
                `The persona "${error.modelName}" is no longer available. ` +
                `You can select a different model in Settings, or refresh the model list.`;
            addMessageToHistory('avatar', friendlyMsg);
            chatHistory.addMessage('assistant', friendlyMsg);
            showMessage('Persona unavailable \u2014 open Settings to choose another model', 'warning');
            setStatus('idle', 'READY');
        } else {
            // Show error with retry button
            _addErrorWithRetry(text, error);
            setStatus('idle', 'ERROR');
            setTimeout(() => setStatus('idle', 'READY'), 2000);
        }
    }
}

// Creates an empty bot message div for streaming token-by-token
function _createStreamingBotMessage() {
    const chatEl = $('chat-history');
    if (!chatEl) return { textDiv: document.createElement('div'), row: document.createElement('div') };

    const emptyState = chatEl.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    const messageDiv = document.createElement('div');
    messageDiv.className = 'chat-message avatar';

    const senderDiv = document.createElement('div');
    senderDiv.className = 'message-sender avatar';
    senderDiv.textContent = 'NEXUS';

    const textDiv = document.createElement('div');
    textDiv.className = 'message-text';
    textDiv.textContent = '';

    messageDiv.appendChild(senderDiv);
    messageDiv.appendChild(textDiv);

    const row = document.createElement('div');
    row.className = 'chat-row';
    row.style.display = 'none'; // Hide until first token arrives
    row.appendChild(messageDiv);
    chatEl.appendChild(row);
    chatEl.scrollTop = chatEl.scrollHeight;

    return { textDiv, row };
}

// Show error message with a retry button
function _addErrorWithRetry(originalText, error) {
    // Log the actual error to console for debugging
    console.error('[Main] Chat error:', error?.message || error, error);
    const chatEl = $('chat-history');
    if (!chatEl) return;

    const row = document.createElement('div');
    row.className = 'chat-row';

    const msgDiv = document.createElement('div');
    msgDiv.className = 'chat-message avatar';

    const senderDiv = document.createElement('div');
    senderDiv.className = 'message-sender avatar';
    senderDiv.textContent = 'NEXUS';

    const textDiv = document.createElement('div');
    textDiv.className = 'message-text';
    textDiv.textContent = 'Sorry, I encountered an error. ';

    const retryBtn = document.createElement('button');
    retryBtn.className = 'retry-btn';
    retryBtn.textContent = 'Retry';
    retryBtn.addEventListener('click', async () => {
        if (window.isGenerating) return; // Prevent triple clicks
        window.isGenerating = true;
        
        // Remove this error message
        if (row.parentElement) row.parentElement.removeChild(row);
        
        setStatus('listening', 'THINKING...');
        
        try {
            const effectiveProvider = config.provider || (window._nexusConfig && window._nexusConfig.provider) || 'none';
            const canStream =
                window._nexusLLM &&
                typeof window._nexusLLM.sendMessageStream === 'function' &&
                effectiveProvider !== 'ollabridge' &&
                effectiveProvider !== 'watsonx';
            
            if (canStream) {
                await _handleStreamingResponse(originalText);
            } else {
                await _handleNonStreamingResponse(originalText);
            }
        } finally {
            window.isGenerating = false;
        }
    });

    textDiv.appendChild(retryBtn);
    msgDiv.appendChild(senderDiv);
    msgDiv.appendChild(textDiv);
    row.appendChild(msgDiv);
    chatEl.appendChild(row);
    chatEl.scrollTop = chatEl.scrollHeight;
}

function getSimpleResponse(text) {
    const t = (text || '').toLowerCase();
    if (t.includes('hello') || t.includes('hi')) return 'Hello! How can I assist you today?';
    if (t.includes('how are you')) return "I'm functioning perfectly, thank you for asking! How can I help you?";
    if (t.includes('bye') || t.includes('goodbye')) return 'Goodbye! Have a wonderful day!';
    if (t.includes('help') || t.includes('settings') || t.includes('configure') || t.includes('provider')) {
        return (
            'I can chat with you, but to use AI features you need to configure an AI provider.\n\n' +
            'Click the ⚙️ Settings icon (top-right) to configure:\n' +
            '• OpenAI — requires an API key from platform.openai.com\n' +
            '• Claude — requires an API key from console.anthropic.com\n' +
            '• WatsonX — requires IBM Cloud API key\n' +
            '• OllaBridge — connects to HomePilot or local Ollama\n\n' +
            'After selecting a provider and entering your API key, click "Save Settings" to start chatting!'
        );
    }
    return (
        "I'm running in offline mode because no AI provider is configured.\n\n" +
        "To enable full AI responses:\n" +
        "1. Click the ⚙️ Settings icon (top-right corner)\n" +
        "2. Select an AI provider (OpenAI, Claude, WatsonX, or OllaBridge)\n" +
        "3. Enter your API key and select a model\n" +
        "4. Click 'Save Settings'\n\n" +
        "Or type 'help' for more information."
    );
}

async function callLLM(userMessage) {
    // ✅ Ensure LLMManager is initialized
    if (!window._nexusLLM && typeof window.LLMManager === 'function') {
        window._nexusLLM = new window.LLMManager();
        const effectiveProvider = config.provider || (window._nexusConfig && window._nexusConfig.provider) || 'none';
        window._nexusLLM.updateSettings({
            provider: effectiveProvider,
            system_prompt: config.systemPrompt || (window._nexusConfig && window._nexusConfig.systemPrompt) || '',
            proxy: { enable_proxy: true, proxy_url: '/api/proxy' }
        });
    }

    // ✅ Use LLMManager with conversation history if available
    if (window._nexusLLM) {
        // Limit history to last 6 messages to prevent context window overflow
        const fullHistory = window.chatHistory.getHistory();
        const history = fullHistory.length > 6 ? fullHistory.slice(-6) : fullHistory;
        let systemPrompt = config.systemPrompt || 'You are a helpful AI assistant named Nexus.';
        // Inject bracket token context for soundboard/flavour non-verbal expressions
        if (window.FoveAI_INTEGRATION?.injectBracketTokens) {
            systemPrompt = window.FoveAI_INTEGRATION.injectBracketTokens(systemPrompt);
        }

        // Use structured response for OllaBridge to get attachments
        if (config.provider === 'ollabridge' && typeof window._nexusLLM.sendMessageStructured === 'function') {
            const raw = await window._nexusLLM.sendMessageStructured(userMessage, systemPrompt, history);
            // Normalize via BridgeResponseAdapter if available
            if (typeof window.BridgeResponseAdapter?.normalizeResponse === 'function') {
                return window.BridgeResponseAdapter.normalizeResponse(raw);
            }
            // Manual extraction fallback
            const text = raw?.choices?.[0]?.message?.content || raw?.text || String(raw);
            return {
                text,
                attachments: raw?.x_attachments || [],
                avatar_directives: raw?.x_avatar_directives || raw?.x_directives || {},
                persona_context: raw?.x_persona_context || null,
                meta: {},
            };
        }

        return await window._nexusLLM.sendMessage(userMessage, systemPrompt, history);
    }

    // Fallback to legacy provider functions
    if (config.provider === 'openai') return callOpenAI(userMessage);
    if (config.provider === 'claude') return callClaude(userMessage);
    if (config.provider === 'watsonx') return callWatsonX(userMessage);
    return 'Provider not configured.';
}

/* ============================
   Speech
   ============================ */
/**
 * Detect emotion from response text and apply to avatar expression.
 * Uses simple keyword heuristics — lightweight and instant.
 */
function _applyEmotionFromText(text) {
    const t = (text || '').toLowerCase();
    let emotion = 'neutral';
    let mode = 'idle';

    if (/\b(haha|lol|😂|😄|great|awesome|wonderful|fantastic|love|exciting|glad|happy)\b/.test(t)) {
        emotion = 'happy';
        mode = 'happy';
    } else if (/\b(sorry|unfortunately|sad|miss|regret|disappointed|😢)\b/.test(t)) {
        emotion = 'sad';
        mode = 'idle';
    } else if (/\b(think|hmm|consider|perhaps|interesting|curious|wonder)\b/.test(t)) {
        emotion = 'neutral';
        mode = 'thinking';
    } else if (/\b(wow|amazing|incredible|surprise|shocked|😮|😲)\b/.test(t)) {
        emotion = 'surprised';
        mode = 'idle';
    }

    try {
        window.NEXUS_VIEWER?.avatarManager?.vrmLoader?.setEmotion?.(emotion, 0.5);
    } catch (_) { }
    if (mode !== 'idle') {
        try {
            window.NEXUS_PROCEDURAL_ANIMATOR?.setMode?.(mode, 4000);
        } catch (_) { }
    }

    // Bridge emotion to VR Intimacy System
    window.dispatchEvent(
        new CustomEvent('avatar-emotion-changed', {
            detail: { emotion: emotion || 'neutral' },
        })
    );
}

/**
 * Strip bracket tokens (<audio:...>, <flavour:...>, <emotion:...>, <laugh>, etc.)
 * from text before passing to TTS. These are non-verbal expression directives
 * for the animation engine and should never be read aloud.
 *
 * This also strips standalone < and > characters that TTS reads as
 * "less than" / "greater than" — the AI sometimes outputs raw angle brackets
 * that are not part of valid bracket tokens.
 */
function stripBracketTokens(text) {
    if (!text || typeof text !== 'string') return text || '';
    // 1. Remove ALL <...> patterns (any content between angle brackets)
    //    This covers: <audio:laugh>, <flavour:thoughtful>, <emotion:happy>, <laugh>, etc.
    text = text.replace(/<[^>]*>/g, '');
    // 2. Remove any remaining standalone < or > characters that weren't part of a pair
    //    (e.g. if the AI outputs a lone < or > that TTS reads as "less than" / "greater than")
    text = text.replace(/[<>]/g, '');
    // 3. Clean up extra whitespace from removed tokens
    return text.replace(/\s{2,}/g, ' ').trim();
}

function speakText(text) {
    // Strip bracket tokens before TTS — never read non-verbal directives aloud
    text = stripBracketTokens(text);
    if (!text) {
        setStatus('idle', 'READY');
        return;
    }
    setStatus('speaking', 'SPEAKING...');

    // Pause VAD Engine so mic doesn't capture AI's own speech
    if (window.nexusVadEngine) {
        window.nexusVadEngine.pauseVAD();
    }

    // Play message received sound trigger
    try {
        window.NEXUS_AMBIENT_SOUND_ENGINE?.playMessageReceived();
    } catch (_) { }

    /* NEXUS_PATCH_LIFE_ENGINE_TALK_MODE */
    try {
        window.NEXUS_PROCEDURAL_ANIMATOR?.setMode?.('talk', 30000);
    } catch (_) { }
    try {
        window.NEXUS_VIEWER?.playAnimationByName?.('Talk');
    } catch (_) { }
    // Start lip-sync while speaking (Phase 3 engine + legacy oscillator fallback)
    try {
        const rate = window.SpeechSettings?.rate || 1.0;
        window.NEXUS_LIP_SYNC?.start?.(text, rate);
    } catch (_) { }
    try {
        window.NEXUS_VIEWER?.avatarManager?.vrmLoader?.startLipSync?.();
    } catch (_) { }

    // --- Pluggable TTS engine path (additive — Piper WASM, etc.) ---
    if (window.TTSProvider && window.TTSProvider.isActive()) {
        try {
            window.speechSynthesis?.cancel?.();
        } catch (_) { }

        let rate = SpeechSettings.rate;
        let pitch = SpeechSettings.pitch;
        if (typeof window.PersonaContextBridge !== 'undefined') {
            const vo = window.PersonaContextBridge.getVoiceOverrides({ rate, pitch });
            if (vo) {
                rate = vo.rate;
                pitch = vo.pitch;
            }
        }

        window.TTSProvider.speak(text, {
            rate,
            pitch,
            onEnd: () => {
                try {
                    window.NEXUS_LIP_SYNC?.stop?.();
                } catch (_) { }
                try {
                    window.NEXUS_BEHAVIOR?.onSpeechEnd?.();
                } catch (_) { }
                try {
                    window.NEXUS_VIEWER?.avatarManager?.vrmLoader?.stopLipSync?.();
                } catch (_) { }

                if (window.nexusVadEngine) window.nexusVadEngine.resumeVAD();

                // Play distant voice echo after speech ends
                try {
                    window.NEXUS_AMBIENT_SOUND_ENGINE?.playJenEcho(text);
                } catch (_) { }

                const personaMode =
                    typeof window.PersonaContextBridge !== 'undefined'
                        ? window.PersonaContextBridge.getDefaultAvatarMode()
                        : 'waiting';
                try {
                    window.NEXUS_PROCEDURAL_ANIMATOR?.setMode?.(
                        personaMode,
                        personaMode === 'idle' || personaMode === 'waiting' ? 0 : 5000
                    );
                } catch (_) { }
                setStatus('idle', 'READY');
                try {
                    const clipName = personaMode === 'happy' ? 'Happy' : 'Idle';
                    window.NEXUS_VIEWER?.playAnimationByName?.(clipName);
                } catch (_) { }
            },
            onError: () => {
                try {
                    window.NEXUS_LIP_SYNC?.stop?.();
                } catch (_) { }
                try {
                    window.NEXUS_BEHAVIOR?.onSpeechEnd?.();
                } catch (_) { }
                try {
                    window.NEXUS_VIEWER?.avatarManager?.vrmLoader?.stopLipSync?.();
                } catch (_) { }
                if (window.nexusVadEngine) window.nexusVadEngine.resumeVAD();
                try {
                    window.NEXUS_PROCEDURAL_ANIMATOR?.setMode?.('waiting', 0);
                } catch (_) { }
                setStatus('idle', 'READY');
                try {
                    window.NEXUS_VIEWER?.playAnimationByName?.('Idle');
                } catch (_) { }
            },
        });
        return; // skip Web Speech API path
    }

    // --- Existing Web Speech API path (unchanged) ---
    if (!('speechSynthesis' in window)) {
        setStatus('idle', 'READY');
        return;
    }

    // Stop any current utterance to avoid overlapping
    try {
        window.speechSynthesis.cancel();
    } catch (_) { }

    const utterance = new SpeechSynthesisUtterance(text);

    // ✅ Apply settings (with optional persona voice overrides)
    utterance.lang = SpeechSettings.lang;
    utterance.rate = SpeechSettings.rate;
    utterance.pitch = SpeechSettings.pitch;

    // Apply persona voice_style overrides from HomePilot (additive)
    if (typeof window.PersonaContextBridge !== 'undefined') {
        const voiceOverrides = window.PersonaContextBridge.getVoiceOverrides({
            rate: SpeechSettings.rate,
            pitch: SpeechSettings.pitch,
        });
        if (voiceOverrides) {
            utterance.rate = voiceOverrides.rate;
            utterance.pitch = voiceOverrides.pitch;
        }
    }

    // Use smart voice picker (handles specific selection or auto-best-match)
    const v = pickBestVoice();
    if (v) utterance.voice = v;

    utterance.onend = () => {
        /* NEXUS_PATCH_LIFE_ENGINE_TALK_END */
        try {
            window.NEXUS_LIP_SYNC?.stop?.();
        } catch (_) { }
        try {
            window.NEXUS_BEHAVIOR?.onSpeechEnd?.();
        } catch (_) { }
        try {
            window.NEXUS_VIEWER?.avatarManager?.vrmLoader?.stopLipSync?.();
        } catch (_) { }
        if (window.nexusVadEngine) window.nexusVadEngine.resumeVAD();
        const personaMode =
            typeof window.PersonaContextBridge !== 'undefined'
                ? window.PersonaContextBridge.getDefaultAvatarMode()
                : 'idle';
        try {
            window.NEXUS_PROCEDURAL_ANIMATOR?.setMode?.(personaMode, personaMode === 'idle' ? 1 : 5000);
        } catch (_) { }
        setStatus('idle', 'READY');
        try {
            const clipName = personaMode === 'happy' ? 'Happy' : 'Idle';
            window.NEXUS_VIEWER?.playAnimationByName?.(clipName);
        } catch (_) { }
    };

    utterance.onerror = () => {
        /* NEXUS_PATCH_LIFE_ENGINE_TALK_ERR */
        try {
            window.NEXUS_LIP_SYNC?.stop?.();
        } catch (_) { }
        try {
            window.NEXUS_BEHAVIOR?.onSpeechEnd?.();
        } catch (_) { }
        try {
            window.NEXUS_VIEWER?.avatarManager?.vrmLoader?.stopLipSync?.();
        } catch (_) { }
        if (window.nexusVadEngine) window.nexusVadEngine.resumeVAD();
        try {
            window.NEXUS_PROCEDURAL_ANIMATOR?.setMode?.('idle', 1);
        } catch (_) { }
        setStatus('idle', 'READY');
        try {
            window.NEXUS_VIEWER?.playAnimationByName?.('Idle');
        } catch (_) { }
    };

    window.speechSynthesis.speak(utterance);
}

function initSpeechRecognition() {
    // Check for secure context — Web Speech API requires HTTPS or localhost
    const isSecure = window.isSecureContext === true ||
        location.protocol === 'https:' ||
        location.hostname === 'localhost' ||
        location.hostname === '127.0.0.1' ||
        location.hostname === '[::1]';

    if (!isSecure) {
        logWarn(
            'Speech recognition requires a secure context (HTTPS or localhost). ' +
            'The page is currently served over HTTP, which blocks the Web Speech API. ' +
            'Current URL: ' + location.href
        );
        return;
    }

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
        logWarn(
            'Speech recognition not available. ' +
            'Your browser may not support the Web Speech API, or it may be blocked ' +
            'by Content Security Policy (CSP). Try Chrome or Edge. ' +
            'navigator.userAgent: ' + navigator.userAgent
        );
        return;
    }

    recognition = new SR();

    // ✅ Apply persisted language
    recognition.lang = SpeechSettings.lang;

    recognition.continuous = false;
    recognition.interimResults = true; // ✅ Enable interim results for real-time feedback

    recognition.onstart = () => {
        isListening = true;
        setStatus('listening', 'LISTENING...');

        console.log('[Desktop STT] 🎙️ Recognition started');
        if (window.NEXUS_LOGGER) {
            window.NEXUS_LOGGER.info('Desktop STT started', {
                browser: navigator.userAgent.includes('Quest') ? 'Quest' : 'Desktop',
            });
        }

        try {
            window.NEXUS_VIEWER?.playAnimationByName?.('Idle');
        } catch (_) { }

        const btn = $('listen-btn');
        if (btn) {
            btn.classList.add('active');
        }
        if ($('voice-btn-text')) {
            $('voice-btn-text').textContent = 'LISTENING...';
        }
        if ($('recognition-status')) {
            $('recognition-status').textContent = 'Listening to your voice...';
        }
        if (btn) {
            btn.setAttribute('aria-pressed', 'true');
        }

        // Clear input and set placeholder
        const inputField = $('speech-text');
        console.log('[Desktop STT] 🖱️ Input field found:', !!inputField);
        if (inputField) {
            inputField.value = '';
            inputField.placeholder = 'Listening...';
            inputField.style.fontStyle = 'normal';
            inputField.style.opacity = '1';
            // On mobile, hide the keyboard while the user is speaking.
            // The keyboard is unnecessary during voice capture and covers
            // half the screen, degrading the experience.
            if ('ontouchstart' in window) {
                inputField.blur();
            }
        } else {
            console.error('[Desktop STT] ❌ ERROR: speech-text input not found!');
        }
    };

    recognition.onresult = (event) => {
        const inputField = $('speech-text');
        if (!inputField) {
            console.error('[Desktop STT] ❌ ERROR: speech-text input field not found in onresult!');
            if (window.NEXUS_LOGGER) {
                window.NEXUS_LOGGER.error('Desktop STT input field missing');
            }
            return;
        }

        // Check if this is the final result
        const result = event.results[event.results.length - 1];
        const transcript = result[0].transcript || '';
        const confidence = result[0].confidence || 0;
        const isFinal = result.isFinal;

        if (isFinal) {
            // Final result - show with confidence
            const confidencePercent = Math.round(confidence * 100);

            console.log(`[Desktop STT] ✅ FINAL: "${transcript}" (${confidencePercent}% confidence)`);
            if (window.NEXUS_LOGGER) {
                window.NEXUS_LOGGER.info('Desktop STT final', { text: transcript, confidence: confidencePercent });
            }

            inputField.value = transcript;
            inputField.style.fontStyle = 'normal';
            inputField.style.opacity = '1';
            inputField.placeholder = 'Type your message…';

            console.log('[Desktop STT] 📤 Populated input field with:', transcript);

            // Stop listening after final result
            stopVoiceInput();

            // Auto-send if enabled and confidence > 80%
            const isMobileTouch = 'ontouchstart' in window;
            if (SpeechSettings.autoSend && confidence >= 0.8 && transcript.trim().length > 0) {
                console.log(`[Desktop STT] Auto-sending (${confidencePercent}% confidence)`);
                if (SpeechSettings.showConfidence) {
                    showMessage(`🎤 Auto-sent (${confidencePercent}% confidence): "${transcript}"`, 'info');
                }
                handleUserMessage(transcript.trim());
                inputField.value = '';
                // On mobile, keep keyboard hidden — the message was sent
                // automatically, so there is nothing for the user to edit.
                if (isMobileTouch) inputField.blur();
            } else {
                // Show confidence feedback only if enabled
                if (SpeechSettings.showConfidence) {
                    showMessage(
                        `🎤 Transcribed (${confidencePercent}% confidence): "${transcript}"\nReview and press SEND, or click ACTIVATE VOICE to record again.`,
                        'info'
                    );
                }
                // On desktop, focus/select so the user can immediately edit
                // or press Enter. On mobile, do NOT focus — it would pop up
                // the keyboard unnecessarily. The user can tap the input to
                // edit, or tap the mic to re-record, or tap SEND.
                if (!isMobileTouch) {
                    inputField.focus();
                    inputField.select();
                }
            }
        } else {
            // Interim result - show in italic
            console.log(`[Desktop STT] 📝 INTERIM: "${transcript}"`);
            if (window.NEXUS_LOGGER) {
                window.NEXUS_LOGGER.info('Desktop STT interim', { text: transcript });
            }

            inputField.value = transcript;
            inputField.style.fontStyle = 'italic';
            inputField.style.opacity = '0.7';
        }
    };

    recognition.onerror = (event) => {
        const errorType = event && event.error;
        console.error(`[Desktop STT] ⚠️ ERROR: ${errorType}`);
        if (window.NEXUS_LOGGER) {
            window.NEXUS_LOGGER.error('Desktop STT error', { error: errorType });
        }
        logError('Speech recognition error', errorType);
        stopVoiceInput();
    };

    recognition.onend = () => {
        if (isVadPinned) {
            console.log('[Desktop STT] VAD Pinned: Restarting recognition...');
            setTimeout(() => { if (isVadPinned) startVoiceInput(); }, 500);
            return;
        }
        console.log('[Desktop STT] ⏹️ Recognition ended');
        if (window.NEXUS_LOGGER) {
            window.NEXUS_LOGGER.info('Desktop STT ended');
        }
        stopVoiceInput();
    };
}

function toggleVoiceInput() {
    if (isVadPinned) {
        isVadPinned = false;
        const pinBtn = document.getElementById('vad-pin-btn');
        if (pinBtn) pinBtn.classList.remove('pinned');
        stopVoiceInput();
        return;
    }
    if (isListening) stopVoiceInput();
    else startVoiceInput();
}

function startVoiceInput() {
    if (!window.VADEngine) {
        return showMessage('❌ VADEngine not loaded.', 'error');
    }

    if (!window.nexusVadEngine) {
        window.nexusVadEngine = new window.VADEngine({
            onStart: () => {
                isListening = true;
                setStatus('listening', 'LISTENING');
                const btn = $('listen-btn');
                if (btn) btn.classList.add('active');
                if ($('voice-btn-text')) $('voice-btn-text').textContent = 'LISTENING...';
                if ($('recognition-status')) $('recognition-status').textContent = 'Listening to your voice...';
                
                const inputField = $('speech-text');
                if (inputField) {
                    inputField.value = '';
                    inputField.placeholder = 'Listening...';
                    inputField.style.fontStyle = 'normal';
                    inputField.style.opacity = '1';
                    if ('ontouchstart' in window) inputField.blur();
                }
            },
            onResult: (text) => {
                const inputField = $('speech-text');
                if (inputField) {
                    inputField.value = text;
                    inputField.style.fontStyle = 'normal';
                    inputField.placeholder = 'Type your message…';
                }
                
                // Auto-send via VAD pipeline
                console.log(`[Desktop STT] Auto-sending: "${text}"`);
                if (SpeechSettings.showConfidence) {
                    showMessage(`🎤 Auto-sent: "${text}"`, 'info');
                }
                handleUserMessage(text.trim());
                if (inputField) inputField.value = '';
                
                stopVoiceInput();
            },
            onError: (err) => {
                showMessage('❌ STT Error: ' + err, 'error');
                stopVoiceInput();
            },
            onStop: () => {
                stopVoiceInput();
            },
            onLog: (msg) => {
                console.log(msg);
                if (window.NEXUS_LOGGER) window.NEXUS_LOGGER.info(msg);
            }
        });
    }

    window.nexusVadEngine.startListening();
}

function stopVoiceInput() {
    isListening = false;
    setStatus('idle', 'READY');
    try {
        window.NEXUS_VIEWER?.playAnimationByName?.('Idle');
    } catch (_) { }

    const btn = $('listen-btn');
    if (btn) {
        btn.classList.remove('active');
        btn.setAttribute('aria-pressed', 'false');
    }
    if ($('voice-btn-text')) {
        $('voice-btn-text').textContent = 'ACTIVATE VOICE';
    }
    if ($('recognition-status')) {
        $('recognition-status').textContent = 'Voice system standby';
    }

    // Reset input field styling
    const inputField = $('speech-text');
    if (inputField) {
        inputField.style.fontStyle = 'normal';
        inputField.style.opacity = '1';
        if (!inputField.value) {
            inputField.placeholder = 'Type your message…';
        }
    }

    if (window.nexusVadEngine) {
        window.nexusVadEngine.stopListening();
    }
}

/* ============================
   Chat UI
   ============================ */
function addMessageToHistory(sender, text, attachments) {
    const chatHistory = $('chat-history');
    if (!chatHistory) return;

    const emptyState = chatHistory.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message ${sender}`;

    const senderDiv = document.createElement('div');
    messageDiv.className = `chat-message ${sender}`;
    senderDiv.className = `message-sender ${sender}`;
    senderDiv.textContent = sender === 'user' ? 'YOU' : 'NEXUS';

    const textDiv = document.createElement('div');
    textDiv.className = 'message-text';
    textDiv.textContent = text;

    messageDiv.appendChild(senderDiv);
    messageDiv.appendChild(textDiv);

    // Render image attachments inline
    if (Array.isArray(attachments) && attachments.length > 0) {
        attachments.forEach((att) => {
            if (att.type === 'image' && att.url) {
                const imgContainer = document.createElement('div');
                imgContainer.style.cssText = 'margin-top: 8px; max-width: 300px;';

                const img = document.createElement('img');
                img.src = att.url;
                img.alt = att.name || 'Image';
                img.style.cssText =
                    'width: 100%; border-radius: 8px; cursor: pointer; border: 1px solid rgba(0,229,255,0.3);';
                img.loading = 'lazy';

                // Click to open in new tab
                img.addEventListener('click', () => window.open(att.url, '_blank'));

                if (att.name) {
                    const label = document.createElement('div');
                    label.textContent = att.name;
                    label.style.cssText =
                        'font-size: 11px; color: rgba(255,255,255,0.5); margin-top: 4px; text-align: center;';
                    imgContainer.appendChild(img);
                    imgContainer.appendChild(label);
                } else {
                    imgContainer.appendChild(img);
                }

                messageDiv.appendChild(imgContainer);
            }
        });
    }

    // Wrap in a clearfix row so floated bubbles stack properly
    const row = document.createElement('div');
    row.className = 'chat-row';
    row.appendChild(messageDiv);
    chatHistory.appendChild(row);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    // Mirror message to AR overlay (if active)
    if (window._arAppendBubble) {
        window._arAppendBubble(sender === 'user' ? 'user' : 'bot', text);
    }
}

function clearHistory() {
    const chatHistoryEl = $('chat-history');
    if (!chatHistoryEl) return;
    chatHistoryEl.innerHTML = `
    <div class="empty-state">
      <p>System Log Ready.</p>
      <p class="sub-text">All transmissions will be recorded here.</p>
    </div>`;

    // ✅ Also clear the chat session history (context memory)
    if (window.chatHistory) {
        window.chatHistory.clear();
        showMessage('Chat history and context memory cleared', 'success');
    }
}

function showMessage(text, type) {
    const notification = document.createElement('div');
    notification.textContent = text;

    const bg =
        type === 'error' ? '#ff5252' : type === 'success' ? '#00ff88' : type === 'warning' ? '#f59e0b' : '#00e5ff';
    notification.style.cssText = `
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    background: ${bg};
    color: #000;
    padding: 12px 24px;
    border-radius: 8px;
    font-family: var(--font-display, system-ui);
    font-weight: 600;
    z-index: 2000;
  `;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transition = 'opacity 0.3s ease-out';
        setTimeout(() => notification.remove(), 350);
    }, 3000);
}

/* ============================
   Chat Session History (Token-Limited Context)
   ============================ */
class ChatSessionHistory {
    constructor(maxTokens = 500) {
        this.maxTokens = maxTokens;
        this.messages = []; // Array of {role: 'user'|'assistant', content: string}
    }

    /**
     * Estimate token count (rough approximation: 1 token ≈ 4 characters)
     * @param {string} text
     * @returns {number} Estimated token count
     */
    estimateTokens(text) {
        return Math.ceil((text || '').length / 4);
    }

    /**
     * Get total token count of current history
     * @returns {number} Total tokens
     */
    getTotalTokens() {
        return this.messages.reduce((sum, msg) => sum + this.estimateTokens(msg.content), 0);
    }

    /**
     * Add a message to history with sliding window token management
     * @param {string} role - 'user' or 'assistant'
     * @param {string} content - Message content
     */
    addMessage(role, content) {
        this.messages.push({ role, content });

        // ✅ Sliding window: Remove oldest messages if over token limit
        while (this.getTotalTokens() > this.maxTokens && this.messages.length > 2) {
            // Keep at least the last exchange (1 user + 1 assistant)
            const removed = this.messages.shift();
            console.log(`[ChatHistory] Removed oldest message (${this.estimateTokens(removed.content)} tokens)`);
        }

        console.log(`[ChatHistory] History: ${this.messages.length} messages, ${this.getTotalTokens()} tokens`);
    }

    /**
     * Get message history in format suitable for LLM APIs
     * @returns {Array} Message history
     */
    getHistory() {
        return [...this.messages];
    }

    /**
     * Clear all history (e.g., when starting new session)
     */
    clear() {
        this.messages = [];
        console.log('[ChatHistory] History cleared');
    }

    /**
     * Get history summary for display
     * @returns {string}
     */
    getSummary() {
        return `${this.messages.length} messages (${this.getTotalTokens()} tokens / ${this.maxTokens} max)`;
    }
}

// Global chat session instance (accessible via window for VR integration)
window.chatHistory = new ChatSessionHistory(500);

/* ============================
   Chat Persistence (localStorage)
   ============================ */
const CHAT_STORAGE_KEY = 'nexus_chat_messages';
const CHAT_DISPLAY_KEY = 'nexus_chat_display';

// Expose for VRChatIntegration to persist after VR messages
window._persistChat = _persistChat;

function _persistChat() {
    try {
        // Save LLM history (for context)
        localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(window.chatHistory.getHistory()));
        // Save display messages (user-facing, with sender labels)
        const chatEl = document.getElementById('chat-history');
        if (chatEl) {
            const rows = chatEl.querySelectorAll('.chat-row');
            const display = [];
            rows.forEach((row) => {
                const msg = row.querySelector('.chat-message');
                if (!msg) return;
                const sender = msg.classList.contains('user') ? 'user' : 'avatar';
                const text = msg.querySelector('.message-text')?.textContent || '';
                if (text) display.push({ sender, text });
            });
            localStorage.setItem(CHAT_DISPLAY_KEY, JSON.stringify(display));
        }
    } catch (_) {
        /* storage full or unavailable */
    }
}

function _restoreChat() {
    try {
        // Restore LLM context history
        const saved = localStorage.getItem(CHAT_STORAGE_KEY);
        if (saved) {
            const msgs = JSON.parse(saved);
            if (Array.isArray(msgs) && msgs.length > 0) {
                window.chatHistory.messages = msgs;
                console.log(`[ChatPersist] Restored ${msgs.length} context messages`);
            }
        }
        // Restore display messages
        const display = localStorage.getItem(CHAT_DISPLAY_KEY);
        if (display) {
            const items = JSON.parse(display);
            if (Array.isArray(items) && items.length > 0) {
                items.forEach((m) => addMessageToHistory(m.sender, m.text));
                console.log(`[ChatPersist] Restored ${items.length} display messages`);
            }
        }
    } catch (e) {
        console.warn('[ChatPersist] Restore failed:', e);
    }
}

/* ============================
   Collapsible Panels
   ============================ */
function initCollapsiblePanels() {
    document.querySelectorAll('[data-collapsible]').forEach((panel) => {
        const toggle = panel.querySelector('.collapse-toggle');
        if (!toggle) return;

        // Set initial state
        const defaultState = panel.dataset.default;
        const isExpanded = defaultState !== 'collapsed';
        panel.dataset.expanded = isExpanded ? 'true' : 'false';
        toggle.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');

        // Toggle on click
        toggle.addEventListener('click', () => {
            const expanded = panel.dataset.expanded === 'true';
            panel.dataset.expanded = expanded ? 'false' : 'true';
            toggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
        });
    });
}

/* ============================
   Init
   ============================ */
async function init() {
    console.log('[Main] init() called', {
        readyState: document.readyState,
        useGltfEngine: !!window.__USE_GLTF_VIEWER_ENGINE__,
        hasNexusViewer: !!window.NEXUS_VIEWER,
        hasReadyPromise: !!window.__NEXUS_VIEWER_READY__,
        device: window.NEXUS_DEVICE?.device || 'unknown',
        os: window.NEXUS_DEVICE?.os || 'unknown',
    });
    showLoading('Loading 3D Avatar...');
    setStatus('idle', 'BOOTING...');

    const useViewerEngine = !!window.__USE_GLTF_VIEWER_ENGINE__;

    if (!useViewerEngine) {
        if (!vendorAssertOrAbort()) return;
    }

    try {
        // Wait for Backend Config to arrive
        if (window.__NEXUS_CONFIG_READY__) {
            showLoading('Connecting to Cognitive Core...');
            await window.__NEXUS_CONFIG_READY__;
            
            // Auto-load model if applicable
            if (config.provider === 'lmstudio' && config.model) {
                 showLoading('Loading AI Model (' + config.model + ')...');
                 try {
                     await fetch('/api/proxy/lmstudio/load', {
                         method: 'POST',
                         headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify({ model: config.model })
                     });
                 } catch (e) {
                     console.warn('[Main] Could not pre-load LMStudio model:', e);
                 }
            } else if (config.provider === 'ollabridge' && config.model) {
                 showLoading('Warming up Local AI Model (' + config.model + ')...');
                 try {
                     await fetch(config.baseUrl + '/chat/completions', {
                         method: 'POST',
                         headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify({ model: config.model, messages: [{role: "system", content: "warmup"}] }),
                         signal: AbortSignal.timeout(3000)
                     });
                 } catch (e) {
                     console.warn('[Main] Warmup failed (expected timeout):', e);
                 }
            }
        }
        
        showLoading('Loading 3D Avatar...');
        // Wait for ViewerEngine with a timeout for mobile reliability
        if (useViewerEngine && window.__NEXUS_VIEWER_READY__) {
            const viewerOrNull = await Promise.race([
                window.__NEXUS_VIEWER_READY__,
                new Promise((resolve) => setTimeout(() => resolve(null), 15000)),
            ]);

            if (!viewerOrNull) {
                console.warn('[Main] ViewerEngine not available (timeout or WebGL failure) — running chat-only mode');
                hideLoading();
                setStatus('idle', 'CHAT MODE');
            } else {
                // Apply saved visual effects settings on startup
                const fxStartup = [
                    { key: 'fx_envmap', apply: (v) => window.NEXUS_VIEWER?.setEnvironmentMap(v) },
                    { key: 'fx_bloom', apply: (v) => window.NEXUS_VIEWER?.postProcessing?.setBloom(v) },
                    { key: 'fx_ssao', apply: (v) => window.NEXUS_VIEWER?.postProcessing?.setSSAO(v) },
                    { key: 'fx_tonemapping', apply: (v) => window.NEXUS_VIEWER?.setToneMapping(v) },
                ];
                for (const { key, apply } of fxStartup) {
                    const saved = localStorage.getItem(key);
                    if (saved !== null) apply(saved === 'true');
                }
            }
        } else if (!useViewerEngine) {
            setupThreeJS();
        }

        // Voices load async in Chrome; keep list current
        if ('speechSynthesis' in window) {
            window.speechSynthesis.onvoiceschanged = () => {
                refreshVoiceList();
            };
        }

        setupEventListeners();
        setupModals();
        setupPoseNormalizerUI();
        initSpeechRecognition();
        loadConfigIntoUI();
        loadSpeechSettingsIntoUI();
        refreshVoiceList(); // initial attempt
        _restoreChat(); // restore previous conversation from localStorage

        await loadAvatarManifest();

        // Initialize Avatar Picker (bottom-sheet UI replacing the dropdown)
        if (window.AvatarPicker) {
            window._avatarPicker = new window.AvatarPicker();
        }

        // Only try to load avatar if 3D engine is available
        if (window.NEXUS_VIEWER) {
            loadDefaultAvatarFromManifest();
        } else {
            hideLoading();
            setStatus('idle', 'READY');
        }
    } catch (err) {
        logError('Initialization failed', err);
        showLoading(`Initialization failed: ${err && err.message ? err.message : err}`);
        setStatus('idle', 'ERROR');
    }
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

/* =====================================================================
   AR CHAT OVERLAY — Bridges AR DOM overlay with the main chat system.
   Activates voice + text input over the camera feed so users can speak
   with the avatar while in AR mode on mobile.
   ===================================================================== */
(function initAROverlay() {
    const overlay = document.getElementById('ar-dom-overlay');
    if (!overlay) return;

    const arChat = document.getElementById('ar-chat');
    const arInput = document.getElementById('ar-chat-input');
    if (arInput) arInput.setAttribute('autocomplete', 'one-time-code');
    const arSendBtn = document.getElementById('ar-send-btn');
    const arVoiceBtn = document.getElementById('ar-voice-btn');
    const arExitBtn = document.getElementById('ar-exit-btn');
    const arPlaceBtn = document.getElementById('ar-place-btn');
    const arScaleBtn = document.getElementById('ar-scale-btn');
    const arStatus = document.getElementById('ar-status');

    let arVoiceActive = false;

    // --- Overlay activation via AR session events ---
    window.addEventListener('ar-session-start', () => {
        overlay.classList.add('ar-active');
        if (arStatus) arStatus.textContent = 'Point at a surface';
    });

    window.addEventListener('ar-session-end', () => {
        overlay.classList.remove('ar-active');
        stopARVoice();
    });

    window.addEventListener('ar-floor-detected', () => {
        if (arStatus) arStatus.textContent = 'Avatar placed — talk to me!';
    });

    // --- Send text message from AR input ---
    function arSendMessage() {
        if (!arInput) return;
        const text = arInput.value.trim();
        if (!text) return;
        arInput.value = '';
        appendARBubble('user', text);
        // Reuse the main chat pipeline
        if (typeof handleUserMessage === 'function') {
            handleUserMessage(text);
        }
    }

    if (arSendBtn) arSendBtn.addEventListener('click', arSendMessage);
    if (arInput) {
        arInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') arSendMessage();
        });
    }

    // --- Voice input in AR ---
    function startARVoice() {
        arVoiceActive = true;
        if (arVoiceBtn) arVoiceBtn.classList.add('ar-listening');
        // Use the existing speech recognition system
        if (typeof startVoiceInput === 'function') {
            startVoiceInput();
        }
    }

    function stopARVoice() {
        arVoiceActive = false;
        if (arVoiceBtn) arVoiceBtn.classList.remove('ar-listening');
        if (typeof stopVoiceInput === 'function') {
            stopVoiceInput();
        }
    }

    if (arVoiceBtn) {
        arVoiceBtn.addEventListener('click', () => {
            if (arVoiceActive) stopARVoice();
            else startARVoice();
        });
    }

    // --- Exit AR ---
    if (arExitBtn) {
        arExitBtn.addEventListener('click', () => {
            try {
                const engine = window.NEXUS_VIEWER;
                if (engine?.arSupport?.isARActive) {
                    engine.arSupport.toggleAR();
                }
            } catch (e) {
                console.warn('[AR Overlay] Exit error:', e);
            }
        });
    }

    // --- Place avatar ---
    if (arPlaceBtn) {
        arPlaceBtn.addEventListener('click', () => {
            try {
                const engine = window.NEXUS_VIEWER;
                if (engine?.arSupport && engine?.avatarManager?.currentRoot) {
                    engine.arSupport.placeAvatarAtReticle(engine.avatarManager.currentRoot);
                    if (arStatus) arStatus.textContent = 'Avatar placed — talk to me!';
                }
            } catch (e) {
                console.warn('[AR Overlay] Place error:', e);
            }
        });
    }

    // --- Scale toggle ---
    let arScaleLevel = 1;
    const SCALE_LEVELS = [1, 0.5, 0.25, 1.5];
    if (arScaleBtn) {
        arScaleBtn.addEventListener('click', () => {
            try {
                arScaleLevel = (arScaleLevel + 1) % SCALE_LEVELS.length;
                const engine = window.NEXUS_VIEWER;
                if (engine?.arSupport && engine?.avatarManager?.currentRoot) {
                    engine.arSupport.setAvatarScale(engine.avatarManager.currentRoot, SCALE_LEVELS[arScaleLevel]);
                    if (arScaleBtn) arScaleBtn.textContent = `SIZE ${SCALE_LEVELS[arScaleLevel]}x`;
                }
            } catch (e) {
                console.warn('[AR Overlay] Scale error:', e);
            }
        });
    }

    // --- Mirror chat messages into the AR overlay ---
    function appendARBubble(role, text) {
        if (!arChat) return;
        const bubble = document.createElement('div');
        bubble.className = `ar-chat-bubble ar-chat-bubble--${role === 'user' ? 'user' : 'bot'}`;
        bubble.textContent = text;
        arChat.appendChild(bubble);
        // Keep only last 8 messages visible to avoid clutter over camera
        while (arChat.children.length > 8) {
            arChat.removeChild(arChat.firstChild);
        }
        arChat.scrollTop = arChat.scrollHeight;
    }

    // Expose so the main addMessageToHistory can mirror to AR
    window._arAppendBubble = appendARBubble;
})();

/* =====================================================================
   FoveAI KOKORO TTS PROVIDER — Registers window.TTSProvider for the
   pluggable TTS engine path in speakText() (line 3763).
   Uses the nexus-proxy /api/tts endpoint which proxies to Kokoro on :8004.
   ===================================================================== */
(function registerTTSProvider() {
    'use strict';

    // Read settings from localStorage (set by _fetchEnvConfig from .env)
    const ttsEnabled = localStorage.getItem('foveai_tts_enabled') !== 'false';
    const kokoroVoice = localStorage.getItem('foveai_kokoro_voice') || 'af_heart';
    const kokoroSpeed = parseFloat(localStorage.getItem('foveai_kokoro_speed') || '1.08');

    let _currentAudio = null;
    let _isSpeaking = false;

    window.TTSProvider = {
        isActive: function () {
            return ttsEnabled;
        },

        speak: function (text, options) {
            options = options || {};
            const onEnd = options.onEnd || function () {};
            const onError = options.onError || function () {};

            // Strip bracket tokens before sending to TTS
            const cleanText = text
                .replace(/<[^>]+>/g, '')
                .replace(/[<>]/g, '')
                .replace(/\s+/g, ' ')
                .trim();

            if (!cleanText) {
                onEnd();
                return;
            }

            _isSpeaking = true;

            // Build TTS URL with voice and speed params
            const params = new URLSearchParams({
                text: cleanText,
                voice: kokoroVoice,
                speed: String(kokoroSpeed)
            });
            const ttsUrl = '/api/tts?' + params.toString();

            try {
                if (!_currentAudio) {
                    _currentAudio = new Audio();
                    _currentAudio.crossOrigin = "anonymous"; // CRITICAL for WebXR / createMediaElementSource
                    window.NEXUS_TTS_AUDIO = _currentAudio;

                    // Route through Web Audio for procedural reverb/echo
                    try {
                        const ctx = window.foveaiAudioContext || new (window.AudioContext || window.webkitAudioContext)();
                        window.foveaiAudioContext = ctx;

                        const source = ctx.createMediaElementSource(_currentAudio);

                        const dryGain = ctx.createGain();
                        dryGain.gain.value = 1.0;

                        const wetGain = ctx.createGain();
                        wetGain.gain.value = 0.22; // 22% wet mix (spacious but clear)

                        const delayNode = ctx.createDelay(2.0);
                        delayNode.delayTime.value = 0.16; // 160ms delay

                        const feedbackNode = ctx.createGain();
                        feedbackNode.gain.value = 0.28; // feedback decay

                        const filterNode = ctx.createBiquadFilter();
                        filterNode.type = 'lowpass';
                        filterNode.frequency.value = 1500; // dark echo

                        // Wire connections
                        source.connect(dryGain);
                        dryGain.connect(ctx.destination);

                        source.connect(delayNode);
                        delayNode.connect(filterNode);
                        filterNode.connect(feedbackNode);
                        feedbackNode.connect(delayNode); // feedback loop

                        filterNode.connect(wetGain);
                        wetGain.connect(ctx.destination);

                        // Apply stored output device if set
                        const savedSpeaker = localStorage.getItem('foveai_speaker_device_id');
                        if (savedSpeaker && typeof _currentAudio.setSinkId === 'function') {
                            _currentAudio.setSinkId(savedSpeaker).catch(() => {});
                        }
                    } catch (e) {
                        console.warn('[TTSProvider] Web Audio setup failed (reverb bypassed):', e);
                    }
                }

                // Ensure context is running (required for Chrome autoplay guidelines)
                if (window.foveaiAudioContext && window.foveaiAudioContext.state === 'suspended') {
                    window.foveaiAudioContext.resume();
                }

                _currentAudio.src = ttsUrl;
                _currentAudio.volume = options.volume || 1.0;

                _currentAudio.onended = function () {
                    _isSpeaking = false;
                    onEnd();
                };

                _currentAudio.onerror = function (e) {
                    console.warn('[TTSProvider] Kokoro playback error, falling back to Web Speech API:', e);
                    _isSpeaking = false;
                    onError();
                };

                _currentAudio.play().catch(function (err) {
                    console.warn('[TTSProvider] Kokoro play() failed:', err);
                    _isSpeaking = false;
                    onError();
                });
            } catch (err) {
                console.warn('[TTSProvider] Kokoro init error:', err);
                _isSpeaking = false;
                onError();
            }
        },

        stop: function () {
            if (_currentAudio) {
                try { _currentAudio.pause(); } catch (_) {}
                try { _currentAudio.currentTime = 0; } catch (_) {}
            }
            _isSpeaking = false;
        },

        isSpeaking: function () {
            return _isSpeaking;
        }
    };

    console.log('[TTSProvider] Registered — Kokoro TTS via /api/tts proxy (voice=' + kokoroVoice + ')');
})();

/* =====================================================================
   FoveAI MEMORY BRIDGE — Persists personality/memory data to Dexie/IndexedDB
   and backs up to the Memory server via /api/memory/backup.
   ===================================================================== */
(function registerMemoryBridge() {
    'use strict';

    const MEMORY_KEYS = [
        'foveai_personality',
        'foveai_user_name',
        'foveai_last_session',
        'foveai_boot_count',
        'foveai_preferred_voice',
        'foveai_chat_history',
        'foveai_greeting_seen',
    ];

    const BACKUP_ENDPOINT = '/api/memory/backup';
    const RESTORE_ENDPOINT = '/api/memory/restore';
    const SYNC_INTERVAL_MS = 60000; // Backup every 60s
    const DEBOUNCE_MS = 3000;

    let _debounceTimer = null;

    function collectSnapshot() {
        const snap = {};
        for (const key of MEMORY_KEYS) {
            const val = localStorage.getItem(key);
            if (val !== null) snap[key] = val;
        }
        return snap;
    }

    async function pushBackup() {
        const snapshot = collectSnapshot();
        if (Object.keys(snapshot).length === 0) return;
        try {
            const resp = await fetch(BACKUP_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source: '3d_avatar', keys: snapshot }),
            });
            if (resp.ok) {
                console.log('[MemoryBridge] Backup pushed OK');
            }
        } catch (err) {
            // Silent — memory server may not be running
        }
    }

    async function pullRestore() {
        try {
            const resp = await fetch(RESTORE_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source: '3d_avatar' }),
            });
            if (!resp.ok) return false;
            const data = await resp.json();
            const keys = data.keys || {};
            let restored = 0;
            for (const [key, value] of Object.entries(keys)) {
                if (localStorage.getItem(key) === null) {
                    localStorage.setItem(key, value);
                    restored++;
                }
            }
            if (restored > 0) {
                console.log('[MemoryBridge] Restored ' + restored + ' keys from server');
            }
            return restored > 0;
        } catch (err) {
            return false;
        }
    }

    function scheduleDebouncedBackup() {
        if (_debounceTimer) clearTimeout(_debounceTimer);
        _debounceTimer = setTimeout(pushBackup, DEBOUNCE_MS);
    }

    // On boot: try to restore if localStorage looks empty
    (async function () {
        const missingCount = MEMORY_KEYS.filter(function (k) {
            return localStorage.getItem(k) === null;
        }).length;
        if (missingCount > MEMORY_KEYS.length / 2) {
            console.log('[MemoryBridge] Browser cleanse detected — restoring from server...');
            await pullRestore();
        }
    })();

    // Periodic backup
    setInterval(pushBackup, SYNC_INTERVAL_MS);

    // Hook localStorage.setItem for same-tab changes
    const _origSetItem = localStorage.setItem.bind(localStorage);
    localStorage.setItem = function (key, value) {
        _origSetItem(key, value);
        if (MEMORY_KEYS.includes(key)) {
            scheduleDebouncedBackup();
        }
    };

    // Backup on page unload
    window.addEventListener('beforeunload', function () {
        const snapshot = collectSnapshot();
        if (Object.keys(snapshot).length > 0) {
            try {
                navigator.sendBeacon(BACKUP_ENDPOINT, JSON.stringify({
                    source: '3d_avatar',
                    keys: snapshot,
                }));
            } catch (_) {}
        }
    });

    console.log('[MemoryBridge] Initialized — watching ' + MEMORY_KEYS.length + ' keys');
})();

/* =====================================================================
   JEN'S GREETING SYSTEM — Dynamic welcome message on first load.
   Reads personality from localStorage, speaks a personalized greeting.
   ===================================================================== */
(function registerGreetingSystem() {
    'use strict';

    // Wait for avatar to be ready before greeting
    function tryGreet() {
        const hasAvatar = !!window.NEXUS_VIEWER?.avatarManager?.currentRoot;
        const hasTTS = !!window.TTSProvider;
        const greetingSeen = localStorage.getItem('foveai_greeting_seen');

        if (!hasAvatar || !hasTTS) {
            // Retry in 1s
            setTimeout(tryGreet, 1000);
            return;
        }

        // Only greet once per session
        if (greetingSeen === 'true') {
            console.log('[Greeting] Already greeted this session');
            return;
        }

        // Get user name from memory
        const userName = localStorage.getItem('foveai_user_name') || 'Darnell';

        // Build personalized greeting
        const greeting = 'Hello, thank you, welcome ' + userName + ', it\'s so happy to have you here.';

        console.log('[Greeting] Speaking: "' + greeting + '"');

        // Speak the greeting
        if (window.TTSProvider && window.TTSProvider.isActive()) {
            window.TTSProvider.speak(greeting, {
                onEnd: function () {
                    localStorage.setItem('foveai_greeting_seen', 'true');
                    console.log('[Greeting] Complete');
                }
            });
        }

        // Also show in chat
        if (typeof addMessageToHistory === 'function') {
            addMessageToHistory('avatar', greeting);
        }
    }

    // Start greeting check after a short delay (let init() finish)
    setTimeout(tryGreet, 3000);
})();

/* =====================================================================
   PATCH_LLM_PROXY_TEST_CONNECTION_V1
   - Fixes CORS by routing Claude + WatsonX (and OpenAI) via proxy
   - Adds Settings -> "Test Connection" button
   - Improves WatsonX auth: accept IAM API key OR Bearer access token
   ===================================================================== */

async function __nexusDetectProxyUrl() {
    if (window.__NEXUS_PROXY_URL__) return window.__NEXUS_PROXY_URL__;

    // Prefer same-origin /api/proxy if it exists.
    try {
        const r = await fetch('/api/proxy', { method: 'OPTIONS' });
        if (r && (r.status === 200 || r.status === 204)) {
            window.__NEXUS_PROXY_URL__ = '/api/proxy';
            return window.__NEXUS_PROXY_URL__;
        }
    } catch (_) { }

    // Fallback: local nexus-proxy
    const candidates = ['http://127.0.0.1:3001/proxy', 'http://localhost:3001/proxy'];
    for (const url of candidates) {
        try {
            const health = url.replace(/\/proxy$/, '/health');
            const r = await fetch(health, { method: 'GET' });
            if (r && r.ok) {
                window.__NEXUS_PROXY_URL__ = url;
                return window.__NEXUS_PROXY_URL__;
            }
        } catch (_) { }
    }

    window.__NEXUS_PROXY_URL__ = null;
    return null;
}

async function __nexusProxyFetch(upstreamUrl, fetchOptions) {
    const proxyUrl = await __nexusDetectProxyUrl();
    if (!proxyUrl) {
        throw new Error(
            'CORS proxy not running. Start it with: `node nexus-proxy/server.js` (local), or deploy on Vercel (production).'
        );
    }

    const method = (fetchOptions?.method || 'GET').toUpperCase();
    const headers = fetchOptions?.headers || {};
    const body = fetchOptions?.body;

    const payload = { url: upstreamUrl, method, headers, body: body === undefined ? undefined : body };

    const res = await fetch(proxyUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });

    return res;
}

// ---- WatsonX: turn IAM API key into Bearer token (cached) ----
let __nexusWatsonxTokenCache = { token: null, expMs: 0 };

function __looksLikeJwt(s) {
    return typeof s === 'string' && s.split('.').length === 3;
}

async function __getWatsonxBearer(apiKeyOrToken) {
    const raw = (apiKeyOrToken || '').trim();
    if (!raw) throw new Error('Missing WatsonX credential.');

    if (__looksLikeJwt(raw)) return raw;
    if (raw.toLowerCase().startsWith('bearer ')) return raw.slice(7).trim();

    const now = Date.now();
    if (__nexusWatsonxTokenCache.token && __nexusWatsonxTokenCache.expMs - now > 60_000) {
        return __nexusWatsonxTokenCache.token;
    }

    const form = new URLSearchParams();
    form.set('grant_type', 'urn:ibm:params:oauth:grant-type:apikey');
    form.set('apikey', raw);

    const res = await __nexusProxyFetch('https://iam.cloud.ibm.com/identity/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' },
        body: form.toString(),
    });

    const text = await res.text();
    if (!res.ok) throw new Error(`WatsonX IAM token error: ${res.status} ${text}`);

    const data = JSON.parse(text);
    const token = data.access_token;
    const expiresIn = Number(data.expires_in || 3600);
    if (!token) throw new Error('WatsonX IAM token response missing access_token.');

    __nexusWatsonxTokenCache = { token, expMs: now + expiresIn * 1000 };
    return token;
}

/**
 * Override: OpenAI via proxy.
 */
async function callOpenAI(userMessage) {
    const upstreamUrl = 'https://api.openai.com/v1/chat/completions';
    const res = await __nexusProxyFetch(upstreamUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${config.apiKey}` },
        body: JSON.stringify({
            model: config.model,
            messages: [
                { role: 'system', content: config.systemPrompt },
                { role: 'user', content: userMessage },
            ],
            max_tokens: 500,
        }),
    });

    const text = await res.text();
    if (!res.ok) throw new Error(`OpenAI API error: ${res.status} ${text}`);
    const data = JSON.parse(text);
    return data?.choices?.[0]?.message?.content || 'No response.';
}

/**
 * Override: Claude via proxy.
 */
async function callClaude(userMessage) {
    const upstreamUrl = 'https://api.anthropic.com/v1/messages';
    const res = await __nexusProxyFetch(upstreamUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-api-key': config.apiKey, 'anthropic-version': '2023-06-01' },
        body: JSON.stringify({
            model: config.model,
            max_tokens: 500,
            system: config.systemPrompt,
            messages: [{ role: 'user', content: userMessage }],
        }),
    });

    const text = await res.text();
    if (!res.ok) throw new Error(`Claude API error: ${res.status} ${text}`);
    const data = JSON.parse(text);
    return data?.content?.[0]?.text || 'No response.';
}

/**
 * Override: WatsonX via proxy.
 */
async function callWatsonX(userMessage) {
    const baseUrl = config.baseUrl || 'https://us-south.ml.cloud.ibm.com';
    const bearer = await __getWatsonxBearer(config.apiKey);

    const upstreamUrl = `${baseUrl}/ml/v1/text/generation?version=2023-05-29`;
    const res = await __nexusProxyFetch(upstreamUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${bearer}`, Accept: 'application/json' },
        body: JSON.stringify({
            model_id: config.model,
            input: `${config.systemPrompt}\n\nUser: ${userMessage}\n\nAssistant:`,
            parameters: { max_new_tokens: 300, temperature: 0.7 },
            project_id: config.watsonxProjectId,
        }),
    });

    const text = await res.text();
    if (!res.ok) throw new Error(`WatsonX API error: ${res.status} ${text}`);
    const data = JSON.parse(text);
    return data?.results?.[0]?.generated_text || 'No response.';
}

// ---- Test Connection button (Settings modal) ----
async function __nexusTestConnection() {
    const effectiveProvider = config.provider || (window._nexusConfig && window._nexusConfig.provider) || 'none';
    if (!config || effectiveProvider === 'none') return { ok: false, message: 'Select a provider first.' };
    if (effectiveProvider === 'foveai_native') return { ok: true, message: 'FoveAI Native is running' };
    if (!config.apiKey) return { ok: false, message: 'Enter an API key/token first.' };
    if (!config.model) return { ok: false, message: 'Select a model first.' };

    const ping = 'Respond with the single word: OK';

    try {
        const reply = await callLLM(ping);
        const short = String(reply || '')
            .trim()
            .slice(0, 120);
        return { ok: true, message: `✅ Connected. Reply: ${short || 'OK'}` };
    } catch (e) {
        return { ok: false, message: `❌ ${e.message || e}` };
    }
}

function __nexusWireTestButton() {
    const btn = document.getElementById('test-connection-btn');
    const status = document.getElementById('test-connection-status');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        // Pull latest values from the Settings inputs (test without saving)
        try {
            const selected = document.querySelector('input[name="provider"]:checked');
            const provider = selected ? selected.value : 'none';
            const apiKey = (document.getElementById('api-key')?.value || '').trim();
            const model = (document.getElementById('model-select')?.value || '').trim();
            const systemPrompt = (document.getElementById('system-prompt')?.value || config.systemPrompt).trim();
            const watsonxProjectId = (document.getElementById('watsonx-project-id')?.value || '').trim();
            const baseUrl = (document.getElementById('base-url')?.value || '').trim();

            config.provider = provider;
            config.apiKey = apiKey;
            config.model = model;
            config.systemPrompt = systemPrompt;
            config.watsonxProjectId = watsonxProjectId;
            config.baseUrl = baseUrl;
        } catch (_) { }

        btn.disabled = true;
        if (status) status.textContent = 'Testing...';

        const result = await __nexusTestConnection();
        if (status) status.textContent = result.message;

        btn.disabled = false;
    });
}

if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', __nexusWireTestButton);
} else {
    __nexusWireTestButton();
}

/* =====================================================================
   FETCH MODELS BUTTON
   - Manually fetch latest available models from the selected provider
   - Useful for refreshing model list without reloading the page
   ===================================================================== */
function __nexusWireFetchModelsButton() {
    const btn = document.getElementById('fetch-models-btn');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        const selected = document.querySelector('input[name="provider"]:checked');
        const provider = selected ? selected.value : 'none';

        if (provider === 'none') {
            alert('Please select a provider first (OpenAI, Claude, Watsonx, Ollama, or OllaBridge)');
            return;
        }

        if (provider === 'watsonx') {
            alert('Watsonx models are fetched automatically. Use the dropdown to see available models.');
            return;
        }

        if (provider === 'ollama') {
            alert('Ollama models are fetched automatically. Use the dropdown to see available models.');
            return;
        }

        const modelSelect = document.getElementById('model-select');
        if (!modelSelect) return;

        // Disable button during fetch
        btn.disabled = true;
        const originalText = btn.textContent;
        btn.textContent = '⏳ Fetching...';

        try {
            await fetchAndPopulateModels(provider, modelSelect);

            // Show success feedback
            btn.textContent = '✅ Updated!';
            setTimeout(() => {
                btn.textContent = originalText;
                btn.disabled = false;
            }, 2000);
        } catch (e) {
            console.error('[Main] Failed to fetch models:', e);
            btn.textContent = '❌ Error';
            setTimeout(() => {
                btn.textContent = originalText;
                btn.disabled = false;
            }, 2000);
        }
    });
}

if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', __nexusWireFetchModelsButton);
} else {
    __nexusWireFetchModelsButton();
}

/* =====================================================================
   OllaBridge Pairing Button
   - Exchanges a pairing code for a persistent bearer token
   - Stores the token in LLMManager settings (ollabridge.pair_token)
   ===================================================================== */
function __nexusWireOllaBridgePairButton() {
    const btn = document.getElementById('ollabridge-pair-btn');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        const codeInput = document.getElementById('ollabridge-pair-code');
        const statusDiv = document.getElementById('ollabridge-pair-status');
        if (!codeInput) return;

        const code = codeInput.value.trim().toUpperCase().replace(/-/g, '').replace(/\s+/g, '');

        if (!code || code.length < 4) {
            if (statusDiv) {
                statusDiv.textContent = 'Please enter a valid OllaBridge pairing code.';
                statusDiv.style.color = '#f59e0b';
            }
            return;
        }

        btn.disabled = true;
        btn.textContent = '⏳ Pairing...';
        if (statusDiv) {
            statusDiv.textContent = 'Exchanging code...';
            statusDiv.style.color = '#888';
        }

        try {
            // Auto-create LLMManager if not yet instantiated
            if (!window._nexusLLM) {
                if (typeof window.LLMManager !== 'function') {
                    throw new Error('LLMManager script not loaded. Refresh the page.');
                }
                window._nexusLLM = new window.LLMManager();
            }

            // Apply the current base_url and enable proxy before pairing
            // (proxy avoids CORS when pairing from a different origin)
            const baseUrlInput = document.getElementById('base-url');
            const pairPatch = {
                proxy: { enable_proxy: true, proxy_url: '/api/proxy' },
            };
            if (baseUrlInput && baseUrlInput.value.trim()) {
                pairPatch.ollabridge = { base_url: baseUrlInput.value.trim() };
            }
            window._nexusLLM.updateSettings(pairPatch);

            const result = await window._nexusLLM.pairWithOllaBridge(code);

            if (result.ok) {
                codeInput.value = '';
                if (statusDiv) {
                    statusDiv.textContent = `✅ Paired successfully! Device: ${result.device_id || 'unknown'}. Token saved.`;
                    statusDiv.style.color = '#22c55e';
                }
                btn.textContent = '✅ Paired!';

                // Refresh models now that we have a token
                const modelSelect = document.getElementById('model-select');
                if (modelSelect) {
                    fetchAndPopulateModels('ollabridge', modelSelect);
                }
            } else {
                if (statusDiv) {
                    statusDiv.textContent = `❌ ${result.error || 'Pairing failed'}`;
                    statusDiv.style.color = '#ef4444';
                }
                btn.textContent = '❌ Failed';
            }
        } catch (e) {
            if (statusDiv) {
                statusDiv.textContent = `❌ Error: ${e.message}`;
                statusDiv.style.color = '#ef4444';
            }
            btn.textContent = '❌ Error';
        }

        setTimeout(() => {
            btn.textContent = '🔗 Pair';
            btn.disabled = false;
        }, 3000);
    });
}

window.addEventListener('DOMContentLoaded', __nexusWireOllaBridgePairButton);

/* =====================================================================
   DEBUG HELPER: Check Stored API Keys
   - Run window.debugAPIKeys() in console to see what's stored
   - Helps diagnose authentication issues
   ===================================================================== */
window.debugAPIKeys = function () {
    console.log('=== NEXUS API KEY DEBUGGER ===\n');

    try {
        // Check unified settings
        const unified = localStorage.getItem('nexus_llm_settings');
        if (unified) {
            const settings = JSON.parse(unified);
            console.log('📦 Unified Settings (nexus_llm_settings):');
            console.log('  Provider:', settings.provider || 'none');

            if (settings.openai?.api_key) {
                const key = settings.openai.api_key;
                console.log(
                    '  OpenAI Key:',
                    key.substring(0, 12) + '...' + key.substring(key.length - 4),
                    `(${key.length} chars)`
                );
                console.log('    ✓ Starts with:', key.substring(0, 7));
                console.log('    ✓ Valid format:', key.startsWith('sk-') && !key.startsWith('sk-ant-') ? '✅' : '❌');
            }

            if (settings.claude?.api_key) {
                const key = settings.claude.api_key;
                console.log(
                    '  Claude Key:',
                    key.substring(0, 12) + '...' + key.substring(key.length - 4),
                    `(${key.length} chars)`
                );
                console.log('    ✓ Starts with:', key.substring(0, 7));
                console.log('    ✓ Valid format:', key.startsWith('sk-ant-') ? '✅' : '❌');
            }

            if (settings.watsonx?.api_key) {
                const key = settings.watsonx.api_key;
                console.log(
                    '  Watsonx Key:',
                    key.substring(0, 12) + '...' + key.substring(key.length - 4),
                    `(${key.length} chars)`
                );
            }

            if (settings.ollama?.base_url) {
                console.log('  Ollama URL:', settings.ollama.base_url);
            }
        } else {
            console.log('📦 No unified settings found (nexus_llm_settings is empty)');
        }

        // Check legacy settings
        console.log('\n📜 Legacy Settings:');
        const legacyProvider = localStorage.getItem('ai_provider');
        const legacyKey = localStorage.getItem('ai_api_key');
        if (legacyProvider) {
            console.log('  Provider:', legacyProvider);
        }
        if (legacyKey) {
            console.log('  API Key:', legacyKey.substring(0, 12) + '...' + legacyKey.substring(legacyKey.length - 4));
        }

        console.log('\n💡 Tips:');
        console.log('  - OpenAI keys should start with "sk-" (NOT "sk-ant-")');
        console.log('  - Claude keys should start with "sk-ant-"');
        console.log('  - If keys look wrong, delete them in Settings and re-enter');
        console.log('  - To reset: localStorage.clear() then reload page');
        console.log('\n=== END DEBUG ===');
    } catch (e) {
        console.error('Error debugging API keys:', e);
    }
};

console.log('💡 Tip: Run window.debugAPIKeys() in console to check your stored API keys');

/* =====================================================================
   SPICY MODE — Refresh UI when spicy toggle changes
   ===================================================================== */
if (window.NEXUS_SPICY) {
    window.NEXUS_SPICY.onChange(function () {
        // Refresh Pose Studio panel (re-filters NAV_PRESETS)
        if (window.poseStudioPanel && typeof window.poseStudioPanel.refresh === 'function') {
            window.poseStudioPanel.refresh();
        }
        // Show/hide adult optgroup in settings VR pose dropdown
        var adultGroup = document.getElementById('vr-pose-adult-group');
        if (adultGroup) {
            adultGroup.style.display = window.NEXUS_SPICY.isEnabled() ? '' : 'none';
        }
        // Refresh talk style dropdown if present in Pose Studio
        var talkSelect = document.getElementById('poseTalkStyleSelect');
        if (talkSelect && window.NEXUS_ANIMATION_MANAGER) {
            var styles = window.NEXUS_ANIMATION_MANAGER.getTalkStyles();
            talkSelect.innerHTML = '';
            for (var i = 0; i < styles.length; i++) {
                var opt = document.createElement('option');
                opt.value = styles[i].id;
                opt.textContent = styles[i].label;
                talkSelect.appendChild(opt);
            }
        }
        console.log('[main] Spicy mode changed:', window.NEXUS_SPICY.isEnabled() ? 'ON' : 'OFF');
    });
}

// [NEXUS OVERHAUL] VAD Pin Toggle
// [NEXUS OVERHAUL] Director Prompt Injector
// [NEXUS OVERHAUL] Director Manual Surprise
window.triggerDirectorSurprise = async function () {
    console.log('[DIRECTOR] Manual surprise triggered by user.');
    showMessage('Requesting plot twist from Director...', 'info');
    try {
        // Fallback local hardcoded twist if backend not ready, 
        // ideally hits an endpoint to Python DirectorManager
        const fallbackTwist = "Make her notice a strange light flickering in the distance.";

        if (window.chatHistory) {
            window.chatHistory.addMessage('system', `[DIRECTOR SURPRISE]: ${fallbackTwist}`);
        }
        if (window.NEXUS_LLM?.generateResponse) {
            await window.NEXUS_LLM.generateResponse(`(You feel a sudden impulse: ${fallbackTwist})`);
        }
    } catch (err) {
        console.error('[DIRECTOR] Failed to trigger surprise:', err);
    }
};

// [NEXUS OVERHAUL] Quick Prompts Menu
// [NEXUS OVERHAUL] To-Do Tracker Logic
window.NexusTodos = JSON.parse(localStorage.getItem('nexus_todos') || '[]');

window.updateTodoUI = function () {
    const btn = document.getElementById('ar-todo-btn');
    if (!btn) return;
    btn.classList.remove('todo-active', 'todo-success');
    if (window.NexusTodos.length > 0) {
        btn.classList.add('todo-active');
        btn.setAttribute('title', window.NexusTodos.length + ' Pending To-Dos');
    } else {
        btn.setAttribute('title', 'Add To-Do');
    }
};

window.addTodo = function (taskText) {
    window.NexusTodos.push({ id: Date.now(), text: taskText, done: false });
    localStorage.setItem('nexus_todos', JSON.stringify(window.NexusTodos));
    window.updateTodoUI();
    showMessage('To-Do Added: ' + taskText, 'info');
};

window.completeAllTodos = function () {
    window.NexusTodos = [];
    localStorage.setItem('nexus_todos', '[]');
    const btn = document.getElementById('ar-todo-btn');
    if (btn) {
        btn.classList.remove('todo-active');
        btn.classList.add('todo-success');
        setTimeout(() => btn.classList.remove('todo-success'), 2000);
    }
    showMessage('All To-Dos Completed!', 'info');
};

window.manualAddTodo = function () {
    const text = prompt("Enter a new To-Do:");
    if (text) window.addTodo(text);
};

// Override chatMessage to intercept [ADD_TODO]
const origShowMessage = window.showMessage;
window.showMessage = function (msg, type, skipHistory = false) {
    if (type === 'bot' || type === 'system') {
        const todoMatch = msg.match(/\[ADD_TODO:\s*(.*?)\]/i);
        if (todoMatch) {
            window.addTodo(todoMatch[1].trim());
            msg = msg.replace(/\[ADD_TODO:\s*.*?\]/i, '').trim();
        }
        if (msg.match(/\[COMPLETE_TODO\]/i)) {
        }

        // [NEXUS OVERHAUL] Director AR Tags
        const soundMatch = msg.match(/\[PLAY_SOUND:\s*(.*?)\]/i);
        if (soundMatch && window.DirectorAR) {
            window.DirectorAR.playSound(soundMatch[1].trim());
            msg = msg.replace(/\[PLAY_SOUND:\s*.*?\]/i, "").trim();
        }

        const thoughtMatch = msg.match(/\[SHOW_THOUGHT:\s*(.*?)\]/i);
        if (thoughtMatch && window.DirectorAR) {
            window.DirectorAR.showThought(thoughtMatch[1].trim());
            msg = msg.replace(/\[SHOW_THOUGHT:\s*.*?\]/i, "").trim();
        }

        const holodeckMatch = msg.match(/\[HOLODECK:\s*(.*?)\]/i);
        if (holodeckMatch && window.DirectorAR) {
            window.DirectorAR.holodeck(holodeckMatch[1].trim());
            msg = msg.replace(/\[HOLODECK:\s*.*?\]/i, "").trim();
            window.completeAllTodos();
            msg = msg.replace(/\[COMPLETE_TODO\]/i, '').trim();
        }
    }
    if (msg) origShowMessage(msg, type, skipHistory);
};

// [NEXUS OVERHAUL] Dynamic Custom Prompts Logic
window.NexusCustomPrompts = JSON.parse(localStorage.getItem('nexus_custom_prompts') || JSON.stringify([
    { id: '1', category: 'system', text: 'Give me the latest news updates.' },
    { id: '2', category: 'organic', text: 'Tell me a story.' },
    { id: '3', category: 'system', text: 'What is my current objective?' },
    { id: '4', category: 'organic', text: 'Tell me everything you know about me.' }
]));

window.currentPromptTab = 'system';

window.renderQuickPrompts = function () {
    const list = document.getElementById('quick-prompts-list');
    if (!list) return;
    list.innerHTML = '';
    const filtered = window.NexusCustomPrompts.filter(p => p.category === window.currentPromptTab);
    filtered.forEach(p => {
        const btn = document.createElement('button');
        btn.className = 'glass-btn action-btn';
        btn.style = 'font-size:14px; text-align:left; padding:8px; display:flex; gap:8px; align-items:center;';
        btn.innerHTML = '<span>💬</span>';
        btn.onclick = () => window.sendQuickPrompt(p.text);
        list.appendChild(btn);
    });
};

window.switchPromptTab = function (tabName) {
    window.currentPromptTab = tabName;
    document.querySelectorAll('.prompt-tab').forEach(b => b.classList.remove('active'));
    const targetTab = document.querySelector(`.prompt-tab[onclick="switchPromptTab('${tabName}')"]`);
    if (targetTab) targetTab.classList.add('active');
    window.renderQuickPrompts();
};

window.openPromptEditor = function () {
    document.getElementById('prompt-editor-ui').style.display = 'flex';
    window.renderPromptEditorList();
};
window.closePromptEditor = function () {
    document.getElementById('prompt-editor-ui').style.display = 'none';
    window.renderQuickPrompts();
};

window.renderPromptEditorList = function () {
    const list = document.getElementById('prompt-edit-list');
    list.innerHTML = '';
    window.NexusCustomPrompts.forEach(p => {
        const row = document.createElement('div');
        row.style = 'display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.05); padding:5px; border-radius:4px;';
        row.innerHTML = `<span style="color:#fff; font-size:12px;">${p.text}</span>
                         <button style="background:transparent; border:none; color:#ff4444; cursor:pointer;" onclick="deleteCustomPrompt('${p.id}')">X</button>`;
        list.appendChild(row);
    });
};

window.addCustomPrompt = function () {
    const text = document.getElementById('new-prompt-text').value.trim();
    const cat = document.getElementById('new-prompt-category').value;
    if (text) {
        window.NexusCustomPrompts.push({ id: Date.now().toString(), category: cat, text: text });
        localStorage.setItem('nexus_custom_prompts', JSON.stringify(window.NexusCustomPrompts));
        document.getElementById('new-prompt-text').value = '';
        window.renderPromptEditorList();
    }
};

window.deleteCustomPrompt = function (id) {
    window.NexusCustomPrompts = window.NexusCustomPrompts.filter(p => p.id !== id);
    localStorage.setItem('nexus_custom_prompts', JSON.stringify(window.NexusCustomPrompts));
    window.renderPromptEditorList();
};
window.toggleQuickPrompts = function () {
    const ui = document.getElementById('quick-prompts-ui');
    if (ui.style.display === 'none' || !ui.style.display) {
        ui.style.display = 'flex';
    } else {
        ui.style.display = 'none';
    }
};

window.sendQuickPrompt = async function (text) {
    console.log('[QuickPrompt] Sending:', text);
    const ui = document.getElementById('quick-prompts-ui');
    ui.style.display = 'none';

    // Simulate user typing and sending it
    const inputField = document.getElementById('chat-input');
    if (inputField) {
        inputField.value = text;
        const sendBtn = document.getElementById('send-btn');
        if (sendBtn) sendBtn.click();
    }
};

window.toggleInbox = function () {
    const ui = document.getElementById('inbox-ui');
    if (ui.style.display === 'none' || !ui.style.display) {
        ui.style.display = 'flex';
        window.fetchInbox();
    } else {
        ui.style.display = 'none';
    }
};

window.fetchInbox = async function () {
    const list = document.getElementById('inbox-list');
    const countBadge = document.getElementById('inbox-count');
    try {
        const res = await fetch('/api/inbox');
        if (!res.ok) throw new Error('Network response was not ok');
        const data = await res.json();
        const messages = data.messages || [];

        countBadge.innerText = messages.length.toString();
        list.innerHTML = '';

        if (messages.length === 0) {
            list.innerHTML = '<div style="color:#aaa; font-style:italic;">No messages in inbox.</div>';
            return;
        }

        messages.forEach(msg => {
            const div = document.createElement('div');
            div.style.padding = '8px';
            div.style.background = 'rgba(0,229,255,0.1)';
            div.style.borderLeft = '3px solid var(--neon-cyan)';
            div.style.borderRadius = '4px';
            div.innerText = msg;
            list.appendChild(div);
        });
    } catch (e) {
        list.innerHTML = '<div style="color:#ff4444;">Failed to load inbox.</div>';
    }
};

window.clearInbox = async function () {
    try {
        const res = await fetch('/api/inbox/clear', { method: 'POST' });
        if (res.ok) {
            window.fetchInbox();
        }
    } catch (e) {
        console.error('Failed to clear inbox:', e);
    }
};

window.togglePromptInjector = function () {
    const ui = document.getElementById('prompt-injector-ui');
    const input = document.getElementById('prompt-injector-input');
    if (ui.style.display === 'none') {
        ui.style.display = 'block';
        if (input) {
            input.focus();
            // Handle enter key to submit
            input.onkeydown = async (e) => {
                if (e.key === 'Enter') {
                    const text = input.value.trim();
                    if (text) {
                        console.log('[DIRECTOR] Injecting impulse:', text);
                        try {
                            // Inject directly into the chat history as a system/director note
                            if (window.chatHistory) {
                                window.chatHistory.addMessage('system', `[DIRECTOR IMPULSE]: ${text}`);
                                showMessage('Impulse injected into subconscious.', 'info');
                            }

                            // Optionally trigger an immediate LLM generation if configured
                            if (window.NEXUS_LLM?.generateResponse) {
                                await window.NEXUS_LLM.generateResponse(`(You feel a sudden impulse: ${text})`);
                            }
                        } catch (err) {
                            console.error('[DIRECTOR] Failed to inject:', err);
                        }
                        input.value = '';
                        ui.style.display = 'none';
                    }
                }
            };
        }
    } else {
        ui.style.display = 'none';
    }
};
window.toggleVadPin = function () {
    isVadPinned = !isVadPinned;
    const pinBtn = document.getElementById('vad-pin-btn');
    if (isVadPinned) {
        if (pinBtn) pinBtn.classList.add('pinned');
        startVoiceInput();
        showMessage('Continuous Listening (VAD) Activated.', 'info');
    } else {
        if (pinBtn) pinBtn.classList.remove('pinned');
        stopVoiceInput();
        showMessage('Continuous Listening Disabled.', 'info');
    }
};
// Init UI on load
setTimeout(() => {
    if (window.updateTodoUI) window.updateTodoUI();
    if (window.renderQuickPrompts) window.renderQuickPrompts();
    if (window.DirectorAR && typeof scene !== "undefined" && typeof camera !== "undefined") {
        window.DirectorAR.init(scene, camera, typeof currentAvatar !== "undefined" ? currentAvatar : null);
    }
}, 2000);
