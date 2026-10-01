#!/usr/bin/env node
/**
 * XRL Tokenizer — Core Tokenizer
 * 
 * Parses XRS skeleton text output into a binary token stream with depth masks.
 * Each token carries a 5-bit opcode and 3-bit depth mask for O(1) filtering.
 * 
 * Usage:
 *   const tokenizer = require('./xrl-tokenizer.cjs');
 *   const tokens = tokenizer.tokenize(skeletonText);
 *   const filtered = tokenizer.filterByDepth(tokens, 2);
 * 
 * Token Types (25):
 *   END, KEEP, DETAIL, FLESH, FN_SIG, TYPE_DEF, IMPORT, EXPORT,
 *   BLOCK_OPEN, BLOCK_CLOSE, IDENT, STRING, NUMBER, DECORATOR,
 *   MODIFIER, ASSIGN, SEPARATOR, FLESH_MARKER, EXPAND_HINT,
 *   COMMENT, DOC_COMMENT, ANNOTATION, OPERATOR, KEYWORD, RESERVED
 */

// ─── Token Type Definitions ───────────────────────────────────────

const TOKEN_TYPES = {
    END:            { opcode: 0x00, name: 'END' },
    KEEP:           { opcode: 0x01, name: 'KEEP' },
    DETAIL:         { opcode: 0x02, name: 'DETAIL' },
    FLESH:          { opcode: 0x03, name: 'FLESH' },
    FN_SIG:         { opcode: 0x04, name: 'FN_SIG' },
    TYPE_DEF:       { opcode: 0x05, name: 'TYPE_DEF' },
    IMPORT:         { opcode: 0x06, name: 'IMPORT' },
    EXPORT:         { opcode: 0x07, name: 'EXPORT' },
    BLOCK_OPEN:     { opcode: 0x08, name: 'BLOCK_OPEN' },
    BLOCK_CLOSE:    { opcode: 0x09, name: 'BLOCK_CLOSE' },
    IDENT:          { opcode: 0x0A, name: 'IDENT' },
    STRING:         { opcode: 0x0B, name: 'STRING' },
    NUMBER:         { opcode: 0x0C, name: 'NUMBER' },
    DECORATOR:      { opcode: 0x0D, name: 'DECORATOR' },
    MODIFIER:       { opcode: 0x0E, name: 'MODIFIER' },
    ASSIGN:         { opcode: 0x0F, name: 'ASSIGN' },
    SEPARATOR:      { opcode: 0x10, name: 'SEPARATOR' },
    FLESH_MARKER:   { opcode: 0x11, name: 'FLESH_MARKER' },
    EXPAND_HINT:    { opcode: 0x12, name: 'EXPAND_HINT' },
    COMMENT:        { opcode: 0x13, name: 'COMMENT' },
    DOC_COMMENT:    { opcode: 0x14, name: 'DOC_COMMENT' },
    ANNOTATION:     { opcode: 0x15, name: 'ANNOTATION' },
    OPERATOR:       { opcode: 0x16, name: 'OPERATOR' },
    KEYWORD:        { opcode: 0x17, name: 'KEYWORD' },
    RESERVED:       { opcode: 0x18, name: 'RESERVED' }
};

// Reverse lookup: opcode -> token type
const OPCODE_MAP = {};
for (const [key, val] of Object.entries(TOKEN_TYPES)) {
    OPCODE_MAP[val.opcode] = key;
}

// ─── Depth Mask Constants ─────────────────────────────────────────

const DEPTH_MASKS = {
    ALL:    0x0F,  // Visible at all depths
    DEEP:   0x08,  // Visible at depth 3 (deep) — only imports + public sigs
    MEDIUM: 0x04,  // Visible at depth 2 (medium)
    LIGHT:  0x02,  // Visible at depth 1 (light)
    FULL:   0x01,  // Visible at depth 0 (full) — all tokens
    NONE:   0x00   // Not visible at any depth (internal)
};

/**
 * Default depth mask assignments per token type
 */
