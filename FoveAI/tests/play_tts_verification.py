import asyncio
import os
import subprocess

import httpx


async def play_tts_on_pc():
    url = "http://localhost:8002/tts"
    payload = {
        "text": "Verification complete. My voice is active and transmitting on the PC speakers.",
        "voice": "female",
    }
    file_path = "verification_tts.wav"

    print("Requesting TTS audio...")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                with open(file_path, "wb") as f:
                    f.write(resp.content)
                print(f"Audio saved to {file_path}. Playing now...")

                # Use PowerShell to play the WAV on the host PC
                ps_command = f"(New-Object Media.SoundPlayer '{os.path.abspath(file_path)}').PlaySync()"
                subprocess.run(["powershell.exe", "-Command", ps_command])
                print("Playback finished.")
            else:
                print(f"Failed to get audio. Status: {resp.status_code}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(play_tts_on_pc())
