#!/usr/bin/env node
/**
 * XRL Benchmark — Local Inference Benchmark
 *
 * Takes a test file and a set of questions, runs each question twice
 * (once with raw code, once with XRL skeleton), compares response
 * quality (token count, inference time, compression), and outputs
 * a markdown report.
 *
 * Usage:
 *   node xrl-benchmark-local.cjs --file service.py --questions questions.json
 *   node xrl-benchmark-local.cjs --file service.py --questions "What does this do?,Find bugs,Explain the architecture"
 *   node xrl-benchmark-local.cjs --file service.py --questions questions.json --output report.md
 *   node xrl-benchmark-local.cjs --file service.py --questions questions.json --dry-run
 *
 * Options:
 *   --file <path>       Source file to analyze (required)
 *   --questions <str>   Comma-separated questions or path to JSON array file
 *   --depths <str>      Comma-separated depth levels to test (default: "1,2,3")
 *   --model <path>      Path to GGUF model file
 *   --llama-path <str>  Path to llama-cli executable
 *   --lm-studio-url     LM Studio API URL (default: http://localhost:1234)
 *   --use-lm-studio     Force use LM Studio API
 *   --max-tokens <n>    Max tokens for model response (default: 1024)
 *   --temperature <f>   Temperature for model (default: 0.5)
 *   --output <path>     Write markdown report to file
 *   --dry-run           Run benchmark without calling a model (stats only)
 *   --verbose           Show detailed output
 *
 * Questions file format (JSON):
 *   ["What does this module do?", "Find potential bugs", "Explain the architecture"]
 *   or
 *   [
 *     { "question": "What does this do?", "category": "understanding" },
 *     { "question": "Find bugs", "category": "analysis" }
 *   ]
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// ─── Module Paths ─────────────────────────────────────────────────

const XRL_PATH = path.join(__dirname, 'xrl.cjs');

// ─── CLI Argument Parsing ────────────────────────────────────────

const args = process.argv.slice(2);
let filePath = null;
let questionsInput = null;
let depths = [1, 2, 3];
let modelPath = null;
let llamaPath = null;
let lmStudioUrl = 'http://localhost:1234';
let useLmStudio = false;
let maxTokens = 1024;
let temperature = 0.5;
let outputPath = null;
let dryRun = false;
let verbose = false;

for (let i = 0; i < args.length; i++) {
    if (args[i] === '--file' && i + 1 < args.length) {
        filePath = args[i + 1];
        i++;
    } else if (args[i] === '--questions' && i + 1 < args.length) {
        questionsInput = args[i + 1];
        i++;
    } else if (args[i] === '--depths' && i + 1 < args.length) {
        depths = args[i + 1].split(',').map(Number).filter(n => !isNaN(n) && n >= 0 && n <= 3);
        if (depths.length === 0) depths = [1, 2, 3];
        i++;
    } else if (args[i] === '--model' && i + 1 < args.length) {
        modelPath = args[i + 1];
        i++;
    } else if (args[i] === '--llama-path' && i + 1 < args.length) {
        llamaPath = args[i + 1];
        i++;
    } else if (args[i] === '--lm-studio-url' && i + 1 < args.length) {
        lmStudioUrl = args[i + 1].replace(/\/+$/, '');
        i++;
    } else if (args[i] === '--use-lm-studio') {
        useLmStudio = true;
    } else if (args[i] === '--max-tokens' && i + 1 < args.length) {
        maxTokens = parseInt(args[i + 1], 10);
        i++;
    } else if (args[i] === '--temperature' && i + 1 < args.length) {
        temperature = parseFloat(args[i + 1]);
        i++;
    } else if (args[i] === '--output' && i + 1 < args.length) {
        outputPath = args[i + 1];
        i++;
    } else if (args[i] === '--dry-run') {
        dryRun = true;
    } else if (args[i] === '--verbose') {
        verbose = true;
    }
}

// ─── Validation ──────────────────────────────────────────────────

if (!filePath) {
    console.error('Error: No source file provided. Use --file <path>');
    console.error('');
    console.error('Usage:');
    console.error('  node xrl-benchmark-local.cjs --file service.py --questions "Q1?,Q2?"');
    console.error('  node xrl-benchmark-local.cjs --file service.py --questions questions.json');
    process.exit(1);
}

if (!fs.existsSync(filePath)) {
    console.error(`Error: File not found: ${filePath}`);
    process.exit(1);
}

if (!questionsInput) {
    console.error('Error: No questions provided. Use --questions <str> or --questions <file.json>');
    process.exit(1);
}

// ─── Helper Functions ────────────────────────────────────────────

/**
 * Count approximate tokens (1 token ~= 4 chars)
 */
