#!/usr/bin/env python3
"""
Lumax Soul Coder Chat Service
============================
Interactive coding assistant with project context.
Runs inside Docker with access to entire FoveAI-lite project.
Streams responses in real-time via HTTP.

Web UI:  http://localhost:8006
API:     http://localhost:8006/api/chat
"""

import os
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, AsyncGenerator
import httpx

from fastapi import FastAPI, WebSocket, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# === Logging ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("soul-coder-chat")

# === Configuration ===
FoveAI_LOCAL_BASE_URL = os.getenv("FoveAI_LOCAL_BASE_URL", "http://localhost:8888/v1")
FoveAI_REPO_ROOT = os.getenv("FoveAI_REPO_ROOT", "/app")
DEFAULT_MODEL = os.getenv("ACTIVE_MODEL", "TQL-Coder-Qwen3.5-9B-thinking.IQ4_XS.gguf")
CHAT_HISTORY_FILE = "/app/backend/Cognition/soul_coder_chat_history.json"

# === FastAPI App ===
app = FastAPI(
    title="Soul Coder Chat",
    description="Interactive AI coding assistant with project context",
    version="1.0.0"
)

# CORS for web access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Data Models ===
class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = None
    model: Optional[str] = None
    stream: bool = True

class ChatResponse(BaseModel):
    role: str
    content: str
    model: str
    timestamp: str

# === Project Context ===
class ProjectContext:
    """Analyze and cache project structure for context"""
    
    def __init__(self, repo_root: str = FoveAI_REPO_ROOT):
        self.repo_root = Path(repo_root)
        self.cache = None
        self.last_update = None
    
    def get_context(self) -> str:
        """Build project context string"""
        context_parts = []
        
        # Project structure
        context_parts.append("## FoveAI-lite Project Structure\n")
        
        # Key directories
        for dir_name in ["Mind", "Body", "Build", "Scripts"]:
            dir_path = self.repo_root / dir_name
            if dir_path.exists():
                context_parts.append(f"\n### {dir_name}/\n")
                context_parts.append(self._list_dir_contents(dir_path, max_depth=2))
        
        # Key config files
        context_parts.append("\n### Configuration Files\n")
        for filename in ["docker-compose.yml", ".env.example", "FoveAI.md"]:
            file_path = self.repo_root / filename
            if file_path.exists():
                context_parts.append(f"- {filename}")
        
        # Recent changes
        context_parts.append("\n### Active Development\n")
        context_parts.append(f"- Soul Coder Service (coding-agent profile)\n")
        context_parts.append(f"- Unsloth/LM Studio Models: 9B Qwen Coder (prod) / 2B variant (test)\n")
        context_parts.append(f"- Docker Compose Integration\n")
        
        return "".join(context_parts)
    
    def _list_dir_contents(self, dir_path: Path, max_depth: int = 1, current_depth: int = 0) -> str:
        """List directory contents"""
        if current_depth >= max_depth:
            return ""
        
        items = []
        try:
            for item in sorted(dir_path.iterdir())[:10]:  # Limit to 10 items
                if item.name.startswith("."):
                    continue
                if item.is_dir():
                    items.append(f"{'  ' * (current_depth + 1)}- {item.name}/")
                else:
                    items.append(f"{'  ' * (current_depth + 1)}- {item.name}")
        except PermissionError:
            pass
        
        return "\n".join(items)

project_context = ProjectContext()

# === Chat History ===
class ChatHistory:
    def __init__(self, history_file: str = CHAT_HISTORY_FILE):
        self.history_file = Path(history_file)
        self.messages = []
        self.load()
    
    def load(self):
        """Load history from file"""
        if self.history_file.exists():
            try:
                data = json.loads(self.history_file.read_text())
                self.messages = data.get("messages", [])
            except Exception as e:
                logger.warning(f"Could not load chat history: {e}")
    
    def add_message(self, role: str, content: str):
        """Add message to history"""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        self.save()
    
    def save(self):
        """Save history to file"""
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            self.history_file.write_text(json.dumps({
                "messages": self.messages[-50:],  # Keep last 50 messages
                "updated": datetime.now().isoformat()
            }, indent=2))
        except Exception as e:
            logger.warning(f"Could not save chat history: {e}")
    
    def get_context_messages(self, limit: int = 10) -> list:
        """Get recent messages for context"""
        return self.messages[-limit:]

