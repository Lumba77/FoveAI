#!/usr/bin/env node
/**
 * XRL Serializer — XRB Binary Serializer/Deserializer
 * 
 * Implements the XRB (X-Ray Binary) format v1.0 as specified in xrb-format.md.
 * Converts token streams to/from compact binary representation with:
 *   - 16-byte header (magic, version, depth, budget, block count, flags)
 *   - Block table entries (16 bytes each) for random access
 *   - Variable-length token encoding (1-byte header + payload)
 * 
 * Usage:
 *   const serializer = require('./xrl-serializer.cjs');
 *   const binary = serializer.serialize(tokens, { depth: 2 });
 *   const parsed = serializer.deserialize(binary);
 */

const { TOKEN_TYPES, OPCODE_MAP, DEPTH_MASKS, DEFAULT_DEPTH_MASKS, createToken } = require('./xrl-tokenizer.cjs');

// ─── XRB Format Constants ────────────────────────────────────────

const XRB_MAGIC = 0x584E4231; // 'XRB1' in little-endian
const XRB_VERSION = 1;
const XRB_HEADER_SIZE = 16;
const XRB_BLOCK_ENTRY_SIZE = 16;
const XRB_MAX_BLOCKS = 255;

// ─── Modifier Enum ────────────────────────────────────────────────

const MODIFIER_ENUM = {
    'public': 0x00,
    'private': 0x01,
    'protected': 0x02,
    'static': 0x03,
    'abstract': 0x04,
    'async': 0x05,
    'const': 0x06,
    'let': 0x07,
    'var': 0x08
};

const MODIFIER_REVERSE = {};
for (const [key, val] of Object.entries(MODIFIER_ENUM)) {
    MODIFIER_REVERSE[val] = key;
}

// ─── Buffer Helpers ──────────────────────────────────────────────

/**
 * Write a 32-bit unsigned integer (little-endian)
 */
function writeUint32LE(buffer, offset, value) {
    buffer[offset] = value & 0xFF;
    buffer[offset + 1] = (value >> 8) & 0xFF;
    buffer[offset + 2] = (value >> 16) & 0xFF;
    buffer[offset + 3] = (value >> 24) & 0xFF;
}

/**
 * Read a 32-bit unsigned integer (little-endian)
 */
function readUint32LE(buffer, offset) {
    return buffer[offset] | (buffer[offset + 1] << 8) | (buffer[offset + 2] << 16) | (buffer[offset + 3] << 24);
}

/**
 * Write a 16-bit unsigned integer (little-endian)
 */
function writeUint16LE(buffer, offset, value) {
    buffer[offset] = value & 0xFF;
    buffer[offset + 1] = (value >> 8) & 0xFF;
}

/**
 * Read a 16-bit unsigned integer (little-endian)
 */
function readUint16LE(buffer, offset) {
    return buffer[offset] | (buffer[offset + 1] << 8);
}

/**
 * Encode a string with variable-length length prefix
 * Length < 128: single byte
 * Length >= 128: two bytes (0x80 | (len >> 8), len & 0xFF)
 */
function encodeString(str) {
    const utf8 = Buffer.from(str, 'utf8');
    const len = utf8.length;
    
    if (len < 128) {
        const header = Buffer.alloc(1);
        header[0] = len;
        return Buffer.concat([header, utf8]);
    } else {
        const header = Buffer.alloc(2);
        header[0] = 0x80 | (len >> 8);
        header[1] = len & 0xFF;
        return Buffer.concat([header, utf8]);
    }
}

/**
 * Decode a string with variable-length length prefix
 * Returns { value, bytesRead }
 */
function decodeString(buffer, offset) {
    if (offset >= buffer.length) {
        return { value: '', bytesRead: 0 };
    }
    
    const first = buffer[offset];
    let strLen;
    let headerSize;
    
    if (first & 0x80) {
        // Two-byte length
        if (offset + 2 > buffer.length) {
            return { value: '', bytesRead: 0 };
        }
        strLen = ((first & 0x7F) << 8) | buffer[offset + 1];
        headerSize = 2;
    } else {
        // Single-byte length
        strLen = first;
        headerSize = 1;
    }
    
    if (offset + headerSize + strLen > buffer.length) {
        return { value: '', bytesRead: 0 };
    }
    
    const value = buffer.toString('utf8', offset + headerSize, offset + headerSize + strLen);
    return { value, bytesRead: headerSize + strLen };
}

