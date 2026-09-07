// FoveAI Control Panel — popup.js
// v2.0: Connection-aware UX with clear next-step guidance

const HOST = 'com.foveai.foveai_host';

// ── Native Messaging ──

function sendNative(msg) {
  return new Promise((resolve, reject) => {
    try {
      chrome.runtime.sendNativeMessage(HOST, msg, response => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else {
          resolve(response);
        }
      });
    } catch (e) {
      reject(e);
    }
  });
}

// ── Connection Status ──

let nativeHostConnected = false;

async function checkConnection() {
  const banner = document.getElementById('conn-banner');
  const title = document.getElementById('conn-title');
  const detail = document.getElementById('conn-detail');

  try {
    const r = await sendNative({ action: 'ping' });
    nativeHostConnected = true;
    banner.className = 'conn-banner conn-ok';
    title.textContent = '✅ Native host connected';
    detail.innerHTML = 'System control & LLM management available.';
  } catch (e) {
    nativeHostConnected = false;
    banner.className = 'conn-banner conn-fail';
    title.textContent = '⚠ Native host not connected';

    const errMsg = e.message || '';
    let diagnosis = '';

    if (errMsg.includes('not found') || errMsg.includes('native messaging') || errMsg.includes('Receiving end')) {
      diagnosis = `
        <div class="conn-step">
          <b>Chrome caches native messaging hosts.</b> Reloading the extension is NOT enough.<br><br>
          <b>Step 1:</b> <a id="restart-chrome">Restart Chrome completely</a> (close all windows, reopen)<br>
          <b>Step 2:</b> After restart, run in PowerShell:<br>
          <code>cd Frontend/ChromeExtension/native</code><br>
          <code>.\install_host.ps1</code><br>
          <b>Step 3:</b> <a id="reload-ext">Reload the extension</a> in chrome://extensions<br><br>
          <div style="font-size:9px;color:#ff4444;margin-top:4px;">
            Error: <code>${errMsg.slice(0, 120)}</code>
          </div>
        </div>`;
    } else if (errMsg.includes('access') || errMsg.includes('denied')) {
      diagnosis = `
        <div class="conn-step">
          <b>Registry key may be wrong.</b><br>
          Run <code>install_host.ps1</code> again, then <a id="reload-ext">reload the extension</a>.
        </div>`;
    } else {
      diagnosis = `
        <div class="conn-step">
          Error: <code>${errMsg.slice(0, 120)}</code><br><br>
          <b>Fix:</b> <a id="restart-chrome">Restart Chrome completely</a>,<br>
          then run <code>install_host.ps1</code> if still broken.
        </div>`;
    }

    detail.innerHTML = `The native messaging host bridge is not reachable.${diagnosis}`;

    // Wire all links
    document.querySelectorAll('#reload-ext, #reload-ext-2').forEach(el => {
      if (el) el.onclick = () => chrome.tabs.create({ url: 'chrome://extensions' });
    });
    document.querySelectorAll('#restart-chrome').forEach(el => {
      if (el) el.onclick = () => chrome.tabs.create({ url: 'chrome://restart' });
    });
  }

  // Update button states based on connection
  document.getElementById('btn-start').disabled = !nativeHostConnected;
  document.getElementById('btn-stop').disabled = !nativeHostConnected;
  document.getElementById('btn-build').disabled = !nativeHostConnected;
  document.getElementById('btn-pull').disabled = !nativeHostConnected;
  document.getElementById('btn-toggle-stack').disabled = !nativeHostConnected;

  // Check if stack is already running and update toggle button
  checkStackRunning().then(updateToggleButton);
}

// ── Service Status ──

