import { spawn } from 'child_process';
import path from 'path';

const unslothExe = path.join('C:', 'Users', 'danie', '.unsloth', 'llama.cpp', 'build', 'bin', 'Release', 'llama-server.exe');
const modelPath = path.join('C:', 'Users', 'danie', '.cache', 'huggingface', 'hub', 'models--jica98--qwen3.5-4B-super-coder', 'snapshots', '73c25a036706ebb5f09338f6743ec4d3ec0ce66e', 'qwen3.5-4B-super-coder.Q4_0.gguf');

console.log('EXE:', unslothExe);
console.log('MODEL:', modelPath);

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

let stdout = '';
let stderr = '';

proc.stdout.on('data', d => { stdout += d.toString(); });
proc.stderr.on('data', d => { stderr += d.toString(); });

setTimeout(() => {
  console.log('=== STDOUT ===');
  console.log(stdout);
  console.log('=== STDERR ===');
  console.log(stderr);
  console.log('=== EXIT CODE ===');
  console.log(proc.exitCode);
  process.exit(0);
}, 5000);