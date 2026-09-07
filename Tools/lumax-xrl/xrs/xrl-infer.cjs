#!/usr/bin/env node
/**
 * XRL Infer — Local Inference Wrapper
 *
 * Takes a source file + prompt, runs XRL skeletonization, then calls a local
 * llama.cpp instance (or LM Studio API) with the skeletonized code + user prompt.
 *
 * Usage:
 *   node xrl-infer.cjs --model "F:\Lumax\Models\..." --file service.py --prompt "What does this do?"
 *   cat service.py | node xrl-infer.cjs --model "F:\Lumax\Models\..." --prompt "Find bugs"
 *   node xrl-infer.cjs --file service.py --prompt "Explain" --dry-run
 *   node xrl-infer.cjs --file service.py --prompt "Explain" --benchmark
 *
 * Options:
 *   --model <path>     Path to GGUF model file (for llama-cli)
 *   --file <path>      Source file to analyze
 *   --prompt <str>     User prompt / question about the code
 *   --depth <0-3>      Skeletonization depth (default: 2)
 *   --dry-run          Output XRL skeleton + prompt without calling a model
 *   --benchmark        Compare XRL vs raw (same prompt, both formats)
 *   --llama-path <str> Path to llama-cli executable (default: auto-detect)
 *   --lm-studio-url    LM Studio API URL (default: http://localhost:1234)
 *   --use-lm-studio    Force use LM Studio API instead of llama-cli
 *   --max-tokens <n>   Max tokens for model response (default: 2048)
 *   --temperature <f>  Temperature for model (default: 0.7)
 *   --verbose          Show detailed pipeline info
 */

const fs = require('fs');
const path = require('path');
const { execSync, spawn } = require('child_process');

// ─── Module Paths ─────────────────────────────────────────────────

const XRL_PATH = path.join(__dirname, 'xrl.cjs');
const XRS_PATH = path.join(__dirname, 'xrs.cjs');

// ─── CLI Argument Parsing ────────────────────────────────────────

const args = process.argv.slice(2);
let modelPath = null;
let filePath = null;
let prompt = null;
let depth = 2;
let dryRun = false;
let benchmark = false;
let llamaPath = null;
let lmStudioUrl = 'http://localhost:7272';
let lmStudioModel = 'qwen2.5-vl-7b-instruct';
let useLmStudio = false;
let maxTokens = 2048;
let temperature = 0.7;
let verbose = false;
let pipeMode = false;

for (let i = 0; i < args.length; i++) {
    if (args[i] === '--model' && i + 1 < args.length) {
        modelPath = args[i + 1];
        i++;
    } else if (args[i] === '--file' && i + 1 < args.length) {
        filePath = args[i + 1];
        i++;
    } else if (args[i] === '--prompt' && i + 1 < args.length) {
        prompt = args[i + 1];
        i++;
    } else if (args[i] === '--depth' && i + 1 < args.length) {
        depth = parseInt(args[i + 1], 10);
        if (isNaN(depth) || depth < 0 || depth > 3) {
            console.error('Error: --depth must be 0, 1, 2, or 3');
            process.exit(1);
        }
        i++;
    } else if (args[i] === '--dry-run') {
        dryRun = true;
    } else if (args[i] === '--benchmark') {
        benchmark = true;
    } else if (args[i] === '--llama-path' && i + 1 < args.length) {
        llamaPath = args[i + 1];
        i++;
    } else if (args[i] === '--lm-studio-url' && i + 1 < args.length) {
        lmStudioUrl = args[i + 1].replace(/\/+$/, '');
        i++;
    } else if (args[i] === '--use-lm-studio') {
        useLmStudio = true;
    } else if (args[i] === '--model-name' && i + 1 < args.length) {
        lmStudioModel = args[i + 1];
        i++;
    } else if (args[i] === '--max-tokens' && i + 1 < args.length) {
        maxTokens = parseInt(args[i + 1], 10);
        i++;
    } else if (args[i] === '--temperature' && i + 1 < args.length) {
        temperature = parseFloat(args[i + 1]);
        i++;
    } else if (args[i] === '--verbose') {
        verbose = true;
    }
}

// ─── Detect Pipe Mode ────────────────────────────────────────────

// Check if stdin has data (pipe mode)
const isPipeMode = !process.stdin.isTTY;

if (isPipeMode && !filePath) {
    pipeMode = true;
}

// ─── Validation ──────────────────────────────────────────────────

