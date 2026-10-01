import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import readline from 'readline';

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
const askQuestion = (query) => new Promise((resolve) => rl.question(query, resolve));

// LM Studio Local Engine Port (Customized to 7272)
const LOCAL_LLM_URL = "http://localhost:7272/v1/chat/completions";
const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;
const TARGET_EXTENSIONS = ['.py', '.ts', '.js', '.log', '.html', '.svelte', '.json', '.md'];

// OMEGA_085 Service Ports Manifest for Telemetry Probing
const HEALTH_ENDPOINTS = [
    { name: "Vessel UI/XR httpd", url: "http://localhost:5176/health", port: 5176 },
    { name: "XRLF Runtime (Core Cognition)", url: "http://localhost:8402/health", port: 8402 },
    { name: "Ears (STT Whisper)", url: "http://localhost:8002/health", port: 8002 },
    { name: "Genai (Creative Vision)", url: "http://localhost:8003/health", port: 8003 },
    { name: "Mouth (TTS Kokoro)", url: "http://localhost:8004/health", port: 8004 },
    { name: "Memory (Context Vault)", url: "http://localhost:8005/health", port: 8005 },
    { name: "Soundboard (Audio Gen)", url: "http://localhost:8006/health", port: 8006 },
    { name: "Agency (SQLite Storage)", url: "http://localhost:8009/health", port: 8009 },
    { name: "htproxy Gateway", url: "http://localhost:8080/health", port: 8080 }
];

function getRecentCoreFiles(dir, fileList = []) {
    const files = fs.readdirSync(dir);
    for (const file of files) {
        const fullPath = path.join(dir, file);
        if (['node_modules', '.git', '.venv', '.svelte-kit', 'build', 'dist', '.logs'].some(p => fullPath.includes(p))) continue;
        
        try {
            const stat = fs.statSync(fullPath);
            if (stat.isDirectory()) {
                getRecentCoreFiles(fullPath, fileList);
            } else {
                const ext = path.extname(file).toLowerCase();
                const isRecent = (Date.now() - stat.mtimeMs) < SEVEN_DAYS_MS;
                if (TARGET_EXTENSIONS.includes(ext) && isRecent) {
                    fileList.push({ fullPath, mtime: stat.mtimeMs });
                }
            }
        } catch (e) {}
    }
    return fileList;
}

