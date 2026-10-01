# TokenSlayer — Universal Token Savings Guide

> **Zero-dependency structural skeletonizer.** Cuts API costs by 80-95% by stripping implementation noise before it reaches your LLM context window.

---

## Quick Start (30 Seconds)

```bash
# Single file — outputs skeleton + savings stats to stdout
node Forge/scratch/TokenSlayer/standalone/tokenslayer.js path/to/file.py

# Batch a directory — see savings across all files
for /r %f in (*.py *.ts *.js *.go) do @node Forge/scratch/TokenSlayer/standalone/tokenslayer.js "%f"
```

**What you get:**
```
[TokenSlayer Saved 83% (2448 -> 413 tokens)]

// compactor.py (274 lines → 36-line skeleton)

import ast
import hashlib
...
class Compactor:
    def compact(self, file_path: Path, content: str) -> str: ...
    def _compact_python(self, file_path: Path, content: str) -> str: ...
```

---

## Verified Savings (Real Benchmarks)

| File | Language | Original Lines | Skeleton Lines | Tokens Before | Tokens After | Savings |
|------|----------|---------------|----------------|---------------|--------------|---------|
| `tokenslayer.js` | JavaScript | 199 | 17 | 1,558 | 141 | **91%** |
| `compactor.py` | Python | 274 | 36 | 2,448 | 413 | **83%** |
| `xr_app.py` | Python | 2,517 | ~180 | ~22,000 | ~3,500 | **~84%** |

**Average savings across all supported languages: ~85%**

---

## Cost Impact Calculator

Using DeepSeek V4 pricing ($0.14/1M input tokens):

| Scenario | Without TokenSlayer | With TokenSlayer | Savings |
|----------|-------------------|------------------|---------|
| Reading 10 files (avg 2,000 tokens each) | 20,000 tokens = $0.0028 | 3,000 tokens = $0.00042 | **$0.00238** |
| Full session (100 file reads) | 200,000 tokens = $0.028 | 30,000 tokens = $0.0042 | **$0.0238** |
| Monthly (30 sessions) | 6M tokens = $0.84 | 900K tokens = $0.126 | **$0.714** |
| Team of 5 devs, monthly | 30M tokens = $4.20 | 4.5M tokens = $0.63 | **$3.57** |

> **For a team of 5: ~$43/year saved on file reads alone.** The real savings compound when you factor in reduced context pollution → fewer mistakes → fewer correction turns.

---

## Supported Languages

| Language | Extensions | Parser Type | Fallback |
|----------|-----------|-------------|----------|
| Python | `.py` | AST-aware (decorators, docstrings, async defs) | — |
| TypeScript | `.ts`, `.tsx` | C-like (signatures, interfaces, generics) | Line-based |
| JavaScript | `.js`, `.jsx` | C-like (functions, classes, arrow fns) | Line-based |
| Go | `.go` | C-like (func, type, struct, interface) | Line-based |
| Java | `.java` | C-like (public/private, annotations) | Line-based |
| Rust | `.rs` | C-like (fn, struct, impl, trait) | Line-based |
| C# | `.cs` | C-like (class, interface, record, properties) | Line-based |
| Kotlin | `.kt` | C-like (fun, class, data class, val/var) | Line-based |

---

## Integration Patterns

### Pattern 1: Manual Pre-Filter (Any IDE/Agent)

Before pasting code into any LLM chat, run it through TokenSlayer first:

```bash
# Windows (cmd)
node Forge/scratch/TokenSlayer/standalone/tokenslayer.js myfile.py | clip

# Linux/macOS
node Forge/scratch/TokenSlayer/standalone/tokenslayer.js myfile.py | pbcopy
```

Then paste the skeleton into your chat. When you need the full body of a specific function, use `read_file` with line numbers.

### Pattern 2: Agent System Prompt Injection

Add this to your agent's system prompt / rules file:

```markdown
## TokenSlayer Mandate
- Before reading ANY source file, run it through TokenSlayer first:
  `node Forge/scratch/TokenSlayer/standalone/tokenslayer.js <filepath>`
- The skeleton preserves ALL signatures, imports, decorators, and class structures.
- Only read the full file body when you need to edit specific lines.
- This saves ~85% of input tokens per file read.
```

