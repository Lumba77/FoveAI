'use strict';

/**
 * ═══════════════════════════════════════════════════════════════════════
 * MODEL PROFILE LOADER
 * ═══════════════════════════════════════════════════════════════════════
 *
 * Single source of truth for model configuration.
 *
 * NAMING: XRLF_ is the canonical prefix going forward.
 *         LUMAX_ vars are kept in sync as legacy aliases during transition.
 *
 * A "profile" bundles ALL settings that must change together when
 * switching models: upstream URL, cognitive mode, context window,
 * token caps, fovea aggression, etc.
 *
 * Previously these were ~10 aliased env vars with two prefixes
 * (LUMAX_MODEL_LOCAL_ID, LOCAL_LLM_MODEL, XRLF_MODEL_CLOUD_ID,
 *  LUMAX_PROXY_MODEL, XRLF_COGNITIVE_MODE, LUMAX_COGNITIVE_MODE…)
 * causing races and forgotten updates whenever the model changed.
 *
 * Now: one call to applyProfile(modelName, config) updates everything.
 *
 * Profile registry : memory_data/model-profiles.json
 * Active selection : memory_data/active-model.json  (survives restarts)
 */

const fs   = require('fs');
const path = require('path');

const PROFILES_PATH     = path.resolve(__dirname, '..', 'memory_data', 'model-profiles.json');
const ACTIVE_MODEL_PATH = path.resolve(__dirname, '..', 'memory_data', 'active-model.json');

let _cache      = null;
let _cacheMtime = 0;

// ── Load profiles (hot-reloads when the file changes on disk) ─────────────────
function loadProfiles() {
    try {
        const stat = fs.statSync(PROFILES_PATH);
        if (_cache && stat.mtimeMs === _cacheMtime) return _cache;

        const raw = JSON.parse(fs.readFileSync(PROFILES_PATH, 'utf8'));

        // Build alias index: any alias or canonical name → canonical id
        const index = {};
        for (const [id, p] of Object.entries(raw)) {
            if (id.startsWith('_')) continue;   // skip _comment, _version
            index[id] = id;
            for (const alias of (p.aliases || [])) index[alias] = id;
        }

        _cache = { profiles: raw, index };
        _cacheMtime = stat.mtimeMs;
        return _cache;
    } catch (e) {
        console.warn('[ModelProfile] Could not load model-profiles.json:', e.message);
        return { profiles: {}, index: {} };
    }
}

// ── Resolve any name/alias to its full canonical profile ──────────────────────
function resolveProfile(modelName) {
    if (!modelName) return null;
    const { profiles, index } = loadProfiles();
    const canonical = index[modelName];
    if (!canonical) return null;
    return { id: canonical, ...profiles[canonical] };
}

