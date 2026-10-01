import { spawn } from 'child_process';
import path from 'path';
import fs from 'fs';

const unslothExe = 'C:\\Users\\danie\\.unsloth\\llama.cpp\\build\\bin\\Release\\llama-server.exe';
const modelPath = 'C:\\Users\\danie\\.cache\\huggingface\\hub\\models--jica98--qwen3.5-4B-super-coder\\snapshots\\73c25a036706ebb5f09338f6743ec4d3ec0ce66e\\qwen3.5-4B-super-coder.Q4_0.gguf';

const logFile = path.join(process.cwd(), 'llama_test4.txt');
let log = '';

// Test 1: spawn with NO env modifications (bare minimum)
log += '=== TEST 1: spawn with process.env only ===\n';
const proc1 = spawn(unslothExe, [
  '-m', modelPath,
  '-c', '4096',
  '--port', '8891',
  '-ngl', '24',
  '-t', '4',
  '--flash-attn', 'on'
], {
  stdio: ['ignore', 'pipe', 'pipe'],
  env: process.env
});

proc1.stdout.on('data', d => { log += '[STDOUT1] ' + d.toString(); });
proc1.stderr.on('data', d => { log += '[STDERR1] ' + d.toString(); });

proc1.on('close', (code) => {
  log += '\nEXIT1 CODE: ' + code + '\n';
  
  // Test 2: spawn with PATH modified (like sleipnir does)
  log += '\n=== TEST 2: spawn with custom PATH ===\n';
  const proc2 = spawn(unslothExe, [
    '-m', modelPath,
    '-c', '4096',
    '--port', '8892',
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

  proc2.stdout.on('data', d => { log += '[STDOUT2] ' + d.toString(); });
  proc2.stderr.on('data', d => { log += '[STDERR2] ' + d.toString(); });

  proc2.on('close', (code2) => {
    log += '\nEXIT2 CODE: ' + code2 + '\n';
    fs.writeFileSync(logFile, log);
    console.log('Written to', logFile);
    process.exit(0);
  });
});

setTimeout(() => {
  log += '\n[TIMEOUT 15s] Still running\n';
  fs.writeFileSync(logFile, log);
  console.log('Written to', logFile, '(timeout)');
  process.exit(0);
}, 15000);