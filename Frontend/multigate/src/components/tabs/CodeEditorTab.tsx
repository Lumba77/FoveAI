/**
 * CodeEditorTab.tsx — Vibe IDE
 * Port of Tools/jenna-vscode ("FoveAI Vibe Coder") to the Multigate web surface:
 * repo file tree + Monaco editor + Jenna chat with the persona set, streaming
 * through the foveated proxy. Edits land via the execution-buffer-lite apply
 * flow: fenced code blocks can be inserted at cursor, replace the open file,
 * or write to an explicit `// file: <path>` target.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import * as monaco from 'monaco-editor';
import { loader, Editor } from '@monaco-editor/react';
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';
import jsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker';
import cssWorker from 'monaco-editor/esm/vs/language/css/css.worker?worker';
import htmlWorker from 'monaco-editor/esm/vs/language/html/html.worker?worker';
import tsWorker from 'monaco-editor/esm/vs/language/typescript/ts.worker?worker';

self.MonacoEnvironment = {
  getWorker(_: string, label: string) {
    if (label === 'json') return new jsonWorker();
    if (label === 'css' || label === 'scss' || label === 'less') return new cssWorker();
    if (label === 'html' || label === 'handlebars' || label === 'razor') return new htmlWorker();
    if (label === 'typescript' || label === 'javascript') return new tsWorker();
    return new editorWorker();
  },
};
loader.config({ monaco });

// ── Personas ported from Tools/jenna-vscode/src/memory/foveatedClient.ts ──────
interface PersonaDef { id: string; icon: string; name: string; prompt: string }
const PERSONAS: PersonaDef[] = [
  { id: 'code', icon: '⚡', name: 'Code', prompt: `You are a brilliant and warm AI pair programmer built into FoveAI — a personal AI OS. Operating in CODE mode.
Your traits: highly experimental, open-minded, logical, warm and engaged.
Focus on direct, precise code implementation and pair programming. Prefer minimal targeted diffs over rewrites.
When you produce code meant to replace or create a file, emit it as a fenced block whose first line is a comment: // file: <repo-relative-path> — so the Apply button can write it.` },
  { id: 'plan', icon: '📋', name: 'Plan', prompt: `You are an AI pair programmer operating in PLAN mode.
Your goal is to thoroughly research, analyze the repository, and create structured implementation plans before making any source code edits.
Outline proposed changes, step-by-step verification steps, and risk considerations. Do not produce unrequested raw file overwrites.` },
  { id: 'architect', icon: '🏗️', name: 'Architect', prompt: `You are an AI pair programmer operating in ARCHITECT mode.
Focus on system topology, scalability, design patterns, micro-architectures, and high-level trade-offs.
Explain architectural concepts clearly with structured markdown and diagrams where relevant.` },
  { id: 'audit', icon: '🕵️', name: 'Audit', prompt: `You are an AI pair programmer operating in AUDIT mode.
Focus on root-cause analysis, stack trace diagnosis, race conditions, memory management, invariant checks, and edge cases.
Never mask errors — analyze underlying contract failures systematically.` },
  { id: 'scribe', icon: '📝', name: 'Scribe', prompt: `You are an AI pair programmer operating in SCRIBE mode.
Focus on producing beautiful, production-grade documentation, API specifications, inline docstrings, and architectural diagrams.` },
  { id: 'test', icon: '🧪', name: 'Test', prompt: `You are an AI pair programmer operating in TEST mode.
Focus on test coverage, unit testing, integration suites, edge case boundary validation, and mock setups.` },
  { id: 'probe', icon: '📡', name: 'Probe', prompt: `You are an AI pair programmer operating in PROBE mode.
Your goal is to probe the user with sharp, targeted questions to uncover hidden requirements, resolve ambiguity, and align on design trade-offs.
Ask clarifying questions, present structured options, and help the user flesh out their vision before writing code.` },
  { id: 'selfcode', icon: '🤖', name: 'SelfCode', prompt: `You are an AI pair programmer operating in SELFCODE mode — developing the FoveAI system itself from inside itself.
Your job: implement features, fix bugs, refactor, and organize the codebase for FoveAI — the local-first XR/AI OS whose XRLF models run locally through the foveated-memory proxy (:8400) and llama.cpp runtime (:8402).
Cloud is scaffolding; local is the cathedral.
Prefer minimal targeted diffs, follow existing conventions, and keep everything typed. Emit code blocks with // file: <path> headers the Apply button can write.` },
  { id: 'fovecode', icon: '🏠', name: 'FoveCode', prompt: `You are an AI pair programmer operating in FOVECODE mode — maintaining the main FoveAI repository as a whole.
Scope: foveated-memory proxy (:8400), XRLF runtime (:8402/8403), frontends (:5177), Tools/*, and the root .env as shared source of truth.
Keep ports/protocols consistent (replace legacy references, don't merge zombie code), and respect the local-first architecture.` },
];

const LANGS: Record<string, string> = {
  ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript', mjs: 'javascript',
  py: 'python', json: 'json', md: 'markdown', css: 'css', scss: 'scss', html: 'html',
  rs: 'rust', go: 'go', sh: 'shell', bash: 'shell', yml: 'yaml', yaml: 'yaml', toml: 'toml',
  sql: 'sql', xml: 'xml', c: 'c', cpp: 'cpp', h: 'c', hpp: 'cpp', java: 'java',
};
const langOf = (p: string) => LANGS[p.split('.').pop()?.toLowerCase() || ''] || 'plaintext';

interface TreeEntry { name: string; type: 'dir' | 'file'; size: number | null }
interface OpenFile { path: string; saved: string }
interface ChatMsg { role: 'user' | 'assistant'; content: string; persona?: string }

const CODE_FENCE_RE = /```(\w*)\n([\s\S]*?)```/g;
const FILE_HDR_RE = /^\s*(?:\/\/|#|<!--)\s*file:\s*(\S+)/m;

function getToken(): string {
  try { return JSON.parse(localStorage.getItem('foveai_foveai_user') || '{}').apiKey || ''; }
  catch { return ''; }
}

async function apiFetch(path: string, opts: RequestInit = {}): Promise<Response> {
  return fetch(path, {
    ...opts,
    headers: {
      'Authorization': `Bearer ${getToken()}`,
      'Content-Type': 'application/json',
      ...(opts.headers || {}),
    },
  });
}

export const CodeEditorTab: React.FC = () => {
  // ── workspace / files ──
  const [tree, setTree] = useState<Record<string, TreeEntry[]>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['.']));
  const [files, setFiles] = useState<Record<string, OpenFile>>({});
  const [openOrder, setOpenOrder] = useState<string[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [dirty, setDirty] = useState<Record<string, boolean>>({});
  const [statusMsg, setStatusMsg] = useState('');

  // ── chat ──
  const [chat, setChat] = useState<ChatMsg[]>([
    { role: 'assistant', content: "Hey! I'm your pair programmer. Open a file on the left, pick a mode below, and let's build. Emit `// file: path` headers in my code blocks and I can write straight to the repo." },
  ]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [persona, setPersona] = useState(() => localStorage.getItem('vibe_persona') || 'code');
  const [attachFile, setAttachFile] = useState(true);
  const sessionId = useRef(`vibe-${Date.now().toString(36)}`);

  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const monacoRef = useRef<typeof monaco | null>(null);

  useEffect(() => { localStorage.setItem('vibe_persona', persona); }, [persona]);
  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [chat]);
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  }, [input]);

  // ── file tree ──
  const loadDir = useCallback(async (rel: string) => {
    try {
      const r = await apiFetch(`/api/files/tree?path=${encodeURIComponent(rel)}`);
      if (!r.ok) throw new Error((await r.json()).error || r.statusText);
      const data = await r.json();
      setTree(t => ({ ...t, [data.path === '.' ? '' : data.path]: data.entries }));
    } catch (e: any) {
      setStatusMsg(`tree: ${e.message}`);
    }
  }, []);

  useEffect(() => { loadDir(''); }, [loadDir]);

  const toggleDir = (rel: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(rel)) next.delete(rel);
      else { next.add(rel); if (!tree[rel]) loadDir(rel); }
      return next;
    });
  };

  // ── open / save / close ──
  const openFile = useCallback(async (rel: string) => {
    if (!files[rel]) {
      try {
        const r = await apiFetch(`/api/files/read?path=${encodeURIComponent(rel)}`);
        if (!r.ok) throw new Error((await r.json()).error || r.statusText);
        const data = await r.json();
        setFiles(f => ({ ...f, [rel]: { path: rel, saved: data.content } }));
        setOpenOrder(o => o.includes(rel) ? o : [...o, rel]);
      } catch (e: any) { setStatusMsg(`open: ${e.message}`); return; }
    }
    setActive(rel);
  }, [files]);

  const saveFile = useCallback(async (rel: string) => {
    const model = monacoRef.current?.editor.getModel(monaco.Uri.parse(`file:///${rel}`));
    const content = model?.getValue() ?? files[rel]?.saved;
    if (content === undefined) return;
    try {
      const r = await apiFetch('/api/files/write', { method: 'POST', body: JSON.stringify({ path: rel, content }) });
      if (!r.ok) throw new Error((await r.json()).error || r.statusText);
      setFiles(f => ({ ...f, [rel]: { ...f[rel], saved: content } }));
      setDirty(d => ({ ...d, [rel]: false }));
      setStatusMsg(`saved ${rel}`);
    } catch (e: any) { setStatusMsg(`save: ${e.message}`); }
  }, [files]);

  const closeFile = (rel: string) => {
    monacoRef.current?.editor.getModel(monaco.Uri.parse(`file:///${rel}`))?.dispose();
    setFiles(f => { const n = { ...f }; delete n[rel]; return n; });
    setOpenOrder(o => {
      const n = o.filter(p => p !== rel);
      if (active === rel) setActive(n[n.length - 1] ?? null);
      return n;
    });
  };

  // ── chat ──
  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    const p = PERSONAS.find(x => x.id === persona) || PERSONAS[0];

    let content = text;
    if (attachFile && active) {
      const model = monacoRef.current?.editor.getModel(monaco.Uri.parse(`file:///${active}`));
      const fileContent = model?.getValue();
      if (fileContent) content += `\n\n\`\`\`${langOf(active)}\n// file: ${active}\n${fileContent}\n\`\`\``;
    }

    const history = [...chat, { role: 'user' as const, content }];
    setChat([...chat, { role: 'user', content: text + (attachFile && active ? `  📎${active}` : '') }]);
    setInput('');
    setStreaming(true);

    try {
      const resp = await fetch('/api/foveated/v1/chat/completions', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${getToken()}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: 'auto',
          session_id: sessionId.current,
          stream: true,
          temperature: 0.7,
          max_tokens: 4096,
          messages: [
            { role: 'system', content: p.prompt + "\n\nCRITICAL RESPONSE DIRECTIVE: Respond directly to the user immediately. Do NOT output internal <think> reasoning blocks." },
            ...history.slice(-20).map(m => ({ role: m.role, content: m.content })),
          ],
        }),
      });
      if (!resp.ok) throw new Error(`${resp.status}: ${(await resp.text()).substring(0, 200)}`);

      setChat(c => [...c, { role: 'assistant', content: '', persona: p.id }]);
      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6).trim();
          if (payload === '[DONE]') break;
          try {
            const delta = JSON.parse(payload).choices?.[0]?.delta?.content;
            if (delta) setChat(c => {
              const n = [...c];
              n[n.length - 1] = { ...n[n.length - 1], content: n[n.length - 1].content + delta };
              return n;
            });
          } catch { /* malformed SSE chunk — skip */ }
        }
      }
    } catch (e: any) {
      setChat(c => [...c, { role: 'assistant', content: `❌ ${e.message}` }]);
    } finally {
      setStreaming(false);
    }
  };

  // ── apply blocks ──
  const insertAtCursor = (code: string) => {
    const ed = editorRef.current;
    if (!ed) return;
    const sel = ed.getSelection();
    ed.executeEdits('vibe', [{ range: sel || ed.getModel()!.getFullModelRange(), text: code }]);
    ed.focus();
  };

  const replaceActiveFile = (code: string) => {
    const ed = editorRef.current;
    if (!ed || !active) return;
    ed.getModel()?.setValue(code);
    setDirty(d => ({ ...d, [active]: true }));
  };

  const writeToPath = async (rel: string, code: string) => {
    try {
      const r = await apiFetch('/api/files/write', { method: 'POST', body: JSON.stringify({ path: rel, content: code }) });
      if (!r.ok) throw new Error((await r.json()).error || r.statusText);
      setStatusMsg(`wrote ${rel}`);
      loadDir(rel.split('/').slice(0, -1).join('/'));
      openFile(rel);
    } catch (e: any) { setStatusMsg(`write: ${e.message}`); }
  };

  // ── render helpers ──
  const renderTree = (rel: string, depth: number): React.ReactNode =>
    (tree[rel] || []).map(e => {
      const childRel = rel ? `${rel}/${e.name}` : e.name;
      const isDir = e.type === 'dir';
      const isOpen = expanded.has(childRel);
      return (
        <React.Fragment key={childRel}>
          <div
            className="vibe-tree-row"
            style={{ paddingLeft: 8 + depth * 14 }}
            onClick={() => isDir ? toggleDir(childRel) : openFile(childRel)}
          >
            <span style={{ opacity: 0.6, marginRight: 5, fontSize: '0.75rem' }}>
              {isDir ? (isOpen ? '▾' : '▸') : '·'}
            </span>
            <span style={{ marginRight: 5 }}>{isDir ? '📁' : fileIcon(e.name)}</span>
            <span className="vibe-tree-name" style={{ color: active === childRel ? '#00eaff' : undefined }}>{e.name}</span>
          </div>
          {isDir && isOpen && renderTree(childRel, depth + 1)}
        </React.Fragment>
      );
    });

  const renderApplyButtons = (msg: ChatMsg) => {
    const blocks = [...msg.content.matchAll(CODE_FENCE_RE)];
    if (!blocks.length) return null;
    return (
      <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
        {blocks.map((m, i) => {
          const code = m[2];
          const fileMatch = code.match(FILE_HDR_RE);
          const target = fileMatch?.[1];
          return (
            <React.Fragment key={i}>
              <button style={applyBtn} onClick={() => insertAtCursor(code)} title="Insert at cursor">📋 insert</button>
              {active && <button style={applyBtn} onClick={() => replaceActiveFile(code)} title="Replace open file">⇄ replace file</button>}
              {target && (
                <button style={{ ...applyBtn, borderColor: 'rgba(80,250,123,0.4)', color: '#50fa7b' }}
                  onClick={() => writeToPath(target, code.replace(FILE_HDR_RE, '').replace(/^\n/, ''))}
                  title={`Write to ${target}`}>
                  💾 {target}
                </button>
              )}
            </React.Fragment>
          );
        })}
      </div>
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#0a0a0f', color: '#e0e0e0' }}>
      <style>{`
        .vibe-tree-row { display:flex; align-items:center; padding:2px 8px; cursor:pointer; font-size:0.8rem; white-space:nowrap; }
        .vibe-tree-row:hover { background: rgba(0,234,255,0.06); }
        .vibe-tree-name { overflow:hidden; text-overflow:ellipsis; }
        .vibe-file-tab { padding:4px 10px; font-size:0.78rem; cursor:pointer; border-right:1px solid rgba(255,255,255,0.06); display:flex; align-items:center; gap:6px; white-space:nowrap; }
      `}</style>

      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px',
        background: 'rgba(0,0,0,0.3)', borderBottom: '1px solid rgba(0,243,255,0.1)', flexShrink: 0,
      }}>
        <span style={{ fontSize: '1.1rem' }}>🧑‍💻</span>
        <span style={{ fontWeight: 700, fontSize: '0.85rem', color: '#00eaff' }}>Vibe IDE</span>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {PERSONAS.map(p => (
            <button key={p.id} onClick={() => setPersona(p.id)} title={p.name}
              style={{
                ...btnStyle, padding: '3px 8px',
                background: persona === p.id ? 'rgba(0,234,255,0.18)' : 'transparent',
                borderColor: persona === p.id ? 'rgba(0,234,255,0.5)' : 'rgba(255,255,255,0.08)',
              }}>
              {p.icon}<span className="vibe-persona-name"> {p.name}</span>
            </button>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
          <input type="checkbox" checked={attachFile} onChange={e => setAttachFile(e.target.checked)} />
          📎 file
        </label>
        {active && <button onClick={() => saveFile(active)} style={{ ...btnStyle, borderColor: 'rgba(80,250,123,0.4)', color: '#50fa7b' }}>💾 save</button>}
      </div>

      {/* Main split */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* File tree */}
        <div style={{ width: 200, flexShrink: 0, overflowY: 'auto', borderRight: '1px solid rgba(255,255,255,0.05)', padding: '6px 0' }}>
          {renderTree('', 0)}
        </div>

        {/* Editor */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', borderRight: '1px solid rgba(255,255,255,0.05)', minWidth: 0 }}>
          <div style={{ display: 'flex', background: 'rgba(0,0,0,0.35)', overflowX: 'auto', flexShrink: 0 }}>
            {openOrder.map(p => (
              <div key={p} className="vibe-file-tab"
                style={{ background: active === p ? 'rgba(0,234,255,0.08)' : 'transparent', color: active === p ? '#00eaff' : '#999' }}
                onClick={() => setActive(p)}>
                {dirty[p] ? '●' : fileIcon(p)} {p.split('/').pop()}
                <span style={{ opacity: 0.5, marginLeft: 2 }} onClick={e => { e.stopPropagation(); closeFile(p); }}>✕</span>
              </div>
            ))}
          </div>
          {active ? (
            <Editor
              path={`file:///${active}`}
              defaultLanguage={langOf(active)}
              defaultValue={files[active]?.saved ?? ''}
              theme="vs-dark"
              onMount={(ed, mon) => {
                editorRef.current = ed;
                monacoRef.current = mon;
                ed.addCommand(mon.KeyMod.CtrlCmd | mon.KeyCode.KeyS, () => { if (active) saveFile(active); });
              }}
              onChange={() => {
                const model = monacoRef.current?.editor.getModel(monaco.Uri.parse(`file:///${active}`));
                if (model && files[active]) setDirty(d => ({ ...d, [active]: model.getValue() !== files[active].saved }));
              }}
              options={{ fontSize: 13, minimap: { enabled: false }, tabSize: 4, scrollBeyondLastLine: false, automaticLayout: true, padding: { top: 8 } }}
            />
          ) : (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#555', fontSize: '0.9rem' }}>
              open a file from the tree — or ask the co-pilot to write one for you
            </div>
          )}
          {statusMsg && (
            <div style={{ padding: '4px 10px', fontSize: '0.72rem', color: '#888', background: 'rgba(0,0,0,0.4)', flexShrink: 0 }}>{statusMsg}</div>
          )}
        </div>

        {/* Chat */}
        <div style={{ width: 400, flexShrink: 0, display: 'flex', flexDirection: 'column', background: 'rgba(0,0,0,0.2)' }}>
          <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
            {chat.map((msg, i) => (
              <div key={i} style={{ marginBottom: 12, marginLeft: msg.role === 'user' ? 36 : 0, marginRight: msg.role === 'assistant' ? 36 : 0 }}>
                <div style={{ fontSize: '0.68rem', color: msg.role === 'user' ? '#00eaff' : '#a020f0', marginBottom: 3, fontWeight: 700 }}>
                  {msg.role === 'user' ? 'YOU' : `CO-PILOT${msg.persona ? ` · ${PERSONAS.find(p => p.id === msg.persona)?.name.toUpperCase()}` : ''}`}
                </div>
                <div style={{
                  background: msg.role === 'user' ? 'rgba(0,234,255,0.08)' : 'rgba(160,32,240,0.08)',
                  border: `1px solid ${msg.role === 'user' ? 'rgba(0,234,255,0.15)' : 'rgba(160,32,240,0.15)'}`,
                  borderRadius: 8, padding: '9px 11px', fontSize: '0.83rem', lineHeight: 1.5, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                }}>
                  {msg.content}
                </div>
                {msg.role === 'assistant' && renderApplyButtons(msg)}
              </div>
            ))}
            {streaming && <div style={{ color: '#888', fontSize: '0.82rem', padding: 6 }}><span style={{ animation: 'pulse 1s infinite' }}>●</span> thinking…</div>}
            <div ref={chatEndRef} />
          </div>
          <div style={{ padding: 10, borderTop: '1px solid rgba(255,255,255,0.05)', flexShrink: 0 }}>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
              placeholder={attachFile && active ? `ask about ${active.split('/').pop()}… (Enter sends, Shift+Enter newline)` : 'ask co-pilot… (Enter sends)'}
              disabled={streaming}
              style={{
                width: '100%', background: 'rgba(0,0,0,0.3)', color: '#fff', border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 8, padding: 9, fontSize: '0.83rem', resize: 'none', minHeight: 42, maxHeight: 120,
                outline: 'none', fontFamily: 'inherit', boxSizing: 'border-box',
              }}
            />
            <button onClick={send} disabled={streaming || !input.trim()}
              style={{
                ...btnStyle, width: '100%', marginTop: 6,
                background: streaming ? 'rgba(100,100,100,0.2)' : 'rgba(0,234,255,0.15)', borderColor: 'rgba(0,234,255,0.3)',
              }}>
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

function fileIcon(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() || '';
  const map: Record<string, string> = {
    ts: '🟦', tsx: '⚛️', js: '🟨', jsx: '⚛️', py: '🐍', json: '📋', md: '📝',
    css: '🎨', html: '🌐', rs: '🦀', go: '🐹', sh: '💻', yml: '⚙️', yaml: '⚙️',
    env: '🔐', lock: '🔒', png: '🖼️', jpg: '🖼️', svg: '🖼️', gguf: '🧠', xrlf: '🧠',
  };
  return map[ext] || '📄';
}

const btnStyle: React.CSSProperties = {
  background: 'rgba(0,0,0,0.3)', color: '#ccc', border: '1px solid rgba(255,255,255,0.1)',
  padding: '5px 12px', borderRadius: 4, fontSize: '0.8rem', cursor: 'pointer',
  fontFamily: 'inherit', transition: 'all 0.2s',
};

const applyBtn: React.CSSProperties = {
  fontSize: '0.7rem', color: '#00eaff', background: 'transparent',
  border: '1px solid rgba(0,234,255,0.25)', padding: '2px 8px', borderRadius: 4, cursor: 'pointer',
};