async function httpStatus() {
  const services = [
    { name: 'soul', port: 8402 },
    { name: 'proxy', port: 8400 },
    { name: 'dashboard', port: 8401 },
    { name: 'ears', port: 8001 },
    { name: 'memory', port: 8002 },
    { name: 'creative', port: 8003 },
    { name: 'mouth', port: 8004 },
    { name: 'webui', port: 8080 },
  ];
  const grid = document.getElementById('svc-grid');
  grid.innerHTML = '';
  for (const svc of services) {
    let alive = false;
    let reason = '';
    try {
      // Route health checks through the Nexus Proxy on port 8080 to avoid CORS errors.
      // The extension runs from chrome-extension:// origin, which can't directly fetch
      // http://127.0.0.1:8000/health etc. The proxy adds CORS headers for chrome-extension://.
      const r = await fetch(`http://127.0.0.1:8080/api/health-proxy/${svc.port}`, { signal: AbortSignal.timeout(3000) });
      if (r.ok) {
        const data = await r.json();
        alive = data.ok;
        if (!data.ok) {
          reason = data.error || `HTTP ${data.status}`;
        }
      } else {
        alive = false;
        reason = `HTTP ${r.status}`;
      }
    } catch (e) {
      alive = false;
      reason = e.message || 'Connection refused';
    }
    const div = document.createElement('div');
    div.className = 'svc';
    const reasonHtml = reason ? `<span style="color:#ff4444;font-size:9px;margin-left:4px;" title="${reason}">⚠</span>` : '';
    div.innerHTML = `<div class="dot ${alive ? 'alive' : 'dead'}"></div>${svc.name} :${svc.port}${reasonHtml}`;
    grid.appendChild(div);
  }
}

// ── LLM Backend UI ──

function renderBackends(backends) {
  const container = document.getElementById('llm-backends');
  container.innerHTML = '';

  for (const [key, info] of Object.entries(backends)) {
    const card = document.createElement('div');
    card.className = `backend-card${info.running ? ' running' : ''}`;

    const statusText = info.running ? '● Running' : (info.installed ? '○ Installed' : '✗ Not found');
    const statusColor = info.running ? '#2ecc71' : (info.installed ? '#f0ad4e' : '#ff4444');

    let modelsHtml = '';
    if (info.models && info.models.length > 0) {
      modelsHtml = `<div class="backend-models">Models: ${info.models.join(', ')}</div>`;
    }

    let offloadHtml = '';
    if (info.supports_offload) {
      offloadHtml = `<div style="font-size:9px;color:#2ecc71;margin-top:2px">⚡ GPU offload supported</div>`;
    } else if (info.offload_description) {
      offloadHtml = `<div style="font-size:9px;color:#ff4444;margin-top:2px">${info.offload_description}</div>`;
    }

    card.innerHTML = `
      <div class="backend-name">${info.name}</div>
      <div class="backend-status" style="color:${statusColor}">${statusText} — port ${info.port}</div>
      ${offloadHtml}
      ${modelsHtml}
      <div class="backend-actions">
        ${info.installed && key === 'llama_cpp' ? `
          <input type="text" id="llm-model-path" placeholder="Model path (.gguf)" style="margin-top:4px">
          <input type="number" id="llm-gpu-layers" value="-1" min="-1" max="999" placeholder="GPU layers (-1=all, 0=CPU)" style="margin-top:2px">
        ` : ''}
        ${info.installed ? `<button class="btn btn-sm btn-start" data-backend="${key}" data-action="start">▶ Start</button>` : ''}
        ${info.running ? `<button class="btn btn-sm btn-stop" data-backend="${key}" data-action="stop">■ Stop</button>` : ''}
      </div>
    `;
    container.appendChild(card);
  }

  // Wire up backend action buttons
  container.querySelectorAll('button[data-action]').forEach(btn => {
    btn.onclick = async () => {
      const backend = btn.dataset.backend;
      const action = btn.dataset.action;
      const msg = document.getElementById('msg-llm');

      if (action === 'start') {
        msg.textContent = `Starting ${backend}...`;
        try {
          const startMsg = { action: 'llm_start', backend };
          if (backend === 'llama_cpp') {
            const modelInput = document.getElementById('llm-model-path');
            const gpuInput = document.getElementById('llm-gpu-layers');
            if (modelInput?.value) startMsg.model = modelInput.value;
            if (gpuInput?.value) startMsg.n_gpu_layers = parseInt(gpuInput.value);
          }
          const r = await sendNative(startMsg);
          msg.className = 'msg msg-ok';
          msg.textContent = r.message || 'Started';
        } catch (e) {
          msg.className = 'msg msg-err';
          msg.textContent = '✗ Native host error — see banner above';
        }
        setTimeout(refreshLLMs, 3000);
      } else if (action === 'stop') {
        msg.textContent = `Stopping ${backend}...`;
        try {
          const r = await sendNative({ action: 'llm_stop', backend });
          msg.className = 'msg msg-ok';
          msg.textContent = r.message || 'Stopped';
        } catch (e) {
          msg.className = 'msg msg-err';
          msg.textContent = '✗ Native host error — see banner above';
        }
        setTimeout(refreshLLMs, 2000);
      }
    };
  });
}

