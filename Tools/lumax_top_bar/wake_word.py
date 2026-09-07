import os
import sys
import queue
import json
import threading
import urllib.request
import subprocess

try:
    import sounddevice as sd
    from vosk import Model, KaldiRecognizer
except ImportError:
    pass

class AmbientEar:
    """
    Microscopic offline wake-word listener using Vosk.
    Consumes very little RAM/CPU and runs purely locally.
    """
    def __init__(self, top_bar_instance=None):
        self.top_bar = top_bar_instance
        self.is_listening = False
        self.audio_queue = queue.Queue()
        self.model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Models", "Ears", "vosk-model-small-en-us"))
        self.samplerate = 16000
        
    def start(self):
        if not os.path.exists(self.model_path):
            print(f"[AmbientEar] Vosk model not found at {self.model_path}")
            return
            
        try:
            import sounddevice as sd
            from vosk import Model, KaldiRecognizer
        except ImportError:
            print("[AmbientEar] Vosk or sounddevice not installed.")
            return

        self.is_listening = True
        threading.Thread(target=self._listen_loop, daemon=True).start()
        print("[AmbientEar] 👂 Actively listening for 'foveai'...")

    def stop(self):
        self.is_listening = False

    def _audio_callback(self, indata, frames, time_info, status):
        """This is called by sounddevice for each audio block."""
        if status:
            print(status, file=sys.stderr)
        self.audio_queue.put(bytes(indata))

    def _listen_loop(self):
        try:
            model = Model(self.model_path)
            # Create recognizer
            recognizer = KaldiRecognizer(model, self.samplerate)
            
            with sd.RawInputStream(samplerate=self.samplerate, blocksize=8000, dtype='int16',
                                   channels=1, callback=self._audio_callback):
                while self.is_listening:
                    data = self.audio_queue.get()
                    if recognizer.AcceptWaveform(data):
                        result = json.loads(recognizer.Result())
                        text = result.get("text", "")
                        
                        if "foveai" in text.lower() or "hey foveai" in text.lower():
                            print(f"[AmbientEar] WAKE WORD DETECTED: {text}")
                            self._trigger_wake()
                            # Reset recognizer state
                            recognizer = KaldiRecognizer(model, self.samplerate)
                    else:
                        partial_result = json.loads(recognizer.PartialResult())
                        partial_text = partial_result.get("partial", "")
                        
                        if "foveai" in partial_text.lower():
                            print(f"[AmbientEar] WAKE WORD DETECTED (Partial): {partial_text}")
                            self._trigger_wake()
                            recognizer = KaldiRecognizer(model, self.samplerate)
                            
        except Exception as e:
            print(f"[AmbientEar] Listener crashed: {e}")
            self.is_listening = False

    def _trigger_wake(self):
        """Action performed when wake word is heard."""
        # 1. Play the Chime (Jen's subconscious acknowledgement)
        if self.top_bar and hasattr(self.top_bar, 'ambient_engine'):
            # Force a chime strike
            with self.top_bar.ambient_engine._lock:
                self.top_bar.ambient_engine.chime_amp = 0.15
                self.top_bar.ambient_engine.chime_duration = int(self.top_bar.ambient_engine.sample_rate * 5.0)

        # 2. Open the UI / Video Call
        # Slide down the Top Bar and then simulate a click on the video call button
        if self.top_bar:
            # Safely schedule UI update
            self.top_bar.after(10, self.top_bar.slide_down)
            self.top_bar.after(500, self.top_bar._toggle_call)
        else:
            # Fallback if running standalone
            print("🔊 [Chime Plays] 'Yes? I am here.'")

if __name__ == "__main__":
    # Test mode
    ear = AmbientEar()
    ear.start()
    try:
        import time
        while True: time.sleep(1)
    except KeyboardInterrupt:
        ear.stop()
