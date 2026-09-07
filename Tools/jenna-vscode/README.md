# Jenna — LUMAX Copilot

> **Persistent-memory AI pair programmer.** Jenna remembers your coding sessions across workspaces via the LUMAX Foveated Memory proxy (port 8400).

> [!NOTE]
> The extension is **not yet published** to Open VSX or the VS Code Marketplace. Install it locally from source using the steps below.

---

## Installation (Local — from source)

### Step 1 — Install dependencies & build

```powershell
cd Tools\jenna-vscode
npm install
npm run compile       # or: npm run build
```

### Step 2 — Package into a `.vsix`

```powershell
# Install vsce if you don't have it
npm install -g @vscode/vsce

# Package (run from inside Tools\jenna-vscode)
vsce package
```

This produces a file like `jenna-copilot-0.1.0.vsix` in the same folder.

### Step 3 — Install the `.vsix` in VS Code

**Option A — Command Palette (easiest):**

1. Open VS Code
2. Press `Ctrl+Shift+P` → type **"Install from VSIX"**
3. Browse to `Tools\jenna-vscode\jenna-copilot-0.1.0.vsix` → click **Install**
4. Reload VS Code when prompted

**Option B — Terminal:**

```powershell
code --install-extension Tools\jenna-vscode\jenna-copilot-0.1.0.vsix
```

### Step 4 — Start LUMAX services

Make sure the Foveated Memory proxy is running before using Jenna:

```powershell
# From LUMAX repo root
node Tools\foveated-memory\server.js
```

Or use the LUMAX taskbar launcher (starts all services automatically).

---

## Features

| Feature | Description |
|---|---|
| **Jenna Chat** | Persistent sidebar chat with full session history and streaming responses |
| **Foveated Memory** | Every conversation is stored and recalled via the LUMAX memory proxy (port 8400). Jenna never forgets your project context. |
| **Inline Completions** | Ghost-text code suggestions powered by your local model — no telemetry, fully offline |
| **Memory Search** | Fuzzy-search your entire conversation history directly from the toolbar |
| **Model Switcher** | Hot-swap between LM Studio, Ollama, and OpenAI models without leaving VS Code |
| **Workspace Isolation** | Each workspace gets its own memory silo — no cross-project leakage |

---

## Requirements

| Service | Port | Purpose |
|---|---|---|
| **Foveated Memory Proxy** | `8400` | Core memory & LLM routing (`server.js`) |
| **LM Studio** (optional) | `7272` | Local inference back-end |
| **Ollama** (optional) | `11434` | Fallback local inference |

Start the proxy before opening VS Code:

```powershell
# From repo root
node Tools\foveated-memory\server.js
```

Or use the LUMAX taskbar launcher which starts all services automatically.

---

## Extension Settings

| Setting | Default | Description |
|---|---|---|
| `jenna.foveatedMemoryUrl` | `http://127.0.0.1:8400` | URL of the Foveated Memory proxy |
| `jenna.model` | `auto` | Model identifier passed to the proxy (`auto` = proxy decides) |
| `jenna.workspaceId` | _(blank)_ | Override workspace memory silo. Blank = workspace folder name |
| `jenna.streamingEnabled` | `true` | Enable token-streaming responses |
| `jenna.inlineCompletions` | `true` | Enable ghost-text inline code completions |

---

## Commands

| Command | Description |
|---|---|
| `Jenna: Search Memory` | Full-text search across stored conversation history |
| `Jenna: Switch Model` | Interactively pick LLM model (LM Studio / Ollama / cloud) |
| `Jenna: Start New Session` | Clear the active chat thread and start fresh |
| `Jenna: Clear Workspace Memory` | Permanently wipe memory for the current workspace |
| `Jenna: Show Memory Status` | View memory stats in the status bar |
| `Jenna: Open Sidebar` | Open the Jenna panel |

---

## Publishing a New Release

The repo uses a GitHub Actions workflow (`.github/workflows/publish.yml`) that automatically:

1. Bundles via `esbuild`
2. Packages a `.vsix` with `vsce`
3. Creates a GitHub Release (attaches `.vsix` + `CHANGELOG.md` notes)
4. Publishes to the [Open VSX Registry](https://open-vsx.org/)

**To cut a release:**

```bash
# Bump version in package.json, then:
git tag v0.1.1
git push origin v0.1.1
```

**Required GitHub Secrets:**

| Secret | Value |
|---|---|
| `GITHUB_TOKEN` | Auto-provided by Actions (for releases) |
| `OVSX_PAT` | Your [open-vsx.org](https://open-vsx.org) Personal Access Token |

---

## Architecture

```
VS Code Extension
      │
      ▼
Foveated Memory Proxy (port 8400)
      ├── Active TF-IDF recall  →  conversation history
      ├── LM Studio (7272)      →  local inference
      └── Ollama (11434)        →  fallback inference
```

---

## License

MIT © LUMAX
