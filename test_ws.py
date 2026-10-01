import asyncio
import json

import websockets


async def test():
    async with websockets.connect("ws://127.0.0.1:8001/ws") as ws:
        print("Connected to ws://127.0.0.1:8001/ws")
        await ws.send(
            json.dumps({"event": "chat", "payload": {"text": "Say hello in one word"}})
        )
        print("Sent chat message, waiting for response...")
        r = await asyncio.wait_for(ws.recv(), timeout=60)
        print("Response:", r)


asyncio.run(test())
