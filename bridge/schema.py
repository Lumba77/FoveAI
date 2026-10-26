"""XRL-Bridge/1.0 — Security Schema & Storage Models.

Strict Pydantic models for contract validation, replay prevention, and storage.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
import time
from pydantic import BaseModel, Field, field_validator


class IntentType(str, Enum):
    QUERY = "query"
    TASK_DISPATCH = "task_dispatch"
    STATUS_CHECK = "status_check"
    MEMORY_RESONANCE = "memory_resonance"


class CapabilityType(str, Enum):
    READ = "read"
    INFERENCE = "inference"
    RESONANCE_RECALL = "resonance_recall"
    NOTIFY = "notify"


class TaskStatus(str, Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class XRLBridgeRequest(BaseModel):
    message_id: str = Field(..., min_length=16, max_length=128)
    nonce: str = Field(..., min_length=16, max_length=128)
    timestamp: int = Field(..., description="Epoch seconds")
    intent: IntentType
    capability: CapabilityType
    payload: Dict[str, Any] = Field(default_factory=dict)
    signature: Optional[str] = Field(None, max_length=256)

    @field_validator("payload")
    @classmethod
    def validate_payload_size(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        import json
        dumped = json.dumps(v)
        if len(dumped) > 65536:  # 64 KB limit
            raise ValueError("Payload size exceeds maximum allowed 64KB limit")
        return v


class ApprovalRequest(BaseModel):
    csrf_token: str = Field(..., min_length=16)
    approved: bool


class BridgeTaskRecord(BaseModel):
    task_id: str
    message_id: str
    intent: IntentType
    capability: CapabilityType
    payload: Dict[str, Any]
    status: TaskStatus = TaskStatus.PENDING_APPROVAL
    created_at: int = Field(default_factory=lambda: int(time.time()))
    expires_at: int
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
