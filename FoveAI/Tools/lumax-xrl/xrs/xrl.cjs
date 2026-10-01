#!/usr/bin/env node
/**
 * XRL — Unified CLI for X-Ray Language Pipeline
 * 
 * Complete pipeline: read source → XRS skeletonize → tokenize → apply budget → serialize → output
 * 
 * Usage:
 *   node xrl.cjs <filepath> [options]
 * 
 * Options:
 *   --depth <0-3>     Skeletonization depth (default: 2)
 *   --json            Output as JSON
 *   --stats           Show token statistics only
 *   --expand <name>   Expand a specific block
 *   --budget <n>      Enforce token budget
 *   --output <path>   Write XRB binary to file
 *   --to-text         Convert XRB binary back to text
 *   --blocks          Show extracted blocks
 *   --validate        Run round-trip validation
 * 
 * Examples:
 *   node xrl.cjs service.py --depth 2 --json
 *   node xrl.cjs service.py --depth 2 --budget 500
 *   node xrl.cjs service.py --output service.xrb
 *   node xrl.cjs service.xrb --to-text
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// ─── Module Paths ─────────────────────────────────────────────────

const XRS_PATH = path.join(__dirname, 'xrs.cjs');
const TOKENIZER_PATH = path.join(__dirname, 'xrl-tokenizer.cjs');
const SERIALIZER_PATH = path.join(__dirname, 'xrl-serializer.cjs');
const BUDGET_PATH = path.join(__dirname, 'xrl-budget.cjs');

// ─── CLI Argument Parsing ────────────────────────────────────────

const args = process.argv.slice(2);
let filePath = null;
let depth = 2;
let outputJson = false;
let statsOnly = false;
let expandTarget = null;
let budget = null;
let outputPath = null;
let toText = false;
let showBlocks = false;
let runValidate = false;

for (let i = 0; i < args.length; i++) {
    if (args[i] === '--depth' && i + 1 < args.length) {
        depth = parseInt(args[i + 1], 10);
        if (isNaN(depth) || depth < 0 || depth > 3) {
            console.error('Error: --depth must be 0, 1, 2, or 3');
            process.exit(1);
        }
        i++;
    } else if (args[i] === '--json') {
        outputJson = true;
    } else if (args[i] === '--stats') {
        statsOnly = true;
    } else if (args[i] === '--expand' && i + 1 < args.length) {
        expandTarget = args[i + 1];
        i++;
    } else if (args[i] === '--budget' && i + 1 < args.length) {
        budget = parseInt(args[i + 1], 10);
        i++;
    } else if (args[i] === '--output' && i + 1 < args.length) {
        outputPath = args[i + 1];
        i++;
    } else if (args[i] === '--to-text') {
        toText = true;
    } else if (args[i] === '--blocks') {
        showBlocks = true;
    } else if (args[i] === '--validate') {
        runValidate = true;
    } else if (!args[i].startsWith('--')) {
        filePath = args[i];
    }
}

if (!filePath) {
    console.log('Usage: node xrl.cjs <filepath> [options]');
    console.log('');
    console.log('Options:');
    console.log('  --depth <0-3>     Skeletonization depth (default: 2)');
    console.log('  --json            Output as JSON');
    console.log('  --stats           Show token statistics only');
    console.log('  --expand <name>   Expand a specific block');
    console.log('  --budget <n>      Enforce token budget');
    console.log('  --output <path>   Write XRB binary to file');
    console.log('  --to-text         Convert XRB binary back to text');
    console.log('  --blocks          Show extracted blocks');
    console.log('  --validate        Run round-trip validation');
    process.exit(1);
}

if (!fs.existsSync(filePath)) {
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
        '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml', '.xml': 'xml', '.svg': 'xml',
        '.xrb': 'xrb'
    };
    return langMap[ext] || 'unknown';
}

/**
 * Run XRS skeletonizer
 */
function runSkeletonizer(filePath, depth) {
    const result = execSync(
        `node "${XRS_PATH}" "${filePath}" --depth ${depth} --json`,
        { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }
    );
    return JSON.parse(result.trim());
}

/**
 * Run tokenizer
 */
function runTokenizer(skeletonContent, depth) {
    const tokenizer = require(TOKENIZER_PATH);
    const tokens = tokenizer.tokenize(skeletonContent);
    return tokenizer.assignDepthMask(tokens, depth);
}

/**
 * Run serializer
 */
function runSerializer(tokens, options = {}) {
    const serializer = require(SERIALIZER_PATH);
    return serializer.serialize(tokens, options);
}

/**
 * Run budget enforcement
 */
function runBudget(tokens, budget) {
    const budgetModule = require(BUDGET_PATH);
    return budgetModule.enforceBudget(tokens, budget);
}

/**
 * Run XRS expand
 */
function runExpand(filePath, blockName) {
    const result = execSync(
        `node "${XRS_PATH}" "${filePath}" --depth ${depth} --expand "${blockName}" --json`,
        { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024 }
    );
    return JSON.parse(result.trim());
}

// ─── Main Pipeline ───────────────────────────────────────────────