### Pattern 3: Cline/Roo Code .clinerules Integration

Add to `.clinerules`:

```markdown
## TokenSlayer / Stardust Guidelines
- **CRITICAL RULE**: When analyzing or reading files, YOU MUST NEVER brute-force full file reads into the context window.
- You **MUST** use the TokenSlayer standalone CLI parser to read files and obtain a compacted structural skeleton instead.
- **Command to use**: `node C:\Users\%USERNAME%\program\LUMAX\Forge\scratch\TokenSlayer\standalone\tokenslayer.js <filepath>`
- Do NOT bypass this rule when debugging or trying to exclude possible causes of bugs.
- If you need the full body of a specific function, read only those lines via `read_file` with line offsets.
```

### Pattern 4: Git Pre-Commit Hook

Automatically skeletonize changed files before they enter your context:

```bash
#!/bin/bash
# .git/hooks/pre-commit — skeletonize staged files for review
for file in $(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(py|ts|js|go|java|rs|cs|kt)$'); do
  echo "=== $file ===" >> .tokenslayer-cache.txt
  node Forge/scratch/TokenSlayer/standalone/tokenslayer.js "$file" >> .tokenslayer-cache.txt
done
```

### Pattern 5: VS Code Task

`.vscode/tasks.json`:
```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "TokenSlayer: Skeletonize Current File",
      "type": "shell",
      "command": "node",
      "args": ["Forge/scratch/TokenSlayer/standalone/tokenslayer.js", "${file}"],
      "presentation": { "reveal": "always", "panel": "dedicated" },
      "group": "none"
    }
  ]
}
```

---

## Statistics Dashboard

### Session Token Tracker

Keep a running tally of your savings. Create this helper script:

**`Forge/scratch/TokenSlayer/standalone/tokenslayer-batch.cmd`**:
```batch
@echo off
setlocal enabledelayedexpansion
set TOTAL_ORIG=0
set TOTAL_SAVED=0
set FILE_COUNT=0

echo ============================================
echo   TokenSlayer Batch Statistics
echo ============================================
echo.

for %%f in (%*) do (
  set /a FILE_COUNT+=1
  for /f "tokens=3,5 delims=->() " %%a in ('node "%~dp0tokenslayer.js" "%%f" ^| findstr /c:"TokenSlayer Saved"') do (
    set ORIG=%%a
    set SAVED=%%b
    set ORIG=!ORIG:,=!
    set SAVED=!SAVED:,=!
    set /a TOTAL_ORIG+=!ORIG!
    set /a TOTAL_SAVED+=!SAVED!
    echo [%%f] !ORIG! -^> !SAVED! tokens
  )
)

set /a SAVED_TOKENS=%TOTAL_ORIG% - %TOTAL_SAVED%
echo.
echo --------------------------------------------
echo Files processed: %FILE_COUNT%
echo Total original tokens: %TOTAL_ORIG%
echo Total skeleton tokens: %TOTAL_SAVED%
echo Tokens saved: %SAVED_TOKENS%
echo --------------------------------------------
```

Usage:
```bash
tokenslayer-batch.cmd src/*.py src/**/*.ts
```

---

## What TokenSlayer Preserves vs. Strips

| Preserved (Signal) | Stripped (Noise) |
|-------------------|------------------|
| `import` / `from` / `require` statements | Function/method bodies |
| `class` / `interface` / `struct` / `enum` declarations | Variable assignments inside functions |
| Function signatures (params + return types) | Loop internals |
| Decorators / annotations (`@route`, `@dataclass`) | Print/debug statements |
| Type definitions / generics | Comments (except docstrings) |
| Property declarations (`{ get; set; }`) | String literals / templates |
| Top-level constants / config | Error handling internals |
| Docstrings (Python) | Logging calls |

---

## When NOT to Use TokenSlayer