async function detectBackends() {
  const msg = document.getElementById('msg-llm');
  msg.textContent = 'Scanning system...';
  try {
    const r = await sendNative({ action: 'llm_detect' });
    if (r.status === 'ok') {
      renderBackends(r.backends);
      const found = Object.values(r.backends).filter(b => b.installed).length;
      msg.className = 'msg msg-ok';
      msg.textContent = `✓ Found ${found} backend(s)`;
    }
  } catch (e) {
    msg.className = 'msg msg-err';
    msg.textContent = '✗ Native host not connected — see banner';
  }
}

async function refreshLLMs() {
  try {
    const r = await sendNative({ action: 'llm_status' });
    if (r.status === 'ok') {
      renderBackends(r.backends);
    }
  } catch (e) {
    // Silent — native host status shown in banner
  }
}

// ── Environment & Features ──
// ── Initialize checkboxes from .env on popup load ──
async function initEnvCheckboxes() {
    try {
        const r = await fetch('http://127.0.0.1:8080/api/soul/env', { signal: AbortSignal.timeout(3000) });
        if (r.ok) {
            const data = await r.json();
            if (data.status === 'ok' && data.env) {
                const env = data.env;
                const checkboxMap = {
                    'env-hud-enabled': 'FoveAI_HUD_ENABLED',
                    'env-audio-only': 'FoveAI_AUDIO_ONLY_PROXY',
                    'env-librarian': 'FoveAI_LIBRARIAN_ENABLED',
                };
                for (const [id, envKey] of Object.entries(checkboxMap)) {
                    const el = document.getElementById(id);
                    if (el && env[envKey] !== undefined) {
                        el.checked = env[envKey] === 'true';
                    }
                }
                // Token conservation: true if FoveAI_CLOUD_MAX_TOKENS <= 3000
                const tokenConserv = document.getElementById('env-token-conserv');
                if (tokenConserv && env.FoveAI_CLOUD_MAX_TOKENS) {
                    tokenConserv.checked = parseInt(env.FoveAI_CLOUD_MAX_TOKENS) <= 3000;
                }
            }
        }
    } catch (e) {
        console.log('Could not fetch .env for checkbox init:', e.message);
    }
}
initEnvCheckboxes();


document.getElementById('btn-env-save').onclick = async () => {
  const msg = document.getElementById('msg-env');
  msg.textContent = 'Saving & Rebooting...';

  const hudEnabled = document.getElementById('env-hud-enabled').checked;
  const audioOnly = document.getElementById('env-audio-only').checked;
  const tokenConserv = document.getElementById('env-token-conserv').checked;
  const librarianEnabled = document.getElementById('env-librarian').checked;

  const updates = {
    "FoveAI_HUD_ENABLED": hudEnabled ? "true" : "false",
    "FoveAI_AUDIO_ONLY_PROXY": audioOnly ? "true" : "false",
    "FoveAI_CLOUD_MAX_TOKENS": tokenConserv ? "3000" : "8192",
    "FoveAI_SOFT_PROMPT_TOKENS_HIGH": tokenConserv ? "3000" : "8192",
    "FoveAI_LIBRARIAN_ENABLED": librarianEnabled ? "true" : "false"
  };

  try {
    // Route through Nexus Proxy to avoid CORS errors from chrome-extension:// origin
    const r = await fetch('http://127.0.0.1:8080/api/soul/env', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ updates })
    });
    if (r.ok) {
      msg.className = 'msg msg-ok';
      msg.textContent = '✓ Saved! Reloading frontend...';
      // Reload any open FoveAI frontend tabs to apply settings
      chrome.tabs.query({ url: 'http://localhost:8080/*' }, (tabs) => {
        for (const tab of tabs) {
          chrome.tabs.reload(tab.id);
        }
      });
    } else {
      throw new Error('HTTP ' + r.status);
    }
  } catch (e) {
    msg.className = 'msg msg-err';
    msg.textContent = '✗ Failed to reach XRLF Runtime (port 8402)';
  }
};