// ─── Token Encoding/Decoding ──────────────────────────────────────

/**
 * Encode a single token to binary
 * @param {object} token - Token object
 * @returns {Buffer} Encoded binary
 */
function encodeToken(token) {
    const opcode = TOKEN_TYPES[token.type] ? TOKEN_TYPES[token.type].opcode : 0x00;
    const depthMask = token.depthMask !== undefined ? token.depthMask : 0x0F;
    
    // 1-byte header: 5-bit opcode + 3-bit depth mask
    const header = Buffer.alloc(1);
    header[0] = (opcode << 3) | (depthMask & 0x07);
    
    // Encode payload based on token type
    switch (token.type) {
        case 'END':
        case 'BLOCK_OPEN':
        case 'BLOCK_CLOSE':
        case 'ASSIGN':
        case 'SEPARATOR':
        case 'FLESH_MARKER':
            // No payload
            return header;
        
        case 'NUMBER':
            // 4 bytes float32
            const numBuf = Buffer.alloc(4);
            numBuf.writeFloatLE(parseFloat(token.value) || 0, 0);
            return Buffer.concat([header, numBuf]);
        
        case 'MODIFIER':
            // 1 byte enum
            const modBuf = Buffer.alloc(1);
            modBuf[0] = MODIFIER_ENUM[token.value] !== undefined ? MODIFIER_ENUM[token.value] : 0x00;
            return Buffer.concat([header, modBuf]);
        
        default:
            // String payload with variable-length prefix
            return Buffer.concat([header, encodeString(token.value)]);
    }
}

/**
 * Decode a single token from binary
 * @param {Buffer} buffer - Binary data
 * @param {number} offset - Starting offset
 * @returns {object} { token, bytesRead }
 */
function decodeToken(buffer, offset) {
    if (offset >= buffer.length) {
        return { token: createToken('END', ''), bytesRead: 0 };
    }
    
    const header = buffer[offset];
    const opcode = (header >> 3) & 0x1F;
    const depthMask = header & 0x07;
    
    // Look up token type from opcode
    let type = 'RESERVED';
    for (const [key, val] of Object.entries(TOKEN_TYPES)) {
        if (val.opcode === opcode) {
            type = key;
            break;
        }
    }
    
    let value = '';
    let payloadSize = 0;
    
    switch (type) {
        case 'END':
        case 'BLOCK_OPEN':
        case 'BLOCK_CLOSE':
        case 'ASSIGN':
        case 'SEPARATOR':
        case 'FLESH_MARKER':
            // No payload
            payloadSize = 0;
            break;
        
        case 'NUMBER':
            // 4 bytes float32
            if (offset + 1 + 4 <= buffer.length) {
                value = buffer.readFloatLE(offset + 1).toString();
                payloadSize = 4;
            }
            break;
        
        case 'MODIFIER':
            // 1 byte enum
            if (offset + 1 + 1 <= buffer.length) {
                const modVal = buffer[offset + 1];
                value = MODIFIER_REVERSE[modVal] || 'public';
                payloadSize = 1;
            }
            break;
        
        default:
            // String payload
            const decoded = decodeString(buffer, offset + 1);
            value = decoded.value;
            payloadSize = decoded.bytesRead;
            break;
    }
    
    const token = createToken(type, value, depthMask);
    return { token, bytesRead: 1 + payloadSize };
}

// ─── Serialization ────────────────────────────────────────────────

/**
 * Serialize tokens to XRB binary format
 * @param {Array<object>} tokens - Array of token objects
 * @param {object} [options] - Serialization options
 * @param {number} [options.depth] - Default depth
 * @param {number} [options.budget] - Token budget
 * @param {Array<object>} [options.blocks] - Block definitions
 * @param {object} [options.metadata] - Metadata key-value pairs
 * @returns {Buffer} XRB binary data
 */
