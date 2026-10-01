const fs = require('fs');
const path = require('path');
const { extractFacts, injectHarness, saveHarnessData } = require('./core/harness');

async function runTest() {
    console.log("=== LUMAX Harness Test ===");

    // Clear existing data for a clean test
    saveHarnessData({ facts: [], rules: [], preferences: [] });
    console.log("1. Cleared harness data.");

    // Simulate an incoming message to test injection (should inject an empty block or skip)
    let fakeMessages = [{ role: 'user', content: 'Hello!' }];
    fakeMessages = injectHarness(fakeMessages, 'cloud');
    console.log("2. Injected harness (empty):", JSON.stringify(fakeMessages, null, 2));

    // Simulate an outgoing chat log (Swedish)
    const chatLog = `User: Jag föredrar alltid att använda mörk bakgrund när jag bygger appar, och jag gillar inte ramverk som TailwindCSS. Vanilla CSS är bäst!
Assistant: Jag förstår. Jag ska komma ihåg att du föredrar mörk bakgrund och Vanilla CSS framför TailwindCSS.`;

    console.log("\n3. Triggering background extraction with Swedish chat...");
    try {
        await extractFacts(chatLog);
        
        // Wait a tiny bit just in case
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // Check what got saved
        const dbPath = path.join(__dirname, 'memory_data', 'harness_facts.json');
        if (fs.existsSync(dbPath)) {
            const data = JSON.parse(fs.readFileSync(dbPath, 'utf8'));
            console.log("\n4. Saved Harness Data (Should be in English):");
            console.log(JSON.stringify(data, null, 2));

            // Test injection again with data
            console.log("\n5. Testing Injection with Data (Cloud Mode):");
            const injectedMessages = injectHarness([{ role: 'user', content: 'Write some code.' }], 'cloud');
            console.log(JSON.stringify(injectedMessages, null, 2));
        } else {
            console.log("\n❌ harness_facts.json was not created.");
        }
    } catch (err) {
        console.error("\n❌ Test failed. Make sure LM Studio is running on port 7272 with 'smart-router_gguf'.");
        console.error(err);
    }
}

runTest();