// ── System Buttons ──

document.getElementById('btn-start').onclick = async () => {
  const msg = document.getElementById('msg-system');
  msg.textContent = 'Starting FoveAI stack...';
  try {
    const r = await sendNative({ action: 'start' });
    if (r.status === 'ok') {
      msg.className = 'msg msg-ok';
      msg.textContent = r.message || '✓ Started';
    } else if (r.status === 'degraded') {
      msg.className = 'msg msg-warn';
      msg.innerHTML = (r.message || '⚠ Partially started').replace(/\n/g, '<br>');
    } else {
      msg.className = 'msg msg-err';
      // Show diagnostics in a readable format
      let html = (r.message || '✗ Failed to start').replace(/\n/g, '<br>');
      if (r.diagnostics && r.diagnostics.length > 0) {
        html += '<br><br><b>Pre-flight check:</b><br>';
        html += r.diagnostics.map(d => d.replace(/^✅ /, '<span style="color:#2ecc71">✅</span> ')
                                          .replace(/^⚠ /, '<span style="color:#ffaa00">⚠</span> ')
                                          .replace(/^❌ /, '<span style="color:#ff4444">❌</span> ')).join('<br>');
      }
      msg.innerHTML = html;
    }
    setTimeout(httpStatus, 3000);
    setTimeout(refreshLLMs, 5000);
  } catch (e) {
    msg.className = 'msg msg-err';
    msg.textContent = '✗ Native host not connected — see banner';
  }
};

// ── Single Toggle Button: Start & Open / Stop & Close ──

const FRONTEND_URL = 'https://foveai.1um6a.se/';
const HEALTH_CHECKS = [
  { name: 'Nexus Proxy (Frontend)', url: 'http://127.0.0.1:8080/health', port: 8080 },
  { name: 'Soul Core', url: 'http://127.0.0.1:8402/health', port: 8402 },
  { name: 'Memory', url: 'http://127.0.0.1:8080/api/health-proxy/8002', port: 8002 },
  { name: 'Creative', url: 'http://127.0.0.1:8080/api/health-proxy/8003', port: 8003 },
  { name: 'Mouth (TTS)', url: 'http://127.0.0.1:8080/api/health-proxy/8004', port: 8004 },
  { name: 'WebUI', url: 'http://127.0.0.1:8080/', port: 8080 },
];

const POLL_INTERVAL = 2000; // 2 seconds between checks
const MAX_POLL_TIME = 60000; // 60 seconds total timeout

async function checkServiceHealth(url) {
  try {
    const r = await fetch(url, { signal: AbortSignal.timeout(3000) });
    if (!r.ok) return false;
    // For health-proxy endpoints, check the JSON response body
    if (url.includes('/api/health-proxy/')) {
      const data = await r.json();
      return data.ok === true;
    }
    return true;
  } catch {
    return false;
  }
}

async function pollServices(progressBar, statusText) {
  const startTime = Date.now();
  let allHealthy = false;
  const healthy = new Set();

  while (Date.now() - startTime < MAX_POLL_TIME) {
    // Check all services
    for (const svc of HEALTH_CHECKS) {
      if (healthy.has(svc.name)) continue; // Already confirmed healthy
      const alive = await checkServiceHealth(svc.url);
      if (alive) {
        healthy.add(svc.name);
      }
    }

    // Update progress
    const pct = Math.round((healthy.size / HEALTH_CHECKS.length) * 100);
    progressBar.style.width = pct + '%';
    statusText.textContent = `${healthy.size}/${HEALTH_CHECKS.length} services ready — ${HEALTH_CHECKS.map(s => healthy.has(s.name) ? '✓' : '⟳').join(' ')}`;

    // Check if all healthy
    if (healthy.size >= HEALTH_CHECKS.length) {
      allHealthy = true;
      progressBar.style.width = '100%';
      statusText.textContent = '✅ All services ready! Redirecting...';
      break;
    }

    // Wait before next poll
    await new Promise(r => setTimeout(r, POLL_INTERVAL));
  }

  return allHealthy;
}

