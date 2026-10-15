'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

class AuthManager {
    constructor(dbPath) {
        this.dbFile = path.resolve(dbPath, 'auth.json');
        this.data = {
            users: {}, // username -> { passwordHash, salt, created }
            teams: {}, // teamId -> { name, created }
            tokens: {} // token -> { teamId, userId, role }
        };
        this.load();
    }

    load() {
        try {
            if (fs.existsSync(this.dbFile)) {
                const raw = fs.readFileSync(this.dbFile, 'utf8');
                this.data = JSON.parse(raw);
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
                fs.mkdirSync(dir, { recursive: true });
            }
            fs.writeFileSync(this.dbFile, JSON.stringify(this.data, null, 2), 'utf8');
        } catch (e) {
            console.error('[AuthManager] Error saving auth db:', e.message);
        }
    }

    createTeam(teamId, name) {
        if (!this.data.teams) this.data.teams = {};
        if (this.data.teams[teamId]) return false;
        
        this.data.teams[teamId] = {
            name: name || teamId,
            created: new Date().toISOString()
        };
        this.save();
        return true;
    }

    generateToken(teamId, userId, role = 'member') {
        if (!this.data.teams[teamId]) {
            throw new Error(`Team ${teamId} does not exist`);
        }
        
        // Generate a random token
        const token = `lmx_${crypto.randomBytes(16).toString('hex')}`;
        
        if (!this.data.tokens) this.data.tokens = {};
        this.data.tokens[token] = {
            teamId,
            userId,
            role,
            created: new Date().toISOString()
        };
        
        this.save();
        return token;
    }

    registerUser(username, password) {
        if (!this.data.users) this.data.users = {};
        if (this.data.users[username]) {
            return { error: 'Username already exists' };
        }
        
        const salt = crypto.randomBytes(16).toString('hex');
        const hash = crypto.pbkdf2Sync(password, salt, 100000, 64, 'sha512').toString('hex');
        
        this.data.users[username] = {
            passwordHash: hash,
            salt: salt,
            created: new Date().toISOString()
        };
        
        this.save();
        return { success: true, username };
    }

    authenticateUser(username, password) {
        this.load(); // Ensure fresh data
        if (!this.data.users || !this.data.users[username]) {
            return { error: 'Invalid username or password' };
        }
        
        const user = this.data.users[username];
        const hash = crypto.pbkdf2Sync(password, user.salt, 100000, 64, 'sha512').toString('hex');
        
        if (hash === user.passwordHash) {
            return { success: true, username };
        }
        
        return { error: 'Invalid username or password' };
    }

    /* ══ Profile persistence ══ persona fields (firstName/lastName/aiName)
       ride the user record so the setup questions answer themselves on the
       next login — the user should never re-type their name. */
    getProfile(username) {
        this.load();
        const u = this.data.users && this.data.users[username];
        if (!u) return null;
        return { username, firstName: u.firstName || '', lastName: u.lastName || '', aiName: u.aiName || '' };
    }

    setProfile(username, profile) {
        this.load();
        const u = this.data.users && this.data.users[username];
        if (!u) return { error: 'no such user' };
        for (const k of ['firstName', 'lastName', 'aiName']) {
            if (typeof profile?.[k] === 'string' && profile[k].trim()) u[k] = profile[k].trim().slice(0, 64);
        }
        this.save();
        return { success: true, profile: this.getProfile(username) };
    }

    resolveToken(token) {
        // First check if it's a registered multi-user token
        if (this.data.tokens && this.data.tokens[token]) {
            return this.data.tokens[token];
        }
        
        // Try reloading from disk in case it was created by another process
        this.load();
        if (this.data.tokens && this.data.tokens[token]) {
            return this.data.tokens[token];
        }
        
        // Fallback for legacy / solo mode: the token IS the workspace ID.
        // We sanitize it to use as a folder name.
        if (token && token !== 'lm-studio') {
            const sanitized = token.replace(/[^a-zA-Z0-9_-]/g, '_');
            return {
                teamId: sanitized,
                userId: 'solo_user',
                role: 'admin',
                isLegacy: true
            };
        }
        
        // Default fallback
        return {
            teamId: 'default',
            userId: 'anonymous',
            role: 'guest',
            isLegacy: true
        };
    }
}

// Singleton instance for the server
let instance = null;
function getAuthManager(dbPath) {
    if (!instance) {
        instance = new AuthManager(dbPath);
    }
    return instance;
}

module.exports = { getAuthManager, AuthManager };