function serialize(tokens, options = {}) {
    const {
        depth = 2,
        budget = 0,
        blocks = [],
        metadata = {}
    } = options;
    
    // 1. Encode all tokens
    const tokenBuffers = [];
    for (const token of tokens) {
        tokenBuffers.push(encodeToken(token));
    }
    const tokenData = Buffer.concat(tokenBuffers);
    
    // 2. Build block table
    const blockEntries = buildBlockTable(blocks, tokens, tokenData);
    const blockCount = blockEntries.length;
    
    // 3. Build string table for block names
    const stringTable = buildStringTable(blockEntries);
    
    // 4. Build metadata section (optional)
    let metadataSection = Buffer.alloc(0);
    let flags = 0;
    const metadataKeys = Object.keys(metadata);
    if (metadataKeys.length > 0) {
        flags |= 0x01; // Bit 0: metadata present
        metadataSection = buildMetadataSection(metadata);
    }
    
    // 5. Calculate sizes
    const blockTableSize = blockCount * XRB_BLOCK_ENTRY_SIZE;
    const stringTableSize = stringTable.length;
    const tokenDataSize = tokenData.length;
    const metadataSize = metadataSection.length;
    
    // 6. Build header
    const header = Buffer.alloc(XRB_HEADER_SIZE);
    writeUint32LE(header, 0, XRB_MAGIC);
    writeUint16LE(header, 4, XRB_VERSION);
    header[6] = depth & 0x03; // Default depth (2 bits)
    writeUint32LE(header, 7, budget); // Token budget
    header[11] = blockCount; // Block count
    header[12] = flags; // Flags
    // Bytes 13-15: reserved (zero)
    
    // 7. Assemble final binary
    const blockEntryBuffers = blockEntries.map(e => e.buffer);
    const result = Buffer.concat([
        header,
        ...blockEntryBuffers,
        stringTable,
        tokenData,
        metadataSection
    ]);
    
    return result;
}

/**
 * Build block table entries
 */
function buildBlockTable(blocks, tokens, tokenData) {
    const entries = [];
    let tokenOffset = 0;
    
    // Calculate token offsets
    const tokenOffsets = [];
    for (const token of tokens) {
        tokenOffsets.push(tokenOffset);
        const encoded = encodeToken(token);
        tokenOffset += encoded.length;
    }
    
    for (const block of blocks) {
        const nameOffset = 0; // Will be patched after string table
        const startToken = block.startToken || 0;
        const endToken = block.endToken || (tokens.length - 1);
        const tokenCount = endToken - startToken + 1;
        const blockType = block.type === 'function' ? 0x01 : 0x02;
        const depthMask = block.depth || 0x0F;
        const annotation = block.annotation || 0;
        
        const entry = Buffer.alloc(XRB_BLOCK_ENTRY_SIZE);
        writeUint32LE(entry, 0, nameOffset); // Patched later
        writeUint32LE(entry, 4, tokenOffsets[startToken] || 0);
        writeUint32LE(entry, 8, tokenCount);
        entry[12] = blockType;
        entry[13] = depthMask;
        entry[14] = annotation;
        entry[15] = 0; // Reserved
        
        entries.push({ buffer: entry, name: block.name || 'unknown' });
    }
    
    return entries;
}

/**
 * Build string table from block names
 */
function buildStringTable(blockEntries) {
    const strings = [];
    let offset = 0;
    
    for (const entry of blockEntries) {
        const name = entry.name;
        const encoded = Buffer.from(name + '\0', 'utf8'); // Null-terminated
        strings.push(encoded);
        
        // Patch the name offset in the entry buffer
        writeUint32LE(entry.buffer, 0, offset);
        offset += encoded.length;
    }
    
    return Buffer.concat(strings);
}

/**
 * Build metadata section
 */
