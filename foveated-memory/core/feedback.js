'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

/**
 * feedback.js — feedback + targeted question store.
 *
 * questions: admin-posted prompts pushed to users — { id, text, targets, created, by }
 *   targets: ['all'] or a list of usernames.
 * responses: user submissions — { id, questionId|null, username, text, created, read }
 *   questionId null = unsolicited feedback from the free-form box.
 */

class FeedbackStore {
    constructor(dbPath) {
        this.dbFile = path.resolve(dbPath, 'feedback.json');
        this.data = { questions: [], responses: [] };
        this.load();
    }

    load() {
        try {
            if (fs.existsSync(this.dbFile)) {
                const parsed = JSON.parse(fs.readFileSync(this.dbFile, 'utf8'));
                this.data = { ...this.data, ...parsed };
            }
        } catch (e) {
            console.error('[Feedback] load failed:', e.message);
        }
    }

    save() {
        try {
            const dir = path.dirname(this.dbFile);
            if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
            fs.writeFileSync(this.dbFile, JSON.stringify(this.data, null, 2), 'utf8');
        } catch (e) {
            console.error('[Feedback] save failed:', e.message);
        }
    }

    /* ── questions (admin → users) ── */

    addQuestion(text, targets, by) {
        const q = {
            id: 'q_' + crypto.randomBytes(8).toString('hex'),
            text: String(text || '').slice(0, 2000),
            targets: Array.isArray(targets) && targets.length ? targets.map(String) : ['all'],
            created: new Date().toISOString(),
            by: by || 'admin',
        };
        this.data.questions.push(q);
        this.save();
        return q;
    }

    questionsFor(username) {
        return this.data.questions.filter(q =>
            q.targets.includes('all') || q.targets.includes(username));
    }

    deleteQuestion(id) {
        const before = this.data.questions.length;
        this.data.questions = this.data.questions.filter(q => q.id !== id);
        if (this.data.questions.length !== before) { this.save(); return true; }
        return false;
    }

    /* ── responses (users → admin) ── */

    addResponse(username, text, questionId) {
        const r = {
            id: 'r_' + crypto.randomBytes(8).toString('hex'),
            questionId: questionId || null,
            username: username || 'anonymous',
            text: String(text || '').slice(0, 4000),
            created: new Date().toISOString(),
            read: false,
        };
        this.data.responses.push(r);
        this.save();
        return r;
    }

    listResponses() {
        // newest first, with the question text attached for context
        const qById = {};
        for (const q of this.data.questions) qById[q.id] = q.text;
        return [...this.data.responses].reverse().map(r => ({
            ...r,
            questionText: r.questionId ? (qById[r.questionId] || '(question deleted)') : null,
        }));
    }

    markRead(id) {
        const r = this.data.responses.find(x => x.id === id);
        if (!r) return false;
        r.read = true;
        this.save();
        return true;
    }
}

let instance = null;
function getFeedbackStore(dbPath) {
    if (!instance) instance = new FeedbackStore(dbPath);
    return instance;
}

module.exports = { getFeedbackStore, FeedbackStore };
