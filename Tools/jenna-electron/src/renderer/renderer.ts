/**
 * renderer.ts — LUMAX Vibe Coder Renderer Process
 *
 * Initialises Monaco Editor, manages open files/tabs,
 * bridges the chat iframe ↔ main process IPC,
 * and wires up all the UI controls in index.html.
 */

// The electronAPI is exposed by preload.ts via contextBridge
declare const window: Window & {
  electronAPI: import('../main/preload').ElectronAPI;
  require: (moduleName: string) => any;
};

// ── State ──────────────────────────────────────────────────────────────────────
let monacoEditor: any = null;
let currentWorkspaceRoot = '';
let currentSessionId = '';
let workspaceId = '';
let openTabs: { path: string; model: any; dirty: boolean }[] = [];
let activeTabPath = '';

// ── Init ───────────────────────────────────────────────────────────────────────
async function init(): Promise<void> {
  try {
    workspaceId = await window.electronAPI.app.getWorkspaceId();
    await Promise.all([
      loadSessions(),
      initMonaco(),
      setupWindowControls(),
      setupSidebar(),
      pollStatus(),
    ]);

    // Hide loading screen
    const loading = document.getElementById('loading-screen');
    if (loading) {
      loading.classList.add('hidden');
      setTimeout(() => loading.remove(), 400);
    }
  } catch (err) {
    console.error('[renderer] init failed:', err);
  }
}

// ── Window Controls ────────────────────────────────────────────────────────────
function setupWindowControls(): void {
  document.getElementById('btn-minimize')?.addEventListener('click', () =>
    window.electronAPI.window.minimize()
  );
  document.getElementById('btn-maximize')?.addEventListener('click', () =>
    window.electronAPI.window.maximize()
  );
  document.getElementById('btn-close')?.addEventListener('click', () =>
    window.electronAPI.window.close()
  );
}

// ── Monaco Editor ──────────────────────────────────────────────────────────────
function initMonaco(): Promise<void> {
  return new Promise((resolve) => {
    (window as any).require.config({
      paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.47.0/min/vs' },
    });
    (window as any).require(['vs/editor/editor.main'], (monaco: any) => {
      // Define LUMAX dark theme
      monaco.editor.defineTheme('lumax-dark', {
        base: 'vs-dark',
        inherit: true,
        rules: [
          { token: 'comment', foreground: '555577', fontStyle: 'italic' },
          { token: 'keyword', foreground: 'a855f7' },
          { token: 'string', foreground: '00ffcc' },
          { token: 'number', foreground: 'f59e0b' },
          { token: 'type', foreground: '7c3aed' },
          { token: 'function', foreground: '60a5fa' },
        ],
        colors: {
          'editor.background': '#0f0f17',
          'editor.foreground': '#e8e8f0',
          'editor.lineHighlightBackground': '#14141f',
          'editorLineNumber.foreground': '#333355',
          'editorLineNumber.activeForeground': '#6666aa',
          'editor.selectionBackground': '#7c3aed33',
          'editor.findMatchBackground': '#00ffcc33',
          'editorWidget.background': '#14141f',
          'editorWidget.border': '#1a1a28',
          'editorCursor.foreground': '#00ffcc',
          'editorGutter.background': '#0f0f17',
          'scrollbarSlider.background': '#ffffff15',
          'scrollbarSlider.hoverBackground': '#ffffff25',
        },
      });

      const container = document.getElementById('monaco-container')!;
      monacoEditor = monaco.editor.create(container, {
        theme: 'lumax-dark',
        value: '',
        language: 'typescript',
        fontSize: 13,
        fontFamily: "'Cascadia Code', 'JetBrains Mono', 'Fira Code', Consolas, monospace",
        fontLigatures: true,
        lineHeight: 22,
        minimap: { enabled: true, scale: 1 },
        scrollBeyondLastLine: false,
        wordWrap: 'off',
        automaticLayout: true,
        padding: { top: 12, bottom: 12 },
        smoothScrolling: true,
        cursorSmoothCaretAnimation: 'on',
        cursorBlinking: 'smooth',
        renderLineHighlight: 'gutter',
        bracketPairColorization: { enabled: true },
        guides: { indentation: true, bracketPairs: true },
        suggest: { showStatusBar: false },
        formatOnPaste: false,
        formatOnType: false,
      });

      // Track dirty state
      monacoEditor.onDidChangeModelContent(() => {
        const tab = openTabs.find(t => t.path === activeTabPath);
        if (tab) { tab.dirty = true; renderTabs(); }
      });

      // Keyboard shortcuts
      monacoEditor.addAction({
        id: 'lumax.save',
        label: 'Save File',
        keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS],
        run: () => saveCurrentFile(),
      });

      // Send selection to chat
      monacoEditor.addAction({
        id: 'lumax.sendToChat',
        label: 'Send Selection to Jenna',
        keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyJ],
        run: () => {
          const selection = monacoEditor.getModel()?.getValueInRange(monacoEditor.getSelection());
          if (selection) sendToChat(`\`\`\`\n${selection}\n\`\`\``);
        },
      });

      (window as any)._monaco = monaco;
      resolve();
    });
  });
}

