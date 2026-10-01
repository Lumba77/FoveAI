import os
import re

p = os.path.expanduser("~/FoveAI/Tools/xrlf-model/foveated-memory/core/context-compressor.js")
with open(p, "r") as f:
    text = f.read()

# Replace summarizeWithLMStudio
new_summarize = """async function summarizeWithLMStudio(messages, level = 3) {
    try {
        if (!process.env.LM_STUDIO_URL && !LM_STUDIO_URL) return null;
        
        const turns = messages.map(m => `${m.role}: ${typeof m.content === 'string' ? m.content : JSON.stringify(m.content)}`).join('\\n');
        
        let promptInstruction = "";
        let maxT = 300;
        
        if (level <= 2) {
            promptInstruction = `Tidy up the following messages. Remove unnecessary words but maintain a highly readable, conversational summary.\\n\\nFormat EXACTLY:\\nDECISIONS: <key decisions/conclusions>\\nFILES: <files created/modified, or "none">\\nSTATUS: <solved|pending|in-progress>\\nCONTEXT: <critical facts next agent must know>`;
            maxT = 500;
        } else if (level === 3 || level === 4) {
            promptInstruction = `Extract key facts, code decisions, and file names into a dense bulleted list.\\n\\nFormat EXACTLY:\\nDECISIONS: <key decisions>\\nFILES: <files>\\nSTATUS: <solved|pending|in-progress>\\nCONTEXT: <bullets of critical facts>`;
            maxT = 200;
        } else {
            promptInstruction = `Aggressively compress into pure XRLF syntax. Provide only a headline and essential atomic keywords. Discard all conversational pleasantries.\\n\\nFormat EXACTLY:\\n<xrlf status="solved|pending" files="[files]"><headline>...</headline><keywords>...</keywords></xrlf>`;
            maxT = 100;
        }

        const res = await fetch(`${LM_STUDIO_URL}/v1/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: COMPRESS_MODEL,
                messages: [
                    { role: 'system', content: 'You are a conversation checkpoint encoder.' },
                    { role: 'user', content: `${promptInstruction}\\n\\nConversation:\\n${turns}\\n\\nCHECKPOINT:` }
                ],
                max_tokens: maxT,
                temperature: 0.1,
                stream: false
            }),
            signal: AbortSignal.timeout(20000)
        });

        if (!res.ok) throw new Error(`LM Studio ${res.status}: ${await res.text()}`);
        const data = await res.json();
        const rawContent = data.choices?.[0]?.message?.content;
        if (!rawContent) return null;
        const out = Array.isArray(rawContent)
            ? rawContent.filter(p => p && typeof p.text === 'string').map(p => p.text).join('\\n')
            : String(rawContent);
        return out.trim() || null;
    } catch (err) {
        console.warn('[Compressor] LM Studio unreachable, using extractive fallback:', err.message);
        return null;
    }
}"""

pattern1 = re.compile(r'async function summarizeWithLMStudio\(messages\) \{.*?return null;\n    \}\n\}', re.DOTALL)
text = pattern1.sub(new_summarize, text)


# Replace Main Compressor batch loop
new_batch_loop = """
    const minKeep = 2; // Ring 1 is raw tokens
    let compressCount = turnMsgs.length - minKeep;
    const batchSize = 4;
    const toCompress = turnMsgs.slice(0, compressCount - (compressCount % batchSize));
    const toKeep     = turnMsgs.slice(toCompress.length);
    
    if (toCompress.length === 0) {
        return messages;
    }

    const baseAggression = parseInt(process.env.XRLF_PROXY_AGGRESSION, 10) || parseInt(level, 10) || 3;
    const batches = [];
    
    for (let i = 0; i < toCompress.length; i += batchSize) {
        batches.push({
            messages: toCompress.slice(i, i + batchSize),
            startIndex: i
        });
    }

    // Assign Rings: Newest batch (closest to toKeep) is Ring 2. Oldest batch (index 0) is Ring N.
    batches.forEach((b, idx) => {
        const ringNumber = (batches.length - idx) + 1; 
        const ringCompression = Math.min(5, baseAggression + (ringNumber - 2));
        b.ringNumber = ringNumber;
        b.compressionLevel = ringCompression;
    });

    const checkpointBlocks = [];
    
    for (const b of batches) {
        const batchText = b.messages.map(m =>
            `${m.role}: ${typeof m.content === 'string' ? m.content : JSON.stringify(m.content)}`
        ).join('\\n');

        // Include compression level in hash so aging memories get re-compressed!
        const hash = hashContent(batchText + "_lvl" + b.compressionLevel);

        let cached = loadCheckpoint(hash);
        if (!cached) {
            console.log(`[Compressor] Ring ${b.ringNumber} | Compressing turns ${b.startIndex+1}-${b.startIndex+b.messages.length} at Level ${b.compressionLevel} → [CKP:${hash}]`);
            const summary = await summarizeWithLMStudio(b.messages, b.compressionLevel) || extractiveSummary(b.messages);
            cached = {
                hash,
                session: sessionId,
                turnRange: [b.startIndex + 1, b.startIndex + b.messages.length],
                timestamp: new Date().toISOString(),
                summary,
                raw: b.messages
            };
            saveCheckpoint(hash, cached);
        }

        checkpointBlocks.push(`[CKP:${hash} @ turns ${cached.turnRange[0]}-${cached.turnRange[1]} | Ring ${b.ringNumber} | ${cached.timestamp.slice(0,10)}]\\n${cached.summary}`);
    }"""

pattern2 = re.compile(r'const minKeep = 2; // Hard minimum to keep verbatim.*?    for \(let i = 0; i < toCompress\.length; i \+= batchSize\) \{.*?        checkpointBlocks\.push.*?\\n\$\{cached\.summary\}`\);\n    \}', re.DOTALL)
text = pattern2.sub(new_batch_loop, text)

with open(p, "w") as f:
    f.write(text)