function countTokens(text) {
    return Math.ceil(text.length / 4);
}

/**
 * Get file extension for language detection
 */
function getLanguage(filePath) {
    const ext = path.extname(filePath).toLowerCase();
    const langMap = {
        '.py': 'python', '.ts': 'typescript', '.tsx': 'typescript',
        '.js': 'typescript', '.jsx': 'typescript', '.cjs': 'typescript', '.mjs': 'typescript',
        '.go': 'go', '.java': 'java', '.rs': 'rust', '.cs': 'csharp', '.kt': 'kotlin',
        '.html': 'html', '.htm': 'html',
        '.md': 'markdown', '.markdown': 'markdown',
        '.css': 'css', '.scss': 'css', '.less': 'css',
        '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml', '.xml': 'xml', '.svg': 'xml'
    };
    return langMap[ext] || 'unknown';
}

/**
 * Parse questions input (comma-separated string or JSON file)
 */
function parseQuestions(input) {
    // Check if it's a file path
    if (fs.existsSync(input)) {
        const content = fs.readFileSync(input, 'utf8');
        const parsed = JSON.parse(content);
        if (Array.isArray(parsed)) {
            return parsed.map((item, i) => {
                if (typeof item === 'string') {
                    return { question: item, category: 'general', id: `q${i + 1}` };
                }
                return {
                    question: item.question || item.text || String(item),
                    category: item.category || 'general',
                    id: item.id || `q${i + 1}`
                };
            });
        }
        throw new Error('Questions file must contain a JSON array');
    }

    // Treat as comma-separated string
    return input.split(',').map((q, i) => ({
        question: q.trim(),
        category: 'general',
        id: `q${i + 1}`
    })).filter(q => q.question.length > 0);
}

/**
 * Run XRL skeletonization on a file at a given depth
 * Returns { skeleton, stats }
 */
function runSkeletonization(filePath, depth) {
    try {
        const result = execSync(
            `node "${XRL_PATH}" "${filePath}" --depth ${depth} --json`,
            { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }
        );
        const data = JSON.parse(result.trim());

        return {
            skeleton: data.skeleton.content,
            stats: {
                originalTokens: data.original.tokens,
                skeletonTokens: data.skeleton.tokens,
                reduction: data.skeleton.reduction,
                compressionRatio: data.original.tokens / data.skeleton.tokens,
                originalLines: data.original.lines,
                originalChars: data.original.chars
            },
            raw: data
        };
    } catch (err) {
        throw new Error(`XRL skeletonization failed at depth ${depth}: ${err.message}`);
    }
}

/**
 * Build the XRL prompt
 */
function buildXrlPrompt(skeletonContent, userPrompt, language) {
    return [
        `You are analyzing source code. Below is an XRL (X-Ray Language) skeleton of the code.`,
        `The skeleton shows the structure: imports, function signatures, type definitions, and key identifiers.`,
        `Implementation bodies marked with @flesh have been stripped for brevity.`,
        ``,
        `Language: ${language || 'unknown'}`,
        `--- CODE SKELETON ---`,
        skeletonContent,
        `--- END CODE SKELETON ---`,
        ``,
        `User question: ${userPrompt}`,
        ``,
        `Please answer based on the code structure shown above.`
    ].join('\n');
}

