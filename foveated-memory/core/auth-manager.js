'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

/**
 * auth-manager.js — account store for the FoveAI proxy.
 *
 * Three credential shapes, resolved through resolveToken():
 *   1. Session tokens (fvs_*)   — from POST /api/auth/login, expire, carry userId
 *   2. API tokens    (lmx_*)   — long-lived team tokens (legacy swarm mode)
 *   3. Legacy bearer           — the token string itself is the workspace name
 *                                (jenna-vscode, LM Studio, solo scripts)
 *
 * Every endpoint should call resolveRequestAuth() so all of them scope
 * memory to the same workspace for a given credential.
 */

// Feature flags a non-admin user can be granted. Missing key = denied.
const FEATURE_CATALOG = {
    chat: 'Chat with the model',
    voice: 'TTS/STT voice features',
    tools: 'Agent tool calls (jenna-vscode)',
    xr: 'XR vessel / avatar endpoints',
    byok: 'Bring-your-own-key cloud models',
    cloud: 'Hosted NVIDIA NIM cloud models',
    settings_user: 'Change own user-level settings',
    settings_admin: 'Change core server settings',
    users_admin: 'Manage user accounts',
    memory_admin: 'Cross-workspace memory access',
};
const DEFAULT_MEMBER_FEATURES = ['chat', 'voice', 'tools', 'xr', 'byok', 'cloud', 'settings_user'];
const ADMIN_FEATURES = Object.keys(FEATURE_CATALOG);

const SESSION_TTL_MS = 1000 * 60 * 60 * 24 * 30; // 30 days

function hashPassword(password, salt) {
    salt = salt || crypto.randomBytes(16).toString('hex');
    const hash = crypto.scryptSync(String(password), salt, 64).toString('hex');
    return { salt, hash };
}

