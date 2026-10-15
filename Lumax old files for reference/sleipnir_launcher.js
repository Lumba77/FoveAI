import fs from 'fs';
import os from 'os';
import path from 'path';
import http from 'http';
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

const LUMAX_ROOT = process.cwd();
const FOVEAI_ROOT = fs.existsSync(path.join(LUMAX_ROOT, 'FoveAI')) ? path.join(LUMAX_ROOT, 'FoveAI') : LUMAX_ROOT;
const FOVEAI_VENV = path.join(FOVEAI_ROOT, '.venv', 'Scripts', 'python.exe');
const PYTHON_BIN = fs.existsSync(FOVEAI_VENV) ? FOVEAI_VENV : path.join(LUMAX_ROOT, '.venv', 'Scripts', 'python.exe');

// ─── .env Loader — the single source of truth for model paths & config ───
function loadEnv() {
    const envPath = path.join(LUMAX_ROOT, '.env');
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
    "LUMAX-MCP-SERVER": [],
    "LUMAX-CORE-SOLVER": [],
    "STARDUST-NEURAL-8109": [8109],
    "MOTOR-CORTEX-8110": [8110],
    "EARS-STT-8001": [8001],
    "FOVEATED-MEMORY-8400": [8400],
    "MOUTH-KOKORO-8004": [8004],
    "SPATIAL-MACHINE-PROXY-8403": [8403],
    "XR-VESSEL-FRONTEND-5176": [5176],
    "CLOUDFLARE-TUNNEL": [],
    "DEADSURE-FAILSAFE-8112": [8112],
    "UNSLOTH-GEMMA-8888": [8888]
};

/**
 * Smart zombie sweep — health-checks fleet ports BEFORE killing.
 * Preserves healthy services, kills only zombies squatting on ports.
 * Learned from archive/Start_LUMAX.ps1 (lines 143-179).
 * Returns object with cleaned and preserved port lists.
 */
function checkUrlHealth(url) {
    return new Promise((resolve) => {
        const req = http.get(url, { timeout: 2000 }, (res) => {
            resolve(res.statusCode === 200);
        });
        req.on('error', () => {
            resolve(false);
        });
        req.on('timeout', () => {
            req.destroy();
            resolve(false);
        });
    });
}

