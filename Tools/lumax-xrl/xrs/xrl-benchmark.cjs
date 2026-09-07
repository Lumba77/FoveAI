#!/usr/bin/env node
/**
 * XRL Benchmark — Compare full code vs skeleton LLM responses
 * 
 * Generates paired prompts (full code vs XRL skeleton) for 5 test cases,
 * measures token savings, and outputs structured results for analysis.
 * 
 * Usage:
 *   node xrl-benchmark.cjs <filepath> [options]
 * 
 * Options:
 *   --depth <0-3>    Skeletonization depth (default: 2)
 *   --test <1-5>     Run specific test case (default: all)
 *   --json           Output as JSON
 *   --csv            Output as CSV
 *   --output <dir>   Output directory for prompt files (default: ./benchmark-output)
 * 
 * Test Cases:
 *   1. API Understanding — List all public functions and describe what each does
 *   2. Type Inference — Determine parameter/return types from signatures
 *   3. Dependency Analysis — Trace import dependencies
 *   4. Code Generation — Implement a @flesh block based on context
 *   5. Bug Detection — Identify potential bugs from skeleton
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const XRS_PATH = path.join(__dirname, 'xrs.cjs');
const PROMPT_TEMPLATE_PATH = path.join(__dirname, 'xrl-prompt.md');

// Parse CLI args
const args = process.argv.slice(2);
let filePath = null;
let depth = 2;
let testFilter = null;
let outputJson = false;
let outputCsv = false;
let outputDir = path.join(__dirname, 'benchmark-output');

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--depth' && i + 1 < args.length) {
    depth = parseInt(args[i + 1], 10);
    i++;
  } else if (args[i] === '--test' && i + 1 < args.length) {
    testFilter = parseInt(args[i + 1], 10);
    i++;
  } else if (args[i] === '--json') {
    outputJson = true;
  } else if (args[i] === '--csv') {
    outputCsv = true;
  } else if (args[i] === '--output' && i + 1 < args.length) {
    outputDir = args[i + 1];
    i++;
  } else if (!args[i].startsWith('--')) {
    filePath = args[i];
  }
}

if (!filePath) {
  console.error('Error: No file path provided');
  console.error('Usage: node xrl-benchmark.cjs <filepath> [--depth <0-3>] [--test <1-5>] [--json] [--csv] [--output <dir>]');
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
 * Get skeleton output for a file
 */
function getSkeleton(filePath, depth) {
  try {
    const result = execSync(`node "${XRS_PATH}" "${filePath}" --depth ${depth} --json`, {
      encoding: 'utf8',
      maxBuffer: 10 * 1024 * 1024
    });
    return JSON.parse(result.trim());
  } catch (err) {
    console.error(`Error skeletonizing ${filePath}: ${err.message}`);
    return null;
  }
}

/**
 * Test case definitions
 */
const TEST_CASES = [
  {
    id: 1,
    name: 'API Understanding',
    description: 'List all public functions and describe what each does',
    prompt: 'List all public functions, classes, and exports in this code. For each one, describe:\n1. What it does\n2. Its parameters (name and type)\n3. Its return value\n4. Any decorators or annotations applied to it',
    expectedAccuracy: '100%',
    category: 'understanding'
  },
  {
    id: 2,
    name: 'Type Inference',
    description: 'Determine parameter/return types from signatures',
    prompt: 'For every function and method in this code, list:\n1. The function name\n2. Each parameter with its type\n3. The return type\n4. Any generic type parameters\nIf a type is not explicitly stated, infer it from usage context.',
    expectedAccuracy: '95%',
    category: 'understanding'
  },
  {
    id: 3,
    name: 'Dependency Analysis',
    description: 'Trace import dependencies',
    prompt: 'List all external dependencies and imports in this code. For each one:\n1. What module/package is being imported\n2. What specific symbols are imported\n3. How each import is used in the code\n4. Whether the dependency is standard library, third-party, or local',
    expectedAccuracy: '100%',
    category: 'understanding'
  },
  {
    id: 4,
    name: 'Code Generation',
    description: 'Implement a @flesh block based on context',
    prompt: 'Based on the visible code structure and context, implement the body of the function marked as @flesh (implementation detail). Your implementation should:\n1. Match the function signature exactly\n2. Use the same patterns and style as visible code\n3. Handle edge cases appropriately\n4. Include proper error handling\n\nExplain your implementation choices.',
    expectedAccuracy: '90%',
    category: 'generation'
  },
  {
    id: 5,
    name: 'Bug Detection',
    description: 'Identify potential bugs from skeleton',
    prompt: 'Review this code for potential bugs, issues, or anti-patterns. Look for:\n1. Type mismatches or unsafe type assumptions\n2. Missing error handling or edge cases\n3. Logic errors in control flow\n4. Resource leaks or performance issues\n5. Security vulnerabilities\n\nFor each issue found, explain why it\'s a problem and how to fix it.',
    expectedAccuracy: '85%',
    category: 'understanding'
  }
];

