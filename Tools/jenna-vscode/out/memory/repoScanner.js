"use strict";
/**
 * repoScanner.ts — XRL Codebase Scanner
 * Walks workspace, builds dependency map, finds hotspots, generates a compressed digest.
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
exports.scanRepo = scanRepo;
const path = __importStar(require("path"));
const fs = __importStar(require("fs"));
const contextFarmer_1 = require("./contextFarmer");
const EXT = new Set(['.ts', '.tsx', '.js', '.jsx', '.py', '.rs', '.go', '.java',
    '.c', '.cpp', '.h', '.cs', '.rb', '.php', '.swift', '.kt']);
const SKIP = new Set(['node_modules', '.git', '__pycache__', 'dist', 'out',
    'build', 'target', 'bin', 'obj', 'venv']);
async function scanRepo(wsRoot, client, wid) {
    const nodes = [];
    const depG = {};
    const q = [wsRoot];
    while (q.length > 0) {
        const d = q.pop();
        let entries;
        try {
            entries = fs.readdirSync(d);
        }
        catch {
            continue;
        }
        for (const entry of entries) {
            const f = path.join(d, entry);
            let st;
            try {
                st = fs.statSync(f);
            }
            catch {
                continue;
            }
            if (st.isDirectory()) {
                if (!SKIP.has(entry) && !entry.startsWith('.'))
                    q.push(f);
                continue;
            }
            const ext = path.extname(entry).toLowerCase();
            if (!EXT.has(ext))
                continue;
            const rp = path.relative(wsRoot, f).replace(/\\\\/g, '/');
            try {
                const c = fs.readFileSync(f, 'utf8');
                const lines = c.split('\n');
                const langMap = { '.ts': 'TS', '.tsx': 'TSX', '.js': 'JS', '.jsx': 'JSX', '.py': 'Python', '.rs': 'Rust', '.go': 'Go', '.java': 'Java', '.c': 'C', '.cpp': 'C++', '.cs': 'C#', '.rb': 'Ruby', '.php': 'PHP', '.swift': 'Swift', '.kt': 'Kotlin' };
                const imps = [];
                const IMP_R = /(?:import\s+(?:[\w*{},]\s+from\s+)?['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\)|from\s+['"]([^'"]+)['"]\s+import)/g;
                let m;
                while ((m = IMP_R.exec(c)) !== null) {
                    const i = m[1] || m[2] || m[3];
                    if (i && (i.startsWith('.') || i.startsWith('/')))
                        imps.push(i);
                }
                const exps = [];
                const EXP_R = /export\s+(?:default\s+)?(?:function|class|const|let|var|interface|type|enum)\s+(\w+)/g;
                while ((m = EXP_R.exec(c)) !== null)
                    exps.push(m[1]);
                const funcs = [];
                const FUN_R = /(?:export\s+)?(?:async\s+)?function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s*)?(?:\(|function)/g;
                while ((m = FUN_R.exec(c)) !== null)
                    funcs.push(m[1] || m[2]);
                const cls = [];
                const CLA_R = /(?:export\s+)?(?:abstract\s+)?class\s+(\w+)/g;
                while ((m = CLA_R.exec(c)) !== null)
                    cls.push(m[1]);
                const todos = [];
                const TODO_R = /\b(TODO|FIXME|HACK|XXX|FIX|WORKAROUND|UNTESTED)/gi;
                lines.forEach((l, i) => { if (TODO_R.test(l))
                    todos.push('L' + (i + 1) + ': ' + l.trim().slice(0, 100)); });
                const stubs = [];
                const STUB_R = /\b(stub|placeholder|unimplemented|not.implemented|pass\s*$|throw\s+new\s+Error\b)/gi;
                lines.forEach((l, i) => { if (STUB_R.test(l) && l.trim().length < 120)
                    stubs.push('L' + (i + 1) + ': ' + l.trim()); });
                const rslv = [];
                const dir = path.dirname(f);
                for (const imp of imps) {
                    const cands = [path.resolve(dir, imp), path.resolve(dir, imp + '.ts'), path.resolve(dir, imp + '.tsx'), path.resolve(dir, imp + '.js'), path.resolve(dir, imp, 'index.ts'), path.resolve(dir, imp, 'index.js')];
                    for (const cand of cands) {
                        if (fs.existsSync(cand)) {
                            rslv.push(path.relative(wsRoot, cand).replace(/\\/g, '/'));
                            break;
                        }
                    }
                }
                depG[rp] = rslv;
                nodes.push({ file: entry, relPath: rp, language: langMap[ext] || ext, size: c.length, imports: rslv, exported: exps, functions: funcs, classes: cls, todos, stubs, xrlRatio: +(4000 / Math.max(c.length, 4000)).toFixed(3) });
            }
            catch (_) { }
        }
    }
    // Missing deps
    const localFiles = new Set(nodes.map(n => n.relPath));
    const missingDeps = new Set();
    for (const [, deps] of Object.entries(depG)) {
        for (const dep of deps) {
            if (![dep, dep + '.ts', dep + '.js'].some(v => localFiles.has(v)))
                missingDeps.add(dep);
        }
    }
    // Stats
    const totalLines = nodes.reduce((s, n) => s + Math.round(n.size / 30), 0);
    const languages = {};
    nodes.forEach(n => { languages[n.language] = (languages[n.language] || 0) + 1; });
    const hotspots = nodes.filter(n => n.stubs.length > 0 || n.todos.length > 0);
    // Build digest
    const dirs = {};
    nodes.forEach(n => { const d = path.dirname(n.relPath) || '.'; if (!dirs[d])
        dirs[d] = []; dirs[d].push(n); });
    let digest = '# Repo: ' + path.basename(wsRoot) + '\n- Files:' + nodes.length + ' Lines:~' + totalLines + ' Langs:' + Object.keys(languages).join(',') + '\n- Missing:' + (missingDeps.size ? [...missingDeps].slice(0, 15).join(',') + (missingDeps.size > 15 ? '...' : '') : 'none') + '\n- Hotspots:' + hotspots.length + '\n\n## Tree\n';
    for (const [dir, files] of Object.entries(dirs)) {
        digest += dir + '/\n';
        files.slice(0, 10).forEach(f => { digest += '  ' + (f.stubs.length ? '⚠' : f.todos.length ? '📝' : '📄') + ' ' + f.file + ' (' + f.functions.length + 'f)\n'; });
        if (files.length > 10)
            digest += '  +' + (files.length - 10) + ' more\n';
    }
    digest += '\n## Deps\n';
    [...nodes].sort((a, b) => b.imports.length - a.imports.length).slice(0, 15).forEach(n => { if (n.imports.length)
        digest += n.relPath + ' → ' + n.imports.slice(0, 6).join(',') + '\n'; });
    if (hotspots.length) {
        digest += '\n## Hotspots\n';
        hotspots.slice(0, 10).forEach(n => { const s2 = n.stubs.slice(0, 2).join('; '); const t2 = n.todos.slice(0, 2).join('; '); digest += '- ' + n.relPath + ': ' + (s2 || '') + ' ' + (t2 || '') + '\n'; });
    }
    // Farm if large
    if (client && wid && digest.length > 4000) {
        const farmed = await (0, contextFarmer_1.farmContext)(digest, client, wid, 'audit');
        digest = farmed.digest;
    }
    return { root: wsRoot, totalFiles: nodes.length, totalLines, languages, nodes, depGraph: depG, missingDeps: [...missingDeps], hotspots, digest };
}
//# sourceMappingURL=repoScanner.js.map