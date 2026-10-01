
    const vscode = acquireVsCodeApi();

    // UI Elements
    const $messages = document.getElementById('messages');
    const $emptyState = document.getElementById('empty-state');
    const $recentSessionsContainer = document.getElementById('recent-sessions-container');
    const $recentSessionsList = document.getElementById('recent-sessions-list');
    
    const $btnStartNew = document.getElementById('btn-start-new');
    const $btnListSessions = document.getElementById('btn-list-sessions');
    
    const $input = document.getElementById('chat-input');
    const $sendBtn = document.getElementById('send-btn');
    const $recordBtn = document.getElementById('record-btn');
    
    const $statusDot = document.getElementById('status-dot');
    const $hudXrl = document.getElementById('hud-xrl');
    
    // Dropdowns
    const $personaBtn = document.getElementById('persona-btn');
    const $personaDropdown = document.getElementById('persona-dropdown');
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
    });
    $xrlBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      $xrlDropdown.classList.toggle('open');
      $personaDropdown.classList.remove('open');
    });
    document.addEventListener('click', () => {
      $personaDropdown.classList.remove('open');
      $xrlDropdown.classList.remove('open');
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

    let attachedFiles = [];
    const $attachBtn = document.getElementById('attach-btn');
    const $attachedFilesBar = document.getElementById('attached-files-bar');

    if ($attachBtn) {
      $attachBtn.addEventListener('click', () => {
        vscode.postMessage({ type: 'attach_file' });
      });
    }

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
      vscode.postMessage({ type: 'chat', text: fullPrompt });
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
      
      $messages.appendChild(msg);
      $messages.scrollTop = $messages.scrollHeight;
    }

    function startStreamBubble() {
      const msg = document.createElement('div');
      msg.className = 'msg assistant';
      const bubble = document.createElement('div');
      bubble.className = 'msg-bubble';
      bubble.dataset.raw = '';
      msg.innerHTML = '<div class="msg-role">Jenna</div>';
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

      actionsBar.appendChild(copyBtn);
      actionsBar.appendChild(editBtn);
      actionsBar.appendChild(delBtn);

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
        
        let bodyHtml = items.map(s => {
          let sid = s.session_id || s.id || '';
          let shortId = sid ? 'Session #' + sid.slice(-6) : 'Untitled Session';
          let rawTitle = s.title || (typeof s.preview === 'string' && s.preview.trim() ? '"' + s.preview.slice(0, 35).trim() + '..."' : shortId);
          rawTitle = rawTitle.replace(/[◆◇■□●○★☆▲▼#*_`]/g, '').trim();
          if (!rawTitle || rawTitle === 'Untitled Session') rawTitle = shortId;
          let keywordsHtml = '';
          if (s.keywords) {
            const kwLines = String(s.keywords).split('\n').map(l => l.trim()).filter(Boolean);
            const row1 = kwLines[0] || '';
            const row2 = kwLines[1] || '';
            keywordsHtml = `
              <div class="rs-keywords-container" style="margin: 4px 0 2px 0; display: flex; flex-direction: column; gap: 2px;">
                ${row1 ? `<div class="rs-keywords-row1" style="font-size: 10px; font-weight: 500; color: var(--vscode-textLink-foreground, #3794ff); opacity: 0.85; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">🏷️ ${escapeHtml(row1)}</div>` : ''}
                ${row2 ? `<div class="rs-keywords-row2" style="font-size: 10px; font-weight: 500; color: var(--vscode-charts-orange, #e5a43b); opacity: 0.85; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">📌 ${escapeHtml(row2)}</div>` : ''}
              </div>
            `;
          }
          return `
          <div class="recent-session-card" data-id="${sid}">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 4px;">
              <div class="rs-title" style="flex: 1; font-weight: 600;">${escapeHtml(rawTitle)}</div>
              <button class="ingredients-btn" data-id="${sid}" title="View Detailed Session Index & Ingredients" style="background: var(--bg-glass); border: 1px solid var(--border); border-radius: 4px; padding: 1px 5px; font-size: 10px; cursor: pointer; color: var(--text-primary); opacity: 0.85; flex-shrink: 0;">📜 Index</button>
            </div>
            ${keywordsHtml}
            <div class="rs-meta" style="margin-top: 2px;">${new Date(s.last_updated).toLocaleString()} · ${s.turn_count || s.count || 0} turns</div>
          </div>
        `;
        }).join('');

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
        case 'file_attached':
          if (msg.file) {
            attachedFiles.push(msg.file);
            renderAttachedFiles();
          }
          break;
        case 'status_update':
          updateStatus(msg.status);
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
            else if (m.role === 'assistant') addMessage('assistant', 'Jenna', m.content);
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
      }
    });



    const $statsBtn = document.getElementById('stats-btn');
    if ($newSessionBtn) {
      $newSessionBtn.addEventListener('click', () => {
        vscode.postMessage({ type: 'new_session' });
        $messages.innerHTML = '';
        $messages.appendChild($emptyState);
        $emptyState.style.display = 'block';
        $recentSessionsContainer.classList.add('recent-sessions-container-hide');
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

    // Lock table top at 130px below header so heads & shoulders remain completely visible below status bar
    function alignTableToArtwork() {
      $emptyState.style.marginTop = '130px';
    }
    window.addEventListener('resize', alignTableToArtwork);
    const $wmImg = document.querySelector('#app-watermark img');
    if ($wmImg) {
      $wmImg.addEventListener('load', alignTableToArtwork);
      if ($wmImg.complete) setTimeout(alignTableToArtwork, 100);
    }

    // Startup
    vscode.postMessage({ type: 'get_status' });
    vscode.postMessage({ type: 'get_sessions' });
    if (typeof vscode !== "undefined") {
      vscode.postMessage({ type: "webview_ready" });
    }
  
