import logging
from typing import Dict, Any

try:
    from evdev import UInput, ecodes as e, AbsInfo
    _EVDEV_AVAILABLE = True
except ImportError:
    _EVDEV_AVAILABLE = False

class VirtualGamepad:
    def __init__(self):
        self.ui = None
        if not _EVDEV_AVAILABLE:
            logging.warning("evdev not available. Virtual Gamepad disabled.")
            return

        cap = {
            e.EV_KEY: [
                e.BTN_A, e.BTN_B, e.BTN_X, e.BTN_Y,
                e.BTN_TL, e.BTN_TR, e.BTN_SELECT, e.BTN_START,
                e.BTN_MODE, e.BTN_THUMBL, e.BTN_THUMBR,
                e.BTN_DPAD_UP, e.BTN_DPAD_DOWN, e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT
            ],
            e.EV_ABS: [
                (e.ABS_X, AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)),
                (e.ABS_Y, AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)),
                (e.ABS_RX, AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)),
                (e.ABS_RY, AbsInfo(value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0)),
                (e.ABS_Z, AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)),
                (e.ABS_RZ, AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)),
            ]
        }

        self.btn_mapping = [
            e.BTN_A, e.BTN_B, e.BTN_X, e.BTN_Y,
            e.BTN_TL, e.BTN_TR, None, None,
            e.BTN_SELECT, e.BTN_START, e.BTN_THUMBL, e.BTN_THUMBR,
            e.BTN_DPAD_UP, e.BTN_DPAD_DOWN, e.BTN_DPAD_LEFT, e.BTN_DPAD_RIGHT
        ]

        try:
            self.ui = UInput(cap, name="FoveAI Virtual Xbox Controller", vendor=0x045e, product=0x028e)
            logging.info("Virtual Gamepad created successfully (/dev/input/jsX)")
        except Exception as ex:
            logging.error(f"Failed to create Virtual Gamepad. (Need uinput permissions?): {ex}")
            self.ui = None

    def handle_payload(self, data: Dict[str, Any]):
        if not self.ui:
            return

        try:
            buttons = data.get("buttons", [])
            for i, state in enumerate(buttons):
                if i < len(self.btn_mapping) and self.btn_mapping[i] is not None:
                    self.ui.write(e.EV_KEY, self.btn_mapping[i], 1 if state else 0)
            
            ls = data.get("leftStick", [0.0, 0.0])
            rs = data.get("rightStick", [0.0, 0.0])
            self.ui.write(e.EV_ABS, e.ABS_X, int(ls[0] * 32767))
            self.ui.write(e.EV_ABS, e.ABS_Y, int(-ls[1] * 32767))
            self.ui.write(e.EV_ABS, e.ABS_RX, int(rs[0] * 32767))
            self.ui.write(e.EV_ABS, e.ABS_RY, int(-rs[1] * 32767))
            
            lt = data.get("leftTrigger", 0.0)
            rt = data.get("rightTrigger", 0.0)
            self.ui.write(e.EV_ABS, e.ABS_Z, int(lt * 255))
            self.ui.write(e.EV_ABS, e.ABS_RZ, int(rt * 255))

            self.ui.syn()
        except Exception as ex:
            logging.error(f"Virtual Gamepad error: {ex}")
