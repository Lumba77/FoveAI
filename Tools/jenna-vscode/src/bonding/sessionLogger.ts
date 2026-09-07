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

import * as vscode from 'vscode';
import { FoveatedClient } from '../memory/foveatedClient';

export interface BondingEntry {
  sessionId: string;
  workspaceFolder: string;
  workspaceId: string;
  startTime: string;
  endTime?: string;
  filesTouched: Set<string>;
  conversationTurns: number;
  highlights: string[];
}

export class SessionLogger {
  private entry: BondingEntry;
  private client: FoveatedClient;
  private disposables: vscode.Disposable[] = [];

  constructor(workspaceId: string, workspaceFolder: string, client: FoveatedClient) {
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

  private _generateId(): string {
    return `sess_${Date.now().toString(36)}`;
  }

  private _attachListeners(): void {
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
  recordTurn(userMessage: string, jennaResponse: string): void {
    this.entry.conversationTurns++;

    // Extract highlights: lines with "TODO", "FIX", "IMPORTANT", or code blocks
    const highlight = this._extractHighlight(userMessage, jennaResponse);
    if (highlight) {
      this.entry.highlights.push(highlight);
    }
  }

  private _extractHighlight(user: string, response: string): string | null {
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
  private _buildSummary(): string {
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

  private _durationStr(): string {
    const start = new Date(this.entry.startTime).getTime();
    const end = Date.now();
    const mins = Math.round((end - start) / 60000);
    return mins < 60 ? `${mins}m` : `${Math.floor(mins / 60)}h ${mins % 60}m`;
  }

  /** Flush the session summary into foveated memory */
  async flush(): Promise<void> {
    this.entry.endTime = new Date().toISOString();
    const summary = this._buildSummary();

    try {
      await this.client.injectBondMemory(summary, this.entry.workspaceId);
      console.log(`[jenna] session bond injected: ${this.entry.sessionId}`);
    } catch (err) {
      console.warn('[jenna] bond injection failed (non-fatal):', err);
    }
  }

  dispose(): void {
    this.disposables.forEach(d => d.dispose());
  }

  get sessionId(): string {
    return this.entry.sessionId;
  }

  get turnCount(): number {
    return this.entry.conversationTurns;
  }
}