if (!filePath && !pipeMode) {
    console.error('Error: No source file provided. Use --file <path> or pipe input.');
    console.error('');
    console.error('Usage:');
    console.error('  node xrl-infer.cjs --model <path> --file <path> --prompt "question"');
    console.error('  cat file.js | node xrl-infer.cjs --model <path> --prompt "question"');
    console.error('  node xrl-infer.cjs --file <path> --prompt "question" --dry-run');
    process.exit(1);
}

if (!prompt) {
    console.error('Error: No prompt provided. Use --prompt "your question"');
    process.exit(1);
}

if (!dryRun && !benchmark && !modelPath && !useLmStudio) {
    console.error('Error: No model specified. Use --model <path> or --use-lm-studio');
    console.error('  Or use --dry-run to test the pipeline without calling a model.');
    process.exit(1);
}

if (filePath && !fs.existsSync(filePath)) {
    console.error(`Error: File not found: ${filePath}`);
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
 * Read source content (from file or stdin)
 */
function readSource() {
    if (pipeMode) {
        return fs.readFileSync(0, 'utf8'); // stdin
    }
    return fs.readFileSync(filePath, 'utf8');
}

/**
 * Run XRL skeletonization on source content
 * Returns { skeleton, stats, raw }
 */
function runSkeletonization(sourceContent, sourcePath, depth) {
    // Write source to temp file if in pipe mode
    let tempFile = null;
    let targetPath = sourcePath;

    if (pipeMode || !sourcePath) {
        tempFile = path.join(
            require('os').tmpdir(),
            `xrl-infer-${Date.now()}.tmp`
        );
        fs.writeFileSync(tempFile, sourceContent, 'utf8');
        targetPath = tempFile;
    }

    try {
        const result = execSync(
            `node "${XRL_PATH}" "${targetPath}" --depth ${depth} --json`,
            { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }
        );
        const data = JSON.parse(result.trim());

        // Clean up temp file
        if (tempFile) {
            try { fs.unlinkSync(tempFile); } catch (e) { /* ignore */ }
        }

        return {
            skeleton: data.skeleton.content,
            stats: {
                originalTokens: data.original.tokens,
                skeletonTokens: data.skeleton.tokens,
                reduction: data.skeleton.reduction,
                compressionRatio: data.original.tokens / data.skeleton.tokens
            },
            raw: data
        };
    } catch (err) {
        if (tempFile) {
            try { fs.unlinkSync(tempFile); } catch (e) { /* ignore */ }
        }
        throw new Error(`XRL skeletonization failed: ${err.message}`);
    }
}

/**
 * Detect available llama.cpp backend
 * Returns { type: 'llama-cli'|'llama-server'|'lm-studio'|null, path: string|null }
 */
function detectBackend() {
    // 1. Check if user specified LM Studio
    if (useLmStudio) {
        return { type: 'lm-studio', path: lmStudioUrl };
    }

    // 2. Check if user specified a custom llama path
    if (llamaPath) {
        if (fs.existsSync(llamaPath)) {
            return { type: 'llama-cli', path: llamaPath };
        }
        console.warn(`[WARN] Specified llama path not found: ${llamaPath}`);
    }

    // 3. Try to find llama-cli in PATH or common locations
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

    // 4. Try llama-server API on default port
    try {
        const result = execSync(
            `curl -s -o nul -w "%{http_code}" http://localhost:8080/health 2>nul || curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health 2>/dev/null`,
            { encoding: 'utf8', timeout: 2000 }
        ).trim();
        if (result === '200') {
            return { type: 'llama-server', path: 'http://localhost:8080' };
        }
    } catch (e) { /* not available */ }

    // 5. Try LM Studio API (check /api/v1/chat endpoint)
    try {
        const result = execSync(
            `curl -s -o nul -w "%{http_code}" ${lmStudioUrl}/api/v1/chat 2>nul || curl -s -o /dev/null -w "%{http_code}" ${lmStudioUrl}/api/v1/chat 2>/dev/null`,
            { encoding: 'utf8', timeout: 2000 }
        ).trim();
        if (result === '200' || result === '405') {
            return { type: 'lm-studio', path: lmStudioUrl };
        }
    } catch (e) { /* not available */ }

    return { type: null, path: null };
}

/**
 * Build the prompt for the model
 */
function buildPrompt(skeletonContent, userPrompt, language) {
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
 * Build a raw (non-skeletonized) prompt for benchmarking
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
 * Call llama-cli with a model and prompt
 */
function callLlamaCli(modelPath, promptText, options = {}) {
    const {
        maxTokens = 2048,
        temperature = 0.7,
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
        '-ngl', '99' // Use all GPU layers if available
    ];

    if (verbose) {
        console.log(`[VERBOSE] llama-cli ${args.join(' ')}`);
    }

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
 * Call LM Studio API (LM Studio Server format)
 * Endpoint: POST /api/v1/chat
 * Body: { model, system_prompt, input }
 * Response: { model_instance_id, output: [{ type: 'message', content }], stats }
 */
function callLmStudio(promptText, options = {}) {
    const {
        maxTokens = 2048,
        temperature = 0.7,
        apiUrl = 'http://localhost:7272'
    } = options;

    const http = require('http');
    const url = new URL('/api/v1/chat', apiUrl);

    // Use the model name from the loaded model or default
    const modelName = options.modelName || 'qwen2.5-vl-7b-instruct';
    const body = JSON.stringify({
        model: modelName,
        system_prompt: 'You are analyzing source code. Answer based on the code structure shown.',
        input: promptText
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
                    if (parsed.output && parsed.output.length > 0) {
                        resolve(parsed.output[0].content.trim());
                    } else {
                        reject(new Error(`LM Studio returned unexpected response: ${JSON.stringify(data)}`));
                    }
                } catch (e) {
                    reject(new Error(`Failed to parse LM Studio response: ${e.message}`));
                }
            });
        });

        req.on('error', reject);
        req.on('timeout', () => {
            req.destroy();
            reject(new Error('LM Studio request timed out'));
        });

        req.write(body);
        req.end();
    });
}

