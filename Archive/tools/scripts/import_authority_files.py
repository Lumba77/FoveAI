import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add Backend/Memory to sys.path to import MemoryServer
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "Backend" / "Memory"))

try:
    from foveai_mcp_server import DOCS_INDEX_PATH, MEMORY_INDEX_PATH, MemoryServer
except ImportError as e:
    print(f"Error importing MemoryServer: {e}")
    sys.exit(1)


def parse_context_md(context_path: Path):
    if not context_path.exists():
        print(f"context.md not found at {context_path}")
        return []

    with open(context_path, "r", encoding="utf-8") as f:
        content = f.read()

    sessions = []

    # 1. Match * Task X start ... * Task X end pattern
    task_blocks = re.findall(
        r"(\*\s*Task\s+\d+\s+start.*?)(?=\*\s*Task\s+\d+\s+start|\#\#\#\s+\d{4}-\d{2}-\d{2}|\Z)",
        content,
        re.DOTALL,
    )
    print(f"Found {len(task_blocks)} task blocks in context.md")

    for block in task_blocks:
        title_match = re.search(r"\*\s*\[(.*?)\]", block)
        title = title_match.group(1).strip() if title_match else "Task"

        investigation_match = re.search(
            r"\*\s*Investigation\s*\d*(?:,|\s*:)\s*(.*?)(?=\*\s*Solution:|\*|User confirmation|\Z)",
            block,
            re.DOTALL,
        )
        solution_match = re.search(
            r"(?:\*\s*Solution:|Tried solution\s*\d*(?:,|\s*:))\s*(.*?)(?=\*|User confirmation|\Z)",
            block,
            re.DOTALL,
        )

        investigation = (
            investigation_match.group(1).strip() if investigation_match else ""
        )
        solution = solution_match.group(1).strip() if solution_match else ""

        # Strip trailing task markers
        task_end_match = re.search(
            r"\*\s*Task\s+\d+\s+end\s*\[(.*?)\]", block, re.DOTALL
        )
        end_msg = task_end_match.group(1).strip() if task_end_match else ""

        user_prompt = f"Help me implement task: {title}\nInvestigation: {investigation}"
        assistant_response = f"Solution: {solution}\nOutcome: {end_msg}"

        if investigation or solution:
            sessions.append((user_prompt, assistant_response))

    # 2. Match ### YYYY-MM-DD HH:MM:SS dated blocks
    dated_blocks = re.findall(
        r"(\#\#\#\s+\d{4}-\d{2}-\d{2}.*?)(?=\#\#\#\s+\d{4}-\d{2}-\d{2}|\*\s*Task\s+\d+\s+start|\Z)",
        content,
        re.DOTALL,
    )
    print(f"Found {len(dated_blocks)} dated tasks in context.md")

    for block in dated_blocks:
        header_match = re.search(
            r"\#\#\#\s+(\d{4}-\d{2}-\d{2}\s+(?:\d{2}:\d{2}:\d{2})?)\s*—?\s*(.*)", block
        )
        date_str = header_match.group(1).strip() if header_match else ""
        header_title = (
            header_match.group(2).strip().split("\n")[0] if header_match else "Task Log"
        )

        task_match = re.search(
            r"-\s*\*\*Task:\*\*\s*(.*?)(?=- \*\*Action:|- \*\*Status:|- \*\*Fixes:|\Z)",
            block,
            re.DOTALL,
        )
        action_match = re.search(
            r"-\s*\*\*Action:\*\*\s*(.*?)(?=- \*\*Status:|- \*\*Fixes:|- \*\*Task:|\Z)",
            block,
            re.DOTALL,
        )
        fixes_match = re.search(
            r"-\s*\*\*Fixes:\*\*\s*(.*?)(?=- \*\*Status:|- \*\*Task:|\Z)",
            block,
            re.DOTALL,
        )
        status_match = re.search(
            r"-\s*\*\*Status:\*\*\s*(.*?)(?=- \*\*Task:|\Z)", block, re.DOTALL
        )

        task_desc = task_match.group(1).strip() if task_match else ""
        action_desc = action_match.group(1).strip() if action_match else ""
        fixes_desc = fixes_match.group(1).strip() if fixes_match else ""
        status_desc = status_match.group(1).strip() if status_match else ""

        user_prompt = f"Help me implement: {header_title}\nDescription: {task_desc}"
        assistant_response = (
            f"Actions: {action_desc}\nFixes: {fixes_desc}\nStatus: {status_desc}"
        )

        if task_desc or action_desc or fixes_desc:
            sessions.append((user_prompt, assistant_response))

    return sessions


def main():
    print("=== FoveAI Memory Reset & Authority File Import ===")

    # 1. Back up database files
    backup_dir = PROJECT_ROOT / ".logs" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if MEMORY_INDEX_PATH.exists():
        backup_mem = backup_dir / f"memory_index_{timestamp}.json"
        shutil.copy2(MEMORY_INDEX_PATH, backup_mem)
        print(f"Backed up memory_index to {backup_mem}")

    if DOCS_INDEX_PATH.exists():
        backup_docs = backup_dir / f"docs_index_{timestamp}.json"
        shutil.copy2(DOCS_INDEX_PATH, backup_docs)
        print(f"Backed up docs_index to {backup_docs}")

    # 2. Instantiate server
    server = MemoryServer()

    # 3. Empty database lists
    print("Emptying conversation and document indexes...")
    server.conversations = []
    server.docs = []

    # 4. Import sessions from context.md into conversations
    context_path = PROJECT_ROOT / "context.md"
    print(f"Parsing sessions from {context_path}...")
    sessions = parse_context_md(context_path)

    for i, (user_prompt, assistant_response) in enumerate(sessions):
        # We append each user prompt and assistant response as individual conversation turns
        # Using a fixed timestamp sequence to order them
        t_str = datetime.now().isoformat()
        server.conversations.append(
            {
                "role": "user",
                "content": user_prompt,
                "timestamp": t_str,
                "session_id": server.session_id,
                "metadata": {"imported_from": "context.md", "session_index": i},
            }
        )
        server.conversations.append(
            {
                "role": "assistant",
                "content": assistant_response,
                "timestamp": t_str,
                "session_id": server.session_id,
                "metadata": {"imported_from": "context.md", "session_index": i},
            }
        )

    print(
        f"Registered {len(sessions) * 2} conversation turns (from {len(sessions)} sessions/tasks)"
    )

    # 5. Import authority files into document index
    authority_files = [
        ("context.md", "authority", ["context", "history", "sessions"]),
        ("uptodate.md", "authority", ["status", "components", "recent-changes"]),
        ("ARCHITECTURE.md", "authority", ["architecture", "topology", "flows"]),
    ]

    for filename, category, tags in authority_files:
        filepath = PROJECT_ROOT / filename
        if filepath.exists():
            print(f"Importing {filename} into document index...")
            res = server.import_doc_file(str(filepath), category=category, tags=tags)
            print(f"Imported {filename}: {res.get('chunks', 0)} chunks")
        else:
            print(f"Authority file not found: {filepath}")

    # Save the databases
    server.save_memory()
    server.save_docs()

    print("\n=== Success ===")
    print(f"Total conversations in DB: {len(server.conversations)}")
    print(f"Total document chunks in DB: {len(server.docs)}")


if __name__ == "__main__":
    main()