// ── File Tabs ──────────────────────────────────────────────────────────────────
function renderTabs(): void {
  const tabsEl = document.getElementById('editor-tabs')!;
  const emptyEl = document.getElementById('editor-empty')!;
  const monacoEl = document.getElementById('monaco-container')!;

  if (openTabs.length === 0) {
    tabsEl.style.display = 'none';
    emptyEl.style.display = 'flex';
    monacoEl.classList.remove('visible');
    return;
  }

  tabsEl.style.display = 'flex';
  emptyEl.style.display = 'none';
  monacoEl.classList.add('visible');

  tabsEl.innerHTML = openTabs.map(tab => {
    const name = tab.path.split(/[\\/]/).pop() ?? tab.path;
    const isActive = tab.path === activeTabPath;
    return `<div class="editor-tab ${isActive ? 'active' : ''}" data-path="${encodeURIComponent(tab.path)}">
      ${tab.dirty ? '<span style="color:#f59e0b;font-size:9px">●</span>' : ''}
      ${getFileIcon(name)} <span>${name}</span>
      <span class="editor-tab-close" data-close="${encodeURIComponent(tab.path)}">✕</span>
    </div>`;
  }).join('');

  tabsEl.querySelectorAll('.editor-tab').forEach(el => {
    el.addEventListener('click', (e) => {
      const closeBtn = (e.target as HTMLElement).closest('[data-close]');
      if (closeBtn) {
        closeTab(decodeURIComponent(closeBtn.getAttribute('data-close')!));
        return;
      }
      const path = decodeURIComponent((el as HTMLElement).dataset['path']!);
      switchToTab(path);
    });
  });
}

function getFileIcon(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  const icons: Record<string, string> = {
    ts: '🔷', tsx: '⚛️', js: '🟨', jsx: '⚛️', py: '🐍',
    json: '📋', md: '📝', css: '🎨', html: '🌐', yaml: '⚙️', toml: '⚙️',
    rs: '🦀', go: '🐹', java: '☕', cpp: '⚡', c: '⚡',
  };
  return icons[ext] ?? '📄';
}

async function openFile(filePath: string): Promise<void> {
  const existing = openTabs.find(t => t.path === filePath);
  if (existing) { switchToTab(filePath); return; }

  try {
    const content = await window.electronAPI.files.read(filePath);
    const monaco = (window as any)._monaco;
    const ext = filePath.split('.').pop()?.toLowerCase() ?? '';
    const langMap: Record<string, string> = {
      ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript',
      py: 'python', json: 'json', md: 'markdown', css: 'css',
      html: 'html', yaml: 'yaml', toml: 'ini', rs: 'rust', go: 'go',
      cpp: 'cpp', c: 'c', java: 'java', cs: 'csharp', rb: 'ruby',
    };
    const lang = langMap[ext] ?? 'plaintext';
    const model = monaco.editor.createModel(content, lang, monaco.Uri.file(filePath));
    openTabs.push({ path: filePath, model, dirty: false });
    switchToTab(filePath);
  } catch (err) {
    console.error('[renderer] openFile failed:', err);
  }
}

function switchToTab(filePath: string): void {
  activeTabPath = filePath;
  const tab = openTabs.find(t => t.path === filePath);
  if (tab && monacoEditor) {
    monacoEditor.setModel(tab.model);
    monacoEditor.focus();
  }
  renderTabs();
}

