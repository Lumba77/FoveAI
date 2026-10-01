#!/usr/bin/env python3
"""FoveAI Native Messaging Host — bridges Chrome Extension ↔ local system.

Chrome native messaging protocol: 4-byte little-endian length prefix + UTF-8 JSON.
This script reads commands from Chrome stdin, executes them, and sends responses back.

LLM backends managed as headless processes:
- llama-cpp-python — port 8081, BEST for low-VRAM (partial GPU offloading)
- LM Studio (lms/cli) — port 1234, OpenAI-compatible (also partial offload)
- vLLM — port 8001, fastest throughput but NO partial offload (model must fit in VRAM)
- LiteLLM — port 4000, proxy to any backend
- Ollama — port 11434, native + OpenAI-compatible (also partial offload via llama.cpp)
"""

import glob
import json
import os
import shutil
import struct
import subprocess
import sys

FoveAI_ROOT = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

# ── Chrome native messaging protocol ──


def read_message():
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        sys.exit(0)
    length = struct.unpack("=I", raw)[0]
    data = sys.stdin.buffer.read(length)
    return json.loads(data.decode("utf-8"))


def send_message(msg):
    encoded = json.dumps(msg).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("=I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


# ── Helpers ──


def find_in_path(name):
    """Check if a command exists in PATH."""
    result = shutil.which(name)
    return result is not None


def find_in_common_dirs(patterns):
    """Search common install locations for executables."""
    common = [
        os.path.expanduser("~"),
        os.path.expanduser("~/AppData/Local"),
        os.path.expanduser("~/AppData/Local/Programs"),
        "C:/Program Files",
        "C:/Program Files (x86)",
    ]
    for base in common:
        for pattern in patterns:
            matches = glob.glob(os.path.join(base, pattern))
            if matches:
                return matches[0]
    return None


def http_get(url, timeout=2):
    """Quick HTTP GET, returns (ok, status_code)."""
    import urllib.error
    import urllib.request

    try:
        req = urllib.request.urlopen(url, timeout=timeout)
        return True, req.status
    except:
        return False, 0


def http_get_json(url, timeout=2):
    """HTTP GET expecting JSON response."""
    import urllib.error
    import urllib.request

    try:
        req = urllib.request.urlopen(url, timeout=timeout)
        return json.loads(req.read().decode("utf-8"))
    except:
        return None


# ── LLM Backend Definitions ──

BACKENDS = {
    "llama_cpp": {
        "name": "llama-cpp-python",
        "detect_commands": ["python"],
        "detect_paths": [],
        "detect_modules": ["llama_cpp"],
        "default_port": 8081,
        # llama-cpp-python server: OpenAI-compatible, partial GPU offload via n_gpu_layers
        # Example: python -m llama_cpp.server --model model.gguf --port 8081 --n_gpu_layers 40
        "start_cmd": [
            "python",
            "-m",
            "llama_cpp.server",
            "--model",
            "{model}",
            "--port",
            "{port}",
            "--host",
            "0.0.0.0",
            "--n_gpu_layers",
            "{n_gpu_layers}",
        ],
        "health_url": "http://127.0.0.1:{port}/v1/models",
        "models_url": "http://127.0.0.1:{port}/v1/models",
        "supports_offload": True,
        "offload_description": "Set n_gpu_layers to control GPU/CPU split. -1=all GPU, 0=all CPU, 40=partial",
    },
    "lmstudio": {
        "name": "LM Studio",
        "detect_commands": ["lms"],
        "detect_paths": [
            os.path.expanduser("~/AppData/Local/lm-studio/lms.exe"),
            os.path.expanduser("~/AppData/Local/Programs/LM Studio/lms.exe"),
        ],
        "default_port": 1234,
        "start_cmd": ["lms", "start", "--port", "{port}"],
        "health_url": "http://127.0.0.1:{port}/v1/models",
        "models_url": "http://127.0.0.1:{port}/v1/models",
    },
    "vllm": {
        "name": "vLLM",
        "detect_commands": ["vllm"],
        "detect_paths": [],
        "default_port": 8001,
        "start_cmd": [
            "python",
            "-m",
            "vllm.serve",
            "--model",
            "{model}",
            "--port",
            "{port}",
            "--host",
            "0.0.0.0",
        ],
        "health_url": "http://127.0.0.1:{port}/health",
        "models_url": "http://127.0.0.1:{port}/v1/models",
        "supports_offload": False,
        "offload_description": "vLLM requires entire model in VRAM. No CPU offloading.",
    },
    "litellm": {
        "name": "LiteLLM",
        "detect_commands": ["litellm"],
        "detect_paths": [],
        "default_port": 4000,
        "start_cmd": ["litellm", "--port", "{port}"],
        "health_url": "http://127.0.0.1:{port}/health",
        "models_url": "http://127.0.0.1:{port}/v1/models",
    },
    "ollama": {
        "name": "Ollama",
        "detect_commands": ["ollama"],
        "detect_paths": [
            os.path.expanduser("~/AppData/Local/Programs/Ollama/ollama.exe"),
        ],
        "default_port": 11434,
        "start_cmd": ["ollama", "serve"],
        "health_url": "http://127.0.0.1:{port}/api/tags",
        "models_url": "http://127.0.0.1:{port}/api/tags",
        "supports_offload": True,
        "offload_description": "Ollama auto-detects GPU layers. Uses llama.cpp internally.",
    },
}

# Track running backend processes
_running = {}
# Track proxy PIDs for clean shutdown
_proxy_pids = []

# ── Command Handlers ──


def handle_command(cmd):
    action = cmd.get("action", "")

    # ── System actions (Phase 2) ──

    if action == "ping":
        return {"status": "ok", "message": "pong", "root": FoveAI_ROOT}

    elif action == "start":
        try:
            import shutil

            # ── Pre-flight diagnostics ──
            diagnostics = []

            # Check if Start_Concordia.PS1 exists
            ps1_path = os.path.join(FoveAI_ROOT, "Start_Concordia.PS1")
            if not os.path.exists(ps1_path):
                diagnostics.append("❌ Start_Concordia.PS1 not found")
            else:
                diagnostics.append("✅ Start_Concordia.PS1 found")

            # Check if node is available
            node_path = shutil.which("node")
            if not node_path:
                diagnostics.append("❌ Node.js not found in PATH")
            else:
                diagnostics.append(f"✅ Node.js found: {node_path}")

            # Check if node_modules exists for the frontend
            node_modules_path = os.path.join(
                FoveAI_ROOT, "Frontend", "3D_Avatar_Chatbot", "node_modules"
            )
            if not os.path.exists(node_modules_path):
                diagnostics.append("⚠ node_modules missing — will auto-install")
            else:
                diagnostics.append("✅ node_modules present")

            # Check if Python venv exists
            venv_path = os.path.join(FoveAI_ROOT, ".venv", "Scripts", "python.exe")
            if not os.path.exists(venv_path):
                diagnostics.append("⚠ .venv python not found — will use system python")
            else:
                diagnostics.append("✅ .venv python found")

            # Check if sleipnir_launcher.js exists
            js_path = os.path.join(FoveAI_ROOT, "sleipnir_launcher.js")
            if not os.path.exists(js_path):
                diagnostics.append("❌ sleipnir_launcher.js not found")
            else:
                diagnostics.append("✅ sleipnir_launcher.js found")

            # ── Launch the start script (fire-and-forget) ──
            # IMPORTANT: Do NOT use creationflags=0x00000008 (CREATE_NO_WINDOW) —
            # that prevents ANY window from appearing, even with -WindowStyle Normal.
            # The user needs to see the PowerShell window to spot errors.
            subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-WindowStyle",
                    "Normal",
                    "-File",
                    ps1_path,
                ],
                cwd=FoveAI_ROOT,
            )

            # Return immediately — do NOT block the native messaging pipe.
            # Chrome's native messaging protocol expects a quick response.
            # The popup.js will poll for service readiness via httpStatus().
            return {
                "status": "ok",
                "message": "✅ FoveAI stack starting... A PowerShell window should be open. The extension will check service health automatically.",
                "diagnostics": diagnostics,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"❌ Exception in start handler: {e!s}",
            }

    elif action == "stop":
        try:
            # Stop tracked backend processes
            for name, proc in _running.items():
                try:
                    proc.terminate()
                except:
                    pass
            _running.clear()
            # Kill proxy processes by PID (reliable, no window title matching)
            for name, pid in _proxy_pids:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True,
                        timeout=5,
                    )
                except:
                    pass
            _proxy_pids.clear()
            # Stop ALL FoveAI services — sleipnir_launcher.js spawns node + python processes
            # in hidden windows, so window title matching won't work. Use port-based killing
            # on all known FoveAI ports instead.
            foveai_ports = [
                8400,
                8401,
                8402,
                8403,
                8300,
                8001,
                8002,
                8003,
                8004,
                8080,
                8101,
                8103,
                8104,
                8106,
                8109,
                8110,
                8112,
                8113,
                8888,
                5000,
            ]
            for port in foveai_ports:
                subprocess.run(
                    f'for /f "tokens=5" %a in (\'netstat -ano ^| findstr ":{port} "\') do @taskkill /F /PID %a 2>nul',
                    shell=True,
                    capture_output=True,
                    timeout=5,
                )
            # Kill node.exe processes (NOT python.exe — that would kill us!)
            subprocess.run(
                "taskkill /F /IM node.exe 2>nul",
                shell=True,
                capture_output=True,
                timeout=5,
            )

            # Wait for ports to actually clear
            import time

            deadline = time.time() + 10
            while time.time() < deadline:
                still_running = False
                for port in foveai_ports:
                    result = subprocess.run(
                        f'netstat -ano | findstr ":{port} "',
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    if result.stdout.strip():
                        still_running = True
                        break
                if not still_running:
                    return {
                        "status": "ok",
                        "message": "FoveAI services stopped. All ports clear.",
                    }
                time.sleep(1)

            return {
                "status": "ok",
                "message": "FoveAI services stopping... (some ports may take a moment to release)",
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif action == "status":

        services = {}
        for name, port in [
            ("soul", 8402),
            ("proxy", 8400),
            ("dashboard", 8401),
            ("ws_ipc", 8403),
            ("ears", 8001),
            ("memory", 8002),
            ("creative", 8003),
            ("mouth", 8004),
            ("soundboard", 8006),
            ("mcp", 8005),
            ("webui", 8080),
        ]:
            alive, _ = http_get(f"http://127.0.0.1:{port}/health")
            services[name] = {"alive": alive, "port": port}
        alive = sum(1 for s in services.values() if s["alive"])
        return {"status": "ok", "services": services, "alive_count": alive}

    elif action == "build":
        try:
            xr_dir = os.path.join(FoveAI_ROOT, "Frontend", "3D_Avatar_Chatbot")
            result = subprocess.run(
                ["npm.cmd", "run", "build"],
                cwd=xr_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return {
                "status": "ok" if result.returncode == 0 else "error",
                "output": result.stdout[-500:] + result.stderr[-500:],
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif action == "git_pull":
        try:
            result = subprocess.run(
                ["git", "pull"],
                cwd=FoveAI_ROOT,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return {
                "status": "ok" if result.returncode == 0 else "error",
                "output": result.stdout + result.stderr,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif action == "open_dev_terminal":
        return {"status": "ok", "action": "open_tab", "url": "http://localhost:8080/"}

    # ── File & Shell actions (Phase 4: FoveAI Cline) ──

    elif action == "read_file":
        """Read a file from the FoveAI repo."""
        path = cmd.get("path", "")
        if not path:
            return {"status": "error", "message": "No path specified"}
        # Resolve relative to FoveAI_ROOT
        if not os.path.isabs(path):
            path = os.path.join(FoveAI_ROOT, path)
        # Safety: only allow reading within FoveAI_ROOT
        if not os.path.abspath(path).startswith(os.path.abspath(FoveAI_ROOT)):
            return {
                "status": "error",
                "message": "Access denied: path outside FoveAI_ROOT",
            }
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            return {"status": "ok", "content": content, "path": path}
        except FileNotFoundError:
            return {"status": "error", "message": f"File not found: {path}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif action == "write_file":
        """Write a file in the FoveAI repo."""
        path = cmd.get("path", "")
        content = cmd.get("content", "")
        if not path:
            return {"status": "error", "message": "No path specified"}
        if not os.path.isabs(path):
            path = os.path.join(FoveAI_ROOT, path)
        if not os.path.abspath(path).startswith(os.path.abspath(FoveAI_ROOT)):
            return {
                "status": "error",
                "message": "Access denied: path outside FoveAI_ROOT",
            }
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return {
                "status": "ok",
                "message": f"Written {len(content)} chars to {path}",
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif action == "list_files":
        """List directory contents."""
        path = cmd.get("path", "")
        recursive = cmd.get("recursive", False)
        if not path:
            path = FoveAI_ROOT
        if not os.path.isabs(path):
            path = os.path.join(FoveAI_ROOT, path)
        if not os.path.abspath(path).startswith(os.path.abspath(FoveAI_ROOT)):
            return {"status": "error", "message": "Access denied"}
        try:
            entries = []
            for entry in os.scandir(path):
                entries.append(
                    {
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "size": entry.stat().st_size if entry.is_file() else 0,
                    }
                )
            entries.sort(key=lambda e: (not e["is_dir"], e["name"]))
            return {"status": "ok", "entries": entries, "path": path}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif action == "search_files":
        """Search for a regex pattern in files."""
        import re

        path = cmd.get("path", "")
        pattern = cmd.get("pattern", "")
        file_pattern = cmd.get("file_pattern", "")
        if not path:
            path = FoveAI_ROOT
        if not os.path.isabs(path):
            path = os.path.join(FoveAI_ROOT, path)
        if not pattern:
            return {"status": "error", "message": "No pattern specified"}
        try:
            regex = re.compile(pattern, re.IGNORECASE)
            results = []
            # Skip binary dirs
            skip_dirs = {
                ".git",
                ".venv",
                "node_modules",
                "__pycache__",
                ".aider-venv",
                "webvm_source",
            }
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                for fname in files:
                    if file_pattern and not fname.endswith(file_pattern.lstrip("*")):
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            for i, line in enumerate(f, 1):
                                if regex.search(line):
                                    rel = os.path.relpath(fpath, FoveAI_ROOT)
                                    results.append(
                                        {
                                            "file": rel,
                                            "line": i,
                                            "text": line.strip()[:200],
                                        }
                                    )
                                    if len(results) >= 30:
                                        return {
                                            "status": "ok",
                                            "results": results,
                                            "truncated": True,
                                        }
                    except:
                        pass
            return {"status": "ok", "results": results}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif action == "exec":
        """Execute a shell command and return output."""
        command = cmd.get("command", "")
        if not command:
            return {"status": "error", "message": "No command specified"}
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=FoveAI_ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return {
                "status": "ok" if result.returncode == 0 else "error",
                "exit_code": result.returncode,
                "stdout": result.stdout[-2000:],
                "stderr": result.stderr[-500:],
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Command timed out (30s)"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ── LLM Backend actions (Phase 3) ──

    elif action == "llm_detect":
        """Scan system for installed LLM backends."""
        found = {}
        for key, cfg in BACKENDS.items():
            installed = False
            exe_path = None

            # Check PATH
            for c in cfg["detect_commands"]:
                p = shutil.which(c)
                if p:
                    installed = True
                    exe_path = p
                    break

            # Check Python modules (e.g., llama_cpp)
            if not installed and "detect_modules" in cfg:
                for mod in cfg["detect_modules"]:
                    result = subprocess.run(
                        ["python", "-c", f"import {mod}; print({mod}.__version__)"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        installed = True
                        exe_path = f"python -m {mod}"
                        break

            # Check common install locations
            if not installed:
                for p in cfg["detect_paths"]:
                    if os.path.isfile(p):
                        installed = True
                        exe_path = p
                        break

            # Check if already running
            port = cfg["default_port"]
            alive, _ = http_get(cfg["health_url"].format(port=port))

            found[key] = {
                "name": cfg["name"],
                "installed": installed,
                "path": exe_path,
                "running": alive,
                "port": port,
                "supports_offload": cfg.get("supports_offload", False),
                "offload_description": cfg.get("offload_description", ""),
            }

        return {"status": "ok", "backends": found}

    elif action == "llm_start":
        """Start an LLM backend as a headless process.
        
        Reads .env to determine which LLM to start if no explicit backend/model given.
        Kills any conflicting processes on the target port before starting.
        """
        backend = cmd.get("backend", "")
        model = cmd.get("model", "")
        n_gpu_layers = cmd.get("n_gpu_layers", "-1")  # -1 = all layers to GPU
        port = cmd.get("port", 0)

        # If no explicit backend, read from .env
        if not backend:
            env_path = os.path.join(FoveAI_ROOT, ".env")
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("FoveAI_CHAT_PROVIDER="):
                            backend = line.split("=", 1)[1].strip().lower()
                        elif line.startswith("FoveAI_LOCAL_ENGINE="):
                            if not backend:
                                backend = line.split("=", 1)[1].strip().lower()
                        elif line.startswith("FoveAI_MODEL_LOCAL_PATH="):
                            if not model:
                                model = line.split("=", 1)[1].strip()
                        elif line.startswith("FoveAI_LOCAL_BASE_URL="):
                            if not port:
                                url = line.split("=", 1)[1].strip()
                                import re

                                m = re.search(r":(\d+)", url)
                                if m:
                                    port = int(m.group(1))

        # Map provider names to backend keys
        provider_map = {
            "unsloth": "llama_cpp",
            "lmstudio": "lmstudio",
            "ollama": "ollama",
            "llama_cpp": "llama_cpp",
            "litellm": "litellm",
            "vllm": "vllm",
        }
        backend = provider_map.get(backend, backend)

        if backend not in BACKENDS:
            return {
                "status": "error",
                "message": f"Unknown backend: {backend}. Available: {list(BACKENDS.keys())}",
            }

        cfg = BACKENDS[backend]
        if not port:
            port = cfg["default_port"]

        # Kill any existing process on the target port
        try:
            import psutil

            for proc in psutil.process_iter(["pid", "name", "connections"]):
                try:
                    for conn in proc.connections():
                        if conn.laddr.port == port:
                            proc.kill()
                            time.sleep(0.5)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except ImportError:
            # Fallback: use netstat + taskkill
            subprocess.run(
                f'for /f "tokens=5" %a in (\'netstat -ano ^| findstr ":{port} "\') do @taskkill /F /PID %a 2>nul',
                shell=True,
                capture_output=True,
                timeout=5,
            )

        # Check if already running (after killing conflicts)
        alive, _ = http_get(cfg["health_url"].format(port=port))
        if alive:
            return {
                "status": "ok",
                "message": f"{cfg['name']} already running on port {port}",
                "port": port,
            }

        # Build command (support n_gpu_layers for llama-cpp-python)
        fmt = {"port": port, "model": model, "n_gpu_layers": n_gpu_layers}
        start_cmd = [c.format(**fmt) for c in cfg["start_cmd"]]

        try:
            proc = subprocess.Popen(
                start_cmd,
                cwd=FoveAI_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x00000008,  # DETACHED_PROCESS
            )
            _running[backend] = proc
            return {
                "status": "ok",
                "message": f"{cfg['name']} starting on port {port}...",
                "port": port,
                "pid": proc.pid,
            }
        except FileNotFoundError:
            return {
                "status": "error",
                "message": f"{cfg['name']} not found. Is it installed and in PATH?",
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif action == "llm_stop":
        """Stop an LLM backend process."""
        backend = cmd.get("backend", "")
        if backend in _running:
            try:
                _running[backend].terminate()
                del _running[backend]
                return {
                    "status": "ok",
                    "message": f"{BACKENDS[backend]['name']} stopped",
                }
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return {"status": "ok", "message": "Not running (or started outside extension)"}

    elif action == "llm_status":
        """Check LLM backend health and list models."""
        results = {}
        for key, cfg in BACKENDS.items():
            port = cmd.get("port", cfg["default_port"])
            if isinstance(port, dict):
                port = port.get(key, cfg["default_port"])
            alive, _ = http_get(cfg["health_url"].format(port=port))
            models = []
            if alive:
                data = http_get_json(cfg["models_url"].format(port=port))
                if data and "data" in data:
                    models = [m.get("id", "?") for m in data["data"]]
                elif data and "models" in data:  # Ollama format
                    models = [m.get("name", "?") for m in data.get("models", [])]
            results[key] = {
                "name": cfg["name"],
                "running": alive,
                "port": port,
                "models": models,
            }
        return {"status": "ok", "backends": results}

    elif action == "llm_list_models":
        """List models for a specific running backend."""
        backend = cmd.get("backend", "")
        if backend not in BACKENDS:
            return {"status": "error", "message": f"Unknown backend: {backend}"}
        cfg = BACKENDS[backend]
        port = cmd.get("port", cfg["default_port"])
        data = http_get_json(cfg["models_url"].format(port=port))
        if data is None:
            return {
                "status": "error",
                "message": f"Cannot reach {cfg['name']} on port {port}",
            }
        if "data" in data:
            models = [m.get("id", "?") for m in data["data"]]
        elif "models" in data:
            models = [m.get("name", "?") for m in data.get("models", [])]
        else:
            models = []
        return {"status": "ok", "models": models}

    elif action == "set_vault_password":
        pwd = cmd.get("password")
        if pwd:
            try:
                # Try keyring first, fall back to local file
                try:
                    import keyring

                    keyring.set_password("Lumax", "DormantEggPassword", pwd)
                except ImportError:
                    pass
                # Always save to local vault file as reliable fallback
                vault_dir = os.path.join(FoveAI_ROOT, ".foveai")
                os.makedirs(vault_dir, exist_ok=True)
                vault_path = os.path.join(vault_dir, "vault_pass.json")
                with open(vault_path, "w") as f:
                    json.dump({"password": pwd}, f)
                return {"status": "ok"}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return {"status": "error", "message": "no password provided"}

    elif action == "generate_dormant_egg":
        pwd = cmd.get("password")
        if pwd:
            try:
                import base64

                import pyzipper

                egg_path = os.path.join(FoveAI_ROOT, "Lumax_Dormant_Egg.zip")
                env_path = os.path.join(FoveAI_ROOT, ".env")
                soul_path = os.path.join(
                    FoveAI_ROOT, "Backend", "Cognition", "jen_soul.json"
                )
                with pyzipper.AESZipFile(
                    egg_path,
                    "w",
                    compression=pyzipper.ZIP_LZMA,
                    encryption=pyzipper.WZ_AES,
                ) as zf:
                    zf.setpassword(pwd.encode("utf-8"))
                    if os.path.exists(env_path):
                        zf.write(env_path, ".env")
                    if os.path.exists(soul_path):
                        zf.write(soul_path, "jen_soul.json")
                    zf.writestr(
                        "RECOVERY_INSTRUCTIONS.txt",
                        "Master AES key inside .env. Password recovered via Google Sync.",
                    )
                with open(egg_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                os.remove(egg_path)
                return {"status": "ok", "egg_base64": b64}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        return {"status": "error", "message": "no password provided"}

    return {"status": "error", "message": f"Unknown action: {action}"}


if __name__ == "__main__":
    try:
        msg = read_message()
        response = handle_command(msg)
        send_message(response)
    except Exception as e:
        send_message({"status": "error", "message": str(e)})
