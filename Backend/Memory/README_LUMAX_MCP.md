# LUMAX Memory MCP Server for Cline

This MCP server integrates Cline (VS Code) with LUMAX memory services, enabling:
- **Session persistence** - All conversations saved across sessions
- **LLM summarization** - Automatic extraction of topics, decisions, and actions
- **Cognee graph search** - Semantic search through the knowledge graph
- **Context injection** - Previous session context automatically loaded

## Installation

### 1. Add to Cline MCP Settings

In VS Code, open Cline settings and add:

```json
{
  "mcpServers": {
    "lumax-memory": {
      "command": "/home/lumba/LUMAX-lite/.venv/sentry/bin/python",
      "args": ["/home/lumba/LUMAX-lite/backend/Memory/cline_mcp_server.py"],
      "transportType": "stdio"
    }
  }
}
```

### 2. Restart Cline

Reload VS Code or restart the Cline extension.

## Available Tools

### 1. `get_lumax_memory`
Retrieve recent conversation history.

**Parameters:**
- `limit` (default: 20) - Number of entries to retrieve

### 2. `add_to_lumax_memory`
Add a conversation turn to memory.

**Parameters:**
- `role` - "user" or "assistant"
- `content` - The message text

### 3. `get_session_injection`
Get context prompt for injecting into new sessions.

### 4. `search_lumax_memory`
Search conversation history by keyword.

**Parameters:**
- `query` - Search term

### 5. `import_previous_sessions` ⭐
Import and summarize all previous Cline and CON Vessel sessions.

**Parameters:**
- `source` - "cline", "con_vessel", or "both" (default: "both")
- `summarize` - Use LLM to generate summaries (default: true)

**Returns:**
- `imported_count` - Number of sessions imported
- `summaries_created` - Number of summaries generated
- `summaries` - First 5 summaries with:
  - `title` - Session title
  - `topics` - Extracted topics
  - `summary` - Overview
  - `decisions` - Key decisions made
  - `actions_taken` - Actions completed
  - `files_modified` - Files changed
  - `problems_solved` - Issues resolved
  - `follow_up_tasks` - Pending tasks
  - `category` - coding|planning|debugging|architecture|creative|other
  - `tags` - Searchable tags

### 6. `search_session_summaries`
Search summarized sessions with LLM-extracted metadata.

**Parameters:**
- `query` - Search term
- `category` (optional) - Filter by category

### 7. `export_to_cognee`
Export session summaries to Cognee knowledge graph.

**Parameters:**
- `session_id` - Specific session or "all"

### 8. `cognee_graph_search`
Search Cognee knowledge graph for semantic matches.

**Parameters:**
- `query` - Search query
- `top_k` (default: 8) - Number of results

## Usage Examples

### Import All Previous Sessions
```
Use import_previous_sessions with source="both", summarize=true
```

### Search for Past Work
```
Use search_session_summaries with query="virtual environment setup"
```

### Export to Cognee Graph
```
Use export_to_cognee with session_id="all"
```

### Semantic Graph Search
```
Use cognee_graph_search with query="TTS service configuration"
```

## File Locations

| File | Purpose |
|------|---------|
| `.logs/cline_memory.json` | Cline conversation storage |
| `.logs/session_summaries.json` | LLM-summarized sessions |
| `.logs/cognee_import_queue.jsonl` | Queued for Cognee import |
| `frontend/CON_vessel/con_history.json` | CON Vessel history |

## Cognee Integration

When Cognee is enabled (`LUMAX_COGNEE_ENABLED=true`), summaries are automatically exported to the knowledge graph for semantic search.

**Environment variables:**
- `LUMAX_COGNEE_ENABLED` - Enable Cognee integration
- `LUMAX_COGNEE_BASE_URL` - Cognee API endpoint
- `LUMAX_COGNEE_API_KEY` - API key (optional)
- `LUMAX_COGNEE_DATASET` - Dataset name (default: "lumax_sessions")

## CLI Usage

The session importer can also be run from command line:

```bash
# Import and summarize all sessions
python backend/Memory/session_importer.py --import-cline --import-con --summarize

# Export to Cognee
python backend/Memory/session_importer.py --export-cognee

# Search summaries
python backend/Memory/session_importer.py --search "virtual environment"

# List all summaries
python backend/Memory/session_importer.py --list