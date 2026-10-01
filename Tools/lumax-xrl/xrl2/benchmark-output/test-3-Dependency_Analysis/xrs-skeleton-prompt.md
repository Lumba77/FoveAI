# XRL Prompt Template — LLM Instruction Set

## Purpose

This template teaches any LLM to work with XRL (X-Ray Language) skeletons. It defines:
1. How to interpret skeletonized code
2. The expansion protocol for requesting flesh blocks
3. Expected behavior at different depth levels

---

## System Prompt Template

```
You are an XRL-aware code assistant. The code below is in XRL (X-Ray Language) format — a skeletonized representation that preserves structure while hiding implementation details.

## XRL Format Rules

### Depth Levels
- **Depth 0** (full): All code visible, including @flesh blocks
- **Depth 1** (light): Imports, signatures, @keep blocks, @detail blocks visible. @flesh blocks hidden.
- **Depth 2** (medium): Imports, signatures, @keep blocks visible. @detail and @flesh blocks hidden.
- **Depth 3** (deep): Only imports and public signatures visible.

### Annotation Meanings
| Annotation | Visibility | What It Contains |
|------------|-----------|------------------|
| `@keep` | Always visible | Public API, types, exports, interfaces |
| `@detail` | Visible at depth ≤ 2 | Non-critical logic, helpers, utilities |
| `@flesh` | Visible only at depth 0 | Implementation bodies, error handling, verbose patterns |
| `@test` | Never in skeleton | Test code (excluded from all skeletons) |
| `@doc` | Always visible | Documentation strings |

### Skeleton Markers
- `/* ... */ }` — Indicates a collapsed block body
- `...` — Indicates truncated content
- `// @flesh: <description>` — Describes what's hidden in a flesh block

## Expansion Protocol

If you need to see the full implementation of a @flesh block, request expansion using EXACTLY this format:

```
EXPAND: <file_path> <block_name>
```

Example:
```
EXPAND: src/services/user_service.py fn hash_password
```

The system will respond with the expanded block content.

## Your Behavior

1. **Assume skeleton input by default.** Treat all code as potentially skeletonized.
2. **Work with what you have.** Answer questions based on visible structure.
3. **Request expansion when needed.** If a @flesh block is relevant to the question, request expansion.
4. **Acknowledge limitations.** If you can't fully answer without seeing flesh, say so and request expansion.
5. **Preserve annotations in output.** When generating XRL code, include @keep/@detail/@flesh annotations.

## Example Interaction

User:
```
@keep
class UserService {
    @keep
    fn get_user(id: UserId) -> User /* ... */ }

    @detail
    fn validate_email(email: String) -> Bool /* ... */ }

    @flesh
    fn _hash_password(password: String) -> String /* ... */ }
}
```

What public methods does UserService provide?

Assistant:
From the skeleton, UserService provides:
- `get_user(id: UserId) -> User` — @keep (public API)
- `validate_email(email: String) -> Bool` — @detail (non-critical)
- `_hash_password(password: String) -> String` — @flesh (implementation detail, hidden)

The `_hash_password` method is marked @flesh. If you need to see its implementation, request:
```
EXPAND: user_service.xr _hash_password
```

## Quality Guidelines

- **API Understanding**: You can identify all public functions from skeleton alone (100% accuracy expected)
- **Type Inference**: You can determine parameter/return types from signatures (95%+ accuracy expected)
- **Dependency Analysis**: You can trace import dependencies from skeleton (100% accuracy expected)
- **Code Generation**: You can generate correct code from skeleton context (90%+ accuracy expected)
- **Bug Detection**: You can identify logic bugs from skeleton (85%+ accuracy expected — some bugs require seeing flesh)

## Current Depth

The code below is at depth 2. This means:
- Depth 0: All code visible
- Depth 1: @flesh blocks hidden
- Depth 2: @flesh and @detail blocks hidden
- Depth 3: Only imports and public signatures visible

---

## Code Skeleton

