import http.server
import json
import os
import socketserver
import subprocess
import threading
import urllib.request
import webbrowser
from functools import partial
from pathlib import Path

SANDBOX_DIR = Path(__file__).parent.resolve()
PARENT_DIR = SANDBOX_DIR.parent.resolve()
DEBUG_LOG = SANDBOX_DIR / "sandbox_debug.json"


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env(PARENT_DIR / ".env")

PORT: int = int(os.getenv("SELFCODER_PORT", "9999"))
API_URL: str = os.getenv(
    "FOVEAI_NVIDIA_URL", "https://integrate.api.nvidia.com/v1/chat/completions"
)
API_KEY: str = os.getenv("FOVEAI_NVIDIA_API_KEY", "")
MODEL_NAME: str = os.getenv("FOVEAI_NVIDIA_MODEL", "moonshotai/kimi-k3")
REASONING: str = os.getenv("FOVEAI_NVIDIA_REASONING", "").lower()

# Removed the 'f' prefix to stop Python from parsing the JSON curly brackets
SYSTEM_PROMPT = """You are an Autonomous Voice Coder sandboxed in a workspace subfolder. Return ONLY a raw JSON object matching this schema exactly:
{
  "thought": "Your internal logic analyzing file system state and previous command error codes closely.",
  "speak": "The text the browser should read out loud.",
  "commands": ["pip install flask"],
  "files": [{"path": "index.html", "content": "... full html code ..."}]
}
Rule: Do not wrap your response in markdown code blocks or ticks. Ensure HTML files keep voice recognition hooks."""


def append_log(entries: list) -> None:
    logs: list = []
    if DEBUG_LOG.is_file():
        try:
            logs = json.loads(DEBUG_LOG.read_text())
        except Exception:
            logs = []
    logs.extend(entries)
    DEBUG_LOG.write_text(json.dumps(logs[-50:], indent=2))


def call_llm(prompt: str) -> str:
    body: dict = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 4096,
        "temperature": 0.4,
        "stream": False,
        "response_format": {"type": "json_object"},
    }
    effort = {"max": "high", "min": "low"}.get(REASONING, REASONING)
    if effort in ("low", "medium", "high"):
        body["reasoning_effort"] = effort

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 400 and ("reasoning_effort" in body or "response_format" in body):
            body.pop("reasoning_effort", None)
            body.pop("response_format", None)
            req = urllib.request.Request(
                API_URL,
                data=json.dumps(body).encode(),
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read())
        else:
            raise
    return data["choices"][0]["message"]["content"] or ""


def parse_payload(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        text = text.removeprefix("json")
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])


def safe_write(rel_path: str, content: str) -> str:
    target = (SANDBOX_DIR / rel_path).resolve()
    if SANDBOX_DIR not in target.parents and target != SANDBOX_DIR:
        raise ValueError(f"refused write outside sandbox: {rel_path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return str(target.relative_to(SANDBOX_DIR))


def run_command(cmd: str) -> dict:
    try:
        p = subprocess.run(
            cmd,
            shell=True,
            cwd=SANDBOX_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return {"command": cmd, "stdout": p.stdout[-4000:], "stderr": p.stderr[-4000:]}
    except Exception as e:
        return {"command": cmd, "error": str(e)}


def process(prompt: str) -> dict:
    payload = parse_payload(call_llm(prompt))
    logs = [run_command(c) for c in payload.get("commands", [])]
    written = []
    for f in payload.get("files", []):
        try:
            written.append(safe_write(f["path"], f["content"]))
        except Exception as e:
            logs.append({"command": f"write {f.get('path')}", "error": str(e)})
    if logs:
        append_log(logs)
    return {
        "speak": payload.get("speak", "Done."),
        "thought": payload.get("thought", ""),
        "files_written": written,
    }


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/api/process":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            result = process(body.get("prompt", ""))
            out = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
        except Exception as e:
            out = json.dumps({"speak": f"Error: {e}", "error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()

    def log_message(self, fmt: str, *args) -> None:
        print(f"[selfcoder] {fmt % args}")


if __name__ == "__main__":
    if not API_KEY:
        print("WARNING: FOVEAI_NVIDIA_API_KEY not set (checked env + ../.env)")
    print(
        f"Self-coder on http://localhost:{PORT}  model={MODEL_NAME}  sandbox={SANDBOX_DIR}"
    )
    server = socketserver.ThreadingTCPServer(
        ("127.0.0.1", PORT), partial(Handler, directory=str(SANDBOX_DIR))
    )
    server.daemon_threads = True
    threading.Timer(
        1.0, lambda: webbrowser.open(f"http://localhost:{PORT}/index.html")
    ).start()
    server.serve_forever()
