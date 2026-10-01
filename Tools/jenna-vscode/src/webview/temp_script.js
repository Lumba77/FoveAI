
  const vscode = acquireVsCodeApi();

  // ── DOM References ────────────────────────────────────────────────────────
  const $messages        = document.getElementById('messages');
  const $emptyState      = document.getElementById('empty-state');
  const $typingInd       = document.getElementById('typing-indicator');
  const $input           = document.getElementById('user-input');
  const $sendBtn         = document.getElementById('send-btn');
  const $statusDot       = document.getElementById('status-dot');
  const $hudThemes       = document.getElementById('hud-themes');
  const $hudSessions     = document.getElementById('hud-sessions');
  const $hudXrl          = document.getElementById('hud-xrl');
  const $hudLatency      = document.getElementById('hud-latency');
  const $ringSeg         = document.querySelectorAll('.ring-segment');
  const $personaBtn      = document.getElementById('persona-btn');
  const $personaIcon     = document.getElementById('persona-icon');
  const $personaLabel    = document.getElementById('persona-label');
  const $personaDropdown = document.getElementById('persona-dropdown');
  const $newSessionBtn   = document.getElementById('new-session-btn');
  const $reloadBtn       = document.getElementById('reload-btn');
  const $settingsBtn     = document.getElementById('settings-btn');
  const $headerSearchBtn = document.getElementById('header-search-btn');

  // Start New Session (+) Button Handler
  if ($newSessionBtn) {
    $newSessionBtn.addEventListener('click', () => {
      document.querySelectorAll('.msg').forEach(el => el.remove());
      if ($emptyState) $emptyState.style.display = 'flex';
      vscode.postMessage({ type: 'new_session' });
    });
  }

  // Reload / Update Plugin Frame Button Handler
  if ($reloadBtn) {
    $reloadBtn.addEventListener('click', () => {
      $reloadBtn.classList.add('spinning');
      setTimeout(() => $reloadBtn.classList.remove('spinning'), 600);
      vscode.postMessage({ type: 'refresh_plugin' });
    });
  }

  // Header Search Button (🔍) Handler
  if ($headerSearchBtn) {
    $headerSearchBtn.addEventListener('click', () => {
      if ($emptyState) $emptyState.style.display = 'flex';
      const $searchInput = document.getElementById('session-search-input');
      if ($searchInput) {
        $searchInput.focus();
        $searchInput.select();
      }
    });
  }

  // ── State ─────────────────────────────────────────────────────────────────
  let isStreaming = false;
  let currentStreamBubble = null;
  let activePersona = 'code';
  let personasData = {};

  // Toggle Persona Dropdown
  if ($personaBtn) {
    $personaBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if ($xrlDropdown) $xrlDropdown.classList.remove('visible');
      if ($personaDropdown) $personaDropdown.classList.toggle('visible');
    });
  }

  document.addEventListener('click', () => {
    if ($personaDropdown) $personaDropdown.classList.remove('visible');
    if ($xrlDropdown) $xrlDropdown.classList.remove('visible');
  });

  // Auto-resize textarea
  $input.addEventListener('input', () => {
    $input.style.height = 'auto';
    $input.style.height = Math.min($input.scrollHeight, 100) + 'px';
  });

  // Send on Enter
  $input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  $sendBtn.addEventListener('click', sendMessage);

  function sendMessage() {
    const text = $input.value.trim();
    if (!text || isStreaming) return;

    hideEmptyState();
    addMessage('user', 'You', text);
    $input.value = '';
    $input.style.height = 'auto';
    setStreaming(true);
    showTyping(true);

    vscode.postMessage({ type: 'chat', text });
  }

  function renderPersonaDropdown(activeId, personas) {
    personasData = personas || {};
    activePersona = activeId;

    if (personas[activeId]) {
      $personaIcon.textContent = personas[activeId].icon;
      $personaLabel.textContent = personas[activeId].shortName;
    }

    $personaDropdown.innerHTML = '';
    Object.keys(personas).forEach((id) => {
      const p = personas[id];
      const opt = document.createElement('div');
      opt.className = `persona-option ${id === activeId ? 'active' : ''}`;
      opt.innerHTML = `<span>${p.icon}</span> <span>${p.shortName}</span>`;
      opt.addEventListener('click', () => {
        vscode.postMessage({ type: 'set_persona', personaId: id });
        $personaDropdown.classList.remove('visible');
      });
      $personaDropdown.appendChild(opt);
    });
  }

  // ── Message Rendering & Stream Thinking Parser ─────────────────────────────
  function addMessage(role, displayName, content) {
    const msg = document.createElement('div');
    msg.className = `msg ${role}`;

    const header = document.createElement('div');
    header.className = 'msg-header';
    header.textContent = displayName;

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    bubble.innerHTML = renderMarkdown(content);

    msg.appendChild(header);
    msg.appendChild(bubble);

    $messages.insertBefore(msg, $typingInd);
    scrollToBottom();
    return bubble;
  }

  function startStreamBubble() {
    const pDef = personasData[activePersona] || { icon: '⚡', shortName: 'LUMAX' };
    const msg = document.createElement('div');
    msg.className = 'msg assistant';

    const header = document.createElement('div');
    header.className = 'msg-header';
    header.textContent = `${pDef.icon} ${pDef.shortName}`;

    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble';
    
    // Attach stream parsing state
    bubble._streamState = {
      raw: '',
      thinkText: '',
      responseText: '',
      inThink: false,
      thinkStartTime: Date.now(),
      thinkDuration: 0,
      thinkFinished: false,
      accordionEl: null,
      responseEl: null,
    };

    msg.appendChild(header);
    msg.appendChild(bubble);
    $messages.insertBefore(msg, $typingInd);
    return bubble;
  }

  function appendToStreamBubble(bubble, chunk) {
    if (!bubble || !bubble._streamState) return;

    const state = bubble._streamState;
    state.raw += chunk;

    // Stream Thinking Parsing Logic
    const thinkOpenIdx = state.raw.indexOf('<think>');
    const thinkCloseIdx = state.raw.indexOf('</think>');

    if (thinkOpenIdx !== -1) {
      if (thinkCloseIdx !== -1) {
        // Thinking completed
        state.thinkText = state.raw.slice(thinkOpenIdx + 7, thinkCloseIdx).trim();
        state.responseText = state.raw.slice(thinkCloseIdx + 8).trim();
        if (!state.thinkFinished) {
          state.thinkFinished = true;
          state.thinkDuration = ((Date.now() - state.thinkStartTime) / 1000).toFixed(1);
        }
        state.inThink = false;
      } else {
        // Currently inside thinking
        state.inThink = true;
        state.thinkText = state.raw.slice(thinkOpenIdx + 7).trim();
        state.responseText = '';
      }
    } else {
      // No think tag — direct response
      state.inThink = false;
      state.responseText = state.raw;
    }

    renderStreamState(bubble, state);
    scrollToBottom();
  }

  // Global Event Delegation for Accordion Toggles (Robust for WebXR & Spatial Quest Controllers)
  $messages.addEventListener('click', (e) => {
    const header = e.target.closest('.think-header');
    if (header) {
      const accordion = header.closest('.think-accordion');
      if (accordion) {
        accordion.classList.toggle('expanded');
      }
    }
  });

  function renderStreamState(bubble, state) {
    let html = '';

    if (state.thinkText) {
      const isFinished = state.thinkFinished || !state.inThink;
      const headerText = isFinished
        ? `💭 Thought for ${state.thinkDuration || '1.0'}s (click to toggle)`
        : `💭 Thinking... (${((Date.now() - state.thinkStartTime) / 1000).toFixed(1)}s)`;
      
      const expandedClass = isFinished ? '' : 'expanded';

      html += `
        <div class="think-accordion ${expandedClass}">
          <div class="think-header" tabindex="0" role="button" aria-label="Toggle thinking text">
            ${isFinished ? '' : '<div class="think-spinner"></div>'}
            <span>${headerText}</span>
          </div>
          <div class="think-body">${escapeHtml(state.thinkText)}</div>
        </div>
      `;
    }

    if (state.responseText) {
      html += renderMarkdown(state.responseText);
    } else if (state.inThink) {
      html += `<div style="font-size: 11px; color: var(--text-muted); font-style: italic;">Generating response…</div>`;
    }

    bubble.innerHTML = html;
  }

  function finalizeStreamBubble(bubble) {
    if (!bubble || !bubble._streamState) return;
    const state = bubble._streamState;

    if (state.inThink) {
      state.inThink = false;
      state.thinkFinished = true;
      state.thinkDuration = ((Date.now() - state.thinkStartTime) / 1000).toFixed(1);
    }

    // Fallback: If no response text was generated outside <think>, salvage thought text into final response!
    if (!state.responseText && state.thinkText) {
      state.responseText = state.thinkText;
    }

    renderStreamState(bubble, state);
  }

  const $micBtn          = document.getElementById('mic-btn');

  // ── Web Speech API (Voice Input) ──────────────────────────────────────────
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let isRecording = false;

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onresult = (event) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        transcript += event.results[i][0].transcript;
      }
      if (transcript) {
        $input.value = transcript;
        $input.style.height = 'auto';
        $input.style.height = Math.min($input.scrollHeight, 100) + 'px';
      }
    };

    recognition.onerror = (e) => {
      console.warn('[Voice Input] Error:', e.error);
      stopRecording();
    };

    recognition.onend = () => {
      stopRecording();
    };
  }

  if ($micBtn) {
    $micBtn.addEventListener('click', () => {
      if (!recognition) {
        alert('Voice input is not supported in this webview environment.');
        return;
      }
      if (isRecording) {
        recognition.stop();
        stopRecording();
      } else {
        try {
          recognition.start();
          startRecording();
        } catch (err) {
          console.warn('[Voice Input] Failed to start:', err);
        }
      }
    });
  }

  function startRecording() {
    isRecording = true;
    if ($micBtn) {
      $micBtn.classList.add('recording');
      $micBtn.title = 'Listening… Click to Stop';
    }
  }

  function stopRecording() {
    isRecording = false;
    if ($micBtn) {
      $micBtn.classList.remove('recording');
      $micBtn.title = 'Voice Input (Click to Speak)';
    }
  }

  function renderMarkdown(text) {
    if (!text) return '';

    // 1. Unescape literal string newlines (\n or \\n)
    text = text.replace(/\\n/g, '\n');

    // 2. Extract & hoist emotion tags e.g. (emotion: welcoming) or [emotion: warm]
    let emotionBadgeHtml = '';
    text = text.replace(/(?:\(|\[)emotion:\s*([\w\s-]+)(?:\)|\])/gi, (_, emo) => {
      const eName = emo.trim().toLowerCase();
      emotionBadgeHtml += `<div class="emotion-badge">🎭 ${eName}</div>`;
      return '';
    });

    // 3. Escape HTML
    let html = escapeHtml(text.trim());

    // 4. Markdown formatting
    html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => `<pre><code class="lang-${lang}">${code.trim()}</code></pre>`);
    html = html.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/__(.+?)__/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/\n/g, '<br/>');

    // Emotion badge prepended at top of bubble
    return emotionBadgeHtml + html;
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function setStreaming(val) {
    isStreaming = val;
    $sendBtn.disabled = val;
  }

  function showTyping(val) {
    $typingInd.className = val ? 'visible' : '';
  }

  function hideEmptyState() {
    $emptyState.style.display = 'none';
  }

  function scrollToBottom() {
    $messages.scrollTop = $messages.scrollHeight;
  }

  function updateRings(activeBlocks) {
    $ringSeg.forEach((seg, i) => {
      seg.className = 'ring-segment';
      if (i < activeBlocks) seg.classList.add(`active-${i}`);
    });
  }

  // ── Session & Settings Drawers ───────────────────────────────────────────
  // $settingsBtn is already declared at the top
  const $settingsDrawer   = document.getElementById('settings-drawer');
  const $settingsCloseBtn = document.getElementById('settings-close-btn');

  const $statsBtn         = document.getElementById('stats-btn');
  const $statsDrawer      = document.getElementById('stats-drawer');
  const $statsCloseBtn    = document.getElementById('stats-close-btn');

  const $hudSessBtn       = document.getElementById('hud-sess-btn');
  const $sessionDrawer    = document.getElementById('session-drawer');
  const $sessionCloseBtn  = document.getElementById('session-close-btn');
  const $sessionList      = document.getElementById('session-list');

  const $xrlBtn           = document.getElementById('xrl-btn');
  const $xrlDropdown      = document.getElementById('xrl-dropdown');

  const $fontSizeSelect   = document.getElementById('setting-font-size');
  const $settingThemeCount= document.getElementById('settings-theme-count');

  if ($xrlBtn) {
    $xrlBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      $personaDropdown.classList.remove('visible');
      $xrlDropdown.classList.toggle('visible');
    });
  }

  if ($xrlDropdown) {
    $xrlDropdown.addEventListener('click', (e) => {
      const opt = e.target.closest('.persona-option');
      if (opt && opt.dataset.level !== undefined) {
        const lvl = parseInt(opt.dataset.level, 10);
        $xrlDropdown.classList.remove('visible');
        vscode.postMessage({ type: 'set_fovea_level', level: lvl });
      }
    });
  }

  document.addEventListener('click', () => {
    if ($xrlDropdown) $xrlDropdown.classList.remove('visible');
  });

  if ($hudSessBtn) {
    $hudSessBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      $settingsDrawer.classList.remove('open');
      $sessionDrawer.classList.toggle('open');
      if ($sessionDrawer.classList.contains('open')) {
        vscode.postMessage({ type: 'get_sessions' });
      }
    });
  }

  if ($sessionCloseBtn) {
    $sessionCloseBtn.addEventListener('click', () => $sessionDrawer.classList.remove('open'));
  }

  if ($settingsBtn) {
    $settingsBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      $sessionDrawer.classList.remove('open');
      if ($statsDrawer) $statsDrawer.classList.remove('open');
      $settingsDrawer.classList.toggle('open');
    });
  }

  if ($statsBtn) {
    $statsBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      $sessionDrawer.classList.remove('open');
      $settingsDrawer.classList.remove('open');
      $statsDrawer.classList.toggle('open');
      if ($statsDrawer.classList.contains('open')) {
        vscode.postMessage({ type: 'get_compression_stats' });
      }
    });
  }

  if ($statsCloseBtn) {
    $statsCloseBtn.addEventListener('click', () => $statsDrawer.classList.remove('open'));
  }

  if ($settingsCloseBtn) {
    $settingsCloseBtn.addEventListener('click', () => $settingsDrawer.classList.remove('open'));
  }

  if ($fontSizeSelect) {
    $fontSizeSelect.addEventListener('change', (e) => {
      const px = e.target.value;
      document.documentElement.style.setProperty('--font-size-base', px + 'px');
      document.body.style.fontSize = px + 'px';
    });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  const CATEGORIES = [
    { id: 'frontend',  name: 'Frontend & UI',       icon: '🎨', match: /frontend|vessel|xr|html|css|ui|webview|chat|component/i },
    { id: 'cognition', name: 'Cognition & Soul',    icon: '🧠', match: /cognition|soul|llm|brain|persona|prompt|agent/i },
    { id: 'memory',    name: 'Memory & Context',    icon: '💾', match: /memory|foveated|stardust|vector|xrl|context|token/i },
    { id: 'tools',     name: 'Tools & Extension',   icon: '🛠️', match: /tools|vscode|plugin|extension|mcp|jenna|cli/i },
    { id: 'core',      name: 'Core & Config',       icon: '⚡', match: /.*/ }
  ];

  let storedSessions = []; // populated from disk or port 8200
  const openCategories = new Set(['core']); // core open by default (catches uncategorised sessions)

  function classifySession(s) {
    if (s.category && CATEGORIES.some(c => c.id === s.category)) return s.category;
    const text = `${s.preview || ''} ${s.session_id || ''} ${s.title || ''}`;
    for (let i = 0; i < CATEGORIES.length - 1; i++) {
      if (CATEGORIES[i].match.test(text)) return CATEGORIES[i].id;
    }
    return 'core';
  }

  function renderSessionList(sessions) {
    storedSessions = sessions || [];
    renderAccordion();
  }

  // Show skeleton categories immediately on load
  renderAccordion();

  function renderAccordion() {
    const $list = document.getElementById('recent-sessions-list');
    const $drawerList = document.getElementById('session-list');

    // Group sessions by category
    const groups = {};
    CATEGORIES.forEach(c => { groups[c.id] = []; });
    (storedSessions || []).forEach(s => {
      const cat = classifySession(s);
      if (groups[cat]) groups[cat].push(s);
    });

    // Build accordion HTML
    let html = '';
    CATEGORIES.forEach(cat => {
      const items = groups[cat.id] || [];
      const isOpen = openCategories.has(cat.id);
      const count = items.length;
      if (count === 0) return; // hide empty categories

      const bodyContent = items.map(s => {
        const num = storedSessions.indexOf(s) + 1;
        const timeStr = s.last_updated
          ? new Date(s.last_updated).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
          : '';
        const msgCount = s.count ? `${s.count} msgs` : '';
        const preview = escapeHtml(s.preview || 'Conversation history…');
        return `
          <div class="recent-session-card" data-session-id="${escapeHtml(s.session_id)}" tabindex="0">
            <div class="recent-session-title">
              <span>📜 Session ${num}</span>
              <span class="recent-session-meta">${msgCount}${msgCount && timeStr ? ' · ' : ''}${timeStr}</span>
            </div>
            <div class="recent-session-preview">${preview}</div>
          </div>`;
      }).join('');

      html += `
        <div class="acc-category" data-cat="${cat.id}">
          <div class="acc-header ${isOpen ? 'open' : ''}">
            <span class="acc-chevron">${isOpen ? '▾' : '▸'}</span>
            <span class="acc-icon">${cat.icon}</span>
            <span class="acc-label">${cat.name}</span>
            <span class="acc-count">${count}</span>
          </div>
          <div class="acc-body" style="display:${isOpen ? 'flex' : 'none'}">
            ${bodyContent}
          </div>
        </div>`;
    });

    if (!html) {
      html = '<div class="sessions-empty">No sessions yet — start your first conversation!</div>';
    }

    if ($list) $list.innerHTML = html;
    if ($drawerList) $drawerList.innerHTML = html;

    // Wire up accordion toggles in both containers
    [$list, $drawerList].forEach(container => {
      if (!container) return;
      container.querySelectorAll('.acc-header').forEach(header => {
        header.addEventListener('click', () => {
          const cat = header.closest('.acc-category').dataset.cat;
          const isNowOpen = openCategories.has(cat);
          if (isNowOpen) {
            openCategories.delete(cat);
          } else {
            openCategories.add(cat);
          }
          renderAccordion(); // re-render both
        });
      });

      // Wire up session card clicks
      container.querySelectorAll('.recent-session-card').forEach(card => {
        card.addEventListener('click', () => {
          if (card.dataset.sessionId) {
            const $drawer = document.getElementById('session-drawer');
            if ($drawer) $drawer.classList.remove('open');
            vscode.postMessage({ type: 'get_session_messages', sessionId: card.dataset.sessionId });
          }
        });
      });
    });
  }

  // Handle click on session-drawer cards (legacy drawer)
  if ($sessionList) {
    $sessionList.addEventListener('click', (e) => {
      const card = e.target.closest('.recent-session-card') || e.target.closest('.session-card');
      if (card && card.dataset.sessionId) {
        $sessionDrawer.classList.remove('open');
        vscode.postMessage({ type: 'get_session_messages', sessionId: card.dataset.sessionId });
      }
    });
  }

  function renderSessionHistory(messages) {
    if (!messages || messages.length === 0) return;
    hideEmptyState();
    document.querySelectorAll('.msg').forEach(el => el.remove());
    
    messages.forEach(m => {
      if (m.role === 'user') {
        addMessage('user', 'You', m.content);
      } else if (m.role === 'assistant') {
        const bubble = startStreamBubble();
        appendToStreamBubble(bubble, m.content);
        finalizeStreamBubble(bubble);
      }
    });
    scrollToBottom();
  }

  function updateStatus(status) {
    if (!status) return;
    const $statusLabel = document.querySelector('.status-label');
    if ($statusDot) $statusDot.className = status.online ? 'online' : 'offline';
    if ($statusLabel) {
      $statusLabel.textContent = status.online ? 'Online' : 'Offline';
      $statusLabel.style.color = status.online ? '#10b981' : '#f59e0b';
    }
    if ($hudSessions) $hudSessions.textContent = status.online ? String(status.totalSessions || 0) : '—';
    if ($hudXrl) $hudXrl.textContent      = status.online ? `L${status.compressionLevel}`     : '—';
    if ($hudLatency) $hudLatency.textContent  = status.online ? `${status.latencyMs}ms`           : '—';
    if ($settingThemeCount) {
      $settingThemeCount.textContent = `${status.totalThemes || 0} Consolidated Theme Blocks Active`;
    }
    if (status.online && typeof updateRings === 'function') updateRings(status.activeBlocks);
  }

  // ── Message Bus ───────────────────────────────────────────────────────────
  window.addEventListener('message', (event) => {
    const msg = event.data;

    switch (msg.type) {
      case 'stream_start':
        showTyping(false);
        currentStreamBubble = startStreamBubble();
        break;

      case 'stream_chunk':
        if (currentStreamBubble) {
          appendToStreamBubble(currentStreamBubble, msg.chunk);
        }
        break;

      case 'stream_end':
        if (currentStreamBubble) {
          finalizeStreamBubble(currentStreamBubble);
        }
        currentStreamBubble = null;
        setStreaming(false);
        break;

      case 'stream_error':
        showTyping(false);
        setStreaming(false);
        currentStreamBubble = null;
        addMessage('assistant', 'LUMAX', `⚠️ ${msg.error || 'Connection error (port 8200).'}`);
        break;

      case 'persona_update':
        renderPersonaDropdown(msg.activePersona, msg.personas);
        break;

      case 'status_update':
        updateStatus(msg.status);
        break;

      case 'sessions_list':
        renderSessionList(msg.sessions);
        break;

      case 'sessions_offline': {
        const $list = document.getElementById('recent-sessions-list');
        if ($list) {
          $list.innerHTML = `
            <div class="sessions-offline">
              <div class="sessions-offline-icon">🔌</div>
              <div class="sessions-offline-text">LUMAX offline</div>
              <div class="sessions-offline-sub">Start the LUMAX stack to load past sessions</div>
              <button class="sessions-retry-btn" onclick="vscode.postMessage({type:'get_sessions'})">Retry</button>
            </div>`;
        }
        break;
      }

      case 'session_messages':
        renderSessionHistory(msg.messages);
        break;

      case 'compression_stats':
        {
          const d = msg.data;
          if (!d) break;

          document.getElementById('stats-time-gained').textContent = `~${d.timeGainedHours}h Extra Time Gained`;
          document.getElementById('stats-total-saved').textContent = `${d.savedTokens.toLocaleString()} tokens saved this session`;

          const rawK = (d.rawTokens / 1000).toFixed(1);
          const fovK = (d.foveatedTokens / 1000).toFixed(1);
          document.getElementById('stats-lbl-uncompressed').textContent = `${rawK}k tokens`;
          document.getElementById('stats-lbl-compressed').textContent = `${fovK}k tokens`;

          const total = Math.max(d.rawTokens, 1);
          const fovPct = Math.max((d.foveatedTokens / total) * 100, 2); // min 2% for visibility
          document.getElementById('stats-bar-uncompressed').style.width = '100%';
          document.getElementById('stats-bar-compressed').style.width = `${fovPct}%`;

          document.getElementById('stats-budget-bar').style.width = `${d.budgetPct}%`;
          document.getElementById('stats-budget-pct').textContent = `${d.budgetPct.toFixed(1)}% Used`;
          document.getElementById('stats-budget-reset').textContent = `Resets in ${d.hoursUntilReset}h`;

          document.getElementById('stats-money-saved').textContent = `$${d.moneySaved.toFixed(3)}`;
          document.getElementById('stats-ratio').textContent = `${d.compressionRatio.toFixed(1)}x`;
        }
        break;

      case 'clear':
        document.querySelectorAll('.msg').forEach(el => el.remove());
        $emptyState.style.display = '';
        break;
    }
  });

  // Auto-restore status and latest sessions on startup
  vscode.postMessage({ type: 'get_status' });
  vscode.postMessage({ type: 'get_sessions' });
