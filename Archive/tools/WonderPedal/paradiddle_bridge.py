import asyncio
import json

import websockets
from pythonosc import udp_client
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer

# Configuration
QUEST_IP = "192.168.8.106"
PARADIDDLE_OSC_PORT = 9000
LISTEN_IP = "0.0.0.0"
WS_PORT = 9006
OSC_PORT = 9005

# Setup OSC Client to talk to Quest
quest_client = udp_client.SimpleUDPClient(QUEST_IP, PARADIDDLE_OSC_PORT)


class ParadiddleBridge:
    def __init__(self):
        self.dispatcher = Dispatcher()

    def trigger_paradiddle(self, trigger_type):
        """Ricochet the trigger back to the Quest headset natively."""
        # Paradiddle natively accepts OSC. Typical mappings are /kick or /hihat with velocity.
        if trigger_type == "kick":
            quest_client.send_message("/kick", 1.0)
            print(f"[RICOCHET] Sent /kick to Quest ({QUEST_IP}:{PARADIDDLE_OSC_PORT})")
        elif trigger_type == "hihat":
            quest_client.send_message("/hihat", 1.0)
            print(f"[RICOCHET] Sent /hihat to Quest ({QUEST_IP}:{PARADIDDLE_OSC_PORT})")

    async def handle_websocket(self, websocket):
        print("[WebSocket] XR Client Connected!")
        try:
            async for message in websocket:
                data = json.loads(message)
                if data.get("trigger") == "kick":
                    print("\n[Wonder Pedal] Kick Triggered (via WebXR)!")
                    self.trigger_paradiddle("kick")
                elif data.get("trigger") == "hihat":
                    print("\n[Wonder Pedal] Hi-Hat Triggered (via WebXR)!")
                    self.trigger_paradiddle("hihat")
                elif "speech" in data:
                    user_speech = data["speech"]
                    print(f"\n[Jen AR] User said: {user_speech}")
                    # Hit the Foveated Memory proxy on port 8200
                    try:
                        import json
                        import urllib.request

                        url = "http://127.0.0.1:8400/v1/chat/completions"
                        payload = {
                            "model": "jen-core",
                            "messages": [{"role": "user", "content": user_speech}],
                            "max_tokens": 100,
                        }
                        req = urllib.request.Request(
                            url,
                            data=json.dumps(payload).encode("utf-8"),
                            headers={
                                "Content-Type": "application/json",
                                "Authorization": "Bearer jen_ar_session",
                            },
                        )
                        response = urllib.request.urlopen(req, timeout=10)
                        resp_data = json.loads(response.read().decode("utf-8"))
                        reply = resp_data["choices"][0]["message"]["content"]
                        print(f"[Jen AR] Jen replies: {reply}")

                        # Send back to AR
                        await websocket.send(json.dumps({"jen_reply": reply}))
                    except Exception as e:
                        print(f"[Jen AR] Error contacting Foveated Memory: {e}")
                        await websocket.send(
                            json.dumps(
                                {"jen_reply": "I'm having trouble thinking right now."}
                            )
                        )

        except websockets.exceptions.ConnectionClosed:
            print("[WebSocket] XR Client Disconnected.")
        except Exception as e:
            print(f"[WebSocket] Error: {e}")

    async def keyboard_listener(self):
        import msvcrt

        print("\n[DEBUG] PC Keyboard Test Mode Active!")
        print("-> Press 'k' to simulate Kick Drum")
        print("-> Press 'h' to simulate Hi-Hat")

        while True:
            if msvcrt.kbhit():
                key = msvcrt.getch().decode("utf-8").lower()
                if key == "k":
                    print("\n[PC Keyboard] Kick Triggered!")
                    self.trigger_paradiddle("kick")
                elif key == "h":
                    print("\n[PC Keyboard] Hi-Hat Triggered!")
                    self.trigger_paradiddle("hihat")
            await asyncio.sleep(0.01)

    async def run_servers(self):
        print("\n🚀 Starting Wonder Pedal Bridge (UDP Ricochet Mode)...")
        print(f"-> Target Quest IP: {QUEST_IP}:{PARADIDDLE_OSC_PORT}")

        osc_server = AsyncIOOSCUDPServer(
            (LISTEN_IP, OSC_PORT), self.dispatcher, asyncio.get_running_loop()
        )
        transport, protocol = await osc_server.create_serve_endpoint()
        print(f"-> Listening for external OSC on udp://{LISTEN_IP}:{OSC_PORT}")

        ws_server = await websockets.serve(self.handle_websocket, LISTEN_IP, WS_PORT)
        print(f"-> Listening for WebXR WebSockets on ws://{LISTEN_IP}:{WS_PORT}")

        # Start keyboard listener in the background
        asyncio.create_task(self.keyboard_listener())

        print("\nReady for Wonder Pedal triggers! Press Ctrl+C to stop.\n")
        await asyncio.Event().wait()  # Run forever

    def run(self):
        try:
            asyncio.run(self.run_servers())
        except KeyboardInterrupt:
            print("\nShutting down bridge.")


if __name__ == "__main__":
    bridge = ParadiddleBridge()
    bridge.run()
