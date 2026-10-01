import subprocess
import sys
from pathlib import Path

# Setup paths for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(PROJECT_ROOT / "Backend" / "Memory"))

try:
    from foveai_mcp_server import FoveAI_ROOT, MemoryServer
except ImportError as e:
    print(f"Error importing MemoryServer: {e}")
    sys.exit(1)


def run_generate_repo_skeleton():
    script_path = PROJECT_ROOT / "Scripts" / "generate_repo_principia.py"
    if not script_path.exists():
        print(f"generate_repo_principia.py not found at {script_path}")
        return False

    print("Running generate_repo_principia.py to refresh repo-principia.md...")
    # Executing the script via the venv python executable
    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        venv_python = "python"

    try:
        res = subprocess.run(
            [str(venv_python), str(script_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if res.returncode == 0:
            print("Successfully regenerated repo-principia.md!")
            print(res.stdout.strip())
            return True
        else:
            print(f"generate_repo_principia.py failed with exit code {res.returncode}")
            print(f"Stdout:\n{res.stdout}")
            print(f"Stderr:\n{res.stderr}")
            return False
    except Exception as e:
        print(f"Error running generate_repo_principia.py: {e}")
        return False


def main():
    print("=== XRL Scan, Generation & Memory Indexing ===")

    # 1. Regenerate repository principia
    success = run_generate_repo_skeleton()
    if not success:
        print(
            "Warning: Repository principia regeneration failed. Continuing with indexing..."
        )

    # 2. Instantiate MemoryServer
    print("\nInitializing MemoryServer...")
    server = MemoryServer()

    # 3. Import repo-principia.md into document index
    skeleton_file = PROJECT_ROOT / "repo-principia.md"
    if skeleton_file.exists():
        print(f"Importing {skeleton_file.name} into document index...")
        res = server.import_doc_file(
            str(skeleton_file), category="authority", tags=["principia", "authority"]
        )
        print(f"Imported {skeleton_file.name}: {res.get('chunks', 0)} chunks")
    else:
        print(f"repo-principia.md not found at {skeleton_file}")

    # 4. Trigger repo-wide codebase indexing (which will generate and store XRL principia)
    print(f"\nTriggering codebase indexing for {FoveAI_ROOT}...")
    print(
        "This will scan the codebase and automatically generate/cache XRL principia for files..."
    )

    # Let's index up to 1000 files in the workspace
    index_res = server.index_directory(str(FoveAI_ROOT), max_files=1000, assess=True)

    print("\n=== Indexing Summary ===")
    print(f"Indexed files: {index_res.get('indexed', 0)}")
    print(f"Skipped unchanged files: {index_res.get('skipped_unchanged', 0)}")
    print(f"Skipped dirs: {index_res.get('skipped_dirs', 0)}")
    print(f"Failed files: {index_res.get('failed', 0)}")

    skeleton_count = index_res.get("indexed", 0)
    print(f"Total files with cached XRL principia: {skeleton_count}")
    print("\n✅ XRL Scan Complete! All files indexed into memory server.")

    print("\n=== Success ===")


if __name__ == "__main__":
    main()
