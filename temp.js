
    const vscode = acquireVsCodeApi();

    // UI Elements
    const $messages = document.getElementById('messages');
    const $emptyState = document.getElementById('empty-state');
    const $recentSessionsContainer = document.getElementById('recent-sessions-container');
    const $recentSessionsList = document.getElementById('recent-sessions-list');
    
    const $btnStartNew = document.getElementById('btn-start-new');
    const $btnLoadLatest = document.getElementById('btn-load-latest');
    const $btnListSessions = document.getElementById('btn-list-sessions');
    
    const $input = document.getElementById('chat-input');
    const $sendBtn = document.getElementById('send-btn');
    const $recordBtn = document.getElementById('record-btn');
    
    const $statusDot = document.getElementById('status-dot');
    const $hudXrl = document.getElementById('hud-xrl');
    
    // Dropdowns

    // ── TASK BOARD ─────────────────────────────────────────────────────────────
    const $taskBoard       = document.getElementById('task-board');
    const $taskBoardHeader = document.getElementById('task-board-header');
    const $taskBoardBody   = document.getElementById('task-board-body');
    const $taskBoardBadge  = document.getElementById('task-board-badge');
    const $taskBoardEmpty  = document.getElementById('task-board-empty');
    const $taskClearDone   = document.getElementById('task-clear-done');
    const $taskClearAll    = document.getElementById('task-clear-all');

    let _tasks = []; // { id, text, done }

    /** Parse markdown checkboxes from a string. Returns [{text, done}] */
    function parseTasksFromText(text) {
      const tasks = [];
      const regex = /^[ \t]*[-*]\s+\[([ xX])\]\s+(.+)$/gm;
      let m;
      while ((m = regex.exec(text)) !== null) {
        tasks.push({ text: m[2].trim(), done: m[1].toLowerCase() === 'x' });
      }
      return tasks;
    }

    /** Render all tasks into the board */
    function renderTaskBoard() {
      const active = _tasks.filter(t => !t.done);
      const total  = _tasks.length;
      $taskBoardBadge.textContent = `${active.length}/${total}`;

      // Show/hide board
      if (total === 0) {
        $taskBoard.classList.add('task-board-hidden');
        return;
      }
      $taskBoard.classList.remove('task-board-hidden');

      // Rebuild body
      $taskBoardBody.innerHTML = '';
      if (total === 0) {
        $taskBoardBody.appendChild($taskBoardEmpty);
        return;
      }
      _tasks.forEach((task, i) => {
        const el = document.createElement('div');
        el.className = 'task-item' + (task.done ? ' done' : '');
        el.dataset.idx = i;
        el.innerHTML = `
          <div class="task-checkbox"></div>
          <div class="task-label">${escapeHtml(task.text)}</div>
          <span class="task-clear-btn" title="Remove task">✕</span>`;
        // Toggle done
        el.querySelector('.task-checkbox').onclick = (e) => {
          e.stopPropagation();
          _tasks[i].done = !_tasks[i].done;
          renderTaskBoard();
        };
        el.querySelector('.task-label').onclick = () => {
          _tasks[i].done = !_tasks[i].done;
          renderTaskBoard();
        };
        // Remove individual task
        el.querySelector('.task-clear-btn').onclick = (e) => {
          e.stopPropagation();
          _tasks.splice(i, 1);
          renderTaskBoard();
        };
        $taskBoardBody.appendChild(el);
      });
    }

    /** Merge new tasks in from a chat message (avoid duplicates by text) */
    function syncTasksFromMessage(text) {
      const found = parseTasksFromText(text);
      if (!found.length) return;
      let changed = false;
      found.forEach(t => {
        const existing = _tasks.find(x => x.text === t.text);
        if (!existing) {
          _tasks.push({ id: Date.now() + Math.random(), text: t.text, done: t.done });
          changed = true;
        } else if (t.done && !existing.done) {
          existing.done = true;
          changed = true;
        }
      });
      if (changed) renderTaskBoard();
    }

    // Collapse/expand toggle
    $taskBoardHeader.addEventListener('click', () => {
      $taskBoard.classList.toggle('collapsed');
    });
    // Clear done tasks
    $taskClearDone.addEventListener('click', (e) => {
      e.stopPropagation();
      _tasks = _tasks.filter(t => !t.done);
      renderTaskBoard();
    });
    // Clear all tasks
    $taskClearAll.addEventListener('click', (e) => {
      e.stopPropagation();
      _tasks = [];
      renderTaskBoard();
    });

    const $personaBtn = document.getElementById('persona-btn');
    const $personaDropdown = document.getElementById('persona-dropdown');
    const $modelBtn = document.getElementById('model-btn');
    const $modelDropdown = document.getElementById('model-dropdown');
    const $hudModel = document.getElementById('hud-model');
    const $xrlBtn = document.getElementById('xrl-btn');
    const $xrlDropdown = document.getElementById('xrl-dropdown');
    const $personaLabel = document.getElementById('persona-label');

    let currentStreamBubble = null;
    let isStreaming = false;

    // Accordion State
    const CATEGORIES = [
      { id: 'all',       name: 'All Sessions',      icon: '📂' },
      { id: 'today',     name: 'Today',             icon: '☀️' },
      { id: 'yesterday', name: 'Yesterday',         icon: '⏪' },
      { id: 'older',     name: 'Older',             icon: '🕰️' }
    ];
    let storedSessions = null;
    const openCategories = new Set(['today']); // open by default

    function autoResizeInput() {
      $input.style.height = 'auto';
      const maxHeight = Math.max(120, window.innerHeight * 0.45);
      const newHeight = Math.min($input.scrollHeight, maxHeight);
      $input.style.height = newHeight + 'px';
      $input.style.overflowY = $input.scrollHeight >= maxHeight ? 'scroll' : 'hidden';
    }
    $input.addEventListener('input', autoResizeInput);
    $input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });
    $sendBtn.addEventListener('click', sendMessage);

    // Dropdown toggles
    $personaBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      $personaDropdown.classList.toggle('open');
      $xrlDropdown.classList.remove('open');
      $modelDropdown.classList.remove('open');
    });
    $xrlBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      $xrlDropdown.classList.toggle('open');
      $personaDropdown.classList.remove('open');
      $modelDropdown.classList.remove('open');
    });
    $modelBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      $modelDropdown.classList.toggle('open');
      $personaDropdown.classList.remove('open');
      $xrlDropdown.classList.remove('open');
    });
    document.addEventListener('click', () => {
      $personaDropdown.classList.remove('open');
      $xrlDropdown.classList.remove('open');
      $modelDropdown.classList.remove('open');
    });
    
    $xrlDropdown.querySelectorAll('.persona-option').forEach(opt => {
      opt.addEventListener('click', (e) => {
        e.stopPropagation();
        const level = parseInt(opt.dataset.level, 10);
        $hudXrl.textContent = `XRL ${level}`;
        vscode.postMessage({ type: 'set_xrl', level });
        $xrlDropdown.classList.remove('open');
      });
    });

    $modelDropdown.querySelectorAll('.persona-option').forEach(opt => {
      opt.addEventListener('click', (e) => {
        e.stopPropagation();
        const model = opt.dataset.model;
        $hudModel.textContent = opt.textContent;
        vscode.postMessage({ type: 'set_model', model });
        $modelDropdown.classList.remove('open');
      });
    });

    let attachedFiles = [];
    const $attachedFilesBar = document.getElementById('attached-files-bar');

    function renderAttachedFiles() {
      if (!attachedFiles || attachedFiles.length === 0) {
        $attachedFilesBar.style.display = 'none';
        $attachedFilesBar.innerHTML = '';
        return;
      }
      $attachedFilesBar.style.display = 'flex';
      $attachedFilesBar.innerHTML = attachedFiles.map((f, idx) => {
        const icon = f.isImage ? '🖼️' : '📄';
        return `
          <div style="background: var(--bg-glass); border: 1px solid var(--border); border-radius: 12px; padding: 2px 8px; font-size: 11px; display: flex; align-items: center; gap: 4px;">
            <span>${icon} ${escapeHtml(f.name)}</span>
            <span style="cursor: pointer; opacity: 0.6; font-weight: bold; margin-left: 2px;" onclick="removeAttachedFile(${idx})">×</span>
          </div>
        `;
      }).join('');
    }

    window.removeAttachedFile = function(idx) {
      attachedFiles.splice(idx, 1);
      renderAttachedFiles();
    };

    function sendMessage() {
      const text = $input.value.trim();
      if ((!text && attachedFiles.length === 0) || isStreaming) return;

      let fullPrompt = text;
      if (attachedFiles.length > 0) {
        const fileContext = attachedFiles.map(f => `[Attached File: ${f.name}]\n\`\`\`\n${f.content}\n\`\`\``).join('\n\n');
        fullPrompt = text ? `${fileContext}\n\n${text}` : fileContext;
      }

      $emptyState.style.display = 'none';
      addMessage('user', 'You', text || `[Attached ${attachedFiles.length} file(s)]`);
      $input.value = '';
      $input.style.height = 'auto';
      attachedFiles = [];
      renderAttachedFiles();

      isStreaming = true;
      $sendBtn.disabled = true;
      vscode.postMessage({ type: 'chat', text: fullPrompt, tasks: _tasks.map(t => ({ text: t.text, done: t.done })) });
    }

    function addMessage(role, labelText, content) {
      const msg = document.createElement('div');
      msg.className = 'msg ' + role;
      const roleDiv = document.createElement('div');
      roleDiv.className = 'msg-role';
      roleDiv.textContent = labelText;
      const bubble = document.createElement('div');
      bubble.className = 'msg-bubble';
      bubble.dataset.raw = content;
      bubble.innerHTML = renderMarkdown(content);
      msg.appendChild(roleDiv);
      msg.appendChild(bubble);
      
      attachMessageActions(msg, role, content, bubble);
      
      // Auto-sync task checkboxes to Task Board
      if (role === 'assistant') syncTasksFromMessage(content || '');

      $messages.appendChild(msg);
      $messages.scrollTop = $messages.scrollHeight;
    }

    function startStreamBubble() {
      const msg = document.createElement('div');
      msg.className = 'msg assistant';
      const bubble = document.createElement('div');
      bubble.className = 'msg-bubble';
      bubble.dataset.raw = '';
      msg.innerHTML = '<div class="msg-role">Vibe Coder</div>';
      msg.appendChild(bubble);
      $messages.appendChild(msg);
      return bubble;
    }

    function appendToStreamBubble(bubble, chunk) {
      bubble.dataset.raw += chunk;
      bubble.innerHTML = renderMarkdown(bubble.dataset.raw);
      $messages.scrollTop = $messages.scrollHeight;
    }
    function finalizeStreamBubble(bubble) {
      bubble.innerHTML = renderMarkdown(bubble.dataset.raw);
      // Auto-sync any markdown task checkboxes to Task Board
      syncTasksFromMessage(bubble.dataset.raw || '');
      const msg = bubble.closest('.msg');
      if (msg) {
        attachMessageActions(msg, 'assistant', bubble.dataset.raw, bubble);
      }
    }

    function attachMessageActions(msgNode, role, content, bubbleNode) {
      const actionsBar = document.createElement('div');
      actionsBar.style.display = 'flex';
      actionsBar.style.gap = '8px';
      actionsBar.style.marginTop = '4px';
      actionsBar.style.justifyContent = role === 'user' ? 'flex-end' : 'flex-start';
      actionsBar.style.opacity = '0.5';
      actionsBar.style.fontSize = '0.8rem';
      
      const copyBtn = document.createElement('span');
      copyBtn.textContent = '📋 Copy';
      copyBtn.style.cursor = 'pointer';
      copyBtn.title = 'Copy to clipboard';
      copyBtn.onclick = () => {
        navigator.clipboard.writeText(bubbleNode.dataset.raw);
        copyBtn.textContent = '✅ Copied';
        setTimeout(() => copyBtn.textContent = '📋 Copy', 2000);
      };

      const editBtn = document.createElement('span');
      editBtn.textContent = '✏️ Edit';
      editBtn.style.cursor = 'pointer';
      editBtn.title = 'Edit message';
      editBtn.onclick = () => {
        const textarea = document.createElement('textarea');
        textarea.value = bubbleNode.dataset.raw;
        textarea.style.width = '100%';
        textarea.style.minHeight = '100px';
        textarea.style.fontFamily = 'var(--vscode-editor-font-family)';
        textarea.style.background = 'var(--vscode-input-background)';
        textarea.style.color = 'var(--vscode-input-foreground)';
        textarea.style.border = '1px solid var(--vscode-focusBorder)';
        textarea.style.padding = '8px';
        
        const saveBtn = document.createElement('button');
        saveBtn.textContent = '💾 Save';
        saveBtn.className = 'toolbar-btn';
        saveBtn.style.marginTop = '4px';
        
        const cancelBtn = document.createElement('button');
        cancelBtn.textContent = '✕ Cancel';
        cancelBtn.className = 'toolbar-btn toolbar-btn-danger';
        cancelBtn.style.marginTop = '4px';
        cancelBtn.style.marginLeft = '4px';

        const controls = document.createElement('div');
        controls.appendChild(saveBtn);
        controls.appendChild(cancelBtn);

        const oldHtml = bubbleNode.innerHTML;
        bubbleNode.innerHTML = '';
        bubbleNode.appendChild(textarea);
        bubbleNode.appendChild(controls);
        actionsBar.style.display = 'none';

        saveBtn.onclick = () => {
          const newText = textarea.value;
          bubbleNode.dataset.raw = newText;
          bubbleNode.innerHTML = renderMarkdown(newText);
          actionsBar.style.display = 'flex';
          // Send edit event to host. Index is calculated based on .msg elements minus streaming/empty state
          const allMsgs = Array.from(document.querySelectorAll('.msg'));
          const idx = allMsgs.indexOf(msgNode);
          vscode.postMessage({ type: 'message_edit', index: idx, text: newText });
        };
        cancelBtn.onclick = () => {
          bubbleNode.innerHTML = oldHtml;
          actionsBar.style.display = 'flex';
        };
      };

      const delBtn = document.createElement('span');
      delBtn.textContent = '🗑️ Delete';
      delBtn.style.cursor = 'pointer';
      delBtn.title = 'Delete message';
      delBtn.onclick = () => {
        const allMsgs = Array.from(document.querySelectorAll('.msg'));
        const idx = allMsgs.indexOf(msgNode);
        vscode.postMessage({ type: 'message_delete', index: idx });
        msgNode.remove();
      };

      const rollbackBtn = document.createElement('span');
      rollbackBtn.textContent = '⏪ Rollback';
      rollbackBtn.style.cursor = 'pointer';
      rollbackBtn.title = 'Rollback session to this message';
      rollbackBtn.onclick = () => {
        const allMsgs = Array.from(document.querySelectorAll('.msg'));
        const idx = allMsgs.indexOf(msgNode);
        // Ask for confirmation
        vscode.postMessage({ type: 'rollback_session', index: idx });
      };

      actionsBar.appendChild(copyBtn);
      actionsBar.appendChild(editBtn);
      actionsBar.appendChild(delBtn);
      actionsBar.appendChild(rollbackBtn);

      // Add hover effect
      actionsBar.onmouseover = () => actionsBar.style.opacity = '1';
      actionsBar.onmouseout = () => actionsBar.style.opacity = '0.5';

      msgNode.appendChild(actionsBar);
    }

    // Markdown simple renderer with thinking block support
    function renderMarkdown(text) {
      if (!text) return '';
      let escaped = escapeHtml(text);
      
      // 1. Convert completed <think>...</think> tags into collapsible details with scrollable container
      escaped = escaped.replace(/&lt;think&gt;([\s\S]*?)&lt;\/think&gt;/gi, (_, thought) => {
        return `<details style="opacity:0.8; font-size:11px; margin-bottom:8px; border:1px solid var(--border); border-radius:6px; padding:4px 8px; background:color-mix(in srgb, var(--bg-panel) 85%, transparent);"><summary style="cursor:pointer; font-weight:600; opacity:0.9;">💭 Thought Process</summary><div style="padding:6px 4px; max-height:140px; overflow-y:auto; font-family:monospace; line-height:1.4; font-size:10.5px; opacity:0.85; white-space:pre-wrap; margin-top:4px; border-top:1px solid var(--border);">${thought.trim()}</div></details>`;
      });
      
      // 2. Handle active unclosed streaming <think>... blocks as an active open scrollable details box
      if (escaped.includes('&lt;think&gt;')) {
        escaped = escaped.replace(/&lt;think&gt;([\s\S]*)$/gi, (_, liveThought) => {
          return `<details open style="opacity:0.85; font-size:11px; margin-bottom:8px; border:1px dashed var(--vscode-textLink-foreground, #3794ff); border-radius:6px; padding:4px 8px; background:color-mix(in srgb, var(--bg-panel) 90%, transparent);"><summary style="cursor:pointer; font-weight:600; color:var(--vscode-textLink-foreground, #3794ff);">💭 Thinking in progress...</summary><div style="padding:6px 4px; max-height:140px; overflow-y:auto; font-family:monospace; line-height:1.4; font-size:10.5px; opacity:0.85; white-space:pre-wrap; margin-top:4px; border-top:1px solid var(--border);">${liveThought.trim()}</div></details>`;
        });
      }

      let html = escaped;
      html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => `<pre><code>${code.trim()}</code></pre>`);
      html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');
      html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      html = html.replace(/\n/g, '<br/>');
      return html;
    }
    function escapeHtml(str) {
      if(!str) return '';
      return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // Accordion Logic
    function classifySession(s) {
      const now = Date.now();
      const ts = new Date(s.last_updated).getTime();
      const diffDays = (now - ts) / (1000*3600*24);
      if (diffDays < 1) return 'today';
      if (diffDays < 2) return 'yesterday';
      return 'older';
    }

    let sortMode = 'theme';
    const $sortSelect = document.getElementById('sort-select');
    if ($sortSelect) {
      $sortSelect.addEventListener('change', (e) => {
        sortMode = e.target.value;
        renderAccordion();
      });
    }

    function classifyByTheme(s) {
      if (s.theme) {
        const t = s.theme.toLowerCase();
        if (t.includes('ui') || t.includes('design') || t.includes('aesthetic')) return 'theme_ui';
        if (t.includes('arch') || t.includes('system') || t.includes('memory')) return 'theme_arch';
        if (t.includes('code') || t.includes('feature') || t.includes('bug')) return 'theme_code';
      }
      const text = ((s.title || '') + ' ' + (s.preview || '')).toLowerCase();
      if (/ui|theme|icon|button|design|watermark|aesthetic|gradient|style|color|layout/.test(text)) return 'theme_ui';
      if (/architect|system|server|proxy|memory|matrix|sleipnir|backend|database|nedb|foveated/.test(text)) return 'theme_arch';
      if (/code|fix|bug|feature|script|deploy|html|css|js|ts|function|api|endpoint/.test(text)) return 'theme_code';
      return 'theme_gen';
    }

    function renderAccordion() {
      const validSessions = (storedSessions || []).filter(s => {
        if (!s) return false;
        const cnt = s.count || s.turn_count || 0;
        const cleanT = (s.title || '').replace(/^["'\s]+|["'\s]+$/g, '').trim();
        const isJunkTitle = !cleanT || cleanT.length <= 3 || /^(the|a|an|in|on|untitled|session)$/i.test(cleanT);
        if (cnt > 0 && cnt <= 2 && isJunkTitle && (!s.preview || s.preview.trim().length <= 10)) {
          return false;
        }
        return true;
      });
      if (validSessions.length === 0) {
        $recentSessionsList.innerHTML = '<div style="text-align: center; font-size: 11px; opacity: 0.6; padding: 20px;">No sessions found.</div>';
        return;
      }

      let activeCategories = CATEGORIES;
      let groups = {};

      if (sortMode === 'theme') {
        activeCategories = [
          { id: 'theme_code', name: 'Code & Features',      icon: '⚡' },
          { id: 'theme_arch', name: 'Architecture & Memory',icon: '🏗️' },
          { id: 'theme_ui',   name: 'UI & Aesthetics',      icon: '🎨' },
          { id: 'theme_gen',  name: 'General & Reflection', icon: '💬' }
        ];
        activeCategories.forEach(c => groups[c.id] = []);
        validSessions.forEach(s => {
          const cat = classifyByTheme(s);
          if (groups[cat]) groups[cat].push(s);
        });
        // Sort sessions inside each theme by date descending (latest sessions at the top!)
        Object.keys(groups).forEach(k => {
          groups[k].sort((a, b) => (b.last_updated || '').localeCompare(a.last_updated || ''));
        });
      } else if (sortMode === 'project') {
        // Group dynamically by s.project or workspace_id
        const projMap = new Map();
        validSessions.forEach(s => {
          const proj = s.project || s.workspace_id || 'LUMAX';
          if (!projMap.has(proj)) projMap.set(proj, []);
          projMap.get(proj).push(s);
        });
        activeCategories = Array.from(projMap.keys()).map(p => ({
          id: 'proj_' + p,
          name: 'Project: ' + p,
          icon: '📁'
        }));
        activeCategories.forEach(c => {
          const key = c.id.replace('proj_', '');
          const list = projMap.get(key) || [];
          list.sort((a, b) => (b.last_updated || '').localeCompare(a.last_updated || ''));
          groups[c.id] = list;
        });
      } else {
        // Copy array for sorting
        let list = [...validSessions];
        if (sortMode === 'turns') {
          list.sort((a, b) => (b.count || b.turn_count || 0) - (a.count || a.turn_count || 0));
        } else {
          list.sort((a, b) => (b.last_updated || '').localeCompare(a.last_updated || ''));
        }

        groups = { today: [], yesterday: [], older: [], all: list };
        list.forEach(s => {
          const cat = classifySession(s);
          if (groups[cat]) groups[cat].push(s);
        });
      }

      let html = '';
      activeCategories.forEach(cat => {
        const items = groups[cat.id] || [];
        if (items.length === 0 && cat.id !== 'all') return;
        const isOpen = openCategories.has(cat.id) || sortMode === 'theme';
        
        let bodyHtml = `
          <table style="width: 100%; border-collapse: collapse; font-size: 11px; margin-top: 4px;">
            <thead>
              <tr style="border-bottom: 1px solid var(--border); text-align: left; opacity: 0.7; font-size: 10px; text-transform: uppercase;">
                <th style="padding: 6px 4px; width: 60%;">Session Info</th>
                <th style="padding: 6px 4px; width: 40%;">Activity & Tags</th>
              </tr>
            </thead>
            <tbody>
        `;

        bodyHtml += items.map(s => {
          let sid = s.session_id || s.id || '';
          let shortId = sid ? 'Session #' + sid.slice(-6) : 'Untitled Session';
          let rawTitle = s.title || (typeof s.preview === 'string' && s.preview.trim() ? '"' + s.preview.slice(0, 35).trim() + '..."' : shortId);
          rawTitle = rawTitle.replace(/[◆◇■□●○★☆▲▼#*_`]/g, '').trim();
          if (!rawTitle || rawTitle === 'Untitled Session') rawTitle = shortId;
          
          let kwLines = [];
          if (s.keywords) {
            kwLines = String(s.keywords).split('\n').map(l => l.trim()).filter(Boolean);
          }
          const row1 = kwLines[0] || 'Uncategorized';

          return `
          <tr class="recent-session-card" data-id="${sid}" style="cursor: pointer; border-bottom: 1px solid var(--border); transition: background 0.2s;">
            <td style="padding: 8px 4px; vertical-align: top;">
              <div class="rs-title" style="font-weight: 600; font-size: 12px; color: var(--vscode-textLink-foreground, #3794ff); margin-bottom: 4px;">${escapeHtml(rawTitle)}</div>
              <div style="font-size: 10px; opacity: 0.6;">🕒 ${new Date(s.last_updated).toLocaleString()}</div>
            </td>
            <td style="padding: 8px 4px; vertical-align: top;">
              <div style="font-size: 10px; font-weight: 500; opacity: 0.85; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 4px;" title="${escapeHtml(row1)}">🏷️ ${escapeHtml(row1)}</div>
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 10px; opacity: 0.7;">💬 ${s.turn_count || s.count || 0} turns</span>
                <button class="ingredients-btn" data-id="${sid}" title="View Detailed Session Index & Ingredients" style="background: var(--bg-glass); border: 1px solid var(--border); border-radius: 4px; padding: 2px 6px; font-size: 10px; cursor: pointer; color: var(--text-primary); opacity: 0.85;">📜 Index</button>
              </div>
            </td>
          </tr>
          `;
        }).join('');
        
        bodyHtml += `</tbody></table>`;

        html += `
        <div class="acc-category">
          <div class="acc-header" data-cat="${cat.id}">
            <span class="acc-icon">${cat.icon}</span>
            <span class="acc-label">${cat.name}</span>
            <span class="acc-count">${items.length}</span>
            <span class="acc-chevron">${isOpen ? '▾' : '▸'}</span>
          </div>
          <div class="acc-body ${isOpen ? 'open' : ''}">
            ${bodyHtml}
          </div>
        </div>`;
      });
      $recentSessionsList.innerHTML = html;

      // Bind events
      $recentSessionsList.querySelectorAll('.acc-header').forEach(hdr => {
        hdr.addEventListener('click', () => {
          const catId = hdr.dataset.cat;
          if (openCategories.has(catId)) { openCategories.delete(catId); } 
          else { openCategories.add(catId); }
          renderAccordion(); // re-render
        });
      });
      $recentSessionsList.querySelectorAll('.recent-session-card').forEach(card => {
        card.addEventListener('click', () => {
          vscode.postMessage({ type: 'get_session_messages', sessionId: card.dataset.id });
        });
      });

      // Bind Ingredients Modal trigger buttons
      $recentSessionsList.querySelectorAll('.ingredients-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
          e.stopPropagation();
          const sId = btn.dataset.id;
          const modal = document.getElementById('ingredients-modal');
          const body = document.getElementById('ingredients-modal-body');
          modal.style.display = 'block';
          body.innerHTML = '<div style="text-align: center; padding: 10px;">⚡ Analyzing full session & extracting ingredients list using local LLM...</div>';
          
          try {
            const config = vscode.workspace.getConfiguration('jenna');
            const baseUrl = config.get<string>('foveatedMemoryUrl', 'http://127.0.0.1:8400');
            const res = await fetch(`${baseUrl}/api/session/ingredients`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ session_id: sId }),
              signal: AbortSignal.timeout(20000)
            });
            if (res.ok) {
              const data = await res.json();
              body.innerHTML = `
                ${data.summary ? `<div style="margin-bottom: 8px;"><strong>📝 Summary:</strong> ${escapeHtml(data.summary)}</div>` : ''}
                ${data.topics ? `<div style="margin-bottom: 8px;"><strong>🏷️ Key Topics:</strong> ${escapeHtml(data.topics)}</div>` : ''}
                <div><strong>🧪 Ingredients & Modifications:</strong><br/><pre style="white-space: pre-wrap; font-family: inherit; font-size: 11px; margin-top: 4px; background: var(--bg-glass); padding: 8px; border-radius: 6px; border: 1px solid var(--border); line-height: 1.4;">${escapeHtml(data.ingredients || 'No detailed ingredients available.')}</pre></div>
              `;
            } else {
              body.innerHTML = 'Failed to load session ingredients index.';
            }
          } catch (e) {
            body.innerHTML = 'Failed to load ingredients index: ' + e.message;
          }
        });
      });

      const closeModalBtn = document.getElementById('close-modal-btn');
      if (closeModalBtn) {
        closeModalBtn.onclick = () => {
          document.getElementById('ingredients-modal').style.display = 'none';
        };
      }
    }

    function updateStatus(status) {
      if (!status) return;
      $statusDot.className = status.online ? 'online' : 'offline';
      const lvl = (typeof status.compressionLevel === 'number' && status.compressionLevel >= 0) ? status.compressionLevel : 5;
      $hudXrl.textContent = status.online ? `XRL ${lvl}` : '—';
    }

    // Message Bus
    window.addEventListener('message', (event) => {
      const msg = event.data;
      switch (msg.type) {
        case 'stream_start':
          currentStreamBubble = startStreamBubble();
          break;
        case 'stream_chunk':
          if (currentStreamBubble) appendToStreamBubble(currentStreamBubble, msg.chunk);
          break;
        case 'stream_end':
          if (currentStreamBubble) finalizeStreamBubble(currentStreamBubble);
          currentStreamBubble = null;
          isStreaming = false;
          $sendBtn.disabled = false;
          break;
        case 'stream_error':
          if (currentStreamBubble) finalizeStreamBubble(currentStreamBubble);
          addMessage('assistant', 'System Error', '<span style="color:var(--vscode-errorForeground);">Connection to Foveated Memory Proxy failed: ' + escapeHtml(msg.error || 'Unknown error') + '</span>');
          currentStreamBubble = null;
          isStreaming = false;
          $sendBtn.disabled = false;
          break;
        case 'file_attached':
          if (msg.file) {
            attachedFiles.push(msg.file);
            renderAttachedFiles();
          }
          break;
        case 'status_update':
          updateStatus(msg.status);
          if (msg.status) {
            if (msg.status.workspaceName) {
              const $name = document.getElementById('ws-ctx-name');
              if ($name) $name.textContent = msg.status.workspaceName;
            }
            if (msg.status.lastCommit) {
              const $commit = document.getElementById('ws-ctx-commit');
              if ($commit) $commit.textContent = msg.status.lastCommit;
            }
            if (typeof msg.status.activeBlocks === 'number') {
              const $xrl = document.getElementById('ws-ctx-xrl');
              if ($xrl) $xrl.textContent = msg.status.activeBlocks;
            }
            if (typeof msg.status.hasRepoSkeleton === 'boolean') {
              const $repo = document.getElementById('ws-ctx-repo');
              if ($repo) $repo.textContent = msg.status.hasRepoSkeleton ? 'Ready' : 'Missing';
            }
          }
          break;
        case 'sessions_list':
          storedSessions = msg.sessions || [];
          renderAccordion();
          break;
        case 'session_messages':
          $emptyState.style.display = 'none';
          document.querySelectorAll('.msg').forEach(el => el.remove());
          (msg.messages || []).forEach(m => {
            if (m.role === 'user') addMessage('user', 'You', m.content);
            else if (m.role === 'assistant') addMessage('assistant', 'Vibe Coder', m.content);
          });
          break;
        case 'persona_update':
          $personaDropdown.innerHTML = Object.entries(msg.personas || {}).map(([id, p]) => 
            `<div class="persona-option" data-id="${id}">${p.name}</div>`
          ).join('');
          $personaLabel.textContent = msg.activePersona || 'Code';
          $personaDropdown.querySelectorAll('.persona-option').forEach(opt => {
            opt.addEventListener('click', () => {
              vscode.postMessage({ type: 'set_persona', personaId: opt.dataset.id });
              $personaDropdown.classList.remove('open');
            });
          });
          break;
        case 'compression_stats':
          const d = msg.data || {};
          const statsBody = document.getElementById('stats-modal-body');
          if (statsBody) {
            const savingsPct = d.rawTokens > 0 ? (((d.rawTokens - d.foveatedTokens) / d.rawTokens) * 100).toFixed(1) : '0.0';
            statsBody.innerHTML = `
              <div class="stats-container">
                <div class="stats-row">
                  <span>🗜️ <strong>Active Compression Level:</strong></span>
                  <span class="stats-level">Level ${d.level || 3}</span>
                </div>
                <div class="stats-grid">
                  <div class="stats-card">
                    <div class="stats-card-sub">RAW CONTEXT TOKENS</div>
                    <div class="stats-card-val">${(d.rawTokens || 0).toLocaleString()}</div>
                  </div>
                  <div class="stats-card">
                    <div class="stats-card-sub">COMPRESSED TOKENS SENT</div>
                    <div class="stats-card-val stats-green">${(d.foveatedTokens || 0).toLocaleString()}</div>
                  </div>
                </div>
                <div class="stats-banner">
                  <div>
                    <div class="stats-banner-sub">Total Token Reduction</div>
                    <div class="stats-banner-val">⚡ ${savingsPct}% Saved</div>
                  </div>
                  <div class="text-right">
                    <div class="stats-banner-sub">Est. Cloud Cost Saved</div>
                    <div class="stats-banner-val-sm">$${(d.moneySaved || 0).toFixed(2)}</div>
                  </div>
                </div>
              </div>
            `;
          }
          break;
        case 'user_message':
          // Problems (or any external text) injected as a user message
          if (msg.text) {
            $emptyState.style.display = 'none';
            addMessage('user', 'You', msg.text);
            $messages.scrollTop = $messages.scrollHeight;
          }
          break;
        case 'problem_count': {
          const n = msg.count || 0;
          const has = n > 0;
          if ($toolbarProblemCount) {
            $toolbarProblemCount.textContent = String(n);
            $toolbarProblemCount.style.display = has ? 'inline-flex' : 'none';
          }
          $toolbarProblemsBtn && $toolbarProblemsBtn.classList.toggle('toolbar-btn-danger', has);
          const $hdrBtn = document.getElementById('send-problems-btn');
          if ($hdrBtn) $hdrBtn.classList.toggle('btn-problems-hud', has);
          break;
        }
      }
    });

    // ── Old header send-problems-btn (may still exist) ──────────────────
    const $sendProblemsBtn = document.getElementById('send-problems-btn');
    if ($sendProblemsBtn) {
      $sendProblemsBtn.addEventListener('click', () => {
        vscode.postMessage({ type: 'send_all_problems' });
      });
    }

    // ── Toolbar: Send Problems button ────────────────────────────────────
    const $toolbarProblemsBtn = document.getElementById('toolbar-problems-btn');
    const $toolbarProblemCount = document.getElementById('toolbar-problem-count');
    if ($toolbarProblemsBtn) {
      $toolbarProblemsBtn.addEventListener('click', () => {
        vscode.postMessage({ type: 'send_all_problems' });
      });
    }

    // ── Toolbar: Attach File button ──────────────────────────────────────
    const $toolbarAttachBtn = document.getElementById('toolbar-attach-btn');
    if ($toolbarAttachBtn) {
      $toolbarAttachBtn.addEventListener('click', () => {
        vscode.postMessage({ type: 'attach_file' });
      });
    }

    // ── Problem count badge: update when host sends count ─────────────────
    // The extension will push 'problem_count' messages periodically
    window.addEventListener('message', (event) => {
      const msg = event.data;
      if (msg.type === 'problem_count' && $toolbarProblemCount) {
        const n = msg.count || 0;
        const hasProblems = n > 0;
        // Toolbar button
        if (hasProblems) {
          $toolbarProblemCount.textContent = String(n);
          $toolbarProblemCount.style.display = 'inline-flex';
          $toolbarProblemsBtn && $toolbarProblemsBtn.classList.add('toolbar-btn-danger');
        } else {
          $toolbarProblemCount.style.display = 'none';
          $toolbarProblemsBtn && $toolbarProblemsBtn.classList.remove('toolbar-btn-danger');
        }
        // Header button (send-problems-btn)
        const $headerProblemsBtn = document.getElementById('send-problems-btn');
        if ($headerProblemsBtn) {
          $headerProblemsBtn.classList.toggle('btn-problems-hud', hasProblems);
        }
        
        // Workspace context dashboard update
        const $wsProblems = document.getElementById('ws-ctx-problems');
        if ($wsProblems) {
          $wsProblems.textContent = String(n);
          $wsProblems.style.color = hasProblems ? '#ff5252' : 'inherit';
        }
      }
    });



    function showNewSessionFeedback() {
      const $h2 = $emptyState.querySelector('h2');
      const $btnRow = $emptyState.querySelector('.empty-state-btn-row');
      if (!$h2) return;
      
      $h2.innerHTML = '<span style="color: #4caf50;">✨ New Session Created!</span>';
      
      $h2.style.transform = 'scale(1.05)';
      $h2.style.transition = 'transform 0.2s, color 0.2s';
      
      if ($btnRow) {
        $btnRow.style.display = 'none';
      }
      
      setTimeout(() => {
        $h2.style.transform = 'scale(1)';
      }, 300);
    }

    const $statsBtn = document.getElementById('stats-btn');
    const $newSessionBtn = document.getElementById('new-session-btn');
    if ($newSessionBtn) {
      $newSessionBtn.addEventListener('click', () => {
        vscode.postMessage({ type: 'new_session' });
        $messages.innerHTML = '';
        $messages.appendChild($emptyState);
        $emptyState.style.display = 'block';
        $recentSessionsContainer.classList.add('recent-sessions-container-hide');
        showNewSessionFeedback();
      });
    }

    if ($btnStartNew) {
      $btnStartNew.addEventListener('click', () => {
        vscode.postMessage({ type: 'new_session' });
        $messages.innerHTML = '';
        $messages.appendChild($emptyState);
        $emptyState.style.display = 'block';
        $recentSessionsContainer.classList.add('recent-sessions-container-hide');
        $input.focus();
        showNewSessionFeedback();
      });
    }

    if ($btnListSessions) {
      $btnListSessions.addEventListener('click', () => {
        const isHidden = $recentSessionsContainer.classList.contains('recent-sessions-container-hide');
        if (isHidden) {
          $recentSessionsContainer.classList.remove('recent-sessions-container-hide');
          vscode.postMessage({ type: 'get_sessions' });
        } else {
          $recentSessionsContainer.classList.add('recent-sessions-container-hide');
        }
      });

      $btnLoadLatest.addEventListener('click', () => {
        vscode.postMessage({ type: 'load_latest_session' });
      });
    }

    if ($statsBtn) {
      $statsBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const modal = document.getElementById('stats-modal');
        modal.style.display = 'block';
        vscode.postMessage({ type: 'get_compression_stats' });
      });
    }
    const $closeStatsBtn = document.getElementById('close-stats-modal-btn');
    if ($closeStatsBtn) {
      $closeStatsBtn.onclick = () => {
        document.getElementById('stats-modal').style.display = 'none';
      };
    }

    // Lock table top at 70px below header so heads & shoulders remain completely visible below status bar
    function alignTableToArtwork() {
      $emptyState.style.marginTop = '70px';
    }
    window.addEventListener('resize', alignTableToArtwork);
    const $wmImg = document.querySelector('#app-watermark img');
    if ($wmImg) {
      $wmImg.addEventListener('load', alignTableToArtwork);
      if ($wmImg.complete) setTimeout(alignTableToArtwork, 100);
    }
    // ── Smart Microphone & Voice Dictation ──────────────────────────────────
    const micModeKey = 'vibe_coder_mic_mode';
    let micMode = localStorage.getItem(micModeKey) || 'continuous';
    let isRecording = false;
    let recognition = null;
    let finalTranscript = '';
    let holdTimer = null;
    
    // Inject the mode selection menu dynamically
    const $micMenu = document.createElement('div');
    $micMenu.style.cssText = 'display:none; position:absolute; bottom:50px; right:10px; background:var(--vscode-editor-background); border:1px solid var(--vscode-editorWidget-border); border-radius:6px; box-shadow:0 4px 12px rgba(0,0,0,0.5); z-index:100; padding:4px; font-size:11px; font-weight:600; min-width:120px;';
    $micMenu.innerHTML = `
      <div style="padding:4px 8px; color:var(--vscode-descriptionForeground); font-size:10px; border-bottom:1px solid var(--vscode-editorWidget-border); margin-bottom:2px;">Mic Mode</div>
      <div class="mic-option" data-mode="continuous" style="padding:6px 8px; cursor:pointer; border-radius:4px; margin-bottom:2px;">🔄 Continuous</div>
      <div class="mic-option" data-mode="ptt" style="padding:6px 8px; cursor:pointer; border-radius:4px;">👆 Push-To-Talk</div>
    `;
    document.body.appendChild($micMenu);

    const updateMenuSelection = () => {
      $micMenu.querySelectorAll('.mic-option').forEach(el => {
        el.style.background = (el.getAttribute('data-mode') === micMode) ? 'var(--vscode-list-activeSelectionBackground)' : 'transparent';
        el.style.color = (el.getAttribute('data-mode') === micMode) ? 'var(--vscode-list-activeSelectionForeground)' : 'var(--vscode-foreground)';
      });
    };

    $micMenu.querySelectorAll('.mic-option').forEach(el => {
      el.addEventListener('click', (e) => {
        micMode = el.getAttribute('data-mode');
        localStorage.setItem(micModeKey, micMode);
        updateMenuSelection();
        $micMenu.style.display = 'none';
      });
      el.addEventListener('mouseenter', () => el.style.filter = 'brightness(1.2)');
      el.addEventListener('mouseleave', () => el.style.filter = 'none');
    });

    document.addEventListener('click', (e) => {
      if (!e.target.closest('#record-btn') && !e.target.closest('.mic-option')) {
        $micMenu.style.display = 'none';
      }
    });

    if ('webkitSpeechRecognition' in window) {
      recognition = new window.webkitSpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      
      const setRecordingVisuals = (on) => {
        isRecording = on;
        if (on) {
          $recordBtn.style.color = '#ff5252';
          $recordBtn.style.backgroundColor = 'rgba(255, 82, 82, 0.1)';
          $input.placeholder = 'Listening...';
        } else {
          $recordBtn.style.color = 'inherit';
          $recordBtn.style.backgroundColor = 'transparent';
          $input.placeholder = 'Ask Vibe Coder...';
        }
      };

      const stopRecording = () => {
        if (!isRecording) return;
        recognition.stop();
        setRecordingVisuals(false);
        const textToFormat = $input.value.trim();
        if (textToFormat.length > 0) {
          $input.placeholder = 'Auto-formatting dictation...';
          $input.value = '';
          vscode.postMessage({ type: 'format_dictation', text: textToFormat });
        }
      };

      const startRecording = () => {
        if (isRecording) return;
        finalTranscript = '';
        $input.value = '';
        try { recognition.start(); } catch (e) {}
        setRecordingVisuals(true);
      };

      // Button Interaction Logic
      const handlePointerDown = (e) => {
        if (e.button !== 0) return; // Only left click
        e.preventDefault();
        
        // Start Long Press Timer
        holdTimer = setTimeout(() => {
          holdTimer = null;
          updateMenuSelection();
          $micMenu.style.display = 'block';
        }, 500);

        if (micMode === 'ptt') {
          startRecording();
        }
      };

      const handlePointerUp = (e) => {
        e.preventDefault();
        
        // If long press triggered, do nothing more
        if (!holdTimer) {
          if (micMode === 'ptt') {
             stopRecording();
          }
          return;
        }

        // It was a short click
        clearTimeout(holdTimer);
        holdTimer = null;

        if (micMode === 'continuous') {
          if (isRecording) stopRecording();
          else startRecording();
        } else if (micMode === 'ptt') {
          stopRecording(); // In case they clicked incredibly fast
        }
      };

      $recordBtn.addEventListener('mousedown', handlePointerDown);
      $recordBtn.addEventListener('mouseup', handlePointerUp);
      $recordBtn.addEventListener('mouseleave', () => {
        if (holdTimer) clearTimeout(holdTimer);
        if (micMode === 'ptt' && isRecording) stopRecording();
      });
      $recordBtn.addEventListener('touchstart', handlePointerDown);
      $recordBtn.addEventListener('touchend', handlePointerUp);

      recognition.onresult = (event) => {
        let interimTranscript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            finalTranscript += event.results[i][0].transcript + ' ';
          } else {
            interimTranscript += event.results[i][0].transcript;
          }
        }
        $input.value = finalTranscript + interimTranscript;
        autoResizeInput();
      };

      recognition.onend = () => {
        if (isRecording) {
          // If it ends unexpectedly but we think it's still recording, restart
          try { recognition.start(); } catch (e) { setRecordingVisuals(false); }
        }
      };

      recognition.onerror = (e) => {
        console.error('Speech recognition error:', e.error);
        setRecordingVisuals(false);
        $input.placeholder = 'Mic Error: ' + e.error;
      };
    } else {
      $recordBtn.addEventListener('click', () => {
        $input.value = "Voice dictation unsupported in this Webview.";
      });
    }

    // ── New Button Handlers: Ascender Mic, Speaker, Gear ─────────────
    const $ascenderMic = document.getElementById('ascender-mic-btn');
    const $speakerBtn = document.getElementById('speaker-btn');
    const $gearBtn = document.getElementById('gear-btn');
    const $lipBtn = document.getElementById('lip-btn');

    if ($ascenderMic) {
      $ascenderMic.addEventListener('mousedown', () => {
        if ($recordBtn) $recordBtn.dispatchEvent(new MouseEvent('mousedown'));
        $ascenderMic.style.background = 'rgba(255,68,68,0.3)';
        $ascenderMic.style.color = '#ff4444';
        $ascenderMic.style.borderColor = 'rgba(255,68,68,0.4)';
      });
      $ascenderMic.addEventListener('mouseup', () => {
        if ($recordBtn) $recordBtn.dispatchEvent(new MouseEvent('mouseup'));
        $ascenderMic.style.background = 'rgba(57,255,20,0.12)';
        $ascenderMic.style.color = '#39ff14';
        $ascenderMic.style.borderColor = 'rgba(57,255,20,0.2)';
      });
      $ascenderMic.addEventListener('mouseleave', () => {
        if ($recordBtn && isRecording) $recordBtn.dispatchEvent(new MouseEvent('mouseup'));
        $ascenderMic.style.background = 'rgba(57,255,20,0.12)';
        $ascenderMic.style.color = '#39ff14';
        $ascenderMic.style.borderColor = 'rgba(57,255,20,0.2)';
      });
      $ascenderMic.addEventListener('touchstart', (e) => {
        e.preventDefault();
        if ($recordBtn) $recordBtn.dispatchEvent(new Event('mousedown'));
        $ascenderMic.style.background = 'rgba(255,68,68,0.3)';
        $ascenderMic.style.color = '#ff4444';
      });
      $ascenderMic.addEventListener('touchend', (e) => {
        e.preventDefault();
        if ($recordBtn) $recordBtn.dispatchEvent(new Event('mouseup'));
        $ascenderMic.style.background = 'rgba(57,255,20,0.12)';
        $ascenderMic.style.color = '#39ff14';
      });
    }

    if ($speakerBtn) {
      let speakerOn = true;
      $speakerBtn.addEventListener('click', () => {
        speakerOn = !speakerOn;
        $speakerBtn.textContent = speakerOn ? '🔊' : '🔇';
        $speakerBtn.style.opacity = speakerOn ? '1' : '0.4';
        vscode.postMessage({ type: 'toggle_speaker', enabled: speakerOn });
      });
    }

    // ── Bottom bar buttons: History, Settings, Audio, Continuous, Send
    const $historyBtn = document.getElementById('history-btn');
    const $settingsIconBtn = document.getElementById('settings-icon-btn');
    const $audioIconBtn = document.getElementById('audio-icon-btn');
    const $continuousIconBtn = document.getElementById('continuous-icon-btn');
    const $sendBottomBtn = document.getElementById('send-bottom-btn');

    if ($historyBtn) {
      $historyBtn.addEventListener('click', () => {
        const $c = document.getElementById('recent-sessions-container');
        if ($c) {
          const h = $c.classList.contains('recent-sessions-container-hide');
          $c.classList.toggle('recent-sessions-container-hide');
          $historyBtn.textContent = h ? '📋 Hide' : '📋 History';
          if (h) vscode.postMessage({ type: 'get_sessions' });
        }
      });
    }

    if ($settingsIconBtn) {
      $settingsIconBtn.addEventListener('click', () => vscode.postMessage({ type: 'open_settings' }));
    }

    if ($audioIconBtn) {
      let audioMode = 'ptt';
      $audioIconBtn.addEventListener('click', () => {
        audioMode = audioMode === 'ptt' ? 'continuous' : 'ptt';
        $audioIconBtn.style.background = audioMode === 'continuous' ? 'rgba(57,255,20,0.2)' : 'rgba(57,255,20,0.08)';
        $audioIconBtn.title = audioMode === 'continuous' ? 'Continuous listening (ON)' : 'Push-to-talk';
        if (micMode) { micMode = audioMode; localStorage.setItem(micModeKey, audioMode); }
      });
    }

    if ($continuousIconBtn) {
      let continuousOn = false;
      $continuousIconBtn.addEventListener('click', () => {
        continuousOn = !continuousOn;
        $continuousIconBtn.style.background = continuousOn ? 'rgba(57,255,20,0.2)' : 'transparent';
        $continuousIconBtn.style.color = continuousOn ? '#39ff14' : 'var(--text-muted)';
        $continuousIconBtn.title = continuousOn ? 'Continuous: ON' : 'Continuous: OFF';
        if (continuousOn && recognition) { try { recognition.start(); } catch(e) {} }
        else if (!continuousOn && recognition) { try { recognition.stop(); } catch(e) {} }
      });
    }

    if ($sendBottomBtn) {
      $sendBottomBtn.addEventListener('click', () => {
        sendMessage();
      });
    }
    if ($lipBtn) {
      $lipBtn.addEventListener('mousedown', () => {
        if ($recordBtn) $recordBtn.dispatchEvent(new MouseEvent('mousedown'));
        $lipBtn.style.background = 'rgba(255,68,68,0.3)';
        $lipBtn.style.color = '#ff4444';
      });
      $lipBtn.addEventListener('mouseup', () => {
        if ($recordBtn) $recordBtn.dispatchEvent(new MouseEvent('mouseup'));
        $lipBtn.style.background = 'rgba(0,243,255,0.08)';
        $lipBtn.style.color = '#00f3ff';
      });
      $lipBtn.addEventListener('mouseleave', () => {
        if ($recordBtn && isRecording) $recordBtn.dispatchEvent(new MouseEvent('mouseup'));
        $lipBtn.style.background = 'rgba(0,243,255,0.08)';
        $lipBtn.style.color = '#00f3ff';
      });
    }

    // Startup
    vscode.postMessage({ type: 'get_status' });
    vscode.postMessage({ type: 'get_sessions' });
    if (typeof vscode !== "undefined") {
      vscode.postMessage({ type: "webview_ready" });
    }
  