chat_history = ChatHistory()

# === System Prompt ===
def get_system_prompt() -> str:
    """Build comprehensive system prompt with project context"""
    return f"""You are the Soul Coder, an AI coding assistant with deep knowledge of the FoveAI-lite project.

You run INSIDE the Docker container of the FoveAI-lite project, giving you an insider perspective on:
- Project architecture and structure
- Running services and their interactions
- Development patterns and conventions used
- Recent changes and active development areas

## Your Expertise
- Backend AI development (backend/ components: Cognition, Creativity, Memory)
- Python services and servers
- Docker Compose orchestration
- GGUF model management and optimization
- GDScript for VR/XR frontends
- TTS/STT integration and audio processing

## Your Context
Repository: {FoveAI_REPO_ROOT}
Active Model: {DEFAULT_MODEL}
Local LLM Host: {FoveAI_LOCAL_BASE_URL}

Project Context:
{project_context.get_context()}

## Your Role
- Assist with code generation and debugging
- Suggest improvements based on project patterns
- Help with Docker and deployment
- Explain architecture and design decisions
- Provide examples from similar code in the project
- Track context across multiple conversations

## Guidelines
- Reference actual files when suggesting changes
- Consider the full system impact of changes
- Suggest testing strategies for the local environment
- Be aware of GPU/VRAM constraints
- Provide runnable code examples
- Ask clarifying questions when needed

Remember: You have insider knowledge of this specific project. Use it!"""

# === Health Check ===
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{FoveAI_LOCAL_BASE_URL}/models", timeout=5.0)
            ollama_ok = resp.status_code == 200
    except Exception:
        ollama_ok = False
    
    return {
        "service": "soul-coder-chat",
        "status": "healthy" if ollama_ok else "degraded",
        "ollama": "ok" if ollama_ok else "not-responding",
        "timestamp": datetime.now().isoformat()
    }