const DEFAULT_DEPTH_MASKS = {
    END:            DEPTH_MASKS.ALL,
    KEEP:           DEPTH_MASKS.ALL,
    DETAIL:         DEPTH_MASKS.LIGHT | DEPTH_MASKS.FULL,
    FLESH:          DEPTH_MASKS.FULL,
    FN_SIG:         DEPTH_MASKS.ALL,
    TYPE_DEF:       DEPTH_MASKS.ALL,
    IMPORT:         DEPTH_MASKS.ALL,
    EXPORT:         DEPTH_MASKS.ALL,
    BLOCK_OPEN:     DEPTH_MASKS.ALL,
    BLOCK_CLOSE:    DEPTH_MASKS.ALL,
    IDENT:          DEPTH_MASKS.ALL,
    STRING:         DEPTH_MASKS.ALL,
    NUMBER:         DEPTH_MASKS.ALL,
    DECORATOR:      DEPTH_MASKS.MEDIUM | DEPTH_MASKS.LIGHT | DEPTH_MASKS.FULL,
    MODIFIER:       DEPTH_MASKS.MEDIUM | DEPTH_MASKS.LIGHT | DEPTH_MASKS.FULL,
    ASSIGN:         DEPTH_MASKS.ALL,
    SEPARATOR:      DEPTH_MASKS.ALL,
    FLESH_MARKER:   DEPTH_MASKS.FULL,
    EXPAND_HINT:    DEPTH_MASKS.ALL,
    COMMENT:        DEPTH_MASKS.LIGHT | DEPTH_MASKS.FULL,
    DOC_COMMENT:    DEPTH_MASKS.ALL,
    ANNOTATION:     DEPTH_MASKS.ALL,
    OPERATOR:       DEPTH_MASKS.ALL,
    KEYWORD:        DEPTH_MASKS.ALL,
    RESERVED:       DEPTH_MASKS.ALL
};

// ─── Token Structure ─────────────────────────────────────────────

/**
 * Create a token object
 * @param {string} type - Token type name
 * @param {string} value - Token value/payload
 * @param {number} [depthMask] - Custom depth mask (defaults to type default)
 * @param {object} [meta] - Additional metadata
 * @returns {object} Token object
 */
function createToken(type, value, depthMask, meta) {
    const typeDef = TOKEN_TYPES[type];
    if (!typeDef) {
        throw new Error(`Unknown token type: ${type}`);
    }
    return {
        type,
        opcode: typeDef.opcode,
        value: value || '',
        depthMask: depthMask !== undefined ? depthMask : (DEFAULT_DEPTH_MASKS[type] || DEPTH_MASKS.ALL),
        meta: meta || {}
    };
}

// ─── Pattern Detection ───────────────────────────────────────────

/**
 * Regex patterns for detecting token types from skeleton text lines
 */
