import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';

const unslothExe = path.join('C:', 'Users', 'danie', '.unsloth', 'llama.cpp', 'build', 'bin', 'Release', 'llama-server.exe');
const modelPath = path.join('C:', 'Users', 'danie', '.cache', 'huggingface', 'hub', 'models--jica98--qwen3.5-4B-super-coder', 'snapshots', '73c25a036706ebb5f09338f6743ec4d3ec0ce66e', 'qwen3.5-4B-super-coder.Q4_0.gguf');

const logFile = path.join(process.cwd(), 'llama_test_output.txt');
let log = '';

log += 'EXE: ' + unslothExe + '\n';
log += 'MODEL: ' + modelPath + '\n';
log += 'MODEL EXISTS: ' + fs.existsSync(modelPath) + '\n';
log += 'EXE EXISTS: ' + fs.existsSync(unslothExe) + '\n';

const proc = spawn(unslothExe, [
  '-m', modelPath,
  '-c', '4096',
  '--port', '8889',
  '-ngl', '24',
  '-t', '4',
  '--flash-attn', 'on'
], {
  stdio: ['ignore', 'pipe', 'pipe'],
  env: {
    ...process.env,
    PATH: path.dirname(unslothExe) + ';' + (process.env.PATH || '')
  }
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

// Also write after 8 seconds if still running
setTimeout(() => {
  log += '\n[TIMEOUT 8s] Process still running, exit code: ' + proc.exitCode + '\n';
  fs.writeFileSync(logFile, log);
  console.log('Written to', logFile, '(timeout)');
  process.exit(0);
}, 8000);