/**
 * Build the raw (full code) prompt
 */
function buildRawPrompt(sourceContent, userPrompt, language) {
    return [
        `You are analyzing source code. Below is the full source code.`,
        ``,
        `Language: ${language || 'unknown'}`,
        `--- FULL CODE ---`,
        sourceContent,
        `--- END CODE ---`,
        ``,
        `User question: ${userPrompt}`,
        ``,
        `Please answer based on the code shown above.`
    ].join('\n');
}

/**
 * Detect available inference backend
 */
function detectBackend() {
    if (useLmStudio) {
        return { type: 'lm-studio', path: lmStudioUrl };
    }

    if (llamaPath) {
        if (fs.existsSync(llamaPath)) {
            return { type: 'llama-cli', path: llamaPath };
        }
        console.warn(`[WARN] Specified llama path not found: ${llamaPath}`);
    }

    const commonPaths = [
        'llama-cli',
        'llama-cli.exe',
        path.join('C:', 'Program Files', 'llama.cpp', 'llama-cli.exe'),
        path.join('C:', 'llama.cpp', 'llama-cli.exe'),
        path.join(process.env.LOCALAPPDATA || 'C:\\Users\\Public', 'llama.cpp', 'llama-cli.exe')
    ];

    for (const p of commonPaths) {
        try {
            const result = execSync(`where ${p} 2>nul || which ${p} 2>/dev/null`, {
                encoding: 'utf8',
                stdio: ['pipe', 'pipe', 'ignore']
            }).trim();
            if (result) {
                return { type: 'llama-cli', path: result.split('\n')[0].trim() };
            }
        } catch (e) { /* not found */ }
    }

    try {
        const result = execSync(
            `curl -s -o nul -w "%{http_code}" http://localhost:8080/health 2>nul || curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health 2>/dev/null`,
            { encoding: 'utf8', timeout: 2000 }
        ).trim();
        if (result === '200') {
            return { type: 'llama-server', path: 'http://localhost:8080' };
        }
    } catch (e) { /* not available */ }

    try {
        const result = execSync(
            `curl -s -o nul -w "%{http_code}" ${lmStudioUrl}/v1/models 2>nul || curl -s -o /dev/null -w "%{http_code}" ${lmStudioUrl}/v1/models 2>/dev/null`,
            { encoding: 'utf8', timeout: 2000 }
        ).trim();
        if (result === '200') {
            return { type: 'lm-studio', path: lmStudioUrl };
        }
    } catch (e) { /* not available */ }

    return { type: null, path: null };
}

/**
 * Call LM Studio API
 */
function callLmStudio(promptText, options = {}) {
    const {
        maxTokens = 1024,
        temperature = 0.5,
        apiUrl = 'http://localhost:1234'
    } = options;

    const http = require('http');
    const url = new URL('/v1/chat/completions', apiUrl);

    const body = JSON.stringify({
        model: 'local-model',
        messages: [
            { role: 'user', content: promptText }
        ],
        max_tokens: maxTokens,
        temperature: temperature,
        stream: false
    });

    return new Promise((resolve, reject) => {
        const req = http.request({
            hostname: url.hostname,
            port: url.port,
            path: url.pathname,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(body)
            },
            timeout: 120000
        }, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    const parsed = JSON.parse(data);
                    if (parsed.choices && parsed.choices.length > 0) {
                        resolve(parsed.choices[0].message.content.trim());
                    } else {
                        reject(new Error(`Unexpected response: ${data}`));
                    }
                } catch (e) {
                    reject(new Error(`Failed to parse response: ${e.message}`));
                }
            });
        });

        req.on('error', reject);
        req.on('timeout', () => {
            req.destroy();
            reject(new Error('Request timed out'));
        });

        req.write(body);
        req.end();
    });
}

/**
 * Call llama-cli
 */
