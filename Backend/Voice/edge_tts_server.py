import asyncio
import json
import subprocess

import websockets

PORT = 8403
VOICE = "en-US-AriaNeural"  # Fallback edge-tts voice


async def handle_client(websocket, path):
    try:
        async for message in websocket:
            if isinstance(message, str):
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type")
                if msg_type == "config":
                    await websocket.send(json.dumps({"type": "ready"}))
                    print("[TTS Server] Client connected and configured.")

                elif msg_type == "speak":
                    text = data.get("text", "").strip()
                    if not text:
                        continue

                    print(f"[TTS Server] Generating audio for: {text}")
                    await websocket.send(
                        json.dumps({"type": "start", "sample_rate": 24000})
                    )

                    # 1. Generate audio using edge-tts
                    edge_cmd = ["edge-tts", "--voice", VOICE, "--text", text]
                    edge_proc = subprocess.Popen(
                        edge_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
                    )

                    # 2. Pipe into ffmpeg to convert to 24000Hz 16-bit PCM little-endian
                    ffmpeg_cmd = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        "pipe:0",
                        "-f",
                        "s16le",
                        "-acodec",
                        "pcm_s16le",
                        "-ac",
                        "1",
                        "-ar",
                        "24000",
                        "pipe:1",
                    ]
                    ffmpeg_proc = subprocess.Popen(
                        ffmpeg_cmd,
                        stdin=edge_proc.stdout,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )

                    # Ensure edge_proc stdout is closed so ffmpeg receives EOF when edge-tts finishes
                    if edge_proc.stdout:
                        edge_proc.stdout.close()

                    # 3. Read chunks from ffmpeg and stream to websocket
                    duration_ms = 0
                    while True:
                        chunk = ffmpeg_proc.stdout.read(4096)
                        if not chunk:
                            break
                        await websocket.send(chunk)
                        # 4096 bytes / 2 bytes per sample = 2048 samples
                        # 2048 samples / 24000 Hz = 0.0853 seconds = ~85 ms
                        duration_ms += (len(chunk) // 2) * 1000 // 24000

                    ffmpeg_proc.wait()
                    print(f"[TTS Server] Finished streaming {duration_ms}ms of audio.")
                    await websocket.send(
                        json.dumps({"type": "end", "duration_ms": duration_ms})
                    )

    except websockets.exceptions.ConnectionClosed:
        print("[TTS Server] Client disconnected.")


async def main():
    print(f"Starting Fallback Edge-TTS Server on port {PORT}...")
    async with websockets.serve(handle_client, "0.0.0.0", PORT):
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())
