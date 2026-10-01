"""Simple MCP HTTP client to bridge Python to Meta XR Unity Runtime."""

import json
import logging
import urllib.request
from typing import Any

logger = logging.getLogger("FoveAI.MCPClient")

MCP_URL = "http://127.0.0.1:48736/mcpbridge/"
MCP_AUTH = "Bearer f58fe9e6aece4cb1a18d83fe7a442e59"


def call_mcp_tool(method: str, params: dict[str, Any] = None) -> dict[str, Any]:
    """Call an MCP tool synchronously on the Unity AgentBridge.

    Examples:
        call_mcp_tool("SelectObjectInHierarchy", {"gameObjectName": "AvatarContainer"})
        call_mcp_tool("SetDebuggerVisibility", {"visible": True})
    """
    if params is None:
        params = {}

    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}

    req = urllib.request.Request(
        MCP_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": MCP_AUTH},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=5.0) as response:
            data = json.loads(response.read().decode("utf-8"))
            logger.info(f"MCP Success ({method}): {data}")
            return data.get("result", {})
    except Exception as exc:
        logger.error(f"MCP Call failed ({method}): {exc}")
        return {"error": str(exc)}
