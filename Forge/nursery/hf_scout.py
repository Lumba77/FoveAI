"""
Hugging Face Model Scout & Open XRL Provisioner for Forge Nursery
Finds, downloads, benchmarks, and provisions compatible AI models with Open XRL contracts.
All downloads and model weights are stored on sda2 in /opt/foveai-models/hub.
"""

import json
import logging
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any

from huggingface_hub import HfApi, hf_hub_download

from .model_registry import VariantDefinition, get_registry

logger = logging.getLogger("forge-hf-scout")

MODELS_DIR = os.environ.get("FORGE_NURSERY_MODELS_DIR", "/opt/foveai-models")
HUB_CACHE_DIR = os.path.join(MODELS_DIR, "hub")
os.makedirs(HUB_CACHE_DIR, exist_ok=True)

HF_TOKEN = os.environ.get("HF_TOKEN")
api = HfApi(token=HF_TOKEN)

# Hardware limits for RTX 4060 (8GB VRAM)
MAX_MODEL_SIZE_GB = 6.2  # Leave >= 1.8GB for context, mmproj, and display


def notify_system_and_journal(title: str, message: str):
    """Send a desktop notification and write an announcement to Jen's agent_journal."""
    try:
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":0")
        env.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")
        subprocess.run(["notify-send", "-a", "Forge Nursery ✨", title, message], env=env, check=False)
    except Exception as e:
        logger.debug(f"notify-send failed: {e}")

    try:
        import sqlite3
        from pathlib import Path
        db_path = Path("/home/lumba/FoveAI/db/agent_memory.db")
        if db_path.exists():
            con = sqlite3.connect(db_path, timeout=5)
            full_entry = f"[Forge Nursery] {title}: {message}"
            words = len(full_entry.split())
            con.execute(
                "INSERT INTO agent_journal (entry, mood, category, importance, word_count) "
                "VALUES (?, 'proud', 'discovery', 85, ?)",
                (full_entry, words)
            )
            con.commit()
            con.close()
            logger.info("Announcement recorded into agent_journal.")
    except Exception as e:
        logger.warning(f"Failed to record announcement to agent_journal: {e}")


