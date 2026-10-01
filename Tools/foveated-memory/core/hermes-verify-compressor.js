#!/usr/bin/env node
/**
 * Ad-hoc verification for context-compressor.js continuity fix.
 * Static checks only — does not require LM Studio / proxy to be running.
 */
const fs = require('fs');
const { execSync } = require('child_process');

const compressor = 'C:\\\\Users\\\\danie\\\\program\\\\LUMAX\\\\Tools\\\\foveated-memory\\\\core\\\\context-compressor.js';
const envFile = 'C:\\\\Users\\\\danie\\\\program\\\\LUMAX\\\\.env';

function assert(cond, msg) {
    if (!cond) {
        console.error(`FAIL: ${msg}`);
        process.exit(1);
    }
    console.log(`PASS: ${msg}`);
}

const src = fs.readFileSync(compressor, 'utf8');
const env = fs.readFileSync(envFile, 'utf8');

assert(src.includes('IDENTITY:'), 'checkpoint output includes IDENTITY');
assert(src.includes('NEXT:'), 'checkpoint output includes NEXT pending task');
assert(src.includes('continue the SAME session'), 'summarizer instructed to preserve session continuity');
assert(src.includes('Do NOT start a new greeting'), 'summarizer forbidden from greeting reset');
assert(src.includes('This is compressed context from the SAME ongoing session'), 'compressed history wrapper asserts continuity');
assert(src.includes('Continue the conversation naturally'), 'compressed history wrapper instructs continuation');
assert(src.includes('LUMAX_COMPRESSOR_MODEL'), 'uses LUMAX_COMPRESSOR_MODEL env var');
assert(env.includes('LUMAX_COMPRESSOR_MODEL=reasoning-summarizer-800m-pre-q8_0'), '.env points at small SupraLabs 800M summarizer');
assert(src.includes('IDENTITY: Hermes Agent'), 'extractive fallback includes identity');
assert(src.includes('NEXT:'), 'extractive fallback includes NEXT');

execSync(`node --check "${compressor}"`, { stdio: 'inherit' });

console.log('\nAll ad-hoc invariants passed.');