function closeTab(filePath: string): void {
  const idx = openTabs.findIndex(t => t.path === filePath);
  if (idx === -1) return;
  openTabs[idx].model?.dispose();
  openTabs.splice(idx, 1);
  if (activeTabPath === filePath) {
    activeTabPath = openTabs[Math.max(0, idx - 1)]?.path ?? '';
    if (activeTabPath) switchToTab(activeTabPath);
  }
  renderTabs();
}

async function saveCurrentFile(): Promise<void> {
  const tab = openTabs.find(t => t.path === activeTabPath);
  if (!tab || !monacoEditor) return;
  const content = monacoEditor.getValue();
  try {
    await window.electronAPI.files.write(tab.path, content);
    tab.dirty = false;
    tab.model.pushEditOperations([], [], () => null); // Mark model as clean
    renderTabs();
  } catch (err) {
    console.error('[renderer] save failed:', err);
  }
}

// ── Sessions ───────────────────────────────────────────────────────────────────
async function loadSessions(): Promise<void> {
  const sessions = await window.electronAPI.sessions.list();
  const listEl = document.getElementById('session-list')!;

  if (sessions.length === 0) {
    listEl.innerHTML = '<div style="padding:12px;font-size:11px;color:var(--text-muted);text-align:center;">No sessions yet</div>';
    // Auto-create first session
    const s = await window.electronAPI.sessions.create('Session 1');
    currentSessionId = s.id;
    notifyChatSession(s.id);
    await loadSessions();
    return;
  }

  if (!currentSessionId) {
    currentSessionId = sessions[0].id;
    notifyChatSession(currentSessionId);
  }

  listEl.innerHTML = sessions.map(s => `
    <div class="session-item ${s.id === currentSessionId ? 'active' : ''}" data-session-id="${s.id}">
      <div class="session-item-dot"></div>
      <div class="session-item-title">${escapeHtml(s.title)}</div>
      <div class="session-item-count">${s.message_count ?? 0}</div>
    </div>
  `).join('');

  listEl.querySelectorAll('.session-item').forEach(el => {
    el.addEventListener('click', () => {
      currentSessionId = (el as HTMLElement).dataset['sessionId']!;
      notifyChatSession(currentSessionId);
      listEl.querySelectorAll('.session-item').forEach(x => x.classList.remove('active'));
      el.classList.add('active');
    });
  });
}

async function newSession(): Promise<void> {
  const title = `Session ${Date.now().toString(36).slice(-4)}`;
  const s = await window.electronAPI.sessions.create(title);
  currentSessionId = s.id;
  notifyChatSession(s.id);
  await loadSessions();
}

// ── Sidebar Buttons ────────────────────────────────────────────────────────────
function setupSidebar(): void {
  document.getElementById('btn-new-session')?.addEventListener('click', newSession);

  const openFolderHandler = async () => {
    const paths = await window.electronAPI.files.openDialog({
      filters: [],
      properties: ['openDirectory'],
    });
    if (paths && paths.length > 0) {
      setWorkspaceRoot(paths[0]);
    }
  };
  document.getElementById('btn-open-folder')?.addEventListener('click', openFolderHandler);
  document.getElementById('btn-open-folder-editor')?.addEventListener('click', openFolderHandler);

  document.getElementById('btn-open-file')?.addEventListener('click', async () => {
    const paths = await window.electronAPI.files.openDialog();
    for (const p of paths ?? []) await openFile(p);
  });

  document.getElementById('btn-scan-repo')?.addEventListener('click', async () => {
    if (!currentWorkspaceRoot) { alert('Open a folder first'); return; }
    sendToChat(`Scanning repo at \`${currentWorkspaceRoot}\`...\n\n_Please wait..._`);
    const result = await window.electronAPI.files.scanRepo(currentWorkspaceRoot, workspaceId);
    sendToChat(`**Repo scan complete** (${result.fileCount} files):\n\`\`\`\n${result.digest.slice(0, 3000)}\n\`\`\``);
  });

  // Tray open workspace
  window.electronAPI.tray.onOpenWorkspace(openFolderHandler);
}

