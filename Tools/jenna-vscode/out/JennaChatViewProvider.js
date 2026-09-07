"use strict";
/**
 * JennaChatViewProvider.ts — Thin WebView shell.
 * Owns the webview lifecycle. Delegates all message handling to MessageRouter and sub-handlers.
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
exports.JennaChatViewProvider = void 0;
const vscode = __importStar(require("vscode"));
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const crypto = __importStar(require("crypto"));
const foveatedClient_1 = require("./memory/foveatedClient");
const messageRouter_1 = require("./handlers/messageRouter");
class JennaChatViewProvider {
    _extensionUri;
    _storageUri;
    _client;
    _logger;
    _statusBar;
    _workspaceId;
    _buffer;
    static viewType = 'jennaChat';
    _view;
    _router;
    constructor(_extensionUri, _storageUri, _client, _logger, _statusBar, _workspaceId, _buffer) {
        this._extensionUri = _extensionUri;
        this._storageUri = _storageUri;
        this._client = _client;
        this._logger = _logger;
        this._statusBar = _statusBar;
        this._workspaceId = _workspaceId;
        this._buffer = _buffer;
    }
    setPersona(personaId) {
        if (foveatedClient_1.PERSONAS[personaId]) {
            this._post({ type: 'persona_update', activePersona: personaId, personas: foveatedClient_1.PERSONAS });
        }
    }
    reload() {
        if (this._view) {
            this._view.webview.html = this._buildHtml(this._view.webview);
            this._post({ type: 'persona_update', activePersona: 'code', personas: foveatedClient_1.PERSONAS });
        }
    }
    getActivePersona() {
        return 'code';
    }
    resolveWebviewView(webviewView, _context, _token) {
        this._view = webviewView;
        // Init router with the post function
        const post = (msg) => this._post(msg);
        this._router = new messageRouter_1.MessageRouter(this._client, this._logger, this._statusBar, this._workspaceId, this._buffer, this._storageUri, post);
        try {
            webviewView.webview.options = {
                enableScripts: true,
                localResourceRoots: [
                    this._extensionUri,
                    vscode.Uri.joinPath(this._extensionUri, 'assets'),
                    vscode.Uri.joinPath(this._extensionUri, 'src', 'webview'),
                    vscode.Uri.joinPath(this._extensionUri, 'dist'),
                ],
            };
            webviewView.webview.html = this._buildHtml(webviewView.webview);
        }
        catch (err) {
            console.error('[Jenna] Webview HTML error:', err);
            webviewView.webview.html = this._fallbackHtml();
        }
        // Live problem count push
        const pushProbs = () => {
            if (!this._view)
                return;
            let count = 0;
            for (const [, diags] of vscode.languages.getDiagnostics()) {
                for (const d of diags) {
                    if (d.severity <= vscode.DiagnosticSeverity.Warning)
                        count++;
                }
            }
            this._post({ type: 'problem_count', count });
        };
        const diagDisp = vscode.languages.onDidChangeDiagnostics(pushProbs);
        webviewView.onDidDispose(() => diagDisp.dispose());
        setTimeout(pushProbs, 1500);
        // Message handler — delegates to router
        webviewView.webview.onDidReceiveMessage(async (msg) => {
            await this._router.handle(msg);
        });
        // Initial sends
        this._router.handle({ type: 'webview_ready' });
        this._router.handle({ type: 'get_sessions' });
    }
    // ── Public API for extension.ts ─────────────────────────────────────────
    get isReady() { return !!this._view; }
    handleUserPrompt(userText) {
        this._router.handle({ type: 'chat', text: userText });
    }
    handleExternalChat(userText) {
        if (this._view) {
            this._view.show?.(true);
            this._post({ type: 'user_message', text: userText });
        }
        return this._router.chat.handleChat(userText);
    }
    clearHistory() {
        this._router.handle({ type: 'new_session' });
    }
    fetchAndSendSessions() {
        this._router.handle({ type: 'get_sessions' });
    }
    // ── HTML builder ────────────────────────────────────────────────────────
    _buildHtml(wv) {
        const nonce = crypto.randomBytes(16).toString('base64');
        const htmlPath = path.join(this._extensionUri.fsPath, 'src', 'webview', 'chat.html');
        let html;
        try {
            html = fs.readFileSync(htmlPath, 'utf8');
        }
        catch {
            return this._fallbackHtml();
        }
        const logoUri = vscode.Uri.joinPath(this._extensionUri, 'assets', 'FoveAI-logo.png');
        let logo = wv.asWebviewUri(logoUri).toString();
        try {
            if (fs.existsSync(logoUri.fsPath)) {
                const b64 = fs.readFileSync(logoUri.fsPath).toString('base64');
                logo = 'data:image/png;base64,' + b64;
            }
        }
        catch { }
        html = html.replace(/\{\{NONCE\}\}/g, nonce);
        html = html.replace(/\{\{CSP_SOURCE\}\}/g, wv.cspSource);
        html = html.replace(/\{\{LOGO_URI\}\}/g, logo);
        const sendBtnUri = vscode.Uri.joinPath(this._extensionUri, 'assets', 'send-button.png');
        let sendBtn = wv.asWebviewUri(sendBtnUri).toString();
        try {
            if (fs.existsSync(sendBtnUri.fsPath)) {
                const b64 = fs.readFileSync(sendBtnUri.fsPath).toString('base64');
                sendBtn = 'data:image/png;base64,' + b64;
            }
        }
        catch { }
        html = html.replace(/\{\{SEND_BTN_URI\}\}/g, sendBtn);
        return html;
    }
    _fallbackHtml() {
        return '<!DOCTYPE html><html><body style="background:#0a0a12;color:#e2e8f0;font-family:sans-serif;padding:20px;"><h2 style="color:#a78bfa">Jenna</h2><p>WebView template not found.</p></body></html>';
    }
    _post(msg) {
        this._view?.webview.postMessage(msg);
    }
}
exports.JennaChatViewProvider = JennaChatViewProvider;
//# sourceMappingURL=JennaChatViewProvider.js.map