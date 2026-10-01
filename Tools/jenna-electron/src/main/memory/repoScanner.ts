/**
 * repoScanner.ts — Ported from jenna-vscode with chokidar adaptation
 * Adapted: replaced vscode.workspace.findFiles with native fs walk.
 * fileCount field added to RepoMap for Electron IPC return.
 */

import * as path from 'path';
import * as fs from 'fs';
import { farmContext } from './contextFarmer';
import { FoveatedClient } from './foveatedClient';

export interface RepoNode {
  file: string;
  relPath: string;
  language: string;
  size: number;
  imports: string[];
  exported: string[];
  functions: string[];
  classes: string[];
  todos: string[];
  stubs: string[];
  xrlRatio: number;
}

export interface RepoMap {
  root: string;
  totalFiles: number;
  fileCount: number;       // alias for totalFiles (used in IPC response)
  totalLines: number;
  languages: Record<string, number>;
  nodes: RepoNode[];
  depGraph: Record<string, string[]>;
  missingDeps: string[];
  hotspots: RepoNode[];
  digest: string;
}

const EXT = new Set(['.ts', '.tsx', '.js', '.jsx', '.py', '.rs', '.go', '.java', '.c', '.cpp', '.h', '.cs', '.rb', '.php', '.swift', '.kt']);
const SKIP = new Set(['node_modules', '.git', '__pycache__', 'dist', 'out', 'build', 'target', 'bin', 'obj', 'venv', '.venv', 'release']);

