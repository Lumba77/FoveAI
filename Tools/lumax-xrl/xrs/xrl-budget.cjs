#!/usr/bin/env node
/**
 * XRL Budget — Token Budget Enforcement
 * 
 * Enforces token budgets by progressively stripping content at different depth levels.
 * Uses a progressive stripping strategy: flesh → detail → test → minimal
 * 
 * Usage:
 *   const budget = require('./xrl-budget.cjs');
 *   const result = budget.enforceBudget(tokens, 500);
 *   const depth = budget.suggestDepth(tokens, 500);
 */

const { filterByDepth, countTokens, getTokenStats, DEPTH_MASKS } = require('./xrl-tokenizer.cjs');

// ─── Depth Level Definitions ──────────────────────────────────────

const DEPTH_LEVELS = {
    0: { name: 'full', description: 'All code visible, including @flesh blocks' },
    1: { name: 'light', description: 'Imports, signatures, @keep, @detail visible. @flesh hidden.' },
    2: { name: 'medium', description: 'Imports, signatures, @keep visible. @detail and @flesh hidden.' },
    3: { name: 'deep', description: 'Only imports and public signatures visible.' }
};

const STRIPPING_ORDER = [
    { name: 'flesh', depth: 0, description: 'Implementation bodies, error handling, verbose patterns' },
    { name: 'detail', depth: 1, description: 'Non-critical logic, helpers, utilities' },
    { name: 'test', depth: 2, description: 'Test code (excluded from all skeletons)' },
    { name: 'minimal', depth: 3, description: 'Only imports and public signatures' }
];

// ─── Budget Enforcement ──────────────────────────────────────────

/**
 * Enforce a token budget by progressively stripping content
 * @param {Array<object>} tokens - Array of token objects
 * @param {number} budget - Maximum token count
 * @param {object} [options] - Options
 * @param {number} [options.startDepth] - Starting depth (default: 0)
 * @param {boolean} [options.returnFiltered] - Return filtered tokens (default: true)
 * @returns {object} Budget enforcement result
 */
function enforceBudget(tokens, budget, options = {}) {
    const { startDepth = 0, returnFiltered = true } = options;
    
    if (!tokens || tokens.length === 0) {
        return {
            success: false,
            error: 'No tokens provided',
            depth: startDepth,
            tokenCount: 0,
            budget,
            withinBudget: true,
            stripped: 0,
            remaining: 0
        };
    }
    
    // Calculate profile at each depth
    const profile = calculateDepthProfile(tokens);
    
    // Find the deepest level that fits within budget
    let selectedDepth = startDepth;
    let selectedTokens = tokens;
    
    for (let d = 3; d >= startDepth; d--) {
        const count = profile[d];
        if (count <= budget) {
            selectedDepth = d;
            selectedTokens = filterByDepth(tokens, d);
            break;
        }
    }
    
    // If even depth 3 doesn't fit, we need to strip further
    if (profile[3] > budget) {
        // Apply progressive stripping within depth 3
        const result = stripToFit(tokens, budget, 3);
        selectedDepth = result.depth;
        selectedTokens = result.tokens;
    }
    
    const remaining = selectedTokens.length;
    const stripped = tokens.length - remaining;
    const withinBudget = remaining <= budget;
    
    return {
        success: true,
        depth: selectedDepth,
        depthName: DEPTH_LEVELS[selectedDepth]?.name || 'unknown',
        tokenCount: remaining,
        budget,
        withinBudget,
        stripped,
        remaining,
        profile,
        tokens: returnFiltered ? selectedTokens : undefined,
        strippingApplied: stripped > 0 ? getStrippingDescription(selectedDepth) : 'none'
    };
}

/**
 * Strip tokens to fit within budget at a given depth
 * @param {Array<object>} tokens - Token array
 * @param {number} budget - Maximum token count
 * @param {number} depth - Depth level
 * @returns {object} { tokens, depth }
 */
