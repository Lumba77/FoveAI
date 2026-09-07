import json
from typing import List, Dict, Any

def get_motor_tools_schema() -> List[Dict[str, Any]]:
    """Returns the OpenAI-compatible JSON schema for Jen's physical motor tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": "virtual_gamepad",
                "description": "Simulate pushing standard game controller joysticks. Use this for physical analog movement (like Xbox/PlayStation controllers). Left stick moves your body (forward/back/strafe), right stick rotates your body (spin/look).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "move_x": {
                            "type": "number",
                            "description": "Left stick X-axis (strafe left/right). Value from -1.0 to 1.0."
                        },
                        "move_y": {
                            "type": "number",
                            "description": "Left stick Y-axis (walk forward/backward). Value from -1.0 to 1.0."
                        },
                        "spin_x": {
                            "type": "number",
                            "description": "Right stick X-axis (spin/turn left/right). Value from -1.0 to 1.0."
                        },
                        "duration": {
                            "type": "number",
                            "description": "How many seconds to hold this input before springing back to neutral (e.g. 1.0, 3.5)."
                        }
                    },
                    "required": ["duration"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "walk_forward",
                "description": "Walk forward in the direction you are currently facing.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "distance": {
                            "type": "number",
                            "description": "How far to walk in meters (e.g., 0.5 to 2.0). Keep this small for natural micro-movements."
                        }
                    },
                    "required": ["distance"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "walk_to_target",
                "description": "Walk towards a specific semantic target in the room.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "The name of the target (e.g., 'sofa', 'window', 'desk', 'user')."
                        }
                    },
                    "required": ["target"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "change_emotion",
                "description": "Shift your facial expression and physical body posture.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "emotion": {
                            "type": "string",
                            "description": "The emotion to express. Valid values: happy, sad, angry, surprised, curious, thinking, neutral, calm, playful, love."
                        },
                        "intensity": {
                            "type": "number",
                            "description": "The strength of the emotion from 0.1 to 1.0."
                        }
                    },
                    "required": ["emotion"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "trigger_micro_gesture",
                "description": "Perform a small, haptically-aware body gesture to show active listening or physical presence.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "gesture": {
                            "type": "string",
                            "description": "The gesture to perform. Valid values: nod, tilt, look_away, double_take, shrug, lean_in."
                        }
                    },
                    "required": ["gesture"]
                }
            }
        }
    ]

def format_sse_motor_event(tool_name: str, arguments: Dict[str, Any]) -> str:
    """Formats a parsed tool call into a Server-Sent Event string for the frontend."""
    payload = {
        "type": "motor_action",
        "tool": tool_name,
        "args": arguments
    }
    return f"data: {json.dumps(payload)}\n\n"
