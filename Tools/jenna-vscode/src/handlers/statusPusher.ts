/**
 * statusPusher.ts — Pushes live connection, git branch, and active file status to webview.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { FoveatedClient } from '../memory/foveatedClient';
import { JennaStatusBar } from '../statusBar';

export class StatusPusher {
  constructor(
    private _client: FoveatedClient,
    private _statusBar: JennaStatusBar,
    private _workspaceId: string,
    private _getXrl: () => number,
    private _post: (msg: Record<string, unknown>) => void,
  ) {}

  async push(): Promise<void> {
    try {
      if (this._statusBar) this._statusBar.refresh();

      // Probe proxy status safely without letting exceptions clear workspace context
      let st: any = null;
      try {
        st = await this._client.getStatus(this._workspaceId);
        if (st) st.compressionLevel = this._getXrl();
      } catch (err) {
        console.warn('[StatusPusher] Foveated proxy status check failed:', err);
      }

      const ws = vscode.workspace.name || '';
      const wf = vscode.workspace.workspaceFolders;
      let skel = false, commit = '', commitHash = '', commitMsg = '', branch = '', branchStatus = '', repoUrl = '';
      let afterEdits = '', importantFiles = '';
      
      if (wf && wf.length > 0) {
        const r = wf[0].uri.fsPath;
        skel = fs.existsSync(path.join(r, 'repo-principia.md')) || fs.existsSync(path.join(r, 'repo-skeleton.md'));
        try {
          const cp = require('child_process');
          commit = cp.execSync('git log -1 --format="%cd" --date=relative', { cwd: r, timeout: 2000, windowsHide: true }).toString().trim();
          commitHash = cp.execSync('git rev-parse --short HEAD', { cwd: r, timeout: 2000, windowsHide: true }).toString().trim();
          commitMsg = cp.execSync('git log -1 --format="%s"', { cwd: r, timeout: 2000, windowsHide: true }).toString().trim();
          const b = cp.execSync('git rev-parse --abbrev-ref HEAD', { cwd: r, timeout: 2000, windowsHide: true }).toString().trim();
          if (b) branch = b;
          const statusOutput = cp.execSync('git status --porcelain', { cwd: r, timeout: 2000, windowsHide: true }).toString().trim();
          branchStatus = statusOutput ? 'Modified files' : 'Clean & Synced';
          const origin = cp.execSync('git config --get remote.origin.url', { cwd: r, timeout: 2000, windowsHide: true }).toString().trim();
          if (origin) {
            repoUrl = origin.replace(/\.git$/, '').replace(/^git@github\.com:/, 'https://github.com/');
          }
        } catch {}

        // Dynamically detect afterEdits and important authoritative files in the workspace
        const editCandidates = ['uptodate.md', 'context.md', 'WORKFLOW.md'];
        for (const candidate of editCandidates) {
          if (fs.existsSync(path.join(r, candidate))) {
            afterEdits = candidate;
            break;
          }
        }

        const impCandidates = ['context.md', 'uptodate.md', 'ARCHITECTURE.md', 'LUMAX.md', 'AGENTS.md'];
        const foundImp = impCandidates.filter(f => fs.existsSync(path.join(r, f)));
        if (foundImp.length > 0) {
          importantFiles = foundImp.slice(0, 2).join(', ');
        }
      }

      // Count active problems across all languages
      let errorCount = 0;
      let warningCount = 0;
      for (const [, diags] of vscode.languages.getDiagnostics()) {
        for (const d of diags) {
          if (d.severity === vscode.DiagnosticSeverity.Error) errorCount++;
          else if (d.severity === vscode.DiagnosticSeverity.Warning) warningCount++;
        }
      }
      const totalProblems = errorCount + warningCount;
      const problemsText = totalProblems === 0 ? '0 Problems (Clean)' : `${errorCount} Err, ${warningCount} Warn`;

      const cfgModel = vscode.workspace.getConfiguration('jenna').get<string>('model') || 'XRLF 9B (Coder)';
      const activeModel = (st && st.model && st.model !== 'auto') ? st.model : cfgModel;

      const ae = vscode.window.activeTextEditor;
      const af = ae ? path.basename(ae.document.fileName) : '';
      let wsFolder = '';
      if (ae) {
        const activeFolder = vscode.workspace.getWorkspaceFolder(ae.document.uri);
        if (activeFolder) wsFolder = activeFolder.name;
      }
      if (!wsFolder && wf && wf.length > 0) {
        wsFolder = wf[0].name;
      }
      const wsName = wsFolder || (ws || 'FoveAI');
      const stack = 'Python • FastAPI • Redis';

      this._post({
        type: 'status_update',
        status: {
          ...(st || {}),
          workspaceName: wsName,
          workspacePath: wsFolder || 'FoveAI',
          hasRepoSkeleton: skel,
          activeFile: af ? `Active: ${af}` : 'No active file',
          stack,
          branch: branch || 'main',
          branchStatus: branchStatus || 'Clean & Synced',
          repoUptime: branch ? `${branch} (${branchStatus || 'Clean'})` : 'main (Clean)',
          lastCommit: commit || 'Just now',
          commitHash: commitHash || 'HEAD',
          commitMsg: commitMsg || 'Latest Commit',
          repoUrl: repoUrl || 'https://github.com/Lumba77/lumax',
          domains: 'lumax.1um6a.se',
          ports: 'Ports :8400 | :5177',
          tunnelStatus: 'Cloudflare Secure Tunnel',
          afterEdits: afterEdits || 'uptodate.md',
          editsStatus: 'Sync on change',
          editsDetail: 'Auto-updated on build',
          importantFiles: importantFiles || 'context.md, uptodate.md',
          importantStatus: 'Core context bridge',
          importantDetail: 'Active Recall Memory',
          model: activeModel,
          modelStatus: (st && st.online) ? ':8400 Connected' : 'Local / Active',
          modelDetail: 'Foveated Proxy Active',
          totalProblems,
          problemsText,
          problemsDetail: totalProblems === 0 ? '0 Compiler Errors' : 'Workspace Diagnostics',
          online: st?.online ?? true
        }
      });
    } catch (e) {
      console.error('[StatusPusher] Unexpected error in push():', e);
      if (this._statusBar) this._statusBar.refresh();
    }
  }
}
