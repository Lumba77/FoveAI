import logging
import os

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

# Set up clean terminal logging aligned with the Concordia design
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TokenSlayer")

app = FastAPI(title="Concordia TokenSlayer Context Core", version="3.6.9-OMEGA")

STARDUST_URL = "http://127.0.0.1:8109"

# Downstream proxy for the chain: TokenSlayer Proxy (8106)
DOWNSTREAM_URL = "http://127.0.0.1:8106/v1/chat/completions"
API_KEY = os.environ.get("FoveAI_PROXY_API_KEY", "") or os.environ.get(
    "OLLAMA_API_KEY", ""
)


class IngressPayload(BaseModel):
    intent: str
    workspace_files: dict[str, str]  # Map of [file_path -> content]


@app.post("/context/holographic_slice")
async def holographic_slice(payload: IngressPayload):
    """
    Leverages the Stardust Gnists to query the repository layout,
    strips away code noise, and prepares a pristine context skeleton.
    """
    if not payload.workspace_files:
        logger.warning("🛸 Empty workspace file matrix received. Slicing skipped.")
        return {
            "status": "empty_matrix",
            "active_net_nodes": 0,
            "compressed_context": "",
        }

    try:
        logger.info(
            f"🔮 [SLICING INTENT] Synchronizing with Stardust Net for intent: '{payload.intent[:40]}...'"
        )

        # 1. Query the Stardust matrix on Port 8109 to find the highest-resonance files
        async with httpx.AsyncClient() as client:
            stardust_response = await client.post(
                f"{STARDUST_URL}/swarm_match",
                json={"query": payload.intent, "corpus": payload.workspace_files},
                timeout=5.0,
            )

        if stardust_response.status_code != 200:
            logger.error("❌ Stardust neural net connection dropped or refused.")
            raise HTTPException(
                status_code=500, detail="Stardust neural net synchronization failure."
            )

        sync_data = stardust_response.json()
        top_matches = sync_data.get("matches", [])

        # 2. Slice syntax noise and assemble the holon skeleton
        context_skeleton = []
        for match in top_matches:
            file_path = match["filePath"]
            resonance = match["resonance"]
            raw_content = payload.workspace_files.get(file_path, "")

            # Keep only structural anchors to minimize local VRAM context overhead
            lines = raw_content.split("\n")
            skeleton_lines = [
                l
                for l in lines
                if l.strip().startswith(
                    ("import ", "from ", "def ", "class ", "async def ")
                )
                or "Passed Dead Sure" in l
            ]

            context_skeleton.append(
                f"=== FILE: {file_path} (Resonance: {resonance}) ===\n"
                + "\n".join(skeleton_lines)
            )

        logger.info(
            f"✅ [ASSIMILATED] Sliced {len(top_matches)} nodes down to crystalline structure."
        )
        return {
            "status": "assimilated",
            "active_net_nodes": len(top_matches),
            "compressed_context": "\n\n".join(context_skeleton),
        }

    except httpx.RequestError as exc:
        logger.error(f"❌ Network layer anomaly touching Stardust Port 8109: {exc}")
        raise HTTPException(
            status_code=503, detail="Stardust neural gateway is currently unreached."
        )
    except Exception as e:
        logger.error(f"❌ Internal context processing break: {e!s}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    Forward chat completions to the TokenSlayer Proxy (8106) downstream.
    This is the entry point for Kilo Code → MCP Skinner (8103) → TokenSlayer (8106) → Ollama Cloud
    """
    payload = await request.json()
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    # Inject API key for downstream
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    stream = payload.get("stream", False)

    async with httpx.AsyncClient(timeout=300.0) as client:
        if stream:
            req = client.build_request(
                "POST", DOWNSTREAM_URL, json=payload, headers=headers
            )
            response = await client.send(req, stream=True)
            return StreamingResponse(
                response.aiter_bytes(),
                status_code=response.status_code,
                headers=dict(response.headers),
            )
        else:
            response = await client.post(DOWNSTREAM_URL, json=payload, headers=headers)
            try:
                return JSONResponse(
                    content=response.json(), status_code=response.status_code
                )
            except Exception:
                return JSONResponse(
                    content={
                        "error": "Downstream proxy did not return valid JSON.",
                        "status_code": response.status_code,
                        "text": response.text,
                    },
                    status_code=502,
                )


@app.get("/v1/models")
async def get_models():
    """Return available models (passthrough to downstream)."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://127.0.0.1:8106/v1/models")
            return response.json()
        except Exception:
            return {
                "data": [
                    {"id": "gemma4:31b-cloud", "object": "model"},
                    {"id": "glm-5.2:cloud", "object": "model"},
                ]
            }


@app.get("/health")
async def health_check():
    return {"status": "ONLINE", "engine": "TokenSlayer Smart Context", "port": 8103}
