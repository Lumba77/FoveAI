import shutil
from pathlib import Path


def repair_hf_cache(hub_root: str):
    print(f"Scanning Hugging Face cache at: {hub_root}")
    hub_path = Path(hub_root)
    if not hub_path.exists():
        print(f"Error: {hub_root} does not exist.")
        return

    repaired_count = 0
    skipped_count = 0

    # Traverse all snapshots directories
    for snapshot_dir in hub_path.glob("**/snapshots/*"):
        if not snapshot_dir.is_dir():
            continue

        print(f"\nChecking snapshot: {snapshot_dir}")
        for file_path in snapshot_dir.glob("**/*"):
            if not file_path.is_file():
                continue

            # Read first few bytes to check if it's a pointer
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(1024).strip()
            except Exception:
                # Binary files or read errors mean it's probably not a text pointer
                continue

            # Check if content looks like a relative path to blobs
            if "blobs/" in content and (
                content.startswith("../") or content.startswith("blobs/")
            ):
                # It's a pointer!
                target_rel = content
                # Resolve target path relative to the file's parent directory
                target_abs = (file_path.parent / target_rel).resolve()

                if target_abs.exists():
                    print(f"  [POINTER] {file_path.name} -> {target_rel}")
                    print(
                        f"    Replacing with actual file ({target_abs.stat().st_size} bytes)..."
                    )
                    try:
                        # Backup pointer text just in case (optional, we'll just overwrite)
                        file_path.unlink()  # Delete the pointer text file/symlink
                        shutil.copy2(target_abs, file_path)  # Copy actual file contents
                        print("    [SUCCESS]")
                        repaired_count += 1
                    except Exception as e:
                        print(f"    [FAILED] to copy: {e}")
                else:
                    print(
                        f"  [ERROR] Pointer target {target_abs} does not exist for {file_path.name}!"
                    )
            else:
                skipped_count += 1

    print("\n=== HF Symlink Repair Complete ===")
    print(f"Repaired/copied: {repaired_count} files")
    print(f"Skipped/actual: {skipped_count} files")


if __name__ == "__main__":
    repair_hf_cache("F:/Lumax/models/hub")