// Main execution
const fullContent = fs.readFileSync(filePath, 'utf8');
const fullTokens = countTokens(fullContent);
const fullLines = fullContent.split('\n').length;
const language = getLanguage(filePath);
const fileName = path.basename(filePath);

// Get skeleton
const skeletonData = getSkeleton(filePath, depth);
if (!skeletonData) {
  process.exit(1);
}

const skeletonContent = skeletonData.skeleton.content;
const skeletonTokens = skeletonData.skeleton.tokens;
const reduction = skeletonData.skeleton.reduction;

// Read prompt template
let promptTemplate = '';
try {
  promptTemplate = fs.readFileSync(PROMPT_TEMPLATE_PATH, 'utf8');
} catch (err) {
  // Use inline template if file not found
  promptTemplate = `You are an XRL-aware code assistant. The code below is in XRL format.
Current Depth: {{DEPTH}}
Code Skeleton:
\`\`\`
{{SKELETON}}
\`\`\``;
}

// Filter test cases
const testCases = testFilter
  ? TEST_CASES.filter(t => t.id === testFilter)
  : TEST_CASES;

// Generate prompts for each test case
const results = [];

for (const test of testCases) {
  // Full code prompt
  const fullPrompt = `## Task: ${test.name}\n\n${test.description}\n\n## Instructions\n\n${test.prompt}\n\n## Code (Full)\n\n\`\`\`${language}\n${fullContent}\n\`\`\``;
  
  // Skeleton prompt (using template)
  const skeletonPrompt = promptTemplate
    .replace('{{DEPTH}}', String(depth))
    .replace('{{SKELETON}}', skeletonContent)
    + `\n\n## Task: ${test.name}\n\n${test.description}\n\n## Instructions\n\n${test.prompt}`;

  const fullPromptTokens = countTokens(fullPrompt);
  const skeletonPromptTokens = countTokens(skeletonPrompt);
  const tokenSavings = fullPromptTokens - skeletonPromptTokens;
  const savingsPercent = fullPromptTokens > 0
    ? Math.round((tokenSavings / fullPromptTokens) * 100)
    : 0;

  results.push({
    test: test.id,
    name: test.name,
    category: test.category,
    expectedAccuracy: test.expectedAccuracy,
    fullPrompt: fullPrompt,
    skeletonPrompt: skeletonPrompt,
    stats: {
      fullTokens: fullPromptTokens,
      fullChars: fullPrompt.length,
      skeletonTokens: skeletonPromptTokens,
      skeletonChars: skeletonPrompt.length,
      savings: {
        tokens: tokenSavings,
        percent: `${savingsPercent}%`
      }
    },
    code: {
      file: fileName,
      language,
      fullTokens,
      skeletonTokens,
      reduction
    }
  });
}

// Create output directory
if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

// Write prompt files for manual LLM testing
const safeFileName = fileName.replace(/[^a-zA-Z0-9._-]/g, '_');
const baseName = path.parse(safeFileName).name;

for (const result of results) {
  const testDir = path.join(outputDir, `test-${result.test}-${result.name.replace(/[^a-zA-Z0-9]/g, '_')}`);
  if (!fs.existsSync(testDir)) {
    fs.mkdirSync(testDir, { recursive: true });
  }

  // Write full code prompt
  fs.writeFileSync(
    path.join(testDir, `${baseName}-full-prompt.md`),
    result.fullPrompt
  );

  // Write skeleton prompt
  fs.writeFileSync(
    path.join(testDir, `${baseName}-skeleton-prompt.md`),
    result.skeletonPrompt
  );

  // Write expected answers template
  fs.writeFileSync(
    path.join(testDir, `${baseName}-expected-answers.md`),
    `# Expected Answers — Test ${result.test}: ${result.name}\n\n` +
    `## File: ${fileName}\n` +
    `## Language: ${language}\n` +
    `## Expected Accuracy: ${result.expectedAccuracy}\n\n` +
    `### Full Code Response\n\n` +
    `[Paste LLM response to full code prompt here]\n\n` +
    `### Skeleton Response\n\n` +
    `[Paste LLM response to skeleton prompt here]\n\n` +
    `### Quality Comparison\n\n` +
    `| Aspect | Full Code | Skeleton | Match? |\n` +
    `|--------|-----------|----------|--------|\n` +
    `| [Aspect 1] | | | |\n` +
    `| [Aspect 2] | | | |\n` +
    `| [Aspect 3] | | | |\n\n` +
    `### Overall Quality Score: _/10_\n` +
    `### Notes\n\n`
  );
}

