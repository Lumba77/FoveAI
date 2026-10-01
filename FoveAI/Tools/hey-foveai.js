#!/usr/bin/env node

import http from 'http';

const query = process.argv.slice(2).join(' ').trim();

if (!query) {
    console.log('\n🛸 Hey Lumax — Terminal Assistance CLI');
    console.log('Usage:');
    console.log('  hey "your request here"');
    console.log('\nExample:');
    console.log('  hey "fix the typo in the README.md file"');
    process.exit(0);
}

const payload = JSON.stringify({
    error: `User requested assistance: ${query}`,
    force: true // Bypasses emergency gate for direct user request
});

const reqOptions = {
    hostname: '127.0.0.1',
    port: 8113,
    path: '/solve/apply',
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload)
    },
    timeout: 120000 // 2 minute timeout for local reasoning
};

console.log(`\n📡 Sending request to Lumax Solver: "${query}"...`);
console.log('   Reasoning with 4B Fast Coder tier. Please wait...');

const req = http.request(reqOptions, (res) => {
    let body = '';
    res.setEncoding('utf-8');
    res.on('data', (chunk) => body += chunk);
    res.on('end', () => {
        try {
            const data = JSON.parse(body);
            if (res.statusCode !== 200) {
                console.error(`\n❌ Error from solver (status ${res.statusCode}):`, data.error || body);
                process.exit(1);
            }
            
            console.log('\n✨ ─── Lumax Solver Response ─── ✨');
            console.log(data.chatResponse || 'No explanation returned.');
            
            if (data.status === 'applied') {
                console.log(`\n✅ Applied edits to files: ${data.applied.join(', ')}`);
            } else if (data.status === 'proposed') {
                console.log(`\n💾 Proposed solution saved to: ${data.proposalFile}`);
            } else {
                console.log(`\nℹ️ Status: ${data.status}`);
            }
            console.log('─────────────────────────────────');
        } catch (e) {
            console.error('\n❌ Failed to parse JSON response from solver:', e.message);
            console.error('Raw response:', body);
            process.exit(1);
        }
    });
});

req.on('error', (err) => {
    console.error('\n❌ Connection to local solver failed.');
    console.error('Make sure the Concordia launcher (Sleipnir) is running on port 8113.');
    console.error(`Detail: ${err.message}`);
    process.exit(1);
});

req.on('timeout', () => {
    console.error('\n❌ Request timed out. The local model took too long to respond.');
    req.destroy();
    process.exit(1);
});

req.write(payload);
req.end();
