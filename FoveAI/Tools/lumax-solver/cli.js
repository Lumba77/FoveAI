#!/usr/bin/env node
import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import readline from 'readline';

const WORKER_URL = "https://workers.dev";
const SECRET = "your_secure_env_token_here";

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

async function captureAndSolve() {
    console.log("🚀 Lumax-Solver active. Analyzing directory snapshot...");

    // 1. Gather a snapshot of file structures in the current working directory
    const files = fs.readdirSync(process.cwd())
        .filter(f => !['node_modules', '.git', '.venv'].includes(f));

    // 2. Read the latest terminal crash logs (e.g., from an npm debug file or standard input)
    let terminalLog = "Insert captured or passed error stream here";
    
    console.log("🧠 Sending snapshot to Cloudflare Edge Engine...");

    // 3. Securely transmit payload to the Cloudflare Worker via HTTP POST
    try {
        const response = await fetch(WORKER_URL, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${SECRET}`,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ currentDirFiles: files, terminalLog })
        });

        const actionPlan = await response.json();
        
        console.log(`\n💡 Analysis: ${actionPlan.explanation}\n`);

        // 4. Prompt user to authorize the proposed automated changes
        rl.question("🤖 Apply suggested fixes and run correction commands? (y/n): ", (answer) => {
            if (answer.toLowerCase() === 'y') {
                
                // Execute file edits
                if (actionPlan.fileEdits) {
                    actionPlan.fileEdits.forEach(edit => {
                        const fullPath = path.join(process.cwd(), edit.filePath);
                        fs.writeFileSync(fullPath, edit.content, 'utf-8');
                        console.log(`📝 Corrected: ${edit.filePath}`);
                    });
                }

                // Run system terminal patch commands
                if (actionPlan.commands) {
                    actionPlan.commands.forEach(cmd => {
                        console.log(`⚙️ Executing: ${cmd}`);
                        try {
                            execSync(cmd, { stdio: 'inherit' });
                        } catch (e) {
                            console.error(`❌ Command failed: ${cmd}`);
                        }
                    });
                }
                console.log("✅ Resolution sequence completed.");
            } else {
                console.log("❌ Execution aborted by user.");
            }
            rl.close();
            process.exit(0);
        });

    } catch (error) {
        console.error("❌ Cloudflare communication error:", error.message);
        rl.close();
        process.exit(1);
    }
}

captureAndSolve();