/**
 * Call llama-server API
 */
function callLlamaServer(promptText, options = {}) {
    const {
        maxTokens = 2048,
        temperature = 0.7,
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
                        reject(new Error(`llama-server returned unexpected response: ${data}`));
                    }
                } catch (e) {
                    reject(new Error(`Failed to parse llama-server response: ${e.message}`));
                }
            });
        });

        req.on('error', reject);
        req.on('timeout', () => {
            req.destroy();
            reject(new Error('llama-server request timed out'));
        });

        req.write(body);
        req.end();
    });
}

/**
 * Call the model with a prompt (auto-detect backend)
 */
async function callModel(promptText, options = {}) {
    const backend = detectBackend();

    if (!backend.type) {
        throw new Error(
            'No local inference backend detected.\n' +
            '  Install llama.cpp (https://github.com/ggerganov/llama.cpp) or\n' +
            '  Start LM Studio with local server on port 1234, or\n' +
            '  Use --dry-run to test the pipeline without a model.'
        );
    }

    if (verbose) {
        console.log(`[VERBOSE] Using backend: ${backend.type} (${backend.path})`);
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
                apiUrl: backend.path,
                modelName: lmStudioModel
            });

        default:
            throw new Error(`Unknown backend type: ${backend.type}`);
    }
}

/**
 * Run benchmark: compare XRL vs raw for the same prompt
 */
