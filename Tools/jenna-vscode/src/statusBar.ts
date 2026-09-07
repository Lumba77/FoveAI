/**
 * statusBar.ts — Jenna Status Bar Integration
 *
 * Shows live compression level and online/offline state.
 * Click to open the Jenna sidebar.
 */

import * as vscode from 'vscode';
import { FoveatedClient, MemoryStatus } from './memory/foveatedClient';

const POLL_INTERVAL_MS = 30_000;
const OFFLINE_THRESHOLD = 3; // consecutive failures before showing OFFLINE

export class JennaStatusBar {
  private item: vscode.StatusBarItem;
  private timer: ReturnType<typeof setInterval> | null = null;
  private client: FoveatedClient;
  private workspaceId: string;
  private lastStatus: MemoryStatus | null = null;
  private consecutiveFailures = 0;

  constructor(client: FoveatedClient, workspaceId: string) {
    this.client = client;
    this.workspaceId = workspaceId;

    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100
    );
    this.item.command = 'jenna.openSidebar';
    this.item.tooltip = 'Jenna — FoveAI Copilot (click to open)';
    this.item.show();

    this._renderConnecting();
    this._startPolling();
  }

  private _renderConnecting(): void {
    this.item.text = '$(loading~spin) Jenna';
    this.item.color = undefined;
    this.item.backgroundColor = undefined;
  }

  private _render(status: MemoryStatus): void {
    if (!status.online) {
      this.item.text = '$(circle-slash) Jenna [OFFLINE]';
      this.item.color = new vscode.ThemeColor('statusBarItem.warningForeground');
      this.item.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
    } else {
      const xrl = status.compressionLevel;
      const rings = status.activeBlocks;
      this.item.text = `$(brain) Jenna [XRL:${xrl} | ◉${rings}]`;
      this.item.color = undefined;
      this.item.backgroundColor = undefined;
    }
  }

  private _startPolling(): void {
    // Immediate first check
    this._poll();
    this.timer = setInterval(() => this._poll(), POLL_INTERVAL_MS);
  }

  private async _poll(): Promise<void> {
    try {
      const status = await this.client.getStatus(this.workspaceId);
      this.consecutiveFailures = 0; // reset on success
      this.lastStatus = status;
      this._render(status);
    } catch {
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
  async refresh(): Promise<MemoryStatus | null> {
    await this._poll();
    return this.lastStatus;
  }

  getLastStatus(): MemoryStatus | null {
    return this.lastStatus;
  }

  dispose(): void {
    if (this.timer) clearInterval(this.timer);
    this.item.dispose();
  }
}