function verifyPassword(password, salt, expectedHash) {
    const { hash } = hashPassword(password, salt);
    const a = Buffer.from(hash, 'hex');
    const b = Buffer.from(expectedHash, 'hex');
    return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function parseSshEd25519(sshStr) {
    if (!sshStr || typeof sshStr !== 'string') throw new Error('invalid ssh key string');
    const parts = sshStr.trim().split(/\s+/);
    if (parts[0] !== 'ssh-ed25519' || !parts[1]) throw new Error('Not an ed25519 ssh key');
    const buf = Buffer.from(parts[1], 'base64');
    const typeLen = buf.readUInt32BE(0);
    const keyOffset = 4 + typeLen;
    const keyLen = buf.readUInt32BE(keyOffset);
    const rawKey = buf.slice(keyOffset + 4, keyOffset + 4 + keyLen);
    if (rawKey.length !== 32) throw new Error('Invalid raw key length: ' + rawKey.length);
    const spkiPrefix = Buffer.from('302a300506032b6570032100', 'hex');
    const spkiDer = Buffer.concat([spkiPrefix, rawKey]);
    return crypto.createPublicKey({ key: spkiDer, format: 'der', type: 'spki' });
}

function computeSshFingerprint(sshStr) {
    const parts = sshStr.trim().split(/\s+/);
    if (parts[0] !== 'ssh-ed25519' || !parts[1]) return null;
    const buf = Buffer.from(parts[1], 'base64');
    const hash = crypto.createHash('sha256').update(buf).digest('base64').replace(/=+$/, '');
    return `SHA256:${hash}`;
}

class AuthManager {
    constructor(dbPath) {
        this.dbFile = path.resolve(dbPath, 'auth.json');
        this._challenges = {}; // nonce -> { username, expires }
        this.data = {
            teams: {},    // teamId -> { name, created }
            tokens: {},   // lmx_* token -> { teamId, userId, role }
            users: {},    // username -> { passSalt, passHash, displayName, role, features[], workspaceId, created, disabled }
            sessions: {}, // fvs_* token -> { username, created, expires }
        };
        this.load();
    }

    load() {
        try {
            if (fs.existsSync(this.dbFile)) {
                const raw = fs.readFileSync(this.dbFile, 'utf8');
                const parsed = JSON.parse(raw);
                this.data = { ...this.data, ...parsed };
            } else {
                this.save();
            }
        } catch (e) {
            console.error('[AuthManager] Error loading auth db:', e.message);
        }
    }

    save() {
        try {
            const dir = path.dirname(this.dbFile);
            if (!fs.existsSync(dir)) {
                fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
            }
            fs.writeFileSync(this.dbFile, JSON.stringify(this.data, null, 2), { encoding: 'utf8', mode: 0o600 });
            try { fs.chmodSync(this.dbFile, 0o600); } catch (_) {}
        } catch (e) {
            console.error('[AuthManager] Error saving auth db:', e.message);
        }
    }

    /* ── teams / API tokens (unchanged legacy surface) ── */

    createTeam(teamId, name) {
        if (!this.data.teams) this.data.teams = {};
        if (this.data.teams[teamId]) return false;
        this.data.teams[teamId] = { name: name || teamId, created: new Date().toISOString() };
        this.save();
        return true;
    }

    generateToken(teamId, userId, role = 'member') {
        if (!this.data.teams[teamId]) throw new Error(`Team ${teamId} does not exist`);
        const token = `lmx_${crypto.randomBytes(16).toString('hex')}`;
        if (!this.data.tokens) this.data.tokens = {};
        this.data.tokens[token] = { teamId, userId, role, created: new Date().toISOString() };
        this.save();
        return token;
    }

    /* ── BYOK: user-supplied cloud API keys, AES-256-GCM at rest ──
       Key lives in memory_data/.byok_key (0600, auto-generated). Keys are
       never returned in full — getByokPublic() masks them for the UI. */

    _byokKey() {
        if (this._bk) return this._bk;
        const kf = path.resolve(path.dirname(this.dbFile), '.byok_key');
        if (fs.existsSync(kf)) {
            this._bk = fs.readFileSync(kf);
        } else {
            this._bk = crypto.randomBytes(32);
            fs.writeFileSync(kf, this._bk, { mode: 0o600 });
        }
        return this._bk;
    }

    _enc(text) {
        const iv = crypto.randomBytes(12);
        const c = crypto.createCipheriv('aes-256-gcm', this._byokKey(), iv);
        const ct = Buffer.concat([c.update(String(text), 'utf8'), c.final()]);
        return `${iv.toString('hex')}.${c.getAuthTag().toString('hex')}.${ct.toString('hex')}`;
    }

    _dec(blob) {
        try {
            const [iv, tag, ct] = String(blob).split('.').map(h => Buffer.from(h, 'hex'));
            const d = crypto.createDecipheriv('aes-256-gcm', this._byokKey(), iv);
            d.setAuthTag(tag);
            return Buffer.concat([d.update(ct), d.final()]).toString('utf8');
        } catch { return null; }
    }

    setByok(username, { provider, apiKey, baseUrl, model } = {}) {
        const u = this.data.users?.[username];
        if (!u) throw new Error('user not found');
        if (!apiKey || String(apiKey).length < 8) throw new Error('apiKey too short');
        u.byok = {
            provider: String(provider || 'openai'),
            apiKey: this._enc(apiKey),
            keyHint: String(apiKey).slice(0, 7) + '…',
            baseUrl: baseUrl ? String(baseUrl).replace(/\/+$/, '') : null,
            model: model ? String(model) : null,
            updated: new Date().toISOString(),
        };
        this.save();
        return this.getByokPublic(username);
    }

    getByok(username) {
        const b = this.data.users?.[username]?.byok;
        if (!b) return null;
        const apiKey = this._dec(b.apiKey);
        if (!apiKey) return null;
        return { provider: b.provider, apiKey, baseUrl: b.baseUrl, model: b.model };
    }

    getByokPublic(username) {
        const b = this.data.users?.[username]?.byok;
        if (!b) return null;
        return { provider: b.provider, keyHint: b.keyHint, baseUrl: b.baseUrl, model: b.model, updated: b.updated };
    }

    deleteByok(username) {
        const u = this.data.users?.[username];
        if (!u || !u.byok) return false;
        delete u.byok;
        this.save();
        return true;
    }

    /* ── usage metering (per user, per UTC day) ──
       Feeds the cloud-model quota. '__global__' counts across all users. */

    usageToday(username, kind) {
        const day = new Date().toISOString().slice(0, 10);
        return this.data.usage?.[username]?.[day]?.[kind] || 0;
    }

    bumpUsage(username, kind) {
        const day = new Date().toISOString().slice(0, 10);
        if (!this.data.usage) this.data.usage = {};
        if (!this.data.usage[username]) this.data.usage[username] = {};
        if (!this.data.usage[username][day]) this.data.usage[username][day] = {};
        const d = this.data.usage[username][day];
        d[kind] = (d[kind] || 0) + 1;
        this.save();
        return d[kind];
    }

    /* ── user accounts ── */

    userCount() {
        return Object.keys(this.data.users || {}).length;
    }

    createUser(username, password, opts = {}) {
        if (!this.data.users) this.data.users = {};
        username = String(username || '').trim().toLowerCase();
        // Unicode letters + digits welcome — Nordic/international names
        // (ø, æ, å, é, ü…) are "quite standard procedure" for testers.
        if (!/^[\p{L}\p{N}_.-]{2,32}$/u.test(username)) throw new Error('invalid username (2-32 chars: letters, numbers, _ . -)');
        if (this.data.users[username]) throw new Error('username taken');
        if (!password || String(password).length < 4) throw new Error('password too short (min 4)');

        const isFirst = this.userCount() === 0;
        const role = opts.role || (isFirst ? 'admin' : 'member');
        const { salt, hash } = hashPassword(password);
        const features = Array.isArray(opts.features)
            ? opts.features.filter(f => FEATURE_CATALOG[f])
            : (role === 'admin' ? ADMIN_FEATURES : DEFAULT_MEMBER_FEATURES);

        // Each user gets a personal memory workspace; admins additionally see
        // the shared team workspace via role.
        this.data.users[username] = {
            passSalt: salt,
            passHash: hash,
            displayName: opts.displayName || username,
            role,
            features,
            workspaceId: opts.workspaceId || `u_${username}`,
            created: new Date().toISOString(),
            disabled: false,
        };
        this.save();
        return this.publicUser(username);
    }

    publicUser(username) {
        const u = this.data.users?.[username];
        if (!u) return null;
        return {
            username,
            displayName: u.displayName,
            role: u.role,
            features: u.features,
            workspaceId: u.workspaceId,
            created: u.created,
            disabled: !!u.disabled,
            profilePicture: u.profilePicture || null,
            firstName: u.firstName || '',
            lastName: u.lastName || '',
            aiName: u.aiName || '',
            pubKeys: (u.pubKeys || []).map(pk => ({ fingerprint: pk.fingerprint, created: pk.created })),
        };
    }

    listUsers() {
        return Object.keys(this.data.users || {}).map(u => this.publicUser(u));
    }

    updateUser(username, patch = {}) {
        const u = this.data.users?.[username];
        if (!u) throw new Error('user not found');
        if (patch.displayName !== undefined) u.displayName = String(patch.displayName).slice(0, 64);
        if (patch.firstName !== undefined) u.firstName = String(patch.firstName).slice(0, 64);
        if (patch.lastName !== undefined) u.lastName = String(patch.lastName).slice(0, 64);
        if (patch.aiName !== undefined) u.aiName = String(patch.aiName).slice(0, 64);
        if (patch.profilePicture !== undefined) u.profilePicture = patch.profilePicture === null ? null : String(patch.profilePicture).slice(0, 512);
        if (patch.role && ['admin', 'member', 'guest'].includes(patch.role)) u.role = patch.role;
        if (Array.isArray(patch.features)) u.features = patch.features.filter(f => FEATURE_CATALOG[f]);
        if (patch.disabled !== undefined) u.disabled = !!patch.disabled;
        if (patch.password) {
            const { salt, hash } = hashPassword(patch.password);
            u.passSalt = salt; u.passHash = hash;
        }
        this.save();
        return this.publicUser(username);
    }

    deleteUser(username) {
        if (!this.data.users?.[username]) return false;
        delete this.data.users[username];
        // drop their sessions too
        for (const [tok, s] of Object.entries(this.data.sessions || {})) {
            if (s.username === username) delete this.data.sessions[tok];
        }
        this.save();
        return true;
    }

    /* ── sessions ── */

    login(username, password) {
        username = String(username || '').trim().toLowerCase();
        const u = this.data.users?.[username];
        if (!u || u.disabled) return null;
        if (!verifyPassword(password, u.passSalt, u.passHash)) return null;
        const token = `fvs_${crypto.randomBytes(24).toString('hex')}`;
        if (!this.data.sessions) this.data.sessions = {};
        this.data.sessions[token] = {
            username,
            created: new Date().toISOString(),
            expires: Date.now() + SESSION_TTL_MS,
        };
        this.save();
        return { token, user: this.publicUser(username) };
    }

    logout(token) {
        if (this.data.sessions?.[token]) {
            delete this.data.sessions[token];
            this.save();
            return true;
        }
        return false;
    }

    _resolveSession(token) {
        const s = this.data.sessions?.[token];
        if (!s) return null;
        if (s.expires && Date.now() > s.expires) {
            delete this.data.sessions[token];
            this.save();
            return null;
        }
        const u = this.data.users?.[s.username];
        if (!u || u.disabled) return null;
        return {
            teamId: u.workspaceId,
            userId: s.username,
            role: u.role,
            features: u.features,
            isSession: true,
        };
    }

    /* ── public key identity (Ed25519) ── */

    addPublicKey(username, sshPublicKeyStr) {
        username = String(username || '').trim().toLowerCase();
        const u = this.data.users?.[username];
        if (!u) throw new Error('user not found');
        const pubKeyObj = parseSshEd25519(sshPublicKeyStr);
        if (!pubKeyObj) throw new Error('failed to parse ed25519 key');
        const fingerprint = computeSshFingerprint(sshPublicKeyStr);
        if (!fingerprint) throw new Error('failed to compute fingerprint');
        if (!Array.isArray(u.pubKeys)) u.pubKeys = [];
        if (u.pubKeys.some(pk => pk.fingerprint === fingerprint)) {
            return { fingerprint, alreadyExists: true };
        }
        const entry = {
            key: sshPublicKeyStr.trim(),
            fingerprint,
            created: new Date().toISOString(),
        };
        u.pubKeys.push(entry);
        this.save();
        return { fingerprint, created: entry.created };
    }

    removePublicKey(username, fingerprint) {
        username = String(username || '').trim().toLowerCase();
        const u = this.data.users?.[username];
        if (!u || !Array.isArray(u.pubKeys)) return false;
        const initialLen = u.pubKeys.length;
        u.pubKeys = u.pubKeys.filter(pk => pk.fingerprint !== fingerprint);
        if (u.pubKeys.length !== initialLen) {
            this.save();
            return true;
        }
        return false;
    }

    createChallenge(username) {
        username = String(username || '').trim().toLowerCase();
        const u = this.data.users?.[username];
        if (!u || u.disabled) throw new Error('user not found or disabled');
        if (!Array.isArray(u.pubKeys) || u.pubKeys.length === 0) {
            throw new Error('user has no registered public keys');
        }
        const now = Date.now();
        for (const [n, ch] of Object.entries(this._challenges)) {
            if (ch.expires < now) delete this._challenges[n];
        }
        const nonce = crypto.randomBytes(32).toString('hex');
        const expires = now + 60000;
        this._challenges[nonce] = { username, expires };
        return { nonce, expires };
    }

    verifySignature(username, nonce, signatureB64) {
        username = String(username || '').trim().toLowerCase();
        const ch = this._challenges[nonce];
        if (!ch) return false;
        if (ch.username !== username || ch.expires < Date.now()) {
            delete this._challenges[nonce];
            return false;
        }
        delete this._challenges[nonce];

        const u = this.data.users?.[username];
        if (!u || u.disabled || !Array.isArray(u.pubKeys) || u.pubKeys.length === 0) {
            return false;
        }

        const challengeData = Buffer.from(`xrl-challenge:${username}:${nonce}`, 'utf8');
        let sigBuf;
        try {
            sigBuf = Buffer.from(signatureB64, 'base64');
        } catch (_) {
            return false;
        }

        for (const pk of u.pubKeys) {
            try {
                const pubKeyObj = parseSshEd25519(pk.key);
                if (crypto.verify(null, challengeData, pubKeyObj, sigBuf)) {
                    return true;
                }
            } catch (err) {
                console.error('[AuthManager] verifySignature error:', err.message);
            }
        }
        return false;
    }

    loginWithSignature(username, nonce, signatureB64) {
        username = String(username || '').trim().toLowerCase();
        if (!this.verifySignature(username, nonce, signatureB64)) {
            return null;
        }
        const token = `fvs_${crypto.randomBytes(24).toString('hex')}`;
        if (!this.data.sessions) this.data.sessions = {};
        this.data.sessions[token] = {
            username,
            created: new Date().toISOString(),
            expires: Date.now() + SESSION_TTL_MS,
            authType: 'ed25519',
        };
        this.save();
        return { token, user: this.publicUser(username) };
    }


    hasFeature(resolved, feature) {
        if (!resolved) return false;
        if (resolved.role === 'admin') return true;
        return Array.isArray(resolved.features) && resolved.features.includes(feature);
    }

    resolveToken(token) {
        // Session tokens first
        if (token && token.startsWith('fvs_')) {
            const s = this._resolveSession(token);
            if (s) return s;
            this.load();
            const s2 = this._resolveSession(token);
            if (s2) return s2;
            return null; // expired/unknown session = reject, no legacy fallthrough
        }

        // Registered API token
        if (this.data.tokens && this.data.tokens[token]) {
            return this.data.tokens[token];
        }
        this.load();
        if (this.data.tokens && this.data.tokens[token]) {
            return this.data.tokens[token];
        }

        // Legacy: the token IS the workspace ID (jenna-vscode, solo scripts)
        if (token && token !== 'lm-studio') {
            const sanitized = token.replace(/[^a-zA-Z0-9_-]/g, '_');
            return { teamId: sanitized, userId: 'solo_user', role: 'admin', features: ADMIN_FEATURES, isLegacy: true };
        }

        return { teamId: 'default', userId: 'anonymous', role: 'guest', features: [], isLegacy: true };
    }
}

let instance = null;
function getAuthManager(dbPath) {
    if (!instance) instance = new AuthManager(dbPath);
    return instance;
}

module.exports = { getAuthManager, AuthManager, FEATURE_CATALOG };
