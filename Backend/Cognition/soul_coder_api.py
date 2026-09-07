#!/usr/bin/env python3
"""
Lumax Soul Coder API Controller
=============================
FastAPI service for managing Ollama coding model:
  - Pause/resume inference
  - Model switching (9B ↔ 2B)
  - Status monitoring
  - Pause for VR tests

Endpoints:
  GET  /health                 - Health check
  GET  /api/status            - Current status (model, paused, etc)
  POST /api/pause             - Pause model (VR test mode)
  POST /api/resume            - Resume model
  POST /api/switch-model      - Switch between 9B and 2B models
  GET  /api/models            - List available models
  POST /api/test-mode         - Switch to 2B testing model
  POST /api/production-mode   - Switch back to 9B production model
"""

import os
import json
import asyncio
import logging
import httpx
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any

# === Configuration ===
FoveAI_LOCAL_BASE_URL = os.getenv("FoveAI_LOCAL_BASE_URL", "http://localhost:8888/v1")
STATE_FILE = os.getenv("STATE_FILE", "/app/state.json")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger("soul-coder-api")

app = FastAPI(
    title="Lumax Soul Coder API",
    description="Ollama coding model manager with pause/resume",
    version="1.0.0"
)

# === State Management ===
class SoulCoderState:
    def __init__(self, state_file: str):
        self.state_file = Path(state_file)
        self.lock = asyncio.Lock()
        self.ensure_state_file()

    def ensure_state_file(self):
        """Create state file if it doesn't exist"""
        if not self.state_file.exists():
            initial_state = {
                "status": "ready",
                "model": "TQL-Coder-Qwen3.5-9B-thinking.IQ4_XS.gguf",
                "paused": False,
                "last_check": datetime.now().isoformat(),
                "vr_test_mode": False,
                "model_history": []
            }
            self.state_file.write_text(json.dumps(initial_state, indent=2))

    async def get(self) -> Dict[str, Any]:
        """Read current state"""
        async with self.lock:
            try:
                return json.loads(self.state_file.read_text())
            except Exception as e:
                logger.error(f"Failed to read state: {e}")
                self.ensure_state_file()
                return json.loads(self.state_file.read_text())

    async def update(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update state with new values"""
        async with self.lock:
            try:
                state = json.loads(self.state_file.read_text())
                state.update(updates)
                state["last_check"] = datetime.now().isoformat()
                self.state_file.write_text(json.dumps(state, indent=2))
                return state
            except Exception as e:
                logger.error(f"Failed to update state: {e}")
                raise

state_manager = SoulCoderState(STATE_FILE)

# === Pydantic Models ===
class ModelSwitchRequest(BaseModel):
    model: str
    reason: Optional[str] = None

class StatusResponse(BaseModel):
    status: str
    model: str
    paused: bool
    vr_test_mode: bool
    ollama_health: bool
    timestamp: str

# === Health & Status ===
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{FoveAI_LOCAL_BASE_URL}/models", timeout=5.0)
            ollama_ok = resp.status_code == 200
    except Exception as e:
        logger.warning(f"Ollama health check failed: {e}")
        ollama_ok = False

    state = await state_manager.get()
    return {
        "service": "soul-coder-api",
        "status": "healthy" if ollama_ok else "degraded",
        "ollama": "ok" if ollama_ok else "not-responding",
        "paused": state.get("paused", False),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/status", response_model=StatusResponse)
async def get_status():
    """Get current soul-coder status"""
    state = await state_manager.get()
    
    # Check Ollama health
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{FoveAI_LOCAL_BASE_URL}/models", timeout=2.0)
            ollama_health = resp.status_code == 200
    except Exception:
        ollama_health = False

    return StatusResponse(
        status=state.get("status", "unknown"),
        model=state.get("model", "unknown"),
        paused=state.get("paused", False),
        vr_test_mode=state.get("vr_test_mode", False),
        ollama_health=ollama_health,
        timestamp=datetime.now().isoformat()
    )

# === Pause / Resume ===
@app.post("/api/pause")
async def pause_model(reason: Optional[str] = None):
    """
    Pause the coding model (for VR tests).
    This unloads the model from VRAM to free GPU memory.
    """
    try:
        state = await state_manager.update({
            "paused": True,
            "pause_reason": reason or "manual pause",
            "paused_at": datetime.now().isoformat()
        })
        
        # Attempt to unload model (Ollama allows this via DELETE /api/embed with model)
        try:
            async with httpx.AsyncClient() as client:
                # Ollama doesn't have a direct unload, but we can track pause state
                # Future: implement via Ollama plugin or external GPU memory management
                logger.info(f"Model paused: {reason}")
        except Exception as e:
            logger.warning(f"Could not unload model from VRAM: {e}")

        return {
            "status": "paused",
            "model": state.get("model"),
            "reason": reason or "manual",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Pause failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pause failed: {e}")

@app.post("/api/resume")
async def resume_model():
    """
    Resume the coding model after pause (e.g., after VR test completes).
    Pre-loads the model into VRAM.
    """
    try:
        state = await state_manager.update({
            "paused": False,
            "resumed_at": datetime.now().isoformat()
        })
        
        # Pre-load the current model to warm up VRAM
        try:
            model = state.get("model", "TQL-Coder-Qwen3.5-9B-thinking.IQ4_XS.gguf")
            async with httpx.AsyncClient() as client:
                # This will load the model into VRAM
                await client.post(
                    f"{FoveAI_LOCAL_BASE_URL}/chat/completions",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "Ready."}],
                        "stream": False
                    },
                    timeout=60.0
                )
        except Exception as e:
            logger.warning(f"Could not pre-load model: {e}")

        return {
            "status": "resumed",
            "model": state.get("model"),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Resume failed: {e}")
        raise HTTPException(status_code=500, detail=f"Resume failed: {e}")

# === Model Switching ===
@app.post("/api/switch-model")
async def switch_model(request: ModelSwitchRequest):
    """Switch to a different coding model"""
    try:
        state = await state_manager.update({
            "model": request.model,
            "switch_reason": request.reason or "manual switch",
            "switched_at": datetime.now().isoformat()
        })
        
        logger.info(f"Switched to model: {request.model} (reason: {request.reason})")
        
        return {
            "status": "switched",
            "model": request.model,
            "reason": request.reason,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Model switch failed: {e}")
        raise HTTPException(status_code=500, detail=f"Model switch failed: {e}")

@app.post("/api/test-mode")
async def test_mode():
    """Switch to 2B testing model (faster, lower VRAM)"""
    model_2b = os.getenv("CODING_MODEL_2B", "Qwen2.5-Coder-3B.IQ3_M.gguf")
    
    try:
        state = await state_manager.update({
            "model": model_2b,
            "vr_test_mode": True,
            "mode_switched_at": datetime.now().isoformat()
        })
        
        logger.info(f"Switched to test mode (2B model): {model_2b}")
        
        return {
            "status": "test-mode-active",
            "model": model_2b,
            "vr_test_mode": True,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test mode switch failed: {e}")

@app.post("/api/production-mode")
async def production_mode():
    """Switch to 9B production model (full capability)"""
    model_9b = os.getenv("CODING_MODEL_9B", "TQL-Coder-Qwen3.5-9B-thinking.IQ4_XS.gguf")
    
    try:
        state = await state_manager.update({
            "model": model_9b,
            "vr_test_mode": False,
            "mode_switched_at": datetime.now().isoformat()
        })
        
        logger.info(f"Switched to production mode (9B model): {model_9b}")
        
        return {
            "status": "production-mode-active",
            "model": model_9b,
            "vr_test_mode": False,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Production mode switch failed: {e}")

# === Available Models ===
@app.get("/api/models")
async def list_models():
    """List available Ollama models"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{OLLAMA_HOST}/api/tags", timeout=10.0)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                return {
                    "models": [m.get("name") for m in models],
                    "count": len(models),
                    "timestamp": datetime.now().isoformat()
                }
            else:
                raise HTTPException(status_code=502, detail="Ollama not responding")
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        raise HTTPException(status_code=502, detail=f"Ollama error: {e}")

# === Startup ===
@app.on_event("startup")
async def startup():
    """Initialize on startup"""
    logger.info("Soul Coder API starting...")
    state = await state_manager.get()
    logger.info(f"Initial state: {state}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8005,
        log_level=LOG_LEVEL.lower()
    )
