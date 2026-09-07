# LUMAX Vibe Coder — Blueprint

Architecture document for the VSCode plugin and standalone IDE application.

## Architecture Overview

`
INPUTS: Voice / Text / Files / Scan / Plugins
        │
        ▼
📦 EXECUTION BUFFER  (executionBuffer.ts)
   Draft → Approve → Execute → Rollback
        │
        ▼
🧠 INTENT ENGINE  (intentEngine.ts)
   classifyIntent() → buildPlan() → execute steps
        │
        ▼
⚙️ PROCESSING: Context Farmer + Repo Scanner
        │
        ▼
🤖 AI PROXY (port 8400) → Stream response
        │
        ▼
💾 Auto-apply edits / 📋 Task Board / 🔄 Continuous
`

## 15 Source Files

| File | Role |
|------|------|
| extension.ts | Entry point — wires everything |
| JennaChatViewProvider.ts | Message hub (24 handlers) |
| audioManager.ts | Voice recording (Python + Web Speech) |
| executionBuffer.ts | 📦 Draft/approve/execute/rollback |
| intentEngine.ts | 🧠 Intent classification + planning |
| problemsStatusBar.ts | Problem count in status bar |
| statusBar.ts | Connection status HUD |
| bonding/sessionLogger.ts | Session → memory continuity |
| commands/searchMemory.ts | Memory search QuickPick |
| commands/sendProblems.ts | Errors → AI diagnosis |
| commands/switchModel.ts | Model selector |
| inline/inlineProvider.ts | Ghost-text completions |
| memory/contextFarmer.ts | Chunk + compress large inputs |
| memory/repoScanner.ts | Full codebase scanner + deps |
| memory/foveatedClient.ts | HTTP/SSE client (port 8400) |

## Port

- **8400** — Foveated Memory proxy (Ollama upstream, local only)

## Build

- TypeScript: 0 errors
- Bundle: 111.3kb
- VS Code requirement: ^1.85.0
- All 24 frontend messages handled by backend

## To Standalone App

Same architecture, swap: WebView→Electron, VS Code editor→Monaco Editor, WS storage→SQLite