function main() {
    const language = getLanguage(filePath);
    const fileName = path.basename(filePath);
    
    // ── Handle XRB to-text mode ──
    if (toText) {
        if (language !== 'xrb') {
            console.error('Error: --to-text requires an .xrb file');
            process.exit(1);
        }
        const serializer = require(SERIALIZER_PATH);
        const data = fs.readFileSync(filePath);
        const result = serializer.deserialize(data);
        const text = serializer.tokensToText(result.tokens, depth);
        
        if (outputJson) {
            console.log(JSON.stringify({
                file: fileName,
                depth,
                tokenCount: result.tokens.length,
                blockCount: result.blocks.length,
                text
            }, null, 2));
        } else {
            console.log(text);
        }
        return;
    }
    
    // ── Handle XRB validation mode ──
    if (runValidate && language === 'xrb') {
        const serializer = require(SERIALIZER_PATH);
        const data = fs.readFileSync(filePath);
        const result = serializer.deserialize(data);
        
        if (outputJson) {
            console.log(JSON.stringify({
                file: fileName,
                valid: true,
                version: result.header.version,
                defaultDepth: result.header.defaultDepth,
                tokenBudget: result.header.tokenBudget,
                blockCount: result.blocks.length,
                tokenCount: result.tokens.length,
                metadata: result.metadata
            }, null, 2));
        } else {
            console.log(`\n╔══════════════════════════════════════════════╗`);
            console.log(`║        XRL — XRB Validation                  ║`);
            console.log(`╚══════════════════════════════════════════════╝`);
            console.log(`\n📁 File: ${fileName}`);
            console.log(`📏 Version: ${result.header.version}`);
            console.log(`📏 Default Depth: ${result.header.defaultDepth}`);
            console.log(`💰 Token Budget: ${result.header.tokenBudget}`);
            console.log(`📦 Blocks: ${result.blocks.length}`);
            console.log(`🔤 Tokens: ${result.tokens.length}`);
            console.log(`\n📋 Blocks:`);
            for (const block of result.blocks) {
                console.log(`   ${block.name} (${block.type}, ${block.tokenCount} tokens)`);
            }
            if (Object.keys(result.metadata).length > 0) {
                console.log(`\n📋 Metadata:`);
                for (const [key, value] of Object.entries(result.metadata)) {
                    console.log(`   ${key}: ${value}`);
                }
            }
        }
        return;
    }
    
    // ── Read source file ──
    const content = fs.readFileSync(filePath, 'utf8');
    const originalLines = content.split('\n').length;
    const originalChars = content.length;
    const originalTokens = countTokens(content);
    
    // ── Step 1: XRS Skeletonize ──
    const skeletonData = runSkeletonizer(filePath, depth);
    const skeletonContent = skeletonData.skeleton.content;
    const skeletonTokens = skeletonData.skeleton.tokens;
    const textReduction = skeletonData.skeleton.reduction;
    
    // ── Step 2: Tokenize ──
    const tokens = runTokenizer(skeletonContent, depth);
    const tokenStats = require(TOKENIZER_PATH).getTokenStats(tokens);
    
    // ── Step 3: Extract blocks ──
    const blocks = require(TOKENIZER_PATH).extractBlocks(tokens);
    
    // ── Step 4: Apply budget (if specified) ──
    let budgetResult = null;
    let finalTokens = tokens;
    let finalDepth = depth;
    
    if (budget !== null) {
        budgetResult = runBudget(tokens, budget);
        finalTokens = budgetResult.tokens || tokens;
        finalDepth = budgetResult.depth;
    }
    
    // ── Step 5: Serialize to XRB ──
    const metadata = {
        source_file: fileName,
        language: language,
        created: new Date().toISOString(),
        original_size: String(originalChars),
        original_tokens: String(originalTokens),
        skeleton_tokens: String(skeletonTokens),
        compression_ratio: originalTokens > 0 ? (originalTokens / skeletonTokens).toFixed(2) : '1.00',
        tool_version: '1.0.0'
    };
    
    const binary = runSerializer(finalTokens, {
        depth: finalDepth,
        budget: budget || 0,
        blocks: blocks.map(b => ({
            name: b.name,
            type: b.type,
            startToken: b.startToken,
            endToken: b.endToken,
            depth: b.depth,
            annotation: 0
        })),
        metadata
    });
    
    // ── Write XRB output ──
    if (outputPath) {
        fs.writeFileSync(outputPath, binary);
    }
    
    // ── Handle expand mode ──
    if (expandTarget) {
        const expanded = runExpand(filePath, expandTarget);
        
        if (outputJson) {
            console.log(JSON.stringify({
                file: fileName,
                language,
                depth,
                original: { lines: originalLines, chars: originalChars, tokens: originalTokens },
                skeleton: { chars: skeletonContent.length, tokens: skeletonTokens, reduction: textReduction },
                binary: { size: binary.length, tokens: finalTokens.length },
                expansion: expanded.expansion,
                blocks: blocks.map(b => ({ name: b.name, type: b.type, tokenCount: b.tokens.length }))
            }, null, 2));
        } else {
            console.log(`\n╔══════════════════════════════════════════════╗`);
            console.log(`║        XRL — X-Ray Language Pipeline         ║`);
            console.log(`╚══════════════════════════════════════════════╝`);
            console.log(`\n📁 File: ${fileName}`);
            console.log(`🔤 Language: ${language}`);
            console.log(`📏 Depth: ${['full', 'light', 'medium', 'deep'][depth]} (${depth})`);
            console.log(`\n📊 Token Statistics:`);
            console.log(`   Original: ${originalTokens.toLocaleString()} tokens (${originalLines} lines)`);
            console.log(`   Skeleton: ${skeletonTokens.toLocaleString()} tokens (${textReduction})`);
            console.log(`   Binary:   ${finalTokens.length} tokens (${binary.length} bytes)`);
            console.log(`\n🔍 Expanded Block: ${expandTarget}`);
            console.log(expanded.expansion.content);
        }
        return;
    }
    
    // ── Output ──
    if (outputJson) {
        const result = {
            file: fileName,
            language,
            depth,
            original: {
                lines: originalLines,
                chars: originalChars,
                tokens: originalTokens
            },
            skeleton: {
                content: skeletonContent,
                chars: skeletonContent.length,
                tokens: skeletonTokens,
                reduction: textReduction
            },
            tokenizer: {
                tokens: finalTokens.length,
                byType: tokenStats.byType,
                byDepth: tokenStats.byDepth,
                estimatedBytes: tokenStats.estimatedBytes
            },
            binary: {
                size: binary.length,
                tokens: finalTokens.length,
                bytesPerToken: (binary.length / finalTokens.length).toFixed(2)
            },
            blocks: blocks.map(b => ({
                name: b.name,
                type: b.type,
                signature: b.signature,
                tokenCount: b.tokens.length
            }))
        };
        
        if (budgetResult) {
            result.budget = {
                target: budget,
                selectedDepth: budgetResult.depth,
                depthName: budgetResult.depthName,
                tokenCount: budgetResult.tokenCount,
                withinBudget: budgetResult.withinBudget,
                stripped: budgetResult.stripped
            };
        }
        
        if (outputPath) {
            result.output = {
                path: outputPath,
                size: binary.length
            };
        }
        
        console.log(JSON.stringify(result, null, 2));
    } else if (statsOnly) {
        const stats = {
            file: fileName,
            language,
            depth,
            originalLines,
            originalTokens,
            skeletonTokens,
            textReduction,
            binaryBytes: binary.length,
            binaryTokens: finalTokens.length,
            blockCount: blocks.length,
            bytesPerToken: (binary.length / finalTokens.length).toFixed(2)
        };
        
        if (budgetResult) {
            stats.budget = {
                target: budget,
                selectedDepth: budgetResult.depth,
                tokenCount: budgetResult.tokenCount,
                withinBudget: budgetResult.withinBudget
            };
        }
        
        console.log(JSON.stringify(stats));
    } else {
        // Human-readable output
        console.log(`\n╔══════════════════════════════════════════════╗`);
        console.log(`║        XRL — X-Ray Language Pipeline         ║`);
        console.log(`╚══════════════════════════════════════════════╝`);
        console.log(`\n📁 File: ${fileName}`);
        console.log(`🔤 Language: ${language}`);
        console.log(`📏 Depth: ${['full', 'light', 'medium', 'deep'][depth]} (${depth})`);
        
        console.log(`\n📊 Token Statistics:`);
        console.log(`   Original: ${originalTokens.toLocaleString()} tokens (${originalLines} lines)`);
        console.log(`   Skeleton: ${skeletonTokens.toLocaleString()} tokens (${textReduction})`);
        console.log(`   Binary:   ${finalTokens.length} tokens (${binary.length} bytes)`);
        console.log(`   Bytes/token: ${(binary.length / finalTokens.length).toFixed(2)}`);
        
        if (budgetResult) {
            console.log(`\n💰 Budget Enforcement:`);
            console.log(`   Target:       ${budget} tokens`);
            console.log(`   Selected:     ${budgetResult.depthName} (depth ${budgetResult.depth})`);
            console.log(`   Token count:  ${budgetResult.tokenCount}`);
            console.log(`   Within budget: ${budgetResult.withinBudget ? '✓' : '✗'}`);
            console.log(`   Stripped:     ${budgetResult.stripped} tokens`);
        }
        
        console.log(`\n📦 Blocks (${blocks.length}):`);
        for (const block of blocks) {
            console.log(`   ${block.type === 'function' ? 'ƒ' : '◈'} ${block.name} (${block.tokens.length} tokens)`);
        }
        
        console.log(`\n📦 Skeleton Output:`);
        console.log(skeletonContent);
        
        if (outputPath) {
            console.log(`\n📁 XRB written: ${outputPath} (${binary.length} bytes)`);
        }
        
        console.log(`\n💡 Tip: Use --json for machine-readable output`);
        console.log(`   Use --stats for token statistics only`);
        console.log(`   Use --budget <n> to enforce token budget`);
        console.log(`   Use --expand <name> to expand a specific block`);
        console.log(`   Use --output <path> to write XRB binary`);
    }
}

// ─── Run ──────────────────────────────────────────────────────────

main();