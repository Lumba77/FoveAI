import fs from 'fs';
import os from 'os';
import path from 'path';
import { spawn, exec, execSync } from 'child_process';

// ─── Suppress EPIPE crashes — parent process may close stdout before children finish ───
process.stdout.on('error', (err) => {
    if (err.code === 'EPIPE') {
        // Parent closed stdout — silently ignore, child processes continue
        return;
    }
    // Re-throw non-EPIPE errors
    throw err;
});
process.stderr.on('error', (err) => {
    if (err.code === 'EPIPE') {
        return;
    }
    throw err;
});

const FoveAI_ROOT = process.cwd();

// ─── .env Loader — the single source of truth for model paths & config ───
function loadEnv() {
    const envPath = path.join(FoveAI_ROOT, '.env');
    const vars = {};
    if (!fs.existsSync(envPath)) return vars;
    try {
        const lines = fs.readFileSync(envPath, 'utf-8').split('\n');
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) continue;
            const idx = trimmed.indexOf('=');
            const key = trimmed.slice(0, idx).trim();
            let val = trimmed.slice(idx + 1).trim();
            // Strip inline comments: find first unquoted '#' and remove everything after it
            // But preserve '#' inside quoted strings
            let commentIdx = -1;
            let inQuote = false;
            let quoteChar = '';
            for (let ci = 0; ci < val.length; ci++) {
                const ch = val[ci];
                if (inQuote) {
                    if (ch === quoteChar) inQuote = false;
                } else if (ch === '"' || ch === "'") {
                    inQuote = true;
                    quoteChar = ch;
                } else if (ch === '#') {
                    commentIdx = ci;
                    break;
                }
            }
            if (commentIdx >= 0) {
                val = val.slice(0, commentIdx).trim();
            }
            // Strip surrounding quotes
            if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
                val = val.slice(1, -1);
            }
            vars[key] = val;
        }
    } catch (_) {}
    return vars;
}
const ENV = loadEnv();

console.log(`🦾 [SLEIPNIR LAUNCHER] Constructing Concordia parallel worker arrays...`);

const FLEET_PORTS = {
    "FOVEATED-MEMORY-8400": [8400],
    "MEMORY-DASHBOARD-8414": [8414],
    "XRLF-RUNTIME-8402": [8402, 8403],
    "SOVEREIGN-CORE-8404": [8404, 8000],
    "EARS-STT-8401": [8401, 8001],
    "MOUTH-KOKORO-8411": [8411, 8004],
    "STARDUST-NEURAL-8413": [8413, 8109],
    "MOTOR-CORTEX-8407": [8407, 8110],
    "CORE-SOLVER-8414": [8414, 8113],
    "XR-VESSEL-FRONTEND-5176": [5176]
};

/**
 * Smart zombie sweep — health-checks fleet ports BEFORE killing.
 * Preserves healthy services, kills only zombies squatting on ports.
 * Learned from archive/Start_FoveAI.ps1 (lines 143-179).
 * Returns object with cleaned and preserved port lists.
 */
function purgeZombies() {
    const cleaned = [];
    const preserved = [];
    const allPorts = [...new Set(Object.values(FLEET_PORTS).flat().filter(Boolean))];
    if (allPorts.length === 0) return { cleaned, preserved };

    console.log('   🧹 [ZOMBIE SWEEP] Scanning fleet ports...');

    for (const port of allPorts) {
        // 1. Health-check first — preserve healthy services
        let healthy = false;
        try {
            const healthCheck = execSync(
                `powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:${port}/health' -TimeoutSec 2 -UseBasicParsing).StatusCode } catch { 0 }"`,
                { encoding: 'utf8', timeout: 4000, stdio: ['ignore', 'pipe', 'ignore'] }
            ).trim();
            if (healthCheck === '200') {
                console.log(`   ✅ Port ${port} healthy — preserving`);
                healthy = true;
                preserved.push(port);
            }
        } catch (_) {
            // No response or timeout — port is either free or held by a zombie
        }

        if (healthy) continue;

        // 2. Find and kill zombie squatting on this port
        //    Matches BOTH LISTENING and TIME_WAIT states — TIME_WAIT prevents
        //    rebinding on Windows even though the process is dead, causing the
        //    server to fall back to port 8081 (which the extension doesn't know about).
        try {
            const out = execSync('netstat -ano -p tcp', { encoding: 'utf8', timeout: 5000 });
            const lines = out.split('\n');
            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed) continue;
                const state = trimmed.split(/\s+/).slice(-1)[0] || '';
                // Match LISTENING (active zombie) or TIME_WAIT (dead process, port still reserved)
                if (state !== 'LISTENING' && state !== 'TIME_WAIT') continue;
                const parts = trimmed.split(/\s+/);
                if (parts.length < 5) continue;
                const addr = parts[1];
                const pid = parts[4].trim();
                const portMatch = addr.match(/:(\d+)$/);
                if (!portMatch) continue;
                const foundPort = parseInt(portMatch[1], 10);
                if (foundPort === port) {
                    try {
                        execSync(`taskkill /pid ${pid} /f`, { stdio: 'ignore', timeout: 3000 });
                        cleaned.push(port);
                        console.log(`   💀 Killed zombie PID ${pid} on port ${port} (state: ${state})`);
                    } catch (_) {
                        // Process already gone
                    }
                    break; // Port cleared, move to next
                }
            }
        } catch (e) {
            console.error(`   ⚠️  [ZOMBIE SWEEP] Port ${port} scan failed: ${e.message}`);
        }
    }

    if (cleaned.length > 0) {
        console.log(`   ✨ Sweep complete. Cleared ${cleaned.length} port(s).`);
    } else {
        console.log('   ✨ All ports clear or healthy.');
    }
    return { cleaned, preserved };
}