function buildMetadataSection(metadata) {
    const pairs = Object.entries(metadata);
    const pairBuffers = [];
    
    for (const [key, value] of pairs) {
        const keyEncoded = Buffer.from(key, 'utf8');
        const valueEncoded = Buffer.from(String(value), 'utf8');
        
        const pair = Buffer.alloc(2 + keyEncoded.length + 2 + valueEncoded.length);
        writeUint16LE(pair, 0, keyEncoded.length);
        keyEncoded.copy(pair, 2);
        writeUint16LE(pair, 2 + keyEncoded.length, valueEncoded.length);
        valueEncoded.copy(pair, 2 + keyEncoded.length + 2);
        
        pairBuffers.push(pair);
    }
    
    const pairsData = Buffer.concat(pairBuffers);
    const section = Buffer.alloc(4 + 2 + pairsData.length);
    writeUint32LE(section, 0, 4 + 2 + pairsData.length); // Total size
    writeUint16LE(section, 4, pairs.length); // Key count
    pairsData.copy(section, 6);
    
    return section;
}

// ─── Deserialization ──────────────────────────────────────────────

/**
 * Deserialize XRB binary data to tokens and metadata
 * @param {Buffer} data - XRB binary data
 * @returns {object} { tokens, header, blocks, metadata }
 */
function deserialize(data) {
    const header = readHeader(data);
    if (!header.valid) {
        throw new Error(`Invalid XRB data: ${header.error}`);
    }
    
    const blocks = readBlockTable(data, header);
    const tokens = readTokenData(data, header, blocks);
    const metadata = readMetadata(data, header);
    
    return { tokens, header, blocks, metadata };
}

/**
 * Read and validate XRB header
 * @param {Buffer} data - XRB binary data
 * @returns {object} Header fields
 */
function readHeader(data) {
    if (data.length < XRB_HEADER_SIZE) {
        return { valid: false, error: `Data too short: ${data.length} bytes (need ${XRB_HEADER_SIZE})` };
    }
    
    const magic = readUint32LE(data, 0);
    if (magic !== XRB_MAGIC) {
        return { valid: false, error: `Invalid magic: 0x${magic.toString(16)} (expected 0x${XRB_MAGIC.toString(16)})` };
    }
    
    const version = readUint16LE(data, 4);
    if (version > XRB_VERSION) {
        return { valid: false, error: `Unsupported version: ${version} (max: ${XRB_VERSION})` };
    }
    
    const defaultDepth = data[6] & 0x03;
    const tokenBudget = readUint32LE(data, 7);
    const blockCount = data[11];
    const flags = data[12];
    
    return {
        valid: true,
        magic,
        version,
        defaultDepth,
        tokenBudget,
        blockCount,
        flags,
        hasMetadata: !!(flags & 0x01),
        headerSize: XRB_HEADER_SIZE
    };
}

/**
 * Read block table from XRB data
 * @param {Buffer} data - XRB binary data
 * @param {object} header - Parsed header
 * @returns {Array<object>} Block entries
 */
function readBlockTable(data, header) {
    const blocks = [];
    let offset = XRB_HEADER_SIZE;
    
    for (let i = 0; i < header.blockCount; i++) {
        if (offset + XRB_BLOCK_ENTRY_SIZE > data.length) {
            break;
        }
        
        const nameOffset = readUint32LE(data, offset);
        const tokenOffset = readUint32LE(data, offset + 4);
        const tokenCount = readUint32LE(data, offset + 8);
        const blockType = data[offset + 12];
        const depthMask = data[offset + 13];
        const annotation = data[offset + 14];
        
        // Read block name from string table
        let name = '';
        if (nameOffset > 0 && nameOffset < data.length) {
            let end = nameOffset;
            while (end < data.length && data[end] !== 0) end++;
            name = data.toString('utf8', nameOffset, end);
        }
        
        blocks.push({
            name,
            nameOffset,
            tokenOffset,
            tokenCount,
            blockType,
            type: blockType === 0x01 ? 'function' : blockType === 0x02 ? 'type' : 'unknown',
            depthMask,
            annotation,
            annotationName: ['none', '@keep', '@detail', '@flesh', '@test', '@doc'][annotation] || 'none'
        });
        
        offset += XRB_BLOCK_ENTRY_SIZE;
    }
    
    return blocks;
}

