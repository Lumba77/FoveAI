## Task: Dependency Analysis

Trace import dependencies

## Instructions

List all external dependencies and imports in this code. For each one:
1. What module/package is being imported
2. What specific symbols are imported
3. How each import is used in the code
4. Whether the dependency is standard library, third-party, or local

## Code (Full)

```typescript
#!/usr/bin/env node
/**
 * XRS (X-Ray Skeletonizer) — CLI Wrapper
 * 
 * Wraps the existing TokenSlayer skeletonizer with XRL-formatted output.
 * 
 * Usage:
 *   node xrs.js <filepath> [options]
 * 
 * Options:
 *   --depth <0-3>    Skeletonization depth (default: 2)
 *                      0 = full file (no reduction)
 *                      1 = light (keep comments, docstrings, signatures + bodies)
 *                      2 = medium (keep imports, decorators, signatures, top-level vars)
 *                      3 = deep (keep only imports and signatures)
 *   --expand <name>  Expand a specific @flesh block
 *   --json           Output as JSON (machine-readable)
 *   --stats          Show only token statistics (no skeleton output)
 * 
 * Examples:
 *   node xrs.js service.py --depth 2
 *   node xrs.js service.py --depth 2 --expand "fn authenticate"
 *   node xrs.js service.py --json
 *   node xrs.js service.py --stats
 */

const fs = require('fs');
const path = require('path');

// Path to the existing TokenSlayer skeletonizer
const TOKENSLAYER_PATH = path.join(__dirname, '..', 'scratch', 'TokenSlayer', 'standalone', 'tokenslayer.js');

// Parse CLI args
const args = process.argv.slice(2);
let filePath = null;
let depth = 2;
let expandTarget = null;
let outputJson = false;
let statsOnly = false;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--depth' && i + 1 < args.length) {
    depth = parseInt(args[i + 1], 10);
    if (isNaN(depth) || depth < 0 || depth > 3) {
      console.error('Error: --depth must be 0, 1, 2, or 3');
      process.exit(1);
    }
    i++;
  } else if (args[i] === '--expand' && i + 1 < args.length) {
    expandTarget = args[i + 1];
    i++;
  } else if (args[i] === '--json') {
    outputJson = true;
  } else if (args[i] === '--stats') {
    statsOnly = true;
  } else if (!args[i].startsWith('--')) {
    filePath = args[i];
  }
}

if (!filePath) {
  console.error('Error: No file path provided');
  console.error('Usage: node xrs.js <filepath> [--depth <0-3>] [--expand <name>] [--json] [--stats]');
  process.exit(1);
}

if (!fs.existsSync(filePath)) {
  console.error(`Error: File not found: ${filePath}`);
  process.exit(1);
}

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
    '.py': 'python',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.js': 'typescript',
    '.jsx': 'typescript',
    '.cjs': 'typescript',
    '.mjs': 'typescript',
    '.go': 'go',
    '.java': 'java',
    '.rs': 'rust',
    '.cs': 'csharp',
    '.kt': 'kotlin',
    '.html': 'html',
    '.htm': 'html',
    '.md': 'markdown',
    '.markdown': 'markdown',
    '.css': 'css',
    '.scss': 'css',
    '.less': 'css',
    '.json': 'json',
    '.yaml': 'yaml',
    '.yml': 'yaml',
    '.xml': 'xml',
    '.svg': 'xml'
  };
  return langMap[ext] || 'unknown';
}

/**
 * Run the TokenSlayer skeletonizer as a child process
 * (Must use child process to avoid argv pollution from require())
 */
function runSkeletonizer(filePath, depth) {
  const { execSync } = require('child_process');
  const result = execSync(`node "${TOKENSLAYER_PATH}" "${filePath}" --level ${depth}`, {
    encoding: 'utf8',
    maxBuffer: 10 * 1024 * 1024
  });
  return result;
}

/**
 * Parse skeleton output to extract blocks for expansion
 */
function parseBlocks(skeleton) {
  const blocks = [];
  const lines = skeleton.split('\n');
  let currentBlock = null;
  
  for (const line of lines) {
    // Detect function/class signatures
    const fnMatch = line.match(/^(?:@\w+\s+)?(?:fn|function|def|class|async def)\s+(\w+)/);
    if (fnMatch) {
      if (currentBlock) blocks.push(currentBlock);
      currentBlock = {
        name: fnMatch[1],
        type: line.includes('class') ? 'class' : 'function',
        signature: line,
        lines: [line],
        isFlesh: line.includes('@flesh')
      };
    } else if (currentBlock) {
      currentBlock.lines.push(line);
      // Check if block ends
      if (line.trim() === '}' || line.trim() === 'end' || line.trim() === '') {
        blocks.push(currentBlock);
        currentBlock = null;
      }
    }
  }
  
  if (currentBlock) blocks.push(currentBlock);
  return blocks;
}

/**
 * Expand a specific block (read full source and extract)
 */
function expandBlock(filePath, blockName) {
  const content = fs.readFileSync(filePath, 'utf8');
  const lines = content.split('\n');
  const expanded = [];
  let inBlock = false;
  let braceDepth = 0;
  let found = false;
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();
    
    // Detect block start
    const fnMatch = trimmed.match(/^(?:@\w+\s+)?(?:fn|function|def|class|async def)\s+(\w+)/);
    if (fnMatch && fnMatch[1] === blockName) {
      inBlock = true;
      found = true;
      braceDepth = (line.match(/\{/g) || []).length - (line.match(/\}/g) || []).length;
      expanded.push(line);
      continue;
    }
    
    if (inBlock) {
      expanded.push(line);
      braceDepth += (line.match(/\{/g) || []).length;
      braceDepth -= (line.match(/\}/g) || []).length;
      if (braceDepth <= 0) {
        break;
      }
    }
  }
  
  if (!found) {
    return `// Block "${blockName}" not found in ${filePath}`;
  }
  
  return expanded.join('\n');
}

