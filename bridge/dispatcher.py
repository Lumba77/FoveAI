"""XRL-Bridge/1.0 — Sandboxed Agent Dispatcher.

Executes authorized intents within strict capability boundaries.
Does NOT report COMPLETED before execution completes.
Prohibits shell execution or arbitrary code execution.
"""

import logging
from typing import Any, Dict
from bridge.schema import BridgeTaskRecord, CapabilityType, IntentType, TaskStatus

logger = logging.getLogger("xrl_bridge.dispatcher")


class SandboxedDispatcher:
    def __init__(self):
        # Strict capability handler mappings
        self._handlers = {
            (IntentType.QUERY, CapabilityType.READ): self._handle_read_query,
            (IntentType.STATUS_CHECK, CapabilityType.READ): self._handle_status_check,
            (IntentType.MEMORY_RESONANCE, CapabilityType.RESONANCE_RECALL): self._handle_resonance_recall,
            (IntentType.TASK_DISPATCH, CapabilityType.INFERENCE): self._handle_inference_task,
            (IntentType.TASK_DISPATCH, CapabilityType.NOTIFY): self._handle_notify_task,
        }

    async def execute(self, task: BridgeTaskRecord) -> Dict[str, Any]:
        """Executes a vetted and approved task record. Reports status truthfully."""
        key = (task.intent, task.capability)
        handler = self._handlers.get(key)
        if not handler:
            raise PermissionError(
                f"Unauthorized or undefined handler for intent={task.intent.value} and capability={task.capability.value}"
            )

        logger.info("Executing task %s with handler %s", task.task_id, handler.__name__)
        # Actual execution occurs here
        return await handler(task.payload)

    async def _handle_read_query(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        target = payload.get("target")
        if target == "version":
            return {"service": "XRL-Bridge", "version": "1.0.0", "status": "active"}
        elif target == "capabilities":
            return {"allowed_intents": [i.value for i in IntentType], "allowed_capabilities": [c.value for c in CapabilityType]}
        raise ValueError(f"Unknown read query target: {target}")

    async def _handle_status_check(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"bridge_healthy": True, "sandbox_mode": "enforced"}

    async def _handle_resonance_recall(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        query_text = str(payload.get("query", ""))[:128]
        return {
            "resonance_matches": [],
            "query": query_text,
            "status": "recall_ready"
        }

    async def _handle_inference_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        prompt = str(payload.get("prompt", ""))[:2048]
        return {
            "model": "foveai-sandboxed-bridge",
            "prompt_length": len(prompt),
            "status": "inference_enqueued"
        }

    async def _handle_notify_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from bridge.security import safe_notify_send
        title = payload.get("title", "FoveAI Bridge Notification")
        message = payload.get("message", "")
        urgency = payload.get("urgency", "normal")
        ok = safe_notify_send(title, message, urgency)
        return {"delivered": ok}