/**
 * Read token data from XRB binary
 * @param {Buffer} data - XRB binary data
 * @param {object} header - Parsed header
 * @param {Array<object>} blocks - Block entries
 * @returns {Array<object>} Token objects
 */
function readTokenData(data, header, blocks) {
    const tokens = [];
    
    // Calculate token data start: after header + block table + string table
    let tokenStart = XRB_HEADER_SIZE + (header.blockCount * XRB_BLOCK_ENTRY_SIZE);
    
    // Skip string table (between block table and token data)
    // String table ends where the first block's token data starts
    if (blocks.length > 0) {
        // Find the minimum token offset to determine where token data starts
        const minTokenOffset = Math.min(...blocks.map(b => b.tokenOffset));
        if (minTokenOffset > tokenStart) {
            tokenStart = minTokenOffset;
        }
    }
    
    let offset = tokenStart;
    while (offset < data.length) {
        const { token, bytesRead } = decodeToken(data, offset);
        if (bytesRead === 0) break;
        
        tokens.push(token);
        offset += bytesRead;
        
        if (token.type === 'END') break;
    }
    
    return tokens;
}

/**
 * Read metadata section from XRB data
 * @param {Buffer} data - XRB binary data
 * @param {object} header - Parsed header
 * @returns {object} Metadata key-value pairs
 */
function readMetadata(data, header) {
    const metadata = {};
    
    if (!header.hasMetadata) return metadata;
    
    // Metadata starts after token data
    // We need to find it by scanning from the end
    let offset = data.length;
    
    // Look for metadata size prefix
    if (offset >= 4) {
        const metaSize = readUint32LE(data, offset - 4);
        if (metaSize > 0 && metaSize <= offset) {
            const metaStart = offset - metaSize;
            const keyCount = readUint16LE(data, metaStart + 4);
            let pairOffset = metaStart + 6;
            
            for (let i = 0; i < keyCount; i++) {
                if (pairOffset + 2 > data.length) break;
                const keyLen = readUint16LE(data, pairOffset);
                pairOffset += 2;
                
                if (pairOffset + keyLen > data.length) break;
                const key = data.toString('utf8', pairOffset, pairOffset + keyLen);
                pairOffset += keyLen;
                
                if (pairOffset + 2 > data.length) break;
                const valLen = readUint16LE(data, pairOffset);
                pairOffset += 2;
                
                if (pairOffset + valLen > data.length) break;
                const value = data.toString('utf8', pairOffset, pairOffset + valLen);
                pairOffset += valLen;
                
                metadata[key] = value;
            }
        }
    }
    
    return metadata;
}

// ─── Block Expansion ──────────────────────────────────────────────

/**
 * Expand a specific block from the token stream
 * @param {Array<object>} tokens - Token array
 * @param {string} blockName - Name of block to expand
 * @returns {Array<object>} Tokens for the block
 */
function expandBlock(tokens, blockName) {
    const { extractBlocks } = require('./xrl-tokenizer.cjs');
    const blocks = extractBlocks(tokens);
    
    const block = blocks.find(b => b.name === blockName);
    if (!block) {
        return [];
    }
    
    return block.tokens;
}

// ─── Token Counting at Depth ──────────────────────────────────────

/**
 * Count tokens visible at a specific depth
 * @param {Array<object>} tokens - Token array
 * @param {number} depth - Depth level (0-3)
 * @returns {number} Token count at depth
 */
function getTokenCountAtDepth(tokens, depth) {
    const mask = 1 << depth;
    return tokens.filter(t => (t.depthMask & mask) !== 0).length;
}

// ─── Text Reconstruction ──────────────────────────────────────────

/**
 * Convert tokens back to text representation
 * @param {Array<object>} tokens - Token array
 * @param {number} [depth] - Optional depth filter
 * @returns {string} Reconstructed text
 */
function tokensToText(tokens, depth) {
    const { tokensToText: tokenizerToText } = require('./xrl-tokenizer.cjs');
    return tokenizerToText(tokens, depth);
}

