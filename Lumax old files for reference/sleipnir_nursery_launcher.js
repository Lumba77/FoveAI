import fs from 'fs';
import os from 'os';
import path from 'path';
import { spawn, execSync } from 'child_process';

const LUMAX_ROOT = process.cwd();

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

console.log(`🦾 [SLEIPNIR NURSERY LAUNCHER] Constructing Speculative Swarm parallel worker arrays...`);

const FLEET_PORTS = {
    "FORGE-NURSERY-8105": [8105],
    "SWARM-RING-UI-8106": [8106],
    "SWARM-RING-VOICE-8107": [8107],
    "SWARM-RING-MEMORY-8108": [8108],
    "SWARM-HEARTBEAT-DAEMON": []
};

/**
 * Smart zombie sweep — health-checks fleet ports BEFORE killing.
 * Preserves healthy services, kills only zombies squatting on ports.
 */
function purgeZombies() {
    const cleaned = [];
    const allPorts = [...new Set(Object.values(FLEET_PORTS).flat().filter(Boolean))];
    if (allPorts.length === 0) return cleaned;

    console.log('   🧹 [ZOMBIE SWEEP] Scanning nursery fleet ports...');

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
            }
        } catch (_) {}

        if (healthy) continue;

        // 2. Find and kill zombie squatting on this port
        try {
            const out = execSync('netstat -ano -p tcp', { encoding: 'utf8', timeout: 5000 });
            const lines = out.split('\n');
            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed || !trimmed.includes('LISTENING')) continue;
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
                        console.log(`   💀 Killed zombie PID ${pid} on port ${port}`);
                    } catch (_) {}
                    break;
                }
            }
        } catch (e) {
            console.error(`   ⚠️  [ZOMBIE SWEEP] Port ${port} scan failed: ${e.message}`);
        }
    }

    if (cleaned.length > 0) {
        console.log(`   🧹 [ZOMBIE SWEEP] Purged ${cleaned.length} port(s): ${cleaned.join(', ')}`);
    } else {
        console.log('   ✨ All ports clear or healthy.');
    }
    return cleaned;
}

class SwarmWorkerNode {
    constructor(name, command, args, options = {}) {
        this.name = name;
        this.command = command;
        this.args = args;
        this.options = Object.assign({ cwd: LUMAX_ROOT, shell: true }, options);
        this.process = null;
    }

    deploy() {
        console.log(`   🚀 [FLEET SECTOR] Launching active thread: ${this.name}`);
        this.process = spawn(this.command, this.args, this.options);

        this.process.stdout.on('data', (data) => {
            const lines = data.toString().split('\n');
            lines.forEach(line => {
                if (line.trim()) console.log(`[${this.name}] ${line.trim()}`);
            });
        });

        this.process.stderr.on('data', (data) => {
            const line = data.toString().trim();
            if (!line) return;
            const noise = [
                'DeprecationWarning', 'UserWarning', 'FutureWarning', 'PendingDeprecationWarning',
                'SyntaxWarning', 'ResourceWarning', 'ImportWarning', 'BytesWarning', 'RuntimeWarning',
                '404', 'Not Found', '200 OK', '307 Temporary Redirect', '302 Found',
                'INFO:', 'DEBUG:', 'WARNING:', 'INFO ', 'DEBUG ', 'WARNING ',
                'trial', 'Trial', 'TRIAL',
                'uvicorn.error', 'uvicorn.access',
                'Application startup complete', 'Uvicorn running on',
                'Press CTRL+C', 'Waiting for application',
                'Started server process', 'Started reloader process',
                'StatReload', 'will watch for changes', 'reload',
                'startup', 'shutdown',
                'connection refused', 'Connection refused', 'connect ECONNREFUSED',
                'ECONNRESET', 'EPIPE',
                'httpx - INFO', 'HTTP Request:',
                'python-dotenv could not parse',
                'lumax.heartbeat - INFO', 'Heartbeat grounded safely',
                'Loading weights:', 'it/s]',
                'DEP0190'
            ];
            const isNoise = noise.some(pattern => line.includes(pattern));
            if (!isNoise) {
                console.error(`⚠️ [${this.name} ALERT] ${line}`);
            }
        });

        this.process.on('close', (code) => {
            console.log(`🛑 [${this.name}] Disconnected from master hive. Exit code: ${code}`);
        });
    }

