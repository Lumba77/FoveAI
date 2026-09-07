import httpx
import asyncio
import base64

async def test_stt_backend():
    url = "http://localhost:8001/stt"
    # Sending a tiny dummy WAV header (44 bytes of 0s)
    dummy_wav = b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x44\xac\x00\x00\x01\x00\x08\x00data\x00\x00\x00\x00'
    b64 = base64.b64encode(dummy_wav).decode("utf-8")
    
    print(f"Testing STT Backend at {url}...")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json={"audio_base64": b64})
            print(f"Status Code: {resp.status_code}")
            print(f"Response: {resp.json()}")
    except Exception as e:
        print(f"STT Backend Test Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_stt_backend())
