import fs from 'fs';
import path from 'path';
import readline from 'readline';

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const askQuestion = (query) => new Promise((resolve) => rl.question(query, resolve));

// Standard Open-Source Fallback Port
const LOCAL_LLM_URL = "http://localhost:1234/v1/chat/completions";
const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;
const UNIVERSAL_EXTENSIONS = ['.py', '.ts', '.js', '.log', '.go', '.rs', '.cpp', '.cs', '.html', '.svelte', '.json', '.md', '.java', '.rb'];

function getRecentFiles(dir, fileList = []) {
    let files = [];
    try { files = fs.readdirSync(dir); } catch (e) { return fileList; }
    for (const file of files) {
        const fullPath = path.join(dir, file);
        if (['node_modules', '.git', '.venv', '.svelte-kit', 'build', 'dist', 'target', '.logs', 'logs'].some(p => fullPath.includes(p))) continue;
        try {
            const stat = fs.statSync(fullPath);
            if (stat.isDirectory()) {
                getRecentFiles(fullPath, fileList);
            } else {
                const ext = path.extname(file).toLowerCase();
                const isRecent = (Date.now() - stat.mtimeMs) < SEVEN_DAYS_MS;
                if (UNIVERSAL_EXTENSIONS.includes(ext) && isRecent) {
                    fileList.push({ fullPath, mtime: stat.mtimeMs });
                }
            }
        } catch (e) {}
    }
    return fileList;
}

async function run() {
    console.log("\n🛸 ================================================================= 🛸");
    console.log("                FoveAI UNIVERSAL SOLVER — SYSTEM AUDITOR                 ");
    console.log("🛸 ================================================================= 🛸\n");

    let activeModel = "default";
    try {
        const check = await fetch("http://localhost:1234/v1/models", { signal: AbortSignal.timeout(1000) });
        if (check.ok) {
            const mData = await check.json();
            if (mData.data && mData.data.length > 0) activeModel = mData.data.id;
            console.log(`💻 Local Inference Engine Active: [Model: ${activeModel}]`);
        }
    } catch (e) {
        console.error("❌ Local inference engine on port 1234 is offline. Please launch your local LLM server first.");
        rl.close();
        return;
    }

    console.log("📋 Tracking file modifications across active directory tree...");
    let candidateFiles = getRecentFiles(process.cwd());
    candidateFiles.sort((a, b) => b.mtime - a.mtime);
    const top40Files = candidateFiles.slice(0, 40);

    if (top40Files.length === 0) {
        console.log("✨ Clean workspace telemetry. No files modified in the past 7 days.");
        rl.close();
        return;
    }

    let manifestContext = [];
    top40Files.forEach(f => {
        const relativePath = path.relative(process.cwd(), f.fullPath);
        let content = "";
        try {
            content = fs.readFileSync(f.fullPath, 'utf-8');
            if (content.length > 2000) content = content.substring(0, 2000) + "\n[... Truncated for token optimization ...]";
        } catch(e) {}
        manifestContext.push(`FILE: ${relativePath}\n---\n${content}\n===\n`);
    });

    console.log(`🧠 Processing workspace contexts (${top40Files.length} files) into tensor pipelines...`);
    const systemPrompt = `You are Lumax Solver, an elite multi-language programming assistant auditing project architecture. Analyze the provided code snapshots and log files. Evaluate general soundness of the code logic, identify logical faults/race conditions, and formulate optimization patches. Your response MUST follow this exact format:\n### 🔬 GENERAL CODE BASE SOUNDNESS\n[Audit details]\n\n### ⚡ PERCEIVED WEAKNESSES & LOGICAL FAULTS\n[Vulnerabilities]\n\n### 🛡️ RECOMMENDED ACTION STAGE PROTOCOLS\n[Next steps]`;

    try {
        const response = await fetch(LOCAL_LLM_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                model: activeModel,
                messages: [
                    { role: 'system', content: systemPrompt },
                    { role: 'user', content: manifestContext.join("\n") }
                ],
                temperature: 0.1
            })
        });

        const data = await response.json();
        const rawContent = data.choices.message.content;
        const cleanReport = rawContent.replace(/<channel|>|[\s\S]*?<\/channel>/gi, "").trim();
        console.log(`\n--------------------------------------------------\n${cleanReport}\n--------------------------------------------------`);

        console.log("\n💬 Anything else bothering the development team?");
        console.log("1. 🛠️  Auto fix bugs\n2. 💡 Propose optimizations\n3. 📝 File a new issue\n4. 🚨 Rescue mode\n");
        const selection = await askQuestion("👉 Select an operational protocol index (1-4): ");
        console.log("\n🛸 Audit finalized. Safe coding!");
    } catch(err) {
        console.error("❌ Telemetry extraction loop faulted:", err.message);
    }
    rl.close();
}
run();