    kill() {
        if (this.process) {
            console.log(`   ⏏️  [FLEET SECTOR] Sending kill signal to: ${this.name}`);
            try {
                execSync(`taskkill /pid ${this.process.pid} /t /f`, { stdio: 'ignore' });
            } catch (e) {
                this.process.kill('SIGINT');
            }
            this.process = null;
        }
    }
}

const SwarmFleet = [
    // Node 5: Coder (Port 8105) speculates with draft model of UI layout worker (Port 8106)
    new SwarmWorkerNode(
        "FORGE-NURSERY-CODER-8105",
        "C:\\Users\\danie\\.unsloth\\studio\\unsloth_studio\\Scripts\\python.exe",
        ["-m", "uvicorn", "Tools.lumax-xrl.nursery.forge_nursery_api:app", "--port", "8105", "--host", "127.0.0.1"]
    ),

    // Node 6: UI Swarm Worker (Port 8106) speculates with draft model of Voice worker (Port 8107)
    (() => {
        const modelPath = "C:/Users/danie/.cache/huggingface/hub/lumax-forge/ui-0.5b-moq.gguf";
        if (!fs.existsSync(modelPath)) {
            console.log("   ℹ️  [SWARM-RING-UI-8106] Model not found — skipping Node.");
            return null;
        }
        return new SwarmWorkerNode(
            "SWARM-RING-UI-8106",
            "python",
            ["-m", "llama_cpp.server", "--model", modelPath, "--port", "8106", "--host", "127.0.0.1", "--draft_model", "C:/Users/danie/.cache/huggingface/hub/lumax-forge/voice-0.5b-moq.gguf"]
        );
    })(),

    // Node 7: Voice Swarm Worker (Port 8107) speculates with draft model of Memory worker (Port 8108)
    (() => {
        const modelPath = "C:/Users/danie/.cache/huggingface/hub/lumax-forge/voice-0.5b-moq.gguf";
        if (!fs.existsSync(modelPath)) {
            console.log("   ℹ️  [SWARM-RING-VOICE-8107] Model not found — skipping Node.");
            return null;
        }
        return new SwarmWorkerNode(
            "SWARM-RING-VOICE-8107",
            "python",
            ["-m", "llama_cpp.server", "--model", modelPath, "--port", "8107", "--host", "127.0.0.1", "--draft_model", "C:/Users/danie/.cache/huggingface/hub/lumax-forge/memory-0.5b-moq.gguf"]
        );
    })(),

    // Node 8: Memory Swarm Worker (Port 8108) speculates with draft model of State worker (Port 8109)
    (() => {
        const modelPath = "C:/Users/danie/.cache/huggingface/hub/lumax-forge/memory-0.5b-moq.gguf";
        if (!fs.existsSync(modelPath)) {
            console.log("   ℹ️  [SWARM-RING-MEMORY-8108] Model not found — skipping Node.");
            return null;
        }
        return new SwarmWorkerNode(
            "SWARM-RING-MEMORY-8108",
            "python",
            ["-m", "llama_cpp.server", "--model", modelPath, "--port", "8108", "--host", "127.0.0.1", "--draft_model", "C:/Users/danie/.cache/huggingface/hub/lumax-forge/state-0.5b-moq.gguf"]
        );
    })(),

    // Node 15: Heartbeat Daemon — measures speculative loop latency & feeds pilot-wave resonance
    new SwarmWorkerNode(
        "SWARM-HEARTBEAT-DAEMON",
        "python",
        ["Tools/lumax-xrl/nursery/heartbeat_daemon.py"]
    ),
];

console.log("\n🛸 Starting Nursery & Speculative Swarm Ring fleet...\n");
purgeZombies();
SwarmFleet.filter(Boolean).forEach(node => node.deploy());

// Catch emergency breaks and run defensive state preservation
process.on('SIGINT', () => {
    console.log("\n🛑 [SHUTDOWN INTERCEPTED] Grounding Swarm Ring safely.");
    SwarmFleet.filter(Boolean).forEach(node => node.kill());
    process.exit(0);
});
