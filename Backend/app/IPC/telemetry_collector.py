import time
import json
import os
import threading
import logging
from typing import Dict, Any

try:
    import evdev
    from evdev import ecodes as e
except ImportError:
    print("Please install evdev: pip install evdev")

try:
    import mss
    import mss.tools
except ImportError:
    print("Please install mss: pip install mss")

logging.basicConfig(level=logging.INFO)

# Dataset folder
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'Data', 'LoRA_VR_Sports')
os.makedirs(OUTPUT_DIR, exist_ok=True)

class TelemetryCollector:
    def __init__(self, fps=10):
        self.fps = fps
        self.device = self._find_controller()
        self.state = {
            "leftStick": [0.0, 0.0],
            "rightStick": [0.0, 0.0],
            "leftTrigger": 0.0,
            "rightTrigger": 0.0,
            "buttons": {
                "A": 0, "B": 0, "X": 0, "Y": 0
            }
        }
        self.running = False
        self.sct = None

    def _find_controller(self):
        devices = [evdev.InputDevice(path) for path in evdev.list_devices()]
        for dev in devices:
            if "Xbox" in dev.name or "Controller" in dev.name or "Gamepad" in dev.name:
                logging.info(f"Found Controller for Telemetry: {dev.name} at {dev.path}")
                return dev
        logging.warning("No physical controller found. Make sure it's plugged in.")
        return None

    def _input_listener_loop(self):
        if not self.device: return
        for event in self.device.read_loop():
            if event.type == e.EV_ABS:
                if event.code == e.ABS_X:
                    self.state["leftStick"][0] = event.value / 32767.0
                elif event.code == e.ABS_Y:
                    self.state["leftStick"][1] = -(event.value / 32767.0)
                elif event.code == e.ABS_RX:
                    self.state["rightStick"][0] = event.value / 32767.0
                elif event.code == e.ABS_RY:
                    self.state["rightStick"][1] = -(event.value / 32767.0)
                elif event.code == e.ABS_Z:
                    self.state["leftTrigger"] = event.value / 255.0
                elif event.code == e.ABS_RZ:
                    self.state["rightTrigger"] = event.value / 255.0
            elif event.type == e.EV_KEY:
                if event.code == e.BTN_A: self.state["buttons"]["A"] = event.value
                elif event.code == e.BTN_B: self.state["buttons"]["B"] = event.value
                elif event.code == e.BTN_X: self.state["buttons"]["X"] = event.value
                elif event.code == e.BTN_Y: self.state["buttons"]["Y"] = event.value

    def _capture_loop(self):
        self.sct = mss.mss()
        monitor = self.sct.monitors[1] # Primary monitor
        
        frame_time = 1.0 / self.fps
        logging.info(f"Starting telemetry capture loop at {self.fps} FPS")

        while self.running:
            start_time = time.time()
            ts = int(start_time * 1000)

            # 1. Grab visual state
            img = self.sct.grab(monitor)
            img_path = os.path.join(OUTPUT_DIR, f"{ts}.jpg")
            mss.tools.to_png(img.rgb, img.size, level=1, output=img_path)
            
            # 2. Grab analog input state
            current_state = json.dumps(self.state)
            json_path = os.path.join(OUTPUT_DIR, f"{ts}.json")
            with open(json_path, 'w') as f:
                f.write(current_state)

            # Throttle to desired FPS
            elapsed = time.time() - start_time
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def start(self):
        if not self.device:
            logging.error("Cannot start. No controller detected.")
            return
            
        self.running = True
        threading.Thread(target=self._input_listener_loop, daemon=True).start()
        
        try:
            self._capture_loop()
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        logging.info("Stopping telemetry capture...")
        self.running = False

if __name__ == '__main__':
    collector = TelemetryCollector(fps=10)
    collector.start()
