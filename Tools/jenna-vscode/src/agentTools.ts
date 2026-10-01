/**
 * agentTools.ts — Agentic tool loop for the coder personas.
 *
 * The model emits Cline-style XML tool calls inside its response; this module
 * parses them, executes them against the workspace (paths are confined to the
 * workspace root), and returns textual results that get fed back into the
 * conversation so the model can continue — the same loop Cline/Roo run.
 *
 * Grammar (one or more per response):
 *   <read_file><path>src/foo.ts</path></read_file>
 *   <list_dir><path>src</path></list_dir>
 *   <search><query>handleChat</query></search>
 *   <edit_file><path>x.ts</path><find>old</find><replace>new</replace></edit_file>
 *   <write_file><path>x.ts</path><content>...</content></write_file>
 *   <run_command><cmd>npm test</cmd></run_command>
 *   <problems/>
 *   <scan_repo/>
 *   <done/>
 *
 * Mutating tools (edit/write) apply directly — git accept/reject in the UI is
 * the review path. run_command asks the user via a modal before executing.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import * as cp from 'child_process';
import { scanRepo } from './memory/repoScanner';
import type { FoveatedClient } from './memory/foveatedClient';

export const AGENT_TOOLS_PROMPT = `You have tools to work on the user's actual workspace. When you need repository information or want to make changes, emit tool calls — do NOT describe actions you cannot perform.

Available tools (emit anywhere in your reply, one per block):
<read_file><path>relative/path.ts</path></read_file> — read a file
<list_dir><path>relative/dir</path></list_dir> — list a directory
<search><query>textOrRegex</query></search> — search all workspace files
<edit_file><path>x.ts</path><find>exact existing text</find><replace>replacement text</replace></edit_file> — surgical edit (find must match exactly once)
<write_file><path>x.ts</path><content>full file content</content></write_file> — create/overwrite a file
<run_command><cmd>shell command</cmd></run_command> — run a terminal command (asks user approval)
<problems/> — current IDE errors/warnings
<scan_repo/> — full repo digest: tree, dependencies, hotspots
<done/> — emit when the task is complete

Rules: paths are relative to the workspace root. Read before you edit. Prefer edit_file over write_file for existing files. You may chain multiple rounds of tool calls; results come back as [tool_result] messages.`;

export interface ToolCall {
  name: string;
  args: Record<string, string>;
}

const TOOL_NAMES = [
  'read_file', 'list_dir', 'search', 'edit_file', 'write_file',
  'run_command', 'problems', 'scan_repo', 'done',
];

/** Extract inner text of the first <tag>...</tag> inside a block. */
function inner(block: string, tag: string): string {
  const m = block.match(new RegExp(`<${tag}>([\\s\\S]*?)</${tag}>`));
  return m ? m[1].trim() : '';
}

/** Parse all tool calls from a model response. Tolerant of partial trailing blocks. */
export function parseToolCalls(text: string): ToolCall[] {
  const calls: ToolCall[] = [];
  for (const name of TOOL_NAMES) {
    const re = new RegExp(`<${name}>([\\s\\S]*?)</${name}>|<${name}\\s*/>`, 'g');
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      const block = m[1] || '';
      const args: Record<string, string> = {};
      for (const tag of ['path', 'query', 'find', 'replace', 'content', 'cmd']) {
        const v = inner(block, tag);
        if (v) args[tag] = v;
      }
      calls.push({ name, args });
    }
  }
  return calls;
}

/** Resolve a model-given path safely inside the workspace root. */
function resolvePath(root: string, rel: string): string | null {
  const clean = rel.replace(/^[/\\]+/, '').trim();
  const abs = path.resolve(root, clean);
  return abs.startsWith(root + path.sep) || abs === root ? abs : null;
}

const MAX_READ = 15000;
const MAX_SEARCH_HITS = 60;
const MAX_CMD_OUT = 4000;

export class AgentTools {
  constructor(private _client: FoveatedClient, private _workspaceId: string) {}

  private _root(): string | null {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? null;
  }