// Main execution
const content = fs.readFileSync(filePath, 'utf8');
const originalLines = content.split('\n').length;
const originalChars = content.length;
const originalTokens = countTokens(content);
const language = getLanguage(filePath);

// Run skeletonizer
const skeletonOutput = runSkeletonizer(filePath, depth);

// Parse skeleton output to extract just the skeleton content
const skeletonLines = skeletonOutput.split('\n');
let skeletonContent = '';
let inSkeleton = false;
let statsLine = '';

for (const line of skeletonLines) {
  if (line.startsWith('[TokenSlayer Saved')) {
    statsLine = line;
    continue;
  }
  if (line.startsWith('//') && line.includes('skeleton')) {
    continue;
  }
  if (line.trim() === '') {
    continue;
  }
  skeletonContent += line + '\n';
}

skeletonContent = skeletonContent.trim();
const skeletonTokens = countTokens(skeletonContent);
const reduction = originalTokens > 0 ? Math.round(((originalTokens - skeletonTokens) / originalTokens) * 100) : 0;

// Handle expansion
let expandedBlock = null;
if (expandTarget) {
  expandedBlock = expandBlock(filePath, expandTarget);
  const expandedTokens = countTokens(expandedBlock);
  
  if (outputJson) {
    console.log(JSON.stringify({
      file: filePath,
      language,
      depth,
      original: {
        lines: originalLines,
        chars: originalChars,
        tokens: originalTokens
      },
      skeleton: {
        chars: skeletonContent.length,
        tokens: skeletonTokens,
        reduction: `${reduction}%`
      },
      expansion: {
        target: expandTarget,
        content: expandedBlock,
        tokens: expandedTokens
      }
    }, null, 2));
    process.exit(0);
  }
  
  console.log(`\n╔══════════════════════════════════════════════╗`);
  console.log(`║           XRS — X-Ray Skeletonizer           ║`);
  console.log(`╚══════════════════════════════════════════════╝`);
  console.log(`\n📁 File: ${filePath}`);
  console.log(`🔤 Language: ${language}`);
  console.log(`📏 Depth: ${['full', 'light', 'medium', 'deep'][depth]} (${depth})`);
  console.log(`\n📊 Token Statistics:`);
  console.log(`   Original: ${originalTokens.toLocaleString()} tokens (${originalLines} lines)`);
  console.log(`   Skeleton: ${skeletonTokens.toLocaleString()} tokens`);
  console.log(`   Reduction: ${reduction}%`);
  console.log(`\n📦 Skeleton Output:`);
  console.log(skeletonContent);
  console.log(`\n🔍 Expanded Block: ${expandTarget}`);
  console.log(`   (+${expandedTokens} tokens)`);
  console.log(expandedBlock);
  process.exit(0);
}

// Output
if (outputJson) {
  console.log(JSON.stringify({
    file: filePath,
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
      reduction: `${reduction}%`
    },
    blocks: parseBlocks(skeletonContent)
  }, null, 2));
} else if (statsOnly) {
  console.log(JSON.stringify({
    file: path.basename(filePath),
    language,
    depth,
    originalLines,
    originalTokens,
    skeletonTokens,
    reduction: `${reduction}%`
  }));
} else {
  console.log(`\n╔══════════════════════════════════════════════╗`);
  console.log(`║           XRS — X-Ray Skeletonizer           ║`);
  console.log(`╚══════════════════════════════════════════════╝`);
  console.log(`\n📁 File: ${filePath}`);
  console.log(`🔤 Language: ${language}`);
  console.log(`📏 Depth: ${['full', 'light', 'medium', 'deep'][depth]} (${depth})`);
  console.log(`\n📊 Token Statistics:`);
  console.log(`   Original: ${originalTokens.toLocaleString()} tokens (${originalLines} lines)`);
  console.log(`   Skeleton: ${skeletonTokens.toLocaleString()} tokens`);
  console.log(`   Reduction: ${reduction}%`);
  console.log(`\n📦 Skeleton Output:`);
  console.log(skeletonContent);
  console.log(`\n💡 Tip: Use --expand <name> to expand a specific block`);
  console.log(`   Use --json for machine-readable output`);
  console.log(`   Use --stats for token statistics only`);
}
```