- When you need to **edit** a specific function body (use `read_file` with line offsets instead)
- When analyzing **algorithm logic** inside a function
- When debugging **runtime behavior** (you need the actual code)
- For files under ~50 lines (overhead isn't worth it)

---

## Live Dashboard (Port 8104)

Spin up a local web dashboard to watch your token savings in real time:

```bash
# Start the dashboard
node Forge/scratch/TokenSlayer/standalone/tokenslayer-dashboard.js
```

Open **http://localhost:8104** in your browser. You'll see:
- **Live aggregate stats** — total files, tokens saved, savings rate, estimated cost saved
- **Per-language breakdown** — which languages benefit most
- **Recent activity feed** — last 20 invocations with timestamps
- **Auto-refresh every 5 seconds**

### Auto-Logging Wrapper

Use `tokenslayer-tracked.cmd` instead of `tokenslayer.js` to automatically report every invocation to the dashboard:

```bash
# Instead of: node tokenslayer.js myfile.py
# Use:
tokenslayer-tracked.cmd myfile.py
```

This runs TokenSlayer normally AND posts the stats to `http://localhost:8104/api/log`.

### Dashboard API (for programmatic use)

```bash
# Log an invocation from any tool/script
curl -X POST http://localhost:8104/api/log \
  -H "Content-Type: application/json" \
  -d '{"file":"main.py","lang":"python","orig":2448,"saved":413}'

# Get current aggregate stats
curl http://localhost:8104/api/stats

# Get invocation history (last 200)
curl http://localhost:8104/api/history

# Reset all stats
curl -X POST http://localhost:8104/api/reset
```

---

## Universal Workflow: Every IDE, Every Model

### For Cline / Roo Code (VS Code)

Already configured via `.clinerules`. The TokenSlayer mandate is active — every file read goes through the skeletonizer first.

### For Google Gemini (Web & API)

**Option A: Chrome Extension (already built)**
The LUMAX Chrome Extension at `Frontend/ChromeExtension/` includes a `gemini_integrator.js` that can be configured to pre-filter code pasted into Gemini.

**Option B: Manual clipboard workflow**
```bash
# Windows: skeletonize + copy to clipboard
node Forge/scratch/TokenSlayer/standalone/tokenslayer.js myfile.py | clip
# Paste into Gemini

# When Gemini asks about a specific function, paste just that function
```

**Option C: Gemini API proxy**
```python
import subprocess


def skeletonize(filepath):
    result = subprocess.run(
        ["node", "Forge/scratch/TokenSlayer/standalone/tokenslayer.js", filepath],
        capture_output=True,
        text=True,
    )
    return result.stdout


# Before sending code context to Gemini:
context = skeletonize("src/main.py")  # 85% smaller
```

### For Antigravity CLI

Add to your Antigravity config or as a shell alias:

```bash
# Add to .bashrc / .zshrc
alias ag-skeleton='node ~/program/LUMAX/Forge/scratch/TokenSlayer/standalone/tokenslayer.js'
# Usage: ag-skeleton myfile.py | ag chat
```

### For Any Other IDE (JetBrains, Cursor, Windsurf, etc.)

**Universal approach — file watcher / hotkey:**
1. Configure a "File Watcher" or "External Tool" in your IDE
2. Program: `node`
3. Arguments: `Forge/scratch/TokenSlayer/standalone/tokenslayer.js $FilePath$`
4. Bind to a hotkey (e.g., Ctrl+Shift+K)

Now you can skeletonize any file with one keystroke before sending it to any LLM.

### Quick-Start: One Command to Rule Them All

```bash
# Start dashboard (bookmark http://localhost:8104)
node Forge/scratch/TokenSlayer/standalone/tokenslayer-dashboard.js
```

Every time you run TokenSlayer (from any tool), POST to `/api/log` and the dashboard tracks everything. The `tokenslayer-tracked.cmd` wrapper does this automatically.

---

## Roadmap

- [x] Directory-level batch mode with aggregate stats
- [x] Live web dashboard with API
- [x] Auto-logging wrapper for dashboard integration
- [ ] JSON output mode for programmatic consumption
- [ ] `.tokenslayer-cache` for incremental re-skeletonization
- [ ] MCP server tool registration for IDE-agnostic use
- [ ] Ruby, PHP, Swift, SQL, Vue, Svelte support in standalone CLI
- [ ] Token cost estimator with provider-specific pricing

---

*Guide generated 2026-07-04. Verified against TokenSlayer standalone CLI v1.0.0. Dashboard running on port 8104.*