"use strict";
/**
 * sessionLogger.ts — Jenna Bonding Layer
 *
 * Tracks each VS Code session as a structured "bonding experience":
 * - Which files were touched
 * - Start/end time
 * - Conversation highlights
 * - Compressed summary injected into foveated memory on deactivation
 *
 * This makes Jenna remember what she and the developer worked on,
 * creating continuity across VS Code restarts.
 */
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.SessionLogger = void 0;
const vscode = __importStar(require("vscode"));
class SessionLogger {
    entry;
    client;
    disposables = [];
    constructor(workspaceId, workspaceFolder, client) {
        this.client = client;
        this.entry = {
            sessionId: this._generateId(),
            workspaceFolder,
            workspaceId,
            startTime: new Date().toISOString(),
            filesTouched: new Set(),
            conversationTurns: 0,
            highlights: [],
        };
        this._attachListeners();
    }
    _generateId() {
        return `sess_${Date.now().toString(36)}`;
    }
    _attachListeners() {
        // Track file saves as "touched" files
        const saveListener = vscode.workspace.onDidSaveTextDocument((doc) => {
            const rel = vscode.workspace.asRelativePath(doc.uri);
            this.entry.filesTouched.add(rel);
        });
        // Track file opens
        const openListener = vscode.window.onDidChangeActiveTextEditor((editor) => {
            if (editor?.document.uri.scheme === 'file') {
                const rel = vscode.workspace.asRelativePath(editor.document.uri);
                this.entry.filesTouched.add(rel);
            }
        });
        this.disposables.push(saveListener, openListener);
    }
    /** Call after each Jenna conversation turn to log highlights */
    recordTurn(userMessage, jennaResponse) {
        this.entry.conversationTurns++;
        // Extract highlights: lines with "TODO", "FIX", "IMPORTANT", or code blocks
        const highlight = this._extractHighlight(userMessage, jennaResponse);
        if (highlight) {
            this.entry.highlights.push(highlight);
        }
    }
    _extractHighlight(user, response) {
        const combined = `${user}\n${response}`;
        const markers = ['TODO', 'FIX', 'IMPORTANT', 'SOLVED', 'ERROR', 'PLAN'];
        for (const marker of markers) {
            const idx = combined.toUpperCase().indexOf(marker);
            if (idx >= 0) {
                // Grab 120 chars around the marker
                const start = Math.max(0, idx - 20);
                const end = Math.min(combined.length, idx + 100);
                return combined.slice(start, end).replace(/\n/g, ' ').trim();
            }
        }
        return null;
    }
    /** Build a compact bond summary string */
    _buildSummary() {
        const duration = this._durationStr();
        const files = Array.from(this.entry.filesTouched).slice(0, 10).join(', ') || 'none';
        const highlights = this.entry.highlights.slice(0, 5).map(h => `• ${h}`).join('\n') || 'No highlights';
        return [
            `=== Jenna Session Bond ===`,
            `Session: ${this.entry.sessionId}`,
            `Workspace: ${this.entry.workspaceFolder}`,
            `Date: ${this.entry.startTime.slice(0, 10)} | Duration: ${duration}`,
            `Turns: ${this.entry.conversationTurns}`,
            `Files touched: ${files}`,
            `Highlights:\n${highlights}`,
        ].join('\n');
    }
    _durationStr() {
        const start = new Date(this.entry.startTime).getTime();
        const end = Date.now();
        const mins = Math.round((end - start) / 60000);
        return mins < 60 ? `${mins}m` : `${Math.floor(mins / 60)}h ${mins % 60}m`;
    }
    /** Flush the session summary into foveated memory */
    async flush() {
        this.entry.endTime = new Date().toISOString();
        const summary = this._buildSummary();
        try {
            await this.client.injectBondMemory(summary, this.entry.workspaceId);
            console.log(`[jenna] session bond injected: ${this.entry.sessionId}`);
        }
        catch (err) {
            console.warn('[jenna] bond injection failed (non-fatal):', err);
        }
    }
    dispose() {
        this.disposables.forEach(d => d.dispose());
    }
    get sessionId() {
        return this.entry.sessionId;
    }
    get turnCount() {
        return this.entry.conversationTurns;
    }
}
exports.SessionLogger = SessionLogger;
//# sourceMappingURL=sessionLogger.js.map