import os

p = os.path.expanduser("~/FoveAI/Tools/xrlf-model/foveated-memory/core/context-compressor.js")
with open(p, "r") as f:
    text = f.read()

# Replace the entire Main Compressor function
import re
new_func = """async function compressContext(messages, sessionId = 'default', level = 3) {
    const mode = process.env.XRLF_COGNITIVE_MODE || 'local';
    
    // ── DYNAMIC TOKEN BUDGET ──
    // Local (RTX 4060 8GB): max ~4000 context tokens to avoid OOM
    // Cloud (Gemini/Claude): higher budget
    const maxTokens = mode === 'local' ? 4000 : 
                     (parseInt(process.env.XRLF_CLOUD_MAX_TOKENS_CAP, 10) || 16000);
                     
    // Approximation: 1 token = ~4 characters
    const maxChars = maxTokens * 4;

    console.log(`[Compressor] ▶️ entry | session=${sessionId} | mode=${mode} | tokenBudget=${maxTokens} | total=${messages.length}`);
    
    const systemMsgs  = messages.filter(m => m.role === 'system');
    const turnMsgs    = messages.filter(m => m.role !== 'system');

    // Calculate current character count of turn messages
    const currentChars = turnMsgs.reduce((acc, m) => {
        return acc + (typeof m.content === 'string' ? m.content.length : JSON.stringify(m.content).length);
    }, 0);
    
    const currentTokens = Math.ceil(currentChars / 4);

    // If we are under budget, skip compression! (Dynamic token safety)
    if (currentTokens <= maxTokens) {
        console.log(`[Compressor] ⏭️ skip | currentTokens=${currentTokens} <= maxTokens=${maxTokens}`);
        return messages;
    }

    // We are OVER budget. Compress oldest turns until we are under budget.
    // Always preserve the absolute newest 2 messages as a hard minimum.
    console.log(`[Compressor] 📊 OVER BUDGET: ${currentTokens} / ${maxTokens}. Triggering compression...`);
    
    const minKeep = 2; // Hard minimum to keep verbatim
    const checkpointBlocks = [];
    
    let compressCount = turnMsgs.length - minKeep;
    
    // We will compress in batches of 4 turns
    const batchSize = 4;
    const toCompress = turnMsgs.slice(0, compressCount - (compressCount % batchSize));
    const toKeep     = turnMsgs.slice(toCompress.length);
    
    if (toCompress.length === 0) {
        return messages; // Can't compress without breaking minKeep
    }

    for (let i = 0; i < toCompress.length; i += batchSize) {
        const batch     = toCompress.slice(i, i + batchSize);
        const batchText = batch.map(m =>
            `${m.role}: ${typeof m.content === 'string' ? m.content : JSON.stringify(m.content)}`
        ).join('\\n');

        const hash = hashContent(batchText);

        let cached = loadCheckpoint(hash);
        if (!cached) {
            console.log(`[Compressor] Compressing turns ${i+1}-${i+batch.length} → [CKP:${hash}]`);
            const summary = await summarizeWithLMStudio(batch) || extractiveSummary(batch);
            cached = {
                hash,
                session: sessionId,
                turnRange: [i + 1, i + batch.length],
                timestamp: new Date().toISOString(),
                summary,
                raw: batch
            };
            saveCheckpoint(hash, cached);
        }

        checkpointBlocks.push(`[CKP:${hash} @ turns ${cached.turnRange[0]}-${cached.turnRange[1]} | ${cached.timestamp.slice(0,10)}]\\n${cached.summary}`);
    }

    const compressedHistoryMsg = {
        role: 'system',
        content: `=== COMPRESSED HISTORY (XRL Checkpoints) ===\\n${checkpointBlocks.join('\\n---\\n')}\\n=== END COMPRESSED HISTORY ===\\n\\nRecent turns follow verbatim.`
    };

    const result = [
        ...systemMsgs,
        compressedHistoryMsg,
        ...toKeep
    ];

    const savedTurns = toCompress.length;
    const finalTokens = Math.ceil(JSON.stringify(result).length / 4);
    
    console.log(`[Compressor] ✅ Compressed ${savedTurns} turns → ${checkpointBlocks.length} checkpoints. New context: ~${finalTokens} tokens.`);

    return result;
}"""

# Use regex to replace the old function block
# We replace from "async function compressContext(" up to the end before "function expandCheckpoint("
pattern = re.compile(r'async function compressContext\(.*?\).*?return result;\n}', re.DOTALL)
text = pattern.sub(new_func, text)

with open(p, "w") as f:
    f.write(text)