function stripToFit(tokens, budget, depth) {
    let filtered = filterByDepth(tokens, depth);
    
    // If already within budget, return
    if (filtered.length <= budget) {
        return { tokens: filtered, depth };
    }
    
    // Progressive stripping: remove tokens by priority
    // Priority order (lowest first): flesh > detail > test > minimal
    const priorityOrder = [
        { type: 'FLESH', depth: 0 },
        { type: 'FLESH_MARKER', depth: 0 },
        { type: 'DETAIL', depth: 1 },
        { type: 'COMMENT', depth: 1 },
        { type: 'STRING', depth: 2 },
        { type: 'NUMBER', depth: 2 },
        { type: 'OPERATOR', depth: 2 },
        { type: 'ASSIGN', depth: 2 },
        { type: 'IDENT', depth: 2 },
        { type: 'MODIFIER', depth: 2 },
        { type: 'DECORATOR', depth: 2 },
        { type: 'BLOCK_OPEN', depth: 2 },
        { type: 'BLOCK_CLOSE', depth: 2 },
        { type: 'SEPARATOR', depth: 2 },
        { type: 'KEYWORD', depth: 2 },
        { type: 'ANNOTATION', depth: 2 },
        { type: 'DOC_COMMENT', depth: 2 },
        { type: 'FN_SIG', depth: 3 },
        { type: 'TYPE_DEF', depth: 3 },
        { type: 'IMPORT', depth: 3 },
        { type: 'EXPORT', depth: 3 },
        { type: 'KEEP', depth: 3 }
    ];
    
    // Group tokens by priority
    const grouped = {};
    for (const token of filtered) {
        const priority = priorityOrder.findIndex(p => p.type === token.type);
        const key = priority >= 0 ? priority : 999;
        if (!grouped[key]) grouped[key] = [];
        grouped[key].push(token);
    }
    
    // Start removing from lowest priority until within budget
    const sortedKeys = Object.keys(grouped).map(Number).sort((a, b) => b - a);
    const result = [];
    let remaining = budget;
    
    for (const key of sortedKeys) {
        const groupTokens = grouped[key];
        if (remaining <= 0) break;
        
        if (groupTokens.length <= remaining) {
            result.push(...groupTokens);
            remaining -= groupTokens.length;
        } else {
            // Take only what fits
            result.push(...groupTokens.slice(0, remaining));
            remaining = 0;
        }
    }
    
    return { tokens: result, depth: 3 };
}

/**
 * Get description of stripping applied
 */
function getStrippingDescription(depth) {
    switch (depth) {
        case 0: return 'No stripping (full depth)';
        case 1: return 'Stripped @flesh blocks';
        case 2: return 'Stripped @flesh and @detail blocks';
        case 3: return 'Stripped @flesh, @detail, and test code';
        default: return `Stripped to depth ${depth}`;
    }
}

// ─── Depth Profile ────────────────────────────────────────────────

/**
 * Calculate token count at each depth level
 * @param {Array<object>} tokens - Array of token objects
 * @returns {object} Token counts at depths 0-3
 */
function calculateDepthProfile(tokens) {
    const profile = { 0: 0, 1: 0, 2: 0, 3: 0 };
    
    for (const token of tokens) {
        for (let d = 0; d < 4; d++) {
            if (token.depthMask & (1 << d)) {
                profile[d]++;
            }
        }
    }
    
    return profile;
}

// ─── Depth Suggestion ────────────────────────────────────────────

/**
 * Suggest the optimal depth for a given token budget
 * @param {Array<object>} tokens - Array of token objects
 * @param {number} budget - Maximum token count
 * @param {object} [options] - Options
 * @param {number} [options.minDepth] - Minimum acceptable depth (default: 0)
 * @param {number} [options.maxDepth] - Maximum acceptable depth (default: 3)
 * @returns {object} Suggested depth and details
 */
function suggestDepth(tokens, budget, options = {}) {
    const { minDepth = 0, maxDepth = 3 } = options;
    
    const profile = calculateDepthProfile(tokens);
    
    // Find the deepest level that fits within budget
    for (let d = maxDepth; d >= minDepth; d--) {
        if (profile[d] <= budget) {
            return {
                depth: d,
                depthName: DEPTH_LEVELS[d]?.name || 'unknown',
                tokenCount: profile[d],
                budget,
                withinBudget: true,
                profile,
                description: DEPTH_LEVELS[d]?.description || ''
            };
        }
    }
    
    // Even max depth doesn't fit
    return {
        depth: maxDepth,
        depthName: DEPTH_LEVELS[maxDepth]?.name || 'unknown',
        tokenCount: profile[maxDepth],
        budget,
        withinBudget: false,
        profile,
        description: `Even depth ${maxDepth} (${DEPTH_LEVELS[maxDepth]?.name}) exceeds budget. Consider increasing budget or using stripToFit.`,
        excess: profile[maxDepth] - budget
    };
}

