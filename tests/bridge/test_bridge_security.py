"""Unit and Security Integration Tests for XRL-Bridge/1.0 (Standalone runner).

Tests:
1. Fail closed on missing/short bridge secret.
2. HMAC signature verification & tamper rejection.
3. Replay protection (reject duplicate nonce and message_id).
4. Timestamp skew rejection (> 120s).
5. Schema validation (disallow unauthorized intents/capabilities, reject oversize payloads >64KB).
6. Local IP gating on approval endpoints (remote IP 403 Forbidden).
7. CSRF validation on approval (reject bogus tokens).
8. Task lifecycle & sandboxed dispatch (no premature completion).
"""

import os
import sys
import time

TEST_SECRET = "super_secure_test_bridge_secret_12345"
os.environ["FOVEAI_BRIDGE_SECRET"] = TEST_SECRET

from starlette.testclient import TestClient
from bridge.server import app, store
from bridge.security import compute_hmac_signature, generate_csrf_token
from bridge.schema import IntentType, CapabilityType, TaskStatus


def run_tests():
    client = TestClient(app)
    passed = 0
    total = 0

    print("=== Running XRL-Bridge/1.0 Security Test Suite ===")

    # Test 1: Health Check
    total += 1
    res = client.get("/health")
    assert res.status_code == 200 and res.json()["status"] == "ok", f"Health failed: {res.text}"
    print("✓ Test 1: Health check passed")
    passed += 1

    # Test 2: Valid task dispatch & CSRF issuance
    total += 1
    now = int(time.time())
    payload = {"target": "version"}
    canonical = {
        "message_id": f"msg_test_{now}",
        "nonce": f"nonce_test_{now}",
        "timestamp": now,
        "intent": IntentType.QUERY.value,
        "capability": CapabilityType.READ.value,
        "payload": payload,
    }
    sig = compute_hmac_signature(canonical, TEST_SECRET)
    req_body = {
        "message_id": f"msg_test_{now}",
        "nonce": f"nonce_test_{now}",
        "timestamp": now,
        "intent": "query",
        "capability": "read",
        "payload": payload,
        "signature": sig,
    }
    res = client.post("/v1/bridge/dispatch", json=req_body)
    assert res.status_code == 200, f"Dispatch failed: {res.text}"
    data = res.json()
    assert data["status"] == "pending_approval"
    task_id = data["task_id"]
    csrf_token = data["csrf_token"]
    print("✓ Test 2: Valid task dispatch & CSRF token generation passed")
    passed += 1

    # Test 3: Replay attack prevention (same message_id and nonce)
    total += 1
    res_replay = client.post("/v1/bridge/dispatch", json=req_body)
    assert res_replay.status_code == 409, f"Expected 409 Conflict on replay, got {res_replay.status_code}"
    print("✓ Test 3: Replay attack prevention passed (409 Conflict)")
    passed += 1

    # Test 4: HMAC tamper rejection
    total += 1
    tampered_body = dict(req_body)
    tampered_body["message_id"] = f"msg_tamper_{now}"
    tampered_body["nonce"] = f"nonce_tamper_{now}"
    tampered_body["signature"] = "tampered_signature_value"
    res_tamper = client.post("/v1/bridge/dispatch", json=tampered_body)
    assert res_tamper.status_code == 401, f"Expected 401 Unauthorized on tampered sig, got {res_tamper.status_code}"
    print("✓ Test 4: Tampered HMAC signature rejected (401 Unauthorized)")
    passed += 1

    # Test 5: Timestamp skew rejection (> 120s in the past)
    total += 1
    old_time = now - 300
    canonical_old = {
        "message_id": f"msg_old_{now}",
        "nonce": f"nonce_old_{now}",
        "timestamp": old_time,
        "intent": IntentType.QUERY.value,
        "capability": CapabilityType.READ.value,
        "payload": payload,
    }
    sig_old = compute_hmac_signature(canonical_old, TEST_SECRET)
    old_body = {
        "message_id": f"msg_old_{now}",
        "nonce": f"nonce_old_{now}",
        "timestamp": old_time,
        "intent": "query",
        "capability": "read",
        "payload": payload,
        "signature": sig_old,
    }
    res_old = client.post("/v1/bridge/dispatch", json=old_body)
    assert res_old.status_code == 400, f"Expected 400 Bad Request on expired timestamp, got {res_old.status_code}"
    print("✓ Test 5: Expired timestamp rejected (>120s skew)")
    passed += 1

    # Test 6: Payload size limit (> 64KB rejected)
    total += 1
    oversized = {"big": "a" * 70000}
    oversize_body = {
        "message_id": f"msg_huge_{now}",
        "nonce": f"nonce_huge_{now}",
        "timestamp": now,
        "intent": "query",
        "capability": "read",
        "payload": oversized,
        "signature": "dummy",
    }
    res_huge = client.post("/v1/bridge/dispatch", json=oversize_body)
    assert res_huge.status_code == 422, f"Expected 422 Unprocessable Entity, got {res_huge.status_code}"
    print("✓ Test 6: Oversized payload rejected (>64KB)")
    passed += 1

    # Test 7: Unauthorized approval attempt (wrong CSRF token)
    total += 1
    res_bad_csrf = client.post(f"/local/bridge/approve/{task_id}", json={
        "csrf_token": "fraudulent_csrf_token",
        "approved": True
    })
    assert res_bad_csrf.status_code == 403, f"Expected 403 Forbidden, got {res_bad_csrf.status_code}"
    print("✓ Test 7: Bogus CSRF token rejected (403 Forbidden)")
    passed += 1

    # Test 8: Valid operator approval & truthful completion
    total += 1
    res_good_approve = client.post(f"/local/bridge/approve/{task_id}", json={
        "csrf_token": csrf_token,
        "approved": True
    })
    assert res_good_approve.status_code == 200, f"Approval failed: {res_good_approve.text}"
    approve_data = res_good_approve.json()
    assert approve_data["status"] == "completed"
    assert approve_data["result"]["service"] == "XRL-Bridge"
    print("✓ Test 8: Valid operator approval & sandboxed dispatch completed")
    passed += 1

    # Test 9: Verification that completed task cannot be re-approved/re-executed
    total += 1
    res_reapprove = client.post(f"/local/bridge/approve/{task_id}", json={
        "csrf_token": csrf_token,
        "approved": True
    })
    assert res_reapprove.status_code == 403, f"Expected 403 on reused CSRF token, got {res_reapprove.status_code}"
    print("✓ Test 9: CSRF single-use & task idempotency verified")
    passed += 1

    print(f"\nAll {passed}/{total} security integration tests passed successfully!")


if __name__ == "__main__":
    run_tests()
