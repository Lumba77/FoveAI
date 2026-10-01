"""Test XRL Protocol workflow: skeletonize -> extract XRL -> expand via XRL"""

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8103"


def post(path, data):
    """POST JSON to endpoint, return parsed response."""
    url = BASE + path
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def get(path):
    """GET endpoint, return parsed response."""
    url = BASE + path
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


# Step 1: Check XRL status before skeletonize
print("=== Step 1: XRL Status (before) ===")
status, data = get("/api/xrl/status")
print(f"  Status: {status}")
print(f"  Response: {json.dumps(data, indent=2)}")

# Step 2: Skeletonize a file
print("\n=== Step 2: Skeletonize soul_core.py ===")
status, data = post(
    "/api/skeletonize", {"filepath": "Backend/Cognition/soul_core.py", "level": 3}
)
print(f"  Status: {status}")
if status == 200:
    skeleton = data.get("skeleton", "")
    print(f"  Skeleton length: {len(skeleton)} chars")
    print(f"  First 500 chars:\n{skeleton[:500]}")
    # Check for XRL URI in skeleton
    if "xrl://" in skeleton:
        # Extract first XRL URI
        import re

        xrl_match = re.search(r"xrl://[^\s\)]+", skeleton)
        if xrl_match:
            print(f"\n  Found XRL URI: {xrl_match.group()}")
else:
    print(f"  Error: {data}")

# Step 3: Check XRL status after skeletonize
print("\n=== Step 3: XRL Status (after) ===")
status, data = get("/api/xrl/status")
print(f"  Status: {status}")
print(f"  Response: {json.dumps(data, indent=2)}")

# Step 4: Test XRL expand (if we have entries)
xrl_entries = data.get("xrl_entries", 0)
if xrl_entries > 0:
    print("\n=== Step 4: XRL Expand (first entry) ===")
    # Get first XRL URI from cache
    status, cache_data = get("/api/xrl/status")
    # We need to know the XRL URI - let's try with a known file:line
    status, expand_data = post(
        "/api/xrl/expand",
        {"uris": ["xrl://foveai/Backend/Cognition/soul_core.py:1:abc123"]},
    )
    print(f"  Status: {status}")
    print(f"  Response: {json.dumps(expand_data, indent=2)[:500]}")
else:
    print("\n=== Step 4: Skipping XRL expand (no entries) ===")

# Step 5: Test XRL resolve
print("\n=== Step 5: XRL Resolve ===")
status, data = post(
    "/api/xrl/resolve", {"uri": "xrl://foveai/Backend/Cognition/soul_core.py:1:abc123"}
)
print(f"  Status: {status}")
print(f"  Response: {json.dumps(data, indent=2)[:500]}")

# Step 6: Test health
print("\n=== Step 6: Health Check ===")
status, data = get("/health")
print(f"  Status: {status}")
print(f"  Response: {json.dumps(data, indent=2)}")

print("\n=== Done ===")