  /** Execute one tool call; returns the text to feed back to the model. */
  async execute(call: ToolCall): Promise<string> {
    const root = this._root();
    if (!root && call.name !== 'problems') return 'ERROR: no workspace folder open';
    try {
      switch (call.name) {
        case 'read_file': {
          const p = resolvePath(root!, call.args.path || '');
          if (!p || !fs.existsSync(p) || !fs.statSync(p).isFile()) return `ERROR: file not found: ${call.args.path}`;
          const c = fs.readFileSync(p, 'utf8');
          return c.length > MAX_READ
            ? c.slice(0, MAX_READ) + `\n... [truncated — ${c.length} chars total]`
            : c;
        }
        case 'list_dir': {
          const p = resolvePath(root!, call.args.path || '.');
          if (!p || !fs.existsSync(p) || !fs.statSync(p).isDirectory()) return `ERROR: dir not found: ${call.args.path}`;
          return fs.readdirSync(p, { withFileTypes: true })
            .map(e => (e.isDirectory() ? e.name + '/' : e.name)).join('\n').slice(0, 4000);
        }
        case 'search': {
          const q = call.args.query || '';
          if (!q) return 'ERROR: empty query';
          let rx: RegExp;
          try { rx = new RegExp(q, 'i'); } catch { rx = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'); }
          const hits: string[] = [];
          const SKIP = new Set(['node_modules', '.git', '__pycache__', 'dist', 'out', 'build', 'target', 'venv', '.venv']);
          const walk = (d: string) => {
            if (hits.length >= MAX_SEARCH_HITS) return;
            for (const e of fs.readdirSync(d, { withFileTypes: true })) {
              if (hits.length >= MAX_SEARCH_HITS) return;
              if (e.isDirectory()) { if (!SKIP.has(e.name) && !e.name.startsWith('.')) walk(path.join(d, e.name)); continue; }
              const fp = path.join(d, e.name);
              if (!/\.(ts|tsx|js|jsx|py|rs|go|java|c|cpp|h|cs|json|md|html|css|yml|yaml|toml)$/i.test(e.name)) continue;
              try {
                const lines = fs.readFileSync(fp, 'utf8').split('\n');
                lines.forEach((l, i) => {
                  if (hits.length < MAX_SEARCH_HITS && rx.test(l)) {
                    hits.push(`${path.relative(root!, fp)}:${i + 1}: ${l.trim().slice(0, 140)}`);
                  }
                });
              } catch {}
            }
          };
          walk(root!);
          return hits.length ? hits.join('\n') : 'no matches';
        }
        case 'edit_file': {
          const p = resolvePath(root!, call.args.path || '');
          if (!p || !fs.existsSync(p)) return `ERROR: file not found: ${call.args.path}`;
          const find = call.args.find ?? '';
          const repl = call.args.replace ?? '';
          if (!find) return 'ERROR: empty <find> block';
          const orig = fs.readFileSync(p, 'utf8');
          const count = orig.split(find).length - 1;
          if (count === 0) return 'ERROR: <find> text not found in file — re-read the file and match exactly';
          if (count > 1) return `ERROR: <find> matches ${count} locations — make it more specific`;
          fs.writeFileSync(p, orig.replace(find, repl), 'utf8');
          return `OK: edited ${call.args.path} (replaced ${find.length} chars with ${repl.length} chars)`;
        }
        case 'write_file': {
          const p = resolvePath(root!, call.args.path || '');
          if (!p) return `ERROR: path outside workspace: ${call.args.path}`;
          const content = call.args.content ?? '';
          if (!content) return 'ERROR: empty <content> block';
          fs.mkdirSync(path.dirname(p), { recursive: true });
          fs.writeFileSync(p, content, 'utf8');
          return `OK: wrote ${call.args.path} (${content.length} chars)`;
        }
        case 'run_command': {
          const cmd = call.args.cmd || '';
          if (!cmd) return 'ERROR: empty <cmd>';
          const pick = await vscode.window.showWarningMessage(
            `Jenna wants to run: ${cmd}`, { modal: true }, 'Run', 'Deny');
          if (pick !== 'Run') return 'DENIED by user';
          return await new Promise<string>((resolve) => {
            cp.exec(cmd, { cwd: root!, timeout: 30000, maxBuffer: 1024 * 1024 }, (err: cp.ExecException | null, stdout: string, stderr: string) => {
              const out = (stdout + (stderr ? '\nSTDERR: ' + stderr : '')).trim();
              if (err && !out) return resolve(`ERROR: ${err.message}`);
              resolve((err ? `exit ${err.code}\n` : '') + (out.slice(0, MAX_CMD_OUT) || '(no output)'));
            });
          });
        }
        case 'problems': {
          const items: string[] = [];
          for (const [uri, diags] of vscode.languages.getDiagnostics()) {
            for (const d of diags) {
              if (d.severity <= vscode.DiagnosticSeverity.Warning && items.length < 40) {
                items.push(`[${d.severity === 0 ? 'ERROR' : 'WARN'}] ${vscode.workspace.asRelativePath(uri)}:${d.range.start.line + 1} — ${d.message.slice(0, 140)}`);
              }
            }
          }
          return items.length ? items.join('\n') : 'no problems reported';
        }
        case 'scan_repo': {
          const repo = await scanRepo(root!, this._client, this._workspaceId);
          return repo.digest;
        }
        case 'done':
          return 'OK';
        default:
          return `ERROR: unknown tool ${call.name}`;
      }
    } catch (err) {
      return `ERROR: ${err instanceof Error ? err.message : String(err)}`;
    }
  }

  /** Execute every parsed call and bundle the results into one feedback message. */
  async executeAll(calls: ToolCall[]): Promise<{ feedback: string; didMutate: boolean; isDone: boolean }> {
    let feedback = '';
    let didMutate = false;
    let isDone = false;
    for (const c of calls) {
      if (c.name === 'done') { isDone = true; continue; }
      const result = await this.execute(c);
      if (c.name === 'edit_file' || c.name === 'write_file') didMutate = true;
      const argSummary = c.args.path || c.args.query || c.args.cmd || '';
      feedback += `[tool_result] <${c.name}> ${argSummary}\n${result}\n[/tool_result]\n\n`;
    }
    return { feedback: feedback.trim(), didMutate, isDone };
  }
}