// ─── Round-Trip Validation ────────────────────────────────────────

/**
 * Validate round-trip serialization/deserialization
 * @param {Array<object>} tokens - Original tokens
 * @param {object} [options] - Serialization options
 * @returns {object} Validation result
 */
function validateRoundTrip(tokens, options = {}) {
    const binary = serialize(tokens, options);
    const parsed = deserialize(binary);
    
    const originalCount = tokens.length;
    const parsedCount = parsed.tokens.length;
    
    // Compare token types (values may differ slightly due to encoding)
    const typeMatch = tokens.every((t, i) => {
        if (i >= parsed.tokens.length) return false;
        return t.type === parsed.tokens[i].type;
    });
    
    return {
        valid: typeMatch && Math.abs(originalCount - parsedCount) <= 1,
        originalTokens: originalCount,
        parsedTokens: parsedCount,
        binarySize: binary.length,
        typeMatch,
        header: parsed.header,
        blocks: parsed.blocks,
        metadata: parsed.metadata
    };
}

// ─── CLI Mode ─────────────────────────────────────────────────────

/**
 * Run serializer in CLI mode
 */
function runCLI() {
    const args = process.argv.slice(2);
    let filePath = null;
    let outputPath = null;
    let depth = 2;
    let action = 'serialize'; // serialize, deserialize, validate
    let outputJson = false;
    let showStats = false;
    
    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--depth' && i + 1 < args.length) {
            depth = parseInt(args[i + 1], 10);
            i++;
        } else if (args[i] === '--output' && i + 1 < args.length) {
            outputPath = args[i + 1];
            i++;
        } else if (args[i] === '--deserialize') {
            action = 'deserialize';
        } else if (args[i] === '--validate') {
            action = 'validate';
        } else if (args[i] === '--json') {
            outputJson = true;
        } else if (args[i] === '--stats') {
            showStats = true;
        } else if (!args[i].startsWith('--')) {
            filePath = args[i];
        }
    }
    
    if (!filePath) {
        console.error('Usage: node xrl-serializer.cjs <filepath> [options]');
        console.error('  --depth <0-3>     Default depth (default: 2)');
        console.error('  --output <path>   Output file path');
        console.error('  --deserialize     Deserialize XRB file');
        console.error('  --validate        Run round-trip validation');
        console.error('  --json            Output as JSON');
        console.error('  --stats           Show statistics only');
        process.exit(1);
    }
    
    const fs = require('fs');
    const path = require('path');
    
    if (!fs.existsSync(filePath)) {
        console.error(`Error: File not found: ${filePath}`);
        process.exit(1);
    }
    
    if (action === 'deserialize') {
        // Deserialize XRB binary file
        const data = fs.readFileSync(filePath);
        const result = deserialize(data);
        
        if (outputJson) {
            console.log(JSON.stringify({
                header: result.header,
                blocks: result.blocks,
                metadata: result.metadata,
                tokenCount: result.tokens.length,
                tokens: result.tokens.map(t => ({
                    type: t.type,
                    value: t.value,
                    depthMask: t.depthMask
                }))
            }, null, 2));
        } else {
            console.log(`\n╔══════════════════════════════════════════════╗`);
            console.log(`║     XRL Serializer — XRB Deserialization     ║`);
            console.log(`╚══════════════════════════════════════════════╝`);
            console.log(`\n📁 File: ${filePath}`);
            console.log(`📏 Version: ${result.header.version}`);
            console.log(`📏 Default Depth: ${result.header.defaultDepth}`);
            console.log(`📦 Blocks: ${result.blocks.length}`);
            console.log(`🔤 Tokens: ${result.tokens.length}`);
            console.log(`\n📋 Blocks:`);
            for (const block of result.blocks) {
                console.log(`   ${block.name} (${block.type}, ${block.tokenCount} tokens, ${block.annotationName})`);
            }
            if (Object.keys(result.metadata).length > 0) {
                console.log(`\n📋 Metadata:`);
                for (const [key, value] of Object.entries(result.metadata)) {
                    console.log(`   ${key}: ${value}`);
                }
            }
        }
    } else if (action === 'validate') {
        // Round-trip validation
        const { tokenize, assignDepthMask } = require('./xrl-tokenizer.cjs');
        const content = fs.readFileSync(filePath, 'utf8');
        const tokens = tokenize(content);
        const assigned = assignDepthMask(tokens, depth);
        
        const result = validateRoundTrip(assigned, { depth });
        
        if (outputJson) {
            console.log(JSON.stringify(result, null, 2));
        } else {
            console.log(`\n╔══════════════════════════════════════════════╗`);
            console.log(`║   XRL Serializer — Round-Trip Validation     ║`);
            console.log(`╚══════════════════════════════════════════════╝`);
            console.log(`\n📁 File: ${filePath}`);
            console.log(`📏 Depth: ${depth}`);
            console.log(`\n📊 Results:`);
            console.log(`   Valid:           ${result.valid ? '✓' : '✗'}`);
            console.log(`   Original tokens: ${result.originalTokens}`);
            console.log(`   Parsed tokens:   ${result.parsedTokens}`);
            console.log(`   Binary size:     ${result.binarySize} bytes`);
            console.log(`   Type match:      ${result.typeMatch ? '✓' : '✗'}`);
            console.log(`   Blocks:          ${result.blocks.length}`);
        }
    } else {
        // Serialize
        const { tokenize, assignDepthMask, extractBlocks } = require('./xrl-tokenizer.cjs');
        const content = fs.readFileSync(filePath, 'utf8');
        const tokens = tokenize(content);
        const assigned = assignDepthMask(tokens, depth);
        const blocks = extractBlocks(assigned);
        
        const metadata = {
            source_file: path.basename(filePath),
            language: path.extname(filePath).slice(1),
            created: new Date().toISOString(),
            original_size: String(content.length),
            original_tokens: String(tokens.length),
            tool_version: '1.0.0'
        };
        
        const binary = serialize(assigned, {
            depth,
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
        
        // Write output if specified
        if (outputPath) {
            fs.writeFileSync(outputPath, binary);
            console.log(`Written ${binary.length} bytes to ${outputPath}`);
        }
        
        if (outputJson) {
            console.log(JSON.stringify({
                file: filePath,
                depth,
                binarySize: binary.length,
                tokenCount: assigned.length,
                blockCount: blocks.length,
                metadata
            }, null, 2));
        } else if (showStats) {
            console.log(JSON.stringify({
                file: path.basename(filePath),
                depth,
                binarySize: binary.length,
                tokenCount: assigned.length,
                blockCount: blocks.length
            }));
        } else {
            console.log(`\n╔══════════════════════════════════════════════╗`);
            console.log(`║     XRL Serializer — XRB Serialization       ║`);
            console.log(`╚══════════════════════════════════════════════╝`);
            console.log(`\n📁 File: ${filePath}`);
            console.log(`📏 Depth: ${depth}`);
            console.log(`\n📊 Statistics:`);
            console.log(`   Tokens:          ${assigned.length}`);
            console.log(`   Binary size:     ${binary.length} bytes`);
            console.log(`   Blocks:          ${blocks.length}`);
            console.log(`   Bytes per token: ${(binary.length / assigned.length).toFixed(2)}`);
            
            if (outputPath) {
                console.log(`\n📁 Output: ${outputPath}`);
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
    // Constants
    XRB_MAGIC,
    XRB_VERSION,
    XRB_HEADER_SIZE,
    XRB_BLOCK_ENTRY_SIZE,
    MODIFIER_ENUM,
    MODIFIER_REVERSE,
    
    // Core functions
    serialize,
    deserialize,
    readHeader,
    readBlockTable,
    readTokenData,
    readMetadata,
    
    // Token encoding
    encodeToken,
    decodeToken,
    encodeString,
    decodeString,
    
    // Block operations
    expandBlock,
    
    // Analysis
    getTokenCountAtDepth,
    tokensToText,
    validateRoundTrip
};