async function purgeZombies() {
    const cleaned = [];
    const preserved = [];
    const allPorts = [...new Set(Object.values(FLEET_PORTS).flat().filter(Boolean))];
    if (allPorts.length === 0) return { cleaned, preserved };

    console.log('   🧹 [ZOMBIE SWEEP] Scanning fleet ports...');

    for (const port of allPorts) {
        // 1. Health-check first — preserve healthy services
        const healthy = await checkUrlHealth(`http://127.0.0.1:${port}/health`);
        if (healthy) {
            console.log(`   ✅ Port ${port} healthy — preserving`);
            preserved.push(port);
            continue;
        }

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
        this.options = Object.assign({ cwd: LUMAX_ROOT }, options);
        
        // CRITICAL: Merge .env variables into child process environment.
        // The ENV object is loaded from .env at the top of this file, but Node.js
        // does NOT automatically pass these to child processes. Without this,
        // child processes (like soul_core.py) don't see any LUMAX_* env vars.
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
                    'lumax.heartbeat - INFO',
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

    // Node 1: Foveated Memory Proxy & Dashboard (Ports 8414 & 8414)
    new SwarmWorkerNode(
        "FOVEATED-MEMORY-8400",
        "node",
        ["server.js"],
        { cwd: path.join(FOVEAI_ROOT, "foveated-memory") }
    ),

    // Node 2: XRLF Active Inference Runtime (Port 8402)
    new SwarmWorkerNode(
        "XRLF-RUNTIME-8402",
        PYTHON_BIN,
        [
            "run_xrlf.py",
            "--model", ENV.XRLF_MODEL_LOCAL_ID || "foveai-pfoveai-omni-router-v2.xrlf",
            "--port", "8402",
            "--ws-port", "8403"
        ],
        {
            cwd: FOVEAI_ROOT,
            startupDelay: 2000
        }
    ),

    // Node 3: Sovereign Core Cognition & Soul (Port 8410)
    new SwarmWorkerNode(
        "SOVEREIGN-CORE-8410",
        PYTHON_BIN,
        ["Backend/Cognition/compagent.py"],
        { cwd: FOVEAI_ROOT, startupDelay: 3000 }
    ),

    // Node 4: Emotional Kokoro Mouth Service (Port 8004)
    new SwarmWorkerNode(
        "MOUTH-KOKORO-8004",
        PYTHON_BIN,
        ["Frontend/Mouth/foveai_mouth_kokoro_server.py"],
        { cwd: FOVEAI_ROOT, startupDelay: 3000 }
    ),

    // Node 5: Spatial Machine Native Proxy (Port 8403) — Quest 3 IPC WebSocket
    new SwarmWorkerNode(
        "SPATIAL-MACHINE-PROXY-8403",
        PYTHON_BIN,
        ["-m", "app.main"],
        { cwd: path.join(FOVEAI_ROOT, "Backend"), startupDelay: 2000 }
    ),

    // Node 6: Frontend Selector (Port 5177 Multigate Spatial UI Default / Port 8080 Avatar)
    ...(() => {
        const uiMode = (ENV.LUMAX_FRONTEND_UI || ENV.XRLF_FRONTEND_UI_PRESET || '').trim().toLowerCase();
        if (uiMode === '3d_avatar') {
            return [
                new SwarmWorkerNode(
                    "AVATAR-FRONTEND-8080",
                    "cmd.exe",
                    ["/c", "npm run dev"],
                    { cwd: path.join(FOVEAI_ROOT, "Frontend", "3D_Avatar_Chatbot"), shell: true }
                )
            ];
        } else if (uiMode === 'xr_vessel') {
            return [
                new SwarmWorkerNode(
                    "XR-VESSEL-FRONTEND-5176",
                    "cmd.exe",
                    ["/c", "npm run dev"],
                    { cwd: path.join(FOVEAI_ROOT, "Frontend", "XR_Vessel"), shell: true, env: { ...process.env, VITE_PORT: "5176" } }
                )
            ];
        } else {
            // Default: Multigate Spatial UI on Port 5177
            return [
                new SwarmWorkerNode(
                    "MULTIGATE-FRONTEND-5177",
                    "cmd.exe",
                    ["/c", "npm run dev"],
                    { cwd: path.join(FOVEAI_ROOT, "Frontend", "multigate"), shell: true }
                )
            ];
        }
    })(),

    // ── Opt-in auxiliary services (disabled by default to prevent bloat & keep stack lean) ──
    ...(ENV.FOVEAI_ENABLE_TUNNEL === 'true' && fs.existsSync(path.join(LUMAX_ROOT, "cloudflared.exe")) ? [
        new SwarmWorkerNode(
            "CLOUDFLARE-TUNNEL",
            path.join(LUMAX_ROOT, "cloudflared.exe"),
            ["tunnel", "--config", "config.yml", "run"]
        )
    ] : []),

    ...(ENV.FOVEAI_ENABLE_STARDUST === 'true' ? [
        new SwarmWorkerNode(
            "STARDUST-NEURAL-8109",
            PYTHON_BIN,
            ["-m", "uvicorn", "Backend.Memory.stardust_encoder:app", "--port", "8109", "--host", "127.0.0.1"],
            { cwd: FOVEAI_ROOT }
        )
    ] : [])
];

// Ignite the swarm simultaneously
(async () => {
    console.log("\n🛸 The Queen pulses the grid. The armada takes to the sky...\n");
    const initialPurge = await purgeZombies();
    // Deploy all nodes in parallel — async deploy() handles staggered delays internally
    const deploymentPromises = SwarmFleet.filter(n => n !== null).map(node => node.deploy(initialPurge.preserved));

    await Promise.all(deploymentPromises);
    console.log("\n🛸 [FLEET COM] Armada fully airborne and reporting green.\n");
    
    // Auto-preload LM Studio model to prevent frontend timeout on first chat
    const provider = (ENV.LUMAX_CHAT_PROVIDER || '').toLowerCase();
    const modelId = ENV.LUMAX_MODEL_LOCAL_ID;
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

    // Start the watchdog after initial deployment
    startSoulCoreWatchdog();
})();

// --- Spatial Machine Proxy Auto-Restart Watchdog ---
// Periodically health-checks the 8400 proxy and auto-restarts if dead.
const SOUL_CORE_NAME = "SPATIAL-MACHINE-PROXY-8400";
const SOUL_CORE_PORT = 8400;
let soulCoreWatchdogInterval = null;

function startSoulCoreWatchdog() {
    if (soulCoreWatchdogInterval) return; // Already running

    console.log(`👁️  [SLEIPNIR LAUNCHER] Soul Core watchdog active. Monitoring :${SOUL_CORE_PORT} every 10s.`);

    soulCoreWatchdogInterval = setInterval(async () => {
        // Find the soul core node in the fleet
        const soulNode = SwarmFleet.find(n => n && n.name === SOUL_CORE_NAME);
        if (!soulNode) return;

        // Health-check via HTTP
        const healthy = await checkUrlHealth(`http://127.0.0.1:${SOUL_CORE_PORT}/health`);

        if (healthy) return; // All good

        // Soul Core is down — check if process is still tracked
        const processAlive = soulNode.process && !soulNode.process.killed;
        if (processAlive) {
            // Process object exists but health check failed — might be starting up
            // Wait for next cycle before redeploying
            return;
        }

        console.log(`   ⚠️  [SLEIPNIR LAUNCHER] Soul Core (port ${SOUL_CORE_PORT}) is DOWN. Auto-restarting...`);

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

// Watchdog is started automatically within initial deployment flow

// --- .env Source of Truth Watchdog ---
let restartTimeout = null;
let isRedeploying = false;  // Guard against double-deployment
const envPath = path.join(LUMAX_ROOT, '.env');

if (fs.existsSync(envPath)) {
    console.log(`👁️  [SLEIPNIR LAUNCHER] .env watch disabled to prevent aggressive automatic redeploy loops on Windows.`);
    // fs.watch(envPath, ...) disabled to prevent loop triggers.
}

// Catch emergency breaks and run defensive state preservation
process.on('SIGINT', () => {
    console.log("\n🛑 [SHUTDOWN INTERCEPTED] Grounding Sleipnir safely. Securing linear timeline states...");

    // Ensure all children are killed when the main process shuts down
    SwarmFleet.filter(Boolean).forEach(node => node.kill());

    try {
        if (fs.existsSync(path.join(LUMAX_ROOT, "Scripts/vibe_checkpoint.ps1"))) {
            execSync(`powershell -NoProfile -Command ".\\Scripts\\vibe_checkpoint.ps1 -Action commit -Message 'Sleipnir Engine Soft Landing Auto-Commit'"`, { stdio: 'inherit' });
        }
    } catch (e) {
        console.log("🌱 Timeline state already anchored.");
    }
    process.exit(0);
});