function callLlamaCli(modelPath, promptText, options = {}) {
    const {
        maxTokens = 1024,
        temperature = 0.5,
        llamaExe = 'llama-cli'
    } = options;

    if (!fs.existsSync(modelPath)) {
        throw new Error(`Model file not found: ${modelPath}`);
    }

    const args = [
        '-m', `"${modelPath}"`,
        '--prompt', `"${promptText.replace(/"/g, '\\"')}"`,
        '-n', String(maxTokens),
        '--temp', String(temperature),
        '--no-display-prompt',
        '-ngl', '99'
    ];

    try {
        const result = execSync(
            `"${llamaExe}" ${args.join(' ')}`,
            { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024, timeout: 120000 }
        );
        return result.trim();
    } catch (err) {
        throw new Error(`llama-cli failed: ${err.message}`);
    }
}

/**
 * Call llama-server API
 */
function callLlamaServer(promptText, options = {}) {
    const {
        maxTokens = 1024,
        temperature = 0.5,
        serverUrl = 'http://localhost:8080'
    } = options;

    const http = require('http');
    const url = new URL('/completion', serverUrl);

    const body = JSON.stringify({
        prompt: promptText,
        n_predict: maxTokens,
        temperature: temperature,
        stream: false
    });

    return new Promise((resolve, reject) => {
        const req = http.request({
            hostname: url.hostname,
            port: url.port,
            path: url.pathname,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(body)
            },
            timeout: 120000
        }, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    const parsed = JSON.parse(data);
                    if (parsed.content) {
                        resolve(parsed.content.trim());
                    } else {
                        reject(new Error(`Unexpected response: ${data}`));
                    }
                } catch (e) {
                    reject(new Error(`Failed to parse response: ${e.message}`));
                }
            });
        });

        req.on('error', reject);
        req.on('timeout', () => {
            req.destroy();
            reject(new Error('Request timed out'));
        });

        req.write(body);
        req.end();
    });
}

/**
 * Call the model with a prompt
 */
async function callModel(promptText, options = {}) {
    const backend = detectBackend();

    if (!backend.type) {
        throw new Error('No local inference backend detected');
    }

    switch (backend.type) {
        case 'llama-cli':
            return callLlamaCli(modelPath || backend.path, promptText, {
                maxTokens: options.maxTokens || maxTokens,
                temperature: options.temperature || temperature,
                llamaExe: backend.path
            });

        case 'llama-server':
            return await callLlamaServer(promptText, {
                maxTokens: options.maxTokens || maxTokens,
                temperature: options.temperature || temperature,
                serverUrl: backend.path
            });

        case 'lm-studio':
            return await callLmStudio(promptText, {
                maxTokens: options.maxTokens || maxTokens,
                temperature: options.temperature || temperature,
                apiUrl: backend.path
            });

        default:
            throw new Error(`Unknown backend type: ${backend.type}`);
    }
}

/**
 * Run a single benchmark iteration for one question at one depth
 */
async function runIteration(question, sourceContent, filePath, depth, language) {
    const result = {
        question: question.question,
        category: question.category,
        id: question.id,
        depth,
        xrl: null,
        raw: null,
        error: null
    };

    try {
        // ── XRL skeletonization ──
        const xrlResult = runSkeletonization(filePath, depth);
        const xrlPrompt = buildXrlPrompt(xrlResult.skeleton, question.question, language);
        const rawPrompt = buildRawPrompt(sourceContent, question.question, language);

        result.xrl = {
            skeletonTokens: xrlResult.stats.skeletonTokens,
            promptTokens: countTokens(xrlPrompt),
            compressionRatio: xrlResult.stats.compressionRatio,
            reduction: xrlResult.stats.reduction
        };

        result.raw = {
            promptTokens: countTokens(rawPrompt)
        };

        // ── Model calls (skip if dry run) ──
        if (!dryRun) {
            const backend = detectBackend();
            if (backend.type) {
                // XRL inference
                const xrlStart = Date.now();
                const xrlResponse = await callModel(xrlPrompt, { maxTokens, temperature });
                result.xrl.responseTokens = countTokens(xrlResponse);
                result.xrl.inferenceTime = ((Date.now() - xrlStart) / 1000).toFixed(1);
                result.xrl.response = xrlResponse;

                // Raw inference
                const rawStart = Date.now();
                const rawResponse = await callModel(rawPrompt, { maxTokens, temperature });
                result.raw.responseTokens = countTokens(rawResponse);
                result.raw.inferenceTime = ((Date.now() - rawStart) / 1000).toFixed(1);
                result.raw.response = rawResponse;
            } else {
                result.error = 'No inference backend available';
            }
        }
    } catch (err) {
        result.error = err.message;
    }

    return result;
}