# === Web UI ===
@app.get("/", response_class=HTMLResponse)
async def web_ui():
    """Web chat interface"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Soul Coder - FoveAI Project Assistant</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #1e1e2e 0%, #2d2d44 100%);
                color: #e0e0e0;
                height: 100vh;
                display: flex;
                flex-direction: column;
            }
            
            header {
                background: rgba(20, 20, 35, 0.9);
                border-bottom: 1px solid #3d3d5f;
                padding: 1.5rem;
                backdrop-filter: blur(10px);
            }
            
            h1 {
                font-size: 1.5rem;
                font-weight: 600;
                background: linear-gradient(135deg, #61dafb, #7c3aed);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            
            .subtitle {
                font-size: 0.9rem;
                color: #999;
                margin-top: 0.5rem;
            }
            
            .container {
                display: flex;
                flex-direction: column;
                flex: 1;
                overflow: hidden;
            }
            
            #messages {
                flex: 1;
                overflow-y: auto;
                padding: 2rem;
                display: flex;
                flex-direction: column;
                gap: 1.5rem;
            }
            
            .message {
                display: flex;
                gap: 1rem;
                animation: slideIn 0.3s ease-out;
            }
            
            @keyframes slideIn {
                from {
                    opacity: 0;
                    transform: translateY(10px);
                }
                to {
                    opacity: 1;
                    transform: translateY(0);
                }
            }
            
            .message.user {
                justify-content: flex-end;
            }
            
            .message.assistant {
                justify-content: flex-start;
            }
            
            .message-content {
                max-width: 70%;
                padding: 1rem 1.25rem;
                border-radius: 0.75rem;
                word-wrap: break-word;
                white-space: pre-wrap;
                font-size: 0.95rem;
                line-height: 1.5;
            }
            
            .message.user .message-content {
                background: linear-gradient(135deg, #7c3aed, #6d28d9);
                color: white;
                border-bottom-right-radius: 0.25rem;
            }
            
            .message.assistant .message-content {
                background: #2d2d44;
                color: #e0e0e0;
                border-left: 2px solid #61dafb;
                border-bottom-left-radius: 0.25rem;
            }
            
            .input-area {
                background: rgba(20, 20, 35, 0.9);
                border-top: 1px solid #3d3d5f;
                padding: 1.5rem;
                backdrop-filter: blur(10px);
            }
            
            .input-group {
                display: flex;
                gap: 1rem;
            }
            
            input#messageInput {
                flex: 1;
                background: #2d2d44;
                border: 1px solid #3d3d5f;
                color: #e0e0e0;
                padding: 0.75rem 1rem;
                border-radius: 0.5rem;
                font-size: 0.95rem;
                transition: all 0.3s ease;
            }
            
            input#messageInput:focus {
                outline: none;
                border-color: #7c3aed;
                box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.1);
            }
            
            button {
                background: linear-gradient(135deg, #7c3aed, #6d28d9);
                color: white;
                border: none;
                padding: 0.75rem 1.5rem;
                border-radius: 0.5rem;
                cursor: pointer;
                font-weight: 600;
                transition: all 0.3s ease;
                font-size: 0.95rem;
            }
            
            button:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(124, 58, 237, 0.4);
            }
            
            button:active {
                transform: translateY(0);
            }
            
            .loading {
                display: inline-block;
                width: 8px;
                height: 8px;
                background: #61dafb;
                border-radius: 50%;
                animation: pulse 1.5s ease-in-out infinite;
            }
            
            @keyframes pulse {
                0%, 100% { opacity: 0.6; transform: scale(1); }
                50% { opacity: 1; transform: scale(1.2); }
            }
            
            .timestamp {
                font-size: 0.8rem;
                color: #666;
                margin-top: 0.25rem;
            }
            
            code {
                background: #1a1a2e;
                padding: 0.2em 0.4em;
                border-radius: 0.3em;
                font-family: 'Courier New', monospace;
                color: #61dafb;
            }
            
            pre {
                background: #1a1a2e;
                padding: 1rem;
                border-radius: 0.5rem;
                overflow-x: auto;
                margin: 0.5rem 0;
                border-left: 3px solid #61dafb;
            }
        </style>
    </head>
    <body>
        <header>
            <h1>🧠 Soul Coder</h1>
            <div class="subtitle">FoveAI-lite AI Development Assistant</div>
        </header>
        
        <div class="container">
            <div id="messages"></div>
            
            <div class="input-area">
                <div class="input-group">
                    <input 
                        type="text" 
                        id="messageInput" 
                        placeholder="Ask Soul Coder about code, architecture, or FoveAI-lite..."
                        autocomplete="off"
                    >
                    <button id="sendBtn">Send</button>
                </div>
            </div>
        </div>
        
        <script>
            const messagesDiv = document.getElementById("messages");
            const input = document.getElementById("messageInput");
            const sendBtn = document.getElementById("sendBtn");
            
            // Load initial greeting
            window.addEventListener("load", async () => {
                addMessage("assistant", "🧠 Soul Coder initialized. I'm running inside the FoveAI-lite Docker container with full project context.\\n\\nHow can I help with your development?");
            });
            
            function addMessage(role, content) {
                const msgDiv = document.createElement("div");
                msgDiv.className = `message ${role}`;
                
                const contentDiv = document.createElement("div");
                contentDiv.className = "message-content";
                contentDiv.textContent = content;
                
                msgDiv.appendChild(contentDiv);
                
                const timeDiv = document.createElement("div");
                timeDiv.className = "timestamp";
                timeDiv.textContent = new Date().toLocaleTimeString();
                msgDiv.appendChild(timeDiv);
                
                messagesDiv.appendChild(msgDiv);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }
            
            async function sendMessage() {
                const message = input.value.trim();
                if (!message) return;
                
                input.value = "";
                addMessage("user", message);
                
                // Show loading indicator
                const loadingDiv = document.createElement("div");
                loadingDiv.className = "message assistant";
                const loadingContent = document.createElement("div");
                loadingContent.className = "message-content";
                loadingContent.innerHTML = '<span class="loading"></span> Soul Coder thinking...';
                loadingDiv.appendChild(loadingContent);
                messagesDiv.appendChild(loadingDiv);
                
                try {
                    const response = await fetch("/api/chat", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ message, stream: true })
                    });
                    
                    if (!response.ok) throw new Error("API error");
                    
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let fullText = "";
                    let firstChunk = true;
                    
                    while (true) {
                        const { done, value } = await reader.read();
                        if (done) break;
                        
                        const text = decoder.decode(value);
                        fullText += text;
                        
                        if (firstChunk) {
                            loadingDiv.remove();
                            addMessage("assistant", fullText);
                            firstChunk = false;
                        } else {
                            const lastMsg = messagesDiv.lastChild;
                            if (lastMsg) {
                                lastMsg.querySelector(".message-content").textContent = fullText;
                                messagesDiv.scrollTop = messagesDiv.scrollHeight;
                            }
                        }
                    }
                } catch (error) {
                    loadingDiv.remove();
                    addMessage("assistant", `Error: ${error.message}`);
                }
            }
            
            sendBtn.addEventListener("click", sendMessage);
            input.addEventListener("keypress", (e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
        </script>
    </body>
    </html>
    """

