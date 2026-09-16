import requests
import json

LLM_URL = "http://127.0.0.1:8400/v1/chat/completions"

# Basic MIDI drum map for reference
MIDI_MAP = {
    35: "Acoustic Bass Drum",
    36: "Bass Drum 1",
    37: "Side Stick",
    38: "Acoustic Snare",
    39: "Hand Clap",
    40: "Electric Snare",
    41: "Low Floor Tom",
    42: "Closed Hi Hat",
    43: "High Floor Tom",
    44: "Pedal Hi-Hat",
    45: "Low Tom",
    46: "Open Hi-Hat",
    47: "Low-Mid Tom",
    48: "Hi-Mid Tom",
    49: "Crash Cymbal 1",
    50: "High Tom",
    51: "Ride Cymbal 1",
    52: "Chinese Cymbal",
    53: "Ride Bell",
    54: "Tambourine",
    55: "Splash Cymbal",
    56: "Cowbell",
    57: "Crash Cymbal 2",
    58: "Vibraslap"
}

def get_creative_mapping(gesture_profile, recent_gestures_count):
    """
    Sends the gesture profile to the local Foveated Memory Proxy LLM
    and returns a suggested MIDI note and rationale.
    """
    prompt = f"""
You are the AI Co-Creator for a Cyber-Drumming system.
The user is moving freely to music. They just performed a unique physical gesture with their leg.
Gesture Profile:
{gesture_profile}

This is unique gesture #{recent_gestures_count} they have invented today.

Suggest a creative MIDI drum sound (from standard General MIDI mapping 35-58) that fits this physical movement.
Provide your response strictly in the following JSON format without any markdown blocks or extra text:
{{
    "note": 49,
    "name": "Crash Cymbal 1",
    "rationale": "Because the movement was chaotic and high-energy, it feels like a heavy crash."
}}
"""
    try:
        response = requests.post(
            LLM_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer builder_bot"
            },
            json={
                "model": "local-model", 
                "messages": [
                    {"role": "system", "content": "You are a creative drumming AI co-creator."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "response_format": {"type": "json_object"}
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            result = json.loads(content)
            return result
        else:
            print(f"[AI Co-Creator] Failed to reach LLM. Status: {response.status_code}")
            return None
    except Exception as e:
        print(f"[AI Co-Creator] Exception contacting LLM: {e}")
        return None

if __name__ == "__main__":
    test_profile = "- Tracker: Left Knee\n- Speed: Very Fast\n- Depth: Large\n- Shape: Sharp Bounce"
    print("Testing AI Co-Creator...")
    res = get_creative_mapping(test_profile, 1)
    if res:
        print(f"Suggestion: {res['name']} (Note {res['note']})")
        print(f"Rationale: {res['rationale']}")
