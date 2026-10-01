"use strict";
/**
 * contextAnalyzer.ts — Workspace context collection and analysis.
 * Gathers active file content, diagnostics, and git diff. Feeds to AI.
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
exports.ContextAnalyzer = void 0;
const vscode = __importStar(require("vscode"));
class ContextAnalyzer {
    _onChat;
    constructor(_onChat) {
        this._onChat = _onChat;
    }
    async analyzeContext() {
        const editor = vscode.window.activeTextEditor;
        const ws = vscode.workspace.workspaceFolders;
        if (!editor || !ws) {
            vscode.window.showWarningMessage('Open a file and workspace first');
            return;
        }
        const doc = editor.document;
        const fp = vscode.workspace.asRelativePath(doc.uri);
        const content = doc.getText().slice(0, 8000);
        const lang = doc.languageId;
        const probs = vscode.languages.getDiagnostics(doc.uri).filter(d => d.severity <= vscode.DiagnosticSeverity.Warning).slice(0, 10);
        let diff = '';
        try {
            const cp = require('child_process');
            diff = cp.execSync('git diff --unified=3 HEAD', { cwd: ws[0].uri.fsPath, timeout: 3000, windowsHide: true, maxBuffer: 8192 }).toString().slice(0, 4000);
        }
        catch { }
        let ctx = '## Workspace Context\n\n### Active File: ' + fp + ' (' + lang + ')\n\n`' + lang + '\n' + content + '\n`\n';
        if (probs.length) {
            ctx += '\n### Problems (' + probs.length + ')\n';
            probs.forEach(d => { ctx += '- ' + d.message + ' [line ' + (d.range.start.line + 1) + ']\n'; });
        }
        if (diff)
            ctx += '\n### Uncommitted Changes\n`diff\n' + diff + '\n`\n';
        ctx += '\nAnalyze this context and suggest specific edits or next actions.';
        await this._onChat(ctx);
    }
    async sendContextToChat(text) { await this._onChat(text); }
}
exports.ContextAnalyzer = ContextAnalyzer;
//# sourceMappingURL=contextAnalyzer.js.map