export async function scanRepo(wsRoot: string, client?: FoveatedClient, wid?: string): Promise<RepoMap> {
  const nodes: RepoNode[] = [];
  const depG: Record<string, string[]> = {};
  const q = [wsRoot];

  while (q.length > 0) {
    const d = q.pop()!;
    let entries: string[];
    try { entries = fs.readdirSync(d); } catch { continue; }
    for (const entry of entries) {
      const f = path.join(d, entry);
      let st: fs.Stats;
      try { st = fs.statSync(f); } catch { continue; }
      if (st.isDirectory()) {
        if (!SKIP.has(entry) && !entry.startsWith('.')) q.push(f);
        continue;
      }
      const ext = path.extname(entry).toLowerCase();
      if (!EXT.has(ext)) continue;
      const rp = path.relative(wsRoot, f).replace(/\\/g, '/');
      try {
        const c = fs.readFileSync(f, 'utf8');
        const lines = c.split('\n');
        const langMap: Record<string, string> = { '.ts': 'TS', '.tsx': 'TSX', '.js': 'JS', '.jsx': 'JSX', '.py': 'Python', '.rs': 'Rust', '.go': 'Go', '.java': 'Java', '.c': 'C', '.cpp': 'C++', '.cs': 'C#', '.rb': 'Ruby', '.php': 'PHP', '.swift': 'Swift', '.kt': 'Kotlin' };
        const imps: string[] = [];
        const IMP_R = /(?:import\s+(?:[\w*{},]\s+from\s+)?['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\)|from\s+['"]([^'"]+)['"]\s+import)/g;
        let m: RegExpExecArray | null;
        while ((m = IMP_R.exec(c)) !== null) { const i = m[1] || m[2] || m[3]; if (i && (i.startsWith('.') || i.startsWith('/'))) imps.push(i); }
        const exps: string[] = [];
        const EXP_R = /export\s+(?:default\s+)?(?:function|class|const|let|var|interface|type|enum)\s+(\w+)/g;
        while ((m = EXP_R.exec(c)) !== null) exps.push(m[1]);
        const funcs: string[] = [];
        const FUN_R = /(?:export\s+)?(?:async\s+)?function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s*)?(?:\(|function)/g;
        while ((m = FUN_R.exec(c)) !== null) funcs.push(m[1] || m[2]);
        const cls: string[] = [];
        const CLA_R = /(?:export\s+)?(?:abstract\s+)?class\s+(\w+)/g;
        while ((m = CLA_R.exec(c)) !== null) cls.push(m[1]);
        const todos: string[] = [];
        const TODO_R = /\b(TODO|FIXME|HACK|XXX|FIX|WORKAROUND|UNTESTED)/gi;
        lines.forEach((l, i) => { if (TODO_R.test(l)) todos.push('L' + (i + 1) + ': ' + l.trim().slice(0, 100)); });
        const stubs: string[] = [];
        const STUB_R = /\b(stub|placeholder|unimplemented|not.implemented|pass\s*$|throw\s+new\s+Error\b)/gi;
        lines.forEach((l, i) => { if (STUB_R.test(l) && l.trim().length < 120) stubs.push('L' + (i + 1) + ': ' + l.trim()); });
        const rslv: string[] = [];
        const dir = path.dirname(f);
        for (const imp of imps) {
          const cands = [path.resolve(dir, imp), path.resolve(dir, imp + '.ts'), path.resolve(dir, imp + '.tsx'), path.resolve(dir, imp + '.js'), path.resolve(dir, imp, 'index.ts'), path.resolve(dir, imp, 'index.js')];
          for (const cand of cands) { if (fs.existsSync(cand)) { rslv.push(path.relative(wsRoot, cand).replace(/\\/g, '/')); break; } }
        }
        depG[rp] = rslv;
        nodes.push({ file: entry, relPath: rp, language: langMap[ext] || ext, size: c.length, imports: rslv, exported: exps, functions: funcs, classes: cls, todos, stubs, xrlRatio: +(4000 / Math.max(c.length, 4000)).toFixed(3) });
      } catch (_) { /* skip unreadable */ }
    }
  }

  const localFiles = new Set(nodes.map(n => n.relPath));
  const missingDeps = new Set<string>();
  for (const [, deps] of Object.entries(depG)) {
    for (const dep of deps) {
      if (![dep, dep + '.ts', dep + '.js'].some(v => localFiles.has(v))) missingDeps.add(dep);
    }
  }

  const totalLines = nodes.reduce((s, n) => s + Math.round(n.size / 30), 0);
  const languages: Record<string, number> = {};
  nodes.forEach(n => { languages[n.language] = (languages[n.language] || 0) + 1; });
  const hotspots = nodes.filter(n => n.stubs.length > 0 || n.todos.length > 0);

  const dirs: Record<string, RepoNode[]> = {};
  nodes.forEach(n => { const d = path.dirname(n.relPath) || '.'; if (!dirs[d]) dirs[d] = []; dirs[d].push(n); });
  let digest = '# Repo: ' + path.basename(wsRoot) + '\n- Files:' + nodes.length + ' Lines:~' + totalLines + ' Langs:' + Object.keys(languages).join(',') + '\n- Missing:' + (missingDeps.size ? [...missingDeps].slice(0, 15).join(',') + (missingDeps.size > 15 ? '...' : '') : 'none') + '\n- Hotspots:' + hotspots.length + '\n\n## Tree\n';
  for (const [dir, files] of Object.entries(dirs)) {
    digest += dir + '/\n';
    files.slice(0, 10).forEach(f => { digest += '  ' + (f.stubs.length ? '⚠' : f.todos.length ? '📝' : '📄') + ' ' + f.file + ' (' + f.functions.length + 'f)\n'; });
    if (files.length > 10) digest += '  +' + (files.length - 10) + ' more\n';
  }
  digest += '\n## Deps\n';
  [...nodes].sort((a, b) => b.imports.length - a.imports.length).slice(0, 15).forEach(n => { if (n.imports.length) digest += n.relPath + ' → ' + n.imports.slice(0, 6).join(',') + '\n'; });
  if (hotspots.length) {
    digest += '\n## Hotspots\n';
    hotspots.slice(0, 10).forEach(n => { const s2 = n.stubs.slice(0, 2).join('; '); const t2 = n.todos.slice(0, 2).join('; '); digest += '- ' + n.relPath + ': ' + (s2 || '') + ' ' + (t2 || '') + '\n'; });
  }

  if (client && wid && digest.length > 4000) {
    const farmed = await farmContext(digest, client, wid, 'audit');
    digest = farmed.digest;
  }

  return { root: wsRoot, totalFiles: nodes.length, fileCount: nodes.length, totalLines, languages, nodes, depGraph: depG, missingDeps: [...missingDeps], hotspots, digest };
}