// ── Stack state tracking ──
let _stackRunning = false;

async function checkStackRunning() {
  // Quick check: if frontend is up, stack is likely running
  try {
    const r = await fetch('http://127.0.0.1:8080/health', { signal: AbortSignal.timeout(2000) });
    _stackRunning = r.ok;
  } catch {
    _stackRunning = false;
  }
  return _stackRunning;
}

function updateToggleButton() {
  const btn = document.getElementById('btn-toggle-stack');
  if (!btn) return;
  if (_stackRunning) {
    btn.textContent = '⏹ Stop FoveAI Stack';
    btn.className = 'btn btn-stop';
    btn.style.fontSize = '16px';
    btn.style.padding = '12px';
  } else {
    btn.textContent = '🚀 Start FoveAI Stack';
    btn.className = 'btn btn-primary';
    btn.style.fontSize = '16px';
    btn.style.padding = '12px';
  }
}

document.getElementById('btn-toggle-stack').onclick = async () => {
  const btn = document.getElementById('btn-toggle-stack');
  const progressDiv = document.getElementById('startup-progress');
  const progressBar = document.getElementById('startup-progress-bar');
  const statusText = document.getElementById('startup-status-text');

  // If stack is running, stop it
  if (_stackRunning) {
    btn.disabled = true;
    btn.textContent = '⟳ Stopping...';
    try {
      const r = await sendNative({ action: 'stop' });
      // Close any open FoveAI tabs
      chrome.tabs.query({ url: 'http://localhost:8080/*' }, (tabs) => {
        for (const tab of tabs) {
          chrome.tabs.remove(tab.id);
        }
      });
      _stackRunning = false;
      updateToggleButton();
      setTimeout(httpStatus, 2000);
      setTimeout(refreshLLMs, 3000);
    } catch (e) {
      console.error('Stop failed:', e);
    } finally {
      btn.disabled = false;
    }
    return;
  }

  // Stack is not running — start it
  btn.disabled = true;
  btn.textContent = '⟳ Starting...';
  progressDiv.style.display = 'block';
  progressBar.style.width = '0%';
  statusText.textContent = 'Initiating service start...';

  try {
    // Step 1: Start services via native host
    const r = await sendNative({ action: 'start' });
    if (r.status === 'error') {
      // Show diagnostics in the progress area
      let errorMsg = r.message || 'Failed to start services';
      if (r.diagnostics && r.diagnostics.length > 0) {
        errorMsg += '\n\nPre-flight check:\n' + r.diagnostics.join('\n');
      }
      throw new Error(errorMsg);
    }
    
    if (r.status === 'degraded') {
      // Some services started but not all — show warning but continue
      statusText.textContent = '⚠ ' + (r.message || 'Some services started, some failed');
      progressBar.style.width = '50%';
      progressBar.style.background = 'linear-gradient(90deg, #ffaa00, #ffcc00)';
    } else {
      statusText.textContent = 'Services starting, waiting for readiness...';
    }

    // Step 2: Poll for service readiness
    const allReady = await pollServices(progressBar, statusText);

    if (allReady) {
      // Step 3: Auto-redirect to frontend
      statusText.textContent = '✅ All systems go! Opening FoveAI...';
      _stackRunning = true;
      updateToggleButton();
      await new Promise(r => setTimeout(r, 1000)); // Brief pause so user sees success
      chrome.tabs.create({ url: FRONTEND_URL });
    } else {
      // Timeout — some services didn't start
      statusText.textContent = '⚠️ Some services did not start in time. Opening anyway...';
      progressBar.style.width = '100%';
      progressBar.style.background = 'linear-gradient(90deg, #ffaa00, #ff4444)';
      _stackRunning = true;
      updateToggleButton();
      await new Promise(r => setTimeout(r, 1500));
      chrome.tabs.create({ url: FRONTEND_URL });
    }
  } catch (e) {
    statusText.textContent = '✗ Error: ' + (e.message || 'Unknown error');
    progressBar.style.background = 'linear-gradient(90deg, #ff4444, #ff007f)';
  } finally {
    btn.disabled = false;
    // Hide progress after 5 seconds
    setTimeout(() => {
      progressDiv.style.display = 'none';
    }, 5000);
  }
};

