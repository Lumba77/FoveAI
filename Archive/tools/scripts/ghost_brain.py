import os
import sys
import time
import requests
import base64
import io
import json
import numpy as np
import threading
import collections
from dotenv import load_dotenv

FoveAI_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(FoveAI_ROOT, ".env"))

try:
    import keyboard
except ImportError:
    keyboard = None

try:
    import sounddevice as sd
    import soundfile as sf
    HAS_AUDIO = True
except ImportError:
    sd = None
    sf = None
    HAS_AUDIO = False

try:
    import torch
    HAS_TORCH = True
except ImportError:
    torch = None
    HAS_TORCH = False

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("FoveAI_MODEL_GEMINI_ID", "gemini-1.5-pro-latest")
STT_URL = "http://127.0.0.1:8001/stt"
TTS_URL = "http://127.0.0.1:8004/tts"
SAMPLE_RATE = 16000
HOTKEY = 'right ctrl'

# Wake-word / keyword activation (configurable via .env, comma-separated)
_WAKE_WORDS_RAW = os.getenv("FoveAI_GHOST_WAKE_WORDS", "hey jen,jen,okay jen,yo jen")
WAKE_WORDS = [w.strip().lower() for w in _WAKE_WORDS_RAW.split(",") if w.strip()]
WAKE_WORD_ENABLED = os.getenv("FoveAI_GHOST_WAKE_WORD_ENABLED", "true").lower() == "true"

# VAD parameters
CHUNK_SIZE = 2048 # 128ms at 16000Hz (prevents WASAPI audio buffer ticking clicks)
PRE_RECORD_BUFFER_SIZE = int(16000 / CHUNK_SIZE * 0.5) # 0.5 seconds
SILENCE_TIMEOUT_CHUNKS = int(16000 / CHUNK_SIZE * 1.5) # 1.5 seconds

