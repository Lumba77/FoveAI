import httpx
import asyncio

async def test_tts():
    url = "http://localhost:8002/tts"
    payload = {"text": "System check. My voice is now active and ready.", "voice": "female"}
    
    print(f"Testing TTS at {url}...")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            print(f"Status Code: {resp.status_code}")
            print(f"Content Type: {resp.headers.get('Content-Type')}")
            if resp.status_code == 200 and len(resp.content) > 1000:
                print(f"Success! Received {len(resp.content)} bytes of audio data.")
            else:
                print(f"Failure. Received only {len(resp.content)} bytes.")
    except Exception as e:
        print(f"TTS Test Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_tts())
