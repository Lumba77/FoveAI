# TokenSlayer / Semantic Summarization Context

**Core Functionality:**  
A semantic summarization pipeline using local LLM via MCP (Model Context Protocol) to generate one-line functional summaries of files, prioritizing *what* the code does over its structural composition. The system employs targeted file analysis—leveraging TokenSlayer's skeleton-first approach—to minimize token consumption while preserving critical signatures, imports, and class structures.

**Operational Guidelines:**  
- **Skeleton-First Reads**: Always invoke MCP (`analyze_files`) before detailed inspection to achieve 40–99.5% token reduction without losing structural integrity.
- **Targeted Diffs**: Use precise edit tools (`replace_file_content`, `multi_replace_file_content`) for modifications; avoid full-file rewrites.
- **Concise Communication**: Maintain minimal chat verbosity; direct users to workspace artifacts rather than dumping code blocks.

**Technical Clarity:**  
The `/api/semantic-summary` endpoint orchestrates the workflow, validating file paths and routing requests through `_call_local_llm_for_summary`. The MCP middleman translates prompts into optimized LLM calls (e.g., `qwen3.5-4b`) with strict output constraints—ONE LINE, max 120 chars, zero extraneous text.

**Key Takeaway:**  
This is a lean, token-conscious summarization system designed for AI agents operating under strict resource and context limits. The emphasis on MCP integration, skeleton-first analysis, and targeted diffs ensures both efficiency and fidelity in code comprehension.