class GhostBrain:
    def __init__(self, ui_callback=None):
        self.ui_callback = ui_callback
        self.is_recording = False
        self.is_speaking = False
        self.is_muted = False
        
        self.audio_buffer = []
        self.pre_buffer = collections.deque(maxlen=PRE_RECORD_BUFFER_SIZE)
        self.silence_counter = 0
        self.stream = None
        
        self._setup_gemini()
        self._setup_vad()
        
    def _setup_gemini(self):
        self.cognitive_mode = os.getenv("FoveAI_COGNITIVE_MODE", "local").lower()
        self.log(f"[GhostBrain] Cognitive Mode: {self.cognitive_mode.upper()}")
        
        if self.cognitive_mode in ["cloud", "hybrid"]:
            try:
                from google import genai
                if GEMINI_API_KEY:
                    self.gemini_client = genai.Client(api_key=GEMINI_API_KEY)
                    self.gemini_chat = self.gemini_client.chats.create(
                        model=GEMINI_MODEL,
                        config={"system_instruction": "You are Jen. A highly advanced, proactive AI companion operating at the OS level. Keep answers short, conversational, and witty."}
                    )
                    self.log(f"[GhostBrain] Gemini Cloud link established (model: {GEMINI_MODEL}).")
                else:
                    self.gemini_client = None
                    self.log("[GhostBrain] WARNING: No GEMINI_API_KEY found. Cloud link severed.")
            except ImportError:
                self.gemini_client = None
                self.log("[GhostBrain] WARNING: google-genai not installed.")
        else:
            self.gemini_client = None
            self.log("[GhostBrain] Cloud link disabled via .env. Routing strictly to local Soul Core.")

    def _setup_vad(self):
        self.log("[GhostBrain] Loading Silero VAD Neural Network...")
        try:
            # torch.hub.load downloads the model to ~/.cache/torch/hub if not present
            self.model, utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', force_reload=False, onnx=True)
            self.get_speech_timestamps = utils[0]
            self.log("[GhostBrain] VAD Loaded Successfully.")
        except Exception as e:
            self.log(f"[GhostBrain] Failed to load VAD: {e}")
            self.model = None

    def log(self, msg):
        print(msg)
        if self.ui_callback:
            self.ui_callback(msg)

    def _play_audio(self, audio_bytes):
        try:
            self.is_speaking = True # STRICT MUTE (Deafen mic during playback)
            try:
                from audio_player import play_wav_bytes
                play_wav_bytes(audio_bytes)
            except Exception:
                with io.BytesIO(audio_bytes) as audio_io:
                    data, fs = sf.read(audio_io)
                    sd.play(data, fs)
                    sd.wait()
        except Exception as e:
            self.log(f"[ERROR] Audio playback failed: {e}")
        finally:
            self.pre_buffer.clear() 
            self.is_speaking = False

    def _graceful_sleep(self, reason):
        self.log(f"[GhostBrain] Sleep triggered: {reason}")
        try:
            fallback_text = "I have lost connection to the cloud. I am going to sleep."
            tts_resp = requests.post(TTS_URL, json={"text": fallback_text}, timeout=15)
            if tts_resp.status_code == 200:
                audio_b64 = tts_resp.json().get("audio_base64", "")
                if audio_b64:
                    self._play_audio(base64.b64decode(audio_b64))
        except Exception:
            pass

    def process_interaction(self, audio_data):
        try:
            with io.BytesIO() as wav_io:
                sf.write(wav_io, audio_data, SAMPLE_RATE, format='WAV', subtype='PCM_16')
                wav_bytes = wav_io.getvalue()
            
            b64_audio = base64.b64encode(wav_bytes).decode('utf-8')
            
            self.log("[-] Thinking... (STT)")
            try:
                stt_resp = requests.post(STT_URL, json={"audio_base64": b64_audio}, timeout=10)
                stt_resp.raise_for_status()
                text = stt_resp.json().get("text", "")
            except Exception as e:
                self.log(f"[ERROR] EARS unreachable: {e}")
                return

            if not text.strip():
                return
            self.log(f"[YOU] {text}")

            # Keyword / wake-word gate: ignore speech that does not contain a wake word
            if WAKE_WORD_ENABLED:
                lower_text = text.lower()
                matched_wake = next((w for w in WAKE_WORDS if w in lower_text), None)
                if not matched_wake:
                    self.log("[GhostBrain] Wake word not detected — ignoring.")
                    return
                # Strip the wake word from the command so we don't echo it back
                text = text.lower().replace(matched_wake, "", 1).strip(" ,.-")
                self.log(f"[GhostBrain] Wake word '{matched_wake}' accepted.")

            reply_text = ""
            
            if self.cognitive_mode in ["cloud", "hybrid"] and self.gemini_client:
                self.log("[-] Contemplating... (Cloud / Hybrid)")
                try:
                    response = self.gemini_chat.send_message(text)
                    reply_text = response.text
                except Exception as e:
                    self.log(f"[ERROR] Cloud link failed: {e}")
                    self._graceful_sleep("Cloud unreachable")
                    return
            else:
                self.log("[-] Contemplating... (Foveated Proxy 8400)")
                try:
                    chat_payload = {
                        "model": os.getenv("FoveAI_MODEL_LOCAL_ID", "qwen3.5-4b-moq"),
                        "messages": [{"role": "user", "content": text}]
                    }
                    response = requests.post("http://127.0.0.1:8400/v1/chat/completions", json=chat_payload, timeout=60)
                    response.raise_for_status()
                    
                    data = response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        reply_text = data["choices"][0]["message"].get("content") or data["choices"][0]["message"].get("reasoning_content") or ""
                    elif "message" in data:
                        reply_text = data["message"].get("content", "")
                    else:
                        reply_text = data.get("response", "I heard you, but my cognitive engine returned an empty response.")
                except Exception as e:
                    self.log(f"[ERROR] Proxy link failed: {e}")
                    self._graceful_sleep("Proxy unreachable")
                    return

            self.log(f"[GHOST] {reply_text}")

            self.log("[-] Speaking... (TTS)")
            try:
                import re
                spoken_text = re.sub(r'\(thought:.*?\)', '', reply_text, flags=re.IGNORECASE | re.DOTALL)
                spoken_text = re.sub(r'\([a-zA-Z]+:.*?\)', '', spoken_text, flags=re.IGNORECASE)
                spoken_text = spoken_text.strip()
                
                if not spoken_text:
                    self.log("[GhostBrain] No spoken text generated. Skipping TTS.")
                    return
                    
                tts_resp = requests.post(TTS_URL, json={"text": spoken_text}, timeout=15)
                tts_resp.raise_for_status()
                
                content_type = tts_resp.headers.get("Content-Type", "")
                if "audio/wav" in content_type or "audio/mpeg" in content_type:
                    self._play_audio(tts_resp.content)
                else:
                    audio_b64 = tts_resp.json().get("audio_base64", "")
                    if audio_b64:
                        self._play_audio(base64.b64decode(audio_b64))
            except Exception as e:
                self.log(f"[ERROR] MOUTH unreachable: {e}")
                
            self.log("[*] Autonomous Listening Resumed...")
                
        except Exception as e:
            self.log(f"[ERROR] Interaction failed: {e}")

    def _audio_callback(self, indata, frames, time_info, status):
        # 1. Strict Mute: If she is speaking, or user pressed hotkey mute, drop everything
        if self.is_speaking or self.is_muted or self.model is None:
            return
            
        chunk = indata[:, 0].copy()
        
        # 2. VAD Detection
        try:
            tensor_chunk = torch.from_numpy(chunk).float()
            speech_prob = self.model(tensor_chunk, SAMPLE_RATE).item()
        except:
            speech_prob = 0.0
            
        is_speech = speech_prob > 0.35
        
        if is_speech:
            if not self.is_recording:
                self.log("\n[!] Speech Detected! (Recording...)")
                self.is_recording = True
                self.audio_buffer = list(self.pre_buffer) # Prepend 0.5s buffer
            
            self.audio_buffer.append(chunk)
            self.silence_counter = 0
        else:
            if self.is_recording:
                self.audio_buffer.append(chunk)
                self.silence_counter += 1
                
                # 3. Silence Timeout: End of sentence
                if self.silence_counter > SILENCE_TIMEOUT_CHUNKS:
                    self.is_recording = False
                    self.log("[*] Silence Detected. Processing...")
                    
                    final_audio = np.concatenate(self.audio_buffer, axis=0)
                    threading.Thread(target=self.process_interaction, args=(final_audio,)).start()
                    
                    self.audio_buffer = []
            else:
                self.pre_buffer.append(chunk)

    def _hotkey_listener(self):
        while True:
            try:
                keyboard.wait(HOTKEY)
                self.is_muted = not self.is_muted
                if self.is_muted:
                    self.log(f"\n[X] Muted (Press {HOTKEY} to unmute)")
                    self.pre_buffer.clear()
                else:
                    self.log(f"\n[!] Unmuted. Listening autonomously...")
                time.sleep(0.5) # Debounce
            except Exception:
                time.sleep(1)

    def start_listening(self):
        self.log(f"==============================================")
        self.log(f" 👻 GHOST BRAIN - Autonomous VAD Engine")
        self.log(f" [*] Silero Neural Network is listening.")
        self.log(f" [*] Press [{HOTKEY.upper()}] to toggle mute.")
        self.log(f"==============================================")
        
        threading.Thread(target=self._hotkey_listener, daemon=True).start()
        
        # Intelligent mic selection for Virtual Desktop / Meta Quest / RODE
        input_device = None
        try:
            devices = sd.query_devices()
            preferred_keywords = ["virtual desktop", "vdvad", "oculus", "rode", "microphone", "mic"]
            for idx, dev in enumerate(devices):
                if dev.get('max_input_channels', 0) > 0:
                    d_name = dev.get('name', '').lower()
                    if any(k in d_name for k in preferred_keywords[:4]):
                        input_device = idx
                        self.log(f" [*] Target Input Mic Matched: [{idx}] {dev.get('name')}")
                        break
        except Exception as e:
            self.log(f" [!] Mic query note: {e}")

        if HAS_AUDIO and sd:
            self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, blocksize=CHUNK_SIZE, device=input_device, callback=self._audio_callback)
            self.stream.start()
        else:
            self.log(" [!] sounddevice unavailable. Skipping audio input stream.")
        
        # Keep main thread alive
        while True:
            time.sleep(1)

    def stop_listening(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()

if __name__ == "__main__":
    brain = GhostBrain()
    brain.start_listening()