document.getElementById('btn-stop').onclick = async () => {
  const msg = document.getElementById('msg-system');
  msg.textContent = 'Stopping...';
  try {
    const r = await sendNative({ action: 'stop' });
    msg.className = 'msg msg-ok';
    msg.textContent = r.message || '✓ Stopped';
    setTimeout(httpStatus, 2000);
    setTimeout(refreshLLMs, 3000);
  } catch (e) {
    msg.className = 'msg msg-err';
    msg.textContent = '✗ Native host not connected — see banner';
  }
};

document.getElementById('btn-restart').onclick = async () => {
  const msg = document.getElementById('msg-system');
  msg.textContent = 'Restarting...';
  try {
    const r = await sendNative({ action: 'restart' });
    msg.className = 'msg msg-ok';
    msg.textContent = r.message || '✓ Restarted';
    setTimeout(httpStatus, 3000);
    setTimeout(refreshLLMs, 5000);
  } catch (e) {
    msg.className = 'msg msg-err';
    msg.textContent = '✗ Native host not connected — see banner';
  }
};

document.getElementById('btn-refresh').onclick = httpStatus;
document.getElementById('btn-llm-detect').onclick = detectBackends;
document.getElementById('btn-llm-status').onclick = refreshLLMs;

document.getElementById('btn-build').onclick = async () => {
  const msg = document.getElementById('msg-dev');
  msg.textContent = 'Building...';
  try {
    const r = await sendNative({ action: 'build' });
    msg.className = r.status === 'ok' ? 'msg msg-ok' : 'msg msg-err';
    msg.textContent = r.status === 'ok' ? '✅ Build OK' : '❌ Build failed';
  } catch (e) {
    msg.className = 'msg msg-err';
    msg.textContent = '✗ Native host not connected';
  }
};

document.getElementById('btn-pull').onclick = async () => {
  const msg = document.getElementById('msg-dev');
  msg.textContent = 'Pulling...';
  try {
    const r = await sendNative({ action: 'git_pull' });
    msg.className = 'msg msg-ok';
    msg.textContent = r.output || r.message || '✓ Done';
  } catch (e) {
    msg.className = 'msg msg-err';
    msg.textContent = '✗ Native host not connected';
  }
};

// ── Open FoveAI & Quick Links ──

// Quick health check before opening — used by quick links
async function openLumaxIfReady() {
  try {
    const r = await fetch('http://127.0.0.1:8080/health', { signal: AbortSignal.timeout(2000) });
    if (r.ok) {
      chrome.tabs.create({ url: FRONTEND_URL });
      return;
    }
  } catch { }
  // If health check fails, show guidance
  const msg = document.getElementById('msg-system');
  msg.textContent = 'Services not ready — use the "Start FoveAI Stack" button above';
  msg.className = 'msg msg-err';
  setTimeout(() => { msg.className = ''; msg.textContent = ''; }, 4000);
}

document.getElementById('ql-webui').onclick = () => {
  chrome.tabs.create({ url: FRONTEND_URL });
};

document.getElementById('ql-webvm').onclick = () => {
  chrome.tabs.create({ url: FRONTEND_URL + '?tab=webvm' });
};

// ── TokenSlayer Stats ──

