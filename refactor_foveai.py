import os
import re
import sys

def main():
    dry_run = "--run" not in sys.argv
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__)))
    
    # Files to target
    valid_exts = {".py", ".pyw", ".js", ".ts", ".jsx", ".tsx", ".bat", ".ps1"}
    
    # Exclude directories
    ignored_dirs = {"venv", ".venv", "node_modules", ".git", "__pycache__", "dist", "build", "outputs", "logs", "Library", "Packages", "Bee"}
    
    log_path = os.path.join(base_dir, "FoveAI_Refactor.log")
    log_file = open(log_path, "w", encoding="utf-8")
    
    def log(msg):
        print(msg)
        log_file.write(msg + "\n")

    log(f"Starting FoveAI Refactor (Dry Run: {dry_run})")
    log(f"Base Directory: {base_dir}")
    log("-" * 40)
    
    file_renames = []
    content_replacements = []

    for root, dirs, files in os.walk(base_dir):
        # Filter ignored dirs
        dirs[:] = [d for d in dirs if d not in ignored_dirs]
        
        for file in files:
            file_path = os.path.join(root, file)
            ext = os.path.splitext(file)[1].lower()
            
            # 1. Content Replacement
            if ext in valid_exts or file == ".env":
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    if "FoveAI" in content or "foveai" in content:
                        lines = content.splitlines()
                        new_lines = []
                        changed = False
                        
                        for i, line in enumerate(lines):
                            orig_line = line
                            
                            # Do NOT replace if it's the root path reference or env keys we want to keep
                            if r"program\LUMAX" in line or "program/LUMAX" in line or "LUMAX_DIR" in line:
                                new_lines.append(line)
                                continue
                                
                            # Safe replacement patterns
                            if "FoveAI" in line:
                                line = line.replace("FoveAI", "FoveAI")
                            if "foveai" in line:
                                line = line.replace("foveai", "foveai")
                                
                            if line != orig_line:
                                changed = True
                                log(f"[CONTENT] {os.path.relpath(file_path, base_dir)}:L{i+1}")
                                log(f"  - {orig_line.strip()}")
                                log(f"  + {line.strip()}")
                                
                            new_lines.append(line)
                            
                        if changed:
                            content_replacements.append((file_path, "\n".join(new_lines) + ("\n" if content.endswith("\n") else "")))
                except UnicodeDecodeError:
                    pass # skip binary files disguised with valid extensions
                    
            # 2. File Renaming
            if "FoveAI" in file or "foveai" in file:
                new_file = file.replace("FoveAI", "FoveAI").replace("foveai", "foveai")
                new_path = os.path.join(root, new_file)
                file_renames.append((file_path, new_path))
                log(f"[RENAME] {os.path.relpath(file_path, base_dir)} -> {new_file}")

    log("-" * 40)
    if dry_run:
        log(f"Dry run complete. Found {len(content_replacements)} files to edit and {len(file_renames)} files to rename.")
        log("Run with '--run' argument to execute changes.")
    else:
        log("Executing changes...")
        for file_path, new_content in content_replacements:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        
        for old_path, new_path in file_renames:
            os.rename(old_path, new_path)
            
        log("Refactor complete.")

    log_file.close()

if __name__ == "__main__":
    main()