class SwarmWorkerNode {
    constructor(name, command, args, options = {}) {
        this.name = name;
        this.command = command;
        this.args = args;
        // shell: true is NOT set by default — only nodes that need shell operators
        // (like AVATAR-FRONTEND-8080 with cmd.exe /c &&) should set it explicitly.
        // Setting it globally triggers DEP0190 security warning and causes EPIPE crashes.
        this.options = Object.assign({ cwd: FoveAI_ROOT }, options);
        
        // CRITICAL: Merge .env variables into child process environment.
        // The ENV object is loaded from .env at the top of this file, but Node.js
        // does NOT automatically pass these to child processes. Without this,
        // child processes (like soul_core.py) don't see any FoveAI_* env vars.
        // We merge ENV into the existing process.env so child processes inherit them.
        if (!this.options.env) {
            this.options.env = { ...process.env, ...ENV };
        } else {
            this.options.env = { ...process.env, ...ENV, ...this.options.env };
        }
        
        this.process = null;
        // Optional startup delay (ms) — used for GPU-bound services that need
        // other services (like Stardust with torch.cuda) to finish initializing first.
        this.startupDelay = options.startupDelay || 0;
    }

    async deploy(preservedPorts = []) {
        // Apply startup delay if configured — critical for GPU-bound services
        // like Unsloth/llama-server that need to wait for torch-using services
        // (Stardust, Soul Core) to finish their CUDA initialization first.
        // Without this delay, ggml_cuda and torch.cuda race for VRAM allocation,
        // causing llama-server to crash with OOM or CUDA driver errors.
        if (this.startupDelay > 0) {
            console.log(`   ⏳ [${this.name}] Delaying startup ${this.startupDelay}ms to avoid GPU VRAM race...`);
            await new Promise(resolve => setTimeout(resolve, this.startupDelay));
        }
        const myPorts = FLEET_PORTS[this.name] || [];
        const isPreserved = myPorts.some(p => preservedPorts.includes(p));

        if (isPreserved) {
            console.log(`   ⏭️ [FLEET SECTOR] Skipping active thread: ${this.name} (Service already running and healthy)`);
            return;
        }

        console.log(`   🚀 [FLEET SECTOR] Launching active thread: ${this.name}`);

        // DIAG: Log spawn details for UNSLOTH node
        if (this.name === 'UNSLOTH-GEMMA-8888') {
            console.log(`   🔍 [UNSLOTH DIAG] command: ${this.command}`);
            console.log(`   🔍 [UNSLOTH DIAG] args: ${JSON.stringify(this.args)}`);
            console.log(`   🔍 [UNSLOTH DIAG] cwd: ${this.options.cwd}`);
            console.log(`   🔍 [UNSLOTH DIAG] PATH prefix: ${this.options.env.PATH ? this.options.env.PATH.split(';')[0] : 'N/A'}`);
            // Check for CUDA-related env vars
            const cudaKeys = Object.keys(this.options.env).filter(k => k.toLowerCase().includes('cuda') || k.toLowerCase().includes('ggml'));
            if (cudaKeys.length > 0) {
                console.log(`   🔍 [UNSLOTH DIAG] CUDA/GGML env vars:`);
                cudaKeys.forEach(k => console.log(`        ${k}=${this.options.env[k]}`));
            }
        }

        // When shell: true is needed (e.g. cmd.exe /c with && operators),
        // use exec() instead of spawn() to avoid DEP0190 deprecation warning.
        // spawn() with shell: true and args array triggers:
        //   "Passing args to a child process with shell option true can lead to
        //    security vulnerabilities, as the arguments are not escaped"
        if (this.options.shell) {
            // Build the full command string: "cmd.exe /c npm install && npm run dev"
            const cmdStr = [this.command, ...this.args].join(' ');
            this.process = exec(cmdStr, {
                ...this.options,
                shell: true,
                maxBuffer: 10 * 1024 * 1024  // 10MB stdout buffer
            });
            // exec() already pipes stdout/stderr — skip the spawn handlers below
            this._isExec = true;
        } else {
            this.process = spawn(this.command, this.args, this.options);
        }

        // CRITICAL: Catch spawn errors (ENOENT, EACCES) so one missing binary
        // doesn't crash the entire launcher and kill all other nodes.
        if (this.process) {
            this.process.on('error', (err) => {
                console.error(`   ❌ [${this.name}] Spawn failed: ${err.code} — ${this.command}`);
                console.error(`   ⏭️ [${this.name}] Node skipped. Other nodes continue.`);
                this.process = null;
            });
        }

        // Only register spawn-style handlers for non-exec processes
        // exec() handles its own stdout/stderr piping internally
        if (!this._isExec && this.process.stdout) {
            // Capture stdout for diagnostic dump on close
            this._stdoutBuffer = '';
            this.process.stdout.on('data', (data) => {
                const lines = data.toString().split('\n');
                lines.forEach(line => {
                    if (line.trim()) {
                        this._stdoutBuffer += line.trim() + '\n';
                        try {
                            console.log(`[${this.name}] ${line.trim()}`);
                        } catch (e) {
                            // EPIPE: parent process closed stdout — suppress gracefully
                            if (e.code !== 'EPIPE') {
                                process.stderr.write(`[${this.name}] stdout error: ${e.message}\n`);
                            }
                        }
                    }
                });
            });
        }

        if (!this._isExec && this.process.stderr) {
            // Capture stderr for diagnostic dump on close
            this._stderrBuffer = '';
            this.process.stderr.on('data', (data) => {
                const raw = data.toString();
                const line = raw.trim();
                if (!line) return;
                this._stderrBuffer += raw;
                // Aggressively suppress routine noise — only show genuine errors
                const noise = [
                    // Python warnings
                    'DeprecationWarning', 'UserWarning', 'FutureWarning', 'PendingDeprecationWarning',
                    'SyntaxWarning', 'ResourceWarning', 'ImportWarning', 'BytesWarning', 'RuntimeWarning',
                    // HTTP status noise
                    '404', 'Not Found', '200 OK', '307 Temporary Redirect', '302 Found',
                    // Log levels (routine)
                    'INFO:', 'DEBUG:', 'WARNING:', 'INFO ', 'DEBUG ', 'WARNING ',
                    // Trial / experimental
                    'trial', 'Trial', 'TRIAL',
                    // Uvicorn startup chatter
                    'uvicorn.error', 'uvicorn.access',
                    'Application startup complete', 'Uvicorn running on',
                    'Press CTRL+C', 'Waiting for application',
                    'Started server process', 'Started reloader process',
                    'StatReload', 'will watch for changes', 'reload',
                    'startup', 'shutdown',
                    // Connection noise
                    'connection refused', 'Connection refused', 'connect ECONNREFUSED',
                    'ECONNRESET', 'EPIPE',
                    // Cloudflared routine
                    'INF Starting', 'INF Version', 'INF GOOS', 'INF Settings',
                    'INF Initial protocol', 'INF ICMP proxy', 'INF Generated Connector',
                    'INF cloudflared will not', 'INF Registered tunnel',
                    'INF Retrying connection', 'WRN Connection terminated',
                    'WRN Unable to establish', 'ERR failed to serve',
                    'does not support loading the system root',
                    'Starting metrics server',
                    // httpx / requests
                    'httpx - INFO', 'HTTP Request:',
                    // python-dotenv parse warnings
                    'python-dotenv could not parse',
                    // heartbeat routine
                    'foveai.heartbeat - INFO',
                    'Heartbeat grounded safely',
                    // Loading progress bars
                    'Loading weights:', 'it/s]',
                    // Kokoro routine
                    'Kokoro TTS on', 'Kokoro pipeline created',
                    'Kokoro: warming up', 'Kokoro: warm-up complete',
                    // compagent routine
                    'uvicorn log=warning',
                    // Vite routine
                    'Forced re-optimization',
                    // Node deprecation
                    'DEP0190',
                    // Llama-server routine logging — only suppress known INFO-level patterns
                    // Keep ERROR/FATAL lines visible for diagnostics
                    // NOTE: 'fitting params to device memory' is deliberately NOT suppressed
                    // because it shows VRAM allocation status which is critical for diagnosing
                    // OOM crashes during model loading.
                    'print_timing', 'device_info', 'system_info',
                    'common_init_result', 'control-looking token', 'special_eog_ids',
                    // MCP server routine logs
                    '[MCP] Loaded', '[MCP]',
                ];
                const isNoise = noise.some(pattern => line.includes(pattern));
                if (!isNoise) {
                    console.error(`⚠️ [${this.name} ALERT] ${line}`);
                }
            });
        }

        this.process.on('close', (code) => {
            console.log(`🛑 [${this.name}] Disconnected from master hive. Exit code: ${code}`);
            // Dump captured stderr on non-zero exit for diagnostics
            if (code !== 0) {
                if (this._stderrBuffer) {
                    console.error(`📋 [${this.name}] Last stderr output:\n${this._stderrBuffer}`);
                }
                if (this._stdoutBuffer) {
                    console.error(`📋 [${this.name}] Last stdout output:\n${this._stdoutBuffer}`);
                }
                // Also dump raw signal info
                console.error(`📋 [${this.name}] Process killed: ${this.process ? this.process.killed : 'N/A'}, signal: ${code}`);
            }
        });
    }