async function runBenchmark(sourceContent, sourcePath, userPrompt, depth) {
    const language = sourcePath ? getLanguage(sourcePath) : 'unknown';
    const originalTokens = countTokens(sourceContent);

    console.log(`\n╔══════════════════════════════════════════════╗`);
    console.log(`║     XRL Benchmark — Local Inference         ║`);
    console.log(`╚══════════════════════════════════════════════╝`);
    console.log(`\n📁 Source: ${sourcePath || '(pipe)'}`);
    console.log(`🔤 Language: ${language}`);
    console.log(`🔤 Prompt: "${userPrompt}"`);
    console.log(`📏 Depth: ${depth}`);
    console.log(`📊 Original: ${originalTokens} tokens`);
    console.log(``);

    // ── Run XRL skeletonization ──
    console.log(`[1/4] Running XRL skeletonization...`);
    const xrlResult = runSkeletonization(sourceContent, sourcePath, depth);
    const skeletonTokens = countTokens(xrlResult.skeleton);
    const compressionRatio = (originalTokens / skeletonTokens).toFixed(2);

    console.log(`      Skeleton: ${skeletonTokens} tokens (${compressionRatio}x compression)`);
    console.log(`      Reduction: ${xrlResult.stats.reduction}`);
    console.log(``);

    // ── Build prompts ──
    const xrlPrompt = buildPrompt(xrlResult.skeleton, userPrompt, language);
    const rawPrompt = buildRawPrompt(sourceContent, userPrompt, language);

    const xrlPromptTokens = countTokens(xrlPrompt);
    const rawPromptTokens = countTokens(rawPrompt);
    const promptCompression = (rawPromptTokens / xrlPromptTokens).toFixed(2);

    console.log(`[2/4] Prompt sizes:`);
    console.log(`      XRL prompt:  ${xrlPromptTokens} tokens`);
    console.log(`      Raw prompt:  ${rawPromptTokens} tokens`);
    console.log(`      Compression: ${promptCompression}x`);
    console.log(``);

    // ── Check if backend is available ──
    const backend = detectBackend();
    if (!backend.type) {
        console.log(`[3/4] ⚠ No local inference backend detected.`);
        console.log(`      Skipping model calls. Use --dry-run for skeleton-only output.`);
        console.log(``);
        console.log(`[4/4] Results:`);
        console.log(`\n📊 Benchmark Summary:`);
        console.log(`   Original tokens:  ${originalTokens}`);
        console.log(`   Skeleton tokens:  ${skeletonTokens}`);
        console.log(`   Compression:      ${compressionRatio}x`);
        console.log(`   Prompt reduction: ${promptCompression}x`);
        console.log(`   Status:           DRY RUN (no model called)`);
        return;
    }

    // ── Run XRL inference ──
    console.log(`[3/4] Running XRL inference (${backend.type})...`);
    const xrlStart = Date.now();
    let xrlResponse;
    try {
        xrlResponse = await callModel(xrlPrompt, { maxTokens, temperature });
    } catch (err) {
        xrlResponse = `[ERROR] ${err.message}`;
    }
    const xrlTime = ((Date.now() - xrlStart) / 1000).toFixed(1);
    const xrlResponseTokens = countTokens(xrlResponse);

    console.log(`      Response: ${xrlResponseTokens} tokens in ${xrlTime}s`);
    console.log(``);

    // ── Run raw inference ──
    console.log(`[4/4] Running raw inference (${backend.type})...`);
    const rawStart = Date.now();
    let rawResponse;
    try {
        rawResponse = await callModel(rawPrompt, { maxTokens, temperature });
    } catch (err) {
        rawResponse = `[ERROR] ${err.message}`;
    }
    const rawTime = ((Date.now() - rawStart) / 1000).toFixed(1);
    const rawResponseTokens = countTokens(rawResponse);

    console.log(`      Response: ${rawResponseTokens} tokens in ${rawTime}s`);
    console.log(``);

    // ── Results ──
    const timeSavings = rawTime - xrlTime;
    const tokenSavings = rawPromptTokens - xrlPromptTokens;

    console.log(`\n📊 Benchmark Results:`);
    console.log(`┌──────────────────────────┬──────────────┬──────────────┐`);
    console.log(`│ Metric                  │ XRL          │ Raw          │`);
    console.log(`├──────────────────────────┼──────────────┼──────────────┤`);
    console.log(`│ Prompt tokens           │ ${String(xrlPromptTokens).padStart(10)} │ ${String(rawPromptTokens).padStart(10)} │`);
    console.log(`│ Response tokens         │ ${String(xrlResponseTokens).padStart(10)} │ ${String(rawResponseTokens).padStart(10)} │`);
    console.log(`│ Inference time          │ ${xrlTime.padStart(9)}s │ ${rawTime.padStart(9)}s │`);
    console.log(`│ Compression ratio       │ ${compressionRatio.padStart(10)}x │ ${'1.00'.padStart(10)}x │`);
    console.log(`└──────────────────────────┴──────────────┴──────────────┘`);
    console.log(``);
    console.log(`💡 Savings: ${tokenSavings} fewer prompt tokens, ${timeSavings}s faster`);
    console.log(``);

    // ── Output responses ──
    console.log(`\n═══════════════════════════════════════════════`);
    console.log(`XRL Response (${xrlResponseTokens} tokens, ${xrlTime}s):`);
    console.log(`═══════════════════════════════════════════════`);
    console.log(xrlResponse);
    console.log(``);
    console.log(`═══════════════════════════════════════════════`);
    console.log(`Raw Response (${rawResponseTokens} tokens, ${rawTime}s):`);
    console.log(`═══════════════════════════════════════════════`);
    console.log(rawResponse);
}

// ─── Main ────────────────────────────────────────────────────────

