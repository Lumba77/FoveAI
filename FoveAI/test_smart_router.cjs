const { smartRouteMessages } = require('./Tools/foveated-memory/core/smart-router.js');

async function runTest() {
    console.log('--- Starting Smart Router Test ---');
    
    // Generate a massive string of fake code (> 12,000 characters)
    let massiveCode = 'function start() { console.log("start"); }\n';
    for (let i = 0; i < 500; i++) {
        massiveCode += `function doSomething${i}() { return "This is a very long string to pad the length of the file and ensure it triggers the smart router interception limit of 12000 chars. We need it to be big. Line ${i}"; }\n`;
    }
    massiveCode += 'function end() { console.log("Crucial fix needed here"); }\n';

    console.log(`Generated message of length: ${massiveCode.length}`);

    const messages = [
        { role: 'system', content: 'You are a helpful assistant.' },
        { role: 'user', content: massiveCode }
    ];

    try {
        const routed = await smartRouteMessages(messages, 'qwen2.5-0.5b-instruct', 'http://127.0.0.1:7272');
        
        console.log('\n--- Result ---');
        console.log(`Original messages length: ${messages.length}`);
        console.log(`Routed messages length: ${routed.length}`);
        
        const userMsg = routed.find(m => m.role === 'user');
        console.log(`Routed user message length: ${userMsg.content.length}`);
        
        if (userMsg.content.includes('[SMART ROUTER EXTRACTED CRITICAL CONTEXT]')) {
            console.log('✅ SUCCESS: Smart Router successfully intercepted and replaced the massive block.');
            console.log('\nPreview of new content:');
            console.log(userMsg.content.substring(0, 500) + '...');
        } else {
            console.log('❌ FAILED: Smart Router did not replace the block.');
        }
    } catch (err) {
        console.error('Test failed with error:', err);
    }
}

runTest();