    kill() {
        if (this.process) {
            console.log(`   ⏏️  [FLEET SECTOR] Sending kill signal to: ${this.name}`);
            try {
                // Windows-native tree kill to ensure child python processes die cleanly
                execSync(`taskkill /pid ${this.process.pid} /t /f`, { stdio: 'ignore' });
            } catch (e) {
                // Fallback
                this.process.kill('SIGINT');
            }
            this.process = null;
        }
    }
}

// Map the physical locations of your existing files straight to the grid
const SwarmFleet = [

    // Node 2: Your existing MCP Server Integration
    new SwarmWorkerNode(
        "FoveAI-MCP-SERVER",
        path.join(FoveAI_ROOT, ENV.FoveAI_VENV_PATH || ".venv", "Scripts", "python.exe"),
        ["Backend/Memory/foveai_mcp_server.py"]
    ),

    // Node 3: Lumax Solver — Local Saviour HTTP daemon on port 8113
    // Runs in --serve mode so other services can POST errors to it
    new SwarmWorkerNode(
        "FoveAI-CORE-SOLVER",
        "node",
        ["Tools/foveai-solver/foveai-solver.js", "--serve"],
        {
            env: {
                ...process.env,
                FoveAI_LAUNCHER: "1"
            }
        }
    ),

        // Node 3.5: Smart Repo Librarian — DISARMED per user request
        // The librarian_daemon.py is kept for reference but will not be spawned.
        // It has a hard safety guard (DISARMED = True) preventing file deletion.

    // Node 4: Stardust Neural Coordinates Vector Space (Port 8109)
    new SwarmWorkerNode(
        "STARDUST-NEURAL-8109",
        path.join(FoveAI_ROOT, ENV.FoveAI_VENV_PATH || ".venv", "Scripts", "python.exe"),
        ["-m", "uvicorn", "Backend.Memory.stardust_encoder:app", "--port", "8109", "--host", "127.0.0.1"]
    ),

    // Node 4.5: Foveated Memory Proxy (Port 8400)
    new SwarmWorkerNode(
        "FOVEATED-MEMORY-8400",
        "node",
        ["foveated-memory/server.js"]
    ),

    // Node 4.8: XRLF Runtime — the new Soul (Port 8402 HTTP + 8403 WS IPC)
    // run_xrlf.py starts llama-server with an XRLF model, the OpenAI-compatible
    // API on :8402, and the WebSocket IPC on :8403. Multimodal WS is on :8300.
    // Model is read from .env XRLF_MODEL_LOCAL_ID (falls back to xrlf_config.yaml).
    ...(() => {
        let modelId = ENV.XRLF_MODEL_LOCAL_ID || '';
        const args = ["run_xrlf.py", "--port", "8402", "--ws-port", "8403"];
        if (modelId) {
            // Auto-append .xrlf if missing (tray app settings UI strips it)
            if (!modelId.endsWith('.xrlf') && !modelId.includes('.xrlf')) {
                modelId = modelId + '.xrlf';
            }
            // Resolve to xrl_encoded/<model> if it doesn't contain a path separator
            const modelPath = modelId.includes('/') || modelId.includes('\\\\')
                ? modelId
                : `xrl_encoded/${modelId}`;
            args.splice(1, 0, "--model", modelPath);
        }
        return [new SwarmWorkerNode(
            "XRLF-RUNTIME-8402",
            path.join(FoveAI_ROOT, ENV.FoveAI_VENV_PATH || ".venv", "Scripts", "python.exe"),
            args
        )];
    })(),

    // Node 4.6: Situational Awareness Daemon (Jen's News Radio)
    new SwarmWorkerNode(
        "SITUATIONAL-AWARENESS-DAEMON",
        path.join(FoveAI_ROOT, ENV.FoveAI_VENV_PATH || ".venv", "Scripts", "python.exe"),
        ["Backend/Cognition/SituationalAwarenessDaemon.py"]
    ),

    // Node 4.7: Subconscious & Dream Engine (Jen's Circadian Dream Cycles)
    new SwarmWorkerNode(
        "SUBCONSCIOUS-DREAM-ENGINE",
        path.join(FoveAI_ROOT, ENV.FoveAI_VENV_PATH || ".venv", "Scripts", "python.exe"),
        ["Backend/Cognition/SubconsciousDreamEngine.py"]
    ),

    // Node 9: Subconscious Motor Cortex / State Planner Daemon (Port 8110)
    new SwarmWorkerNode(
        "MOTOR-CORTEX-8110",
        path.join(FoveAI_ROOT, ENV.FoveAI_VENV_PATH || ".venv", "Scripts", "python.exe"),
        ["-m", "uvicorn", "Backend.Cognition.motor_daemon:app", "--port", "8110", "--host", "127.0.0.1"]
    ),

    // Node 10: Ears (Speech-to-Text) — LEGACY, phased out
    // XRLF runtime on :8402 handles STT natively (Gemma) or via Whisper hook (Qwen).
    // Only spawn if XRLF_LEGACY_SERVICES=true in .env.
    ...((ENV.XRLF_LEGACY_SERVICES || '').toLowerCase() === 'true' ? [
    new SwarmWorkerNode(
        "EARS-STT-8001",
        path.join(FoveAI_ROOT, ENV.FoveAI_VENV_PATH || ".venv", "Scripts", "python.exe"),
        ["-m", "uvicorn", "Frontend.Physical_Interface.body_interface:app", "--port", "8001", "--host", "127.0.0.1"],
        {
            env: {
                ...process.env,
                MODE: "EARS"
            }
        }
    ),
    ] : []),

    // Node 11: Mouth (Kokoro TTS) — LEGACY, phased out
    // XRLF runtime on :8402 handles TTS via Kokoro hook internally.
    // Only spawn if XRLF_LEGACY_SERVICES=true in .env.
    ...((ENV.XRLF_LEGACY_SERVICES || '').toLowerCase() === 'true' ? [
    new SwarmWorkerNode(
        "MOUTH-KOKORO-8004",
        path.join(FoveAI_ROOT, ENV.FoveAI_VENV_PATH || ".venv", "Scripts", "python.exe"),
        ["Frontend/Mouth/foveai_mouth_kokoro_server.py", "--port", "8004"]
    ),
    ] : []),

    // Node 11: Sovereign Core (old Soul) — LEGACY, phased out
    // The XRLF runtime on :8402 (run_xrlf.py) is the new Soul.
    // Soul Core on :8000 is only needed for the old agent loop.
    // Only spawn if XRLF_LEGACY_SERVICES=true in .env.
    ...((ENV.XRLF_LEGACY_SERVICES || '').toLowerCase() === 'true' ? [
    new SwarmWorkerNode(
        "SOVEREIGN-CORE-8000",
        path.join(FoveAI_ROOT, ENV.FoveAI_VENV_PATH || ".venv", "Scripts", "python.exe"),
        ["Backend/Cognition/soul_core.py"]
    ),
    ] : []),

    // Node 12: Frontend Selector (Multigate Default Port 5177 vs XR Vessel vs 3D Avatar)
    ...(() => {
        const uiMode = (ENV.FoveAI_FRONTEND_UI || '').trim().toLowerCase();
        if (uiMode === '3d_avatar') {
            return [
                // 3D Avatar Chatbot Node (Port 8080)
                new SwarmWorkerNode(
                    "AVATAR-FRONTEND-8080",
                    "cmd.exe",
                    ["/c", "npm install --no-audit --no-fund 2>&1 && npm run dev"],
                    { cwd: path.join(FoveAI_ROOT, "Frontend", "3D_Avatar_Chatbot"), shell: true }
                )
            ];
        } else if (uiMode === 'xr_vessel') {
            return [
                // XR Vessel Frontend Node (Port 5176)
                new SwarmWorkerNode(
                    "XR-VESSEL-FRONTEND-5176",
                    "cmd.exe",
                    ["/c", "npm install --no-audit --no-fund 2>&1 && npm run dev"],
                    { cwd: path.join(FoveAI_ROOT, "Frontend", "XR_Vessel"), shell: true, env: { ...process.env, VITE_PORT: "5176" } }
                ),
                // XR Vessel API Proxy Node (Port 8101)
                new SwarmWorkerNode(
                    "XR-VESSEL-API-8101",
                    path.join(FoveAI_ROOT, ENV.FoveAI_VENV_PATH || ".venv", "Scripts", "python.exe"),
                    ["Frontend/XR_Vessel/xr_app.py"],
                    {
                        env: { ...process.env, WEBUI_PORT: "8101" }
                    }
                )
            ];
        } else {
            // Default: Multigate Spatial UI on Port 5177
            return [
                new SwarmWorkerNode(
                    "MULTIGATE-FRONTEND-5177",
                    "cmd.exe",
                    ["/c", "npm install --no-audit --no-fund 2>&1 && npm run dev"],
                    { cwd: path.join(FoveAI_ROOT, "Frontend", "multigate"), shell: true }
                )
            ];
        }
    })(),

    // Node 14: Cloudflare Tunnel — exposes Vite at https://foveai.1um6a.se
    // Try FoveAI-local cloudflared first, then system-installed path
    new SwarmWorkerNode(
        "CLOUDFLARE-TUNNEL",
        (() => {
            const local = path.join(FoveAI_ROOT, "cloudflared.exe");
            if (fs.existsSync(local)) return local;
            const system = "C:\\Program Files (x86)\\cloudflared\\cloudflared.exe";
            if (fs.existsSync(system)) return system;
            return local; // fall back to local path (will error but won't crash other nodes)
        })(),
        ["tunnel", "--config", "config.yml", "run"]
    ),



    // Node 16: Dead Sure AI Failsafe Watchdog Service
    // NOTE: Managed by Tools/start-solver-service.ps1 as a Windows Scheduled Task.
    // Do NOT start here — would create a duplicate instance.
    // new SwarmWorkerNode(
    //     "DEADSURE-FAILSAFE-8112",
    //     "python",
    //     ["Tools/deadsure_watchdog.py"]
    // ),

    // Node 17: Unsloth Local Model — driven entirely by .env (source of truth)
    // Model path: FoveAI_MODEL_LOCAL_PATH, port: derived from FoveAI_LOCAL_BASE_URL
    // GPU layers: FoveAI_GGUF_N_GPU_LAYERS, context: FoveAI_LOCAL_N_CTX
    // Only starts if FoveAI_CHAT_PROVIDER=unsloth and model path exists
    (() => {
        const provider = (ENV.FoveAI_CHAT_PROVIDER || '').toLowerCase();
        const modelPath = ENV.FoveAI_MODEL_LOCAL_PATH || '';
        const baseUrl = ENV.FoveAI_LOCAL_BASE_URL || 'http://127.0.0.1:8888/v1';
        const port = (baseUrl.match(/:(\d+)\//) || [null, '8888'])[1];
        const ctxSize = ENV.FoveAI_LOCAL_N_CTX || '4096';
        const gpuLayers = ENV.FoveAI_GGUF_N_GPU_LAYERS || '36';
        // Resolve Unsloth root — UNSLOTH_STUDIO_HOME points to hub, not .unsloth root
        const unslothRoot = path.join(os.homedir(), '.unsloth');
        const unslothExe = path.join(unslothRoot, 'llama.cpp', 'build', 'bin', 'Release', 'llama-server.exe');

        if (provider !== 'unsloth') {
            console.log(`   ℹ️  [UNSLOTH] Provider is '${ENV.FoveAI_CHAT_PROVIDER}' — skipping Unsloth node.`);
            return null;
        }
        if (!modelPath || !fs.existsSync(modelPath)) {
            console.warn(`   ⚠️  [UNSLOTH] Model not found at FoveAI_MODEL_LOCAL_PATH: ${modelPath}`);
            return null;
        }
        if (!fs.existsSync(unslothExe)) {
            console.warn(`   ⚠️  [UNSLOTH] llama-server.exe not found: ${unslothExe}`);
            return null;
        }

        console.log(`   🧠 [UNSLOTH] ${path.basename(modelPath)} → :${port} (ctx=${ctxSize}, gpu=${gpuLayers})`);
        const unslothDir = path.dirname(unslothExe);
        const unslothArgs = ["-m", modelPath, "-c", ctxSize, "--port", port, "-ngl", gpuLayers, "-t", "4", "--flash-attn", "on"];
        return new SwarmWorkerNode(
            "UNSLOTH-GEMMA-8888",
            unslothExe,
            unslothArgs,
            {
                // CRITICAL: Set cwd to llama directory so DLLs (llama-server-impl.dll, ggml-cuda.dll) load correctly
                cwd: unslothDir,
                // Delay startup by 15 seconds to let torch-using services (Stardust, Soul Core)
                // finish their CUDA initialization first. Without this delay, ggml_cuda and
                // torch.cuda race for VRAM allocation, causing llama-server to crash.
                startupDelay: 15000,
                env: {
                    // CRITICAL: Do NOT spread process.env here — the SwarmWorkerNode constructor
                    // does { ...process.env, ...ENV, ...this.options.env }, so spreading process.env
                    // again would UNDO the ENV override. Only provide the PATH override.
                    PATH: unslothDir + ';' + (process.env.PATH || ''),
                    // CRITICAL: Prevent ggml_cuda from pinning shared memory, which conflicts with
                    // torch.cuda's memory allocator. When sleipnir launches all services simultaneously,
                    // Stardust (stardust_encoder.py) loads a sentence-transformer model onto CUDA first,
                    // fragmenting VRAM. Without this flag, ggml_cuda_init tries to pin a large contiguous
                    // block and fails because torch has already pinned memory. This flag tells ggml to
                    // use regular cudaMalloc instead of cudaHostAlloc, avoiding the conflict.
                    // See: https://github.com/ggml-org/llama.cpp/issues/5666
                    GGML_CUDA_NO_PIN_SHARED: '1'
                }
            }
        );
    })(),

    // Node 18: LM Studio Server
    (() => {
        const provider = (ENV.FoveAI_CHAT_PROVIDER || '').toLowerCase();
        if (provider !== 'lm_studio') return null;

        let statusOutput = '';
        try {
            statusOutput = execSync('lms status', { encoding: 'utf8', timeout: 5000 });
        } catch (e) {
            console.warn(`   ⚠️  [LM STUDIO] Could not check lms status: ${e.message}`);
        }

        if (statusOutput.includes('ON')) {
            console.log(`   ℹ️  [LM STUDIO] Server is already ON (likely started via GUI). Sleipnir will attach but not manage its lifecycle.`);
            return null;
        }

        console.log(`   🧠 [LM STUDIO] Server is OFF. Sleipnir will launch and manage it as a daemon.`);
        return new SwarmWorkerNode(
            "LM-STUDIO-SERVER",
            "lms",
            ["server", "start"],
            { shell: true }
        );
    })(),
];

// Ignite the swarm simultaneously
console.log("\n🛸 The Queen pulses the grid. The armada takes to the sky...\n");
const initialPurge = purgeZombies();
// Deploy all nodes in parallel — async deploy() handles staggered delays internally
const deploymentPromises = SwarmFleet.filter(n => n !== null).map(node => node.deploy(initialPurge.preserved));

Promise.all(deploymentPromises).then(() => {
    console.log("\n🛸 [FLEET COM] Armada fully airborne and reporting green.\n");
    
    // Auto-preload LM Studio model to prevent frontend timeout on first chat
    const provider = (ENV.FoveAI_CHAT_PROVIDER || '').toLowerCase();
    const modelId = ENV.FoveAI_MODEL_LOCAL_ID;
    if (provider === 'lm_studio' && modelId) {
        // Check if model is already loaded to prevent duplicate instances
        exec('lms ps', (err, stdout) => {
            if (!err && stdout && stdout.includes(modelId)) {
                console.log(`\n🧠 [LM STUDIO] Model '${modelId}' is already loaded. Skipping preload.`);
                return;
            }
            console.log(`\n🧠 [LM STUDIO] Pre-loading model '${modelId}' into VRAM...`);
            exec(`lms load ${modelId} --yes`, (error, stdout, stderr) => {
                if (error) {
                    console.warn(`⚠️ [LM STUDIO] Preload failed: ${error.message}`);
                } else {
                    console.log(`✅ [LM STUDIO] Model '${modelId}' successfully pre-loaded into VRAM!`);
                }
            });
        });
    }
});

// --- XRLF Runtime Auto-Restart Watchdog ---
// Periodically health-checks XRLF-RUNTIME-8402 (port 8402) and auto-restarts if dead.
// This replaces the old Soul Core watchdog (port 8000) — the XRLF runtime IS the new Soul.
const SOUL_CORE_NAME = "XRLF-RUNTIME-8402";
const SOUL_CORE_PORT = 8402;
let soulCoreWatchdogInterval = null;

function startSoulCoreWatchdog() {
    if (soulCoreWatchdogInterval) return; // Already running

    console.log(`👁️  [SLEIPNIR LAUNCHER] XRLF Runtime watchdog active. Monitoring :${SOUL_CORE_PORT} every 10s.`);

    soulCoreWatchdogInterval = setInterval(() => {
        // Find the soul core node in the fleet
        const soulNode = SwarmFleet.find(n => n && n.name === SOUL_CORE_NAME);
        if (!soulNode) return;

        // Health-check via HTTP
        let healthy = false;
        try {
            const healthCheck = execSync(
                `powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:${SOUL_CORE_PORT}/health' -TimeoutSec 3 -UseBasicParsing).StatusCode } catch { 0 }"`,
                { encoding: 'utf8', timeout: 5000, stdio: ['ignore', 'pipe', 'ignore'] }
            ).trim();
            if (healthCheck === '200') {
                healthy = true;
            }
        } catch (_) {
            // No response — soul core is down
        }

        if (healthy) return; // All good

        // Soul Core is down — check if process is still tracked
        const processAlive = soulNode.process && !soulNode.process.killed;
        if (processAlive) {
            // Process object exists but health check failed — might be starting up
            // Wait for next cycle before redeploying
            return;
        }

        console.log(`   ⚠️  [SLEIPNIR LAUNCHER] XRLF Runtime (port ${SOUL_CORE_PORT}) is DOWN. Auto-restarting...`);

        // Kill any zombie on the port first
        try {
            const out = execSync('netstat -ano -p tcp', { encoding: 'utf8', timeout: 5000 });
            const lines = out.split('\n');
            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed) continue;
                const state = trimmed.split(/\s+/).slice(-1)[0] || '';
                if (state !== 'LISTENING' && state !== 'TIME_WAIT') continue;
                const parts = trimmed.split(/\s+/);
                if (parts.length < 5) continue;
                const addr = parts[1];
                const pid = parts[4].trim();
                const portMatch = addr.match(/:(\d+)$/);
                if (!portMatch) continue;
                const foundPort = parseInt(portMatch[1], 10);
                if (foundPort === SOUL_CORE_PORT) {
                    try {
                        execSync(`taskkill /pid ${pid} /f`, { stdio: 'ignore', timeout: 3000 });
                        console.log(`   💀 Killed zombie PID ${pid} on port ${SOUL_CORE_PORT}`);
                    } catch (_) {}
                    break;
                }
            }
        } catch (_) {}

        // Small delay to let port release
        const waitMs = 2000;
        setTimeout(async () => {
            console.log(`   🚀 [SLEIPNIR LAUNCHER] Redeploying ${SOUL_CORE_NAME}...`);
            await soulNode.deploy([]);
        }, waitMs);
    }, 10000); // Check every 10 seconds
}