/**
 * Generate markdown report
 */
function generateReport(results, sourceFile, language, originalTokens, originalLines) {
    const lines = [];
    const timestamp = new Date().toISOString().replace('T', ' ').slice(0, 19);

    lines.push(`# XRL Benchmark Report`);
    lines.push(``);
    lines.push(`**Generated:** ${timestamp}`);
    lines.push(`**Source:** \`${sourceFile}\``);
    lines.push(`**Language:** ${language}`);
    lines.push(`**Original size:** ${originalTokens} tokens (${originalLines} lines)`);
    lines.push(`**Model:** ${modelPath || 'auto-detect'}`);
    lines.push(`**Max tokens:** ${maxTokens} | **Temperature:** ${temperature}`);
    lines.push(``);

    // ── Summary Table ──
    lines.push(`## Summary`);
    lines.push(``);
    lines.push(`| Depth | Question | XRL Prompt | Raw Prompt | Compression | XRL Time | Raw Time | XRL Resp | Raw Resp |`);
    lines.push(`|-------|----------|-----------:|-----------:|------------:|---------:|---------:|---------:|---------:|`);

    for (const r of results) {
        if (r.error) {
            lines.push(`| ${r.depth} | ${r.question.slice(0, 40)} | — | — | — | — | — | — | **ERROR: ${r.error}** |`);
            continue;
        }
        const xrlPrompt = r.xrl ? r.xrl.promptTokens : '—';
        const rawPrompt = r.raw ? r.raw.promptTokens : '—';
        const compression = r.xrl ? r.xrl.compressionRatio.toFixed(2) + 'x' : '—';
        const xrlTime = r.xrl && r.xrl.inferenceTime ? r.xrl.inferenceTime + 's' : '—';
        const rawTime = r.raw && r.raw.inferenceTime ? r.raw.inferenceTime + 's' : '—';
        const xrlResp = r.xrl && r.xrl.responseTokens ? r.xrl.responseTokens : '—';
        const rawResp = r.raw && r.raw.responseTokens ? r.raw.responseTokens : '—';
        lines.push(`| ${r.depth} | ${r.question.slice(0, 40)} | ${xrlPrompt} | ${rawPrompt} | ${compression} | ${xrlTime} | ${rawTime} | ${xrlResp} | ${rawResp} |`);
    }

    lines.push(``);

    // ── Per-Depth Aggregates ──
    const depthAgg = {};
    for (const r of results) {
        if (r.error) continue;
        if (!depthAgg[r.depth]) {
            depthAgg[r.depth] = {
                count: 0,
                totalXrlPromptTokens: 0,
                totalRawPromptTokens: 0,
                totalXrlTime: 0,
                totalRawTime: 0,
                totalXrlRespTokens: 0,
                totalRawRespTokens: 0,
                totalCompression: 0
            };
        }
        const d = depthAgg[r.depth];
        d.count++;
        d.totalXrlPromptTokens += r.xrl.promptTokens;
        d.totalRawPromptTokens += r.raw.promptTokens;
        d.totalCompression += r.xrl.compressionRatio;
        if (r.xrl.inferenceTime) d.totalXrlTime += parseFloat(r.xrl.inferenceTime);
        if (r.raw.inferenceTime) d.totalRawTime += parseFloat(r.raw.inferenceTime);
        if (r.xrl.responseTokens) d.totalXrlRespTokens += r.xrl.responseTokens;
        if (r.raw.responseTokens) d.totalRawRespTokens += r.raw.responseTokens;
    }

    lines.push(`## Per-Depth Averages`);
    lines.push(``);
    lines.push(`| Depth | Questions | Avg XRL Prompt | Avg Raw Prompt | Avg Compression | Avg XRL Time | Avg Raw Time | Avg XRL Resp | Avg Raw Resp |`);
    lines.push(`|-------|----------:|---------------:|---------------:|-----------------:|-------------:|-------------:|-------------:|-------------:|`);

    for (const depth of Object.keys(depthAgg).sort()) {
        const d = depthAgg[depth];
        const avgXrlPrompt = (d.totalXrlPromptTokens / d.count).toFixed(0);
        const avgRawPrompt = (d.totalRawPromptTokens / d.count).toFixed(0);
        const avgCompression = (d.totalCompression / d.count).toFixed(2) + 'x';
        const avgXrlTime = d.totalXrlTime > 0 ? (d.totalXrlTime / d.count).toFixed(1) + 's' : '—';
        const avgRawTime = d.totalRawTime > 0 ? (d.totalRawTime / d.count).toFixed(1) + 's' : '—';
        const avgXrlResp = d.totalXrlRespTokens > 0 ? (d.totalXrlRespTokens / d.count).toFixed(0) : '—';
        const avgRawResp = d.totalRawRespTokens > 0 ? (d.totalRawRespTokens / d.count).toFixed(0) : '—';
        lines.push(`| ${depth} | ${d.count} | ${avgXrlPrompt} | ${avgRawPrompt} | ${avgCompression} | ${avgXrlTime} | ${avgRawTime} | ${avgXrlResp} | ${avgRawResp} |`);
    }

    lines.push(``);

    // ── Per-Question Details ──
    lines.push(`## Per-Question Details`);
    lines.push(``);

    for (const r of results) {
        lines.push(`### ${r.id}: ${r.question}`);
        lines.push(``);
        lines.push(`**Category:** ${r.category} | **Depth:** ${r.depth}`);
        lines.push(``);

        if (r.error) {
            lines.push(`**Error:** ${r.error}`);
            lines.push(``);
            continue;
        }

        lines.push(`| Metric | XRL | Raw |`);
        lines.push(`|--------|----:|----:|`);
        lines.push(`| Prompt tokens | ${r.xrl.promptTokens} | ${r.raw.promptTokens} |`);
        lines.push(`| Compression | ${r.xrl.compressionRatio.toFixed(2)}x | 1.00x |`);
        if (r.xrl.inferenceTime) {
            lines.push(`| Inference time | ${r.xrl.inferenceTime}s | ${r.raw.inferenceTime}s |`);
        }
        if (r.xrl.responseTokens) {
            lines.push(`| Response tokens | ${r.xrl.responseTokens} | ${r.raw.responseTokens} |`);
        }
        lines.push(``);

        if (r.xrl.response) {
            lines.push(`**XRL Response:**`);
            lines.push(``);
            lines.push('```');
            lines.push(r.xrl.response);
            lines.push('```');
            lines.push(``);
        }

        if (r.raw.response) {
            lines.push(`**Raw Response:**`);
            lines.push(``);
            lines.push('```');
            lines.push(r.raw.response);
            lines.push('```');
            lines.push(``);
        }

        lines.push(`---`);
        lines.push(``);
    }

    // ── Conclusions ──
    lines.push(`## Conclusions`);
    lines.push(``);

    // Calculate overall stats
    let totalXrlPrompt = 0, totalRawPrompt = 0, totalCompression = 0, count = 0;
    for (const r of results) {
        if (r.error) continue;
        totalXrlPrompt += r.xrl.promptTokens;
        totalRawPrompt += r.raw.promptTokens;
        totalCompression += r.xrl.compressionRatio;
        count++;
    }

    if (count > 0) {
        const avgCompression = (totalCompression / count).toFixed(2);
        const totalSavings = totalRawPrompt - totalXrlPrompt;
        const pctSavings = totalRawPrompt > 0 ? ((totalSavings / totalRawPrompt) * 100).toFixed(1) : '0.0';

        lines.push(`- **Average compression ratio:** ${avgCompression}x`);
        lines.push(`- **Total prompt token savings:** ${totalSavings} tokens (${pctSavings}% reduction)`);
        lines.push(`- **Depths tested:** ${depths.join(', ')}`);
        lines.push(`- **Questions:** ${results.length}`);
        lines.push(``);
        lines.push(`XRL skeletonization provides significant context reduction while preserving structural information,`);
        lines.push(`enabling the model to focus on architecture and patterns rather than implementation details.`);
    } else {
        lines.push(`- No successful benchmark runs completed.`);
        if (dryRun) {
            lines.push(`- This was a dry run. Use without --dry-run to call a model.`);
        }
    }

    lines.push(``);
    return lines.join('\n');
}

