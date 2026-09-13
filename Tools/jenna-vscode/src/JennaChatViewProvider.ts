/**
 * JennaChatViewProvider.ts — Thin WebView shell.
 * Owns the webview lifecycle. Delegates all message handling to MessageRouter and sub-handlers.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import * as crypto from 'crypto';
import { FoveatedClient, PersonaId, PERSONAS } from './memory/foveatedClient';
import { SessionLogger } from './bonding/sessionLogger';
import { JennaStatusBar } from './statusBar';
import { ExecutionBuffer } from './executionBuffer';
import { MessageRouter } from './handlers/messageRouter';

export class JennaChatViewProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = 'jennaChat';

  private _view?: vscode.WebviewView;
  private _router!: MessageRouter;

  constructor(
    private _extensionUri: vscode.Uri,
    private _storageUri: vscode.Uri,
    private _client: FoveatedClient,
    private _logger: SessionLogger,
    private _statusBar: JennaStatusBar,
    private _workspaceId: string,
    private _buffer: ExecutionBuffer,
    private _audio?: import('./audioManager').AudioManager,
  ) {}

  public setPersona(personaId: PersonaId): void {
    if (PERSONAS[personaId]) {
      this._post({ type: 'persona_update', activePersona: personaId, personas: PERSONAS });
    }
  }

  public reload(): void {
    if (this._view) {
      this._view.webview.html = this._buildHtml(this._view.webview);
      this._post({ type: 'persona_update', activePersona: 'code', personas: PERSONAS });
    }
  }

  public getActivePersona(): PersonaId {
    return 'code';
  }

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken,
  ): void {
    this._view = webviewView;

    // Init router with the post function
    const post = (msg: Record<string, unknown>) => this._post(msg);
    this._router = new MessageRouter(
      this._client, this._logger, this._statusBar, this._workspaceId,
      this._buffer, this._storageUri, post, this._audio,
    );

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
    } catch (err) {
      console.error('[Jenna] Webview HTML error:', err);
      webviewView.webview.html = this._fallbackHtml();
    }

    // Live problem count push
    const pushProbs = () => {
      if (!this._view) return;
      let count = 0;
      for (const [, diags] of vscode.languages.getDiagnostics()) {
        for (const d of diags) { if (d.severity <= vscode.DiagnosticSeverity.Warning) count++; }
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

  public get isReady(): boolean { return !!this._view; }

  public handleUserPrompt(userText: string): void {
    this._router.handle({ type: 'chat', text: userText });
  }

  public handleExternalChat(userText: string): Promise<void> {
    if (this._view) { this._view.show?.(true); this._post({ type: 'user_message', text: userText }); }
    return this._router.chat.handleChat(userText);
  }

  public clearHistory(): void {
    this._router.handle({ type: 'new_session' });
  }

  public fetchAndSendSessions(): void {
    this._router.handle({ type: 'get_sessions' });
  }

  // ── HTML builder ────────────────────────────────────────────────────────

  private _buildHtml(wv: vscode.Webview): string {
    const nonce = crypto.randomBytes(16).toString('base64');
    const htmlPath = path.join(this._extensionUri.fsPath, 'src', 'webview', 'chat.html');
    let html: string;
    try { html = fs.readFileSync(htmlPath, 'utf8'); } catch { return this._fallbackHtml(); }
    const logoUri = vscode.Uri.joinPath(this._extensionUri, 'assets', 'FoveAI-logo.png');
    let logo = wv.asWebviewUri(logoUri).toString();
    try { if (fs.existsSync(logoUri.fsPath)) { const b64 = fs.readFileSync(logoUri.fsPath).toString('base64'); logo = 'data:image/png;base64,' + b64; } } catch {}
    html = html.replace(/\{\{NONCE\}\}/g, nonce);
    html = html.replace(/\{\{CSP_SOURCE\}\}/g, wv.cspSource);
    html = html.replace(/\{\{LOGO_URI\}\}/g, logo);
    
    const sendBtnUri = vscode.Uri.joinPath(this._extensionUri, 'assets', 'send-button.png');
    let sendBtn = wv.asWebviewUri(sendBtnUri).toString();
    try { if (fs.existsSync(sendBtnUri.fsPath)) { const b64 = fs.readFileSync(sendBtnUri.fsPath).toString('base64'); sendBtn = 'data:image/png;base64,' + b64; } } catch {}
    html = html.replace(/\{\{SEND_BTN_URI\}\}/g, sendBtn);
    
    return html;
  }

  private _fallbackHtml(): string {
    return '<!DOCTYPE html><html><body style="background:#0a0a12;color:#e2e8f0;font-family:sans-serif;padding:20px;"><h2 style="color:#a78bfa">Jenna</h2><p>WebView template not found.</p></body></html>';
  }

  private _post(msg: Record<string, unknown>): void {
    this._view?.webview.postMessage(msg);
  }
}


