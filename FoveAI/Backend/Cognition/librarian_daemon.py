import json
import logging
import os
import shutil
import sys
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import psutil
from huggingface_hub import hf_hub_download
from llama_cpp import Llama

# ─── HARD SAFETY GUARD ───
# DISARMED = True means the librarian will NEVER move or delete files.
# This is a hard-coded safety lock — cannot be overridden by .env or CLI flags.
# Set to False only if you explicitly want to re-enable archival sweeps.
DISARMED = True

# Configure Logging
logging.basicConfig(level=logging.INFO, format="[Librarian] %(asctime)s - %(message)s")
logger = logging.getLogger("Librarian")

FoveAI_ROOT = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = FoveAI_ROOT / "Backend" / "Models"
ARCHIVE_DIR = FoveAI_ROOT / "Archive"
INTERNAL_BACKUPS = ARCHIVE_DIR / "backups"
JUNK_DIR = ARCHIVE_DIR / "junk"
EXTERNAL_BACKUPS = FoveAI_ROOT.parent / "Backup"

EXCLUDED_DIRS = {
    ".venv",
    "node_modules",
    "Models",
    ".git",
    "__pycache__",
    ".idea",
    "backups",
    ".backups",
    "db",
    "unsloth_compiled_cache",
    "Archive",
    "sessions",
    "Build",
    ".pytest_cache",
    ".logs",
    "logs",
}


def set_idle_priority():
    try:
        p = psutil.Process(os.getpid())
        if sys.platform == "win32":
            p.nice(psutil.IDLE_PRIORITY_CLASS)
        else:
            p.nice(19)
        logger.info("💤 Librarian set to IDLE priority.")
    except Exception as e:
        logger.warning(f"Failed to set idle priority: {e}")


def get_lazy_model():
    repo_id = "bartowski/Llama-3.2-1B-Instruct-GGUF"
    filename = "Llama-3.2-1B-Instruct-Q4_K_M.gguf"
    os.makedirs(MODELS_DIR, exist_ok=True)
    model_path = MODELS_DIR / filename

    if not model_path.exists():
        logger.info(f"Downloading tiny 1B librarian model to {model_path}...")
        downloaded = hf_hub_download(
            repo_id=repo_id, filename=filename, local_dir=MODELS_DIR
        )
        model_path = Path(downloaded)

    logger.info("Loading model with mmap=True and 1 thread (CPU lazy mode)...")
    llm = Llama(
        model_path=str(model_path),
        n_ctx=2048,
        n_threads=1,
        n_threads_batch=1,
        use_mmap=True,
        use_mlock=False,
        verbose=False,
    )
    return llm