async function fetchTokenSlayerStats() {
  const dot = document.getElementById('ts-dot');
  const statusText = document.getElementById('ts-status-text');
  const msg = document.getElementById('msg-ts');

  try {
    // Route through Nexus Proxy on :8080 to avoid CORS errors from chrome-extension:// origin
    const r = await fetch('http://127.0.0.1:8080/api/proxy/8103/api/stats', { signal: AbortSignal.timeout(3000) });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();

    const totalFiles = data.totalFiles || 0;
    const totalOrig = data.totalOrig || 0;
    const totalSaved = data.totalSaved || 0;
    const saved = totalOrig - totalSaved;
    const pct = totalOrig > 0 ? Math.round((saved / totalOrig) * 100) : 0;
    const costPerM = 0.14;
    const costSaved = ((saved / 1_000_000) * costPerM).toFixed(4);

    document.getElementById('ts-files').textContent = totalFiles.toLocaleString();
    document.getElementById('ts-saved').textContent = saved.toLocaleString();
    document.getElementById('ts-pct').textContent = pct + '%';
    document.getElementById('ts-cost').textContent = '$' + costSaved;

    if (dot) { dot.className = 'dot alive'; }
    if (statusText) { statusText.textContent = 'Connected • Port 8103'; statusText.style.color = '#2ecc71'; }
    if (msg) { msg.textContent = ''; }
  } catch (e) {
    document.getElementById('ts-files').textContent = '—';
    document.getElementById('ts-saved').textContent = '—';
    document.getElementById('ts-pct').textContent = '—';
    document.getElementById('ts-cost').textContent = '—';
    if (dot) { dot.className = 'dot dead'; }
    if (statusText) { statusText.textContent = 'Offline (port 8103)'; statusText.style.color = '#ff4444'; }
    if (msg) { msg.textContent = 'Start TokenSlayer Dashboard to see stats'; msg.style.color = '#8b949e'; }
  }
}

document.getElementById('btn-ts-dashboard').onclick = () => {
  chrome.tabs.create({ url: 'http://localhost:8103/' });
};

document.getElementById('btn-ts-refresh').onclick = fetchTokenSlayerStats;

// ── Auto-check on open ──
checkConnection();
httpStatus();
fetchTokenSlayerStats();

// ── Cloud Egg Protocol (Vault) ──

async function loadVault() {
  chrome.storage.sync.get(['foveai_vault_password'], (res) => {
    if (res.foveai_vault_password) {
      document.getElementById('vault-password').value = res.foveai_vault_password;
      syncPasswordToBackend(res.foveai_vault_password);
    }
  });
}

function showVaultMsg(msg, isError) {
  const el = document.getElementById('msg-vault');
  el.textContent = msg;
  el.className = isError ? 'msg msg-err' : 'msg msg-ok';
  setTimeout(() => el.textContent = '', 3000);
}

async function syncPasswordToBackend(pwd) {
  try {
    const res = await sendNative({ action: 'set_vault_password', password: pwd });
    if (res.status === 'ok') {
      console.log('Password synced to native backend.');
    }
  } catch (e) {
    console.error('Failed to sync password to backend:', e);
  }
}

document.getElementById('btn-save-vault').addEventListener('click', async () => {
  const pwd = document.getElementById('vault-password').value.trim();
  if (!pwd) {
    showVaultMsg('Password cannot be empty', true);
    return;
  }

  chrome.storage.sync.set({ 'foveai_vault_password': pwd }, () => {
    showVaultMsg('Password Saved to Google Chrome Sync!', false);
    syncPasswordToBackend(pwd);
  });
});

document.getElementById('btn-download-egg').addEventListener('click', async () => {
  const pwd = document.getElementById('vault-password').value.trim();
  if (!pwd) {
    showVaultMsg('Please save a password first.', true);
    return;
  }

  showVaultMsg('Generating Encrypted Egg...', false);
  try {
    const res = await sendNative({ action: 'generate_dormant_egg', password: pwd });
    if (res.status === 'error') {
      showVaultMsg(res.error, true);
      return;
    }

    // The backend returns a base64 encoded zip
    if (res.egg_base64) {
      const url = "data:application/zip;base64," + res.egg_base64;
      chrome.downloads.download({
        url: url,
        filename: "Lumax_Dormant_Egg.zip",
        saveAs: true // This opens the save dialog so user can choose Google Drive
      });
      showVaultMsg('Egg Ready! Save to Google Drive.', false);
    } else {
      showVaultMsg('Failed to receive Egg payload.', true);
    }
  } catch (e) {
    showVaultMsg('Egg Generation Failed: ' + e.message, true);
  }
});

loadVault();
