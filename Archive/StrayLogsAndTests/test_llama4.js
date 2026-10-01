import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';

// Replicate the exact .env loading from sleipnir_launcher.js
function loadEnv() {
    const envPath = path.join(process.cwd(), '.env');
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
            // Strip inline comments
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
            if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
                val = val.slice(1, -1);
            }
            vars[key] = val;
        }
    } catch (_) {}
    return vars;
}

const ENV = loadEnv();
const unslothExe = 'C:\\Users\\danie\\.unsloth\\llama.cpp\\build\\bin\\Release\\llama-server.exe';
const modelPath = 'C:\\Users\\danie\\.cache\\huggingface\\hub\\models--jica98--qwen3.5-4B-super-coder\\snapshots\\73c25a036706ebb5f09338f6743ec4d3ec0ce66e\\qwen3.5-4B-super-coder.Q4_0.gguf';

const logFile = path.join(process.cwd(), 'llama_test3.txt');
let log = '';

// Build the EXACT same env as SwarmWorkerNode constructor
const childEnv = { ...process.env, ...ENV, PATH: path.dirname(unslothExe) + ';' + (process.env.PATH || '') };

log += '=== ENV keys passed to child ===\n';
log += Object.keys(childEnv).sort().join('\n') + '\n\n';

const proc = spawn(unslothExe, [
  '-m', modelPath,
  '-c', '4096',
  '--port', '8890',
  '-ngl', '24',
  '-t', '4',
  '--flash-attn', 'on'
], {
  stdio: ['ignore', 'pipe', 'pipe'],
  env: childEnv
});

log += 'PID: ' + proc.pid + '\n';

proc.stdout.on('data', d => { log += '[STDOUT] ' + d.toString(); });
proc.stderr.on('data', d => { log += '[STDERR] ' + d.toString(); });

proc.on('close', (code) => {
  log += '\nEXIT CODE: ' + code + '\n';
  fs.writeFileSync(logFile, log);
  console.log('Written to', logFile);
  process.exit(0);
});

setTimeout(() => {
  log += '\n[TIMEOUT 10s] Still running\n';
  fs.writeFileSync(logFile, log);
  console.log('Written to', logFile, '(timeout)');
  proc.kill();
  process.exit(0);
}, 10000);