def perform_smart_backup():
    logger.info("📦 Starting Smart Backup Routine...")
    os.makedirs(INTERNAL_BACKUPS, exist_ok=True)
    os.makedirs(EXTERNAL_BACKUPS, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"foveai_backup_{timestamp}.zip"
    internal_zip_path = INTERNAL_BACKUPS / zip_name

    with zipfile.ZipFile(internal_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(FoveAI_ROOT):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for file in files:
                file_path = Path(root) / file
                try:
                    if file_path.stat().st_size > 10 * 1024 * 1024:
                        continue
                    arcname = file_path.relative_to(FoveAI_ROOT)
                    zipf.write(file_path, arcname)
                except Exception:
                    pass

    logger.info(f"✅ Created internal backup: {internal_zip_path}")

    backups = sorted(
        INTERNAL_BACKUPS.glob("foveai_backup_*.zip"), key=lambda x: x.stat().st_mtime
    )
    while len(backups) > 3:
        oldest = backups.pop(0)
        oldest.unlink()

    external_zip_path = EXTERNAL_BACKUPS / zip_name
    shutil.copy2(internal_zip_path, external_zip_path)
    logger.info(f"🛡️ Mirrored backup externally to {external_zip_path}")

    ext_backups = sorted(
        EXTERNAL_BACKUPS.glob("foveai_backup_*.zip"), key=lambda x: x.stat().st_mtime
    )
    while len(ext_backups) > 3:
        oldest = ext_backups.pop(0)
        oldest.unlink()


def perform_archival_sweep(llm):
    # ─── HARD SAFETY GUARD ───
    if DISARMED:
        logger.info(
            "🔒 Librarian is DISARMED — archival sweep skipped. Set DISARMED = False to re-enable."
        )
        return

    logger.info("🕵️ Starting Archivarian Routine (Safe Mover with Registry)...")
    cutoff_date = datetime.now() - timedelta(days=60)

    stale_files = []
    for root, dirs, files in os.walk(FoveAI_ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
        for file in files:
            if not file.endswith((".py", ".js", ".ts", ".md", ".html")):
                continue
            file_path = Path(root) / file
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime < cutoff_date:
                    stale_files.append(file_path)
            except:
                pass

    if not stale_files:
        logger.info("No stale files found.")
        return

    logger.info(
        f"Found {len(stale_files)} stale files. Archiving and generating registry..."
    )
    os.makedirs(JUNK_DIR, exist_ok=True)
    registry_path = ARCHIVE_DIR / "archive_registry.json"

    registry = []
    if registry_path.exists():
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                registry = json.load(f)
        except:
            pass

    moved_in_this_run = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for sf in stale_files:
        rel_path = sf.relative_to(FoveAI_ROOT)
        dest_path = JUNK_DIR / rel_path

        try:
            with open(sf, "r", encoding="utf-8") as sf_f:
                head = sf_f.read(1000)
            prompt = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\nYou are an archivist. Write a 1-sentence description of what this code does. Start with 'Appears to be...'<|eot_id|><|start_header_id|>user<|end_header_id|>\nCode:\n{head}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"
            output = llm(prompt, max_tokens=30, stop=["<|eot_id|>"], echo=False)
            desc = output["choices"][0]["text"].strip()
        except:
            desc = "Unable to analyze contents."

        try:
            os.makedirs(dest_path.parent, exist_ok=True)
            shutil.move(str(sf), str(dest_path))

            entry = {
                "timestamp": timestamp,
                "original_path": str(sf),
                "archived_path": str(dest_path),
                "assessment": desc,
            }
            registry.append(entry)
            moved_in_this_run.append(entry)
            logger.info(f"📦 Moved to archive: {rel_path}")
        except Exception as e:
            logger.error(f"Failed to move {sf}: {e}")

        time.sleep(2)

    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=4)

    restore_script_path = ARCHIVE_DIR / "Restore_Last_Archive.ps1"
    with open(restore_script_path, "w", encoding="utf-8") as f:
        f.write("# RESTORE SCRIPT - Generated by Smart Librarian\n")
        f.write(f"# Run this to undo the archival run from {timestamp}\n\n")
        for entry in moved_in_this_run:
            archived = entry["archived_path"].replace("'", "''")
            original = entry["original_path"].replace("'", "''")
            f.write(f"Write-Host 'Restoring: {original}'\n")
            f.write(
                f"New-Item -ItemType Directory -Force -Path (Split-Path '{original}') | Out-Null\n"
            )
            f.write(
                f"Move-Item -Path '{archived}' -Destination '{original}' -Force\n\n"
            )
        f.write("Write-Host '✅ Restore Complete!'\n")
        f.write("Pause\n")

    logger.info("✅ Archival sweep complete. Registry updated.")


def prune_feature_inventory():
    logger.info("🧹 Starting Feature Inventory Pruning...")
    plans_dir = FoveAI_ROOT / "Plans"
    history_file = ARCHIVE_DIR / "historical_memory.md"

    if not plans_dir.exists():
        return

    stale_keywords = ["docker", "linux", "wsl", "kuzu", "cognee"]
    pruned_items = []

    for plan_file in plans_dir.glob("*.md"):
        try:
            with open(plan_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            kept_lines = []
            for line in lines:
                if any(kw in line.lower() for kw in stale_keywords):
                    pruned_items.append(f"From {plan_file.name}: {line.strip()}")
                else:
                    kept_lines.append(line)

            if len(kept_lines) != len(lines):
                with open(plan_file, "w", encoding="utf-8") as f:
                    f.writelines(kept_lines)
                logger.info(f"Pruned stale features from {plan_file.name}")
        except Exception as e:
            logger.error(f"Failed to prune {plan_file}: {e}")

    if pruned_items:
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d")
        mode = "a" if history_file.exists() else "w"
        with open(history_file, mode, encoding="utf-8") as f:
            if mode == "w":
                f.write("# 🏛️ Historical Memory (Pruned Features)\n\n")
            f.write(f"## {timestamp} Sweep\n")
            f.writelines(f"- {item} *(Reason: Mentioned legacy paradigm)*\n" for item in pruned_items)
            f.write("\n")
        logger.info(
            f"✅ Logged {len(pruned_items)} pruned features to historical_memory.md"
        )


def update_core_authority(llm):
    logger.info("📜 Updating Core Authority Files...")
    timestamp = datetime.now().strftime("%Y-%m-%d")

    prompt = "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\nYou are the Project Historian. Write exactly 3 short sentences. Sentence 1: The Past (We moved away from Linux/Docker). Sentence 2: The Present (We use Windows-Native, Dexie, TokenSlayer). Sentence 3: The Vision (Highly optimized, zero-drag AI swarm).<|eot_id|><|start_header_id|>user<|end_header_id|>\nGo.<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n"

    try:
        output = llm(prompt, max_tokens=100, stop=["<|eot_id|>"], echo=False)
        brief = output["choices"][0]["text"].strip()
    except Exception as e:
        logger.error(f"LLM failed to generate authority brief: {e}")
        return

    log_entry = f"\n\n## 🏛️ Historian's Log ({timestamp})\n{brief}\n"

    for filename in ["ARCHITECTURE.md", "context.md"]:
        filepath = FoveAI_ROOT / filename
        if filepath.exists():
            try:
                # Basic check to avoid appending infinite logs
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                if f"Historian's Log ({timestamp})" not in content:
                    with open(filepath, "a", encoding="utf-8") as f:
                        f.write(log_entry)
                    logger.info(f"✅ Appended Historian's Log to {filename}")
            except Exception as e:
                logger.error(f"Failed to update {filename}: {e}")


def librarian_loop(llm):
    # ─── HARD SAFETY GUARD ───
    if DISARMED:
        logger.info(
            "🔒 Librarian is DISARMED — loop will not run. Set DISARMED = False to re-enable."
        )
        return

    logger.info("📚 Librarian started its watch. Will perform duties every 24 hours.")
    last_run_time = 0
    INTERVAL = 24 * 60 * 60

    while True:
        try:
            current_time = time.time()
            if current_time - last_run_time > INTERVAL:
                logger.info("⏰ Time for the daily sweeps!")
                perform_smart_backup()
                perform_archival_sweep(llm)
                prune_feature_inventory()
                update_core_authority(llm)
                last_run_time = time.time()

            time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Librarian shutting down.")
            break
        except Exception as e:
            logger.error(f"Error in lazy loop: {e}")
            time.sleep(60)


if __name__ == "__main__":
    set_idle_priority()
    llm = get_lazy_model()
    librarian_loop(llm)
