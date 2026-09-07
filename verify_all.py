"""FoveAI Consolidation - Final End-to-End Verification"""
import urllib.request
import json

print("=== Final End-to-End Verification ===\n")

# 1. Multigate frontend (5177)
print("[1] Multigate Frontend (5177):")
try:
    with urllib.request.urlopen("http://127.0.0.1:5177/", timeout=5) as r:
        html = r.read().decode("utf-8")
        print(f"  Status: {r.status} OK  |  Size: {len(html)} bytes")
except Exception as e:
    print(f"  ERROR: {e}")

# 2. XRLF Proxy (8400) - health
print("\n[2] XRLF Proxy (8400):")
try:
    with urllib.request.urlopen("http://127.0.0.1:8400/health", timeout=5) as r:
        h = json.loads(r.read().decode())
        print(f"  Status: {h.get('status')}  |  Mode: {h.get('mode')}  |  Session: {h.get('session')}")
except Exception as e:
    print(f"  ERROR: {e}")

# 3. Dashboard (8401) - settings page
print("\n[3] Dashboard (8401/settings.html):")
try:
    with urllib.request.urlopen("http://127.0.0.1:8401/settings.html", timeout=5) as r:
        html = r.read().decode("utf-8")
        checks = {
            "has :8400": ":8400" in html,
            "has :8401": ":8401" in html,
            "has summarizer": "qwen3-0.6b-summarizer" in html,
            "no stale :8200": ":8200" not in html,
            "no stale :8300": ":8300" not in html,
        }
        print(f"  Status: {r.status} OK  |  Size: {len(html)} bytes")
        for k, v in checks.items():
            print(f"  {k}: {'PASS' if v else 'FAIL'}")
        all_ok = all(checks.values())
        print(f"  Overall: {'ALL PASS' if all_ok else 'ISSUES FOUND'}")
except Exception as e:
    print(f"  ERROR: {e}")

# 4. LM Studio (7272)
print("\n[4] LM Studio (7272):")
try:
    with urllib.request.urlopen("http://127.0.0.1:7272/v1/models", timeout=5) as r:
        m = json.loads(r.read().decode())
        print(f"  Models: {len(m.get('data', []))} available")
except Exception as e:
    print(f"  ERROR: {e}")

# 5. Proxy API - compressor setting
print("\n[5] API Setting (compressor):")
try:
    data = json.dumps({"key": "XRLF_COMPRESSOR_MODEL", "val": "qwen3-0.6b-summarizer"}).encode()
    req = urllib.request.Request("http://127.0.0.1:8400/api/setting", data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        s = json.loads(r.read().decode())
        print(f"  Response: {s}")
except Exception as e:
    print(f"  ERROR: {e}")

# 6. Monitor dashboard (index.html)
print("\n[6] Monitor Dashboard (8401/):")
try:
    with urllib.request.urlopen("http://127.0.0.1:8401/", timeout=5) as r:
        html = r.read().decode("utf-8")
        checks = {
            "no stale :8300": ":8300" not in html,
            "no stale :8301": ":8301" not in html,
            "has :8400": ":8400" in html,
        }
        print(f"  Status: {r.status} OK  |  Size: {len(html)} bytes")
        for k, v in checks.items():
            print(f"  {k}: {'PASS' if v else 'FAIL'}")
except Exception as e:
    print(f"  ERROR: {e}")

# 7. Graphtest page (8401)
print("\n[7] Graphtest Dashboard (8401/graphtest.html):")
try:
    with urllib.request.urlopen("http://127.0.0.1:8401/graphtest.html", timeout=5) as r:
        html = r.read().decode("utf-8")
        checks = {
            "no stale :8200": ":8200" not in html,
            "has :8400": ":8400" in html,
        }
        print(f"  Status: {r.status} OK  |  Size: {len(html)} bytes")
        for k, v in checks.items():
            print(f"  {k}: {'PASS' if v else 'FAIL'}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== Verification Complete ===")