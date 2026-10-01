"use strict";
/**
 * statusBar.ts — Jenna Status Bar Integration
 *
 * Shows live compression level and online/offline state.
 * Click to open the Jenna sidebar.
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
exports.JennaStatusBar = void 0;
const vscode = __importStar(require("vscode"));
const POLL_INTERVAL_MS = 30_000;
const OFFLINE_THRESHOLD = 3; // consecutive failures before showing OFFLINE
class JennaStatusBar {
    item;
    timer = null;
    client;
    workspaceId;
    lastStatus = null;
    consecutiveFailures = 0;
    constructor(client, workspaceId) {
        this.client = client;
        this.workspaceId = workspaceId;
        this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
        this.item.command = 'jenna.openSidebar';
        this.item.tooltip = 'Jenna — FoveAI Copilot (click to open)';
        this.item.show();
        this._renderConnecting();
        this._startPolling();
    }
    _renderConnecting() {
        this.item.text = '$(loading~spin) Jenna';
        this.item.color = undefined;
        this.item.backgroundColor = undefined;
    }
    _render(status) {
        if (!status.online) {
            this.item.text = '$(circle-slash) Jenna [OFFLINE]';
            this.item.color = new vscode.ThemeColor('statusBarItem.warningForeground');
            this.item.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
        }
        else {
            const xrl = status.compressionLevel;
            const rings = status.activeBlocks;
            this.item.text = `$(brain) Jenna [XRL:${xrl} | ◉${rings}]`;
            this.item.color = undefined;
            this.item.backgroundColor = undefined;
        }
    }
    _startPolling() {
        // Immediate first check
        this._poll();
        this.timer = setInterval(() => this._poll(), POLL_INTERVAL_MS);
    }
    async _poll() {
        try {
            const status = await this.client.getStatus(this.workspaceId);
            this.consecutiveFailures = 0; // reset on success
            this.lastStatus = status;
            this._render(status);
        }
        catch {
            this.consecutiveFailures++;
            // Only flip to OFFLINE visually after OFFLINE_THRESHOLD consecutive misses
            // NOTE: Auto-start of sleipnir_launcher.js removed — the FoveAI tray app
            // (FoveAI_Taskbar.pyw) now manages the proxy lifecycle. Auto-starting
            // sleipnir here would conflict with the tray app's watchdog.
            if (this.consecutiveFailures >= OFFLINE_THRESHOLD) {
                this._render({
                    online: false, compressionLevel: 0, activeBlocks: 0,
                    totalMemories: 0, totalThemes: 0, totalSessions: 0, model: 'offline', workspaceId: this.workspaceId, latencyMs: -1
                });
            }
            // else: keep showing last known good state while proxy is briefly down
        }
    }
    /** Force an immediate status refresh */
    async refresh() {
        await this._poll();
        return this.lastStatus;
    }
    getLastStatus() {
        return this.lastStatus;
    }
    dispose() {
        if (this.timer)
            clearInterval(this.timer);
        this.item.dispose();
    }
}
exports.JennaStatusBar = JennaStatusBar;
//# sourceMappingURL=statusBar.js.map