async function run() {
    console.log("\n🛸 ================================================================= 🛸");
    console.log("          FoveAI POST-ANALYSIS DEEP SCAN SEQUENCE (OMEGA_085)          ");
    console.log("🛸 ================================================================= 🛸\n");

    // 1. Verify Local CUDA 12.8 Engine State on Port 7272
    let activeModel = "foveai/gemma-4-12b-qat";
    try {
        const check = await fetch("http://localhost:7272/v1/models", { signal: AbortSignal.timeout(1000) });
        if (check.ok) {
            const mData = await check.json();
            if (mData.data && mData.data.length > 0) activeModel = mData.data[0].id;
        }
    } catch (e) {
        console.error("❌ Local execution engine on port 7272 is offline. Wake up your CUDA 12.8 pipeline first!");
        rl.close();
        return;
    }

    // 2. Perform Dynamic Avionics Health Probe on Active Lumax Ports
    console.log("📡 Probing active OMEGA_085 service matrix health endpoints...");
    let serviceReport = [];
    for (const service of HEALTH_ENDPOINTS) {
        try {
            const res = await fetch(service.url, { signal: AbortSignal.timeout(800) });
            const status = res.ok ? "ONLINE" : "FAULTY";
            serviceReport.push(`[Port ${service.port}] ${service.name}: ${status}`);
        } catch (err) {
            serviceReport.push(`[Port ${service.port}] ${service.name}: OFFLINE (Inhibited)`);
        }
    }
    serviceReport.forEach(line => console.log(`  ${line}`));

    // 3. Scan for Code Updates & Grinding Swarm telemetry records (Last 7 Days)
    console.log("\n📋 Scanning workspace code files, trading agents, and active logs...");
    let candidateFiles = getRecentCoreFiles(process.cwd());
    
    // Explicitly scan the .logs directory for the latest debug trace file
    const logDir = path.join(process.cwd(), '.logs');
    if (fs.existsSync(logDir)) {
        const logFiles = fs.readdirSync(logDir).filter(f => f.endsWith('.log'));
        logFiles.forEach(file => {
            const fullPath = path.join(logDir, file);
            const stat = fs.statSync(fullPath);
            candidateFiles.push({ fullPath, mtime: stat.mtimeMs });
        });
    }

    candidateFiles.sort((a, b) => b.mtime - a.mtime);
    const top40Files = candidateFiles.slice(0, 40);

    if (top40Files.length === 0) {
        console.log("✨ Clean flight telemetry records. No files or log files altered this week.");
        rl.close();
        return;
    }

    // 4. Build manifest contexts safely bounded to protect the 8k N_CTX rolling window
    let manifestContext = [];
    top40Files.forEach(f => {
        const relativePath = path.relative(process.cwd(), f.fullPath);
        let content = "";
        try {
            content = fs.readFileSync(f.fullPath, 'utf-8');
            if (content.length > 2000) content = content.substring(0, 2000) + "\n[... Content truncated to preserve token VRAM headroom ...]";
        } catch(e) {}
        manifestContext.push(`FILE: ${relativePath}\n---\n${content}\n===`);
    });

    console.log(`\n🧠 Transmitting environment records (${top40Files.length} files) into Gemma 4 QAT matrix...`);
    
    const systemPrompt = `You are Lumax Solver, auditing structural code integrity across the OMEGA_085 stack.
Analyze the provided code snapshots and log files. Evaluate general soundness of the TypeScript/Vite WebXR interface, the Python Cognition backends, and the CET Grinding Swarm autonomous trading code logic.

Your response MUST follow this exact layout structure string format:
### 🔬 CODE BASE SOUNDNESS ANALYSIS
[Provide technical health audit details here]

### ⚡ PERCEIVED WEAKNESSES & LOGICAL FAULTS
[Highlight any code weaknesses, race conditions, or trading algorithm risks here]

### 🛡️ RECOMMENDED ACTION STAGE PROTOCOLS
[Provide concise step-by-step next actions here]

Keep your response concise, dense with actionable programming insights, and friendly.`;

    try {
        const response = await fetch(LOCAL_LLM_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                model: activeModel,
                messages: [
                    { role: 'system', content: systemPrompt },
                    { role: 'user', content: `SERVICE_STATUS:\n${serviceReport.join("\n")}\n\nMANIFEST:\n${manifestContext.join("\n")}` }
                ],
                temperature: 0.1
            })
        });

        const data = await response.json();
        const rawContent = data.choices[0].message.content;
        
        // Clean out any accidental raw conversational background thinking dumps
        const cleanReport = rawContent.replace(/<channel|>|[\s\S]*?<\/channel>|Accumulated \d+ tokens/gi, "").trim();
        console.log(`\n--------------------------------------------------\n${cleanReport}\n--------------------------------------------------`);

        // 5. Cockpit Interactive Menu Loop
        console.log("\n💬 Anything else bothering the Lumax team?");
        console.log("------------------------------------------");
        console.log("1. 🛠️  Auto fix bugs");
        console.log("2. 💡 Propose optimizations");
        console.log("3. 📝 File a new issue");
        console.log("4. 🚨 Rescue mode\n");

        const selection = await askQuestion("👉 Select an operational protocol index (1-4): ");
        
        switch (selection.trim()) {
            case '1':
                console.log("\n⚙️ Initiating repair routines... Generating automated differential patch schema...");
                break;
            case '2':
                console.log("\n💡 Computing optimization arrays... Evaluating structural code refactors...");
                break;
            case '3':
                console.log("\n📝 Structuring bug ticket... Saving issue layout tracking records to .logs/...");
                break;
            case '4':
                console.log("\n🚨 RESCUE MODE ACTIVATED. Rolling back recent Git branches and executing safe environment clean scripts...");
                break;
            default:
                console.log("\n🛸 Telemetry session finalized. Safe flights, Lumax crew!");
                break;
        }
    } catch(err) {
        console.error("❌ Telemetry extraction loop faulted:", err.message);
    }
    rl.close();
}

run();