// Start the watchdog after initial deployment
startSoulCoreWatchdog();

// --- .env Source of Truth Watchdog ---
let restartTimeout = null;
let isRedeploying = false;  // Guard against double-deployment
const envPath = path.join(FoveAI_ROOT, '.env');

if (fs.existsSync(envPath)) {
    console.log(`👁️  [SLEIPNIR LAUNCHER] Watchdog active. Monitoring .env for architectural shifts.`);
    fs.watch(envPath, (eventType, filename) => {
        if (filename && eventType === 'change') {
            // Debounce to prevent multiple rapid triggers on a single file save
            if (restartTimeout) clearTimeout(restartTimeout);
            restartTimeout = setTimeout(() => {
                // GUARD: If already redeploying, skip — prevents double fleet
                if (isRedeploying) {
                    console.log("   ⚠️  [WATCHDOG] Redeploy already in progress — skipping duplicate trigger.");
                    return;
                }
                isRedeploying = true;

                console.log("\n♻️ [.env CHANGED] The source of truth has shifted. Restarting Concordia Swarm to apply new realities...\n");

                // Kill all active nodes
                SwarmFleet.filter(Boolean).forEach(node => node.kill());

                // Wait for ports to clear, then redeploy
                setTimeout(() => {
                    // Aggressive port cleanup before redeploy
                    const purgeResult = purgeZombies();
                    if (purgeResult.cleaned.length > 0) {
                        console.log(`   🧹 [PORT CLEANUP] Purged ${purgeResult.cleaned.length} lingering port(s): ${purgeResult.cleaned.join(', ')}`);
                        // Extra breath for Windows to release sockets
                        setTimeout(async () => {
                            console.log("\n🛸 The Queen pulses the grid. Redeploying armada...\n");
                            await Promise.all(SwarmFleet.filter(Boolean).map(node => node.deploy(purgeResult.preserved)));
                            isRedeploying = false;
                        }, 2000);
                    } else {
                        console.log("\n🛸 The Queen pulses the grid. Redeploying armada...\n");
                        Promise.all(SwarmFleet.filter(Boolean).map(node => node.deploy(purgeResult.preserved)))
                            .then(() => { isRedeploying = false; })
                            .catch(err => console.error(`⚠️ [FLEET REDEPLOY] Error: ${err.message}`));
                    }
                }, 3000);
            }, 1000);
        }
    });
}

// Catch emergency breaks and run defensive state preservation
process.on('SIGINT', () => {
    console.log("\n🛑 [SHUTDOWN INTERCEPTED] Grounding Sleipnir safely. Securing linear timeline states...");

    // Ensure all children are killed when the main process shuts down
    SwarmFleet.filter(Boolean).forEach(node => node.kill());

    try {
        if (fs.existsSync(path.join(FoveAI_ROOT, "Scripts/vibe_checkpoint.ps1"))) {
            execSync(`powershell -NoProfile -Command ".\\Scripts\\vibe_checkpoint.ps1 -Action commit -Message 'Sleipnir Engine Soft Landing Auto-Commit'"`, { stdio: 'inherit' });
        }
    } catch (e) {
        console.log("🌱 Timeline state already anchored.");
    }
    process.exit(0);
});