const PATTERNS = {
    // Import statements: import/from/require/include
    IMPORT: /^\s*(?:import|from|require|include|use|using)\s+/,
    
    // Export statements: export/module.exports/pub mod
    EXPORT: /^\s*(?:export|module\.exports|pub(?:\(crate\))?\s+(?:fn|struct|enum|trait|mod|type|const|let|use))\s+/,
    
    // Function signatures: fn/function/def/async def
    FN_SIG: /^\s*(?:(?:@\w+\s+)*)?(?:export\s+)?(?:pub\s+)?(?:async\s+)?(?:fn|function|def)\s+\w+\s*\(/,
    
    // Class/struct/enum/trait definitions
    TYPE_DEF: /^\s*(?:(?:@\w+\s+)*)?(?:export\s+)?(?:pub\s+)?(?:class|struct|enum|trait|interface|type|protocol)\s+\w+/,
    
    // Decorators: @dataclass, @property, @app.route, etc.
    DECORATOR: /^\s*@\w+/,
    
    // Flesh markers: @flesh annotation
    FLESH_MARKER: /^\s*@flesh\b/,
    
    // Expand hints: // @flesh: description
    EXPAND_HINT: /\/\/\s*@flesh:/,
    
    // Comments: // or #
    COMMENT: /^\s*(?:\/\/|#|--|%;)\s*/,
    
    // Doc comments: ///, """ """, /** */, '''
    DOC_COMMENT: /^\s*(?:\/\/\/|""".*"""|'''|'''|\/\*\*)/,
    
    // Block open: { or do/begin/then
    BLOCK_OPEN: /\{\s*$/,
    
    // Block close: } or end
    BLOCK_CLOSE: /^\s*\}\s*$/,
    
    // Annotations: @keep, @detail, @test, @doc
    ANNOTATION: /^\s*@(?:keep|detail|test|doc)\b/,
    
    // Modifiers: public, private, protected, static, abstract, async, const, let, var
    MODIFIER: /\b(?:public|private|protected|static|abstract|async|const|let|var|readonly|override|virtual)\b/,
    
    // String literals: "..." or '...'
    STRING: /["']/,
    
    // Number literals
    NUMBER: /\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b/,
    
    // Assignment: =
    ASSIGN: /=\s*(?:$|[^=])/,
    
    // Separators: , ; 
    SEPARATOR: /^\s*[,;]\s*$/,
    
    // Identifiers: word tokens
    IDENT: /\b[a-zA-Z_]\w*\b/,
    
    // Operators: +, -, *, /, etc.
    OPERATOR: /[+\-*\/%&|^~<>!?]=?/
};

// ─── Core Tokenizer ───────────────────────────────────────────────

/**
 * Tokenize skeleton text into an array of tokens
 * @param {string} text - XRS skeleton text
 * @returns {Array<object>} Array of token objects
 */
function tokenize(text) {
    const tokens = [];
    const lines = text.split('\n');
    let currentDepth = 2; // Default depth
    let inBlock = false;
    let blockStack = [];
    
    for (let lineIdx = 0; lineIdx < lines.length; lineIdx++) {
        const line = lines[lineIdx];
        const trimmed = line.trim();
        
        if (!trimmed) continue;
        
        // Detect depth level from skeleton header
        const depthMatch = trimmed.match(/^📏\s*Depth:\s*(?:full|light|medium|deep)\s*\((\d)\)/i);
        if (depthMatch) {
            currentDepth = parseInt(depthMatch[1], 10);
            continue;
        }
        
        // Detect TokenSlayer stats line
        if (trimmed.startsWith('[TokenSlayer Saved')) {
            continue;
        }
        
        // Detect skeleton header lines
        if (trimmed.startsWith('//') && (trimmed.includes('skeleton') || trimmed.includes('lines'))) {
            continue;
        }
        
        // Process line based on content
        const lineTokens = tokenizeLine(trimmed, line, lineIdx);
        tokens.push(...lineTokens);
        
        // Track block depth for brace matching
        if (trimmed.includes('{') && !trimmed.includes('}')) {
            blockStack.push({ line: lineIdx, type: 'open' });
            inBlock = true;
        }
        if (trimmed.includes('}') && !trimmed.includes('{')) {
            if (blockStack.length > 0) blockStack.pop();
            if (blockStack.length === 0) inBlock = false;
        }
    }
    
    // Add END token
    tokens.push(createToken('END', ''));
    
    return tokens;
}

/**
 * Tokenize a single line of skeleton text
 * @param {string} trimmed - Trimmed line content
 * @param {string} originalLine - Original line with whitespace
 * @param {number} lineIdx - Line index
 * @returns {Array<object>} Array of tokens from this line
 */
function tokenizeLine(trimmed, originalLine, lineIdx) {
    const tokens = [];
    const indent = originalLine.length - originalLine.trimStart().length;
    
    // Check for @flesh marker first (highest priority)
    if (PATTERNS.FLESH_MARKER.test(trimmed)) {
        tokens.push(createToken('FLESH_MARKER', '@flesh', DEPTH_MASKS.FULL, { line: lineIdx, indent }));
        return tokens;
    }
    
    // Check for expand hints
    if (PATTERNS.EXPAND_HINT.test(trimmed)) {
        const hintContent = trimmed.replace(/\/\/\s*@flesh:\s*/, '').trim();
        tokens.push(createToken('EXPAND_HINT', hintContent, DEPTH_MASKS.ALL, { line: lineIdx, indent }));
        return tokens;
    }
    
    // Check for annotations (@keep, @detail, @test, @doc)
    if (PATTERNS.ANNOTATION.test(trimmed)) {
        const annMatch = trimmed.match(/@(\w+)/);
        if (annMatch) {
            tokens.push(createToken('ANNOTATION', annMatch[1], DEPTH_MASKS.ALL, { line: lineIdx, indent }));
            const rest = trimmed.replace(/@\w+\s*/, '');
            if (rest.trim()) {
                tokens.push(...tokenizeLine(rest.trim(), rest, lineIdx));
            }
        }
        return tokens;
    }
    
    // Check for decorators
    if (PATTERNS.DECORATOR.test(trimmed)) {
        const decMatch = trimmed.match(/@(\S+)/);
        if (decMatch) {
            tokens.push(createToken('DECORATOR', decMatch[1], DEPTH_MASKS.MEDIUM | DEPTH_MASKS.LIGHT | DEPTH_MASKS.FULL, { line: lineIdx, indent }));
            const rest = trimmed.replace(/@\S+\s*/, '');
            if (rest.trim()) {
                tokens.push(...tokenizeLine(rest.trim(), rest, lineIdx));
            }
        }
        return tokens;
    }
    
    // Check for doc comments
    if (PATTERNS.DOC_COMMENT.test(trimmed)) {
        tokens.push(createToken('DOC_COMMENT', trimmed, DEPTH_MASKS.ALL, { line: lineIdx, indent }));
        return tokens;
    }
    
    // Check for comments
    if (PATTERNS.COMMENT.test(trimmed)) {
        const commentContent = trimmed.replace(/^\s*(?:\/\/|#|--|%;)\s*/, '').trim();
        tokens.push(createToken('COMMENT', commentContent, DEPTH_MASKS.LIGHT | DEPTH_MASKS.FULL, { line: lineIdx, indent }));
        return tokens;
    }
    
    // Check for import statements
    if (PATTERNS.IMPORT.test(trimmed)) {
        tokens.push(createToken('IMPORT', trimmed, DEPTH_MASKS.ALL, { line: lineIdx, indent }));
        return tokens;
    }
    
    // Check for export statements
    if (PATTERNS.EXPORT.test(trimmed)) {
        tokens.push(createToken('EXPORT', trimmed, DEPTH_MASKS.ALL, { line: lineIdx, indent }));
        return tokens;
    }
    
    // Check for function signatures
    if (PATTERNS.FN_SIG.test(trimmed)) {
        tokens.push(createToken('FN_SIG', trimmed, DEPTH_MASKS.ALL, { line: lineIdx, indent }));
        return tokens;
    }
    
    // Check for type definitions (class, struct, enum, trait, interface)
    if (PATTERNS.TYPE_DEF.test(trimmed)) {
        tokens.push(createToken('TYPE_DEF', trimmed, DEPTH_MASKS.ALL, { line: lineIdx, indent }));
        return tokens;
    }
    
    // Check for block close
    if (PATTERNS.BLOCK_CLOSE.test(trimmed)) {
        tokens.push(createToken('BLOCK_CLOSE', '}', DEPTH_MASKS.ALL, { line: lineIdx, indent }));
        return tokens;
    }
    
    // Check for block open (line ending with {)
    if (PATTERNS.BLOCK_OPEN.test(trimmed)) {
        // Extract content before {
        const beforeBrace = trimmed.replace(/\{\s*$/, '').trim();
        if (beforeBrace) {
            tokens.push(...tokenizeContent(beforeBrace, lineIdx, indent));
        }
        tokens.push(createToken('BLOCK_OPEN', '{', DEPTH_MASKS.ALL, { line: lineIdx, indent }));
        return tokens;
    }
    
    // Check for separators
    if (PATTERNS.SEPARATOR.test(trimmed)) {
        tokens.push(createToken('SEPARATOR', trimmed.trim(), DEPTH_MASKS.ALL, { line: lineIdx, indent }));
        return tokens;
    }
    
    // Default: tokenize content into finer-grained tokens
    tokens.push(...tokenizeContent(trimmed, lineIdx, indent));
    
    return tokens;
}

/**
 * Tokenize content string into fine-grained tokens
 * @param {string} content - Content to tokenize
 * @param {number} lineIdx - Line index
 * @param {number} indent - Indentation level
 * @returns {Array<object>} Array of tokens
 */
function tokenizeContent(content, lineIdx, indent) {
    const tokens = [];
    let remaining = content;
    
    while (remaining.length > 0) {
        let matched = false;
        
        // Skip whitespace
        const wsMatch = remaining.match(/^\s+/);
        if (wsMatch) {
            remaining = remaining.slice(wsMatch[0].length);
            continue;
        }
        
        // Check for string literals
        if (remaining[0] === '"' || remaining[0] === "'") {
            const quote = remaining[0];
            let endIdx = 1;
            while (endIdx < remaining.length) {
                if (remaining[endIdx] === '\\') {
                    endIdx += 2;
                    continue;
                }
                if (remaining[endIdx] === quote) {
                    endIdx++;
                    break;
                }
                endIdx++;
            }
            const strContent = remaining.slice(0, endIdx);
            tokens.push(createToken('STRING', strContent, DEPTH_MASKS.ALL, { line: lineIdx, indent }));
            remaining = remaining.slice(endIdx);
            matched = true;
            continue;
        }
        
        // Check for numbers
        const numMatch = remaining.match(/^\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/);
        if (numMatch) {
            tokens.push(createToken('NUMBER', numMatch[0], DEPTH_MASKS.ALL, { line: lineIdx, indent }));
            remaining = remaining.slice(numMatch[0].length);
            matched = true;
            continue;
        }
        
        // Check for assignment
        if (remaining.startsWith('=') && !remaining.startsWith('==') && !remaining.startsWith('=>')) {
            tokens.push(createToken('ASSIGN', '=', DEPTH_MASKS.ALL, { line: lineIdx, indent }));
            remaining = remaining.slice(1);
            matched = true;
            continue;
        }
        
        // Check for separators
        if (remaining[0] === ',' || remaining[0] === ';') {
            tokens.push(createToken('SEPARATOR', remaining[0], DEPTH_MASKS.ALL, { line: lineIdx, indent }));
            remaining = remaining.slice(1);
            matched = true;
            continue;
        }
        
        // Check for block tokens
        if (remaining[0] === '{') {
            tokens.push(createToken('BLOCK_OPEN', '{', DEPTH_MASKS.ALL, { line: lineIdx, indent }));
            remaining = remaining.slice(1);
            matched = true;
            continue;
        }
        if (remaining[0] === '}') {
            tokens.push(createToken('BLOCK_CLOSE', '}', DEPTH_MASKS.ALL, { line: lineIdx, indent }));
            remaining = remaining.slice(1);
            matched = true;
            continue;
        }
        
        // Check for operators
        const opMatch = remaining.match(/^[+\-*\/%&|^~<>!?]=?/);
        if (opMatch && opMatch[0].length > 0) {
            tokens.push(createToken('OPERATOR', opMatch[0], DEPTH_MASKS.ALL, { line: lineIdx, indent }));
            remaining = remaining.slice(opMatch[0].length);
            matched = true;
            continue;
        }
        
        // Check for identifiers and keywords
        const idMatch = remaining.match(/^[a-zA-Z_]\w*/);
        if (idMatch) {
            const word = idMatch[0];
            // Check for modifiers
            if (/^(?:public|private|protected|static|abstract|async|const|let|var|readonly|override|virtual)$/.test(word)) {
                tokens.push(createToken('MODIFIER', word, DEPTH_MASKS.MEDIUM | DEPTH_MASKS.LIGHT | DEPTH_MASKS.FULL, { line: lineIdx, indent }));
            } else if (/^(?:if|else|for|while|do|switch|case|return|try|catch|finally|throw|new|this|super|class|struct|enum|trait|interface|type|protocol|fn|function|def|import|export|from|require|include|use|using|pub|mod|where|as|in|of|match|let|mut|ref|impl|trait|dyn|async|await|yield|break|continue)$/.test(word)) {
                tokens.push(createToken('KEYWORD', word, DEPTH_MASKS.ALL, { line: lineIdx, indent }));
            } else {
                tokens.push(createToken('IDENT', word, DEPTH_MASKS.ALL, { line: lineIdx, indent }));
            }
            remaining = remaining.slice(word.length);
            matched = true;
            continue;
        }
        
        // Skip any remaining unrecognized characters
        if (!matched) {
            remaining = remaining.slice(1);
        }
    }
    
    return tokens;
}

// ─── Depth Mask Assignment ────────────────────────────────────────

/**
 * Assign depth masks to tokens based on their type and context
 * @param {Array<object>} tokens - Array of token objects
 * @param {number} [depth] - Current skeleton depth (0-3)
 * @returns {Array<object>} Tokens with updated depth masks
 */
function assignDepthMask(tokens, depth) {
    return tokens.map(token => {
        // Use default depth mask from type
        let mask = DEFAULT_DEPTH_MASKS[token.type] || DEPTH_MASKS.ALL;
        
        // Override based on context if depth is provided
        if (depth !== undefined) {
            // At depth 3 (deep): only KEEP, FN_SIG, TYPE_DEF, IMPORT, EXPORT
            if (depth >= 3) {
                if (!['KEEP', 'FN_SIG', 'TYPE_DEF', 'IMPORT', 'EXPORT', 'END', 'BLOCK_OPEN', 'BLOCK_CLOSE', 'SEPARATOR'].includes(token.type)) {
                    mask = DEPTH_MASKS.FULL; // Only visible at full depth
                }
            }
            // At depth 2 (medium): KEEP, FN_SIG, TYPE_DEF, IMPORT, EXPORT, DECORATOR, MODIFIER
            else if (depth >= 2) {
                if (['DETAIL', 'FLESH', 'FLESH_MARKER', 'COMMENT'].includes(token.type)) {
                    mask = DEPTH_MASKS.FULL; // Only visible at full depth
                }
            }
            // At depth 1 (light): everything except FLESH
            else if (depth >= 1) {
                if (['FLESH', 'FLESH_MARKER'].includes(token.type)) {
                    mask = DEPTH_MASKS.FULL; // Only visible at full depth
                }
            }
        }
        
        return { ...token, depthMask: mask };
    });
}

// ─── Block Extraction ────────────────────────────────────────────

/**
 * Extract blocks (functions, classes) from token stream
 * @param {Array<object>} tokens - Array of token objects
 * @returns {Array<object>} Array of block objects
 */
function extractBlocks(tokens) {
    const blocks = [];
    let currentBlock = null;
    let braceDepth = 0;
    
    for (let i = 0; i < tokens.length; i++) {
        const token = tokens[i];
        
        // Detect block start from FN_SIG or TYPE_DEF
        if ((token.type === 'FN_SIG' || token.type === 'TYPE_DEF') && !currentBlock) {
            currentBlock = {
                name: extractName(token.value),
                type: token.type === 'FN_SIG' ? 'function' : 'type',
                signature: token.value,
                startToken: i,
                tokens: [token],
                depth: token.depthMask,
                isFlesh: false
            };
            continue;
        }
        
        if (currentBlock) {
            currentBlock.tokens.push(token);
            
            if (token.type === 'BLOCK_OPEN') {
                braceDepth++;
            } else if (token.type === 'BLOCK_CLOSE') {
                braceDepth--;
                if (braceDepth <= 0) {
                    currentBlock.endToken = i;
                    blocks.push(currentBlock);
                    currentBlock = null;
                    braceDepth = 0;
                }
            }
        }
    }
    
    // Close any unclosed block
    if (currentBlock) {
        currentBlock.endToken = tokens.length - 1;
        blocks.push(currentBlock);
    }
    
    return blocks;
}

/**
 * Extract name from a signature string
 * @param {string} signature - Function/type signature
 * @returns {string} Extracted name
 */
function extractName(signature) {
    const match = signature.match(/(?:fn|function|def|class|struct|enum|trait|interface|type|protocol)\s+(\w+)/);
    return match ? match[1] : 'unknown';
}

// ─── Token Counting ───────────────────────────────────────────────

/**
 * Count tokens, optionally filtered by depth
 * @param {Array<object>} tokens - Array of token objects
 * @param {number} [depth] - Depth to filter by (omit for all)
 * @returns {number} Token count
 */
function countTokens(tokens, depth) {
    if (depth === undefined) {
        return tokens.length;
    }
    return tokens.filter(t => t.depthMask & (1 << depth)).length;
}

// ─── Depth Filtering ──────────────────────────────────────────────

/**
 * Filter tokens by depth visibility
 * @param {Array<object>} tokens - Array of token objects
 * @param {number} depth - Depth level (0-3)
 * @returns {Array<object>} Filtered tokens
 */
function filterByDepth(tokens, depth) {
    const mask = 1 << depth;
    return tokens.filter(t => (t.depthMask & mask) !== 0);
}

// ─── Token Statistics ─────────────────────────────────────────────

/**
 * Get statistics about token stream
 * @param {Array<object>} tokens - Array of token objects
 * @returns {object} Statistics object
 */
function getTokenStats(tokens) {
    const stats = {
        total: tokens.length,
        byType: {},
        byDepth: { 0: 0, 1: 0, 2: 0, 3: 0 },
        estimatedBytes: 0
    };
    
    for (const token of tokens) {
        // Count by type
        stats.byType[token.type] = (stats.byType[token.type] || 0) + 1;
        
        // Count by depth visibility
        for (let d = 0; d < 4; d++) {
            if (token.depthMask & (1 << d)) {
                stats.byDepth[d]++;
            }
        }
        
        // Estimate binary size: 1 byte header + variable payload
        const payloadSize = token.value ? Buffer.byteLength(token.value, 'utf8') : 0;
        const headerSize = 1;
        const lengthPrefix = payloadSize < 128 ? 1 : 2;
        stats.estimatedBytes += headerSize + lengthPrefix + payloadSize;
    }
    
    return stats;
}

// ─── Text Reconstruction ─────────────────────────────────────────

/**
 * Convert tokens back to text (for debugging/testing)
 * @param {Array<object>} tokens - Array of token objects
 * @param {number} [depth] - Optional depth filter
 * @returns {string} Reconstructed text
 */
function tokensToText(tokens, depth) {
    const filtered = depth !== undefined ? filterByDepth(tokens, depth) : tokens;
    let result = '';
    let indent = 0;
    
    for (const token of filtered) {
        if (token.type === 'END') break;
        
        if (token.type === 'BLOCK_CLOSE') {
            indent = Math.max(0, indent - 1);
            result += '\n' + '  '.repeat(indent) + '}';
            continue;
        }
        
        if (token.type === 'BLOCK_OPEN') {
            result += ' {';
            indent++;
            continue;
        }
        
        if (token.type === 'SEPARATOR') {
            result += token.value;
            continue;
        }
        
        if (token.type === 'ASSIGN') {
            result += ' = ';
            continue;
        }
        
        if (token.type === 'OPERATOR') {
            result += ' ' + token.value + ' ';
            continue;
        }
        
        // Add newline for new tokens
        if (result.length > 0 && !result.endsWith('\n')) {
            result += '\n' + '  '.repeat(indent);
        }
        
        result += token.value;
    }
    
    return result.trim();
}

// ─── CLI Mode ─────────────────────────────────────────────────────

/**
 * Run tokenizer in CLI mode
 */
function runCLI() {
    const args = process.argv.slice(2);
    let filePath = null;
    let depth = null;
    let outputJson = false;
    let showStats = false;
    let showBlocks = false;
    
    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--depth' && i + 1 < args.length) {
            depth = parseInt(args[i + 1], 10);
            i++;
        } else if (args[i] === '--json') {
            outputJson = true;
        } else if (args[i] === '--stats') {
            showStats = true;
        } else if (args[i] === '--blocks') {
            showBlocks = true;
        } else if (!args[i].startsWith('--')) {
            filePath = args[i];
        }
    }
    
    if (!filePath) {
        console.error('Usage: node xrl-tokenizer.cjs <filepath> [--depth <0-3>] [--json] [--stats] [--blocks]');
        process.exit(1);
    }
    
    const fs = require('fs');
    if (!fs.existsSync(filePath)) {
        console.error(`Error: File not found: ${filePath}`);
        process.exit(1);
    }
    
    const content = fs.readFileSync(filePath, 'utf8');
    const tokens = tokenize(content);
    const assigned = assignDepthMask(tokens, depth !== null ? depth : 2);
    const stats = getTokenStats(assigned);
    
    if (outputJson) {
        const result = {
            file: filePath,
            depth: depth !== null ? depth : 2,
            tokenCount: stats.total,
            estimatedBytes: stats.estimatedBytes,
            byType: stats.byType,
            byDepth: stats.byDepth,
            tokens: assigned.map(t => ({
                type: t.type,
                value: t.value,
                depthMask: t.depthMask,
                meta: t.meta
            }))
        };
        
        if (showBlocks) {
            result.blocks = extractBlocks(assigned).map(b => ({
                name: b.name,
                type: b.type,
                signature: b.signature,
                tokenCount: b.tokens.length,
                depth: b.depth
            }));
        }
        
        console.log(JSON.stringify(result, null, 2));
    } else if (showStats) {
        console.log(JSON.stringify({
            file: require('path').basename(filePath),
            depth: depth !== null ? depth : 2,
            totalTokens: stats.total,
            estimatedBytes: stats.estimatedBytes,
            byType: stats.byType,
            byDepth: stats.byDepth
        }));
    } else {
        console.log(`\n╔══════════════════════════════════════════════╗`);
        console.log(`║        XRL Tokenizer — Token Stream          ║`);
        console.log(`╚══════════════════════════════════════════════╝`);
        console.log(`\n📁 File: ${filePath}`);
        console.log(`📏 Depth: ${depth !== null ? depth : 2}`);
        console.log(`\n📊 Token Statistics:`);
        console.log(`   Total tokens:    ${stats.total}`);
        console.log(`   Est. binary:     ${stats.estimatedBytes} bytes`);
        console.log(`\n📦 By Type:`);
        for (const [type, count] of Object.entries(stats.byType).sort((a, b) => b[1] - a[1])) {
            console.log(`   ${type.padEnd(15)} ${count}`);
        }
        console.log(`\n📏 By Depth:`);
        for (let d = 0; d < 4; d++) {
            console.log(`   Depth ${d}: ${stats.byDepth[d]} tokens`);
        }
        
        if (showBlocks) {
            const blocks = extractBlocks(assigned);
            console.log(`\n📦 Blocks (${blocks.length}):`);
            for (const block of blocks) {
                console.log(`   ${block.type === 'function' ? 'ƒ' : '◈'} ${block.name} (${block.tokens.length} tokens)`);
            }
        }
        
        console.log(`\n💡 Tip: Use --json for machine-readable output`);
        console.log(`   Use --blocks to show extracted blocks`);
    }
}

// Run CLI if executed directly
if (require.main === module) {
    runCLI();
}

// ─── Exports ──────────────────────────────────────────────────────

module.exports = {
    TOKEN_TYPES,
    OPCODE_MAP,
    DEPTH_MASKS,
    DEFAULT_DEPTH_MASKS,
    createToken,
    tokenize,
    tokenizeLine,
    tokenizeContent,
    assignDepthMask,
    extractBlocks,
    extractName,
    countTokens,
    filterByDepth,
    getTokenStats,
    tokensToText,
    PATTERNS
};