// ─── Main ────────────────────────────────────────────────────────

async function main() {
    // ── Read source ──
    const sourceContent = fs.readFileSync(filePath, 'utf8');
    const language = getLanguage(filePath);
    const originalTokens = countTokens(sourceContent);
    const originalLines = sourceContent.split('\n').length;

    // ── Parse questions ──
    const questions = parseQuestions(questionsInput);

    console.log(`\n╔══════════════════════════════════════════════╗`);
    console.log(`║     XRL Benchmark — Local Inference         ║`);
    console.log(`╚══════════════════════════════════════════════╝`);
    console.log(`\n📁 Source: ${filePath}`);
    console.log(`🔤 Language: ${language}`);
    console.log(`📊 Original: ${originalTokens} tokens (${originalLines} lines)`);
    console.log(`🔤 Questions: ${questions.length}`);
    console.log(`📏 Depths: ${depths.join(', ')}`);
    console.log(`🔤 Mode: ${dryRun ? 'DRY RUN (no model calls)' : 'FULL (with model calls)'}`);
    console.log(``);

    // ── Detect backend ──
    if (!dryRun) {
        const backend = detectBackend();
        if (backend.type) {
            console.log(`✅ Backend detected: ${backend.type} (${backend.path})`);
        } else {
            console.log(`⚠ No local inference backend detected. Running in stats-only mode.`);
            console.log(`  Install llama.cpp or start LM Studio to enable model calls.`);
            console.log(``);
        }
    }
    console.log(``);

    // ── Run benchmarks ──
    const allResults = [];

    for (const depth of depths) {
        console.log(`[Depth ${depth}] Running ${questions.length} questions...`);

        for (const q of questions) {
            if (verbose) {
                console.log(`  [${q.id}] "${q.question.slice(0, 50)}..."`);
            }

            const result = await runIteration(q, sourceContent, filePath, depth, language);
            allResults.push(result);

            if (result.error) {
                console.log(`  ⚠ ${q.id}: ${result.error}`);
            } else if (verbose) {
                const compression = result.xrl.compressionRatio.toFixed(2);
                console.log(`  ✓ ${q.id}: ${compression}x compression`);
            }
        }
    }

    // ── Generate report ──
    console.log(`\n📊 Generating report...`);
    const report = generateReport(allResults, filePath, language, originalTokens, originalLines);

    // ── Output ──
    if (outputPath) {
        fs.writeFileSync(outputPath, report, 'utf8');
        console.log(`📁 Report written: ${outputPath}`);
    }

    console.log(``);
    console.log(`═══════════════════════════════════════════════`);
    console.log(report);
    console.log(`\n💡 Benchmark complete.`);
}

// ─── Run ──────────────────────────────────────────────────────────

main().catch(err => {
    console.error(`Fatal error: ${err.message}`);
    process.exit(1);
});