```
*   --depth <0-3>    Skeletonization depth (default: 2)
 *                      0 = full file (no reduction)
 *   --json           Output as JSON (machine-readable)
 *   --stats          Show only token statistics (no skeleton output)
const fs = require('fs');
const path = require('path');
const TOKENSLAYER_PATH = path.join(__dirname, '..', 'scratch', 'TokenSlayer', 'standalone', 'tokenslayer.js');
const args = process.argv.slice(2);
let filePath = null;
let depth = 2;
let expandTarget = null;
let outputJson = false;
let statsOnly = false;
for (let i = 0; i < args.length; i++) { /* ... */ }
}
if (!filePath) {
}
if (!fs.existsSync(filePath)) {
  console.error(`Error: File not found: ${filePath}`);
}
 * Count approximate tokens (1 token ~= 4 chars)
function countTokens(text) { /* ... */ }
}
function getLanguage(filePath) { /* ... */ }
  const ext = path.extname(filePath).toLowerCase();
  const langMap = { /* ... */ }
}
 * (Must use child process to avoid argv pollution from require())
function runSkeletonizer(filePath, depth) { /* ... */ }
  const { execSync } = require('child_process');
  const result = execSync(`node "${TOKENSLAYER_PATH}" "${filePath}" --level ${depth}`, { /* ... */ }
}
function parseBlocks(skeleton) { /* ... */ }
  const blocks = [];
  const lines = skeleton.split('\n');
  let currentBlock = null;
  for (const line of lines) { /* ... */ }
  }
 * Expand a specific block (read full source and extract)
function expandBlock(filePath, blockName) { /* ... */ }
  const content = fs.readFileSync(filePath, 'utf8');
  const lines = content.split('\n');
  const expanded = [];
  let inBlock = false;
  let braceDepth = 0;
  let found = false;
  for (let i = 0; i < lines.length; i++) { /* ... */ }
}
const content = fs.readFileSync(filePath, 'utf8');
const originalLines = content.split('\n').length;
const originalChars = content.length;
const originalTokens = countTokens(content);
const language = getLanguage(filePath);
const skeletonOutput = runSkeletonizer(filePath, depth);
const skeletonLines = skeletonOutput.split('\n');
let skeletonContent = '';
let inSkeleton = false;
let statsLine = '';
for (const line of skeletonLines) { /* ... */ }
}
const skeletonTokens = countTokens(skeletonContent);
const reduction = originalTokens > 0 ? Math.round(((originalTokens - skeletonTokens) / originalTokens) * 100) : 0;
let expandedBlock = null;
if (expandTarget) {
  const expandedTokens = countTokens(expandedBlock);
  console.log(`\n📁 File: ${filePath}`);
  console.log(`🔤 Language: ${language}`);
  console.log(`📏 Depth: ${['full', 'light', 'medium', 'deep'][depth]} (${depth})`);
  console.log(`   Original: ${originalTokens.toLocaleString()} tokens (${originalLines} lines)`);
  console.log(`   Skeleton: ${skeletonTokens.toLocaleString()} tokens`);
  console.log(`   Reduction: ${reduction}%`);
  console.log(`\n🔍 Expanded Block: ${expandTarget}`);
  console.log(`   (+${expandedTokens} tokens)`);
}
if (outputJson) {
} else if (statsOnly) { /* ... */ }
} else {
  console.log(`\n📁 File: ${filePath}`);
  console.log(`🔤 Language: ${language}`);
  console.log(`📏 Depth: ${['full', 'light', 'medium', 'deep'][depth]} (${depth})`);
  console.log(`   Original: ${originalTokens.toLocaleString()} tokens (${originalLines} lines)`);
  console.log(`   Skeleton: ${skeletonTokens.toLocaleString()} tokens`);
  console.log(`   Reduction: ${reduction}%`);
}
```
```

---

## Usage Instructions

### Basic Usage

Replace `{{DEPTH}}` with the actual depth level (0-3) and `{{SKELETON}}` with the XRL skeleton output.

### With xrs.cjs

```bash
# Generate skeleton
node xrs.cjs service.py --depth 2 > skeleton.xrl

# Then use in prompt:
# 1. Set {{DEPTH}} to 2
# 2. Set {{SKELETON}} to contents of skeleton.xrl
```

### Expansion in Practice

When the LLM requests expansion:

```bash
# LLM says: EXPAND: service.py fn authenticate
node xrs.cjs service.py --depth 2 --expand "fn authenticate"
```

The expanded block is returned to the LLM, which can then continue its analysis with the full implementation visible.

---

## Test Cases Reference

### Test 1: API Understanding
**Goal**: LLM identifies all public functions from skeleton
**Expected**: 100% accuracy
**Prompt**: "List all public functions in this code and describe what each does."

### Test 2: Type Inference
**Goal**: LLM determines parameter/return types from signatures
**Expected**: 95%+ accuracy
**Prompt**: "What are the input and output types of each function?"

### Test 3: Dependency Analysis
**Goal**: LLM traces import dependencies from skeleton
**Expected**: 100% accuracy
**Prompt**: "What external dependencies does this module have?"

### Test 4: Code Generation
**Goal**: LLM generates correct code from skeleton context
**Expected**: 90%+ accuracy
**Prompt**: "Implement the @flesh block for `fn process_data` based on the visible context."

### Test 5: Bug Detection
**Goal**: LLM identifies bugs from skeleton
**Expected**: 85%+ accuracy
**Prompt**: "Are there any potential bugs or issues in this code?"
```


## Task: Dependency Analysis

Trace import dependencies

## Instructions

List all external dependencies and imports in this code. For each one:
1. What module/package is being imported
2. What specific symbols are imported
3. How each import is used in the code
4. Whether the dependency is standard library, third-party, or local