// Calculate summary
const totalFullTokens = results.reduce((sum, r) => sum + r.stats.fullTokens, 0);
const totalSkeletonTokens = results.reduce((sum, r) => sum + r.stats.skeletonTokens, 0);
const totalSavings = totalFullTokens - totalSkeletonTokens;
const totalSavingsPercent = totalFullTokens > 0
  ? Math.round((totalSavings / totalFullTokens) * 100)
  : 0;

// Output
if (outputJson) {
  console.log(JSON.stringify({
    file: fileName,
    language,
    depth,
    code: {
      fullTokens,
      skeletonTokens,
      reduction
    },
    testCases: results.map(r => ({
      test: r.test,
      name: r.name,
      category: r.category,
      expectedAccuracy: r.expectedAccuracy,
      stats: r.stats,
      code: r.code
    })),
    summary: {
      totalTests: results.length,
      totalFullTokens,
      totalSkeletonTokens,
      totalSavings: `${totalSavingsPercent}%`,
      outputDir
    }
  }, null, 2));
} else if (outputCsv) {
  console.log('test,test_name,category,expected_accuracy,full_tokens,skeleton_tokens,savings_tokens,savings_percent,code_full_tokens,code_skeleton_tokens,code_reduction');
  for (const r of results) {
    console.log(`${r.test},${r.name},${r.category},${r.expectedAccuracy},${r.stats.fullTokens},${r.stats.skeletonTokens},${r.stats.savings.tokens},${r.stats.savings.percent},${r.code.fullTokens},${r.code.skeletonTokens},${r.code.reduction}`);
  }
} else {
  console.log(`\n╔══════════════════════════════════════════════════════════╗`);
  console.log(`║           XRL Benchmark — Prompt Generator              ║`);
  console.log(`╚══════════════════════════════════════════════════════════╝`);
  console.log(`\n📁 File: ${fileName}`);
  console.log(`🔤 Language: ${language}`);
  console.log(`📏 Depth: ${['full', 'light', 'medium', 'deep'][depth]} (${depth})`);
  console.log(`\n📊 Code Token Statistics:`);
  console.log(`   Original: ${fullTokens.toLocaleString()} tokens (${fullLines} lines)`);
  console.log(`   Skeleton: ${skeletonTokens.toLocaleString()} tokens`);
  console.log(`   Reduction: ${reduction}`);
  console.log(`\n══════════════════════════════════════════════`);
  console.log(`  Test Results`);
  console.log(`══════════════════════════════════════════════`);
  
  for (const r of results) {
    const savingsPercent = parseInt(r.stats.savings.percent);
    const bar = '█'.repeat(Math.floor(savingsPercent / 5)) + '░'.repeat(20 - Math.floor(savingsPercent / 5));
    console.log(`\n  Test ${r.test}: ${r.name}`);
    console.log(`  ${bar} ${r.stats.savings.percent.padStart(4)} token savings`);
    console.log(`  Full prompt:    ${r.stats.fullTokens.toLocaleString().padStart(6)} tokens`);
    console.log(`  Skeleton prompt: ${r.stats.skeletonTokens.toLocaleString().padStart(6)} tokens`);
    console.log(`  Expected accuracy: ${r.expectedAccuracy}`);
  }
  
  console.log(`\n══════════════════════════════════════════════`);
  console.log(`  Summary`);
  console.log(`══════════════════════════════════════════════`);
  console.log(`  Tests generated: ${results.length}`);
  console.log(`  Total full tokens:    ${totalFullTokens.toLocaleString()}`);
  console.log(`  Total skeleton tokens: ${totalSkeletonTokens.toLocaleString()}`);
  console.log(`  Total savings:        ${totalSavingsPercent}%`);
  console.log(`\n  📂 Prompt files written to: ${outputDir}`);
  console.log(`  💡 To run benchmarks:`);
  console.log(`     1. Send each *-full-prompt.md to your LLM`);
  console.log(`     2. Send each *-skeleton-prompt.md to your LLM`);
  console.log(`     3. Compare responses using *-expected-answers.md`);
  console.log(`     4. Record results in xrl-poc-results.md`);
}