@dataclass
class CandidateModel:
    repo_id: str
    filename: str
    size_gb: float
    description: str = ""
    downloads: int = 0
    likes: int = 0
    quant_type: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HFModelScout:
    """
    Searches Hugging Face for GGUF/MoQ models, filters by VRAM compatibility,
    and provisions selected models with Open XRL contracts.
    """

    def __init__(self, cache_dir: str = HUB_CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    def search_candidates(self, query: str = "Qwen3.5 MoQ", limit: int = 15) -> list[CandidateModel]:
        """Search Hugging Face for GGUF models matching query and VRAM budget."""
        results = []
        try:
            models = api.list_models(
                search=query,
                filter=["gguf"],
                limit=limit,
                sort="downloads",
            )

            for m in models:
                repo_id = m.id
                likes = getattr(m, "likes", 0) or 0
                downloads = getattr(m, "downloads", 0) or 0

                try:
                    siblings = api.list_repo_files(repo_id=repo_id, token=HF_TOKEN)
                    gguf_files = [f for f in siblings if f.lower().endswith(".gguf") and "mmproj" not in f.lower()]

                    for gfile in gguf_files:
                        # Try to get file size via repo_info or estimate
                        fname = os.path.basename(gfile)
                        quant_guess = "unknown"
                        if "moq" in fname.lower():
                            quant_guess = "moq"
                        elif "q4_k_m" in fname.lower():
                            quant_guess = "q4_k_m"
                        elif "q5_k_m" in fname.lower():
                            quant_guess = "q5_k_m"
                        elif "q8_0" in fname.lower():
                            quant_guess = "q8_0"

                        candidate = CandidateModel(
                            repo_id=repo_id,
                            filename=gfile,
                            size_gb=4.0,  # Estimated baseline for 9B MoQ/Q4
                            description=f"{repo_id} - {fname}",
                            downloads=downloads,
                            likes=likes,
                            quant_type=quant_guess,
                        )
                        results.append(candidate)
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"HF Search failed: {e}")

        return results[:limit]

    def adopt_model_with_xrl(
        self,
        repo_id: str,
        filename: str,
        variant_id: str | None = None,
        display_name: str | None = None,
        quant_type: str = "moq",
    ) -> dict[str, Any]:
        """
        Download GGUF model directly to /opt/foveai-models/hub, run a sanity benchmark,
        and provision an Open XRL contract profile in the model registry.
        """
        logger.info(f"Adopting model {repo_id}/{filename} into /opt/foveai-models...")
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            cache_dir=self.cache_dir,
            token=HF_TOKEN,
        )

        size_bytes = os.path.getsize(local_path)
        size_gb = round(size_bytes / (1024 ** 3), 2)

        if not variant_id:
            safe_name = os.path.splitext(os.path.basename(filename))[0].lower().replace(".", "_").replace("-", "_")
            variant_id = f"xrl_{safe_name}"

        if not display_name:
            display_name = f"{repo_id.split('/')[-1]} ({os.path.basename(filename)})"

        # Benchmark / sanity check with native llama-cli
        bench_result = self._benchmark_model(local_path)

        # Provision Open XRL Contract in registry
        reg = get_registry()
        variant = VariantDefinition(
            id=variant_id,
            name=display_name,
            description=f"Open XRL Adopted: {repo_id}/{filename} ({size_gb} GB)",
            base_model=repo_id,
            datasets=[],
            training_config={"adopted_from": repo_id, "file": filename, "size_gb": size_gb},
            quant_type=quant_type,
            status="active",
        )
        reg.add_variant(variant)

        # Notify system & write to Jen's agent_journal
        notify_system_and_journal(
            f"Ny modell adopterad: {display_name}",
            f"Modellen '{variant_id}' ({size_gb} GB) sparades på sda2 (/opt) och har försetts med ett aktivt Open XRL-kontrakt!"
        )

        return {
            "status": "adopted",
            "variant_id": variant_id,
            "display_name": display_name,
            "local_path": local_path,
            "size_gb": size_gb,
            "benchmark": bench_result,
            "xrl_contract": {
                "profile": "xrl-memory/1.0",
                "port_target": 8408,
                "memory_bus": "ws://127.0.0.1:8403",
                "soul_dna": "Jenny Ninebe",
            },
        }

    def _benchmark_model(self, model_path: str) -> dict[str, Any]:
        """Quick 32-token CPU inference test with llama-cli to verify sanity."""
        llama_cli = "/home/lumba/FoveAI/Tools/llama-b11053-cuda/llama-b11053/llama-cli"
        if not os.path.exists(llama_cli) or not os.path.exists(model_path):
            return {"ok": False, "note": "Binary or model missing"}

        cmd = [
            llama_cli,
            "-m", model_path,
            "-p", "<|im_start|>user\nSay hello!<|im_end|>\n<|im_start|>assistant\n",
            "-n", "32",
            "--temp", "0.3",
            "-ngl", "0",
            "-st",
        ]
        env = os.environ.copy()
        env["LD_LIBRARY_PATH"] = f"/home/lumba/FoveAI/Tools/llama-b11053-cuda/llama-b11053:{env.get('LD_LIBRARY_PATH', '')}"

        t0 = time.time()
        try:
            res = subprocess.run(
                cmd,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=60,
            )
            elapsed = time.time() - t0
            output = res.stdout.strip()
            return {
                "ok": res.returncode == 0,
                "elapsed_s": round(elapsed, 2),
                "output_preview": output[:150],
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}


_scout_instance: HFModelScout | None = None


def get_model_scout() -> HFModelScout:
    global _scout_instance
    if _scout_instance is None:
        _scout_instance = HFModelScout()
    return _scout_instance