async function main() {
    // ── Read source ──
    const sourceContent = readSource();
    const sourceName = filePath || '(pipe)';
    const language = filePath ? getLanguage(filePath) : 'unknown';
    const originalTokens = countTokens(sourceContent);

    if (verbose) {
        console.log(`[VERBOSE] Source: ${sourceName}`);
        console.log(`[VERBOSE] Language: ${language}`);
        console.log(`[VERBOSE] Original: ${originalTokens} tokens`);
        console.log(`[VERBOSE] Depth: ${depth}`);
        console.log(`[VERBOSE] Prompt: "${prompt}"`);
        console.log(``);
    }

    // ── Benchmark mode ──
    if (benchmark) {
        await runBenchmark(sourceContent, filePath, prompt, depth);
        return;
    }

    // ── Run XRL skeletonization ──
    if (verbose) {
        console.log(`[VERBOSE] Running XRL skeletonization at depth ${depth}...`);
    }

    let xrlResult;
    try {
        xrlResult = runSkeletonization(sourceContent, filePath, depth);
    } catch (err) {
        console.error(`Error: ${err.message}`);
        process.exit(1);
    }

    const skeletonTokens = countTokens(xrlResult.skeleton);
    const compressionRatio = (originalTokens / skeletonTokens).toFixed(2);

    // ── Context budget check: if skeleton is too large, auto-drop to depth 3 ──
    const MAX_SKELETON_TOKENS = 4096; // Conservative limit for 7B model context
    let effectiveDepth = depth;
    let effectiveSkeleton = xrlResult.skeleton;
    let effectiveStats = xrlResult.stats;

    if (skeletonTokens > MAX_SKELETON_TOKENS && depth < 3) {
        const newDepth = 3;
        if (verbose) {
            console.log(`[VERBOSE] Skeleton too large (${skeletonTokens} tokens > ${MAX_SKELETON_TOKENS} limit)`);
            console.log(`[VERBOSE] Auto-dropping to depth ${newDepth}...`);
        }
        try {
            const deeperResult = runSkeletonization(sourceContent, filePath, newDepth);
            effectiveDepth = newDepth;
            effectiveSkeleton = deeperResult.skeleton;
            effectiveStats = deeperResult.stats;
        } catch (err) {
            // Keep original if deeper fails
            if (verbose) {
                console.log(`[VERBOSE] Depth ${newDepth} failed, keeping depth ${depth}`);
            }
        }
    }

    // ── Build prompt ──
    const fullPrompt = buildPrompt(effectiveSkeleton, prompt, language);
    const promptTokens = countTokens(fullPrompt);

    // ── Output header ──
    console.log(`\n╔══════════════════════════════════════════════╗`);
    console.log(`║     XRL Infer — Local Inference             ║`);
    console.log(`╚══════════════════════════════════════════════╝`);
    console.log(`\n📁 Source: ${sourceName}`);
    console.log(`🔤 Language: ${language}`);
    console.log(`📏 Depth: ${['full', 'light', 'medium', 'deep'][effectiveDepth]} (${effectiveDepth})`);
    console.log(`📊 Original: ${originalTokens} tokens`);
    console.log(`📊 Skeleton: ${skeletonTokens} tokens (${compressionRatio}x compression)`);
    console.log(`📊 Reduction: ${effectiveStats.reduction}`);
    console.log(`📊 Prompt: ${promptTokens} tokens`);
    console.log(``);

    // ── Dry run: output skeleton + prompt ──
    if (dryRun) {
        console.log(`\n═══════════════════════════════════════════════`);
        console.log(`XRL Skeleton (depth ${effectiveDepth}):`);
        console.log(`═══════════════════════════════════════════════`);
        console.log(effectiveSkeleton);
        console.log(``);
        console.log(`═══════════════════════════════════════════════`);
        console.log(`Prompt (${promptTokens} tokens):`);
        console.log(`═══════════════════════════════════════════════`);
        console.log(fullPrompt);
        console.log(``);
        console.log(`💡 Dry run complete. No model was called.`);
        console.log(`   To run with a model, add --model <path> or --use-lm-studio`);
        return;
    }

    // ── Call model ──
    if (verbose) {
        console.log(`[VERBOSE] Calling model...`);
    }

    try {
        const response = await callModel(fullPrompt, { maxTokens, temperature });
        const responseTokens = countTokens(response);

        console.log(`\n═══════════════════════════════════════════════`);
        console.log(`Model Response (${responseTokens} tokens):`);
        console.log(`═══════════════════════════════════════════════`);
        console.log(response);
        console.log(``);
        console.log(`💡 ${compressionRatio}x compression via XRL skeletonization`);
    } catch (err) {
        console.error(`\nError calling model: ${err.message}`);
        console.error(``);
        console.error(`Fallback: XRL skeleton + prompt output for manual use:`);
        console.error(`═══════════════════════════════════════════════`);
        console.error(effectiveSkeleton);
        console.error(`═══════════════════════════════════════════════`);
        console.error(fullPrompt);
        process.exit(1);
    }
}

// ─── Run ──────────────────────────────────────────────────────────

main().catch(err => {
    console.error(`Fatal error: ${err.message}`);
    process.exit(1);
});