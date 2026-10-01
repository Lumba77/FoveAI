from pathlib import Path

PORT = 9999
API_URL = "https://nvidia.com"
API_KEY = "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"
MODEL_NAME = "moonshotai/kimi-k3"

SANDBOX_DIR = Path(__file__).parent.resolve()
PARENT_DIR = SANDBOX_DIR.parent.resolve()

# Removed the 'f' prefix to stop Python from parsing the JSON curly brackets
SYSTEM_PROMPT = """You are an Autonomous Voice Coder sandboxed in a workspace subfolder. Return ONLY a raw JSON object matching this schema exactly:
{
  "thought": "Your internal logic analyzing file system state and previous command error codes closely.",
  "speak": "The text the browser should read out loud.",
  "commands": ["pip install flask"],
  "files": [{"path": "index.html", "content": "... full html code ..."}]
}
Rule: Do not wrap your response in markdown code blocks or ticks. Ensure HTML files keep voice recognition hooks."""