// ─── Budget Report ───────────────────────────────────────────────

/**
 * Get a comprehensive budget report
 * @param {Array<object>} tokens - Array of token objects
 * @param {number} [budget] - Optional budget to evaluate against
 * @returns {object} Budget report
 */
function getBudgetReport(tokens, budget) {
    const stats = getTokenStats(tokens);
    const profile = calculateDepthProfile(tokens);
    
    const report = {
        totalTokens: tokens.length,
        estimatedBinaryBytes: stats.estimatedBytes,
        depthProfile: {
            0: { name: 'full', count: profile[0], percentage: Math.round((profile[0] / tokens.length) * 100) + '%' },
            1: { name: 'light', count: profile[1], percentage: Math.round((profile[1] / tokens.length) * 100) + '%' },
            2: { name: 'medium', count: profile[2], percentage: Math.round((profile[2] / tokens.length) * 100) + '%' },
            3: { name: 'deep', count: profile[3], percentage: Math.round((profile[3] / tokens.length) * 100) + '%' }
        },
        byType: stats.byType,
        strippingOptions: STRIPPING_ORDER.map(s => ({
            ...s,
            tokensAtDepth: profile[s.depth],
            savings: tokens.length - profile[s.depth],
            savingsPercent: Math.round(((tokens.length - profile[s.depth]) / tokens.length) * 100) + '%'
        }))
    };
    
    if (budget !== undefined) {
        const suggestion = suggestDepth(tokens, budget);
        report.budget = budget;
        report.suggestion = suggestion;
        report.enforcement = enforceBudget(tokens, budget);
    }
    
    return report;
}

// ─── CLI Mode ─────────────────────────────────────────────────────

/**
 * Run budget enforcement in CLI mode
 */