// ── Apply a profile atomically ────────────────────────────────────────────────
//
//  Sets XRLF_ vars as canonical, mirrors to LUMAX_ legacy aliases so older
//  code paths still work during the LUMAX → XRLF rename transition.
//
//  Call this:
//    • at the top of handleChatCompletion (auto-apply per request)
//    • from the POST /v1/switch-model endpoint
//    • at startup (restore last active model from active-model.json)
//
// @param {string} modelName   model name or alias from request/user
// @param {object} config      live server config object (mutated in place)
// @returns {object|null}      the applied profile, or null if not found
function applyProfile(modelName, config) {
    const profile = resolveProfile(modelName);
    if (!profile) return null;

    const prevMode     = process.env.XRLF_COGNITIVE_MODE || process.env.LUMAX_COGNITIVE_MODE;
    const prevUpstream = config && config.upstream_url;

    // ── XRLF_ canonical vars (primary going forward) ──────────────────────
    process.env.XRLF_MODEL_ID              = profile.id;
    process.env.XRLF_COGNITIVE_MODE        = profile.cognitive_mode;
    process.env.XRLF_PROXY_TARGET          = profile.upstream_url;
    process.env.XRLF_SPOOF_CONTEXT_WINDOW  = String(profile.spoof_context_window || 0);
    process.env.XRLF_PROXY_AGGRESSION      = String(process.env.LUMAX_PROXY_AGGRESSION || process.env.XRLF_PROXY_AGGRESSION || profile.proxy_aggression || 2);
    process.env.XRLF_CLOUD_MAX_TOKENS_CAP  = String(profile.cloud_max_tokens_cap || 0);
    process.env.XRLF_CLOUD_PRESERVE_LAST   = String(profile.cloud_preserve_last ?? 4);

    if (profile.cognitive_mode === 'cloud') {
        process.env.XRLF_MODEL_CLOUD_ID    = profile.id;
    } else {
        process.env.XRLF_MODEL_LOCAL_ID    = profile.id;
    }

    // ── LUMAX_ legacy aliases (kept in sync during transition) ────────────
    process.env.LUMAX_MODEL_ID              = profile.id;
    process.env.LUMAX_COGNITIVE_MODE        = profile.cognitive_mode;
    process.env.LUMAX_PROXY_TARGET          = profile.upstream_url;
    process.env.LUMAX_SPOOF_CONTEXT_WINDOW  = String(profile.spoof_context_window || 0);
    process.env.LUMAX_PROXY_AGGRESSION      = String(process.env.LUMAX_PROXY_AGGRESSION || profile.proxy_aggression || 2);
    process.env.LUMAX_CLOUD_MAX_TOKENS_CAP  = String(profile.cloud_max_tokens_cap || 0);
    process.env.LUMAX_CLOUD_PRESERVE_LAST   = String(profile.cloud_preserve_last ?? 4);

    // Unify the old fragmented aliases into one
    if (profile.cognitive_mode === 'cloud') {
        process.env.LUMAX_MODEL_CLOUD_ID    = profile.id;
    } else {
        process.env.LUMAX_MODEL_LOCAL_ID    = profile.id;
        process.env.LOCAL_LLM_MODEL         = profile.id;   // oldest alias
        process.env.LUMAX_MODEL_ACTIVE_ID   = profile.id;   // hot-swap alias
    }

    // ── Live config object ────────────────────────────────────────────────
    if (config) {
        config.upstream_url    = profile.upstream_url.replace(/\/v1\/?$/, '');
        config._cloud_mode     = (profile.cognitive_mode === 'cloud');
        config._api_key        = profile.api_key_env
            ? (process.env[profile.api_key_env] || '')
            : '';
        config._active_profile = profile;
    }

    const modeChanged = prevMode !== profile.cognitive_mode;
    const urlChanged  = prevUpstream !== (config && config.upstream_url);

    console.log(
        `[ModelProfile] ✅ '${profile.id}' → ${profile.label} | ` +
        `mode=${profile.cognitive_mode} upstream=${profile.upstream_url} ` +
        `aggression=${profile.proxy_aggression} ctx=${profile.spoof_context_window}` +
        (modeChanged ? ' ⚡ MODE CHANGED' : '') +
        (urlChanged  ? ' 🔀 URL CHANGED'  : '')
    );

    return profile;
}

// ── Persist the active selection so it survives restarts ──────────────────────
function saveActiveModel(modelName) {
    try {
        fs.writeFileSync(ACTIVE_MODEL_PATH, JSON.stringify({
            model:     modelName,
            appliedAt: new Date().toISOString()
        }, null, 2));
    } catch (e) {
        console.warn('[ModelProfile] Could not write active-model.json:', e.message);
    }
}

// ── Read back the last saved selection (called at startup) ───────────────────
function loadActiveModel() {
    try {
        if (!fs.existsSync(ACTIVE_MODEL_PATH)) return null;
        return JSON.parse(fs.readFileSync(ACTIVE_MODEL_PATH, 'utf8'));
    } catch { return null; }
}

// ── Return all profiles (used by GET /v1/profiles) ────────────────────────────
function listProfiles() {
    const { profiles } = loadProfiles();
    return Object.entries(profiles)
        .filter(([k]) => !k.startsWith('_'))
        .map(([id, p]) => ({
            id,
            label:          p.label,
            role:           p.role,           // "primary" | "dormant"
            provider:       p.provider,
            cognitive_mode: p.cognitive_mode,
            upstream_url:   p.upstream_url,
            aliases:        p.aliases || []
        }));
}

module.exports = {
    resolveProfile,
    applyProfile,
    saveActiveModel,
    loadActiveModel,
    listProfiles
};
