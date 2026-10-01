# Terminal Librarian — Quick Reference

## What It Does

Your terminal output gets **intelligently summarized** before it scrolls away:

| Output Type | Kept | Summarized | Discarded |
|-------------|------|------------|-----------|
| Successful commands | ✅ Command only | | Full output |
| Failed commands | ✅ Error + fix | | Stack trace |
| File listings (`ls`, `dir`) | | | ✅ Discarded |
| Build outputs | ✅ Final status | Progress spam | |
| Stack traces | ✅ Error type + location | | Full trace |

## New Commands

```powershell
# Search terminal history
thist "what was that git command"

# Get suggestions based on patterns
thist "command that fixed"

# Get Librarian suggestions
tsuggest
```

## Librarian Voice

> "After 'git push origin main', you often run 'git pull origin main --rebase'. Consider: git pull origin main --rebase"

> "Command 'python run_tests.py' has failed 3 times. Consider running: pip install -r requirements.txt"

## How It Works

```
Command runs → Terminal Librarian captures → Analyzes value → Summarizes → Archives

Last 50 commands: Full detail
Older commands: Compressed summary
Errors: Always preserved with solutions
```

## Integration

- Captures all commands automatically
- Preserves error-recovery pairs
- Detects command sequences
- Suggests based on patterns

---
*Part of the LUMAX Librarian System*