function runCLI() {
    const args = process.argv.slice(2);
    let filePath = null;
    let budget = null;
    let depth = null;
    let outputJson = false;
    let action = 'report'; // report, enforce, suggest
    
    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--budget' && i + 1 < args.length) {
            budget = parseInt(args[i + 1], 10);
            i++;
        } else if (args[i] === '--depth' && i + 1 < args.length) {
            depth = parseInt(args[i + 1], 10);
            i++;
        } else if (args[i] === '--json') {
            outputJson = true;
        } else if (args[i] === '--enforce') {
            action = 'enforce';
        } else if (args[i] === '--suggest') {
            action = 'suggest';
        } else if (!args[i].startsWith('--')) {
            filePath = args[i];
        }
    }
    
    if (!filePath) {
        console.error('Usage: node xrl-budget.cjs <filepath> [options]');
        console.error('  --budget <n>     Token budget');
        console.error('  --depth <0-3>    Depth level');
        console.error('  --json           Output as JSON');
        console.error('  --enforce        Enforce budget (strip tokens)');
        console.error('  --suggest        Suggest optimal depth');
        process.exit(1);
    }
    
    const fs = require('fs');
    const path = require('path');
    const { tokenize, assignDepthMask } = require('./xrl-tokenizer.cjs');
    
    if (!fs.existsSync(filePath)) {
        console.error(`Error: File not found: ${filePath}`);
        process.exit(1);
    }
    
    const content = fs.readFileSync(filePath, 'utf8');
    const tokens = tokenize(content);
    const assigned = assignDepthMask(tokens, depth !== null ? depth : 2);
    
    if (action === 'enforce') {
        if (budget === null) {
            console.error('Error: --budget required for enforce mode');
            process.exit(1);
        }
        const result = enforceBudget(assigned, budget, { returnFiltered: outputJson });
        
        if (outputJson) {
            console.log(JSON.stringify({
                file: path.basename(filePath),
                budget,
                depth: result.depth,
                depthName: result.depthName,
                tokenCount: result.tokenCount,
                withinBudget: result.withinBudget,
                stripped: result.stripped,
                remaining: result.remaining,
                profile: result.profile
            }, null, 2));
        } else {
            console.log(`\n╔══════════════════════════════════════════════╗`);
            console.log(`║        XRL Budget — Budget Enforcement       ║`);
            console.log(`╚══════════════════════════════════════════════╝`);
            console.log(`\n📁 File: ${filePath}`);
            console.log(`💰 Budget: ${budget} tokens`);
            console.log(`\n📊 Results:`);
            console.log(`   Selected depth: ${result.depthName} (${result.depth})`);
            console.log(`   Token count:    ${result.tokenCount}`);
            console.log(`   Within budget:  ${result.withinBudget ? '✓' : '✗'}`);
            console.log(`   Stripped:       ${result.stripped} tokens`);
            console.log(`   Remaining:      ${result.remaining} tokens`);
            console.log(`\n📏 Depth Profile:`);
            for (let d = 0; d < 4; d++) {
                const dn = ['full', 'light', 'medium', 'deep'][d];
                console.log(`   ${dn} (${d}): ${result.profile[d]} tokens`);
            }
        }
    } else if (action === 'suggest') {
        if (budget === null) {
            console.error('Error: --budget required for suggest mode');
            process.exit(1);
        }
        const suggestion = suggestDepth(assigned, budget);
        
        if (outputJson) {
            console.log(JSON.stringify(suggestion, null, 2));
        } else {
            console.log(`\n╔══════════════════════════════════════════════╗`);
            console.log(`║        XRL Budget — Depth Suggestion         ║`);
            console.log(`╚══════════════════════════════════════════════╝`);
            console.log(`\n📁 File: ${filePath}`);
            console.log(`💰 Budget: ${budget} tokens`);
            console.log(`\n📊 Suggestion:`);
            console.log(`   Depth:         ${suggestion.depthName} (${suggestion.depth})`);
            console.log(`   Token count:   ${suggestion.tokenCount}`);
            console.log(`   Within budget: ${suggestion.withinBudget ? '✓' : '✗'}`);
            if (suggestion.excess) {
                console.log(`   Excess:        ${suggestion.excess} tokens over budget`);
            }
            console.log(`\n📏 Depth Profile:`);
            for (let d = 0; d < 4; d++) {
                const dn = ['full', 'light', 'medium', 'deep'][d];
                console.log(`   ${dn} (${d}): ${suggestion.profile[d]} tokens`);
            }
        }
    } else {
        // Report mode (default)
        const report = getBudgetReport(assigned, budget);
        
        if (outputJson) {
            console.log(JSON.stringify(report, null, 2));
        } else {
            console.log(`\n╔══════════════════════════════════════════════╗`);
            console.log(`║        XRL Budget — Budget Report            ║`);
            console.log(`╚══════════════════════════════════════════════╝`);
            console.log(`\n📁 File: ${filePath}`);
            console.log(`\n📊 Overview:`);
            console.log(`   Total tokens:       ${report.totalTokens}`);
            console.log(`   Est. binary size:   ${report.estimatedBinaryBytes} bytes`);
            console.log(`\n📏 Depth Profile:`);
            for (let d = 0; d < 4; d++) {
                const dp = report.depthProfile[d];
                console.log(`   ${dp.name} (${d}): ${dp.count} tokens (${dp.percentage})`);
            }
            console.log(`\n📦 Stripping Options:`);
            for (const opt of report.strippingOptions) {
                console.log(`   ${opt.name.padEnd(10)} depth ${opt.depth}: ${opt.tokensAtDepth} tokens (save ${opt.savingsPercent})`);
            }
            
            if (budget !== null) {
                console.log(`\n💰 Budget: ${budget} tokens`);
                console.log(`   Suggested: ${report.suggestion.depthName} (${report.suggestion.depth}) — ${report.suggestion.withinBudget ? '✓ fits' : '✗ exceeds'}`);
            }
        }
    }
}

// Run CLI if executed directly
if (require.main === module) {
    runCLI();
}

// ─── Exports ──────────────────────────────────────────────────────

module.exports = {
    DEPTH_LEVELS,
    STRIPPING_ORDER,
    enforceBudget,
    calculateDepthProfile,
    suggestDepth,
    getBudgetReport,
    stripToFit
};