# === Chat API ===
async def stream_chat_response(message: str, model: str) -> AsyncGenerator[str, None]:
    """Stream chat response from Ollama"""
    
    # Build context from recent messages
    context_messages = chat_history.get_context_messages(limit=5)
    conversation_context = ""
    if context_messages:
        conversation_context = "Recent conversation:\n"
        for msg in context_messages:
            role = "User" if msg["role"] == "user" else "Assistant"
            conversation_context += f"{role}: {msg['content'][:200]}\n"
    
    # Full prompt
    full_prompt = f"""{get_system_prompt()}

{conversation_context}

User: {message}

Soul Coder:"""
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": model,
                    "prompt": full_prompt,
                    "stream": True,
                    "temperature": 0.7,
                    "top_p": 0.9,
                },
            ) as response:
                if response.status_code != 200:
                    yield f"Error: Ollama returned {response.status_code}"
                    return
                
                async for line in response.aiter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            if "response" in chunk:
                                yield chunk["response"]
                        except json.JSONDecodeError:
                            pass
    except Exception as e:
        logger.error(f"Stream error: {e}")
        yield f"Error communicating with Ollama: {str(e)}"

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Chat endpoint with streaming response"""
    
    model = request.model or DEFAULT_MODEL
    
    # Add user message to history
    chat_history.add_message("user", request.message)
    
    async def generate():
        """Generate streaming response"""
        assistant_response = ""
        
        async for chunk in stream_chat_response(request.message, model):
            assistant_response += chunk
            if request.stream:
                yield chunk
        
        # Save assistant response to history
        if assistant_response:
            chat_history.add_message("assistant", assistant_response)
    
    return StreamingResponse(generate(), media_type="text/plain")

# === Chat History API ===
@app.get("/api/history")
async def get_history():
    """Get chat history"""
    return {
        "messages": chat_history.messages,
        "count": len(chat_history.messages)
    }

@app.post("/api/history/clear")
async def clear_history():
    """Clear chat history"""
    chat_history.messages = []
    chat_history.save()
    return {"status": "cleared"}

# === Startup ===
@app.on_event("startup")
async def startup():
    """Initialize on startup"""
    logger.info("Soul Coder Chat Service starting...")
    logger.info(f"Ollama Host: {OLLAMA_HOST}")
    logger.info(f"Project Root: {FoveAI_REPO_ROOT}")
    logger.info(f"Default Model: {DEFAULT_MODEL}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8006,
        log_level=LOG_LEVEL.lower()
    )
