import pathlib

p = pathlib.Path(r"c:\Users\danie\program\LUMAX\Forge\proxy_server_v2.py")
t = p.read_text(encoding="utf-8")

old1 = '''error_body = await resp.aread()
                    yield json.dumps({
                        "error": f"Upstream returned {resp.status_code}",
                        "detail": error_body.decode("utf-8", errors="replace"),
                    }).encode()
                    return'''

new1 = '''error_body = await resp.aread()
                    error_detail = error_body.decode("utf-8", errors="replace")
                    logger.error(f"Upstream streaming returned {resp.status_code}: {error_detail[:300]}")
                    # Wrap error in SSE format so clients can parse it
                    error_sse = json.dumps({
                        "error": f"Upstream returned {resp.status_code}",
                        "detail": error_detail,
                    })
                    yield f"data: {error_sse}\\n\\n".encode()
                    return'''

old2 = 'yield json.dumps({"error": f"Streaming request failed: {str(e)}"}).encode()'
new2 = 'error_sse = json.dumps({"error": f"Streaming request failed: {str(e)}"})\n            yield f"data: {error_sse}\\n\\n".encode()'

print("old1 found:", old1 in t)
print("old2 found:", old2 in t)

if old1 in t:
    t = t.replace(old1, new1)
if old2 in t:
    t = t.replace(old2, new2)

p.write_text(t, encoding="utf-8")
print("Done.")