function setWorkspaceRoot(root: string): void {
  currentWorkspaceRoot = root;
  const display = document.getElementById('workspace-root-display')!;
  const parts = root.replace(/\\/g, '/').split('/');
  display.textContent = `📁 ${parts.slice(-2).join('/')}`;
  display.title = root;
  notifyChatWorkspace(root);
}

// ── Status Polling ─────────────────────────────────────────────────────────────
async function pollStatus(): Promise<void> {
  const update = async () => {
    try {
      const status = await window.electronAPI.chat.getStatus(workspaceId);
      const dot = document.getElementById('status-dot')!;
      const modelEl = document.getElementById('status-model')!;
      dot.className = `status-dot ${status.online ? '' : 'offline'}`;
      modelEl.textContent = status.online ? `${status.model} · ${status.latencyMs}ms` : 'Offline';
    } catch {
      const dot = document.getElementById('status-dot')!;
      dot.className = 'status-dot offline';
    }
  };
  update();
  setInterval(update, 15000);
}

// ── Chat Bridge ────────────────────────────────────────────────────────────────
function getChat(): Window | null {
  const iframe = document.getElementById('chat-iframe') as HTMLIFrameElement;
  return iframe?.contentWindow ?? null;
}

function sendToChat(message: string): void {
  getChat()?.postMessage({ type: 'lumax:inject-message', content: message }, '*');
}

function notifyChatSession(sessionId: string): void {
  getChat()?.postMessage({ type: 'lumax:session-changed', sessionId, workspaceId }, '*');
}

function notifyChatWorkspace(root: string): void {
  getChat()?.postMessage({ type: 'lumax:workspace-changed', root, workspaceId }, '*');
}

// Listen for messages FROM chat iframe
window.addEventListener('message', async (event) => {
  const msg = event.data;
  if (!msg?.type) return;

  switch (msg.type) {
    case 'lumax:chat:send': {
      // Chat is asking us to stream a message
      await window.electronAPI.chat.send({
        messages: msg.messages,
        model: msg.model,
        persona: msg.persona,
        workspaceId: msg.workspaceId || workspaceId,
        sessionId: currentSessionId,
        tasks: msg.tasks,
      });
      break;
    }
    case 'lumax:chat:abort': {
      await window.electronAPI.chat.abort();
      break;
    }
    case 'lumax:chat:ready': {
      // Chat iframe loaded — send session info
      notifyChatSession(currentSessionId);
      if (currentWorkspaceRoot) notifyChatWorkspace(currentWorkspaceRoot);
      break;
    }
    case 'lumax:file:open': {
      await openFile(msg.path);
      break;
    }
    case 'lumax:session:save-message': {
      if (currentSessionId) {
        await window.electronAPI.sessions.addMessage(currentSessionId, msg.role, msg.content);
        await loadSessions();
      }
      break;
    }
    case 'lumax:session:get-messages': {
      const messages = await window.electronAPI.sessions.messages(currentSessionId);
      getChat()?.postMessage({ type: 'lumax:session:messages', messages }, '*');
      break;
    }
  }
});

// Forward streaming tokens to chat iframe
window.electronAPI.chat.onToken((token) => {
  getChat()?.postMessage({ type: 'lumax:chat:token', token }, '*');
});
window.electronAPI.chat.onDone(() => {
  getChat()?.postMessage({ type: 'lumax:chat:done' }, '*');
});
window.electronAPI.chat.onError((err) => {
  getChat()?.postMessage({ type: 'lumax:chat:error', error: err }, '*');
});

// ── Resize Handles ─────────────────────────────────────────────────────────────
function setupResizeHandles(): void {
  const handle = document.getElementById('resize-handle-chat')!;
  const chatPane = document.getElementById('chat-pane')!;
  let dragging = false;
  let startX = 0;
  let startWidth = 0;

  handle.addEventListener('mousedown', (e) => {
    dragging = true;
    startX = e.clientX;
    startWidth = chatPane.offsetWidth;
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const delta = startX - e.clientX;
    const newWidth = Math.max(280, Math.min(700, startWidth + delta));
    chatPane.style.width = `${newWidth}px`;
    chatPane.style.maxWidth = `${newWidth}px`;
    monacoEditor?.layout();
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Bootstrap ──────────────────────────────────────────────────────────────────
setupResizeHandles();
renderTabs();
window.addEventListener('load', init);
